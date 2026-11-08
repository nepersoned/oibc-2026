"""Fetch audited NOAA GFS instantaneous cloud-layer box means for SM#58.

The tool only requests the three GRIB message byte ranges identified in each
public index. It never downloads a whole GRIB file and writes a local parquet.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import fetch_gfs as gfs  # noqa: E402

BASE = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
FIELDS = {"gfs_lcdc": ("LCDC", "low cloud layer"),
          "gfs_mcdc": ("MCDC", "middle cloud layer"),
          "gfs_hcdc": ("HCDC", "high cloud layer")}
LEADS = tuple(range(15, 40, 3))
TZ = "Asia/Seoul"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def get(url: str, byte_range: tuple[int, int] | None = None, tries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url)
            if byte_range:
                req.add_header("Range", f"bytes={byte_range[0]}-{byte_range[1]}")
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except Exception as exc:  # bounded retries for public object transport
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404):
                break
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}: {last}")


def object_urls(init_day: date, lead: int) -> tuple[tuple[str, str], ...]:
    stem = f"gfs.t00z.pgrb2.1p00.f{lead:03d}"
    return ((f"{BASE}/gfs.{init_day:%Y%m%d}/00/atmos/{stem}.idx",
             f"{BASE}/gfs.{init_day:%Y%m%d}/00/atmos/{stem}"),
            (f"{BASE}/gfs.{init_day:%Y%m%d}/00/{stem}.idx",
             f"{BASE}/gfs.{init_day:%Y%m%d}/00/{stem}"))


def messages(index_text: str, lead: int) -> dict[str, tuple[int, int]]:
    lines = index_text.strip().splitlines()
    found: dict[str, tuple[int, int]] = {}
    for i, line in enumerate(lines):
        p = line.split(":")
        if len(p) < 6 or " hour fcst" not in p[5] or "ave fcst" in p[5]:
            continue
        if p[5].strip() != f"{lead} hour fcst":
            continue
        for out_name, (short_name, level) in FIELDS.items():
            if p[3] == short_name and p[4] == level:
                start = int(p[1])
                end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else start + 5_000_000
                found[out_name] = (start, end)
    return found


def fetch_init(init_day: date) -> tuple[date, dict[int, dict[str, float]], int]:
    by_lead: dict[int, dict[str, float]] = {}
    bytes_read = 0
    for lead in LEADS:
        idx = None
        grib_url = ""
        for idx_url, candidate_grib_url in object_urls(init_day, lead):
            try:
                idx = get(idx_url)
                grib_url = candidate_grib_url
                break
            except RuntimeError:
                continue
        if idx is None:
            raise RuntimeError(f"{init_day} f{lead:03d}: no accessible index")
        bytes_read += len(idx)
        ranges = messages(idx.decode("utf-8"), lead)
        if set(ranges) != set(FIELDS):
            return init_day, {}, bytes_read
        vals: dict[str, float] = {}
        for out_name, bounds in ranges.items():
            raw = get(grib_url, bounds)
            bytes_read += len(raw)
            vals[out_name] = gfs.box_mean(raw)
        by_lead[lead] = vals
    return init_day, by_lead, bytes_read


def hourly_rows(init_day: date, by_lead: dict[int, dict[str, float]]) -> list[dict]:
    """Interpolate f015/f018/.../f039 to target leads 16..39 (KST 01..24)."""
    rows: list[dict] = []
    anchor = pd.Timestamp(init_day, tz="UTC")
    for target_lead in range(16, 40):
        lo = 15 + 3 * ((target_lead - 15) // 3)
        hi = lo if target_lead == lo else lo + 3
        frac = 0.0 if hi == lo else (target_lead - lo) / (hi - lo)
        row = {"ts": (anchor + pd.Timedelta(hours=target_lead)).tz_convert(TZ)}
        for name in FIELDS:
            row[name] = float(np.clip((1.0 - frac) * by_lead[lo][name] + frac * by_lead[hi][name], 0.0, 100.0))
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-start", required=True, help="inclusive KST target day")
    ap.add_argument("--target-end", required=True, help="inclusive KST target day")
    ap.add_argument("--eligibility-csv", required=True, help="run audit with index/GRIB cutoff results")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", default="outputs/sm58/cloud_cache")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if not 1 <= a.workers <= 16:
        raise SystemExit("workers must be in 1..16")
    targets = pd.date_range(a.target_start, a.target_end, freq="D")
    init_days = [d.date() - timedelta(days=1) for d in targets]
    audit = pd.read_csv(a.eligibility_csv)
    audit["init_date"] = pd.to_datetime(audit.init_date).dt.date
    audit["last_modified"] = pd.to_datetime(audit.last_modified, utc=True, errors="coerce")
    audit["grib_last_modified"] = pd.to_datetime(audit.grib_last_modified, utc=True, errors="coerce")
    cutoff = pd.to_datetime(pd.Series(init_days)).dt.tz_localize("UTC") + pd.Timedelta(hours=8)
    cutoff_by_day = dict(zip(init_days, cutoff))
    valid = audit[(audit.init_date.isin(init_days)) & audit.status.eq(200) & audit.grib_status.eq(200)]
    cutoff_for_row = valid.init_date.map(cutoff_by_day)
    valid = valid[valid.last_modified.le(cutoff_for_row) & valid.grib_last_modified.le(cutoff_for_row)]
    eligible = valid.groupby("init_date").lead.nunique()
    required = set(LEADS)
    eligible_days = sorted(day for day, n in eligible.items() if n == len(required))
    if len(eligible_days) < int(np.ceil(0.95 * len(init_days))):
        raise SystemExit(f"eligible GRIB run support below preregistered 95%: {len(eligible_days)}/{len(init_days)}")
    skipped_days = sorted(set(init_days) - set(eligible_days))
    cache_dir = Path(a.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[date, dict[int, dict[str, float]], int]] = []
    missing: list[date] = []
    for day in eligible_days:
        cache_path = cache_dir / f"{day:%Y%m%d}.json"
        if not cache_path.exists():
            missing.append(day)
            continue
        try:
            obj = json.loads(cache_path.read_text(encoding="utf-8"))
            by_lead = {int(k): v for k, v in obj["values"].items()}
            if set(by_lead) != set(LEADS) or any(set(v) != set(FIELDS) for v in by_lead.values()):
                raise ValueError("cache schema mismatch")
            if not np.isfinite([[v[name] for name in FIELDS] for v in by_lead.values()]).all():
                raise ValueError("non-finite cached value")
            results.append((day, by_lead, int(obj.get("payload_bytes", 0))))
        except Exception:
            missing.append(day)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(fetch_init, day): day for day in missing}
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            day, values, nbytes = result
            if values:
                (cache_dir / f"{day:%Y%m%d}.json").write_text(
                    json.dumps({"init_date": day.isoformat(), "values": values,
                                "payload_bytes": nbytes}, separators=(",", ":")), encoding="utf-8")
            if i % 25 == 0:
                print(f"decoded {i}/{len(futures)} uncached runs", flush=True)
    hourly: list[dict] = []
    payload_bytes = 0
    field_missing_days = []
    for day, by_lead, nbytes in results:
        if not by_lead:
            field_missing_days.append(day.isoformat())
            continue
        payload_bytes += nbytes
        hourly.extend(hourly_rows(day, by_lead))
    frame = pd.DataFrame(hourly).sort_values("ts").reset_index(drop=True)
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    start_day, end_day = date.fromisoformat(a.target_start), date.fromisoformat(a.target_end)
    evaluation_splits = {
        "train_2022_06_to_2024_05": (date(2022, 6, 1), date(2024, 5, 31)),
        "validation_2024_06_to_2025_05": (date(2024, 6, 1), date(2025, 5, 31)),
    }
    split_coverage = {}
    available_dates = {(x - pd.Timedelta(hours=1)).date() for x in frame.ts.dt.tz_convert(TZ)}
    for name, (split_a, split_b) in evaluation_splits.items():
        if split_a < start_day or split_b > end_day:
            continue
        n_expected = (split_b - split_a).days + 1
        n_present = sum(split_a <= d <= split_b for d in available_dates)
        split_coverage[name] = {"target_days": n_expected, "days_with_layers": n_present,
                                "coverage_pct": round(100 * n_present / n_expected, 4)}
        if n_present < int(np.ceil(0.95 * n_expected)):
            raise SystemExit(f"layer-field coverage below 95% in {name}: {n_present}/{n_expected}")
    meta = {"target_start": a.target_start, "target_end": a.target_end,
            "requested_target_days": len(init_days), "eligible_runs": len(eligible_days),
            "skipped_init_dates": [d.isoformat() for d in skipped_days],
            "field_missing_dates": field_missing_days, "split_coverage": split_coverage,
            "lead_hours": list(range(16, 40)), "anchor_leads": list(LEADS),
            "box": "fixed 20 points: 34..38N x 126..129E, 1-degree grid",
            "field_time_semantics": "instantaneous forecast; linear interpolation",
            "response_payload_bytes": payload_bytes, "rows": len(frame), "out": str(path),
            "output_sha256": sha256_file(path),
            "eligibility_audit_sha256": sha256_file(Path(a.eligibility_csv)),
            "script_sha256": sha256_file(Path(__file__).resolve())}
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
