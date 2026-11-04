"""데이터 무결성 점검 — 집계값만 출력한다 (원본 행은 절대 출력하지 않음).

    .venv/Scripts/python.exe src/inspect_data.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "handover 2", "01_participant_dataset")


def p(path: str) -> str:
    return os.path.join(DATA, path)


def summarize(name: str, df: pd.DataFrame, keys: list[str]) -> None:
    print(f"\n=== {name} ===")
    print(f"rows={len(df):,}  cols={df.shape[1]}")
    if "ts" in df:
        ts = pd.to_datetime(df["ts"])
        print(f"ts dtype={ts.dtype}  range={ts.min()} ~ {ts.max()}  unique={ts.nunique():,}")
    dup = df.duplicated(subset=keys).sum() if keys else 0
    print(f"key={keys}  duplicate keys={dup:,}")
    for k in keys:
        if k != "ts":
            print(f"  unique {k}={df[k].nunique():,}")
    nulls = df.isna().sum()
    nulls = nulls[nulls > 0]
    print("nulls:", dict(nulls) if len(nulls) else "none")
    print("dtypes:", {c: str(t) for c, t in df.dtypes.items()})


def main() -> None:
    sites = pd.read_csv(p("sites.csv"))
    summarize("sites.csv", sites, ["site_id"])
    print(f"capacity_kw total={sites.capacity_kw.sum():,.1f}  "
          f"quantiles(0,.25,.5,.75,1)={np.round(sites.capacity_kw.quantile([0,.25,.5,.75,1]).values,1).tolist()}")
    print("current_group capacity:", sites.groupby("current_group").capacity_kw.sum().round(1).to_dict(),
          " counts:", sites.current_group.value_counts().to_dict())
    print(f"wa_station unique={sites.wa_station.nunique()}  wb_station unique={sites.wb_station.nunique()}")

    smp = pd.read_csv(p("smp.csv"))
    summarize("smp.csv (eval)", smp, ["ts"])
    print(f"k counts={smp.k.value_counts().to_dict()}  smp==0 hours={(smp.smp == 0).sum()}")
    smp_tr = pd.read_csv(p("train/smp.csv"))
    summarize("train/smp.csv", smp_tr, ["ts"])
    print(f"smp==0 hours={(smp_tr.smp == 0).sum()}")

    gen = pd.read_parquet(p("train/generation.parquet"))
    summarize("train/generation.parquet", gen, ["site_id", "ts"])
    rows_per_site = gen.groupby("site_id").size()
    print(f"sites in gen={rows_per_site.size}  missing from gen={len(set(sites.site_id) - set(rows_per_site.index))}")
    print(f"rows/site quantiles(0,.25,.5,.75,1)={rows_per_site.quantile([0,.25,.5,.75,1]).astype(int).tolist()}")
    first = pd.to_datetime(gen.groupby("site_id").ts.min())
    print(f"site first-ts by year: {first.dt.year.value_counts().sort_index().to_dict()}")
    cf = gen.merge(sites[["site_id", "capacity_kw"]], on="site_id").eval("energy / capacity_kw")
    print(f"energy<0 rows={(gen.energy < 0).sum()}  CF quantiles(.5,.99,.999,1)="
          f"{np.round(cf.quantile([.5,.99,.999,1]).values,3).tolist()}  CF>1.2 rows={(cf > 1.2).sum()}")
    del gen, cf

    for split in ("train", "test"):
        for prov, st in (("wa", "wa_station"), ("wb", "wb_station")):
            f = pd.read_parquet(p(f"{split}/forecast_{prov}.parquet"))
            summarize(f"{split}/forecast_{prov}", f, [st, "round", "ts"])
            print(f"round counts={f['round'].value_counts().to_dict()}")
            if split == "test":
                n_st = f[st].nunique()
                expected = n_st * 2 * 8760
                print(f"expected full grid={expected:,}  missing rows={expected - len(f):,}")
            del f

    for prov, st in (("wa", "wa_station"), ("wb", "wb_station")):
        o = pd.read_parquet(p(f"train/observed_{prov}.parquet"))
        summarize(f"train/observed_{prov}", o, [st, "ts"])
        del o


if __name__ == "__main__":
    main()
