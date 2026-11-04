"""Optuna — 집합 모델 하이퍼파라미터 탐색.

과적합 방지: 점수는 검증 구간(2024-06~)이 아니라 그 직전 1년 (2023-06 ~ 2024-06) 내부 검증으로 매긴다.
학습은 그 이전 3년. 특징 행렬은 한 번만 만들어 두고 시도마다 LightGBM 만 다시 학습한다.

    .venv/Scripts/python.exe src/tune_agg.py --trials 60 --ext mean
    → outputs/agg_best_params.json  (agg_model.py --params 에 그대로 사용)
출력은 집계값만.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_model as A  # noqa: E402
import features as F  # noqa: E402
import scoring as sc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--ext", choices=["none", "mean"], default="mean")
    ap.add_argument("--min-cov", type=float, default=0.2)
    a = ap.parse_args()

    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    smp = sc.load_smp()
    fa, fb = A.forecasts("train")
    ext = F.load_ext(a.ext)
    gw = A.group_weather(fa, fb, sites, comp)
    wd = A.wide(fa, fb)
    if ext is not None:
        wd = wd.join(ext.set_index("ts"), how="left")

    va, vb = sc.window("2023-06-01", "2024-06-01")
    gen = A.load_gen(va - pd.DateOffset(years=3), vb)
    tr = A.targets(gen[gen.ts < va], sites, comp, a.min_cov)
    act_t = A.targets(gen[gen.ts >= va], sites, comp, 0.0)
    dtr = A.design(tr, gw, wd, sites, comp)
    dtr = dtr[dtr.elev > -2]
    dva = A.design(act_t, gw, wd, sites, comp)
    feats = A.feats_of(dtr)
    k = sc.k_weight(dtr.ts)
    print(f"내부 학습 {len(dtr):,}행 / 내부 검증 {len(dva):,}행 × {len(feats)}")

    def score(params: dict, weight: str) -> float:
        w = None if weight == "none" else np.asarray(k * (dtr.ts.map(smp).fillna(0).clip(lower=0).to_numpy() if weight == "smpk" else 1), dtype=float)
        m = lgb.LGBMRegressor(**{**A.PARAMS, **params, "verbose": -1}).fit(dtr[feats], dtr.cf.clip(0, 1.2), sample_weight=w)
        cf = np.where(dva.elev > -2, np.clip(m.predict(dva[feats]), 0, None), 0.0)
        p = dva[["group", "ts"]].assign(pred=cf * act_t.cap_avail.to_numpy())
        return A.group_score(p, act_t, smp)

    base = score({}, "none")
    print(f"현재 설정 내부 W {base:,.0f}")

    def objective(trial: optuna.Trial) -> float:
        params = dict(
            n_estimators=trial.suggest_int("n_estimators", 300, 3000, log=True),
            learning_rate=trial.suggest_float("learning_rate", 0.005, 0.08, log=True),
            num_leaves=trial.suggest_int("num_leaves", 7, 127, log=True),
            min_child_samples=trial.suggest_int("min_child_samples", 5, 200, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.1, 0.9),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 30, log=True),
            objective=trial.suggest_categorical("objective", ["l2", "l1", "huber"]),
        )
        weight = trial.suggest_categorical("weight", ["none", "k", "smpk"])
        return score(params, weight)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=0))
    study.optimize(objective, n_trials=a.trials, show_progress_bar=False,
                   callbacks=[lambda s, t: print(f"  #{t.number:3d} W {t.value:,.0f}  best {s.best_value:,.0f}", flush=True)])
    best = dict(study.best_params)
    print(f"최적 내부 W {study.best_value:,.0f}  ({(study.best_value / base - 1) * 100:+.2f}%)  {best}")
    path = os.path.join(sc.ROOT, "outputs", "agg_best_params.json")
    json.dump(best, open(path, "w"), indent=2)
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
