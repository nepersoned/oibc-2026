# SM#56 Next Research Decision

Date: 2026-11-08 (KST)  
Reference: [SM56 complementarity report](SM56_COMPLEMENTARITY_REPORT.md) and [artifact alignment audit](SM56_ARTIFACT_ALIGNMENT_AUDIT.md)

## Decision

**Do not blend SM46 A1-REF into ens_v12 or create a new candidate.** Alpha 0.05 improved only the 2024 common-mask group penalty by 98,560 KRW (0.059%), its 168-hour bootstrap interval included zero, and 2023 worsened by 31.28m KRW under a severely incomplete G2 actual mask. Alpha 0.10 and 0.20 did not improve both periods. This is not stable evidence of additional settlement value.

The validation predictions show some residual diversity (2024 residual correlation 0.696 and opposite signs on 21.2% of nonzero group-hours), but the small low-weight point improvement is not statistically distinguishable from zero and shifts the over/underprediction balance. The 2023 lower correlation is confounded by low observed coverage and cannot be used as evidence of genuine complementarity.

## One recommended next hypothesis

If the team wants one more SM–ens_v12 diagnostic, test only this:

> **On the 3,802 2024–25 group-hours where generation is observed for every plant in both reference groups, does any preregistered low fixed SM share (0.05 or 0.10) reduce complete-group settlement W through residual cancellation?**

Use the same frozen JH and SM predictions, reference composition, SMP and 11–15 multiplier; do not retrain, tune alpha, or construct a submission. Report the selected complete-hour period's month, daylight, group and peak composition, and treat it as a selected-subset diagnostic rather than a new independent validation. Do not extend the claim to 2023–24, where there are zero fully observed group-hours. If the complete-hour sample is not adequately represented across daylight and months, stop this line and keep ens_v12 and SM46 separate.

The ens_v12 external-input lineage is not independently verified from the public validation files. Resolve source manifests, licenses, exact retrieval sources and prior-day publication timestamps separately before any rule-based claim or operational blending decision.

## Status

- SM#56: diagnostic completed; no model or submission change.
- Official score: none for SM#56.
- Recommended operational action: preserve the recorded ens_v12 score and the already validated SM46 A1-REF artifacts separately. Do not infer remaining leaderboard attempts from repository files.

