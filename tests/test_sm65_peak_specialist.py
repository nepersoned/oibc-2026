import pandas as pd
import pytest

from src.analysis.sm65_peak_specialist import blend_peak


def test_peak_blend_changes_only_11_to_15_kst():
    ts = pd.to_datetime(["2024-06-01 10:00", "2024-06-01 11:00", "2024-06-01 15:00", "2024-06-01 16:00"]).tz_localize("Asia/Seoul")
    base = pd.DataFrame({"site_id": [1] * 4, "ts": ts, "kwh": [5., 10., 20., 5.]})
    expert = pd.DataFrame({"site_id": [1, 1], "ts": ts[[1, 2]], "kwh": [14., 16.]})
    out = blend_peak(base, expert)
    assert out.kwh.tolist() == [5., 12., 18., 5.]
    pd.testing.assert_frame_equal(base, pd.DataFrame({"site_id": [1] * 4, "ts": ts, "kwh": [5., 10., 20., 5.]}))


def test_peak_blend_rejects_missing_expert_key():
    ts = pd.to_datetime(["2024-06-01 11:00", "2024-06-01 12:00"]).tz_localize("Asia/Seoul")
    base = pd.DataFrame({"site_id": [1, 1], "ts": ts, "kwh": [10., 20.]})
    expert = base.iloc[:1].copy()
    with pytest.raises(ValueError, match="keys differ"):
        blend_peak(base, expert)
