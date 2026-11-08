"""SM67: RICH2 Site baseline and fixed peak specialist on SM58/SM66 masks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import features as F  # noqa: E402
import model as M  # noqa: E402
import pipeline as P  # noqa: E402
import scoring as sc  # noqa: E402
from sm58_controlled_pilot import bootstrap_delta, calc_hourly_w, predict_in_batches, sha256_file, summarize  # noqa: E402
from sm65_peak_specialist import PEAK_HOURS, blend_peak  # noqa: E402
from sm66_peak_cross_year import source_data as source_2023  # noqa: E402

OUT = ROOT / "outputs" / "sm67"
FROZEN_2024 = {
    "sm58_A": 188_593_035.90775314,
    "sm65_peak": 186_666_176.6782984,
    "sm58_cloud": 186_530_358.84941596,
}
# Fixed before scoring: 0.5% peak gain, no group >1% worse, and within 0.5%
# of the strongest frozen 2024 SM Site candidate to qualify for 2023 follow-up.
MIN_PEAK_GAIN = .005
MAX_GROUP_WORSEN = .01
MAX_FROZEN_GAP = .005


def make_source(year: int) -> tuple[pd.DataFrame, pd.DatetimeIndex, dict]:
    if year == 2023:
        return source_2023()
    layers = pd.read_parquet(ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet")
    layers["ts"] = sc.to_ts(layers.ts)
    if layers.ts.duplicated().any() or layers[["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]].isna().any().any():
        raise ValueError("invalid frozen layer support")
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.merge(layers, on="ts", how="inner", validate="one_to_one")
    ext = ext.dropna(subset=["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens", "gfs_lcdc", "gfs_mcdc", "gfs_hcdc"])
    ext = ext.sort_values("ts")
    if ext.ts.duplicated().any():
        raise ValueError("duplicate external source timestamp")
    return ext, pd.DatetimeIndex(ext.ts), {"mask": "frozen_SM58_common_GFS_layer_mask"}


def run(year: int) -> dict:
    if not F.RICH2 or F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise RuntimeError("SM67 requires RICH2, weekday, GFS and no Open-Meteo")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM67 excludes GEFS/UM/spatial/physics")
    start, end = sc.window(f"{year}-06-01", f"{year+1}-06-01")
    train_start = start - pd.DateOffset(years=2)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    ext, eligible, support = make_source(year)
    eval_ts = eligible[(eligible >= start) & (eligible <= end)]
    if year == 2024:
        frozen = pd.read_parquet(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet")
        frozen["ts"] = sc.to_ts(frozen.ts)
        if sha256_file(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet") != "28b4cacf877431559e14fe91763422657bb63ed317910069f29efe5c15b7810e":
            raise ValueError("SM58 baseline hash mismatch")
        expected = pd.MultiIndex.from_product([sites.site_id, eval_ts], names=["site_id", "ts"])
        if not pd.MultiIndex.from_frame(frozen[["site_id", "ts"]]).equals(expected):
            raise ValueError("SM67 evaluation mask differs from frozen SM58")

    gen = P.load_generation(train_start, start)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(eligible)].copy()
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    design = F.build_rich(gen[["site_id", "ts", "energy"]], site_features, fa, fb, reg, ext)
    feats = [c for c in P.select_rich_features(design) if c != "site_code" and c not in {"gfs_lcdc", "gfs_mcdc", "gfs_hcdc"}]
    # The RICH2 additions are counted against the exact frozen 102-column SM58 list.
    frozen_feats = json.loads((ROOT / "outputs" / "sm58" / "pilot_result.json").read_text())["features"]["A"]
    if set(frozen_feats) - set(feats):
        raise ValueError("RICH2 lost a frozen SM58 baseline feature")
    added = [c for c in feats if c not in frozen_feats]
    peak_design = design[design.ts.dt.hour.isin(PEAK_HOURS) & (design.elev > 0) & design.energy.notna()]
    model_a = M.fit(design, weight="none", feats=feats, params={"random_state": 7}, cat=[])
    model_peak = M.fit(peak_design, weight="none", feats=feats, params={"random_state": 7}, cat=[])
    base = predict_in_batches(model_a, sites, site_features, eval_ts, start, end, fa, fb, reg, ext, feats)
    peak_ts = eval_ts[eval_ts.hour.isin(PEAK_HOURS)]
    peak = predict_in_batches(model_peak, sites, site_features, peak_ts, start, end, fa, fb, reg, ext, feats)
    candidate = blend_peak(base, peak)
    actual = sc.load_actual(f"{year}-06-01", f"{year+1}-06-01")
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual[actual.ts.isin(eval_ts)]
    smp = sc.load_smp()
    ha, hb = calc_hourly_w(base, comp, actual, smp), calc_hourly_w(candidate, comp, actual, smp)
    wa = sc.score(base[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    wb = sc.score(candidate[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    if abs(wa-ha.w.sum()) > 1e-4 or abs(wb-hb.w.sum()) > 1e-4:
        raise AssertionError("hourly W differs from scoring.py")
    da, db = summarize(base, comp, actual, smp, ha), summarize(candidate, comp, actual, smp, hb)
    if da["offpeak_W"] != db["offpeak_W"]:
        raise AssertionError("nonpeak W changed")
    peak_actual = actual[actual.ts.dt.hour.isin(PEAK_HOURS)]
    bias = {}
    for name, pred in (("A", base), ("B", candidate)):
        match = peak_actual.merge(pred, on=["site_id", "ts"], validate="one_to_one")
        bias[name] = float((match.kwh-match.energy).mean())
    result = {
        "year": year, "source_support": support, "train_rows": len(design),
        "train_peak_rows": len(peak_design), "eval_hours": len(eval_ts), "observed_site_hours": len(actual),
        "frozen_baseline_features": len(frozen_feats), "A_features": len(feats),
        "added_features": added, "added_train_missing_fraction": {c: float(design[c].isna().mean()) for c in added},
        "A_W": float(wa), "B_W": float(wb), "delta_W": float(wb-wa),
        "A": da, "B": db, "peak_signed_bias_kWh": bias,
        "peak_group_W_A": ha[ha.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum().to_dict(),
        "peak_group_W_B": hb[hb.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum().to_dict(),
        "input_hashes": {str(p): sha256_file(p) for p in [Path(sc.DATA)/"train"/"generation.parquet", Path(sc.DATA)/"train"/"forecast_wa.parquet", Path(sc.DATA)/"train"/"forecast_wb.parquet", ROOT/"data_ext"/"gfs_hourly_partial_full.parquet"]},
    }
    if year == 2024:
        result["frozen_2024"] = FROZEN_2024
        result["stage1_go"] = bool(wb <= (1-MIN_PEAK_GAIN)*wa
            and all(db["group_W"][g] <= (1+MAX_GROUP_WORSEN)*da["group_W"][g] for g in ("G1", "G2"))
            and wb <= (1+MAX_FROZEN_GAP)*min(FROZEN_2024["sm65_peak"], FROZEN_2024["sm58_cloud"]))
        result["bootstrap_168h_ci"] = bootstrap_delta(ha, hb) if result["stage1_go"] else None
    else:
        result["bootstrap_168h_ci"] = bootstrap_delta(ha, hb) if wb < wa else None
    OUT.mkdir(parents=True, exist_ok=True)
    base.to_parquet(OUT / f"baseline_{year}_sites.parquet", index=False)
    candidate.to_parquet(OUT / f"candidate_{year}_sites.parquet", index=False)
    result["prediction_hashes"] = {n: sha256_file(OUT / f"{n}_{year}_sites.parquet") for n in ("baseline", "candidate")}
    (OUT / f"result_{year}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, choices=(2023, 2024), required=True)
    args = p.parse_args()
    if args.year == 2023:
        prior = OUT / "result_2024.json"
        if not prior.exists() or not json.loads(prior.read_text())["stage1_go"]:
            raise RuntimeError("2024 stage-1 gate did not pass")
    print(json.dumps(run(args.year), ensure_ascii=False, indent=2, default=str))
