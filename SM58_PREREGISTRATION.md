# SM#58 Conditional Pilot Preregistration

Date: 2026-11-08 (KST)

## Single hypothesis

On the same fixed-grid GFS 1° source, add forecast low-, middle-, and high-cloud-cover fields to the existing GFS DSWRF/TCDC and WA/WB inputs. Do the three vertical-layer fields reduce 2024–25 group settlement W on an identical observed-site-hour mask?

## Gate before training

Training is allowed only after:

1. Daily run/lead `.idx` and GRIB payload objects are audited for public availability and S3 Last-Modified; for target day D retain a run only if every required index and payload object is publicly retrievable and each current object version was last modified no later than D−1 08:00 UTC (17:00 KST).
2. A representative index scan confirms the expected GRIB field, level, step type, and time-window semantics across each product era.
3. Eligible daily-run coverage is at least 95% of each evaluated daylight period and at least 95% of the training target days. Missing runs are masked consistently; do not impute absent forecasts with observations or zero.
4. Fixed 34–38°N × 126–129°E grid is used for every site; licensing/re-download evidence is adequate; no future observations or post-cutoff inputs enter features.
5. The GFS raw time builder uses an isolated raw directory and the GFS test suite passes.

The 95% gate is a predeclared practical support criterion, not a claim that OIBC requires complete coverage.

## Fixed comparison

- **A (baseline):** existing calendar-weekday Site LightGBM features, competition WA/WB, GFS DSWRF/TCDC.
- **B (candidate):** A plus exactly `gfs_lcdc`, `gfs_mcdc`, `gfs_hcdc` from the same fixed 20 grid points.
- Fit Site-only predictions and aggregate them by the frozen reference composition for settlement scoring; no Group model or blend is added in this pilot.
- Only input features differ. Same rows, train window, model parameters, one seed, reference composition, prediction mask, and scoring implementation.
- `fset=rich`, `site_code` dropped, `weight=none`, LightGBM `PARAMS` unchanged, `random_state=7`, objective default regression/L2. Calendar is weekday-only.
- Environment: `OIBC_CAL_MODE=weekday`, `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_GFS=1`, `OIBC_GEFS=0`, `OIBC_UM=0`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`; use `--ext mean` so the baseline contains only the explicitly audited NOAA GFS source in addition to WA/WB. No other external source is admitted.
- Training window: two years immediately preceding the 2024–25 evaluation window, using existing pipeline's time-cut convention.
- First run: seed 7; no multi-seed expansion.
- Primary metric: official reference-composition settlement W on common observed site-hour rows. Secondary: G1/G2, 11–15, month, site MAE, signed bias and cancellation benefit.
- If W worsens, stop. If point W improves, calculate paired 168-hour moving-block bootstrap before considering any further work.
- Use a run only if all required hourly-source lead files pass the pre-cutoff check; common row mask for A/B. Forecast hours without eligible GFS run are dropped from both models' training and evaluation comparisons, not filled with realized data.
- Compute budget: one two-year train window, one 365-day validation window, one fit per arm at the existing LightGBM parameter set, and at most 3 GB of selected GFS message-range transfer for the required 2022-06–2025-05 target days. No full GRIB files, second validation year, or extra seeds.
- `ext_gfs_kcs` is undefined at night by construction; it remains NaN and is not used to decide whether a GFS run/hour is missing. The common row mask requires valid GFS irradiance proxy, TCDC, and all three cloud-layer values, while the model's existing daylight-only training rule is preserved.

## Layer time construction (fixed before scores)

Read instantaneous forecast messages for each of LCDC/MCDC/HCDC from the `.idx` at 3-hour leads 15, 18, …, 39. Compute the mean over the same fixed 20 grid points, then linearly interpolate between these instantaneous values for target leads 16–39; lead 15 is only the left anchor for lead 16. Clip to the physical 0–100% interval. This avoids treating instantaneous fields as period averages. Map target 01–24 KST to D−1 00 UTC initialization. If any index era lacks the instantaneous field or uses incompatible step semantics, exclude that era rather than silently substituting an average.

## Stop and adoption rules

- No training if any source/coverage/test gate fails.
- A single-seed improvement is exploratory only. If it worsens, stop. If it improves, report bootstrap; do not tune thresholds or expand seeds in the same validation period.
- No submission candidate, leaderboard mixing, or official upload in SM#58.
- Reused 2024–25 validation is not an independent future test.
