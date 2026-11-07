"""SM48 frozen-composition Group refit and validation diagnostic."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "sm48"
OUT.mkdir(parents=True, exist_ok=True)
COMP = ROOT / "outputs" / "sm45" / "composition_a1_site_only.csv"
COMP_SHA = "2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872"
os.environ.update({"OIBC_CAL_MODE": "weekday", "OIBC_EXT_SOURCES": "no_openmeteo", "OIBC_GFS": "0",
                   "OIBC_GEFS": "0", "OIBC_UM": "0", "OIBC_SRC": "prov", "OIBC_SPATIAL": "none",
                   "OIBC_PHYSICS": "none", "OIBC_EXT2024": "0"})
os.environ.pop("OIBC_WX2", None)
os.environ.pop("OIBC_SM42_FEATURES", None)
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import agg_model as AM  # noqa: E402
import scoring as SC  # noqa: E402
from sm39_group_site_integration import block_bootstrap, hourly_penalties, redistribute  # noqa: E402
from sm43_group_bagging import average_site_frames  # noqa: E402


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def val_site(year: int) -> pd.DataFrame:
    suffix = "_2023" if year == 2023 else ""
    paths = [ROOT / "outputs" / f"val_sm45_a1_s{s}{suffix}_sites.parquet" for s in (7, 21, 42)]
    return average_site_frames([pd.read_parquet(p) for p in paths])


def calc(pred: pd.DataFrame, comp: pd.Series, actual: pd.DataFrame, smp: pd.Series) -> dict:
    w = float(SC.score(pred, comp, actual, smp)["W"])
    d = hourly_penalties(pred, actual, comp, smp)
    wi = float(d.pen.sum())
    if not np.isclose(w, wi, rtol=0, atol=1e-5):
        raise AssertionError(f"official/independent W mismatch: {w} vs {wi}")
    return {"W": w, "W_independent_hourly": wi,
            "W_by_group": {k: float(v) for k, v in d.groupby("group").pen.sum().items()},
            "W_11_15": float(d.loc[d.ts.dt.hour.between(11, 15), "pen"].sum()),
            "W_offpeak": float(d.loc[~d.ts.dt.hour.between(11, 15), "pen"].sum()),
            "monthly_W": {str(k): float(v) for k, v in d.groupby(d.ts.dt.strftime("%Y-%m")).pen.sum().items()},
            "site_hour_rows": int(len(actual))}


def score_window(year: int, models: dict[str, pd.DataFrame], comps: dict[str, pd.Series],
                 sites: pd.DataFrame, smp: pd.Series) -> dict:
    start, end = f"{year}-06-01", f"{year+1}-06-01"
    lo, hi = SC.window(start, end)
    actual = SC.load_actual(start, end)
    return {name: calc(p[(p.ts >= lo) & (p.ts <= hi)], comps[name], actual, smp)
            for name, p in models.items()}


def main() -> None:
    if sha(COMP) != COMP_SHA:
        raise RuntimeError("frozen SM45 composition hash mismatch")
    sites, smp = SC.load_sites(), SC.load_smp()
    ref, opt = SC.reference_composition(sites), SC.read_composition(str(COMP))
    if SC.check_composition(opt, sites):
        raise RuntimeError("fixed composition is invalid: " + "; ".join(SC.check_composition(opt, sites)))

    coverage_audit: dict = {}
    trained_features: dict[str, list[str]] = {}
    original_feats_of = AM.feats_of
    def record_feats(d):
        cols = original_feats_of(d)
        bad = [c for c in cols if c in {"is_hol", "is_off", "off_run"} or c.startswith(("ext_", "phys_", "sp_", "hat_"))]
        if bad:
            raise RuntimeError(f"prohibited Group columns: {bad}")
        if not {"dow", "is_weekend"}.issubset(cols):
            raise RuntimeError("weekday features absent from Group design")
        trained_features[active_year[0]] = list(cols)
        return cols
    AM.feats_of = record_feats
    for year in (2024, 2023):
        pa, _ = SC.window(f"{year}-06-01", f"{year+1}-06-01")
        ta = pa - pd.DateOffset(years=2)
        gen = AM.load_gen(ta, pa - pd.Timedelta(hours=1))
        audit = {"train_start": str(ta), "train_end_inclusive": str(pa - pd.Timedelta(hours=1)),
                 "generation_rows": int(len(gen)), "compositions": {}}
        for label, comp in (("reference", ref), ("sm45_fixed", opt)):
            tg = AM.targets(gen, sites, comp, min_cov=0.0)
            audit["compositions"][label] = {}
            for g in SC.GROUPS:
                z = tg[tg.group == g]
                cov = z["cov"]
                audit["compositions"][label][g] = {
                    "group_hours": int(len(z)), "cov_ge_0_1": int((cov >= .1).sum()),
                    "cov_ge_0_3": int((cov >= .3).sum()), "cov_ge_0_5": int((cov >= .5).sum()),
                    "mean_cov": float(cov.mean()), "median_cov": float(cov.median()),
                }
        coverage_audit[str(year)] = audit
        gp_path = OUT / f"group_b2_{year}.parquet"
        if gp_path.exists():
            raise RuntimeError(f"refusing to overwrite existing checkpoint: {gp_path}")
        active_year = [str(year)]
        sys.argv = ["agg_model.py", "--mode", "val", "--train-years", "2", "--ext", "none",
                    "--min-cov", "0.3", "--params", "{}", "--composition", str(COMP),
                    "--val-start", f"{year}-06-01", "--val-end", f"{year+1}-06-01", "--out", str(gp_path)]
        AM.main()

    group_manifest = {str(y): {"path": str(OUT / f"group_b2_{y}.parquet"),
                               "sha256": sha(OUT / f"group_b2_{y}.parquet"),
                               "features": trained_features[str(y)]} for y in (2024, 2023)}
    models_by_year: dict[str, dict[str, pd.DataFrame]] = {}
    for year in (2024, 2023):
        lo, hi = SC.window(f"{year}-06-01", f"{year+1}-06-01")
        ts = pd.date_range(lo, hi, freq="h").tz_convert(SC.TZ)
        site = val_site(year)
        gp_new = pd.read_parquet(OUT / f"group_b2_{year}.parquet"); gp_new["ts"] = SC.to_ts(gp_new.ts)
        gp_old = pd.read_parquet(ROOT / "outputs" / "sm45" / f"group_a1_{year}.parquet"); gp_old["ts"] = SC.to_ts(gp_old.ts)
        site_ref = redistribute(site, gp_old[["group", "ts", "pred"]], sites, ref, .2, ts)
        site_comp = site.copy()
        comp_blend = redistribute(site, gp_new[["group", "ts", "pred"]], sites, opt, .2, ts)
        models_by_year[str(year)] = {"B0_A1_REF": site_ref, "B1_A1_COMP_site": site_comp, "B2_COMP_group_refit": comp_blend}
        site_ref.to_parquet(OUT / f"B0_A1_REF_{year}.parquet", index=False)
        site_comp.to_parquet(OUT / f"B1_A1_COMP_site_{year}.parquet", index=False)
        comp_blend.to_parquet(OUT / f"B2_COMP_group_refit_{year}.parquet", index=False)

    comps = {"B0_A1_REF": ref, "B1_A1_COMP_site": opt, "B2_COMP_group_refit": opt}
    results: dict = {"experiment": "SM48 composition-aware Group refit", "composition_sha256": sha(COMP),
                     "coverage_audit": coverage_audit, "group_model": {"seed": 100, "min_cov": .3,
                     "params": AM.PARAMS}, "group_predictions": group_manifest,
                     "windows": {"2023_full_retrospective": score_window(2023, models_by_year["2023"], comps, sites, smp),
                                 "2024_full_diagnostic": score_window(2024, models_by_year["2024"], comps, sites, smp)}}

    lo, hi = SC.window("2024-12-01", "2025-06-01")
    actual = SC.load_actual("2024-12-01", "2025-06-01")
    hold: dict[str, pd.DataFrame] = {}
    for name, frame in models_by_year["2024"].items():
        p = frame[(frame.ts >= lo) & (frame.ts <= hi)].copy()
        hold[name] = p
    results["windows"]["2024-12_to_2025-05_reused_holdout"] = {
        name: calc(p, comps[name], actual, smp) for name, p in hold.items()}
    hourly = {name: hourly_penalties(p, actual, comps[name], smp).groupby("ts").pen.sum()
              for name, p in hold.items()}
    deltas = {"B2_minus_B1": (hourly["B2_COMP_group_refit"] - hourly["B1_A1_COMP_site"]).to_numpy(),
              "B2_minus_B0": (hourly["B2_COMP_group_refit"] - hourly["B0_A1_REF"]).to_numpy()}
    results["bootstrap"] = {name: block_bootstrap(delta, block=168, n_boot=5000, seed=7)
                             for name, delta in deltas.items()}
    results["interpretation"] = "2023 is retrospective; 2024 full year and Dec-May holdout were previously inspected. Bootstrap does not remove selection or reuse bias."
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
