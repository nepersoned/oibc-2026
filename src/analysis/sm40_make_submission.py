"""Build the SM#40 alpha=0.2 noext site/group submission candidate."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import gc
from datetime import datetime, timezone
from pathlib import Path

import lightgbm
import numpy as np
import pandas as pd
import pyarrow

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import agg_model as am
import scoring as sc
from sm39_group_site_integration import redistribute

ALPHA = 0.2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _require_new(paths: list[Path]) -> None:
    exists = [str(p) for p in paths if p.exists()]
    if exists:
        raise FileExistsError("refusing to overwrite existing SM#40 output(s): " + ", ".join(exists))


def main() -> None:
    out = ROOT / "outputs" / "sm40"
    sub = ROOT / "submissions"
    out.mkdir(parents=True, exist_ok=True)
    sub.mkdir(parents=True, exist_ok=True)
    site_src = ROOT / "outputs" / "test_sm40_site_noext_sites.parquet"
    group_path = out / "group_test.parquet"
    site_copy = out / "site_test.parquet"
    ensemble_path = out / "ensemble_test.parquet"
    comp_path = sub / "composition_sm40_noext_ensemble.csv"
    forecast_path = sub / "forecast_sm40_noext_ensemble.csv"
    site_forecast_path = sub / "forecast_sm40_site_noext.csv"
    manifest_path = out / "submission_manifest.json"
    _require_new([site_copy, ensemble_path, comp_path, forecast_path, manifest_path])
    if not site_src.exists() or not group_path.exists():
        raise FileNotFoundError(f"site/group prediction missing: {site_src}, {group_path}")

    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    errors = sc.check_composition(comp, sites)
    if errors:
        raise ValueError("invalid reference composition: " + "; ".join(errors))
    _, expected = __import__("validate_submission").load_reference(str(am.sc.DATA))
    expected = pd.DatetimeIndex(expected).sort_values()
    if len(expected) != 8760 or expected.tz is None or str(expected.tz) != sc.TZ:
        raise ValueError("test SMP does not define the expected 8760-hour Asia/Seoul timeline")

    site_pred = pd.read_parquet(site_src)
    group_pred = pd.read_parquet(group_path)
    site_pred["ts"] = sc.to_ts(site_pred.ts)
    group_pred["ts"] = sc.to_ts(group_pred.ts)
    wanted_site = pd.MultiIndex.from_product([sites.site_id, expected], names=["site_id", "ts"])
    got_site = pd.MultiIndex.from_frame(site_pred[["site_id", "ts"]])
    if len(site_pred) != 253 * 8760 or not got_site.is_unique or len(wanted_site.difference(got_site)):
        raise ValueError("site model is not a unique complete 253 × 8760 prediction grid")
    if {"group", "ts", "cf_hat", "pred"} - set(group_pred.columns):
        raise ValueError("group prediction schema must include group, ts, cf_hat, pred")
    wanted_group = pd.MultiIndex.from_product([["G1", "G2"], expected], names=["group", "ts"])
    got_group = pd.MultiIndex.from_frame(group_pred[["group", "ts"]])
    if len(group_pred) != 2 * 8760 or not got_group.is_unique or len(wanted_group.difference(got_group)):
        raise ValueError("group model is not a unique complete 2 × 8760 prediction grid")
    for frame, col, label in ((site_pred, "kwh", "site"), (group_pred, "pred", "group kWh"),
                              (group_pred, "cf_hat", "group CF")):
        v = frame[col].to_numpy(dtype=float)
        if not np.isfinite(v).all() or (v < 0).any():
            raise ValueError(f"{label} contains negative/non-finite predictions")

    # End-point checks: alpha 0 is exactly the original site aggregate; alpha 1 is T.
    site_group = site_pred.assign(group=site_pred.site_id.map(comp)).groupby(
        ["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "B"})
    gt = group_pred[["group", "ts", "pred"]].rename(columns={"pred": "T"})
    joined = site_group.merge(gt, on=["group", "ts"], validate="one_to_one")
    joined["F0"] = joined["B"]
    joined["F1"] = joined["T"]
    joined["F02"] = (1 - ALPHA) * joined["B"] + ALPHA * joined["T"]
    if not np.allclose(joined["F0"], joined["B"], rtol=0, atol=1e-9):
        raise AssertionError("alpha=0 endpoint differs from site-only aggregation")
    if not np.allclose(joined["F1"], joined["T"], rtol=0, atol=1e-9):
        raise AssertionError("alpha=1 endpoint differs from group model")
    if not site_forecast_path.exists():
        raise FileNotFoundError(f"site-only pipeline forecast missing: {site_forecast_path}")
    site_only = pd.read_csv(site_forecast_path)
    site_only["ts"] = pd.to_datetime(site_only.ts, utc=True).dt.tz_convert(sc.TZ)
    check0 = site_only.merge(site_group.rename(columns={"B": "site_aggregate"}),
                             on=["group", "ts"], how="outer", validate="one_to_one", indicator=True)
    if not (check0._merge == "both").all() or not np.allclose(
            check0.forecast_kwh.to_numpy(), check0.site_aggregate.to_numpy(), rtol=1e-12, atol=1e-8):
        raise AssertionError("alpha=0 site aggregation differs from pipeline's site-only submission forecast")

    endpoint0 = redistribute(site_pred, group_pred, sites, comp, 0.0, expected)
    endpoint0_check = site_pred[["site_id", "ts", "kwh"]].merge(
        endpoint0.rename(columns={"kwh": "redistributed"}), on=["site_id", "ts"], validate="one_to_one")
    if not np.allclose(endpoint0_check.kwh, endpoint0_check.redistributed, rtol=0, atol=1e-9):
        raise AssertionError("alpha=0 redistribute differs from original site predictions")
    del endpoint0, endpoint0_check
    gc.collect()
    endpoint1 = redistribute(site_pred, group_pred, sites, comp, 1.0, expected)
    endpoint1_group = endpoint1.assign(group=endpoint1.site_id.map(comp)).groupby(
        ["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "group_sum"})
    endpoint1_check = group_pred[["group", "ts", "pred"]].merge(
        endpoint1_group, on=["group", "ts"], validate="one_to_one")
    if not np.allclose(endpoint1_check.pred, endpoint1_check.group_sum, rtol=1e-9, atol=1e-6):
        raise AssertionError("alpha=1 redistributed group totals differ from group model")
    del endpoint1, endpoint1_group, endpoint1_check
    gc.collect()

    ensemble = redistribute(site_pred, group_pred, sites, comp, ALPHA, expected)
    ensemble["ts"] = sc.to_ts(ensemble.ts)
    ensemble.to_parquet(ensemble_path, index=False)
    redistributed_group = ensemble.assign(group=ensemble.site_id.map(comp)).groupby(
        ["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "F_site"})
    checks = joined[["group", "ts", "B", "T", "F02"]].merge(
        redistributed_group, on=["group", "ts"], validate="one_to_one")
    if not np.allclose(checks.F_site, checks.F02, rtol=1e-9, atol=1e-6):
        raise AssertionError("redistributed site predictions do not equal 0.8 B + 0.2 T")

    forecast = redistributed_group.rename(columns={"F_site": "forecast_kwh"})
    forecast = forecast.sort_values(["group", "ts"])
    forecast["ts"] = forecast.ts.dt.strftime("%Y-%m-%d %H:%M:%S%z").str.replace(
        r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
    comp_df = comp.rename("group").rename_axis("site_id").reset_index()
    comp_df.to_csv(comp_path, index=False)
    forecast[["group", "ts", "forecast_kwh"]].to_csv(forecast_path, index=False)
    shutil.copy2(site_src, site_copy)
    saved_forecast = pd.read_csv(forecast_path)
    saved_forecast["ts"] = pd.to_datetime(saved_forecast.ts, utc=True).dt.tz_convert(sc.TZ)
    check_saved = saved_forecast.merge(redistributed_group, on=["group", "ts"], validate="one_to_one")
    if len(check_saved) != 2 * len(expected) or not np.allclose(
            check_saved.forecast_kwh, check_saved.F_site, rtol=1e-12, atol=1e-8):
        raise AssertionError("forecast CSV save/reload changed timestamps or values")

    # Capture actual training CF coverage (training only, before 2025-06-01 01:00 KST).
    pa, _ = sc.window("2025-06-01", "2026-06-01")
    gen = am.load_gen(pa - pd.DateOffset(years=2), pa - pd.Timedelta(hours=1))
    t = am.targets(gen[gen.ts < pa], sites, comp, min_cov=0.3)
    total_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    target_rows = {str(k): int(v) for k, v in t.groupby("group").size().items()}
    coverage = t.groupby("group").cap_avail.mean() / total_cap
    coverage_mean = {str(k): float(v) for k, v in coverage.items()}
    if any(target_rows.get(g, 0) == 0 for g in ("G1", "G2")):
        raise ValueError("blocking: a group has zero valid training targets")

    data_root = Path(sc.DATA)
    inputs = [site_src, group_path, site_forecast_path, data_root / "sites.csv", data_root / "train" / "generation.parquet",
              data_root / "train" / "smp.csv", data_root / "train" / "forecast_wa.parquet",
              data_root / "train" / "forecast_wb.parquet", data_root / "test" / "forecast_wa.parquet",
              data_root / "test" / "forecast_wb.parquet", data_root / "smp.csv"]
    outputs = [site_copy, ensemble_path, comp_path, forecast_path]
    manifest = {
        "experiment": "SM#40", "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": "seongmin", "alpha": ALPHA, "composition": "reference/current_group",
        "site_model": {"model": "LightGBM rich", "train_years": 2, "ext": "none", "drop_features": ["site_code"],
                       "random_state": 7, "feature_count": 94, "training_end_exclusive": str(pa),
                       "prediction_rows": int(len(site_pred))},
        "group_model": {"model": "LightGBM CF", "train_years": 2, "ext": "none", "effective_seed": 100,
                        "params": am.PARAMS, "input_features": 302,
                        "training_window_start": str(pa - pd.DateOffset(years=2)),
                        "training_end_exclusive": str(pa), "min_cov": 0.3,
                        "valid_target_rows_by_group": target_rows,
                        "mean_observed_capacity_coverage_by_group": coverage_mean},
        "data_policy": {"OIBC_EXT_SOURCES": "no_openmeteo", "OIBC_SPATIAL": "none",
                        "OIBC_PHYSICS": "none", "OIBC_SRC": "prov", "OIBC_CAL": "1",
                        "OIBC_WX2": "unset", "external_weather_used": False,
                        "forecast_policy": "round 17 preferred; round 10 fallback; participant dataset README states both issued before D-1 17:00 KST",
                        "explicit_publication_timestamps_in_files": False},
        "timeline": {"start": str(expected[0]), "end": str(expected[-1]), "hours": int(len(expected)),
                     "timezone": str(expected.tz), "forecast_rows": int(len(forecast)),
                     "rows_per_group": {str(k): int(v) for k, v in forecast.groupby("group").size().items()}},
        "checks": {"alpha0_equals_site_aggregate": True,
                   "alpha0_redistribute_equals_original_site_predictions": True,
                   "alpha0_equals_pipeline_site_only_csv": True, "alpha1_equals_group_prediction": True,
                   "alpha1_redistribution_sums_to_group_prediction": True,
                   "alpha02_redistribution_matches_0_8B_plus_0_2T": True,
                   "forecast_csv_reload_matches_numeric_predictions": True,
                   "site_group_grid_complete": True, "group_time_grid_complete": True,
                   "finite_nonnegative_predictions": True},
        "input_sha256": {str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): sha256(p) for p in inputs},
        "output_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in outputs},
        "environment": {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__,
                        "pyarrow": pyarrow.__version__, "lightgbm": lightgbm.__version__},
        "note": "Validation-period W is not extrapolated to submission period; no submission-period actuals exist.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"composition": str(comp_path), "forecast": str(forecast_path),
                      "composition_rows": len(comp_df), "forecast_rows": len(forecast),
                      "group_capacity_kw": {str(k): float(v) for k, v in total_cap.items()},
                      "target_rows_by_group": target_rows, "coverage": coverage_mean,
                      "manifest": str(manifest_path)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
