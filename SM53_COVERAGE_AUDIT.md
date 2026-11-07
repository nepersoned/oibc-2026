# SM#53 Historical Profile Coverage Audit

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `bd9b69c961920820aff44550743380b8987f2219`

## Method

At each evaluation start, inspect the preceding two years of provided generation and `sites.csv` only. The profile support count is the number of site-days with at least one matched morning/afternoon clear-sky-normalized output pair in the same 5° solar-elevation band. Keep `elev >= 15°`, `ghi_cs >= 250 W/m²`, and only complete paired dates whose last right-closed timestamp is at least 48 hours before the prior-day 17:00 forecast issue time. This is enforced by allowing profile days through `target_day(start) - 4 days`. Missing generation rows are not treated as zero.

Solar geometry uses the existing `features.solar()` and `target_day()` functions with supplied, shifted coordinates only. No evaluation-period generation or observed weather, external irradiance, source forecast, reconstructed coordinate, or portal result enters this audit. Reference groups map source `current_group=A` to G1 and `B` to G2.

## Two-year support at each model cutoff

Eligibility below means at least 30 paired site-days; this cutoff was fixed before validation W was inspected. Capacity coverage uses the sum of `capacity_kw` from the supplied `sites.csv` divided by the total capacity in that group or portfolio.

| First forecast timestamp | Two-year history available | Paired elevation-band rows | Plants with any paired day | Capacity with any paired day | Plants with >=30 paired days | Capacity meeting >=30-day gate |
|---|---|---:|---:|---:|---:|---:|
| 2023-06-01 01:00 KST | 2021-05-29 00:00–2023-05-29 00:00 | 110,056 | 106/253 | 20.89% | 106/253 | 20.89% |
| 2024-06-01 01:00 KST | 2022-05-30 00:00–2024-05-29 00:00 | 221,884 | 202/253 | 74.26% | 179/253 | 63.74% |
| 2025-06-01 01:00 KST | 2023-05-30 00:00–2025-05-29 00:00 | 399,991 | 253/253 | 100.00% | 253/253 | 100.00% |

“Paired elevation-band rows” counts site-day-band pairs, not independent observations. The profile estimator first reduces those pairs to one median asymmetry per site-day, so densely observed days do not receive more weight than sparse paired days.

| Forecast start | Group | Any paired support | Capacity with any paired support | >=30 paired days | Capacity meeting >=30-day gate |
|---|---|---:|---:|---:|---:|
| 2023-06-01 | G1 | 100/134 plants | 40.71% | 100/134 plants | 40.71% |
| 2023-06-01 | G2 | 6/119 plants | 2.61% | 6/119 plants | 2.61% |
| 2024-06-01 | G1 | 130/134 plants | 94.14% | 127/134 plants | 87.50% |
| 2024-06-01 | G2 | 72/119 plants | 55.92% | 52/119 plants | 41.82% |
| 2025-06-01 | G1 | 134/134 plants | 100.00% | 134/134 plants | 100.00% |
| 2025-06-01 | G2 | 119/119 plants | 100.00% | 119/119 plants | 100.00% |

## Support by season

Season counts are matched site-days across the same two-year history, after the fixed solar-elevation and 48-hour rules. A site can contribute to more than one season.

| Forecast start | Season | Matched site-days | Sites represented |
|---|---|---:|---:|
| 2023-06-01 | Winter | 10,678 | 93 |
| 2023-06-01 | Spring | 12,602 | 106 |
| 2023-06-01 | Summer | 6,856 | 58 |
| 2023-06-01 | Autumn | 9,269 | 77 |
| 2024-06-01 | Winter | 21,533 | 173 |
| 2024-06-01 | Spring | 24,865 | 202 |
| 2024-06-01 | Summer | 14,937 | 117 |
| 2024-06-01 | Autumn | 17,949 | 136 |
| 2025-06-01 | Winter | 36,708 | 253 |
| 2025-06-01 | Spring | 38,517 | 253 |
| 2025-06-01 | Summer | 31,595 | 252 |
| 2025-06-01 | Autumn | 34,425 | 252 |

Across all 253 plants, the paired-day support 10th percentile / median / 90th percentile was 0 / 0 / 689.6 days at the 2023 cutoff, 0 / 224 / 720 days at the 2024 cutoff, and 322.2 / 589 / 730 days at the 2025 cutoff. The zeros are unobserved plants, not zero-generation labels.

## Interpretation

SM52’s 2023 support concern remains real: the new observed-generation-only method avoids the expensive OOF requirement but cannot create a history for the unobserved 147 plants or the unsupported portion of G2. However, the 2025 submission training cutoff has matched profile support for all 253 plants, and the 2024 validation cutoff has materially broader coverage than the 2023 cutoff. This is enough to justify a carefully isolated 2024 pilot and a 2023 stress diagnostic; it does not establish the feature’s predictive value or solve the 2023 support limitation.

These are pre-validation support counts. They do not use evaluation actuals, nor do they prove that the observed subset is representative of plants scored during each hour.
