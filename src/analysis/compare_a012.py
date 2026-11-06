"""Matched W/monthly/bootstrap comparison for A0/A1/A2 site predictions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import scoring as sc


def one(pred: pd.DataFrame, actual: pd.DataFrame, comp: pd.Series, smp: pd.Series) -> dict:
    p = pred.copy()
    p["ts"] = sc.to_ts(p.ts)
    a = actual.copy()
    a["ts"] = sc.to_ts(a.ts)
    m = a.merge(p[["site_id", "ts", "kwh"]], on=["site_id", "ts"], how="left", validate="one_to_one")
    if m.kwh.isna().any():
        raise ValueError("prediction coverage does not match observed evaluation rows")
    m["group"] = m.site_id.map(comp)
    h = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), pred=("kwh", "sum"))
    h["smp"] = h.ts.map(smp)
    h["pen"] = 0.1 * h.smp * sc.k_weight(h.ts) * (h.pred - h.act).abs()
    h["day"] = (h.ts - pd.Timedelta(hours=1)).dt.floor("D")
    h["month"] = h.day.dt.strftime("%Y-%m")
    daily = h.groupby("day").pen.sum().sort_index()
    blocks = np.array([daily.to_numpy()[i:i + 7].sum() for i in range(0, len(daily), 7)])
    rng = np.random.default_rng(20261106)
    draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
    return {
        "W": float(h.pen.sum()),
        "midday_W": float(h.loc[h.ts.dt.hour.between(11, 15), "pen"].sum()),
        "monthly_W": {k: float(v) for k, v in h.groupby("month").pen.sum().items()},
        "daily_W": {str(k): float(v) for k, v in daily.items()},
        "daily_mae": float(h.groupby("day").apply(lambda x: abs(x.pred.sum() - x.act.sum()), include_groups=False).mean()),
        "bootstrap_W": np.quantile(blocks[draws].sum(axis=1), [.025, .975]).tolist(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--a0", required=True)
    ap.add_argument("--a1", required=True)
    ap.add_argument("--a2", required=True)
    args = ap.parse_args()
    actual = sc.load_actual(args.start, args.end)
    comp = sc.reference_composition(sc.load_sites())
    smp = sc.load_smp()
    result = {name: one(pd.read_parquet(path), actual, comp, smp)
              for name, path in (("A0", args.a0), ("A1", args.a1), ("A2", args.a2))}
    base = result["A0"]["W"]
    for item in result.values():
        item["delta_vs_A0_pct"] = (item["W"] / base - 1) * 100
    base_daily = pd.Series(result["A0"]["daily_W"])
    for name in ("A1", "A2"):
        delta = pd.Series(result[name]["daily_W"]) - base_daily
        values = delta.to_numpy()
        blocks = np.array([values[i:i + 7].sum() for i in range(0, len(values), 7)])
        rng = np.random.default_rng(20261106)
        draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
        result[name]["bootstrap_delta_W_ci95"] = np.quantile(blocks[draws].sum(axis=1), [.025, .975]).tolist()
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
