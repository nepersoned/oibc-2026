# SM#31 — SM#30 C1 Feature Audit

## Scope and method

Audited the actual `rich + ext mean` C1 input produced by `F.rich_feats()` with `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, a two-year window, and the SM#30 LightGBM defaults. The measured training window is 2022-06-01 01:00 through 2024-06-01 00:00 KST; evaluation inputs are 2024-06-01 01:00 through 2025-06-01 00:00 KST. The model's fit filters to `elev > 0`: 963,460 training rows and 1,111,073 validation daylight rows (2,216,280 full prediction rows). The feature audit is in [`FEATURE_AUDIT_SM30.csv`](FEATURE_AUDIT_SM30.csv): 105 actual inputs, definitions and lineage, train/validation dtype, cardinality, missingness, quantiles, mode share, correlations, monthly mean range, and LightGBM gain/split.

One same-configuration reference fit was performed only to recover gain/split importance that SM#30 did not save. The original C1 booster was not retained, and `random_state` is not fixed in the existing LightGBM defaults, so this is a diagnostic repeat fit, not the exact original C1 model importance and not an importance-stability estimate. No ablation or new W experiment was run.

## Input groups and exact feature membership

| Group | Count | Feature names |
|---|---:|---|
| Forecast A | 27 | `wa_cloud`, `wa_cloud_d10`, `wa_cloud_daymean`, `wa_cloud_dmean`, `wa_cloud_lag1`, `wa_cloud_lag2`, `wa_cloud_lead1`, `wa_cloud_lead2`, `wa_cloud_r10`, `wa_ground_press`, `wa_humidity`, `wa_humidity_daymean`, `wa_humidity_dmean`, `wa_humidity_lag1`, `wa_humidity_lag2`, `wa_humidity_lead1`, `wa_humidity_lead2`, `wa_rain`, `wa_rain_daymean`, `wa_rain_dmean`, `wa_rain_lag1`, `wa_rain_lag2`, `wa_rain_lead1`, `wa_rain_lead2`, `wa_snow`, `wa_temp`, `wa_wind_speed` |
| Forecast B | 49 | `wb_ceiling`, `wb_ceiling_daymean`, `wb_ceiling_dmean`, `wb_ceiling_lag1`, `wb_ceiling_lag2`, `wb_ceiling_lead1`, `wb_ceiling_lead2`, `wb_cloud`, `wb_cloud_d10`, `wb_cloud_daymean`, `wb_cloud_dmean`, `wb_cloud_lag1`, `wb_cloud_lag2`, `wb_cloud_lead1`, `wb_cloud_lead2`, `wb_cloud_r10`, `wb_dew_point`, `wb_precip_prob`, `wb_precip_prob_d10`, `wb_precip_prob_daymean`, `wb_precip_prob_dmean`, `wb_precip_prob_lag1`, `wb_precip_prob_lag2`, `wb_precip_prob_lead1`, `wb_precip_prob_lead2`, `wb_precip_prob_r10`, `wb_rain_prob`, `wb_rel_hum`, `wb_snow`, `wb_snow_prob`, `wb_temp`, `wb_total_liq`, `wb_uv_idx`, `wb_uv_idx_d10`, `wb_uv_idx_daymean`, `wb_uv_idx_dmean`, `wb_uv_idx_lag1`, `wb_uv_idx_lag2`, `wb_uv_idx_lead1`, `wb_uv_idx_lead2`, `wb_uv_idx_r10`, `wb_vis`, `wb_vis_daymean`, `wb_vis_dmean`, `wb_vis_lag1`, `wb_vis_lag2`, `wb_vis_lead1`, `wb_vis_lead2`, `wb_wind_speed` |
| NOAA GFS external | 10 | `ext_gfs_ghi`, `ext_gfs_ghi_dsum`, `ext_gfs_ghi_lag1`, `ext_gfs_ghi_lead1`, `ext_gfs_kcs`, `ext_gfs_tcc`, `ext_ghi_ens`, `ext_ghi_ens_dsum`, `ext_ghi_ens_lag1`, `ext_ghi_ens_lead1` |
| National forecast means | 4 | `reg_wa_cloud`, `reg_wb_cloud`, `reg_wb_precip_prob`, `reg_wb_uv_idx` |
| Solar/time | 7 | `azim`, `cosz`, `doy_cos`, `doy_sin`, `elev`, `ghi_cs`, `hour` |
| Site static | 4 | `cap`, `lat`, `lon`, `site_code` |
| Calendar | 4 | `dow`, `is_hol`, `is_off`, `off_run` |
| **Total** | **105** | |

Forecast A/B raw variables and their round-10, target-day lag/lead and context means are generated in `prep_forecast()`. `reg_*` are same-valid-time means over forecast stations. Solar geometry and clear-sky proxy are deterministic from timestamp and the provided anonymized site coordinates; those coordinates are not used to select external weather grid cells. `ext_gfs_ghi` is GFS fixed-box DSWRF-derived hourly irradiance; `ext_gfs_kcs` is its clear-sky normalization and `ext_gfs_tcc` is cloud cover. The target-day `*_dsum` is a sum of same-run hourly forecast values, not a measured daily irradiation target.

## Findings

### Data lineage, timing, and leakage

- All 105 rows in the audit CSV have `openmeteo_dependency=false`. For C1, `ext_ghi_ens` is recomputed from the sole available GFS source, so it is an exact duplicate of `ext_gfs_ghi`; no Open-Meteo data is read. GEFS and LDAPS files were not present in this execution environment and are not C1 inputs.
- Forecast A/B `round=17` is preferred and falls back to `round=10`; the supplied dataset README describes both as issued the day before the target date and available by the 17:00 KST deadline. The `lag`/`lead`, daily means and sums are generated within `target_day()` using that issued forecast's valid times. A `lead` name therefore refers to a later *forecast valid time*, not future observed weather. No generation or SMP columns are in `rich_feats()`; SMP is loaded for training/settlement, but C1 uses `weight=none` and it is not a model input.
- No direct future-label leakage or coordinate-based external grid selection was found in this code path. NOAA archive publication timestamps and commercial reuse terms are not proven for the full historical data; classify this C1 as research-only pending those checks.
- `site_code` is a category, not an ordinal physical measurement. It has 205 unique values in daylight training rows versus 253 in validation inputs. Thus 48 site IDs are absent from the training feature matrix; the high `site_code` gain (16,134; split 13,395) must not be interpreted as reliable transfer to unseen sites. The capacity mean shifts by 0.333 training SD, consistent with the training target rows covering a different set of operating/observed sites than the full validation grid.

### Missingness and temporal coverage

All comparisons below use daylight rows, matching `model.fit()` and nonzero prediction hours. No feature is completely missing or constant. `ext_gfs_ghi`/`ext_ghi_ens` missingness is 1.75% train and 1.84% validation; GFS lag1 is 1.32% / 1.43%; `ext_gfs_kcs` is 1.98% / 2.05%. Other raw forecast missingness is at most 0.077% in training and zero in validation. Two-hour `lag2`/`lead2` columns are missing on 8.33% of validation daylight rows and one-hour context columns on 4.17%; this is the deliberate target-day boundary behavior (`groupby(..., tday).shift`) rather than an absent forecast source. Preserve that distinction.

`wa_snow` has modal value 0 on 99.69% of training daylight rows and gain 5.87 / split 10. `wb_snow` has modal value 0 on 99.885%, gain 0 / split 0. These are the only near-constant inputs at a 99.5% mode-share threshold. They are candidates for ablation, not automatic removals.

Training-to-validation mean shifts are modest for weather inputs after matching daylight. The largest shift is fixed `cap` (+0.333 SD), then `wa_snow` (+0.239 SD) and surface pressure (-0.170 SD). Monthly mean ranges are expected to be large for seasonal variables (`doy_sin`/`doy_cos` about 2.71 training SD across the validation year); this is expected seasonality, not leakage. The CSV carries per-period monthly mean ranges and train/evaluation means for checking other changes.

### Correlation, source duplication, and importance

Exact duplicate pairs in C1 are:

- `ext_gfs_ghi` / `ext_ghi_ens` (Pearson r=1.0), with the same duplication for their `_dsum`, `_lag1`, and `_lead1` variants.

Other high correlations (absolute Pearson r ≥0.98 on daylight training rows) include `ghi_cs`/`cosz` (0.9997), `wb_precip_prob`/`wb_rain_prob` (0.9949), `wb_uv_idx_dmean`/`wb_uv_idx_daymean` (0.9976), `elev`/`ghi_cs` (0.9922), `elev`/`cosz` (0.9910), `wa_temp`/`wb_temp` (0.9854), and `wb_uv_idx`/`wb_uv_idx_r10` (0.9817). These do not prove interchangeability; the solar features have different formulas and humidity/forecast providers can contain distinct error information.

Largest diagnostic repeat-fit gains were `ext_gfs_ghi` 238,272; `ext_ghi_ens` 67,889 (the same underlying signal); `site_code` 16,134; `wa_humidity_lead1` 11,203; `ext_gfs_ghi_lead1` 9,009; and `ext_gfs_ghi_dsum` 4,980. `site_code` has the most splits (13,395). `wb_snow` has zero gain and splits. Gain across correlated inputs is shared/unstable, and the fitted booster was not saved, so these figures are screening evidence only, not a stability result.

## Immediate handling (A)

No proven illegal or leaked variable was found in the C1 input. Do not claim NOAA submission eligibility until full-period license and release-time evidence are obtained. Keep prediction-time GFS coverage/missingness explicit. Treat `site_code`'s unseen validation categories and train/validation site coverage mismatch as a generalization issue requiring evaluation, not as a reason to remove the feature without a controlled test. Do not remove `ghi_cs`, `cosz`, or `elev` based on correlation alone.

## Frozen Group Ablation candidates (B)

These four candidates were selected from source identity, training-only importance/missingness, and training-only correlation. No candidate-specific validation W was examined or used to select this list. Freeze this list before running any ablation:

| ID | Exact removal set | Rationale and hypothesis | Failure mode |
|---|---|---|---|
| FA1 `gfs_ens_alias` | `ext_ghi_ens`, `ext_ghi_ens_dsum`, `ext_ghi_ens_lag1`, `ext_ghi_ens_lead1` | Remove four mathematically exact GFS aliases while retaining original `ext_gfs_*`; may reduce duplicate split competition without losing information. | LightGBM's tree choices can change and alias columns may accidentally be the preferred split representation; W can worsen. |
| FA2 `wb_snow_only` | `wb_snow` | It is constant-zero 99.885% of training daylight rows and has zero gain/splits. | Rare snowfall episodes may matter for panel losses or albedo; the validation year can contain events absent from training. |
| FA3 `wb_visibility_context` | `wb_vis_lag1`, `wb_vis_lag2`, `wb_vis_lead1`, `wb_vis_lead2` | Four low-gain temporal context features; removing them avoids weak day-boundary values and reduces input complexity while retaining current `wb_vis` and day means. | Future-valid-time forecast context may reveal cloud/aerosol persistence not captured by other variables. |
| FA4 `wb_rain_prob_alias` | `wb_rain_prob` | Strong train correlation with `wb_precip_prob` (r=0.9949); retain the slightly more important general precipitation probability. | Rain probability can differ from total precipitation probability and help during convective events. |

For each frozen candidate, compare A0 (all 105 columns) with the corresponding deletion using the same GFS-only 2-year rich LightGBM, training cutoff, site rows, fixed seed (`random_state=7`), reference composition and official local W. Re-run each A0 control with the same pinned seed because historical SM#30 did not pin a seed. Evaluate 2023-06-01~2024-06-01 and 2024-06-01~2025-06-01, with paired 7-day bootstrap on daily W, 11~15 W and monthly W. These validation years have been reused in prior research; results are not an independent final test. Do not change the candidate definitions after viewing their W.

Run (PowerShell; exact columns are provided to the new `--drop-features` option):

```powershell
$env:OIBC_EXT_SOURCES = 'no_openmeteo'
$env:OIBC_SPATIAL = 'none'
$env:OIBC_PHYSICS = 'none'
python src/pipeline.py --mode val --fset rich --ext mean --train-years 2 --params '{"random_state":7}' --tag sm32_FA1_2023 --val-start 2023-06-01 --val-end 2024-06-01 --drop-features ext_ghi_ens,ext_ghi_ens_dsum,ext_ghi_ens_lag1,ext_ghi_ens_lead1
python src/pipeline.py --mode val --fset rich --ext mean --train-years 2 --params '{"random_state":7}' --tag sm32_FA1_2024 --val-start 2024-06-01 --val-end 2025-06-01 --drop-features ext_ghi_ens,ext_ghi_ens_dsum,ext_ghi_ens_lag1,ext_ghi_ens_lead1
```

Replace `--drop-features` with the exact removal set from the table for FA2–FA4; run matching A0 controls if baseline predictions were not generated by the identical current code and settings.

## Reproduction

```powershell
$env:OIBC_EXT_SOURCES = 'no_openmeteo'
$env:OIBC_SPATIAL = 'none'
$env:OIBC_PHYSICS = 'none'
python src/analysis/feature_audit_sm30.py --start 2024-06-01 --end 2025-06-01 --train-years 2
```

The audit script does one reference fit solely for importance and writes aggregate feature-level metadata; it does not save a model or predictions.
