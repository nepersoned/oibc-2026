"""앙상블 검증 예측의 편향 진단 (집계값만 출력): 연도·월·시간대·요일별 예측/실적 비율과 전체 배율별 페널티."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "src")
import pick_best as P

WS = 0.505
for y in P.YEARS:
    df, w = P.load_year(y, ["site_dv"], ["l1umxdv"])
    p = WS * df.site_dv + (1 - WS) * df.l1umxdv
    a = df.act
    ts = df.index.get_level_values("ts")
    base = float((w * np.abs(p - a)).sum())
    print(f"\n=== {y}  예측합/실적합 {p.sum()/a.sum():.4f}  W {base:,.0f}")
    sc = {s: float((w * np.abs(s * p - a)).sum()) / base - 1 for s in np.arange(0.94, 1.061, 0.01)}
    print("배율별 W 변화:", " ".join(f"{s:.2f}:{v:+.2%}" for s, v in sc.items()))
    m = pd.DataFrame({"p": p.values, "a": a.values, "m": ts.to_period("M").astype(str),
                      "h": ts.hour, "we": ts.dayofweek >= 5}, index=df.index)
    r = m.groupby("m")[["p", "a"]].sum(); print("월별 비율", (r.p / r.a).round(3).to_dict())
    hb = pd.cut(m.h, [0, 10, 15, 24], labels=["~10", "11-15", "16~"], right=True)
    r = m.groupby(hb, observed=True)[["p", "a"]].sum(); print("시간대 비율", (r.p / r.a).round(3).to_dict())
    r = m.groupby("we")[["p", "a"]].sum(); print("주말 비율", (r.p / r.a).round(3).to_dict())
    spring = m.m.str[5:].isin(["03", "04", "05"]) & m.we & m.h.between(11, 15)
    r = m[spring][["p", "a"]].sum(); print(f"봄 주말 11-15시 비율 {r.p/r.a:.3f}")
    g = m.assign(g=df.index.get_level_values("group")).groupby("g")[["p", "a"]].sum(); print("그룹 비율", (g.p / g.a).round(3).to_dict())
