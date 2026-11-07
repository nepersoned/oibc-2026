# SM#52 Preregistration — Historical Solar-Shape Response

Date: 2026-11-08 (KST)
Starting revision: `e00d9f6dc540e97a1ae08000532639d77bfdca17`
Status: preregistration completed for auditability; **feasibility gate failed, so no W experiment was run**.

## Single hypothesis

A plant-specific, historical morning–afternoon residual response proxy may explain variation not captured by shared solar geometry and the supplied WA/WB forecast features, and may lower reference-composition group settlement W.

The coefficient is a statistical response proxy. It is not an estimate or measurement of module azimuth, tilt, or actual plant orientation.

## Candidate feature definition (frozen before any W evaluation)

1. For every prior, valid daylight observation, normalize generation and baseline forecast by supplied plant capacity. Define normalized residual `r = (energy - baseline_site_prediction) / capacity_kw`.
2. Use the existing supplied-coordinate solar calculation. For right-closed `ts`, retain the existing interval midpoint and target-day convention. Define the fixed direction basis `b = sin(radians(azim))`; morning/east is positive and afternoon/west is negative. Only `elev > 0` observations with finite generation, prediction, and positive capacity contribute.
3. Baseline predictions for residuals must be strict rolling-origin OOF predictions from the existing A1 weekday Site model, seed 7, rich features, `site_code` removed, two-year rolling training window, weight none, ext none. Each prediction must be produced by a fit whose training labels precede the target row's feature cutoff (`target_ts - 48 hours`). Apply a 48-hour generation embargo because no official reporting-delay rule was found.
4. At a feature cutoff, a plant is eligible only if it has at least 100 distinct observed target days on **each** side using the prior OOF residual history. Estimate one signed ridge coefficient per eligible plant: `beta_i = sum(b*r) / (sum(b^2) + lambda)`, with fixed `lambda = 200` daylight residual rows. Use only residuals available before the cutoff. No evaluation-window generation may update the coefficient. The 100-day threshold is a conservative support gate proposed before any W result; it is not tuned in this run.
5. Generate `sm52_shape_coef = beta_i`, `sm52_shape_interaction = beta_i * b(target_ts)`, and `sm52_shape_support = log1p(min(n_AM_days, n_PM_days))`; for target rows with no eligible plant history, set coefficient and interaction to zero while support retains the observed history count (zero when none). Keep the fallback identical in training and inference. The fallback is a missing-signal encoding, not a claim of zero physical asymmetry.

This is the single preregistered feature family. No alternate basis, shrinkage strength, minimum-support cutoff, or fleet-mean fallback may be selected after looking at W. The fixed ridge penalty and 100-day support gate are proposals for a future run, not parameters fitted or validated in SM#52.

## Stage order and stop rules

1. Audit raw plant/season/side support and locate authentic strict OOF residual artifacts.
2. If no valid OOF artifact exists, estimate the rolling-origin workload and support before implementing a feature.
3. Stop before implementation and model training if rolling OOF generation is not practical within the available compute budget or the primary 2023 support is too sparse to represent the scored portfolio.
4. Only after the feasibility gate passes, implement leakage tests. Tests must show that changing future generation, changing validation outcomes, removing submission-period actuals, adding a new unseen plant, and the right-closed midnight boundary cannot leak into a feature. Enforce the 17:00 forecast cutoff and 48-hour generation embargo.
5. Only after all tests pass, run the seed7 controlled 2023 comparison. Candidate and baseline must have identical rows, inputs, model parameters, group prediction, alpha 0.2, and reference composition. Proceed to 2024 only if 2023 W improves.
6. Consider 168-hour paired bootstrap and seeds 21/42 only if both years improve and the pre-registered stability checks remain feasible.

No post-result formula or threshold changes are allowed. Existing validation periods have been reused; even a passing result would not be an untouched independent test.

## Evaluation and adoption criteria (if a future run passes feasibility)

Use the same observed site-hour mask, SMP, peak factor, reference composition, and official `src/scoring.py` as A1-REF. Independently sum hourly penalties and require agreement. Report total, G1/G2, peak 11–15, nonpeak, monthly, AM/PM W, Site/Group MAE, signed bias, support-stratified W, and 168-hour paired bootstrap.

Do not adopt unless 2023 and 2024 W both improve, the 2024 paired-bootstrap 95% CI upper endpoint is below zero, no complete month worsens by more than 5%, all as-of-time and OOF lineage tests pass, and all inference plants have an explicit safe fallback. These criteria do not convert reused validation periods into independent evidence.

## Actual execution status

Stage 0 failed the support and OOF availability gates. No feature code, leakage test, OOF forecast, model fit, W calculation, bootstrap, or submission forecast was produced. See [SM52 feasibility audit](SM52_FEASIBILITY_AUDIT.md). This preregistration records a future test design; it is not evidence that the feature was implemented or evaluated.
