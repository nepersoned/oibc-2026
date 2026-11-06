"""Decode a verified fixed-grid GFS cache into hourly spatial features."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import fetch_gfs as g
from spatial_features import decode_fixed_box_with_metadata, summarize_arrays, validate_grib_metadata


def build(raw: Path) -> tuple[pd.DataFrame, dict]:
    rows, failed = [], []
    for path in sorted(raw.glob("*.grib2")):
        if "_f" not in path.name:
            continue
    keys = sorted({p.name.split("_f", 1)[0] for p in raw.glob("*_f*.grib2")})
    for key in keys:
        init = pd.Timestamp(key, tz="UTC")
        grids, metas = {}, {}
        for lead in g.LEADS:
            for var in ("DSWRF", "TCDC"):
                path = raw / f"{key}_f{lead:03d}_{var}.grib2"
                if not path.exists():
                    continue
                try:
                    grids.setdefault(lead, {})[var], metas[(lead, var)] = decode_fixed_box_with_metadata(path.read_bytes())
                    validate_grib_metadata(metas[(lead, var)], var)
                except Exception as exc:  # noqa: BLE001
                    failed.append({"init": key, "reason": f"{path.name}:{type(exc).__name__}"})
        if any(lead not in grids or len(grids[lead]) != 2 for lead in g.LEADS):
            failed.append({"init": key, "reason": "missing_message"})
            continue
        de = {}
        for lead in g.LEADS[1:]:
            de[lead] = {}
            for var in ("DSWRF", "TCDC"):
                start, end = metas[(lead, var)]["startStep"], metas[(lead, var)]["endStep"]
                if end - start == 3:
                    de[lead][var] = grids[lead][var]
                elif end - start == 6 and lead - 3 in grids:
                    de[lead][var] = 2 * grids[lead][var] - grids[lead - 3][var]
                else:
                    de[lead][var] = None
        if any(de[lead][var] is None for lead in de for var in ("DSWRF", "TCDC")):
            failed.append({"init": key, "reason": "unsupported_interval"})
            continue
        for lead in sorted(de):
            prev = {"ghi": de[lead - 3]["DSWRF"], "tcc": de[lead - 3]["TCDC"]} if lead - 3 in de else None
            feat = summarize_arrays(de[lead]["DSWRF"], de[lead]["TCDC"], prev)
            end = init + pd.Timedelta(hours=lead)
            hours = pd.date_range(end - pd.Timedelta(hours=2), end, freq="h").tz_convert("Asia/Seoul")
            for ts in hours:
                rows.append({"ts": ts, **feat})
    frame = pd.DataFrame(rows).drop_duplicates("ts").sort_values("ts")
    return frame, {"init_dates": len(keys), "rows": len(frame), "failed": failed}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    frame, ledger = build(Path(args.raw))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False)
    Path(args.out).with_suffix(".ledger.json").write_text(json.dumps(ledger, indent=2))
    print(json.dumps(ledger, ensure_ascii=False))


if __name__ == "__main__":
    main()
