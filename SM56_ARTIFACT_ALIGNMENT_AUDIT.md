# SM#56 Artifact Alignment & Provenance Audit

Date: 2026-11-08 (KST)  
Working branch: `seongmin`  
SM reference revision: `87b9748271ba89d6d49333884ce5342deb79b8ef`  
Read-only JH reference: `origin/main` at `793f5f6662f074dbc8e50d3b0f925b9b214c3683`

## Scope

The JH files were read from the fetched `origin/main` Git objects; no main change, merge or cherry-pick was made. Local copies for reproducible analysis are in ignored `outputs/sm56/`. No forecast file was rewritten, and no model was trained.

## Public JH artifact checks

`predictions/README.md` at the reference commit documents the validation schema and semantics: `forecast_kwh` is the final group forecast, blending group-summed Site predictions at 0.505 and Group-model predictions at 0.495; the other two columns are the respective components. The validation file has no actuals.

| Period | JH validation file SHA256 | Rows | Groups × hours | Timestamp range (KST) | Duplicate / missing values | Component formula check |
|---|---|---:|---|---|---|---|
| 2023–24 | `04065af84c4b7aef5abb26f6eec39987f6b8d7991d39a8e5ff3582c12f6af3a1` | 17,568 | G1/G2 × 8,784 | 2023-06-01 01:00 – 2024-06-01 00:00 | none | `forecast = .505×site + .495×group`; max absolute difference 0.000955 kWh, consistent with CSV component precision |
| 2024–25 | `58388ca4328444443812116176cafdf07584f944e0ede11208524b39b95e233e` | 17,520 | G1/G2 × 8,760 | 2024-06-01 01:00 – 2025-06-01 00:00 | none | max absolute difference 0.000960 kWh |

The public `composition_ens_v12.csv` SHA256 is `933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463`. It is serialized differently from the local SM46 CSV, but after parsing it has the same 253 `site_id→group` assignments (G1 134, G2 119). The public forecasts use the right-closed validation windows and group-hour keys are complete.

| SM historical validation artifact | SHA256 | Rows / schema |
|---|---|---|
| `outputs/sm45/2023_A1_B1_site_group_20_sites.parquet` | `341677ec5326b77e123bbc86e3eca296b77d805c4eb76812b78562f4c72c86fe` | 2,222,352; `site_id, ts, kwh` |
| `outputs/sm45/2024_A1_B1_site_group_20_sites.parquet` | `a57692044c87d04ce3145a8d52e024d6f429ebca325e25f1e954d5287e0d79cd` | 2,216,280; `site_id, ts, kwh` |
| `outputs/sm45/group_a1_2023.parquet` | `22dc17b9581073a370a0dc4dd1d5fabcb75e281fd3a9b3fb4a76cf57f6052598` | 17,568; `group, ts, cf_hat, pred` |
| `outputs/sm45/group_a1_2024.parquet` | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | 17,520; `group, ts, cf_hat, pred` |

SM47/SM50 manifests describe these as calendar-weekday, no-external-weather A1-REF validation forecasts: Site seeds 7/21/42, Group seed 100, alpha 0.2, reference composition. Summing the saved SM site forecasts by group produces complete 17,568 / 17,520 group-hour grids. The historical SM official-local site-mask scores recalculate from the saved site forecasts and `src/scoring.py` within 0.48 KRW of the rounded published values.

## Actual coverage and score comparability

The target actual in the repository is the sum of generation rows present for each group-hour. It is not a complete-group actual throughout both validation years. Reference composition has 134 G1 and 119 G2 plants.

| Period | Observed site-hours | Mean observed sites / group-hour | Mean fraction of group sites | Fully observed group-hours (G1 / G2) |
|---|---:|---:|---:|---:|
| 2023–24 | 1,256,595 | G1 119.35; G2 23.70 | G1 89.07%; G2 19.92% | 0 / 0 |
| 2024–25 | 2,170,645 | G1 133.64; G2 114.15 | G1 99.73%; G2 95.93% | 7,790 / 3,802 |

The public JH artifact is a **full-group forecast**. The SM artifact is per-site; the SM local scorer joins forecasts to observed site-hours first and then aggregates that observed subset. To compare forecast complementarity on the JH group-prediction scale, the diagnostic separately sums all SM plant predictions into full-group predictions and scores both models against the same group sums of available generation, timestamps and weights. This is a common-target, partial-observation diagnostic; it is not a complete-group actual score, and is not the same as the published SM site-mask score. In 2023–24, especially G2, that incomplete actual is too weakly representative for a credible full-group performance conclusion. No coverage correction or imputed actual was used.

The existing JH experiment record reports ens_v12 W of 93,377,951 KRW (2023–24) and 167,041,881 KRW (2024–25). Applying the frozen formula to the published group CSV and local available-generation group sums gives 93,391,369 and 167,076,206 KRW, respectively: **+13,418** and **+34,325 KRW** versus the recorded figures. Those differences are not explained by integer rounding. The public prediction CSV has no paired manifest for its exact source-data hashes, scorer revision, or runtime. We therefore report a near but not exact reproduction; the cause remains unverified and the prior JH values are not silently replaced.

SM A1-REF local W is 106,673,757 / 197,526,260 KRW when scored on its established observed-site predictions. These values are retained as their own scoring series and are not compared directly with the full-group common-mask diagnostic.

## JH#56–73 results and overlap with SM research

The following summaries were read from the JH `EXPERIMENTS.md` in `origin/main@793f5f6`; they remain JH results, not SM results.

| JH study | Reported result / decision | Related SM work and distinction |
|---|---|---|
| #56 | Group loss L1 improved both validation years; adopted. Huber and peak-weighted variants did not. | SM#47 tried L1 on the Site model and worsened 2024; different target level, so it does not refute JH Group L1. |
| #57–58 | Site/Group blend candidate; Site L1 and Group no-recent-weight / more-tree variants worsened. | SM#43 studied Group seed bagging, not model-family/source complementarity. |
| #59–62 | ECMWF ENS and KMA UM inputs improved the Group model; Site-all feature set then improved; #62 found spring UM regional/global missingness and replaced that period’s model. | SM#42 used WA/WB cloud revision/disagreement as Site features; SM#50 diagnosed forecast regimes. Neither adds JH external NWP nor establishes rule eligibility. |
| #63–65 | Site loss candidates, curtailment tendency, and Group target/reference-CF designs; only Site L2 with k-weight narrowly improved, the Group target change failed. | SM#44 separately audited Group observed-capacity coverage and deferred candidate training; not a reproduction of JH target designs. |
| #66–68 | Fifteen cross-source derivatives improved Group; Site `site_dv` improved; the Site/Group mixture became the ens_v11/v12 lineage. | SM#42 overlaps conceptually on cloud disagreement/revision, but used provided WA/WB and a small Site feature family; JH#66 combines several external forecast sources and a wider derivative set. |
| #69 | KMA short-range forecast addition failed the two-year stability rule and was excluded from v12. | SM calendar-safe investigations did not use this source. |
| #70–73 | Bias diagnosis led to a spring-holiday scaling candidate; it worsened the official score (ens_v13), so ens_v12 remains the recorded best. A composition experiment also found apparent gain depended on low-history plants. | SM#45–49 studied calendar-safe candidates, composition and Group refit on its own validation setup; SM#55 analyzed Site-to-group cancellation for SM53. These are related diagnostics, not direct tests of JH v12 complementarity. |

The new SM#56 question is prediction-level complementarity across two already-trained systems. It does not repeat Group bagging, Site L1, WA/WB revision feature generation, or SM composition search.

## JH external-source provenance status

`SUBMISSIONS.md` records ens_v12/S9 as the official team-best submission and labels it compliant. The same repository records its model inputs as ECMWF ENS, KMA UM regional/global forecasts, LDAPS, and cross-source derivatives. An official score does not itself document permission or forecast availability. The local public artifact set has no ens_v12 row-level source manifest, exact external-input snapshots/hashes, retrieval/run logs, or release timestamps.

| Requirement | Finding from available record |
|---|---|
| Public source | ECMWF ENS / KMA UM / LDAPS are named in experiment notes; exact files and retrieval paths are not tied to the validation CSV. |
| Commercial-use terms | IDEAS describes a Dynamical ENS distribution as CC BY 4.0; the exact ENS snapshot/license evidence and the corresponding UM/LDAPS commercial-use terms are not in the prediction manifest. |
| Same-address reproducibility | Not verified for the exact historic inputs. No source manifest or snapshot hashes accompany the validation files. |
| Published before the prior-day 17:00 cutoff | Not verified: the CSV has valid timestamps but no source-run publication/retrieval-time record. |
| Same external information for every plant | Not verified from the saved group-level output; source notes indicate different Site/Group feature families and do not establish identical station/grid coverage. |
| No validation-period actual/statistic leakage | No row-level source manifest or extraction log is included, so this cannot be independently confirmed from these files. |

Accordingly, the ens_v12 data-rule status remains **not independently confirmed** in this audit, notwithstanding the team's recorded compliance label. This is separate from its leading official score of **6,460,690,768**.

## Reproducibility

- Analysis: [`src/analysis/sm56_complementarity.py`](src/analysis/sm56_complementarity.py)
- JH CSV snapshots and comparison artifacts: `outputs/sm56/` (ignored local outputs)
- Alignment/inputs manifest: `outputs/sm56/alignment_manifest.json`
- Machine-readable score summary: `outputs/sm56/complementarity.json`
- Preregistered scoring interpretation: [SM56_PREREGISTRATION.md](SM56_PREREGISTRATION.md)

