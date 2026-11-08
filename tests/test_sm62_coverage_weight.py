import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from sm62_coverage_weight import coverage_weights, should_fit, support_audit  # noqa: E402


def test_weights_are_sqrt_coverage_and_group_mean_one():
    frame = pd.DataFrame({"group": ["G1", "G1", "G2", "G2"], "cov": [.25, 1.0, .04, .64]})
    weights = coverage_weights(frame)
    assert np.allclose(weights.iloc[:2].mean(), 1.0)
    assert np.allclose(weights.iloc[2:].mean(), 1.0)
    assert weights.iloc[0] < weights.iloc[1]
    assert weights.iloc[2] < weights.iloc[3]


def test_support_audit_reports_ess_and_seasonal_shares():
    frame = pd.DataFrame({
        "group": ["G1"] * 4,
        "cov": [.5, .6, .7, .8],
        "ts": pd.to_datetime(["2023-06-01 01:00+09:00", "2023-09-01 01:00+09:00",
                              "2024-01-01 01:00+09:00", "2024-04-01 01:00+09:00"]),
    })
    result = support_audit(frame)["G1"]
    assert result["n"] == 4
    assert 0 < result["ess"] <= 4
    assert np.isclose(result["weight"]["mean"], 1.0)
    assert set(result["season_share_weighted"]) == {"JJA", "SON", "DJF", "MAM"}


def test_preflight_stops_on_low_ess_or_excess_season_shift():
    unsafe = {"G1": {"ess_ratio": .7, "max_abs_season_share_shift": .01}}
    go, reasons = should_fit(unsafe)
    assert not go and reasons
