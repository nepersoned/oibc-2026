"""NOAA GFS 확장 요약 — 변수 추가 + 넓은 상자 + 공간 표준편차 (모든 발전소에 같은 값).

fetch_gfs.py 와 같은 규칙: D-1 00 UTC 실행분만(마감 전 공개), 리드 15~39h, 1° 격자, 고정 상자.
추가: 하향 장파(DLWRF, 구름 신호), 2m 상대습도(RH), 넓은 상자(32~39°N, 124~131°E) 평균,
안쪽 상자(34~38°N, 126~129°E)의 **공간 표준편차**(부분 흐림 정도). 발전소 좌표 미사용.

    .venv/Scripts/python.exe src/fetch_gfs2.py --workers 24   → data_ext/gfs2_hourly.parquet
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

RAW = os.path.join(G.ROOT, "data_ext", "gfs2_raw")
OUT = os.path.join(G.ROOT, "data_ext", "gfs2_hourly.parquet")
VARS = {"DSWRF": ("DSWRF:surface", "ave"), "TCDC": ("TCDC:entire atmosphere", "ave"),
        "DLWRF": ("DLWRF:surface", "ave"), "RH": ("RH:2 m above ground", "inst")}
INNER = (np.arange(34, 39), np.arange(126, 130))
OUTER = (np.arange(32, 40), np.arange(124, 132))


def messages(idx_text: str) -> dict[str, tuple[int, int | None, str]]:
    lines = idx_text.strip().splitlines()
    out = {}
    for i, ln in enumerate(lines):
        p = ln.split(":")
        start = int(p[1])
        end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
        for k, (key, kind) in VARS.items():
            if f"{p[3]}:{p[4]}" != key:
                continue
            is_ave = "ave fcst" in p[5]
            if (kind == "ave" and is_ave) or (kind == "inst" and not is_ave and "hour fcst" in p[5]):
                out[k] = (start, end, p[5])
    return out


def stats(grib: bytes) -> tuple[float, float, float]:
    """(안쪽 평균, 안쪽 공간 표준편차, 넓은 상자 평균)."""
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

    def box(lats, lons):
        li = [int(round((lat0 - la) / dlat)) if neg else int(round((la - lat0) / dlat)) for la in lats]
        lj = [int(round((lo - lon0) / dlon)) % nlon for lo in lons]
        return g[np.ix_(li, lj)]

    inner, outer = box(*INNER), box(*OUTER)
    return float(inner.mean()), float(inner.std()), float(outer.mean())


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
        m = messages(txt) if txt else {}
        for k in VARS:
            if k not in m:
                rec += [np.nan] * 4
                continue
            s, e, desc = m[k]
            gb = G.get(base_u, (s, e if e is not None else s + 5_000_000))
            mi, sd, mo = stats(gb) if gb else (np.nan, np.nan, np.nan)
            w = np.nan
            if "ave" in desc:
                a0, a1 = desc.split(" hour")[0].split("-")
                w = int(a1) - int(a0)
            rec += [mi, sd, mo, w]
        rows.append(rec)
    np.savez(path, rows=np.array(rows, dtype=float))
    return "ok"


def build() -> pd.DataFrame:
    """평균형(ave) 변수는 6h 누적 평균 → 3h 평균 복원, 순간값(RH)은 그대로. 3시간 값을 각 시간에 배정."""
    names = list(VARS)
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
            for i, k in enumerate(names):
                base = 1 + 4 * i
                w = x[base + 3]
                for j, stat in enumerate(("in", "insd", "out")):
                    v = x[base + j]
                    if VARS[k][1] == "ave" and w == 6 and stat != "insd":
                        p = byl.get(lead - 3)
                        v = 2 * v - p[base + j] if p is not None else np.nan
                    vals[f"gfs2_{k.lower()}_{stat}"] = v
            end = init + pd.Timedelta(hours=lead)
            for h in pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert(G.TZ):
                recs.append({"ts": h, "init": init, **vals})
    df = pd.DataFrame(recs)
    tday = (df.ts - pd.Timedelta(hours=1)).dt.tz_convert(G.TZ).dt.floor("D").dt.tz_localize(None)
    df = df[tday - pd.Timedelta(days=1) == df.init.dt.tz_localize(None)].drop(columns="init")
    for c in [c for c in df.columns if "dswrf" in c and not c.endswith("insd")]:
        df[c] = df[c].clip(lower=0)
    return df.sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-12-31")
    ap.add_argument("--end", default="2026-05-31")
    ap.add_argument("--workers", type=int, default=24)
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
    print(f"저장: {OUT}  {len(df):,}행  열 {list(df.columns)[1:]}", flush=True)


if __name__ == "__main__":
    main()
