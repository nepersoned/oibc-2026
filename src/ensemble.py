"""앙상블 — 여러 모델의 예측을 집합 단위로 섞어 W 를 최소화하는 비율을 찾고, 같은 비율로 제출 파일을 만든다.

구성원: 발전소별 예측 parquet (site_id, ts, kwh) 여러 개 + 집합 모델 예측 (group, ts, cf_hat).
비율은 0 이상, 합 1 (단체 제약). 검증 구간에서 찾고 평가 구간에 그대로 적용한다.

    # 1) 검증: 비율 찾기 → outputs/ensemble_weights.json
    .venv/Scripts/python.exe src/ensemble.py fit --members rich_big rich_ext rich_wx --agg outputs/val_agg_group.parquet

    # 2) 제출: test_<member>_sites.parquet 와 test_agg_group.parquet 를 같은 비율로 섞어 submissions/ 에 저장
    .venv/Scripts/python.exe src/ensemble.py submit --tag ens1 [--composition C.csv]
출력은 집계값만.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scoring as sc  # noqa: E402

OUT = os.path.join(sc.ROOT, "outputs")
SUB = os.path.join(sc.ROOT, "submissions")
WPATH = os.path.join(OUT, "ensemble_weights.json")


def group_sum(path: str, actual: pd.DataFrame | None, comp: pd.Series) -> pd.DataFrame:
    """발전소별 예측 → 집합 합계. actual 이 있으면 실적이 있는 (site, ts) 만 합산."""
    p = pd.read_parquet(path)
    p["ts"] = sc.to_ts(p.ts)
    if actual is not None:
        p = actual[["site_id", "ts"]].merge(p, on=["site_id", "ts"], how="left").fillna({"kwh": 0})
    p["group"] = p.site_id.map(comp)
    return p.groupby(["group", "ts"]).kwh.sum()


def solve(P: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """min Σ w |P·a − y|,  a ≥ 0, Σa = 1 (소프트맥스 매개변수화 + Nelder-Mead/BFGS)."""
    k = P.shape[1]
    f = lambda z: float((w * np.abs(P @ (np.exp(z) / np.exp(z).sum()) - y)).sum())
    best = None
    for z0 in [np.zeros(k)] + [np.eye(k)[i] * 2 for i in range(k)]:
        r = minimize(f, z0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1})
        if best is None or r.fun < best.fun:
            best = r
    a = np.exp(best.x)
    return a / a.sum()


def cmd_fit(a) -> None:
    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    actual = sc.load_actual()
    smp = sc.load_smp()
    act = actual.assign(group=actual.site_id.map(comp)).groupby(["group", "ts"]).energy.sum().rename("act")
    cols = {m: group_sum(os.path.join(OUT, f"val_{m}_sites.parquet"), actual, comp) for m in a.members}
    df = pd.concat([act] + [s.rename(m) for m, s in cols.items()], axis=1).fillna(0)
    names = list(a.members)
    if a.agg:
        g = pd.read_parquet(a.agg)
        g["ts"] = sc.to_ts(g.ts)
        df = df.join(g.set_index(["group", "ts"]).pred.rename("agg")).fillna({"agg": 0})
        names.append("agg")
    ts = df.index.get_level_values("ts").to_series(index=df.index)
    w = (0.1 * ts.map(smp) * sc.k_weight(ts)).to_numpy()
    y = df.act.to_numpy()
    for n in names:
        print(f"  {n:14s} W {float((w * np.abs(df[n].to_numpy() - y)).sum()):>15,.0f}")
    P = df[names].to_numpy()
    wt = solve(P, y, w)
    W = float((w * np.abs(P @ wt - y)).sum())
    eq = float((w * np.abs(P.mean(1) - y)).sum())
    print(f"  균등 평균        W {eq:>15,.0f}")
    print(f"  최적 혼합        W {W:>15,.0f}   비율 " + ", ".join(f"{n}={x:.3f}" for n, x in zip(names, wt)))
    json.dump({"members": a.members, "agg": bool(a.agg), "weights": dict(zip(names, map(float, wt))), "W_val": W},
              open(WPATH, "w"), indent=2, ensure_ascii=False)
    print(f"저장: {WPATH}")


def cmd_submit(a) -> None:
    cfg = json.load(open(a.weights))
    sites = sc.load_sites()
    comp = sc.read_composition(a.composition) if a.composition else sc.reference_composition(sites)
    total = None
    for m in cfg["members"]:
        s = group_sum(os.path.join(OUT, f"test_{m}_sites.parquet"), None, comp) * cfg["weights"][m]
        total = s if total is None else total.add(s, fill_value=0)
    if cfg["agg"]:
        g = pd.read_parquet(a.agg_test)
        g["ts"] = sc.to_ts(g.ts)
        total = total.add(g.set_index(["group", "ts"]).pred * cfg["weights"]["agg"], fill_value=0)
    f = total.clip(lower=0).rename("forecast_kwh").reset_index().sort_values(["group", "ts"])
    f["ts"] = f.ts.dt.strftime("%Y-%m-%d %H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
    os.makedirs(SUB, exist_ok=True)
    cpath, fpath = os.path.join(SUB, f"composition_{a.tag}.csv"), os.path.join(SUB, f"forecast_{a.tag}.csv")
    comp.rename("group").rename_axis("site_id").reset_index().to_csv(cpath, index=False)
    f.to_csv(fpath, index=False)
    print(f"저장: {cpath} / {fpath} ({len(f):,}행)  비율 {cfg['weights']}")
    subprocess.run([sys.executable, os.path.join(sc.ROOT, "src", "validate_submission.py"),
                    "--composition", cpath, "--forecast", fpath], check=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fit")
    f.add_argument("--members", nargs="+", required=True, help="outputs/val_<member>_sites.parquet 의 <member>")
    f.add_argument("--agg", default=None, help="집합 모델 검증 예측 (group, ts, pred)")
    f.add_argument("--composition", default=None)
    s = sp.add_parser("submit")
    s.add_argument("--tag", required=True)
    s.add_argument("--composition", default=None)
    s.add_argument("--weights", default=WPATH, help="ensemble.py fit 이 저장한 비율 json")
    s.add_argument("--agg-test", default=os.path.join(OUT, "test_agg_group.parquet"), help="집합 모델 평가 구간 예측")
    a = ap.parse_args()
    cmd_fit(a) if a.cmd == "fit" else cmd_submit(a)


if __name__ == "__main__":
    main()
