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


def fit(d: pd.DataFrame):
    d = d[d.elev > 0]
    y = (d.energy / d.cap).clip(0, 1.2).astype("float32")
    return lgb.LGBMRegressor(**PARAMS).fit(d[FEATS].astype("float32"), y)


def predict(model, d: pd.DataFrame) -> np.ndarray:
    """발전소별 kWh 예측 (0 이상)."""
    cf = model.predict(d[FEATS].astype("float32"))
    cf = np.where(d.elev.to_numpy() > 0, cf, 0.0)
    return np.clip(cf, 0, None) * d.cap.to_numpy()
