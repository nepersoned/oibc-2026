"""Index-object availability audit for SM#58; never downloads GRIB payloads."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

import pandas as pd

BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
# f015 is included as the left interpolation anchor for target lead 16.
LEADS = (15, 18, 21, 24, 27, 30, 33, 36, 39)


def probe(init_day: date, lead: int) -> dict:
    stem = f"gfs.t00z.pgrb2.1p00.f{lead:03d}"
    urls = (
        f"{BASE}/gfs.{init_day:%Y%m%d}/00/atmos/{stem}",
        f"{BASE}/gfs.{init_day:%Y%m%d}/00/{stem}",
    )
    started = time.monotonic()
    def head(url: str) -> tuple[object, object, object, str | None]:
        last_status, last_size, last_modified = None, None, None
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    return (resp.status, resp.headers.get("Content-Length"),
                            resp.headers.get("Last-Modified"), url)
            except urllib.error.HTTPError as exc:
                last_status = exc.code
                if exc.code in (403, 404):
                    break
                if attempt == 0:
                    time.sleep(0.25)
            except Exception as exc:  # bounded network retry for an audit probe
                last_status = f"ERROR:{type(exc).__name__}"
                if attempt == 0:
                    time.sleep(0.25)
        return last_status, last_size, last_modified, None

    index_status, index_size, index_modified, index_url = None, None, None, None
    grib_status, grib_size, grib_modified, grib_url = None, None, None, None
    for suffix in (".idx", ""):
        for base_url in urls:
            status, size, modified, used_url = head(base_url + suffix)
            if status == 200:
                if suffix == ".idx":
                    index_status, index_size, index_modified, index_url = status, size, modified, used_url
                else:
                    grib_status, grib_size, grib_modified, grib_url = status, size, modified, used_url
                break
            if suffix == ".idx":
                index_status, index_size = status, size
            else:
                grib_status, grib_size = status, size
        if suffix == ".idx" and index_status != 200:
            continue
    return {
        "init_date": init_day.isoformat(),
        "lead": lead,
        "status": index_status,
        "content_length": int(index_size) if index_size and str(index_size).isdigit() else None,
        "last_modified": index_modified,
        "url": index_url or urls[-1] + ".idx",
        "grib_status": grib_status,
        "grib_content_length": int(grib_size) if grib_size and str(grib_size).isdigit() else None,
        "grib_last_modified": grib_modified,
        "grib_url": grib_url or urls[-1],
        "elapsed_s": round(time.monotonic() - started, 3),
    }


def run(start: date, end: date, workers: int) -> list[dict]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    jobs = [(day, lead) for day in days for lead in LEADS]
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(probe, day, lead) for day, lead in jobs]
        for i, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if i % 1000 == 0:
                print(f"HEAD probes {i}/{len(jobs)}", flush=True)
    rows.sort(key=lambda x: (x["init_date"], x["lead"]))
    return rows


def inspect_field_sample(out: Path) -> dict:
    """Fetch monthly representative .idx text only to audit field/step semantics."""
    sample_days = [date(2021, 3, 22)]
    current = date(2021, 4, 15)
    while current <= date(2026, 5, 15):
        sample_days.append(current)
        year = current.year + (current.month == 12)
        month = 1 if current.month == 12 else current.month + 1
        current = date(year, month, 15)
    fields = ("LCDC", "MCDC", "HCDC", "TCDC", "DSWRF")

    def inspect_one(init_day: date, lead: int) -> tuple[dict, int]:
        name = f"gfs.t00z.pgrb2.1p00.f{lead:03d}.idx"
        urls = (
            f"{BASE}/gfs.{init_day:%Y%m%d}/00/atmos/{name}",
            f"{BASE}/gfs.{init_day:%Y%m%d}/00/{name}",
        )
        text, used_url, nbytes = None, None, 0
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=20) as response:
                    body = response.read()
                    text = body.decode("utf-8")
                    nbytes = len(body)
                    used_url = url
                    break
            except urllib.error.HTTPError as exc:
                if exc.code not in (403, 404):
                    raise
            except Exception:
                continue
        record = {"init_date": init_day.isoformat(), "lead": lead, "url": used_url,
                  "index_bytes": nbytes}
        lines = text.splitlines() if text else []
        for field in fields:
            matched = [line for line in lines if f":{field}:" in line]
            record[f"{field}_instant"] = sum(
                " hour fcst:" in line and "ave fcst" not in line for line in matched
            )
            record[f"{field}_average"] = sum("ave fcst" in line for line in matched)
        return record, nbytes

    rows, bytes_read = [], 0
    jobs = [(day, lead) for day in sample_days for lead in LEADS]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(inspect_one, day, lead) for day, lead in jobs]
        for i, future in enumerate(as_completed(futures), start=1):
            row, nbytes = future.result()
            rows.append(row)
            bytes_read += nbytes
            if i % 100 == 0:
                print(f"field index samples {i}/{len(jobs)}", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    csv_path = out / "gfs_field_index_samples.csv"
    frame.to_csv(csv_path, index=False)
    summary = {
        "sample_runs": len(sample_days), "leads_per_run": len(LEADS),
        "requests": len(rows), "response_payload_bytes": bytes_read,
        "all_sample_indexes_retrieved": bool(frame.url.notna().all()),
        "instantaneous_field_rows": {
            field: int((frame[f"{field}_instant"] > 0).sum()) for field in fields
        },
        "average_field_rows": {
            field: int((frame[f"{field}_average"] > 0).sum()) for field in fields
        },
        "csv": str(csv_path),
    }
    (out / "gfs_field_index_samples_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def summarize_cutoff_coverage(csv_path: Path, out_dir: Path) -> dict:
    frame = pd.read_csv(csv_path)
    frame["init_date"] = pd.to_datetime(frame.init_date)
    frame["index_lm"] = pd.to_datetime(frame.last_modified, utc=True, errors="coerce")
    frame["grib_lm"] = pd.to_datetime(frame.grib_last_modified, utc=True, errors="coerce")
    frame["cutoff"] = frame.init_date.dt.tz_localize("UTC") + pd.Timedelta(hours=8)
    frame["eligible_object"] = (frame.status.eq(200) & frame.grib_status.eq(200)
                                & frame.index_lm.le(frame.cutoff) & frame.grib_lm.le(frame.cutoff))
    windows = {
        "archive_2021_01_to_2025_05": ("2021-01-01", "2025-06-01"),
        "train_all": ("2021-06-01", "2025-06-01"),
        "train_2023_window": ("2021-06-01", "2023-06-01"),
        "val_2023_24": ("2023-06-01", "2024-06-01"),
        "train_2024_window": ("2022-06-01", "2024-06-01"),
        "val_2024_25": ("2024-06-01", "2025-06-01"),
        "eval_2025_26": ("2025-06-01", "2026-06-01"),
    }
    result = {}
    for label, (target_start, target_end_exclusive) in windows.items():
        init_start = pd.Timestamp(target_start) - pd.Timedelta(days=1)
        init_end = pd.Timestamp(target_end_exclusive) - pd.Timedelta(days=2)
        subset = frame[frame.init_date.between(init_start, init_end)]
        per_day = subset.groupby("init_date").eligible_object.agg(["sum", "count"])
        n_days = len(per_day)
        n_eligible = int((per_day["sum"] == len(LEADS)).sum())
        result[label] = {
            "target_start": target_start,
            "target_end_inclusive": (pd.Timestamp(target_end_exclusive) - pd.Timedelta(days=1)).date().isoformat(),
            "target_dates": n_days,
            "all_leads_before_cutoff": n_eligible,
            "eligible_pct": round(100 * n_eligible / n_days, 4) if n_days else 0.0,
            "index_http_200_objects": int(subset.status.eq(200).sum()),
            "grib_http_200_objects": int(subset.grib_status.eq(200).sum()),
            "late_index_objects": int((subset.status.eq(200) & subset.index_lm.gt(subset.cutoff)).sum()),
            "late_grib_objects": int((subset.grib_status.eq(200) & subset.grib_lm.gt(subset.cutoff)).sum()),
            "missing_index_objects": int((~subset.status.eq(200)).sum()),
            "missing_grib_objects": int((~subset.grib_status.eq(200)).sum()),
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "gfs_actual_object_coverage_summary.json"
    dest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-12-31", help="00Z initialization date")
    parser.add_argument("--end", default="2026-05-30", help="00Z initialization date")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--out", default="outputs/sm58")
    parser.add_argument("--field-samples-only", action="store_true",
                        help="fetch only monthly representative GRIB index text, no GRIB payloads")
    parser.add_argument("--summarize-existing", action="store_true",
                        help="recompute run cut-off coverage from the existing HEAD CSV without network access")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if end < start or args.workers < 1 or args.workers > 24:
        raise SystemExit("invalid date range or workers (1..24)")
    out = Path(args.out)
    if args.field_samples_only:
        print(json.dumps(inspect_field_sample(out), indent=2))
        return
    if args.summarize_existing:
        print(json.dumps(summarize_cutoff_coverage(out / "gfs_index_head_audit.csv", out), indent=2))
        return
    rows = run(start, end, args.workers)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "gfs_index_head_audit.csv"
    json_path = out / "gfs_index_head_summary.json"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False)
    frame["available"] = frame.status.eq(200)
    per_date = frame.groupby("init_date").available.agg(["sum", "count"])
    summary = {
        "start_init_date": start.isoformat(),
        "end_init_date": end.isoformat(),
        "days": int(len(per_date)),
        "leads": list(LEADS),
        "requests": int(len(frame)),
        "status_counts": {str(k): int(v) for k, v in frame.status.value_counts(dropna=False).items()},
        "all_leads_available_dates": int((per_date["sum"] == len(LEADS)).sum()),
        "partial_dates": int(((per_date["sum"] > 0) & (per_date["sum"] < len(LEADS))).sum()),
        "no_lead_dates": int((per_date["sum"] == 0).sum()),
        "reported_content_length_bytes": int(frame.content_length.fillna(0).sum()),
        "response_payload_bytes_downloaded": 0,
        "csv": str(csv_path),
    }
    cutoff_summary = summarize_cutoff_coverage(csv_path, out)
    summary["cutoff_coverage_summary"] = cutoff_summary
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
