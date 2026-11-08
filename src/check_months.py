"""제출 후보의 월별 합계를 기준 제출과 비교 — 어느 달이든 차이가 한도를 넘으면 종료코드 1 (S6 같은 결측 사고 방지).

    python src/check_months.py submissions/forecast_ens_v12.csv submissions/forecast_ens_v9b.csv --tol 0.04
"""
import argparse
import sys

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("cand")
ap.add_argument("ref")
ap.add_argument("--tol", type=float, default=0.04)
a = ap.parse_args()
m = {}
for n, p in (("cand", a.cand), ("ref", a.ref)):
    d = pd.read_csv(p)
    d["m"] = pd.to_datetime(d.ts, utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m")
    m[n] = d.groupby("m").forecast_kwh.sum() / 1e6
    if n == "cand":
        bad = int(d.forecast_kwh.isna().sum() + (d.forecast_kwh < 0).sum())
t = pd.DataFrame(m)
t = t[t.ref > 0.1]
t["diff%"] = (t.cand / t.ref - 1) * 100
print(t.round(2).to_string())
worst = float(t["diff%"].abs().max())
print(f"최대 월 차이 {worst:.2f}%  결측·음수 {bad}")
sys.exit(1 if worst > a.tol * 100 or bad else 0)
