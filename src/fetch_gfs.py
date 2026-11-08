"""NOAA GFS 원본 아카이브 → 한반도 고정 상자 평균 일사량·운량 (대상일 시간별).

출처: NOAA GFS, AWS Open Data  https://noaa-gfs-bdp-pds.s3.amazonaws.com  (https://registry.opendata.aws/noaa-gfs-bdp-pds/)
라이선스: 미국 정부 공개 데이터 (NOAA Open Data, 상업적 이용 제한 없음). 같은 주소로 누구나 다시 받을 수 있음.

대회 규칙 준수
- 대상일 D 의 예측에는 **D-1 일 00 UTC 실행분**만 사용. 이 실행은 보통 D-1 03~05 UTC(= 12~14 KST)에 공개되어
  예측시점(D-1 17:00 KST = 08:00 UTC)보다 앞선다. 대상일 01~24 KST = 리드 16~39 시간.
- 한반도 고정 상자(위도 34~38°N, 경도 126~129°E, 1° 격자 20점) **평균 하나**만 사용, 발전소 좌표 미사용,
  모든 발전소에 같은 값 (공지 5항).
- 필요한 GRIB 메시지(DSWRF surface 평균, TCDC 전층 평균)만 .idx 로 위치를 찾아 바이트 범위로 받는다.

시간 처리: GFS 플럭스는 6시간마다 초기화되는 구간 평균 → 3시간 평균으로 복원 →
맑은날 비율(k = GFS 3h 평균 / 상자 중심 맑은날 3h 평균)을 각 시간의 맑은날 일사량에 곱해 시간별 값으로 만든다.

    .venv/Scripts/python.exe src/fetch_gfs.py --start 2021-01-01 --end 2026-05-31 --workers 24
    → data_ext/gfs_raw/YYYYMMDD.npz (실행별 원자료 상자 평균), data_ext/gfs_hourly.parquet
"""
from __future__ import annotations

import argparse
import os
import threading
import sys
import time
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_ext", "gfs_raw")
OUT = os.path.join(ROOT, "data_ext", "gfs_hourly.parquet")
BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
LEADS = list(range(15, 40, 3))          # 15,18,...,39  (15 는 18 의 6h 평균 복원용)
VARS = {"DSWRF": "DSWRF:surface", "TCDC": "TCDC:entire atmosphere"}
LAT = np.arange(34, 39)                  # 34..38
LON = np.arange(126, 130)                # 126..129
BOX_C = (36.0, 127.5)                    # 맑은날 계산용 상자 중심
TZ = "Asia/Seoul"
_LOCK = threading.Lock()           # eccodes 는 스레드 안전하지 않음 → 해독만 직렬화


def url(day: pd.Timestamp, lead: int, idx: bool) -> list[str]:
    d = day.strftime("%Y%m%d")
    f = f"gfs.t00z.pgrb2.1p00.f{lead:03d}" + (".idx" if idx else "")
    return [f"{BASE}/gfs.{d}/00/atmos/{f}", f"{BASE}/gfs.{d}/00/{f}"]


def get(u: str, rng: tuple[int, int] | None = None, tries: int = 4) -> bytes | None:
    for t in range(tries):
        try:
            req = urllib.request.Request(u)
            if rng:
                req.add_header("Range", f"bytes={rng[0]}-{rng[1]}")
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            time.sleep(2 * (t + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (t + 1))
    return None


def messages(idx_text: str) -> dict[str, tuple[int, int, str]]:
    """평균(ave) 메시지의 바이트 범위."""
    lines = idx_text.strip().splitlines()
    out = {}
    for i, ln in enumerate(lines):
        p = ln.split(":")
        start = int(p[1])
        end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
        for k, key in VARS.items():
            if f"{p[3]}:{p[4]}" == key and "ave fcst" in p[5]:
                out[k] = (start, end, p[5])
    return out


def box_mean(grib: bytes) -> float:
    with _LOCK:
        return _box_mean(grib)


def _box_mean(grib: bytes) -> float:
    import eccodes
    h = eccodes.codes_new_from_message(grib)
    try:
        vals = eccodes.codes_get_values(h)
        nlat = eccodes.codes_get(h, "Nj")
        nlon = eccodes.codes_get(h, "Ni")
        lat0 = eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees")
        lon0 = eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees")
        dlat = eccodes.codes_get(h, "jDirectionIncrementInDegrees")
        dlon = eccodes.codes_get(h, "iDirectionIncrementInDegrees")
        scan_neg = lat0 > 0
    finally:
        eccodes.codes_release(h)
    g = vals.reshape(nlat, nlon)
    lat_idx = [int(round((lat0 - la) / dlat)) if scan_neg else int(round((la - lat0) / dlat)) for la in LAT]
    lon_idx = [int(round((lo - lon0) / dlon)) % nlon for lo in LON]
    return float(g[np.ix_(lat_idx, lon_idx)].mean())


def fetch_day(day: pd.Timestamp, raw_dir: str = RAW) -> str:
    path = os.path.join(raw_dir, day.strftime("%Y%m%d") + ".npz")
    if os.path.exists(path):
        try:
            old = np.load(path)["rows"]
            if old.shape == (len(LEADS), 5) and np.isfinite(old[:, 1:]).all():
                return "skip"
        except Exception:
            pass
        try:
            os.remove(path)
        except OSError:
            return "invalid-cache"
    rows = []
    for lead in LEADS:
        txt = None
        for u in url(day, lead, True):
            b = get(u)
            if b:
                txt, base_u = b.decode(), u[:-4]
                break
        if txt is None:
            rows.append([lead, np.nan, np.nan, np.nan, np.nan])
            continue
        m = messages(txt)
        rec = [lead]
        for k in ("DSWRF", "TCDC"):
            if k not in m:
                rec += [np.nan, np.nan]
                continue
            s, e, desc = m[k]
            b = get(base_u, (s, e if e is not None else s + 5_000_000))
            v = box_mean(b) if b else np.nan
            a0, a1 = desc.split(" hour")[0].split("-")                 # 'a0-a1 hour ave fcst'
            rec += [v, int(a1) - int(a0)]
        rows.append(rec)
    arr = np.array(rows, dtype=float)
    if arr.shape != (len(LEADS), 5) or not np.isfinite(arr[:, 1:]).all():
        return "failed"
    fd, tmp = tempfile.mkstemp(prefix=".gfs-", suffix=".npz", dir=raw_dir)
    os.close(fd)
    try:
        np.savez(tmp, rows=arr)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return "ok"


def deaverage(rows: np.ndarray) -> dict[int, tuple[float, float]]:
    """리드별 (DSWRF 3h 평균, TCDC 3h 평균) — 6h 누적 평균에서 복원."""
    d = {int(r[0]): r for r in rows}
    out = {}
    for lead in LEADS[1:]:
        r = d.get(lead)
        if r is None:
            continue
        vals = []
        for vi, wi in ((1, 2), (3, 4)):
            v, w = r[vi], r[wi]
            if np.isnan(v):
                vals.append(np.nan)
            elif w == 3:
                vals.append(v)
            elif w == 6:
                prev = d.get(lead - 3)
                vals.append(2 * v - prev[vi] if prev is not None and not np.isnan(prev[vi]) else np.nan)
            else:
                vals.append(np.nan)
        out[lead] = (max(vals[0], 0.0) if not np.isnan(vals[0]) else np.nan, vals[1])
    return out


def clear_sky(ts_kst: pd.DatetimeIndex) -> np.ndarray:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from features import solar
    _, _, cz = solar(ts_kst, np.full(len(ts_kst), BOX_C[0]), np.full(len(ts_kst), BOX_C[1]))
    czc = np.clip(cz, 1e-3, None)
    return np.where(cz > 0, 1098 * czc * np.exp(-0.057 / czc), 0.0)


def build_hourly(raw_dir: str | None = None) -> pd.DataFrame:
    # Resolve at call time so tests and staged callers can safely replace RAW.
    # A default argument of RAW captures the original path at import time.
    if raw_dir is None:
        raw_dir = RAW
    recs = []
    for f in sorted(os.listdir(raw_dir)):
        init = pd.Timestamp(f[:8], tz="UTC")                       # D-1 00 UTC
        da = deaverage(np.load(os.path.join(raw_dir, f))["rows"])
        for lead, (ghi3, tcc3) in da.items():
            end = init + pd.Timedelta(hours=lead)                  # 3h 구간 (end-3h, end] UTC
            hrs = pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert(TZ)
            cs = clear_sky(hrs)
            k = ghi3 / cs.mean() if cs.mean() > 5 else np.nan
            for h, c in zip(hrs, cs):
                recs.append((h, init, ghi3, k * c if not np.isnan(k) else (0.0 if c == 0 else np.nan),
                             k, tcc3))
    df = pd.DataFrame(recs, columns=["ts", "init", "gfs_ghi3", "gfs_ghi", "gfs_kcs", "gfs_tcc"])
    # 대상일 D(KST) 01~24시는 D-1 00UTC 실행분만: init(UTC 날짜) == (ts-1h) KST 날짜 - 1일
    tday = (df.ts - pd.Timedelta(hours=1)).dt.tz_convert(TZ).dt.floor("D").dt.tz_localize(None)
    ok = tday - pd.Timedelta(days=1) == df.init.dt.tz_localize(None)
    return df[ok].drop(columns="init").sort_values("ts").drop_duplicates("ts").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-12-31")
    ap.add_argument("--end", default="2026-05-31")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--raw-dir", default=RAW)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.raw_dir, exist_ok=True)
    if not a.build_only:
        days = pd.date_range(a.start, a.end, freq="D", tz="UTC")
        t0, done = time.time(), 0
        with ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(fetch_day, d, a.raw_dir): d for d in days}
            results = []
            for f in as_completed(futs):
                done += 1
                results.append((futs[f].strftime("%Y-%m-%d"), f.result()))
                if done % 100 == 0:
                    print(f"{done}/{len(days)}  {time.time() - t0:.0f}s", flush=True)
            failed = [d for d, status in results if status not in ("ok", "skip")]
            if failed:
                print(f"실패 날짜 {len(failed)}개: {', '.join(failed[:20])}", flush=True)
    df = build_hourly(a.raw_dir)
    df.to_parquet(a.out, index=False)
    cov = df.groupby(df.ts.dt.year).gfs_ghi.apply(lambda x: x.notna().mean()).round(2).to_dict()
    print(f"저장: {a.out}  {len(df):,}행  연도별 커버리지 {cov}")


if __name__ == "__main__":
    main()
