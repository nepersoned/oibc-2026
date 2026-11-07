# SM#49 Submission Readiness Audit

## Candidates and immutable files

All files below were checked in place. Their SHA256 values equal the supplied SM46 expected hashes or SM48's existing manifest values. No candidate CSV or prior manifest was rewritten.

| Candidate | Composition path | Composition SHA256 | Forecast path | Forecast SHA256 |
|---|---|---|---|---|
| A — A1-REF | `outputs/sm46/composition_sm46_a1_ref.csv` | `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` | `outputs/sm46/forecast_sm46_a1_ref.csv` | `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` |
| B — A1-COMP | `outputs/sm46/composition_sm46_a1_comp.csv` | `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872` | `outputs/sm46/forecast_sm46_a1_comp.csv` | `0cda37b9576e1fa35cf849cf11847414dc440ab2242598f33d2ab68fa75ddfa9` |
| C — SM48 B2 | `outputs/sm48/composition_sm48_final.csv` | `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872` | `outputs/sm48/forecast_sm48_final.csv` | `7d48693a161db87cc55c202dba006e4eda874d86c0e3712046ba5e290f4f8067` |

A and B hashes match the frozen SM46 candidate records; C hashes match the unchanged `outputs/sm48/manifest.json`. Candidate B and C deliberately share the fixed composition, but have different forecasts. Never pair B's composition with A or C's forecast by name alone; use the rows above.

## Local format checks

Re-ran `src/validate_submission.py` on all three original file pairs. Exit codes: **A=0, B=0, C=0**.

Each composition maps all 253 supplied site IDs once to G1/G2. Each forecast has 17,520 unique group-time rows, 8,760 timezone-aware KST timestamps (`2025-06-01 01:00` through `2026-06-01 00:00`), no missing/duplicate timestamps, no NaN/Inf/negative values. Capacity checks:

| Candidate | G1 sites | G1 kW | G2 sites | G2 kW |
|---|---:|---:|---:|---:|
| A | 134 | 20,465.655 | 119 | 22,189.715 |
| B | 138 | 21,161.640 | 115 | 21,493.730 |
| C | 138 | 21,161.640 | 115 | 21,493.730 |

Validator exit 0 certifies submission format against local `sites.csv` and `smp.csv`; it does not certify forecast accuracy or data-policy compliance.

## Provenance and time cutoff

SM46 A/B manifests record `OIBC_CAL_MODE=weekday`, `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_GFS=0`, `OIBC_GEFS=0`, `OIBC_UM=0`, `OIBC_SRC=prov`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, `OIBC_WX2` unset, and `--ext none`. They list 92 Site and 300 Group columns; calendar inputs are `dow` and `is_weekend`. The inspected feature lists have no `is_hol`, `is_off`, `off_run`, `ext_*`, `phys_*`, `sp_*`, or `hat_*` fields. Candidate C reuses the same Site3 and uses the 300-column weekday Group design recorded in SM48 results. `holidays` and `EXTRA_OFF` are not used by this weekday path.

The local package's `README.md` documents that the supplied `lat/lon` are shifted/rounded and warns against identifying a site/operator or reconstructing original location. The existing solar geometry uses only supplied metadata; no original coordinates were recovered and no external location/weather join was made. Site and Group models use provided WA/WB forecasts and historical training generation; no future generation or observed test weather is present in the test inputs. SMP is used for scoring/format timebase, not as a future generation target.

The official [DataEn 2026 OIBC page](https://dataen.ai/en/challenge/2026) says forecasts must not use information generated after the prior-day 17:00 KST cutoff and bans outside data and externally trained models. The local package README and scorer define the 20 MW, timestamp, and W-format checks. The 2026 presentation itself was not found as a repository file; this audit uses the 2026 briefing points supplied by the user. It does not use the separate 2023 slide deck as a 2026 authority.

This is a code, manifest, and artifact lineage audit rather than a regulatory ruling. The supplied-coordinate restriction is observed conservatively; confirm the portal's current remaining submission count and any participant-specific notices there before upload.

## SM48 Group coverage qualification

The SM48 optimized composition had zero G2 labels with `coverage >= 0.3` in its 2023 Group fit. C's 2023 G2 output is consequently extrapolative. In the 2024 fit, fixed composition changed eligible label counts to G1 11,798 and G2 3,540 (versus reference 12,346 and 2,889). Its 2024 W gains are not a fresh out-of-sample guarantee. See `SM48_COMPOSITION_GROUP_REFIT.md` and `outputs/sm48/manifest.json`.

The existing SM48 manifest has two entries for the Group-refit script under Windows and normalized path spellings. The Windows-spelled entry (`9904…`) is the run-time source hash; the normalized entry (`21b5…`) is the later committed script after removing a duplicate, idempotent environment-setting block. The candidate CSV hash still matches the original SM48 manifest exactly. The cleanup did not change model inputs, parameters, or fit logic. The original SM48 manifest was left untouched.

## Final file selection

Recommended conservative pair: **Candidate A — A1-REF**, exact paths in the table above. Candidate C has the lowest historical 2024 and reused-holdout point W but the B2−B1 paired bootstrap interval includes zero; its composition and validation period were previously reused, and submission W is unknown. Keep Candidate B as a valid alternate only if the user explicitly chooses portfolio optimization over the conservative reference grouping. Do not mix candidate files. No portal action was taken.
