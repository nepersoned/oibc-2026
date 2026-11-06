"""Fit group/site weight only on earlier observed OOF hours."""
import argparse
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import scoring as sc
import build_group_comparison as common
import build_ens_v2_oof as v2
import compare_candidates as compare


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("site-model","group-model","start","end","out"):
        ap.add_argument("--"+name,required=True)
    a=ap.parse_args()
    sites=sc.load_sites();comp=sc.reference_composition(sites);actual=sc.load_actual(a.start,a.end)
    site=pd.read_parquet(a.site_model)
    table=common.build(actual,comp,sc.load_smp(),site,site)
    observed=actual.copy();observed["group"]=observed.site_id.map(comp)
    observed["cap"]=observed.site_id.map(sites.set_index("site_id").capacity_kw)
    capacity=observed.groupby(["group","ts"],as_index=False).cap.sum().rename(columns={"cap":"observed_cap"})
    direct=v2.attach_group(table,pd.read_parquet(a.group_model),capacity,group_weight=1.)
    table=table.drop(columns="candidate").merge(direct[["group","ts","team"]].rename(columns={"team":"candidate"}),
                                                 on=["group","ts"],validate="one_to_one")
    data=compare.validate(table)
    alpha=compare.fit_alpha(data)
    out={"start":a.start,"end":a.end,"group_weight":alpha,
         "warning":"in-sample fit; evaluate only on a later time period"}
    with Path(a.out).open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2)
    print(f"Earlier OOF fitted group weight: {alpha:.6f}")


if __name__=="__main__":
    main()
