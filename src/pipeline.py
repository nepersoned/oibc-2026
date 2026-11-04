"""전체 파이프라인 — 전처리 → 학습 → 추론 → (검증 채점 | 제출 파일 생성).

    # 1) 검증: 2024-06-01 이전으로 학습 → 마지막 1년 예측 → 로컬 정산금 S 출력
    .venv/Scripts/python.exe src/pipeline.py --mode val

    # 2) 제출: 학습 구간 전체로 학습 → 평가 구간 예측 → submissions/ 에 두 파일 + 형식 검사
    .venv/Scripts/python.exe src/pipeline.py --mode submit

옵션: --train-years 2 (학습에 쓸 최근 연수), --composition C.csv (기본: sites.csv 참조 구성)
출력은 집계값만 — 원본 데이터 행은 출력하지 않는다.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as F  # noqa: E402
import model as M  # noqa: E402
import scoring as sc  # noqa: E402

ROUNDS = (10, 17)
OUT = os.path.join(sc.ROOT, "outputs")
SUB = os.path.join(sc.ROOT, "submissions")
TRAIN_END = "2025-06-01"          # 학습 구간 끝 (평가 구간 시작 직전)

t0 = time.time()
log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)


def load_generation(a: pd.Timestamp, b: pd.Timestamp) -> pd.DataFrame:
    """[a, b) 구간 학습 발전량. 음수 실적은 0으로."""
    g = pd.read_parquet(os.path.join(sc.DATA, "train", "generation.parquet"))
    g["ts"] = sc.to_ts(g.ts)
    g = g[(g.ts >= a) & (g.ts < b)].copy()
    g["energy"] = g.energy.clip(lower=0)
    return g


def run(train_a, train_b, pred_a, pred_b, fc_split: str, train_years: int) -> pd.DataFrame:
    """학습 [train_a, train_b) → 예측 [pred_a, pred_b] 발전소별 kWh (라운드 10·17 평균)."""
    sites = sc.load_sites()
    gen = load_generation(train_a, train_b)
    log(f"학습 발전량 {len(gen):,}행 ({train_years}년)")

    fa_tr, fb_tr = F.load_forecast("train", "wa", F.WA_COLS), F.load_forecast("train", "wb", F.WB_COLS)
    if fc_split == "train":
        fa_pr, fb_pr = fa_tr, fb_tr
    else:
        fa_pr, fb_pr = F.load_forecast("test", "wa", F.WA_COLS), F.load_forecast("test", "wb", F.WB_COLS)
    target = F.grid(sites.site_id, pred_a, pred_b)

    preds = []
    for r in ROUNDS:
        m = M.fit(F.build(gen[["site_id", "ts", "energy"]], sites, fa_tr, fb_tr, r))
        d = F.build(target, sites, fa_pr, fb_pr, r)
        preds.append(M.predict(m, d))
        log(f"round={r} 학습·예측 완료")
    return target.assign(kwh=np.mean(preds, axis=0))


def composition(path: str | None) -> pd.Series:
    sites = sc.load_sites()
    comp = sc.read_composition(path) if path else sc.reference_composition(sites)
    errs = sc.check_composition(comp, sites)
    if errs:
        raise SystemExit("[무효 구성] " + "; ".join(errs))
    return comp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["val", "submit"], required=True)
    ap.add_argument("--train-years", type=int, default=2)
    ap.add_argument("--composition", default=None)
    ap.add_argument("--tag", default="baseline", help="출력 파일 이름 꼬리표")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    comp = composition(a.composition)

    if a.mode == "val":
        pa, pb = sc.window(sc.VAL_START, sc.VAL_END)
        ta = pa - pd.DateOffset(years=a.train_years)
        pred = run(ta, pa, pa, pb, "train", a.train_years)
        path = os.path.join(OUT, f"val_{a.tag}_sites.parquet")
        pred.to_parquet(path, index=False)
        log(f"발전소별 검증 예측 저장: {path}")
        sc.report(sc.score(pred, comp, sc.load_actual(), sc.load_smp()), f"[{a.tag}] ")
        return

    pa, pb = sc.window(TRAIN_END, "2026-06-01")
    ta = pa - pd.DateOffset(years=a.train_years)
    pred = run(ta, pa, pa, pb, "test", a.train_years)
    pred.to_parquet(os.path.join(OUT, f"test_{a.tag}_sites.parquet"), index=False)

    os.makedirs(SUB, exist_ok=True)
    pred["group"] = pred.site_id.map(comp)
    f = (pred.groupby(["group", "ts"], as_index=False).kwh.sum()
         .rename(columns={"kwh": "forecast_kwh"}).sort_values(["group", "ts"]))
    f["ts"] = f.ts.dt.strftime("%Y-%m-%d %H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
    cpath, fpath = os.path.join(SUB, f"composition_{a.tag}.csv"), os.path.join(SUB, f"forecast_{a.tag}.csv")
    comp.rename("group").rename_axis("site_id").reset_index().to_csv(cpath, index=False)
    f.to_csv(fpath, index=False)
    log(f"저장: {cpath} / {fpath} ({len(f):,}행)")
    subprocess.run([sys.executable, os.path.join(sc.ROOT, "src", "validate_submission.py"),
                    "--composition", cpath, "--forecast", fpath], check=False)


if __name__ == "__main__":
    main()
