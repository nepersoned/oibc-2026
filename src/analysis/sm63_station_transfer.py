"""SM63: a WB-station-cluster CF model and fixed 0.8/0.2 blend pilot."""
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agg_model as A  # noqa: E402
import features as F  # noqa: E402
import scoring as sc  # noqa: E402
from sm39_group_site_integration import hourly_penalties  # noqa: E402

OUT = ROOT / "outputs" / "sm63"
BASELINE_PATH = ROOT / "outputs" / "sm45" / "2024_A1_B1_site_group_20_sites.parquet"
START, END = "2024-06-01", "2025-06-01"
TRAIN_YEARS = 2
MIN_COV = 0.30
MIN_SUPPORT_ROWS = 100
ALPHA_STATION = 0.20
SEED = 100
PARAMS = dict(n_estimators=1000, learning_rate=0.03, num_leaves=31,
              min_child_samples=100, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=1.0, verbose=-1, n_jobs=-1,
              objective="regression", random_state=SEED)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require_env() -> None:
    if F.CAL_MODE != "weekday" or F.USE_GFS or F.USE_GEFS or F.USE_UM:
        raise RuntimeError("SM63 requires weekday calendar and external NWP disabled")
    if F.EXT_SOURCES != "no_openmeteo" or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM63 requires Open-Meteo/spatial/physics disabled")
    if A.SOURCE != "prov" or A.WX_CUT:
        raise RuntimeError("SM63 uses competition WA/WB forecasts only; set OIBC_SRC=prov and unset WX2")


def load_weather(sites: pd.DataFrame) -> pd.DataFrame:
    fa, fb = A.forecasts("train")
    for df, key in ((fa, "wa_station"), (fb, "wb_station")):
        if df.duplicated([key, "ts"]).any():
            raise ValueError(f"prepared {key} forecast has duplicate station-hour keys")
    station_links = sites[["site_id", "wb_station", "wa_station", "capacity_kw"]].copy()
    station_links["wb_station"] = station_links.wb_station.astype(str)
    station_links["wa_station"] = station_links.wa_station.astype(str)

    # Capacity-weighted WA summaries over plants linked to each WB station.
    wm = station_links.merge(fa, on="wa_station", how="inner", validate="many_to_many")
    wa_cols = list(A.GVARS["wa"])
    wa_agg = {}
    for col in wa_cols:
        valid_w = wm["capacity_kw"].where(wm[col].notna(), 0.0)
        num = (wm[col].fillna(0.0) * wm["capacity_kw"]).groupby([wm.wb_station, wm.ts]).sum()
        den = valid_w.groupby([wm.wb_station, wm.ts]).sum().replace(0, np.nan)
        wa_agg[f"wa_link_{col}"] = (num / den)
    wa = pd.DataFrame(wa_agg).reset_index()
    # Static station metadata uses only the provided mapping and capacities.
    meta = station_links.groupby("wb_station").apply(lambda d: pd.Series({
        "station_capacity_kw": d.capacity_kw.sum(),
        "station_site_count": d.site_id.nunique(),
        "station_capacity_mean_kw": d.capacity_kw.mean(),
        "station_capacity_std_kw": d.capacity_kw.std(ddof=0),
        "station_lat": np.average(d.site_id.map(sites.set_index("site_id").lat), weights=d.capacity_kw),
        "station_lon": np.average(d.site_id.map(sites.set_index("site_id").lon), weights=d.capacity_kw),
    }), include_groups=False).reset_index()
    wb_cols = list(A.GVARS["wb"])
    wb = fb[["wb_station", "ts"] + wb_cols].copy()
    station = wb.merge(wa, on=["wb_station", "ts"], how="left", validate="one_to_one")
    station = station.merge(meta, on="wb_station", how="left", validate="many_to_one")
    ts = pd.DatetimeIndex(station.ts)
    station["elev"], station["azim"], station["cosz"] = F.solar(
        ts, station.station_lat.to_numpy(), station.station_lon.to_numpy())
    station["ghi_cs"] = np.where(station.cosz > 0,
        1098 * np.clip(station.cosz, 1e-3, None) * np.exp(-0.057 / np.clip(station.cosz, 1e-3, None)), 0)
    station["doy_sin"] = np.sin(2 * np.pi * ts.day_of_year.to_numpy() / 365.25)
    station["doy_cos"] = np.cos(2 * np.pi * ts.day_of_year.to_numpy() / 365.25)
    station["hour"] = ts.hour.to_numpy()
    cal = F.calendar(station.ts, mode="weekday")
    for col in cal:
        station[col] = cal[col].to_numpy()
    # IDs and raw coordinates never enter the feature matrix.
    station = station.drop(columns=["station_lat", "station_lon"])
    station = station.sort_values(["wb_station", "ts"]).reset_index(drop=True)
    if station.duplicated(["wb_station", "ts"]).any():
        raise ValueError("station weather keys are not unique")
    return station


def station_targets(gen: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    links = sites[["site_id", "wb_station", "capacity_kw"]].copy()
    links["wb_station"] = links.wb_station.astype(str)
    g = gen.merge(links, on="site_id", how="inner", validate="many_to_one")
    target = g.groupby(["wb_station", "ts"]).agg(
        act=("energy", "sum"), cap_avail=("capacity_kw", "sum"),
        observed_sites=("site_id", "nunique")).reset_index()
    total = links.groupby("wb_station").capacity_kw.sum()
    target["cov"] = target.cap_avail / target.wb_station.map(total)
    target["cf"] = target.act / target.cap_avail
    return target


def target_windows(sites: pd.DataFrame, weather: pd.DataFrame):
    pa, pb = sc.window(START, END)
    train_a = pa - pd.DateOffset(years=TRAIN_YEARS)
    gen_train = A.load_gen(train_a, pa - pd.Timedelta(hours=1))
    t = station_targets(gen_train[gen_train.ts < pa], sites)
    weather_index = pd.MultiIndex.from_frame(weather[["wb_station", "ts"]])
    train = t[(t.ts >= train_a) & (t.ts < pa) & (t["cov"] >= MIN_COV)].copy()
    train = train[pd.MultiIndex.from_frame(train[["wb_station", "ts"]]).isin(weather_index)]
    return pa, pb, train_a, gen_train, train


def feature_columns(station: pd.DataFrame) -> list[str]:
    drops = {"wb_station", "ts", "act", "cap_avail", "observed_sites", "cov", "cf"}
    features = [c for c in station.columns if c not in drops]
    if any(c in features for c in ("wa_station", "wb_station", "site_id", "station_lat", "station_lon")):
        raise AssertionError("station or plant identity/raw coordinates leaked into features")
    return features


def season_counts(t: pd.DataFrame) -> dict:
    d = t.assign(target_day=(t.ts - pd.Timedelta(hours=1)).dt.floor("D"))
    return {str(k): {"rows": int(len(g)), "days": int(g.target_day.nunique())}
            for k, g in d.assign(season=d.target_day.dt.quarter).groupby("season")}


def audit_support(sites: pd.DataFrame, weather: pd.DataFrame, train: pd.DataFrame,
                  eval_targets: pd.DataFrame) -> dict:
    station_ids = sorted(sites.wb_station.astype(str).unique())
    train_day = train[train.ts.dt.hour.between(6, 18)].copy()
    train_support = {}
    for station in station_ids:
        rows = train_day[train_day.wb_station == station]
        quarter_counts = rows.assign(quarter=(rows.ts - pd.Timedelta(hours=1)).dt.quarter).groupby("quarter").size()
        train_support[station] = {"eligible_daylight_rows": int(len(rows)),
            "unique_days": int((rows.ts - pd.Timedelta(hours=1)).dt.floor("D").nunique()),
            "season_count": int(len(quarter_counts)),
            "season_rows": {str(k): int(v) for k, v in quarter_counts.items()},
            "mean_cov": float(rows["cov"].mean()) if len(rows) else None}
    support_ids = {s for s, z in train_support.items() if z["eligible_daylight_rows"] >= MIN_SUPPORT_ROWS}
    total_cap = sites.groupby(sites.wb_station.astype(str)).capacity_kw.sum()
    supported_capacity_share = float(total_cap.reindex(sorted(support_ids)).sum() / total_cap.sum())
    eval_day = eval_targets[eval_targets.ts.dt.hour.between(6, 18)]
    eval_station_rows = eval_day.groupby("wb_station").size()
    eval_sites_capacity = sites.assign(wb_station=sites.wb_station.astype(str)).set_index("site_id")
    eval_actual_capacity = eval_day.groupby("wb_station").cap_avail.sum()
    forecast_eval = weather[(weather.ts >= eval_targets.ts.min()) & (weather.ts <= eval_targets.ts.max())]
    forecast_stations = set(forecast_eval.wb_station.astype(str).unique())
    missing_forecast = sorted(set(station_ids) - forecast_stations)
    eligible_cap_share = float(total_cap.reindex(sorted(support_ids)).sum() / total_cap.sum())
    return {
        "wb_station_count": len(station_ids), "site_count": int(sites.site_id.nunique()),
        "sites_per_station": {"mean": float(sites.groupby("wb_station").site_id.nunique().mean()),
            "median": float(sites.groupby("wb_station").site_id.nunique().median()),
            "single_site_stations": int((sites.groupby("wb_station").site_id.nunique() == 1).sum()),
            "max": int(sites.groupby("wb_station").site_id.nunique().max())},
        "training_window_station_CF_rows_cov_ge_0_30": int(len(train)),
        "training_station_support_daylight": train_support,
        "training_stations_any_label": sum(x["eligible_daylight_rows"] > 0 for x in train_support.values()),
        "training_stations_ge_100_daylight_labels": len(support_ids),
        "training_capacity_share_stations_ge_100_daylight_labels": supported_capacity_share,
        "training_season_rows": season_counts(train_day),
        "evaluation_observed_station_hours": int(len(eval_targets)),
        "evaluation_stations_with_observed_daylight": int((eval_station_rows > 0).sum()),
        "evaluation_observed_capacity_by_station": {str(k): float(v) for k, v in eval_actual_capacity.items()},
        "evaluation_capacity_share_with_ge_100_train_rows": eligible_cap_share,
        "evaluation_observed_capacity_share_on_supported_stations": float(
            eval_actual_capacity.reindex(sorted(support_ids), fill_value=0).sum() / eval_actual_capacity.sum()),
        "evaluation_forecast_stations": len(forecast_stations),
        "evaluation_missing_WB_forecast_stations": missing_forecast,
        "support_rule": f"station is called supported at >= {MIN_SUPPORT_ROWS} daylight training rows with cov >= {MIN_COV:.2f}; labels use observed generation / observed capacity",
        "evaluation_capacity_note": "reported capacity is post-hoc support audit only, not a model input",
    }


def score_diagnostics(pred: pd.DataFrame, actual: pd.DataFrame, comp: pd.Series,
                      smp: pd.Series) -> tuple[dict, pd.DataFrame]:
    score = sc.score(pred, comp, actual, smp)
    detail = hourly_penalties(pred, actual, comp, smp)
    if not np.isclose(detail.pen.sum(), score["W"], rtol=0, atol=1e-5):
        raise AssertionError("independent hourly W differs from scoring.score")
    act = actual[["site_id", "ts", "energy"]].copy()
    p = pred.rename(columns={"kwh": "pred"})
    m = act.merge(p, on=["site_id", "ts"], how="left", validate="one_to_one")
    if m.pred.isna().any():
        raise ValueError("prediction absent for an observed site-hour")
    m["group"] = m.site_id.map(comp)
    m["err"] = m.pred - m.energy
    m["weight"] = .1 * m.ts.map(smp).to_numpy() * sc.k_weight(m.ts)
    m["weighted_site_abs"] = m.weight * m.err.abs()
    m["month"] = (m.ts - pd.Timedelta(hours=1)).dt.strftime("%Y-%m")
    m["peak"] = m.ts.dt.hour.between(11, 15)
    groups = m.groupby(["group", "ts"], as_index=False).agg(
        actual=("energy", "sum"), pred=("pred", "sum"), weight=("weight", "first"))
    groups["group_w"] = groups.weight * (groups.pred - groups.actual).abs()
    iw = float(m.weighted_site_abs.sum())
    gw = float(groups.group_w.sum())
    metrics = {"W": float(score["W"]), "W_by_group": {str(k): float(v) for k,v in detail.groupby("group").pen.sum().items()},
        "peak_W": float(detail.loc[detail.ts.dt.hour.between(11,15), "pen"].sum()),
        "monthly_W": {str(k): float(v) for k,v in detail.assign(month=detail.ts.sub(pd.Timedelta(hours=1)).dt.strftime("%Y-%m")).groupby("month").pen.sum().items()},
        "site_MAE_kwh": float(m.err.abs().mean()), "site_bias_kwh": float(m.err.mean()),
        "weighted_individual_W": iw, "cancellation_benefit_W": iw - gw,
        "cancellation_ratio": float((iw-gw)/iw) if iw else None,
        "observed_site_hours": int(len(m))}
    return metrics, m


def main(mode: str) -> dict:
    require_env()
    sites = sc.load_sites()
    sites["wb_station"] = sites.wb_station.astype(str)
    sites["wa_station"] = sites.wa_station.astype(str)
    weather = load_weather(sites)
    pa, pb, train_a, gen_train, train = target_windows(sites, weather)
    actual = sc.load_actual(START, END)
    comp = sc.reference_composition(sites)
    eval_targets = station_targets(actual, sites)
    support = audit_support(sites, weather, train, eval_targets)
    expected_train_station_count = len(sites.wb_station.unique())
    # At least 75% of nameplate capacity must have meaningful historical station labels;
    # all evaluation stations must have WA/WB input rows. These gates are checked pre-fit.
    if support["training_capacity_share_stations_ge_100_daylight_labels"] < .75:
        raise RuntimeError("pre-fit gate failed: <75% capacity has >=100 station daylight labels")
    if support["evaluation_missing_WB_forecast_stations"]:
        raise RuntimeError("pre-fit gate failed: evaluation WB forecast missing for one or more stations")
    if support["evaluation_stations_with_observed_daylight"] < expected_train_station_count * .9:
        raise RuntimeError("pre-fit gate failed: too few WB stations have evaluation observations")

    OUT.mkdir(parents=True, exist_ok=True)
    support_path = OUT / "support_audit.json"
    support_path.write_text(json.dumps(support, indent=2), encoding="utf-8")
    if mode == "audit":
        return {"status": "FEASIBLE; no fit requested", **support}

    features = feature_columns(weather)
    pa, pb = sc.window(START, END)
    eval_ts = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    expected_site_rows = sites.site_id.nunique() * len(eval_ts)
    candidate_path = OUT / "forecast_b_sites.parquet"
    fit_metadata_path = OUT / "fit_metadata.json"
    if mode == "pilot":
        train_rows = train.merge(weather, on=["wb_station", "ts"], how="inner", validate="one_to_one")
        train_rows = train_rows[train_rows.elev > -2].copy()
        y = train_rows.cf.clip(0, 1.2).astype("float32")
        model = lgb.LGBMRegressor(**PARAMS)
        model.fit(train_rows[features], y)

        station_ids = sorted(sites.wb_station.unique())
        station_pred_index = pd.MultiIndex.from_product([station_ids, eval_ts], names=["wb_station", "ts"]).to_frame(index=False)
        eval_weather = station_pred_index.merge(weather, on=["wb_station", "ts"], how="left", validate="one_to_one")
        if eval_weather[features].isna().all(axis=1).any():
            raise ValueError("entirely missing station forecast feature row during evaluation")
        cf_hat = model.predict(eval_weather[features])
        cf_hat = np.where(eval_weather.elev.to_numpy() > -2, np.clip(cf_hat, 0, None), 0.0)
        station_pred = station_pred_index.copy()
        station_pred["cf_hat"] = cf_hat
        site_pred = sites[["site_id", "wb_station", "capacity_kw"]].merge(
            station_pred, on="wb_station", how="inner", validate="many_to_many")
        site_pred["kwh"] = site_pred.cf_hat * site_pred.capacity_kw
        site_pred = site_pred[["site_id", "ts", "kwh"]]
        if len(site_pred) != expected_site_rows or site_pred.duplicated(["site_id", "ts"]).any():
            raise AssertionError("Station-restored prediction grid is incomplete or duplicated")
        site_pred.to_parquet(candidate_path, index=False)
        importance = pd.DataFrame({"feature": features,
            "gain": model.booster_.feature_importance("gain"),
            "split": model.booster_.feature_importance("split")}).sort_values("gain", ascending=False).head(20).to_dict("records")
        fit_metadata = {"features": features, "params": PARAMS, "training_rows_after_daylight": int(len(train_rows)),
                        "top_gain_features": importance, "baseline_path": str(BASELINE_PATH),
                        "baseline_sha256": sha256(BASELINE_PATH), "candidate_sha256": sha256(candidate_path),
                        "lightgbm": lgb.__version__}
        fit_metadata_path.write_text(json.dumps(fit_metadata, indent=2, default=str), encoding="utf-8")
    elif mode == "score-existing":
        if not candidate_path.exists() or not fit_metadata_path.exists():
            raise FileNotFoundError("no saved SM63 pilot predictions/metadata; run --pilot once")
        site_pred = pd.read_parquet(candidate_path)
        fit_metadata = json.loads(fit_metadata_path.read_text(encoding="utf-8"))
        if sha256(candidate_path) != fit_metadata["candidate_sha256"]:
            raise ValueError("saved Station prediction SHA256 differs from fit metadata")
        if sha256(BASELINE_PATH) != fit_metadata["baseline_sha256"]:
            raise ValueError("frozen A1-REF baseline SHA256 changed since pilot fit")
        features = fit_metadata["features"]
        train_rows = None
    else:
        raise ValueError(f"unknown mode: {mode}")

    baseline = pd.read_parquet(BASELINE_PATH)
    baseline["ts"] = sc.to_ts(baseline.ts)
    if baseline.duplicated(["site_id", "ts"]).any():
        raise ValueError("frozen A1-REF validation site prediction has duplicate keys")
    if len(baseline) != expected_site_rows or not set(baseline.site_id.unique()) == set(sites.site_id):
        raise ValueError("frozen A1-REF prediction grid does not match expected site-hour grid")
    candidate = site_pred
    blended = baseline[["site_id", "ts", "kwh"]].merge(
        candidate, on=["site_id", "ts"], suffixes=("_a", "_b"), how="inner", validate="one_to_one")
    if len(blended) != expected_site_rows:
        raise ValueError("A/C site-hour grids differ")
    blended["kwh"] = (1 - ALPHA_STATION) * blended.kwh_a + ALPHA_STATION * blended.kwh_b
    blended = blended[["site_id", "ts", "kwh"]]

    smp = sc.load_smp()
    metrics = {}
    scored_frames = {}
    for name, pred in (("A", baseline), ("B", candidate), ("C", blended)):
        metrics[name], scored_frames[name] = score_diagnostics(pred, actual, comp, smp)
    if not np.isclose(metrics["A"]["W"], 197_526_260.47453704, atol=.01, rtol=0):
        raise AssertionError(f"stored SM46 A1-REF W did not reproduce: {metrics['A']['W']}")
    joined = scored_frames["A"][["site_id", "ts", "err"]].merge(
        scored_frames["B"][["site_id", "ts", "err"]], on=["site_id", "ts"], suffixes=("_a", "_b"),
        validate="one_to_one")
    corr = float(joined.err_a.corr(joined.err_b))
    # Compare history-length strata using training-period observed days only.
    support_days = gen_train.assign(target_day=(gen_train.ts - pd.Timedelta(hours=1)).dt.floor("D"))
    site_days = support_days.groupby("site_id").target_day.nunique()
    m_history = scored_frames["A"][["site_id", "ts", "energy", "pred", "err"]].copy()
    m_history = m_history.merge(scored_frames["B"][["site_id", "ts", "pred", "err"]],
        on=["site_id", "ts"], suffixes=("_a", "_b"), validate="one_to_one")
    m_history = m_history.merge(scored_frames["C"][["site_id", "ts", "pred", "err"]],
        on=["site_id", "ts"], validate="one_to_one")
    m_history = m_history.rename(columns={"pred": "pred_c", "err": "err_c"})
    m_history["history_days"] = m_history.site_id.map(site_days).fillna(0)
    m_history["history_bin"] = pd.cut(m_history.history_days, [-1, 180, 540, np.inf],
        labels=["<=180d", "181-540d", ">540d"])
    history_metrics = {}
    for label, h in m_history.groupby("history_bin", observed=False):
        history_metrics[str(label)] = {"site_hours": int(len(h)),
            "site_MAE_A": float(h.err_a.abs().mean()) if len(h) else None,
            "site_MAE_B": float(h.err_b.abs().mean()) if len(h) else None,
            "site_MAE_C": float(h.err_c.abs().mean()) if len(h) else None}

    pred_paths = {"B": {"path": str(candidate_path.relative_to(ROOT)), "sha256": sha256(candidate_path)}}
    for name, pred in (("C", blended),):
        path = OUT / f"forecast_{name.lower()}_sites.parquet"
        pred.to_parquet(path, index=False)
        pred_paths[name] = {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
    report = {"status": "PILOT_COMPLETED", "evaluation": {"start_inclusive": str(pa),
        "end_inclusive": str(pb), "timestamps": len(eval_ts), "actual_site_hours": len(actual),
        "expected_site_hour_grid": expected_site_rows}, "support": support,
        "model": {"unit": "WB station cluster", "labels": "sum observed energy / sum observed capacity",
            "min_cov": MIN_COV, "seed": SEED, "features": len(features),
            "feature_columns": features, "params": PARAMS, "station_id_in_features": False,
            "GFS_ECMWF_UM": False, "training_rows_after_daylight": fit_metadata["training_rows_after_daylight"]},
        "scores": metrics, "C_minus_A_W": metrics["C"]["W"] - metrics["A"]["W"],
        "residual_correlation_A_B_site_hour": corr, "history_bin_site_MAE": history_metrics,
        "top_gain_features": fit_metadata["top_gain_features"],
        "input_sha256": {"baseline_A": sha256(BASELINE_PATH)},
        "prediction_files": pred_paths, "lightgbm": lgb.__version__,
        "bootstrap": None if metrics["C"]["W"] >= metrics["A"]["W"] else "pending stability gate; only run if gain is evident across groups and months"}
    (OUT / "pilot_result.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--score-existing", action="store_true")
    args = parser.parse_args()
    modes = [args.audit, args.pilot, args.score_existing]
    if sum(modes) != 1:
        parser.error("choose exactly one of --audit, --pilot, or --score-existing")
    mode = "audit" if args.audit else "pilot" if args.pilot else "score-existing"
    print(json.dumps(main(mode), indent=2, default=str))
