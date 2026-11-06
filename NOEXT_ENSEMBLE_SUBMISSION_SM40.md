# SM#40 — Submission-ready Noext Group–Site Ensemble

## 산출 요약

SM#39에서 2023~24로 고정 선택한 alpha 0.2를 사용해 2025-06-01 01:00~2026-06-01 00:00 KST 제출 후보를 만들었다. 실제 제출 평가 기간 발전량은 없으므로 제출기간 W나 정산수익 개선은 산출·추정하지 않았다. 대회 포털에는 업로드하지 않았다.

| 산출물 | 행 수 | SHA256 |
|---|---:|---|
| `submissions/composition_sm40_noext_ensemble.csv` | 253 | `374A7E01ADF59D0724741121CEEA09D434416530358107A6F62931471331DCFD` |
| `submissions/forecast_sm40_noext_ensemble.csv` | 17,520 | `C3ECF25CA0BF03EA90710D99F8A7B1935B144929F5980600355311FAB4DE2892` |

공식 `src/validate_submission.py` 종료 코드는 **0**이다. 253개 발전소, G1/G2 용량 각 20MW 이상, 8,760개 시각, 그룹별 8,760행, KST 타임존, 음수·NaN·Inf 및 중복/누락이 없음을 검사했다. 실제 업로드는 하지 않았다.

## 학습 및 추론 설정

승인된 Python 3.11.15 실행기와 pandas 3.1.1, numpy, pyarrow, LightGBM 4.7.0을 사용했다. 환경은 `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, `OIBC_SRC=prov`, `OIBC_CAL=1`, `OIBC_WX2` unset이었다. 두 모델 모두 외부 기상 입력을 끄고 대회 제공 WA/WB 예보와 시간·태양 위치/달력 피처만 사용했다.

사이트 모델 실제 실행:

```powershell
python src/pipeline.py --mode submit --fset rich --train-years 2 --ext none --drop-features site_code --params '{"random_state":7}' --tag sm40_site_noext
```

학습은 3,427,240행, 94개 입력 피처였다. 출력은 `outputs/test_sm40_site_noext_sites.parquet`이며 전체 2,216,280개 site-hour를 포함한다. `site_code`를 빼고 `cap`, `lat`, `lon`은 기존 rich feature set에서 유지했다. 구성은 reference composition이다.

그룹 모델 실제 실행:

```powershell
python src/agg_model.py --mode submit --train-years 2 --ext none --out outputs/sm40/group_test.parquet
```

기존 LightGBM CF 설정과 effective seed 100을 사용했다. 모델은 302개 입력 피처, 태양고도 필터 적용 후 15,174개 학습 행을 사용했다. `min_cov=0.3`을 통과한 CF 타깃은 G1 17,544행, G2 11,649행이며 양 그룹 모두 타깃이 존재했다. 이 타깃의 평균 관측용량 커버리지는 G1 86.53%, G2 80.64%였다. 고정 그룹 총용량은 G1 20,465.655kW, G2 22,189.715kW다.

그룹 학습 발전량은 2023-06-01 01:00~2025-06-01 00:00 KST이며 제출 첫 시각보다 앞선 자료만 사용했다. 학습 타깃은 기존 `targets()` 정의에 따라 관측 발전량/관측 용량 CF이고, 제출 추론은 `cf_hat × reference group fixed capacity`로 kWh를 산출했다. 이 훈련 분모와 추론 분모 차이는 남은 한계다.

## alpha=0.2 결합 검증

검증 및 제출 조립에 동일한 `src/analysis/sm39_group_site_integration.py::redistribute()`를 재사용했다. 사이트 모델 그룹합을 B, 고정용량 그룹 예측을 T라 하고 제출 group forecast는 `F = 0.8 B + 0.2 T`로 생성했다. B가 양수면 사이트별 예측을 비례 조정하고, B가 0이면 고정 사이트 설비용량 비율로 T를 배분했다. 전체 발전소를 사용했으며 과거 검증의 관측 발전소 마스크는 제출에 적용하지 않았다.

- alpha=0은 기존 사이트-only pipeline의 `forecast_sm40_site_noext.csv` 집계와 정확히 일치했다.
- alpha=1의 기준 그룹합은 `group_test.parquet`의 고정용량 pred와 일치했다.
- alpha=0.2의 재배분 사이트 합은 각 그룹·시각에서 0.8B+0.2T와 일치했다. 최대 부동소수점 차이는 `7.28e-12` kWh였다.
- 최종 forecast CSV 저장 후 재로드 값 차이는 0이었다.
- 제출 시간축은 test `smp.csv`의 8,760시각, 2025-06-01 01:00~2026-06-01 00:00 KST와 일치했다.

파일 크기와 SHA256은 `outputs/sm40/submission_manifest.json`에 입력·출력별로 기록했다. 주요 Parquet SHA256:

| 파일 | SHA256 |
|---|---|
| `outputs/test_sm40_site_noext_sites.parquet` | `6D045E8F2DC34EB9E6D9DCB4F1F0183670620D3BB54F758CAADD2E87043D48F4` |
| `outputs/sm40/group_test.parquet` | `9136D392CEFEFC9543237C6827E13E6F565B97AA089E092F222A744978B83C77` |
| `outputs/sm40/ensemble_test.parquet` | `672D1B58346657ECD009C918A7205E6E03F7ACEBE6AAE517710FF4FA0195C03A` |

## 데이터 규정과 예측시점 점검

`forecast_wa`와 `forecast_wb`만 외부 기상 입력으로 사용했다. 대회 제공 데이터 README는 round 10/17을 대상일 전날 10시/17시 발행 예보로 정의하고 두 라운드 모두 전날 17:00 마감 이전이라고 안내한다. 기존 `prep_forecast()`는 round 17을 우선하고 비어 있는 값은 round 10으로 보충한다. Parquet에는 각 행의 별도 실제 공개 timestamp가 없어 공개시각 검증은 제공된 round 정의에 의존한다.

Open-Meteo, NOAA GFS/GEFS, LDAPS, 사후 관측 기상, 제출기간 실적 및 사후 관측용량은 사용하지 않았다. `submission_manifest.json`에는 사용한 데이터 파일과 최종 산출물 SHA256, 환경·학습 설정, validator 종료 코드가 저장돼 있다.

## SM#39 W 결과의 적용 한계

SM#39에서 alpha=0.2는 2023~24 W로 선택됐고, 고정 적용한 2024~25 W는 201,164,873원에서 198,736,384원으로 1.207% 감소했다. 7일 paired bootstrap 95% CI는 [-4,299,695,-445,862]원이었다. 해당 과거 검증 결과는 제출기간 실제 W가 아니며 여기서는 제출기간 성능으로 주장하지 않는다. 2023 학습창에는 G2의 `min_cov=0.3` 통과 라벨이 없었다는 학습 이력 한계도 SM#39 기록대로 유지한다.

## 이전 GFS 테스트 실패 조사

SM#39 전체 테스트에서 보고된 네 실패는 GFS 관련이었다. SM#39 부모 커밋(`749ed23`)과 그 직전 커밋 사이에서 `fetch_gfs.py`, `export_gfs_partial.py`, `partial_gfs_runner.py`, 관련 테스트가 변경되지 않았음을 확인했다. SM#40에서도 이 코드들은 변경하지 않았다.

SM#40 환경의 `OIBC_EXT_SOURCES=legacy`에서 네 실패 테스트를 다시 분리 실행했을 때 `test_partial_gfs_runner::test_matches_original_feature_loader_when_same_data`는 통과했다. SM#39 전체 실행 환경은 `no_openmeteo`여서 이 테스트의 legacy Open-Meteo fixture를 무시한 환경 차이가 있었다. 나머지 세 실패는 재현됐다.

- `test_export_gfs_partial` 2건은 `export_gfs_partial.py`의 부분 grid 크기 검사에서 실패했다. 임시 1~2일 캐시를 둔 테스트인데 `fetch_gfs.build_hourly()`가 기본 전체 기간 날짜 범위를 생성해 `len(sources)*24`와 맞지 않는다.
- `test_gfs_time_conversion::test_build_hourly_synthetic_day`도 같은 기본 날짜 범위 문제로 24행 대신 전체 기간 행을 반환했다.

이는 SM#39/40 변경 파일과 무관한 기존 GFS 테스트/구현 문제로 분류했다. 본 제출 후보와 무관하므로 GFS 코드를 수정하지 않았다.

## Git 및 제출 상태

코드와 이 보고서는 `seongmin`에만 커밋·push한다. `outputs/`와 `submissions/`는 `.gitignore` 상태로 유지한다. 팀 최고 `ens_v3`와의 제출기간 점수 비교는 평가 정답이 없으므로 하지 않았다. 자동 포털 업로드도 하지 않았다.
