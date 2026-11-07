# SM#48 Preregistration — Composition-Aware Group Refit

Registered 2026-11-07 KST before inspecting any SM48 Group-fit score. Branch `seongmin`; starting revision `56a9c8801d59400e0972f899ecfed6869e89c574`.

## Fixed hypothesis and candidate definitions

The only hypothesis is that refitting the unchanged Group LightGBM for the frozen SM45 optimized composition can improve the fixed Site3 blend relative to a Site-only model assigned to that same composition.

- **B0:** existing SM46 A1-REF (weekday Site3 + reference-composition Group1, alpha 0.2).
- **B1:** existing SM46 A1-COMP (same weekday Site3-only, fixed SM45 composition).
- **B2:** same Site3 predictions, the same fixed SM45 composition and alpha 0.2, but a newly trained Group seed100 model using that composition.
- B2−B1 estimates the Group-combination increment at fixed composition. B2−B0 changes composition and Group training rows/features together and is only a full-pipeline contrast, not a causal composition-only effect.

## Locked model and input controls

Group code/parameters, seed100, min coverage 0.3, two-year time-forward window, weekday calendar, `--ext none`, `OIBC_SRC=prov`, alpha 0.2, and redistribution logic are unchanged. Site forecasts are reused; no Site model retraining. The SM45 composition is read-only and its SHA256 must equal `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872`.

Only competition-provided WA/WB forecasts, site metadata, historical training generation, timestamps and derived solar geometry are used. No outside weather, holiday list, evaluation actuals in fitting, or observed test weather. Do not modify SM41/SM46 submission files or their prediction artifacts.

## Evaluation schedule and interpretation

1. Audit G1/G2 coverage, label counts, Group feature columns and forecast grid feasibility under reference vs fixed SM45 composition before fitting.
2. Fit Group for 2024–25 using only pre-validation two-year history and fixed SM45 composition. B2 is evaluated in the entire 2024–25 year for diagnosis and specifically 2024-12 through 2025-05 against B1 and B0.
3. Only if Group training is feasible and G2 has sufficient labels to fit under the existing code, fit 2023–24 Group as a **retrospective diagnostic**. The composition was chosen using 2024 actuals; 2023 is not an independent past-to-future test.
4. Use the frozen Site3 predictions and `redistribute()` at alpha 0.2. Official scoring and independent hourly penalties must agree within `1e-5` KRW.
5. Report W by year/window, group, peak/off-peak and month; Group bias/coverage; B2−B1 and B2−B0; and paired 168-hour block bootstrap, 5,000 replicates, seed7, on the already-used 2024-12..2025-05 holdout. This bootstrap is descriptive and cannot make the repeatedly viewed holdout independent.

No composition, alpha, features, model parameters, or seed changes are allowed after results. If either composition's training labels are infeasible/seriously inadequate, record and stop that fit rather than weaken existing thresholds.

## Submission and protection rule

SM46 A1-REF remains the default candidate regardless of SM48 point estimates. Only if B2 improves against B1 on the holdout, improves vs B0 on both full-year W diagnostics, shows gains across months, and has bootstrap 95% upper bound <0 with no new compliance issue may a separate SM48 submission-period Group fit be considered. Even then this repeated-period study is not independent evidence; no auto-promotion and no portal upload. Do not overwrite any existing candidate.
