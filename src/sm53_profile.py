"""Leakage-safe historical solar-response profiles for the SM#53 pilot."""
from __future__ import annotations

import numpy as np
import pandas as pd

from features import solar, target_day
from scoring import TZ, to_ts

ELEVATION_MIN = 15.0
CLEARSKY_MIN = 250.0
ELEVATION_BIN_DEGREES = 5.0
PROFILE_LOOKBACK_DAYS = 730
PROFILE_EMBARGO_DAYS = 4
MIN_PAIRED_DAYS = 30
SHRINKAGE_DAYS = 30.0
FEATURE_COLUMNS = [
    "sm53_am_pm_profile",
    "sm53_am_pm_interaction",
    "sm53_profile_support",
]


def daily_asymmetry(generation: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    """Reduce observed generation to one same-day, matched-elevation AM/PM value per site-day.

    Only supplied generation, capacity, coordinates for existing solar geometry, and
    timestamps are used. Missing generation records remain missing; they are never
    synthesized as zero observations.
    """
    required_gen = {"site_id", "ts", "energy"}
    required_sites = {"site_id", "capacity_kw", "lat", "lon"}
    if missing := required_gen - set(generation.columns):
        raise ValueError(f"generation missing columns: {sorted(missing)}")
    if missing := required_sites - set(sites.columns):
        raise ValueError(f"sites missing columns: {sorted(missing)}")
    if sites.site_id.duplicated().any():
        raise ValueError("sites must have unique site_id")

    g = generation[["site_id", "ts", "energy"]].copy()
    g["ts"] = to_ts(g.ts)
    site = sites.set_index("site_id")
    g["capacity_kw"] = g.site_id.map(site.capacity_kw)
    g["lat"] = g.site_id.map(site.lat)
    g["lon"] = g.site_id.map(site.lon)
    valid = (g.capacity_kw > 0) & np.isfinite(g.energy) & g.lat.notna() & g.lon.notna()
    g = g.loc[valid].copy()
    elev, azim, cosz = solar(pd.DatetimeIndex(g.ts), g.lat.to_numpy(), g.lon.to_numpy())
    cosz = np.clip(cosz.astype("float64"), 1e-3, None)
    ghi_cs = np.where(cosz > 0, 1098.0 * cosz * np.exp(-0.057 / cosz), 0.0)
    g["elev"] = elev
    g["azim"] = azim
    g["ghi_cs"] = ghi_cs
    g = g[(g.elev >= ELEVATION_MIN) & (g.ghi_cs >= CLEARSKY_MIN)].copy()
    if g.empty:
        return pd.DataFrame(columns=["site_id", "profile_day", "daily_asymmetry"])

    g["u"] = g.energy.clip(lower=0).to_numpy() / (
        g.capacity_kw.to_numpy() * g.ghi_cs.to_numpy() / 1000.0
    )
    g["profile_day"] = target_day(g.ts)
    g["elevation_band"] = np.floor(g.elev.to_numpy() / ELEVATION_BIN_DEGREES).astype("int16")
    g["side"] = np.where(np.sin(np.deg2rad(g.azim.to_numpy())) >= 0.0, "am", "pm")
    band = (g.groupby(["site_id", "profile_day", "elevation_band", "side"],
                      observed=True, sort=False).u.median().unstack("side"))
    if not {"am", "pm"}.issubset(band.columns):
        return pd.DataFrame(columns=["site_id", "profile_day", "daily_asymmetry"])
    paired = band.dropna(subset=["am", "pm"]).copy()
    if paired.empty:
        return pd.DataFrame(columns=["site_id", "profile_day", "daily_asymmetry"])
    paired["delta"] = paired.am - paired.pm
    daily = (paired.groupby(level=["site_id", "profile_day"], sort=False).delta
             .agg(daily_asymmetry="median", paired_bands="size").reset_index())
    daily = daily[np.isfinite(daily.daily_asymmetry)].copy()
    return daily.sort_values(["site_id", "profile_day"], kind="stable").reset_index(drop=True)


def _history_lookup(daily: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if daily.empty:
        return out
    for site_id, group in daily.groupby("site_id", sort=False):
        days = pd.DatetimeIndex(group.profile_day).asi8
        values = group.daily_asymmetry.to_numpy(dtype="float64")
        order = np.argsort(days, kind="stable")
        out[site_id] = (days[order], values[order])
    return out


def add_profile_features(targets: pd.DataFrame, daily: pd.DataFrame, sites: pd.DataFrame,
                         frozen_profile_day: pd.Timestamp | None = None) -> pd.DataFrame:
    """Attach the three registered features to rows without consulting their outcomes.

    Training rows use an as-of date per right-closed target day. Validation/inference
    rows may pass one frozen last-eligible paired day so later actuals cannot refresh
    the profile during the evaluation period.
    """
    required = {"site_id", "ts"}
    if missing := required - set(targets.columns):
        raise ValueError(f"targets missing columns: {sorted(missing)}")
    t = targets[["site_id", "ts"]].copy().reset_index(drop=True)
    t["ts"] = to_ts(t.ts)
    t["target_day"] = target_day(t.ts)
    site = sites.set_index("site_id")
    t["lat"] = t.site_id.map(site.lat)
    t["lon"] = t.site_id.map(site.lon)
    if "azim" in targets:
        azim = pd.to_numeric(targets.azim, errors="coerce").to_numpy(dtype="float64")
    else:
        _, azim, _ = solar(pd.DatetimeIndex(t.ts), t.lat.to_numpy(), t.lon.to_numpy())
    if not np.isfinite(azim).all():
        raise ValueError("target azimuth must be finite")

    queries = t[["site_id", "target_day"]].drop_duplicates().reset_index(drop=True)
    if frozen_profile_day is not None:
        frozen_profile_day = pd.Timestamp(frozen_profile_day)
        if frozen_profile_day.tz is None:
            frozen_profile_day = frozen_profile_day.tz_localize(TZ)
        else:
            frozen_profile_day = frozen_profile_day.tz_convert(TZ)
        queries["profile_end"] = frozen_profile_day.normalize()
    else:
        queries["profile_end"] = queries.target_day - pd.Timedelta(days=PROFILE_EMBARGO_DAYS)

    lookup = _history_lookup(daily)
    rows = []
    for query in queries.itertuples(index=False):
        dates_values = lookup.get(query.site_id)
        n = 0
        profile = 0.0
        if dates_values is not None:
            date_ns, values = dates_values
            end = pd.Timestamp(query.profile_end).value
            start = end - pd.Timedelta(days=PROFILE_LOOKBACK_DAYS - 1).value
            left = int(np.searchsorted(date_ns, start, side="left"))
            right = int(np.searchsorted(date_ns, end, side="right"))
            sample = values[left:right]
            n = len(sample)
            if n >= MIN_PAIRED_DAYS:
                profile = (n / (n + SHRINKAGE_DAYS)) * float(np.median(sample))
        rows.append((query.site_id, query.target_day, profile, np.log1p(n)))
    table = pd.DataFrame(
        rows,
        columns=["site_id", "target_day", "sm53_am_pm_profile", "sm53_profile_support"],
    )
    out = t[["site_id", "target_day"]].merge(table, on=["site_id", "target_day"],
                                               how="left", validate="many_to_one", sort=False)
    out["sm53_am_pm_interaction"] = out.sm53_am_pm_profile.to_numpy() * np.sin(np.deg2rad(azim))
    out[FEATURE_COLUMNS] = out[FEATURE_COLUMNS].astype("float32")
    return out[FEATURE_COLUMNS]
