"""Verify SM53 artifact lineage and decompose its frozen 2024 settlement delta."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import scoring as sc
from features import solar
from sm39_group_site_integration import hourly_penalties, redistribute

EXPECTED = {
    "baseline_site": "dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26",
    "candidate_site": "1ba0066f6457f8eb242673124ca882ef98c3a09c167b04815dc8f853a08eacf4",
    "group": "651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7",
    "baseline_blend": "a0332f098ef64959c7b47f04ebfd3e2e6c72fb75d0660aea2822f908b6ea4cfa",
    "candidate_blend": "69d9422d79a5806b5d378fb5bc4d39fbcfe109775b2f86124e994c8a1055208a",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_artifact(path: Path, expected: str, keys: list[str], value: str) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha = sha256(path)
    if actual_sha != expected:
        raise RuntimeError(f"SHA256 mismatch for {path}: {actual_sha} != {expected}")
    df = pd.read_parquet(path)
    required = set(keys + [value])
    if not required <= set(df.columns):
        raise RuntimeError(f"Unexpected schema for {path}: {df.columns.tolist()}")
    df = df[keys + [value]].copy()
    df["ts"] = sc.to_ts(df.ts)
    if df.duplicated(keys).any() or not np.isfinite(df[value].to_numpy(float)).all():
        raise RuntimeError(f"Duplicate keys/nonfinite values in {path}")
    return df


def check_grid(df: pd.DataFrame, keys: list[str], groups: list[str], times: pd.DatetimeIndex,
               label: str) -> None:
    expected = pd.MultiIndex.from_product([groups, times], names=keys)
    got = pd.MultiIndex.from_frame(df[keys])
    if len(got) != len(expected) or not got.is_unique or len(expected.difference(got)):
        raise RuntimeError(f"{label} grid does not match expected full grid")


def make_detail(blend: pd.DataFrame, actual: pd.DataFrame, sites: pd.DataFrame,
                comp: pd.Series, smp: pd.Series) -> tuple[pd.DataFrame, float, float]:
    # Actual rows define the common official observed site-hour mask.
    site = actual[["site_id", "ts", "energy"]].copy()
    site["ts"] = sc.to_ts(site.ts)
    site = site.merge(blend, on=["site_id", "ts"], validate="one_to_one")
    if site.kwh.isna().any():
        raise RuntimeError("Missing prediction on observed site-hour mask")
    site["group"] = site.site_id.map(comp)
    site["resid"] = site.kwh - site.energy
    site["w"] = sc.PENALTY_RATE * site.ts.map(smp) * sc.k_weight(site.ts)
    if site.w.isna().any() or (site.w < 0).any():
        raise RuntimeError("Missing/invalid SMP settlement weights")
    site["weighted_individual"] = site.w * site.resid.abs()
    site_mae = float(site.resid.abs().mean())
    site_bias = float(site.resid.mean())

    group = site.groupby(["group", "ts"], as_index=False).agg(
        pred=("kwh", "sum"), actual=("energy", "sum"),
        residual=("resid", "sum"), W_individual=("weighted_individual", "sum"),
        w=("w", "first"), observed_sites=("site_id", "size"),
    )
    group["W_group"] = group.w * group.residual.abs()
    group["C_cancel"] = group.W_individual - group.W_group
    group["over_W"] = group.w * group.residual.clip(lower=0)
    group["under_W"] = group.w * (-group.residual).clip(lower=0)
    group["weighted_signed"] = group.w * group.residual
    group["peak"] = group.ts.dt.hour.between(11, 15)
    group["month"] = group.ts.dt.strftime("%Y-%m")
    group["date"] = group.ts.dt.strftime("%Y-%m-%d")
    ref = sites.set_index("site_id")
    ts = pd.DatetimeIndex(group.ts.unique())
    _, azim, _ = solar(ts, np.full(len(ts), float(ref.lat.median())),
                       np.full(len(ts), float(ref.lon.median())))
    am_map = pd.Series(np.sin(np.deg2rad(azim)) >= 0, index=ts)
    group["solar_side"] = np.where(group.ts.map(am_map), "morning", "afternoon")
    if (group.C_cancel < -1e-7).any():
        raise AssertionError("Cancellation benefit cannot be negative under common mask/weights")
    return group, site_mae, site_bias


def metrics(df: pd.DataFrame, site_mae: float, site_bias: float) -> dict:
    individual = float(df.W_individual.sum())
    group = float(df.W_group.sum())
    return {
        "site_MAE_kWh": site_mae,
        "site_signed_bias_kWh": site_bias,
        "weighted_individual_W_KRW": individual,
        "group_settlement_W_KRW": group,
        "cancellation_benefit_KRW": individual - group,
        "cancellation_ratio": (individual - group) / individual,
        "group_mean_signed_residual_kWh": float(df.residual.mean()),
        "group_weighted_signed_residual_sum": float(df.weighted_signed.sum()),
        "group_weighted_signed_residual_mean_kWh": float(df.weighted_signed.sum() / df.w.sum()),
        "group_overprediction_W_KRW": float(df.over_W.sum()),
        "group_underprediction_W_KRW": float(df.under_W.sum()),
        "group_hours": int(len(df)),
    }


def summarize_buckets(base: pd.DataFrame, cand: pd.DataFrame, column: str) -> pd.DataFrame:
    rows = []
    labels = sorted(set(base[column].unique()) | set(cand[column].unique()))
    measures = ["W_individual", "W_group", "C_cancel", "over_W", "under_W", "weighted_signed"]
    for label in labels:
        r = {"bucket": label}
        for name, frame in (("baseline", base), ("candidate", cand)):
            part = frame[frame[column] == label]
            for measure in measures:
                r[f"{name}_{measure}"] = float(part[measure].sum())
            r[f"{name}_group_mean_signed_kWh"] = float(part.residual.mean())
            r[f"{name}_weighted_signed_mean_kWh"] = float(part.weighted_signed.sum() / part.w.sum())
        for measure in measures:
            r[f"delta_{measure}"] = r[f"candidate_{measure}"] - r[f"baseline_{measure}"]
        r["delta_group_mean_signed_kWh"] = r["candidate_group_mean_signed_kWh"] - r["baseline_group_mean_signed_kWh"]
        r["delta_weighted_signed_mean_kWh"] = r["candidate_weighted_signed_mean_kWh"] - r["baseline_weighted_signed_mean_kWh"]
        rows.append(r)
    return pd.DataFrame(rows)


def main() -> None:
    out = ROOT / "outputs" / "sm55"
    out.mkdir(parents=True, exist_ok=True)
    outputs = ROOT / "outputs"
    paths = {
        "baseline_site": outputs / "val_sm45_a1_s7_sites.parquet",
        "candidate_site": outputs / "val_sm53_profile_s7_sites.parquet",
        "group": outputs / "sm45" / "group_a1_2024.parquet",
        "baseline_blend": outputs / "sm53" / "baseline_blend_2024.parquet",
        "candidate_blend": outputs / "sm53" / "candidate_blend_2024.parquet",
    }
    source = {name: read_artifact(path, EXPECTED[name],
                                  ["group", "ts"] if name == "group" else ["site_id", "ts"],
                                  "pred" if name == "group" else "kwh")
              for name, path in paths.items()}
    start, end = "2024-06-01", "2025-06-01"
    ts0, ts1 = sc.window(start, end)
    times = pd.date_range(ts0, ts1, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    check_grid(source["baseline_site"], ["site_id", "ts"], sites.site_id.tolist(), times, "baseline Site")
    check_grid(source["candidate_site"], ["site_id", "ts"], sites.site_id.tolist(), times, "candidate Site")
    check_grid(source["group"], ["group", "ts"], ["G1", "G2"], times, "Group")
    check_grid(source["baseline_blend"], ["site_id", "ts"], sites.site_id.tolist(), times, "baseline blend")
    check_grid(source["candidate_blend"], ["site_id", "ts"], sites.site_id.tolist(), times, "candidate blend")

    # Verify saved redistribution exactly from the SHA-checked inputs.
    blend_regen_max_abs_delta = {}
    for site_name, blend_name in (("baseline_site", "baseline_blend"), ("candidate_site", "candidate_blend")):
        fresh = redistribute(source[site_name], source["group"], sites, comp, .2, times)
        saved = source[blend_name]
        compare = fresh.merge(saved, on=["site_id", "ts"], suffixes=("_fresh", "_saved"), validate="one_to_one")
        if len(compare) != len(fresh) or not np.allclose(compare.kwh_fresh, compare.kwh_saved, rtol=0, atol=1e-10):
            raise RuntimeError(f"Saved {blend_name} does not match redistribution from checked inputs")
        blend_regen_max_abs_delta[blend_name] = float((compare.kwh_fresh - compare.kwh_saved).abs().max())

    actual = sc.load_actual(start, end)
    smp = sc.load_smp()
    detailed, model_metrics, official_w = {}, {}, {}
    for name in ("baseline_blend", "candidate_blend"):
        label = "baseline" if name.startswith("baseline") else "candidate"
        pred = source[name]
        r = sc.score(pred, comp, actual, smp)
        group_from_helper = hourly_penalties(pred, actual, comp, smp)
        if not np.isclose(r["W"], group_from_helper.pen.sum(), rtol=0, atol=1e-6):
            raise AssertionError(f"scoring.py and hourly penalty sum disagree for {label}")
        g, mae, site_bias = make_detail(pred, actual, sites, comp, smp)
        if not np.isclose(r["W"], g.W_group.sum(), rtol=0, atol=1e-6):
            raise AssertionError(f"scoring.py and decomposition group W disagree for {label}")
        detailed[label] = g
        model_metrics[label] = metrics(g, mae, site_bias)
        official_w[label] = float(r["W"])

    base, cand = detailed["baseline"], detailed["candidate"]
    if not base[["group", "ts"]].equals(cand[["group", "ts"]]):
        raise RuntimeError("Common settlement mask differs between models")
    delta = {key: model_metrics["candidate"][key] - model_metrics["baseline"][key]
             for key in model_metrics["baseline"]}
    if not np.isclose(delta["group_settlement_W_KRW"],
                       delta["weighted_individual_W_KRW"] - delta["cancellation_benefit_KRW"], atol=1e-6):
        raise AssertionError("Portfolio ΔW identity does not reconcile")
    if not np.isclose(delta["group_settlement_W_KRW"], 872544.1493698657, rtol=0, atol=1e-5):
        raise RuntimeError(f"Previous SM53 ΔW not reproduced: {delta['group_settlement_W_KRW']}")

    tables = {}
    for name, col in (("by_group", "group"), ("by_peak", "peak"),
                      ("by_solar_side", "solar_side"), ("by_month", "month"), ("by_day", "date")):
        x, y = base.copy(), cand.copy()
        if name == "by_peak":
            x[col] = np.where(x.peak, "peak_11_15", "nonpeak")
            y[col] = np.where(y.peak, "peak_11_15", "nonpeak")
        tables[name] = summarize_buckets(x, y, col)
        tables[name].to_csv(out / f"{name}.csv", index=False)

    group_peak = summarize_buckets(
        base.assign(group_peak=base.group.astype(str) + "_" + np.where(base.peak, "peak", "offpeak")),
        cand.assign(group_peak=cand.group.astype(str) + "_" + np.where(cand.peak, "peak", "offpeak")), "group_peak")
    group_peak.to_csv(out / "by_group_peak.csv", index=False)
    day = tables["by_day"].sort_values("delta_W_group", ascending=False)
    top = day.head(10)[["bucket", "baseline_W_group", "candidate_W_group", "delta_W_group"]].rename(columns={"bucket": "date"}).copy()
    for group_name in ("G1", "G2"):
        b = base[base.group == group_name].groupby("date").W_group.sum()
        c = cand[cand.group == group_name].groupby("date").W_group.sum()
        bp = base[(base.group == group_name) & base.peak].groupby("date").W_group.sum()
        cp = cand[(cand.group == group_name) & cand.peak].groupby("date").W_group.sum()
        top[f"delta_{group_name}_W"] = top.date.map(c - b)
        top[f"delta_{group_name}_peak_W"] = top.date.map(cp - bp).fillna(0)
    top.to_csv(out / "top10_adverse_dates.csv", index=False)

    # Group and period subsets must add back to the all-portfolio difference.
    group_delta = tables["by_group"]
    for column in ("W_individual", "W_group", "C_cancel", "over_W", "under_W", "weighted_signed"):
        target = delta[{
            "W_individual": "weighted_individual_W_KRW", "W_group": "group_settlement_W_KRW",
            "C_cancel": "cancellation_benefit_KRW", "over_W": "group_overprediction_W_KRW",
            "under_W": "group_underprediction_W_KRW", "weighted_signed": "group_weighted_signed_residual_sum"
        }[column]]
        if not np.isclose(group_delta[f"delta_{column}"].sum(), target, atol=1e-4):
            raise AssertionError(f"G1/G2 partition does not reconcile for {column}")

    payload = {
        "experiment": "SM55 artifact provenance and settlement loss decomposition",
        "period": f"({start} 00:00, {end} 00:00] KST",
        "delta_convention": "candidate minus baseline",
        "verified_sha256": {name: sha256(path) for name, path in paths.items()},
        "rows_and_schema": {name: {"rows": int(len(df)),
                                    "stored_columns": pd.read_parquet(paths[name]).columns.tolist(),
                                    "scored_columns": df.columns.tolist(),
                                    "min_ts": df.ts.min().isoformat(), "max_ts": df.ts.max().isoformat(),
                                    "unique_groups": sorted(df.group.unique().tolist()) if "group" in df else None}
                            for name, df in source.items()},
        "actual_observed_site_hours": int(len(actual)),
        "official_group_hours": int(len(actual.groupby([actual.site_id.map(comp).rename("group"), actual.ts]))),
        "reference_composition_site_count": int(len(comp)),
        "alpha": 0.2,
        "scoring_py_W_KRW": {"baseline": official_w["baseline"], "candidate": official_w["candidate"],
                              "delta": official_w["candidate"] - official_w["baseline"]},
        "metrics": model_metrics,
        "delta": delta,
        "monthly_improved_count": int((tables["by_month"].delta_W_group < 0).sum()),
        "monthly_worsened_count": int((tables["by_month"].delta_W_group > 0).sum()),
        "top10_adverse_dates": top.to_dict(orient="records"),
        "blend_regeneration_verified": True,
        "blend_regeneration_max_abs_kwh_delta": blend_regen_max_abs_delta,
        "scoring_py_crosscheck_verified": True,
        "source_pilot_json_group_hash": json.loads((outputs / "sm53" / "pilot_2024.json").read_text(encoding="utf-8"))["artifacts"].get("frozen_group_prediction_sha256"),
        "source_sha256": {
            "sm45_manifest": sha256(outputs / "sm45" / "manifest.json"),
            "sm53_pilot_json": sha256(outputs / "sm53" / "pilot_2024.json"),
            "generation_actuals": sha256(Path(sc.DATA) / "train" / "generation.parquet"),
            "smp": sha256(Path(sc.DATA) / "train" / "smp.csv"),
        },
        "code_sha256": {
            str(path.relative_to(ROOT)): sha256(path) for path in (
                ROOT / "src" / "analysis" / "sm55_settlement_decomposition.py",
                ROOT / "src" / "analysis" / "sm39_group_site_integration.py",
                ROOT / "src" / "scoring.py",
                ROOT / "src" / "features.py",
            )
        },
    }
    (out / "decomposition.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"W": payload["scoring_py_W_KRW"], "delta": delta}, indent=2))


if __name__ == "__main__":
    main()
