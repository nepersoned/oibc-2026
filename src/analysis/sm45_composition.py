"""Locked SM45 limited-composition fit/holdout experiment."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import composition as co
import features as F
import scoring as sc
from sm39_group_site_integration import hourly_penalties

OUT = ROOT / "outputs" / "sm45"


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    caps = sites.set_index("site_id").capacity_kw.reindex(comp.index).to_numpy(float)
    ref = (comp == "G1").to_numpy(float)
    seed_paths = [ROOT / "outputs" / f"val_sm45_a1_s{s}_sites.parquet" for s in (7, 21, 42)]
    # This Site3 mean is the same A1 model used in B0; the individual files are hashed.
    frames = [pd.read_parquet(p) for p in seed_paths]
    for x in frames:
        x["ts"] = sc.to_ts(x.ts)
    pred = frames[0][["site_id", "ts"]].copy()
    vals = []
    for f in frames:
        v = pred.merge(f[["site_id", "ts", "kwh"]], on=["site_id", "ts"], validate="one_to_one").kwh.to_numpy(float)
        vals.append(v)
    pred["kwh"] = np.mean(vals, axis=0)
    pred.to_parquet(OUT / "a1_site3_2024_composition_eval.parquet", index=False)

    # Fit interval uses the exact right-closed target-day convention.
    fit_start, fit_end = "2024-06-01", "2024-12-01"
    R, w = co.residuals(str(OUT / "a1_site3_2024_composition_eval.parquet"), fit_start, fit_end, sites)
    actual_fit = sc.load_actual(fit_start, fit_end)
    ts = pd.date_range(*sc.window(fit_start, fit_end), freq="h")
    ts = ts.tz_localize(sc.TZ) if ts.tz is None else ts.tz_convert(sc.TZ)
    ts_all = pd.DatetimeIndex(np.tile(ts.to_numpy(), len(sites)))
    ts_all = ts_all.tz_localize(sc.TZ) if ts_all.tz is None else ts_all.tz_convert(sc.TZ)
    elev, _, _ = F.solar(ts_all, np.repeat(sites.lat.to_numpy(), len(ts)),
                         np.repeat(sites.lon.to_numpy(), len(ts)))
    expected = pd.DataFrame({"site_id": sites.site_id.repeat(len(ts)), "ts": np.tile(ts, len(sites)),
                             "daylight": elev > 0})
    day = expected[expected.daylight]
    observed = actual_fit.assign(daylight=True).merge(day[["site_id", "ts"]], on=["site_id", "ts"], how="inner")
    counts = observed.groupby("site_id").size().reindex(sites.site_id, fill_value=0).to_numpy()
    denom = day.groupby("site_id").size().reindex(sites.site_id, fill_value=0).to_numpy()
    coverage = np.divide(counts, denom, out=np.zeros_like(counts, dtype=float), where=denom > 0)
    movable = coverage >= 0.80
    x, fit_obj = co.local_search(ref, R, w, caps, max_rounds=50, movable_mask=movable,
                                 max_changed=10, min_group_capacity=20_100)
    changed = sites.loc[x != ref, "site_id"].astype(str).tolist()
    if len(changed) > 10:
        raise AssertionError("selected composition exceeds 10 changed sites")
    chosen = pd.Series(np.where(x > 0.5, "G1", "G2"), index=sites.site_id)
    if not co.feasible(x, caps, 20_100):
        raise AssertionError("selected composition violates capacity constraints")

    start, end = "2024-12-01", "2025-06-01"
    actual = sc.load_actual(start, end)
    smp = sc.load_smp()
    holdout = sc.window(start, end)
    holdpred = pred[(pred.ts >= holdout[0]) & (pred.ts <= holdout[1])].copy()
    ref_w = sc.score(holdpred, comp, actual, smp)["W"]
    new_w = sc.score(holdpred, chosen, actual, smp)["W"]
    ref_h = hourly_penalties(holdpred, actual, comp, smp).groupby("ts").pen.sum()
    new_h = hourly_penalties(holdpred, actual, chosen, smp).groupby("ts").pen.sum()
    pair = pd.concat([ref_h.rename("ref"), new_h.rename("new")], axis=1).fillna(0)
    delta = pair.new.to_numpy() - pair.ref.to_numpy()
    rng = np.random.default_rng(7)
    block, n, b = 168, len(delta), 5000
    boot = np.empty(b)
    for i in range(b):
        ix = []
        while len(ix) < n:
            s = int(rng.integers(0, n))
            ix.extend((s + np.arange(block)) % n)
        boot[i] = delta[np.asarray(ix[:n])].sum()
    monthly_ref = ref_h.groupby(ref_h.index.strftime("%Y-%m")).sum()
    monthly_new = new_h.groupby(new_h.index.strftime("%Y-%m")).sum()
    monthly = {m: {"reference_W": float(monthly_ref[m]), "candidate_W": float(monthly_new[m]),
                   "delta_W": float(monthly_new[m] - monthly_ref[m]),
                   "change_pct": float(100 * (monthly_new[m] / monthly_ref[m] - 1))}
               for m in monthly_ref.index}
    # Retrospective diagnostic only; these observations do not alter the selected composition.
    p23s = [ROOT / "outputs" / f"val_sm45_a1_s{s}_2023_sites.parquet" for s in (7, 21, 42)]
    f23 = [pd.read_parquet(p) for p in p23s]
    for f in f23:
        f["ts"] = sc.to_ts(f.ts)
    p23 = f23[0][["site_id", "ts"]].copy()
    p23["kwh"] = np.mean([p23.merge(f[["site_id", "ts", "kwh"]], on=["site_id", "ts"],
                                      validate="one_to_one").kwh.to_numpy(float) for f in f23], axis=0)
    a23 = sc.load_actual("2023-06-01", "2024-06-01")
    p23w = sc.window("2023-06-01", "2024-06-01")
    p23 = p23[(p23.ts >= p23w[0]) & (p23.ts <= p23w[1])]
    retrospective_2023 = {"reference_W": float(sc.score(p23, comp, a23, smp)["W"]),
                          "candidate_W": float(sc.score(p23, chosen, a23, smp)["W"])}
    retrospective_2023["delta_W"] = retrospective_2023["candidate_W"] - retrospective_2023["reference_W"]
    caps_by = {g: float(sites.set_index("site_id").capacity_kw[chosen == g].sum()) for g in ("G1", "G2")}
    result = {
        "experiment": "SM45 limited composition, A1 weekday Site3 only",
        "fit_interval_right_closed": [fit_start, fit_end], "holdout_interval_right_closed": [start, end],
        "fit_reference_objective": float(co.objective(ref, R, w)), "fit_selected_objective": float(fit_obj),
        "mover_criterion": "selection-window observed daylight coverage >= 0.80; daylight elevation > 0",
        "movable_sites": int(movable.sum()), "mover_coverage_min": float(coverage[movable].min()) if movable.any() else None,
        "changed_sites": changed, "changed_count": len(changed), "capacity_kw": caps_by,
        "holdout_reference_W": float(ref_w), "holdout_candidate_W": float(new_w),
        "holdout_delta_W": float(new_w - ref_w), "holdout_change_pct": float(100 * (new_w / ref_w - 1)),
        "monthly_holdout": monthly,
        "retrospective_2023_diagnostic_only": retrospective_2023,
        "bootstrap": {"repetitions": b, "block_hours": block, "seed": 7,
                      "mean_delta_W": float(boot.mean()), "ci95": np.quantile(boot, [.025, .975]).tolist()},
        "input_sha256": {str(p): digest(p) for p in seed_paths + p23s},
        "observed_site_hours_fit": int(len(actual_fit)), "observed_site_hours_holdout": int(len(actual)),
        "interpretation": "unobserved site-hour residuals are omitted from the objective, not assumed error-free",
    }
    (OUT / "composition_a1_site_only.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame({"site_id": sites.site_id, "group": chosen.to_numpy()}).to_csv(OUT / "composition_a1_site_only.csv", index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
