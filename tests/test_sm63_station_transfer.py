import pandas as pd

from src.analysis.sm63_station_transfer import feature_columns, station_targets


def test_station_targets_aggregate_only_observed_sites_by_station():
    sites = pd.DataFrame({
        "site_id": ["a", "b", "c"],
        "wb_station": ["WB1", "WB1", "WB2"],
        "capacity_kw": [100.0, 300.0, 200.0],
    })
    ts = pd.Timestamp("2024-06-01 12:00", tz="Asia/Seoul")
    generation = pd.DataFrame({
        "site_id": ["a", "c"],
        "ts": [ts, ts],
        "energy": [50.0, 40.0],
    })

    got = station_targets(generation, sites).set_index("wb_station")

    assert got.loc["WB1", "act"] == 50.0
    assert got.loc["WB1", "cap_avail"] == 100.0
    assert got.loc["WB1", "cov"] == 0.25
    assert got.loc["WB1", "cf"] == 0.5
    assert got.loc["WB1", "observed_sites"] == 1
    assert got.loc["WB2", "cf"] == 0.2


def test_station_feature_columns_exclude_ids_targets_and_raw_coordinates():
    frame = pd.DataFrame(columns=[
        "wb_station", "ts", "act", "cap_avail", "observed_sites", "cov", "cf", "wb_cloud",
        "station_capacity_kw", "elev",
    ])

    assert feature_columns(frame) == ["wb_cloud", "station_capacity_kw", "elev"]

    leaked = frame.assign(site_id="plant-id")
    try:
        feature_columns(leaked)
    except AssertionError:
        pass
    else:
        raise AssertionError("plant ID must be rejected if it enters the feature frame")
