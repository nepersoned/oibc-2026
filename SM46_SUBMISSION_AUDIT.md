# SM#46 Submission Candidate Audit

Date: 2026-11-07 (KST)
Branch: `seongmin`
Starting revision: `2c20ee08ece286edb6c9e43b2ce135ae41572a7b`

## 1. Candidates and decision

Both requested candidates were generated from scratch for the submission period, saved under `outputs/sm46/`, reloaded, and passed `src/validate_submission.py` with exit code 0. Neither file was uploaded.

- **A1-REF:** Site LightGBM rich, seeds 7/21/42 averaged; Group LightGBM seed 100; 80% Site + 20% Group; reference composition; `OIBC_CAL_MODE=weekday`; two-year window; `--ext none`; Group `min_cov=0.3`.
- **A1-COMP:** same shared Site3 predictions; no Group blend; the exact SM45 10-site composition file copied byte-for-byte; weekday calendar; two-year window; `--ext none`.

The Site model was trained once and shared by both candidates. It used the right-closed training history `[2023-06-01 01:00, 2025-06-01 01:00)` and predicted `[2025-06-01 01:00, 2026-06-01 00:00]` KST. Candidate A's Group model used the same two-year window, reference composition, seed 100 and `min_cov=0.3`.

### Recommendation

**If choosing one of these two files, A1-REF is the more conservative choice.** It retains the reference portfolio and its point W is below SM41 in both historical full-year comparisons. The gains are very small and the existing 2024 paired bootstrap interval includes zero, so this is not proof of an improvement. A1-COMP has the lower 2024 full-year and fixed-holdout W, but is worse than SM41 over 2023–24 and its validation period was already used to select the composition. Under the SM45 preregistered statistical adoption criterion, **neither candidate has established a reliable improvement**. This recommendation ranks the two valid files; it does not change that criterion.

## 2. Input and feature-lineage audit

Run controls were set before importing model modules:

```text
OIBC_CAL_MODE=weekday
OIBC_EXT_SOURCES=no_openmeteo
OIBC_GFS=0, OIBC_GEFS=0, OIBC_UM=0
OIBC_SRC=prov
OIBC_SPATIAL=none, OIBC_PHYSICS=none
OIBC_WX2 unset; SM42 feature flag unset
--ext none for Site and Group
```

The Site input had 92 columns and the Group input had 300 columns. Both included only `dow` and `is_weekend` as calendar fields; neither contained `is_hol`, `is_off`, or `off_run`. The weekday path derives the day from supplied `ts` through `target_day()`, preserving the convention that 00:00 belongs to the prior target day. `holidays` and `EXTRA_OFF` are not accessed in this mode. External-weather flags were off, Site used `--ext none`, and Group source selection was `prov`; no external forecast columns entered either fitted feature list.

Training used only provided historical generation/forecasts and the two-year pre-submission window. Inference used only provided test WA/WB forecasts, timestamps, and site metadata. No test generation or observed test weather exists in the input path, and neither was loaded. No evaluation-period actuals were used to alter forecasts or composition.

The submitted composition uses supplied site IDs and the preselected portfolio. The Site rich feature list also includes `lat` and `lon` from `sites.csv`, as well as their existing solar-geometry derivatives. Those coordinates are supplied, shifted/rounded fields; no coordinate-based external weather join, site identification, or location reconstruction was done. The participant package warns against using coordinates to identify a plant/operator. The [official DataEn rule](https://dataen.ai/en/challenge) prohibits outside data; no external weather or holiday data was used.

## 3. Independent re-score of frozen SM45 artifacts

`src/analysis/sm46_decision_audit.py` re-created group forecasts from the frozen site/group Parquets, scored identical observed site-hour masks with the official scorer and independent hourly penalty aggregation, and asserted agreement within `1e-5` KRW.

| Model | 2023–24 W | 2024–25 W |
|---|---:|---:|
| SM41 legacy blend | 106,754,876 | 197,534,279 |
| A1 weekday REF blend | 106,673,757 | 197,526,260 |
| A1 weekday Site-only REF | 107,248,930 | 199,015,602 |
| A1 weekday Site-only COMP | 107,077,100 | 196,397,961 |

This independently confirms the previously reported A1-COMP 2024 full-year W. The 2024 full-year Site-only COMP value equals the SM45 result to the won after rounding.

The comparisons answer different questions:

1. **A1-REF vs SM41:** removing the external holiday features while retaining weekday information and refitting changed both Site and Group. Point W changed by −81,119 in 2023–24 and −8,019 in 2024–25. Existing 2024 paired bootstrap for A1-REF minus SM41: mean +4,806; 95% CI [−1,277,865, +1,287,139] KRW. This does not establish a score gain.
2. **A1 Site-only REF vs COMP:** Site forecasts are identical; only grouping changes. COMP changed full-year W by −171,830 in 2023–24 and −2,617,641 in 2024–25. On the previously inspected December–May holdout it changed W by −769,904; the existing 5,000-draw, 168-hour paired bootstrap interval was [−1,108,829, −455,768] KRW. This is a re-use of a known holdout, not a new independent validation.
3. **A1-REF blend vs A1-COMP Site-only:** this changes both composition and whether the Group model is blended, so the score difference is not a causal composition effect. COMP was +403,343 worse in 2023–24, −1,128,299 better in 2024–25, and −886,422 better on the fixed holdout.

## 4. Group, peak, and monthly diagnostics

All W figures are KRW. The 2023–24 observed-site coverage is relatively low and the legacy Group model had no eligible G2 training labels in that validation window; interpret that year's Group scores as partly extrapolative.

| Window / model | Total W | G1 W | G2 W | 11–15 W |
|---|---:|---:|---:|---:|
| 2023–24 SM41 | 106,754,876 | 79,417,053 | 27,337,822 | 88,886,367 |
| 2023–24 A1-REF | 106,673,757 | 79,437,385 | 27,236,372 | 88,965,726 |
| 2023–24 A1 Site REF | 107,248,930 | 79,933,804 | 27,315,126 | 89,545,713 |
| 2023–24 A1 Site COMP | 107,077,100 | 76,298,267 | 30,778,833 | 89,329,711 |
| 2024–25 SM41 | 197,534,279 | 93,807,603 | 103,726,676 | 163,021,141 |
| 2024–25 A1-REF | 197,526,260 | 93,693,778 | 103,832,482 | 163,019,883 |
| 2024–25 A1 Site REF | 199,015,602 | 94,338,816 | 104,676,787 | 164,085,589 |
| 2024–25 A1 Site COMP | 196,397,961 | 98,106,024 | 98,291,937 | 161,946,076 |
| Dec 2024–May 2025 SM41 | 87,772,396 | 39,958,651 | 47,813,745 | 72,539,406 |
| Dec 2024–May 2025 A1-REF | 87,757,370 | 39,935,290 | 47,822,080 | 72,555,179 |
| Dec 2024–May 2025 A1 Site REF | 87,640,852 | 39,723,431 | 47,917,421 | 72,259,552 |
| Dec 2024–May 2025 A1 Site COMP | 86,870,948 | 41,195,304 | 45,675,644 | 71,699,268 |

In the fixed holdout, the monthly A1-COMP minus A1-REF-blend W differences for Dec through May were +464,692, −164,362, −512,357, −182,495, +240,557, and −732,458 KRW. Thus the Site-only COMP candidate did not beat the blend in every month, even though it beat the Site-only REF comparison in each complete holdout month. The final `2025-06-01 00:00` right-closed boundary contributes a single boundary-hour amount; it is not a complete June month and is excluded from complete-month claims.

Existing composition bootstrap: 5,000 paired 168-hour block draws, seed 7; candidate COMP minus Site-only REF mean −771,725 and 95% CI [−1,108,829, −455,768] KRW. It supports the historical holdout contrast only. It does not remove the fact that this period had already been inspected, and it is not a bootstrap for A1-COMP versus A1-REF blend.

## 5. Submission CSV checks

The official validator returned exit code **0 for both candidates**. It checked 253 sites, two group capacities, the 8,760 KST time grid, 17,520 group-hour rows, time zones, duplicates/missing timestamps, and finite nonnegative predictions. Candidate A's groups are G1: 134 sites / 20,465.7 kW and G2: 119 / 22,189.7 kW. Candidate B's groups are G1: 138 / 21,161.6 kW and G2: 115 / 21,493.7 kW. The script additionally checked 2,216,280 site-hour rows, in-memory vs saved/reloaded CSV equality, group aggregation, forecast finiteness, and the fixed composition hash.

| Candidate | Composition CSV SHA256 | Forecast CSV SHA256 | Validator |
|---|---|---|---:|
| A1-REF | `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` | `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` | 0 |
| A1-COMP | `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872` | `0cda37b9576e1fa35cf849cf11847414dc440ab2242598f33d2ab68fa75ddfa9` | 0 |

The SM41 CSVs were re-hashed and remain unchanged: forecast `ed9d14e194259971802ef1e1530f0bd38b05455cf3ca66a7815abaedbd63fd8d`; composition `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd`.

## 6. Reproduction and artifacts

Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6. Site model used `src/model.py::PARAMS` with `random_state=7/21/42`, rich features and `site_code` dropped. Group used `src/agg_model.py::PARAMS` with `random_state=100`, `min_cov=0.3`. Exact dictionaries, feature lists, input/source hashes, prediction hashes and per-candidate validation records are in the manifests.

Commands:

```powershell
.\.venv\Scripts\python.exe src\analysis\sm46_submission_candidates.py
.\.venv\Scripts\python.exe src\analysis\sm46_decision_audit.py
.\.venv\Scripts\python.exe src\validate_submission.py --composition outputs\sm46\composition_sm46_a1_ref.csv --forecast outputs\sm46\forecast_sm46_a1_ref.csv
.\.venv\Scripts\python.exe src\validate_submission.py --composition outputs\sm46\composition_sm46_a1_comp.csv --forecast outputs\sm46\forecast_sm46_a1_comp.csv
```

Model forecasts and CSVs are local artifacts under `outputs/sm46/` and are excluded from Git. Candidate A and B manifests are `manifest_a1_ref.json` and `manifest_a1_comp.json`; aggregate hashes and feature inventories are in `manifest.json`. The historical GFS-related test failures were not run or modified in SM46.

## 7. Final selection statement

Both candidates are format-valid and generated without external weather or holiday data. A1-REF is the more conservative option if one of these two is selected because its point W direction versus SM41 is consistent across both full validation years and it does not use a composition chosen against the reused 2024 period. A1-COMP has stronger 2024/holdout W but a worse 2023 full-year result and added portfolio-selection risk. The original statistical preregistration remains unmet: A1-REF's 2024 bootstrap interval crosses zero, and the composition holdout is not independent. Portal upload remains the user's decision and was not performed.
