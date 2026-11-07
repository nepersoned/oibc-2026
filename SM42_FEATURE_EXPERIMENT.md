# SM42 feature experiment

SM42의 사전등록은 `SM42_PREREGISTRATION.md`, 코드 `src/analysis/sm42_features.py`의 기본 mode `none`이다. F3/F4만 opt-in이며 SM40/41 기존 실행에 개입하지 않는다. 외부 기상, 미래 실측·발전량, 좌표 복원은 없다. 라운드는 공식 설명의 전일 발행 시각을 사용한다. 예보 행별 실제 발행 timestamp는 없어 공지에 의존한다.

| family | 이름 | 식 / 단위 | 기존 정보와 관계 |
|---|---|---|---|
| F4 | sm42_wa_cloud_std, sm42_wb_cloud_std | 각 시각·기관별 전체 관측지점 구름량의 표본 표준편차 ddof=1, %p | 기존 전국 평균 외 산포; 한 지점이면 NaN |
| F4 | sm42_wa_cloud_p90_p10, sm42_wb_cloud_p90_p10 | 각 기관 같은 시각 cloud의 90분위−10분위, %p | 분포 폭; 한 지점이면 0 |
| F3 | sm42_wa_cloud_revision_abs, sm42_wb_cloud_revision_abs | abs(round17−round10), %p | 기존 signed d10의 결정적 변환, 원본 d10 유지; 결측 시 NaN |
| F3 | sm42_wa_wb_cloud_disagreement | abs(17 우선/10 보충 WA−WB), %p | 같은 발전소의 각 연결 관측지점 예보 차이. 두 기관 모두 %지만 공간적 대표성은 다름 |

F4의 원천은 대회 제공 예보 관측지점이며 기존 NOAA GFS 공간 실험과 다르다. 분포는 동일 유효시간 예보만 사용한다. train 2023/2024 시간별 유효 관측지점 수는 각각 WA 61, WB 73; test도 round17 우선 및 round10 보충 후 해당 수였다. 이 개수는 raw round별 결측이 없다는 뜻은 아니다. F4 4개는 시간 단위 집계에서 2023/2024 train과 test 연도별 NaN 0%다. F3는 발전소-시간 격자 기준 train 2023 WA/WB revision 결측 0.0116%/0.2626%, train 2024 각각 0%; test 2026 WA revision 0.1156%, WB 0%, 기관 간 차이 0%. 원본에 없는 양 라운드를 0으로 채우지 않는다. 구체적 연도별 분위수 및 station count는 `outputs/sm42/feature_audit.json`에 있다. 이 감사의 역년은 검증창의 6월 경계와 다르다.

train 2023/2024 WA spatial std 중앙값 15.87/16.90%p, WB 17.30/16.78%p; test 2025/2026 WA 19.80/15.46, WB 21.98/16.35다. WB revision 평균은 train 2023 3.06, train 2024 2.60, train 2025 일부 9.72, test 2025 일부 12.77%p로 분포가 달라 추가 조사가 필요하다. 역년별 서로 다른 기간·계절을 포함하므로 원인이나 운영 변경으로 단정하지 않는다. 모델 입력 간 상관은 계산하지 않았으며 signed d10의 abs는 정보 추가가 아닌 표현 변화다.

2023 seed7 F4 W 108,031,063원(기준 SM40 107,551,309원 대비 +0.446%), F3 106,535,683원(-0.944%)으로 F3를 선택했다. 사전 선택 기준에 따라 F4 2024·다중시드는 Not Run이다. F3 seed7의 2024 W는 197,257,247원으로 동일 seed7 SM40 198,736,384원 대비 -0.744%다. F3 seed7의 기간별 실행은 약 68~79초, F4 2023은 약 68초이며 실측에는 학습·추론이 모두 포함된다. F3 seed 21·42를 추가 학습해 3-seed를 검증했다. F5와 L1 손실은 우선순위상 선택 실험으로 남겼다.

`sm42_train.py`는 학습 시작 전 KST 21:15 cutoff를 검사하며 데이터·코드·출력 해시가 일치하는 완료 예측은 재사용한다. 새 특성은 site model에만 들어가고 SM39 Group 예측·alpha .2·reference composition은 고정했다. SM42 입력·출력·설정은 `outputs/sm42/`의 실험별 JSON과 parquet에 있다.

검증: SM42 신규 피처 테스트 5개 포함 전체 pytest 45 통과·3 실패. 실패는 SM40/41에서 이미 기록된 GFS `test_export_gfs_partial` 2개 및 `test_gfs_time_conversion` 1개다. GFS 코드나 테스트를 변경하지 않았다. `compileall`과 `git diff --check` 통과. `redistribute()`가 전체 site×time 및 group×time 중복·누락을 검증하고, 모든 평가 모델은 동일한 실제 site-hour에 `scoring.score()`와 독립 시간별 W가 일치함을 확인했다.
