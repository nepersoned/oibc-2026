"""Score SM45 calendar-mode forecasts and site/group blend alternatives."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc
from analysis.sm39_group_site_integration import block_bootstrap, hourly_penalties, redistribute, sha256
from analysis.sm43_group_bagging import average_site_frames

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "sm45"


def site_paths(mode: str, year: int) -> list[Path]:
    suffix = "_2023" if year == 2023 else ""
    if mode == "A0":
        return [ROOT / "outputs" / f"val_sm37_noext_repro{suffix}_sites.parquet"] + [
            ROOT / "outputs" / f"val_sm41_baseseed{s}{suffix}_sites.parquet" for s in (21, 42)]
    return [ROOT / "outputs" / f"val_sm45_{mode.lower()}_s{s}{suffix}_sites.parquet" for s in (7, 21, 42)]


def evaluate(year: int, mode: str, composition: pd.Series, sites: pd.DataFrame,
             smp: pd.Series, actual: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    start, end = f"{year}-06-01", f"{year+1}-06-01"
    pa, pb = sc.window(start, end)
    times = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    inputs = site_paths(mode, year)
    for p in inputs:
        if not p.exists():
            raise FileNotFoundError(p)
    site = average_site_frames([pd.read_parquet(p) for p in inputs])
    group = None
    if mode != "A0":
        gp_path = OUT / f"group_{mode.lower()}_{year}.parquet"
    else:
        gp_path = ROOT / "outputs" / "sm39" / f"group_pred_{year}.parquet"
    if not gp_path.exists():
        raise FileNotFoundError(gp_path)
    group = pd.read_parquet(gp_path)
    group["ts"] = sc.to_ts(group.ts)
    group = group.sort_values(["group", "ts"]).reset_index(drop=True)
    if len(group) != 2 * len(times) or group.duplicated(["group", "ts"]).any():
        raise ValueError(f"{mode} {year}: Group grid invalid")

    predictions = {"B0_site_only": site,
                   "B1_site_group_20": redistribute(site, group, sites, composition, 0.2, times)}
    detail_by_model, summary = {}, {"mode": mode, "year": year,
                                    "actual_site_hours": int(len(actual)), "hours": int(len(times)),
                                    "site_prediction_inputs": {str(p): sha256(p) for p in inputs},
                                    "group_prediction_input": str(gp_path),
                                    "group_prediction_sha256": sha256(gp_path), "models": {}}
    obs_site = actual[["site_id", "ts", "energy"]].merge(
        site.rename(columns={"kwh": "site_pred"}), on=["site_id", "ts"], how="left", validate="one_to_one")
    if obs_site.site_pred.isna().any():
        raise ValueError("site ensemble does not cover observed rows")
    site_mae = float((obs_site.site_pred - obs_site.energy).abs().mean())
    site_bias = float((obs_site.site_pred - obs_site.energy).mean())
    group_actual = actual.assign(group=actual.site_id.map(composition)).groupby(
        ["group", "ts"], as_index=False).energy.sum().rename(columns={"energy": "act"})
    group_raw = group[["group", "ts", "pred"]]
    raw_cmp = group_actual.merge(group_raw, on=["group", "ts"], how="left", validate="one_to_one")
    raw_cmp["err"] = raw_cmp["pred"] - raw_cmp.act
    summary["group_direct_full_capacity_mae_kwh_vs_observed_sum"] = float(raw_cmp.err.abs().mean())
    summary["group_direct_full_capacity_bias_kwh_vs_observed_sum"] = float(raw_cmp.err.mean())

    for name, pred in predictions.items():
        detail = hourly_penalties(pred, actual, composition, smp)
        independent_w = float(detail.pen.sum())
        official_w = float(sc.score(pred, composition, actual, smp)["W"])
        if not np.isclose(independent_w, official_w, rtol=0, atol=1e-5):
            raise AssertionError(f"W mismatch {mode} {year} {name}: {independent_w} vs {official_w}")
        totals = detail.groupby(["group", "ts"], as_index=False).agg(act=("act", "sum"), pred=("pred", "sum"))
        totals["err"] = totals.pred - totals.act
        hourly = detail.groupby("ts").pen.sum().reindex(times, fill_value=0)
        monthly = detail.assign(month=detail.ts.dt.strftime("%Y-%m")).groupby("month").pen.sum()
        path = OUT / f"{year}_{mode}_{name}_sites.parquet"
        pred.to_parquet(path, index=False)
        summary["models"][name] = {
            "W": independent_w,
            "W_by_group": {str(g): float(x) for g, x in detail.groupby("group").pen.sum().items()},
            "W_11_15": float(detail.loc[detail.ts.dt.hour.between(11, 15), "pen"].sum()),
            "monthly_W": {str(k): float(v) for k, v in monthly.items()},
            "site_MAE_kWh": site_mae,
            "site_signed_bias_kWh": site_bias,
            "group_observed_sum_MAE_kWh": float(totals.err.abs().mean()),
            "group_observed_sum_signed_bias_kWh": float(totals.err.mean()),
            "site_prediction_sha256": sha256(path),
        }
        detail_by_model[name] = (detail, hourly, monthly, totals)
    b0, b1 = detail_by_model["B0_site_only"], detail_by_model["B1_site_group_20"]
    summary["blend_delta_W_B1_minus_B0"] = summary["models"]["B1_site_group_20"]["W"] - summary["models"]["B0_site_only"]["W"]
    summary["blend_delta_W_by_group"] = {
        str(g): float(summary["models"]["B1_site_group_20"]["W_by_group"][str(g)] - summary["models"]["B0_site_only"]["W_by_group"][str(g)])
        for g in sc.GROUPS}
    summary["blend_monthly_delta_W"] = {str(k): float(b1[2].get(k, 0) - b0[2].get(k, 0)) for k in b0[2].index}
    summary["blend_delta_W_11_15"] = summary["models"]["B1_site_group_20"]["W_11_15"] - summary["models"]["B0_site_only"]["W_11_15"]
    summary["group_prediction_vs_observed_error_correlation"] = float(
        b0[3].merge(b1[3], on=["group", "ts", "act"], suffixes=("_site", "_mix"))[
            ["err_site", "err_mix"]].corr().iloc[0, 1])
    # Site-only and mixed model paired bootstrap on complete hourly group penalties.
    delta_mix_site = b1[1].to_numpy() - b0[1].to_numpy()
    if year == 2024:
        summary["B1_minus_B0_bootstrap_2024"] = block_bootstrap(delta_mix_site, 168, 5000, 7)
    monthly_frame = pd.DataFrame({"B0_site_only": b0[2], "B1_site_group_20": b1[2]})
    monthly_frame["delta_W"] = monthly_frame.B1_site_group_20 - monthly_frame.B0_site_only
    monthly_frame.to_csv(OUT / f"{year}_{mode}_monthly.csv", index_label="month")
    return summary, predictions["B0_site_only"], predictions["B1_site_group_20"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sites = sc.load_sites()
    composition = sc.reference_composition(sites)
    smp = sc.load_smp()
    result = {"experiment": "SM45 calendar-safe scoring", "composition": "reference", "alpha": 0.2,
              "calendar_mode": __import__("features").CAL_MODE, "years": {}}
    for year in (2023, 2024):
        actual = sc.load_actual(f"{year}-06-01", f"{year+1}-06-01")
        result["years"][str(year)] = {}
        for mode in ("A0", "A1", "A2"):
            if mode != "A0" and not (OUT / f"group_{mode.lower()}_{year}.parquet").exists():
                continue
            try:
                summary, _, _ = evaluate(year, mode, composition, sites, smp, actual)
            except FileNotFoundError as exc:
                if mode == "A0":
                    raise
                summary = {"status": "Not Run", "reason": str(exc)}
            result["years"][str(year)][mode] = summary
    # Bootstrap every available calendar-mode blended candidate versus legacy A0.
    pa, pb = sc.window("2024-06-01", "2025-06-01")
    times = pd.date_range(pa, pb, freq="h").astype(f"datetime64[ns, {sc.TZ}]")
    comp = composition
    actual = sc.load_actual("2024-06-01", "2025-06-01")
    legacy_sites = average_site_frames([pd.read_parquet(p) for p in site_paths("A0", 2024)])
    legacy_group = pd.read_parquet(ROOT / "outputs" / "sm39" / "group_pred_2024.parquet")
    legacy = redistribute(legacy_sites, legacy_group, sites, comp, 0.2, times)
    legacy_hour = hourly_penalties(legacy, actual, comp, smp).groupby("ts").pen.sum().reindex(times, fill_value=0)
    for mode in ("A1", "A2"):
        paths = site_paths(mode, 2024)
        gp_path = OUT / f"group_{mode.lower()}_2024.parquet"
        if not all(p.exists() for p in paths) or not gp_path.exists():
            continue
        sp = average_site_frames([pd.read_parquet(p) for p in paths])
        gp = pd.read_parquet(gp_path)
        pred = redistribute(sp, gp, sites, comp, 0.2, times)
        hour = hourly_penalties(pred, actual, comp, smp).groupby("ts").pen.sum().reindex(times, fill_value=0)
        result["years"]["2024"][mode]["vs_A0_legacy_bootstrap"] = block_bootstrap(
            hour.to_numpy() - legacy_hour.to_numpy(), 168, 5000, 7)
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    rows = []
    for year, modes in result["years"].items():
        if "A0" in modes and "models" in modes["A0"]:
            baseline_w = modes["A0"]["models"]["B1_site_group_20"]["W"]
            for mode, data in modes.items():
                for model_name, metrics in data.get("models", {}).items():
                    metrics["delta_W_vs_A0"] = metrics["W"] - baseline_w
                    metrics["change_pct_vs_A0"] = 100 * metrics["delta_W_vs_A0"] / baseline_w
        for mode, data in modes.items():
            if data.get("status") == "Not Run":
                rows.append({"year": year, "mode": mode, "status": data["status"], "reason": data["reason"]})
                continue
            for model_name, metrics in data.get("models", {}).items():
                rows.append({"year": year, "mode": mode, "model": model_name, "status": "scored", **metrics})
    pd.DataFrame(rows).to_csv(OUT / "comparison.csv", index=False)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
