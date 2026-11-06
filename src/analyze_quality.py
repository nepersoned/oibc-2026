"""학습 데이터 품질 점검 — 직선 보간·값 고정·출력제어 의심 구간 (집계값만 출력).

플래그 결과는 outputs/quality_flags.parquet (site_id, ts, flag) 로 저장 → 학습 제외 실험에 사용.

    .venv/Scripts/python.exe src/analyze_quality.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

MIN_RUN = 3


def runs(mask: pd.Series, key: pd.Series) -> pd.Series:
    """같은 key 안에서 연속 True 구간 길이."""
    blk = (mask != mask.groupby(key).shift()).cumsum()
    return mask.groupby([key, blk]).transform("size").where(mask, 0)


def main() -> None:
    sites = sc.load_sites().set_index("site_id")
    g = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    g["ts"] = sc.to_ts(g.ts)
    g = g.sort_values(["site_id", "ts"]).reset_index(drop=True)
    g["cap"] = g.site_id.map(sites.capacity_kw)
    g["cf"] = g.energy / g.cap
    el, _, _ = F.solar(pd.DatetimeIndex(g.ts), g.site_id.map(sites.lat).to_numpy(), g.site_id.map(sites.lon).to_numpy())
    g["day"] = el > 10
    # 시간 연속성 (행이 없는 시각은 끊김)
    cont = g.groupby("site_id").ts.diff().eq(pd.Timedelta(hours=1))
    d1 = g.groupby("site_id").energy.diff().where(cont)
    d2 = d1.groupby(g.site_id).diff().where(cont)
    nz = g.energy > 0.01 * g.cap

    lin = (d2.abs() <= 1e-6 * g.cap) & (d1.abs() > 1e-6 * g.cap) & nz      # 기울기 일정 & 변화 있음
    flat = (d1.abs() <= 1e-9 * g.cap) & nz & g.day                         # 값 그대로
    g["lin_run"] = runs(lin, g.site_id)
    g["flat_run"] = runs(flat, g.site_id)
    g["f_lin"] = g.lin_run >= MIN_RUN - 1
    g["f_flat"] = g.flat_run >= MIN_RUN - 1

    # 출력제어 의심: 같은 A 관측지점 동료들의 중앙 CF 가 높은데 혼자 30% 미만
    g["st"] = g.site_id.map(sites.wa_station)
    peer = g[g.day].groupby(["st", "ts"]).cf.agg(["median", "size"])
    g = g.join(peer, on=["st", "ts"])
    g["f_curt"] = g.day & (g["size"] >= 3) & (g["median"] > 0.35) & (g.cf < 0.3 * g["median"])
    # 동시 다발(같은 시각 여러 발전소가 함께 급감) = 계통 출력제어 성격
    sim = g[g.f_curt].groupby("ts").size()
    g["curt_multi"] = g.f_curt & g.ts.map(sim).fillna(0).ge(5)

    day = g[g.day]
    tot = len(day)
    E = day.energy.sum()
    print(f"낮 시간(태양고도>10°) 행 {tot:,}개, 발전소 {g.site_id.nunique()}개")
    for f, name in (("f_lin", "직선 보간 의심"), ("f_flat", "값 고정"), ("f_curt", "출력제어/고장 의심 (동료 대비 30% 미만)"),
                    ("curt_multi", "  └ 같은 시각 5개소 이상 동시 급감")):
        m = day[f]
        lost = (day.loc[m, "median"] * day.loc[m, "cap"] - day.loc[m, "energy"]).clip(lower=0).sum() if "curt" in f else np.nan
        print(f"[{name}] 행 {m.sum():,} ({m.mean() * 100:.2f}%), 관련 발전소 {day.loc[m, 'site_id'].nunique()}개"
              + (f", 손실 추정 {lost / E * 100:.2f}% (낮 총발전 대비)" if "curt" in f else ""))

    c = day[day.f_curt].copy()
    c["year"] = c.ts.dt.year
    c["month"] = c.ts.dt.month
    tday = F.target_day(c.ts).dt.tz_localize(None)
    c["off"] = (tday.dt.dayofweek >= 5) | tday.isin(F.off_days())
    base = day.assign(year=day.ts.dt.year, month=day.ts.dt.month)
    rate_y = (c.groupby("year").size() / base.groupby("year").size() * 100).round(2)
    print("\n출력제어/고장 의심 비율(%) — 연도별:", rate_y.to_dict())
    rate_m = (c.groupby("month").size() / base.groupby("month").size() * 100).round(2)
    print("월별:", rate_m.to_dict())
    bt = F.target_day(base.ts).dt.tz_localize(None)
    base_off = (bt.dt.dayofweek >= 5) | bt.isin(F.off_days())
    spring = base.month.isin([3, 4, 5])
    for lab, cm, bm in (("봄 평일", (c.month.isin([3, 4, 5])) & ~c.off, spring & ~base_off),
                        ("봄 휴일", (c.month.isin([3, 4, 5])) & c.off, spring & base_off),
                        ("그 외 평일", ~c.month.isin([3, 4, 5]) & ~c.off, ~spring & ~base_off),
                        ("그 외 휴일", ~c.month.isin([3, 4, 5]) & c.off, ~spring & base_off)):
        print(f"  {lab}: {cm.sum() / bm.sum() * 100:.2f}%")
    ym = c[c.curt_multi].groupby([c.year, c.month]).size()
    print("동시 다발 급감 시각 수 상위(연-월):", ym.sort_values(ascending=False).head(8).to_dict())

    out = g.loc[g.f_lin | g.f_flat | g.f_curt, ["site_id", "ts", "f_lin", "f_flat", "f_curt", "curt_multi"]]
    path = os.path.join(sc.ROOT, "outputs", "quality_flags.parquet")
    out.to_parquet(path, index=False)
    print(f"\n저장: {path} ({len(out):,}행)")


if __name__ == "__main__":
    main()
