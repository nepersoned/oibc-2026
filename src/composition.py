"""G1/G2 구성 최적화 — 발전소별 예측 잔차로 집합 페널티 Σ_t w_t (|e1_t| + |e2_t|) 최소화.

    e1_t = Σ_{s∈G1} r_st,  e2_t = R_t − e1_t,  w_t = 0.1·SMP·k,  두 집합 모두 설비용량 ≥ 20,000 kW

방법
- local : 한 개 이동 / 두 개 교환 국소 탐색 (빠름, numpy)
- milp  : scipy.optimize.milp (HiGHS, MIT 라이선스) — 시간 제한, 국소 탐색 결과보다 나쁘면 버림

과적합 점검: --fit 으로 최적화하고 --eval 의 다른 기간 예측으로 평가한다.

    .venv/Scripts/python.exe src/composition.py --fit outputs/val_rich_sites.parquet
    .venv/Scripts/python.exe src/composition.py --fit A.parquet --fit-start 2023-06-01 --fit-end 2024-06-01 \
        --eval B.parquet --out outputs/composition_opt.csv
출력은 집계값만.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scoring as sc  # noqa: E402

MIN_CAP = sc.MIN_CAP


def residuals(pred_path: str, start: str, end: str, sites: pd.DataFrame):
    """Observed-only 잔차 행렬. 미관측 기여 0은 objective 집계용이며 무오차 뜻이 아니다."""
    p = pd.read_parquet(pred_path)
    p["ts"] = sc.to_ts(p.ts)
    if p.duplicated(["site_id", "ts"]).any():
        raise ValueError("예측 site_id, ts 중복")
    actual = sc.load_actual(start, end)
    if actual.duplicated(["site_id", "ts"]).any():
        raise ValueError("실적 site_id, ts 중복")
    if not np.isfinite(p.kwh.to_numpy(dtype=float)).all():
        raise ValueError("예측에 NaN/Inf 존재")
    a = actual.merge(p, on=["site_id", "ts"], how="left", validate="one_to_one")
    if a.kwh.isna().any():
        raise ValueError(f"관측 실적 행의 예측 누락 {int(a.kwh.isna().sum())}개")
    if not len(a):
        raise ValueError("최적화 기간의 관측 잔차 입력이 비어 있음")
    a["r"] = a.kwh - a.energy
    M = a.pivot(index="ts", columns="site_id", values="r")
    M = M.reindex(columns=sites.site_id).fillna(0.0)  # observed-only 목적함수의 미관측 기여
    if M.empty:
        raise ValueError("최적화 기간의 잔차 행렬이 비어 있음")
    w = 0.1 * M.index.to_series().map(sc.load_smp()).to_numpy() * sc.k_weight(M.index.to_series())
    if not np.isfinite(w).all() or (w < 0).any():
        raise ValueError("SMP 누락/비유효 값 또는 음수 가중치")
    return M.to_numpy(np.float64), w.astype(np.float64)


def objective(x: np.ndarray, R: np.ndarray, w: np.ndarray) -> float:
    e1 = R @ x
    e2 = R.sum(1) - e1
    return float((w * (np.abs(e1) + np.abs(e2))).sum())


def feasible(x: np.ndarray, cap: np.ndarray, min_group_capacity: float = MIN_CAP) -> bool:
    c1 = cap @ x
    return c1 >= min_group_capacity and cap.sum() - c1 >= min_group_capacity


def local_search(x: np.ndarray, R: np.ndarray, w: np.ndarray, cap: np.ndarray, max_rounds: int = 50,
                 movable_mask: np.ndarray | None = None, max_changed: int | None = None,
                 min_group_capacity: float = MIN_CAP):
    x = x.astype(np.float64).copy()
    x_initial = x.copy()
    movable = np.ones(len(x), dtype=bool) if movable_mask is None else np.asarray(movable_mask, dtype=bool)
    if movable.shape != x.shape:
        raise ValueError("movable_mask 길이가 구성과 다름")
    if max_changed is not None and max_changed < 0:
        raise ValueError("max_changed must be nonnegative")
    if not feasible(x, cap, min_group_capacity):
        raise ValueError("initial composition violates min_group_capacity")
    tot = R.sum(1)
    e1 = R @ x
    best = float((w * (np.abs(e1) + np.abs(tot - e1))).sum())
    total_cap = cap.sum()
    for _ in range(max_rounds):
        improved = False
        # 1) 단일 이동: 모든 발전소 이동 효과를 한 번에 계산
        sign = 1 - 2 * x                                   # G2→G1 이면 +, G1→G2 이면 −
        E1 = e1[:, None] + R * sign[None, :]
        cand = (w[:, None] * (np.abs(E1) + np.abs(tot[:, None] - E1))).sum(0)
        c1 = cap @ x + cap * sign
        cand[(c1 < min_group_capacity) | (total_cap - c1 < min_group_capacity) | ~movable] = np.inf
        changed_count = int(np.count_nonzero(x != x_initial))
        if max_changed is not None:
            changed_after_toggle = changed_count + np.where(x == x_initial, 1, -1)
            cand[changed_after_toggle > max_changed] = np.inf
        j = int(np.argmin(cand))
        if cand[j] < best - 1e-6:
            x[j] = 1 - x[j]
            e1 = E1[:, j].copy()
            best = float(cand[j])
            improved = True
            continue
        # 2) 교환: G1 하나 ↔ G2 하나 (최선 이동 후보 상위끼리만)
        g1, g2 = np.where((x == 1) & movable)[0], np.where((x == 0) & movable)[0]
        top1 = g1[np.argsort(cand[g1])[:40]]
        top2 = g2[np.argsort(cand[g2])[:40]]
        for i in top1:
            E1i = e1 - R[:, i]
            E = E1i[:, None] + R[:, top2]
            v = (w[:, None] * (np.abs(E) + np.abs(tot[:, None] - E))).sum(0)
            c1 = cap @ x - cap[i] + cap[top2]
            v[(c1 < min_group_capacity) | (total_cap - c1 < min_group_capacity)] = np.inf
            if max_changed is not None:
                ci_before = int(x[i] != x_initial[i])
                ci_after = int((1 - x[i]) != x_initial[i])
                cj_before = (x[top2] != x_initial[top2]).astype(np.int8)
                cj_after = ((1 - x[top2]) != x_initial[top2]).astype(np.int8)
                moved_after_swap = changed_count - ci_before - cj_before + ci_after + cj_after
                v[moved_after_swap > max_changed] = np.inf
            k = int(np.argmin(v))
            if v[k] < best - 1e-6:
                x[i], x[top2[k]] = 0, 1
                e1 = E[:, k].copy()
                best = float(v[k])
                improved = True
                break
        if not improved:
            break
    return x, best


def milp(R: np.ndarray, w: np.ndarray, cap: np.ndarray, time_limit: float):
    from scipy.optimize import Bounds, LinearConstraint, milp as _milp
    from scipy.sparse import csr_matrix, hstack, identity, vstack

    T, S = R.shape
    tot = R.sum(1)
    # 변수 [x(S), u(T), v(T)]   u ≥ |e1|, v ≥ |tot − e1|
    c = np.concatenate([np.zeros(S), w, w])
    Rs = csr_matrix(R)
    I = identity(T, format="csr")
    Z = csr_matrix((T, T))
    A = vstack([
        hstack([-Rs, I, Z]),     # u − e1 ≥ 0
        hstack([Rs, I, Z]),      # u + e1 ≥ 0
        hstack([Rs, Z, I]),      # v + e1 ≥ tot
        hstack([-Rs, Z, I]),     # v − e1 ≥ −tot
        hstack([csr_matrix(cap[None, :]), csr_matrix((1, 2 * T))]),
    ]).tocsr()
    lb = np.concatenate([np.zeros(T), np.zeros(T), tot, -tot, [MIN_CAP]])
    ub = np.concatenate([np.full(4 * T, np.inf), [cap.sum() - MIN_CAP]])
    integ = np.concatenate([np.ones(S), np.zeros(2 * T)])
    bounds = Bounds(np.zeros(S + 2 * T), np.concatenate([np.ones(S), np.full(2 * T, np.inf)]))
    res = _milp(c, constraints=LinearConstraint(A, lb, ub), integrality=integ, bounds=bounds,
                options={"time_limit": time_limit, "disp": False, "mip_rel_gap": 1e-4})
    if res.x is None:
        return None, np.inf
    x = np.round(res.x[:S])
    return x, objective(x, R, w)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", required=True, help="최적화에 쓸 발전소별 예측")
    ap.add_argument("--fit-start", default=sc.VAL_START)
    ap.add_argument("--fit-end", default=sc.VAL_END)
    ap.add_argument("--eval", default=None, help="다른 기간 예측 (과적합 점검)")
    ap.add_argument("--eval-start", default=sc.VAL_START)
    ap.add_argument("--eval-end", default=sc.VAL_END)
    ap.add_argument("--fit2", default=None, help="두 번째 기간 예측 (함께 최적화)")
    ap.add_argument("--fit2-start", default="2023-06-01")
    ap.add_argument("--fit2-end", default="2024-06-01")
    ap.add_argument("--milp-seconds", type=float, default=0, help="0 이면 MILP 생략")
    ap.add_argument("--out", default=None, help="최적 구성 저장 경로 (composition.csv 형식)")
    a = ap.parse_args()

    sites = sc.load_sites()
    cap = sites.capacity_kw.to_numpy(np.float64)
    x0 = (sites.current_group == "A").to_numpy(np.float64)          # 참조 구성: A → G1
    R, w = residuals(a.fit, a.fit_start, a.fit_end, sites)
    if a.fit2:                                           # 두 기간을 이어 붙여 함께 최적화 (한 해에 덜 치우침)
        R2, w2 = residuals(a.fit2, a.fit2_start, a.fit2_end, sites)
        R, w = np.vstack([R, R2]), np.concatenate([w, w2])
    lb = float((w * np.abs(R.sum(1))).sum())
    W0 = objective(x0, R, w)
    print(f"[fit] 시각 {R.shape[0]:,}  참조 구성 W {W0:,.0f}  하한 {lb:,.0f}")

    t = time.time()
    x, W = local_search(x0, R, w, cap)
    print(f"[fit] 국소 탐색 W {W:,.0f} ({(W / W0 - 1) * 100:+.2f}%)  {time.time() - t:.0f}s")
    if a.milp_seconds > 0:
        t = time.time()
        xm, Wm = milp(R, w, cap, a.milp_seconds)
        print(f"[fit] MILP W {Wm:,.0f} ({(Wm / W0 - 1) * 100:+.2f}%)  {time.time() - t:.0f}s")
        if xm is not None and Wm < W and feasible(xm, cap):
            x, W = xm, Wm
    print(f"[fit] 이동한 발전소 {int((x != x0).sum())}개  G1 {cap @ x:,.1f} kW / G2 {cap.sum() - cap @ x:,.1f} kW")

    if a.eval:
        Re, we = residuals(a.eval, a.eval_start, a.eval_end, sites)
        E0, E1 = objective(x0, Re, we), objective(x, Re, we)
        print(f"[eval] 참조 구성 W {E0:,.0f}  최적 구성 W {E1:,.0f}  ({(E1 / E0 - 1) * 100:+.2f}%)"
              f"  하한 {float((we * np.abs(Re.sum(1))).sum()):,.0f}")

    if a.out:
        g = np.where(x == 1, "G1", "G2")
        pd.DataFrame({"site_id": sites.site_id, "group": g}).to_csv(a.out, index=False)
        print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
