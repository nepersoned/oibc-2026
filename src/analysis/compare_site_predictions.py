"""Compare two site forecasts on precisely the same observed site-hours."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import features as F
import scoring as sc
import daily_irradiance_calibration as study


def compare(base, candidate, actual, comp, smp, weather):
    for p in (base, candidate):
        p["ts"] = sc.to_ts(p.ts)
        if p.duplicated(["site_id", "ts"]).any():
            raise ValueError("duplicate site forecasts")
    m = actual.merge(base[["site_id", "ts", "kwh"]].rename(columns={"kwh":"base"}), on=["site_id", "ts"], how="left", validate="one_to_one")
    m = m.merge(candidate[["site_id", "ts", "kwh"]].rename(columns={"kwh":"candidate"}), on=["site_id", "ts"], how="left", validate="one_to_one")
    if not np.isfinite(m[["base", "candidate"]].to_numpy()).all() or (m[["base", "candidate"]] < 0).any().any():
        raise ValueError("missing or invalid observed forecasts")
    m["group"] = m.site_id.map(comp)
    if m.group.isna().any():
        raise ValueError("missing group")
    site_mae = {c: float((m[c] - m.energy).abs().mean()) for c in ("base", "candidate")}
    h = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), base=("base", "sum"), candidate=("candidate", "sum"))
    h["day"] = study.day(h.ts)
    h["smp"] = h.ts.map(smp)
    if h.smp.isna().any() or (h.smp < 0).any():
        raise ValueError("missing/negative SMP")
    h["weight"] = .1 * h.smp * sc.k_weight(h.ts)
    h = h.join(weather[["clearness"]], on="day")
    h["month"] = h.day.dt.strftime("%Y-%m")
    h["period"] = np.select([h.ts.dt.hour.between(8,10), h.ts.dt.hour.between(11,13), h.ts.dt.hour.between(14,16)], ["morning","noon","afternoon"], default="other")
    h["season"] = h.day.dt.month.map({12:"winter",1:"winter",2:"winter",3:"spring",4:"spring",5:"spring",6:"summer",7:"summer",8:"summer",9:"autumn",10:"autumn",11:"autumn"})
    h["sky"] = np.select([h.clearness < .35, h.clearness > .65], ["cloudy", "clear"], default="middle_or_missing")
    try:
        dates = h.day.dt.tz_localize(None)
        h["daytype"] = np.select([dates.isin(F.off_days()), dates.dt.dayofweek >= 5], ["holiday", "weekend"], default="weekday")
    except ImportError:
        h["daytype"] = np.where(h.day.dt.dayofweek >= 5, "weekend_or_holiday", "weekday_or_holiday")
    h["error_sign"] = np.where(h.base >= h.act, "over_or_equal", "under")
    errs = {c: h[c] - h.act for c in ("base", "candidate")}
    out = {}
    for name in ("base", "candidate"):
        pen = h.weight * errs[name].abs()
        daily = h.groupby(["group", "day"])[[name, "act"]].sum()
        out[name] = {"W": float(pen.sum()), "S": float((h.smp*h.act).sum() - pen.sum()),
                     "site_mae": site_mae[name], "group_mae": float(errs[name].abs().mean()),
                     "daily_mae": float((daily[name] - daily.act).abs().mean()),
                     "midday_W": float(pen[h.ts.dt.hour.between(11,15)].sum()),
                     "monthly_W": pen.groupby(h.month).sum().to_dict(),
                     "segments": {key: pen.groupby(h[key]).sum().to_dict() for key in ("period","season","sky","daytype","error_sign")}}
    out["residual_corr"] = float(errs["base"].corr(errs["candidate"]))
    delta = (h.weight*(errs["candidate"].abs()-errs["base"].abs())).groupby(h.day).sum().sort_index().to_numpy()
    blocks = np.array([delta[i:i+7].sum() for i in range(0, len(delta), 7)])
    rng = np.random.default_rng(20261106)
    draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
    out["bootstrap_delta_W_ci95"] = np.quantile(blocks[draws].sum(axis=1), [.025, .975]).tolist()
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ("base", "candidate", "start", "end", "weather", "out"):
        ap.add_argument("--"+arg, required=True)
    a=ap.parse_args()
    sites=sc.load_sites()
    result=compare(pd.read_parquet(a.base), pd.read_parquet(a.candidate), sc.load_actual(a.start,a.end),
                   sc.reference_composition(sites), sc.load_smp(), study.build_weather(a.weather))
    with open(a.out,"w",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
    for name in ("base", "candidate"):
        item=result[name]
        print(f"{name}: W={item['W']:.2f} S={item['S']:.2f} daily_mae={item['daily_mae']:.2f} midday_W={item['midday_W']:.2f}")
    print(f"delta_W_percent={(result['candidate']['W']/result['base']['W']-1)*100:+.3f}% corr={result['residual_corr']:.4f} CI={result['bootstrap_delta_W_ci95']}")


if __name__ == "__main__":
    main()
