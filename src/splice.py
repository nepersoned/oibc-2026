"""LDAPS(UM)가 2026-03-31 생산 종료 → 평가 기간 마지막 구간을 LDAPS 없는 모델 예측으로 교체.

대상일(target_day) ≤ 2026-04-01 은 LDAPS 포함 모델, 이후는 LDAPS 없는 모델.

    # 발전소 단위 (site_id, ts, kwh)
    .venv/Scripts/python.exe src/splice.py --kind sites --um outputs/test_site_um_sites.parquet \
        --fallback outputs/test_site_gfs4_sites.parquet --out outputs/test_site_split_sites.parquet
    # 집합 단위 (group, ts, pred)
    .venv/Scripts/python.exe src/splice.py --kind group --um A.parquet --fallback B.parquet --out C.parquet
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402

LAST_UM_DAY = pd.Timestamp("2026-04-01")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["sites", "group"], required=True)
    ap.add_argument("--um", required=True)
    ap.add_argument("--fallback", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    key, val = (["site_id", "ts"], "kwh") if a.kind == "sites" else (["group", "ts"], "pred")
    um, fb = pd.read_parquet(a.um), pd.read_parquet(a.fallback)
    for d in (um, fb):
        d["ts"] = pd.to_datetime(d.ts).dt.tz_convert("Asia/Seoul")
    m = um[key + [val]].merge(fb[key + [val]], on=key, suffixes=("_um", "_fb"), how="outer")
    use = F.target_day(m.ts).dt.tz_localize(None) <= LAST_UM_DAY
    m[val] = m[f"{val}_um"].where(use & m[f"{val}_um"].notna(), m[f"{val}_fb"])
    m[key + [val]].to_parquet(a.out, index=False)
    print(f"저장: {a.out}  {len(m):,}행  LDAPS 구간 {use.mean() * 100:.1f}%  결측 {int(m[val].isna().sum())}")


if __name__ == "__main__":
    main()
