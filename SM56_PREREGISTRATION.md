# SM#56 Preregistration — ens_v12 Prediction-Level Complementarity

Date: 2026-11-08 (KST)  
Branch: `seongmin`  
Starting revision: `87b9748271ba89d6d49333884ce5342deb79b8ef`  
Read-only reference: `origin/main` at `793f5f6662f074dbc8e50d3b0f925b9b214c3683`

## Objective and limits

Test whether the already-published SM46 A1-REF validation predictions add information to JH `ens_v12` validation predictions. This is a prediction-level diagnostic only. No model training, external data retrieval, feature engineering, submission-file creation, portal submission, or modification of existing forecasts is allowed.

## Frozen comparison

- JH input: `predictions/val_2023-24/forecast_ens_v12_val.csv` and `predictions/val_2024-25/forecast_ens_v12_val.csv` from the read-only `origin/main` commit above.
- JH score column: `forecast_kwh`, pending confirmation from the public README and implementation metadata. Public documentation describes it as the group prediction made from 0.505 Site and 0.495 Group model outputs; `site_model_kwh` and `group_model_kwh` are component diagnostics, not separately selected forecasts.
- SM input: existing SM45 A1 weekday/reference validation forecasts that reproduce SM46 A1-REF (3-seed Site + Group seed100, 0.8/0.2, reference composition). Use historical validation artifacts only; SM46 2025–26 submission CSVs are not validation predictions.
- Periods: right-closed windows `(2023-06-01 00:00, 2024-06-01 00:00]` and `(2024-06-01 00:00, 2025-06-01 00:00]`, with first timestamps 01:00 KST.
- Fixed mixture: `P_mix=(1-alpha)*P_JH + alpha*P_SM`, with alpha exactly `0, 0.05, 0.10, 0.20`. Alpha 0 is the reference. No data-driven selection of alpha for submission is permitted.
- Composition must be identical reference G1/G2 for both forecast artifacts. Keys must be unique and complete over each period's G1/G2 × timestamps.
- For a prediction-level comparison on a common group-unit target, sum all 253 SM site forecasts into full reference-group forecasts (do not use the observed-only SM redistributions), and compare JH and SM full-group forecasts against the same generation-observed group sums with the same SMP and official `k=3` for right-closed timestamps 11:00–15:00 (otherwise 1), and 0.1 penalty rate. This preserves a common prediction unit and actual mask but remains a local partial-observation diagnostic, not a complete-group official W where generation is missing.
- Separately report the established SM official-local site-mask score from `src/scoring.py`; do not compare that value directly with the full-group JH-style score.

## Alignment gate

Before comparing scores, inspect actual column semantics, timestamp timezone/right-closed convention, group composition, time-grid completeness, prediction units, and the relation between group predictions and observed generation. The public JH CSV is group-level while the SM settlement artifact may be site-level and evaluated only on observed plant-hours. Do not compare a full-capacity group forecast to a partial observed-capacity actual unless the official/local evaluation semantics make the quantities commensurate. If there is no valid common prediction unit and observed mask, report the incompatibility and stop W/blend inference rather than inventing a conversion.

## Planned diagnostics, only after alignment passes

For each period and fixed alpha: common-mask group-unit penalty (descriptive, not full-observation official W); G1/G2; 11–15 and nonpeak; monthly; signed group residuals; residual correlation between JH and SM; fraction of group-hours with opposite residual signs; and loss contribution where absolute forecast disagreement is largest. Run the 168-hour paired moving-block bootstrap with 5,000 replicates and fixed seed 56 for each nonzero alpha versus alpha 0. Separately reproduce the published JH local W where its scoring definition allows. This is descriptive, and does not remove validation-period reuse or multiple-comparison selection bias.

## Interpretation rules

Distinguish (A) similar and weaker SM predictions, (B) diverse residuals without W improvement, and (C) lower W at fixed low-alpha mixtures in both periods. Even case C is not independent future validation and does not authorize a submission candidate. Any external-data eligibility conclusion remains separate from prediction performance and requires explicit rule/source evidence.

