# SM#58 GFS Test Failure Root Cause

Date: 2026-11-08 (KST)

## Findings

The three SM57 failures were caused by a **runtime path injection/isolation bug**, not by wrong target-date filtering or a bad 24-hour expectation.

`fetch_gfs.build_hourly(raw_dir: str = RAW)` bound the original production `RAW` path when Python imported the module. The tests and `export_gfs_partial` later patched `fetch_gfs.RAW` to a temporary/staging directory and called `build_hourly()` without an explicit argument, but Python continued using the captured production path. The local production cache had 1,612 raw files, so the synthetic one-day test saw 38,688 rows (1,612 × 24); the partial exporter likewise read outside its isolated staging directory and rejected the result.

Classification: **A — test/staging isolation failure caused by import-time default argument binding.** It also exposed a real defect in the partial exporter path: its intended staged isolation was not actually honored. The underlying build's normal CLI explicitly passes `a.raw_dir`, so ordinary configured production builds were not changed by the fix.

## Minimal fix

Changed the function signature to `build_hourly(raw_dir: str | None = None)` and resolve `RAW` inside the call when no argument is supplied. This preserves the default behavior while allowing callers to safely redirect the raw directory after import. No cached GFS objects or output files were modified.

## Regression validation

Before fix: the three affected tests failed with 38,688 rows / unexpected partial grid. After fix:

```text
python -m pytest -q tests/test_gfs_time_conversion.py tests/test_partial_gfs_runner.py tests/test_export_gfs_partial.py
10 passed
```

The pre-fix behavior was reproduced in this SM58 turn: the synthetic-day test returned 38,688 rather than 24 rows, and both isolated partial-export tests raised `unexpected partial grid` (3 failed, 1 passed in the two files). After the correction, all related GFS tests passed (16 passed across time conversion, partial runner/export, repair/recovery ledger, and spatial features); the full repository suite also passed (67 passed; 9 existing Pandas deprecation warnings).
