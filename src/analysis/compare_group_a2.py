"""Compare existing G0/G2 group prediction files on a matched scoring set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import scoring as sc


def score(path: str, actual: pd.DataFrame, smp: pd.Series) -> tuple[pd.DataFrame, dict]:
    p = pd.read_parquet(path)
    p["ts"] = sc.to_ts(p.ts)
    if p.duplicated(["group", "ts"]).any() or p.pred.isna().any() or not np.isfinite(p.pred).all():
        raise ValueError(f"invalid prediction file: {path}")
    a = actual.copy()
    a["ts"] = sc.to_ts(a.ts)
    a = a.assign(group=a.site_id.map(sc.reference_composition(sc.load_sites())))
    a = a.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"))
    m = a.merge(p[["group", "ts", "pred"]], on=["group", "ts"], how="left", validate="one_to_one")
    if m.pred.isna().any():
        raise ValueError(f"prediction coverage mismatch: {path}")
    m["pen"] = 0.1 * m.ts.map(smp) * sc.k_weight(m.ts) * (m.pred - m.act).abs()
    m["day"] = (m.ts - pd.Timedelta(hours=1)).dt.floor("D")
    m["month"] = m.day.dt.strftime("%Y-%m")
    daily = m.groupby("day").pen.sum().sort_index()
    return m, {"W": float(m.pen.sum()), "midday_W": float(m.loc[m.ts.dt.hour.between(11, 15), "pen"].sum()),
               "monthly_W": {k: float(v) for k, v in m.groupby("month").pen.sum().items()},
               "daily_W": {str(k): float(v) for k, v in daily.items()}}


def bootstrap(delta: pd.Series) -> list[float]:
    blocks = np.array([delta.to_numpy()[i:i + 7].sum() for i in range(0, len(delta), 7)])
    rng = np.random.default_rng(20261106)
    draws = rng.integers(0, len(blocks), size=(2000, len(blocks)))
    return np.quantile(blocks[draws].sum(axis=1), [.025, .975]).tolist()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True); ap.add_argument("--end", required=True)
    ap.add_argument("--g0", required=True); ap.add_argument("--g2", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    actual, smp = sc.load_actual(a.start, a.end), sc.load_smp()
    m0, r0 = score(a.g0, actual, smp); m2, r2 = score(a.g2, actual, smp)
    d = m2.set_index(["group", "ts"]).pen - m0.set_index(["group", "ts"]).pen
    daily = d.groupby(level="ts").sum()
    r = {"G0": r0, "G2": r2, "delta_W": float(d.sum()), "delta_pct": float((r2["W"] / r0["W"] - 1) * 100),
         "bootstrap_delta_W_ci95": bootstrap(daily), "improved_days_pct": float((daily < 0).mean() * 100),
         "worsened_days_pct": float((daily > 0).mean() * 100),
         "monthly_delta_W": {k: float(v) for k, v in (m2.groupby("month").pen.sum() - m0.groupby("month").pen.sum()).items()}}
    Path(a.out).write_text(json.dumps(r, indent=2, ensure_ascii=False))
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
