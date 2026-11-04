"""1단계 날씨 보정 모델 — 하루전 예보 → 실측 기상(구름·자외선·시정) 예측.

학습 구간의 실측 기상은 **정답(타깃)으로만** 쓰고, 예측 입력은 예보뿐이다 (평가 구간 실측 미사용).
학습 기간 행은 시간 블록 교차예측(OOF)으로 만들어 2단계가 과신하지 않게 하고,
그 뒤 구간은 컷오프 이전 데이터로만 학습한 모델로 예측한다.

    .venv/Scripts/python.exe src/weather_model.py --cutoff 2024-06-01   # 검증용 → outputs/wx_2024-06-01.parquet
    .venv/Scripts/python.exe src/weather_model.py --cutoff 2025-06-01   # 제출용 → outputs/wx_2025-06-01.parquet

출력: (provider_station, ts) 별 예측 실측값. 집계 지표(MAE)만 출력.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

t0 = time.time()
log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)

TARGETS = {"wa": {"wa_cloud": (0, 100)},
           "wb": {"wb_cloud": (0, 100), "wb_uv_idx": (0, 15), "wb_vis": (0, 50)}}
COLS = {"wa": F.WA_ALL, "wb": F.WB_ALL}
PARAMS = dict(n_estimators=400, learning_rate=0.08, num_leaves=63, min_child_samples=100,
              subsample=0.7, subsample_freq=1, colsample_bytree=0.7, verbose=-1, n_jobs=-1)
FOLDS = 4
DAYLIGHT = (6, 20)        # 발전과 무관한 야간은 학습·예측 생략


def frame(split: str, prov: str) -> pd.DataFrame:
    d = F.prep_forecast(F.load_forecast(split, prov, COLS[prov]), prov, COLS[prov])
    d = d[d.ts.dt.hour.between(*DAYLIGHT)].copy()
    st = f"{prov}_station"
    d["st_code"] = d[st].str[2:].astype("int16")
    doy = d.ts.dt.day_of_year.to_numpy()
    d["doy_sin"], d["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    d["hour"] = d.ts.dt.hour.astype("int8")
    return d


def run(prov: str, cutoff: pd.Timestamp) -> pd.DataFrame:
    st = f"{prov}_station"
    tr = frame("train", prov)
    obs = pd.read_parquet(os.path.join(sc.DATA, "train", f"observed_{prov}.parquet"),
                          columns=[st, "ts"] + list(TARGETS[prov]))
    obs["ts"] = sc.to_ts(obs.ts)
    obs = obs.drop_duplicates([st, "ts"]).rename(columns={c: f"obs_{c}" for c in TARGETS[prov]})
    lab = tr.merge(obs, on=[st, "ts"], how="left")
    feats = [c for c in tr.columns if c not in {st, "ts"}]

    past = lab[lab.ts < cutoff]
    fut_tr = tr[tr.ts >= cutoff]
    pieces = [fut_tr[[st, "ts"]].copy()]
    test = frame("test", prov) if cutoff >= pd.Timestamp("2025-06-01", tz=sc.TZ) else None
    if test is not None:
        pieces.append(test[[st, "ts"]].copy())
    oof = past[[st, "ts"]].copy()

    month = past.ts.dt.year * 12 + past.ts.dt.month
    fold = (month - month.min()) % FOLDS                # 월 단위 블록을 번갈아 배정
    for tgt, (lo, hi) in TARGETS[prov].items():
        y = past[f"obs_{tgt}"].clip(lo, hi)
        ok = y.notna().to_numpy()
        pred = np.full(len(past), np.nan, dtype="float32")
        for k in range(FOLDS):
            trn = ok & (fold != k).to_numpy()
            m = lgb.LGBMRegressor(**PARAMS).fit(past.loc[trn, feats], y[trn], categorical_feature=["st_code"])
            te = (fold == k).to_numpy()
            pred[te] = m.predict(past.loc[te, feats])
        mae_fc = np.nanmean(np.abs(past[tgt] - y)) if tgt in past else np.nan
        mae = np.nanmean(np.abs(pred[ok] - y[ok]))
        log(f"{prov} {tgt}: 예보 그대로 MAE {mae_fc:.2f} → 보정 OOF MAE {mae:.2f}")
        oof[f"hat_{tgt}"] = pred
        m = lgb.LGBMRegressor(**PARAMS).fit(past.loc[ok, feats], y[ok], categorical_feature=["st_code"])
        pieces[0][f"hat_{tgt}"] = m.predict(fut_tr[feats]).astype("float32")
        if test is not None:
            pieces[1][f"hat_{tgt}"] = m.predict(test[feats]).astype("float32")
    return pd.concat([oof] + pieces, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", required=True, help="이 시각 이전 실측만 학습 (검증 2024-06-01, 제출 2025-06-01)")
    a = ap.parse_args()
    cutoff = pd.Timestamp(a.cutoff, tz=sc.TZ) + pd.Timedelta(hours=1)
    out = {}
    for prov in ("wa", "wb"):
        out[prov] = run(prov, cutoff)
    path = os.path.join(sc.ROOT, "outputs", f"wx_{a.cutoff}.parquet")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wa, wb = out["wa"], out["wb"]
    wa.to_parquet(path.replace(".parquet", "_wa.parquet"), index=False)
    wb.to_parquet(path.replace(".parquet", "_wb.parquet"), index=False)
    log(f"저장: {path.replace('.parquet', '_wa/_wb.parquet')}")


if __name__ == "__main__":
    main()
