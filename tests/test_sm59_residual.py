import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from sm59_power_residual import correct_predictions


def test_correction_preserves_night_and_clips_daylight_capacity_factor():
    base_kwh = np.array([0.0, 10.0, 11.0])
    capacity = np.array([10.0, 10.0, 10.0])
    delta_cf = np.array([0.20, -0.20, 0.20])
    daylight = np.array([False, True, True])

    actual = correct_predictions(base_kwh, capacity, delta_cf, daylight)

    np.testing.assert_allclose(actual, [0.0, 8.0, 12.0])


def test_correction_keeps_frozen_positive_night_allocation_unchanged():
    base_kwh = np.array([0.05, 4.0])
    capacity = np.array([10.0, 10.0])
    delta_cf = np.array([0.20, 0.05])
    daylight = np.array([False, True])

    actual = correct_predictions(base_kwh, capacity, delta_cf, daylight)

    assert actual[0] == base_kwh[0]
    assert actual[1] == 4.5
