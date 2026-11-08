import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "analysis"))
from sm55_settlement_decomposition import make_detail


def test_group_settlement_decomposition_identity_and_directional_parts():
    ts = pd.DatetimeIndex([
        pd.Timestamp("2024-06-01 12:00", tz="Asia/Seoul"),
        pd.Timestamp("2024-06-01 16:00", tz="Asia/Seoul"),
    ])
    sites = pd.DataFrame({
        "site_id": ["A", "B", "C"],
        "lat": [36.0, 36.1, 35.9],
        "lon": [127.0, 127.1, 126.9],
        "capacity_kw": [100.0, 100.0, 100.0],
    })
    comp = pd.Series({"A": "G1", "B": "G1", "C": "G2"})
    actual = pd.DataFrame([
        {"site_id": site, "ts": time, "energy": 10.0}
        for time in ts for site in sites.site_id
    ])
    pred = actual[["site_id", "ts"]].copy()
    residuals = {"A": 4.0, "B": -3.0, "C": -2.0}
    pred["kwh"] = pred.site_id.map(residuals) + 10.0
    smp = pd.Series([100.0, 100.0], index=ts)

    detail, mae, bias = make_detail(pred, actual, sites, comp, smp)
    assert len(detail) == 4  # two groups × two hours
    assert mae > 0
    assert np.isfinite(bias)
    assert (detail.C_cancel >= 0).all()
    assert np.isclose(detail.W_individual.sum() - detail.W_group.sum(), detail.C_cancel.sum())
    assert np.isclose(detail.W_group.sum(), detail.over_W.sum() + detail.under_W.sum())
