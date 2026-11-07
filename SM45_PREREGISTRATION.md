# SM#45 Preregistration

Registered 2026-11-07 16:57 KST before fitting any calendar-safe model or viewing its validation W. Starting repository revision: `62c1da1425296d11baf43c715ef4a659e6f6dba0`, branch `seongmin`.

## Calendar treatment

- `legacy`: exact previous `dow`, `is_hol`, `is_off`, `off_run` features, for comparison only.
- `weekday`: `dow` and `is_weekend` computed from existing right-closed timestamps using `features.target_day()`. No `holidays` import or `EXTRA_OFF` access.
- `none`: no calendar columns and no holiday source access.
- `OIBC_CAL_MODE` takes precedence when set. When unset, legacy `OIBC_CAL=1/0` behavior is retained for backward compatibility.
- Both Site and Group paths must use the same process environment and feature mode. Training and prediction must have identical feature names and order.

## Fixed model settings and input controls

Reference composition; no outside weather (`--ext none`); participant WA/WB forecasts only; no WX2/SM42/GFS/GEFS/UM/spatial/physics inputs; `OIBC_SRC=prov`; 2-year training window; Site LightGBM existing `M.PARAMS`, seeds 7/21/42, rich feature set, `site_code` excluded; Group LightGBM existing `agg_model.PARAMS`, seed 100, `min_cov=0.3`; Site 80% + Group 20% for A comparisons. No model structure, loss, feature family, alpha, group assignment, or hyperparameter tuning changes.

## Phases A–C

- A0: reuse verified SM#41 legacy predictions and recorded W; do not retrain legacy.
- A1: weekday-only, retrain all Site seeds and Group separately in each validation window.
- A2: calendar-none, same retraining plan, only after A1 predictions and metrics have been checkpointed.
- B0: A1 Site-only (`alpha=0`). B1: same A1 Site predictions with its Group model and `alpha=0.2`; no retraining.
- W is computed on identical reference composition, observed site-hour masks, SMP and peak weights. Independent hourly W must match `scoring.score` to `1e-5` KRW. Report per-group, 11–15, complete-month W, site/group MAE and signed bias.
- For A1/A2/B1, 2024 paired moving-block bootstrap: 168-hour blocks, 5,000 replicates, seed 7, candidate minus A0 hourly penalties. B0 vs B1 also report the same bootstrap.
- A calendar-safe model is eligible for recommendation only if it has lower W than A0 in both years, 2024 bootstrap 95% upper endpoint < 0, no complete month worsens over 5%, complete inference/validator succeeds, and data lineage is rule-compatible. If no safe model meets these criteria, report no submission-cleared candidate; A0 remains a performance reference only if its holiday-derived features are rule-incompatible.

## Phase D (only after A–C, if time remains)

Start from reference composition; optimize with A1 Site-only predictions. A mover site must have >=80% observed daylight site-hour coverage in the selection window, where daylight is computed from the supplied site coordinates and existing solar function with `elev > 0`, and the denominator is all expected daylight site-hours for that site in that window. Freeze this movable mask before optimizing. At most 10 sites may differ from reference; single moves and swaps are allowed. Keep each group at least 20,100 kW (20 MW + 100 kW slack); both reference groups already meet this. Fit/selection interval is the right-closed `(2024-06-01 00:00, 2024-12-01 00:00]` window (2024-06-01 01:00 through 2024-12-01 00:00 KST); fixed holdout is `(2024-12-01 00:00, 2025-06-01 00:00]` (2024-12-01 01:00 through 2025-06-01 00:00 KST). Select only on the former; report the latter once. At most one deterministic locked local-search result; no full-window residual use, retries against holdout, or post-result candidate revisions. Require lower holdout W, no single-month concentration of gains, valid capacity, and 7-day paired bootstrap upper endpoint < 0. The observed-only residual matrix's zeros represent omitted site-hours in the objective, not known zero errors.

No D optimizer run is planned until A1/A2 and B results are complete. A2 and D are dropped when they would push new model/optimization starts past 21:15 KST.

## Briefing-source provenance

The only local OIBC slide file found is `work/oibc2023/assets/OIBC_presentation.pdf`. It is titled “5th Solar Power Generation Prediction Competition” (2023), has 13 PDF pages, and does not contain the requested 2026 slide numbers 17, 21, 23, 25–27. It will not be represented as the 2026 online briefing. The user's summarized 2026 slide points are retained as hypotheses to check against package/official sources; exact slide wording remains unverified because the specified deck is absent from this checkout.
