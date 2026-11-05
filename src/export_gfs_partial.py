"""Export explicitly partial GFS only after checked recovery has finished.

Valid original caches are hard-linked into a private staging directory for
the existing fetch_gfs.build_hourly implementation. Missing days are kept as
NaN in a complete hourly grid. Never writes the normal gfs_hourly.parquet.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import numpy as np
import pandas as pd

import fetch_gfs as g
from recover_gfs_checked import inspect_rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", required=True, help="partial parquet path, never gfs_hourly.parquet")
    args=ap.parse_args()
    ledger=json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    if ledger["completed"] != ledger["total"]:
        raise ValueError("recovery is still running")
    output=Path(args.out).resolve()
    if output == Path(g.OUT).resolve() or output.exists():
        raise ValueError("normal or existing output path is not allowed")
    raw=Path(g.RAW).resolve()
    days=pd.date_range(ledger["start"],ledger["end"],freq="D")
    failures=ledger["failed"]
    good=[d.strftime("%Y%m%d") for d in days if d.strftime("%Y%m%d") not in failures]
    if not good:
        raise ValueError("no valid dates")
    stage=raw.parent / ("gfs_checked_stage_"+uuid.uuid4().hex)
    if stage.parent.resolve()!=raw.parent:
        raise ValueError("unexpected staging path")
    stage.mkdir()
    links=[]
    old=g.RAW
    try:
        for key in good:
            source=raw/(key+".npz")
            inspect_rows(source)
            target=stage/(key+".npz")
            os.link(source,target)
            links.append(target)
        g.RAW=str(stage)
        frame=g.build_hourly()
    finally:
        g.RAW=old
        for link in links:
            link.unlink()
        stage.rmdir()
    if frame.ts.duplicated().any() or len(frame)!=len(good)*24:
        raise ValueError("unexpected partial grid")
    first=pd.Timestamp(ledger["start"],tz=g.TZ)+pd.Timedelta(days=1,hours=1)
    last=pd.Timestamp(ledger["end"],tz=g.TZ)+pd.Timedelta(days=2)
    grid=pd.DataFrame({"ts":pd.date_range(first,last,freq="h")})
    frame=grid.merge(frame,on="ts",how="left",validate="one_to_one")
    frame.to_parquet(output,index=False)
    coverage=frame.groupby(frame.ts.dt.year).agg(rows=("ts","size"),ghi=("gfs_ghi",lambda x:float(x.notna().mean())),
                                                   tcc=("gfs_tcc",lambda x:float(x.notna().mean())))
    print(f"Partial only; valid init days={len(good)}, failed={len(failures)}; no release-time guarantee")
    print(coverage.to_string())
    print(f"Saved {output}")


if __name__=="__main__":
    main()
