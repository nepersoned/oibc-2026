"""Forward-only comparison of two *group* forecasts on identical keys.

Each local parquet/CSV input has group, ts, actual, smp, team, candidate.
Forecasts must refer to the same fixed composition and observed sites; caller
is responsible for creating this local-only table from time-valid OOF results.
No missing values are filled. Weight fitting is allowed only on earlier rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


def validate(data):
    required = ["group", "ts", "actual", "smp", "team", "candidate"]
    if data.empty or not set(required).issubset(data):
        raise ValueError("missing required columns or empty input")
    d = data[required].copy()
    d["ts"] = sc.to_ts(d.ts)
    if d.duplicated(["group", "ts"]).any() or d.group.isna().any() or not d.group.isin(sc.GROUPS).all():
        raise ValueError("invalid or duplicate group/time")
    if not np.isfinite(d[["actual", "smp", "team", "candidate"]].to_numpy()).all():
        raise ValueError("missing/nonfinite input")
    if (d[["smp", "team", "candidate"]] < 0).any().any():
        raise ValueError("negative price/forecast")
    if (d.groupby("ts").smp.nunique() != 1).any():
        raise ValueError("inconsistent price within timestamp")
    d["weight"] = .1 * d.smp * sc.k_weight(d.ts)
    return d


def fit_alpha(d):
    """Exact convex piecewise-linear minimum of W for candidate fraction."""
    diff = (d.candidate - d.team).to_numpy()
    residual = (d.team - d.actual).to_numpy()
    w = d.weight.to_numpy()
    keep = (np.abs(diff) > 0) & (w > 0)
    if not keep.any():
        return 0.0
    cuts = -residual[keep] / diff[keep]
    weights = w[keep] * np.abs(diff[keep])
    order = np.argsort(cuts)
    cuts, weights = cuts[order], weights[order]
    median = cuts[np.searchsorted(np.cumsum(weights), weights.sum()/2, side="left")]
    return float(np.clip(median, 0, 1))


def compare(train, evaluation):
    tr, ev = validate(train), validate(evaluation)
    if tr.ts.max() >= ev.ts.min():
        raise ValueError("training timestamps must strictly precede evaluation")
    alpha = fit_alpha(tr)
    actual = ev.actual.to_numpy()
    ts = ev.ts
    result = {"fit_period": [str(tr.ts.min()), str(tr.ts.max())],
              "evaluation_period": [str(ts.min()), str(ts.max())], "fitted_candidate_fraction": alpha,
              "residual_correlation": float((ev.team-ev.actual).corr(ev.candidate-ev.actual)), "models": {}}
    for name, frac in (("team", 0.), ("candidate", 1.), ("team90_candidate10", .1),
                       ("team80_candidate20", .2), ("team70_candidate30", .3), ("fit_earlier", alpha)):
        p = ev.team.to_numpy() * (1-frac) + ev.candidate.to_numpy() * frac
        penalty = ev.weight * np.abs(p-actual)
        daily = (ts - pd.Timedelta(hours=1)).dt.floor("D")
        result["models"][name] = {"W": float(penalty.sum()),
            "monthly_W": penalty.groupby(daily.dt.strftime("%Y-%m")).sum().to_dict(),
            "daily_penalty_mean": float(penalty.groupby(daily).sum().mean())}
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", required=True)
    a=ap.parse_args()
    read=lambda path: pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    r=compare(read(a.train), read(a.eval))
    with open(a.out,"w",encoding="utf-8") as f:
        json.dump(r,f,indent=2)
    print(f"candidate weight fitted on earlier data: {r['fitted_candidate_fraction']:.4f}")
    for name, score in r["models"].items():
        print(f"{name}: W={score['W']:.2f}")


if __name__ == "__main__":
    main()
