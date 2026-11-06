"""Repair a GFS day with stale index offsets using GRIB metadata, not guesses.

Reads nearby public GRIB bytes, accepts only a unique metadata-exact match,
and writes a new separate raw cache. Never overwrites any prior cache. This
does not establish that the object was available before the forecast cutoff.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import urllib.request

import numpy as np
import pandas as pd

optional=Path(__file__).resolve().parents[2]/"oibc-dependencies"
if optional.is_dir():
    sys.path.append(str(optional))
import eccodes
import fetch_gfs as g

IDENTITY={"DSWRF":("sdswrf","surface",260087), "TCDC":("tcc","atmosphere",228164)}
KEYS=("shortName","typeOfLevel","paramId","dataDate","dataTime","stepType","startStep","endStep")


def metadata_matches(metadata, key, date, begin, end):
    short, level, param = IDENTITY[key]
    return (metadata.get("shortName")==short and metadata.get("typeOfLevel")==level and
            metadata.get("paramId")==param and metadata.get("dataDate")==date and
            metadata.get("dataTime")==0 and metadata.get("stepType")=="avg" and
            metadata.get("startStep")==begin and metadata.get("endStep")==end)


def metadata(message):
    h=eccodes.codes_new_from_message(message)
    try:
        return {k:eccodes.codes_get(h,k) for k in KEYS}
    finally:
        eccodes.codes_release(h)


def read_range(url, start, end):
    req=urllib.request.Request(url,headers={"Range":f"bytes={start}-{end}"})
    with urllib.request.urlopen(req,timeout=90) as response:
        content_range=response.headers.get("Content-Range","")
        data=response.read()
    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",content_range)
    if not match or int(match[1])!=start or int(match[2])-start+1!=len(data):
        raise ValueError("unexpected HTTP range response")
    return data


def find_message(url, key, start, end, date, begin, lead):
    exact=read_range(url,start,end)
    try:
        if exact[:4]==b"GRIB" and exact[-4:]==b"7777" and metadata_matches(metadata(exact),key,date,begin,lead):
            return exact,False
    except Exception:
        pass
    # Index can reference a different object version. Never infer a constant
    # offset: scan a bounded window and require all metadata to match uniquely.
    window_start=max(0,start-1_500_000)
    data=read_range(url,window_start,end+1_500_000)
    pos=0
    matches=[]
    while True:
        pos=data.find(b"GRIB",pos)
        if pos<0:
            break
        k=pos
        pos+=4
        if k+16>len(data) or data[k+7]!=2:
            continue
        size=int.from_bytes(data[k+8:k+16],"big")
        if size<20 or k+size>len(data):
            continue
        message=data[k:k+size]
        if message[-4:]!=b"7777":
            continue
        try:
            if metadata_matches(metadata(message),key,date,begin,lead):
                matches.append(message)
        except Exception:
            continue
    if len(matches)!=1:
        raise ValueError(f"{key} lead {lead}: expected one metadata match, found {len(matches)}")
    return matches[0],True


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date",required=True,help="initialization YYYY-MM-DD UTC")
    ap.add_argument("--out-dir",required=True,help="separate output cache directory")
    args=ap.parse_args()
    date=pd.Timestamp(args.date,tz="UTC")
    out=Path(args.out_dir)/f"{date:%Y%m%d}.npz"
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    rows=[]
    fallback_count=0
    for lead in g.LEADS:
        for idx_url in g.url(date,lead,True):
            index=g.get(idx_url)
            if index:
                break
        else:
            raise ValueError(f"no index for lead {lead}")
        ranges=g.messages(index.decode())
        row=[lead]
        for key in ("DSWRF","TCDC"):
            if key not in ranges:
                raise ValueError(f"missing {key} index for lead {lead}")
            start,end,description=ranges[key]
            if end is None:
                raise ValueError("open-ended index range")
            begin,finish=map(int,description.split(" hour")[0].split("-"))
            if finish!=lead:
                raise ValueError("unexpected lead")
            message,recovered=find_message(idx_url[:-4],key,start,end,int(date.strftime("%Y%m%d")),begin,lead)
            value=g.box_mean(message)
            if not np.isfinite(value):
                raise ValueError("non-finite spatial mean")
            row.extend([value,finish-begin])
            fallback_count+=int(recovered)
        rows.append(row)
        print(f"lead {lead}: metadata verified",flush=True)
    with out.open("xb") as f:
        np.savez(f,rows=np.asarray(rows,dtype=float))
    print(f"saved separate cache {out}; stale offsets repaired={fallback_count}")


if __name__=="__main__":
    main()
