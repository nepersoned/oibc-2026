# SM#41 Literature and feature gap research

상태: 진행 중. 후보·선택 규칙은 `SM41_PREREGISTRATION.md`에 2023 SM41 결과 확인 전에 고정했다. 공식 포털 제출 없음.

## 근거와 이식 가능성

| 출처 | 핵심 피처/방법 | 원본 데이터 | 등급 | 가설 | 제약 |
|---|---|---|---|---|---|
| [2023 POSTECH OIBC 3위, README 및 노트북](https://github.com/Glanceyes/2023-POSTECH-OIBC-Challenge) | 시간 평균 대기권 밖 수평 일사 Q, 상관 행렬, attention LSTM | 기상, 발전실적, 기존 다섯 모델 예측 | B | 구름×태양 기하 proxy | 2026에는 5개 예측과 실제 일사가 없음 |
| [AMS 2013–14, McGovern et al. 2015](https://doi.org/10.1175/BAMS-D-14-00006.1) | GBRT, 근접 및 거리 가중 네 격자, NWP 앙상블, 시간·천문·공간·일별 평균 | GEFS 격자·앙상블 및 관측 복사 | B | 제공 관측지점의 분포 요약 | 공식 격자 일사나 다중 NWP 멤버는 없음; 임의 좌표 복원 금지 |
| [Xu et al. 2024, Tianchi 1위](https://doi.org/10.1016/j.eswa.2024.124286) | GRU와 XGBoost 예측 융합 | 과거 발전·일사 및 NWP | B | 예보의 같은 발행분 내 시간 문맥 | 공개 초록만 확인: 세부 생성식과 융합 가중은 확인 불가; 10일 예측과 day-ahead 차이 |
| [Nagy et al. 2016 GEFCom2014](https://doi.org/10.1016/j.ijforecast.2015.11.013) | QRF와 stacked RF–GBDT 분포의 voted ensemble | 풍력·태양광 예측 입력 | B | 불확실성 진단 | pinball과 W는 별개; 정규분포 전제 아님. 초록만 확인 |
| [Ali et al. 2025](https://doi.org/10.1038/s41598-025-07038-x) | ReliefF, mRMR 등 선택과 MLP/LSTM 비교 | 알제리 단일 PV 예측자료 | A | 선택 자체를 별도 검증 | 최적 피처 수·순위 전이 보장 불가 |
| [Berlanger et al. 2024](https://doi.org/10.1080/26941899.2024.2426786) | 기상·천문 및 공간 해상도별 tree 예측 | 세분 기상자료 | B | 관측지점 간 변동 | 초록만 확인, 상세 성능 추측 금지 |
| [Alonso-Montesinos et al. 2021](https://doi.org/10.3390/atmos12030395) | 하늘 영상 기반 구름량 추정 및 일사·발전 예측 | 하늘 영상 | C | 구름 감쇠의 필요성 | 영상 부재; 동일한 기법 재현 불가 |

2023 팀은 최종 3위다. 공개 EDA의 Q12/Q13은 1367 W/m², Fourier 지구–태양 거리 보정과 적위, 위도 36.9°, 시간각, 1시간 적분 계수 `(24/pi) sin(pi/24)`를 이용하며 음수는 0 처리한다. Q13은 시각 13시 중심 설정이다. Q는 태양 기하와 계절을 물리량으로 압축하지만, 현행 cosz와 달리 거리 보정과 시간 적분을 포함한다. 현행 `solar()`는 시간 구간 중앙 근사이므로 수치가 동일하지 않다. EDA는 절대 상관 heatmap을 그렸고 README는 타깃과 상관이 약한 변수를 제거했다고 설명한다. 선택 변수는 cloud, humidity, wind_dir, vis, uv_idx, elevation, hour, Q13과 model0–3이다. 온도 제거 이유는 당시 성능 악화 관찰이며 보편 법칙이 아니다. attention LSTM과 네 기존 예측 입력을 사용했다는 것은 확인되나 가중 앙상블 구체식은 이 기록에서 확인하지 못했다. 2023 인센티브/오차와 2026의 그룹별 SMP·시간가중 절대오차 W는 동일하지 않다.

AMS의 3위는 11개 NWP 멤버 평균을 만들고 가장 가까운 격자와 거리 가중 4격자로 각각 GBRT를 학습해 교차검증 가중으로 결합했다. 학생 우승자는 Gaussian process 공간 보간의 분산, 일평균, 일조 길이 및 비선형 조합과 LAD GBRT·seed 평균을 사용했다. 이 대회는 일별 일사 MAE이며 현 대회의 W와 다르다. GEFCom QRF는 경험적 조건부 분위수를 추정하여 Gaussian의 대칭성과 꼬리 모양을 강제하지 않는다. W가 가중 절대오차이므로 조건부 중앙값이 기본 의사결정점이지만 그룹 합과 가중치 조건에 따른다.

## 기존 inventory와 gap

`features.py` 및 `pipeline.py`는 WA/WB 원본, 17 우선/10 결측 대체, round 차이, 같은 대상일 lag/lead와 일·주간 평균, 전국 평균, 태양고도·방위·cosz, Haurwitz `ghi_cs`, 시간과 연주기, 용량·위경도·달력을 제공한다. `site_code`는 SM40에서 제거한다. 대회 README에서 WA/WB cloud %; WA 풍속 m/s, WB 풍속 km/h; 온도 °C; 습도 %; WB UV 지수 및 시정이 확인된다. 풍향은 원본에 있으나 현재 `WA_ALL`/`WB_ALL` 선택 여부는 코드 기준으로 판단해야 한다. 원시 자료에는 이상치가 있으며 관측 기간 raw 결측률과 gain은 추가 감사가 필요하다.

Q0는 대기권 밖; `ghi_cs`는 Haurwitz 맑은 하늘 모형; 실제 GHI는 관측값; `sm41_*_cloud_ghi_proxy`는 예보 구름량과 `ghi_cs`로 만든 가상 지표다. 실제 GHI 또는 실제 clearness index로 부르면 안 된다. 단일 cloud 비율이 구름 두께·종류를 알리지 못한다. 선택한 F2는 사전 정의 `ghi_cs*(1-0.75*clip(cloud/100,0,1)**3.4)` (각 기관별)이며 [AERMOD 문서의 구름 감쇠 형식](https://linux.vbird.org/enve/images/aermod_mfed.pdf)에 근거한 proxy다. 상수는 검증 연도에 맞춰 조정하지 않았다. 고정 공식이 대상 도메인에 보정되었다고 주장하지 않는다.

## 우선순위 및 누수

F2 A: 기존 sky baseline×구름 감쇠. F1 A: Q0는 기존 cosz·ghi_cs 및 날짜와 중복 위험. F3 A/B: 같은 발행분 구름 revision 절댓값 또는 기관 차이는 예보 불일치 proxy이며 이미 `d10` 존재. F4 A/B: 제공 관측소의 동시 예보 분산은 공간 이질성 proxy, GFS 기반 SM26과 다른 원천. F5 A: 기온·풍속과 일사 proxy 상호작용, 풍속 단위 변환 필요; 실제 모듈 온도 아님. F6 B: 예보 변동성을 불확실성 proxy로 분석; 정규성은 검정 대상. Actual GHI/clear-sky index, 실제 패널온도, 실제 예보오차와 NWP 멤버 분산은 C. 같은 대상일의 미래 유효시각 예보는 발행 시점 기준 허용되지만 미래 관측 발전·기상값은 금지. 10/17의 실제 개별 게시시각은 데이터에 없어 공지 정의에 의존한다.
원본 예보 결측 감사: train WA 4,710,356행, WB 5,621,996행 중 cloud 값 자체의 NaN은 모두 0%; train WB 강수확률 및 강수량 관련 값 0.0231% NaN. test WA 1,068,456행, WB 1,278,960행의 저장된 값은 NaN 0%. 이는 없는 station-round-time 행을 포함하지 않는다. 대회 명세에 test WA 264개 조합 누락이 명시되어 있으며 join 이후 결측률과 이상치·연도 안정성은 별도 감사가 필요하다. 상세 `outputs/sm41/forecast_inventory.json`.

공개 `pipeline.ipynb` 추가 확인: 12개 입력을 쓰는 LSTM+Transformer BertEncoder, 길이 2 윈도, MSE 학습이다. 추론에서 하나의 시점에 겹쳐 나온 윈도 예측을 산술 평균하고 음수는 0으로 처리한다. 이 예측 결합은 4개 기존 모델 예측을 입력으로 사용하는 stacking 성격이며 고정 선형가중치가 아니다. 노트북의 임의 train_test_split은 시간순 검증의 근거로 쓸 수 없다.

기존 입력 상세: 원본 풍향 WA/WB는 각각 °로 존재하나 rich의 `WA_ALL`, `WB_ALL`에서는 제외된다. WB 시정 km, 강수확률 %, WA 비 mm, 두 기온 °C·습도 %, WB UV 무차원이다. 공개 `sites`의 관측지점 연결과 용량을 쓴다. Forecast 데이터 round=10/17, KST 대상 시각이 키이며 지점-라운드-시각의 결손 행은 값 NaN과 구분한다. 타깃일 경계를 넘지 않는 예보 lead는 같은 발행 예보에 한한다. 2023 gain 상위 및 F2의 gain 상위는 `FEATURE_SELECTION_SM41.md`에 기록하며 기존 모든 원본별 gain과 통계적 중복 수치는 미완료다.

발표자료 5–10쪽을 직접 확인했다. 슬라이드 5는 정오를 12시로 근사했다고 설명하지만 슬라이드 6과 README의 선택 목록은 `Q13`이므로 공개 자료 간 불일치가 있다. 실험에서 어느 하나로 단정하지 않는다. 발표자료는 6–10월 학습 대비 11월 대회 기간 기온 차이 때문에 온도 포함 모델이 11월 13일 과소예측했고 이후 온도를 제거했다고 설명한다. 기존 예측 단순 평균보다 낮은 오차를 보고했고 RF 기반 결합은 단순 평균보다 나빴다고 설명한다. 다른 데이터·시즌에서 온도를 제거해야 한다는 근거는 아니다.
