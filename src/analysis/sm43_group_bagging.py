"""Compare SM41 group seed 100 against SM43 five-seed group mean."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agg_model as am
import scoring as sc
from analysis.sm39_group_site_integration import (
    block_bootstrap, hourly_penalties, redistribute, sha256,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "sm43"


def average_site_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    ps = []
    for frame in frames:
        p = frame[["site_id", "ts", "kwh"]].copy()
        p["ts"] = sc.to_ts(p.ts)
        p = p.sort_values(["site_id", "ts"]).reset_index(drop=True)
        if p.duplicated(["site_id", "ts"]).any():
            raise ValueError("duplicate site prediction keys")
        ps.append(p)
    keys = ps[0][["site_id", "ts"]]
    for p in ps[1:]:
        if not keys.equals(p[["site_id", "ts"]]):
            raise ValueError("site ensemble keys differ")
    out = ps[0].copy()
    out["kwh"] = np.mean(np.stack([p.kwh.to_numpy() for p in ps]), axis=0)
    return out


def mean_sites(paths: list[Path]) -> pd.DataFrame:
    return average_site_frames([pd.read_parquet(path) for path in paths])


def digest(path: Path) -> str:
    return sha256(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    smp = sc.load_smp()
    report: dict = {"experiment": "SM43 group-only seed bagging", "alpha": 0.2,
                    "site_seeds": [7, 21, 42], "group_control_seed": 100,
                    "group_candidate_seeds": [100, 101, 102, 103, 104],
                    "environment": {k: os.environ.get(k) for k in (
                        "OIBC_EXT_SOURCES", "OIBC_GFS", "OIBC_GEFS", "OIBC_UM", "OIBC_SPATIAL",
                        "OIBC_PHYSICS", "OIBC_SRC", "OIBC_WX2", "OIBC_SM42_FEATURES", "OIBC_CAL")},
                    "python": sys.version, "lightgbm": __import__("lightgbm").__version__,
                    "pandas": pd.__version__, "numpy": np.__version__, "years": {}}
    for year in (2023, 2024):
        suffix = "_2023" if year == 2023 else ""
        start, end = f"{year}-06-01", f"{year+1}-06-01"
        pa, pb = sc.window(start, end)
        times = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
        site_paths = [ROOT / "outputs" / f"val_sm37_noext_repro{suffix}_sites.parquet"] + [
            ROOT / "outputs" / "sm41" / f"../val_sm41_baseseed{s}{suffix}_sites.parquet" for s in (21, 42)]
        # The SM41 seed predictions live directly under outputs/.
        site_paths = [p.resolve() for p in site_paths]
        site = mean_sites(site_paths)
        actual = sc.load_actual(start, end)
        candidates = {
            "SM41_group1": pd.read_parquet(ROOT / "outputs" / "sm39" / f"group_pred_{year}.parquet"),
            "SM43_group5": pd.read_parquet(OUT / f"group_pred_{year}.parquet"),
        }
        base_detail = None
        year_result = {"hours": len(times), "observed_site_hours": len(actual), "models": {},
                       "site_seed_inputs": {str(p): digest(p) for p in site_paths},
                       "scoring_inputs": {
                           "sites_csv_sha256": digest(Path(sc.DATA) / "sites.csv"),
                           "generation_parquet_sha256": digest(Path(sc.DATA) / "train" / "generation.parquet"),
                           "smp_csv_sha256": digest(Path(sc.DATA) / "train" / "smp.csv")}}
        details = {}
        for name, gp in candidates.items():
            gp["ts"] = sc.to_ts(gp.ts)
            gp = gp.sort_values(["group", "ts"]).reset_index(drop=True)
            if len(gp) != 2 * len(times) or gp.duplicated(["group", "ts"]).any():
                raise ValueError(f"{name}: group-time grid invalid")
            pred = redistribute(site, gp, sites, comp, 0.2, times)
            pred.to_parquet(OUT / f"{year}_{name}_sites.parquet", index=False)
            detail = hourly_penalties(pred, actual, comp, smp)
            w = float(detail.pen.sum())
            api_w = float(sc.score(pred, comp, actual, smp)["W"])
            if not np.isclose(w, api_w, rtol=0, atol=1e-5):
                raise AssertionError(f"independent/scoring W mismatch {name}: {w} vs {api_w}")
            group_w = {str(k): float(v) for k, v in detail.groupby("group").pen.sum().items()}
            hourly = detail.groupby("ts").pen.sum().reindex(times, fill_value=0)
            months = detail.assign(month=detail.ts.dt.strftime("%Y-%m")).groupby("month").pen.sum()
            details[name] = (detail, hourly, months, gp)
            year_result["models"][name] = {
                "W": w, "W_11_15": float(detail.loc[detail.ts.dt.hour.between(11, 15), "pen"].sum()),
                "group_W": group_w, "monthly_W": {str(k): float(v) for k, v in months.items()},
                "site_prediction_sha256": digest(OUT / f"{year}_{name}_sites.parquet"),
                "group_prediction_sha256": digest(OUT / f"group_pred_{year}.parquet") if name == "SM43_group5" else digest(ROOT / "outputs" / "sm39" / f"group_pred_{year}.parquet"),
            }
        bdetail, bhour, bmonth, gp1 = details["SM41_group1"]
        cdetail, chour, cmonth, gp5 = details["SM43_group5"]
        delta_hour = chour.to_numpy() - bhour.to_numpy()
        delta = year_result["models"]["SM43_group5"]["W"] - year_result["models"]["SM41_group1"]["W"]
        base_w = year_result["models"]["SM41_group1"]["W"]
        year_result["delta_W"] = float(delta)
        year_result["improvement_pct"] = float(100 * (base_w - (base_w + delta)) / base_w)
        year_result["monthly_delta_W"] = {str(k): float(cmonth.get(k, 0) - bmonth.get(k, 0)) for k in bmonth.index}
        full_month_pct = [100 * (cmonth[k] / bmonth[k] - 1) for k in bmonth.index if bmonth[k] > 0]
        year_result["worst_month_change_pct"] = float(max(full_month_pct)) if full_month_pct else None
        if year == 2024:
            year_result["paired_moving_block_bootstrap"] = block_bootstrap(delta_hour, block=168, n_boot=5000, seed=7)
        # Group forecast stability and paired error correlation use observed aggregate outcomes.
        observed = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"], as_index=False).energy.sum().rename(columns={"energy": "act"})
        p1 = gp1[["group", "ts", "pred"]].rename(columns={"pred": "pred1"})
        p5 = gp5[["group", "ts", "pred"]].rename(columns={"pred": "pred5"})
        mm = observed.merge(p1, on=["group", "ts"]).merge(p5, on=["group", "ts"])
        mm["err1"] = mm.pred1 - mm.act
        mm["err5"] = mm.pred5 - mm.act
        year_result["group_forecast_mae_difference_kwh"] = float((mm.pred5 - mm.pred1).abs().mean())
        year_result["group_prediction_correlation"] = float(mm[["pred1", "pred5"]].corr().iloc[0, 1])
        year_result["group_error_correlation"] = float(mm[["err1", "err5"]].corr().iloc[0, 1])
        year_result["group_prediction_bias_kwh"] = {"seed100": float(mm.err1.mean()), "seedmean5": float(mm.err5.mean())}
        # Training CF target coverage audit: no evaluation labels enter model fitting.
        gen = am.load_gen(pa - pd.DateOffset(years=2), pa - pd.Timedelta(hours=1))
        target = am.targets(gen[gen.ts < pa], sites, comp, min_cov=0.3)
        total_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
        cov_rows = target.groupby("group").agg(rows=("cf", "size"), mean_cf=("cf", "mean"),
                                                 median_cf=("cf", "median"), cf_std=("cf", "std"),
                                                 mean_observed_cap=("cap_avail", "mean"))
        year_result["training_cf_target_audit"] = {
            "rows": int(len(target)),
            "by_group": {str(g): {"rows": int(row.rows), "mean_cf": float(row.mean_cf),
                                    "median_cf": float(row.median_cf), "cf_std": float(row.cf_std),
                                    "mean_capacity_coverage": float(row.mean_observed_cap / total_cap[g])}
                         for g, row in cov_rows.iterrows()},
            "missing_groups": [g for g in sc.GROUPS if g not in cov_rows.index],
            "target_definition": "sum observed energy / sum capacity of reporting sites; inference scales CF by fixed reference group capacity",
        }
        report["years"][str(year)] = year_result
        print(year, json.dumps(year_result, indent=2), flush=True)
    (OUT / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = []
    for yr, result in report["years"].items():
        for model, vals in result["models"].items():
            rows.append({"model": model, "year": yr, "W": vals["W"], "W_11_15": vals["W_11_15"],
                         "delta_vs_SM41": result["delta_W"] if model == "SM43_group5" else 0,
                         "change_pct_vs_SM41": result["improvement_pct"] if model == "SM43_group5" else 0})
    pd.DataFrame(rows).to_csv(OUT / "comparison.csv", index=False)


if __name__ == "__main__":
    main()
