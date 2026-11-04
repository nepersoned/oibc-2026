"""발전소별 오차 집중도 점검 (집계값만).

- 발전소별 편향 (Σ(예측−실적)/Σ실적) 분포
- 학습 끝 직전 90일의 실적/예측 비율이 검증 1년 편향을 설명하는지 (지속되는 고장·노후화 신호)
- 장기 0 발전(고장) 일수

    .venv/Scripts/python.exe src/analyze_sites.py --pred outputs/val_rich_sites.parquet
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scoring as sc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    a = ap.parse_args()
    sites = sc.load_sites().set_index("site_id")
    p = pd.read_parquet(a.pred)
    p["ts"] = sc.to_ts(p.ts)
    m = sc.load_actual().merge(p, on=["site_id", "ts"])
    m["day"] = m.ts.dt.floor("D")

    s = m.groupby("site_id").agg(pred=("kwh", "sum"), act=("energy", "sum"), n=("ts", "size"))
    s["bias"] = (s.pred - s.act) / s.act.replace(0, np.nan)
    s["cap"] = sites.capacity_kw
    s["abs_bias_kwh"] = (s.pred - s.act).abs()
    print("발전소별 연간 편향 (예측-실적)/실적 분위수 (5,25,50,75,95%):",
          np.round(s.bias.quantile([.05, .25, .5, .75, .95]).values * 100, 1).tolist())
    tot = (s.pred - s.act).abs().sum()
    top = s.abs_bias_kwh.sort_values(ascending=False)
    print(f"연간 편향 |kWh| 상위 10개소 비중 {top.iloc[:10].sum() / tot * 100:.1f}%  상위 30 {top.iloc[:30].sum() / tot * 100:.1f}%")
    print(f"편향 > +20% (과대예측) 발전소 {int((s.bias > .2).sum())}개, 용량 {s.cap[s.bias > .2].sum():,.0f} kW")
    print(f"편향 < −20% (과소예측) 발전소 {int((s.bias < -.2).sum())}개, 용량 {s.cap[s.bias < -.2].sum():,.0f} kW")

    d = m.groupby(["site_id", "day"]).agg(act=("energy", "sum"), pred=("kwh", "sum"))
    dead = d[(d.pred > 0) & (d.act <= 0.02 * d.pred)]
    print(f"실적≈0 인 날 (예측 대비 2% 이하): {len(dead):,} 발전소-일, 관련 발전소 {dead.index.get_level_values(0).nunique()}개")
    lost = dead.pred.sum() / s.pred.sum() * 100
    print(f"  그 날들의 예측량 = 전체 예측의 {lost:.2f}%")

    # 학습 끝 90일 비율로 다음 1년 편향을 설명할 수 있나 (in-sample 예측 대신 간단히 실적 CF 변화로)
    g = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    g["ts"] = sc.to_ts(g.ts)
    end = pd.Timestamp(sc.VAL_START, tz=sc.TZ)
    last = g[(g.ts > end - pd.Timedelta(days=90)) & (g.ts <= end)].groupby("site_id").energy.sum()
    prev = g[(g.ts > end - pd.Timedelta(days=365 + 90)) & (g.ts <= end - pd.Timedelta(days=365))].groupby("site_id").energy.sum()
    ratio = (last / prev).rename("yoy")
    j = s.join(ratio, how="inner").dropna()
    j = j[(j.yoy > 0) & np.isfinite(j.yoy)]
    print(f"\n학습 끝 90일 전년동기 대비 비율 vs 검증 편향 상관 (n={len(j)}): {np.corrcoef(np.log(j.yoy), j.bias)[0, 1]:+.3f}")


if __name__ == "__main__":
    main()
