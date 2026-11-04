"""기상청 API허브 — 수치모델(KIM/UM) 일사량 예보 + 천리안2A 일사량 + 지상 일사 관측.

출처: 기상청 API허브 https://apihub.kma.go.kr  (산업특화 → 태양광)
  6. 수치모델 데이터 지점 조회   /api/typ01/cgi-bin/url/nph_sun_nwp_txt
  5. 천리안2A 기상산출물 지점    /api/typ01/cgi-bin/url/nph_sun_sat_txt
  3. 관측-통계(일사) 묶음        /api/typ01/cgi-bin/url/nph-sun_sfc_sts_pkg
라이선스: 공공누리 제1유형(출처표시, 상업적 이용 가능). 인증키는 `.env` 의 KMA_API_KEY (git 제외, 본인만 사용).

대회 규칙 준수
- 수치모델: 발표시각 tm = **D-1 00 UTC** 만 사용 (D-1 17:00 KST 마감 전 공개). 대상일 01~24 KST = 발효 D-1 16 UTC ~ D 15 UTC.
- 한반도 **고정 지점 3×3** 만 조회해 평균 하나로 요약, 발전소 좌표 미사용, 모든 발전소에 같은 값 (공지 5항).
- 위성·지상 관측(5, 3번)은 **학습 구간의 정답(날씨 보정 모델 타깃)** 으로만 사용, 예측 입력으로 쓰지 않음.
- API 약관: 하루 20,000건·5GB 이내, 요청 간격 유지, 단일 인증키.

    .venv/Scripts/python.exe src/fetch_kma.py --probe          # 응답 형식·과거 범위 확인 (집계 출력)
"""
from __future__ import annotations

import argparse
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/"
POINTS = [(la, lo) for la in (35.0, 36.2, 37.4) for lo in (126.8, 127.8, 128.8)]   # 고정 3×3
SLEEP = 0.35                                                                          # 요청 간격 (과부하 방지)


def api_key() -> str:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip().startswith("KMA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("KMA_API_KEY")
    if not key:
        raise SystemExit(".env 에 KMA_API_KEY=... 를 넣어 주세요")
    return key


def call(endpoint: str, **params) -> str:
    params["authKey"] = api_key()
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    for t in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                raw = r.read()
            time.sleep(SLEEP)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"  재시도 {t + 1}: {type(e).__name__}")
            time.sleep(3 * (t + 1))
    return ""


def nwp(model: str, varn: str, tm: str, tmef1: str, tmef2: str, lat: float, lon: float, interval: int = 3) -> str:
    return call("nph_sun_nwp_txt", nwp=model, varn=varn, tm=tm, tmef1=tmef1, tmef2=tmef2, int=interval,
                lat=lat, lon=lon)


def probe() -> None:
    """응답 형식과 과거 자료 범위만 확인 (키 노출 없이 앞부분만 출력)."""
    la, lo = POINTS[4]
    for model in ("KIMR", "KIMG", "UMG"):
        for day in ("20210115", "20220615", "20230615", "20240615", "20251115"):
            txt = nwp(model, "NSWRF", day + "0000", day + "1500", day + "2400" if False else
                      (f"{day[:6]}{int(day[6:]) + 1:02d}1500"), la, lo)
            lines = [ln for ln in txt.splitlines() if ln.strip()]
            data = [ln for ln in lines if not ln.lstrip().startswith("#")]
            print(f"{model} {day}: 줄 {len(lines)}, 데이터 줄 {len(data)}")
            if day == "20240615":
                print("   형식 예시(머리글):", " | ".join(ln[:120] for ln in lines[:4]))
                print("   데이터 첫 줄:", data[0][:160] if data else "(없음)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--sat", action="store_true", help="천리안2A 위성 일사량 수집 (학습 정답용)")
    ap.add_argument("--um", action="store_true", help="UM 국지모델(LDAPS) 일사량 예보 수집 (D-1 00UTC)")
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="2025-05-31")
    a = ap.parse_args()
    if a.probe:
        probe()
    if a.sat:
        fetch_sat(a.start, a.end)
    if a.um:
        fetch_um(a.start, a.end)



# ------------------------------------------------------------------ 천리안2A 위성 일사량 (학습 정답용)
SAT_POINTS = [(35.0, 127.0), (35.0, 128.8), (36.2, 127.8), (37.4, 126.8), (37.4, 128.8)]   # 고정 5점
SAT_RAW = os.path.join(ROOT, "data_ext", "kma_sat_raw")
SAT_OUT = os.path.join(ROOT, "data_ext", "kma_sat_hourly.parquet")


def sat_day(day: str, lat: float, lon: float) -> list[float] | None:
    """UTC 하루(00~23시) 정시 DSR (W/m²). 6553.5 = 결측(야간 등)."""
    txt = call("nph_sun_sat_txt", tm1=day + "0000", tm2=day + "2300", int=60, varn="DSR", lat=lat, lon=lon)
    rows = [ln for ln in txt.splitlines() if ln.strip().startswith("|") and "DSR" in ln]
    if not rows:
        return None
    vals = [c.strip() for c in rows[0].split("|") if c.strip()][4:]
    out = []
    for v in vals[:24]:
        try:
            x = float(v)
            out.append(float("nan") if x >= 6000 or x < 0 else x)
        except ValueError:
            out.append(float("nan"))
    return out + [float("nan")] * (24 - len(out))


def fetch_sat(start: str, end: str, workers: int = 4) -> None:
    import json
    from concurrent.futures import ThreadPoolExecutor
    import pandas as pd
    os.makedirs(SAT_RAW, exist_ok=True)
    days = [d.strftime("%Y%m%d") for d in pd.date_range(start, end, freq="D")]
    todo = [d for d in days if not os.path.exists(os.path.join(SAT_RAW, d + ".json"))]
    print(f"위성 일사량: {len(todo)}/{len(days)}일 수집 (지점 {len(SAT_POINTS)}개)", flush=True)

    def one(d):
        res = [sat_day(d, la, lo) for la, lo in SAT_POINTS]
        json.dump(res, open(os.path.join(SAT_RAW, d + ".json"), "w"))
        return d

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    build_sat()


def build_sat() -> None:
    import json
    import numpy as np
    import pandas as pd
    recs = []
    for f in sorted(os.listdir(SAT_RAW)):
        res = json.load(open(os.path.join(SAT_RAW, f)))
        arr = np.array([r if r else [np.nan] * 24 for r in res], dtype=float)      # 지점 × 24
        mean = np.nanmean(np.where(np.isnan(arr), np.nan, arr), axis=0) if np.isfinite(arr).any() else np.full(24, np.nan)
        base = pd.Timestamp(f[:8], tz="UTC")
        for h in range(24):
            recs.append((base + pd.Timedelta(hours=h), mean[h]))
    s = pd.DataFrame(recs, columns=["ts_utc", "dsr"]).set_index("ts_utc").dsr.sort_index()
    # 우측닫힘 1시간 평균 ≈ (h-1 시 정시 + h 시 정시)/2, 야간 결측은 0
    hourly = ((s + s.shift(1)) / 2)
    df = pd.DataFrame({"ts": hourly.index.tz_convert("Asia/Seoul"), "sat_dsr": hourly.to_numpy()})
    df.to_parquet(SAT_OUT, index=False)
    print(f"저장: {SAT_OUT}  {len(df):,}행  유효 {df.sat_dsr.notna().mean():.2f}", flush=True)



# ------------------------------------------------------------------ UM 국지모델(UMKR = LDAPS 1.5km) 일사량 예보
# API: 수치모델 → 10.4 임의 격자점 시계열(발표시간 기준) um_grib_pt_tmfc.php (2026-03-31 생산 종료)
# 변수: 4200 지면 하향단파(전체) = 4198 직달 + 4199 산란 (W/m²). 대상일 D 는 D-1 00 UTC 실행만, 리드 15~39h.
UM_URL = "https://apihub.kma.go.kr/api/typ06/url/um_grib_pt_tmfc.php"
UM_RAW = os.path.join(ROOT, "data_ext", "kma_um_raw")
UM_OUT = os.path.join(ROOT, "data_ext", "kma_um_hourly.parquet")
UM_VARS = {"4200": "um_ghi", "4198": "um_dir", "4199": "um_dif"}


def um_run(tmfc: str, lat: float, lon: float) -> list[tuple[str, str, float]]:
    q = urllib.parse.urlencode({"group": "UMKR", "nwp": "N512", "data": "U", "varn": ",".join(UM_VARS),
                                "tmfc": tmfc, "ef": "15,39,1", "lat": lat, "lon": lon, "authKey": api_key()})
    for t in range(4):
        try:
            with urllib.request.urlopen(UM_URL + "?" + q, timeout=60) as r:
                txt = r.read().decode("euc-kr", "replace")
            time.sleep(SLEEP)
            out = []
            for ln in txt.splitlines():
                p = ln.split()
                if len(p) >= 5 and not ln.startswith("#") and p[2] in UM_VARS:
                    out.append((p[1], p[2], float(p[4])))
            return out
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return []
            if e.code == 500:                     # 자료 없음
                return []
            time.sleep(3 * (t + 1))
        except Exception:  # noqa: BLE001
            time.sleep(3 * (t + 1))
    return []


def fetch_um(start: str, end: str, workers: int = 4) -> None:
    import json
    from concurrent.futures import ThreadPoolExecutor
    import pandas as pd
    os.makedirs(UM_RAW, exist_ok=True)
    days = [d for d in pd.date_range(start, end, freq="D")]
    todo = [d for d in days if not os.path.exists(os.path.join(UM_RAW, d.strftime("%Y%m%d") + ".json"))]
    print(f"UM 국지(LDAPS): {len(todo)}/{len(days)}일 (지점 {len(SAT_POINTS)}개, 호출 {len(todo) * len(SAT_POINTS):,}건)", flush=True)

    def one(d):
        tmfc = (d - pd.Timedelta(days=1)).strftime("%Y%m%d") + "00"         # D-1 00 UTC
        res = [um_run(tmfc, la, lo) for la, lo in SAT_POINTS]
        json.dump(res, open(os.path.join(UM_RAW, d.strftime("%Y%m%d") + ".json"), "w"))

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    build_um()


def build_um() -> None:
    import json
    import pandas as pd
    recs = []
    for f in sorted(os.listdir(UM_RAW)):
        for pi, rows in enumerate(json.load(open(os.path.join(UM_RAW, f)))):
            for tmef, v, x in rows:
                recs.append((tmef, UM_VARS[v], pi, x))
    if not recs:
        print("UM 자료 없음"); return
    df = pd.DataFrame(recs, columns=["tmef", "var", "pt", "val"])
    df["val"] = df.val.where((df.val >= 0) & (df.val < 2000))
    w = df.groupby(["tmef", "var"]).val.mean().unstack()                 # 지점 평균 (고정 5점)
    w.index = pd.to_datetime(w.index, format="%Y%m%d%H").tz_localize("UTC").tz_convert("Asia/Seoul")
    w = w.sort_index()
    w.index.name = "ts"
    w.reset_index().to_parquet(UM_OUT, index=False)
    print(f"저장: {UM_OUT}  {len(w):,}행  연도별 커버리지 "
          f"{w.um_ghi.notna().groupby(w.index.year).mean().round(2).to_dict()}", flush=True)


if __name__ == "__main__":
    main()
