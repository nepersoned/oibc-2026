"""Research-only, resumable Open-Meteo collection via the existing fetcher.

API access and contest eligibility are separate: do not use output for a
submission before the competition's commercial-use requirement is resolved.
Raw files are ignored by git. Never overwrite an existing source file.
"""
from __future__ import annotations

import argparse
import os
import time
import pandas as pd
import fetch_external as original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True,
                        choices=["ecmwf_ifs025", "jma_seamless", "gfs_seamless", "jma_extra"])
    args = parser.parse_args()
    source = args.source
    model = "jma_seamless" if source == "jma_extra" else source
    variables = original.EXTRA_VARS if source == "jma_extra" else original.VARS
    path = os.path.join(original.OUT, f"openmeteo_{source}.parquet")
    if os.path.exists(path):
        raise SystemExit(f"Refusing to overwrite: {path}")
    os.makedirs(original.OUT, exist_ok=True)
    parts = []
    for start, end in original.YEARS:
        frame = original.fetch(model, start, end, variables)
        required = {"time", "pt"} | {v.replace("_previous_day2", "") for v in variables}
        if not required.issubset(frame.columns) or frame.duplicated(["pt", "time"]).any():
            raise ValueError(f"Invalid schema/duplicate keys for {source} {start}")
        col = variables[0].replace("_previous_day2", "")
        print(f"{source} {start[:4]} rows={len(frame)} {col}_nonnull={frame[col].notna().mean():.4f}", flush=True)
        parts.append(frame)
        time.sleep(3)
    out = pd.concat(parts, ignore_index=True)
    out["ts"] = pd.to_datetime(out.pop("time")).dt.tz_localize("Asia/Seoul")
    tmp = path + ".tmp"
    try:
        out.to_parquet(tmp, index=False)
        os.link(tmp, path)  # atomic create; fails if a file appeared in the meantime
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"Saved {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
