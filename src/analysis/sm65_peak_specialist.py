"""SM65: one peak-only Site model against the frozen SM58 Site baseline."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
import model as M  # noqa: E402
import pipeline as P  # noqa: E402
import scoring as sc  # noqa: E402
from sm58_controlled_pilot import (  # noqa: E402
    calc_hourly_w, predict_in_batches, sha256_file, summarize, bootstrap_delta,
)

OUT = ROOT / "outputs" / "sm65"
BASE = ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet"
LAYERS = ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet"
BASE_SHA256 = "28b4cacf877431559e14fe91763422657bb63ed317910069f29efe5c15b7810e"
BASE_W = 188_593_035.90775314
PEAK_HOURS = tuple(range(11, 16))


def blend_peak(base: pd.DataFrame, expert: pd.DataFrame) -> pd.DataFrame:
    """Blend only right-closed KST peak keys; preserve all other baseline rows."""
    keys = ["site_id", "ts"]
    if base.duplicated(keys).any() or expert.duplicated(keys).any():
        raise ValueError("duplicate site-hour prediction key")
    peak = base.ts.dt.hour.isin(PEAK_HOURS)
    expected = pd.MultiIndex.from_frame(base.loc[peak, keys])
    got = pd.MultiIndex.from_frame(expert[keys])
    if not expected.equals(got):
        raise ValueError("expert prediction keys differ from baseline peak keys")
    if not np.isfinite(expert.kwh.to_numpy()).all() or (expert.kwh < 0).any():
        raise ValueError("expert output is nonfinite or negative")
    result = base.copy()
    result.loc[peak, "kwh"] = 0.5 * base.loc[peak, "kwh"].to_numpy() + 0.5 * expert.kwh.to_numpy()
    if not np.array_equal(result.loc[~peak, "kwh"].to_numpy(), base.loc[~peak, "kwh"].to_numpy()):
        raise AssertionError("nonpeak predictions changed")
    return result


def run() -> dict:
    if F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise RuntimeError("SM65 requires weekday, GFS, and no Open-Meteo")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM65 requires the frozen SM58 feature environment")
    if sha256_file(BASE) != BASE_SHA256:
        raise RuntimeError("frozen SM58 baseline hash mismatch")

    start, end = sc.window("2024-06-01", "2025-06-01")
    train_start = start - pd.DateOffset(years=2)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    base = pd.read_parquet(BASE)
    base["ts"] = sc.to_ts(base.ts)
    if base.duplicated(["site_id", "ts"]).any() or base.ts.dt.tz is None:
        raise ValueError("invalid frozen baseline keys or timezone")

    layers = pd.read_parquet(LAYERS)
    layers["ts"] = sc.to_ts(layers.ts)
    if layers.ts.duplicated().any() or layers[["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]].isna().any().any():
        raise ValueError("invalid frozen SM58 layer mask")
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.merge(layers, on="ts", how="inner", validate="one_to_one")
    required = ["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens", "gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]
    ext = ext.dropna(subset=required).sort_values("ts")
    eligible = pd.DatetimeIndex(ext.ts)
    eval_ts = eligible[(eligible >= start) & (eligible <= end)]
    expected_keys = pd.MultiIndex.from_product([sites.site_id, eval_ts], names=["site_id", "ts"])
    if not pd.MultiIndex.from_frame(base[["site_id", "ts"]]).equals(expected_keys):
        raise ValueError("frozen baseline does not match SM58 eligible full site-hour grid")

    gen = P.load_generation(train_start, start)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(eligible)].copy()
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    peak_train = gen[gen.ts.dt.hour.isin(PEAK_HOURS)].copy()
    design = F.build_rich(peak_train[["site_id", "ts", "energy"]], site_features, fa, fb, reg, ext)
    feats = [c for c in P.select_rich_features(design) if c != "site_code" and c not in {"gfs_lcdc", "gfs_mcdc", "gfs_hcdc"}]
    if len(feats) != 102:
        raise RuntimeError(f"expected SM58 baseline's 102 features, got {len(feats)}")
    train_rows = design[(design.elev > 0) & design.energy.notna()]
    expert = M.fit(train_rows, weight="none", feats=feats, params={"random_state": 7}, cat=[])
    peak_ts = eval_ts[eval_ts.hour.isin(PEAK_HOURS)]
    expert_pred = predict_in_batches(expert, sites, site_features, peak_ts, start, end, fa, fb, reg, ext, feats)
    candidate = blend_peak(base, expert_pred)
    if not np.isfinite(candidate.kwh.to_numpy()).all() or (candidate.kwh < 0).any():
        raise ValueError("candidate predictions nonfinite or negative")

    actual = sc.load_actual("2024-06-01", "2025-06-01")
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual[actual.ts.isin(eval_ts)]
    smp = sc.load_smp()
    hourly_a = calc_hourly_w(base, comp, actual, smp)
    hourly_b = calc_hourly_w(candidate, comp, actual, smp)
    official_a = sc.score(base[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    official_b = sc.score(candidate[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    if abs(official_a - BASE_W) > 1e-4 or abs(official_a - hourly_a.w.sum()) > 1e-4 or abs(official_b - hourly_b.w.sum()) > 1e-4:
        raise AssertionError("baseline W or independent hourly W mismatch")
    a = summarize(base, comp, actual, smp, hourly_a)
    b = summarize(candidate, comp, actual, smp, hourly_b)
    if a["offpeak_W"] != b["offpeak_W"]:
        raise AssertionError("nonpeak W changed")
    peak_group_a = hourly_a[hourly_a.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum()
    peak_group_b = hourly_b[hourly_b.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum()
    peak_actual = actual[actual.ts.dt.hour.isin(PEAK_HOURS)]
    peak_base = peak_actual.merge(base, on=["site_id", "ts"], validate="one_to_one")
    peak_candidate = peak_actual.merge(candidate, on=["site_id", "ts"], validate="one_to_one")
    delta = float(official_b - official_a)
    do_bootstrap = delta <= -0.005 * official_a and (peak_group_b < peak_group_a).all()
    result = {
        "baseline_sha256": BASE_SHA256, "layers_sha256": sha256_file(LAYERS),
        "evaluation_hours": len(eval_ts), "observed_site_hours": len(actual),
        "training_peak_site_hours": len(peak_train), "training_daylight_peak_site_hours": len(train_rows),
        "training_peak_sites": int(train_rows.site_id.nunique()), "training_features": feats,
        "training_window": [str(train_start), str(start)], "seed": 7, "mix_peak_expert": 0.5,
        "A_W": float(official_a), "B_W": float(official_b), "delta_B_minus_A_W": delta,
        "A": a, "B": b,
        "peak_group_W_A": peak_group_a.to_dict(), "peak_group_W_B": peak_group_b.to_dict(),
        "peak_signed_bias_kWh_A": float((peak_base.kwh - peak_base.energy).mean()),
        "peak_signed_bias_kWh_B": float((peak_candidate.kwh - peak_candidate.energy).mean()),
        "bootstrap_168h_ci": bootstrap_delta(hourly_a, hourly_b) if do_bootstrap else None,
        "source_hashes": {str(p): sha256_file(p) for p in [Path(sc.DATA)/"train"/"generation.parquet", Path(sc.DATA)/"train"/"forecast_wa.parquet", Path(sc.DATA)/"train"/"forecast_wb.parquet", ROOT/"data_ext"/"gfs_hourly_partial_full.parquet"]},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    candidate.to_parquet(OUT / "candidate_sites.parquet", index=False)
    result["candidate_sha256"] = sha256_file(OUT / "candidate_sites.parquet")
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
