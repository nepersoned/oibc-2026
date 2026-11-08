# SM#54 Preregistration — Settlement Error Decomposition

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `303a17ad6839088672342049471386cce6216a88`
Status: registered before score recomputation. Artifact SHA gate subsequently failed, so the decomposition was stopped.

## Question

Explain why SM53's Site MAE improved while its fixed Site/Group settlement W worsened. This is a post hoc accounting decomposition of the already evaluated 2024–25 predictions, not a new model experiment or an independent validation.

## Frozen inputs and checks

- Baseline Site: A1 weekday Site seed7, `outputs/val_sm45_a1_s7_sites.parquet`, SHA256 `dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26`.
- Candidate Site: SM53 Site seed7, `outputs/val_sm53_profile_s7_sites.parquet`, SHA256 `1ba0066f6457f8eb242673124ca882ef98c3a09c167b04815dc8f853a08eacf4`.
- Frozen Group: weekday Group seed100, `outputs/sm45/group_a1_2024.parquet`, SHA256 `651b2f296316139af6ccf6aecabdd3071b1710de6fff35df18ecd20bb63b58b7`.
- Existing redistributed blends: baseline `a0332f098ef64959c7b47f04ebfd3e2e6c72fb75d0660aea2822f908b6ea4cfa`; candidate `69d9422d79a5806b5d378fb5bc4d39fbcfe109775b2f86124e994c8a1055208a`.
- Period is right-closed `(2024-06-01 00:00, 2025-06-01 00:00]` KST; reference composition; alpha 0.2; identical official observed site-hour mask, SMP, and `k=3` for timestamps 11–15, otherwise 1.
- Any missing/mismatched artifact, key grid, timestamp, mask, or W reproduction stops analysis. No model training or replacement prediction is allowed.

The paths existed and the Site/blend hashes matched, but the frozen Group file's current SHA256 did not match the value recorded in `outputs/sm53/pilot_2024.json`. This triggers the preregistered stop gate; no decomposition was run and no other Group file was substituted.

## Fixed decomposition

For observed site-hour residual `e_it = pred_it - actual_it` and official `w_t = 0.1 × SMP_t × k_t`:

- `W_individual = sum_i,t w_t × |e_it|` on the official observed site-hour mask.
- `W_group = sum_g,t w_t × |sum_i(in g) e_it|`; this is the official settlement penalty.
- `C_cancel = W_individual - W_group`.
- Report `Δ = Candidate - Baseline`; therefore `ΔW_group = ΔW_individual - ΔC_cancel`.

Compute these totals for the portfolio, G1/G2, 11–15 peak/nonpeak, morning/afternoon (solar-azimuth side using the same supplied-coordinate convention as SM53), month, and day. Also report ordinary Site MAE, raw and weighted signed group residuals, and weighted over/under prediction contributions. The cancellation ratio is `C_cancel/W_individual`.

Top ten adverse dates are diagnostic rankings only. Do not use them to define a correction, feature, or new selection rule. No uncertainty interval is required for this accounting identity; do not imply causal attribution from it.

## Decision rules

Verify the recorded blended W values and their unrounded difference (approximately +872,544.15 KRW). Determine whether the change is arithmetically explained by increased weighted individual error, reduced cancellation benefit, or both. If the decomposition or subgroup sums do not reconcile within numerical tolerance, report the discrepancy and stop. Recommend only one next research direction from the specified options; do not estimate future model performance or tune a correction on 2024 outcomes.

No CSV, submission artifact, or existing model output may be changed. No external data is used.

## SM55 follow-up

The Group hash copied into this preregistration contained a transcription typo. The later provenance check found the existing artifact matched SM50, SM51, and the SM53 JSON manifest. The original preregistration and stop history are retained; see [SM55 audit](SM55_ARTIFACT_PROVENANCE_AUDIT.md).
