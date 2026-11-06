"""SM#39: train outputs are produced by agg_model.py; this module integrates and scores them."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc
import agg_model as am

ALPHAS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
EPS = 1e-8


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate_rows(df: pd.DataFrame, keys: list[str], value: str, label: str) -> pd.DataFrame:
    out = df[keys + [value]].copy()
    out["ts"] = sc.to_ts(out.ts)
    if out.duplicated(keys).any():
        raise ValueError(f"{label}: duplicate prediction key")
    vals = out[value].to_numpy(dtype=float)
    if not np.isfinite(vals).all() or (vals < 0).any():
        raise ValueError(f"{label}: predictions must be finite and nonnegative")
    return out


def redistribute(site_pred: pd.DataFrame, group_pred: pd.DataFrame, sites: pd.DataFrame,
                 comp: pd.Series, alpha: float, expected_ts: pd.DatetimeIndex) -> pd.DataFrame:
    """Allocate fixed-capacity group forecast to all sites without evaluation outcomes/cap_avail."""
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be in [0, 1]")
    p = validate_rows(site_pred, ["site_id", "ts"], "kwh", "site")
    gp = validate_rows(group_pred, ["group", "ts"], "pred", "group")
    site_ids = sites.site_id.tolist()
    expected = pd.MultiIndex.from_product([site_ids, expected_ts], names=["site_id", "ts"])
    got = pd.MultiIndex.from_frame(p[["site_id", "ts"]])
    if len(got) != len(expected) or not got.is_unique or len(expected.difference(got)):
        raise ValueError("site prediction does not cover the complete site × time grid")
    groups = sorted(set(comp.unique()))
    exp_gp = pd.MultiIndex.from_product([groups, expected_ts], names=["group", "ts"])
    got_gp = pd.MultiIndex.from_frame(gp[["group", "ts"]])
    if len(got_gp) != len(exp_gp) or not got_gp.is_unique or len(exp_gp.difference(got_gp)):
        raise ValueError("group prediction does not cover the complete group × time grid")

    s = p.assign(group=p.site_id.map(comp)).merge(
        sites[["site_id", "capacity_kw"]], on="site_id", validate="many_to_one")
    b = s.groupby(["group", "ts"], as_index=False).kwh.sum().rename(columns={"kwh": "B"})
    g = gp.rename(columns={"pred": "T"})
    g = g.merge(b, on=["group", "ts"], validate="one_to_one")
    total_cap = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    s = s.merge(g[["group", "ts", "B", "T"]], on=["group", "ts"], validate="many_to_one")
    g["F"] = (1 - alpha) * g["B"] + alpha * g["T"]
    s = s.merge(g[["group", "ts", "F"]], on=["group", "ts"], validate="many_to_one")
    nonzero = s["B"] > EPS
    s["kwh_new"] = np.where(
        nonzero,
        s.kwh * ((1 - alpha) + alpha * s["T"] / s["B"]),
        (1 - alpha) * s.kwh + alpha * s["T"] * s.capacity_kw / s.group.map(total_cap),
    )
    # Check the allocation conserves the prescribed combined group forecast.
    allocated = s.groupby(["group", "ts"]).kwh_new.sum().sort_index()
    target = g.set_index(["group", "ts"]).F.sort_index()
    if not np.allclose(allocated.to_numpy(), target.to_numpy(), rtol=1e-9, atol=1e-6):
        raise AssertionError("site allocation does not conserve combined group forecast")
    out = s[["site_id", "ts", "kwh_new"]].rename(columns={"kwh_new": "kwh"})
    if not np.isfinite(out.kwh.to_numpy()).all() or (out.kwh < 0).any():
        raise ValueError("redistributed predictions are invalid")
    return out


def hourly_penalties(pred: pd.DataFrame, actual: pd.DataFrame, comp: pd.Series,
                     smp: pd.Series) -> pd.DataFrame:
    p = validate_rows(pred, ["site_id", "ts"], "kwh", "scoring")
    a = actual[["site_id", "ts", "energy"]].copy()
    a["ts"] = sc.to_ts(a.ts)
    if a.duplicated(["site_id", "ts"]).any():
        raise ValueError("duplicate actual key")
    m = a.merge(p, on=["site_id", "ts"], how="left", validate="one_to_one")
    if m.kwh.isna().any():
        raise ValueError("missing prediction on observed actual rows")
    m["group"] = m.site_id.map(comp)
    g = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), pred=("kwh", "sum"))
    g["smp"] = g.ts.map(smp)
    if g.smp.isna().any() or not np.isfinite(g.smp.to_numpy()).all() or (g.smp < 0).any():
        raise ValueError("missing or invalid SMP")
    g["k"] = sc.k_weight(g.ts)
    g["pen"] = sc.PENALTY_RATE * g.smp * g.k * (g.pred - g.act).abs()
    return g


def block_bootstrap(delta: np.ndarray, block: int = 168, n_boot: int = 5000,
                    seed: int = 7) -> dict:
    if len(delta) < block or not np.isfinite(delta).all():
        raise ValueError("insufficient/invalid hourly paired differences for bootstrap")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(len(delta) / block))
    max_start = len(delta) - block
    vals = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        vals[i] = np.concatenate([delta[s:s + block] for s in starts])[:len(delta)].sum()
    return {"repetitions": n_boot, "seed": seed, "block_hours": block,
            "mean": float(vals.mean()), "median": float(np.median(vals)),
            "ci95": [float(x) for x in np.quantile(vals, [0.025, 0.975])],
            "includes_zero": bool(np.quantile(vals, .025) <= 0 <= np.quantile(vals, .975))}


def score_window(pred: pd.DataFrame, start: str, end: str, comp: pd.Series,
                 actual: pd.DataFrame, smp: pd.Series) -> float:
    a, b = sc.window(start, end)
    act = actual[(sc.to_ts(actual.ts) >= a) & (sc.to_ts(actual.ts) <= b)]
    r = sc.score(pred, comp, act, smp)
    return float(r["W"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="outputs/sm39")
    ap.add_argument("--sites-2023", default="outputs/val_sm37_noext_repro_2023_sites.parquet")
    ap.add_argument("--sites-2024", default="outputs/val_sm37_noext_repro_sites.parquet")
    a = ap.parse_args()
    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    if sc.check_composition(comp, sites):
        raise ValueError("invalid reference composition: " + "; ".join(sc.check_composition(comp, sites)))
    smp = sc.load_smp()
    monthly_path = outdir / "_monthly_tmp.csv"
    if monthly_path.exists():
        monthly_path.unlink()
    inputs = []
    all_rows = []
    diagnostics = {"experiment": "SM#39", "source": "competition-provided forecast_wa/forecast_wb only",
                   "composition": "reference/current_group fixed", "alpha_candidates": list(ALPHAS), "years": {}}
    chosen_alpha = None
    for year, start, end, site_path, gp_path in (
        (2023, "2023-06-01", "2024-06-01", Path(a.sites_2023), outdir / "group_pred_2023.parquet"),
        (2024, "2024-06-01", "2025-06-01", Path(a.sites_2024), outdir / "group_pred_2024.parquet"),
    ):
        if not gp_path.exists():
            raise FileNotFoundError(f"missing trained group predictions: {gp_path}")
        site_pred = pd.read_parquet(site_path)
        site_pred = validate_rows(site_pred, ["site_id", "ts"], "kwh", f"site {year}")
        gp = pd.read_parquet(gp_path)
        gp["ts"] = sc.to_ts(gp.ts)
        if {"group", "ts", "cf_hat", "pred"} - set(gp.columns):
            raise ValueError(f"group output columns incomplete: {gp.columns.tolist()}")
        pa, pb = sc.window(start, end)
        times = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
        if len(times) != (8784 if year == 2023 else 8760):
            raise AssertionError("unexpected evaluation hour count")
        actual = sc.load_actual(start, end)
        act_t = am.targets(actual, sites, comp, min_cov=0.0)
        ref_detail = hourly_penalties(site_pred, actual, comp, smp)
        ref_w = float(ref_detail.pen.sum())
        api_ref = sc.score(site_pred, comp, actual, smp)["W"]
        if not np.isclose(ref_w, api_ref, atol=1e-6):
            raise AssertionError("independent hourly W differs from scoring.score")
        if year == 2023 and chosen_alpha is None:
            pass
        year_alphas = ALPHAS
        score_by_alpha = {}
        for alpha in year_alphas:
            cp = redistribute(site_pred, gp, sites, comp, alpha, times)
            detail = hourly_penalties(cp, actual, comp, smp)
            w = float(detail.pen.sum())
            # Cross-check against the official scoring implementation.
            if not np.isclose(w, sc.score(cp, comp, actual, smp)["W"], atol=1e-6):
                raise AssertionError(f"scoring mismatch ({year}, alpha={alpha})")
            score_by_alpha[alpha] = (w, cp, detail)
            all_rows.append({"year": year, "alpha": alpha, "W": w, "reference_W": ref_w,
                             "delta_W": w - ref_w, "change_pct": 100 * (w / ref_w - 1)})
        if year == 2023:
            chosen_alpha = min(ALPHAS, key=lambda x: (score_by_alpha[x][0], x))
        selected = chosen_alpha if year == 2024 else chosen_alpha
        sel_w, sel_pred, sel_detail = score_by_alpha[selected]
        ref_1115 = float(ref_detail.loc[ref_detail.ts.dt.hour.between(11, 15), "pen"].sum())
        selected_1115 = float(sel_detail.loc[sel_detail.ts.dt.hour.between(11, 15), "pen"].sum())
        gp_fixed_w = am.group_score(gp[["group", "ts", "pred"]], act_t, smp)
        gp_observed = gp[["group", "ts", "cf_hat"]].merge(
            act_t[["group", "ts", "cap_avail"]], on=["group", "ts"], how="inner", validate="one_to_one")
        gp_observed["pred"] = gp_observed.cf_hat * gp_observed.cap_avail
        gp_observed_w = am.group_score(gp_observed[["group", "ts", "pred"]], act_t, smp)
        per_month = sel_detail.assign(month=sel_detail.ts.dt.strftime("%Y-%m")).groupby("month").pen.sum()
        ref_month = ref_detail.assign(month=ref_detail.ts.dt.strftime("%Y-%m")).groupby("month").pen.sum()
        monthly = pd.DataFrame({"month": per_month.index, "selected_W": per_month.values,
                                "reference_W": ref_month.reindex(per_month.index).values})
        monthly["delta_W"] = monthly.selected_W - monthly.reference_W
        monthly["change_pct"] = 100 * monthly.delta_W / monthly.reference_W
        monthly["year"] = year
        # Store both years' monthly rows in one output, append after loop below.
        diagnostics["years"][str(year)] = {
            "evaluation_start_inclusive": str(pa), "evaluation_end_inclusive": str(pb),
            "hours": len(times), "observed_site_hours": int(len(actual)),
            "group_prediction_rows": int(len(gp)), "expected_group_prediction_rows": 2 * len(times),
            "group_prediction_missing_hours": int(gp.pred.isna().sum()),
            "reference_W": ref_w, "W_by_alpha": {str(k): v[0] for k, v in score_by_alpha.items()},
            "selected_alpha_from_2023_only": chosen_alpha, "selected_W": sel_w,
            "selected_delta_W": sel_w - ref_w, "selected_change_pct": 100 * (sel_w / ref_w - 1),
            "selected_per_group_W": {str(k): float(v) for k, v in sel_detail.groupby("group").pen.sum().items()},
            "reference_per_group_W": {str(k): float(v) for k, v in ref_detail.groupby("group").pen.sum().items()},
            "selected_11_15_W": selected_1115, "reference_11_15_W": ref_1115,
            "fixed_capacity_direct_group_W_on_observed_rows": float(gp_fixed_w),
            "posthoc_observed_capacity_direct_group_W_diagnostic_only": float(gp_observed_w),
            "selected_monthly": monthly.drop(columns="year").to_dict(orient="records"),
            "reference_monthly": ref_month.to_dict(),
            "selected_daily_delta_distribution": {},
        }
        daily = sel_detail.groupby(sel_detail.ts.dt.floor("D")).pen.sum() - ref_detail.groupby(ref_detail.ts.dt.floor("D")).pen.sum()
        diagnostics["years"][str(year)]["selected_daily_delta_distribution"] = {
            "improved_days": int((daily < 0).sum()), "worse_days": int((daily > 0).sum()),
            "equal_days": int((daily == 0).sum()), "mean_delta": float(daily.mean()),
            "median_delta": float(daily.median())}
        monthly.to_csv(monthly_path, index=False, mode="a", header=not monthly_path.exists())
        total_caps = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
        diagnostics["years"][str(year)]["reference_group_capacity_kw"] = {str(k): float(v) for k, v in total_caps.items()}
        # Training label coverage uses only pre-evaluation generation and is reported separately from prediction.
        gen_train = am.load_gen(pa - pd.DateOffset(years=2), pa - pd.Timedelta(hours=1))
        t_train = am.targets(gen_train, sites, comp, min_cov=0.3)
        cov = t_train.groupby("group").cap_avail.mean() / total_caps
        diagnostics["years"][str(year)]["training_observed_capacity_coverage_mean"] = {str(k): float(v) for k, v in cov.items()}
        diagnostics["years"][str(year)]["training_target_rows"] = int(len(t_train))
        diagnostics["years"][str(year)]["training_target_rows_by_group"] = {
            str(k): int(v) for k, v in t_train.groupby("group").size().items()}
        inputs.append({"year": year, "site_prediction": str(site_path), "site_prediction_sha256": sha256(site_path),
                       "group_prediction": str(gp_path), "group_prediction_sha256": sha256(gp_path)})
    monthly_path = outdir / "_monthly_tmp.csv"
    if monthly_path.exists():
        pd.read_csv(monthly_path).to_csv(outdir / "monthly_selected_alpha.csv", index=False)
        monthly_path.unlink()
    alpha_df = pd.DataFrame(all_rows)
    alpha_df["selected_alpha"] = alpha_df.alpha.eq(chosen_alpha)
    alpha_df.to_csv(outdir / "alpha_comparison.csv", index=False)
    diagnostics["selected_alpha"] = chosen_alpha
    diagnostics["inputs"] = inputs
    diagnostics["forecast_round_cutoff_audit"] = {
        "selected_policy": "round=17 preferred, round=10 fallback via features.prep_forecast",
        "cutoff_evidence": "participant dataset README defines round 10/17 as target-day previous-day issue; both are before D-1 17:00 KST cutoff",
        "actual_round_17_missing_fallback_is_per_feature_nan_fill": True,
        "publication_timestamp_limit": "forecast files contain round and valid ts, not explicit publication timestamps; audit relies on provided round definition",
    }
    diagnostics["posthoc_observed_capacity"] = {
        "used_for_prediction_or_redistribution": False,
        "used_for_training_cf_target": True,
        "meaning": "training target cf=observed generation / observed capacity; prediction multiplies cf_hat by fixed reference group capacity, so target denominator differs from inference denominator",
    }
    # Bootstrap only if the locked future alpha improves against reference.
    y24 = diagnostics["years"]["2024"]
    if y24["selected_delta_W"] < 0:
        start, end = "2024-06-01", "2025-06-01"
        actual = sc.load_actual(start, end)
        site_pred = pd.read_parquet(a.sites_2024)
        gp = pd.read_parquet(outdir / "group_pred_2024.parquet")
        times = pd.date_range(*sc.window(start, end), freq="h").astype(f"datetime64[ns, {sc.TZ}]")
        ref = hourly_penalties(site_pred, actual, comp, smp).groupby("ts").pen.sum()
        cp = redistribute(site_pred, gp, sites, comp, chosen_alpha, times)
        cand = hourly_penalties(cp, actual, comp, smp).groupby("ts").pen.sum()
        delta = cand.reindex(times, fill_value=0).to_numpy() - ref.reindex(times, fill_value=0).to_numpy()
        diagnostics["future_7day_bootstrap"] = block_bootstrap(delta)
    else:
        diagnostics["future_7day_bootstrap"] = {"performed": False, "reason": "locked alpha did not improve future W"}
    (outdir / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"selected_alpha": chosen_alpha, "years": diagnostics["years"],
                      "bootstrap": diagnostics["future_7day_bootstrap"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
