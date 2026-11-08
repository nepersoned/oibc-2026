"""그룹(집합) 단위 직접 예측 모델 + 발전소 단위 모델과 혼합.

채점은 집합 합계 단위이므로, 집합 설비이용률 CF_g(t) = Σ 실적 / Σ (보고 중인) 설비용량 을 직접 학습한다.
입력: 집합의 용량가중 예보 평균, 전국 전 관측지점 예보(넓은 형식), 대상일 내 문맥, 태양 위치.

    # 검증 (기본 2024-06 ~ 2025-05), --bu 로 발전소 단위 예측을 주면 혼합 비율별 점수도 출력
    .venv/Scripts/python.exe src/agg_model.py --mode val --bu outputs/val_rich_sites.parquet
    # 제출용 집합 예측 저장
    .venv/Scripts/python.exe src/agg_model.py --mode submit --out outputs/test_agg_group.parquet

출력은 집계값만.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

t0 = time.time()
log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)

GVARS = {"wa": ["wa_cloud", "wa_humidity", "wa_rain", "wa_temp", "wa_cloud_dmean", "wa_cloud_daymean",
                "wa_cloud_lag1", "wa_cloud_lead1", "wa_cloud_r10"],
         "wb": ["wb_cloud", "wb_uv_idx", "wb_vis", "wb_precip_prob", "wb_rel_hum", "wb_ceiling", "wb_temp",
                "wb_cloud_dmean", "wb_cloud_daymean", "wb_uv_idx_lag1", "wb_uv_idx_lead1", "wb_uv_idx_r10",
                "wb_cloud_r10"]}
WIDE = {"wa": ["wa_cloud", "wa_humidity"], "wb": ["wb_cloud", "wb_uv_idx"]}
PARAMS = dict(n_estimators=1500, learning_rate=0.02, num_leaves=31, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.5, reg_lambda=1.0, verbose=-1, n_jobs=-1)


def forecasts(split: str):
    fa = F.prep_forecast(F.load_forecast(split, "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast(split, "wb", F.WB_ALL), "wb", F.WB_ALL)
    return fa, fb


def wide(fa: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    """시각 × (변수@관측지점) 넓은 표 — 전국 예보장 전체."""
    parts = []
    for f, prov in ((fa, "wa"), (fb, "wb")):
        st = f"{prov}_station"
        p = f.pivot_table(index="ts", columns=st, values=WIDE[prov])
        p.columns = [f"{v}@{s}" for v, s in p.columns]
        parts.append(p)
    return parts[0].join(parts[1], how="outer").astype("float32")


WX_CUT = os.environ.get("OIBC_WX2")                     # 날씨 보정 v2 컷오프 (예: 2024-06-01) — 설정 시 사용


def attach_wx(fa: pd.DataFrame, fb: pd.DataFrame, cutoff: str | None):
    """날씨 보정 v2 예측(hat_*)을 관측지점 예보 표에 붙인다 → group_weather 가 용량가중 평균."""
    if not cutoff:
        return fa, fb
    out = []
    for f, prov in ((fa, "wa"), (fb, "wb")):
        w = pd.read_parquet(os.path.join(sc.ROOT, "outputs", f"wx2_{cutoff}_{prov}.parquet"))
        w["ts"] = w.ts.dt.tz_convert(sc.TZ).astype(f"datetime64[ns, {sc.TZ}]")
        out.append(f.merge(w, on=[f"{prov}_station", "ts"], how="left"))
    for prov in ("wa", "wb"):
        GVARS[prov] = GVARS[prov] + [c for c in out[0 if prov == "wa" else 1].columns
                                     if c.startswith("hat_") and c not in GVARS[prov]]
    return out[0], out[1]


def group_weather(fa: pd.DataFrame, fb: pd.DataFrame, sites: pd.DataFrame, comp: pd.Series) -> pd.DataFrame:
    """집합별 용량가중 예보 평균 (group, ts) — 집합의 '평균 날씨'."""
    out = []
    s = sites.assign(group=sites.site_id.map(comp))
    for f, prov in ((fa, "wa"), (fb, "wb")):
        st = f"{prov}_station"
        w = s.groupby(["group", st]).capacity_kw.sum().rename("w").reset_index()
        m = f[[st, "ts"] + GVARS[prov]].merge(w, on=st)
        vals = m[GVARS[prov]].mul(m.w, axis=0)
        vals[["group", "ts"]] = m[["group", "ts"]]
        num = vals.groupby(["group", "ts"]).sum()
        den = m.assign(**{c: m.w.where(m[c].notna(), 0) for c in GVARS[prov]}).groupby(["group", "ts"])[GVARS[prov]].sum()
        out.append((num / den.replace(0, np.nan)).add_prefix("g_"))
    return out[0].join(out[1], how="outer").reset_index()


def design(idx: pd.DataFrame, gw: pd.DataFrame, wd: pd.DataFrame, sites: pd.DataFrame,
           comp: pd.Series) -> pd.DataFrame:
    """idx: (group, ts) 행 → 특징."""
    d = idx.merge(gw, on=["group", "ts"], how="left").merge(wd, left_on="ts", right_index=True, how="left")
    s = sites.assign(group=sites.site_id.map(comp))
    cen = s.groupby("group").apply(lambda x: pd.Series({
        "lat": np.average(x.lat, weights=x.capacity_kw), "lon": np.average(x.lon, weights=x.capacity_kw)}),
        include_groups=False)
    d = d.merge(cen, left_on="group", right_index=True)
    ts = pd.DatetimeIndex(d.ts)
    d["elev"], d["azim"], d["cosz"] = F.solar(ts, d.lat.to_numpy(), d.lon.to_numpy())
    cz = np.clip(d.cosz.to_numpy(), 1e-3, None)
    d["ghi_cs"] = np.where(d.cosz > 0, 1098 * cz * np.exp(-0.057 / cz), 0).astype("float32")
    doy = ts.day_of_year.to_numpy()
    d["doy_sin"], d["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    d["hour"] = ts.hour.to_numpy()
    d["gcode"] = (d.group == "G2").astype("int8")
    if F.CALENDAR:
        cal = F.calendar(d.ts)
        for c in cal.columns:
            d[c] = cal[c].to_numpy()
    return d


def targets(gen: pd.DataFrame, sites: pd.DataFrame, comp: pd.Series, min_cov: float = 0.3) -> pd.DataFrame:
    """(group, ts) 실적 합, 보고 중 용량, CF. 용량 커버리지가 낮은 시각은 제외."""
    g = gen.merge(sites[["site_id", "capacity_kw"]], on="site_id")
    g["group"] = g.site_id.map(comp)
    t = g.groupby(["group", "ts"]).agg(act=("energy", "sum"), cap_avail=("capacity_kw", "sum")).reset_index()
    total = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    t["cov"] = t.cap_avail / t.group.map(total)
    t["cf"] = t.act / t.cap_avail
    return t[t["cov"] >= min_cov]


SOURCE = os.environ.get("OIBC_SRC", "all")              # all | nwp (수치예보만) | prov (대회 예보만)
BASE_COLS = {"elev", "azim", "cosz", "ghi_cs", "doy_sin", "doy_cos", "hour", "gcode", "dow", "is_hol", "is_off", "off_run"}


def feats_of(d: pd.DataFrame) -> list[str]:
    f = [c for c in d.columns if c not in {"group", "ts", "act", "cap_avail", "cov", "cf", "lat", "lon"}]
    if SOURCE == "nwp":
        f = [c for c in f if c.startswith("ext_") or c in BASE_COLS]
    elif SOURCE == "prov":
        f = [c for c in f if not c.startswith("ext_")]
    return f


def fit_predict(train_t, pred_idx, gw_tr, wd_tr, gw_pr, wd_pr, sites, comp, params):
    dtr = design(train_t, gw_tr, wd_tr, sites, comp)
    dtr = dtr[dtr.elev > -2]
    feats = feats_of(dtr)
    params = dict(params)
    seeds = params.pop("seeds", 1)                       # 시드 배깅: 여러 시드 평균
    algo = params.pop("algo", "lgb")                     # lgb | xgb | cat
    dpr = design(pred_idx, gw_pr, wd_pr, sites, comp)
    halflife = params.pop("halflife", None)              # 최근 데이터 가중: 반감기(년)
    csi = params.pop("csi", False)                       # 맑은날 지수 타깃: cf / (청천일사/1000)
    ref_mode = params.pop("ref", False)                  # True: 타깃 cf/기준CF (구조 모델) | "feat": 기준CF 를 특징으로만
    use_ref = ref_mode is True and "ref_cf" in dtr.columns
    raw = np.zeros(len(dpr))
    y = dtr.cf.clip(0, 1.2)
    if use_ref:
        r_tr = np.clip(dtr.ref_cf.to_numpy(), 0.02, None)
        r_pr = np.clip(dpr.ref_cf.fillna(0).to_numpy(), 0.02, None)
        keep = dtr.ref_cf.to_numpy() > 0.05                       # 기준이 거의 0인 새벽·저녁은 학습에서 제외
        y = (y / r_tr).clip(0, 1.5)
        dtr, y = dtr[keep], y[keep]
    if csi:
        cs_tr = np.clip(dtr.ghi_cs.to_numpy() / 1000.0, 0.03, None)
        cs_pr = np.clip(dpr.ghi_cs.to_numpy() / 1000.0, 0.03, None)
        y = (y / cs_tr).clip(0, 1.5)
    kw = params.pop("kweight", False)                    # 채점 가중: 11~15시 ×3 (SMP 는 미래값이라 제외)
    sw = None
    if halflife:
        age = (dtr.ts.max() - dtr.ts).dt.total_seconds().to_numpy() / (365.25 * 86400)
        sw = 0.5 ** (age / float(halflife))
        sw = sw / sw.mean()
    if kw:
        k = np.where(dtr.ts.dt.hour.between(11, 15), 3.0, 1.0)
        sw = k if sw is None else sw * k
        sw = sw / sw.mean()
    for s in range(seeds):
        if algo == "xgb":
            import xgboost as xgb
            m = xgb.XGBRegressor(n_estimators=2000, learning_rate=0.015, max_depth=5, min_child_weight=5,
                                 subsample=0.8, colsample_bytree=0.4, reg_lambda=2.0, tree_method="hist",
                                 random_state=100 + s, n_jobs=-1, **params).fit(dtr[feats], y)
        elif algo == "cat":
            from catboost import CatBoostRegressor
            m = CatBoostRegressor(iterations=2500, learning_rate=0.03, depth=6, l2_leaf_reg=3, rsm=0.3,
                                  random_seed=100 + s, verbose=0, thread_count=-1, **params).fit(dtr[feats], y)
        else:
            m = lgb.LGBMRegressor(**{**PARAMS, **params, "random_state": 100 + s}).fit(dtr[feats], y, sample_weight=sw)
        raw += m.predict(dpr[feats]) / seeds
    if csi:
        raw = raw * cs_pr
    if use_ref:
        raw = raw * r_pr
    cf = np.where(dpr.elev > -2, np.clip(raw, 0, None), 0.0)
    imp = pd.Series(m.feature_importances_, index=feats).sort_values(ascending=False)
    log(f"[{algo}] 학습 {len(dtr):,}행 × {len(feats)}  중요도 상위: " + ", ".join(imp.index[:10]))
    return dpr[["group", "ts"]].assign(cf_hat=cf)


def site_curves(gen: pd.DataFrame, sites: pd.DataFrame, min_n: int = 8) -> pd.Series:
    """발전소별 (월, 시) 맑은날 곡선 = 설비이용률 95% 분위. 표본 부족은 같은 B 관측지점 평균 → 전체 평균으로 대체."""
    cap = sites.set_index("site_id").capacity_kw
    g = gen.assign(cf=gen.energy / gen.site_id.map(cap), mo=gen.ts.dt.month, hr=gen.ts.dt.hour)
    q = g.groupby(["site_id", "mo", "hr"]).cf
    ref = q.quantile(0.95).where(q.size() >= min_n)
    st = sites.set_index("site_id").wb_station
    ref_df = ref.rename("v").reset_index().assign(st=lambda d: d.site_id.map(st))
    ref_st = ref_df.groupby(["st", "mo", "hr"]).v.mean()
    ref_all = g.groupby(["mo", "hr"]).cf.quantile(0.95)
    full = pd.MultiIndex.from_product([sites.site_id, range(1, 13), range(24)], names=["site_id", "mo", "hr"]).to_frame(index=False)
    a = ref.reindex(pd.MultiIndex.from_frame(full)).to_numpy()
    b = ref_st.reindex(pd.MultiIndex.from_arrays([full.site_id.map(st), full.mo, full.hr])).to_numpy()
    c = ref_all.reindex(pd.MultiIndex.from_frame(full[["mo", "hr"]])).to_numpy()
    full["v"] = np.where(np.isnan(a), np.where(np.isnan(b), c, b), a)
    return full.set_index(["site_id", "mo", "hr"]).v.fillna(0.0)


def ref_cf(curves: pd.Series, gen_rows: pd.DataFrame, sites: pd.DataFrame, comp: pd.Series) -> pd.Series:
    """(group, ts) 기준 CF = Σ 보고 중 발전소 용량 × 곡선 / Σ 용량. gen_rows: (site_id, ts) 보고 행."""
    cap = sites.set_index("site_id").capacity_kw
    r = gen_rows[["site_id", "ts"]].copy()
    r["mo"], r["hr"] = r.ts.dt.month, r.ts.dt.hour
    r["v"] = curves.reindex(pd.MultiIndex.from_frame(r[["site_id", "mo", "hr"]])).to_numpy()
    r["cap"] = r.site_id.map(cap)
    r["group"] = r.site_id.map(comp)
    t = r.groupby(["group", "ts"]).apply(lambda d: float((d.v * d.cap).sum() / d.cap.sum()), include_groups=False)
    return t.rename("ref_cf")


def attach_ref(train_t: pd.DataFrame, gen_train: pd.DataFrame, pred_rows: pd.DataFrame, pred_idx: pd.DataFrame,
               sites: pd.DataFrame, comp: pd.Series):
    """학습 행: 자기 12개월 블록을 뺀 실적으로 곡선 (누출 방지). 예측 행: **최근 12개월** 실적으로 곡선 (평가 연도에 가장 가까움)."""
    last = gen_train.ts.max()
    blk = ((last - gen_train.ts).dt.days // 365)
    parts = []
    for b in sorted(blk.unique()):
        curves = site_curves(gen_train[blk != b], sites)
        rows = gen_train[blk == b]
        parts.append(ref_cf(curves, rows, sites, comp))
    tr_ref = pd.concat(parts)
    train_t = train_t.merge(tr_ref.reset_index(), on=["group", "ts"], how="left")
    recent = gen_train[gen_train.ts > last - pd.DateOffset(months=12)]
    pr_ref = ref_cf(site_curves(recent, sites), pred_rows, sites, comp)
    pred_idx = pred_idx.merge(pr_ref.reset_index(), on=["group", "ts"], how="left")
    return train_t, pred_idx


def load_gen(a, b):
    g = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    g["ts"] = sc.to_ts(g.ts)
    g = g[(g.ts >= a) & (g.ts <= b)].copy()
    g["energy"] = g.energy.clip(lower=0)
    return g


def group_score(gp: pd.DataFrame, actual_t: pd.DataFrame, smp: pd.Series) -> float:
    """gp: group, ts, pred (보고 중 발전소 기준 kWh) / actual_t: group, ts, act → W."""
    m = actual_t[["group", "ts", "act"]].merge(gp, on=["group", "ts"], how="left").fillna({"pred": 0})
    w = 0.1 * m.ts.map(smp).to_numpy() * sc.k_weight(m.ts)
    return float((w * (m.pred - m.act).abs()).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["val", "submit"], required=True)
    ap.add_argument("--train-years", type=int, default=3)
    ap.add_argument("--val-start", default=sc.VAL_START)
    ap.add_argument("--val-end", default=sc.VAL_END)
    ap.add_argument("--composition", default=None)
    ap.add_argument("--bu", default=None, help="발전소 단위 예측 parquet (혼합용)")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-cov", type=float, default=0.3, help="학습에 쓸 최소 용량 커버리지")
    ap.add_argument("--ext", choices=["none", "mean"], default="mean")
    a = ap.parse_args()
    params = json.loads(a.params)

    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    smp = sc.load_smp()
    fa_tr, fb_tr = forecasts("train")
    wx_cut = WX_CUT if a.mode == "val" else (WX_CUT and "2025-06-01")
    fa_tr, fb_tr = attach_wx(fa_tr, fb_tr, wx_cut)
    ext = F.load_ext(a.ext)
    add_ext = (lambda w: w.join(ext.set_index("ts"), how="left")) if ext is not None else (lambda w: w)
    gw_tr, wd_tr = group_weather(fa_tr, fb_tr, sites, comp), add_ext(wide(fa_tr, fb_tr))
    log("예보 준비 완료")

    if a.mode == "val":
        pa, pb = sc.window(a.val_start, a.val_end)
        gen = load_gen(pa - pd.DateOffset(years=a.train_years), pb)
        tr = targets(gen[gen.ts < pa], sites, comp, a.min_cov)
        act = load_gen(pa, pb)
        act_t = targets(act, sites, comp, min_cov=0.0)            # 보고 중 발전소 기준 실적
        idx = act_t[["group", "ts"]]
        if params.get("ref"):
            tr, idx = attach_ref(tr, gen[gen.ts < pa], act[["site_id", "ts"]], idx, sites, comp)
            log(f"기준 CF 부착 — 학습 평균 {tr.ref_cf.mean():.3f}, 예측 평균 {idx.ref_cf.mean():.3f}")
        p = fit_predict(tr, idx, gw_tr, wd_tr, gw_tr, wd_tr, sites, comp, params)
        p = p.merge(act_t[["group", "ts", "cap_avail"]], on=["group", "ts"])
        p["pred"] = p.cf_hat * p.cap_avail
        W_agg = group_score(p[["group", "ts", "pred"]], act_t, smp)
        print(f"\n[집합 모델] W {W_agg:,.0f}")
        if a.out:
            p.to_parquet(a.out, index=False)
        if a.bu:
            bu = pd.read_parquet(a.bu)
            bu["ts"] = sc.to_ts(bu.ts)
            bu = act[["site_id", "ts"]].merge(bu, on=["site_id", "ts"], how="left")
            bu["group"] = bu.site_id.map(comp)
            bg = bu.groupby(["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "bu"})
            j = p.merge(bg, on=["group", "ts"], how="left").fillna({"bu": 0})
            W_bu = group_score(j[["group", "ts"]].assign(pred=j.bu), act_t, smp)
            print(f"[발전소 모델] W {W_bu:,.0f}")
            for alpha in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0):
                Wm = group_score(j[["group", "ts"]].assign(pred=alpha * j.pred + (1 - alpha) * j.bu), act_t, smp)
                print(f"  혼합 집합 {alpha:.1f} : W {Wm:,.0f}  (발전소 모델 대비 {(Wm / W_bu - 1) * 100:+.2f}%)")
        return

    pa, pb = sc.window("2025-06-01", "2026-06-01")
    gen = load_gen(pa - pd.DateOffset(years=a.train_years), pa)
    tr = targets(gen[gen.ts < pa], sites, comp, a.min_cov)
    fa_te, fb_te = attach_wx(*forecasts("test"), wx_cut)
    idx = pd.MultiIndex.from_product([["G1", "G2"], pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")],
                                     names=["group", "ts"]).to_frame(index=False)
    if params.get("ref"):                                              # 제출: 모든 발전소가 보고한다고 보고 기준 CF 계산
        all_rows = pd.MultiIndex.from_product([sites.site_id, idx.ts.unique()], names=["site_id", "ts"]).to_frame(index=False)
        tr, idx = attach_ref(tr, gen, all_rows, idx, sites, comp)
        log(f"기준 CF 부착 — 학습 평균 {tr.ref_cf.mean():.3f}, 예측 평균 {idx.ref_cf.mean():.3f}")
    p = fit_predict(tr, idx, gw_tr, wd_tr, group_weather(fa_te, fb_te, sites, comp), add_ext(wide(fa_te, fb_te)),
                    sites, comp, params)
    total = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    p["pred"] = p.cf_hat * p.group.map(total)
    out = a.out or os.path.join(sc.ROOT, "outputs", "test_agg_group.parquet")
    p.to_parquet(out, index=False)
    log(f"저장: {out}")


if __name__ == "__main__":
    main()
