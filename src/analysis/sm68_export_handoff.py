"""Export minimum SM68 group delta/actual CSVs in an approved Parquet runtime.

This script reads frozen artifacts only. It does not train or alter forecasts.
Run from the repository root with a Python environment able to read Parquet.
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

OUT = ROOT / "outputs" / "sm68" / "handoff"
STARTING_SHA = "e0ddee1420903b9881d2ab7149a36649e63d2872"
MAIN_SHA = "793f5f6662f074dbc8e50d3b0f925b9b214c3683"
COMPOSITION_SHA = "933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463"
JH_SHA = {
    2023: "04065af84c4b7aef5abb26f6eec39987f6b8d7991d39a8e5ff3582c12f6af3a1",
    2024: "58388ca4328444443812116176cafdf07584f944e0ede11208524b39b95e233e",
}
JH_PATHS = {
    2023: "predictions/val_2023-24/forecast_ens_v12_val.csv",
    2024: "predictions/val_2024-25/forecast_ens_v12_val.csv",
}
PERIODS = {2023: ("2023-06-01", "2024-06-01"), 2024: ("2024-06-01", "2025-06-01")}
SM67_DIR = ROOT / "outputs" / "sm67"


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
    check = subprocess.run(["git", "merge-base", "--is-ancestor", STARTING_SHA, "HEAD"], cwd=ROOT)
    if check.returncode != 0:
        raise RuntimeError("current HEAD is not a descendant of the SM68 starting revision")
    main_sha = subprocess.run(["git", "rev-parse", "origin/main"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    if main_sha != MAIN_SHA:
        raise RuntimeError("origin/main differs from the pinned read-only reference")


def build_group_delta(base: pd.DataFrame, cand: pd.DataFrame, composition: pd.DataFrame,
                      ts_grid: pd.DatetimeIndex, expected_hours: int) -> pd.DataFrame:
    keys = ["site_id", "ts"]
    for frame in (base, cand):
        if not set(keys + ["kwh"]).issubset(frame.columns):
            raise ValueError("SM67 forecast columns must include site_id, ts, kwh")
        frame["ts"] = sc.to_ts(frame.ts)
        if frame.duplicated(keys).any() or not np.isfinite(frame.kwh.to_numpy(dtype="float64")).all():
            raise ValueError("SM67 forecasts contain duplicate keys or nonfinite values")
    if len(base) != len(cand) or not base[keys].equals(cand[keys]):
        raise ValueError("SM67 A/B (site_id, ts) keys differ")
    expected_sites = set(composition.site_id)
    if len(expected_sites) != 253 or set(base.site_id.unique()) != expected_sites:
        raise ValueError("SM67 support does not contain exactly the reference 253 sites")
    sites_per_ts = base.groupby("ts", sort=False).site_id.nunique()
    if len(sites_per_ts) != expected_hours or not sites_per_ts.eq(253).all():
        raise ValueError("each SM67 support timestamp must have exactly 253 site forecasts")
    if len(base) != 253 * expected_hours or not set(base.ts.unique()).issubset(set(ts_grid)):
        raise ValueError("SM67 support row count or evaluation timestamp range is invalid")

    delta = cand[keys].copy()
    delta["delta_kwh"] = cand.kwh.to_numpy(dtype="float64") - base.kwh.to_numpy(dtype="float64")
    offpeak = ~delta.ts.dt.hour.between(11, 15)
    if not np.equal(delta.loc[offpeak, "delta_kwh"].to_numpy(), 0.0).all():
        raise ValueError("SM67 site delta is not exactly zero outside KST peak hours")
    group_map = composition.set_index("site_id").group
    delta["group"] = delta.site_id.map(group_map)
    if delta.group.isna().any():
        raise ValueError("one or more SM67 sites have no reference group")
    result = (delta.groupby(["group", "ts"], as_index=False).delta_kwh.sum()
              .sort_values(["group", "ts"]).reset_index(drop=True))
    if len(result) != 2 * expected_hours or result.duplicated(["group", "ts"]).any():
        raise ValueError("group delta does not contain both groups at every support timestamp")
    return result


def build_actual_groups(actual: pd.DataFrame, sites: pd.DataFrame,
                        composition: pd.DataFrame, begin: pd.Timestamp,
                        finish: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    required = {"site_id", "ts", "energy"}
    if not required.issubset(actual.columns):
        raise ValueError("generation data must include site_id, ts, energy")
    actual = actual.copy()
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual.loc[actual.ts.between(begin, finish)].copy()
    if actual.empty:
        raise ValueError("no observed generation rows in the right-closed evaluation window")
    if actual.duplicated(["site_id", "ts"]).any() or not np.isfinite(actual.energy.to_numpy(dtype="float64")).all():
        raise ValueError("generation observations contain duplicate keys or nonfinite energy")
    group_map = composition.set_index("site_id").group
    cap_map = sites.set_index("site_id").capacity_kw
    actual["group"] = actual.site_id.map(group_map)
    actual["capacity_kw"] = actual.site_id.map(cap_map)
    if actual[["group", "capacity_kw"]].isna().any().any():
        raise ValueError("generation includes a site without reference group/capacity")
    grouped = (actual.groupby(["group", "ts"], as_index=False)
               .agg(actual_kwh=("energy", "sum"), observed_sites=("site_id", "nunique"),
                    observed_capacity_kw=("capacity_kw", "sum"))
               .sort_values(["group", "ts"]).reset_index(drop=True))
    # Rows exist only where one or more plants were actually observed; no zero fill.
    if (grouped.observed_sites <= 0).any() or (grouped.observed_capacity_kw <= 0).any():
        raise ValueError("group actual aggregation contains an empty observation")
    return grouped, len(actual)


def write_roundtrip(frame: pd.DataFrame, path: Path, float_columns: list[str]) -> str:
    frame.to_csv(path, index=False, float_format="%.17g")
    reread = pd.read_csv(path, float_precision="round_trip")
    if list(reread.columns) != list(frame.columns) or len(reread) != len(frame):
        raise AssertionError(f"CSV round-trip schema/row count failed: {path.name}")
    for col in float_columns:
        if not np.array_equal(reread[col].to_numpy(dtype="float64"), frame[col].to_numpy(dtype="float64")):
            raise AssertionError(f"CSV round-trip lost float64 precision in {col}")
    if not reread.ts.astype(str).equals(frame.ts.astype(str)):
        # CSV parser stringifies timezone timestamps with an equivalent but stable ISO format.
        parsed = sc.to_ts(reread.ts)
        if not np.array_equal(parsed.to_numpy(), frame.ts.to_numpy()):
            raise AssertionError(f"CSV round-trip changed timestamps in {path.name}")
    return sha256_file(path)


def export(year: int, outdir: Path = OUT) -> dict:
    verify_revision()
    outdir.mkdir(parents=True, exist_ok=True)
    delta_path = outdir / f"group_delta_{year}.csv"
    actual_path = outdir / f"actual_group_{year}.csv"
    manifest_path = outdir / f"handoff_manifest_{year}.json"
    if any(path.exists() for path in (delta_path, actual_path, manifest_path)):
        raise FileExistsError("SM68 handoff outputs exist; export refuses to overwrite them")

    baseline_path = SM67_DIR / f"baseline_{year}_sites.parquet"
    candidate_path = SM67_DIR / f"candidate_{year}_sites.parquet"
    result_path = SM67_DIR / f"result_{year}.json"
    result_bytes = result_path.read_bytes()
    result = json.loads(result_bytes)
    source_hashes = {
        "sm67_baseline_parquet": sha256_file(baseline_path),
        "sm67_candidate_parquet": sha256_file(candidate_path),
        "sm67_result_json": sha256_bytes(result_bytes),
    }
    if source_hashes["sm67_baseline_parquet"] != result["prediction_hashes"]["baseline"]:
        raise ValueError("SM67 baseline hash differs from its frozen result JSON")
    if source_hashes["sm67_candidate_parquet"] != result["prediction_hashes"]["candidate"]:
        raise ValueError("SM67 candidate hash differs from its frozen result JSON")

    comp_bytes = main_bytes("predictions/submissions/composition_ens_v12.csv")
    jh_bytes = main_bytes(JH_PATHS[year])
    source_hashes["composition_csv"] = sha256_bytes(comp_bytes)
    source_hashes["jh_validation_csv"] = sha256_bytes(jh_bytes)
    sites_path = Path(sc.DATA) / "sites.csv"
    source_hashes["sites_csv"] = sha256_file(sites_path)
    if source_hashes["composition_csv"] != COMPOSITION_SHA or source_hashes["jh_validation_csv"] != JH_SHA[year]:
        raise ValueError("pinned JH source hash mismatch")

    from io import BytesIO
    composition = pd.read_csv(BytesIO(comp_bytes)).sort_values("site_id").reset_index(drop=True)
    sites = sc.load_sites()
    reference = pd.DataFrame({"site_id": sites.site_id,
                              "group": sites.current_group.map({"A": "G1", "B": "G2"})})
    if not composition.equals(reference.sort_values("site_id").reset_index(drop=True)):
        raise ValueError("pinned JH composition differs from reference composition")
    start, end = PERIODS[year]
    begin, finish = sc.window(start, end)
    ts_grid = pd.date_range(begin, finish, freq="h", tz=sc.TZ)
    base = pd.read_parquet(baseline_path)
    cand = pd.read_parquet(candidate_path)
    delta_group = build_group_delta(base, cand, composition, ts_grid, int(result["eval_hours"]))

    generation_path = Path(sc.DATA) / "train" / "generation.parquet"
    source_hashes["generation_parquet"] = sha256_file(generation_path)
    generation = pd.read_parquet(generation_path, columns=["site_id", "ts", "energy"])
    actual_group, observed_site_hours = build_actual_groups(generation, sites, composition, begin, finish)

    delta_hash = write_roundtrip(delta_group, delta_path, ["delta_kwh"])
    actual_hash = write_roundtrip(actual_group, actual_path,
                                  ["actual_kwh", "observed_capacity_kw"])
    delta_read = pd.read_csv(delta_path, float_precision="round_trip")
    if not np.array_equal(delta_read.delta_kwh.to_numpy(dtype="float64"),
                          delta_group.delta_kwh.to_numpy(dtype="float64")):
        raise AssertionError("group delta CSV differs from original in-memory aggregation")
    manifest = {
        "schema_version": 1,
        "experiment": "SM68 peak delta transfer CSV handoff",
        "year": year,
        "main_sha": MAIN_SHA,
        "source_hashes": source_hashes,
        "output_hashes": {"group_delta_csv": delta_hash, "actual_group_csv": actual_hash},
        "schemas": {
            "group_delta_csv": ["group", "ts", "delta_kwh"],
            "actual_group_csv": ["group", "ts", "actual_kwh", "observed_sites", "observed_capacity_kw"],
        },
        "site_count": 253,
        "support_hours": int(delta_group.ts.nunique()),
        "support_start_kst": str(delta_group.ts.min()),
        "support_end_kst": str(delta_group.ts.max()),
        "delta_group_rows": int(len(delta_group)),
        "all_253_sites_each_support_timestamp": True,
        "actual_group_rows": int(len(actual_group)),
        "actual_group_rows_by_group": {g: int((actual_group.group == g).sum()) for g in sc.GROUPS},
        "actual_observed_site_hours": observed_site_hours,
        "actual_start_kst": str(actual_group.ts.min()),
        "actual_end_kst": str(actual_group.ts.max()),
        "actual_rows_are_observed_only_no_zero_fill": True,
        "timestamp_rule": "Asia/Seoul right-closed scoring.window (start, end]",
        "float_csv_format": "%.17g; pandas float_precision=round_trip verified",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, choices=(2023, 2024), default=2024)
    parser.add_argument("--outdir", type=Path, default=OUT)
    args = parser.parse_args()
    result = export(args.year, args.outdir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
