"""Research-only, forward OOF daily calibration of fixed site forecasts.

Train only on earlier OOF residuals. Prediction features use complete site
forecast grids and issued weather; observed availability is used only to
construct past labels and to score. Missing weather falls back to factor 1.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Optional isolated pure-Python packages; the main scientific stack has
# already been imported from the selected, policy-approved environment.
optional = Path(__file__).resolve().parents[3] / "oibc-dependencies"
if optional.is_dir():
    sys.path.append(str(optional))
import features as F
import scoring as sc


def day(ts):
    return (ts - pd.Timedelta(hours=1)).dt.floor("D")


def build_weather(path):
    wx = pd.read_parquet(path)
    wx["ts"] = sc.to_ts(wx.ts)
    if wx.duplicated(["ts", "pt"]).any():
        raise ValueError("duplicate weather keys")
    h = wx.groupby("ts").agg(ghi=("shortwave_radiation", "mean"),
                              ghi_n=("shortwave_radiation", "count"),
                              cloud=("cloud_cover", "mean"), cloud_n=("cloud_cover", "count")).reset_index()
    h = h[h.ts.dt.hour.between(9, 16)].copy()
    idx = pd.DatetimeIndex(h.ts)
    _, _, cosz = F.solar(idx, np.full(len(h), 36.), np.full(len(h), 127.5))
    cosz = np.clip(cosz, 0, 1)
    safe = np.maximum(cosz, 1e-3)
    h["clear"] = np.where(cosz > 0, 1098 * safe * np.exp(-0.057 / safe), 0)
    h["valid"] = (h.ghi_n >= 20) & (h.cloud_n >= 20)
    h["day"] = day(h.ts)
    d = h.groupby("day").agg(ghi=("ghi", "sum"), cloud=("cloud", "mean"),
                             clear=("clear", "sum"), count=("valid", "sum"), n=("ts", "size"))
    d["valid"] = (d["count"] == 8) & (d.n == 8) & (d.clear > 0)
    d["clearness"] = d.ghi / d.clear.replace(0, np.nan)
    doy = d.index.dayofyear.to_numpy()
    d["sin"], d["cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return d


def frame(path, start, end, sites, comp, weather):
    a, b = sc.window(start, end)
    pred = pd.read_parquet(path)
    pred["ts"] = sc.to_ts(pred.ts)
    pred = pred[(pred.ts >= a) & (pred.ts <= b)].copy()
    if pred.duplicated(["site_id", "ts"]).any() or pred.kwh.isna().any() or not np.isfinite(pred.kwh).all() or (pred.kwh < 0).any():
        raise ValueError("invalid predictions")
    pred["group"] = pred.site_id.map(comp)
    if pred.group.isna().any():
        raise ValueError("unknown site")
    expected = pd.date_range(a, b, freq="h")
    if len(pred) != len(expected) * len(sites) or not pred.ts.isin(expected).all():
        raise ValueError("full prediction grid required")
    full = pred.groupby(["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "full_pred"})
    full["day"] = day(full.ts)
    feat = full.groupby(["group", "day"]).full_pred.sum().rename("full_daily").reset_index()
    cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    feat["full_cf"] = feat.full_daily / feat.group.map(cap)
    feat = feat.join(weather, on="day")

    actual = sc.load_actual(start, end)
    if actual.duplicated(["site_id", "ts"]).any():
        raise ValueError("duplicate actuals")
    actual["group"] = actual.site_id.map(comp)
    actual["cap"] = actual.site_id.map(sites.set_index("site_id").capacity_kw)
    m = actual.merge(pred[["site_id", "ts", "kwh"]], on=["site_id", "ts"], how="left", validate="one_to_one")
    if m.kwh.isna().any() or m.group.isna().any():
        raise ValueError("missing observed-site prediction")
    h = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), pred=("kwh", "sum"), cap=("cap", "sum"))
    h["day"] = day(h.ts)
    h["smp"] = h.ts.map(sc.load_smp())
    if h.smp.isna().any() or (h.smp < 0).any():
        raise ValueError("missing or negative SMP")
    h["weight"] = 0.1 * h.smp * sc.k_weight(h.ts)
    labels = h.groupby(["group", "day"]).agg(act=("act", "sum"), obs_pred=("pred", "sum"), avail=("cap", "mean"), hours=("ts", "size")).reset_index()
    labels["coverage"] = labels.avail / labels.group.map(cap)
    labels["ratio"] = labels.act / labels.obs_pred.replace(0, np.nan)
    return feat.merge(labels, on=["group", "day"], validate="one_to_one"), h


COLS = {"B_ghi": ["ghi"], "C_clearness": ["clearness"],
        "D_lgb": ["ghi", "clearness", "cloud", "sin", "cos", "full_cf"]}


def factors(train, test, name):
    cols = COLS[name]
    result = np.ones(len(test))
    for group in ("G1", "G2"):
        tr = train[(train.group == group) & train.valid.fillna(False) & (train.coverage >= 0.1) & (train.hours == 24)]
        tr = tr.dropna(subset=cols + ["ratio"])
        ev = (test.group == group) & test.valid.fillna(False) & test[cols].notna().all(axis=1)
        if not ev.any():
            print(f"{name} {group}: no usable forecast days; fallback factor=1", flush=True)
            continue
        if len(tr) < 30:
            raise ValueError(f"insufficient history for {name}/{group}: {len(tr)}")
        if name == "D_lgb":
            models = [lgb.LGBMRegressor(n_estimators=150, learning_rate=0.03, num_leaves=7,
                       min_child_samples=20, reg_lambda=5, verbosity=-1, n_jobs=2,
                       random_state=seed).fit(tr[cols], tr.ratio.clip(0.5, 1.5)) for seed in (13, 37)]
            value = np.mean([model.predict(test.loc[ev, cols]) for model in models], axis=0)
        else:
            model = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(tr[cols], tr.ratio.clip(0.5, 1.5))
            value = model.predict(test.loc[ev, cols])
        result[np.flatnonzero(ev)] = np.clip(value, 0.5, 1.5)
        print(f"{name} {group}: train_days={len(tr)} evaluated_weather_days={int(ev.sum())}", flush=True)
    return result


def scores(h, daily, factors_by_name):
    d = h.merge(daily[["group", "day", "clearness"] + list(factors_by_name)], on=["group", "day"], validate="many_to_one")
    d["month"] = d.day.dt.strftime("%Y-%m")
    d["period"] = np.select([d.ts.dt.hour.between(8, 10), d.ts.dt.hour.between(11, 13), d.ts.dt.hour.between(14, 16)], ["morning", "noon", "afternoon"], default="other")
    d["season"] = d.day.dt.month.map({12:"winter",1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",6:"summer",7:"summer",8:"summer",9:"autumn",10:"autumn",11:"autumn"})
    d["sky"] = np.select([d.clearness < 0.35, d.clearness > 0.65], ["cloudy", "clear"], default="middle_or_missing")
    # Calendar features are known before the forecast cutoff; use the existing
    # holiday definitions when the optional package is present.
    try:
        off = F.off_days()
        dates = d.day.dt.tz_localize(None)
        d["daytype"] = np.select([dates.isin(off), dates.dt.dayofweek >= 5], ["holiday", "weekend"], default="weekday")
    except ImportError:
        d["daytype"] = np.where(d.day.dt.dayofweek >= 5, "weekend_or_holiday", "weekday_or_holiday")
    d["error_sign"] = np.where(d.pred >= d.act, "over_or_equal", "under")
    baseerr = d.pred - d.act
    baseline_daily = (d.weight * baseerr.abs()).groupby(d.day).sum().sort_index()
    rng = np.random.default_rng(20261106)
    days = len(baseline_daily)
    blocks = [np.arange(i, min(i + 7, days)) for i in range(0, days, 7)]
    draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
    out = {}
    for name in factors_by_name:
        err = d.pred * d[name] - d.act
        pen = d.weight * err.abs()
        total = float(pen.sum())
        daily_error = (d.assign(p=d.pred*d[name]).groupby(["group", "day"])[["p", "act"]].sum().eval("p-act").abs().mean())
        delta_day = pen.groupby(d.day).sum().reindex(baseline_daily.index).to_numpy() - baseline_daily.to_numpy()
        block_delta = np.array([delta_day[ix].sum() for ix in blocks])
        ci = np.quantile(block_delta[draws].sum(axis=1), [0.025, 0.975])
        out[name] = {"W": total, "midday_W": float(pen[d.ts.dt.hour.between(11,15)].sum()),
                     "daily_mae": float(daily_error), "residual_corr_baseline": float(err.corr(baseerr)),
                     "bootstrap_delta_W_ci95": ci.tolist(),
                     "monthly_W": pen.groupby(d.month).sum().to_dict(),
                     "segments": {key: pen.groupby(d[key]).sum().to_dict() for key in ("period", "season", "sky", "daytype", "error_sign")}}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-pred", required=True)
    ap.add_argument("--test-pred", required=True)
    ap.add_argument("--train-start", required=True)
    ap.add_argument("--train-end", required=True)
    ap.add_argument("--test-start", required=True)
    ap.add_argument("--test-end", required=True)
    ap.add_argument("--weather", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if pd.Timestamp(a.train_end) > pd.Timestamp(a.test_start):
        raise ValueError("future training prohibited")
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    weather = build_weather(a.weather)
    tr, _ = frame(a.train_pred, a.train_start, a.train_end, sites, comp, weather)
    te, hourly = frame(a.test_pred, a.test_start, a.test_end, sites, comp, weather)
    names = ["A_baseline"] + list(COLS)
    te["A_baseline"] = 1.0
    for name in COLS:
        te[name] = factors(tr, te, name)
    metrics = scores(hourly, te, names)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    for name, result in metrics.items():
        print(f"{name}: W={result['W']:.2f} delta={(result['W']/metrics['A_baseline']['W']-1)*100:+.3f}% "
              f"midday={result['midday_W']:.2f} daily_mae={result['daily_mae']:.2f}")


if __name__ == "__main__":
    main()
