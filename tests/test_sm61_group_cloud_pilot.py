from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analysis.sm61_group_cloud_pilot import (  # noqa: E402
    LAYER_COLS, hourly_observed_capacity_w, registered_feature_pair,
)


def test_group_feature_pair_adds_only_vertical_cloud_layers():
    base = ["g_wa_cloud", "ext_gfs_tcc"]
    a, b = registered_feature_pair(base + LAYER_COLS)
    assert a == base
    assert set(b) - set(a) == set(LAYER_COLS)


def test_group_feature_pair_requires_all_three_cloud_layers():
    with pytest.raises(RuntimeError):
        registered_feature_pair(["g_wa_cloud", "gfs_lcdc"])


def test_observed_capacity_scoring_uses_same_capacity_scale_and_peak_weight():
    ts = pd.to_datetime(["2024-06-01 11:00:00+09:00", "2024-06-01 12:00:00+09:00"])
    actual = pd.DataFrame({
        "group": ["G1", "G1"], "ts": ts, "act": [100.0, 200.0],
        "cap_avail": [250.0, 500.0], "cov": [0.25, 0.50],
    })
    pred = pd.DataFrame({"group": ["G1", "G1"], "ts": ts, "cf_hat": [0.3, 0.3]})
    smp = pd.Series([100.0, 100.0], index=ts)
    scored = hourly_observed_capacity_w(pred, actual, smp)
    assert scored.pred_observed_capacity.tolist() == [75.0, 150.0]
    assert np.isclose(scored.w.sum(), 0.1 * 100 * 3 * (25 + 50))
    assert scored.coverage_bin.astype(str).tolist() == ["<0.30", "≥0.50"]
