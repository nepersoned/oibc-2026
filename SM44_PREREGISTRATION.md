# SM#44 Preregistration — Group Target Coverage

Registered before calculating the SM#44 coverage tables or candidate validation W: 2026-11-07 16:13 KST. Branch `seongmin`, initial HEAD `346781e930a44ab91e3c4068e23cb61c6ca4a3ee`.

## Question and fixed controls

Question: does selecting/weighting training rows by their training-time reporting-capacity coverage make the Group LightGBM more representative and reduce official settlement W?

All variants use the same fixed SM#41 Site seed 7/21/42 mean, `agg_model.py` Group features and LightGBM PARAMS, random seed 100, 2-year training window, reference composition, alpha 0.2, min daytime rule `elev > -2`, forecast inputs, calendar flag as present in existing noext runs, and the same observed site-hour scoring mask. Evaluation generation is used only to calculate final metrics, never to build targets, fit models, define coverage, or select sample weights.

| Candidate | Training row rule | Target | Training weight |
|---|---|---|---|
| G0 | coverage >= 0.3 | observed generation / reporting-site capacity | none; existing SM#39 seed100 prediction reused and SHA-verified |
| G1 | coverage >= 0.1 | unchanged | coverage² for each retained training row |
| G2 | coverage >= 0.5 | unchanged | none |

Coverage thresholds use capacity fractions of the complete reference group. Sample weights use training-window coverage only. No evaluation- or submission-time observed coverage enters features, weighting, or scaling. Inference continues to multiply predicted CF by the fixed full reference-group capacity.

## Pre-fit feasibility rule

Before running candidate forecasts, G1 and G2 must each retain, in each two-year training window, at least 200 rows for **each group** and at least 100 daylight rows for each group. If either group fails, mark that candidate `Not Run: insufficient pre-registered support`; do not lower the threshold, pool/alter groups, or substitute a target. G0 is retained as the existing comparator regardless of this support threshold.

The candidate with the lower 2023 W among feasible G1/G2 variants is the only candidate carried forward to the 2024 confirmation; ties within 1 KRW go to fewer effective training rows (G2). This is a training-period precondition followed by fixed 2023-first selection; no post-result threshold or weight exponent changes are permitted.

## Evaluation and adoption rules

Compute full 2023-06–2024-05 and 2024-06–2025-05 W under the same reference composition and observed site-hour mask, independently cross-checking hourly penalties against `src/scoring.py`. Report group W, 11:00–15:00 W, complete monthly W, prediction bias, coverage support, Group prediction error correlation, and fixed-full-capacity scaling diagnostics. Run a paired 168-hour moving-block bootstrap with 5,000 replicates and seed 7 for 2024 candidate-minus-SM41 hourly penalties.

Adopt only if the candidate lowers SM41 W in both years, the bootstrap 95% upper endpoint is below zero, no complete month worsens more than 5%, the data lineage is compliant, full submission-period inference is possible, and the official validator exits 0. Otherwise retain SM#41. The 2023 window has known coverage limitations; 2024 has been reused in prior research and is not an independent untouched test.

## Data and rules boundary

Only package WA/WB forecasts, package site metadata, training generation and supplied timestamps/SMP are used. No GFS, GEFS, LDAPS, Open-Meteo, measured evaluation weather, or post-cutoff generation is permitted. Keep `OIBC_CAL` as-is during this group-target experiment; do not interpret that control choice as regulatory clearance. The official general external-data rule and holiday-calendar lineage will be audited separately below in the SM#44 report. A calendar-off fit is out of scope and would be a distinct ablation.

No SM#41 files are to be overwritten. Do not create a submission artifact unless all adoption criteria pass. No portal upload.
