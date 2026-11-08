"""Controlled seed-7 A/B pilot for SM#58; run only after source gates pass."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import features as F  # noqa: E402
import model as M  # noqa: E402
import pipeline as P  # noqa: E402
import scoring as sc  # noqa: E402


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def calc_hourly_w(pred: pd.DataFrame, comp: pd.Series, actual: pd.DataFrame, smp: pd.Series) -> pd.DataFrame:
    m = actual.merge(pred, on=["site_id", "ts"], how="left", validate="one_to_one")
    if m.kwh.isna().any():
        raise ValueError("prediction coverage does not match observed site-hour mask")
    m["group"] = m.site_id.map(comp)
    g = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), p=("kwh", "sum"))
    g["w"] = 0.1 * g.ts.map(smp) * sc.k_weight(g.ts) * (g.p - g.act).abs()
    return g


def summarize(pred: pd.DataFrame, comp: pd.Series, actual: pd.DataFrame,
              smp: pd.Series, group_hourly: pd.DataFrame) -> dict:
    m = actual.merge(pred, on=["site_id", "ts"], how="left", validate="one_to_one")
    m["site_abs_w"] = 0.1 * m.ts.map(smp) * sc.k_weight(m.ts) * (m.kwh - m.energy).abs()
    m["signed_error"] = m.kwh - m.energy
    g = group_hourly.copy()
    # Attribute right-closed 00:00 rows to the prior target day/month.
    g["target_day"] = g.ts - pd.Timedelta(hours=1)
    g["month"] = g.target_day.dt.strftime("%Y-%m")
    g["peak"] = g.ts.dt.hour.between(11, 15)
    individual = float(m.site_abs_w.sum())
    group_w = float(g.w.sum())
    return {
        "group_W": {k: float(v) for k, v in g.groupby("group").w.sum().items()},
        "peak_W": float(g.loc[g.peak, "w"].sum()),
        "offpeak_W": float(g.loc[~g.peak, "w"].sum()),
        "monthly_W": {k: float(v) for k, v in g.groupby("month").w.sum().items()},
        "site_MAE_kWh": float((m.kwh - m.energy).abs().mean()),
        "signed_bias_kWh": float(m.signed_error.mean()),
        "group_signed_bias_kWh": {k: float(v) for k, v in g.assign(err=g.p-g.act).groupby("group").err.mean().items()},
        "weighted_individual_W": individual,
        "cancellation_benefit_W": individual - group_w,
        "cancellation_ratio": (individual - group_w) / individual if individual else np.nan,
    }


def predict_in_batches(model, sites: pd.DataFrame, site_features: pd.DataFrame,
                      eligible_ts: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp,
                      fa: pd.DataFrame, fb: pd.DataFrame, reg: pd.DataFrame,
                      ext: pd.DataFrame, feats: list[str], batch_sites: int = 8) -> pd.DataFrame:
    pieces = []
    ids = sites.site_id.tolist()
    for offset in range(0, len(ids), batch_sites):
        group_ids = pd.Series(ids[offset:offset + batch_sites])
        base = F.grid(group_ids, start, end)
        base["ts"] = sc.to_ts(base.ts)
        base = base[base.ts.isin(eligible_ts)].copy()
        design = F.build_rich(base, site_features, fa, fb, reg, ext)
        pieces.append(base.assign(kwh=M.predict(model, design[feats])))
        del design, base
    return pd.concat(pieces, ignore_index=True)


def bootstrap_delta(hourly_a: pd.DataFrame, hourly_b: pd.DataFrame, seed: int = 7,
                    block: int = 168, n_boot: int = 5000) -> list[float]:
    a = hourly_a.groupby("ts").w.sum().sort_index().to_numpy()
    b = hourly_b.groupby("ts").w.sum().sort_index().to_numpy()
    d = b - a
    rng = np.random.default_rng(seed)
    n = len(d)
    n_blocks = int(np.ceil(n / block))
    sims = np.empty(n_boot, dtype="float64")
    starts = np.arange(n)
    for i in range(n_boot):
        idx = np.concatenate([(s + np.arange(block)) % n for s in rng.choice(starts, n_blocks)])[:n]
        sims[i] = d[idx].sum()
    return [float(np.quantile(sims, 0.025)), float(np.quantile(sims, 0.975))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layers", default="outputs/sm58/gfs_cloud_layers.parquet")
    ap.add_argument("--start", default="2024-06-01")
    ap.add_argument("--end", default="2025-06-01")
    ap.add_argument("--out", default="outputs/sm58")
    args = ap.parse_args()
    if F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise SystemExit("SM58 requires weekday calendar, GFS enabled, and Open-Meteo disabled")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise SystemExit("SM58 forbids GEFS/UM/spatial/physics external features")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pred_a, pred_b = sc.window(args.start, args.end)
    train_a = pred_a - pd.DateOffset(years=2)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    layers = pd.read_parquet(args.layers)
    layers["ts"] = sc.to_ts(layers.ts)
    if layers.ts.duplicated().any() or layers[list(c for c in layers if c != "ts")].isna().any().any():
        raise ValueError("layer features contain duplicate timestamps or missing values")
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.merge(layers, on="ts", how="inner", validate="one_to_one")
    # kcs is a clear-sky ratio and is undefined at night; preserve those NaNs
    # instead of treating dark hours as missing GFS runs or dropping them.
    required = ["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens",
                "gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]
    ext = ext.dropna(subset=required).sort_values("ts")
    eligible_ts = pd.DatetimeIndex(ext.ts)
    if eligible_ts.empty:
        raise ValueError("no common eligible GFS/layer hours")
    train_source_ts = eligible_ts[(eligible_ts >= train_a) & (eligible_ts < pred_a)]
    expected_train_hours = int((pred_a - train_a).total_seconds() // 3600)
    if len(train_source_ts) < int(np.ceil(0.95 * expected_train_hours)):
        raise ValueError("common-source training timestamp support below preregistered 95%")

    gen = P.load_generation(train_a, pred_a)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(eligible_ts)].copy()
    gen["smp"] = gen.ts.map(sc.load_smp())
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    train_base = gen[["site_id", "ts", "energy", "smp"]]
    d_train = F.build_rich(train_base, site_features, fa, fb, reg, ext)
    layer_columns = ["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]
    features_b = [f for f in P.select_rich_features(d_train) if f != "site_code"]
    features_a = [f for f in features_b if f not in layer_columns]
    if not all(c in features_b for c in layer_columns):
        raise ValueError("candidate layer columns are not present in the feature matrix")
    d_train = d_train.dropna(subset=["energy"])
    model_a = M.fit(d_train, weight="none", feats=features_a, params={"random_state": 7}, cat=[])
    site_a = predict_in_batches(model_a, sites, site_features, eligible_ts, pred_a, pred_b,
                                fa, fb, reg, ext, features_a)
    del model_a
    model_b = M.fit(d_train, weight="none", feats=features_b, params={"random_state": 7}, cat=[])
    site_b = predict_in_batches(model_b, sites, site_features, eligible_ts, pred_a, pred_b,
                                fa, fb, reg, ext, features_b)
    del model_b, d_train
    pa = site_a[["site_id", "ts", "kwh"]]
    pb = site_b[["site_id", "ts", "kwh"]]
    actual = sc.load_actual(args.start, args.end)
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual[actual.ts.isin(eligible_ts)]
    smp = sc.load_smp()
    official_a = sc.score(pa, comp, actual, smp)
    official_b = sc.score(pb, comp, actual, smp)
    hourly_a = calc_hourly_w(pa, comp, actual, smp)
    hourly_b = calc_hourly_w(pb, comp, actual, smp)
    independent_a, independent_b = float(hourly_a.w.sum()), float(hourly_b.w.sum())
    if not np.isclose(independent_a, official_a["W"], rtol=0, atol=1e-6):
        raise AssertionError("independent baseline W does not match scoring.py")
    if not np.isclose(independent_b, official_b["W"], rtol=0, atol=1e-6):
        raise AssertionError("independent candidate W does not match scoring.py")
    result = {
        "evaluation": {"start": args.start, "end": args.end, "train_start": str(train_a),
                       "train_end_exclusive": str(pred_a), "train_site_hours": len(gen),
                       "eval_site_hours": len(actual), "eval_hours": int(actual.ts.nunique()),
                       "eligible_source_hours": int(len(eligible_ts))},
        "features": {"A": features_a, "B_added": ["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]},
        "A_W": official_a["W"], "B_W": official_b["W"], "delta_B_minus_A": official_b["W"] - official_a["W"],
        "A_diagnostics": summarize(pa, comp, actual, smp, hourly_a),
        "B_diagnostics": summarize(pb, comp, actual, smp, hourly_b),
        "independent_hourly_W_A": independent_a, "independent_hourly_W_B": independent_b,
        "bootstrap_168h_ci": bootstrap_delta(hourly_a, hourly_b) if official_b["W"] < official_a["W"] else None,
    }
    site_a.to_parquet(out_dir / "pilot_A_sites.parquet", index=False)
    site_b.to_parquet(out_dir / "pilot_B_sites.parquet", index=False)
    data_dir = Path(sc.DATA)
    input_paths = [data_dir / "sites.csv", data_dir / "train" / "generation.parquet",
                   data_dir / "train" / "forecast_wa.parquet", data_dir / "train" / "forecast_wb.parquet",
                   data_dir / "train" / "smp.csv", ROOT / "data_ext" / "gfs_hourly_partial_full.parquet",
                   Path(args.layers), Path(__file__).resolve(), ROOT / "src" / "features.py",
                   ROOT / "src" / "model.py", ROOT / "src" / "scoring.py"]
    result["sha256"] = {str(p): sha256_file(p) for p in input_paths if p.exists()}
    result["versions"] = {pkg: importlib.metadata.version(pkg) for pkg in ("lightgbm", "pandas", "numpy")}
    result["parameters"] = {"fset": "rich", "seed": 7, "weight": "none", "composition": "reference",
                            "train_years": 2, "calendar": "weekday", "ext": "GFS only (no Open-Meteo)",
                            "lightgbm": M.PARAMS}
    result["prediction_sha256"] = {
        "A": sha256_file(out_dir / "pilot_A_sites.parquet"),
        "B": sha256_file(out_dir / "pilot_B_sites.parquet"),
    }
    (out_dir / "pilot_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
