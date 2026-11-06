"""그룹 합계 사후 보정 검증 — 예측 × s,  s = max(a + b·x, 0),  x = 그룹 날씨 요약(구름양 등).

한 해로 (a, b)를 맞추고 다른 해에서 채점 (교차 적합). 집계값만 출력.

    .venv/Scripts/python.exe src/calib_test.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agg_model as A  # noqa: E402
import ensemble as E  # noqa: E402
import scoring as sc  # noqa: E402

YEARS = {"2024": ("2024-06-01", "2025-06-01", "", "outputs/val_agg_um.parquet"),
         "2023": ("2023-06-01", "2024-06-01", "_2023", "outputs/val_agg_um_2023.parquet")}
XVARS = ["g_wb_cloud", "g_wa_cloud", "g_wb_cloud_daymean"]


def frame(year: str, gw: pd.DataFrame) -> pd.DataFrame:
    a, b, suf, agg_path = YEARS[year]
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    actual = sc.load_actual(a, b)
    act = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"]).energy.sum().rename("act")
    site = E.group_sum(os.path.join(sc.ROOT, "outputs", f"val_site_um{suf}_sites.parquet"), actual, comp).rename("site")
    g = pd.read_parquet(agg_path)
    g["ts"] = sc.to_ts(g.ts)
    df = pd.concat([act, site, g.set_index(["group", "ts"]).pred.rename("agg")], axis=1).dropna().reset_index()
    df["pred"] = 0.5 * df["site"] + 0.5 * df["agg"]
    df = df.merge(gw, on=["group", "ts"], how="left")
    df["w"] = 0.1 * df.ts.map(sc.load_smp()).to_numpy() * sc.k_weight(df.ts)
    return df


def W(df, s):
    return float((df.w * np.abs(df.pred * s - df.act)).sum())


def fit(df, x):
    best = (np.inf, 1.0, 0.0)
    xs = df[x].fillna(df[x].median()).to_numpy() / 100.0
    for a in np.arange(0.90, 1.101, 0.005):
        for b in np.arange(-0.15, 0.151, 0.005):
            s = np.maximum(a + b * xs, 0)
            v = float((df.w * np.abs(df.pred * s - df.act)).sum())
            if v < best[0]:
                best = (v, a, b)
    return best[1], best[2]


def main() -> None:
    sites = sc.load_sites()
    comp = sc.reference_composition(sites)
    fa, fb = A.forecasts("train")
    gw = A.group_weather(fa, fb, sites, comp)[["group", "ts"] + XVARS]
    d = {y: frame(y, gw) for y in YEARS}
    for y in d:
        print(f"[{y}] 보정 전 W {W(d[y], 1.0):,.0f}")
    for x in XVARS:
        for fit_y, ev_y in (("2023", "2024"), ("2024", "2023")):
            a, b = fit(d[fit_y], x)
            xs = d[ev_y][x].fillna(d[ev_y][x].median()).to_numpy() / 100.0
            w0, w1 = W(d[ev_y], 1.0), W(d[ev_y], np.maximum(a + b * xs, 0))
            print(f"{x:20s} {fit_y}로 적합 a={a:.3f} b={b:+.3f} → {ev_y} 평가 {(w1 / w0 - 1) * 100:+.2f}%")
    for fit_y, ev_y in (("2023", "2024"), ("2024", "2023")):
        best = min(np.arange(0.94, 1.061, 0.005), key=lambda s: W(d[fit_y], s))
        print(f"상수 배율 {fit_y}로 적합 s={best:.3f} → {ev_y} 평가 {(W(d[ev_y], best) / W(d[ev_y], 1.0) - 1) * 100:+.2f}%")


if __name__ == "__main__":
    main()
