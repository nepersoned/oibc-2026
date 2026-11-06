"""Resumeable byte-range collection of fixed-grid GFS DSWRF/TCDC messages.

This is a research-only collector. It never touches the normal GFS caches and
marks an initialization date complete only after all 18 messages decode to the
expected 5x4 fixed box with the existing spatial decoder.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

import fetch_gfs as g
from spatial_features import decode_fixed_box_with_metadata, validate_grib_metadata

VARS = ("DSWRF", "TCDC")


def download_one(day: pd.Timestamp, lead: int, var: str, raw: Path) -> str:
    dest = raw / f"{day:%Y%m%d}_f{lead:03d}_{var}.grib2"
    if dest.exists() and dest.stat().st_size > 1000:
        return "existing"
    idx, base = None, None
    for u in g.url(day, lead, True):
        try:
            idx = urllib.request.urlopen(urllib.request.Request(u), timeout=20).read().decode()
            base = u[:-4]
            break
        except Exception:
            continue
    if idx is None:
        return "idx_failed"
    msg = g.messages(idx).get(var)
    if msg is None:
        return "message_failed"
    start, end, _ = msg
    last_error = "range_failed"
    for attempt in range(2):
        try:
            req = urllib.request.Request(base)
            req.add_header("Range", f"bytes={start}-{end if end is not None else start + 5_000_000}")
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) <= 1000:
                return "short_response"
            dest.write_bytes(data)
            return "downloaded"
        except Exception as exc:  # noqa: BLE001
            last_error = type(exc).__name__
            time.sleep(1 + attempt)
    return last_error


def verify_day(day: pd.Timestamp, raw: Path) -> tuple[bool, str]:
    key = day.strftime("%Y%m%d")
    for lead in g.LEADS:
        for var in VARS:
            path = raw / f"{key}_f{lead:03d}_{var}.grib2"
            if not path.exists():
                return False, f"missing:{path.name}"
            try:
                _, meta = decode_fixed_box_with_metadata(path.read_bytes())
                validate_grib_metadata(meta, var)
                if tuple(meta.get("selected_rows", [])) != (52, 53, 54, 55, 56) or tuple(meta.get("selected_cols", [])) != (126, 127, 128, 129):
                    return False, f"grid:{path.name}"
            except Exception as exc:  # noqa: BLE001
                return False, f"decode:{path.name}:{type(exc).__name__}"
    return True, "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    if not 1 <= args.workers <= 24:
        raise ValueError("workers must be in [1,24]")
    root, raw = Path(args.out), Path(args.out) / "grib"
    raw.mkdir(parents=True, exist_ok=True)
    days = list(pd.date_range(args.start, args.end, freq="D", tz="UTC"))
    ledger_path = root / "collection_ledger.json"
    previous = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}
    completed = {x["init"] for x in previous.get("results", []) if x.get("verified")}
    results = [x for x in previous.get("results", []) if x.get("verified")]
    pending = [d for d in days if d.strftime("%Y%m%d") not in completed]
    jobs = [(d, lead, var) for d in pending for lead in g.LEADS for var in VARS]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, d, lead, var, raw): (d, lead, var) for d, lead, var in jobs}
        for i, future in enumerate(as_completed(futures), 1):
            future.result()
            if i % 100 == 0:
                print(f"messages {i}/{len(jobs)}", flush=True)
    for day in pending:
        key = day.strftime("%Y%m%d")
        ok, reason = verify_day(day, raw)
        results = [x for x in results if x["init"] != key]
        results.append({"init": key, "verified": ok, "reason": reason})
        ledger_path.write_text(json.dumps({"start": args.start, "end": args.end,
                                           "total_dates": len(days), "completed_dates": sum(x["verified"] for x in results),
                                           "results": sorted(results, key=lambda x: x["init"])}, indent=2))
        print(f"{key} verified={ok} reason={reason}", flush=True)


if __name__ == "__main__":
    main()
