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
import json
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


def run_rich(gen, sites, pred_a, pred_b, fc_split: str, weight: str, params: dict,
             ext_mode: str = "none", wx_cut: str | None = None) -> pd.DataFrame:
    """특징 확장 버전 — 두 라운드를 한 모델에 (17 우선 + 10 보조), 대상일 내 문맥, 전국 요약, 발전소 ID."""
    def load(split):
        fa = F.prep_forecast(F.load_forecast(split, "wa", F.WA_ALL), "wa", F.WA_ALL)
        fb = F.prep_forecast(F.load_forecast(split, "wb", F.WB_ALL), "wb", F.WB_ALL)
        return fa, fb, F.region_means(fa, fb)

    fa, fb, reg = load("train")
    ext = F.load_ext(ext_mode)
    wx = F.load_wx(wx_cut) if wx_cut else None
    if wx_cut and wx is None:
        raise SystemExit(f"outputs/wx_{wx_cut}_*.parquet 없음 — src/weather_model.py --cutoff {wx_cut} 먼저 실행")
    s = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    d = F.build_rich(gen[["site_id", "ts", "energy", "smp"]], s, fa, fb, reg, ext, wx)
    feats = F.rich_feats(d)
    log(f"학습 행렬 {len(d):,} × {len(feats)}")
    m = M.fit(d, weight, feats=feats, params=params, cat=["site_code"])
    del d
    log("학습 완료")
    if fc_split == "test":
        fa, fb, reg = load("test")
    target = F.grid(sites.site_id, pred_a, pred_b)
    d = F.build_rich(target, s, fa, fb, reg, ext, wx)
    out = target.assign(kwh=M.predict(m, d))
    imp = pd.Series(m.booster_.feature_importance("gain"), index=feats).sort_values(ascending=False)
    log("중요도 상위 15: " + ", ".join(imp.index[:15]))
    return out


def run(train_a, train_b, pred_a, pred_b, fc_split: str, train_years: int,
        weight: str = "none", fset: str = "base", params: dict | None = None,
        ext_mode: str = "none", wx_cut: str | None = None) -> pd.DataFrame:
    """학습 [train_a, train_b) → 예측 [pred_a, pred_b] 발전소별 kWh."""
    sites = sc.load_sites()
    gen = load_generation(train_a, train_b)
    gen["smp"] = gen.ts.map(sc.load_smp())          # 학습 구간 과거 SMP (가중치용, 입력 특징 아님)
    log(f"학습 발전량 {len(gen):,}행 ({train_years}년)")
    if fset == "rich":
        return run_rich(gen, sites, pred_a, pred_b, fc_split, weight, params or {}, ext_mode, wx_cut)

    fa_tr, fb_tr = F.load_forecast("train", "wa", F.WA_COLS), F.load_forecast("train", "wb", F.WB_COLS)
    if fc_split == "train":
        fa_pr, fb_pr = fa_tr, fb_tr
    else:
        fa_pr, fb_pr = F.load_forecast("test", "wa", F.WA_COLS), F.load_forecast("test", "wb", F.WB_COLS)
    target = F.grid(sites.site_id, pred_a, pred_b)

    preds = []
    for r in ROUNDS:
        m = M.fit(F.build(gen[["site_id", "ts", "energy", "smp"]], sites, fa_tr, fb_tr, r), weight)
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
    ap.add_argument("--weight", choices=["none", "k", "smpk"], default="none",
                    help="학습 샘플 가중: none | k(11~15시 3배)×용량 | smpk(SMP×k)×용량")
    ap.add_argument("--fset", choices=["base", "rich"], default="base", help="특징 세트")
    ap.add_argument("--params", default="{}", help='LightGBM 파라미터 덮어쓰기 JSON, 예: {"objective":"l1"}')
    ap.add_argument("--ext", choices=["none", "mean"], default="none",
                    help="외부 수치예보 일사량 (data_ext/, src/fetch_external.py)")
    ap.add_argument("--wx", action="store_true", help="1단계 날씨 보정 모델 특징 사용 (src/weather_model.py)")
    ap.add_argument("--tag", default="baseline", help="출력 파일 이름 꼬리표")
    ap.add_argument("--val-start", default=sc.VAL_START, help="검증 구간 시작 (기본 2024-06-01)")
    ap.add_argument("--val-end", default=sc.VAL_END)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    comp = composition(a.composition)

    if a.mode == "val":
        pa, pb = sc.window(a.val_start, a.val_end)
        ta = pa - pd.DateOffset(years=a.train_years)
        pred = run(ta, pa, pa, pb, "train", a.train_years, a.weight, a.fset, json.loads(a.params), a.ext,
                   a.val_start if a.wx else None)
        suffix = "" if a.val_start == sc.VAL_START else f"_{a.val_start[:4]}"
        path = os.path.join(OUT, f"val_{a.tag}{suffix}_sites.parquet")
        pred.to_parquet(path, index=False)
        log(f"발전소별 검증 예측 저장: {path}")
        sc.report(sc.score(pred, comp, sc.load_actual(a.val_start, a.val_end), sc.load_smp()),
                  f"[{a.tag}{suffix}] ")
        return

    pa, pb = sc.window(TRAIN_END, "2026-06-01")
    ta = pa - pd.DateOffset(years=a.train_years)
    pred = run(ta, pa, pa, pb, "test", a.train_years, a.weight, a.fset, json.loads(a.params), a.ext,
               TRAIN_END if a.wx else None)
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
