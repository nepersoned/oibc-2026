"""Transfer only SM67 peak deltas onto read-only origin/main ens_v12 forecasts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import scoring as sc  # noqa: E402

OUT = ROOT / "outputs" / "sm68"
STARTING_SHA = "e0ddee1420903b9881d2ab7149a36649e63d2872"
MAIN_SHA = "793f5f6662f074dbc8e50d3b0f925b9b214c3683"
COMPOSITION_SHA = "933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463"
JH_SHA = {2023: "04065af84c4b7aef5abb26f6eec39987f6b8d7991d39a8e5ff3582c12f6af3a1",
          2024: "58388ca4328444443812116176cafdf07584f944e0ede11208524b39b95e233e"}
SM67_FEATURES = Path("outputs/sm67")
SM67_RESULT = OUT.parent / "sm67"
JH_PATHS = {
    2023: "predictions/val_2023-24/forecast_ens_v12_val.csv",
    2024: "predictions/val_2024-25/forecast_ens_v12_val.csv",
}
PERIODS = {2023: ("2023-06-01", "2024-06-01"), 2024: ("2024-06-01", "2025-06-01")}
ALPHA_SITE = 0.505
BOOT_BLOCK, BOOT_N, BOOT_SEED = 168, 5000, 68


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main_bytes(path: str) -> bytes:
    return subprocess.run(["git", "show", f"{MAIN_SHA}:{path}"], cwd=ROOT,
                          check=True, stdout=subprocess.PIPE).stdout


def bootstrap(delta_hourly: pd.Series) -> list[float]:
    d = delta_hourly.sort_index().to_numpy(dtype="float64")
    rng = np.random.default_rng(BOOT_SEED)
    n_blocks = int(np.ceil(len(d) / BOOT_BLOCK))
    starts = np.arange(len(d))
    vals = np.empty(BOOT_N)
    for i in range(BOOT_N):
        ix = np.concatenate([(s + np.arange(BOOT_BLOCK)) % len(d)
                             for s in rng.choice(starts, n_blocks)])[:len(d)]
        vals[i] = d[ix].sum()
    return [float(np.quantile(vals, .025)), float(np.quantile(vals, .975))]


def transfer_candidate(jh: pd.DataFrame, delta_group: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Apply the sole fixed transfer rule; missing SM support means leave JH unchanged."""
    pred = jh[["group", "ts", "forecast_kwh"]].rename(columns={"forecast_kwh": "A"}).copy()
    pred = pred.merge(delta_group, on=["group", "ts"], how="left", validate="one_to_one")
    supported = pred.delta.notna()
    pred["delta"] = pred.delta.fillna(0.0)
    raw = pred.A + ALPHA_SITE * pred.delta
    peak = pred.ts.dt.hour.between(11, 15)
    pred["B"] = np.where(peak, raw.clip(lower=0.0), pred.A)
    clipped = peak & raw.lt(0.0)
    if not np.isfinite(pred[["A", "B", "delta"]].to_numpy()).all():
        raise RuntimeError("nonfinite aligned transfer values")
    return pred, pd.Series({"supported": int(supported.sum()),
                            "clipped": int(clipped.sum()),
                            "changed": int(pred.B.ne(pred.A).sum()),
                            "changed_peak": int((pred.B.ne(pred.A) & peak).sum())})


def load_inputs(year: int):
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    if branch != "seongmin":
        raise RuntimeError(f"expected working branch seongmin, got {branch!r}")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", STARTING_SHA, "HEAD"], cwd=ROOT)
    if ancestor.returncode != 0:
        raise RuntimeError("current HEAD is not a descendant of the required starting revision")
    if subprocess.run(["git", "rev-parse", "origin/main"], cwd=ROOT, check=True,
                      capture_output=True, text=True).stdout.strip() != MAIN_SHA:
        raise RuntimeError("origin/main differs from the pinned read-only reference SHA")
    comp_bytes = main_bytes("predictions/submissions/composition_ens_v12.csv")
    if sha256_bytes(comp_bytes) != COMPOSITION_SHA:
        raise RuntimeError("pinned ens_v12 composition hash mismatch")
    OUT.mkdir(parents=True, exist_ok=True)
    input_dir = OUT / "pinned_main_inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    comp_path = input_dir / "composition_ens_v12.csv"
    comp_path.write_bytes(comp_bytes)
    jh_rel = JH_PATHS[year]
    jh_bytes = main_bytes(jh_rel)
    if sha256_bytes(jh_bytes) != JH_SHA[year]:
        raise RuntimeError("pinned JH forecast hash differs from SM56 artifact audit")
    jh_path = input_dir / Path(jh_rel).name
    jh_path.write_bytes(jh_bytes)
    jh = pd.read_csv(jh_path)
    required = {"group", "ts", "forecast_kwh", "site_model_kwh", "group_model_kwh"}
    if not required.issubset(jh.columns):
        raise RuntimeError(f"JH CSV schema mismatch: {jh.columns.tolist()}")
    jh["ts"] = sc.to_ts(jh.ts)
    jh["group"] = jh.group.astype(str)
    if jh.duplicated(["group", "ts"]).any() or not np.isfinite(jh[["forecast_kwh", "site_model_kwh", "group_model_kwh"]].to_numpy()).all():
        raise RuntimeError("JH prediction keys duplicate or forecasts nonfinite")
    if set(jh.group.unique()) != set(sc.GROUPS):
        raise RuntimeError("JH prediction contains unexpected groups")
    composition = pd.read_csv(comp_path).sort_values("site_id").reset_index(drop=True)
    sites = sc.load_sites()
    reference = pd.DataFrame({"site_id": sites.site_id,
                              "group": sites.current_group.map({"A": "G1", "B": "G2"})})
    if not composition.equals(reference.sort_values("site_id").reset_index(drop=True)):
        raise RuntimeError("ens_v12 composition differs from reference; no automatic remapping")
    result = json.loads((SM67_RESULT / f"result_{year}.json").read_text(encoding="utf-8"))
    base_path = ROOT / SM67_FEATURES / f"baseline_{year}_sites.parquet"
    cand_path = ROOT / SM67_FEATURES / f"candidate_{year}_sites.parquet"
    if sha256_bytes(base_path.read_bytes()) != result["prediction_hashes"]["baseline"]:
        raise RuntimeError("SM67 baseline prediction hash mismatch")
    if sha256_bytes(cand_path.read_bytes()) != result["prediction_hashes"]["candidate"]:
        raise RuntimeError("SM67 candidate prediction hash mismatch")
    base, cand = pd.read_parquet(base_path), pd.read_parquet(cand_path)
    for frame in (base, cand):
        frame["ts"] = sc.to_ts(frame.ts)
        if frame.duplicated(["site_id", "ts"]).any() or not np.isfinite(frame.kwh).all():
            raise RuntimeError("SM67 prediction keys duplicated or values nonfinite")
    keys = ["site_id", "ts"]
    if len(base) != len(cand) or not base[keys].equals(cand[keys]):
        raise RuntimeError("SM67 A/B keys differ")
    if not set(base.site_id.unique()) == set(composition.site_id):
        raise RuntimeError("SM67 site support does not include exactly the 253 composition sites")
    sites_per_hour = base.groupby("ts", sort=False).site_id.nunique()
    if not sites_per_hour.eq(253).all() or len(base) != 253 * len(sites_per_hour):
        raise RuntimeError("SM67 support timestamp has missing/duplicate site predictions")
    dsite = cand[keys].copy()
    dsite["delta"] = cand.kwh.to_numpy() - base.kwh.to_numpy()
    peak = dsite.ts.dt.hour.between(11, 15)
    if not np.equal(dsite.loc[~peak, "delta"].to_numpy(), 0.0).all():
        raise RuntimeError("SM67 contains nonzero site delta outside peak hours")
    comp_map = pd.Series(composition.group.to_numpy(), index=composition.site_id)
    dsite["group"] = dsite.site_id.map(comp_map)
    dgroup = dsite.groupby(["group", "ts"], as_index=False).delta.sum()
    period_start, period_end = PERIODS[year]
    begin, finish = sc.window(period_start, period_end)
    ts_grid = pd.date_range(begin, finish, freq="h", tz=sc.TZ)
    expected = pd.MultiIndex.from_product([sc.GROUPS, ts_grid], names=["group", "ts"])
    if set(pd.MultiIndex.from_frame(jh[["group", "ts"]])) != set(expected) or len(jh) != len(expected):
        raise RuntimeError("JH group-hour grid incomplete or outside scoring.window")
    smkeys = set(pd.MultiIndex.from_frame(dgroup[["group", "ts"]]))
    # Source support can omit hours, but every present timestamp must have both groups.
    sm_times = set(dgroup.ts.unique())
    if len(smkeys) != 2 * len(sm_times) or not set(dgroup.group.unique()) == set(sc.GROUPS):
        raise RuntimeError("SM67 support has a missing group at one or more timestamps")
    if not set(dgroup.ts).issubset(set(ts_grid)):
        raise RuntimeError("SM67 support outside JH evaluation window")
    if not dgroup.loc[dgroup.ts.dt.hour.notna() & ~dgroup.ts.dt.hour.between(11, 15), "delta"].eq(0).all():
        raise RuntimeError("group delta is nonzero outside peak hours")
    pred_grid, transfer_counts = transfer_candidate(jh, dgroup)
    support = pd.Series(False, index=pred_grid.index)
    support_idx = pd.MultiIndex.from_frame(pred_grid[["group", "ts"]]).isin(
        pd.MultiIndex.from_frame(dgroup[["group", "ts"]]))
    support.loc[:] = support_idx
    if not pred_grid.loc[~pred_grid.ts.dt.hour.between(11, 15), "A"].equals(
            pred_grid.loc[~pred_grid.ts.dt.hour.between(11, 15), "B"]):
        raise RuntimeError("nonpeak JH forecasts changed")
    actual = sc.load_actual(period_start, period_end)
    actual["ts"] = sc.to_ts(actual.ts)
    actual["group"] = actual.site_id.map(comp_map)
    ag = actual.groupby(["group", "ts"], as_index=False).agg(actual_kwh=("energy", "sum"), observed_sites=("site_id", "nunique"))
    scored = pred_grid.merge(ag, on=["group", "ts"], how="left", validate="one_to_one")
    scored["observed_sites"] = scored.observed_sites.fillna(0).astype(int)
    score = scored[scored.observed_sites.gt(0)].copy()
    smp = sc.load_smp()
    score["smp"] = score.ts.map(smp)
    if score.smp.isna().any():
        raise RuntimeError("missing SMP on scored group-hours")
    score["w"] = sc.PENALTY_RATE * score.smp * sc.k_weight(score.ts)
    for col in ("A", "B"):
        score[f"pen_{col}"] = score.w * (score[col] - score.actual_kwh).abs()
    delta_hourly = score.assign(d=lambda x: x.pen_B-x.pen_A).groupby("ts").d.sum().sort_index()
    peak = score.ts.dt.hour.between(11, 15)
    monthly = score.assign(month=(score.ts-pd.Timedelta(hours=1)).dt.strftime("%Y-%m"))
    res = {
        "year": year, "main_sha": MAIN_SHA, "jh_input_sha256": sha256_bytes(jh_bytes),
        "composition_sha256": sha256_bytes(comp_bytes),
        "sm67_baseline_sha256": result["prediction_hashes"]["baseline"],
        "sm67_candidate_sha256": result["prediction_hashes"]["candidate"],
        "sm67_support_hours": int(len(sm_times)), "sm67_delta_group_hours": int(len(dgroup)),
        "sm67_unsupported_jh_group_hours": int((~support).sum()),
        "clipped_rows": int(transfer_counts.clipped), "changed_rows": int(transfer_counts.changed),
        "changed_peak_rows": int(transfer_counts.changed_peak),
        "jh_rows": len(jh), "scored_group_hours": len(score), "observed_site_hours": len(actual),
        "observed_group_hour_coverage": {g:int(score.loc[score.group.eq(g)].shape[0]) for g in sc.GROUPS},
        "W": {c:float(score[f"pen_{c}"].sum()) for c in ("A","B")},
        "delta_W": float(score.pen_B.sum()-score.pen_A.sum()),
        "group_W": {g:{c:float(score.loc[score.group.eq(g),f"pen_{c}"].sum()) for c in ("A","B")}
                    for g in sc.GROUPS},
        "peak_W": {c:float(score.loc[peak,f"pen_{c}"].sum()) for c in ("A","B")},
        "offpeak_W": {c:float(score.loc[~peak,f"pen_{c}"].sum()) for c in ("A","B")},
        "monthly_W": {m:{c:float(g[f"pen_{c}"].sum()) for c in ("A","B")} for m,g in monthly.groupby("month")},
        "group_signed_residual_mean": {g:{c:float((score.loc[score.group.eq(g),c]-score.loc[score.group.eq(g),"actual_kwh"]).mean()) for c in ("A","B")} for g in sc.GROUPS},
        "delta_group_summary": {"mean":float(dgroup.delta.mean()),"std":float(dgroup.delta.std()),"min":float(dgroup.delta.min()),"max":float(dgroup.delta.max())},
        "delta_jh_prediction_correlation": float(pred_grid.loc[support, ["A", "delta"]].corr().iloc[0, 1]),
        "delta_supported_peak_fraction": float(dgroup.loc[dgroup.ts.dt.hour.between(11,15)].shape[0] / (2*int(ts_grid.hour.isin(range(11,16)).sum()))),
        "bootstrap_168h_ci": None,
    }
    if year == 2024:
        base_pct = (res["W"]["B"]-res["W"]["A"])/res["W"]["A"]
        res["go_2023"] = bool(base_pct <= -.005 and all(res["group_W"][g]["B"] < res["group_W"][g]["A"] for g in sc.GROUPS)
                              and res["offpeak_W"]["A"] == res["offpeak_W"]["B"])
        if res["go_2023"]:
            res["bootstrap_168h_ci"] = bootstrap(delta_hourly)
        res["recorded_sm56_A1_W"] = 167_076_206.0
        res["recomputed_vs_sm56_delta"] = res["W"]["A"] - res["recorded_sm56_A1_W"]
    return res, pred_grid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, choices=(2023,2024), required=True)
    a=p.parse_args()
    if a.year==2023:
        path=OUT/"result_2024.json"
        if not path.exists() or not json.loads(path.read_text())["go_2023"]:
            raise RuntimeError("2024 pre-fixed gate did not pass")
    result, aligned = load_inputs(a.year)
    OUT.mkdir(parents=True,exist_ok=True)
    aligned.to_parquet(OUT/f"aligned_{a.year}.parquet",index=False)
    (OUT/f"result_{a.year}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))


if __name__=="__main__":
    main()
