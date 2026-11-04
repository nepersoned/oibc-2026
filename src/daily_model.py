"""일일 총량 날씨 모델 — 집합별 하루 발전량(kWh/kW)을 하루 단위 날씨 요약으로 예측하고,
시간별 예측의 하루 합을 그쪽으로 당긴다 (시간대 모양은 유지).

    pred'(t) = pred(t) × (D̂_day / Σ_day pred)^β       β ∈ [0, 1] 은 검증으로 선택

근거: 집합×일 총량을 완벽히 맞히면 W 가 약 49% 감소 (src/analyze 오라클). 페널티 절반이 '그날 얼마나 맑은가'.

    .venv/Scripts/python.exe src/daily_model.py --mode val --bu outputs/val_rich_ext_sites.parquet \
        --agg outputs/val_agg_group.parquet --alpha 0.5
    .venv/Scripts/python.exe src/daily_model.py --mode submit --out outputs/test_daily.parquet
출력은 집계값만.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_model as A  # noqa: E402
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

t0 = time.time()
log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)
PARAMS = dict(n_estimators=1200, learning_rate=0.02, num_leaves=15, min_child_samples=15,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.4, reg_lambda=2.0, verbose=-1, n_jobs=4)
SEEDS = (0, 1, 2, 3, 4)


def daily_features(gw: pd.DataFrame, ext: pd.DataFrame | None, sites, comp) -> pd.DataFrame:
    """(group, tday) 하루 요약: 집합 날씨 주간(9~16시) 평균, 외부 일사량 하루 합(격자점별), 맑은날 일사량 합."""
    g = gw.copy()
    g["tday"] = F.target_day(g.ts)
    day = g[g.ts.dt.hour.between(9, 16)]
    num = [c for c in g.columns if c.startswith("g_")]
    d = day.groupby(["group", "tday"])[num].mean().add_suffix("_day")
    d = d.join(g.groupby(["group", "tday"])[num].max().add_suffix("_max"))
    d = d.reset_index()
    if ext is not None:
        e = ext.copy()
        e["tday"] = F.target_day(e.ts)
        cols = [c for c in e.columns if c.startswith("ext_") and ("_ghi" in c) and not c.endswith(("_dsum", "_lag1", "_lead1"))]
        es = e.groupby("tday")[cols].sum(min_count=1).add_suffix("_sum")
        cc = [c for c in e.columns if c.endswith("_cc")]
        es = es.join(e[e.ts.dt.hour.between(9, 16)].groupby("tday")[cc].mean().add_suffix("_day"))
        d = d.merge(es.reset_index(), on="tday", how="left")
    # 맑은날 기준 하루 일사량 (집합 무게중심)
    s = sites.assign(group=sites.site_id.map(comp))
    cen = s.groupby("group").apply(lambda x: pd.Series({"lat": np.average(x.lat, weights=x.capacity_kw),
                                                        "lon": np.average(x.lon, weights=x.capacity_kw)}),
                                   include_groups=False)
    hrs = pd.date_range(d.tday.min(), d.tday.max() + pd.Timedelta(days=1), freq="h", tz=sc.TZ)
    cs = []
    for grp, row in cen.iterrows():
        el, _, cz = F.solar(pd.DatetimeIndex(hrs), np.full(len(hrs), row.lat), np.full(len(hrs), row.lon))
        czc = np.clip(cz, 1e-3, None)
        ghi = np.where(cz > 0, 1098 * czc * np.exp(-0.057 / czc), 0)
        t = pd.DataFrame({"tday": F.target_day(pd.Series(hrs)), "cs": ghi}).groupby("tday").cs.sum()
        cs.append(t.rename("cs_sum").reset_index().assign(group=grp))
    d = d.merge(pd.concat(cs), on=["group", "tday"], how="left")
    doy = d.tday.dt.day_of_year
    d["doy_sin"], d["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    d["gcode"] = (d.group == "G2").astype("int8")
    return d


def daily_targets(gen, sites, comp, min_cov: float) -> pd.DataFrame:
    t = A.targets(gen, sites, comp, min_cov=0.0)
    t["tday"] = F.target_day(t.ts)
    day = t[t.ts.dt.hour.between(10, 15)].groupby(["group", "tday"])["cov"].mean().rename("cov_mid")
    d = t.groupby(["group", "tday"]).agg(act=("act", "sum"), cap=("cap_avail", "mean"))
    d = d.join(day)
    d["y"] = d.act / d.cap                                      # kWh/kW (보고 중 용량 기준)
    return d[d.cov_mid >= min_cov].reset_index()


def fit_predict(tr: pd.DataFrame, pr: pd.DataFrame) -> np.ndarray:
    feats = [c for c in tr.columns if c not in {"group", "tday", "act", "cap", "cov_mid", "y"}]
    preds = []
    for s in SEEDS:
        m = lgb.LGBMRegressor(**{**PARAMS, "random_state": s}).fit(tr[feats], tr.y)
        preds.append(m.predict(pr[feats]))
    imp = pd.Series(m.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
    log(f"일일 모델 학습 {len(tr):,}일×집합, 특징 {len(feats)}  중요도 상위: " + ", ".join(imp.index[:8]))
    return np.clip(np.mean(preds, axis=0), 0, None)


def rescale(hourly: pd.DataFrame, daily: pd.DataFrame, beta: float) -> pd.Series:
    """hourly: group, ts, pred, cap_avail / daily: group, tday, d_hat(kWh/kW) → 조정된 pred."""
    h = hourly.copy()
    h["tday"] = F.target_day(h.ts)
    h = h.merge(daily[["group", "tday", "d_hat"]], on=["group", "tday"], how="left")
    capd = h.groupby(["group", "tday"]).cap_avail.transform("mean")
    s = h.groupby(["group", "tday"]).pred.transform("sum")
    r = (h.d_hat * capd / s.replace(0, np.nan)).clip(0.3, 3).fillna(1.0)
    return h.pred * r ** beta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["val", "submit"], required=True)
    ap.add_argument("--train-years", type=int, default=3)
    ap.add_argument("--min-cov", type=float, default=0.2)
    ap.add_argument("--ext", choices=["none", "mean"], default="mean")
    ap.add_argument("--composition", default=None)
    ap.add_argument("--bu", default=None, help="발전소 모델 검증 예측")
    ap.add_argument("--agg", default=None, help="집합 모델 검증 예측 (group, ts, pred)")
    ap.add_argument("--alpha", type=float, default=0.5, help="집합 모델 비중")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    ext = F.load_ext(a.ext)
    fa, fb = A.forecasts("train")
    gw_tr = A.group_weather(fa, fb, sites, comp)
    dtr_all = daily_features(gw_tr, ext, sites, comp)
    log("하루 요약 특징 준비")

    if a.mode == "val":
        pa, pb = sc.window(sc.VAL_START, sc.VAL_END)
        gen = A.load_gen(pa - pd.DateOffset(years=a.train_years), pb)
        tr = daily_targets(gen[gen.ts < pa], sites, comp, a.min_cov).merge(dtr_all, on=["group", "tday"])
        tr = tr[tr.tday < pa.floor("D")]
        pr = dtr_all[(dtr_all.tday >= pa.floor("D")) & (dtr_all.tday < pb.floor("D"))].copy()
        pr["d_hat"] = fit_predict(tr, pr)

        act = A.load_gen(pa, pb)
        act_t = A.targets(act, sites, comp, min_cov=0.0)
        dv = daily_targets(act, sites, comp, 0.0).merge(pr[["group", "tday", "d_hat"]], on=["group", "tday"])
        print(f"일일 kWh/kW MAE: 모델 {np.mean(np.abs(dv.d_hat - dv.y)):.3f}  (실적 평균 {dv.y.mean():.3f})")

        bu = pd.read_parquet(a.bu)
        bu["ts"] = sc.to_ts(bu.ts)
        bu = act[["site_id", "ts"]].merge(bu, on=["site_id", "ts"], how="left").fillna({"kwh": 0})
        bu["group"] = bu.site_id.map(comp)
        h = act_t[["group", "ts", "cap_avail"]].merge(
            bu.groupby(["group", "ts"], as_index=False).kwh.sum(), on=["group", "ts"], how="left")
        if a.agg:
            g = pd.read_parquet(a.agg)
            g["ts"] = sc.to_ts(g.ts)
            h = h.merge(g[["group", "ts", "pred"]].rename(columns={"pred": "agg"}), on=["group", "ts"], how="left")
            h["pred"] = (1 - a.alpha) * h["kwh"].fillna(0) + a.alpha * h["agg"].fillna(0)
        else:
            h["pred"] = h.kwh.fillna(0)
        smp = sc.load_smp()
        base = A.group_score(h[["group", "ts", "pred"]], act_t, smp)
        print(f"시간 모델(혼합) W {base:,.0f}")
        for beta in (0.25, 0.5, 0.75, 1.0):
            W = A.group_score(h[["group", "ts"]].assign(pred=rescale(h, pr, beta)), act_t, smp)
            print(f"  일일 총량 당기기 β={beta:.2f}: W {W:,.0f}  ({(W / base - 1) * 100:+.2f}%)")
        if a.out:
            pr[["group", "tday", "d_hat"]].to_parquet(a.out, index=False)
        return

    pa, pb = sc.window("2025-06-01", "2026-06-01")
    gen = A.load_gen(pa - pd.DateOffset(years=a.train_years), pa)
    tr = daily_targets(gen[gen.ts < pa], sites, comp, a.min_cov).merge(dtr_all, on=["group", "tday"])
    fa_te, fb_te = A.forecasts("test")
    dte = daily_features(A.group_weather(fa_te, fb_te, sites, comp), ext, sites, comp)
    dte = dte[(dte.tday >= pa.floor("D")) & (dte.tday < pb.floor("D"))].copy()
    dte["d_hat"] = fit_predict(tr, dte)
    out = a.out or os.path.join(sc.ROOT, "outputs", "test_daily.parquet")
    dte[["group", "tday", "d_hat"]].to_parquet(out, index=False)
    log(f"저장: {out}")


if __name__ == "__main__":
    main()
