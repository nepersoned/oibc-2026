import pandas as pd

from src.analysis.sm68_peak_delta_transfer import transfer_candidate


def test_transfer_changes_only_peak_and_leaves_unsupported_hours_unchanged():
    ts = pd.to_datetime([
        "2024-06-01 10:00:00+09:00",
        "2024-06-01 11:00:00+09:00",
        "2024-06-01 12:00:00+09:00",
    ])
    jh = pd.DataFrame({"group": ["G1"] * 3, "ts": ts,
                       "forecast_kwh": [100.0, 100.0, 5.0]})
    delta = pd.DataFrame({"group": ["G1", "G1"], "ts": ts[1:],
                          "delta": [20.0, -20.0]})

    result, counts = transfer_candidate(jh, delta)

    assert result.B.iloc[0] == result.A.iloc[0]  # off-peak and unsupported
    assert result.B.iloc[1] == 110.1
    assert result.B.iloc[2] == 0.0  # clipped at zero, with fixed 0.505 multiplier
    assert counts.to_dict() == {"supported": 2, "clipped": 1,
                                "changed": 2, "changed_peak": 2}


def test_zero_delta_preserves_peak_prediction_exactly():
    ts = pd.to_datetime(["2024-06-01 11:00:00+09:00"])
    jh = pd.DataFrame({"group": ["G2"], "ts": ts,
                       "forecast_kwh": [123.456]})
    delta = pd.DataFrame({"group": ["G2"], "ts": ts, "delta": [0.0]})

    result, counts = transfer_candidate(jh, delta)

    assert result.B.iloc[0] == result.A.iloc[0]
    assert counts.changed == 0
