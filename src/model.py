"""모델 — 다른 모델을 실험하려면 이 파일의 fit / predict 만 바꾸면 된다.

타깃은 설비이용률(energy / capacity), 야간(태양고도 ≤ 0)은 학습에서 빼고 예측은 0.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from features import FEATS

PARAMS = dict(n_estimators=600, learning_rate=0.06, num_leaves=127, min_child_samples=200,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, n_jobs=-1)


def fit(d: pd.DataFrame, weight: str = "none", feats: list[str] | None = None,
        params: dict | None = None, cat: list[str] | None = None):
    """weight: 'none' | 'k' (11~15시 3배) | 'smpk' (SMP × k — 채점 가중과 동일)."""
    feats = feats or FEATS
    d = d[d.elev > 0]
    y = (d.energy / d.cap).clip(0, 1.2).astype("float32")
    w = None
    if weight != "none":
        k = np.where(d.ts.dt.hour.between(11, 15), 3.0, 1.0)
        w = k * d.cap.to_numpy()
        if weight == "smpk":
            w = w * d.smp.fillna(d.smp.median()).clip(lower=0).to_numpy()
        w = w / w.mean()
    m = lgb.LGBMRegressor(**{**PARAMS, **(params or {})})
    m.fit(d[feats], y, sample_weight=w, categorical_feature=cat or "auto")
    m.feats_ = feats
    return m


def predict(model, d: pd.DataFrame) -> np.ndarray:
    """발전소별 kWh 예측 (0 이상)."""
    feats = getattr(model, "feats_", FEATS)
    cf = model.predict(d[feats])
    cf = np.where(d.elev.to_numpy() > 0, cf, 0.0)
    return np.clip(cf, 0, None) * d.cap.to_numpy()
