"""Retrospective replication of team two-way half-year CV, not forward testing.

Input is a local common-observation group table with site as team and direct
group forecast as candidate. The reverse fold fits on the future, so its sum
must never be treated as a prospective or independent holdout score.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

import compare_candidates as c


def diagnostic(table,start):
    data=c.validate(table)
    mid=pd.Timestamp(start,tz="Asia/Seoul")+pd.DateOffset(months=6)
    halves=(data[data.ts<mid],data[data.ts>=mid])
    if not len(halves[0]) or not len(halves[1]):
        raise ValueError("both half-year folds required")
    folds=[]
    for train,test in (halves,halves[::-1]):
        weight=c.fit_alpha(train)
        pred=(1-weight)*test.team+weight*test.candidate
        W=float((test.weight*(pred-test.actual).abs()).sum())
        folds.append({"group_weight":weight,"eval_start":str(test.ts.min()),"eval_end":str(test.ts.max()),"W":W})
    return {"cv_W":sum(f["W"] for f in folds),"folds":folds,
            "warning":"second-direction training uses future relative to first-half evaluation"}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table",required=True);ap.add_argument("--start",required=True);ap.add_argument("--out",required=True)
    a=ap.parse_args()
    result=diagnostic(pd.read_parquet(a.table),a.start)
    with Path(a.out).open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
    print(f"Retrospective two-way CV W={result['cv_W']:.2f}; not forward-only")


if __name__=="__main__":
    main()
