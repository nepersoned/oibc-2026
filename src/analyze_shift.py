"""예보 시각 정렬 점검 — 예보를 ±h 시간 밀었을 때 실측/발전량과의 상관 (집계값만 출력).

발전소 설비이용률 잔차(실제 CF − 맑은날 기대 CF 근사)와 같은 지점 예보 변수의 상관을 시차별로 계산한다.
가장 상관이 큰 시차가 0이 아니면 예보 ts 정의가 발전량과 어긋나 있다는 신호.

    .venv/Scripts/python.exe src/analyze_shift.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402


def main() -> None:
    sites = sc.load_sites()
    a, b = pd.Timestamp("2023-06-01 01:00", tz=sc.TZ), pd.Timestamp("2024-06-01 00:00", tz=sc.TZ)
    g = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    g["ts"] = sc.to_ts(g.ts)
    g = g[(g.ts >= a) & (g.ts <= b)].merge(sites, on="site_id")
    g["cf"] = g.energy / g.capacity_kw
    elev, _, _ = F.solar(pd.DatetimeIndex(g.ts), g.lat.to_numpy(), g.lon.to_numpy())
    g = g[elev > 10]
    # 같은 시각·같은 날 평균 대비 상대 CF → 구름 효과만 남김
    g["hour"] = g.ts.dt.hour
    g["month"] = g.ts.dt.month
    g["cf_rel"] = g.cf / g.groupby(["site_id", "month", "hour"]).cf.transform("quantile", 0.9).clip(lower=1e-3)

    for prov, var in (("wa", "wa_cloud"), ("wa", "wa_humidity"), ("wb", "wb_cloud"), ("wb", "wb_uv_idx")):
        st = f"{prov}_station"
        f = F.load_forecast("train", prov, [var])
        f = f[f["round"] == 17].drop(columns="round")
        out = []
        for h in (-2, -1, 0, 1, 2):
            s = f.copy()
            s["ts"] = s.ts + pd.Timedelta(hours=h)        # h>0: 예보값을 h시간 뒤 발전량과 짝지음
            m = g[["site_id", "ts", st, "cf_rel"]].merge(s, on=[st, "ts"], how="inner")
            out.append(f"{h:+d}h:{m.cf_rel.corr(m[var]):+.3f}")
        print(f"{var:12s} 시차별 상관  " + "  ".join(out))
    for prov, var in (("wa", "wa_cloud"), ("wb", "wb_cloud"), ("wb", "wb_uv_idx")):
        st = f"{prov}_station"
        o = pd.read_parquet(os.path.join(sc.DATA, "train", f"observed_{prov}.parquet"), columns=[st, "ts", var])
        o["ts"] = sc.to_ts(o.ts)
        o = o.drop_duplicates([st, "ts"])
        out = []
        for h in (-2, -1, 0, 1, 2):
            s = o.copy()
            s["ts"] = s.ts + pd.Timedelta(hours=h)
            m = g[["site_id", "ts", st, "cf_rel"]].merge(s, on=[st, "ts"], how="inner")
            out.append(f"{h:+d}h:{m.cf_rel.corr(m[var]):+.3f}")
        print(f"[실측] {var:10s} 시차별 상관  " + "  ".join(out))


if __name__ == "__main__":
    main()
