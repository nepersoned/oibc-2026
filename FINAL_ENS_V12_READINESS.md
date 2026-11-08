# Final ens_v12 Submission Readiness

Audit date: 2026-11-08 KST
Working branch: `seongmin` at `b771a6d050469c8d93c15c22e9b7ecc73ff55214`
Read-only reference: `origin/main` at `793f5f6662f074dbc8e50d3b0f925b9b214c3683`
Recorded deadline: 2026-11-13 23:59:59 KST

## Decision

**Overall eligibility: CONDITIONAL. Reproducibility: C (not currently reproducible end-to-end from the local record).** The recorded leader remains S9 `ens_v12`, 6,460,690,768 points. No confirmed P0 file defect or data leak was found. There are **4 P1** evidence gaps that affect eligibility or a code-verification response. Retain the recorded submission and score; do not replace or regenerate its CSV during this audit. Do not describe the model as fully compliant until the source-rule scope and source-level use of ens_v12 have been evidenced.

The current DataEn challenge page states that external data is prohibited; the team's `origin/main:README.md` documents a later, conditional external-source policy and records a 2026-11-05 organizer response allowing specified sources and use patterns. Those statements require the archived integrated notice/response to establish which rule controlled S9. [DataEn challenge page](https://dataen.ai/en/challenge)

## ens_v12 lineage from recorded evidence

S9 is logged as JH#68 and used the `site_dv` Site model at 50.5% plus `l1umx+derived` Group model at 49.5%, with reference composition. The logs say the Site model combined LDAPS-present and LDAPS-free predictions; JH#62 records that UM regional/global inputs were missing after 2026-03 and that a model without those inputs was used as a fallback. JH#66's 15 derived cross-source features are reported as included in the Group model. The project describes WA/WB as the participant forecast inputs. These are **experiment-log claims**, not a per-submission feature manifest.

| Source / input | Recorded ens_v12 use | Public | Commercial use | Same-source re-download | D−1 17:00 cutoff | Plant-coordinate assignment | Future/actual leakage |
|---|---|---|---|---|---|---|---|
| Participant WA/WB | Site and Group forecast inputs | **PASS** provided | **PASS** competition data | **PASS** package source | **CONDITIONAL**: exact round/row lineage manifest absent | **PASS** station linkage is competition-provided | **CONDITIONAL**: design says rounds are available pre-cutoff, but S9 run manifest absent |
| NOAA GFS | Site; Group source/derived features and fallback | **PASS** public NOAA bucket | **PASS** U.S. government data per README | **PASS** stable NOAA object paths | **CONDITIONAL**: exact S9 run map absent; SM58's later S3 `Last-Modified` audit is current-object evidence, not first-publication proof | **PASS** fixed 20-point/all-site summary per README | **CONDITIONAL**: no S9 row-level as-of manifest |
| ECMWF IFS ENS via dynamical.org | Listed in `site_dv` and `l1umx`; D−2 00Z leads 40–63 documented | **PASS** public catalog/bucket per README | **CONDITIONAL**: CC BY 4.0 plus ECMWF Terms of Use are recorded; applicable terms snapshot not bundled | **PASS by documented catalog/bucket route** | **CONDITIONAL**: D−2 run rule is recorded, but exact S9 init/lead selection is absent | **PASS** fixed area summary per README | **CONDITIONAL**: exact feature/run lineage absent |
| KMA LDAPS / UMKR | Site model reportedly uses LDAPS through its supply period | **PASS** public API per README | **PASS** public data type 1 per README | **CONDITIONAL** API key/re-fetch procedure documented; S9 retrieval record absent | **CONDITIONAL**: README says use daily availability probes; the actual probe log is absent here | **PASS** fixed five-point mean per README | **CONDITIONAL**: no S9 row-level as-of manifest |
| KMA UM regional/global (UMRG/UMGL) | Used in `site_dv` / `l1umx` according to JH#59/#67/#68; JH#62 reports fallback after source end | **PASS** public API per README | **PASS** public data type 1 per README | **CONDITIONAL** API route documented; exact retrieval record absent | **CONDITIONAL**: exact S9 cutoff probes/run IDs absent | **PASS** fixed five-point summary per README | **CONDITIONAL**: exact feature/run lineage and fallback application absent |
| JH#66 derived features (15) | Reported in `l1umx+derived` | Not a standalone source | Follows parent sources | Follows parent sources | **CONDITIONAL**: exact derivation inputs/time cut not frozen in S9 manifest | **PASS by described fixed summaries** | **CONDITIONAL**: exact 15-column mapping and S9 feature matrix absent |

The public challenge page and the repository's later conditional-source policy are not treated as interchangeable. The repository logs record operator guidance for Open-Meteo removal, NOAA GFS, fixed-grid features and KMA API use, but the exact archived answer covering ENS via dynamical.org and UM regional/global in S9 was not found. There is no basis to declare a confirmed violation, but there is also not enough primary evidence here to declare full compliance. No future actual generation or weather was identified in the recorded design; exact row-level as-of evidence remains unavailable without the run manifest.

## Submitted artifact check

The exact files are present in the read-only `origin/main` Git tree, not in the current local working tree. Their Git blobs were read without changing or checking out them. Temporary byte-identical copies were passed to the repository validator and removed afterward.

| Artifact | SHA256 | Check |
|---|---|---|
| `predictions/submissions/composition_ens_v12.csv` | `933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463` | 253 unique participant sites, no duplicate site IDs; G1 20,465.655 kW, G2 22,189.715 kW |
| `predictions/submissions/forecast_ens_v12.csv` | `5ecb1f8daf3277b64ea47730c900e2685a50acfcf1fed39a9910c16139129123` | 17,520 rows; 8,760 timestamps per group; `+09:00`; 2025-06-01 01:00 through 2026-06-01 00:00; no duplicate/missing group-time keys, NaN, Inf or negative values |

Validator command used on temporary copies: `python src/validate_submission.py --composition <temporary composition copy> --forecast <temporary forecast copy>`. **Exit 0.** This verifies format and composition constraints, not regulatory eligibility or model lineage.

## LDAPS/UM fallback and output profile

JH#62 documents the earlier 4–5 month UM feature failure and says a no-UM model was used to restore the affected forecasts. JH#68/S9 records describe a replacement model for April–May and `src/splice.py` implements a target-day cutoff at 2026-04-01, selecting the fallback afterward. The final submission CSV contains all rows and no all-zero daily group totals. Its monthly forecast totals are smooth through the handoff:

| Target month | G1 total kWh | G2 total kWh |
|---|---:|---:|
| 2026-03 | 2,595,831 | 2,893,885 |
| 2026-04 | 2,680,710 | 3,012,917 |
| 2026-05 | 2,993,792 | 3,417,122 |

These static checks find no obvious collapse. The final group CSV has no model-component column, and the fallback parquet/model and splice manifest are not present in this checkout. Therefore the CSV cannot prove which fallback model produced each April–May row or that no hidden default-value path was used. This remains P1 evidence to obtain, not a confirmed output defect.

## Risk register

| Priority | Evidence / risk | Minimum resolution | JH material needed | Status |
|---|---|---|---|---|
| **P0** | No verified malformed submission, proven post-cutoff feature, or confirmed explicit breach found in the inspected artifacts. | None identified now; escalate if source notice establishes a direct conflict. | — | **0 open P0** |
| **P1** | Public DataEn page says external data is prohibited; repository README records a later conditional-source policy and operator response. Scope for ENS/dynamical.org and KMA UM regional/global is not evidenced. | Preserve the controlling notice and source-specific written answer; map each source to that rule. | Archived integrated notice clauses 5–10 and official Q&A/response covering all S9 sources. | Open |
| **P1** | No S9 feature/source/run manifest proves exact inputs, issue times, missing-run masks, commercial terms and same-source re-fetchability. | Supply immutable per-model/segment run manifest with file hashes, URL, init/run/lead and as-of cutoff. | GFS audit; ECMWF ENS source/run index; KMA availability probe logs; source/license snapshot. | Open |
| **P1** | Fallback exists in the log and generic splice code, but the exported CSV cannot prove the actual April–May fallback model and feature set. | Provide segment-level model IDs, prediction hashes, splice map and missing-input diagnostics. | LDAPS/UM model and no-source fallback artifacts for both Site/Group, plus final splice log. | Open |
| **P1** | Exact S9 train/inference parameters, package lock, seeds, feature order and end-to-end command are not bundled with the tracked CSV. | Provide one reproducibility bundle/manifest linking code revision, environment, configs and artifacts. | Final run command, environment lock, per-model parameters/seeds, model or retraining artifacts. | Open |
| **P2** | Public CSVs are tracked under `origin/main`, while source/model artifacts are not locally packaged; current records are split among README and JH logs. | Assemble requested verification bundle without changing the submission. | Use the five requests in `JH_HANDOFF_REQUEST.md`. | Document cleanup only |

## Reproducibility classification and recommendation

**C — important components are missing for end-to-end reproduction.** Generic source code exists, and the original CSV blobs are intact, but the exact S9 model bundle, execution manifest, environment lock, source-run audit and fallback artifacts are not available in this checkout. A reviewer can validate the submission file and inspect the declared procedure, but cannot currently rebuild the exact prediction byte-for-byte.

**Recommendation: preserve S9 and supplement evidence before the 2026-11-13 deadline.** The available record supports that it is the team's highest-scoring submission and that its CSV is structurally valid. Eligibility remains conditional until the source-rule conflict and exact source/fallback lineage are resolved. Do not claim “fully compliant” based only on the score or validator.
