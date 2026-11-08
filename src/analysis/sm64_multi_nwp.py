"""SM64: add one broad-box GFS shortwave summary to the SM58 Site pilot.

Modes are deliberately staged: --audit-index checks DLWRF field support using
index text only; --extract reuses locally cached GFS DSWRF GRIBs for A/B periods;
--pilot performs the single-seed, common-row comparison.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_gfs as G  # noqa: E402
import features as F  # noqa: E402
import scoring as sc  # noqa: E402

OUT = ROOT / "outputs" / "sm64"
HEAD_AUDIT = ROOT / "outputs" / "sm58" / "gfs_index_head_audit.csv"
GRIB_CACHE = ROOT / "data_ext" / "gfs_spatial_full_2021_2024" / "grib"
LEADS = tuple(range(15, 40, 3))
SOURCE_START, SOURCE_END = "2022-06-01", "2026-05-31"
TRAIN_START, EVAL_START, EVAL_END = "2022-06-01", "2024-06-01", "2025-06-01"
BASELINE_PRED = ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet"
ADDED_FEATURE = "gfs2_dswrf_out"
PARAMS = {"random_state": 7}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def assert_environment() -> None:
    if F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise RuntimeError("SM64 requires weekday calendar, GFS enabled, and Open-Meteo disabled")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM64 forbids GEFS/UM/spatial/physics features")


def parse_dlwrf_index(text: str) -> tuple[int, int | None, int, str] | None:
    """Return byte range, averaging interval hours, and descriptor for DLWRF surface."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        p = line.split(":")
        if len(p) < 6 or p[3] != "DLWRF" or p[4] != "surface" or "ave fcst" not in p[5]:
            continue
        desc = p[5]
        interval = 0
        if "-" in desc.split(" hour")[0]:
            lo, hi = desc.split(" hour")[0].split("-")
            interval = int(hi) - int(lo)
        else:
            return None
        start = int(p[1])
        end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else None
        return start, end, interval, desc
    return None


def successful_index_rows(existing: pd.DataFrame) -> pd.Series:
    """Normalize CSV-inferred status types when resuming an index audit."""
    status_ok = pd.to_numeric(existing["status"], errors="coerce").eq(200)
    field_ok = existing["field_present"].astype(str).str.lower().eq("true")
    return status_ok & field_ok


def index_url(init: str, lead: int) -> str:
    return (f"https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{init}/00/atmos/"
            f"gfs.t00z.pgrb2.1p00.f{lead:03d}.idx")


def request_bytes(url: str, byte_range: tuple[int, int | None] | None = None,
                  tries: int = 5) -> bytes:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url)
            if byte_range:
                start, end = byte_range
                req.add_header("Range", f"bytes={start}-{'' if end is None else end}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                if byte_range and resp.status != 206:
                    raise RuntimeError(f"expected HTTP 206 byte range, got {resp.status}")
                return body
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                raise
            if attempt + 1 == tries:
                raise
        except Exception:
            if attempt + 1 == tries:
                raise
    raise RuntimeError(f"request failed: {url}")


def cutoff_audit() -> pd.DataFrame:
    audit = pd.read_csv(HEAD_AUDIT)
    audit["init_date"] = pd.to_datetime(audit.init_date).dt.strftime("%Y%m%d")
    for c in ("last_modified", "grib_last_modified"):
        audit[c] = pd.to_datetime(audit[c], utc=True, errors="coerce")
    audit["cutoff_eligible"] = (
        audit.status.eq(200) & audit.grib_status.eq(200)
        & audit.last_modified.notna() & audit.grib_last_modified.notna()
        & ((audit.last_modified.dt.hour < 8) | (audit.last_modified.dt.hour.eq(8)
            & audit.last_modified.dt.minute.eq(0) & audit.last_modified.dt.second.eq(0)))
        & ((audit.grib_last_modified.dt.hour < 8) | (audit.grib_last_modified.dt.hour.eq(8)
            & audit.grib_last_modified.dt.minute.eq(0) & audit.grib_last_modified.dt.second.eq(0)))
    )
    return audit


def audit_indexes() -> dict:
    """Index-only DLWRF field check across training, validation and submission support."""
    cutoff = cutoff_audit().set_index(["init_date", "lead"])
    target_days = pd.date_range(TRAIN_START, EVAL_END, freq="D")
    jobs = []
    for day in target_days:
        init = (day - pd.Timedelta(days=1)).strftime("%Y%m%d")
        for lead in LEADS:
            row = cutoff.loc[(init, lead)]
            if bool(row.cutoff_eligible):
                jobs.append((day.strftime("%Y-%m-%d"), init, lead))
    # The existing SM58 object-level audit already covers every submission day.
    # Check DLWRF field indexing at one date per target month for this support-only period.
    future_days = pd.DatetimeIndex([pd.Timestamp(y, m, 15) for y, m in
        [(2025, 6), (2025, 7), (2025, 8), (2025, 9), (2025, 10), (2025, 11),
         (2025, 12), (2026, 1), (2026, 2), (2026, 3), (2026, 4), (2026, 5)]])
    for day in future_days:
        init = (day - pd.Timedelta(days=1)).strftime("%Y%m%d")
        for lead in LEADS:
            row = cutoff.loc[(init, lead)]
            if bool(row.cutoff_eligible):
                jobs.append((day.strftime("%Y-%m-%d"), init, lead))

    OUT.mkdir(parents=True, exist_ok=True)
    audit_path = OUT / "dlwrf_index_audit.csv"
    existing = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
    if len(existing):
        existing["init_date"] = existing.init_date.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8)
        existing["lead"] = existing.lead.astype(int)
    successful = successful_index_rows(existing)
    done = set(zip(existing.loc[successful, "init_date"], existing.loc[successful, "lead"]))
    jobs = [j for j in jobs if (j[1], j[2]) not in done]

    def one(job):
        target, init, lead = job
        url = index_url(init, lead)
        try:
            raw = request_bytes(url)
            parsed = parse_dlwrf_index(raw.decode("utf-8"))
            if parsed is None:
                return {"target_day": target, "init_date": init, "lead": lead,
                        "status": 200, "index_bytes": len(raw), "field_present": False}
            start, end, interval, desc = parsed
            return {"target_day": target, "init_date": init, "lead": lead,
                    "status": 200, "index_bytes": len(raw), "field_present": True,
                    "range_start": start, "range_end": end, "field_interval_h": interval,
                    "descriptor": desc}
        except urllib.error.HTTPError as exc:
            return {"target_day": target, "init_date": init, "lead": lead,
                    "status": exc.code, "index_bytes": 0, "field_present": False}
        except Exception as exc:
            return {"target_day": target, "init_date": init, "lead": lead,
                    "status": f"ERROR:{type(exc).__name__}", "index_bytes": 0, "field_present": False}

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 500 == 0:
                print(f"DLWRF index-only: {i}/{len(futures)}", flush=True)
                checkpoint = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
                checkpoint.drop_duplicates(["init_date", "lead"], keep="last").to_csv(audit_path, index=False)
    detail = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    detail = detail.drop_duplicates(["init_date", "lead"], keep="last").sort_values(["target_day", "lead"])
    detail.to_csv(OUT / "dlwrf_index_audit.csv", index=False)
    detail["target_day"] = pd.to_datetime(detail.target_day)
    day = detail.groupby("target_day").agg(
        available_leads=("field_present", "sum"), lead_rows=("lead", "nunique"), all_fields=("field_present", "all"),
        index_bytes=("index_bytes", "sum"),
    ).reset_index()
    day["all_fields"] = day.all_fields & day.lead_rows.eq(len(LEADS))
    periods = {
        "train_2022_06_to_2024_05": ("2022-06-01", "2024-06-01"),
        "validation_2024_06_to_2025_05": ("2024-06-01", "2025-06-01"),
    }
    summary = {"source_feature": ADDED_FEATURE, "index_requests": int(len(detail)),
        "index_response_bytes": int(detail.index_bytes.sum()),
        "index_http_200": int(pd.to_numeric(detail.status, errors="coerce").eq(200).sum()),
        "field_lead_present": int(detail.field_present.sum()),
        "periods": {}}
    for name, (start, end) in periods.items():
        mask = day.target_day.ge(start) & day.target_day.lt(end)
        selected = day.loc[mask]
        expected_days = int((pd.Timestamp(end) - pd.Timestamp(start)).days)
        summary["periods"][name] = {"target_days": expected_days,
            "all_9_leads_with_DLWRF": int(selected.all_fields.sum()),
            "coverage_pct": 100 * int(selected.all_fields.sum()) / expected_days if expected_days else None,
            "lead_presence": {str(int(k)): int(v) for k, v in detail.loc[
                detail.target_day.ge(start) & detail.target_day.lt(end)].groupby("lead").field_present.sum().items()}}
    future = detail[detail.target_day >= "2025-06-01"].copy()
    future["month"] = pd.to_datetime(future.target_day).dt.strftime("%Y-%m")
    summary["submission_monthly_sample"] = {k: {"sample_days": int(g.target_day.nunique()),
        "sample_leads": int(g.field_present.sum()), "expected_leads": int(len(g)),
        "field_pct": 100 * float(g.field_present.mean())} for k, g in future.groupby("month")}
    # Persist lead metadata for extraction without retaining index response bodies.
    (OUT / "dlwrf_index_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def grid_box_means(message: bytes) -> tuple[float, float]:
    """Return fixed inner and outer box means from a global regular 1-degree GRIB."""
    import eccodes
    # ecCodes is not thread safe; keep only GRIB decoding serialized.
    with G._LOCK:
        h = eccodes.codes_new_from_message(message)
        try:
            values = eccodes.codes_get_values(h)
            nj, ni = int(eccodes.codes_get(h, "Nj")), int(eccodes.codes_get(h, "Ni"))
            lat0 = float(eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees"))
            lon0 = float(eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees"))
            dlat = float(eccodes.codes_get(h, "jDirectionIncrementInDegrees"))
            dlon = float(eccodes.codes_get(h, "iDirectionIncrementInDegrees"))
            if (ni, nj) != (360, 181) or abs(dlat - 1) > 1e-5 or abs(dlon - 1) > 1e-5:
                raise ValueError(f"unexpected GFS grid: {(ni, nj, dlat, dlon)}")
            grid = values.reshape(nj, ni)
            def mean_box(lat_start, lat_stop, lon_start, lon_stop):
                lat_ix = [round((lat0 - x) / dlat) for x in range(lat_start, lat_stop + 1)]
                lon_ix = [round((x - lon0) / dlon) % ni for x in range(lon_start, lon_stop + 1)]
                return float(grid[np.ix_(lat_ix, lon_ix)].mean())
            inner = mean_box(34, 38, 126, 129)
            outer = mean_box(32, 39, 124, 131)
            return inner, outer
        finally:
            eccodes.codes_release(h)


def extract_feature() -> dict:
    """Download only DLWRF byte ranges for model train/eval dates; no full GRIB files."""
    audit = pd.read_csv(OUT / "dlwrf_index_audit.csv")
    audit["init_date"] = audit.init_date.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8)
    audit["lead"] = audit.lead.astype(int)
    audit["field_present"] = audit.field_present.astype(str).str.lower().eq("true")
    required = audit[(audit.target_day >= TRAIN_START) & (audit.target_day < EVAL_END)].copy()
    cutoff = cutoff_audit().set_index(["init_date", "lead"])
    required = required[required.apply(lambda r: bool(cutoff.loc[(r.init_date, int(r.lead))].cutoff_eligible), axis=1)]
    if not required.field_present.all():
        incomplete = required.groupby("target_day").field_present.all()
        raise RuntimeError(f"DLWRF message absent in model period for {int((~incomplete).sum())} dates")
    raw_dir = OUT / "dlwrf_ranges"
    raw_dir.mkdir(parents=True, exist_ok=True)

    def one(r):
        key = f"{r.init_date}_f{int(r.lead):03d}.grib2"
        path = raw_dir / key
        if path.exists():
            body = path.read_bytes()
        else:
            end = None if pd.isna(r.range_end) else int(r.range_end)
            body = request_bytes(index_url(r.init_date, int(r.lead)).removesuffix(".idx"),
                                 (int(r.range_start), end))
            path.write_bytes(body)
        if not body.startswith(b"GRIB") or not body.endswith(b"7777"):
            raise ValueError(f"invalid ranged GRIB message: {key}")
        inner, outer = grid_box_means(body)
        return {"target_day": r.target_day, "init_date": r.init_date, "lead": int(r.lead),
                "inner": inner, "outer": outer, "interval_h": int(r.field_interval_h),
                "message_bytes": len(body)}

    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, r) for r in required.itertuples(index=False)]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 500 == 0:
                print(f"DLWRF range extraction: {i}/{len(futures)}", flush=True)
    lead_data = pd.DataFrame(rows).sort_values(["init_date", "lead"])
    lead_data.to_parquet(OUT / "dlwrf_by_lead.parquet", index=False)
    # Reconstruct 3-hour averages and map each lead to the same three right-closed hours as fetch_gfs2.
    hourly = []
    for init, group in lead_data.groupby("init_date", sort=True):
        by_lead = {int(r.lead): r for r in group.itertuples(index=False)}
        init_ts = pd.Timestamp(init, tz="UTC")
        for lead in LEADS[1:]:
            if lead not in by_lead:
                continue
            row = by_lead[lead]
            value = float(row.outer)
            if int(row.interval_h) == 6:
                prev = by_lead.get(lead - 3)
                if prev is None:
                    value = np.nan
                else:
                    value = 2 * value - float(prev.outer)
            end_local = (init_ts + pd.Timedelta(hours=lead)).tz_convert(sc.TZ)
            for ts in pd.date_range(end_local - pd.Timedelta(hours=2), end_local, freq="h"):
                target_day = (ts - pd.Timedelta(hours=1)).floor("D").tz_localize(None)
                if target_day.strftime("%Y-%m-%d") == (pd.Timestamp(init) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"):
                    hourly.append({"ts": ts, ADDED_FEATURE: value})
    frame = pd.DataFrame(hourly).sort_values("ts").drop_duplicates("ts")
    frame.to_parquet(OUT / "gfs2_dlwrf_hourly.parquet", index=False)
    return {"messages": int(len(lead_data)), "range_bytes": int(lead_data.message_bytes.sum()),
            "hourly_rows": int(len(frame)), "hourly_support_start": str(frame.ts.min()),
            "hourly_support_end": str(frame.ts.max()), "hourly_missing": int(frame[ADDED_FEATURE].isna().sum()),
            "feature_sha256": sha256(OUT / "gfs2_dlwrf_hourly.parquet")}


def run_pilot() -> dict:
    import model as M
    import pipeline as P
    from sm58_controlled_pilot import calc_hourly_w, summarize, predict_in_batches

    assert_environment()
    feature_path = OUT / "gfs2_dlwrf_hourly.parquet"
    if not feature_path.exists() or not BASELINE_PRED.exists():
        raise FileNotFoundError("run --extract first and retain the frozen SM58 baseline")
    start, end = EVAL_START, EVAL_END
    pred_a, pred_b = sc.window(start, end)
    train_start = pred_a - pd.DateOffset(years=2)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    extra = pd.read_parquet(feature_path)
    extra["ts"] = sc.to_ts(extra.ts)
    ext = ext.merge(extra, on="ts", how="inner", validate="one_to_one")
    required = ["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens", ADDED_FEATURE]
    ext = ext.dropna(subset=required).sort_values("ts")
    eligible_ts = pd.DatetimeIndex(ext.ts)
    expected_train_hours = int((pred_a - train_start).total_seconds() // 3600)
    train_source_ts = eligible_ts[(eligible_ts >= train_start) & (eligible_ts < pred_a)]
    if len(train_source_ts) < int(np.ceil(.95 * expected_train_hours)):
        raise RuntimeError("common-source training timestamp support below 95%")
    gen = P.load_generation(train_start, pred_a)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(eligible_ts)].copy()
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    design_train = F.build_rich(gen[["site_id", "ts", "energy"]], site_features, fa, fb, reg, ext)
    features_b = [c for c in P.select_rich_features(design_train) if c != "site_code"]
    if ADDED_FEATURE not in features_b:
        features_b.append(ADDED_FEATURE)
    features_a = [c for c in features_b if c != ADDED_FEATURE]
    if design_train[ADDED_FEATURE].isna().any():
        raise RuntimeError("added NWP feature missing on selected training rows")
    model_a = M.fit(design_train, weight="none", feats=features_a, params=PARAMS, cat=[])
    model_b = M.fit(design_train, weight="none", feats=features_b, params=PARAMS, cat=[])

    # Predict the complete model hour grid, then score only the shared eligible observed mask.
    eval_ts = eligible_ts[(eligible_ts >= pred_a) & (eligible_ts <= pred_b)]
    site_a = predict_in_batches(model_a, sites, site_features, eval_ts, pred_a, pred_b, fa, fb, reg, ext, features_a)
    site_b = predict_in_batches(model_b, sites, site_features, eval_ts, pred_a, pred_b, fa, fb, reg, ext, features_b)
    del model_a, model_b, design_train
    actual = sc.load_actual(start, end)
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual[actual.ts.isin(eval_ts)]
    smp = sc.load_smp()
    hourly_a = calc_hourly_w(site_a, comp, actual, smp)
    hourly_b = calc_hourly_w(site_b, comp, actual, smp)
    result = {"status": "PILOT_COMPLETED", "evaluation": {"start": str(pred_a), "end": str(pred_b),
        "eligible_timestamps": int(len(eval_ts)), "observed_site_hours": int(len(actual)),
        "training_source_timestamps": int(len(train_source_ts)), "training_site_hours": int(len(gen))},
        "feature": ADDED_FEATURE, "features_A": features_a, "features_B_added": [ADDED_FEATURE],
        "model": {"fset": "rich", "seed": 7, "weight": "none", "calendar": "weekday",
            "parameters": M.PARAMS, "n_train_features_A": len(features_a), "n_train_features_B": len(features_b)},
        "A": summarize(site_a, comp, actual, smp, hourly_a),
        "B": summarize(site_b, comp, actual, smp, hourly_b),
        "delta_B_minus_A_W": float(hourly_b.w.sum() - hourly_a.w.sum()),
        "independent_hourly_W_A": float(hourly_a.w.sum()), "independent_hourly_W_B": float(hourly_b.w.sum()),
        "source_feature_sha256": sha256(feature_path),
        "sm58_baseline_prediction_sha256": sha256(BASELINE_PRED),
        "input_sha256": {"generation": sha256(Path(sc.DATA) / "train" / "generation.parquet"),
            "WA": sha256(Path(sc.DATA) / "train" / "forecast_wa.parquet"),
            "WB": sha256(Path(sc.DATA) / "train" / "forecast_wb.parquet")}}
    result["bootstrap_168h_ci"] = None if result["delta_B_minus_A_W"] >= 0 else "pending stable/monthly gate"
    OUT.mkdir(parents=True, exist_ok=True)
    site_a.to_parquet(OUT / "pilot_A_sites.parquet", index=False)
    site_b.to_parquet(OUT / "pilot_B_sites.parquet", index=False)
    result["prediction_sha256"] = {"A": sha256(OUT / "pilot_A_sites.parquet"),
                                   "B": sha256(OUT / "pilot_B_sites.parquet")}
    (OUT / "pilot_result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--audit-index", action="store_true")
    g.add_argument("--extract", action="store_true")
    g.add_argument("--pilot", action="store_true")
    args = p.parse_args()
    if args.audit_index:
        out = audit_indexes()
    elif args.extract:
        out = extract_feature()
    else:
        out = run_pilot()
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
