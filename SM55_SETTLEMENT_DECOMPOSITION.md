# SM#55 Settlement Error Decomposition

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `0868efc1b1ee5a3a6d9fd29ea829af32ae997e28`
Scope: retrospective accounting decomposition of frozen SM53 2024–25 forecasts; no training or tuning.

## 1. Setup and reproduction

SM53's saved baseline/candidate Site predictions, frozen Group seed100 prediction, and both redistributed blends passed SHA256 and grid checks. The SM54 discrepancy was a documentation typo; see [SM55 artifact provenance audit](SM55_ARTIFACT_PROVENANCE_AUDIT.md). Each saved blend matched a row-wise reapplication of the existing SM39 `redistribute()` exactly (maximum absolute difference 0.0 kWh).

Evaluation uses the same 2,170,645 observed site-hour mask, reference composition, SMP, and official `k=3` for timestamps 11–15, otherwise `k=1`. All group settlement W calculations use `src/scoring.py` and are cross-checked with independent hourly penalties. Both match:

| Model | Prior SM53 reported W | SM55 recomputed W | Difference |
|---|---:|---:|---:|
| Baseline A1 seed7 + frozen Group100, alpha 0.2 | 198,977,095.7827 | 198,977,095.7827 | 0.0000 |
| SM53 seed7 + same Group100, alpha 0.2 | 199,849,639.9321 | 199,849,639.9321 | 0.0000 |
| Candidate − baseline | +872,544.1494 | **+872,544.1494** | 0.0000 |

The table shows unrounded KRW values to four decimals; rounded whole-KRW values are 198,977,096, 199,849,640, and +872,544.

## 2. Portfolio loss decomposition

For each observed site-hour, `e_it = prediction_it - actual_it`, `w_t = 0.1 × SMP_t × k_t`. Weighted individual W sums site absolute errors before aggregation; official group W sums signed site errors within G1/G2 first, then takes absolute values. `C_cancel = W_individual − W_group`. Δ is candidate minus baseline.

| Metric | Baseline | Candidate | Δ |
|---|---:|---:|---:|
| Site MAE on redistributed forecasts (kWh/site-hour) | 5.9544 | 5.9067 | **−0.0477** |
| Weighted individual W (KRW) | 377,954,933.08 | 376,601,962.14 | **−1,352,970.95** |
| Group settlement W (KRW) | 198,977,095.78 | 199,849,639.93 | **+872,544.15** |
| Cancellation benefit (KRW) | 178,977,837.30 | 176,752,322.20 | **−2,225,515.09** |
| Cancellation ratio | 47.3543% | 46.9335% | **−0.4208 pp** |

Identity check: `ΔW_group = ΔW_individual − ΔC_cancel = −1,352,970.95 − (−2,225,515.09) = +872,544.15 KRW`.

The Site MAE fell by about 0.80%, and the SMP/peak-weighted individual absolute-error total fell by 1.353 million KRW. But the benefit from cancellation between plants fell by 2.226 million KRW. Thus the group settlement loss worsened because the reduced cancellation benefit outweighed the lower individual-error total. This is an arithmetic explanation, not a causal claim about the physical effect of the profile feature.

The signed-error direction also shifted toward underprediction: mean observed site residual changed from −0.0713 to −0.2823 kWh; mean group-hour residual from −8.83 to −34.98 kWh; SMP/peak-weighted group signed residual mean from −22.74 to −66.46 kWh. Group overprediction penalty contribution fell by 6.353 million KRW, while underprediction contribution rose by 7.226 million KRW.

## 3. G1/G2 and peak decomposition

| Segment | Δ individual W | Δ group W | Δ cancellation benefit | Interpretation |
|---|---:|---:|---:|---|
| G1 | −699,253 | −390,791 | −308,462 | Group W improved; weaker cancellation offset part of the individual-error improvement. |
| G2 | −653,718 | **+1,263,335** | **−1,917,053** | Individual W improved, but lost cancellation more than offset it. |
| 11–15 peak | +28,785 | **+958,465** | **−929,680** | Individual weighted error was almost flat; reduced cancellation explains nearly all peak worsening. |
| Nonpeak | −1,381,756 | −85,921 | −1,295,835 | Large individual improvement was mostly erased by weaker cancellation. |

G1/G2 deltas sum to the portfolio deltas. Peak and nonpeak deltas also sum to the whole-period totals.

Within peak time, G1 group W improved by 283,002 KRW (individual W +69,668; cancellation benefit +352,670). G2 peak W worsened by 1,241,467 KRW (individual W −40,882; cancellation benefit −1,282,350). Therefore G2 accounts for the peak deterioration. G2's peak group signed residual mean moved from −47.78 to −114.61 kWh; its weighted signed mean moved from −81.77 to −148.86 kWh. Peak underprediction W contribution rose 6.195 million KRW while overprediction contribution fell 5.237 million KRW.

Across all hours, G1 mean group residual shifted from +3.73 to −25.78 kWh (weighted signed mean +3.28 to −46.10 kWh); G2 shifted from −21.39 to −44.18 kWh (weighted −48.77 to −86.82 kWh). G1 overprediction contribution fell by 4.030 million KRW and underprediction contribution rose by 3.640 million; G2 overprediction fell by 2.323 million and underprediction rose by 3.586 million. The near-balanced shifts in total W still differ by group because their within-group cancellation changed differently.

By solar side, morning Δ individual/group/cancellation W was −254,247 / +297,636 / −551,883 KRW. Afternoon values were −1,098,724 / +574,908 / −1,673,632 KRW. Both sides show the same accounting pattern: individual weighted error fell, but cancellation benefit fell more.

## 4. Monthly and adverse-date diagnostics

Six of the 12 complete months improved and six worsened. The final `2025-06` right-closed 00:00 bucket is one boundary hour and is excluded from that count.

| Month | Δ individual W | Δ group W | Δ cancellation benefit |
|---|---:|---:|---:|
| 2024-06 | −746,733 | −251,289 | −495,443 |
| 2024-07 | +208,191 | +521,047 | −312,856 |
| 2024-08 | −23,874 | +210,490 | −234,364 |
| 2024-09 | +529,929 | +634,605 | −104,677 |
| 2024-10 | +157,430 | +319,966 | −162,536 |
| 2024-11 | −26,242 | −81,719 | +55,477 |
| 2024-12 | +99,052 | +387,357 | −288,305 |
| 2025-01 | −582,365 | −909,698 | +327,333 |
| 2025-02 | −234,506 | −219,957 | −14,550 |
| 2025-03 | −108,915 | −35,891 | −73,024 |
| 2025-04 | −406,193 | +324,541 | −730,734 |
| 2025-05 | −218,745 | −26,909 | −191,835 |

Largest monthly deterioration was September 2024 (+634,605 KRW); largest monthly improvement was January 2025 (−909,698 KRW). The ten highest adverse daily deltas are in `outputs/sm55/top10_adverse_dates.csv`; the largest was 2024-09-27 (+322,696 KRW), split G1 +180,829 and G2 +141,867, with peak contributions +159,659 and +122,057 respectively. The other top dates and their G1/G2/peak deltas are preserved in that file. These are post hoc diagnostics only.

## 5. Conclusion and limits

The best-supported description is **B: reduced within-group cancellation benefit**, with lower weighted individual error acting as an offset. The 11–15 degradation is especially attributable to G2's reduced cancellation; peak weighted individual error changed little. Site MAE is an unweighted average across observed plant-hours and does not encode the SMP/peak weights or whether residuals cancel after group aggregation.

The Site MAE above is calculated from the redistributed per-site forecasts that enter settlement, not from raw Site-only predictions. This decomposition does not establish why the SM53 feature changed residual alignment, and the 2024 window was repeatedly used in prior experiments. Do not tune group corrections or reselect features on these dates. Recommended next direction: **stop additional model development and focus on official submission management**. No candidate status or submission score changes.

## Reproducibility

- Script: `src/analysis/sm55_settlement_decomposition.py`
- Run: `.venv/Scripts/python.exe src/analysis/sm55_settlement_decomposition.py`
- Aggregate: `outputs/sm55/decomposition.json`
- Segment tables: `outputs/sm55/by_group.csv`, `by_peak.csv`, `by_group_peak.csv`, `by_solar_side.csv`, `by_month.csv`, `by_day.csv`, `top10_adverse_dates.csv`
- Aggregate result SHA256: `outputs/sm55/decomposition.json` — `70d5a57630b140f70c946dbbbf39614d92e46bed4ab525f659b4221d883046ff`.
- Analysis script SHA256: `src/analysis/sm55_settlement_decomposition.py` — `2eebc2bd4eebb98adab97e1e52e41356399c88ddcc98838981fe3d374fa03d07`.
- No model, forecast, submission CSV, or existing manifest was changed. The SM53 JSON manifest SHA256 remains as recorded; errata are added to Markdown only.
