"""Prediction-level complementarity audit for frozen JH ens_v12 and SM46 A1-REF.

Reads only saved validation forecasts and competition-provided generation/SMP.
Does not train, tune, rewrite submissions, or write source forecasts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


ROOT = Path(sc.ROOT)
OUT = ROOT / "outputs" / "sm56"
ALPHAS = (0.0, 0.05, 0.10, 0.20)
SEED = 56
N_BOOT = 5000
BLOCK_HOURS = 168
PERIODS = {
    "2023-24": ("2023-06-01", "2024-06-01", "2023"),
    "2024-25": ("2024-06-01", "2025-06-01", "2024"),
}
JH_REPORTED_W = {"2023-24": 93_377_951.0, "2024-25": 167_041_881.0}
SM_REPORTED_W = {"2023-24": 106_673_757.0, "2024-25": 197_526_260.0}


def mix_prediction(jh: pd.Series, sm: pd.Series, alpha: float) -> pd.Series:
    """Apply a preregistered fixed group-level weight after key alignment."""
    if alpha not in ALPHAS:
        raise ValueError(f"alpha must be one of the frozen values: {ALPHAS}")
    if not jh.index.equals(sm.index):
        raise ValueError("JH and SM predictions must share the same ordered keys")
    return (1.0 - alpha) * jh + alpha * sm


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    comp_path = OUT / "composition_ens_v12.csv"
    sm_comp_path = OUT / "composition_sm46_a1_ref.csv"
    if not sm_comp_path.exists():
        sm_comp_path.write_bytes((ROOT / "outputs/sm46/composition_sm46_a1_ref.csv").read_bytes())
    jh_comp = pd.read_csv(comp_path).sort_values("site_id").reset_index(drop=True)
    sm_comp = pd.read_csv(sm_comp_path).sort_values("site_id").reset_index(drop=True)
    if not jh_comp.equals(sm_comp):
        raise ValueError("JH ens_v12 and SM46 compositions differ")
    comp = pd.Series(jh_comp.group.to_numpy(), index=jh_comp.site_id)

    sites = sc.load_sites()
    actual_all = sc.load_actual("2023-06-01", "2025-06-01")
    actual_all["group"] = actual_all.site_id.map(comp)
    actual_group = (actual_all.groupby(["group", "ts"], as_index=False)
                    .agg(actual_kwh=("energy", "sum"), observed_sites=("site_id", "nunique")))
    smp = sc.load_smp()
    all_rows: list[pd.DataFrame] = []
    manifest: dict[str, object] = {
        "experiment": "SM56 ens_v12 prediction-level complementarity",
        "reference_main": "793f5f6662f074dbc8e50d3b0f925b9b214c3683",
        "sm_base": "87b9748271ba89d6d49333884ce5342deb79b8ef",
        "alpha": list(ALPHAS),
        "bootstrap": {"replicates": N_BOOT, "block_hours": BLOCK_HOURS, "seed": SEED},
        "composition_sha256": {
            "jh": sha256(comp_path),
            "sm": sha256(ROOT / "outputs/sm46/composition_sm46_a1_ref.csv"),
        },
        "periods": {},
    }

    for period, (start, end, year) in PERIODS.items():
        jh_path = OUT / f"forecast_ens_v12_val_{period}.csv"
        jh = pd.read_csv(jh_path)
        jh["ts"] = sc.to_ts(jh.ts)
        jh = jh[["group", "ts", "forecast_kwh", "site_model_kwh", "group_model_kwh"]].copy()
        if jh.duplicated(["group", "ts"]).any():
            raise ValueError(f"Duplicate JH group-hour keys: {period}")
        jh = jh.rename(columns={"forecast_kwh": "jh_kwh"})

        sm_sites_path = ROOT / f"outputs/sm45/{year}_A1_B1_site_group_20_sites.parquet"
        sm_sites = pd.read_parquet(sm_sites_path)
        sm_sites["ts"] = sc.to_ts(sm_sites.ts)
        sm_sites["group"] = sm_sites.site_id.map(comp)
        sm_group = (sm_sites.groupby(["group", "ts"], as_index=False).kwh.sum()
                    .rename(columns={"kwh": "sm_kwh"}))

        begin, finish = sc.window(start, end)
        ts_grid = pd.date_range(begin, finish, freq="h", tz=sc.TZ)
        expected = pd.MultiIndex.from_product([sc.GROUPS, ts_grid], names=["group", "ts"])
        pred_keys = pd.MultiIndex.from_frame(jh[["group", "ts"]])
        if len(jh) != len(expected) or not pred_keys.equals(expected):
            # CSV order should be group then time; test key set independently if ordering differs.
            if set(pred_keys) != set(expected) or pred_keys.has_duplicates:
                raise ValueError(f"JH group-time grid incomplete or duplicated: {period}")
        sm_keys = pd.MultiIndex.from_frame(sm_group[["group", "ts"]])
        if len(sm_group) != len(expected) or set(sm_keys) != set(expected) or sm_keys.has_duplicates:
            raise ValueError(f"SM full-group forecast grid incomplete or duplicated: {period}")

        ag = actual_group[(actual_group.ts >= begin) & (actual_group.ts <= finish)].copy()
        grid = (jh.merge(sm_group, on=["group", "ts"], how="outer", validate="one_to_one")
                .merge(ag, on=["group", "ts"], how="left", validate="one_to_one"))
        grid["actual_kwh"] = grid.actual_kwh.fillna(0.0)
        grid["observed_sites"] = grid.observed_sites.fillna(0).astype(int)
        grid["smp"] = grid.ts.map(smp)
        if grid.smp.isna().any():
            raise ValueError(f"Missing SMP values: {period}")
        grid["k"] = sc.k_weight(grid.ts)
        grid["w"] = sc.PENALTY_RATE * grid.smp * grid.k
        for alpha in ALPHAS:
            grid[f"pred_{alpha:.2f}"] = mix_prediction(grid.jh_kwh, grid.sm_kwh, alpha)
            grid[f"resid_{alpha:.2f}"] = grid[f"pred_{alpha:.2f}"] - grid.actual_kwh
            grid[f"pen_{alpha:.2f}"] = grid.w * grid[f"resid_{alpha:.2f}"].abs()
        score_grid = grid.loc[grid.observed_sites.gt(0)].copy()
        all_rows.append(score_grid.assign(period=period))

        # Check public component arithmetic; CSV rounds to milli-kWh.
        component_error = float(np.max(np.abs(jh.jh_kwh - (0.505 * jh.site_model_kwh + 0.495 * jh.group_model_kwh))))
        nsites = comp.groupby(comp).size().to_dict()
        manifest["periods"][period] = {
            "jh_sha256": sha256(jh_path),
            "sm_site_blend_sha256": sha256(sm_sites_path),
            "jh_rows": len(jh),
            "jh_groups": jh.group.value_counts().to_dict(),
            "unique_timestamps": int(jh.ts.nunique()),
            "min_ts": str(jh.ts.min()),
            "max_ts": str(jh.ts.max()),
            "component_formula_max_abs_error_kwh": component_error,
            "sm_full_group_rows": len(sm_group),
            "actual_observed_site_hours": int(len(actual_all[(actual_all.ts >= begin) & (actual_all.ts <= finish)])),
            "scored_group_hours_with_any_observation": int(len(score_grid)),
            "group_hour_mean_observed_sites": grid.groupby("group").observed_sites.mean().to_dict(),
            "group_hour_mean_site_fraction": {
                g: float(grid.loc[grid.group.eq(g), "observed_sites"].mean() / nsites[g])
                for g in sc.GROUPS
            },
        }
        # Number of all-member-observed group-hours, for the missing-target audit.
        manifest["periods"][period]["group_hour_fully_observed"] = {
            g: int((grid.loc[grid.group.eq(g), "observed_sites"] == nsites[g]).sum()) for g in sc.GROUPS
        }
        period_actual = actual_all.loc[(actual_all.ts >= begin) & (actual_all.ts <= finish), ["site_id", "ts", "energy"]]
        sm_local = sc.score(sm_sites[["site_id", "ts", "kwh"]], comp, period_actual, smp)
        sm_detail = period_actual.merge(sm_sites[["site_id", "ts", "kwh"]], on=["site_id", "ts"], how="left", validate="one_to_one")
        sm_detail["group"] = sm_detail.site_id.map(comp)
        sm_hour = sm_detail.groupby(["group", "ts"], as_index=False).agg(actual=("energy", "sum"), pred=("kwh", "sum"))
        sm_hour["weight"] = sc.PENALTY_RATE * sm_hour.ts.map(smp) * sc.k_weight(sm_hour.ts)
        independent_sm_w = float((sm_hour.weight * (sm_hour.pred - sm_hour.actual).abs()).sum())
        if not np.isclose(sm_local["W"], independent_sm_w, rtol=0, atol=1e-7):
            raise AssertionError(f"src/scoring.py and independent SM W differ: {sm_local['W']} vs {independent_sm_w}")
        manifest["periods"][period]["sm_official_local_score_w"] = float(sm_local["W"])
        manifest["periods"][period]["sm_independent_hourly_w"] = independent_sm_w
        manifest["periods"][period]["scoring_crosscheck_delta"] = float(independent_sm_w - sm_local["W"])
        manifest["periods"][period]["sm_reported_w"] = SM_REPORTED_W[period]
        manifest["periods"][period]["sm_reported_vs_recomputed_delta"] = float(sm_local["W"] - SM_REPORTED_W[period])
        manifest["periods"][period]["jh_reported_w"] = JH_REPORTED_W[period]

    d = pd.concat(all_rows, ignore_index=True)
    results: dict[str, object] = {"periods": {}, "interpretation": "common full-group predictions vs the same group sums of available generation; incomplete labels are not complete-group official outcomes"}
    for period, x in d.groupby("period", sort=False):
        year = results["periods"].setdefault(period, {})
        overall = {}
        for alpha in ALPHAS:
            pcol = f"pen_{alpha:.2f}"
            rcol = f"resid_{alpha:.2f}"
            overall[str(alpha)] = {
                "common_mask_group_penalty": float(x[pcol].sum()),
                "g1": float(x.loc[x.group.eq("G1"), pcol].sum()),
                "g2": float(x.loc[x.group.eq("G2"), pcol].sum()),
                "peak_11_15": float(x.loc[x.k.eq(3), pcol].sum()),
                "nonpeak": float(x.loc[x.k.eq(1), pcol].sum()),
                "signed_residual_mean_kwh": float(x[rcol].mean()),
            }
        year["alpha_scores"] = overall
        base_r = x["resid_0.00"]
        sm_r = x["sm_kwh"] - x.actual_kwh
        year["residual_structure"] = {
            "jh_sm_residual_correlation": float(base_r.corr(sm_r)),
            "opposite_sign_fraction_nonzero_pairs": float(((base_r * sm_r < 0).sum()) / ((base_r.ne(0) & sm_r.ne(0)).sum())),
            "forecast_difference_abs_median_kwh": float((x.sm_kwh - x.jh_kwh).abs().median()),
            "forecast_difference_abs_p90_kwh": float((x.sm_kwh - x.jh_kwh).abs().quantile(0.90)),
            "forecast_difference_abs_max_kwh": float((x.sm_kwh - x.jh_kwh).abs().max()),
        }
        year["residual_structure_by_group"] = {}
        for g in sc.GROUPS:
            gx = x.loc[x.group.eq(g)]
            gr_jh = gx["resid_0.00"]
            gr_sm = gx["sm_kwh"] - gx.actual_kwh
            nonzero = gr_jh.ne(0) & gr_sm.ne(0)
            year["residual_structure_by_group"][g] = {
                "jh_sm_residual_correlation": float(gr_jh.corr(gr_sm)),
                "opposite_sign_fraction_nonzero_pairs": float((gr_jh[nonzero] * gr_sm[nonzero] < 0).mean()),
                "group_hours": int(len(gx)),
            }
        year["directional_loss"] = {}
        for alpha in ALPHAS:
            rcol = f"resid_{alpha:.2f}"
            pcol = f"pen_{alpha:.2f}"
            year["directional_loss"][str(alpha)] = {
                "overprediction_w": float(x.loc[x[rcol] > 0, pcol].sum()),
                "underprediction_w": float(x.loc[x[rcol] < 0, pcol].sum()),
            }
        year["bootstrap"] = {}
        # Bootstrap expects one row per group-hour and a penalty column for each model.
        for alpha in ALPHAS[1:]:
            # Sum paired G1/G2 contributions into hourly paired loss deltas.
            start, end, _ = PERIODS[period]
            begin, finish = sc.window(start, end)
            ts_order = pd.date_range(begin, finish, freq="h", tz=sc.TZ)
            by_t = x.assign(delta=x[f"pen_{alpha:.2f}"] - x["pen_0.00"]).groupby("ts", sort=True).delta.sum().reindex(ts_order).to_numpy()
            hourly = pd.DataFrame({"ts": ts_order, "pen": by_t})
            rng = np.random.default_rng(SEED)
            n = len(hourly); nblocks = int(np.ceil(n / BLOCK_HOURS)); boot = np.empty(N_BOOT)
            for b in range(N_BOOT):
                starts = rng.choice(n, size=nblocks, replace=True)
                idx = np.concatenate([(s + np.arange(BLOCK_HOURS)) % n for s in starts])[:n]
                boot[b] = by_t[idx].sum()
            year["bootstrap"][str(alpha)] = {
                "delta_candidate_minus_jh_krw": float(by_t.sum()),
                "ci95_low": float(np.quantile(boot, .025)),
                "ci95_high": float(np.quantile(boot, .975)),
                "replicates": N_BOOT, "block_hours": BLOCK_HOURS, "seed": SEED,
            }
        tmp = x.copy()
        # The right-closed 00:00 row belongs to the previous target day/month.
        target_ts = tmp.ts.where(tmp.ts.dt.hour.ne(0), tmp.ts - pd.Timedelta(days=1))
        tmp["month"] = target_ts.dt.strftime("%Y-%m")
        tmp["delta_alpha_0.05"] = tmp["pen_0.05"] - tmp["pen_0.00"]
        tmp["delta_alpha_0.10"] = tmp["pen_0.10"] - tmp["pen_0.00"]
        tmp["delta_alpha_0.20"] = tmp["pen_0.20"] - tmp["pen_0.00"]
        monthly = tmp.groupby(["month", "group"])[["pen_0.00", "pen_0.05", "pen_0.10", "pen_0.20", "delta_alpha_0.05", "delta_alpha_0.10", "delta_alpha_0.20"]].sum().reset_index()
        monthly.to_csv(OUT / f"monthly_{period}.csv", index=False)
        absdiff = (x.sm_kwh - x.jh_kwh).abs()
        threshold = absdiff.quantile(.90)
        high = x.loc[absdiff >= threshold]
        year["large_disagreement_top_decile"] = {
            "threshold_abs_kwh": float(threshold),
            "group_hours": int(len(high)),
            "share_of_jh_baseline_w": float(high["pen_0.00"].sum() / x["pen_0.00"].sum()),
            "alpha_delta_w": {
                str(alpha): float((high[f"pen_{alpha:.2f}"] - high["pen_0.00"]).sum())
                for alpha in ALPHAS[1:]
            },
        }
        # Store group-hour rows only in the local ignored output directory for reproducibility.
        x.to_parquet(OUT / f"aligned_group_hours_{period}.parquet", index=False)

    manifest["outputs"] = {
        "scores": "outputs/sm56/complementarity.json",
        "monthly_2023-24": "outputs/sm56/monthly_2023-24.csv",
        "monthly_2024-25": "outputs/sm56/monthly_2024-25.csv",
        "comparison_rows": "outputs/sm56/aligned_group_hours_*.parquet",
    }
    (OUT / "alignment_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "complementarity.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"alignment": manifest["periods"], "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
