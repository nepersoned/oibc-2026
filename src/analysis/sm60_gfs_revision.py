"""SM60: same-model GFS run-revision feature audit and controlled pilot.

Stage 1 only audits D-2 00Z public indexes and object timestamps. It does not
download GRIB payloads. Full extraction/fitting is intentionally a separate,
preregistered follow-up after the audit gate passes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import fetch_gfs as G  # noqa: E402

OUT = ROOT / "outputs" / "sm60"
TARGET_START = date(2022, 6, 1)
TARGET_END = date(2025, 5, 31)
D2_LEADS = tuple(range(39, 64, 3))  # f039 anchor, then 3-hour averages through f063
TARGET_LEADS_D1 = tuple(range(16, 40))
TARGET_LEADS_D2 = tuple(range(40, 64))
FIELD_KEYS = {"DSWRF": ("DSWRF", "surface"), "TCDC": ("TCDC", "entire atmosphere")}
TZ = "Asia/Seoul"
BASE = G.BASE


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def request(url: str, method: str, timeout: int = 30):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = r.read() if method == "GET" else b""
        return r.status, dict(r.headers.items()), payload


def safe_request(url: str, method: str, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return request(url, method)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return e.code, dict(e.headers.items()), b""
            last = e
        except Exception as e:  # bounded retry on public archive transport errors
            last = e
        time.sleep(0.4 * (i + 1))
    return None, {}, str(last).encode()


def parse_average_windows(index_text: str, lead: int) -> dict[str, str]:
    found = {}
    for line in index_text.splitlines():
        p = line.split(":")
        if len(p) < 6 or p[3:5] not in (["DSWRF", "surface"], ["TCDC", "entire atmosphere"]):
            continue
        if "ave fcst" not in p[5]:
            continue
        key = p[3]
        found[key] = p[5].strip()
    return found


def audit_lead(target: date, lead: int) -> dict:
    init = target - timedelta(days=2)
    cutoff = pd.Timestamp(init, tz="UTC") + pd.Timedelta(hours=32)
    stem = f"gfs.t00z.pgrb2.1p00.f{lead:03d}"
    candidates = [
        (f"{BASE}/gfs.{init:%Y%m%d}/00/atmos/{stem}.idx", f"{BASE}/gfs.{init:%Y%m%d}/00/atmos/{stem}"),
        (f"{BASE}/gfs.{init:%Y%m%d}/00/{stem}.idx", f"{BASE}/gfs.{init:%Y%m%d}/00/{stem}"),
    ]
    selected = None
    idx_status = None
    for idx_url, grib_url in candidates:
        # The index GET provides both GRIB field metadata and its Last-Modified.
        idx_status, idx_headers, index_bytes = safe_request(idx_url, "GET")
        if idx_status == 200:
            selected = (idx_url, grib_url, idx_headers, index_bytes)
            break
    if selected is None:
        return {"target_date": target.isoformat(), "init_date": init.isoformat(), "lead": lead,
                "idx_status": idx_status, "grib_status": None, "idx_last_modified": None,
                "grib_last_modified": None, "cutoff_utc": cutoff.isoformat(), "index_bytes": 0,
                "field_windows": {}, "eligible": False, "error": "no index object"}
    idx_url, grib_url, idx_headers, index_bytes = selected
    grib_status, grib_headers, _ = safe_request(grib_url, "HEAD")
    idx_lm = pd.to_datetime(idx_headers.get("Last-Modified"), utc=True, errors="coerce")
    grib_lm = pd.to_datetime(grib_headers.get("Last-Modified"), utc=True, errors="coerce")
    windows = parse_average_windows(index_bytes.decode("utf-8", errors="replace"), lead)
    lm_ok = pd.notna(idx_lm) and pd.notna(grib_lm) and idx_lm <= cutoff and grib_lm <= cutoff
    fields_ok = set(windows) == set(FIELD_KEYS)
    expected_start = 6 * ((lead - 3) // 6)
    expected_desc = f"{expected_start}-{lead} hour ave fcst"
    desc_ok = all(windows.get(k) == expected_desc for k in FIELD_KEYS)
    return {
        "target_date": target.isoformat(), "init_date": init.isoformat(), "lead": lead,
        "idx_url": idx_url, "grib_url": grib_url, "idx_status": idx_status,
        "grib_status": grib_status, "idx_last_modified": str(idx_lm) if pd.notna(idx_lm) else None,
        "grib_last_modified": str(grib_lm) if pd.notna(grib_lm) else None,
        "cutoff_utc": cutoff.isoformat(), "idx_bytes": int(idx_headers.get("Content-Length", 0) or 0),
        "grib_bytes": int(grib_headers.get("Content-Length", 0) or 0), "index_bytes": len(index_bytes),
        "field_windows": windows, "fields_ok": bool(fields_ok), "interval_ok": bool(desc_ok),
        "eligible": bool(idx_status == 200 and grib_status == 200 and lm_ok and fields_ok and desc_ok),
        "error": None,
    }


def audit_run(target: date) -> list[dict]:
    # Fetch nine index/metadata pairs concurrently for each target date.
    with ThreadPoolExecutor(max_workers=9) as pool:
        return list(pool.map(lambda lead: audit_lead(target, lead), D2_LEADS))


def local_d1_support(targets: pd.DatetimeIndex) -> pd.Series:
    ok = []
    raw = ROOT / "data_ext" / "gfs_raw"
    for target in targets:
        init = (target.date() - timedelta(days=1)).strftime("%Y%m%d")
        path = raw / f"{init}.npz"
        if not path.is_file():
            ok.append(False)
            continue
        try:
            arr = np.load(path)["rows"]
            ok.append(arr.shape == (len(G.LEADS), 5) and np.isfinite(arr[:, 1:]).all())
        except Exception:
            ok.append(False)
    return pd.Series(ok, index=targets)


def message_range(index_text: str, short_name: str, level: str, desc: str) -> tuple[int, int]:
    lines = index_text.strip().splitlines()
    for i, line in enumerate(lines):
        p = line.split(":")
        if len(p) >= 6 and p[3] == short_name and p[4] == level and p[5].strip() == desc:
            start = int(p[1])
            end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else start + 5_000_000
            return start, end
    raise KeyError(f"missing GRIB message: {short_name}:{level}:{desc}")


def fetch_d2_target(target: date, day_audit: pd.DataFrame) -> tuple[date, int]:
    """Download only DSWRF/TCDC indexed byte ranges for one audited D-2 run."""
    init = target - timedelta(days=2)
    cache = ROOT / "data_ext" / "gfs_d2_raw" / f"{init:%Y%m%d}.npz"
    if cache.is_file():
        try:
            arr = np.load(cache)["rows"]
            if arr.shape == (len(D2_LEADS), 5) and np.isfinite(arr[:, 1:]).all():
                return target, int(cache.stat().st_size)
        except Exception:
            pass
        cache.unlink(missing_ok=True)
    recs, transferred = [], 0
    for _, r in day_audit.sort_values("lead").iterrows():
        if not bool(r.eligible):
            raise ValueError(f"attempt to fetch ineligible D-2 run {target} f{int(r.lead):03d}")
        status, _, raw_index = safe_request(r.idx_url, "GET")
        if status != 200:
            raise RuntimeError(f"failed to retrieve audited index for {target} f{int(r.lead):03d}: {status}")
        transferred += len(raw_index)
        idx_text = raw_index.decode("utf-8", errors="replace")
        lead = int(r.lead)
        expected_start = 6 * ((lead - 3) // 6)
        desc = f"{expected_start}-{lead} hour ave fcst"
        vals = [lead]
        for short, level in (FIELD_KEYS["DSWRF"], FIELD_KEYS["TCDC"]):
            first, last = message_range(idx_text, short, level, desc)
            decode_error = None
            for attempt in range(3):
                payload = G.get(r.grib_url, (first, last))
                if payload is None:
                    decode_error = RuntimeError("range request returned no payload")
                    continue
                transferred += len(payload)
                try:
                    value = G.box_mean(payload)
                    decode_error = None
                    break
                except Exception as exc:  # archive range responses can be transiently truncated
                    decode_error = exc
            if decode_error is not None:
                raise RuntimeError(f"failed range decode {target} f{lead:03d} {short}: {decode_error}")
            vals.extend([value, int(lead - expected_start)])
        recs.append(vals)
    arr = np.asarray(recs, dtype=float)
    if arr.shape != (len(D2_LEADS), 5) or not np.isfinite(arr[:, 1:]).all():
        raise RuntimeError(f"invalid D-2 raw array {target}: {arr.shape}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, rows=arr)
    tmp.replace(cache)
    return target, transferred


def extract_d2(audit_csv: Path, workers: int = 12) -> dict:
    audit = pd.read_csv(audit_csv)
    audit["eligible"] = audit.eligible.astype(bool)
    audit["target_date"] = pd.to_datetime(audit.target_date).dt.date
    per_day = audit.groupby("target_date").eligible.all()
    d1_ok = local_d1_support(pd.DatetimeIndex(pd.to_datetime(per_day.index)))
    allowed = [d for d, ok in per_day.items() if ok and bool(d1_ok.loc[pd.Timestamp(d)])]
    bytes_in = 0
    extracted, failures = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_d2_target, d, audit[audit.target_date == d]): d for d in allowed}
        for i, fut in enumerate(as_completed(futures), 1):
            target = futures[fut]
            try:
                _, nbytes = fut.result()
                bytes_in += nbytes
                extracted.append(target)
            except Exception as exc:
                failures.append({"target_date": target.isoformat(), "error": repr(exc)})
            if i % 100 == 0:
                print(f"processed audited D-2 target days {i}/{len(allowed)}; valid={len(extracted)} excluded={len(failures)}", flush=True)
    feature = build_revision_features(extracted)
    path = OUT / "gfs_revision_features.parquet"
    feature.to_parquet(path, index=False)
    meta = {"requested_days": int(len(per_day)), "d2_eligible_days": int(per_day.sum()),
            "d1_local_days": int(d1_ok.sum()), "common_days_attempted": int(len(allowed)),
            "common_days_extracted": int(len(extracted)), "failed_target_days": failures,
            "revision_rows": int(len(feature)), "unique_hours": int(feature.ts.nunique()),
            "range_and_index_bytes": int(bytes_in), "box": "same SM58 fixed 20 points 34..38N, 126..129E",
            "d1_leads": list(range(18, 40, 3)), "d2_leads": list(range(42, 64, 3)),
            "d1_cache_sha256_sample": sha256(ROOT / "data_ext" / "gfs_raw" / f"{(TARGET_START-timedelta(days=1)):%Y%m%d}.npz"),
            "output": str(path), "output_sha256": sha256(path)}
    (OUT / "gfs_revision_features.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def deaverage_d2(rows: np.ndarray) -> dict[int, tuple[float, float]]:
    by_lead = {int(r[0]): r for r in rows}
    out = {}
    for lead in D2_LEADS[1:]:
        row = by_lead[lead]
        values = []
        for vi, wi in ((1, 2), (3, 4)):
            value, width = row[vi], row[wi]
            if width == 3:
                values.append(value)
            elif width == 6:
                prev = by_lead.get(lead - 3)
                values.append(2 * value - prev[vi] if prev is not None else np.nan)
            else:
                values.append(np.nan)
        if not np.isfinite(values).all():
            raise ValueError(f"invalid de-averaging at D-2 lead {lead}")
        out[lead] = (max(values[0], 0.0), values[1])
    return out


def build_revision_features(targets: list[date]) -> pd.DataFrame:
    raw1 = ROOT / "data_ext" / "gfs_raw"
    raw2 = ROOT / "data_ext" / "gfs_d2_raw"
    records = []
    for target in targets:
        day1, day2 = target - timedelta(days=1), target - timedelta(days=2)
        a1 = np.load(raw1 / f"{day1:%Y%m%d}.npz")["rows"]
        a2 = np.load(raw2 / f"{day2:%Y%m%d}.npz")["rows"]
        d1 = G.deaverage(a1)
        d2 = deaverage_d2(a2)
        init1 = pd.Timestamp(day1, tz="UTC")
        for lead1 in range(18, 40, 3):
            lead2 = lead1 + 24
            if lead1 not in d1 or lead2 not in d2:
                raise ValueError(f"same-valid-time runs do not align for target {target}, leads {lead1}/{lead2}")
            end = init1 + pd.Timedelta(hours=lead1)
            for ts in pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert(TZ):
                records.append({"ts": ts, "gfs_dswrf_revision": d1[lead1][0] - d2[lead2][0],
                                "gfs_tcdc_revision": d1[lead1][1] - d2[lead2][1]})
    frame = pd.DataFrame(records).sort_values("ts").reset_index(drop=True)
    if frame.ts.duplicated().any() or frame[["gfs_dswrf_revision", "gfs_tcdc_revision"]].isna().any().any():
        raise ValueError("revision feature timestamp or value invalid")
    return frame


def run_pilot(revision_path: Path, out_dir: Path = OUT) -> dict:
    """Fit SM58-matched seed-7 baseline and two-revision candidate on a common mask."""
    import importlib.metadata
    import features as F
    import model as M
    import pipeline as P
    import scoring as sc
    from analysis.sm58_controlled_pilot import (
        calc_hourly_w, predict_in_batches, sha256_file, summarize, bootstrap_delta,
    )

    if F.CAL_MODE != "weekday" or F.EXT_SOURCES != "no_openmeteo" or not F.USE_GFS:
        raise RuntimeError("SM60 requires weekday calendar, GFS enabled, Open-Meteo disabled")
    if F.USE_GEFS or F.USE_UM or F.SPATIAL_MODE != "none" or F.PHYSICS_MODE != "none":
        raise RuntimeError("SM60 forbids GEFS/UM/spatial/physics feature sources")
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_a, pred_b = sc.window("2024-06-01", "2025-06-01")
    train_a = pred_a - pd.DateOffset(years=2)
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    layers = pd.read_parquet(ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet")
    layers["ts"] = sc.to_ts(layers.ts)
    rev = pd.read_parquet(revision_path)
    rev["ts"] = sc.to_ts(rev.ts)
    if rev.ts.duplicated().any() or rev[["gfs_dswrf_revision", "gfs_tcdc_revision"]].isna().any().any():
        raise ValueError("invalid D-2 revision feature artifact")
    ext = F.load_ext("mean")
    ext["ts"] = sc.to_ts(ext.ts)
    ext = ext.merge(layers, on="ts", how="inner", validate="one_to_one")
    required = ["ext_gfs_ghi", "ext_gfs_tcc", "ext_ghi_ens", "gfs_lcdc", "gfs_mcdc", "gfs_hcdc",
                ]
    base_ext = ext.dropna(subset=required).sort_values("ts")
    base_eligible_ts = pd.DatetimeIndex(base_ext.ts)
    sm58_original_train_hours = int(((base_eligible_ts >= train_a) & (base_eligible_ts < pred_a)).sum())
    ext = base_ext.merge(rev, on="ts", how="inner", validate="one_to_one")
    ext = ext.dropna(subset=["gfs_dswrf_revision", "gfs_tcdc_revision"]).sort_values("ts")
    eligible_ts = pd.DatetimeIndex(ext.ts)
    train_ts = eligible_ts[(eligible_ts >= train_a) & (eligible_ts < pred_a)]
    eval_ts = eligible_ts[(eligible_ts >= pred_a) & (eligible_ts <= pred_b)]
    expected = json.loads((ROOT / "outputs" / "sm58" / "pilot_result.json").read_text(encoding="utf-8"))
    expected_features = expected["features"]["A"]
    expected_eval = pd.read_parquet(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet", columns=["ts"])
    expected_eval_ts = pd.DatetimeIndex(sc.to_ts(expected_eval.ts).unique()).sort_values()
    eval_alignment = eval_ts.equals(expected_eval_ts)
    if not eval_alignment:
        missing = expected_eval_ts.difference(eval_ts)
        extra = eval_ts.difference(expected_eval_ts)
        raise RuntimeError(f"D-2 common evaluation mask differs from frozen SM58 A: missing={len(missing)}, extra={len(extra)}")
    if len(train_ts) < int(np.ceil(.95 * ((pred_a - train_a).total_seconds() / 3600))):
        raise RuntimeError(f"common training timestamp support below 95%: {len(train_ts)}")

    gen = P.load_generation(train_a, pred_a)
    gen["ts"] = sc.to_ts(gen.ts)
    gen = gen[gen.ts.isin(train_ts)].copy()
    gen["smp"] = gen.ts.map(sc.load_smp())
    fa = F.prep_forecast(F.load_forecast("train", "wa", F.WA_ALL), "wa", F.WA_ALL)
    fb = F.prep_forecast(F.load_forecast("train", "wb", F.WB_ALL), "wb", F.WB_ALL)
    reg = F.region_means(fa, fb)
    site_features = sites.drop(columns=["wa_dist", "wb_dist"], errors="ignore")
    d_train = F.build_rich(gen[["site_id", "ts", "energy", "smp"]], site_features, fa, fb, reg, ext)
    rev_cols = ["gfs_dswrf_revision", "gfs_tcdc_revision"]
    layer_cols = ["gfs_lcdc", "gfs_mcdc", "gfs_hcdc"]
    baseline_exclusions = ["site_code"] + layer_cols
    features_b = P.select_rich_features(d_train, drop_features=baseline_exclusions)
    features_a = P.select_rich_features(d_train, drop_features=baseline_exclusions + rev_cols)
    if set(features_b) - set(features_a) != set(rev_cols):
        raise RuntimeError("A/B feature difference is not exactly the two registered revision columns")
    if features_a != expected_features:
        raise RuntimeError("SM58 A feature inventory differs; refusing to call this a matched baseline")
    d_train = d_train.dropna(subset=["energy"])
    model_a = M.fit(d_train, weight="none", feats=features_a, params={"random_state": 7}, cat=[])
    site_a = predict_in_batches(model_a, sites, site_features, eligible_ts, pred_a, pred_b, fa, fb, reg, ext, features_a)
    del model_a
    model_b = M.fit(d_train, weight="none", feats=features_b, params={"random_state": 7}, cat=[])
    site_b = predict_in_batches(model_b, sites, site_features, eligible_ts, pred_a, pred_b, fa, fb, reg, ext, features_b)
    del model_b, d_train

    actual = sc.load_actual("2024-06-01", "2025-06-01")
    actual["ts"] = sc.to_ts(actual.ts)
    actual = actual[actual.ts.isin(eval_ts)]
    smp = sc.load_smp()
    score_a = sc.score(site_a, comp, actual, smp)
    score_b = sc.score(site_b, comp, actual, smp)
    hour_a = calc_hourly_w(site_a, comp, actual, smp)
    hour_b = calc_hourly_w(site_b, comp, actual, smp)
    w_a, w_b = float(hour_a.w.sum()), float(hour_b.w.sum())
    if not np.isclose(w_a, score_a["W"], rtol=0, atol=1e-6) or not np.isclose(w_b, score_b["W"], rtol=0, atol=1e-6):
        raise AssertionError("independent hourly settlement W differs from scoring.py")

    old_a = pd.read_parquet(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet")
    old_a["ts"] = sc.to_ts(old_a.ts)
    old_common = old_a[old_a.ts.isin(eval_ts)].sort_values(["site_id", "ts"])
    sm58_saved_score = sc.score(old_common, comp, actual, smp)
    new_common = site_a[site_a.ts.isin(eval_ts)].sort_values(["site_id", "ts"])
    old_cmp = old_common.merge(new_common, on=["site_id", "ts"], suffixes=("_sm58", "_refit"),
                               validate="one_to_one")
    max_old_delta = float((old_cmp.kwh_sm58 - old_cmp.kwh_refit).abs().max())
    delta = w_b - w_a
    a_day = hour_a.groupby("ts").w.sum().rename("A_W")
    b_day = hour_b.groupby("ts").w.sum().rename("B_W")
    daily_delta = pd.concat([a_day, b_day], axis=1).assign(delta=lambda x: x.B_W - x.A_W)
    daily_delta["target_day"] = (daily_delta.index - pd.Timedelta(hours=1)).date
    rev_eval = rev[rev.ts.isin(eval_ts)].copy()
    rev_eval["target_day"] = (rev_eval.ts - pd.Timedelta(hours=1)).dt.date
    daily_revision = rev_eval.groupby("target_day").agg(
        dswrf_revision_abs_mean=("gfs_dswrf_revision", lambda x: float(x.abs().mean())),
        tcdc_revision_abs_mean=("gfs_tcdc_revision", lambda x: float(x.abs().mean())),
    )
    high_revision = {}
    for col in daily_revision.columns:
        cut = float(daily_revision[col].quantile(0.9))
        high_days = set(daily_revision.index[daily_revision[col] >= cut])
        selected = daily_delta[daily_delta.target_day.isin(high_days)]
        high_revision[col] = {"top_decile_cutoff": cut, "days": int(selected.target_day.nunique()),
                              "A_W": float(selected.A_W.sum()), "B_W": float(selected.B_W.sum()),
                              "delta_B_minus_A": float(selected.delta.sum())}
    result = {
        "A_W": w_a, "B_W": w_b, "delta_B_minus_A": delta,
        "SM58_saved_A_W_same_eval_mask": float(sm58_saved_score["W"]),
        "bootstrap_168h_ci": bootstrap_delta(hour_a, hour_b) if delta < 0 else None,
        "A_diagnostics": summarize(site_a, comp, actual, smp, hour_a),
        "B_diagnostics": summarize(site_b, comp, actual, smp, hour_b),
        "high_revision_day_diagnostics": high_revision,
        "independent_hourly_W_A": w_a, "independent_hourly_W_B": w_b,
        "same_eval_timestamp_mask_as_SM58": eval_alignment,
        "common_eval_timestamps": int(len(eval_ts)), "observed_eval_site_hours": int(len(actual)),
        "SM58_original_train_source_hours": sm58_original_train_hours,
        "common_train_source_hours": int(len(train_ts)), "train_site_hours": int(len(gen)) if "gen" in locals() else None,
        "SM58_saved_A_prediction_rows_in_common_eval": int(len(old_common)),
        "refit_A_prediction_max_abs_vs_SM58_saved_A": max_old_delta,
        "features": {"A": features_a, "B_added": rev_cols},
        "parameters": {"fset": "rich", "seed": 7, "weight": "none", "composition": "reference",
                       "train_years": 2, "calendar": "weekday", "ext": "GFS only; no Open-Meteo",
                       "model": M.PARAMS},
        "sha256": {"revision_features": sha256(revision_path),
                   "sm58_A_predictions": sha256(ROOT / "outputs" / "sm58" / "pilot_A_sites.parquet"),
                   "sm58_result": sha256(ROOT / "outputs" / "sm58" / "pilot_result.json"),
                   "layer_features": sha256(ROOT / "outputs" / "sm58" / "gfs_cloud_layers.parquet"),
                   "D1_hourly_source": sha256(ROOT / "data_ext" / "gfs_hourly_partial_full.parquet")},
        "versions": {pkg: importlib.metadata.version(pkg) for pkg in ("lightgbm", "pandas", "numpy")},
    }
    site_a.to_parquet(out_dir / "pilot_A_sites.parquet", index=False)
    site_b.to_parquet(out_dir / "pilot_B_sites.parquet", index=False)
    result["prediction_sha256"] = {"A": sha256(out_dir / "pilot_A_sites.parquet"),
                                   "B": sha256(out_dir / "pilot_B_sites.parquet")}
    (out_dir / "pilot_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def summarize(rows: pd.DataFrame) -> dict:
    rows["target_date"] = pd.to_datetime(rows.target_date)
    per_day = rows.groupby("target_date").eligible.all()
    d1 = local_d1_support(pd.DatetimeIndex(per_day.index))
    common = per_day & d1
    windows = {
        "train_2022_06_to_2024_05": ("2022-06-01", "2024-06-01"),
        "validation_2024_06_to_2025_05": ("2024-06-01", "2025-06-01"),
    }
    result = {"targets": int(len(per_day)), "d2_days_all_leads_fields_and_cutoff": int(per_day.sum()),
              "d1_local_raw_days": int(d1.sum()), "common_days": int(common.sum()),
              "index_get_requests": int(len(rows)), "index_response_bytes": int(rows.index_bytes.sum()),
              "lead_objects": int(len(rows)), "lead_object_pairs_pass": int(rows.eligible.sum()),
              "all_field_windows_ok_objects": int(rows.interval_ok.sum()), "windows": {}}
    for name, (a, b) in windows.items():
        mask = (per_day.index >= pd.Timestamp(a)) & (per_day.index < pd.Timestamp(b))
        n = int(mask.sum())
        result["windows"][name] = {
            "target_days": n, "d2_eligible_days": int(per_day.to_numpy()[mask].sum()),
            "d1_local_days": int(d1.to_numpy()[mask].sum()), "common_days": int(common.to_numpy()[mask].sum()),
            "common_pct": float(100 * common.to_numpy()[mask].sum() / n) if n else None,
        }
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=TARGET_START.isoformat())
    ap.add_argument("--end", default=TARGET_END.isoformat())
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--extract", action="store_true", help="extract eligible D-2 DSWRF/TCDC indexed byte ranges")
    ap.add_argument("--pilot", action="store_true", help="fit matched SM58 A/B models after extraction")
    args = ap.parse_args()
    if not 1 <= args.workers <= 16:
        raise SystemExit("workers must be in 1..16")
    if args.extract:
        result = extract_d2(OUT / "d2_index_audit.csv", workers=args.workers)
        print(json.dumps(result, indent=2), flush=True)
        return
    if args.pilot:
        result = run_pilot(OUT / "gfs_revision_features.parquet")
        print(json.dumps(result, indent=2), flush=True)
        return
    days = [d.date() for d in pd.date_range(args.start, args.end, freq="D")]
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_run, d): d for d in days}
        for i, f in enumerate(as_completed(futures), 1):
            rows.extend(f.result())
            if i % 100 == 0:
                print(f"audited target dates {i}/{len(days)}", flush=True)
    frame = pd.DataFrame(rows).sort_values(["target_date", "lead"])
    csv_path = OUT / "d2_index_audit.csv"
    frame.to_csv(csv_path, index=False)
    summary = summarize(frame)
    summary.update({"target_start": args.start, "target_end": args.end,
                    "d2_run": "target D minus 2 days at 00 UTC", "cutoff": "init +32h = D-1 08 UTC = D-1 17 KST",
                    "leads": list(D2_LEADS), "fields": FIELD_KEYS,
                    "timestamp_logic": "D-2 raw 6h/3h averages de-averaged to the same 3h valid intervals as D-1; hourly revision repeats each 3h interval over its constituent hours",
                    "csv": str(csv_path), "csv_sha256": sha256(csv_path)})
    (OUT / "d2_index_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
