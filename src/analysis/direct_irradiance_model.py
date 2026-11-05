"""Research-only: add two fixed-area issued-weather features to base LGBM.

Uses the original base pipeline and its time split. No model or data is sent
externally; this is not a submission model pending source/availability review.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import runpy
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import features as F
import model as M
import scoring as sc


def load_weather(path):
    wx = pd.read_parquet(path)
    wx["ts"] = sc.to_ts(wx.ts)
    if wx.duplicated(["pt", "ts"]).any():
        raise ValueError("duplicate weather point/time")
    out = wx.groupby("ts", as_index=False).agg(ext_ghi=("shortwave_radiation", "mean"),
                                                ext_cloud=("cloud_cover", "mean"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", required=True)
    args, remaining = ap.parse_known_args()
    if "--mode" not in remaining or remaining[remaining.index("--mode") + 1] != "val":
        raise ValueError("research validation only")
    if "--fset" in remaining and remaining[remaining.index("--fset") + 1] != "base":
        raise ValueError("only baseline features are supported")
    weather = load_weather(args.forecast)
    original_build, original_fit, original_predict = F.build, M.fit, M.predict
    M.FEATS = list(M.FEATS) + ["ext_ghi", "ext_cloud"]

    def build(*a, **kw):
        return original_build(*a, **kw).merge(weather, on="ts", how="left", validate="many_to_one")

    def fit(d, *a, **kw):
        d[M.FEATS] = d[M.FEATS].astype("float32")
        return original_fit(d, *a, **kw)

    def predict(m, d):
        d[M.FEATS] = d[M.FEATS].astype("float32")
        return original_predict(m, d)

    F.build, M.fit, M.predict = build, fit, predict
    sys.argv = [str(Path(__file__).resolve().parents[1] / "pipeline.py")] + remaining
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
