# SM#50 Forecast Uncertainty Diagnostic

Date: 2026-11-07 (KST)  
Branch: `seongmin`  
Part A documentation commit: `167558574608c5876b24fd0c3841606cd44ee76c`  
Status: completed diagnostic; no model training or submission file generation.

## Summary

The stored weekday-only SM45 Site3 and Group seed100 forecasts were evaluated without refitting. Forecast-derived daily tertiles were cut using only the immediately preceding two years of supplied WA/WB forecasts, separately for each validation year. All three fixed alternatives were scored on the same observed site-hour mask, reference composition and SMP using `src/scoring.py`; independent hourly penalty sums agreed within 1e-5 KRW.

The fixed Site 80% + Group 20% blend remains the lowest-W whole-period alternative: 106,673,757 KRW in 2023–24 and 197,526,260 KRW in 2024–25. Site-only scored 107,248,930 / 199,015,602 KRW. The Group-only evaluation construction scored 123,344,894 / 216,273,013 KRW and was worse than Site-only in all 36 indicator×year×bin comparisons after normalizing by observed site-hours. The blend beat Site-only in 13/18 2023 bins and 18/18 2024 bins; 2024 is heavily reused validation. This does not support a condition-dependent blend: no new alpha was fit, high/low differences were not consistently stable after month and peak/offpeak stratification, and Site/Group residual correlations remained high.

## Design and data lineage

- Site prediction: SM45 A1 weekday Site3 artifact; 2023/2024 Parquets have 2,222,352 / 2,216,280 site-hour rows. Group prediction: SM45 A1 weekday Group seed100; 17,568 / 17,520 group-hour rows. Reference composition.
- The existing `redistribute()` was applied at alpha 0 (Site-only), 1 (Group-only), and 0.2 (fixed blend). Group-only is allocated to sites using the frozen Site forecast shape solely to score the same observed-site mask. It is not a prediction fitted to observed subsets. Group training CF uses observed generation / observed capacity, while forecast scales by fixed full reference capacity.
- Uncertainty indicators were generated only from supplied training `forecast_wa.parquet` and `forecast_wb.parquet`, round and valid timestamp fields. Round 17 was preferred per station and missing station-hour cloud values fell back to round 10 before regional aggregation, matching the established forecast policy. Forecast dictionary lists both cloud fields in percent, range 0–100; out-of-range values were treated as missing, not clipped. No observed weather or evaluation actual was used in regime construction or cut points. Evaluation generation and SMP were loaded only for W scoring.
- Existing `target_day()` right-closed convention was retained, including `00:00` belonging to the prior target day. Daylight summaries used solar elevation computed from the median supplied site coordinate, only as a daylight mask. No coordinate joins, external meteorology, holiday data or feature/model changes were used. Environment: `OIBC_CAL_MODE=weekday`; external source controls off.
- The analysis code and observed mask verify complete prediction grids. SM45’s `manifest.json` reports weekday-only `dow` and `is_weekend` calendar fields; the saved forecasts were reused, not rebuilt.

## Overall fixed-model W

| 검증기간 | Site-only | Group-only† | Site 80% + Group 20% | 관측 site-hour |
|---|---:|---:|---:|---:|
| 2023–2024 | 107,248,930 | 123,344,894 | 106,673,757 | 1,256,595 |
| 2024–2025 | 199,015,602 | 216,273,013 | 197,526,260 | 2,170,645 |

† Group-only uses alpha=1 plus the frozen Site allocation shape for observed-only settlement scoring. Its result differs from a direct full-capacity Group W and must be read as the same-mask comparison defined above.

## Train-only tertile boundaries

Each cut uses finite daily values from the preceding two-year forecast window; values are cloud percentage points. Training day counts are 727–731 per indicator. Validation bin counts are uneven where indicators are missing and are stored in `outputs/sm50/diagnostics.json`.

| 지표 | 2023 q33 / q67 | 2024 q33 / q67 |
|---|---:|---:|
| WA/WB cloud disagreement (cloud points) | 9.56 / 19.10 | 9.08 / 21.62 |
| Round 17–10 revision (cloud points) | 2.11 / 5.35 | 1.49 / 3.75 |
| Within-day cloud change (cloud points) | 2.03 / 3.77 | 1.93 / 3.62 |
| WA within-day cloud SD (cloud points SD) | 5.57 / 12.84 | 4.60 / 12.60 |
| WB within-day cloud SD (cloud points SD) | 5.82 / 11.78 | 4.75 / 11.82 |
| Mean provider cloud SD (cloud points SD) | 6.52 / 12.46 | 6.00 / 12.13 |

## Regime comparisons

The following deltas are normalized descriptively as KRW W per 1,000 observed site-hours. Negative `blend−Site` favors the fixed blend; positive `Group−Site` means Group-only is worse. They are not alternative official score definitions. The CSV includes W, G1/G2, 11–15 / nonpeak W, signed error, monthly bucket, observed-hour counts and residual correlations for all bins.

| 지표 | 연도 | Low/High days | Group−Site low / high | Blend−Site low / high |
|---|---:|---:|---:|---:|
| WA/WB cloud disagreement | 2023 | 132 / 138 | +10,931 / +13,164 | -941 / -392 |
| WA/WB cloud disagreement | 2024 | 117 / 102 | +10,558 / +9,784 | -173 / -113 |
| Round 17–10 revision | 2023 | 174 / 75 | +8,328 / +23,489 | -1,129 / +1,147 |
| Round 17–10 revision | 2024 | 80 / 186 | +2,703 / +10,184 | -1,598 / -376 |
| Within-day cloud change | 2023 | 133 / 94 | +10,331 / +11,429 | -1,338 / +302 |
| Within-day cloud change | 2024 | 117 / 124 | +5,129 / +9,872 | -1,369 / -93 |
| WA within-day cloud SD | 2023 | 153 / 114 | +12,809 / +11,647 | -562 / -286 |
| WA within-day cloud SD | 2024 | 95 / 116 | +6,223 / +7,718 | -1,052 / -530 |
| WB within-day cloud SD | 2023 | 148 / 122 | +11,373 / +7,853 | -699 / -661 |
| WB within-day cloud SD | 2024 | 117 / 106 | +6,714 / +10,587 | -637 / -291 |
| Mean provider cloud SD | 2023 | 146 / 108 | +12,675 / +9,001 | -726 / -692 |
| Mean provider cloud SD | 2024 | 122 / 109 | +6,380 / +7,828 | -919 / -541 |

### Interpretation

- **H1 (relative performance varies with uncertainty): partial descriptive signal only.** Group-only W exceeded Site-only in every low/middle/high bin in both years. The magnitude varied. For round revision, Group−Site was 8,328 vs 23,489 KRW/1,000 observed site-hours (low/high) in 2023 and 2,703 vs 10,184 in 2024. For within-day cloud change it was 10,331 vs 11,429 and 5,129 vs 9,872. Provider disagreement moved in opposite directions across years. Thus there is no universal “uncertain forecast → trust Group more” pattern.
- **H2 (not only season/time mix): not established.** For round revision, within-month high-minus-low change in the Group−Site W per scored group-hour was positive in 8/12 matched months in each year (median +692 / +1,230 KRW). For within-day change, the corresponding median was −69 KRW in 2023 and +572 in 2024, with six positive months of twelve in each year. Peak-hour Group−Site penalties were larger than offpeak penalties, as expected from the settlement multiplier and daytime production; they do not yield a stable uncertainty-specific advantage after stratification. See monthly and peak/offpeak rows in the local CSVs.
- **H3 (same direction both years): not supported across indicators.** The blend beat Site-only in all 18 bins in 2024 but 13/18 in 2023. That does not warrant learning a dynamic alpha from re-used validation periods.
- Pooled signed Site/Group residual correlations were positive and high, ranging approximately 0.78–0.90 across bins and years, indicating limited independent error cancellation. A blend can still improve through scaling, but the two error series are not independent.
- The 2023 Group model had **zero eligible G2 training labels** at `min_cov=0.3`; 2023 G2 and any pooled Group comparison containing it are extrapolative. In the 2024 training window, the reference Group fit had 12,346 eligible G1 and 2,889 G2 labels. The Group target/inference capacity mismatch remains.

## Decision

**No dynamic ensemble or new candidate is proposed.** Retain the existing SM46 A1-REF as the official submitted model; SM#50 generated no submission CSV and did not alter any existing candidate. The fixed 20% blend’s 2024 regime results are descriptive on repeatedly reused validation data, not independent evidence. A follow-up dynamic-alpha study would need time-ordered OOF training windows and untouched forward evaluation; it should compare against the same fixed blend and control for month, daylight and peak-hour composition.

## Reproduction and artifacts

Command: `.venv/Scripts/python.exe src/analysis/sm50_forecast_uncertainty.py`  
Tests: `.venv/Scripts/python.exe -m pytest tests/test_sm50_uncertainty.py -q` → 2 passed.  
Compilation: `.venv/Scripts/python.exe -m compileall -q src/analysis/sm50_forecast_uncertainty.py tests/test_sm50_uncertainty.py`.

| Artifact | SHA256 |
|---|---|
| Preregistration | `e235230e18bc820708bb423e5f550396e9f369c2222d0d9835e38a4903c75036` |
| Analysis script | `1b4b3984b4644d0495fdf83068728d3986c3904c1fcfedef0bdc1aaab823907e` |
| SM45 manifest | `554ec9223b97ddf6a8831354f9bc1fccfe91aa1e0eadfc0dc2697f7b3706f820` |
| Site pred 2023 | `72e49d8288cb4352804c8b4c585e94a04bc2e90bd4b69c91f36e2d61d7439985` |
| Group pred 2023 | `22dc17b9581073a370a0dc4dd1d5fabcb75e281fd3a9b3fb4a76cf57f6052598` |
| Site pred 2024 | `d2058c8841618d5380e4b05131ae3c361ff2a0f53e4b74f2188eb2db29fc05d1` |
| Group pred 2024 | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` |
| WA forecast source | `a2bda6853d5dcc2dc140e976c1cbc75d0d9a085b41ba17f5ac994704d364a784` |
| WB forecast source | `e8e5de90652c1e949e695b3f8b7f3e1001d3c4a02e3961a42bca1921d2439483` |
| Generation source | `a2c334a5d2dd0983be78c7ac138e25a013cf70fd9d027515953129ea79964e95` |
| Train SMP source | `6ae610fc3e527e603681da3867ecd79d210ed24a17e676ac16149ba7d349645b` |


### Output file checksums

| Aggregate output | SHA256 |
|---|---|
| `outputs/sm50/diagnostics.json` | `ac54789d8bdd9351605866def8151096ae6e333d1ab3aeda21901a9fdf6325be` |
| `outputs/sm50/daily_uncertainty_bins.csv` | `ac0c834fa29fdde8ddb37935404e867d7c1326e734eab14c75080e5e76c5d097` |
| `outputs/sm50/regime_scores.csv` | `23cd965e21f32916f722f0ff617a6ce396eddf3932c3c4de9b9ef0fad1b12ce6` |
| `outputs/sm50/regime_monthly_w.csv` | `d1b81a3b8b0ad6c7d9fc4580aff5a5f6e94319e1fe715995c8375ba343157263` |
| `outputs/sm50/residual_correlations.csv` | `5c4425477ccee16b9dd7cf117d37ba4aef4951a17573465e3856bb166322993d` |

Generated aggregate outputs under ignored `outputs/sm50/`: `diagnostics.json`, `daily_uncertainty_bins.csv`, `regime_scores.csv`, `regime_monthly_w.csv`, and `residual_correlations.csv`. Their SHA256 values are listed in `diagnostics.json`; no source rows, generation observations, or predictions are committed. Runtime was Python 3.11.15, pandas 3.1.1, NumPy 2.4.6. The diagnostic used the same common site-hour observation mask; W and group/time/month splits are not causal effects. The 2024 validation year was repeatedly used in prior research, and the 2023 Group G2 model is unsupported by eligible labels.
