import pandas as pd

from src.analysis.sm67_strong_site_peak import F


def test_rich2_round10_and_previous_forecast_day(monkeypatch):
    ts = pd.to_datetime([
        "2024-06-01 11:00", "2024-06-01 12:00",
        "2024-06-02 00:00", "2024-06-02 11:00",
    ]).tz_localize("Asia/Seoul")
    rows = []
    for round_, shift in [(10, -5.), (17, 0.)]:
        for stamp, cloud in zip(ts, [20., 30., 40., 50.]):
            rows.append({"wa_station": 1, "round": round_, "ts": stamp,
                         **{c: (cloud if c == "wa_cloud" else 10. + shift) for c in F.WA_ALL}})
    raw = pd.DataFrame(rows)
    monkeypatch.setattr(F, "RICH2", True)
    rich = F.prep_forecast(raw, "wa", F.WA_ALL)
    day2 = rich.loc[rich.ts.eq(ts[3])].iloc[0]
    assert day2.wa_temp_r10 == 5.
    assert day2.wa_cloud_daymean_prev == 25.
    monkeypatch.setattr(F, "RICH2", False)
    old = F.prep_forecast(raw, "wa", F.WA_ALL)
    assert "wa_temp_r10" not in old.columns
    assert "wa_cloud_daymean_prev" not in old.columns
