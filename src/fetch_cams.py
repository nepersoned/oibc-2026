"""CAMS 전구 대기조성 예보 (코페르니쿠스 ADS, ECMWF IFS 기반 0.4°) → 한반도 고정 상자 평균 일사·운량.

출처: https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts
      2015 ~ 현재, 매일 00/12 UTC 실행, 리드 0~120h (시간별). 라이선스: CC-BY (상업 이용 가능), 무료 가입.
      → 학습 기간 전체(2020~2026)를 덮는 유일한 ECMWF 계열 예보 소스.

대회 규칙 (운영진 답변 2026-11-05 기준)
- 대상일 D 의 KST 01~24시 = **D-2 12 UTC 실행**의 리드 28~51h 만 사용. ECMWF 문서상 12z 산출물은 **22:00 UTC 까지 공개 보장**
  (= D-1 07:00 KST) → 마감(D-1 17:00 KST)보다 10시간 앞선다 (근거: confluence.ecmwf.int CAMS forecast documentation). D-1 00z 실행은 공개 시각이 마감과 겹칠 수 있어 쓰지 않는다.
- 한반도 고정 상자(34~38°N, 126~129.5°E) 격자 평균 하나. 발전소 좌표 미사용.
- 인증키는 `.env` 의 ADS_API_KEY (ADS 가입 → 프로필에서 발급). 코드·git 에 넣지 않는다.

    uv pip install --python .venv/Scripts/python.exe cdsapi
    .venv/Scripts/python.exe src/fetch_cams.py --test              # 한 달 요청 (요청 수락·해독 확인)
    .venv/Scripts/python.exe src/fetch_cams.py                     # 전체 → data_ext/cams_hourly.parquet
"""
from __future__ import annotations

import argparse
import os
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_ext", "cams_raw")
OUT = os.path.join(ROOT, "data_ext", "cams_hourly.parquet")
DATASET = "cams-global-atmospheric-composition-forecasts"
AREA = [38.0, 126.0, 34.0, 129.5]                      # N, W, S, E
LEADS = list(range(27, 52))                            # 27h 는 누적 일사 차분용
VARS = ["surface_solar_radiation_downwards", "total_sky_direct_solar_radiation_at_surface",
        "total_cloud_cover", "2m_temperature"]
SHORT = {"ssrd": "ghi", "fdir": "dni", "tcc": "tcc", "2t": "t2m"}
ACCUM = {"ssrd", "fdir"}                               # J/m², 실행 시각부터 누적


def api_key() -> str:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip().startswith("ADS_API_KEY="):
                os.environ["ADS_API_KEY"] = line.strip().split("=", 1)[1].strip().strip('"')
    key = os.environ.get("ADS_API_KEY")
    if not key:
        raise SystemExit(".env 에 ADS_API_KEY=... 를 넣어 주세요 (https://ads.atmosphere.copernicus.eu 가입 → 프로필)")
    return key


def fetch_month(client, ym: pd.Period) -> str:
    path = os.path.join(RAW, f"{ym}.grib")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return "skip"
    start, end = ym.start_time.date(), ym.end_time.date()
    req = {"variable": VARS, "date": f"{start}/{end}", "time": ["12:00"], "type": ["forecast"],
           "leadtime_hour": [str(h) for h in LEADS], "area": AREA, "data_format": "grib"}
    tmp = path + ".part"
    client.retrieve(DATASET, req, tmp)
    os.replace(tmp, path)
    return "ok"


def decode(path: str) -> pd.DataFrame:
    """GRIB → (init, lead, var) 상자 평균. 요청 영역이 곧 상자이므로 격자 전체 평균."""
    import eccodes
    rows = []
    with open(path, "rb") as f:
        while True:
            h = eccodes.codes_grib_new_from_file(f)
            if h is None:
                break
            try:
                sn = eccodes.codes_get(h, "shortName")
                if sn in SHORT:
                    d = str(eccodes.codes_get(h, "dataDate"))
                    t = int(eccodes.codes_get(h, "dataTime")) // 100
                    step = int(eccodes.codes_get(h, "endStep"))
                    val = float(np.nanmean(eccodes.codes_get_values(h)))
                    rows.append((pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:]} {t:02d}:00", tz="UTC"), step, SHORT[sn], val))
            finally:
                eccodes.codes_release(h)
    return pd.DataFrame(rows, columns=["init", "lead", "var", "val"])


def build() -> pd.DataFrame:
    parts = [decode(os.path.join(RAW, f)) for f in sorted(os.listdir(RAW)) if f.endswith(".grib")]
    df = pd.concat(parts, ignore_index=True).drop_duplicates(["init", "lead", "var"])
    wide = df.pivot_table(index=["init", "lead"], columns="var", values="val").sort_index()
    for v in ("ghi", "dni"):                           # 누적 J/m² → 그 시간의 평균 W/m²
        if v in wide:
            diff = wide.groupby(level="init")[v].diff()
            wide[v] = (diff / 3600.0).clip(lower=0)
    wide = wide.reset_index()
    wide = wide[wide.lead >= 28]
    wide["ts"] = (wide.init + pd.to_timedelta(wide.lead, unit="h")).dt.tz_convert("Asia/Seoul")
    out = wide.drop(columns=["init", "lead"]).set_index("ts").add_prefix("cams_").sort_index()
    out = out[~out.index.duplicated()]
    return out.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--start", default="2020-05")
    ap.add_argument("--end", default="2026-06")
    ap.add_argument("--build-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    if not a.build_only:
        import cdsapi
        client = cdsapi.Client(url="https://ads.atmosphere.copernicus.eu/api", key=api_key(), quiet=True)
        months = pd.period_range(a.start, a.end, freq="M")
        if a.test:
            months = months[:1]
        t0 = time.time()
        for ym in months:
            try:
                r = fetch_month(client, ym)
            except Exception as e:  # noqa: BLE001
                r = f"실패 {type(e).__name__}: {str(e)[:120]}"
            print(f"{ym} {r}  {time.time() - t0:.0f}s", flush=True)
    df = build()
    if a.test:
        print(df.head(30).round(1).to_string())
        return
    df.to_parquet(OUT, index=False)
    print(f"저장: {OUT}  {len(df):,}행  {df.ts.min()} ~ {df.ts.max()}", flush=True)


if __name__ == "__main__":
    main()
