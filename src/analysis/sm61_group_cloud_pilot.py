"""SM61: controlled Group L1 pilot with/without GFS vertical cloud layers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import agg_model as A  # noqa: E402
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

OUT = ROOT / "outputs" / "sm61"
START, END = "2024-06-01", "2025-06-01"
TRAIN_YEARS = 2
MIN_COV = 0.30  # locked from the existing Group baseline before coverage audit
SEED = 100
LAYER_COLS = ["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]
COVERAGE_BINS = [0.0, 0.30, 0.50, np.inf]
COVERAGE_LABELS = ["<0.30", "0.30–0.50", "≥0.50"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def require_env() -> None:
    if F.CAL_MODE != "weekday" or not F.USE_GFS or F.EXT_SOURCES != "no_openmeteo":
        raise RuntimeError("SM61 requires weekday calendar, GFS enabled, and Open-Meteo disabled")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM61 forbids GEFS/UM/spatial/physics sources")
    if A.SOURCE != "all" or A.WX_CUT:
        raise RuntimeError("SM61 requires the registered WA/WB + GFS features and no WX2")


def load_inputs():
    require_env()
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    fa, fb = A.forecasts("train")
    gw = A.group_weather(fa, fb, sites, comp)
    wd = A.wide(fa, fb)
    ext = F.load_ext("mean")
    if ext is None:
        raise RuntimeError("GFS external features were not loaded")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.set_index("ts")
    if not {"ext_gfs_ghi", "ext_gfs_tcc"}.issubset(ext.columns):
        raise RuntimeError("expected SM58 GFS DSWRF/TCDC-derived columns are missing")
    wd = wd.join(ext, how="left")
    layers_path = ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet"
    layers = pd.read_parquet(layers_path)
    layers["ts"] = sc.to_ts(layers.ts)
    if layers.ts.duplicated().any() or layers[LAYER_COLS].isna().any().any():
        raise ValueError("SM58 cloud-layer artifact has duplicate timestamps or missing layer values")
    layers = layers.set_index("ts")[LAYER_COLS]
    wd_b = wd.join(layers, how="left")
    # Common A/B availability: baseline GFS support and all three frozen layers.
    gfs_ok = ext.dropna(subset=["ext_gfs_ghi", "ext_gfs_tcc"]).index
    common_ts = pd.DatetimeIndex(gfs_ok.intersection(layers.index)).sort_values()
    if common_ts.has_duplicates:
        raise ValueError("duplicate common weather timestamps")
    return sites, comp, gw, wd, wd_b, ext, layers, common_ts


def target_windows(sites: pd.DataFrame, comp: pd.Series, common_ts: pd.DatetimeIndex):
    pa, pb = sc.window(START, END)
    train_a = pa - pd.DateOffset(years=TRAIN_YEARS)
    gen_train = A.load_gen(train_a, pa - pd.Timedelta(hours=1))
    t_all = A.targets(gen_train[gen_train.ts < pa], sites, comp, min_cov=0.0)
    t_common = t_all[t_all.ts.isin(common_ts) & (t_all.ts >= train_a) & (t_all.ts < pa)].copy()
    t_train = A.targets(gen_train[gen_train.ts < pa], sites, comp, min_cov=MIN_COV)
    t_train = t_train[t_train.ts.isin(common_ts)].copy()
    return pa, pb, train_a, gen_train, t_all, t_common, t_train


def quantiles(values: pd.Series) -> dict:
    if values.empty:
        return {"count": 0}
    return {"count": int(values.count()), "mean": float(values.mean()),
            "p10": float(values.quantile(.10)), "median": float(values.median()),
            "p90": float(values.quantile(.90)), "max": float(values.max())}


def audit_coverage() -> dict:
    sites, comp, gw, wd, wd_b, ext, layers, common_ts = load_inputs()
    pa, pb, train_a, gen_train, t_all, t_common, t_train = target_windows(sites, comp, common_ts)
    total_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    all_by_group = {}
    for group in sc.GROUPS:
        rows = t_all[t_all.group == group]
        common = t_common[t_common.group == group]
        train = t_train[t_train.group == group]
        all_by_group[group] = {
            "full_group_capacity_kw": float(total_cap[group]),
            "raw_observed_group_hours": int(len(rows)),
            "raw_coverage": quantiles(rows["cov"]),
            "common_weather_hours_any_coverage": int(len(common)),
            "common_coverage": quantiles(common["cov"]),
            "eligible_labels_min_cov_0_30": int(len(train)),
            "eligible_labels_by_cov_threshold": {
                str(c): int((common["cov"] >= c).sum()) for c in (.10, .30, .50)},
            "eligible_label_cf": quantiles(train["cf"]),
        }
    cov_counts = {str(c): int((t_common["cov"] >= c).sum()) for c in (.10, .30, .50)}
    common_target_days = (pd.Series(common_ts) - pd.Timedelta(hours=1)).dt.floor("D")
    supported_target_days = int(common_target_days.nunique())
    eval_gen = A.load_gen(pa, pb)
    eval_targets = A.targets(eval_gen, sites, comp, min_cov=0.0)
    eval_targets_common = eval_targets[eval_targets.ts.isin(common_ts)].copy()
    evaluation = {}
    for group in sc.GROUPS:
        rows = eval_targets_common[eval_targets_common.group == group]
        evaluation[group] = {"scored_group_hours": int(len(rows)),
                             "observed_capacity_coverage": quantiles(rows["cov"]),
                             "full_group_capacity_kw": float(total_cap[group]),
                             "mean_observed_capacity_kw": float(rows.cap_avail.mean()) if len(rows) else None}
    report = {
        "periods": {"training_start": str(train_a), "training_end_exclusive": str(pa),
                    "validation_start": str(pa), "validation_end_inclusive": str(pb)},
        "registered_min_cov": MIN_COV,
        "threshold_counts_all_groups": cov_counts,
        "training_group_support": all_by_group,
        "train_rows_after_min_cov_and_common_weather": int(len(t_train)),
        "train_timestamp_count_before_layers_and_gfs_intersection": int(t_all.ts.nunique()),
        "common_weather_timestamp_count": int(len(common_ts)),
        "common_weather_target_days": supported_target_days,
        "sm58_layer_artifact_rows": int(len(layers)),
        "sm58_layer_sha256": sha256(ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet"),
        "eval_observed_common_support": evaluation,
        "evaluation_group_hours_total": int(len(eval_targets_common)),
        "note": "Observed capacity and evaluation coverage are post-hoc scoring diagnostics only, never model inputs.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "coverage_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    prereg = {
        "experiment": "SM61", "model": "independent Group LightGBM, objective=regression_l1",
        "baseline_A": "existing agg_model Group design: WA/WB + SM58 GFS DSWRF/TCDC-derived columns + time/group/solar features",
        "candidate_B_additions": LAYER_COLS,
        "composition": "reference", "training_window": [str(train_a), str(pa)],
        "validation_window": [str(pa), str(pb)], "min_cov": MIN_COV,
        "min_cov_basis": "existing Group default and SM44 baseline; fixed before W review",
        "seed": SEED, "lightgbm_params": {**A.PARAMS, "objective": "regression_l1", "random_state": SEED},
        "common_timestamp_rule": "intersection of nonmissing SM58 GFS ext_gfs_ghi/ext_gfs_tcc timestamps and all three SM58 cloud-layer timestamps; apply to A and B",
        "evaluation_primary": "observed-capacity-scale group W: cf_hat × post-hoc observed cap_avail versus observed act, same group-hours/mask for A/B; diagnostic, not submission-scale full-capacity W",
        "coverage_bins_secondary": COVERAGE_LABELS,
        "bootstrap": "168-hour paired moving-block, 5,000 replicates only if B W < A W",
        "one_seed_only": True,
        "external_data_status": "GFS source eligibility remains CONDITIONAL per SM58; research only",
    }
    (OUT / "preregistration.json").write_text(json.dumps(prereg, indent=2), encoding="utf-8")
    return report


def fit_group_cf(train_t: pd.DataFrame, pred_idx: pd.DataFrame, gw: pd.DataFrame,
                 wd: pd.DataFrame, sites: pd.DataFrame, comp: pd.Series,
                 features: list[str]):
    dtr = A.design(train_t, gw, wd, sites, comp)
    dtr = dtr[dtr.elev > -2].copy()
    dpr = A.design(pred_idx, gw, wd, sites, comp)
    y = dtr.cf.clip(0, 1.2).astype("float32")
    model = lgb.LGBMRegressor(**{**A.PARAMS, "objective": "regression_l1", "random_state": SEED})
    model.fit(dtr[features], y)
    cf_hat = model.predict(dpr[features])
    cf_hat = np.where(dpr.elev.to_numpy() > -2, np.clip(cf_hat, 0, None), 0.0)
    pred = pred_idx[["group", "ts"]].copy()
    pred["cf_hat"] = cf_hat
    return pred, model, int(len(dtr))


def registered_feature_pair(features_b: list[str]) -> tuple[list[str], list[str]]:
    if not set(LAYER_COLS).issubset(features_b):
        raise RuntimeError("vertical cloud columns are absent from candidate Group design")
    features_a = [c for c in features_b if c not in LAYER_COLS]
    if set(features_b) - set(features_a) != set(LAYER_COLS):
        raise RuntimeError("A/B feature difference is not exactly LCDC/MCDC/HCDC")
    return features_a, features_b


def hourly_observed_capacity_w(pred: pd.DataFrame, actual_t: pd.DataFrame, smp: pd.Series) -> pd.DataFrame:
    m = actual_t[["group", "ts", "act", "cap_avail", "cov"]].merge(
        pred, on=["group", "ts"], how="left", validate="one_to_one")
    if m.cf_hat.isna().any() or not np.isfinite(m.cf_hat.to_numpy()).all():
        raise ValueError("prediction missing/non-finite on common observed group-hour mask")
    m["pred_observed_capacity"] = m.cf_hat * m.cap_avail
    m["signed_error"] = m.pred_observed_capacity - m.act
    m["weight"] = 0.1 * m.ts.map(smp).to_numpy() * sc.k_weight(m.ts)
    m["w"] = m.weight * m.signed_error.abs()
    m["target_day"] = m.ts - pd.Timedelta(hours=1)
    m["month"] = m.target_day.dt.strftime("%Y-%m")
    m["peak"] = m.ts.dt.hour.between(11, 15)
    m["coverage_bin"] = pd.cut(m["cov"], bins=COVERAGE_BINS, labels=COVERAGE_LABELS,
                                right=False, include_lowest=True)
    return m


def metric_summary(m: pd.DataFrame) -> dict:
    return {
        "W": float(m.w.sum()),
        "group_W": {str(k): float(v) for k, v in m.groupby("group", observed=False).w.sum().items()},
        "peak_W": float(m.loc[m.peak, "w"].sum()),
        "offpeak_W": float(m.loc[~m.peak, "w"].sum()),
        "monthly_W": {str(k): float(v) for k, v in m.groupby("month").w.sum().items()},
        "group_signed_bias_kwh": {str(k): float(v) for k, v in m.groupby("group").signed_error.mean().items()},
        "overall_signed_bias_kwh": float(m.signed_error.mean()),
        "coverage_bin_W": {str(k): float(v) for k, v in m.groupby("coverage_bin", observed=False).w.sum().items()},
        "coverage_bin_hours": {str(k): int(v) for k, v in m.groupby("coverage_bin", observed=False).size().items()},
        "mean_CF_abs_error": float((m.cf_hat - m.act / m.cap_avail).abs().mean()),
    }


def run_pilot(audit: dict) -> dict:
    sites, comp, gw, wd_a, wd_b, ext, layers, common_ts = load_inputs()
    pa, pb, train_a, gen_train, t_all, t_common, t_train = target_windows(sites, comp, common_ts)
    if not (t_train.groupby("group").size() > 0).all():
        raise RuntimeError("min_cov=0.30 leaves a group without training labels; stop before fitting")
    dtr_b = A.design(t_train, gw, wd_b, sites, comp)
    dtr_b = dtr_b[dtr_b.elev > -2].copy()
    features_a, features_b = registered_feature_pair(A.feats_of(dtr_b))
    dtr_a = A.design(t_train, gw, wd_a, sites, comp)
    dtr_a = dtr_a[dtr_a.elev > -2].copy()
    if not features_a == A.feats_of(dtr_a):
        raise RuntimeError("baseline Group feature list differs between A and B common rows")
    if not dtr_a[["group", "ts", "cf"]].reset_index(drop=True).equals(
            dtr_b[["group", "ts", "cf"]].reset_index(drop=True)):
        raise RuntimeError("A/B training rows or labels differ")

    eval_gen = A.load_gen(pa, pb)
    actual_t = A.targets(eval_gen, sites, comp, min_cov=0.0)
    actual_t = actual_t[actual_t.ts.isin(common_ts)].copy()
    eval_ts = pd.DatetimeIndex(actual_t.ts.unique()).sort_values()
    pred_idx = pd.MultiIndex.from_product([list(sc.GROUPS), eval_ts], names=["group", "ts"]).to_frame(index=False)
    pred_a, model_a, train_rows_a = fit_group_cf(t_train, pred_idx, gw, wd_a, sites, comp, features_a)
    pred_b, model_b, train_rows_b = fit_group_cf(t_train, pred_idx, gw, wd_b, sites, comp, features_b)
    if train_rows_a != train_rows_b:
        raise RuntimeError("A/B training row counts diverged")
    smp = sc.load_smp()
    score_a = hourly_observed_capacity_w(pred_a, actual_t, smp)
    score_b = hourly_observed_capacity_w(pred_b, actual_t, smp)
    if not score_a[["group", "ts", "act", "cap_avail", "cov"]].equals(
            score_b[["group", "ts", "act", "cap_avail", "cov"]]):
        raise RuntimeError("A/B evaluation group-hour targets/mask/capacity differ")
    group_a = score_a[["group", "ts", "pred_observed_capacity"]].rename(columns={"pred_observed_capacity": "pred"})
    group_b = score_b[["group", "ts", "pred_observed_capacity"]].rename(columns={"pred_observed_capacity": "pred"})
    w_check_a = A.group_score(group_a, actual_t, smp)
    w_check_b = A.group_score(group_b, actual_t, smp)
    if not np.isclose(w_check_a, score_a.w.sum(), rtol=0, atol=1e-6) or not np.isclose(
            w_check_b, score_b.w.sum(), rtol=0, atol=1e-6):
        raise AssertionError("agg_model.group_score does not match independent observed-capacity hourly W")
    delta = float(score_b.w.sum() - score_a.w.sum())
    bootstrap = None
    if delta < 0:
        from analysis.sm58_controlled_pilot import bootstrap_delta
        ha = score_a[["group", "ts", "w"]].copy()
        hb = score_b[["group", "ts", "w"]].copy()
        bootstrap = bootstrap_delta(ha, hb, seed=7, block=168, n_boot=5000)

    # Official full-fixed-capacity scale is retained as a diagnostic only; it is not compared to partial observed actuals.
    total_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    report = {
        "A_observed_capacity_diagnostics": metric_summary(score_a),
        "B_observed_capacity_diagnostics": metric_summary(score_b),
        "official_group_score_crosscheck": {"A": w_check_a, "B": w_check_b, "matches_hourly": True},
        "delta_B_minus_A_W": delta,
        "bootstrap_168h_5000": bootstrap,
        "train_group_hours_min_cov_0_30": {str(k): int(v) for k, v in t_train.groupby("group").size().items()},
        "fit_rows_after_daylight_filter": train_rows_a,
        "common_train_timestamp_count": int(t_train.ts.nunique()),
        "evaluation_common_timestamps": int(len(eval_ts)),
        "evaluation_observed_group_hours": int(len(actual_t)),
        "full_fixed_group_capacity_kw": {str(k): float(v) for k, v in total_cap.items()},
        "feature_counts": {"A": len(features_a), "B": len(features_b), "B_added": LAYER_COLS},
        "feature_names_A": features_a,
        "parameters": {"objective": "regression_l1", "random_state": SEED, **A.PARAMS,
                       "min_cov": MIN_COV, "train_years": TRAIN_YEARS},
        "capacity_scale_warning": "Primary W uses post-hoc observed cap_avail to place cf_hat and actual act on the same observed-capacity scale. It is not full-composition submission W; cap_avail is never a model input.",
        "regulatory_status": "GFS source remains CONDITIONAL per SM58; research only",
        "sha256": {"cloud_layers": sha256(ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet"),
                   "baseline_prediction": sha256(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet"),
                   "coverage_audit": sha256(OUT / "coverage_audit.json")},
        "versions": {"lightgbm": lgb.__version__, "pandas": pd.__version__, "numpy": np.__version__},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    pred_a.to_parquet(OUT / "group_A_predictions.parquet", index=False)
    pred_b.to_parquet(OUT / "group_B_predictions.parquet", index=False)
    report["prediction_sha256"] = {"A": sha256(OUT / "group_A_predictions.parquet"),
                                   "B": sha256(OUT / "group_B_predictions.parquet")}
    (OUT / "pilot_result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.audit == args.pilot:
        parser.error("choose exactly one of --audit or --pilot")
    OUT.mkdir(parents=True, exist_ok=True)
    if args.audit:
        print(json.dumps(audit_coverage(), indent=2), flush=True)
    else:
        prereg_path = OUT / "preregistration.json"
        if not prereg_path.exists():
            raise RuntimeError("run --audit and lock preregistration before fitting")
        audit = json.loads((OUT / "coverage_audit.json").read_text(encoding="utf-8"))
        print(json.dumps(run_pilot(audit), indent=2), flush=True)


if __name__ == "__main__":
    main()
