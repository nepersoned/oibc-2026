"""Verify a completed prefix of an ongoing recovery without copying caches.

Every date must have either a verified raw cache or an existing recorded
failure. Unprocessed dates cannot be silently classified as missing.
"""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recover_gfs_checked import inspect_rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("ledger","raw-dir","start","end","out"):
        ap.add_argument("--"+name,required=True)
    a=ap.parse_args()
    prior=json.loads(Path(a.ledger).read_text(encoding="utf-8"))
    days=pd.date_range(a.start,a.end,freq="D")
    if not len(days) or a.start < prior["start"] or a.end > prior["end"]:
        raise ValueError("scope outside recovery")
    failed={}; valid=0
    for date in days:
        key=date.strftime("%Y%m%d"); path=Path(a.raw_dir)/(key+".npz")
        if key in prior["failed"]:
            failed[key]=prior["failed"][key]
        elif not path.exists():
            raise ValueError(f"date not yet verified: {key}")
        else:
            inspect_rows(path)
            valid+=1
    out={"start":a.start,"end":a.end,"total":len(days),"completed":len(days),"valid":valid,
         "failed":failed,"complete":not failed,"parent_ledger":str(a.ledger)}
    with Path(a.out).open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2)
    print(f"Scoped verified dates={len(days)}, valid={valid}, failures={len(failed)}")


if __name__=="__main__":
    main()
