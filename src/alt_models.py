"""다른 각도의 앙상블 구성원 3종 — 출력은 집합 예측 (group, ts, pred). ensemble.py --agg 에 그대로 넣는다.

① regional : 같은 A 관측지점을 쓰는 발전소끼리 묶은 지역(61개) 합계 CF 를 LightGBM 으로 예측 → 집합별 합산
② analog   : 시각별로 내일 예보와 가장 비슷한 과거 시각 K 개의 실제 집합 CF 를 거리가중 평균 (kNN)
③ linear   : 표준화한 날씨·태양 특징에 대한 Ridge 회귀 (시각대별), 물리적으로 단순한 기준

    .venv/Scripts/python.exe src/alt_models.py --model regional --mode val --out outputs/val_alt_regional.parquet
    .venv/Scripts/python.exe src/alt_models.py --model analog --mode submit --out outputs/test_alt_analog.parquet
출력은 집계 점수만.
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
TEST_END = "2026-06-01"


def windows(mode: str):
    if mode == "val":
        pa, pb = sc.window(sc.VAL_START, sc.VAL_END)
    else:
        pa, pb = sc.window("2025-06-01", TEST_END)
    return pa, pb


def group_frames(mode, comp, sites, ext, train_years=3, min_cov=0.2, wide=True):
    """집합 단위 학습/예측 설계 행렬 (agg_model 과 같은 특징)."""
    pa, pb = windows(mode)
    fa, fb = A.forecasts("train")
    gw_tr = A.group_weather(fa, fb, sites, comp)
    wd_tr = A.wide(fa, fb) if wide else pd.DataFrame(index=pd.DatetimeIndex([], tz=sc.TZ, name="ts"))
    if ext is not None:
        wd_tr = wd_tr.join(ext.set_index("ts"), how="outer") if wide else ext.set_index("ts")
    gen = A.load_gen(pa - pd.DateOffset(years=train_years), pb)
    tr = A.targets(gen[gen.ts < pa], sites, comp, min_cov)
    dtr = A.design(tr, gw_tr, wd_tr, sites, comp)
    if mode == "val":
        act_t = A.targets(gen[gen.ts >= pa], sites, comp, 0.0)
        idx = act_t[["group", "ts", "cap_avail"]]
        gw_pr, wd_pr = gw_tr, wd_tr
    else:
        fa_te, fb_te = A.forecasts("test")
        gw_pr = A.group_weather(fa_te, fb_te, sites, comp)
        wd_pr = A.wide(fa_te, fb_te) if wide else pd.DataFrame(index=pd.DatetimeIndex([], tz=sc.TZ, name="ts"))
        if ext is not None:
            wd_pr = wd_pr.join(ext.set_index("ts"), how="outer") if wide else ext.set_index("ts")
        total = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
        ts = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
        idx = pd.MultiIndex.from_product([sorted(total.index), ts], names=["group", "ts"]).to_frame(index=False)
        idx["cap_avail"] = idx.group.map(total).to_numpy()
    dpr = A.design(idx, gw_pr, wd_pr, sites, comp)
    return dtr, dpr


# ------------------------------------------------------------------ ① 지역 모델
def regional(mode, comp, sites, ext):
    region = sites.set_index("site_id").wa_station                   # 지역 = A 관측지점
    dtr, dpr = group_frames(mode, region, sites, ext, wide=False)
    dtr = dtr[dtr.elev > -2]
    dtr["rcode"] = dtr.group.str[2:].astype(int)
    dpr["rcode"] = dpr.group.str[2:].astype(int)
    feats = [c for c in A.feats_of(dtr) if c != "gcode"]
    log(f"지역 모델 학습 {len(dtr):,}행 × {len(feats)}")
    raw = np.zeros(len(dpr))
    for s in range(3):
        m = lgb.LGBMRegressor(n_estimators=1500, learning_rate=0.03, num_leaves=63, min_child_samples=50,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.5, verbose=-1, n_jobs=-1,
                              random_state=s).fit(dtr[feats], dtr.cf.clip(0, 1.2), categorical_feature=["rcode"])
        raw += m.predict(dpr[feats]) / 3
    dpr["pred"] = np.where(dpr.elev > -2, np.clip(raw, 0, None), 0) * dpr.cap_avail.to_numpy()
    dpr["G"] = dpr.group.map(sites.assign(r=region.values, g=sites.site_id.map(comp)).groupby("r").g.first())
    # 한 지역의 발전소가 두 집합에 나뉘어 있으면 용량 비율로 배분
    share = sites.assign(r=sites.wa_station, g=sites.site_id.map(comp)).pivot_table(
        index="r", columns="g", values="capacity_kw", aggfunc="sum").fillna(0)
    share = share.div(share.sum(1), axis=0)
    out = []
    for g in share.columns:
        out.append(dpr.assign(group_out=g, pred=dpr.pred * dpr.group.map(share[g]).to_numpy()))
    o = pd.concat(out)
    return o.groupby(["group_out", "ts"], as_index=False).pred.sum().rename(columns={"group_out": "group"})


# ------------------------------------------------------------------ ② 아날로그 (kNN)
ANALOG_FEATS = ["ext_ghi_ens", "ext_jma_seamless_ghi", "ext_jx_direct_radiation", "ext_jx_diffuse_radiation",
                "ext_ghi_ens_dsum", "g_wb_uv_idx", "g_wb_cloud", "g_wa_cloud", "g_wb_cloud_daymean",
                "ghi_cs", "cosz", "doy_sin", "doy_cos"]


def analog(mode, comp, sites, ext, k=30):
    from sklearn.neighbors import KNeighborsRegressor
    dtr, dpr = group_frames(mode, comp, sites, ext, wide=False)
    feats = [c for c in ANALOG_FEATS if c in dtr.columns]
    dtr = dtr[(dtr.elev > 0)].dropna(subset=feats)
    mu, sd = dtr[feats].mean(), dtr[feats].std().replace(0, 1)
    w = pd.Series(1.0, index=feats)
    w[["ext_ghi_ens", "ext_jma_seamless_ghi", "ghi_cs", "cosz"]] = 2.0         # 일사·태양 위치 강조
    pred = np.zeros(len(dpr))
    for g in dtr.group.unique():
        for h in range(24):
            tr = dtr[(dtr.group == g) & (dtr.hour == h)]
            msk = ((dpr.group == g) & (dpr.hour == h) & (dpr.elev > 0)).to_numpy()
            if len(tr) < k or not msk.any():
                continue
            Xp = dpr.loc[msk, feats].fillna(mu)
            knn = KNeighborsRegressor(n_neighbors=k, weights="distance").fit(((tr[feats] - mu) / sd * w).to_numpy(), tr.cf.clip(0, 1.2))
            pred[msk] = knn.predict(((Xp - mu) / sd * w).to_numpy())
    log(f"아날로그 학습 {len(dtr):,}행, K={k}, 특징 {len(feats)}")
    return dpr[["group", "ts"]].assign(pred=np.clip(pred, 0, None) * dpr.cap_avail.to_numpy())


# ------------------------------------------------------------------ ③ 선형 (Ridge)
def linear(mode, comp, sites, ext):
    from sklearn.linear_model import Ridge
    dtr, dpr = group_frames(mode, comp, sites, ext, wide=False)
    feats = [c for c in A.feats_of(dtr) if dtr[c].dtype.kind in "fiu"]
    dtr = dtr[dtr.elev > 0]
    mu, sd = dtr[feats].mean(), dtr[feats].std().replace(0, 1)
    pred = np.zeros(len(dpr))
    for h in range(24):
        tr = dtr[dtr.hour == h]
        msk = ((dpr.hour == h) & (dpr.elev > 0)).to_numpy()
        if len(tr) < 50 or not msk.any():
            continue
        X = ((tr[feats] - mu) / sd).fillna(0)
        r = Ridge(alpha=30.0).fit(X, tr.cf.clip(0, 1.2))
        pred[msk] = r.predict(((dpr.loc[msk, feats] - mu) / sd).fillna(0))
    log(f"선형 모델 학습 {len(dtr):,}행 × {len(feats)}")
    return dpr[["group", "ts"]].assign(pred=np.clip(pred, 0, None) * dpr.cap_avail.to_numpy())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["regional", "analog", "linear"], required=True)
    ap.add_argument("--mode", choices=["val", "submit"], required=True)
    ap.add_argument("--composition", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    ext = F.load_ext("mean")
    p = {"regional": regional, "analog": analog, "linear": linear}[a.model](a.mode, comp, sites, ext)
    p.to_parquet(a.out, index=False)
    if a.mode == "val":
        act_t = A.targets(A.load_gen(*sc.window(sc.VAL_START, sc.VAL_END)), sites, comp, 0.0)
        print(f"[{a.model}] 검증 W {A.group_score(p, act_t, sc.load_smp()):,.0f}")
    log(f"저장: {a.out}")


if __name__ == "__main__":
    main()
