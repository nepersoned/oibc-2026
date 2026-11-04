"""NOAA GEFS 앙상블 (평균 + 표준편차) → 한반도 고정 상자 평균 일사량·운량 (대상일 시간별).

출처: NOAA GEFS, AWS Open Data  https://noaa-gefs-pds.s3.amazonaws.com  (https://registry.opendata.aws/noaa-gefs/)
라이선스: 미국 정부 공개 데이터 (상업적 이용 제한 없음).

규칙 준수는 fetch_gfs.py 와 같다: D-1 00 UTC 실행분(보통 D-1 05~06 UTC 공개 < 예측시점 08 UTC),
리드 16~39h, 한반도 고정 상자 평균 하나, 발전소 좌표 미사용.
표준편차(퍼짐) = 그 시각 예보의 불확실성 → 새로운 정보.

    .venv/Scripts/python.exe src/fetch_gefs.py --workers 24   → data_ext/gefs_hourly.parquet
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_gfs as G  # noqa: E402

RAW = os.path.join(G.ROOT, "data_ext", "gefs_raw")
OUT = os.path.join(G.ROOT, "data_ext", "gefs_hourly.parquet")
BASE = "https://noaa-gefs-pds.s3.amazonaws.com"


def url(day: pd.Timestamp, kind: str, lead: int) -> str:
    d = day.strftime("%Y%m%d")
    return f"{BASE}/gefs.{d}/00/atmos/pgrb2ap5/{kind}.t00z.pgrb2a.0p50.f{lead:03d}"


def fetch_day(day: pd.Timestamp) -> str:
    path = os.path.join(RAW, day.strftime("%Y%m%d") + ".npz")
    if os.path.exists(path):
        return "skip"
    rows = []
    for lead in G.LEADS:
        rec = [lead]
        for kind in ("geavg", "gespr"):
            b = G.get(url(day, kind, lead) + ".idx")
            m = G.messages(b.decode()) if b else {}
            for k in ("DSWRF", "TCDC"):
                if k not in m:
                    rec += [np.nan, np.nan]
                    continue
                s, e, desc = m[k]
                gb = G.get(url(day, kind, lead), (s, e if e is not None else s + 3_000_000))
                a0, a1 = desc.split(" hour")[0].split("-")
                rec += [G.box_mean(gb) if gb else np.nan, int(a1) - int(a0)]
        rows.append(rec)       # lead, avg_dswrf, w, avg_tcdc, w, spr_dswrf, w, spr_tcdc, w
    np.savez(path, rows=np.array(rows, dtype=float))
    return "ok"


def build_hourly() -> pd.DataFrame:
    recs = []
    for f in sorted(os.listdir(RAW)):
        init = pd.Timestamp(f[:8], tz="UTC")
        rows = np.load(os.path.join(RAW, f))["rows"]
        mean_da = G.deaverage(rows[:, :5])                       # 평균은 GFS 와 같은 방식으로 3h 복원
        spr = {int(r[0]): (r[5], r[7]) for r in rows}            # 퍼짐은 구간 그대로
        for lead, (ghi3, tcc3) in mean_da.items():
            end = init + pd.Timedelta(hours=lead)
            hrs = pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert(G.TZ)
            cs = G.clear_sky(hrs)
            k = ghi3 / cs.mean() if cs.mean() > 5 else np.nan
            s_ghi, s_tcc = spr.get(lead, (np.nan, np.nan))
            for h, c in zip(hrs, cs):
                recs.append((h, init, k * c if not np.isnan(k) else (0.0 if c == 0 else np.nan), k, tcc3,
                             s_ghi, s_tcc, s_ghi / cs.mean() if cs.mean() > 5 else np.nan))
    df = pd.DataFrame(recs, columns=["ts", "init", "gefs_ghi", "gefs_kcs", "gefs_tcc",
                                     "gefs_ghi_spr", "gefs_tcc_spr", "gefs_kcs_spr"])
    tday = (df.ts - pd.Timedelta(hours=1)).dt.tz_convert(G.TZ).dt.floor("D").dt.tz_localize(None)
    ok = tday - pd.Timedelta(days=1) == df.init.dt.tz_localize(None)
    return df[ok].drop(columns="init").sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-12-31")
    ap.add_argument("--end", default="2026-05-31")
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    days = pd.date_range(a.start, a.end, freq="D", tz="UTC")
    t0, done = time.time(), 0
    with ThreadPoolExecutor(a.workers) as ex:
        for _ in as_completed([ex.submit(fetch_day, d) for d in days]):
            done += 1
            if done % 200 == 0:
                print(f"{done}/{len(days)}  {time.time() - t0:.0f}s", flush=True)
    df = build_hourly()
    df.to_parquet(OUT, index=False)
    cov = df.groupby(df.ts.dt.year).gefs_ghi.apply(lambda x: x.notna().mean()).round(2).to_dict()
    print(f"저장: {OUT}  {len(df):,}행  연도별 커버리지 {cov}")


if __name__ == "__main__":
    main()
