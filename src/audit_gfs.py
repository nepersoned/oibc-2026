"""GFS 공개 시각 감사 — 대회 운영진 요구: "쓰는 실행이 대상일 전날 17:00 KST 이전에 공개됐다는 근거".

대상일 D 에 쓰는 것은 D-1 00 UTC 실행의 리드 15~39h 파일. 각 실행에서 **가장 늦게 쓰는 파일(f039)** 의
NOAA AWS 저장소 Last-Modified(업로드 시각)를 조회해, 마감 D-1 08:00 UTC(= 17:00 KST) 이전인지 기록한다.

    .venv/Scripts/python.exe src/audit_gfs.py   → data_ext/gfs_pubtime_audit.csv (+ 요약 출력)
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_gfs as G  # noqa: E402

OUT = os.path.join(G.ROOT, "data_ext", "gfs_pubtime_audit.csv")
LAST_LEAD = 39


def last_modified(init_day: pd.Timestamp) -> tuple[str, str | None]:
    for u in G.url(init_day, LAST_LEAD, idx=False):
        for t in range(3):
            try:
                req = urllib.request.Request(u, method="HEAD")
                with urllib.request.urlopen(req, timeout=30) as r:
                    return u, r.headers.get("Last-Modified")
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    break
                time.sleep(2)
            except Exception:  # noqa: BLE001
                time.sleep(2)
    return "", None


def main() -> None:
    inits = pd.date_range("2020-12-31", "2026-05-31", freq="D", tz="UTC")       # 실행일 = 대상일 D-1
    with ThreadPoolExecutor(24) as ex:
        res = list(ex.map(last_modified, inits))
    df = pd.DataFrame({"init_utc": inits, "url": [r[0] for r in res], "last_modified": [r[1] for r in res]})
    df["last_modified_utc"] = pd.to_datetime(df.last_modified, format="%a, %d %b %Y %H:%M:%S GMT", utc=True, errors="coerce")
    df["deadline_utc"] = df.init_utc + pd.Timedelta(hours=8)                     # D-1 17:00 KST
    df["before_deadline"] = df.last_modified_utc < df.deadline_utc
    df["target_day_kst"] = (df.init_utc + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    df.drop(columns="last_modified").to_csv(OUT, index=False)
    lag = (df.last_modified_utc - df.init_utc).dt.total_seconds() / 3600
    print(f"실행 {len(df)}회, 조회 성공 {df.last_modified_utc.notna().sum()}회")
    print(f"마감 전 공개: {int(df.before_deadline.sum())}회 / 마감 후: {int((df.last_modified_utc >= df.deadline_utc).sum())}회")
    print(f"초기시각 대비 업로드까지 시간(h) 분위 (5, 50, 95, 최대): {lag.quantile([.05, .5, .95, 1]).round(2).tolist()}")
    late = df[df.last_modified_utc >= df.deadline_utc]
    if len(late):
        print("마감 후 업로드된 실행 연도별:", late.init_utc.dt.year.value_counts().sort_index().to_dict())
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
