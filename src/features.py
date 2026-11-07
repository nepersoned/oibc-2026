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


# ---------------------------------------------------------------- rich feature set
WA_ALL = ["wa_cloud", "wa_temp", "wa_humidity", "wa_ground_press", "wa_wind_speed", "wa_rain", "wa_snow"]
WB_ALL = ["wb_cloud", "wb_temp", "wb_dew_point", "wb_rel_hum", "wb_uv_idx", "wb_vis", "wb_ceiling",
          "wb_precip_prob", "wb_rain_prob", "wb_snow_prob", "wb_total_liq", "wb_snow", "wb_wind_speed"]
CTX = {"wa": ["wa_cloud", "wa_humidity", "wa_rain"],
       "wb": ["wb_cloud", "wb_uv_idx", "wb_vis", "wb_precip_prob", "wb_ceiling"]}
R10 = {"wa": ["wa_cloud"], "wb": ["wb_cloud", "wb_uv_idx", "wb_precip_prob"]}
REGION = ["wa_cloud", "wb_cloud", "wb_uv_idx", "wb_precip_prob"]


def target_day(ts: pd.Series) -> pd.Series:
    """우측닫힘 ts 의 대상일 (ts=00:00 은 전날 24시). 같은 대상일의 예보만 묶기 위한 키."""
    return (ts - pd.Timedelta(hours=1)).dt.floor("D")


def prep_forecast(f: pd.DataFrame, prov: str, cols: list[str]) -> pd.DataFrame:
    """(station, round, ts) → (station, ts) 한 행.

    - 기본값: round 17, 결손이면 round 10 으로 채움 (둘 다 예측시점 이전 발행 → 허용)
    - round 10 값과 차이 (예보 갱신량)
    - 같은 대상일 안에서만 앞뒤 1·2시간, 일평균·주간(9~16시) 평균 — 대상일 경계를 넘지 않음
    """
    st = f"{prov}_station"
    r17 = f[f["round"] == 17].drop(columns="round").set_index([st, "ts"])
    r10 = f[f["round"] == 10].drop(columns="round").set_index([st, "ts"])
    idx = r17.index.union(r10.index)
    r17, r10 = r17.reindex(idx), r10.reindex(idx)
    d = r17.fillna(r10)
    for c in R10[prov]:
        d[f"{c}_r10"] = r10[c]
        d[f"{c}_d10"] = r17[c] - r10[c]
    d = d.reset_index().sort_values([st, "ts"])
    d["tday"] = target_day(d.ts)
    hr = d.ts.dt.hour
    g = d.groupby([st, "tday"], sort=False)
    for c in CTX[prov]:
        gc = g[c]
        for k in (1, 2):
            d[f"{c}_lag{k}"] = gc.shift(k)
            d[f"{c}_lead{k}"] = gc.shift(-k)
        d[f"{c}_dmean"] = gc.transform("mean")
        day = d[c].where(hr.between(9, 16))
        d[f"{c}_daymean"] = day.groupby([d[st], d.tday]).transform("mean")
    num = d.columns.difference([st, "ts", "tday"])
    d[num] = d[num].astype("float32")
    return d.drop(columns="tday")


def region_means(fa: pd.DataFrame, fb: pd.DataFrame) -> pd.DataFrame:
    """시각별 전체 관측지점 평균 (전국 요약 — 모든 발전소에 같은 값)."""
    a = fa.groupby("ts")[[c for c in REGION if c.startswith("wa")]].mean()
    b = fb.groupby("ts")[[c for c in REGION if c.startswith("wb")]].mean()
    r = a.join(b, how="outer").add_prefix("reg_").astype("float32")
    return r.reset_index()


EXT_MODELS = ["ecmwf_ifs025", "jma_seamless", "gfs_seamless"]
EXT_MODELS_2024 = ["icon_seamless", "gem_seamless", "meteofrance_seamless", "cma_grapes_global", "bom_access_global"]
USE_2024 = os.environ.get("OIBC_EXT2024", "0") == "1"      # 실험 스위치
_CALENDAR_DEFAULT = "legacy" if os.environ.get("OIBC_CAL", "1") == "1" else "none"
CAL_MODE = os.environ.get("OIBC_CAL_MODE", _CALENDAR_DEFAULT).strip().lower()
if CAL_MODE not in {"legacy", "weekday", "none"}:
    raise ValueError("OIBC_CAL_MODE must be one of: legacy, weekday, none")
CALENDAR = CAL_MODE != "none"                               # backward-compatible presence flag
USE_GFS = os.environ.get("OIBC_GFS", "1") == "1"          # NOAA GFS 원본 상자 평균
USE_GEFS = os.environ.get("OIBC_GEFS", "1") == "1"        # NOAA GEFS 평균·퍼짐
USE_UM = os.environ.get("OIBC_UM", "1") == "1"            # 기상청 UM 국지(LDAPS)
ENS_MODE = os.environ.get("OIBC_ENS", "all")               # ext_ghi_ens 계산 방식: all | stable
SPATIAL_MODE = os.environ.get("OIBC_SPATIAL", "none")     # none | a1 | a2
PHYSICS_MODE = os.environ.get("OIBC_PHYSICS", "none")     # none | b1
EXT_SOURCES = os.environ.get("OIBC_EXT_SOURCES", "legacy")  # legacy | no_openmeteo


def load_ext(mode: str = "mean") -> pd.DataFrame | None:
    """외부 수치예보 (src/fetch_external.py, 48시간 전 발행분, 고정 격자) → 시각별 특징. 모든 발전소에 같은 값.

    mode: 'none' | 'mean' — 고정 격자 25점의 **평균 하나로 요약**해 모든 발전소에 같은 값 (공지 5항).
    격자점별 값을 따로 열로 쓰지 않는다.
    """
    if mode == "none":
        return None
    if EXT_SOURCES not in {"legacy", "no_openmeteo"}:
        raise ValueError(f"unsupported OIBC_EXT_SOURCES={EXT_SOURCES}")
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_ext")
    out = None
    ghi_cols = []
    def add_source(frame: pd.DataFrame) -> None:
        nonlocal out
        out = frame if out is None else out.join(frame, how="outer")

    openmeteo_models = EXT_MODELS + (EXT_MODELS_2024 if USE_2024 else [])
    for m in (() if EXT_SOURCES == "no_openmeteo" else openmeteo_models):
        path = os.path.join(root, f"openmeteo_{m}.parquet")
        if not os.path.exists(path):
            continue
        f = pd.read_parquet(path)
        f["ts"] = f.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        g = f.groupby("ts").agg(**{f"ext_{m}_ghi": ("shortwave_radiation", "mean"),
                                   f"ext_{m}_cc": ("cloud_cover", "mean")})
        ghi_cols.append(f"ext_{m}_ghi")
        add_source(g)
    extra = os.path.join(root, "openmeteo_jma_extra.parquet")
    if EXT_SOURCES == "legacy" and os.path.exists(extra):       # Open-Meteo JMA 추가변수
        f = pd.read_parquet(extra)
        f["ts"] = f.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        cols = [c for c in f.columns if c not in {"ts", "pt"}]
        g = f.groupby("ts")[cols].mean().add_prefix("ext_jx_")
        add_source(g)
        ghi_cols += ["ext_jx_direct_radiation", "ext_jx_diffuse_radiation"]
    gfs = os.path.join(root, "gfs_hourly.parquet")
    if not os.path.exists(gfs):
        partial = os.path.join(root, "gfs_hourly_partial_full.parquet")
        if os.path.exists(partial):
            gfs = partial
    if USE_GFS and os.path.exists(gfs):                        # NOAA GFS 원본 (src/fetch_gfs.py), 상자 평균
        f = pd.read_parquet(gfs)
        f["ts"] = f.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        add_source(f.set_index("ts")[["gfs_ghi", "gfs_kcs", "gfs_tcc"]].add_prefix("ext_"))
        ghi_cols.append("ext_gfs_ghi")
    gefs = os.path.join(root, "gefs_hourly.parquet")
    if USE_GEFS and os.path.exists(gefs):                      # NOAA GEFS 평균 + 퍼짐 (src/fetch_gefs.py)
        f = pd.read_parquet(gefs)
        f["ts"] = f.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        cols = ["gefs_ghi", "gefs_kcs", "gefs_tcc", "gefs_ghi_spr", "gefs_tcc_spr", "gefs_kcs_spr"]
        add_source(f.set_index("ts")[cols].add_prefix("ext_"))
        ghi_cols.append("ext_gefs_ghi")
    um = os.path.join(root, "kma_um_hourly.parquet")
    if USE_UM and os.path.exists(um):                          # 기상청 UM 국지(LDAPS) D-1 00z (src/fetch_kma.py)
        f = pd.read_parquet(um)
        f["ts"] = f.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        add_source(f.set_index("ts")[["um_ghi", "um_dir", "um_dif"]].add_prefix("ext_"))
        ghi_cols.append("ext_um_ghi")
    # 앙상블 평균 일사: 'all' = 그 시점에 있는 모든 소스 평균 (소스 구성이 시기마다 바뀜 → 뜻이 변함)
    #                  'stable' = 학습·평가 전 기간에 항상 있는 소스만 (GFS 원본, 쓰는 경우 LDAPS)
    if out is None:
        raise FileNotFoundError("no external weather source available")
    ens_cols = [c for c in ghi_cols if c.endswith("_ghi")]
    if ENS_MODE == "stable":
        ens_cols = [c for c in ("ext_gfs_ghi", "ext_um_ghi") if c in out.columns] or ens_cols
    out["ext_ghi_ens"] = out[ens_cols].mean(axis=1)
    out = out.reset_index().sort_values("ts")
    if SPATIAL_MODE in {"a1", "a2"}:
        spatial_path = os.path.join(root, "gfs_spatial_features_2021_2024.csv")
        if not os.path.exists(spatial_path):
            raise FileNotFoundError(f"spatial feature table missing: {spatial_path}")
        spatial = pd.read_csv(spatial_path, parse_dates=["ts"])
        spatial["ts"] = pd.to_datetime(spatial.ts, utc=True).dt.tz_convert(TZ)
        a1 = ["sp_ghi_std", "sp_ghi_range", "sp_ghi_p10", "sp_ghi_p50", "sp_ghi_p90",
              "sp_tcc_std", "sp_tcc_range", "sp_tcc_p10", "sp_tcc_p50", "sp_tcc_p90"]
        a2 = ["sp_ghi_east_west", "sp_ghi_north_south", "sp_tcc_east_west", "sp_tcc_north_south",
              "sp_ghi_change_mean", "sp_ghi_change_std", "sp_tcc_change_mean", "sp_tcc_change_std",
              "sp_ghi_tcc_interaction", "sp_ghi_std_tcc_std_interaction"]
        cols = a1 + (a2 if SPATIAL_MODE == "a2" else [])
        out = out.merge(spatial[["ts"] + cols], on="ts", how="left", validate="one_to_one")
    out["tday"] = target_day(out.ts)
    for c in ghi_cols + ["ext_ghi_ens"]:
        g = out.groupby("tday")[c]
        out[f"{c}_dsum"] = g.transform("sum")                     # 대상일 총일사량 (같은 발행분)
        out[f"{c}_lag1"] = g.shift(1)
        out[f"{c}_lead1"] = g.shift(-1)
    num = out.columns.difference(["ts", "tday"])
    out[num] = out[num].astype("float32")
    return out.drop(columns="tday")


def load_wx(cutoff: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """1단계 날씨 보정 예측 (src/weather_model.py) + 대상일 내 문맥."""
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    out = []
    for prov in ("wa", "wb"):
        path = os.path.join(root, f"wx_{cutoff}_{prov}.parquet")
        if not os.path.exists(path):
            return None
        w = pd.read_parquet(path)
        w["ts"] = w.ts.dt.tz_convert(TZ).astype(f"datetime64[ns, {TZ}]")
        st = f"{prov}_station"
        w = w.sort_values([st, "ts"])
        w["tday"] = target_day(w.ts)
        for c in [c for c in w.columns if c.startswith("hat_")]:
            g = w.groupby([st, "tday"])[c]
            w[f"{c}_dmean"] = g.transform("mean")
            w[f"{c}_lag1"] = g.shift(1)
            w[f"{c}_lead1"] = g.shift(-1)
        out.append(w.drop(columns="tday"))
    return out[0], out[1]


def build_rich(base: pd.DataFrame, sites: pd.DataFrame, fa: pd.DataFrame, fb: pd.DataFrame,
               reg: pd.DataFrame, ext: pd.DataFrame | None = None,
               wx: tuple[pd.DataFrame, pd.DataFrame] | None = None) -> pd.DataFrame:
    d = base.merge(sites, on="site_id", how="left")
    d = d.merge(fa, on=["wa_station", "ts"], how="left")
    d = d.merge(fb, on=["wb_station", "ts"], how="left")
    d = d.merge(reg, on="ts", how="left")
    if ext is not None:
        d = d.merge(ext, on="ts", how="left")
    if wx is not None:
        d = d.merge(wx[0], on=["wa_station", "ts"], how="left")
        d = d.merge(wx[1], on=["wb_station", "ts"], how="left")
    ts = pd.DatetimeIndex(d.ts)
    d["elev"], d["azim"], d["cosz"] = solar(ts, d.lat.to_numpy(), d.lon.to_numpy())
    cz = np.clip(d.cosz.to_numpy(), 1e-3, None)
    d["ghi_cs"] = np.where(d.cosz > 0, 1098 * cz * np.exp(-0.057 / cz), 0).astype("float32")  # Haurwitz
    if PHYSICS_MODE == "b1" and "ext_gfs_ghi" in d:
        # B1: retain both source columns and expose their ratio.  Low-sun hours
        # are missing because the ratio has no useful physical interpretation.
        den = d["ghi_cs"].to_numpy(dtype="float64")
        num = d["ext_gfs_ghi"].to_numpy(dtype="float64")
        # Retain values above 1; forecast bias or cloud enhancement is not
        # clipped by assumption.
        ratio = np.divide(num, den, out=np.full(len(d), np.nan), where=den > 5.0)
        d["phys_gfs_ghi_cs_ratio"] = ratio.astype("float32")
    doy = ts.day_of_year.to_numpy()
    d["doy_sin"] = np.sin(2 * np.pi * doy / 365.25).astype("float32")
    d["doy_cos"] = np.cos(2 * np.pi * doy / 365.25).astype("float32")
    d["hour"] = ts.hour.to_numpy().astype("int8")
    d["cap"] = d.capacity_kw.astype("float32")
    d["site_code"] = d.site_id.str[2:].astype("int16")
    if CAL_MODE != "none":
        cal = calendar(d.ts, CAL_MODE)
        for c in cal.columns:
            d[c] = cal[c].to_numpy()
    return d


def rich_feats(d: pd.DataFrame) -> list[str]:
    drop = {"site_id", "ts", "energy", "smp", "current_group", "capacity_kw", "wa_station", "wb_station"}
    return [c for c in d.columns if c not in drop]


# 임시공휴일·선거일 (공지상 사용 허용) — holidays 패키지에 없을 수 있는 날을 직접 추가
EXTRA_OFF = ["2022-03-09", "2022-06-01", "2023-10-02", "2024-04-10", "2024-10-01", "2025-01-27", "2025-06-03",
             "2026-06-03"]


def off_days() -> set:
    import holidays
    kr = holidays.country_holidays("KR", years=range(2020, 2027))
    return {pd.Timestamp(d) for d in kr} | {pd.Timestamp(d) for d in EXTRA_OFF}


_OFF = None


def calendar(ts: pd.Series, mode: str | None = None) -> pd.DataFrame:
    """Calendar features keyed by right-closed target day.

    `weekday` and `none` never consult the external holiday package or EXTRA_OFF.
    """
    global _OFF
    mode = (mode or CAL_MODE).strip().lower()
    if mode not in {"legacy", "weekday", "none"}:
        raise ValueError("calendar mode must be one of: legacy, weekday, none")
    source = pd.Series(ts)
    day = target_day(source).dt.tz_localize(None)
    dow = day.dt.dayofweek
    if mode == "none":
        return pd.DataFrame(index=source.index)
    if mode == "weekday":
        return pd.DataFrame({"dow": dow.astype("int8").to_numpy(),
                             "is_weekend": (dow >= 5).astype("int8").to_numpy()},
                            index=source.index)
    if _OFF is None:
        _OFF = off_days()
    hol = day.isin(_OFF)
    off = (dow >= 5) | hol
    prev_off = (day - pd.Timedelta(days=1)).isin(_OFF) | ((day - pd.Timedelta(days=1)).dt.dayofweek >= 5)
    next_off = (day + pd.Timedelta(days=1)).isin(_OFF) | ((day + pd.Timedelta(days=1)).dt.dayofweek >= 5)
    return pd.DataFrame({"dow": dow.astype("int8").to_numpy(), "is_hol": hol.astype("int8").to_numpy(),
                         "is_off": off.astype("int8").to_numpy(),
                         "off_run": (off & (prev_off | next_off)).astype("int8").to_numpy()})


def grid(site_ids: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """발전소 × 시각 전체 격자 (start, end 포함)."""
    idx = pd.date_range(start, end, freq="h").astype(f"datetime64[ns, {TZ}]")
    return pd.MultiIndex.from_product([site_ids, idx], names=["site_id", "ts"]).to_frame(index=False)
