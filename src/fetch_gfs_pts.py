"""NOAA GFS 고정 격자점 값 — 안쪽 상자(34~38°N × 126~129°E, 1° 격자 20점)의 DSWRF·TCDC 를 점별 열로.

운영진 답변(2026-11-05): 미리 정한 고정 지점 값을 **열마다 나누어 모든 발전소에 똑같이** 넣는 것은 허용
(발전소 좌표로 지점을 고르지 않음). 그 밖의 규칙은 fetch_gfs.py 와 같다 (D-1 00 UTC, 리드 15~39h).

    .venv/Scripts/python.exe src/fetch_gfs_pts.py --workers 8   → data_ext/gfs_pts_hourly.parquet
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

RAW = os.path.join(G.ROOT, "data_ext", "gfs_pts_raw")
OUT = os.path.join(G.ROOT, "data_ext", "gfs_pts_hourly.parquet")
LATS, LONS = np.arange(34, 39), np.arange(126, 130)          # 5 × 4 = 20 점
NPT = len(LATS) * len(LONS)


def grid_vals(grib: bytes) -> np.ndarray:
    import eccodes
    with G._LOCK:
        h = eccodes.codes_new_from_message(grib)
        try:
            vals = eccodes.codes_get_values(h)
            nlat, nlon = eccodes.codes_get(h, "Nj"), eccodes.codes_get(h, "Ni")
            lat0 = eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees")
            lon0 = eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees")
            dlat = eccodes.codes_get(h, "jDirectionIncrementInDegrees")
            dlon = eccodes.codes_get(h, "iDirectionIncrementInDegrees")
        finally:
            eccodes.codes_release(h)
    g = vals.reshape(nlat, nlon)
    neg = lat0 > 0
    li = [int(round((lat0 - la) / dlat)) if neg else int(round((la - lat0) / dlat)) for la in LATS]
    lj = [int(round((lo - lon0) / dlon)) % nlon for lo in LONS]
    return g[np.ix_(li, lj)].ravel()


def fetch_day(day: pd.Timestamp) -> str:
    path = os.path.join(RAW, day.strftime("%Y%m%d") + ".npz")
    if os.path.exists(path):
        return "skip"
    rows = []
    for lead in G.LEADS:
        txt, base_u = None, None
        for u in G.url(day, lead, True):
            b = G.get(u)
            if b:
                txt, base_u = b.decode(), u[:-4]
                break
        rec = [lead]
        m = G.messages(txt) if txt else {}
        for k in ("DSWRF", "TCDC"):
            if k not in m:
                rec += [np.nan] * (NPT + 1)
                continue
            s, e, desc = m[k]
            gb = G.get(base_u, (s, e if e is not None else s + 5_000_000))
            a0, a1 = desc.split(" hour")[0].split("-")
            rec += (grid_vals(gb).tolist() if gb else [np.nan] * NPT) + [int(a1) - int(a0)]
        rows.append(rec)
    np.savez(path, rows=np.array(rows, dtype=float))
    return "ok"


def build() -> pd.DataFrame:
    recs = []
    for f in sorted(os.listdir(RAW)):
        init = pd.Timestamp(f[:8], tz="UTC")
        r = np.load(os.path.join(RAW, f))["rows"]
        byl = {int(x[0]): x for x in r}
        for lead in G.LEADS[1:]:
            x = byl.get(lead)
            if x is None:
                continue
            vals = {}
            for vi, k in enumerate(("dswrf", "tcdc")):
                base = 1 + vi * (NPT + 1)
                v = x[base:base + NPT].copy()
                if x[base + NPT] == 6:
                    p = byl.get(lead - 3)
                    v = 2 * v - p[base:base + NPT] if p is not None else np.full(NPT, np.nan)
                for i in range(NPT):
                    vals[f"gfsp_{k}_{i}"] = max(v[i], 0) if k == "dswrf" and not np.isnan(v[i]) else v[i]
            end = init + pd.Timedelta(hours=lead)
            for h in pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert(G.TZ):
                recs.append({"ts": h, "init": init, **vals})
    df = pd.DataFrame(recs)
    tday = (df.ts - pd.Timedelta(hours=1)).dt.tz_convert(G.TZ).dt.floor("D").dt.tz_localize(None)
    df = df[tday - pd.Timedelta(days=1) == df.init.dt.tz_localize(None)].drop(columns="init")
    return df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-12-31")
    ap.add_argument("--end", default="2026-05-31")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    days = pd.date_range(a.start, a.end, freq="D", tz="UTC")
    t0, n = time.time(), 0
    with ThreadPoolExecutor(a.workers) as ex:
        for _ in as_completed([ex.submit(fetch_day, d) for d in days]):
            n += 1
            if n % 200 == 0:
                print(f"{n}/{len(days)}  {time.time() - t0:.0f}s", flush=True)
    df = build()
    df.to_parquet(OUT, index=False)
    print(f"저장: {OUT}  {len(df):,}행 × {df.shape[1] - 1}열", flush=True)


if __name__ == "__main__":
    main()
