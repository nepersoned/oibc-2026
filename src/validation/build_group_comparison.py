"""Build local-only common-observation group table from two site forecasts."""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scoring as sc


def build(actual, comp, smp, team, candidate):
    m=actual.copy()
    if m.duplicated(["site_id","ts"]).any():
        raise ValueError("duplicate actual keys")
    for name,p in (("team",team),("candidate",candidate)):
        p=p[["site_id","ts","kwh"]].copy()
        p["ts"]=sc.to_ts(p.ts)
        if p.duplicated(["site_id","ts"]).any():
            raise ValueError("duplicate prediction keys")
        m=m.merge(p.rename(columns={"kwh":name}),on=["site_id","ts"],how="left",validate="one_to_one")
    if not np.isfinite(m[["team","candidate"]].to_numpy()).all() or (m[["team","candidate"]] < 0).any().any():
        raise ValueError("missing or invalid forecasts on observed site-hours")
    m["group"]=m.site_id.map(comp)
    if m.group.isna().any():
        raise ValueError("unknown site in composition")
    out=m.groupby(["group","ts"],as_index=False).agg(actual=("energy","sum"),team=("team","sum"),candidate=("candidate","sum"))
    out["smp"]=out.ts.map(smp)
    if out.smp.isna().any():
        raise ValueError("missing SMP")
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ("team-site","candidate-site","start","end","out"):
        ap.add_argument("--"+arg,required=True)
    a=ap.parse_args()
    sites=sc.load_sites()
    table=build(sc.load_actual(a.start,a.end),sc.reference_composition(sites),sc.load_smp(),
                pd.read_parquet(a.team_site),pd.read_parquet(a.candidate_site))
    table.to_parquet(a.out,index=False)
    print(f"Local-only comparison table saved: {len(table)} group-hours")


if __name__ == "__main__":
    main()
