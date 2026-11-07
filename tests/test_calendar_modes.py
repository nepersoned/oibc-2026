import builtins
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import features as F
import agg_model as AM


def test_weekday_mode_uses_right_closed_target_day():
    ts = pd.Series(pd.DatetimeIndex([
        "2025-06-01 00:00:00+09:00",  # previous target day is Saturday
        "2025-06-02 00:00:00+09:00",  # previous target day is Sunday
        "2025-06-03 00:00:00+09:00",  # previous target day is Monday
    ]))
    got = F.calendar(ts, "weekday")
    assert got.columns.tolist() == ["dow", "is_weekend"]
    assert got.dow.tolist() == [5, 6, 0]
    assert got.is_weekend.tolist() == [1, 1, 0]


def test_weekday_and_none_modes_never_read_holiday_sources(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("external holiday source was accessed")

    monkeypatch.setattr(F, "off_days", fail)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "holidays":
            raise AssertionError("holidays package was imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    ts = pd.Series(pd.DatetimeIndex(["2025-06-01 00:00:00+09:00", "2025-06-01 01:00:00+09:00"]))
    weekday = F.calendar(ts, "weekday")
    none = F.calendar(ts, "none")
    assert weekday.columns.tolist() == ["dow", "is_weekend"]
    assert none.empty


def test_legacy_calendar_preserves_existing_feature_names(monkeypatch):
    off = {pd.Timestamp("2025-05-31")}
    monkeypatch.setattr(F, "_OFF", off)
    ts = pd.Series(pd.DatetimeIndex(["2025-06-01 00:00:00+09:00"]))
    got = F.calendar(ts, "legacy")
    assert got.columns.tolist() == ["dow", "is_hol", "is_off", "off_run"]
    assert got.iloc[0].to_dict() == {"dow": 5, "is_hol": 1, "is_off": 1, "off_run": 1}


def test_site_and_group_design_columns_match_between_train_and_inference(monkeypatch):
    monkeypatch.setattr(F, "CAL_MODE", "weekday")
    monkeypatch.setattr(F, "CALENDAR", True)
    ts = pd.DatetimeIndex(["2025-06-01 00:00:00+09:00", "2025-06-01 01:00:00+09:00"])
    sites = pd.DataFrame({"site_id": ["PV001", "PV002"], "lat": [37.0, 36.0],
                          "lon": [127.0, 128.0], "capacity_kw": [100.0, 120.0]})
    comp = pd.Series({"PV001": "G1", "PV002": "G2"})
    idx = pd.DataFrame({"group": ["G1", "G2"], "ts": [ts[0], ts[1]]})
    gw = idx.copy()
    wd = pd.DataFrame(index=pd.DatetimeIndex(ts, name="ts"))
    train = AM.design(idx.copy(), gw.copy(), wd.copy(), sites, comp)
    infer = AM.design(idx.copy(), gw.copy(), wd.copy(), sites, comp)
    assert AM.feats_of(train) == AM.feats_of(infer)
    assert [c for c in train if c in {"dow", "is_weekend", "is_hol", "is_off", "off_run"}] == ["dow", "is_weekend"]
