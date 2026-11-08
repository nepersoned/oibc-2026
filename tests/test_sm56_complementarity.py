import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from sm56_complementarity import ALPHAS, mix_prediction


def test_fixed_mixture_weights_preserve_group_hour_keys():
    idx = pd.MultiIndex.from_tuples([("G1", "t1"), ("G2", "t1")])
    jh = pd.Series([100.0, 200.0], index=idx)
    sm = pd.Series([120.0, 160.0], index=idx)

    assert set(ALPHAS) == {0.0, 0.05, 0.1, 0.2}
    np.testing.assert_allclose(mix_prediction(jh, sm, 0.0), jh)
    np.testing.assert_allclose(mix_prediction(jh, sm, 0.05), [101.0, 198.0])
    np.testing.assert_allclose(mix_prediction(jh, sm, 0.2), [104.0, 192.0])


def test_mixture_rejects_unregistered_weight_or_misaligned_keys():
    jh = pd.Series([1.0], index=["G1-t1"])
    sm = pd.Series([2.0], index=["G2-t1"])
    with pytest.raises(ValueError, match="ordered keys"):
        mix_prediction(jh, sm, 0.05)
    with pytest.raises(ValueError, match="frozen values"):
        mix_prediction(jh, jh, 0.15)
