# SM#52 Feasibility Audit

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `e00d9f6dc540e97a1ae08000532639d77bfdca17`
Decision: **stop before feature implementation or model training**.

## Executive finding

The package contains historical generation and enough history to calculate raw morning/afternoon observation support. It does **not** contain strict time-ordered OOF Site residuals. Producing the residual history needed for a feature on every training row requires a new rolling-origin prediction pipeline and repeated Site model fits. In the 2023–24 training window, only 106 of 253 plants have any daylight generation, representing 20.89% of total capacity; only 93 plants (18.07% of capacity) have at least 100 observed target days on each solar side. G2 has only six reporting plants and 2.61% capacity coverage. The signal would therefore be absent or heavily shrunk for most of the portfolio in the primary selection year.

Given the explicit OOF and support gates, the experiment is **not feasible enough to justify model training in this run**. No feature code, leakage test, model, prediction, bootstrap, or submission file was created. This is a feasibility stop, not a negative W result.

## Data and support audit

Source: participant package `train/generation.parquet` and `sites.csv`; generation has 4,392,566 rows, 253 site IDs, and timestamps from 2021-01-19 13:00 KST through 2025-06-01 00:00 KST. Capacity and coordinates came from supplied `sites.csv`. Solar elevation and azimuth use the existing `features.solar()` function. The review used no external weather, external irradiance, inferred original coordinates, or evaluation-period actuals.

The SM46 manifest gives SHA256 `a2c334a5d2dd0983be78c7ac138e25a013cf70fd9d027515953129ea79964e95` for `generation.parquet` and `93d166fffd009c3643db748fc6d5a1d48851e5f70b314171130e6ab6b7997ea2` for `sites.csv`. Existing runtime environment: Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6. The audit used the current project `.venv` (LightGBM 4.7.0, pandas 3.1.1); no model was fitted.

For each validation cutoff, rows were restricted to the two-year training window and then to timestamps no later than cutoff minus 48 hours. Night observations were excluded from morning/afternoon support. Solar side is the sign of `sin(azimuth)`: positive for the east-facing/morning half of the sun path, negative for the west-facing/afternoon half. This is only a support diagnostic; it does not estimate panel orientation. A missing generation row is never converted to zero.

| Validation model | Available generation window after 48 h embargo | Daylight rows | Plants with daylight history | Capacity represented | Morning / afternoon daylight rows | Plants with >=100 observed days on both sides | Capacity represented by those plants |
|---|---|---:|---:|---:|---:|---:|---:|
| 2023–24 | 2021-06-01 01:00 through 2023-05-30 00:00 KST | 473,895 | 106 / 253 | 8,912.0 / 42,655.4 kW (20.89%) | 234,395 / 239,500 | 93 | 7,709.5 kW (18.07%) |
| 2024–25 | 2022-06-01 01:00 through 2024-05-30 00:00 KST | 957,475 | 205 / 253 | 33,164.4 / 42,655.4 kW (77.75%) | 474,764 / 482,711 | 173 | 26,717.7 kW (62.64%) |

| Validation model | Group | Plants with any daylight history / total | Active capacity / total group capacity | Plants with >=100 observed days on both sides |
|---|---|---:|---:|---:|
| 2023–24 | G1 (source group A) | 100 / 134 | 8,332.5 / 20,465.7 kW (40.71%) | 87 |
| 2023–24 | G2 (source group B) | 6 / 119 | 579.5 / 22,189.7 kW (2.61%) | 6 |
| 2024–25 | G1 (source group A) | 130 / 134 | 19,267.0 / 20,465.7 kW (94.14%) | 126 |
| 2024–25 | G2 (source group B) | 75 / 119 | 13,897.3 / 22,189.7 kW (62.63%) | 47 |

These totals vary seasonally with the reporting-site subset. In the 2023 window, daylight-supported plant counts were 93 in winter, 106 in spring, 58 in summer, and 77 in autumn; 2024 counts were 173, 205, 117, and 136, respectively. Thus a coefficient learned for a plant would still be missing for many target plants and seasonal slices. The aggregate counts do not prove that the supported subset is representative of each group or of the plants scored in every hour.

The 2023 values are especially limiting: the historic records cover only 2.61% of G2 capacity before the validation period. A fallback to zero would be safe computationally, but would leave almost the entire G2 portfolio without the proposed site-specific response signal. Shrinking supported sites toward a fleet mean would not create observed information for those plants.

## Information availability and leakage

The prediction index is right-closed. Existing `features.target_day()` maps `ts=00:00` to the previous target day, and the existing solar function uses the interval midpoint. No official generation reporting-delay document was found in the reviewed local materials. The audit therefore applies the requested conservative 48-hour embargo in the counts above.

No stored A1-REF training-row OOF residuals or matching OOF manifest were found in the checkout or ignored `outputs/`. Existing SM45/SM46 Site Parquets are validation or submission predictions; they are not OOF forecasts for the rows used to fit those models. They cannot be converted into training residuals. No in-sample residual fallback was used.

To satisfy the proposed feature definition, every training row needs an earlier-only residual history. An expanding or rolling-origin process would have to fit and predict the base Site model repeatedly over the historical range, while preserving the two-year training-window semantics, 48-hour embargo, stable forecast-round handling, and prediction timestamps. A later validation fold's actuals cannot update its feature. That generator does not exist in `src/analysis` in this checkout.

The SM46 A1-REF manifest records 339.38 seconds for the complete three-seed Site plus Group submission-candidate pipeline; it does not isolate one Site fit. A rolling OOF run would require dozens of sequential temporal origins (monthly origins across the source span would be on the order of 50), plus feature generation, predictions, and audit outputs. This cost was not benchmarked by launching fits. It is a planning estimate, not a measured runtime. A short 2023 pilot would still need a substantial prefix of this process before the proposed feature could be generated without leakage.

## Feasibility gate

| Gate | Result | Evidence |
|---|---|---|
| Provided historical generation exists | Pass | 4.39M generation rows, 253 plant IDs |
| Morning and afternoon raw support exists | Partial | 106/205 plants in the two training windows; see support table |
| Support covers the primary-year portfolio adequately | Fail | Only 20.89% total capacity has any 2023 daylight history; only 18.07% has >=100 observed days on both sides |
| Strict A1 Site OOF residual artifact exists | Fail | No matching OOF Parquet/manifest found; validation predictions are not OOF |
| Time-ordered OOF generator exists and can be safely reused | Fail | No such generator found; would require repeated Site fits and new lineage code |
| Leakage tests exist for the proposed feature | Fail | Feature path was not implemented; no test result is claimed |

## Verification commands

- `.venv\Scripts\python.exe -m compileall -q src` — passed.
- `.venv\Scripts\python.exe -m pytest -q` — 55 passed, 3 failed. All three failures are existing GFS synthetic-time/partial-export tests (`test_failed_day_remains_missing_without_overwrite`, `test_repaired_failed_day_is_included_only_when_supplied`, `test_build_hourly_synthetic_day`); no SM52 code was changed.
- `git diff --check` — passed.

## Decision

Stop SM#52 before Stage 1 feature implementation and Stage 3 model fitting. The key blocker is not absence of all historical actuals; it is lack of strict OOF residuals plus thin, strongly season- and group-dependent reporting coverage in the primary selection window. Do not use in-sample residuals, evaluation residuals, or full-window observation availability as a substitute.

A future restart should first define a bounded rolling-origin OOF protocol and audit whether it can meet the 2023 support gate. If support does not improve under an allowed earlier historical window, close the hypothesis or change to a feature that does not require plant-level historical residuals. Any new formula and support threshold must be frozen before seeing W.
