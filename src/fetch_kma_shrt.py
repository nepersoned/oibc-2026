"""기상청 **단기예보(동네예보) 격자자료** — 예보관이 보정한 하늘상태(SKY) 5km 격자 → 전국 고정 상자 요약.

출처: 기상청 API허브 → 예특보 → 단기예보 → "2.1 단기예보 격자자료" nph-dfs_shrt_grd (tmfc 발표시각, tmef 발효시각, vars)
      https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_shrt_grd
라이선스: 공공누리 제1유형 (출처표시, 상업 이용 가능). 인증키는 `.env` 의 KMA_API_KEY (코드·git 미포함).

대회 규칙
- 대상일 D 는 **D-1 14:00 KST 발표분**만 사용. 단기예보는 매일 02/05/08/11/14/17/20/23시에 발표되고 발표 직후 공개되므로
  14시 발표분은 마감(D-1 17:00 KST)보다 3시간 앞선다 (발표 시각 자체가 공식 일정 → 공개 근거 명확). 17시 발표분은 쓰지 않는다.
- 발전소 좌표 미사용: 전국 격자(149×253, 유효 격자 ≈ 30,500개)를 **고정 상자 통계**(평균 구름지수, 맑음·흐림 비율,
  4분면 평균)로 요약한다.
- 보유: 격자자료는 2021-12 부근부터 값이 있음 (2021-06 은 0). SKY 코드 1 맑음, 3 구름많음, 4 흐림 → 구름지수 0 / 0.6 / 1.

    .venv/Scripts/python.exe src/fetch_kma_shrt.py --test
    .venv/Scripts/python.exe src/fetch_kma_shrt.py            # 2021-12-01 ~ 2026-06-01 → data_ext/kma_shrt_hourly.parquet
"""
from __future__ import annotations

import argparse
import os
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data_ext", "kma_shrt_raw")
OUT = os.path.join(ROOT, "data_ext", "kma_shrt_hourly.parquet")
URL = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_shrt_grd"
NX, NY = 149, 253
HOURS = [6, 8, 10, 12, 14, 16, 18]                 # 발효시각(KST); 사이 시각은 보간
CLOUD = {1.0: 0.0, 3.0: 0.6, 4.0: 1.0}


def api_key() -> str:
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip().startswith("KMA_API_KEY="):
                os.environ["KMA_API_KEY"] = line.strip().split("=", 1)[1].strip()
    key = os.environ.get("KMA_API_KEY")
    if not key:
        raise SystemExit(".env 에 KMA_API_KEY=... 를 넣어 주세요")
    return key


def fetch_grid(key: str, tmfc: str, tmef: str, var: str = "SKY") -> np.ndarray | None:
    u = URL + "?" + urllib.parse.urlencode(dict(tmfc=tmfc, tmef=tmef, vars=var, authKey=key))
    for attempt in range(3):
        try:
            b = urllib.request.urlopen(u, timeout=90).read()
            txt = b.decode("euc-kr", "replace")
            vals = np.array([float(x) for x in txt.replace("\n", " ").split(",") if x.strip()], dtype=np.float32)
            return vals if len(vals) == NX * NY else None
        except Exception:  # noqa: BLE001
            time.sleep(3 * (attempt + 1))
    return None


def summarize(v: np.ndarray) -> dict[str, float]:
    """유효 격자(SKY>0)만으로 상자 통계. 격자는 x(동서, 149) 가 빠르게 도는 순서, y 는 남→북 으로 가정."""
    g = v.reshape(NY, NX)
    valid = g > 0
    cl = np.full(g.shape, np.nan, dtype=np.float32)
    for code, val in CLOUD.items():
        cl[g == code] = val
    out = {"cloud": float(np.nanmean(cl[valid])), "clear": float((g[valid] == 1).mean()), "ovc": float((g[valid] == 4).mean()),
           "n_valid": float(valid.sum())}
    ys, xs = NY // 2, NX // 2
    for name, sl in {"sw": (slice(0, ys), slice(0, xs)), "se": (slice(0, ys), slice(xs, NX)),
                     "nw": (slice(ys, NY), slice(0, xs)), "ne": (slice(ys, NY), slice(xs, NX))}.items():
        q, m = cl[sl], valid[sl]
        out[f"cloud_{name}"] = float(np.nanmean(q[m])) if m.any() else np.nan
    return out


def fetch_day(key: str, day: pd.Timestamp) -> str:
    path = os.path.join(RAW, day.strftime("%Y%m%d") + ".npz")
    if os.path.exists(path):
        return "skip"
    tmfc = (day - pd.Timedelta(days=1)).strftime("%Y%m%d") + "14"
    rows = []
    for h in HOURS:
        v = fetch_grid(key, tmfc, day.strftime("%Y%m%d") + f"{h:02d}")
        if v is None or (v > 0).sum() < 1000:
            rows.append({"hour": h, "cloud": np.nan})
            continue
        rows.append({"hour": h, **summarize(v)})
    df = pd.DataFrame(rows)
    np.savez(path, hour=df.hour.to_numpy(), **{c: df[c].to_numpy(dtype=np.float32) for c in df.columns if c != "hour"})
    return "ok" if df.cloud.notna().any() else "empty"


def build() -> pd.DataFrame:
    recs = []
    for f in sorted(os.listdir(RAW)):
        if not f.endswith(".npz"):
            continue
        day = pd.Timestamp(f[:4] + "-" + f[4:6] + "-" + f[6:8], tz="Asia/Seoul")
        z = np.load(os.path.join(RAW, f))
        for i, h in enumerate(z["hour"]):
            rec = {"ts": day + pd.Timedelta(hours=int(h))}
            for k in z.files:
                if k != "hour":
                    rec[f"shrt_{k}"] = float(z[k][i]) if i < len(z[k]) else np.nan
            recs.append(rec)
    df = pd.DataFrame(recs).set_index("ts").sort_index()
    full = pd.date_range(df.index.min().floor("D"), df.index.max().ceil("D"), freq="h", tz="Asia/Seoul")
    df = df.reindex(full).interpolate(limit=1, limit_area="inside")      # 2시간 간격 → 사이 1시간 보간
    df.loc[~df.index.hour.isin(range(6, 19)), :] = np.nan                   # 야간은 비움
    df.index.name = "ts"
    return df.reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--start", default="2021-12-01")
    ap.add_argument("--end", default="2026-06-01")
    ap.add_argument("--build-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    key = api_key()
    if a.test:
        d = pd.Timestamp("2025-06-02")
        t0 = time.time()
        print(fetch_day(key, d), f"{time.time() - t0:.1f}s")
        z = np.load(os.path.join(RAW, d.strftime("%Y%m%d") + ".npz"))
        print({k: np.round(z[k], 2).tolist() for k in z.files})
        return
    if not a.build_only:
        days = pd.date_range(a.start, a.end, freq="D")
        t0, n, ok = time.time(), 0, 0
        for d in days:
            r = fetch_day(key, d)
            if r != "skip":
                n += 1
                ok += r == "ok"
            if n and n % 50 == 0:
                print(f"{n}일 ({ok} ok) {time.time() - t0:.0f}s  마지막 {d.date()}", flush=True)
    df = build()
    df.to_parquet(OUT, index=False)
    cov = df[df.ts.dt.hour == 12].groupby(df.ts.dt.year).shrt_cloud.apply(lambda s: round(s.notna().mean(), 2))
    print(f"저장: {OUT}  {len(df):,}행  연도별 커버리지 {cov.to_dict()}", flush=True)


if __name__ == "__main__":
    main()
