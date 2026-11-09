import pandas as pd
import pytest

from src.analysis.sm68_peak_delta_transfer import transfer_candidate, validate_delta_group
from src.analysis.sm68_export_handoff import build_actual_groups, build_group_delta, write_roundtrip


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
    assert counts == {"supported_group_hours": 2, "unsupported_group_hours": 1,
                      "clipped_group_hours": 1, "changed_group_hours": 2,
                      "changed_peak_group_hours": 2}


def test_zero_delta_preserves_peak_prediction_exactly():
    ts = pd.to_datetime(["2024-06-01 11:00:00+09:00"])
    jh = pd.DataFrame({"group": ["G2"], "ts": ts,
                       "forecast_kwh": [123.456]})
    delta = pd.DataFrame({"group": ["G2"], "ts": ts, "delta": [0.0]})

    result, counts = transfer_candidate(jh, delta)

    assert result.B.iloc[0] == result.A.iloc[0]
    assert counts["changed_group_hours"] == 0


def test_group_delta_uses_all_253_sites_and_preserves_zero_offpeak():
    sites = pd.DataFrame({"site_id": range(253), "group": ["G1"] * 134 + ["G2"] * 119})
    ts = pd.Timestamp("2024-06-01 10:00:00", tz="Asia/Seoul")
    base = pd.DataFrame({"site_id": range(253), "ts": [ts] * 253, "kwh": [1.0] * 253})
    cand = base.copy()
    cand["kwh"] = cand.kwh + 0.0

    grouped = build_group_delta(base, cand, sites, pd.DatetimeIndex([ts]), 1)

    assert grouped.group.tolist() == ["G1", "G2"]
    assert grouped.delta_kwh.tolist() == [0.0, 0.0]


def test_actual_group_handoff_contains_only_observed_rows_and_roundtrips_float64(tmp_path):
    sites = pd.DataFrame({"site_id": [1, 2], "capacity_kw": [100.0, 200.0]})
    composition = pd.DataFrame({"site_id": [1, 2], "group": ["G1", "G2"]})
    ts = pd.Timestamp("2024-06-01 11:00:00", tz="Asia/Seoul")
    generation = pd.DataFrame({"site_id": [1], "ts": [ts], "energy": [12.345678901234567]})

    actual, observed_site_hours = build_actual_groups(
        generation, sites, composition, ts, ts)

    assert observed_site_hours == 1
    assert len(actual) == 1  # unobserved G2 is omitted, never filled with zero
    assert actual.observed_capacity_kw.iloc[0] == 100.0
    out = tmp_path / "actual.csv"
    write_roundtrip(actual, out, ["actual_kwh", "observed_capacity_kw"])


def test_handoff_delta_requires_both_groups_at_each_supported_timestamp():
    ts = pd.Timestamp("2024-06-01 12:00:00", tz="Asia/Seoul")
    grid = pd.DatetimeIndex([ts])
    valid = pd.DataFrame({"group": ["G1", "G2"], "ts": [ts, ts], "delta": [1.0, -1.0]})
    assert len(validate_delta_group(valid, grid, expected_support_hours=1)) == 2

    incomplete = valid.iloc[:1].copy()
    with pytest.raises(RuntimeError, match="missing a group"):
        validate_delta_group(incomplete, grid, expected_support_hours=1)
