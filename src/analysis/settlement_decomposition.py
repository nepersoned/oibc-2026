"""Diagnostic only: daily total/shape oracles and triangle-inequality bound.

Group predictions must use exactly the same observed site-hours as the actuals.
Neither oracle is valid for inference. Days with undefined shape are excluded
from *all* oracle comparisons and reported; timestamps are interval-ending.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


def decompose(frame: pd.DataFrame) -> dict:
    """frame: unique group/ts, observed act, pred and nonnegative SMP."""
    g = frame.copy()
    required = {"group", "ts", "act", "pred", "smp"}
    if not required.issubset(g.columns) or g.empty:
        raise ValueError("missing required columns or empty data")
    g["ts"] = sc.to_ts(g.ts)
    if g.duplicated(["group", "ts"]).any():
        raise ValueError("duplicate group/timestamp")
    if not np.isfinite(g[["act", "pred", "smp"]].to_numpy()).all():
        raise ValueError("missing or non-finite values")
    if (g[["pred", "smp"]] < 0).any().any():
        raise ValueError("negative prediction or SMP")
    g["day"] = (g.ts - pd.Timedelta(nanoseconds=1)).dt.floor("D")
    g["w"] = 0.1 * g.smp * sc.k_weight(g.ts)
    sums = g.groupby(["group", "day"])[["act", "pred"]].transform("sum")
    # Actuals can include negative meter anomalies. Preserve official scoring,
    # but exclude entire affected days from shape/total oracle comparison.
    negative_day = (g.act < 0).groupby([g.group, g.day]).transform("any")
    valid = (sums.act > 0) & (sums.pred > 0) & ~negative_day
    h = g.loc[valid].copy()
    h["total_oracle"] = h.pred * sums.loc[valid, "act"] / sums.loc[valid, "pred"]
    h["shape_oracle"] = h.act * sums.loc[valid, "pred"] / sums.loc[valid, "act"]
    def wsum(x, col):
        return float((x.w * (x[col] - x.act).abs()).sum())
    g["pen"] = g.w * (g.pred - g.act).abs()
    total = g.groupby("ts").agg(residual=("pred", "sum"), act=("act", "sum"), w=("w", "first"))
    # SMP must agree across groups; otherwise the bound is invalid.
    if (g.groupby("ts").smp.nunique() != 1).any():
        raise ValueError("inconsistent SMP across groups")
    bound = float((total.w * (total.residual - total.act).abs()).sum())
    daily = g.groupby(["group", "day"])[["pred", "act"]].sum()
    return {"W_all": wsum(g, "pred"), "W_common": wsum(h, "pred"),
            "W_total_oracle": wsum(h, "total_oracle"),
            "W_shape_oracle": wsum(h, "shape_oracle"), "W_lower_bound": bound,
            "excluded_group_days": int((~valid).groupby([g.group, g.day]).any().sum()),
            "daily_energy_mae": float((daily.pred - daily.act).abs().mean()),
            "group_hour_mae": float((g.pred - g.act).abs().mean()),
            "W_11_15": float(g.loc[g.ts.dt.hour.between(11, 15), "pen"].sum()),
            "monthly_W": g.groupby(g.day.dt.strftime("%Y-%m")).pen.sum().to_dict()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred-group", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--composition")
    a = ap.parse_args()
    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    if sc.check_composition(comp, sites):
        raise ValueError("invalid composition")
    actual = sc.load_actual(a.start, a.end)
    if actual.duplicated(["site_id", "ts"]).any() or actual.site_id.map(comp).isna().any():
        raise ValueError("duplicate actuals or missing group")
    actual = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"], as_index=False).energy.sum().rename(columns={"energy": "act"})
    pred = pd.read_parquet(a.pred_group) if a.pred_group.endswith(".parquet") else pd.read_csv(a.pred_group)
    pred["ts"] = sc.to_ts(pred.ts)
    if pred.duplicated(["group", "ts"]).any():
        raise ValueError("duplicate prediction keys")
    merged = actual.merge(pred[["group", "ts", "pred"]], on=["group", "ts"], how="left", validate="one_to_one")
    merged["smp"] = merged.ts.map(sc.load_smp())
    for k, v in decompose(merged).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
