"""Aggregate a SM#30 C1 feature audit from the actual rich training matrix.

This performs one reference fit only to obtain that fit's gain/split importance;
it does not score or save predictions. Output contains feature-level aggregates,
not source rows or model artifacts.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def feature_group(name: str) -> tuple[str, str, str]:
    """Return (group, source lineage, derivation) for the known C1 schema."""
    if name.startswith("wa_"):
        base = name.split("_")
        deriv = "raw selected round-17 forecast (fallback round-10)"
        if name.endswith("_r10"):
            deriv = "round-10 forecast"
        elif name.endswith("_d10"):
            deriv = "round-17 minus round-10 forecast"
        elif any(f"_{x}" in name for x in ("lag1", "lag2", "lead1", "lead2", "dmean", "daymean")):
            deriv = "within-target-day context from selected forecast"
        return "weather_a_forecast", "OIBC forecast A", deriv
    if name.startswith("wb_"):
        deriv = "raw selected round-17 forecast (fallback round-10)"
        if name.endswith("_r10"):
            deriv = "round-10 forecast"
        elif name.endswith("_d10"):
            deriv = "round-17 minus round-10 forecast"
        elif any(f"_{x}" in name for x in ("lag1", "lag2", "lead1", "lead2", "dmean", "daymean")):
            deriv = "within-target-day context from selected forecast"
        return "weather_b_forecast", "OIBC forecast B", deriv
    if name.startswith("reg_"):
        return "national_forecast_means", "OIBC forecast A/B stations", "same-timestamp station mean"
    if name.startswith("ext_"):
        suffixes = ("_dsum", "_lag1", "_lead1")
        deriv = "NOAA GFS fixed-box mean"
        if name == "ext_ghi_ens":
            deriv = "mean of available GHI sources; C1 contains GFS only"
        elif name.endswith("_dsum"):
            deriv = "target-day sum of same-source forecast"
        elif name.endswith("_lag1"):
            deriv = "previous valid-time value within target day"
        elif name.endswith("_lead1"):
            deriv = "next valid-time value within target day"
        source = "NOAA GFS direct archive (fixed box)" if name.startswith("ext_gfs_") or name == "ext_ghi_ens" or name.startswith("ext_ghi_ens_") else "derived from NOAA GFS direct archive"
        return "external_gfs", source, deriv
    if name in {"elev", "azim", "cosz", "ghi_cs", "doy_sin", "doy_cos", "hour"}:
        desc = "Haurwitz clear-sky irradiance from cosz" if name == "ghi_cs" else "NOAA solar geometry / timestamp"
        return "solar_time", desc, "deterministic timestamp and fixed site coordinates"
    if name in {"cap", "lat", "lon", "site_code"}:
        return "site_static", "competition sites.csv", "fixed site attribute / encoded ID"
    if name in {"dow", "is_hol", "is_off", "off_run"}:
        return "calendar", "Korean public holiday calendar + timestamp", "known calendar feature"
    return "unclassified", "unresolved", "inspect source code"


def source_path(group: str, feature: str) -> str:
    if group == "weather_a_forecast":
        return "data/handover 2/01_participant_dataset/train/forecast_wa.parquet; derived in src/features.py"
    if group == "weather_b_forecast":
        return "data/handover 2/01_participant_dataset/train/forecast_wb.parquet; derived in src/features.py"
    if group == "national_forecast_means":
        return "forecast_wa.parquet + forecast_wb.parquet; src/features.py:region_means"
    if group == "external_gfs":
        return "data_ext/gfs_hourly_partial_full.parquet (selected C1 cache); derived in src/features.py:load_ext"
    if group == "solar_time":
        return "timestamp + sites.csv latitude/longitude; src/features.py:solar/build_rich"
    if group == "site_static":
        return "data/handover 2/01_participant_dataset/sites.csv; site_code derived from site_id"
    if group == "calendar":
        return "timestamp + holidays.KR and src/features.py:EXTRA_OFF/calendar"
    return "unresolved"


def summary(x: pd.Series) -> dict:
    v = pd.to_numeric(x, errors="coerce")
    nonnull = v.dropna()
    return {
        "dtype": str(x.dtype),
        "n_unique": int(nonnull.nunique()),
        "missing_rate": float(v.isna().mean()),
        "mean": float(nonnull.mean()) if len(nonnull) else np.nan,
        "std": float(nonnull.std()) if len(nonnull) else np.nan,
        "min": float(nonnull.min()) if len(nonnull) else np.nan,
        "p01": float(nonnull.quantile(.01)) if len(nonnull) else np.nan,
        "p50": float(nonnull.quantile(.50)) if len(nonnull) else np.nan,
        "p99": float(nonnull.quantile(.99)) if len(nonnull) else np.nan,
        "max": float(nonnull.max()) if len(nonnull) else np.nan,
        "modal_value": float(nonnull.value_counts().index[0]) if len(nonnull) else np.nan,
        "top_value_share": float(nonnull.value_counts(normalize=True).iloc[0]) if len(nonnull) else np.nan,
    }


def frame_audit(d: pd.DataFrame, feats: list[str], label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Compare the same daylight domain used by model.fit and by nonzero prediction outputs.
    use = d.loc[d.elev > 0].copy()
    x = use[feats]
    corr = x.corr(method="pearson", min_periods=100)
    records = []
    for c in feats:
        rec = summary(x[c])
        abs_corr = corr[c].drop(labels=[c], errors="ignore").abs().dropna()
        best = abs_corr.nlargest(5)
        rec.update({
            "feature": c,
            "period": label,
            "correlated_features_abs_r_ge_0_98": json.dumps(
                {k: float(v) for k, v in abs_corr[abs_corr >= .98].sort_values(ascending=False).items()},
                ensure_ascii=False,
            ),
            "top_correlations": json.dumps({k: float(v) for k, v in best.items()}, ensure_ascii=False),
        })
        records.append(rec)
    # Temporal variability: month-level means relative to the overall feature SD.
    month = use.ts.dt.tz_localize(None).dt.to_period("M").astype(str)
    monthly = x.groupby(month, sort=True).mean(numeric_only=True)
    monthly_records = []
    for c in feats:
        vals = monthly[c].dropna()
        sd = float(x[c].std())
        spread = float(vals.max() - vals.min()) if len(vals) else np.nan
        monthly_records.append({
            "feature": c,
            f"{label}_monthly_mean_min": float(vals.min()) if len(vals) else np.nan,
            f"{label}_monthly_mean_max": float(vals.max()) if len(vals) else np.nan,
            f"{label}_monthly_mean_range_over_sd": spread / sd if sd > 0 else (0.0 if spread == 0 else np.nan),
        })
    return pd.DataFrame(records), pd.DataFrame(monthly_records)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-06-01")
    ap.add_argument("--end", default="2025-06-01")
    ap.add_argument("--train-years", type=int, default=2)
    ap.add_argument("--out", default="FEATURE_AUDIT_SM30.csv")
    args = ap.parse_args()

    # Import after environment is set by the caller.
    import features as F
    import model as M
    import pipeline as P
    import scoring as sc

    if (F.EXT_SOURCES, F.SPATIAL_MODE, F.PHYSICS_MODE) != ("no_openmeteo", "none", "none"):
        raise RuntimeError("Set OIBC_EXT_SOURCES=no_openmeteo OIBC_SPATIAL=none OIBC_PHYSICS=none")
    a, b = sc.window(args.start, args.end)
    train_a = a - pd.DateOffset(years=args.train_years)
    sites = sc.load_sites().drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    gen = P.load_generation(train_a, a)
    gen["smp"] = gen.ts.map(sc.load_smp())
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    ext = F.load_ext("mean")
    if ext is None or any(c.startswith(("ext_ecmwf", "ext_jma", "ext_icon", "ext_gem", "ext_meteofrance", "ext_cma", "ext_bom", "ext_jx")) for c in ext.columns):
        raise RuntimeError("C1 external source audit failed: unexpected Open-Meteo lineage")

    train = F.build_rich(gen[["site_id", "ts", "energy", "smp"]], sites, fa, fb, reg, ext)
    feats = F.rich_feats(train)
    if len(feats) != 105:
        raise RuntimeError(f"Expected SM#30 105 actual inputs, found {len(feats)}")
    if "ext_gfs_ghi" not in feats or "ghi_cs" not in feats:
        raise RuntimeError("Required GFS / clear-sky C1 features missing")
    train_audit, train_month = frame_audit(train, feats, "train")
    train_rows = int((train.elev > 0).sum())
    # This reference fit is solely to recover gain/split values absent from prior logs.
    fitted = M.fit(train, "none", feats=feats, params={}, cat=["site_code"])
    booster = fitted.booster_
    importance = pd.DataFrame({
        "feature": feats,
        "gain_importance": booster.feature_importance(importance_type="gain").astype(float),
        "split_importance": booster.feature_importance(importance_type="split").astype(int),
    })
    del fitted, booster, train, gen
    gc.collect()

    target = F.grid(sites.site_id, a, b)
    valid = F.build_rich(target, sites, fa, fb, reg, ext)
    valid_audit, valid_month = frame_audit(valid, feats, "validation")
    valid_rows = int(len(valid))
    valid_daylight_rows = int((valid.elev > 0).sum())
    del valid, target
    gc.collect()

    merged = train_audit.merge(valid_audit, on="feature", suffixes=("_train", "_validation"))
    merged = merged.merge(importance, on="feature", validate="one_to_one")
    merged = merged.merge(train_month, on="feature", validate="one_to_one")
    merged = merged.merge(valid_month, on="feature", validate="one_to_one")
    merged["group"], merged["lineage"], merged["derivation"] = zip(*(feature_group(c) for c in merged.feature))
    meaning_units = {
        "wa_cloud": ("cloud cover", "%"), "wa_temp": ("air temperature", "°C"),
        "wa_humidity": ("relative humidity", "%"), "wa_ground_press": ("surface pressure", "hPa"),
        "wa_wind_speed": ("wind speed", "m/s"), "wa_rain": ("precipitation", "mm"),
        "wa_snow": ("snowfall", "mm"), "wb_cloud": ("cloud cover", "%"),
        "wb_temp": ("air temperature", "°C"), "wb_dew_point": ("dew point", "°C"),
        "wb_rel_hum": ("relative humidity", "%"), "wb_uv_idx": ("UV index", "index"),
        "wb_vis": ("visibility", "km"), "wb_ceiling": ("cloud ceiling", "m"),
        "wb_precip_prob": ("precipitation probability", "%"), "wb_rain_prob": ("rain probability", "%"),
        "wb_snow_prob": ("snow probability", "%"), "wb_total_liq": ("total liquid-equivalent precipitation", "mm"),
        "wb_snow": ("snowfall", "cm"), "wb_wind_speed": ("wind speed", "km/h"),
        "wa_cloud": ("cloud cover", "%"), "wa_humidity": ("relative humidity", "%"),
        "wa_rain": ("precipitation", "mm"), "wa_wind_speed": ("wind speed", "m/s"),
        "wa_temp": ("air temperature", "°C"), "wa_ground_press": ("surface pressure", "hPa"),
        "wb_wind_speed": ("wind speed", "km/h"),
        "reg_wa_cloud": ("station-average cloud cover", "%"), "reg_wb_cloud": ("station-average cloud cover", "%"),
        "reg_wb_uv_idx": ("station-average UV index", "index"),
        "reg_wb_precip_prob": ("station-average precipitation probability", "%"),
        "elev": ("solar elevation", "degree"), "azim": ("solar azimuth", "degree"),
        "cosz": ("cosine of solar zenith", "dimensionless"), "ghi_cs": ("Haurwitz clear-sky irradiance proxy", "W/m²"),
        "doy_sin": ("annual day-of-year sine", "dimensionless"), "doy_cos": ("annual day-of-year cosine", "dimensionless"),
        "hour": ("KST valid hour", "hour"), "cap": ("installed capacity", "kW"),
        "lat": ("fixed anonymized latitude", "degree"), "lon": ("fixed anonymized longitude", "degree"),
        "site_code": ("numeric site identifier", "code"), "dow": ("target-day weekday", "0-6"),
        "is_hol": ("target-day public holiday indicator", "0/1"), "is_off": ("weekend or holiday indicator", "0/1"),
        "off_run": ("holiday/weekend adjacent-day indicator", "0/1"),
        "ext_gfs_ghi": ("GFS fixed-box hourly irradiance reconstructed from DSWRF", "W/m² approx."),
        "ext_gfs_kcs": ("GFS irradiance divided by fixed-box clear-sky proxy", "ratio"),
        "ext_gfs_tcc": ("GFS fixed-box total cloud cover", "% (source scale)"),
        "ext_ghi_ens": ("available-source GHI mean; GFS only in C1", "W/m² approx."),
    }
    def base_name(c: str) -> str:
        if c.startswith("reg_"):
            return c
        if c.startswith("ext_"):
            for suffix in ("_dsum", "_lag1", "_lead1"):
                if c.endswith(suffix):
                    return c[:-len(suffix)]
            return c
        for suffix in ("_daymean", "_dmean", "_lag1", "_lag2", "_lead1", "_lead2", "_r10", "_d10"):
            if c.endswith(suffix):
                return c[:-len(suffix)]
        return c
    meta = [meaning_units.get(base_name(c), ("forecast-derived: " + base_name(c), "source variable unit")) for c in merged.feature]
    merged["meaning"] = [x[0] for x in meta]
    merged["unit"] = [x[1] for x in meta]
    merged["source_path"] = [source_path(g, f) for g, f in zip(merged.group, merged.feature)]
    merged["openmeteo_dependency"] = False
    merged["train_rows_daylight"] = train_rows
    merged["validation_rows_daylight"] = valid_daylight_rows
    merged["validation_rows_all_hours"] = valid_rows
    merged["constant_in_train"] = merged.n_unique_train.le(1)
    merged["near_constant_in_train_mode_share_ge_0_995"] = merged.top_value_share_train.ge(.995)
    merged["mean_shift_train_sd"] = (merged.mean_validation - merged.mean_train) / merged.std_train.replace(0, np.nan)
    merged["missing_rate_delta_validation_minus_train"] = merged.missing_rate_validation - merged.missing_rate_train
    merged["gain_rank"] = merged.gain_importance.rank(method="min", ascending=False).astype(int)
    merged["split_rank"] = merged.split_importance.rank(method="min", ascending=False).astype(int)
    merged["forecast_time_status"] = np.where(
        merged.feature.str.startswith(("wa_", "wb_", "reg_")),
        "round 17 preferred / round 10 fallback; target-day convention in prep_forecast; issuance-date archive proof not included in this audit",
        np.where(merged.feature.str.startswith("ext_"),
                 "NOAA GFS D-1 00Z is intended; historical publication-time proof incomplete",
                 "deterministic/static/known calendar input; verify site metadata is fixed before submission"),
    )
    out = ROOT / args.out
    merged.sort_values(["group", "feature"]).to_csv(out, index=False, encoding="utf-8-sig")
    counts = merged.groupby("group").size().to_dict()
    summary_out = {
        "period": {"train_start": str(train_a), "train_end_exclusive": str(a), "validation_start_inclusive": str(a), "validation_end_inclusive": str(b)},
        "actual_feature_count": len(feats),
        "group_counts": counts,
        "train_rows_daylight": train_rows,
        "validation_rows": valid_rows,
        "validation_rows_daylight": valid_daylight_rows,
        "output": str(out),
        "no_openmeteo": True,
    }
    print(json.dumps(summary_out, ensure_ascii=False, indent=2))
    print(f"actual training rows={train_rows:,}; validation rows={valid_rows:,} ({valid_daylight_rows:,} daylight); feature count={len(merged)}; output={out}")


if __name__ == "__main__":
    main()
