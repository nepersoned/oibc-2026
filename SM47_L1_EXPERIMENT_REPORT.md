# SM#47 L1 vs L2 LightGBM Pilot — Report

Date: 2026-11-07 KST
Branch: `seongmin`
Starting revision: `c5ee70a79fe703c6a5046ea07afc1a9414531b69`

## Decision and stopping point

The preregistered **single-seed** comparison was run for both years. L1 improved the 2023 W but worsened 2024 W by 3,943,206 KRW (+1.982%). Per the preregistration, the pilot stops here: no bootstrap and no L1 seed21/42 training. No new candidate or submission CSV was generated. **Keep SM46 A1-REF** as the calendar-safe format-validated candidate; this experiment does not establish that L1 improves settlement W.

## Prior JH#7 and controlled difference

`EXPERIMENTS.md` records JH#7 “rich + L1 objective” at 204,815,516 KRW (−8.8% vs its reference) and marks it failed; JH#6 rich with the default objective was 204,043,129 KRW. JH#7 lacks stored details for seed, calendar inputs, external-weather switches, validation window, Site/Group integration and model parameters, so its W cannot be directly compared with this pilot.

SM47 isolates the Site objective under the modern SM46 pathway: C0 uses the existing weekday-only Site seed7 validation prediction; C1 uses a new seed7 fit with only `objective="regression_l1"` changed. Both use the same frozen A1 Group seed100 prediction, reference composition and alpha=0.2. Thus it is a controlled reproduction-context pilot, not an exact rerun of undocumented JH#7.

## Configuration and execution

- Site: rich LightGBM, `src/model.py::PARAMS`, `site_code` dropped, weight none, seed 7, two-year window.
- C0 objective: LightGBM default `regression` (L2).
- C1 objective: `regression_l1` through `pipeline.py --params`; verified by the parser→`json.loads`→`M.fit` parameter merge path.
- Group: frozen weekday seed100 predictions from `outputs/sm45/group_a1_2023.parquet` and `group_a1_2024.parquet`; no Group retraining.
- Composition: reference; blend: Site 80% + Group 20% through `sm39_group_site_integration.redistribute()`.
- Environment: `OIBC_CAL_MODE=weekday`, `OIBC_EXT_SOURCES=no_openmeteo`, GFS/GEFS/UM=0, `OIBC_SRC=prov`, spatial/physics=none, WX2/SM42 flags unset, `--ext none`.
- Training windows: `(2021-06-01 00:00, 2023-06-01 00:00]` for the 2023 validation and `(2022-06-01 00:00, 2024-06-01 00:00]` for the 2024 validation. Right-closed timestamp convention preserved.
- Runtime: Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6.

Actual C1 commands (PowerShell; environment above set before process start):

```powershell
.\.venv\Scripts\python.exe src\pipeline.py --mode val --fset rich --train-years 2 --weight none --ext none --params '{"random_state":7,"objective":"regression_l1"}' --drop-features site_code --tag sm47_l1_s7 --val-start 2023-06-01 --val-end 2024-06-01
.\.venv\Scripts\python.exe src\pipeline.py --mode val --fset rich --train-years 2 --weight none --ext none --params '{"random_state":7,"objective":"regression_l1"}' --drop-features site_code --tag sm47_l1_s7 --val-start 2024-06-01 --val-end 2025-06-01
```

C0 reused `outputs/val_sm45_a1_s7_2023_sites.parquet` and `outputs/val_sm45_a1_s7_sites.parquet`. Group predictions were reused from the two SM45 weekday Group Parquets. No evaluation actuals entered training.

## W and diagnostic results

W values are KRW. Identical reference composition, Group forecast, alpha and observed site-hour mask were used. `scoring.score()` and independent hourly penalties matched exactly at the displayed precision.

| Validation | Model | W | Δ vs C0 | G1 W | G2 W | 11–15 W | Off-peak W |
|---|---|---:|---:|---:|---:|---:|---:|
| 2023–24 | C0 L2 seed7 + Group100 | 107,004,183 | — | 79,672,945 | 27,331,238 | 89,237,001 | 17,767,183 |
| 2023–24 | C1 L1 seed7 + Group100 | 106,266,107 | −738,076 (−0.690%) | 79,661,281 | 26,604,826 | 88,395,300 | 17,870,807 |
| 2024–25 | C0 L2 seed7 + Group100 | 198,977,096 | — | 94,506,528 | 104,470,568 | 164,213,673 | 34,763,423 |
| 2024–25 | C1 L1 seed7 + Group100 | 202,920,302 | +3,943,206 (+1.982%) | 97,174,914 | 105,745,388 | 167,602,203 | 35,318,099 |

Site-level MAE improved in both periods, while that did not translate into stable settlement W:

| Period | C0 Site MAE | C1 Site MAE | C0 signed bias | C1 signed bias |
|---|---:|---:|---:|---:|
| 2023–24 | 4.9318 kWh | 4.8616 kWh | −0.1270 kWh | +0.0024 kWh |
| 2024–25 | 5.9681 kWh | 5.8340 kWh | −0.1252 kWh | +0.3502 kWh |

The 2023 L1 reduction came mainly from G2 (−726,412); G1 changed −11,664. Peak W improved by 841,701, while off-peak W worsened by 103,625. The 2024 L1 increase affected both groups (G1 +2,668,386; G2 +1,274,820); peak W worsened by 3,388,531 and off-peak by 554,676. January 2025 was the largest complete-month increase, +1,395,491 (+11.39%); April improved by 927,307 (−6.10%).

This explains why better Site MAE is insufficient: the settlement objective aggregates by group and weights errors by SMP and the peak-hour multiplier. C1's shift to positive Site bias in 2024 also coincided with larger group and peak penalties.

## Sequential stop-rule outcome

- Stage A (2023 seed7): improved, so proceed.
- Stage B (2024 seed7): worsened by 3.94M KRW; **stop**.
- 2024 paired bootstrap: not run because both annual single-seed W comparisons did not improve.
- Stage C L1 seeds21/42 and 3-seed comparison: not run.
- Submission-period fit, CSV generation and validator: not run because C1 failed the sequential performance gate.

The two existing SM46 candidates and SM41 originals were not written or modified. Their hashes were checked at start and remained protected. No model selection criterion was changed after results. The old JH#7 finding remains consistent with the caution against L1, while SM47 adds a current calendar-safe controlled observation.

## Artifact hashes and reproducibility

| Artifact | SHA256 |
|---|---|
| C0 2023 Site input | `c91a66367f06f42a00cc72b842d5eedca7b15ab9bc0566455141739a7148bc9b` |
| C1 2023 Site prediction | `cf24f5f8ab7b018203bb4942b43cf83a83c8aa211faa0b9a46bee73bd58eedf1` |
| C0 2024 Site input | `dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26` |
| C1 2024 Site prediction | `c4133cb677590ae4134009c83b47c3703fe698f00373fccad4d7e40d5ea7da70` |
| Frozen Group 2023 prediction | `22dc17b9581073a370a0dc4dd1d5fabcb75e281fd3a9b3fb4a76cf57f6052598` |
| Frozen Group 2024 prediction | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` |
| SM46 A1-REF forecast (protected) | `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` |
| SM46 A1-REF composition (protected) | `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` |
| SM46 A1-COMP forecast (protected) | `0cda37b9576e1fa35cf849cf11847414dc440ab2242598f33d2ab68fa75ddfa9` |
| SM46 A1-COMP composition (protected) | `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872` |

Stage W JSON and redistributed prediction Parquets are local, ignored artifacts in `outputs/sm47/`; the C1 Site validation Parquets are in `outputs/`. No raw data, prediction or submission CSV was committed. Existing GFS-related historical test failures were not run or changed.
