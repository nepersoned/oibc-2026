"""Independent scoring audit for frozen SM45 validation artifacts."""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoring as SC
from sm39_group_site_integration import hourly_penalties, redistribute
from sm43_group_bagging import average_site_frames

OUT = ROOT / "outputs" / "sm46"
SM45 = ROOT / "outputs" / "sm45"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def site_files(mode: str, year: int) -> list[Path]:
    suffix = "_2023" if year == 2023 else ""
    if mode == "A0":
        return [ROOT / "outputs" / f"val_sm37_noext_repro{suffix}_sites.parquet"] + [
            ROOT / "outputs" / f"val_sm41_baseseed{s}{suffix}_sites.parquet" for s in (21, 42)]
    return [ROOT / "outputs" / f"val_sm45_a1_s{s}{suffix}_sites.parquet" for s in (7, 21, 42)]


def score_candidate(pred: pd.DataFrame, comp: pd.Series, actual: pd.DataFrame, smp: pd.Series) -> dict:
    official = SC.score(pred, comp, actual, smp)["W"]
    detail = hourly_penalties(pred, actual, comp, smp)
    independent = float(detail.pen.sum())
    if not np.isclose(official, independent, rtol=0, atol=1e-5):
        raise AssertionError(f"scoring implementations disagree: {official} vs {independent}")
    g = detail.groupby(["group", "ts"], as_index=False).pen.sum()
    by_group = {k: float(v) for k, v in detail.groupby("group").pen.sum().items()}
    peak = float(detail.loc[detail.ts.dt.hour.between(11, 15), "pen"].sum())
    monthly = {str(k): float(v) for k, v in detail.groupby(detail.ts.dt.strftime("%Y-%m")).pen.sum().items()}
    return {"W": float(official), "W_by_group": by_group, "W_11_15": peak,
            "monthly_W": monthly, "independent_hourly_W": independent,
            "scored_site_hour_rows": int(len(actual))}


def evaluate_window(year: int | None, start: str, end: str, candidates: dict[str, pd.DataFrame],
                    comps: dict[str, pd.Series], sites: pd.DataFrame, smp: pd.Series) -> dict:
    actual = SC.load_actual(start, end)
    lo, hi = SC.window(start, end)
    out = {}
    for name, pred0 in candidates.items():
        pred = pred0.copy()
        pred["ts"] = SC.to_ts(pred.ts)
        pred = pred[(pred.ts >= lo) & (pred.ts <= hi)]
        out[name] = score_candidate(pred, comps[name], actual, smp)
    return out


def main() -> None:
    sites = SC.load_sites()
    smp = SC.load_smp()
    ref = SC.reference_composition(sites)
    comp = SC.read_composition(str(SM45 / "composition_a1_site_only.csv"))
    if SC.check_composition(comp, sites):
        raise ValueError(SC.check_composition(comp, sites))
    result: dict = {"experiment": "SM46 independent re-score of frozen SM45 validation artifacts",
                    "composition_sha256": sha256(SM45 / "composition_a1_site_only.csv"), "windows": {}}

    variants = ("SM41_legacy_blend", "A1_REF_blend", "A1_site_REF", "A1_site_COMP")
    comps = {"SM41_legacy_blend": ref, "A1_REF_blend": ref, "A1_site_REF": ref, "A1_site_COMP": comp}
    for year in (2023, 2024):
        a0_site = average_site_frames([pd.read_parquet(p) for p in site_files("A0", year)])
        a1_site = average_site_frames([pd.read_parquet(p) for p in site_files("A1", year)])
        group_path = ROOT / "outputs" / "sm39" / f"group_pred_{year}.parquet" if year == 2023 else ROOT / "outputs" / "sm39" / "group_pred_2024.parquet"
        # For A1, reuse the actual SM45 weekday Group prediction; for SM41, its recorded SM39 Group output.
        a1_gp_path = SM45 / f"group_a1_{year}.parquet"
        a0_gp_path = group_path
        a0_gp, a1_gp = pd.read_parquet(a0_gp_path), pd.read_parquet(a1_gp_path)
        for frame in (a0_gp, a1_gp):
            frame["ts"] = SC.to_ts(frame.ts)
        lo, hi = SC.window(f"{year}-06-01", f"{year+1}-06-01")
        ts = pd.date_range(lo, hi, freq="h")
        ts = ts.tz_localize(SC.TZ) if ts.tz is None else ts.tz_convert(SC.TZ)
        pred_a0 = redistribute(a0_site, a0_gp[["group", "ts", "pred"]], sites, ref, 0.2, ts)
        pred_a1 = redistribute(a1_site, a1_gp[["group", "ts", "pred"]], sites, ref, 0.2, ts)
        cand = {"SM41_legacy_blend": pred_a0, "A1_REF_blend": pred_a1,
                "A1_site_REF": a1_site, "A1_site_COMP": a1_site}
        start, end = f"{year}-06-01", f"{year+1}-06-01"
        result["windows"][f"{year}-{year+1}"] = evaluate_window(year, start, end, cand, comps, sites, smp)

    # Previously viewed holdout. This is a re-score, not a new independent validation.
    year = 2024
    a0_site = average_site_frames([pd.read_parquet(p) for p in site_files("A0", year)])
    a1_site = average_site_frames([pd.read_parquet(p) for p in site_files("A1", year)])
    a0_gp = pd.read_parquet(ROOT / "outputs" / "sm39" / "group_pred_2024.parquet")
    a1_gp = pd.read_parquet(SM45 / "group_a1_2024.parquet")
    for frame in (a0_gp, a1_gp):
        frame["ts"] = SC.to_ts(frame.ts)
    lo, hi = SC.window("2024-12-01", "2025-06-01")
    ts = pd.date_range(lo, hi, freq="h")
    ts = ts.tz_localize(SC.TZ) if ts.tz is None else ts.tz_convert(SC.TZ)
    a0_site = a0_site[(a0_site.ts >= lo) & (a0_site.ts <= hi)]
    a1_site = a1_site[(a1_site.ts >= lo) & (a1_site.ts <= hi)]
    a0_gp = a0_gp[(a0_gp.ts >= lo) & (a0_gp.ts <= hi)]
    a1_gp = a1_gp[(a1_gp.ts >= lo) & (a1_gp.ts <= hi)]
    cand = {
        "SM41_legacy_blend": redistribute(a0_site, a0_gp[["group", "ts", "pred"]], sites, ref, 0.2, ts),
        "A1_REF_blend": redistribute(a1_site, a1_gp[["group", "ts", "pred"]], sites, ref, 0.2, ts),
        "A1_site_REF": a1_site, "A1_site_COMP": a1_site,
    }
    result["windows"]["frozen_holdout_2024-12_to_2025-05"] = evaluate_window(
        None, "2024-12-01", "2025-06-01", cand, comps, sites, smp)
    result["composition_existing_bootstrap"] = json.loads(
        (SM45 / "composition_a1_site_only.json").read_text(encoding="utf-8"))["bootstrap"]
    (OUT / "decision_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
