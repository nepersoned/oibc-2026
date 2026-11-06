"""ECMWF IFS ENS (dynamical.org 가공, ECMWF Open Data 원천) → 한반도 고정 상자 평균 + 앙상블 평균·퍼짐.

출처: https://dynamical.org/catalog/ecmwf-ifs-ens-forecast-15-day-0-25-degree/  (STAC: stac.dynamical.org)
      icechunk/Zarr 공개 저장소 (s3://dynamical-ecmwf-ifs-ens, 익명 HTTPS). 2024-04-01 ~ 현재, 매일 00 UTC, 51멤버.
라이선스: CC BY 4.0 + ECMWF Terms of Use ("ECMWF IFS ENS forecast data processed by dynamical.org from ECMWF Open Data").

대회 규칙
- 대상일 D 에 대해 두 창을 저장: D-2 00 UTC 실행(리드 40~63h; ECMWF 공개 ~D-2 08 UTC 로 마감보다 하루 이상 앞섬 → 근거 확실),
  D-1 00 UTC 실행(리드 16~39h; ECMWF ENS 00z 공개는 07~09 UTC 로 마감 08 UTC 와 겹침 → 공개 시각 근거 확보 전까지 사용 금지).
- 한반도 고정 상자(34~38°N, 126~129.5°E) 격자 평균 하나 + 51멤버 평균/표준편차. 발전소 좌표 미사용.

    .venv/Scripts/python.exe src/fetch_ecmwf_ens.py --test            # 실행 1개 읽기 시간 측정
    .venv/Scripts/python.exe src/fetch_ecmwf_ens.py                   # 전체 → data_ext/ecmwf_ens_hourly.parquet
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_ext", "ecmwf_ens_raw")
OUT = os.path.join(ROOT, "data_ext", "ecmwf_ens_hourly.parquet")
HREF = "https://dynamical-ecmwf-ifs-ens.s3.us-west-2.amazonaws.com/ecmwf-ifs-ens-forecast-15-day-0-25-degree/v0.1.0.icechunk"
VARS = {"downward_short_wave_radiation_flux_surface": "sw", "total_cloud_cover_atmosphere": "tcc"}
LAT = (34.0, 38.0)
LON = (126.0, 129.5)
WINDOWS = {"d2": (40, 63), "d1": (16, 39)}          # 대상일 KST 01~24시 = 실행 기준 리드 (h)


def open_ds():
    import icechunk
    import xarray as xr
    repo = icechunk.Repository.open(icechunk.http_storage(HREF))
    return xr.open_zarr(repo.readonly_session("main").store, chunks=None)


def extract_init(ds, init: pd.Timestamp) -> dict[str, np.ndarray]:
    """한 실행의 두 창에 대해 (리드 × 멤버) 상자 평균 → 멤버 평균·표준편차."""
    sub = ds.sel(init_time=init, latitude=slice(LAT[1], LAT[0]), longitude=slice(LON[0], LON[1]))
    leads = (sub.lead_time / np.timedelta64(1, "h")).astype(int).values
    out = {"lead_h": leads}
    for src, name in VARS.items():
        arr = sub[src].values                                   # (lead, member, lat, lon)
        box = np.nanmean(arr, axis=(2, 3))                      # (lead, member)
        out[f"{name}_mean"] = np.nanmean(box, axis=1)
        out[f"{name}_std"] = np.nanstd(box, axis=1)
        out[f"{name}_ctrl"] = box[:, 0]
    return out


def build() -> pd.DataFrame:
    recs = []
    for f in sorted(os.listdir(RAW)):
        init = pd.Timestamp(f[:10], tz="UTC")
        z = np.load(os.path.join(RAW, f))
        leads = z["lead_h"]
        for win, (lo, hi) in WINDOWS.items():
            tday = (init + pd.Timedelta(hours=lo + 8)).tz_convert("Asia/Seoul").floor("D").tz_localize(None)
            for i, lead in enumerate(leads):
                if lead < lo or lead > hi:
                    continue
                ts = (init + pd.Timedelta(hours=int(lead))).tz_convert("Asia/Seoul")
                rec = {"ts": ts, "win": win, "tday": tday}
                for k in z.files:
                    if k != "lead_h":
                        rec[k] = float(z[k][i])
                recs.append(rec)
    df = pd.DataFrame(recs)
    # 3시간 간격 → 시간별로 보간 (같은 창 안에서), 열 이름 ecm_<win>_<var>
    frames = []
    for win in WINDOWS:
        w = df[df.win == win].drop(columns=["win", "tday"]).set_index("ts").sort_index()
        w = w[~w.index.duplicated()]
        full = pd.date_range(w.index.min(), w.index.max(), freq="h", tz="Asia/Seoul")
        w = w.reindex(full).interpolate(limit=2, limit_area="inside")
        frames.append(w.add_prefix(f"ecm_{win}_"))
    out = pd.concat(frames, axis=1)
    out.index.name = "ts"
    return out.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--start", default="2024-04-01")
    ap.add_argument("--end", default="2026-06-02")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    ds = open_ds()
    inits = pd.DatetimeIndex(ds.init_time.values)
    inits = inits[(inits >= pd.Timestamp(a.start)) & (inits <= pd.Timestamp(a.end))]
    if a.test:
        t0 = time.time()
        r = extract_init(ds, inits[100])
        print(f"{inits[100]} 읽기 {time.time() - t0:.1f}s  리드 수 {len(r['lead_h'])}  sw_mean 리드 24~45h: "
              f"{np.round(r['sw_mean'][(r['lead_h'] >= 24) & (r['lead_h'] <= 45)]).astype(int).tolist()}")
        return
    t0, n = time.time(), 0
    for init in inits:
        path = os.path.join(RAW, init.strftime("%Y-%m-%d") + ".npz")
        if os.path.exists(path):
            continue
        try:
            np.savez(path, **extract_init(ds, init))
        except Exception as e:  # noqa: BLE001
            print(f"{init.date()} 실패 {type(e).__name__}", flush=True)
        n += 1
        if n % 50 == 0:
            print(f"{n} inits  {time.time() - t0:.0f}s", flush=True)
    df = build()
    df.to_parquet(OUT, index=False)
    print(f"저장: {OUT}  {len(df):,}행 × {df.shape[1] - 1}열", flush=True)


if __name__ == "__main__":
    main()
