"""후보 (발전소 태그 × 그룹 결과) 조합을 두 해(2024·2023)에서 모두 채점해 **두 해 모두 기준보다 좋은** 조합 중 최선을 고른다.

    .venv/Scripts/python.exe src/pick_best.py --sites site_r2 site_all site_l1 --groups gpts l1 l1h0 \
        --ref site_r2 gpts --out outputs/best_pick.json

- 발전소: outputs/val_<tag>_sites.parquet (2024), outputs/val_<tag>_2023_sites.parquet (2023)
- 그룹:   outputs/val_agg_<name>_2024.parquet, outputs/val_agg_<name>_2023.parquet
- 각 조합의 비율은 두 해 각각 1차원 격자(0~1, 0.01)로 최적화하고, 제출 비율은 두 해 평균.
- 채택 규칙: 두 해 모두 기준 대비 ≥ min-gain 개선 → 그중 두 해 평균 개선이 가장 큰 조합. 없으면 기준.
출력은 집계값만.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

import ensemble as E
import scoring as sc

YEARS = {"2024": ("2024-06-01", "2025-06-01"), "2023": ("2023-06-01", "2024-06-01")}


def load_year(year: str, sites: list[str], groups: list[str]):
    start, end = YEARS[year]
    comp = sc.reference_composition(sc.load_sites())
    actual = sc.load_actual(start, end)
    suffix = "" if start == sc.VAL_START else f"_{year}"
    smp = sc.load_smp()
    act = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"]).energy.sum().rename("act")
    cols = {}
    for t in sites:
        p = os.path.join(E.OUT, f"val_{t}{suffix}_sites.parquet")
        if os.path.exists(p):
            cols[t] = E.group_sum(p, actual, comp)
    for g in groups:
        p = os.path.join(E.OUT, f"val_agg_{g}_{year}.parquet")
        if os.path.exists(p):
            d = pd.read_parquet(p)
            d["ts"] = sc.to_ts(d.ts)
            cols[g] = d.set_index(["group", "ts"]).pred
    df = pd.concat([act] + [s.rename(n) for n, s in cols.items()], axis=1).fillna(0)
    ts = df.index.get_level_values("ts").to_series(index=df.index)
    w = (0.1 * ts.map(smp) * sc.k_weight(ts)).to_numpy()
    return df, w


def best_blend(a: np.ndarray, b: np.ndarray, y: np.ndarray, w: np.ndarray) -> tuple[float, float]:
    grid = np.linspace(0, 1, 101)
    W = [float((w * np.abs(x * a + (1 - x) * b - y)).sum()) for x in grid]
    i = int(np.argmin(W))
    return float(grid[i]), W[i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", required=True)
    ap.add_argument("--groups", nargs="+", required=True)
    ap.add_argument("--ref", nargs=2, required=True, help="기준 조합: <site> <group>")
    ap.add_argument("--min-gain", type=float, default=0.005)
    ap.add_argument("--out", default=os.path.join(E.OUT, "best_pick.json"))
    a = ap.parse_args()
    data = {y: load_year(y, a.sites, a.groups) for y in YEARS}
    rows = []
    for s in a.sites:
        for g in a.groups:
            rec = {"site": s, "group": g}
            ok = True
            for y, (df, w) in data.items():
                if s not in df or g not in df:
                    ok = False
                    break
                x, W = best_blend(df[s].to_numpy(), df[g].to_numpy(), df.act.to_numpy(), w)
                rec[f"w_{y}"], rec[f"W_{y}"] = x, W
            if ok:
                rows.append(rec)
    t = pd.DataFrame(rows)
    ref = t[(t.site == a.ref[0]) & (t.group == a.ref[1])]
    if ref.empty:
        raise SystemExit(f"기준 조합 {a.ref} 결과 없음")
    ref = ref.iloc[0]
    for y in YEARS:
        t[f"gain_{y}"] = 1 - t[f"W_{y}"] / ref[f"W_{y}"]
    t["gain_mean"] = (t.gain_2024 + t.gain_2023) / 2
    t["pass"] = (t.gain_2024 >= a.min_gain) & (t.gain_2023 >= a.min_gain)
    t = t.sort_values("gain_mean", ascending=False)
    show = t.assign(W_2024=t.W_2024.map("{:,.0f}".format), W_2023=t.W_2023.map("{:,.0f}".format),
                    gain_2024=(t.gain_2024 * 100).map("{:+.2f}%".format), gain_2023=(t.gain_2023 * 100).map("{:+.2f}%".format),
                    w_site=((t.w_2024 + t.w_2023) / 2).round(3)).drop(columns=["w_2024", "w_2023", "gain_mean"])
    print(show.to_string(index=False))
    win = t[t["pass"]].iloc[0] if t["pass"].any() else ref
    w_site = float((win.w_2024 + win.w_2023) / 2)
    pick = {"site": win.site, "group": win.group, "w_site": round(w_site, 3), "w_group": round(1 - w_site, 3),
            "W_2024": float(win.W_2024), "W_2023": float(win.W_2023),
            "gain_2024": float(1 - win.W_2024 / ref.W_2024), "gain_2023": float(1 - win.W_2023 / ref.W_2023),
            "ref": list(a.ref)}
    json.dump(pick, open(a.out, "w"), indent=2)
    print(f"\n채택: 발전소 {pick['site']} {pick['w_site']:.3f} + 그룹 {pick['group']} {pick['w_group']:.3f}  "
          f"(기준 대비 {pick['gain_2024'] * 100:+.2f}% / {pick['gain_2023'] * 100:+.2f}%)  → {a.out}")


if __name__ == "__main__":
    main()
