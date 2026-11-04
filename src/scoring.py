"""로컬 검증 채점기 — 학습 구간 일부를 평가 구간처럼 떼어 대회와 같은 식으로 정산금 S를 계산한다.

    S = Σ SMP(t)·실적(t) − 0.10 × Σ_g Σ_t SMP(t)·k(t)·|예측(g,t) − 실적(g,t)|
    k(t) = 3 (ts의 시가 11~15), 그 외 1

입력은 **발전소별 예측** (site_id, ts, kwh) 이다. 학습 구간 실적에는 결측(행 없음)이 있으므로,
집합 합계는 실적이 있는 (site_id, ts) 만 더해서 예측과 실적을 같은 범위로 맞춘다.
(평가 구간 실적은 결측이 없으므로 대회 채점과 차이는 이 마스킹뿐이다.)

출력은 집계값만 — 원본 행은 출력하지 않는다.

    .venv/Scripts/python.exe src/scoring.py --pred outputs/val_baseline_sites.parquet
    .venv/Scripts/python.exe src/scoring.py --pred P.parquet --composition C.csv --start 2024-06-01 --end 2025-06-01
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "handover 2", "01_participant_dataset")
TZ = "Asia/Seoul"
GROUPS = ("G1", "G2")
MIN_CAP = 20_000.0
PENALTY_RATE = 0.10
VAL_START = "2024-06-01"     # 검증 구간: (VAL_START 00:00, VAL_END 00:00] — 우측닫힘이라 첫 시각은 01:00
VAL_END = "2025-06-01"


def to_ts(s: pd.Series) -> pd.Series:
    """문자열/타임존 timestamp 를 KST ns 단위로 통일 (merge 키 dtype 일치용)."""
    t = pd.to_datetime(s)
    t = t.dt.tz_localize(TZ) if t.dt.tz is None else t.dt.tz_convert(TZ)
    return t.astype(f"datetime64[ns, {TZ}]")


def window(start: str, end: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """우측닫힘 구간 (start, end] 의 첫·마지막 ts."""
    a = pd.Timestamp(start, tz=TZ) + pd.Timedelta(hours=1)
    b = pd.Timestamp(end, tz=TZ)
    return a, b


def k_weight(ts: pd.Series) -> np.ndarray:
    return np.where(ts.dt.hour.between(11, 15), 3, 1)


def load_sites() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA, "sites.csv"))


def load_smp() -> pd.Series:
    s = pd.read_csv(os.path.join(DATA, "train", "smp.csv"))
    return pd.Series(s.smp.to_numpy(), index=to_ts(s.ts), name="smp")


def load_actual(start: str = VAL_START, end: str = VAL_END) -> pd.DataFrame:
    a, b = window(start, end)
    g = pd.read_parquet(os.path.join(DATA, "train", "generation.parquet"))
    g["ts"] = to_ts(g.ts)
    return g[(g.ts >= a) & (g.ts <= b)].reset_index(drop=True)


def reference_composition(sites: pd.DataFrame) -> pd.Series:
    return sites.set_index("site_id").current_group.map({"A": "G1", "B": "G2"})


def read_composition(path: str) -> pd.Series:
    c = pd.read_csv(path)
    return pd.Series(c.group.to_numpy(), index=c.site_id.to_numpy())


def check_composition(comp: pd.Series, sites: pd.DataFrame) -> list[str]:
    errs = []
    want = set(sites.site_id)
    if set(comp.index) != want or comp.index.duplicated().any():
        errs.append("composition 의 site_id 가 sites.csv 253개와 정확히 일치하지 않음")
    if not set(comp.unique()) <= set(GROUPS):
        errs.append("group 값은 G1/G2 만 허용")
    cap = sites.set_index("site_id").capacity_kw
    for g in GROUPS:
        c = cap.reindex(comp[comp == g].index).sum()
        if c < MIN_CAP:
            errs.append(f"{g} 설비용량 {c:,.1f} kW < {MIN_CAP:,.0f}")
    return errs


def score(pred: pd.DataFrame, comp: pd.Series, actual: pd.DataFrame, smp: pd.Series) -> dict:
    """pred: site_id, ts, kwh  /  actual: site_id, ts, energy  /  comp: site_id -> G1|G2."""
    p = pred[["site_id", "ts", "kwh"]].copy()
    p["ts"] = to_ts(p.ts)
    m = actual.merge(p, on=["site_id", "ts"], how="left")
    n_missing = int(m.kwh.isna().sum())
    if n_missing:
        raise ValueError(f"실적이 있는 (site_id, ts) 중 예측이 없는 행 {n_missing:,}개")
    if (m.kwh < 0).any() or not np.isfinite(m.kwh).all():
        raise ValueError("예측에 음수 또는 NaN/inf 가 있음")
    m["group"] = m.site_id.map(comp)

    g = m.groupby(["group", "ts"], as_index=False).agg(act=("energy", "sum"), pred=("kwh", "sum"))
    g["smp"] = g.ts.map(smp)
    if g.smp.isna().any():
        raise ValueError("SMP 가 없는 시각이 있음")
    g["k"] = k_weight(g.ts)
    g["err"] = (g.pred - g.act).abs()
    g["pen"] = PENALTY_RATE * g.smp * g.k * g.err
    g["pen0"] = PENALTY_RATE * g.smp * g.k * g.act.abs()        # 0 예측 시 페널티 (기준선)

    revenue = float((g.smp * g.act).sum())
    W = float(g.pen.sum())
    W0 = float(g.pen0.sum())
    per = g.groupby("group").agg(W=("pen", "sum"), abs_err=("err", "sum"), act=("act", "sum"))
    return {
        "S": revenue - W,
        "revenue": revenue,
        "W": W,
        "W_ratio": W / revenue if revenue else np.nan,       # 매출 대비 페널티 비율
        "skill_vs_zero": 1 - W / W0 if W0 else np.nan,       # 0 예측 대비 페널티 감소율
        "abs_err": float(g.err.sum()),                       # 동점 처리용 비가중 절대오차 합
        "per_group": per,
        "hours": int(g.ts.nunique()),
        "site_hours": len(m),
    }


def report(r: dict, label: str = "") -> None:
    print(f"\n=== 검증 점수 {label}===")
    print(f"S (정산금)        {r['S']:>18,.0f} 원")
    print(f"매전수익           {r['revenue']:>18,.0f} 원")
    print(f"페널티 W           {r['W']:>18,.0f} 원   (매출 대비 {r['W_ratio']*100:.3f}%)")
    print(f"0예측 대비 개선율  {r['skill_vs_zero']*100:>17.2f} %")
    print(f"비가중 |오차| 합   {r['abs_err']:>18,.0f} kWh")
    print(f"채점 시각 {r['hours']:,}h / 발전소-시각 {r['site_hours']:,}")
    for grp, row in r["per_group"].iterrows():
        print(f"  {grp}: W {row.W:>15,.0f} 원   |오차| {row.abs_err:>13,.0f} kWh   실적 {row.act:>14,.0f} kWh"
              f"   nMAE {row.abs_err / row.act * 100:.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description="로컬 검증 채점 (집계값만 출력)")
    ap.add_argument("--pred", required=True, help="발전소별 예측 parquet/csv (site_id, ts, kwh)")
    ap.add_argument("--composition", default=None, help="composition.csv (기본: sites.csv 의 current_group)")
    ap.add_argument("--start", default=VAL_START)
    ap.add_argument("--end", default=VAL_END)
    a = ap.parse_args()

    sites = load_sites()
    comp = read_composition(a.composition) if a.composition else reference_composition(sites)
    errs = check_composition(comp, sites)
    if errs:
        raise SystemExit("[무효 구성] " + "; ".join(errs))
    pred = pd.read_parquet(a.pred) if a.pred.endswith(".parquet") else pd.read_csv(a.pred)
    actual = load_actual(a.start, a.end)
    report(score(pred, comp, actual, load_smp()), f"({a.start} ~ {a.end}] ")


if __name__ == "__main__":
    main()
