"""SM#53 support audit and fixed-configuration 2024 Site seed7 pilot scoring."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import scoring as sc
from features import solar, target_day
from sm53_profile import FEATURE_COLUMNS, MIN_PAIRED_DAYS, PROFILE_LOOKBACK_DAYS, daily_asymmetry
from sm39_group_site_integration import block_bootstrap, hourly_penalties, redistribute


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_paths() -> dict[str, Path]:
    data = Path(sc.DATA)
    return {
        "sites": data / "sites.csv",
        "generation": data / "train" / "generation.parquet",
        "wa_train": data / "train" / "forecast_wa.parquet",
        "wb_train": data / "train" / "forecast_wb.parquet",
        "smp": data / "train" / "smp.csv",
    }


def _window_support(start: str, end: str, generation: pd.DataFrame,
                    sites: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    pa, _ = sc.window(start, end)
    cutoff_day = target_day(pd.Series([pa])).iloc[0] - pd.Timedelta(days=4)
    cutoff_ts = cutoff_day + pd.Timedelta(days=1)
    train_start = cutoff_day - pd.Timedelta(days=PROFILE_LOOKBACK_DAYS - 1)
    history = generation[(generation.ts >= train_start) & (generation.ts <= cutoff_ts)].copy()
    daily = daily_asymmetry(history, sites)
    all_ids = pd.Index(sites.site_id, name="site_id")
    support = daily.groupby("site_id").profile_day.nunique().reindex(all_ids, fill_value=0)
    supported = support >= MIN_PAIRED_DAYS
    site_info = sites.set_index("site_id")
    cap = site_info.capacity_kw
    total_capacity = float(cap.sum())
    paired_bands = int(daily.paired_bands.sum()) if "paired_bands" in daily else 0
    summary = {
        "forecast_start": start,
        "first_forecast_ts": pa.isoformat(),
        "profile_history_start": train_start.isoformat(),
        "last_complete_pair_day": cutoff_day.isoformat(),
        "latest_source_ts_included": cutoff_ts.isoformat(),
        "eligible_rule": f"at least {MIN_PAIRED_DAYS} matched paired site-days",
        "paired_elevation_band_rows": paired_bands,
        "sites_with_any_profile_support": int((support > 0).sum()),
        "sites_eligible": int(supported.sum()),
        "eligible_site_fraction": float(supported.mean()),
        "capacity_with_any_support_kw": float(cap[support > 0].sum()),
        "capacity_any_support_fraction": float(cap[support > 0].sum() / total_capacity),
        "eligible_capacity_kw": float(cap[supported].sum()),
        "eligible_capacity_fraction": float(cap[supported].sum() / total_capacity),
        "support_days_quantiles": {str(q): float(support.quantile(q)) for q in (0.1, 0.5, 0.9)},
        "groups": {},
        "seasons": {},
    }
    for source_group, label in (("A", "G1"), ("B", "G2")):
        ids = site_info.index[site_info.current_group == source_group]
        group_supported = supported.reindex(ids)
        group_any = support.reindex(ids) > 0
        group_cap = cap.reindex(ids)
        summary["groups"][label] = {
            "site_count": int(len(ids)),
            "sites_any": int(group_any.sum()),
            "capacity_fraction_any": float(group_cap[group_any].sum() / group_cap.sum()),
            "sites_eligible": int(group_supported.sum()),
            "capacity_fraction_eligible": float(group_cap[group_supported].sum() / group_cap.sum()),
        }
    season_name = daily.profile_day.dt.month.map(
        lambda month: "winter" if month in (12, 1, 2) else
        "spring" if month in (3, 4, 5) else
        "summer" if month in (6, 7, 8) else "autumn") if not daily.empty else pd.Series(dtype="object")
    if not daily.empty:
        d = daily.assign(season=season_name)
        for season, group in d.groupby("season"):
            summary["seasons"][season] = {
                "paired_site_days": int(group.groupby(["site_id", "profile_day"]).ngroups),
                "paired_elevation_band_rows": int(group.paired_bands.sum()),
                "sites": int(group.site_id.nunique()),
            }
    site_rows = pd.DataFrame({
        "site_id": all_ids,
        "current_group": site_info.current_group.reindex(all_ids).to_numpy(),
        "capacity_kw": cap.reindex(all_ids).to_numpy(),
        "paired_days": support.to_numpy(dtype="int32"),
        "eligible": supported.to_numpy(dtype=bool),
    })
    return summary, site_rows, daily


def run_coverage(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = input_paths()
    sites = pd.read_csv(paths["sites"])
    generation = pd.read_parquet(paths["generation"])
    generation["ts"] = sc.to_ts(generation.ts)
    summaries, site_tables, daily_tables = {}, [], []
    for year, start, end in (
        (2023, "2023-06-01", "2024-06-01"),
        (2024, "2024-06-01", "2025-06-01"),
        (2025, "2025-06-01", "2026-06-01"),
    ):
        summary, site_rows, daily = _window_support(start, end, generation, sites)
        summaries[str(year)] = summary
        site_rows["forecast_start"] = year
        site_tables.append(site_rows)
        if not daily.empty:
            daily = daily.copy()
            daily["forecast_start"] = year
            daily_tables.append(daily)
    report = {
        "experiment": "SM53 historical generation profile support audit",
        "branch": "seongmin",
        "windows": summaries,
        "feature_definition": {
            "elevation_min_degrees": 15,
            "clear_sky_min_wm2": 250,
            "elevation_bin_degrees": 5,
            "profile_lookback_days": 730,
            "minimum_paired_days": MIN_PAIRED_DAYS,
            "shrinkage_prior_days": 30,
            "max_complete_pair_day": "target_day(first forecast ts) - 4 days",
        },
        "sha256": {key: sha256(path) for key, path in paths.items()},
    }
    (outdir / "coverage_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.concat(site_tables, ignore_index=True).to_csv(outdir / "profile_support_by_site.csv", index=False)
    if daily_tables:
        pd.concat(daily_tables, ignore_index=True).to_parquet(outdir / "paired_profile_daily_support.parquet", index=False)
    return report


def _ensure_prediction_grid(pred: pd.DataFrame, sites: pd.DataFrame, times: pd.DatetimeIndex,
                            label: str) -> pd.DataFrame:
    out = pred[["site_id", "ts", "kwh"]].copy()
    out["ts"] = sc.to_ts(out.ts)
    expected = pd.MultiIndex.from_product([sites.site_id, times], names=["site_id", "ts"])
    got = pd.MultiIndex.from_frame(out[["site_id", "ts"]])
    if len(got) != len(expected) or not got.is_unique or len(expected.difference(got)):
        raise ValueError(f"{label} prediction grid is incomplete or duplicated")
    if not np.isfinite(out.kwh.to_numpy()).all() or (out.kwh < 0).any():
        raise ValueError(f"{label} contains invalid predictions")
    return out


def _metric(pred: pd.DataFrame, actual: pd.DataFrame, comp: pd.Series,
            smp: pd.Series, support: pd.Series, sites: pd.DataFrame) -> dict:
    official = sc.score(pred, comp, actual, smp)
    detail = hourly_penalties(pred, actual, comp, smp)
    independent = float(detail.pen.sum())
    if not np.isclose(float(official["W"]), independent, atol=1e-6):
        raise AssertionError("official W and independent hourly W disagree")
    detail["month"] = detail.ts.dt.strftime("%Y-%m")
    detail["peak"] = detail.ts.dt.hour.between(11, 15)
    ref_site = sites.set_index("site_id")
    sample_ts = pd.DatetimeIndex(detail.ts.unique())
    _, representative_azim, _ = solar(
        sample_ts,
        np.full(len(sample_ts), float(ref_site.lat.median())),
        np.full(len(sample_ts), float(ref_site.lon.median())),
    )
    am_mask = np.sin(np.deg2rad(representative_azim)) >= 0
    am_by_ts = pd.Series(am_mask, index=sample_ts)
    detail["solar_side"] = np.where(detail.ts.map(am_by_ts), "morning", "afternoon")
    observed = actual[["site_id", "ts", "energy"]].copy()
    observed["ts"] = sc.to_ts(observed.ts)
    observed = observed.merge(pred[["site_id", "ts", "kwh"]], on=["site_id", "ts"], validate="one_to_one")
    site_mae = float(np.abs(observed.kwh - observed.energy).mean())
    site_bias = float((observed.kwh - observed.energy).mean())
    group_mae = float(np.abs(detail.pred - detail.act).mean())
    group_bias = float((detail.pred - detail.act).mean())
    monthly = detail.groupby("month").pen.sum().to_dict()
    by_group = detail.groupby("group").pen.sum().to_dict()
    support_flag = support.ge(MIN_PAIRED_DAYS)
    obs_info = observed[["site_id", "ts"]].merge(
        ref_site[["capacity_kw"]], left_on="site_id", right_index=True, validate="many_to_one")
    obs_info["supported_capacity"] = obs_info.capacity_kw * obs_info.site_id.map(support_flag).astype(float)
    coverage = obs_info.groupby([obs_info.site_id.map(comp).rename("group"), "ts"]).agg(
        observed_capacity=("capacity_kw", "sum"), supported_capacity=("supported_capacity", "sum")).reset_index()
    coverage["support_fraction"] = coverage.supported_capacity / coverage.observed_capacity
    detail = detail.merge(coverage[["group", "ts", "support_fraction"]], on=["group", "ts"], validate="one_to_one")
    detail["support_bucket"] = np.where(detail.support_fraction >= 0.8, "supported_capacity_ge_80pct", "supported_capacity_lt_80pct")
    support_w = detail.groupby("support_bucket").pen.sum().to_dict()
    return {
        "W": float(official["W"]),
        "W_independent_hourly": independent,
        "W_by_group": {str(k): float(v) for k, v in by_group.items()},
        "W_peak_11_15": float(detail.loc[detail.peak, "pen"].sum()),
        "W_nonpeak": float(detail.loc[~detail.peak, "pen"].sum()),
        "W_by_solar_side": {str(k): float(v) for k, v in detail.groupby("solar_side").pen.sum().items()},
        "W_by_support_bucket": {str(k): float(v) for k, v in support_w.items()},
        "monthly_W": {str(k): float(v) for k, v in monthly.items()},
        "site_MAE": site_mae,
        "site_signed_bias": site_bias,
        "group_MAE_observed_only": group_mae,
        "group_signed_bias_observed_only": group_bias,
        "group_hour_count": int(len(detail)),
        "observed_site_hour_count": int(len(observed)),
        "hourly_detail": detail,
    }


def run_score(candidate_path: Path, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    baseline_path = ROOT / "outputs" / "val_sm45_a1_s7_sites.parquet"
    group_path = ROOT / "outputs" / "sm45" / "group_a1_2024.parquet"
    if not candidate_path.exists() or not baseline_path.exists() or not group_path.exists():
        raise FileNotFoundError("candidate, baseline seed7, or frozen Group100 prediction missing")
    start, end = "2024-06-01", "2025-06-01"
    pa, pb = sc.window(start, end)
    times = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    baseline_site = _ensure_prediction_grid(pd.read_parquet(baseline_path), sites, times, "baseline seed7")
    candidate_site = _ensure_prediction_grid(pd.read_parquet(candidate_path), sites, times, "SM53 seed7")
    group = pd.read_parquet(group_path)
    group["ts"] = sc.to_ts(group.ts)
    if "pred" not in group:
        raise ValueError("frozen Group forecast has no pred column")
    baseline = redistribute(baseline_site, group[["group", "ts", "pred"]], sites, comp, 0.2, times)
    candidate = redistribute(candidate_site, group[["group", "ts", "pred"]], sites, comp, 0.2, times)
    actual = sc.load_actual(start, end)
    smp = sc.load_smp()
    paths = input_paths()
    full_generation = pd.read_parquet(paths["generation"])
    full_generation["ts"] = sc.to_ts(full_generation.ts)
    profile_cutoff = target_day(pd.Series([pa])).iloc[0] - pd.Timedelta(days=4)
    cutoff_ts = profile_cutoff + pd.Timedelta(days=1)
    train_start = profile_cutoff - pd.Timedelta(days=PROFILE_LOOKBACK_DAYS - 1)
    history = full_generation[(full_generation.ts >= train_start) & (full_generation.ts <= cutoff_ts)].copy()
    daily = daily_asymmetry(history, sites)
    support = daily.groupby("site_id").profile_day.nunique().reindex(sites.site_id, fill_value=0)
    support.index.name = "site_id"
    baseline_metrics = _metric(baseline, actual, comp, smp, support, sites)
    candidate_metrics = _metric(candidate, actual, comp, smp, support, sites)
    baseline_site_only_w = float(sc.score(baseline_site, comp, actual, smp)["W"])
    candidate_site_only_w = float(sc.score(candidate_site, comp, actual, smp)["W"])
    hourly_base = baseline_metrics.pop("hourly_detail")
    hourly_candidate = candidate_metrics.pop("hourly_detail")
    hourly_delta = (hourly_candidate.groupby("ts").pen.sum() - hourly_base.groupby("ts").pen.sum()).reindex(times, fill_value=0).fillna(0)
    result = {
        "experiment": "SM53 historical generation profile seed7 pilot",
        "period": f"{start} to {end}",
        "candidate": candidate_metrics,
        "baseline_seed7": baseline_metrics,
        "site_only_W": {
            "baseline_seed7": baseline_site_only_w,
            "candidate_sm53_seed7": candidate_site_only_w,
            "delta_candidate_minus_baseline": candidate_site_only_w - baseline_site_only_w,
        },
        "delta_candidate_minus_baseline": float(candidate_metrics["W"] - baseline_metrics["W"]),
        "relative_change_pct": float(100 * (candidate_metrics["W"] / baseline_metrics["W"] - 1)),
        "profile_support": {
            "eligible_sites": int((support >= MIN_PAIRED_DAYS).sum()),
            "eligible_capacity_kw": float(sites.set_index("site_id").loc[support[support >= MIN_PAIRED_DAYS].index, "capacity_kw"].sum()),
            "eligible_capacity_fraction": float(sites.set_index("site_id").loc[support[support >= MIN_PAIRED_DAYS].index, "capacity_kw"].sum() / sites.capacity_kw.sum()),
        },
        "configuration": {
            "site_model": "LightGBM rich; seed7; 600 estimators; learning_rate 0.06; num_leaves 127; min_child_samples 200; subsample 0.8; colsample_bytree 0.8; site_code dropped",
            "calendar_mode": "weekday",
            "ext": "none",
            "train_years": 2,
            "training_window": "2022-06-01 01:00:00+09:00 through 2024-06-01 00:00:00+09:00",
            "validation_window": "2024-06-01 01:00:00+09:00 through 2025-06-01 00:00:00+09:00",
            "group_prediction": "frozen SM45 weekday Group seed100; alpha=0.2",
            "composition": "reference; derived from provided sites.csv current_group",
            "sm53_feature_columns": FEATURE_COLUMNS,
            "sm53_profile_flag": "OIBC_SM53_PROFILE=1",
        },
        "environment": {
            "python": sys.version,
            "lightgbm": lgb.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "controls": {
                "OIBC_CAL_MODE": "weekday", "OIBC_EXT_SOURCES": "no_openmeteo",
                "OIBC_GFS": "0", "OIBC_GEFS": "0", "OIBC_UM": "0",
                "OIBC_SRC": "prov", "OIBC_SPATIAL": "none", "OIBC_PHYSICS": "none",
                "--ext": "none", "--wx": False,
            },
        },
        "bootstrap": block_bootstrap(hourly_delta.to_numpy(), block=168, n_boot=5000, seed=7)
        if candidate_metrics["W"] < baseline_metrics["W"] else "not run: primary-period point W did not improve",
        "artifacts": {
            "baseline_site_prediction": str(baseline_path.relative_to(ROOT)),
            "baseline_site_prediction_sha256": sha256(baseline_path),
            "candidate_site_prediction": str(candidate_path.relative_to(ROOT)),
            "candidate_site_prediction_sha256": sha256(candidate_path),
            "frozen_group_prediction": str(group_path.relative_to(ROOT)),
            "frozen_group_prediction_sha256": sha256(group_path),
            "baseline_blend": "outputs/sm53/baseline_blend_2024.parquet",
            "candidate_blend": "outputs/sm53/candidate_blend_2024.parquet",
        },
    }
    baseline.to_parquet(outdir / "baseline_blend_2024.parquet", index=False)
    candidate.to_parquet(outdir / "candidate_blend_2024.parquet", index=False)
    result["artifacts"]["baseline_blend_sha256"] = sha256(outdir / "baseline_blend_2024.parquet")
    result["artifacts"]["candidate_blend_sha256"] = sha256(outdir / "candidate_blend_2024.parquet")
    monthly = pd.DataFrame({
        "baseline_W": hourly_base.groupby(hourly_base.ts.dt.strftime("%Y-%m")).pen.sum(),
        "candidate_W": hourly_candidate.groupby(hourly_candidate.ts.dt.strftime("%Y-%m")).pen.sum(),
    })
    monthly["delta"] = monthly.candidate_W - monthly.baseline_W
    monthly.to_csv(outdir / "monthly_w_2024.csv", index_label="month")
    result["artifacts"]["monthly_w_sha256"] = sha256(outdir / "monthly_w_2024.csv")
    code_paths = [ROOT / "src" / p for p in (
        "features.py", "pipeline.py", "model.py", "scoring.py", "agg_model.py",
        "analysis/sm39_group_site_integration.py", "sm53_profile.py", "analysis/sm53_pilot.py")]
    result["code_sha256"] = {str(p.relative_to(ROOT)): sha256(p) for p in code_paths}
    result["input_sha256"] = {key: sha256(path) for key, path in paths.items()}
    (outdir / "pilot_2024.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["coverage", "score"], required=True)
    ap.add_argument("--candidate", default="outputs/val_sm53_profile_s7_sites.parquet")
    ap.add_argument("--outdir", default="outputs/sm53")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    if not outdir.is_absolute():
        outdir = ROOT / outdir
    if args.mode == "coverage":
        print(json.dumps(run_coverage(outdir), indent=2))
    else:
        candidate = Path(args.candidate)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        print(json.dumps(run_score(candidate, outdir), indent=2))


if __name__ == "__main__":
    main()
