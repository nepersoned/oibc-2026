"""Time-forward SM59 residual calibration pilot using frozen SM45 A1-REF predictions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402
from analysis.sm39_group_site_integration import redistribute  # noqa: E402

OUT = ROOT / "outputs" / "sm59"
SEEDS = (7, 21, 42)
ALPHA_GROUP = 0.2
SUPPORT_MIN_ROWS = 500
TARGET_CLIP = 0.20
LABEL_EMBARGO_HOURS = 48
MODEL_PARAMS = {
    "objective": "regression",
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 7,
    "min_child_samples": 500,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 5.0,
    "random_state": 59,
    "n_jobs": -1,
    "verbosity": -1,
}
FEATURES = [
    "pred_cf", "log_capacity", "hour_sin", "hour_cos", "doy_sin", "doy_cos",
    "solar_elev", "wa_cloud", "wb_cloud", "wa_cloud_revision",
    "wb_cloud_revision", "wa_wb_cloud_disagreement",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_environment() -> None:
    if F.CAL_MODE != "weekday":
        raise RuntimeError("SM59 requires OIBC_CAL_MODE=weekday")
    if F.USE_GFS or F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM59 forbids GFS/GEFS/UM/spatial/physics inputs")
    if F.EXT_SOURCES != "no_openmeteo":
        raise RuntimeError("SM59 requires OIBC_EXT_SOURCES=no_openmeteo")


def load_baseline(year: int, sites: pd.DataFrame, comp: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    suffix = "_2023" if year == 2023 else ""
    site_paths = [ROOT / "outputs" / f"val_sm45_a1_s{s}{suffix}_sites.parquet" for s in SEEDS]
    group_path = ROOT / "outputs" / "sm45" / f"group_a1_{year}.parquet"
    saved_path = ROOT / "outputs" / "sm45" / f"{year}_A1_B1_site_group_20_sites.parquet"
    for path in (*site_paths, group_path, saved_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    seed_frames = []
    for path in site_paths:
        frame = pd.read_parquet(path, columns=["site_id", "ts", "kwh"])
        frame["ts"] = sc.to_ts(frame.ts)
        seed_frames.append(frame)
    site = seed_frames[0][["site_id", "ts"]].copy()
    for i, frame in enumerate(seed_frames):
        key = site.merge(frame, on=["site_id", "ts"], how="outer", validate="one_to_one")
        if len(key) != len(site) or key.kwh.isna().any():
            raise RuntimeError(f"seed {SEEDS[i]} prediction key mismatch for {year}")
        site[f"seed_{SEEDS[i]}"] = key.kwh.to_numpy()
    site["kwh"] = site[[f"seed_{s}" for s in SEEDS]].mean(axis=1)
    site = site[["site_id", "ts", "kwh"]]
    group = pd.read_parquet(group_path, columns=["group", "ts", "pred"])
    group["ts"] = sc.to_ts(group.ts)
    a, b = sc.window(f"{year}-06-01", f"{year + 1}-06-01")
    times = pd.date_range(a, b, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    regenerated = redistribute(site, group, sites, comp, ALPHA_GROUP, times)
    saved = pd.read_parquet(saved_path, columns=["site_id", "ts", "kwh"])
    saved["ts"] = sc.to_ts(saved.ts)
    cmp = regenerated.merge(saved, on=["site_id", "ts"], how="outer", suffixes=("_new", "_saved"),
                            validate="one_to_one")
    if len(cmp) != len(regenerated) or cmp.isna().any().any():
        raise RuntimeError(f"saved SM45 blend key mismatch for {year}")
    max_delta = float((cmp.kwh_new - cmp.kwh_saved).abs().max())
    if max_delta > 1e-10:
        raise RuntimeError(f"saved SM45 blend differs from frozen Site3+Group20 by {max_delta}")
    result = sc.score(regenerated, comp, sc.load_actual(f"{year}-06-01", f"{year + 1}-06-01"), sc.load_smp())
    expected = 106_673_757.09443444 if year == 2023 else 197_526_260.47453704
    if abs(result["W"] - expected) > 1e-4:
        raise RuntimeError(f"baseline W does not reproduce for {year}: {result['W']} vs {expected}")
    source_manifest = json.loads((ROOT / "outputs" / "sm45" / "comparison.json").read_text(encoding="utf-8"))
    recorded = source_manifest["years"][str(year)]["A1"]
    for path in site_paths:
        if recorded["site_prediction_inputs"].get(str(path)) != sha256(path):
            raise RuntimeError(f"SM45 comparison manifest input hash mismatch: {path}")
    if recorded["group_prediction_sha256"] != sha256(group_path):
        raise RuntimeError(f"SM45 group hash mismatch for {year}")
    if recorded["models"]["B1_site_group_20"]["site_prediction_sha256"] != sha256(saved_path):
        raise RuntimeError(f"SM45 frozen blend hash mismatch for {year}")
    meta = {"year": year, "W": float(result["W"]), "saved_prediction_max_abs_delta": max_delta,
            "actual_site_hours": len(sc.load_actual(f"{year}-06-01", f"{year + 1}-06-01")),
            "prediction_rows": len(regenerated),
            "site_seed_sha256": {str(p): sha256(p) for p in site_paths},
            "group_sha256": sha256(group_path), "blended_site_sha256": sha256(saved_path)}
    return regenerated, group, meta


def prepared_forecasts() -> tuple[pd.DataFrame, pd.DataFrame]:
    wa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    wb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    required_wa = ["wa_station", "ts", "wa_cloud", "wa_cloud_d10"]
    required_wb = ["wb_station", "ts", "wb_cloud", "wb_cloud_d10"]
    for frame, cols in ((wa, required_wa), (wb, required_wb)):
        missing = set(cols) - set(frame.columns)
        if missing:
            raise RuntimeError(f"required provided forecast columns absent: {sorted(missing)}")
        frame["ts"] = sc.to_ts(frame.ts)
    return wa[required_wa], wb[required_wb]


def build_rows(year: int, baseline: pd.DataFrame, sites: pd.DataFrame,
               wa: pd.DataFrame, wb: pd.DataFrame) -> pd.DataFrame:
    actual = sc.load_actual(f"{year}-06-01", f"{year + 1}-06-01")
    actual["ts"] = sc.to_ts(actual.ts)
    d = baseline.merge(sites[["site_id", "capacity_kw", "lat", "lon", "wa_station", "wb_station"]],
                       on="site_id", how="left", validate="many_to_one")
    d = d.merge(actual[["site_id", "ts", "energy"]], on=["site_id", "ts"], how="left", validate="one_to_one")
    d = d.merge(wa, on=["wa_station", "ts"], how="left", validate="many_to_one")
    d = d.merge(wb, on=["wb_station", "ts"], how="left", validate="many_to_one")
    elev, _, _ = F.solar(pd.DatetimeIndex(d.ts), d.lat.to_numpy(), d.lon.to_numpy())
    d["solar_elev"] = elev
    d["pred_cf"] = d.kwh / d.capacity_kw
    hour = d.ts.dt.hour.to_numpy(dtype=float)
    doy = d.ts.dt.day_of_year.to_numpy(dtype=float)
    d["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    d["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    d["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    d["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    d["log_capacity"] = np.log1p(d.capacity_kw)
    d["wa_cloud"] = d.wa_cloud / 100.0
    d["wb_cloud"] = d.wb_cloud / 100.0
    d["wa_cloud_revision"] = d.wa_cloud_d10 / 100.0
    d["wb_cloud_revision"] = d.wb_cloud_d10 / 100.0
    d["wa_wb_cloud_disagreement"] = (d.wa_cloud - d.wb_cloud) / 100.0
    d["residual_cf"] = (d.energy - d.kwh) / d.capacity_kw
    d["target_day"] = d.ts - pd.Timedelta(hours=1)
    return d


def metrics(pred: pd.DataFrame, actual: pd.DataFrame, comp: pd.Series, smp: pd.Series,
            support: pd.Series) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    m = actual[["site_id", "ts", "energy"]].merge(pred, on=["site_id", "ts"], validate="one_to_one")
    m["group"] = m.site_id.map(comp)
    m["support_band"] = m.site_id.map(support).fillna(0).astype(int)
    m["residual"] = m.kwh - m.energy
    m["weight"] = 0.1 * m.ts.map(smp) * sc.k_weight(m.ts)
    if m.weight.isna().any():
        raise RuntimeError("missing SMP settlement weight")
    m["weighted_abs"] = m.weight * m.residual.abs()
    m["over"] = m.weight * m.residual.clip(lower=0)
    m["under"] = m.weight * (-m.residual).clip(lower=0)
    g = m.groupby(["group", "ts"], as_index=False).agg(
        pred=("kwh", "sum"), actual=("energy", "sum"), residual=("residual", "sum"),
        individual_W=("weighted_abs", "sum"), weight=("weight", "first"), over_W=("over", "sum"),
        under_W=("under", "sum"), observed_sites=("site_id", "size"))
    g["W"] = g.weight * g.residual.abs()
    g["cancellation"] = g.individual_W - g.W
    g["peak"] = g.ts.dt.hour.between(11, 15)
    g["month"] = (g.ts - pd.Timedelta(hours=1)).dt.strftime("%Y-%m")
    site_mae = float(m.residual.abs().mean())
    individual = float(m.weighted_abs.sum())
    group_w = float(g.W.sum())
    summary = {
        "W": group_w,
        "W_by_group": {str(k): float(v) for k, v in g.groupby("group").W.sum().items()},
        "peak_W": float(g.loc[g.peak, "W"].sum()),
        "offpeak_W": float(g.loc[~g.peak, "W"].sum()),
        "site_MAE_kWh": site_mae,
        "site_signed_bias_kWh": float(m.residual.mean()),
        "group_signed_bias_kWh": {str(k): float(v) for k, v in g.assign(group_error=g.residual).groupby("group").group_error.mean().items()},
        "weighted_individual_W": individual,
        "cancellation_benefit_W": individual - group_w,
        "cancellation_ratio": (individual - group_w) / individual if individual else None,
        "overprediction_W": float(g.over_W.sum()),
        "underprediction_W": float(g.under_W.sum()),
        "monthly_W": {str(k): float(v) for k, v in g.groupby("month").W.sum().items()},
        "support_site_MAE": {str(k): float(v) for k, v in m.groupby("support_band").residual.apply(lambda x: x.abs().mean()).items()},
        "support_site_hours": {str(k): int(v) for k, v in m.groupby("support_band").size().items()},
        "support_weighted_individual_W": {str(k): float(v) for k, v in m.groupby("support_band").weighted_abs.sum().items()},
        "observed_site_hours": len(m), "scored_hours": int(g.ts.nunique()),
    }
    hourly = g.groupby("ts", as_index=False).W.sum().sort_values("ts")
    return summary, g, hourly


def bootstrap_delta(base_hour: pd.DataFrame, cand_hour: pd.DataFrame, seed: int = 7,
                    block: int = 168, n_boot: int = 5000) -> dict:
    pair = base_hour.merge(cand_hour, on="ts", suffixes=("_base", "_cand"), validate="one_to_one")
    if len(pair) != len(base_hour) or len(pair) != len(cand_hour):
        raise RuntimeError("bootstrap hourly keys differ")
    delta = (pair.W_cand - pair.W_base).to_numpy()
    rng = np.random.default_rng(seed)
    starts = np.arange(len(delta))
    n_blocks = int(np.ceil(len(delta) / block))
    sims = np.empty(n_boot, dtype=float)
    offset = np.arange(block)
    for b in range(n_boot):
        indices = np.concatenate([(s + offset) % len(delta) for s in rng.choice(starts, n_blocks)])[:len(delta)]
        sims[b] = delta[indices].sum()
    return {"block_hours": block, "replicates": n_boot, "seed": seed,
            "candidate_minus_baseline_mean": float(delta.sum()),
            "ci95": [float(np.quantile(sims, .025)), float(np.quantile(sims, .975))],
            "prob_delta_below_zero": float((sims < 0).mean())}


def correct_predictions(base_kwh: np.ndarray, capacity_kw: np.ndarray, delta_cf: np.ndarray,
                        daylight: np.ndarray) -> np.ndarray:
    """Apply clipped residual corrections in daylight; preserve frozen night rows exactly."""
    base_cf = np.divide(base_kwh, capacity_kw, out=np.zeros_like(base_kwh, dtype=float), where=capacity_kw > 0)
    adjusted = capacity_kw * np.clip(base_cf + np.clip(delta_cf, -TARGET_CLIP, TARGET_CLIP), 0, 1.2)
    return np.where(daylight, adjusted, base_kwh)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-only", action="store_true", help="verify frozen predictions and training support; do not fit")
    args = ap.parse_args()
    verify_environment()
    OUT.mkdir(parents=True, exist_ok=True)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    smp = sc.load_smp()
    base23, group23, meta23 = load_baseline(2023, sites, comp)
    base24, group24, meta24 = load_baseline(2024, sites, comp)
    wa, wb = prepared_forecasts()
    train = build_rows(2023, base23, sites, wa, wb)
    evaluate = build_rows(2024, base24, sites, wa, wb)
    for label, data in (("train", train), ("evaluation", evaluate)):
        miss = float(data[FEATURES].isna().any(axis=1).mean())
        if miss > .01:
            raise RuntimeError(f"{label} eligible observed rows with any missing calibration feature exceed 1%: {miss:.3%}")
    eval_start = pd.Timestamp("2024-06-01 01:00", tz=sc.TZ)
    label_cutoff = eval_start - pd.Timedelta(hours=LABEL_EMBARGO_HOURS)
    train_day = train[(train.solar_elev > 0) & train.energy.notna() & (train.ts < label_cutoff)].copy()
    counts = train_day.groupby("site_id").size()
    capacity = sites.set_index("site_id").capacity_kw
    eligible = counts[counts >= SUPPORT_MIN_ROWS].index
    if eligible.empty:
        raise RuntimeError("no calibration sites pass fixed 500-daylight-row support threshold")
    support_by_site = counts
    support_summary = {
        "all_sites_with_daylight_labels": int(len(counts)),
        "eligible_sites_min_500": int(len(eligible)),
        "eligible_sites_by_group": {g: int(sum(comp.loc[s] == g for s in eligible)) for g in ("G1", "G2")},
        "capacity_kw_by_group_all_supported": {g: float(capacity.reindex([s for s in counts.index if comp.loc[s] == g]).sum()) for g in ("G1", "G2")},
        "capacity_kw_by_group_eligible_min500": {g: float(capacity.reindex([s for s in eligible if comp.loc[s] == g]).sum()) for g in ("G1", "G2")},
        "observation_rows_per_site": {"min": int(counts.min()), "median": float(counts.median()),
                                      "p10": float(counts.quantile(.1)), "max": int(counts.max())},
        "min_support_rows": SUPPORT_MIN_ROWS,
        "label_embargo_hours": LABEL_EMBARGO_HOURS,
        "calibration_label_cutoff_exclusive": str(label_cutoff),
        "baseline_night_nonzero_train": int((train.loc[train.solar_elev <= 0, "kwh"] != 0).sum()),
        "baseline_night_nonzero_eval": int((evaluate.loc[evaluate.solar_elev <= 0, "kwh"] != 0).sum()),
        "missing_feature_row_fraction_train": float(train[FEATURES].isna().any(axis=1).mean()),
        "missing_feature_row_fraction_eval": float(evaluate[FEATURES].isna().any(axis=1).mean()),
    }
    if support_summary["eligible_sites_by_group"]["G2"] < 30:
        raise RuntimeError("G2 calibration support below fixed minimum of 30 eligible sites")
    # The frozen site+group redistribution can allocate a tiny positive night
    # forecast even though the base Site model itself clips night to zero. Keep
    # those frozen baseline rows unchanged; apply correction only for solar_elev>0.
    audit = {"experiment": "SM59 frozen baseline feasibility", "train": meta23, "evaluation": meta24,
             "support": support_summary, "features": FEATURES, "feature_source": {
                 "wa_forecast_sha256": sha256(Path(sc.DATA) / "train" / "forecast_wa.parquet"),
                 "wb_forecast_sha256": sha256(Path(sc.DATA) / "train" / "forecast_wb.parquet")},
             "calendar": F.CAL_MODE, "external_weather": False}
    (OUT / "feasibility_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2), flush=True)
    if args.audit_only:
        return

    # Fit only on mature 2023 out-of-time validation residuals; no 2024 labels enter selection or fitting.
    fit = train_day[train_day.site_id.isin(eligible)].copy()
    fit["residual_cf"] = fit.residual_cf.clip(-TARGET_CLIP, TARGET_CLIP)
    n_by_site = fit.groupby("site_id").site_id.transform("size").to_numpy(dtype=float)
    weights = 1.0 / n_by_site
    weights /= weights.mean()
    model = lgb.LGBMRegressor(**MODEL_PARAMS)
    model.fit(fit[FEATURES], fit.residual_cf, sample_weight=weights)

    baseline_eval = base24[["site_id", "ts", "kwh"]].copy()
    if not baseline_eval[["site_id", "ts"]].reset_index(drop=True).equals(
            evaluate[["site_id", "ts"]].reset_index(drop=True)):
        raise RuntimeError("evaluation feature rows are not aligned to frozen baseline predictions")
    daylight_eval = evaluate.solar_elev > 0
    correction_rows = evaluate.loc[daylight_eval, ["site_id", "ts", "capacity_kw"] + FEATURES].copy()
    raw_hat = model.predict(correction_rows[FEATURES])
    correction_rows["delta_cf"] = np.clip(raw_hat, -TARGET_CLIP, TARGET_CLIP)
    # The frozen Site+Group redistribution is the base; never apply a second Group blend.
    full_delta_cf = np.zeros(len(evaluate), dtype=float)
    full_delta_cf[daylight_eval.to_numpy()] = correction_rows.delta_cf.to_numpy(dtype=float)
    candidate_kwh = correct_predictions(
        baseline_eval.kwh.to_numpy(dtype=float), evaluate.capacity_kw.to_numpy(dtype=float),
        full_delta_cf, daylight_eval.to_numpy(dtype=bool))
    candidate = baseline_eval[["site_id", "ts"]].assign(kwh=candidate_kwh)
    if (candidate.kwh < 0).any() or not np.isfinite(candidate.kwh.to_numpy()).all():
        raise RuntimeError("candidate has invalid forecasts")
    base_actual = sc.load_actual("2024-06-01", "2025-06-01")
    base_actual["ts"] = sc.to_ts(base_actual.ts)
    base_summary, base_detail, base_hour = metrics(baseline_eval, base_actual, comp, smp, support_by_site)
    cand_summary, cand_detail, cand_hour = metrics(candidate, base_actual, comp, smp, support_by_site)
    official_base = sc.score(baseline_eval, comp, base_actual, smp)["W"]
    official_candidate = sc.score(candidate, comp, base_actual, smp)["W"]
    if not np.isclose(base_summary["W"], official_base, rtol=0, atol=1e-6):
        raise AssertionError("independent baseline W differs from scoring.py")
    if not np.isclose(cand_summary["W"], official_candidate, rtol=0, atol=1e-6):
        raise AssertionError("independent candidate W differs from scoring.py")
    delta_w = official_candidate - official_base
    result = {
        "experiment": "SM59 weather-conditioned power residual correction",
        "train_window": "2023-06-01 01:00 through 2024-05-30 00:00 KST (right-closed; 48h label embargo before evaluation)",
        "evaluation_window": "2024-06-01 01:00 through 2025-06-01 00:00 KST (right-closed)",
        "baseline_reproduction": {"2023_W": meta23["W"], "2024_W": meta24["W"]},
        "baseline": base_summary, "candidate": cand_summary, "delta_W_candidate_minus_baseline": delta_w,
        "delta_W_pct": float(100 * delta_w / official_base),
        "bootstrap": bootstrap_delta(base_hour, cand_hour) if delta_w < 0 else None,
        "support": support_summary, "features": FEATURES, "target_clip_cf": TARGET_CLIP,
        "support_min_rows": SUPPORT_MIN_ROWS, "sample_weight": "equal total weight per eligible calibration site",
        "model_params": MODEL_PARAMS, "training_rows": int(len(fit)), "training_sites": int(len(eligible)),
        "training_residual_cf_clip_fraction": float(((train_day.loc[train_day.site_id.isin(eligible), "residual_cf"] < -TARGET_CLIP) |
                                                       (train_day.loc[train_day.site_id.isin(eligible), "residual_cf"] > TARGET_CLIP)).mean()),
        "source_hashes": {
            "generation": sha256(Path(sc.DATA) / "train" / "generation.parquet"),
            "sites": sha256(Path(sc.DATA) / "sites.csv"),
            "wa_forecast": audit["feature_source"]["wa_forecast_sha256"],
            "wb_forecast": audit["feature_source"]["wb_forecast_sha256"],
            "sm45_comparison_json": sha256(ROOT / "outputs" / "sm45" / "comparison.json"),
            "script": sha256(Path(__file__).resolve()),
        },
    }
    candidate.to_parquet(OUT / "candidate_2024_sites.parquet", index=False)
    result["candidate_prediction_sha256"] = sha256(OUT / "candidate_2024_sites.parquet")
    result["baseline_prediction_sha256"] = sha256(ROOT / "outputs" / "sm45" / "2024_A1_B1_site_group_20_sites.parquet")
    result["lightgbm_version"] = lgb.__version__
    (OUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    base_detail.to_parquet(OUT / "baseline_detail_2024.parquet", index=False)
    cand_detail.to_parquet(OUT / "candidate_detail_2024.parquet", index=False)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
