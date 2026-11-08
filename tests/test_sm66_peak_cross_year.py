import pandas as pd

from src.analysis.sm66_peak_cross_year import target_days


def test_right_closed_midnight_belongs_to_prior_target_day():
    ts = pd.Series(pd.to_datetime([
        "2024-06-01 23:00", "2024-06-02 00:00", "2024-06-02 01:00",
    ]).tz_localize("Asia/Seoul"))
    assert target_days(ts).dt.strftime("%Y-%m-%d").tolist() == [
        "2024-06-01", "2024-06-01", "2024-06-02",
    ]
