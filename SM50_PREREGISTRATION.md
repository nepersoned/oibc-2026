# SM#50 Preregistration — Forecast Uncertainty and Site/Group Skill

Date: 2026-11-07 (KST)  
Branch: `seongmin`  
Status: preregistered before condition-specific score analysis

## Question and scope

Test whether the relative settlement performance of the already-fitted weekday-only Site and Group forecasts changes with forecast-derived uncertainty. This is a **diagnostic association study**. It will not train models, create a dynamic blend, change alpha, create a submission, or select a new threshold after viewing validation scores.

The user-provided 2026 briefing notes (pages 25–28) motivate forecast-error, issue-round, group cancellation and composition interactions. The slides themselves are not present in this checkout; no 2023 slide deck is substituted.

## Frozen models and outputs

- Site: SM45 A1 weekday-only Site predictions, seeds 7/21/42 mean.
- Group: SM45 A1 weekday-only Group prediction, seed 100, reference composition, `min_cov=0.3`.
- Composition: reference; no composition search.
- Candidates for the diagnostic: Site-only (`alpha=0`), Group-only allocation (`alpha=1`), and fixed blend (`alpha=0.2`). The blend ratio is fixed and is not estimated per regime.
- Preferred validation Parquets: `outputs/sm45/2023_A1_B0_site_only_sites.parquet`, `outputs/sm45/2024_A1_B0_site_only_sites.parquet`, `outputs/sm45/group_a1_2023.parquet`, `outputs/sm45/group_a1_2024.parquet`. Predictions are reused without refitting. Hashes will be recorded in the results report.
- Before scoring, the analysis must verify the SM45 manifest metadata, file existence, full site/group-time coverage, reference composition and noholiday feature lineage. If any required forecast cannot be reproduced from saved artifacts, stop without training.

## Validation periods and common scoring mask

- 2023–24: local right-closed window `(2023-06-01 00:00, 2024-06-01 00:00]` KST.
- 2024–25: local right-closed window `(2024-06-01 00:00, 2025-06-01 00:00]` KST.
- Use one common observed site-hour mask, provided SMP, official `src/scoring.py` settlement formula, and the established redistribution function for all three candidates within each period.
- Cross-check each W against independent hourly penalties. Do not use validation actual generation, site residuals, or evaluation mask to create uncertainty indicators or their bin boundaries.
- Group-only predictions are allocated to sites with the frozen Site forecast shape through the existing redistribution routine (`alpha=1`), solely to evaluate the same observed-site mask. This is an operational comparison, not a claim that the Group model was trained on that observed subset: Group CF training uses reporting capacity in its denominator while inference scales by fixed reference group capacity. Report this mismatch explicitly.

## Forecast uncertainty indicators

Use only provided `forecast_wa` and `forecast_wb`, their provider station IDs, `round`, valid timestamp, and forecast values. Construct one row per target day from the provider forecasts available by the prior-day 17:00 cutoff. For each provider, prefer round 17 and fill missing fields from round 10 exactly as the documented forecast policy; keep missingness visible and do not replace missing revisions by zero.

For each target day compute four pre-specified scalar indicators:

1. **Provider cloud disagreement:** daily daylight-weighted mean of the absolute WA–WB difference in regional mean cloud percentage at the same valid hours. WA and WB `forecast_wa`/`forecast_wb` cloud units are both percent (0–100) in the supplied participant data dictionary. This check is for the forecast tables, not the distinct observed-WB table whose documented range contains anomalous values above 100.
2. **Round revision magnitude:** daily daylight-weighted average of the absolute round17-minus-round10 change in provider regional mean cloud percentage; average across providers with observed paired rounds. Preserve the paired-round availability count.
3. **Within-day cloud change:** mean absolute adjacent-valid-hour change in the regional cloud ensemble mean, using valid timestamps within that target day only.
4. **Provider temporal dispersion:** for each provider, the within-target-day standard deviation of its daylight regional mean cloud forecast over valid hours; use the mean of WA and WB SD only when both are available, otherwise retain provider-specific fields and missingness.

Daylight for these regime summaries is determined from the supplied timestamp and the existing solar-geometry features, without using generation or evaluation residuals. The exact column map, units, station aggregation, missingness and hash are to be recorded in the result report. Cloud values outside the forecast-table documented range [0,100] are treated as missing (not clipped); counts are reported before indicators are formed.

## Locked bins

For each validation year separately, derive tertile cut points at the 1/3 and 2/3 quantiles from daily indicator values in that year's **two-year pre-validation training forecast window only**:

- 2023 validation: training forecasts through `2023-06-01 00:00 KST`, with the preceding two years used.
- 2024 validation: training forecasts through `2024-06-01 00:00 KST`, with the preceding two years used.

Apply those frozen thresholds to validation target days. Label bins low / middle / high. If a training indicator has insufficient finite daily values or tied quantiles collapse a cut point, report the affected bin as unavailable; do not switch to validation-quantile boundaries. Bin membership is defined at target-day level, then applied to all eligible scored hours on that day.

## Locked outputs and analysis

For each indicator, period and available bin, report:

- number of days, scored site-hours and group-hours;
- total official W for Site-only, Group-only and fixed alpha 0.2 blend, plus G1/G2 and `ts` hour 11–15 / nonpeak breakdowns;
- W per scored day as a descriptive normalization, not a replacement score;
- month distribution and the number of months contributing to each bin;
- signed aggregate error/bias and Group W;
- correlation of paired Site and Group signed group-hour residuals on the shared observed mask;
- which fixed model has the lowest W in each bin.

For H2, additionally report within-month and peak/nonpeak contrasts so that a regime difference is not attributed to uncertainty if it is explained only by season or settlement hour composition. These are descriptive stratifications; do not fit a dynamic policy or optimize within strata.

Report 2023 and 2024 independently. The 2023 Group G2 model had zero eligible training labels at `min_cov=0.3`; identify its G2 comparisons as extrapolative. 2024 and the fixed alpha were repeatedly inspected in prior work, so these results are reused historical diagnostics, not independent confirmation.

## Hypotheses and decision rules

- H1: Site/Group relative W differs between low- and high-uncertainty days.
- H2: any difference remains visible within comparable month and peak/offpeak strata rather than arising only from seasonal/hour composition.
- H3: direction of the condition-specific contrast is consistent across both validation years.

A hypothesis is described as supported only if the pre-specified high-minus-low contrast has the same direction in both periods and is visible in within-month/peak-stratified summaries. No causal interpretation is allowed: forecast disagreement is a proxy, and the same historical periods have been reused. If bins are sparse, feature data incomplete, or directions unstable, report inconclusive and stop. Even if a stable pattern appears, this SM#50 remains diagnostic; any dynamic alpha requires a separate train-only/OOF preregistered experiment.

## Prohibited actions

- No model fitting, model/feature changes, alpha tuning, composition search, threshold changes after results, submission CSV creation, or portal upload.
- No evaluation actuals/residuals in feature construction or cutpoint estimation.
- No external weather, holiday calendars, or site-coordinate reconstruction.
- No raw competition rows or predictions sent to external services.

## Reproducibility artifacts

- Preregistration: `SM50_PREREGISTRATION.md` (this file).
- Script/report/data summaries: `src/analysis/sm50_forecast_uncertainty.py`, `outputs/sm50/`, and `SM50_FORECAST_UNCERTAINTY_DIAGNOSTIC.md`.
- Record source and prediction SHA256 values, command, runtime/package versions, cut points, data coverage, metric counts, scorer cross-checks, and final interpretation. Keep raw Parquets and CSV outputs ignored by Git.
