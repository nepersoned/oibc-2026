"""Build and validate the two fixed SM46 calendar-safe candidates.

Run from repository root with the repository virtual environment:
    .venv/Scripts/python.exe src/analysis/sm46_submission_candidates.py

This script trains Site seeds 7/21/42 once for the 2025-06..2025-06
submission window, trains the reference Group seed 100 once, writes candidate
CSVs only under outputs/sm46, reload-checks them, and runs the official local
format validator. It never uploads to the competition portal.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "sm46"
OUT.mkdir(parents=True, exist_ok=True)

# Set the lineage controls before importing feature/model modules.
os.environ.update({
    "OIBC_CAL_MODE": "weekday",
    "OIBC_EXT_SOURCES": "no_openmeteo",
    "OIBC_GFS": "0",
    "OIBC_GEFS": "0",
    "OIBC_UM": "0",
    "OIBC_SRC": "prov",
    "OIBC_SPATIAL": "none",
    "OIBC_PHYSICS": "none",
    "OIBC_CAL": "1",  # OIBC_CAL_MODE takes precedence; retained only for legacy compatibility.
    "OIBC_EXT2024": "0",
    "OIBC_ENS": "stable",
})
os.environ.pop("OIBC_WX2", None)
os.environ.pop("OIBC_SM42_FEATURES", None)

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "analysis"))
import agg_model as AM  # noqa: E402
import features as F  # noqa: E402
import pipeline as PL  # noqa: E402
import scoring as SC  # noqa: E402
from sm39_group_site_integration import redistribute  # noqa: E402

TRAIN_END = "2025-06-01"
PRED_END = "2026-06-01"
SEEDS = (7, 21, 42)
ALPHA = 0.2
COMP_RESEARCH = ROOT / "outputs" / "sm45" / "composition_a1_site_only.csv"
COMP_RESEARCH_SHA256 = "2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def write_feature_manifest() -> dict:
    original_site = PL.select_rich_features
    original_group = AM.feats_of
    captured: dict[str, list[str]] = {}
    forbidden_exact = {"is_hol", "is_off", "off_run"}
    forbidden_prefix = ("ext_", "phys_", "sp_", "hat_")

    def audit_columns(cols: list[str], family: str) -> list[str]:
        bad = [c for c in cols if c in forbidden_exact or c.startswith(forbidden_prefix)]
        require(not bad, f"{family} input contains prohibited feature columns: {bad}")
        captured[family] = list(cols)
        return cols

    def site_selector(d: pd.DataFrame, drops=None):
        return audit_columns(original_site(d, drops), "site")

    def group_selector(d: pd.DataFrame):
        return audit_columns(original_group(d), "group")

    PL.select_rich_features = site_selector
    AM.feats_of = group_selector
    return captured


def make_forecast_frame(site_pred: pd.DataFrame, comp: pd.Series) -> pd.DataFrame:
    x = site_pred.assign(group=site_pred.site_id.map(comp))
    require(x.group.notna().all(), "unmapped site in candidate composition")
    out = x.groupby(["group", "ts"], as_index=False).kwh.sum()
    out = out.rename(columns={"kwh": "forecast_kwh"}).sort_values(["group", "ts"]).reset_index(drop=True)
    out["ts"] = out.ts.dt.strftime("%Y-%m-%d %H:%M:%S%z").str.replace(
        r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
    return out[["group", "ts", "forecast_kwh"]]


def main() -> None:
    started = time.time()
    require(F.CAL_MODE == "weekday", f"unexpected calendar mode {F.CAL_MODE}")
    require(not F.USE_GFS and not F.USE_GEFS and not F.USE_UM, "external weather toggles are enabled")
    require(F.SPATIAL_MODE == "none" and F.PHYSICS_MODE == "none", "external spatial/physics mode enabled")
    require(not os.environ.get("OIBC_WX2"), "WX2 feature flag must be unset")
    require(COMP_RESEARCH.exists(), f"SM45 fixed composition missing: {COMP_RESEARCH}")
    require(sha256(COMP_RESEARCH) == COMP_RESEARCH_SHA256,
            "SM45 research composition hash differs from the frozen expected artifact")

    sites = SC.load_sites()
    comp_ref = SC.reference_composition(sites)
    comp_opt = SC.read_composition(str(COMP_RESEARCH))
    for label, comp in (("reference", comp_ref), ("SM45 composition", comp_opt)):
        errors = SC.check_composition(comp, sites)
        require(not errors, f"{label} invalid: {errors}")

    pa, pb = SC.window(TRAIN_END, PRED_END)
    train_a = pa - pd.DateOffset(years=2)
    feature_manifest = write_feature_manifest()
    site_paths = []
    for seed in SEEDS:
        path = OUT / f"site_seed{seed}_weekday_submit.parquet"
        if path.exists():
            raise RuntimeError(f"refusing to overwrite existing checkpoint: {path}")
        print(f"[Site] seed={seed}, train=[{train_a},{pa}), forecast=[{pa},{pb}]", flush=True)
        pred = PL.run(train_a, pa, pa, pb, "test", 2, "none", "rich",
                      {"random_state": seed}, "none", None, ["site_code"])
        pred.to_parquet(path, index=False)
        site_paths.append(path)

    expected_ts = pd.date_range(pa, pb, freq="h")
    expected_ts = expected_ts.tz_localize(SC.TZ) if expected_ts.tz is None else expected_ts.tz_convert(SC.TZ)
    site_frames = []
    for path in site_paths:
        df = pd.read_parquet(path)
        df["ts"] = SC.to_ts(df.ts)
        expected_keys = pd.MultiIndex.from_product([sites.site_id, expected_ts], names=["site_id", "ts"])
        got = pd.MultiIndex.from_frame(df[["site_id", "ts"]])
        require(df.columns.tolist() == ["site_id", "ts", "kwh"], f"unexpected Site schema: {path}")
        require(got.is_unique and len(got) == len(expected_keys) and not len(expected_keys.difference(got)),
                f"incomplete/duplicate Site forecast grid: {path}")
        require(np.isfinite(df.kwh.to_numpy(float)).all() and (df.kwh >= 0).all(), f"invalid Site forecast: {path}")
        site_frames.append(df.sort_values(["site_id", "ts"]).reset_index(drop=True))
    base = site_frames[0][["site_id", "ts"]].copy()
    seed_arrays = []
    for frame in site_frames:
        require(frame[["site_id", "ts"]].equals(base), "seed forecast keys/order do not match")
        seed_arrays.append(frame.kwh.to_numpy(float))
    site_mean = base.assign(kwh=np.mean(seed_arrays, axis=0))
    site_mean_path = OUT / "site_seed_mean_weekday_submit.parquet"
    site_mean.to_parquet(site_mean_path, index=False)

    group_path = OUT / "group_seed100_weekday_submit.parquet"
    if group_path.exists():
        raise RuntimeError(f"refusing to overwrite existing checkpoint: {group_path}")
    import sys as _sys
    _sys.argv = ["agg_model.py", "--mode", "submit", "--train-years", "2", "--ext", "none",
                 "--min-cov", "0.3", "--params", "{}", "--out", str(group_path)]
    AM.main()
    gp = pd.read_parquet(group_path)
    gp["ts"] = SC.to_ts(gp.ts)
    require({"group", "ts", "pred", "cf_hat"}.issubset(gp.columns), "unexpected Group output schema")
    require(np.isfinite(gp.pred.to_numpy(float)).all() and (gp.pred >= 0).all(), "invalid Group predictions")

    grid = pd.DatetimeIndex(expected_ts)
    pred_ref = redistribute(site_mean, gp[["group", "ts", "pred"]], sites, comp_ref, ALPHA, grid)
    pred_comp = site_mean.copy()
    pred_ref = pred_ref.sort_values(["group", "ts"]) if "group" in pred_ref else pred_ref

    candidates = {
        "a1_ref": (comp_ref, pred_ref),
        "a1_comp": (comp_opt, pred_comp),
    }
    artifacts: dict[str, dict] = {}
    for suffix, (comp, site_prediction) in candidates.items():
        comp_path = OUT / f"composition_sm46_{suffix}.csv"
        forecast_path = OUT / f"forecast_sm46_{suffix}.csv"
        if suffix == "a1_comp":
            import shutil
            shutil.copy2(COMP_RESEARCH, comp_path)
        else:
            comp_out = comp.rename("group").rename_axis("site_id").reset_index()
            comp_out.to_csv(comp_path, index=False)
        forecast = make_forecast_frame(site_prediction, comp)
        forecast.to_csv(forecast_path, index=False)
        # Reload and compare grouped values to the values intended for serialization.
        reloaded = pd.read_csv(forecast_path)
        intended = make_forecast_frame(site_prediction, comp)
        intended["ts"] = pd.to_datetime(intended.ts, format="%Y-%m-%d %H:%M:%S%z", utc=True).dt.tz_convert(SC.TZ)
        reloaded["ts"] = pd.to_datetime(reloaded.ts, format="%Y-%m-%d %H:%M:%S%z", utc=True).dt.tz_convert(SC.TZ)
        require(reloaded[["group", "ts"]].equals(intended[["group", "ts"]]), f"reload keys differ: {suffix}")
        require(np.allclose(reloaded.forecast_kwh, intended.forecast_kwh, rtol=0, atol=1e-9),
                f"reload values differ: {suffix}")
        # Rebuild the site forecast by group and verify serialization still reflects the model output.
        expected_forecast = make_forecast_frame(site_prediction, comp)
        require(np.allclose(reloaded.forecast_kwh, expected_forecast.forecast_kwh, rtol=0, atol=1e-9),
                f"group aggregation mismatch: {suffix}")
        artifacts[suffix] = {
            "composition": str(comp_path), "forecast": str(forecast_path),
            "composition_sha256": sha256(comp_path), "forecast_sha256": sha256(forecast_path),
            "site_grid_rows": int(len(site_prediction)), "forecast_rows": int(len(reloaded)),
            "site_seed_inputs": {str(p): sha256(p) for p in site_paths},
            "site_mean_sha256": sha256(site_mean_path),
            "group_input_sha256": sha256(group_path) if suffix == "a1_ref" else None,
            "validator_exit_code": None,
        }
        import subprocess
        cmd = [sys.executable, str(ROOT / "src" / "validate_submission.py"),
               "--composition", str(comp_path), "--forecast", str(forecast_path)]
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        print(proc.stdout, end="", flush=True)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, flush=True)
        artifacts[suffix]["validator_exit_code"] = int(proc.returncode)
        artifacts[suffix]["validator_output"] = proc.stdout.strip()
        require(proc.returncode == 0, f"official validator failed for {suffix}: {proc.returncode}")

    manifest = {
        "experiment": "OIBC SM46 submission-ready calendar-safe candidates",
        "branch": "seongmin", "starting_revision": "2c20ee08ece286edb6c9e43b2ce135ae41572a7b",
        "calendar_mode": F.CAL_MODE,
        "controls": {k: os.environ.get(k) for k in ("OIBC_CAL_MODE", "OIBC_EXT_SOURCES", "OIBC_GFS",
                      "OIBC_GEFS", "OIBC_UM", "OIBC_SRC", "OIBC_SPATIAL", "OIBC_PHYSICS", "OIBC_WX2")},
        "train_window": {"start_inclusive": str(train_a), "end_exclusive": str(pa), "train_years": 2},
        "forecast_window_right_closed": {"start_exclusive": TRAIN_END + " 00:00 KST",
                                          "first": str(pa), "last": str(pb), "hours": len(expected_ts)},
        "site_model": {"type": "LightGBM rich", "seeds": list(SEEDS), "drop_features": ["site_code"],
                       "weight": "none", "ext": "none",
                       "params": [{**PL.M.PARAMS, "random_state": seed} for seed in SEEDS],
                       "feature_columns": feature_manifest.get("site")},
        "group_model": {"type": "LightGBM", "seed": 100, "min_cov": 0.3,
                        "params": {**AM.PARAMS, "random_state": 100},
                        "feature_columns": feature_manifest.get("group")},
        "versions": {"python": sys.version, "lightgbm": lgb.__version__, "pandas": pd.__version__,
                     "numpy": np.__version__},
        "blend_alpha_site_weight": 0.8,
        "fixed_comp_research_sha256": sha256(COMP_RESEARCH),
        "candidates": artifacts,
        "source_validation_artifacts": {str(p): sha256(p) for p in (
            ROOT / "outputs" / "val_sm45_a1_s7_2023_sites.parquet",
            ROOT / "outputs" / "val_sm45_a1_s21_2023_sites.parquet",
            ROOT / "outputs" / "val_sm45_a1_s42_2023_sites.parquet",
            ROOT / "outputs" / "val_sm45_a1_s7_sites.parquet",
            ROOT / "outputs" / "val_sm45_a1_s21_sites.parquet",
            ROOT / "outputs" / "val_sm45_a1_s42_sites.parquet",
            ROOT / "outputs" / "sm45" / "comparison.json",
            ROOT / "outputs" / "sm45" / "composition_a1_site_only.json",
        )},
        "elapsed_seconds": round(time.time() - started, 2),
        "portal_upload": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
