"""Training-only Group label coverage and representativeness audit for SM44."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agg_model as am
import features as F
import scoring as sc

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "sm44"
THRESHOLDS = (0.1, 0.3, 0.5)
QUANTILES = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def group_centers(sites: pd.DataFrame, comp: pd.Series) -> pd.DataFrame:
    s = sites.assign(group=sites.site_id.map(comp))
    return s.groupby("group").apply(
        lambda x: pd.Series({
            "lat": np.average(x.lat, weights=x.capacity_kw),
            "lon": np.average(x.lon, weights=x.capacity_kw),
        }), include_groups=False)


def audit_fold(year: int, sites: pd.DataFrame, comp: pd.Series) -> dict:
    pa, _ = sc.window(f"{year}-06-01", f"{year+1}-06-01")
    start = pa - pd.DateOffset(years=2)
    end = pa - pd.Timedelta(hours=1)
    gen = am.load_gen(start, end)
    # min_cov=0 retains every group-hour with any reported generation.
    labels = am.targets(gen, sites, comp, min_cov=0.0)
    ts = pd.date_range(start, end, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    grid = pd.MultiIndex.from_product([sc.GROUPS, ts], names=["group", "ts"]).to_frame(index=False)
    grid = grid.merge(labels[["group", "ts", "act", "cap_avail", "cov", "cf"]],
                      on=["group", "ts"], how="left", validate="one_to_one")
    grid["cov"] = grid["cov"].fillna(0.0)
    grid["daylight"] = False
    centers = group_centers(sites, comp)
    for group in sc.GROUPS:
        mask = grid.group.eq(group)
        elev, _, _ = F.solar(pd.DatetimeIndex(grid.loc[mask, "ts"]),
                             centers.loc[group, "lat"], centers.loc[group, "lon"])
        grid.loc[mask, "daylight"] = np.asarray(elev) > -2

    total_capacity = sites.assign(group=sites.site_id.map(comp)).groupby("group").capacity_kw.sum()
    ggen = gen.merge(sites[["site_id", "capacity_kw"]], on="site_id", validate="many_to_one")
    ggen["group"] = ggen.site_id.map(comp)
    ggen["capacity_exposure"] = ggen.capacity_kw
    result = {
        "validation_year": year,
        "train_start_inclusive": str(start), "train_end_inclusive": str(end),
        "hours_per_group": int(len(ts)), "full_group_hour_rows": int(len(grid)),
        "training_generation_site_rows": int(len(gen)),
        "by_group": {},
    }
    long_rows = []
    for group in sc.GROUPS:
        x = grid[grid.group.eq(group)]
        reported = x[x["cov"].gt(0)]
        stats = {
            "full_group_hours": int(len(x)),
            "hours_with_any_observed_site": int(len(reported)),
            "coverage_mean_all_group_hours_including_zero": float(x["cov"].mean()),
            "coverage_quantiles_all_group_hours_including_zero": {
                str(q): float(x["cov"].quantile(q)) for q in QUANTILES
            },
            "coverage_cf_pearson_correlation_on_reported_hours": (
                float(reported[["cov", "cf"]].corr().iloc[0, 1]) if len(reported) > 1 else None
            ),
            "cf_quantiles_on_reported_hours": (
                {str(q): float(reported.cf.quantile(q)) for q in QUANTILES} if len(reported) else {}
            ),
            "thresholds": {},
        }
        for threshold in THRESHOLDS:
            q = x[x["cov"].ge(threshold)]
            cf = q.cf.dropna()
            threshold_stats = {
                "eligible_rows": int(len(q)),
                "daylight_rows": int(q.daylight.sum()),
                "night_rows": int((~q.daylight).sum()),
                "coverage_mean": float(q["cov"].mean()) if len(q) else None,
                "coverage_median": float(q["cov"].median()) if len(q) else None,
                "cf_rows": int(len(cf)),
                "cf_mean": float(cf.mean()) if len(cf) else None,
                "cf_median": float(cf.median()) if len(cf) else None,
                "cf_std": float(cf.std()) if len(cf) > 1 else None,
                "cf_quantiles": {str(p): float(cf.quantile(p)) for p in QUANTILES} if len(cf) else {},
            }
            stats["thresholds"][str(threshold)] = threshold_stats
            long_rows.append({"validation_year": year, "group": group,
                              "coverage_threshold": threshold, **threshold_stats})

        exposure = (ggen[ggen.group.eq(group)].groupby("site_id")
                    .agg(reporting_rows=("ts", "size"), capacity_exposure=("capacity_exposure", "sum"))
                    .sort_values("capacity_exposure", ascending=False))
        exposure_total = float(exposure.capacity_exposure.sum())
        stats["site_reporting_concentration"] = {
            "sites_with_any_generation_rows": int(len(exposure)),
            "top1_share_of_observed_capacity_exposure": (
                float(exposure.capacity_exposure.iloc[:1].sum() / exposure_total) if exposure_total else 0.0
            ),
            "top5_share_of_observed_capacity_exposure": (
                float(exposure.capacity_exposure.iloc[:5].sum() / exposure_total) if exposure_total else 0.0
            ),
            "observed_capacity_exposure_hhi": (
                float(((exposure.capacity_exposure / exposure_total) ** 2).sum()) if exposure_total else 0.0
            ),
            "top5_sites": [
                {"site_id": str(site_id), "reporting_rows": int(row.reporting_rows),
                 "capacity_exposure_share": float(row.capacity_exposure / exposure_total)}
                for site_id, row in exposure.head(5).iterrows()
            ],
        }
        stats["fixed_reference_group_capacity_kw"] = float(total_capacity[group])
        result["by_group"][group] = stats
    result["sha256"] = {
        "sites_csv": sha256(Path(sc.DATA) / "sites.csv"),
        "generation_parquet": sha256(Path(sc.DATA) / "train" / "generation.parquet"),
    }
    return result, long_rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    all_results, all_rows = {}, []
    for year in (2023, 2024):
        result, rows = audit_fold(year, sites, comp)
        all_results[str(year)] = result
        all_rows.extend(rows)
    feasibility = {}
    for candidate, threshold in (("G1", 0.1), ("G2", 0.5)):
        failed = []
        for year, result in all_results.items():
            for group in sc.GROUPS:
                detail = result["by_group"][group]["thresholds"][str(threshold)]
                if detail["eligible_rows"] < 200 or detail["daylight_rows"] < 100:
                    failed.append({"year": int(year), "group": group,
                                   "eligible_rows": detail["eligible_rows"],
                                   "daylight_rows": detail["daylight_rows"]})
        feasibility[candidate] = {
            "coverage_threshold": threshold,
            "minimum_rows_per_group_per_window": 200,
            "minimum_daylight_rows_per_group_per_window": 100,
            "status": "feasible" if not failed else "Not Run: insufficient pre-registered support",
            "failed_support_checks": failed,
        }
    all_results["candidate_feasibility"] = feasibility
    (OUT / "coverage_audit.json").write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    pd.DataFrame(all_rows).to_csv(OUT / "coverage_threshold_counts.csv", index=False)
    print(json.dumps(all_results, indent=2), flush=True)


if __name__ == "__main__":
    main()
