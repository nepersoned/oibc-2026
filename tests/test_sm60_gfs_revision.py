import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analysis.sm60_gfs_revision import D2_LEADS, deaverage_d2


def test_deaverage_d2_recovers_matching_three_hour_slots():
    # D2 f039 is the 36–39 h average; f042 is the 36–42 h average.
    # De-averaging f042 recovers the 39–42 h interval, matching D1 f015–018.
    # The next D2 lead f045 is already a 42–45 h interval average.
    rows = np.array(
        [
            [39, 10.0, 3, 20.0, 3],
            [42, 16.0, 6, 26.0, 6],  # mean of 10/22 and 20/32
            [45, 30.0, 3, 40.0, 3],
            [48, 38.0, 6, 45.0, 6],  # mean of 30/46 and 40/50
            [51, 50.0, 3, 52.0, 3],
            [54, 56.0, 6, 58.0, 6],
            [57, 62.0, 3, 64.0, 3],
            [60, 68.0, 6, 70.0, 6],
            [63, 74.0, 3, 76.0, 3],
        ],
        dtype=float,
    )
    assert tuple(rows[:, 0].astype(int)) == D2_LEADS
    out = deaverage_d2(rows)
    assert out[42] == (22.0, 32.0)
    assert out[45] == (30.0, 40.0)
    assert out[48] == (46.0, 50.0)


def test_d1_d2_leads_share_valid_interval_after_24_hour_offset():
    from datetime import date, timedelta
    import pandas as pd

    target = date(2024, 6, 1)
    d1_init = pd.Timestamp(target - timedelta(days=1), tz="UTC")
    d2_init = pd.Timestamp(target - timedelta(days=2), tz="UTC")
    for lead_d1 in range(18, 40, 3):
        lead_d2 = lead_d1 + 24
        assert d1_init + pd.Timedelta(hours=lead_d1) == d2_init + pd.Timedelta(hours=lead_d2)
