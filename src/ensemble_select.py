"""앙상블 구성원 선별 — 오차 상관행렬 + 반년 교차검증 전진 선택 (집계값만 출력).

반년 교차검증: 앞 6개월로 비율을 맞추고 뒤 6개월에서 채점, 반대도 해서 합산한 W 로 비교한다.
구성원을 하나씩 더하며 교차검증 W 가 min_gain 이상 줄 때만 채택 → 비율 과적합과 쓸모없는 구성원을 걸러낸다.

    .venv/Scripts/python.exe src/ensemble_select.py --sites site_cal rich_extx rich_wx site2 \
        --groups agg_cal:outputs/val_agg_cal.parquet linear:outputs/val_alt_linear.parquet ...
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ensemble as E  # noqa: E402
import scoring as sc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="*", default=[], help="outputs/val_<name>_sites.parquet 의 <name>")
    ap.add_argument("--groups", nargs="*", default=[], help="name:path (group, ts, pred)")
    ap.add_argument("--min-gain", type=float, default=0.001, help="채택 최소 개선 비율 (0.1%)")
    ap.add_argument("--val-start", default=sc.VAL_START)
    ap.add_argument("--val-end", default=sc.VAL_END)
    ap.add_argument("--composition", default=None)
    ap.add_argument("--fixed", default=None, help="고정 비율로만 채점: 'name=w,name=w' (선별 생략)")
    a = ap.parse_args()

    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    actual = sc.load_actual(a.val_start, a.val_end)
    suffix = "" if a.val_start == sc.VAL_START else f"_{a.val_start[:4]}"
    smp = sc.load_smp()
    act = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"]).energy.sum().rename("act")
    cols = {n: E.group_sum(os.path.join(E.OUT, f"val_{n}{suffix}_sites.parquet"), actual, comp) for n in a.sites}
    for item in a.groups:
        n, path = item.split(":", 1)
        g = pd.read_parquet(path)
        g["ts"] = sc.to_ts(g.ts)
        cols[n] = g.set_index(["group", "ts"]).pred
    df = pd.concat([act] + [s.rename(n) for n, s in cols.items()], axis=1).fillna(0)
    ts = df.index.get_level_values("ts").to_series(index=df.index)
    w = (0.1 * ts.map(smp) * sc.k_weight(ts)).to_numpy()
    y = df.act.to_numpy()
    names = list(cols)
    mid_t = pd.Timestamp(a.val_start, tz=sc.TZ) + pd.DateOffset(months=6)
    half = (ts < mid_t).to_numpy()
    if a.fixed:
        wts = {k: float(v) for k, v in (x.split("=") for x in a.fixed.split(","))}
        P = sum(df[k].to_numpy() * v for k, v in wts.items())
        print(f"고정 비율 {wts}: W {float((w * np.abs(P - y)).sum()):,.0f}")
        for n in names:
            print(f"  단독 {n:12s} W {float((w * np.abs(df[n].to_numpy() - y)).sum()):,.0f}")
        return

    mid = ts.dt.hour.between(9, 16).to_numpy()
    err = df.loc[mid, names].sub(df.act[mid], axis=0)
    print("오차 상관 (9~16시):")
    print(err.corr().round(2).to_string())
    print("\n단독 W:", {n: f"{(w * np.abs(df[n].to_numpy() - y)).sum() / 1e6:.1f}M" for n in names})

    def cv(sel: list[str]) -> float:
        P = df[sel].to_numpy()
        tot = 0.0
        for fit_m, ev_m in ((half, ~half), (~half, half)):
            wt = E.solve(P[fit_m], y[fit_m], w[fit_m]) if len(sel) > 1 else np.ones(1)
            tot += float((w[ev_m] * np.abs(P[ev_m] @ wt - y[ev_m])).sum())
        return tot

    chosen = [min(names, key=lambda n: cv([n]))]
    best = cv(chosen)
    print(f"\n전진 선택 (반년 교차검증 W):\n  시작 {chosen[0]:12s} {best:,.0f}")
    while True:
        rest = [n for n in names if n not in chosen]
        if not rest:
            break
        scores = {n: cv(chosen + [n]) for n in rest}
        n = min(scores, key=scores.get)
        gain = 1 - scores[n] / best
        print(f"  + {n:12s} {scores[n]:,.0f}  ({-gain * 100:+.2f}%)" + ("" if gain >= a.min_gain else "  ← 기준 미달, 중단"))
        if gain < a.min_gain:
            break
        chosen.append(n)
        best = scores[n]
    P = df[chosen].to_numpy()
    wt = E.solve(P, y, w) if len(chosen) > 1 else np.ones(1)
    print(f"\n선택: {chosen}\n전체 1년 비율: " + ", ".join(f"{n}={x:.3f}" for n, x in zip(chosen, wt)))
    print(f"전체 1년 W (참고, in-sample): {float((w * np.abs(P @ wt - y)).sum()):,.0f}")


if __name__ == "__main__":
    main()
