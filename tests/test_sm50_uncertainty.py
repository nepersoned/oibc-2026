import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from analysis.sm50_forecast_uncertainty import INDICATORS, locked_tertiles, provider_hourly


def test_locked_tertiles_use_training_distribution_only():
    train = pd.DataFrame({"target_day": pd.date_range("2021-01-01", periods=90, tz="Asia/Seoul")})
    valid = pd.DataFrame({"target_day": pd.date_range("2022-01-01", periods=6, tz="Asia/Seoul")})
    for col in INDICATORS:
        train[col] = range(90)
        valid[col] = [0, 20, 30, 60, 80, 1035]
    bins_a, cuts_a = locked_tertiles(train, valid)
    train_shifted = train.copy()
    for col in INDICATORS:
        train_shifted[col] += 1000
    bins_b, cuts_b = locked_tertiles(train_shifted, valid)
    assert cuts_a[INDICATORS[0]]["q33"] != cuts_b[INDICATORS[0]]["q33"]
    assert bins_a[INDICATORS[0] + "_bin"].iloc[-1] == "high"
    assert bins_b[INDICATORS[0] + "_bin"].iloc[-1] == "middle"


def test_locked_tertiles_marks_collapsed_cutpoints_unavailable():
    train = pd.DataFrame({"target_day": pd.date_range("2021-01-01", periods=60, tz="Asia/Seoul")})
    valid = pd.DataFrame({"target_day": pd.date_range("2022-01-01", periods=3, tz="Asia/Seoul")})
    for col in INDICATORS:
        train[col] = 1.0
        valid[col] = [0.0, 1.0, 2.0]
    bins, cuts = locked_tertiles(train, valid)
    assert not cuts[INDICATORS[0]]["available"]
    assert bins[INDICATORS[0] + "_bin"].isna().all()



def test_round17_preference_falls_back_per_station(tmp_path):
    ts = pd.Timestamp("2024-06-01 12:00:00", tz="Asia/Seoul")
    raw = pd.DataFrame({
        "wa_station": ["A", "B", "B"],
        "round": [10, 10, 17],
        "ts": [ts, ts, ts],
        "wa_cloud": [40.0, 20.0, 60.0],
    })
    path = tmp_path / "forecast.parquet"
    raw.to_parquet(path, index=False)
    got, audit = provider_hourly(path, "wa", "wa_station", "wa_cloud", ts, ts)
    # A falls back to 40 from round 10; B uses round 17 value 60.
    assert got.loc[0, "wa_cloud"] == 50.0
    assert audit["preferred_station_timestamp_rows"] == 2
