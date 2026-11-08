"""SM66: fixed SM65 peak specialist evaluated on the earlier 2023–24 year."""
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
from sm58_controlled_pilot import (  # noqa: E402
    bootstrap_delta, calc_hourly_w, predict_in_batches, sha256_file, summarize,
)
from sm65_peak_specialist import PEAK_HOURS, blend_peak  # noqa: E402
from sm64_multi_nwp import LEADS, cutoff_audit  # noqa: E402

OUT = ROOT / "outputs" / "sm66"
START, END = sc.window("2023-06-01", "2024-06-01")
TRAIN_START = START - pd.DateOffset(years=2)
REQUIRED = ["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens"]


def target_days(ts: pd.Series) -> pd.Series:
    """Assign a right-closed 00:00 hour to the previous target day."""
    return (sc.to_ts(ts) - pd.Timedelta(hours=1)).dt.tz_localize(None).dt.floor("D")


def valid_run_days() -> set[pd.Timestamp]:
    audit = cutoff_audit()
    audit = audit[audit.lead.isin(LEADS)].copy()
    audit["target_day"] = pd.to_datetime(audit.init_date) + pd.Timedelta(days=1)
    day = audit.groupby("target_day").agg(n=("lead", "nunique"), eligible=("cutoff_eligible", "sum"))
    return set(day.index[(day.n == len(LEADS)) & (day.eligible == len(LEADS))])


def source_data() -> tuple[pd.DataFrame, pd.DatetimeIndex, dict]:
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.dropna(subset=REQUIRED).copy()
    good_days = valid_run_days()
    ext["target_day"] = target_days(ext.ts)
    ext = ext[ext.target_day.isin(good_days)].drop(columns="target_day").sort_values("ts")
    if ext.ts.duplicated().any():
        raise ValueError("duplicate external source timestamp")
    eligible = pd.DatetimeIndex(ext.ts)
    train = eligible[(eligible >= TRAIN_START) & (eligible < START)]
    ev = eligible[(eligible >= START) & (eligible <= END)]
    expect_train = int((START - TRAIN_START).total_seconds() // 3600)
    expect_eval = int((END - START).total_seconds() // 3600) + 1
    source = {"train_hours": len(train), "train_expected_hours": expect_train,
              "eval_hours": len(ev), "eval_expected_hours": expect_eval,
              "train_ratio": len(train) / expect_train, "eval_ratio": len(ev) / expect_eval,
              "train_run_days": sum(TRAIN_START.floor("D").tz_localize(None) <= d < START.floor("D").tz_localize(None) for d in good_days),
              "eval_run_days": sum(START.floor("D").tz_localize(None) <= d < END.floor("D").tz_localize(None) for d in good_days)}
    if source["train_ratio"] < .95 or source["eval_ratio"] < .95:
        raise RuntimeError(f"insufficient common source-hour support: {source}")
    return ext, eligible, source


def observation_audit(sites: pd.DataFrame, comp: pd.Series, eligible: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    gen = P.load_generation(TRAIN_START, START)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(eligible)].copy()
    actual = sc.load_actual("2023-06-01", "2024-06-01")
    actual["ts"] = sc.to_ts(actual.ts)
    ev = eligible[(eligible >= START) & (eligible <= END)]
    actual = actual[actual.ts.isin(ev)].copy()
    full_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    actual["group"] = actual.site_id.map(comp)
    cap = sites.set_index("site_id").capacity_kw
    actual["cap"] = actual.site_id.map(cap)
    peak = actual[actual.ts.dt.hour.isin(PEAK_HOURS) & actual.energy.notna()]
    group_hours = actual.groupby(["group", "ts"]).cap.sum().rename("observed_cap").reset_index()
    group_hours["coverage"] = group_hours.observed_cap / group_hours.group.map(full_cap)
    train_sites = set(gen.site_id.unique())
    eval_sites = set(actual.site_id.unique())
    peak_train = gen[gen.ts.dt.hour.isin(PEAK_HOURS)]
    audit = {
        "train_site_hours": len(gen), "train_observed_sites": len(train_sites),
        "train_peak_site_hours": len(peak_train), "train_peak_sites": int(peak_train.site_id.nunique()),
        "eval_site_hours": len(actual), "eval_observed_sites": len(eval_sites),
        "eval_without_train_sites": len(eval_sites - train_sites),
        "eval_without_train_site_fraction": len(eval_sites-train_sites)/len(eval_sites) if eval_sites else None,
        "daylight_peak_site_hours": len(peak),
        "groups": {g: {"observed_sites": int(actual.loc[actual.group == g, "site_id"].nunique()),
                        "peak_site_hours": int(peak.loc[peak.group == g].shape[0]),
                        "mean_observed_capacity_ratio": float(group_hours.loc[group_hours.group == g, "coverage"].mean()),
                        "full_capacity_kW": float(full_cap[g])} for g in full_cap.index},
    }
    return gen, actual.drop(columns=["group", "cap"]), audit


def run(audit_only: bool) -> dict:
    if F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise RuntimeError("SM66 requires weekday, GFS, and no Open-Meteo")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM66 requires the frozen SM65 feature environment")
    ext, eligible, support = source_data()
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    gen, actual, obs = observation_audit(sites, comp, eligible)
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"source_support": support, "observation_support": obs,
              "train_window": [str(TRAIN_START), str(START)], "eval_window": [str(START), str(END)],
              "source_hashes": {str(p): sha256_file(p) for p in [Path(sc.DATA)/"train"/"generation.parquet", Path(sc.DATA)/"train"/"forecast_wa.parquet", Path(sc.DATA)/"train"/"forecast_wb.parquet", ROOT/"data_ext"/"gfs_hourly_partial_full.parquet", ROOT/"outputs"/"sm58"/"gfs_index_head_audit.csv"]}}
    (OUT / "audit.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    if audit_only:
        return result

    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    design = F.build_rich(gen[["site_id", "ts", "energy"]], site_features, fa, fb, reg, ext)
    feats = [c for c in P.select_rich_features(design) if c != "site_code"]
    if len(feats) != 102:
        raise RuntimeError(f"expected 102 SM65 features, got {len(feats)}")
    peak_design = design[design.ts.dt.hour.isin(PEAK_HOURS) & (design.elev > 0) & design.energy.notna()]
    result["peak_train_rows_after_design"] = len(peak_design)
    result["feature_count"] = len(feats)
    result["train_feature_missing_fraction"] = float(design[feats].isna().to_numpy().mean())
    full_model = M.fit(design, weight="none", feats=feats, params={"random_state": 7}, cat=[])
    peak_model = M.fit(peak_design, weight="none", feats=feats, params={"random_state": 7}, cat=[])
    ev = eligible[(eligible >= START) & (eligible <= END)]
    base = predict_in_batches(full_model, sites, site_features, ev, START, END, fa, fb, reg, ext, feats)
    peak_ts = ev[ev.hour.isin(PEAK_HOURS)]
    expert = predict_in_batches(peak_model, sites, site_features, peak_ts, START, END, fa, fb, reg, ext, feats)
    candidate = blend_peak(base, expert)
    smp = sc.load_smp()
    ha = calc_hourly_w(base, comp, actual, smp)
    hb = calc_hourly_w(candidate, comp, actual, smp)
    wa = sc.score(base[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    wb = sc.score(candidate[["site_id", "ts", "kwh"]], comp, actual, smp)["W"]
    if abs(wa - ha.w.sum()) > 1e-4 or abs(wb - hb.w.sum()) > 1e-4:
        raise AssertionError("official and independent hourly W disagree")
    sa, sb = summarize(base, comp, actual, smp, ha), summarize(candidate, comp, actual, smp, hb)
    if sa["offpeak_W"] != sb["offpeak_W"]:
        raise AssertionError("nonpeak W changed")
    peak_actual = actual[actual.ts.dt.hour.isin(PEAK_HOURS)]
    bias = {}
    for label, pred in [("A", base), ("B", candidate)]:
        rows = peak_actual.merge(pred, on=["site_id", "ts"], validate="one_to_one")
        bias[label] = float((rows.kwh - rows.energy).mean())
    result.update({"A_W": float(wa), "B_W": float(wb), "delta_W": float(wb-wa),
                   "A": sa, "B": sb, "peak_signed_bias_kWh": bias,
                   "peak_group_W_A": ha[ha.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum().to_dict(),
                   "peak_group_W_B": hb[hb.ts.dt.hour.isin(PEAK_HOURS)].groupby("group").w.sum().to_dict(),
                   "bootstrap_168h_ci": bootstrap_delta(ha, hb) if wb < wa and support["eval_ratio"] > .95 else None})
    base.to_parquet(OUT / "baseline_sites.parquet", index=False)
    candidate.to_parquet(OUT / "candidate_sites.parquet", index=False)
    result["prediction_sha256"] = {name: sha256_file(OUT / f"{name}_sites.parquet") for name in ("baseline", "candidate")}
    (OUT / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--audit", action="store_true")
    args = p.parse_args()
    print(json.dumps(run(args.audit), indent=2, default=str))
