# SM#57 Next Decision

Date: 2026-11-08 (KST)

## Decision

**Stop before model training; do not adopt GFS vertical-cloud features.**

The sampled NOAA GRIB2 indexes confirm that LCDC/MCDC/HCDC coexist with TCDC and DSWRF at f018/f039 across sampled 2021-04 through 2026-05 dates. JH#43/#48/#60/#66/#67 do not explicitly use those vertical-layer variables, so the feature idea is not a direct duplicate. These findings establish technical availability at sampled points, not complete historical/evaluation coverage or valid public release before the competition cutoff.

NOAA's general public-domain/open-data information supports broad public/commercial reuse, but it does not establish this competition's approval for the source. Neither the historical AWS object timestamps nor a repository comment that 00Z data are “usually” published around 03–05 UTC supplies date/run-specific evidence that every feature was available by D−1 17:00 KST. The source eligibility and cutoff are therefore unresolved. The required pilot and bootstrap were not run; W is **Not Run**.

## Next action

Do not collect or use these GFS fields for a submission unless the team obtains (a) operational dissemination timestamps or equivalent trustworthy per-run evidence, (b) a complete date × lead availability audit for both training and evaluation periods, and (c) explicit confirmation that the competition permits the source. After those conditions pass, use the frozen A-vs-B design in [SM57_PREREGISTRATION.md](SM57_PREREGISTRATION.md). Until then, preserve the current candidate files and prioritize source lineage/eligibility confirmation over more model work.

No model, submission, or external-source feature code was changed in SM#57.

## Repository checks

- `python -m compileall -q src`: passed.
- GFS-related pytest with repository `.venv`: 7 passed, 3 failed. The three failures are the existing `test_build_hourly_synthetic_day` and two `test_export_gfs_partial` synthetic-grid tests; they expect 24 hourly rows but the current GFS builder emits a larger frame (`38688` rows in the first test). No code was changed to alter these pre-existing behaviors.
- `git diff --check`: passed.
