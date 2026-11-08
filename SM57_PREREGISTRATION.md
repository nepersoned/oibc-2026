# SM#57 Preregistration — Conditional, Not Executed

Date: 2026-11-08 (KST)  
Status: **Gate failed before model training.** This document records the controlled comparison that would be used only after the source and rule gates in [the source audit](SM57_GFS_CLOUD_SOURCE_AUDIT.md) are resolved. It does not register an authorized model run today.

## Hypothesis

Adding GFS low-, middle-, and high-cloud cover to an otherwise identical model that already uses verified GFS DSWRF/TCDC and competition-provided WA/WB may reduce the official group settlement penalty.

## Gate conditions

Before any training, all conditions must be supported with artifacts:

1. Date/run-level evidence that every included D−1 00 UTC cycle was public by D−1 17:00 KST.
2. Same-source re-download and complete availability for all required 2021–2025 training and 2025–26 evaluation dates and forecast leads 16–39.
3. Explicit rule eligibility for the data source and a fixed grid applied uniformly to every plant.
4. Frozen source files/indexes with SHA256, and a validated layer temporal aggregation that matches the target timestamp convention.

Any missing gate means no feature generation or training.

## Conditional controlled pilot

If all gates pass, preregister before building features:

- Baseline A: provided WA/WB + existing SM features + the exact same validated GFS DSWRF/TCDC features used in candidate B.
- Candidate B: A + fixed-grid LCDC, MCDC, HCDC.
- Same training rows, historical window, site model, one fixed seed, composition, prediction mask, Group prediction/blend (if used), and official W scorer.
- First period: 2024–25; one seed only.
- Primary metric: group settlement W on identical observed site-hour masks; also report group coverage limitation, G1/G2, 11–15, monthly W, cancellation, signed bias, and MAE as secondary diagnostics.
- Stop if W worsens; do not expand seeds for a small or uncertain improvement. If point improvement occurs, use paired 168-hour moving-block bootstrap and report its uncertainty.
- No use of future generation, measured future weather, or realized future SMP as model input. No submission generation or portal upload.

No evaluation thresholds or hyperparameters have been tuned against the results because no pilot was run.

## Execution record

| Item | Result |
|---|---|
| Feature implementation | Not run |
| Training | Not run — source release-time and eligibility gates unresolved |
| 2024–25 W / bootstrap | Not run |
| Submission candidate | None |
