"""제출 forecast 후처리 (JH#71): 봄(3~5월) 휴일 10~16시 예측 × 0.96. 두 해 검증 −0.64% / −0.70%.

    .venv/Scripts/python.exe src/postscale.py --src ens_v12 --dst ens_v13
"""
from __future__ import annotations
import argparse, os, shutil, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submissions")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--dst", required=True)
    ap.add_argument("--factor", type=float, default=0.96)
    a = ap.parse_args()
    f = pd.read_csv(os.path.join(SUB, f"forecast_{a.src}.csv"))
    ts = pd.to_datetime(f.ts, utc=True).dt.tz_convert("Asia/Seoul")
    cal = F.calendar(ts)
    mon = F.target_day(ts).dt.month.to_numpy()
    m = (cal.is_off.to_numpy() == 1) & pd.Series(mon).isin([3, 4, 5]).to_numpy() & ts.dt.hour.between(10, 16).to_numpy()
    before = f.forecast_kwh.sum()
    f.loc[m, "forecast_kwh"] *= a.factor
    f.to_csv(os.path.join(SUB, f"forecast_{a.dst}.csv"), index=False)
    shutil.copy(os.path.join(SUB, f"composition_{a.src}.csv"), os.path.join(SUB, f"composition_{a.dst}.csv"))
    print(f"보정 행 {int(m.sum()):,} / {len(f):,} (휴일 {int(m.sum() / 14)}일)  총합 변화 {f.forecast_kwh.sum() / before - 1:+.3%}")

if __name__ == "__main__":
    main()
