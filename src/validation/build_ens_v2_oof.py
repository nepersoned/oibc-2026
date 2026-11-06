"""Build research-only ens_v2-style and E OOF comparison on common coverage.

The group's reported available-capacity prediction is valid only for scoring;
the observed evaluation mask must never be used to construct future inputs.
"""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
import build_group_comparison as common


def attach_group(table, group_pred, expected_capacity):
    g=group_pred[["group","ts","pred","cap_avail"]].copy()
    g["ts"]=sc.to_ts(g.ts)
    if g.duplicated(["group","ts"]).any():
        raise ValueError("duplicate group forecasts")
    d=table.merge(g,on=["group","ts"],how="left",validate="one_to_one")
    d=d.merge(expected_capacity,on=["group","ts"],how="left",validate="one_to_one")
    if not np.isfinite(d[["pred","cap_avail","observed_cap"]].to_numpy()).all() or (d.pred<0).any():
        raise ValueError("missing/invalid group forecast or capacity")
    if not np.allclose(d.cap_avail,d.observed_cap,rtol=1e-6,atol=1e-3):
        raise ValueError("group forecast and observed site coverage differ")
    d["team"]=.472*d.team+.528*d.pred
    return d[["group","ts","actual","smp","team","candidate"]]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("site-model","group-model","candidate-site","start","end","out"):
        ap.add_argument("--"+name,required=True)
    a=ap.parse_args()
    sites=sc.load_sites(); comp=sc.reference_composition(sites)
    actual=sc.load_actual(a.start,a.end)
    table=common.build(actual,comp,sc.load_smp(),pd.read_parquet(a.site_model),pd.read_parquet(a.candidate_site))
    observed=actual.copy();observed["group"]=observed.site_id.map(comp)
    observed["cap"]=observed.site_id.map(sites.set_index("site_id").capacity_kw)
    capacity=observed.groupby(["group","ts"],as_index=False).cap.sum().rename(columns={"cap":"observed_cap"})
    out=attach_group(table,pd.read_parquet(a.group_model),capacity)
    out.to_parquet(a.out,index=False)
    print(f"Local-only v2-style comparison: {len(out)} observed group-hours")


if __name__=="__main__":
    main()
