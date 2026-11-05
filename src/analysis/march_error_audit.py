"""Retrospective aggregate diagnostics; never labels output curtailment.

Uses supplied site OOF forecasts, actuals for scoring only, and issued weather.
Cloud-round revision threshold is estimated only from the prior year. No
post-hoc prediction adjustments or individual observations are exported.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import features as F
import scoring as sc
import daily_irradiance_calibration as cal


def revisions():
    f = F.load_forecast("train", "wb", ["wb_cloud"])
    a = f[f["round"] == 10][["wb_station", "ts", "wb_cloud"]].rename(columns={"wb_cloud":"c10"})
    b = f[f["round"] == 17][["wb_station", "ts", "wb_cloud"]].rename(columns={"wb_cloud":"c17"})
    if a.duplicated(["wb_station", "ts"]).any() or b.duplicated(["wb_station", "ts"]).any():
        raise ValueError("duplicate forecast station/time/round")
    j = a.merge(b, on=["wb_station", "ts"], how="inner", validate="one_to_one").dropna(subset=["c10", "c17"])
    j["revision"] = (j.c17-j.c10).abs()
    h = j.groupby("ts").revision.mean().reset_index()
    h = h[h.ts.dt.hour.between(11,15)].copy()
    h["day"] = cal.day(h.ts)
    d = h.groupby("day").agg(revision=("revision", "mean"), hours=("ts", "size"))
    d.loc[d.hours < 5, "revision"] = np.nan
    return d.revision


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("base", "candidate", "weather", "out"):
        ap.add_argument("--"+name, required=True)
    a=ap.parse_args()
    sites=sc.load_sites()
    comp=sc.reference_composition(sites)
    actual=sc.load_actual("2024-06-01", "2025-06-01")
    m=actual.copy()
    for name, path in (("base",a.base),("candidate",a.candidate)):
        p=pd.read_parquet(path)
        p["ts"]=sc.to_ts(p.ts)
        if p.duplicated(["site_id","ts"]).any():
            raise ValueError("duplicate predictions")
        m=m.merge(p[["site_id","ts","kwh"]].rename(columns={"kwh":name}),on=["site_id","ts"],how="left",validate="one_to_one")
    if not np.isfinite(m[["base","candidate"]].to_numpy()).all():
        raise ValueError("missing prediction")
    m["group"]=m.site_id.map(comp)
    if m.group.isna().any():
        raise ValueError("unknown group")
    m["weight"] = .1*m.ts.map(sc.load_smp())*sc.k_weight(m.ts)
    if m.weight.isna().any() or (m.weight < 0).any():
        raise ValueError("missing/negative SMP")
    for c in ("base","candidate"):
        m[c+"_site_pen"] = m.weight*(m[c]-m.energy).abs()
    h=m.groupby(["group","ts"],as_index=False).agg(act=("energy","sum"),base=("base","sum"),candidate=("candidate","sum"),
                base_site_pen=("base_site_pen","sum"),candidate_site_pen=("candidate_site_pen","sum"),weight=("weight","first"))
    h["day"] = cal.day(h.ts)
    rev = revisions()
    train = rev[(rev.index >= pd.Timestamp("2023-06-01",tz=sc.TZ)) & (rev.index < pd.Timestamp("2024-06-01",tz=sc.TZ))].dropna()
    if len(train) < 30:
        raise ValueError("insufficient prior forecast revision history")
    threshold = float(train.quantile(.75))
    h["revision"] = h.day.map(rev)
    h["revision_class"] = np.select([h.revision.isna(), h.revision >= threshold], ["missing", "high"], default="other")
    h=h.join(cal.build_weather(a.weather)[["clearness"]],on="day")
    h["sky"]=np.select([h.clearness < .35,h.clearness > .65],["cloudy","clear"],default="other_or_missing")
    try:
        dates=h.day.dt.tz_localize(None)
        h["daytype"]=np.select([dates.isin(F.off_days()),dates.dt.dayofweek >= 5],["holiday","weekend"],default="weekday")
    except ImportError:
        h["daytype"]=np.where(h.day.dt.dayofweek>=5,"weekend_or_holiday","weekday_or_holiday")
    h["period"]=np.where((h.day.dt.year==2025)&(h.day.dt.month==3),"2025-03","other_months")
    h["base_error_sign"]=np.where(h.base >= h.act,"over_or_equal","under")
    for c in ("base","candidate"):
        h[c+"_pen"]=h.weight*(h[c]-h.act).abs()
        h[c+"_signed"]=h.weight*(h[c]-h.act)
    result={"revision_q75_from_prior_year":threshold,"prior_revision_days":int(len(train)),"slices":{}}
    for subset, d in (("all",h),("midday",h[h.ts.dt.hour.between(11,15)])):
        result["slices"][subset]={}
        for key in ("period","group","sky","revision_class","daytype","base_error_sign"):
            table=d.groupby(["period",key] if key!="period" else ["period"],dropna=False).agg(
                base_W=("base_pen","sum"),candidate_W=("candidate_pen","sum"),
                base_site_W=("base_site_pen","sum"),candidate_site_W=("candidate_site_pen","sum"),
                base_signed=("base_signed","sum"),candidate_signed=("candidate_signed","sum"),n=("ts","size"))
            records=table.reset_index().to_dict(orient="records")
            result["slices"][subset][key]=records
    with open(a.out,"w",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
    print(f"Prior-year cloud revision q75={threshold:.3f}, days={len(train)}")
    for row in result["slices"]["midday"]["period"]:
        print(f"{row['period']}: W {row['base_W']:.2f} -> {row['candidate_W']:.2f}; "
              f"site sum {row['base_site_W']:.2f} -> {row['candidate_site_W']:.2f}")


if __name__ == "__main__":
    main()
