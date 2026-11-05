"""Time-forward diagnostic: freeze low-history sites during group assignment.

Uses observed site-hours only in both fit and evaluation. Missing residuals are
zero in the objective, as in composition.py, but never treated as observations
when computing coverage. Evaluation must follow fitting and use fixed site
predictions; this cannot reassign a group-direct model or establish causality.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


def load_matrix(path, start, end, sites):
    pred = pd.read_parquet(path)
    pred["ts"] = sc.to_ts(pred.ts)
    if pred.duplicated(["site_id", "ts"]).any():
        raise ValueError("duplicate prediction keys")
    actual = sc.load_actual(start, end)
    if actual.duplicated(["site_id", "ts"]).any():
        raise ValueError("duplicate actual keys")
    df = actual.merge(pred[["site_id", "ts", "kwh"]], on=["site_id", "ts"], how="left", validate="one_to_one")
    if df.kwh.isna().any() or not np.isfinite(df.kwh).all() or (df.kwh < 0).any():
        raise ValueError("missing or invalid prediction for observed site-hour")
    df["residual"] = df.kwh - df.energy
    mat = df.pivot(index="ts", columns="site_id", values="residual").reindex(columns=sites.site_id)
    coverage = mat.notna().mean().to_numpy()
    ts = mat.index.to_series()
    smp = ts.map(sc.load_smp())
    if smp.isna().any() or (smp < 0).any():
        raise ValueError("missing/negative SMP")
    weights = 0.1 * smp.to_numpy() * sc.k_weight(ts)
    return mat.fillna(0).to_numpy(dtype=np.float64), weights, coverage


def objective(x, residual, weights):
    one = residual @ x
    return float(np.dot(weights, np.abs(one) + np.abs(residual.sum(axis=1) - one)))


def optimize(initial, residual, weights, capacity, allowed, min_capacity=20000, rounds=50):
    """Greedy best feasible single move; the same solver for both policies."""
    x = initial.astype(float).copy()
    total_r = residual.sum(axis=1)
    e = residual @ x
    best = float(np.dot(weights, np.abs(e) + np.abs(total_r - e)))
    for _ in range(rounds):
        signs = 1 - 2 * x
        capacity1 = capacity @ x + signs * capacity
        feasible = allowed & (capacity1 >= min_capacity) & (capacity.sum() - capacity1 >= min_capacity)
        if not feasible.any():
            break
        indices = np.flatnonzero(feasible)
        errors = e[:, None] + residual[:, indices] * signs[indices]
        vals = (weights[:, None] * (np.abs(errors) + np.abs(total_r[:, None] - errors))).sum(axis=0)
        k = int(np.argmin(vals))
        if vals[k] >= best - 1e-6:
            break
        x[indices[k]] = 1 - x[indices[k]]
        e, best = errors[:, k], float(vals[k])
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--fit-start", default="2023-06-01")
    ap.add_argument("--fit-end", default="2024-06-01")
    ap.add_argument("--eval-start", default="2024-06-01")
    ap.add_argument("--eval-end", default="2025-06-01")
    ap.add_argument("--min-coverage", type=float, default=0.8)
    args = ap.parse_args()
    if pd.Timestamp(args.fit_end) > pd.Timestamp(args.eval_start):
        raise ValueError("fit period must precede evaluation")
    if not 0 <= args.min_coverage <= 1:
        raise ValueError("coverage must be between zero and one")
    sites = sc.load_sites()
    initial = (sites.current_group == "A").to_numpy(float)
    capacity = sites.capacity_kw.to_numpy(float)
    rfit, wfit, coverage = load_matrix(args.fit, args.fit_start, args.fit_end, sites)
    reval, weval, cov_eval = load_matrix(args.eval, args.eval_start, args.eval_end, sites)
    strict = coverage >= args.min_coverage
    print(f"fit sites={len(sites)} eligible={strict.sum()} zero_coverage={(coverage == 0).sum()} threshold={args.min_coverage}")
    print(f"mean fit site coverage={coverage.mean():.4f} eval={cov_eval.mean():.4f}")
    for name, allowed in (("reference", None), ("unrestricted", np.ones(len(sites), dtype=bool)), ("freeze_low_coverage", strict)):
        x = initial if allowed is None else optimize(initial, rfit, wfit, capacity, allowed)
        moved = x != initial
        print(f"{name}: moved={int(moved.sum())} low_coverage_moved={int((moved & ~strict).sum())} "
              f"unobserved_moved={int((moved & (coverage == 0)).sum())} "
              f"W_fit={objective(x,rfit,wfit):.2f} W_eval={objective(x,reval,weval):.2f}")


if __name__ == "__main__":
    main()
