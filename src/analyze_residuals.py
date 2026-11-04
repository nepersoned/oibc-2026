"""잔차 구조 분석 — 요일·공휴일(출력제어), 직전 눈 예보(눈 덮임), 발전소 출력 상한 (집계값만).

    .venv/Scripts/python.exe src/analyze_residuals.py --pred outputs/val_rich_extx_sites.parquet
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

# 2024-06 ~ 2025-05 공휴일 (대체·임시 공휴일, 선거일 포함 — 공지상 사용 허용)
HOLIDAYS = pd.to_datetime([
    "2024-06-06", "2024-08-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-01", "2024-10-03",
    "2024-10-09", "2024-12-25", "2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
    "2025-03-01", "2025-03-03", "2025-05-05", "2025-05-06"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    a = ap.parse_args()
    comp = sc.reference_composition(sc.load_sites())
    smp = sc.load_smp()
    p = pd.read_parquet(a.pred)
    p["ts"] = sc.to_ts(p.ts)
    m = sc.load_actual().merge(p, on=["site_id", "ts"])
    m["g"] = m.site_id.map(comp)
    g = m.groupby(["g", "ts"]).agg(act=("energy", "sum"), pred=("kwh", "sum")).reset_index()
    g["w"] = 0.1 * g.ts.map(smp).to_numpy() * sc.k_weight(g.ts)
    g["pen"] = g.w * (g.pred - g.act).abs()
    g["r"] = g.pred - g.act
    day = F.target_day(g.ts).dt.tz_localize(None)
    g["dow"] = day.dt.dayofweek
    g["off"] = (g.dow >= 5) | day.isin(HOLIDAYS)
    g["season"] = day.dt.month.map({3: "봄", 4: "봄", 5: "봄", 6: "여름", 7: "여름", 8: "여름",
                                    9: "가을", 10: "가을", 11: "가을", 12: "겨울", 1: "겨울", 2: "겨울"})
    mid = g[g.ts.dt.hour.between(10, 16)]
    t = mid.groupby(["season", "off"]).agg(bias=("r", "sum"), act=("act", "sum"), pen=("pen", "sum"))
    t["bias%"] = (t.bias / t.act * 100).round(2)
    t["pen_share%"] = (t.pen / g.pen.sum() * 100).round(1)
    print("[1] 10~16시 편향 (예측−실적)/실적 — 계절 × 휴일여부 (off=True: 주말·공휴일)")
    print(t[["bias%", "pen_share%"]].to_string())
    spring_off = mid[(mid.season == "봄") & mid.off]
    big = spring_off.groupby(day[spring_off.index]).r.sum().sort_values(ascending=False)
    print(f"  봄 휴일 과대예측 상위 10일 합 = 봄 휴일 전체 편향의 {big.iloc[:10].sum() / max(big.sum(), 1) * 100:.0f}%")

    # [2] 직전 2일 눈 예보 (예측시점 이전 발행)
    fb = F.load_forecast("train", "wb", ["wb_snow"])
    fb = fb[fb["round"] == 17]
    fb["tday"] = F.target_day(fb.ts).dt.tz_localize(None)
    snow_day = fb.groupby("tday").wb_snow.mean()
    prev = snow_day.shift(1).fillna(0) + snow_day.shift(2).fillna(0)
    g["snow_prev2"] = day.map(prev).fillna(0).to_numpy()
    w = g[(g.season == "겨울") & g.ts.dt.hour.between(10, 16)]
    w = w.assign(snowy=pd.cut(w.snow_prev2, [-1, 0.01, 0.1, 100], labels=["없음", "약간", "많음"]))
    s = w.groupby("snowy", observed=True).agg(bias=("r", "sum"), act=("act", "sum"), pen=("pen", "sum"), n=("r", "size"))
    s["bias%"] = (s.bias / s.act * 100).round(1)
    s["pen_share%"] = (s.pen / g.pen.sum() * 100).round(1)
    print("\n[2] 겨울 10~16시, 직전 2일 B 눈 예보량별 편향")
    print(s[["n", "bias%", "pen_share%"]].to_string())

    # [3] 발전소 출력 상한: 학습 기간 실적 99.9% 분위 CF 를 넘는 예측
    gen = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts < pd.Timestamp(sc.VAL_START, tz=sc.TZ)]
    cap = sc.load_sites().set_index("site_id").capacity_kw
    q = (gen.groupby("site_id").energy.quantile(0.999) / cap).rename("cfmax")
    m["cfmax"] = m.site_id.map(q)
    over = m.kwh > m.cfmax * m.site_id.map(cap)
    clipped = m.kwh.where(~over, m.cfmax * m.site_id.map(cap))
    W0 = sc.score(m[["site_id", "ts", "kwh"]], comp, m[["site_id", "ts", "energy"]], smp)["W"]
    W1 = sc.score(m[["site_id", "ts"]].assign(kwh=clipped), comp, m[["site_id", "ts", "energy"]], smp)["W"]
    print(f"\n[3] 상한 초과 예측 {over.mean() * 100:.2f}% 행 → 상한으로 자르면 W {W0:,.0f} → {W1:,.0f} ({(W1 / W0 - 1) * 100:+.2f}%)")


if __name__ == "__main__":
    main()
