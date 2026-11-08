"""SM62: train one coverage-weighted Group L1 candidate against frozen SM61 A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agg_model as A  # noqa: E402
import scoring as sc  # noqa: E402
import sm61_group_cloud_pilot as S  # noqa: E402

OUT = ROOT / "outputs" / "sm62"
BASELINE_PATH = ROOT / "outputs" / "sm61" / "group_A_predictions.parquet"
SEED = 100
ESS_MIN_RATIO = 0.75
MAX_SEASON_SHARE_SHIFT = 0.15
BOOTSTRAP_MIN_IMPROVEMENT = 0.01


def coverage_weights(frame: pd.DataFrame) -> pd.Series:
    """sqrt(cov), normalized to mean one independently within each group."""
    if not {"group", "cov"}.issubset(frame.columns):
        raise ValueError("training frame must contain group and cov")
    raw = np.sqrt(frame["cov"].clip(lower=0).astype(float))
    means = raw.groupby(frame["group"]).transform("mean")
    if means.isna().any() or (means <= 0).any():
        raise ValueError("coverage weights cannot be normalized for an empty-coverage group")
    return (raw / means).astype(float)


def _season(month: pd.Series) -> pd.Series:
    return month.map(lambda m: "DJF" if m in (12, 1, 2) else "MAM" if m in (3, 4, 5)
                     else "JJA" if m in (6, 7, 8) else "SON")


def support_audit(frame: pd.DataFrame) -> dict:
    """Compute ESS and how normalization changes year/season concentration."""
    d = frame.copy().reset_index(drop=True)
    if "target_day" not in d:
        d["target_day"] = (d["ts"] - pd.Timedelta(hours=1)).dt.floor("D")
    d["sample_weight"] = coverage_weights(d)
    result = {}
    for group, g in d.groupby("group", sort=True):
        w = g["sample_weight"]
        ess = float(w.sum() ** 2 / w.pow(2).sum())
        year = g["target_day"].dt.year.astype(str)
        season = _season(g["target_day"].dt.month)
        raw_year = year.value_counts(normalize=True).sort_index()
        weighted_year = g.assign(_year=year, _w=w).groupby("_year")["_w"].sum() / w.sum()
        raw_season = season.value_counts(normalize=True).sort_index()
        weighted_season = g.assign(_season=season, _w=w).groupby("_season")["_w"].sum() / w.sum()
        result[str(group)] = {
            "n": int(len(g)), "coverage": {"mean": float(g["cov"].mean()),
                "p10": float(g["cov"].quantile(.10)), "median": float(g["cov"].median()),
                "p90": float(g["cov"].quantile(.90))},
            "weight": {"mean": float(w.mean()), "min": float(w.min()),
                "median": float(w.median()), "p90": float(w.quantile(.90)), "max": float(w.max())},
            "ess": ess, "ess_ratio": ess / len(g),
            "year_share_unweighted": raw_year.to_dict(), "year_share_weighted": weighted_year.to_dict(),
            "season_share_unweighted": raw_season.to_dict(), "season_share_weighted": weighted_season.to_dict(),
            "max_abs_season_share_shift": float((weighted_season - raw_season).abs().max()),
        }
    return result


def should_fit(audit: dict) -> tuple[bool, list[str]]:
    reasons = []
    for group, values in audit.items():
        if values["ess_ratio"] < ESS_MIN_RATIO:
            reasons.append(f"{group} ESS ratio {values['ess_ratio']:.3f} < {ESS_MIN_RATIO:.2f}")
        if values["max_abs_season_share_shift"] > MAX_SEASON_SHARE_SHIFT:
            reasons.append(f"{group} season share shift {values['max_abs_season_share_shift']:.3f} > {MAX_SEASON_SHARE_SHIFT:.2f}")
    return not reasons, reasons


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run() -> dict:
    sites, comp, gw, wd, _, _, _, common_ts = S.load_inputs()
    pa, pb, train_a, _, _, _, train_targets = S.target_windows(sites, comp, common_ts)
    train = A.design(train_targets, gw, wd, sites, comp)
    train = train[train.elev > -2].copy().reset_index(drop=True)
    audit = support_audit(train)
    features = A.feats_of(train)
    train["sample_weight"] = coverage_weights(train)
    go, reasons = should_fit(audit)
    OUT.mkdir(parents=True, exist_ok=True)
    preflight = {"rows": int(len(train)), "groups": audit, "go": go,
                 "stop_reasons": reasons, "ess_min_ratio": ESS_MIN_RATIO,
                 "max_season_share_shift": MAX_SEASON_SHARE_SHIFT,
                 "weight_formula": "sqrt(cov), normalized to mean 1 within group"}
    (OUT / "weight_audit.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
    if not go:
        return {"status": "STOP_BEFORE_FIT", **preflight}

    baseline = pd.read_parquet(BASELINE_PATH)
    if baseline[["group", "ts"]].duplicated().any():
        raise ValueError("frozen SM61 baseline has duplicate group-ts keys")
    y = train.cf.clip(0, 1.2).astype("float32")
    weights = train["sample_weight"].to_numpy(dtype=np.float64)
    model = lgb.LGBMRegressor(**{**A.PARAMS, "objective": "regression_l1", "random_state": SEED})
    model.fit(train[features], y, sample_weight=weights)

    eval_gen = A.load_gen(pa, pb)
    actual = A.targets(eval_gen, sites, comp, min_cov=0.0)
    actual = actual[actual.ts.isin(common_ts)].copy()
    eval_ts = pd.DatetimeIndex(actual.ts.unique()).sort_values()
    pred_idx = pd.MultiIndex.from_product([list(sc.GROUPS), eval_ts], names=["group", "ts"]).to_frame(index=False)
    dpr = A.design(pred_idx, gw, wd, sites, comp)
    cf_hat = model.predict(dpr[features])
    cf_hat = np.where(dpr.elev.to_numpy() > -2, np.clip(cf_hat, 0, None), 0.0)
    candidate = pred_idx[["group", "ts"]].copy()
    candidate["cf_hat"] = cf_hat
    candidate_path = OUT / "group_B_weighted_predictions.parquet"
    candidate.to_parquet(candidate_path, index=False)

    smp = sc.load_smp()
    baseline_m = S.hourly_observed_capacity_w(baseline, actual, smp)
    candidate_m = S.hourly_observed_capacity_w(candidate, actual, smp)
    if not baseline_m[["group", "ts", "act", "cap_avail", "cov"]].equals(
            candidate_m[["group", "ts", "act", "cap_avail", "cov"]]):
        raise RuntimeError("baseline/candidate evaluation masks differ")
    pred_a = baseline_m[["group", "ts", "pred_observed_capacity"]].rename(columns={"pred_observed_capacity": "pred"})
    pred_b = candidate_m[["group", "ts", "pred_observed_capacity"]].rename(columns={"pred_observed_capacity": "pred"})
    w_a = A.group_score(pred_a, actual, smp)
    w_b = A.group_score(pred_b, actual, smp)
    if not np.isclose(w_a, baseline_m.w.sum(), atol=1e-6, rtol=0) or not np.isclose(w_b, candidate_m.w.sum(), atol=1e-6, rtol=0):
        raise AssertionError("official Group score cross-check mismatch")
    delta = float(w_b - w_a)
    improvement = -delta / w_a

    monthly = {}
    for month in sorted(set(baseline_m.month) | set(candidate_m.month)):
        a = float(baseline_m.loc[baseline_m.month == month, "w"].sum())
        b = float(candidate_m.loc[candidate_m.month == month, "w"].sum())
        monthly[str(month)] = {"A": a, "B": b, "delta": b - a}
    group_w = {g: {"A": float(baseline_m.loc[baseline_m.group == g, "w"].sum()),
                   "B": float(candidate_m.loc[candidate_m.group == g, "w"].sum())} for g in sc.GROUPS}
    group_bias = {g: {"A": float(baseline_m.loc[baseline_m.group == g, "signed_error"].mean()),
                      "B": float(candidate_m.loc[candidate_m.group == g, "signed_error"].mean())} for g in sc.GROUPS}
    peak_a = float(baseline_m.loc[baseline_m.peak, "w"].sum())
    peak_b = float(candidate_m.loc[candidate_m.peak, "w"].sum())
    bootstrap = None
    bootstrap_reason = ""
    # Bootstrap is reserved for a >=1% total gain with no group-level W increase.
    if improvement >= BOOTSTRAP_MIN_IMPROVEMENT and all(group_w[g]["B"] <= group_w[g]["A"] for g in sc.GROUPS):
        from analysis.sm58_controlled_pilot import bootstrap_delta
        bootstrap = bootstrap_delta(baseline_m[["group", "ts", "w"]], candidate_m[["group", "ts", "w"]],
                                    seed=7, block=168, n_boot=5000)
    else:
        bootstrap_reason = "not run: improvement below 1% or at least one group W increased"
    importance = pd.DataFrame({"feature": features, "gain": model.booster_.feature_importance("gain"),
                               "split": model.booster_.feature_importance("split")})
    importance = importance.sort_values("gain", ascending=False).head(15).to_dict("records")
    result = {
        "status": "COMPLETED", "periods": {"train_start": str(train_a), "train_end_exclusive": str(pa),
            "validation_start": str(pa), "validation_end_inclusive": str(pb)},
        "model": {"objective": "regression_l1", "seed": SEED, "params": A.PARAMS,
                  "features": len(features), "sample_weight_only_change": True,
                  "coverage_weight": "sqrt(cap_avail/full_group_capacity), normalized group mean=1"},
        "training_rows_after_daylight": int(len(train)), "training_weight_support": audit,
        "evaluation_timestamps": int(len(eval_ts)), "evaluation_group_hours": int(len(actual)),
        "scale": "observed-capacity diagnostic; post-hoc cap_avail used only to scale predictions for scoring",
        "W": {"A": float(w_a), "B": float(w_b), "delta_B_minus_A": delta,
              "relative_improvement": improvement},
        "group_W": group_w, "peak_W": {"A": peak_a, "B": peak_b, "delta": peak_b - peak_a},
        "monthly_W": monthly, "group_mean_signed_bias_kwh": group_bias,
        "bootstrap_168h_5000": bootstrap, "bootstrap_decision": bootstrap_reason,
        "candidate_gain_importance_top15": importance,
        "baseline_prediction_sha256": sha256(BASELINE_PATH),
        "candidate_prediction_sha256": sha256(candidate_path),
        "lightgbm_version": lgb.__version__,
    }
    (OUT / "pilot_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
