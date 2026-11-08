# SM#58 Controlled Pilot

Date: 2026-11-08 (KST)
Prerequisites: source and cutoff evidence are **conditional** as documented in [SM58_GFS_PUBLICATION_EVIDENCE.md](SM58_GFS_PUBLICATION_EVIDENCE.md). This is a local exploratory experiment, not a submission model.

## Fixed A/B experiment

Both arms used the same two-year training window (2022-06-01 01:00 KST through 2024-06-01 00:00 right-closed), the same eligible input rows and evaluation mask, `rich` weekday-only Site LightGBM, seed 7, `site_code` removed, reference composition, no external source other than GFS, and the original LightGBM parameters. The only arm difference was the addition of `gfs_lcdc`, `gfs_mcdc`, and `gfs_hcdc` in B. The existing Group model was not used; site predictions were summed to the two frozen reference groups for settlement scoring. This isolates the three cloud-layer feature increment within this pilot, not a full SM46 blend comparison.

The 2024-06-01–2025-06-01 evaluation used 8,672 timestamps with eligible GFS and layer inputs and 2,149,985 observed site-hour rows. The 365 target days had 100% layer-run object/cutoff support; 88 hourly timestamps outside the common GFS feature support were omitted identically from both arms. Training had 1,908,816 site-hour rows and 25,965 eligible source timestamps. The pilot's local scoring function and independent hourly recomputation matched exactly in both arms.

## Results

| Metric | A: WA/WB + GFS DSWRF/TCDC | B: A + LCDC/MCDC/HCDC | B − A |
|---|---:|---:|---:|
| Reference-group W (KRW) | 188,593,035.91 | 186,530,358.85 | **−2,062,677.06** |
| G1 W | 89,356,612.35 | 88,624,770.37 | −731,841.98 |
| G2 W | 99,236,423.56 | 97,905,588.47 | −1,330,835.08 |
| 11–15 W | 155,847,352.53 | 153,785,426.19 | −2,061,926.34 |
| Off-peak W | 32,745,683.38 | 32,744,932.66 | −750.72 |
| Site MAE (kWh) | 5.88114 | 5.87851 | −0.00263 |
| Weighted individual W | 370,746,351.54 | 369,658,672.20 | −1,087,679.34 |
| Cancellation benefit | 182,153,315.63 | 183,128,313.35 | +974,997.72 |
| Cancellation ratio | 49.13% | 49.54% | +0.41 percentage points |

The group W improvement is the combination of a 1.088M reduction in weighted individual absolute error and a 0.975M increase in cancellation benefit. The result is concentrated in peak hours; non-peak W is nearly unchanged. Seven of twelve months improved and five worsened. Both groups improved in aggregate, but monthly movements were mixed.

| Target month | A W | B W | B−A |
|---|---:|---:|---:|
| 2024-06 | 12,027,597 | 12,661,908 | +634,311 |
| 2024-07 | 20,916,757 | 20,092,373 | −824,384 |
| 2024-08 | 17,363,825 | 16,905,279 | −458,546 |
| 2024-09 | 21,333,511 | 20,011,435 | −1,322,076 |
| 2024-10 | 19,075,475 | 18,487,863 | −587,612 |
| 2024-11 | 12,168,235 | 12,604,924 | +436,689 |
| 2024-12 | 12,395,400 | 12,655,406 | +260,007 |
| 2025-01 | 13,382,567 | 13,697,950 | +315,383 |
| 2025-02 | 15,264,813 | 15,669,178 | +404,365 |
| 2025-03 | 12,686,843 | 12,645,412 | −41,431 |
| 2025-04 | 14,875,615 | 14,185,028 | −690,587 |
| 2025-05 | 17,102,398 | 16,913,603 | −188,795 |

The fixed-seed, 5,000-replicate paired 168-hour moving-block bootstrap for B−A was **[−5,786,434, +1,308,454] KRW**. It includes zero. The point estimate is promising but uncertain and does not meet a significance-based promotion standard. The small Site MAE reduction alone does not establish a settlement improvement.

## Reproducibility and limits

- Result JSON: `outputs/sm58/pilot_result.json` (ignored/local).
- A predictions SHA256: `28b4cacf877431559e14fe91763422657bb63ed317910069f29efe5c15b7810e`.
- B predictions SHA256: `b776e91609986644bb2e11814660ffaad380a889559761559c6fb31c19322e50`.
- Layer parquet SHA256: `ba87460c4571ffee124f378e47f665bb0308b449232baf0ad8c75502241779e2`.
- Inputs, scripts, features, model, scorer, and package versions are hashed in the local result JSON.
- Only seed 7 and the reused 2024–25 validation period were run. There is no 2023 pilot, multi-seed confirmation, Group model, submission inference, or leaderboard submission.
- The current-object S3 timestamp cutoff evidence is conditional rather than proof of first operational publication. The validation period has been reused in prior work, so the bootstrap does not remove experiment-selection bias.

## Decision

The pilot was technically feasible and the point W improved, but the preregistered uncertainty check does not establish stable benefit. Keep the result as exploratory; do not promote it to a submission candidate or expand seeds on this reused validation period. Preserve all existing submission files unchanged.
