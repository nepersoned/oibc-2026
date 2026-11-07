# SM#53 Preregistration — Historical Generation Profile

Date: 2026-11-08 (KST)
Starting revision: `bd9b69c961920820aff44550743380b8987f2219`
Status: **registered before opening SM53 validation W results**.

## Hypothesis and distinction from SM52

H1: A plant-specific historical morning–afternoon output asymmetry, derived directly from past generation and solar geometry, adds predictive information beyond the existing A1 weekday Site features and reduces settlement W.

SM52 required strict OOF residuals and stopped because those artifacts did not exist and 2023 support was low. SM53 does not use a model prediction, residual, or OOF artifact. It uses only prior generation, supplied capacity, timestamps, and the existing solar calculation. It does not estimate actual panel orientation or recover a plant location. The profile may also reflect local cloud, shadow, curtailment, or reporting patterns.

## Frozen profile definition

For each historical generation row:

1. Clamp negative `energy` to zero, matching the existing Site training path. Normalize to one-hour clear-sky proxy output: `u = energy / (capacity_kw * ghi_cs / 1000)`, where `ghi_cs = 1098 * cosz * exp(-0.057 / cosz)` for positive `cosz`, from the existing solar geometry. This is a dimensionless clear-sky-normalized output proxy, not measured irradiance or module efficiency.
2. Keep only `elev >= 15°`, `ghi_cs >= 250 W/m²`, finite `u`, and positive-capacity observations. Use the supplied solar azimuth: `sin(azim) >= 0` is the morning/eastern side and `< 0` the afternoon/western side.
3. Derive the right-closed target date using existing `target_day()`. Bin elevation into fixed 5° bands. Within `site_id × target_day × elevation_band × side`, take the median `u`. Pair only bands with both morning and afternoon medians. For each site-day, take the median of paired-band differences `u_AM - u_PM`. A site-day without a shared band contributes no profile observation.
4. For a row with target day `D`, profile history uses complete paired days from the previous 730 calendar days, ending no later than `D - 4 days`. This complete-day cutoff is conservative relative to the day-before 17:00 issue time plus the 48-hour generation embargo. It also means the `00:00` right-closed timestamp follows the existing previous-target-day rule.
5. Let `n` be the number of paired historical site-days in that window and `m` their median daily asymmetry. The profile is zero when `n < 30`; otherwise use fixed zero-centered shrinkage `profile = n/(n+30) * m`. `lambda_days=30` is the fixed prior strength. Support is `log1p(n)` whether or not the 30-day gate is met.
6. Generate exactly three Site features: `sm53_am_pm_profile = profile`, `sm53_am_pm_interaction = profile * sin(azim_target)`, and `sm53_profile_support = log1p(n)`. A new plant or sparse history receives profile and interaction zero with explicit support zero/low. This fallback denotes no reliable measured profile, not physical symmetry.

No formula, elevation threshold, bin width, rolling window, support threshold, shrinkage strength, or interaction is changed after seeing W.

## As-of-time construction and evaluation design

- For Site training rows, compute the profile separately by site and right-closed target day using only generation from earlier paired days through `D-4`; never use the row's own target, same-day observation, future generation, or current/future observation existence.
- For validation rows, freeze the profile from the model's pre-validation training history. Do not refresh it with any validation-period generation, even when later validation timestamps are being scored.
- The existing WA/WB forecast features retain their established round 17 preference, round 10 fallback, and target-day grouping. New Site feature flag defaults off; the Group model, Group seed100 forecast, alpha 0.2, reference composition, calendar `weekday`, and `ext none` remain fixed.
- 2024–25 is the single primary pilot because its pre-evaluation paired-profile support is much broader than in 2023. This is a repeatedly used exploratory period, not an independent test. 2023 is a coverage stress-test only, not a retroactive adoption gate.
- Candidate is A1 weekday Site seed7 plus the three SM53 columns. Baseline is the same A1 Site seed7 artifact with the same frozen Group seed100 predictions and 80/20 blend. Rows, timestamps, reference composition, observed mask, SMP, and LightGBM parameters are held fixed.
- If 2024 W worsens, stop. If it improves, perform the preregistered diagnostics and 5,000-draw paired 168-hour bootstrap; do not automatically train seeds21/42. No submission candidate is generated in this experiment.

## Leakage test requirements

Before training, tests must establish: (a) changing generation later than a training row's cutoff does not change its profile; (b) adding/removing validation actuals does not change frozen validation features; (c) submission feature construction works with no submission actuals; (d) unseen sites get safe fallback; (e) `00:00` maps to the previous target day; (f) profile history obeys `D-4`, which is at least the official day-before-17:00 cutoff plus 48 hours; (g) current/future generation existence is not used as an input; and (h) training/inference expose the same three columns in the same order.

## Reported outcomes and decision

Score with `src/scoring.py` on the identical observed site-hour mask and cross-check with an independent hourly sum. Report total, G1/G2, morning/afternoon, 11–15, nonpeak, monthly W, Site MAE, observed-only Group W and bias, support-coverage-stratified W, and paired bootstrap. W is the only adoption score; Site MAE is descriptive.

SM53 has no adoption rule that treats the 2023 coverage-stress window as independent confirmation. A positive 2024 result is exploratory and requires later untouched forward evidence before changing the official candidate. No official submission or file replacement is authorized.
