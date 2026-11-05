"""Scenario calculator, not a leaderboard predictor or confidence interval.

The local scores must use the same time window and observed site-hours.
The evaluation baseline score is itself an assumption from team records.
"""
from __future__ import annotations

import argparse
import json
import math

BASE_SCORE = 6_418_396_513
TEAM_BEST = 6_459_800_168
FACTORS = (0.86, 0.98, 1.0)


def scenarios(local_baseline, local_candidate, base_score=BASE_SCORE, team_best=TEAM_BEST):
    values = (local_baseline, local_candidate, base_score, team_best)
    if not all(math.isfinite(x) for x in values) or local_baseline <= 0 or local_candidate < 0:
        raise ValueError("finite scores and positive baseline/nonnegative candidate W required")
    gain = local_baseline - local_candidate
    out = {"local_reduction": gain, "local_reduction_fraction": gain / local_baseline,
           "assumed_baseline_score": base_score, "actual_team_best": team_best, "scenarios": []}
    for factor in FACTORS:
        estimated = base_score + factor * gain
        out["scenarios"].append({"assumed_transfer_ratio": factor, "scenario_score": estimated,
                                  "scenario_minus_actual_best": estimated - team_best})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-w", type=float, required=True)
    ap.add_argument("--candidate-w", type=float, required=True)
    ap.add_argument("--baseline-score", type=float, default=BASE_SCORE)
    ap.add_argument("--team-best", type=float, default=TEAM_BEST)
    a = ap.parse_args()
    print(json.dumps(scenarios(a.baseline_w, a.candidate_w, a.baseline_score, a.team_best), indent=2))
    print("Scenario only: transfer ratios are assumptions, not intervals or predicted leaderboard scores.")


if __name__ == "__main__":
    main()
