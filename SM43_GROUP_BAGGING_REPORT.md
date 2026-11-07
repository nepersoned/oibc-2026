# SM#43 Group LightGBM Multi-Seed Bagging

## Decision

**Retain SM#41. Do not generate or upload an SM#43 submission candidate.** The five-seed Group model reduced point-estimate settlement W in both historical windows, but the 2024 paired 7-day moving-block bootstrap 95% interval for `SM43 − SM41` is `[-283,242, +209,236]` KRW and includes zero. The preregistered uncertainty requirement therefore fails. No alpha, seed set, feature, target, training-window, or group assignment was retuned after seeing these results.

## Executed experiment

- Site prediction fixed to the arithmetic mean of SM#41 Site LightGBM seeds 7, 21, and 42. No Site model was retrained.
- Group control: existing SM#39 prediction, LightGBM seed 100, 2-year window, min coverage 0.3.
- Group treatment: five LightGBM fits with `random_state=100..104`, arithmetic mean, same `PARAMS`, features, CF target, 2-year windows, and min coverage 0.3.
- Composition: reference/current-group; blend alpha 0.2.
- Inputs: participant WA/WB forecasts, site metadata, training generation, SMP, timestamps and derived solar/calendar features. `--ext none`; `OIBC_SRC=prov`; GFS/GEFS/UM, spatial, physics, WX2, and SM42 feature flags disabled. Existing `OIBC_CAL=1` behavior was retained for comparability. Its use of the installed `holidays` package/manual holiday list is not a determination that such calendar information is allowed under the competition rule; a calendar-off ablation was outside this group-only experiment.
- Environment: Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6, pyarrow 26.0.1.
- Commands (PowerShell; run from repository root; environment variables above set):

```powershell
.\.venv\Scripts\python.exe src\agg_model.py --mode val --train-years 2 --ext none --min-cov 0.3 --params '{"seeds":5}' --val-start 2023-06-01 --val-end 2024-06-01 --out outputs\sm43\group_pred_2023.parquet
.\.venv\Scripts\python.exe src\agg_model.py --mode val --train-years 2 --ext none --min-cov 0.3 --params '{"seeds":5}' --val-start 2024-06-01 --val-end 2025-06-01 --out outputs\sm43\group_pred_2024.parquet
.\.venv\Scripts\python.exe src\analysis\sm43_group_bagging.py
```

An initial 2023 attempt trained but could not save because `outputs/sm43` did not exist. The directory was created and the five-seed run repeated successfully. A call through system `python` also failed because that interpreter lacked LightGBM; all completed runs used repository `.venv`.

## W results

All rows below use the same reference composition, observed site-hour mask, SMP, peak-hour multiplier, and W implementation. SM41 control W reproduced to sub-cent precision. The independent group-hour penalty implementation matched `src/scoring.py` within `1e-5` KRW.

| Model | 2023–24 W (KRW) | 2024–25 W (KRW) | Δ vs SM41 2023 | Δ vs SM41 2024 |
|---|---:|---:|---:|---:|
| Official baseline (SM42 temporal reproduction) | 123,998,096 | 224,547,460 | +17,243,220 | +27,013,181 |
| SM40 Site1 + Group1 | 107,551,309 | 198,736,384 | — | — |
| SM41 Site3 + Group1 | 106,754,876 | 197,534,279 | baseline | baseline |
| SM43 Site3 + Group5 | 106,739,743 | 197,493,336 | **−15,133 (−0.0142%)** | **−40,943 (−0.0207%)** |

The official baseline values are from the executed, time-forward official-code adapter documented in `SM42_OFFICIAL_BASELINE_REPRODUCTION.md`; it was not rerun for SM43. SM40 values are historical same-window scores. SM43's comparison against SM41 is the paired controlled experiment.

| Diagnostic | 2023–24 | 2024–25 |
|---|---:|---:|
| SM41 → SM43 11:00–15:00 W change | +1,065 (worse) | −45,248 (better) |
| SM43 G1 W change | −7,862 | −57,291 |
| SM43 G2 W change | −7,271 | +16,348 |
| Worst complete-month W increase | +0.457% | +0.228% |
| Paired bootstrap CI for ΔW | not preregistered for selection year | [−283,242, +209,236] KRW |

The point estimate improved in 6 of 12 complete months in 2023–24 and 7 of 12 in 2024–25; worst relative month increase was below 5% in both. The bootstrap is paired by hourly aggregate penalties, with 168-hour moving blocks, 5,000 replicates and seed 7. It quantifies sampling variability conditional on these reused validation years; it does not remove model/feature selection bias.

## Group forecast stability and CF target audit

| Window | Mean absolute Group forecast change (kWh) | Prediction correlation | Error correlation | Mean signed Group error, seed100 → five-seed (kWh) |
|---|---:|---:|---:|---:|
| 2023–24 | 53.40 | 0.99976 | 0.99945 | 1,650.06 → 1,644.09 |
| 2024–25 | 48.27 | 0.99982 | 0.99599 | 149.74 → 149.70 |

The five-seed forecast is extremely close to seed 100; the marginal W gains are small relative to total W.

Training target remains `CF = sum(reporting-site generation) / sum(reporting-site capacity)`. Inference remains `predicted CF × fixed full reference-group capacity`. This training/inference coverage mismatch was diagnosed, not modified:

- 2023 training window: G1 had 3,562 eligible group-hour labels with mean capacity coverage 36.33%; G2 had no eligible labels. The G2 model therefore has no valid training labels in this window, a known weakness of 2023 validation.
- 2024 training window: G1 had 12,346 rows (mean coverage 62.85%); G2 had 2,889 rows (42.50%).
- CF labels are sparse/zero-heavy: median CF was 0.00584 (2023 G1), and 0.00598 / 0.01064 (2024 G1/G2), while their means were 0.1683 / 0.1552 / 0.1724. The estimator learns a reporting-capacity CF but scales by full group capacity at inference. Evaluation-time observed capacity was not used to adjust candidate forecasts.

## Controls, integrity, and deliverables

- No new feature family, loss, CF target, composition, alpha, or training window was changed.
- No external meteorological source was loaded. Calendar legality remains an explicit unresolved rules audit, inherited from SM41.
- The SM41 full-period forecast and composition were not modified; their protected hashes must remain `ed9d14e194259971802ef1e1530f0bd38b05455cf3ca66a7815abaedbd63fd8d` and `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` respectively.
- Since the preregistered adoption criteria failed, no SM43 submission-period Group training, CSV generation, or validator run was warranted. SM41 remains the only recommended candidate; portal upload was not performed.
- Detailed hourly/site predictions, group predictions, per-month metrics, bootstrap results, and input/output hashes are kept under ignored `outputs/sm43/`.
- Added `src/analysis/sm43_group_bagging.py` for reproducible averaging, full site-grid redistribution, independent-vs-official scoring cross-checks, bootstrap, and CF audit. Added unit tests for keyed averaging and fixed-alpha redistribution conservation.

## Limitations

The 2023 validation year has no G2 Group training labels and low G1 reporting coverage. The 2024 validation year has been reused across prior experiments. Thus the modest two-window point-estimate gains are not evidence of a robust general improvement, consistent with the wide paired bootstrap interval. The Group feature/target structure is unchanged, so this experiment tests bagging only, not target adequacy.
