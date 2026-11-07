import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from features import solar, target_day
from sm53_profile import FEATURE_COLUMNS, add_profile_features, daily_asymmetry


def _synthetic_data(days=60):
    site = pd.DataFrame({
        "site_id": ["SP0001"], "capacity_kw": [100.0],
        "lat": [36.0], "lon": [127.0],
    })
    dates = pd.date_range("2024-01-01 05:00", periods=days * 15, freq="h", tz="Asia/Seoul")
    keep = (dates.hour >= 5) & (dates.hour <= 19)
    ts = dates[keep]
    elev, azim, cosz = solar(ts, np.full(len(ts), 36.0), np.full(len(ts), 127.0))
    cs = np.where(cosz > 0, 1098 * np.maximum(cosz, 1e-3) * np.exp(-0.057 / np.maximum(cosz, 1e-3)), 0)
    side_scale = np.where(np.sin(np.deg2rad(azim)) >= 0, 0.8, 0.5)
    energy = 100.0 * cs / 1000.0 * side_scale
    generation = pd.DataFrame({"site_id": "SP0001", "ts": ts, "energy": energy})
    return site, generation


def _target(site, ts):
    elev, azim, _ = solar(pd.DatetimeIndex([ts]), site.lat.to_numpy(), site.lon.to_numpy())
    return pd.DataFrame({"site_id": [site.site_id.iloc[0]], "ts": [ts], "azim": azim, "elev": elev})


def test_historical_profile_uses_prior_only_and_future_mutation_is_inert():
    sites, history = _synthetic_data()
    target_ts = pd.Timestamp("2024-02-25 12:00", tz="Asia/Seoul")
    targets = _target(sites, target_ts)
    changed = history.copy()
    changed.loc[changed.ts >= pd.Timestamp("2024-02-22", tz="Asia/Seoul"), "energy"] *= 50
    base = add_profile_features(targets, daily_asymmetry(history, sites), sites)
    future_changed = add_profile_features(targets, daily_asymmetry(changed, sites), sites)
    pd.testing.assert_frame_equal(base, future_changed)
    assert base.sm53_am_pm_profile.iloc[0] > 0
    assert base.sm53_am_pm_interaction.iloc[0] != 0


def test_validation_profile_is_frozen_against_evaluation_actuals():
    sites, history = _synthetic_data()
    validation_start = pd.Timestamp("2024-02-20 01:00", tz="Asia/Seoul")
    target_ts = pd.Timestamp("2024-03-01 12:00", tz="Asia/Seoul")
    frozen_end = target_day(pd.Series([validation_start])).iloc[0] - pd.Timedelta(days=4)
    targets = _target(sites, target_ts)
    eval_actual = history[history.ts >= validation_start].copy()
    eval_actual["energy"] *= 100
    a = add_profile_features(targets, daily_asymmetry(history, sites), sites, frozen_profile_day=frozen_end)
    b = add_profile_features(targets, daily_asymmetry(pd.concat([history, eval_actual]), sites), sites,
                              frozen_profile_day=frozen_end)
    pd.testing.assert_frame_equal(a, b)


def test_unseen_site_has_finite_safe_fallback_and_shared_schema():
    sites, history = _synthetic_data()
    unseen = pd.DataFrame({"site_id": ["SP9999"], "ts": [pd.Timestamp("2024-03-01 12:00", tz="Asia/Seoul")],
                           "azim": [100.0], "elev": [40.0]})
    site_unseen = pd.concat([sites, pd.DataFrame({"site_id": ["SP9999"], "capacity_kw": [50.0],
                                                   "lat": [36.0], "lon": [127.0]})], ignore_index=True)
    daily = daily_asymmetry(history, sites)
    train_features = add_profile_features(_target(sites, pd.Timestamp("2024-02-25 12:00", tz="Asia/Seoul")),
                                          daily, sites)
    inference_features = add_profile_features(unseen, daily, site_unseen,
                                              frozen_profile_day=pd.Timestamp("2024-02-15", tz="Asia/Seoul"))
    assert list(train_features.columns) == list(inference_features.columns) == FEATURE_COLUMNS
    assert np.isfinite(inference_features.to_numpy()).all()
    assert inference_features.loc[0, "sm53_am_pm_profile"] == 0
    assert inference_features.loc[0, "sm53_am_pm_interaction"] == 0
    assert inference_features.loc[0, "sm53_profile_support"] == 0


def test_right_closed_midnight_uses_previous_target_day_for_embargo():
    ts = pd.Series([pd.Timestamp("2024-06-01 00:00", tz="Asia/Seoul")])
    assert target_day(ts).iloc[0] == pd.Timestamp("2024-05-31 00:00", tz="Asia/Seoul")
