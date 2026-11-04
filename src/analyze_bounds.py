"""발전소별 검증 예측으로 개선 여지를 측정한다 (집계값만 출력).

- 현재 구성 W
- 하한: 253개소를 하나로 합친 오차 |ΣR| (어떤 2분할도 이보다 작을 수 없음)
- 상수 배율 보정 (예측 × α) 의 효과
- 시간대별 페널티 비중

    .venv/Scripts/python.exe src/analyze_bounds.py --pred outputs/val_baseline_sites.parquet
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

    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    pred = pd.read_parquet(a.pred)
    pred["ts"] = sc.to_ts(pred.ts)
    m = sc.load_actual().merge(pred, on=["site_id", "ts"], how="left")
    m["r"] = m.kwh - m.energy
    m["g"] = m.site_id.map(comp)
    smp = sc.load_smp()

    g = m.groupby(["g", "ts"]).agg(r=("r", "sum"), act=("energy", "sum"), p=("kwh", "sum")).reset_index()
    g["w"] = 0.1 * g.ts.map(smp).to_numpy() * sc.k_weight(g.ts)
    W = (g.w * g.r.abs()).sum()

    t = m.groupby("ts").agg(r=("r", "sum")).reset_index()
    t["w"] = 0.1 * t.ts.map(smp).to_numpy() * sc.k_weight(t.ts)
    W_lb = (t.w * t.r.abs()).sum()
    print(f"현재 구성 W            {W:,.0f}")
    print(f"하한 (전체 합산 오차)  {W_lb:,.0f}   → 구성 최적화 최대 개선 {(1 - W_lb / W) * 100:.1f}%")

    for alpha in (0.90, 0.95, 0.97, 1.0, 1.03, 1.05):
        Wa = (g.w * (alpha * g.p - g.act).abs()).sum()
        print(f"  예측 × {alpha:.2f}  W {Wa:,.0f}  ({(Wa / W - 1) * 100:+.2f}%)")

    g["hour"] = g.ts.dt.hour
    g["pen"] = g.w * g.r.abs()
    by_h = g.groupby("hour").agg(pen=("pen", "sum"), bias=("r", "sum"), act=("act", "sum"))
    by_h["share%"] = by_h.pen / by_h.pen.sum() * 100
    by_h["bias%"] = by_h.bias / by_h.act.replace(0, np.nan) * 100
    print("\n시간대별 페널티 비중 / 편향(예측-실적)/실적")
    print(by_h[by_h.act > 0][["share%", "bias%"]].round(1).to_string())

    g["month"] = g.ts.dt.month
    by_m = g.groupby("month").agg(pen=("pen", "sum"), bias=("r", "sum"), act=("act", "sum"))
    by_m["share%"] = by_m.pen / by_m.pen.sum() * 100
    by_m["bias%"] = by_m.bias / by_m.act * 100
    print("\n월별 페널티 비중 / 편향%")
    print(by_m[["share%", "bias%"]].round(1).to_string())


if __name__ == "__main__":
    main()
