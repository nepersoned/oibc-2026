"""Fixed-grid spatial weather summaries for the Research A experiment.

The functions operate on the fixed 34--38N, 126--129E GFS box used by
``fetch_gfs.py``.  They never use plant coordinates.  A caller must provide
the original GRIB grid values; aggregate hourly parquet files are not enough
to reconstruct these features.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np


def summarize_arrays(ghi: np.ndarray, tcc: np.ndarray, previous: Mapping[str, np.ndarray] | None = None) -> dict[str, float]:
    """Return A1/A2 summaries for two same-shaped fixed-grid arrays.

    ``ghi`` is DSWRF (W/m²) and ``tcc`` is total cloud cover (% or the source
    unit); all statistics preserve the source unit.  NaNs are ignored.  A2
    temporal features are emitted only when a previous grid is supplied.
    """
    g = np.asarray(ghi, dtype=float)
    c = np.asarray(tcc, dtype=float)
    if g.shape != c.shape or g.ndim != 2:
        raise ValueError("ghi and tcc must be same-shaped 2-D grids")

    def stats(x: np.ndarray, prefix: str) -> dict[str, float]:
        valid = x[np.isfinite(x)]
        if valid.size == 0:
            return {f"{prefix}_{s}": float("nan") for s in ("std", "range", "p10", "p50", "p90")}
        return {
            f"{prefix}_std": float(np.std(valid)),
            f"{prefix}_range": float(np.max(valid) - np.min(valid)),
            f"{prefix}_p10": float(np.percentile(valid, 10)),
            f"{prefix}_p50": float(np.percentile(valid, 50)),
            f"{prefix}_p90": float(np.percentile(valid, 90)),
        }

    def mean(x: np.ndarray) -> float:
        return float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")

    # Arrays are north-to-south and west-to-east, matching the GFS grid subset.
    # For even dimensions both halves are used; for odd dimensions the centre
    # row/column is omitted so the comparison remains symmetric.
    mid_y, mid_x = g.shape[0] // 2, g.shape[1] // 2
    north, south = (slice(0, mid_y), slice(mid_y, None)) if g.shape[0] % 2 == 0 else (slice(0, mid_y), slice(mid_y + 1, None))
    west, east = (slice(0, mid_x), slice(mid_x, None)) if g.shape[1] % 2 == 0 else (slice(0, mid_x), slice(mid_x + 1, None))
    out = {**stats(g, "sp_ghi"), **stats(c, "sp_tcc")}
    out.update({
        "sp_ghi_east_west": mean(g[:, east]) - mean(g[:, west]),
        "sp_ghi_north_south": mean(g[north, :]) - mean(g[south, :]),
        "sp_tcc_east_west": mean(c[:, east]) - mean(c[:, west]),
        "sp_tcc_north_south": mean(c[north, :]) - mean(c[south, :]),
        "sp_ghi_tcc_interaction": mean(g) * mean(c),
        "sp_ghi_std_tcc_std_interaction": out["sp_ghi_std"] * out["sp_tcc_std"],
    })
    if previous is not None:
        pg, pc = np.asarray(previous["ghi"], dtype=float), np.asarray(previous["tcc"], dtype=float)
        if pg.shape != g.shape or pc.shape != c.shape:
            raise ValueError("previous grids must have the same shape")
        out["sp_ghi_change_mean"] = mean(g - pg)
        out["sp_ghi_change_std"] = float(np.nanstd(g - pg))
        out["sp_tcc_change_mean"] = mean(c - pc)
        out["sp_tcc_change_std"] = float(np.nanstd(c - pc))
    return out


def decode_fixed_box_with_metadata(grib: bytes, lat_min: float = 34.0, lat_max: float = 38.0,
                     lon_min: float = 126.0, lon_max: float = 129.0) -> tuple[np.ndarray, dict]:
    """Decode one GRIB message and select the fixed geographic box.

    Importing ecCodes is deliberately deferred so feature definitions remain
    testable in environments where native GRIB bindings are unavailable.
    """
    try:
        import eccodes
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("ecCodes is required to decode spatial GRIB input") from exc
    h = eccodes.codes_new_from_message(grib)
    try:
        vals = np.asarray(eccodes.codes_get_values(h), dtype=float)
        nj, ni = int(eccodes.codes_get(h, "Nj")), int(eccodes.codes_get(h, "Ni"))
        lat0 = float(eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees"))
        lon0 = float(eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees"))
        dlat = float(eccodes.codes_get(h, "jDirectionIncrementInDegrees"))
        dlon = float(eccodes.codes_get(h, "iDirectionIncrementInDegrees"))
        meta = {k: eccodes.codes_get(h, k) for k in (
            "shortName", "paramId", "typeOfLevel", "units", "stepType",
            "startStep", "endStep", "dataDate", "dataTime", "gridType",
        ) if eccodes.codes_is_defined(h, k)}
    finally:
        eccodes.codes_release(h)
    grid = vals.reshape(nj, ni)
    lats = lat0 - np.arange(nj) * dlat if lat0 > 0 else lat0 + np.arange(nj) * dlat
    lons = (lon0 + np.arange(ni) * dlon) % 360
    yi = np.flatnonzero((lats >= lat_min) & (lats <= lat_max))
    xi = np.flatnonzero((lons >= lon_min) & (lons <= lon_max))
    if yi.size == 0 or xi.size == 0:
        raise ValueError("GRIB grid does not cover the fixed research box")
    return grid[np.ix_(yi, xi)], {
        **meta, "Nj": nj, "Ni": ni, "latitude_first": lat0,
        "longitude_first": lon0, "latitude_increment": dlat,
        "longitude_increment": dlon, "scan_north_to_south": bool(lat0 > 0),
        "selected_rows": yi.tolist(), "selected_cols": xi.tolist(),
    }


def decode_fixed_box(grib: bytes, lat_min: float = 34.0, lat_max: float = 38.0,
                     lon_min: float = 126.0, lon_max: float = 129.0) -> np.ndarray:
    """Compatibility wrapper returning only the selected grid values."""
    grid, _ = decode_fixed_box_with_metadata(grib, lat_min, lat_max, lon_min, lon_max)
    return grid
