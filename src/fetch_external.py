"""외부 수치예보 일사량 수집 — Open-Meteo Previous Runs API.

출처: https://previous-runs-api.open-meteo.com/v1/forecast  (문서: https://open-meteo.com/en/docs/previous-runs-api)
라이선스: Open-Meteo 데이터 CC BY 4.0 (https://open-meteo.com/en/licence). 원자료 ECMWF IFS(CC BY 4.0), NOAA GFS, JMA.

대회 규칙 준수
- `_previous_day2` = 유효시각 48시간 전 발행 예보만 사용 → 대상일 모든 시각이 전날 00시 이전 발행
  (예측시점 전날 17:00 KST 보다 앞섬)
- 한반도 고정 격자 25점 — 발전소 좌표를 쓰지 않으며, 모든 발전소에 같은 값으로만 사용 (공지 5항)
- 대회 데이터는 외부로 보내지 않음 (요청에는 고정 격자 좌표와 날짜만 포함)
- 누구나 같은 주소로 다시 받을 수 있음 — 이 스크립트가 받는 방법 그 자체

시각: timezone=Asia/Seoul, 일사량은 직전 1시간 평균 → 대회의 우측닫힘 ts 와 같은 규약.

    .venv/Scripts/python.exe src/fetch_external.py        # data_ext/openmeteo_<model>.parquet
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data_ext")
URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
LATS = [34.75, 35.5, 36.25, 37.0, 37.75]
LONS = [126.5, 127.25, 128.0, 128.75, 129.5]
MODELS = ["ecmwf_ifs025", "jma_seamless", "gfs_seamless"]
VARS = ["shortwave_radiation_previous_day2", "cloud_cover_previous_day2"]
YEARS = [("2021-01-01", "2021-12-31"), ("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"),
         ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-06-01")]


EXTRA_VARS = ["cloud_cover_low_previous_day2", "cloud_cover_mid_previous_day2", "cloud_cover_high_previous_day2",
              "direct_radiation_previous_day2", "diffuse_radiation_previous_day2",
              "precipitation_previous_day2", "temperature_2m_previous_day2"]


def fetch(model: str, start: str, end: str, vars_: list[str] | None = None) -> pd.DataFrame:
    vars_ = vars_ or VARS
    pts = [(la, lo) for la in LATS for lo in LONS]
    q = (f"{URL}?latitude={','.join(str(p[0]) for p in pts)}&longitude={','.join(str(p[1]) for p in pts)}"
         f"&hourly={','.join(vars_)}&models={model}&start_date={start}&end_date={end}&timezone=Asia%2FSeoul")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(q, timeout=120) as r:
                data = json.load(r)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  재시도 {attempt + 1}: {e}")
            time.sleep(20 * (attempt + 1))
    else:
        raise RuntimeError(f"{model} {start} 수집 실패")
    frames = []
    for i, d in enumerate(data if isinstance(data, list) else [data]):
        h = d["hourly"]
        f = pd.DataFrame({"time": h["time"], **{v.replace("_previous_day2", ""): h[v] for v in vars_}})
        f["pt"] = i
        frames.append(f)
    return pd.concat(frames)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    extra = os.path.join(OUT, "openmeteo_jma_extra.parquet")
    if not os.path.exists(extra):
        parts = []
        for s, e in YEARS:
            parts.append(fetch("jma_seamless", s, e, EXTRA_VARS))
            print(f"jma_extra {s[:4]} 완료", flush=True)
            time.sleep(3)
        f = pd.concat(parts)
        f["ts"] = pd.to_datetime(f.time).dt.tz_localize("Asia/Seoul")
        f.drop(columns="time").to_parquet(extra, index=False)
        cov = f.groupby(f.ts.dt.year).direct_radiation.apply(lambda x: x.notna().mean()).round(2).to_dict()
        print(f"jma_extra: {len(f):,}행, 연도별 직달일사 커버리지 {cov}")
    for model in MODELS:
        path = os.path.join(OUT, f"openmeteo_{model}.parquet")
        if os.path.exists(path):
            print(f"{model}: 이미 있음")
            continue
        parts = []
        for s, e in YEARS:
            parts.append(fetch(model, s, e))
            print(f"{model} {s[:4]} 완료", flush=True)
            time.sleep(3)
        f = pd.concat(parts)
        f["ts"] = pd.to_datetime(f.time).dt.tz_localize("Asia/Seoul")
        f.drop(columns="time").to_parquet(path, index=False)
        cov = f.groupby(f.ts.dt.year).shortwave_radiation.apply(lambda x: x.notna().mean()).round(2).to_dict()
        print(f"{model}: {len(f):,}행 저장, 연도별 일사량 커버리지 {cov}")


if __name__ == "__main__":
    main()
