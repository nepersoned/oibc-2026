# SM#53 Historical Generation Profile — Pilot Report

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `bd9b69c961920820aff44550743380b8987f2219`
Decision: **reject the single-seed candidate; retain SM46 A1-REF**.

## 1. Hypothesis and scope

SM53 tested whether a plant-specific morning/afternoon output asymmetry computed from past generation and solar geometry could add information to the existing A1 Site features. It did not use model predictions, residuals, or OOF forecasts. This is distinct from SM52, which stopped because strict OOF residuals were unavailable. The profile is a statistical output proxy, not measured panel azimuth or tilt; local cloud, shading, curtailment, and reporting patterns may influence it.

The three preregistered Site features were generated from same-date morning/afternoon output ratios in shared 5° solar-elevation bands, with Haurwitz clear-sky geometry normalization, a 730-day lookback, a 30 paired-day eligibility gate, and zero-centered shrinkage `n/(n+30)`. For each target day, only complete historical paired days through target day minus four days were included. This is conservative to the official prior-day 17:00 cutoff plus 48-hour embargo. Validation features were frozen from pre-validation history and never updated from validation actuals.

## 2. Coverage result

All support comes from the supplied generation file and `sites.csv`. The 2025-06-01 submission-training cutoff has eligible profiles for all 253 plants and all portfolio capacity. At the 2024 validation cutoff, 179 plants (70.8%) and 63.74% of capacity meet the registered support gate; G2 has 52/119 eligible plants and 41.82% of G2 capacity. At the 2023 cutoff, only 106 plants (41.9%) and 20.89% of total capacity qualify; G2 support is only 2.61% of its capacity. The earlier window is therefore a severe coverage stress case, not a representative test of a full-portfolio profile.

Detailed per-site, group, and seasonal counts are in [SM53_COVERAGE_AUDIT.md](SM53_COVERAGE_AUDIT.md) and `outputs/sm53/coverage_audit.json`.

## 3. Leakage controls and tests

The training profile for each row uses only earlier paired days. The 2024 validation profile is fixed from the pre-validation generation window. `OIBC_SM53_PROFILE` defaults to `0`; the pipeline rejects the enabled path unless `--ext none` and `OIBC_CAL_MODE=weekday` are active. The Group model was not changed or retrained.

The four focused tests passed. They verify future-generation mutation invariance, frozen validation features under evaluation-actual changes, unseen-site fallback/schema, and the right-closed midnight convention. These synthetic tests support the implemented time-slicing behavior; they do not certify that an undocumented real-world reporting delay is exactly 48 hours. The complete 2024 score used only the existing observed-site-hour mask for settlement.

## 4. 2024 seed7 controlled pilot

The baseline is the saved A1 weekday Site seed7 prediction; the candidate retrained the same Site model with only the three SM53 columns added. Both use two training years, rich features, `site_code` dropped, no weighting, seed 7, ext none, reference composition, the same frozen weekday Group seed100 prediction, and alpha 0.2. The observed mask contains 2,170,645 site-hours and 17,520 group-hours. Official `scoring.py` and the independent hourly penalty sum agree exactly at the stored precision.

All W values are KRW. `Δ` is candidate minus baseline, so positive means worse.

| Metric | A1 seed7 + Group100 | SM53 seed7 + same Group100 | Δ |
|---|---:|---:|---:|
| Site-only reference W | 201,309,669 | 202,375,569 | +1,065,901 |
| Blended settlement W | 198,977,096 | 199,849,640 | **+872,544 (+0.439%)** |
| G1 W | 94,506,528 | 94,115,737 | −390,791 |
| G2 W | 104,470,568 | 105,733,903 | **+1,263,335** |
| Peak 11–15 W | 164,213,673 | 165,172,138 | **+958,465** |
| Nonpeak W | 34,763,423 | 34,677,502 | −85,921 |
| Morning solar-side W | 95,752,449 | 96,050,085 | +297,636 |
| Afternoon solar-side W | 103,224,647 | 103,799,555 | +574,908 |
| Site MAE (kWh) | 5.9544 | 5.9067 | −0.0477 |
| Observed-only group MAE (kWh) | 385.1571 | 385.7655 | +0.6084 |
| Site signed bias (kWh) | −0.0713 | −0.2823 | more underprediction |
| Observed-only group signed bias (kWh) | −8.830 | −34.981 | more underprediction |

Site MAE improved slightly, but the official Group settlement W worsened. G1 improved while G2 and peak loss worsened. The G2/low-support association is descriptive: both reflect the same fixed group composition and do not establish that support caused the W change. The support-bucket comparison uses an 80% observed-capacity support threshold; at this cutoff it separates G1 from G2 almost exactly, so it is not an independent causal diagnostic.

The candidate’s gain-importance log ranked `sm53_am_pm_interaction` 12th among the top 15 features; the profile and support columns were outside the logged top 15. This importance result does not outweigh the worse settlement W.

## 5. Monthly W

Six months improved and six worsened among the complete months. The largest monthly deterioration was December 2024, +387,357 KRW (+3.06%); January 2025 improved by 909,698 KRW (−7.43%). The net whole-period result still worsened.

| Month | Baseline W | SM53 W | Δ |
|---|---:|---:|---:|
| 2024-06 | 14,391,453 | 14,140,163 | −251,289 |
| 2024-07 | 24,310,913 | 24,831,961 | +521,047 |
| 2024-08 | 16,196,804 | 16,407,295 | +210,490 |
| 2024-09 | 24,123,551 | 24,758,157 | +634,605 |
| 2024-10 | 18,818,813 | 19,138,779 | +319,966 |
| 2024-11 | 12,300,076 | 12,218,357 | −81,719 |
| 2024-12 | 12,669,708 | 13,057,065 | +387,357 |
| 2025-01 | 12,251,261 | 11,341,563 | −909,698 |
| 2025-02 | 16,443,617 | 16,223,661 | −219,957 |
| 2025-03 | 12,695,363 | 12,659,472 | −35,891 |
| 2025-04 | 15,195,169 | 15,519,711 | +324,541 |
| 2025-05 | 19,580,365 | 19,553,456 | −26,909 |

The final `2025-06` bucket contains only the right-closed `2025-06-01 00:00` hour and is effectively zero; it is shown in the machine-readable CSV but excluded from the complete-month count.

## 6. Stopping decision

The preregistered primary-period blended W worsened, so the experiment stopped. No bootstrap was run, no 2023 candidate was trained, no seed21/42 model was trained, and no submission forecast or CSV was generated. Do not tune the elevation bins, lookback, support threshold, shrinkage, or add further profile variants based on this result. Keep the hypothesis as an unsuccessful single-seed pilot; SM46 A1-REF and all existing submissions remain unchanged.

## 7. Reproducibility

Candidate training command (PowerShell environment controls were set before process launch):

```powershell
.\.venv\Scripts\python.exe src\pipeline.py --mode val --fset rich --train-years 2 --weight none --ext none --params '{"random_state":7}' --drop-features site_code --tag sm53_profile_s7 --val-start 2024-06-01 --val-end 2025-06-01
```

Scoring and coverage commands:

```powershell
.\.venv\Scripts\python.exe src\analysis\sm53_pilot.py --mode coverage
.\.venv\Scripts\python.exe src\analysis\sm53_pilot.py --mode score --candidate outputs/val_sm53_profile_s7_sites.parquet --outdir outputs/sm53
```

The runtime was 97.7 seconds end-to-end, including feature construction, fit, prediction, and pipeline’s site-only scoring; model fit completed at 63.9 seconds. The process reported 95 Site features after adding the three SM53 columns.

Input and output hashes, code hashes, versions, configuration, score details, and monthly W are recorded in `outputs/sm53/pilot_2024.json` and `outputs/sm53/coverage_audit.json`. Key predictions: baseline Site seed7 `dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26`; candidate Site seed7 `1ba0066f6457f8eb242673124ca882ef98c3a09c167b04815dc8f853a08eacf4`; frozen Group100 `651b2f296316139af6ccf6aecabdd3071b1710de6fff35df18ecd20bb63b58b7`.

Focused SM53 tests: **4 passed**. `compileall` and `git diff --check` passed. The full repository suite had 59 passed and 3 pre-existing GFS time/partial-export failures (`test_failed_day_remains_missing_without_overwrite`, `test_repaired_failed_day_is_included_only_when_supplied`, `test_build_hourly_synthetic_day`); SM53 did not modify GFS code.

## Erratum — Group prediction SHA256

The Group100 SHA256 printed above has a transcription typo. The correct digest is `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7`, as recorded in `outputs/sm53/pilot_2024.json` and corroborated by SM50, SM51, and direct hashing of the existing Parquet. This is a documentation correction only; no artifact or JSON manifest was changed. See [SM55 provenance audit](SM55_ARTIFACT_PROVENANCE_AUDIT.md).
