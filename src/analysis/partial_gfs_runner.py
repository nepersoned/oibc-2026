"""Research-only launcher for original validation with explicit partial GFS.

The normal gfs_hourly.parquet is never created or overwritten. Missing source
days remain missing in hourly columns. Reconstructed artifacts are not an
exact ens_v2 reproduction; source availability and other inputs can differ.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
optional=Path(__file__).resolve().parents[3]/"oibc-dependencies"
if optional.is_dir():
    sys.path.append(str(optional))
import features as F
import scoring as sc


def attach_gfs(base, raw):
    """Match load_ext's default all-source feature construction on a partial input."""
    if base is None or base.ts.duplicated().any() or raw.ts.duplicated().any():
        raise ValueError("missing base or duplicate external timestamps")
    if {"ext_gfs_ghi","ext_gfs_kcs","ext_gfs_tcc"} & set(base.columns):
        raise ValueError("base already includes NOAA GFS")
    if not {"ts","gfs_ghi","gfs_kcs","gfs_tcc"}.issubset(raw):
        raise ValueError("partial GFS schema is incomplete")
    raw=raw[["ts","gfs_ghi","gfs_kcs","gfs_tcc"]].copy()
    raw["ts"]=sc.to_ts(raw.ts)
    out=base.merge(raw.rename(columns={c:"ext_"+c for c in ("gfs_ghi","gfs_kcs","gfs_tcc")}),
                   on="ts",how="outer",validate="one_to_one").sort_values("ts").reset_index(drop=True)
    cols=[f"ext_{name}_ghi" for name in F.EXT_MODELS if f"ext_{name}_ghi" in out]
    cols.append("ext_gfs_ghi")
    out["ext_ghi_ens"]=out[cols].mean(axis=1)
    tday=F.target_day(out.ts)
    for c in ("ext_gfs_ghi","ext_ghi_ens"):
        grp=out.groupby(tday)[c]
        out[c+"_dsum"]=grp.transform("sum")
        out[c+"_lag1"]=grp.shift(1)
        out[c+"_lead1"]=grp.shift(-1)
    num=out.columns.difference(["ts"])
    out[num]=out[num].astype("float32")
    return out


def parse_args(argv=None):
    # --mode belongs to the underlying pipeline and must not abbreviate --model.
    ap=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    ap.add_argument("--gfs-partial",required=True)
    ap.add_argument("--model",choices=["site","group"],required=True)
    return ap.parse_known_args(argv)


def main():
    a,rest=parse_args()
    if "--mode" not in rest or rest[rest.index("--mode")+1]!="val":
        raise ValueError("research validation only")
    if F.USE_GEFS or F.USE_UM or F.USE_2024 or F.ENS_MODE!="all":
        raise ValueError("set OIBC_GEFS=0 OIBC_UM=0 OIBC_EXT2024=0 OIBC_ENS=all")
    if Path(sc.ROOT,"data_ext","gfs_hourly.parquet").exists():
        raise ValueError("normal GFS file exists; use the original pipeline instead")
    raw=pd.read_parquet(a.gfs_partial)
    original=F.load_ext
    def load(mode="mean"):
        return None if mode=="none" else attach_gfs(original(mode),raw)
    F.load_ext=load
    script=Path(sc.ROOT,"src","pipeline.py" if a.model=="site" else "agg_model.py")
    sys.argv=[str(script)]+rest
    runpy.run_path(str(script),run_name="__main__")


if __name__=="__main__":
    main()
