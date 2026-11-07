# SM#49 Final Candidate Comparison

## Scope and scoring

No model, feature, composition, or forecast CSV was changed. The comparison uses the frozen SM46/SM48 site-hour Parquets and the three already generated CSVs. `src/scoring.py::score` and `sm39_group_site_integration.hourly_penalties` were applied to the same observed site-hour mask, reference/optimized composition, SMP series, and `k=3` at right-closed `ts` hours 11–15 (`k=1` otherwise). In every model/window, independent hourly W matched the official local scoring function exactly (absolute difference 0.00 KRW). The W formula and peak-hour convention follow the 2026 briefing facts supplied by the user and the local participant README/scorer; no older 2023 presentation is treated as a 2026 source.

| Candidate | Composition / prediction | 2023–24 W | 2024–25 W | Dec 2024–May 2025 W |
|---|---|---:|---:|---:|
| A — A1-REF | SM46 reference / SM46 A1-REF | 106,673,757 | 197,526,260 | 87,757,370 |
| B — A1-COMP | SM45 fixed / SM46 A1-COMP | 107,077,100 | 196,397,961 | 86,870,948 |
| C — SM48 B2 | SM45 fixed / SM48 refit Group | 106,740,431 | 194,338,244 | 86,259,282 |

Each score is reproduced from saved predictions; the score periods use the established right-closed local validation windows. The last window includes the 2025-06-01 00:00 boundary hour, so June contributes only that boundary observation and is not counted as a complete holdout month.

## Group and peak-hour decomposition

| Window / candidate | Total W | G1 W | G2 W | 11–15 W | Off-peak W |
|---|---:|---:|---:|---:|---:|
| 2023–24 A | 106,673,757 | 79,437,385 | 27,236,372 | 88,965,726 | 17,708,031 |
| 2023–24 B | 107,077,100 | 76,298,267 | 30,778,833 | 89,329,711 | 17,747,389 |
| 2023–24 C | 106,740,431 | 75,929,541 | 30,810,890 | 88,980,050 | 17,760,381 |
| 2024–25 A | 197,526,260 | 93,693,778 | 103,832,482 | 163,019,883 | 34,506,377 |
| 2024–25 B | 196,397,961 | 98,106,024 | 98,291,937 | 161,946,076 | 34,451,886 |
| 2024–25 C | 194,338,244 | 97,274,255 | 97,063,989 | 160,413,061 | 33,925,183 |
| Reused holdout A | 87,757,370 | 39,935,290 | 47,822,080 | 72,555,179 | 15,202,191 |
| Reused holdout B | 86,870,948 | 41,195,304 | 45,675,644 | 71,699,268 | 15,171,680 |
| Reused holdout C | 86,259,282 | 41,143,565 | 45,115,718 | 71,351,281 | 14,908,002 |

## Contrasts and interpretation

2024–25 versus A: B reduces W by 1,128,299 KRW; C reduces W by 3,188,017 KRW (1.61%). For C, G1 W increases by 3,580,477 while G2 W falls by 6,768,493. Versus B, C reduces G1 W by 831,769 and G2 W by 1,227,948, for a 2,059,717 total reduction. B2−B is the same-composition Group-blend increment. C−A also changes composition and Group training data and is a whole-pipeline contrast.

On the reused Dec–May window, B improves 886,422 KRW over A and C improves 1,498,088 KRW over A. C is 611,665 KRW better than B at the point estimate. The existing 5,000-replicate, 168-hour paired bootstrap for C−B is [−1,944,103, +670,232] KRW and includes zero. C−A is [−2,295,761, −851,975] KRW, but reuse/selection bias remains. Neither interval converts this repeatedly inspected holdout into an independent test.

| Window | Candidate vs A | Monthly buckets with lower / higher W | Daily date buckets with lower / higher / tied W* |
|---|---|---:|---:|
| 2023–24 | B | 5 / 6 | 175 / 191 / 1 |
| 2023–24 | C | 4 / 7 | 168 / 198 / 1 |
| 2024–25 | B | 7 / 4 | 197 / 168 / 1 |
| 2024–25 | C | 11 / 0 | 229 / 136 / 1 |
| Dec–May reused holdout | B | 4 / 2 | 106 / 76 / 1 |
| Dec–May reused holdout | C | 6 / 0 | 121 / 61 / 1 |

For the two full-year windows, monthly counts compare the 11 complete Jul–May buckets and exclude partial June boundary buckets. The Dec–May window counts the six named buckets; December begins at 01:00 KST and is partial, while the following June boundary hour is excluded. *Daily counts compare date-level sums of hourly W deltas and include partial boundary dates; the single tie is a boundary-only/zero-delta bucket. Daily wins are not an independent-sample significance test.

Monthly C−A W deltas (negative is better):

| Month | 2023–24 | 2024–25 | Reused Dec–May |
|---|---:|---:|---:|
| Jun boundary | −9,746 (partial) | −252,393 (partial) | — |
| Jul | +37,679 | −578,510 | — |
| Aug | +85,047 | −270,922 | — |
| Sep | +56,173 | −214,929 | — |
| Oct | −29,962 | −140,842 | — |
| Nov | −10,754 | −232,333 | — |
| Dec | +27,100 | −37,978 | −37,978 |
| Jan | +28,879 | −576,247 | −576,247 |
| Feb | +112,311 | −285,948 | −285,948 |
| Mar | −116,349 | −207,438 | −207,438 |
| Apr | −136,623 | −176,688 | −176,688 |
| May | +22,918 | −213,789 | −213,789 |

The 2024–25 full-year comparison includes June–November, which participated in selecting the SM45 composition; it is diagnostic, not independent. The reused holdout has broader month-by-month improvement for C against A, but it has already been inspected and selected against.

## Bias and secondary metrics

Signed bias is the sum of Site-hour forecast minus observed energy over the same observed-site mask; positive means overprediction. This is a diagnostic, not the settlement objective.

| Window / candidate | Signed bias (kWh) | G1 bias | G2 bias | Site-hour MAE (kWh) |
|---|---:|---:|---:|---:|
| 2023–24 A | −250,324 | +49,953 | −300,277 | 4.8943 |
| 2023–24 B | −174,934 | +128,893 | −303,827 | 4.8984 |
| 2023–24 C | −323,034 | −12,371 | −310,663 | 4.9038 |
| 2024–25 A | −111,891 | +51,538 | −163,429 | 5.9001 |
| 2024–25 B | −217,073 | −58,941 | −158,133 | 5.9092 |
| 2024–25 C | −267,647 | −50,877 | −216,771 | 5.8983 |
| Reused holdout A | +321,870 | +116,354 | +205,517 | 5.4178 |
| Reused holdout B | +218,592 | +80,808 | +137,783 | 5.4104 |
| Reused holdout C | +235,673 | +98,436 | +137,236 | 5.4097 |

2024 seasonal signed bias (kWh), with JJA/Son etc. assigned by timestamp month:

| Candidate | DJF | MAM | JJA | SON |
|---|---:|---:|---:|---:|
| A | +378,935 | −57,064 | −481,967 | +48,206 |
| B | +392,996 | −174,404 | −524,643 | +88,978 |
| C | +320,519 | −84,846 | −513,799 | +10,479 |

Lower MAE does not imply lower W. B has lower 2024 W than A while its Site-hour MAE is slightly higher; C has the lowest MAE but still shows group-specific bias tradeoffs.

## Reuse and coverage limits

A1-COMP was selected from 2024 observations and repeatedly evaluated on the same 2024 windows. The 2024 full-year score contains its composition-selection period. The Dec–May segment is a previously examined fixed holdout. The SM48 bootstrap does not remove multiple-comparison or evaluation-reuse bias. In the 2023 retrospective window, SM45 composition was chosen using 2024 data and the fixed composition had zero eligible G2 Group labels at `coverage >= 0.3`; C's 2023 G2 result is an extrapolation diagnostic, not an unbiased test.

All 3 model scores are backed by saved prediction Parquets and score reproduction. Source manifests for Site predictions and SM48 Group predictions are in `outputs/sm48/manifest.json`; candidate and input hashes are in `outputs/sm49/submission_files_manifest.json`.
