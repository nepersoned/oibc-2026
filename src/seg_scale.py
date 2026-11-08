"""구간별 배율 보정 두 해 검증 (집계값만): 구간 예측에 f 를 곱했을 때 W 변화."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "src")
import pick_best as P
import features as F

WS = 0.505
D = {}
for y in P.YEARS:
    df, w = P.load_year(y, ["site_dv"], ["l1umxdv"])
    p = (WS * df.site_dv + (1 - WS) * df.l1umxdv).to_numpy(); a = df.act.to_numpy()
    ts = pd.Series(df.index.get_level_values("ts"))
    cal = F.calendar(ts); day = F.target_day(ts).dt.tz_localize(None)
    h = ts.dt.hour.to_numpy(); mon = day.dt.month.to_numpy(); off = cal.is_off.to_numpy() == 1
    g = df.index.get_level_values("group").to_numpy()
    D[y] = dict(p=p, a=a, w=w, h=h, mon=mon, off=off, g=g, base=float((w * np.abs(p - a)).sum()))

def segs(d):
    mid = (d["h"] >= 10) & (d["h"] <= 16); spring = np.isin(d["mon"], [3, 4, 5]); autumn = np.isin(d["mon"], [9, 10, 11])
    return {"봄휴일10-16": spring & d["off"] & mid, "봄휴일전체": spring & d["off"], "가을휴일10-16": autumn & d["off"] & mid,
            "봄가을휴일10-16": (spring | autumn) & d["off"] & mid, "휴일10-16": d["off"] & mid,
            "봄평일10-16": spring & ~d["off"] & mid,
            "봄휴일10-16_G1": spring & d["off"] & mid & (d["g"] == "G1"), "봄휴일10-16_G2": spring & d["off"] & mid & (d["g"] == "G2")}

F_GRID = np.round(np.arange(0.80, 1.051, 0.01), 2)
for name in segs(D["2024"]):
    out = []
    for y, d in D.items():
        m = segs(d)[name]
        res = []
        for f in F_GRID:
            q = d["p"].copy(); q[m] *= f
            res.append(float((d["w"] * np.abs(q - d["a"])).sum()) / d["base"] - 1)
        res = np.array(res); out.append(res)
        share = float((d["w"] * np.abs(d["p"] - d["a"]))[m].sum()) / d["base"]
        print(f"{name:14s} {y}: 페널티 비중 {share:5.1%}  최적 f {F_GRID[res.argmin()]:.2f} ({res.min():+.2%})", end="  ")
    tot = out[0] + out[1]; i = int(np.argmin(np.maximum(out[0], out[1])))
    print(f"| 공통 f {F_GRID[i]:.2f} → {out[0][i]:+.2%} / {out[1][i]:+.2%}")
