# SM#32 — FA1 / FA2 실제 LightGBM Ablation

## 설정

`OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, `rich + ext mean`, 2년 학습창, 참조 그룹, 기존 LightGBM 파라미터에 `random_state=7`을 고정했다. 모든 후보는 같은 GFS 부분 캐시, 발전소·시간 평가 행, 정산 함수를 사용했다. FS0는 105개, FA1은 101개, FA2는 104개 입력이다.

실행 예:

```powershell
$env:OIBC_EXT_SOURCES='no_openmeteo'; $env:OIBC_SPATIAL='none'; $env:OIBC_PHYSICS='none'
python src/pipeline.py --mode val --fset rich --ext mean --train-years 2 --params '{"random_state":7}' --tag sm32_fs0 --val-start 2023-06-01 --val-end 2024-06-01
python src/pipeline.py --mode val --fset rich --ext mean --train-years 2 --params '{"random_state":7}' --tag sm32_fa1 --val-start 2023-06-01 --val-end 2024-06-01 --drop-features ext_ghi_ens,ext_ghi_ens_dsum,ext_ghi_ens_lag1,ext_ghi_ens_lead1
python src/pipeline.py --mode val --fset rich --ext mean --train-years 2 --params '{"random_state":7}' --tag sm32_fa2 --val-start 2023-06-01 --val-end 2024-06-01 --drop-features wb_snow
```

The same three commands were run for 2024-06-01~2025-06-01 without the 2023 date arguments. Predictions are Git-ignored under `outputs/val_sm32_*`.

## W results

| Period | Model | Features | W (원) | ΔW vs FS0 | Change |
|---|---|---:|---:|---:|---:|
| 2023~24 | FS0 | 105 | 110,008,344 | — | — |
| 2023~24 | FA1 | 101 | 109,343,198 | -665,147 | -0.605% |
| 2023~24 | FA2 | 104 | 108,294,214 | -1,714,130 | -1.558% |
| 2024~25 | FS0 | 105 | 193,476,373 | — | — |
| 2024~25 | FA1 | 101 | 192,212,700 | -1,263,672 | -0.653% |
| 2024~25 | FA2 | 104 | 194,561,688 | +1,085,315 | +0.561% |

Official scoring first aggregates each prediction to G1/G2 at each timestamp and then applies the absolute-error penalty. No missing, negative, NaN, or infinite predictions were found; all candidates had identical observed evaluation rows (1,256,595 for 2023~24 and 2,170,645 for 2024~25).

## Midday and group effects

| Period | Model | 11~15 W (원) | G1 W (원) | G2 W (원) |
|---|---|---:|---:|---:|
| 2023~24 | FS0 | 91,647,874 | 84,584,375 | 25,423,969 |
| 2023~24 | FA1 | 90,821,154 | 83,960,348 | 25,382,850 |
| 2023~24 | FA2 | 89,823,605 | 83,215,283 | 25,078,932 |
| 2024~25 | FS0 | 159,672,125 | 91,567,579 | 101,908,794 |
| 2024~25 | FA1 | 158,810,696 | 90,879,079 | 101,333,621 |
| 2024~25 | FA2 | 160,981,629 | 91,904,523 | 102,657,165 |

FA1's improvement is shared by G1 and G2 in both periods. FA2 reduces both groups in 2023~24 but worsens both in 2024~25. Monthly FA1 changes range from -4.51% to +4.97% in 2023~24 and -6.02% to +1.76% in 2024~25. FA2 ranges from -3.54% to +0.59% and -1.67% to +3.83%, respectively. The worst month is below the pre-existing 5% monthly limit for FA2; FA1 has a 2023~24 September +4.97% month and 2024~25 June -6.02% improvement, but its inferential criterion still fails.

## Paired 7-day bootstrap

`ΔW = W(candidate) - W(FS0)`, with contiguous 7-day blocks and 10,000 resamples:

| Period | Candidate | 95% bootstrap interval (원) | 0 included |
|---|---|---:|---|
| 2023~24 | FA1 | [-2,589,529, +741,151] | Yes |
| 2023~24 | FA2 | [-3,397,369, -149,787] | No |
| 2024~25 | FA1 | [-3,045,043, +987,689] | Yes |
| 2024~25 | FA2 | [-1,087,386, +3,507,555] | Yes |

Improved versus worsened dates were FA1 49.18%/50.82% and FA2 53.83%/46.17% in 2023~24; FA1 55.07%/44.93% and FA2 51.51%/48.49% in 2024~25. The intervals are paired diagnostic uncertainty, not independent final-test confidence intervals; both years have been reused in earlier research.

## `site_code` coverage diagnostic

The diagnostic uses the same FS0 prediction files and classifies a site as seen when it has at least one generation row in the preceding two-year training window. It does not retrain.

| Period | Training site IDs | Evaluation site IDs | Unseen IDs | Unseen capacity share | Seen site MAE (kWh) | Unseen site MAE (kWh) |
|---|---:|---:|---:|---:|---:|---:|
| 2023~24 | 106 | 205 | 99 | 73.13% | 2.825 | 10.410 |
| 2024~25 | 205 | 253 | 48 | 22.25% | 5.534 | 7.011 |

The site-level weighted absolute error contribution is not the official group W because group errors can cancel. For 2023~24 it was 84.71M seen / 103.70M unseen; for 2024~25 it was 294.29M seen / 76.18M unseen. These values are diagnostic only. In 2023~24, the evaluation itself has only 205 sites, so the 99 absent IDs are sites without observed evaluation rows, while in 2024~25 all 253 sites are evaluated and 48 were unseen during training. This coverage shift makes `site_code` transfer a clear follow-up experiment, not evidence that FA1 or FA2 is superior.

## Decision

FA1: **보류**. It improves W in both periods, but both paired intervals include zero and the years are reused. It is a safe duplicate-removal candidate for a future fixed-seed ablation review, not an adopted model change.

FA2: **보류/기각 for adoption**. It improves 2023~24 with a negative interval but worsens 2024~25 and its interval includes zero. The variable's near-constant status alone is insufficient to remove it.

No FA3/FA4 or new candidate was added after seeing these results. The next independent experiment should isolate `site_code` handling and use a future, previously unused time window if available.
