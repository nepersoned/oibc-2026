"""Describe association between a fixed-grid forecast and baseline error.

This does not estimate forecast bias or causal irradiance effects: actual
irradiance is not an input. Values are aggregated over observed site-hours.
"""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred-site", required=True)
    ap.add_argument("--forecast", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args()
    comp = sc.reference_composition(sc.load_sites())
    actual = sc.load_actual(a.start, a.end)
    pred = pd.read_parquet(a.pred_site)
    pred["ts"] = sc.to_ts(pred.ts)
    if actual.duplicated(["site_id", "ts"]).any() or pred.duplicated(["site_id", "ts"]).any():
        raise ValueError("duplicate site-hour")
    d = actual.merge(pred[["site_id", "ts", "kwh"]], on=["site_id", "ts"], how="left", validate="one_to_one")
    if d.kwh.isna().any() or not np.isfinite(d.kwh).all() or (d.kwh < 0).any():
        raise ValueError("missing or invalid observed-site prediction")
    d["group"] = d.site_id.map(comp)
    if d.group.isna().any():
        raise ValueError("missing group")
    d["residual"] = d.kwh - d.energy
    hourly = d.groupby(["group", "ts"], as_index=False).residual.sum()
    weather = pd.read_parquet(a.forecast)
    weather["ts"] = sc.to_ts(weather.ts)
    if weather.duplicated(["ts", "pt"]).any():
        raise ValueError("duplicate forecast grid/time")
    weather = weather.groupby("ts").shortwave_radiation.mean().rename("ghi")
    hourly["ghi"] = hourly.ts.map(weather)
    hourly = hourly[hourly.ts.dt.hour.between(11, 15)].dropna(subset=["ghi"])
    if hourly.empty:
        raise ValueError("no common midday forecast data")
    hourly["day"] = (hourly.ts - pd.Timedelta(hours=1)).dt.floor("D")
    print("Common 11-15 group-hours:", len(hourly))
    for group, sub in hourly.groupby("group"):
        daily = sub.groupby("day").agg(ghi=("ghi", "mean"), residual=("residual", "sum"))
        print(f"{group}: hourly_corr={sub.ghi.corr(sub.residual):.4f} "
              f"daily_corr={daily.ghi.corr(daily.residual):.4f} days={len(daily)}")


if __name__ == "__main__":
    main()
