# SM#56 ens_v12 Prediction-Level Complementarity Report

Date: 2026-11-08 (KST)  
Analysis only: frozen artifacts; no training, tuning, or submission generation.  
Design: [SM56_PREREGISTRATION.md](SM56_PREREGISTRATION.md) · Alignment/provenance: [SM56_ARTIFACT_ALIGNMENT_AUDIT.md](SM56_ARTIFACT_ALIGNMENT_AUDIT.md)

## Comparison scale

The JH artifact is a full-group forecast. To make the prediction unit the same, the saved SM site predictions were summed over all 253 sites by reference group, then fixed blends were evaluated against the identical sums of generation rows available in the validation file, with identical SMP, `k` and group-hour keys. This is a common-mask group penalty using **partial actual totals**, not a full-capacity actual W. It is not directly comparable with SM's established site-mask W. The JH/SM historical actual coverage audit and the near-but-not-exact reproduction of the JH experiment W are documented separately. In particular, 2023–24 G2 actual coverage is too incomplete for a reliable full-group interpretation.

The JH `forecast_kwh` alpha-zero penalty was 93,391,369 / 167,076,206 KRW, versus the existing JH#68/ens_v12 record of 93,377,951 / 167,041,881. The differences (+13,418 / +34,325 KRW) are small relative to totals but not explained by displayed integer rounding. Exact reproduction is therefore **not achieved**; absent JH input/scorer manifest prevents resolving the gap.

## Fixed-weight results

All deltas below are candidate mixture minus alpha 0 (ens_v12); negative is lower penalty. Values are KRW. The score is the common-mask partial-actual group penalty described above.

| Period | alpha | Common-mask group penalty | Δ vs JH | G1 Δ | G2 Δ | Peak 11–15 Δ | Nonpeak Δ |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023–24 | 0.00 | 93,391,369 | 0 | 0 | 0 | 0 | 0 |
| 2023–24 | 0.05 | 124,671,631 | +31,280,262 | +3,628,264 | +27,651,998 | +27,236,665 | +4,043,596 |
| 2023–24 | 0.10 | 164,978,650 | +71,587,282 | +9,533,236 | +62,054,046 | +61,753,163 | +9,834,118 |
| 2023–24 | 0.20 | 253,526,867 | +160,135,498 | +25,473,581 | +134,661,917 | +137,041,726 | +23,093,772 |
| 2024–25 | 0.00 | 167,076,206 | 0 | 0 | 0 | 0 | 0 |
| 2024–25 | 0.05 | 166,977,646 | **−98,560** | −58,300 | −40,261 | +6,795 | −105,355 |
| 2024–25 | 0.10 | 167,704,406 | +628,200 | −10,501 | +638,701 | +706,052 | −77,853 |
| 2024–25 | 0.20 | 170,748,120 | +3,671,913 | +395,754 | +3,276,159 | +3,381,074 | +290,839 |

2024–25 alpha-zero residual correlation / opposite-sign share by group was G1 **0.815 / 18.9%** and G2 **0.634 / 23.4%**. For 2023–24 it was G1 0.377 / 28.4% and G2 0.113 / 38.5%; the low-coverage G2 result is not a reliable diversity estimate.

Alpha 0.05 improved 2024–25 by only 98,560 KRW (0.059% of this diagnostic W); it worsened 2023–24 by 31.28m KRW. Higher fixed SM weights increased the penalty in both years. The 2023 worsening is dominated by G2, where only about one fifth of group sites were observed on average; it cannot be treated as evidence about complete-group future performance.

Absolute segment penalties (KRW):

| Period | alpha | G1 | G2 | 11–15 peak | Nonpeak |
|---|---:|---:|---:|---:|---:|
| 2023–24 | 0.00 | 72,130,006 | 21,261,363 | 78,372,997 | 15,018,372 |
| 2023–24 | 0.05 | 75,758,269 | 48,913,361 | 105,609,662 | 19,061,969 |
| 2023–24 | 0.10 | 81,663,242 | 83,315,409 | 140,126,160 | 24,852,490 |
| 2023–24 | 0.20 | 97,603,587 | 155,923,280 | 215,414,723 | 38,112,145 |
| 2024–25 | 0.00 | 79,645,281 | 87,430,925 | 137,910,823 | 29,165,383 |
| 2024–25 | 0.05 | 79,586,981 | 87,390,665 | 137,917,619 | 29,060,028 |
| 2024–25 | 0.10 | 79,634,780 | 88,069,626 | 138,616,876 | 29,087,531 |
| 2024–25 | 0.20 | 80,041,035 | 90,707,085 | 141,291,897 | 29,456,222 |

## Bootstrap and month stability

Paired circular 168-hour moving-block bootstrap, 5,000 replicates, seed 56, comparing each fixed mixture to alpha 0:

| Period | alpha | Δ W | 95% interval |
|---|---:|---:|---:|
| 2023–24 | 0.05 | +31,280,262 | [+25,027,778, +37,594,860] |
| 2023–24 | 0.10 | +71,587,282 | [+59,063,870, +84,398,582] |
| 2023–24 | 0.20 | +160,135,498 | [+135,025,504, +186,038,295] |
| 2024–25 | 0.05 | −98,560 | [−789,187, +721,335] |
| 2024–25 | 0.10 | +628,200 | [−970,561, +2,516,892] |
| 2024–25 | 0.20 | +3,671,913 | [−314,294, +8,348,197] |

No 2024 interval excludes zero. Across the 12 target-day months, 2023–24 showed no monthly improvement for any tested alpha. In 2024–25, alpha 0.05 improved 8/12 months, alpha 0.10 improved 8/12, and alpha 0.20 improved 7/12. None was consistently beneficial across periods. The bootstrap does not remove multiple-alpha selection bias or repeated use of these validation years.

## Residual diversity and disagreement

| Period | JH–SM group residual correlation | Opposite-sign fraction (nonzero residual pairs) | Median / p90 absolute forecast difference (kWh) |
|---|---:|---:|---:|
| 2023–24 | 0.133 | 33.8% | 31 / 6,285 |
| 2024–25 | 0.696 | 21.2% | 12 / 900 |

The low 2023 correlation is not a clean diversity signal: its G2 targets average only 19.9% site count coverage and 0 of 8,784 group-hours are complete in either group. In 2024, residuals are positively correlated and have opposite signs in about one fifth of nonzero group-hour pairs. A low 5% weight produces a small whole-period reduction, but the bootstrap includes zero and peak W increases by 6,795 KRW. At the top decile of absolute forecast disagreement, alpha 0.05 adds 184,913 KRW in 2024; the slight total improvement comes from the remaining hours, not the largest-disagreement tail. This is descriptive, not causal.

The 2024 signed group-hour residual mean moves from −4.11 kWh at alpha 0 to +2.39 at alpha 0.05, +8.90 at alpha 0.10 and +21.91 at alpha 0.20. Weighted directional penalties at alpha 0 were 82.04m overprediction and 85.03m underprediction; at alpha 0.05 they were 83.69m and 83.28m, respectively. The marginal mix mostly shifts the bias balance while barely changing total W.

The lower residual correlation in 2023 also contrasts with SM#55's Site-level cancellation analysis, but it does not establish useful complementarity: the JH and SM group forecasts are on the full-group scale while the 2023 target is severely partial. SM#55's cancellation results concern a different SM53 feature comparison and cannot be transferred to ens_v12.

## Conclusion

The evidence is **Case B, with a major 2023 coverage qualification**: forecasts differ, but a robust group-W improvement is not demonstrated. In 2024, alpha 0.05 is nearly neutral and statistically inconclusive; alpha 0.10/0.20 worsen the point estimate. In 2023, all mixes worsen markedly, mostly against incomplete G2 actuals. The alpha values were fixed before scoring and are not candidates for post-hoc selection.

Do not promote an SM–ens_v12 mixture, generate a submission, or change the official candidate. Keep ens_v12's highest recorded official score and SM46 A1-REF's provided-data candidate record separate. External-source compliance is unresolved separately; see the alignment audit.

## Reproduction

- Run: `\.venv\Scripts\python.exe src\analysis\sm56_complementarity.py`
- Script: [`src/analysis/sm56_complementarity.py`](src/analysis/sm56_complementarity.py)
- Machine results: `outputs/sm56/complementarity.json`
- Input/alignment hashes: `outputs/sm56/alignment_manifest.json`
- Monthly group table: `outputs/sm56/monthly_2023-24.csv`, `outputs/sm56/monthly_2024-25.csv`
- Paired group-hour data: `outputs/sm56/aligned_group_hours_*.parquet` (local ignored output only)

SHA256:

| Artifact | SHA256 |
|---|---|
| Analysis script | `ade073470afd3a36352a460f75f91bee0e26c13d0a3a1db486cdcbcfbdf37daf` |
| Alignment/input manifest | `68d9b4065c2ac9228aa02ce10a8cd314b5661c6e512810bd7f711a8865680f55` |
| Score summary | `00a2bea0e0b3ed08043201f6fcd466acacc0a89f9609f5b79eed569596543bd1` |
| 2023–24 monthly table | `0f8ecd8c9b1ce9dab972de5538e8551b217891b0d5e3ee532e0a2a5cffd50d77` |
| 2024–25 monthly table | `2b86b1c82b1b1ddcb53880bb2a7349ef5af3c7ba0e7a8138435bc2280ba213cf` |

