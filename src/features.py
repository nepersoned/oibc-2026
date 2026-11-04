"""특징(feature) 생성 — 새 특징은 여기에 추가한다.

규칙 (대회 공지):
- 각 대상일 예측에는 전날 17:00 KST 이전에 발행된 예보(round 10·17)만 사용
- 평가 기간 예보 전체로 정규화하거나 그 통계로 그룹을 나누지 않기
- 외부 기상을 발전소 좌표로 골라 붙이지 않기 (위경도는 태양 위치 계산에만)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from scoring import DATA, TZ, to_ts

WA_COLS = ["wa_cloud", "wa_temp", "wa_humidity", "wa_rain", "wa_wind_speed", "wa_ground_press"]
WB_COLS = ["wb_cloud", "wb_temp", "wb_rel_hum", "wb_uv_idx", "wb_precip_prob",
           "wb_total_liq", "wb_vis", "wb_wind_speed", "wb_dew_point"]
SOLAR_COLS = ["elev", "azim", "cosz", "doy_sin", "doy_cos", "hour"]
SITE_COLS = ["cap", "lat", "lon"]
FEATS = WA_COLS + WB_COLS + SOLAR_COLS + SITE_COLS


def solar(ts: pd.DatetimeIndex, lat: np.ndarray, lon: np.ndarray):
    """태양 고도·방위 (NOAA 근사, 도 단위). ts 는 우측닫힘이라 구간 중앙(-30분) 기준."""
    doy = ts.day_of_year.to_numpy()
    hour = ts.hour.to_numpy() + ts.minute.to_numpy() / 60.0
    g = 2 * np.pi / 365.0 * (doy - 1 + (hour - 12) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                       - 0.014615 * np.cos(2 * g) - 0.040849 * np.sin(2 * g))
    decl = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
            - 0.006758 * np.cos(2 * g) + 0.000907 * np.sin(2 * g)
            - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    tst = (hour - 0.5) * 60 + eqtime + 4 * (lon - 135.0)
    ha = np.radians(tst / 4.0 - 180.0)
    la = np.radians(lat)
    cosz = np.clip(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha), -1, 1)
    elev = 90.0 - np.degrees(np.arccos(cosz))
    az = np.degrees(np.arctan2(-np.sin(ha), np.tan(decl) * np.cos(la) - np.sin(la) * np.cos(ha))) % 360
    return elev.astype("float32"), az.astype("float32"), cosz.astype("float32")


def load_forecast(split: str, prov: str, cols: list[str]) -> pd.DataFrame:
    """split: 'train' | 'test', prov: 'wa' | 'wb'."""
    st = f"{prov}_station"
    f = pd.read_parquet(os.path.join(DATA, split, f"forecast_{prov}.parquet"),
                        columns=[st, "round", "ts"] + cols)
    f["ts"] = to_ts(f.ts)
    return f


def build(base: pd.DataFrame, sites: pd.DataFrame, fa: pd.DataFrame, fb: pd.DataFrame,
          rnd: int) -> pd.DataFrame:
    """(site_id, ts[, energy]) 격자에 예보·태양기하·발전소 정보를 붙인다."""
    d = base.merge(sites, on="site_id", how="left")
    d = d.merge(fa[fa["round"] == rnd].drop(columns="round"), on=["wa_station", "ts"], how="left")
    d = d.merge(fb[fb["round"] == rnd].drop(columns="round"), on=["wb_station", "ts"], how="left")
    ts = pd.DatetimeIndex(d.ts)
    d["elev"], d["azim"], d["cosz"] = solar(ts, d.lat.to_numpy(), d.lon.to_numpy())
    doy = ts.day_of_year.to_numpy()
    d["doy_sin"] = np.sin(2 * np.pi * doy / 365.25).astype("float32")
    d["doy_cos"] = np.cos(2 * np.pi * doy / 365.25).astype("float32")
    d["hour"] = ts.hour.to_numpy().astype("int8")
    d["cap"] = d.capacity_kw.astype("float32")
    return d


def grid(site_ids: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """발전소 × 시각 전체 격자 (start, end 포함)."""
    idx = pd.date_range(start, end, freq="h").astype(f"datetime64[ns, {TZ}]")
    return pd.MultiIndex.from_product([site_ids, idx], names=["site_id", "ts"]).to_frame(index=False)
