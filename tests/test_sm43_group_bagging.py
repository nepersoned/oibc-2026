import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from analysis.sm39_group_site_integration import redistribute
from analysis.sm43_group_bagging import average_site_frames


def test_group_seed_predictions_average_by_aligned_site_time_keys():
    ts = pd.DatetimeIndex(["2024-06-01 01:00:00+09:00"])
    a = pd.DataFrame({"site_id": [1, 2], "ts": [ts[0], ts[0]], "kwh": [10.0, 20.0]})
    b = pd.DataFrame({"site_id": [2, 1], "ts": [ts[0], ts[0]], "kwh": [40.0, 30.0]})
    got = average_site_frames([a, b]).set_index("site_id").kwh
    assert got.to_dict() == {1: 20.0, 2: 30.0}


def test_redistribution_conserves_fixed_alpha_group_target():
    ts = pd.DatetimeIndex(["2024-06-01 01:00:00+09:00"])
    sites = pd.DataFrame({"site_id": [1, 2], "capacity_kw": [100.0, 100.0]})
    comp = pd.Series({1: "G1", 2: "G1"})
    site_pred = pd.DataFrame({"site_id": [1, 2], "ts": [ts[0], ts[0]], "kwh": [10.0, 20.0]})
    group_pred = pd.DataFrame({"group": ["G1"], "ts": [ts[0]], "pred": [40.0]})
    out = redistribute(site_pred, group_pred, sites, comp, 0.2, ts)
    # 0.8 * (10 + 20) + 0.2 * 40 = 32 kWh.
    assert np.isclose(out.kwh.sum(), 32.0)
    assert np.isfinite(out.kwh).all() and (out.kwh >= 0).all()
