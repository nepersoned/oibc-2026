"""Recover NOAA GFS using existing fetch_gfs functions with a failure ledger.

Does not overwrite existing raw caches or hourly outputs. Individual dates
with missing messages are explicitly recorded; an incomplete run is never
silently presented as the complete hourly dataset.
Past object publication before each competition cutoff still requires audit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

# Allow a separately installed ecCodes package without replacing the approved
# environment's numpy/pandas. OS code-signing policy remains in force.
optional = Path(__file__).resolve().parents[2] / "oibc-dependencies"
if optional.is_dir():
    sys.path.append(str(optional))
import fetch_gfs as g


def inspect_rows(path):
    with np.load(path) as f:
        rows = f["rows"]
    if rows.shape != (len(g.LEADS), 5) or not np.array_equal(rows[:, 0], g.LEADS):
        raise ValueError("unexpected lead/schema")
    if not np.isfinite(rows).all() or not np.isin(rows[:, 2], [3, 6]).all() or not np.isin(rows[:, 4], [3, 6]).all():
        raise ValueError("missing data or unsupported averaging window")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    if not 1 <= args.workers <= 24:
        raise ValueError("workers must be in [1,24]")
    outdir = Path(g.OUT).parent
    raw = Path(g.RAW)
    outdir.mkdir(exist_ok=True)
    raw.mkdir(exist_ok=True)
    if Path(g.OUT).exists():
        raise FileExistsError(f"Refusing to overwrite existing hourly data: {g.OUT}")
    start, end = pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC")
    if end < start:
        raise ValueError("end before start")
    days = pd.date_range(start, end, freq="D")
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ledger = outdir / f"gfs_recovery_{run}.json"
    failures, succeeded = {}, []

    def one(d):
        key = d.strftime("%Y%m%d")
        path = raw / (key + ".npz")
        try:
            g.fetch_day(d)  # existing cache is preserved by original code
            inspect_rows(path)
            return key, None
        except Exception as exc:
            return key, f"{type(exc).__name__}: {exc}"

    def save_ledger(done):
        info = {"start":args.start,"end":args.end,"total":len(days),"completed":done,
                "valid":len(succeeded),"failed":failures,"complete":done==len(days) and not failures,
                "availability_before_cutoff":"not established for all dates"}
        ledger.write_text(json.dumps(info, indent=2), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future = [pool.submit(one, day) for day in days]
        for done, f in enumerate(as_completed(future), 1):
            key, error = f.result()
            if error:
                failures[key] = error
            else:
                succeeded.append(key)
            if done % 25 == 0 or done == len(days):
                save_ledger(done)
                print(f"processed={done}/{len(days)} valid={len(succeeded)} failed={len(failures)}", flush=True)

    if failures:
        print(f"Incomplete: failures retained in {ledger}; no complete hourly file written.", flush=True)
        return
    # The original builder reads all .npz files in RAW, so ensure it contains
    # exactly the requested init days before constructing the final dataset.
    available = {p.stem for p in raw.glob("*.npz")}
    if available != set(succeeded):
        print(f"Extra raw cache files detected; inspect {ledger}; hourly output not written.", flush=True)
        return
    final = Path(g.OUT)
    if final.exists():
        raise FileExistsError(f"Refusing to overwrite existing hourly data: {final}")
    frame = g.build_hourly()
    if frame.ts.duplicated().any() or len(frame) != len(days)*24:
        raise ValueError("hourly grid is incomplete or has duplicates")
    frame.to_parquet(final, index=False)
    coverage = frame.groupby(frame.ts.dt.year).agg(rows=("ts","size"), ghi=("gfs_ghi",lambda x: float(x.notna().mean())),
                                                  tcc=("gfs_tcc",lambda x: float(x.notna().mean())))
    print(f"Saved {final}\n{coverage.to_string()}", flush=True)


if __name__ == "__main__":
    main()
