"""LDAPS 공개 시각 실측 기록 — "전날 17:00 KST 이전 공개" 근거를 쌓는 프로브.

하루 중 아무 때나(특히 12:00~17:00 KST 사이) 실행하면, **오늘 00 UTC 실행**의 리드 39h 값이
API허브에서 이미 조회되는지와 현재 시각을 data_ext/ldaps_availability_log.csv 에 한 줄 추가한다.
여러 날 기록이 쌓이면 "00 UTC 실행은 매일 HH:MM KST 이전에 공개된다"는 실측 근거가 된다.

    .venv/Scripts/python.exe src/probe_ldaps_latency.py        # 팀원 누구나, 본인 .env 키로
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_kma as K  # noqa: E402

LOG = os.path.join(K.ROOT, "data_ext", "ldaps_availability_log.csv")


def available_kim(tmfc: str) -> tuple[bool, int]:
    """후속 모델 KIM 전구(KIMG, 산업특화 6번 API)의 같은 실행이 조회되는지 — UM 은 2026-03 제공 중단이라
    실시간 실측은 KIM 으로 한다 (같은 기상청 운영 체계의 공개 지연 근거)."""
    d = dt.datetime.strptime(tmfc, "%Y%m%d%H")
    ef = (d + dt.timedelta(hours=39)).strftime("%Y%m%d%H%M")
    txt = K.call("nph_sun_nwp_txt", nwp="KIMG", varn="NSWRF", tm=tmfc + "00", tmef1=ef, tmef2=ef, int=3,
                 lat=36.2, lon=127.8)
    rows = [ln for ln in txt.splitlines() if ln.strip().startswith("|") and "NSWRF" in ln]
    return len(rows) > 0, len(rows)


def available(tmfc: str) -> tuple[bool, int]:
    q = urllib.parse.urlencode({"group": "UMKR", "nwp": "N512", "data": "U", "varn": "4200", "tmfc": tmfc,
                                "ef": "39,39,1", "lat": 36.2, "lon": 127.8, "authKey": K.api_key()})
    try:
        with urllib.request.urlopen(K.UM_URL + "?" + q, timeout=60) as r:
            txt = r.read().decode("euc-kr", "replace")
        rows = [ln for ln in txt.splitlines() if ln.strip() and not ln.startswith("#")]
        return len(rows) > 0, len(rows)
    except urllib.error.HTTPError as e:
        return False, -e.code


def main() -> None:
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_kst = now_utc + dt.timedelta(hours=9)
    today00 = now_utc.strftime("%Y%m%d") + "00"
    ok, n = available(today00)                 # UM (2026-03 이후 항상 없음 — 기록용)
    ok_k, n_k = available_kim(today00)         # KIM 전구 (후속 모델)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["checked_kst", "checked_utc", "run_tmfc_utc", "um_lead39_available", "um_rows",
                        "kim_lead39_available", "kim_rows", "hours_after_run", "before_17kst"])
        hrs = (now_utc - dt.datetime.strptime(today00, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)).total_seconds() / 3600
        w.writerow([now_kst.strftime("%Y-%m-%d %H:%M"), now_utc.strftime("%Y-%m-%d %H:%M"), today00, ok, n,
                    ok_k, n_k, round(hrs, 2), now_kst.hour < 17])
    print(f"{now_kst:%Y-%m-%d %H:%M KST}: 오늘 00 UTC 실행 리드 39h — UM {'있음' if ok else '없음(제공 중단)'}, "
          f"KIM {'공개됨' if ok_k else '아직 없음'} (실행 후 {hrs:.1f}h) → {LOG}")


if __name__ == "__main__":
    main()
