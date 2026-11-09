"""Transfer frozen SM67 peak deltas to read-only origin/main ens_v12 forecasts.

Use --handoff outputs/sm68/handoff to score CSVs produced by the approved
Parquet-capable environment. The default mode remains available there too.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import scoring as sc  # noqa: E402

OUT = ROOT / "outputs" / "sm68"
STARTING_SHA = "e0ddee1420903b9881d2ab7149a36649e63d2872"
MAIN_SHA = "793f5f6662f074dbc8e50d3b0f925b9b214c3683"
COMPOSITION_SHA = "933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463"
JH_SHA = {
    2023: "04065af84c4b7aef5abb26f6eec39987f6b8d7991d39a8e5ff3582c12f6af3a1",
    2024: "58388ca4328444443812116176cafdf07584f944e0ede11208524b39b95e233e",
}
SM67_DIR = OUT.parent / "sm67"
JH_PATHS = {
    2023: "predictions/val_2023-24/forecast_ens_v12_val.csv",
    2024: "predictions/val_2024-25/forecast_ens_v12_val.csv",
}
PERIODS = {2023: ("2023-06-01", "2024-06-01"), 2024: ("2024-06-01", "2025-06-01")}
ALPHA_SITE = 0.505
BOOT_BLOCK, BOOT_N, BOOT_SEED = 168, 5000, 68


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main_bytes(path: str) -> bytes:
    return subprocess.run(["git", "show", f"{MAIN_SHA}:{path}"], cwd=ROOT,
                          check=True, stdout=subprocess.PIPE).stdout


def verify_revision() -> None:
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    if branch != "seongmin":
        raise RuntimeError(f"expected working branch seongmin, got {branch!r}")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", STARTING_SHA, "HEAD"], cwd=ROOT)
    if ancestor.returncode != 0:
        raise RuntimeError("current HEAD is not a descendant of the required starting revision")
    current_main = subprocess.run(["git", "rev-parse", "origin/main"], cwd=ROOT, check=True,
                                  capture_output=True, text=True).stdout.strip()
    if current_main != MAIN_SHA:
        raise RuntimeError("origin/main differs from the pinned read-only reference SHA")


def bootstrap(delta_hourly: pd.Series) -> list[float]:
    d = delta_hourly.sort_index().to_numpy(dtype="float64")
    if not len(d):
        raise ValueError("cannot bootstrap an empty hourly series")
    rng = np.random.default_rng(BOOT_SEED)
    n_blocks = int(np.ceil(len(d) / BOOT_BLOCK))
    starts = np.arange(len(d))
    vals = np.empty(BOOT_N)
    for i in range(BOOT_N):
        ix = np.concatenate([(s + np.arange(BOOT_BLOCK)) % len(d)
                             for s in rng.choice(starts, n_blocks)])[:len(d)]
        vals[i] = d[ix].sum()
    return [float(np.quantile(vals, .025)), float(np.quantile(vals, .975))]


def transfer_candidate(jh: pd.DataFrame, delta_group: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply only the preregistered 0.505 peak transfer; absent support leaves A intact."""
    pred = jh[["group", "ts", "forecast_kwh"]].rename(columns={"forecast_kwh": "A"}).copy()
    pred = pred.merge(delta_group, on=["group", "ts"], how="left", validate="one_to_one")
    supported = pred.delta.notna()
    pred["delta"] = pred.delta.fillna(0.0)
    raw = pred.A + ALPHA_SITE * pred.delta
    peak = pred.ts.dt.hour.between(11, 15)
    pred["B"] = np.where(peak, raw.clip(lower=0.0), pred.A)
    clipped = peak & raw.lt(0.0)
    if not np.isfinite(pred[["A", "B", "delta"]].to_numpy()).all():
        raise RuntimeError("nonfinite aligned transfer values")
    if not np.array_equal(pred.loc[~peak, "A"].to_numpy(), pred.loc[~peak, "B"].to_numpy()):
        raise RuntimeError("nonpeak JH forecasts changed")
    counts = {
        "supported_group_hours": int(supported.sum()),
        "unsupported_group_hours": int((~supported).sum()),
        "clipped_group_hours": int(clipped.sum()),
        "changed_group_hours": int(pred.B.ne(pred.A).sum()),
        "changed_peak_group_hours": int((pred.B.ne(pred.A) & peak).sum()),
    }
    return pred, counts


def pinned_inputs(year: int):
    verify_revision()
    comp_bytes = main_bytes("predictions/submissions/composition_ens_v12.csv")
    if sha256_bytes(comp_bytes) != COMPOSITION_SHA:
        raise RuntimeError("pinned ens_v12 composition hash mismatch")
    jh_rel = JH_PATHS[year]
    jh_bytes = main_bytes(jh_rel)
    if sha256_bytes(jh_bytes) != JH_SHA[year]:
        raise RuntimeError("pinned JH forecast hash differs from SM56 artifact audit")
    from io import BytesIO
    comp = pd.read_csv(BytesIO(comp_bytes)).sort_values("site_id").reset_index(drop=True)
    jh = pd.read_csv(BytesIO(jh_bytes))
    required = {"group", "ts", "forecast_kwh", "site_model_kwh", "group_model_kwh"}
    if not required.issubset(jh.columns):
        raise RuntimeError(f"JH prediction schema mismatch: {jh.columns.tolist()}")
    jh["ts"] = sc.to_ts(jh.ts)
    jh["group"] = jh.group.astype(str)
    if jh.duplicated(["group", "ts"]).any():
        raise RuntimeError("JH prediction group-hour keys duplicate")
    if set(jh.group.unique()) != set(sc.GROUPS):
        raise RuntimeError("JH prediction contains unexpected groups")
    if not np.isfinite(jh[["forecast_kwh", "site_model_kwh", "group_model_kwh"]].to_numpy()).all():
        raise RuntimeError("JH prediction has NaN or infinite values")
    sites = sc.load_sites()
    reference = pd.DataFrame({"site_id": sites.site_id,
                              "group": sites.current_group.map({"A": "G1", "B": "G2"})})
    if not comp.equals(reference.sort_values("site_id").reset_index(drop=True)):
        raise RuntimeError("ens_v12 composition differs from reference; no automatic remapping")
    period_start, period_end = PERIODS[year]
    begin, finish = sc.window(period_start, period_end)
    ts_grid = pd.date_range(begin, finish, freq="h", tz=sc.TZ)
    expected = pd.MultiIndex.from_product([sc.GROUPS, ts_grid], names=["group", "ts"])
    actual_keys = pd.MultiIndex.from_frame(jh[["group", "ts"]])
    if len(jh) != len(expected) or set(actual_keys) != set(expected):
        raise RuntimeError("JH group-hour grid incomplete or outside scoring.window")
    result_path = SM67_DIR / f"result_{year}.json"
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    return comp_bytes, jh_bytes, comp, jh, sites, begin, finish, ts_grid, result, result_bytes


def validate_delta_group(dgroup: pd.DataFrame, ts_grid: pd.DatetimeIndex,
                         expected_support_hours: int | None = None) -> pd.DataFrame:
    required = {"group", "ts", "delta"}
    if not required.issubset(dgroup.columns):
        raise RuntimeError(f"group delta schema mismatch: {dgroup.columns.tolist()}")
    dgroup = dgroup[["group", "ts", "delta"]].copy()
    dgroup["ts"] = sc.to_ts(dgroup.ts)
    dgroup["group"] = dgroup.group.astype(str)
    if dgroup.duplicated(["group", "ts"]).any():
        raise RuntimeError("group delta contains duplicate keys")
    if set(dgroup.group.unique()) != set(sc.GROUPS):
        raise RuntimeError("group delta is missing a group")
    if not np.isfinite(dgroup.delta.to_numpy(dtype="float64")).all():
        raise RuntimeError("group delta contains NaN or infinite values")
    if not set(dgroup.ts).issubset(set(ts_grid)):
        raise RuntimeError("group delta has timestamps outside scoring.window")
    support_times = dgroup.ts.unique()
    if len(dgroup) != 2 * len(support_times):
        raise RuntimeError("group delta has a missing group row at a supported timestamp")
    if expected_support_hours is not None and len(support_times) != expected_support_hours:
        raise RuntimeError("group delta support-hour count disagrees with handoff manifest")
    offpeak = ~dgroup.ts.dt.hour.between(11, 15)
    if not np.equal(dgroup.loc[offpeak, "delta"].to_numpy(), 0.0).all():
        raise RuntimeError("SM67 delta is nonzero outside KST peak hours")
    return dgroup


def load_handoff(year: int, handoff_dir: Path, comp_bytes: bytes, jh_bytes: bytes,
                 result: dict, result_bytes: bytes, ts_grid: pd.DatetimeIndex):
    manifest_path = handoff_dir / f"handoff_manifest_{year}.json"
    delta_path = handoff_dir / f"group_delta_{year}.csv"
    actual_path = handoff_dir / f"actual_group_{year}.csv"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("year") != year or manifest.get("main_sha") != MAIN_SHA:
        raise RuntimeError("handoff year or pinned main revision mismatch")
    if (manifest.get("site_count") != 253
            or manifest.get("all_253_sites_each_support_timestamp") is not True
            or manifest.get("actual_rows_are_observed_only_no_zero_fill") is not True):
        raise RuntimeError("handoff manifest failed site-grid or observed-only assertions")
    expected_schemas = {
        "group_delta_csv": ["group", "ts", "delta_kwh"],
        "actual_group_csv": ["group", "ts", "actual_kwh", "observed_sites", "observed_capacity_kw"],
    }
    if manifest.get("schemas") != expected_schemas or manifest.get("timestamp_rule") != "Asia/Seoul right-closed scoring.window (start, end]":
        raise RuntimeError("handoff manifest schema or timestamp rule mismatch")
    expected_sources = {
        "sm67_baseline_parquet": result["prediction_hashes"]["baseline"],
        "sm67_candidate_parquet": result["prediction_hashes"]["candidate"],
        "sm67_result_json": sha256_bytes(result_bytes),
        "generation_parquet": manifest.get("source_hashes", {}).get("generation_parquet"),
        "jh_validation_csv": sha256_bytes(jh_bytes),
        "composition_csv": sha256_bytes(comp_bytes),
        "sites_csv": sha256_file(Path(sc.DATA) / "sites.csv"),
    }
    sources = manifest.get("source_hashes", {})
    for name in ("sm67_baseline_parquet", "sm67_candidate_parquet", "sm67_result_json",
                 "jh_validation_csv", "composition_csv"):
        if sources.get(name) != expected_sources[name]:
            raise RuntimeError(f"handoff source hash mismatch: {name}")
    generation_path = Path(sc.DATA) / "train" / "generation.parquet"
    if not generation_path.exists() or sha256_file(generation_path) != expected_sources["generation_parquet"]:
        raise RuntimeError("generation.parquet hash differs from handoff manifest")
    if sources.get("sites_csv") != expected_sources["sites_csv"]:
        raise RuntimeError("sites.csv hash differs from handoff manifest")
    for path, key in ((delta_path, "group_delta_csv"), (actual_path, "actual_group_csv")):
        if sha256_file(path) != manifest.get("output_hashes", {}).get(key):
            raise RuntimeError(f"handoff CSV hash mismatch: {path.name}")
    dgroup = pd.read_csv(delta_path, float_precision="round_trip")
    dgroup = dgroup.rename(columns={"delta_kwh": "delta"})
    if manifest.get("support_hours") != result.get("eval_hours"):
        raise RuntimeError("handoff support-hour count differs from frozen SM67 result")
    dgroup = validate_delta_group(dgroup, ts_grid,
                                  expected_support_hours=manifest.get("support_hours"))
    if len(dgroup) != manifest.get("delta_group_rows"):
        raise RuntimeError("handoff delta row count differs from manifest")
    actual = pd.read_csv(actual_path, float_precision="round_trip")
    required_actual = {"group", "ts", "actual_kwh", "observed_sites", "observed_capacity_kw"}
    if not required_actual.issubset(actual.columns):
        raise RuntimeError(f"actual group schema mismatch: {actual.columns.tolist()}")
    actual = actual[list(required_actual)].copy()
    actual["group"] = actual.group.astype(str)
    actual["ts"] = sc.to_ts(actual.ts)
    if actual.duplicated(["group", "ts"]).any():
        raise RuntimeError("actual group CSV contains duplicate keys")
    if not set(actual.group.unique()).issubset(set(sc.GROUPS)) or not set(actual.ts).issubset(set(ts_grid)):
        raise RuntimeError("actual group CSV has unexpected group or timestamp")
    numeric = actual[["actual_kwh", "observed_sites", "observed_capacity_kw"]].to_numpy(dtype="float64")
    if not np.isfinite(numeric).all() or (actual.observed_sites <= 0).any() or (actual.observed_capacity_kw <= 0).any():
        raise RuntimeError("actual group CSV has invalid observation metadata or values")
    if len(actual) != manifest.get("actual_group_rows"):
        raise RuntimeError("actual group row count differs from manifest")
    if {g: int(actual.group.eq(g).sum()) for g in sc.GROUPS} != manifest.get("actual_group_rows_by_group"):
        raise RuntimeError("actual group row counts differ from manifest")
    if str(actual.ts.min()) != manifest.get("actual_start_kst") or str(actual.ts.max()) != manifest.get("actual_end_kst"):
        raise RuntimeError("actual group timestamp range differs from manifest")
    return dgroup, actual, manifest


def bootstrap_ci(score: pd.DataFrame, ts_grid: pd.DatetimeIndex) -> list[float]:
    hourly = score.assign(d=lambda x: x.pen_B - x.pen_A).groupby("ts").d.sum().reindex(ts_grid, fill_value=0.0)
    return bootstrap(hourly)


def score_year(year: int, handoff_dir: Path | None = None) -> dict:
    comp_bytes, jh_bytes, composition, jh, sites, begin, finish, ts_grid, result, result_bytes = pinned_inputs(year)
    if year == 2023:
        gate_path = (handoff_dir / "sm68_score_2024.json") if handoff_dir else (OUT / "result_2024.json")
        if not gate_path.exists() or not json.loads(gate_path.read_text(encoding="utf-8")).get("go_2023"):
            raise RuntimeError("2024 preregistered gate did not pass")
    if handoff_dir:
        dgroup, ag, handoff_manifest = load_handoff(year, handoff_dir, comp_bytes, jh_bytes,
                                                     result, result_bytes, ts_grid)
        actual_rows_site = handoff_manifest.get("observed_site_hours")
        actual_source_hash = handoff_manifest["source_hashes"]["generation_parquet"]
    else:
        base_path = SM67_DIR / f"baseline_{year}_sites.parquet"
        cand_path = SM67_DIR / f"candidate_{year}_sites.parquet"
        if sha256_file(base_path) != result["prediction_hashes"]["baseline"]:
            raise RuntimeError("SM67 baseline prediction hash mismatch")
        if sha256_file(cand_path) != result["prediction_hashes"]["candidate"]:
            raise RuntimeError("SM67 candidate prediction hash mismatch")
        base, cand = pd.read_parquet(base_path), pd.read_parquet(cand_path)
        for frame in (base, cand):
            frame["ts"] = sc.to_ts(frame.ts)
            if frame.duplicated(["site_id", "ts"]).any() or not np.isfinite(frame.kwh).all():
                raise RuntimeError("SM67 prediction keys duplicated or values nonfinite")
        keys = ["site_id", "ts"]
        if len(base) != len(cand) or not base[keys].equals(cand[keys]):
            raise RuntimeError("SM67 A/B keys differ")
        if set(base.site_id.unique()) != set(composition.site_id):
            raise RuntimeError("SM67 support does not include exactly the 253 composition sites")
        sites_per_hour = base.groupby("ts", sort=False).site_id.nunique()
        if not sites_per_hour.eq(253).all() or len(base) != 253 * len(sites_per_hour):
            raise RuntimeError("SM67 timestamp has incomplete site predictions")
        dsite = base[keys].copy()
        dsite["delta"] = cand.kwh.to_numpy(dtype="float64") - base.kwh.to_numpy(dtype="float64")
        peak = dsite.ts.dt.hour.between(11, 15)
        if not np.equal(dsite.loc[~peak, "delta"].to_numpy(), 0.0).all():
            raise RuntimeError("SM67 contains nonzero site delta outside peak hours")
        comp_map = pd.Series(composition.group.to_numpy(), index=composition.site_id)
        dsite["group"] = dsite.site_id.map(comp_map)
        dgroup = dsite.groupby(["group", "ts"], as_index=False).delta.sum()
        dgroup = validate_delta_group(dgroup, ts_grid, result.get("eval_hours"))

        actual = sc.load_actual(*PERIODS[year])
        actual["ts"] = sc.to_ts(actual.ts)
        comp_map = pd.Series(composition.group.to_numpy(), index=composition.site_id)
        cap_map = sites.set_index("site_id").capacity_kw
        actual["group"] = actual.site_id.map(comp_map)
        actual["capacity_kw"] = actual.site_id.map(cap_map)
        if actual[["group", "capacity_kw"]].isna().any().any() or actual.duplicated(["site_id", "ts"]).any():
            raise RuntimeError("actual generation has unknown sites, missing capacity, or duplicate keys")
        ag = actual.groupby(["group", "ts"], as_index=False).agg(
            actual_kwh=("energy", "sum"), observed_sites=("site_id", "nunique"),
            observed_capacity_kw=("capacity_kw", "sum"))
        actual_rows_site = len(actual)
        actual_source_hash = sha256_file(Path(sc.DATA) / "train" / "generation.parquet")
        handoff_manifest = None

    pred_grid, transfer_counts = transfer_candidate(jh, dgroup)
    support_keys = pd.MultiIndex.from_frame(dgroup[["group", "ts"]])
    pred_keys = pd.MultiIndex.from_frame(pred_grid[["group", "ts"]])
    supported = pred_keys.isin(support_keys)
    pred_grid["delta_supported"] = supported
    scored = pred_grid.merge(ag, on=["group", "ts"], how="left", validate="one_to_one")
    scored["observed_sites"] = scored.observed_sites.fillna(0).astype(int)
    score = scored.loc[scored.observed_sites.gt(0)].copy()
    if score.actual_kwh.isna().any():
        raise RuntimeError("observed group-hour has no actual group sum")
    smp = sc.load_smp()
    score["smp"] = score.ts.map(smp)
    if score.smp.isna().any():
        raise RuntimeError("missing SMP on scored group-hours")
    score["w"] = sc.PENALTY_RATE * score.smp * sc.k_weight(score.ts)
    for col in ("A", "B"):
        score[f"pen_{col}"] = score.w * (score[col] - score.actual_kwh).abs()
    if not np.array_equal(score.loc[~score.ts.dt.hour.between(11, 15), "pen_A"].to_numpy(),
                          score.loc[~score.ts.dt.hour.between(11, 15), "pen_B"].to_numpy()):
        raise RuntimeError("nonpeak W changed")
    delta_hourly = score.assign(d=lambda x: x.pen_B - x.pen_A).groupby("ts").d.sum().sort_index()
    peak_mask = score.ts.dt.hour.between(11, 15)
    monthly = score.assign(month=(score.ts - pd.Timedelta(hours=1)).dt.strftime("%Y-%m"))
    d_supported = dgroup.merge(jh[["group", "ts", "forecast_kwh"]], on=["group", "ts"], validate="one_to_one")
    d_supported = d_supported.merge(ag[["group", "ts", "actual_kwh"]], on=["group", "ts"], how="inner", validate="one_to_one")
    delta_summary = {
        "mean": float(dgroup.delta.mean()), "std": float(dgroup.delta.std()),
        "p10": float(dgroup.delta.quantile(.10)), "median": float(dgroup.delta.median()),
        "p90": float(dgroup.delta.quantile(.90)), "min": float(dgroup.delta.min()),
        "max": float(dgroup.delta.max()), "positive_rows": int(dgroup.delta.gt(0).sum()),
        "negative_rows": int(dgroup.delta.lt(0).sum()), "zero_rows": int(dgroup.delta.eq(0).sum()),
    }
    corr = float((d_supported.forecast_kwh - d_supported.actual_kwh).corr(d_supported.delta)) if len(d_supported) > 1 else None
    res = {
        "year": year, "main_sha": MAIN_SHA, "jh_input_sha256": sha256_bytes(jh_bytes),
        "composition_sha256": sha256_bytes(comp_bytes),
        "sm67_baseline_sha256": result["prediction_hashes"]["baseline"],
        "sm67_candidate_sha256": result["prediction_hashes"]["candidate"],
        "generation_sha256": actual_source_hash,
        "sites_sha256": sha256_file(Path(sc.DATA) / "sites.csv"),
        "smp_sha256": sha256_file(Path(sc.DATA) / "train" / "smp.csv"),
        "source_support_hours": int(dgroup.ts.nunique()),
        "unsupported_timestamps": int(len(ts_grid) - dgroup.ts.nunique()),
        "unsupported_group_hours": transfer_counts["unsupported_group_hours"],
        "delta_group_rows": int(len(dgroup)), "handoff_manifest_used": handoff_manifest is not None,
        "clipped_rows": transfer_counts["clipped_group_hours"],
        "changed_rows": transfer_counts["changed_group_hours"],
        "changed_peak_rows": transfer_counts["changed_peak_group_hours"],
        "jh_rows": len(jh), "scored_group_hours": len(score),
        "observed_site_hours": int(actual_rows_site),
        "observed_group_hour_coverage": {g: int(score.loc[score.group.eq(g)].shape[0]) for g in sc.GROUPS},
        "W": {c: float(score[f"pen_{c}"].sum()) for c in ("A", "B")},
        "delta_W": float(score.pen_B.sum() - score.pen_A.sum()),
        "group_W": {g: {c: float(score.loc[score.group.eq(g), f"pen_{c}"].sum()) for c in ("A", "B")}
                    for g in sc.GROUPS},
        "group_peak_W": {g: {c: float(score.loc[score.group.eq(g) & peak_mask, f"pen_{c}"].sum())
                              for c in ("A", "B")} for g in sc.GROUPS},
        "group_offpeak_W": {g: {c: float(score.loc[score.group.eq(g) & ~peak_mask, f"pen_{c}"].sum())
                                 for c in ("A", "B")} for g in sc.GROUPS},
        "peak_W": {c: float(score.loc[peak_mask, f"pen_{c}"].sum()) for c in ("A", "B")},
        "offpeak_W": {c: float(score.loc[~peak_mask, f"pen_{c}"].sum()) for c in ("A", "B")},
        "monthly_W": {m: {c: float(g[f"pen_{c}"].sum()) for c in ("A", "B")}
                       for m, g in monthly.groupby("month")},
        "group_signed_residual_mean": {
            g: {c: float((score.loc[score.group.eq(g), c] - score.loc[score.group.eq(g), "actual_kwh"]).mean())
                for c in ("A", "B")} for g in sc.GROUPS},
        "delta_group_summary": delta_summary,
        "delta_vs_jh_signed_error_correlation": corr,
        "bootstrap_168h_ci": None,
        "observed_capacity_kw_mean": (float(ag.observed_capacity_kw.mean()) if "observed_capacity_kw" in ag else None),
    }
    if year == 2024:
        res["recorded_sm56_A1_W"] = 167_076_206.0
        res["recomputed_vs_sm56_delta"] = res["W"]["A"] - res["recorded_sm56_A1_W"]
        improvement = (res["W"]["B"] - res["W"]["A"]) / res["W"]["A"]
        res["go_2023"] = bool(improvement <= -.005
                              and all(res["group_W"][g]["B"] < res["group_W"][g]["A"] for g in sc.GROUPS)
                              and res["offpeak_W"]["A"] == res["offpeak_W"]["B"])
        res["improvement_fraction"] = improvement
        if res["go_2023"]:
            res["bootstrap_168h_ci"] = bootstrap_ci(score, ts_grid)

    outdir = handoff_dir if handoff_dir else OUT
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"sm68_score_{year}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return res


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, choices=(2023, 2024), required=True)
    p.add_argument("--handoff", type=Path, default=None,
                   help="CSV handoff directory from sm68_export_handoff.py; avoids Parquet reads")
    args = p.parse_args()
    result = score_year(args.year, args.handoff)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
