# SM42 공식 기준선 재현

## 출처와 실행 범위

공식 참가자 패키지 `data/handover 2/01_participant_dataset/baseline.py` 원본은 실제 존재한다. SHA256 `ab2a5752aa2df07cd0414acb53959a1956a8a261a3858324e9216cff268a2a02`. README와 원본은 reference composition 및 제공 WA/WB의 두 round별 site LightGBM을 정의한다. 원본 main은 제출기간으로 고정되어 있으므로 2023/2024 평가에 그대로 실행하면 미래 라벨이 섞인다. `src/analysis/sm42_official_baseline.py`는 원본 `features()`·`solar()`·컬럼을 import하고 같은 LightGBM 파라미터·float32를 적용하되 각각의 학습과 예측 기간만 과거로 옮긴 시간순 adapter다. 원본 파일은 수정하지 않았다.

별도의 2026 온라인 설명회 슬라이드는 로컬 자료에서 발견하지 못했다. [대회 안내](https://dataen.ai/challenge)의 설명회 동영상 링크는 확인했으나 동영상 내용을 가져오지 못했으므로 슬라이드와 코드의 일치 여부는 미확인이다. 예제 제출 CSV는 패키지에 없고 `baseline.py`가 생성한다. 대회 원본은 W 대신 제출파일을 생성하며 W는 같은 `src/scoring.py`로 계산했다. 본 채점은 과거에 실측이 있는 site-hour만 예측·실적을 합산하므로 완전 관측 제출기간 점수와 마스크가 다르다.

## 설정과 JH#1 차이

공식 입력은 WA cloud/temp/humidity/rain/wind speed/pressure 6개, WB cloud/temp/humidity/UV/precip probability/total liquid/visibility/wind speed/dew point 9개, elev/azim/cosz/doy sin·cos/hour/cap/lat/lon 9개, 합계 24개다. midpoint 태양기하·음수 예측 0·야간 0·CF 목표 [0,1.2] clip; 두 라운드에 각각 모델 학습 후 사이트별 산술 평균; G1/G2는 sites의 current_group. 600 trees, learning_rate .06, leaves 127, min_child_samples 200, subsample .8/freq 1, colsample .8, 기본 LGBM 회귀 objective 및 random_state 기본값이다. 실측 기상·외부 예보를 사용하지 않는다.

JH#1 기록은 공식 baseline 재현이라는 설명은 있으나 당시의 정확한 코드·환경은 확인되지 않았다. 현재 `src/model.py`는 공식 원본과 달리 X를 명시적으로 float32로 만들지 않으며, 과거 SM4는 그 버전에서 Python 3.12.14 / pandas 2.3.3 등을 사용했다. 원본 함수의 이번 실제 2023 W=123,998,095.54, 2024 W=224,547,459.98원이다. 이전 JH#1 표의 123,997,939 / 224,547,074원과 각각 +156.54 / +385.98원 차이. 2024 수치는 기존 float32 실험 기록 224,547,460원에 일치한다. 비-float32 SM4는 123,997,939 / 224,680,215원으로 별도 표시한다. dtype, 라이브러리 버전 및 초기 seed 설정 차이는 확인했으나 당시 환경 미상으로 남은 차이의 원인을 확정할 수 없다.

재현 명령(승인된 Python 3.11.15; PYTHONPATH `.venv/Lib/site-packages`):

```
python src/analysis/sm42_official_baseline.py --year 2023
python src/analysis/sm42_official_baseline.py --year 2024
python src/analysis/sm42_benchmark.py
```

환경 numpy 2.4.6, pandas 3.1.1, pyarrow 26.0.1, LightGBM 4.7.0. 입력·출력·adapter SHA256, 기간 및 실행시각은 `outputs/sm42/baseline_reproduction.json`과 각 연도 manifest에 있다. 원본 데이터·결과 예측을 외부 서비스에 전송하지 않았다.

## 동일 조건 벤치마크

모든 모델은 같은 reference 구성, 실제 관측 행, SMP 및 k, 평가 시간과 `scoring.py` W를 사용했다. 2023 관측 site-hours 1,256,595 / 8,784시간, 2024 2,170,645 / 8,760시간이다. W(원):

| 모델 | 2023 | 2024 | 2024 공식 대비 | 2024 SM41 대비 |
|---|---:|---:|---:|---:|
| 공식 코드 시간순 adapter | 123,998,096 | 224,547,460 | 기준 | +13.675% |
| JH#1 스타일 SM4 (기존 비-float32) | 123,997,939 | 224,680,215 | +0.059% | +13.742% |
| SM40 | 107,551,309 | 198,736,384 | -11.495% | +0.609% |
| SM41 | 106,754,876 | 197,534,279 | -12.030% | 기준 |
| SM42 F4 seed7 | 108,031,063 | Not Run | Not Run | Not Run |
| SM42 F3 seed7 | 106,535,683 | 197,257,247 | -12.153% | -0.140% |
| SM42 F3 3-seed | 106,949,376 | 196,517,774 | -12.483% | -0.515% |

F4는 2023 선택 기준에 미달해 이후 연도·다중시드는 사전등록대로 진행하지 않았다. SM41의 2024 group G1/G2 W 93,807,603 / 103,726,676원, 공식은 106,675,294 / 117,872,166원. 2024 공식/SM41의 11–15시 W 185,460,634 / 163,021,141원, 사이트 MAE 6.194 / 5.917 kWh, 그룹 MAE 433.743 / 382.505 kWh, 사이트 signed bias -0.215 / -0.050 kWh, 그룹 signed bias -26.621 / -6.247 kWh다. 월별, 그룹별, 11–15시, bias 및 기상 regime 수치는 `outputs/sm42/baseline_comparison.csv`, `monthly_comparison.csv`, `benchmark_diagnostics.json`에 남겼다. 기상별 MAE는 야간을 포함한 기술통계이며 전국 WA 구름 forecast 기반 상태의 크기·계절이 다르므로 인과적 설명이 아니다.

## 피처 차이 해석

SM41은 공식 24개 공통 원본 및 태양기하 외 예보 round17 우선 보충, round10·revision, 같은 발행분의 lag/lead·일/주간 평균, 전국 평균, Haurwitz clear-sky GHI, 달력을 추가한다. 공식은 별도 round 모델 평균, float32 입력과 site-only를 사용하고 SM41은 rich 3 seed 평균과 그룹 예측 20% 결합이다. 공식 원본에서만 쓰는 독립 원본 기상변수는 확인되지 않았다. 날짜·자료·구성을 맞췄어도 피처, 라운드 처리, 앙상블과 모델 설정이 함께 달라 전체 W 차이를 특정 피처의 인과효과로 돌릴 수 없다.
