# 아이디어 노트 — 선행연구 · 참고 저장소 · 검토 기록

> 실험 결과는 [EXPERIMENTS.md](EXPERIMENTS.md), 제출 기록은 [SUBMISSIONS.md](SUBMISSIONS.md).
> 여기에는 **아직 안 해 본 아이디어와 그 근거**를 모은다. 실험하면 `이니셜#번호`로 EXPERIMENTS.md 에 옮긴다.
> 모든 아이디어는 공지 기준을 먼저 확인: 외부 기상은 **고정 지점 평균 하나**, 예보는 **전날 17시 이전 발행분**, 평가 기간 실측 금지, 대회 데이터를 외부 AI 에 넣지 않기.

---

## 1. 우선순위 (다음에 해 볼 것)

| 순위 | 아이디어 | 근거 | 예상 효과 | 비용 | 규칙 |
| --- | --- | --- | --- | --- | --- |
| **1** | **학습 데이터 정제 — 출력제어·통신 보간 구간 제거** | 출력제어된 실적으로 학습하면 잠재 출력을 과소예측하도록 치우침 → 탐지·제거가 블렌딩 모델 학습을 개선 (Fraunhofer, Herzberg). 작년 대상 팀도 선형 보간 구간을 찾아 제거 | 중 (평가연도 출력제어 증가 의심과 직결) | 낮음 | ✅ |
| **2** | **최근 데이터 가중 (시간 감쇠)** | 출력제어·노후화 등 시간에 따라 변하는 패턴에 맞춤. 평가 직전 해(2025)를 더 중요하게 학습 | 소~중 | 낮음 | ✅ |
| **3** | **맑은날 지수(clear-sky index) 타깃** | 실적 ÷ 맑은날 잠재 발전량을 예측 → 계절·시간대 효과를 제거하고 날씨 효과만 학습. GBM 기반 PV 예측에서 표준적 정규화 | 소~중 | 낮음 | ✅ |
| **4** | **그룹 모델 = 아날로그 앙상블(AnEn) 재시도** | IEA PVPS Task 16 지역 예측 벤치마크에서 AnEn 이 1~3일 앞 RMSE 기술점수 20~36% 로 상위권. 우리 kNN 시도(JH#21)는 특징이 적고 학습 행이 8.9천뿐이라 약했음 → 수치예보 일사(GFS·LDAPS·JMA) 위주 + 2021~ 전체 기간으로 재구성 | 소 (다양성) | 중 | ✅ |
| **5** | **계층 조정(reconciliation)** | 발전소 합산 vs 그룹 직접 예측을 단순 가중평균 대신 오차 공분산 기반으로 결합 (Yang et al. 2017). 추가 입력 없이 모든 수준 정확도 개선 보고 | 소 | 낮음 | ✅ |
| **6** | **신규 발전소 보강 (전이 학습의 실용판)** | 2024 편입 105개소는 이력 1년 → 같은 관측지점·비슷한 용량의 오래된 발전소 패턴으로 보정 (발전소 ID 대신 지점·용량 군집 특징) | 소~중 | 중 | ✅ |
| 7 | 수치예보 MOS (일사 편향 보정) | 천정각·맑은날 지수 기반 편향 보정으로 1일 앞 상대 RMSE 37.8%→22.7% 사례 (Los et al.). 위성 일사(천리안 DSR)를 정답으로 GFS·LDAPS 일사를 보정 | 소 | 중 | ✅ (위성은 학습 정답으로만) |
| 8 | 그룹 단위 중앙값 학습 | 채점이 절대오차 → 그룹 합계의 조건부 중앙값이 최적. 발전소 L1(JH#7)은 실패했지만 그룹 모델 L1 은 단독 검증 안 함 | 소 | 낮음 | ✅ |

## 2. 하지 않을 것 (검토 후 제외)

| 아이디어 | 제외 이유 |
| --- | --- |
| 사전학습 시계열 모델 (Chronos, TimesFM 등) | "최근 실적 → 미래" 구조. 평가 기간 실적이 없어 입력할 최근 값이 없음 |
| 온라인/적응 학습 (실적 들어올 때마다 갱신) | 평가 기간 실적 미제공, 1년치를 한 번에 제출 |
| 강화학습 | 정답이 있는 지도학습 문제. 구성은 1회성 조합 최적화 → 국소탐색/MILP 가 적합 |
| 발전소별 최근접 격자 외부 기상 | 공지 5항 위반 |
| 예측값 이동평균 스무딩 (작년 대상 팀) | 작년은 5분 일사, 올해는 1시간 합계를 그룹으로 채점 → 이득 없음 |
| 주변 발전소 동시각 실측 가중평균 IDW (작년 대상 팀 핵심) | 평가 기간 실측이 없고, 좌표 기반 이웃 선택은 공지 5항과 충돌 |

## 3. 참고 저장소 분석

### 작년 대상 — [DohyunBu/OIBC_ReTry](https://github.com/DohyunBu/OIBC_ReTry) (2025 OIBC 일사량 추정, 대상)

- **과제가 다름**: 센서 없는 발전소의 **같은 시각 일사량 추정** (주변 발전소 실측이 있음). 올해는 하루 전 예측이고 평가 기간 실측이 없음.
- 방법: ① 학습 데이터에서 **선형 보간으로 채워진 구간 탐지·제거** (연속 기울기가 같은 구간, 0 구간 제외) ② 시각별로 주변 발전소 실측을 **거리 역제곱 가중평균** (상위 55개, 일부 발전소 블랙리스트) ③ 3점 이동평균 스무딩.
- **가져올 것**: ①의 데이터 정제 → 우선순위 1번.

### `_kth_` (3위, 11/06 재분석) — [KTHYEONG/oibc-2026](https://github.com/KTHYEONG/oibc-2026)

11/03 이후 커밋 없음 → 12회 제출이 모두 이 코드. 결정적 한 방보다 **같은 재료를 더 꼼꼼히** 쓴 구조.

| 항목 | 그 팀 | 우리 | 가져올 것 |
| --- | --- | --- | --- |
| 외부 GFS | sw·lw·tcc·rh, 넓은 상자 + 안쪽 평균 + 공간 SD, ±1h, 주간 평균, **공개 시각 감사(늦은 실행 NaN)** | gfs2 로 동일 구현, 감사 완료 | 동일 |
| 대회 예보 | 두 라운드 전부 별도 열, 이웃 시각, 라운드 수정량, 전날·다음날 일평균, 7일 롤링, fleet 평균 + **vsfleet(발전소−전체)**, `wb_ceiling`·`wb_snow` | r17 우선+r10 보조, 일부 문맥 | ✅ r10 전체 열, 다음날 일평균, vsfleet, ceiling/snow |
| 발전소 모델 | LGBM **L1 + SMP×k×용량 가중, 시드 3 평균** | L2, 무가중, 시드 1 | ✅ 시드 평균; L1·가중은 현재 특징으로 재시험 (JH#2·3·7 은 베이스라인 특징 기준) |
| 집합 | KMeans 지역 단면 패널 직접 예측 + CatBoost·MLP 혼합 | 그룹 직접(LGBM) | △ (우리 실험: 알고리즘 다양성 0) |
| 사후 보정 | 운량 선형(교차 적합) | 시험, 악화 | ✗ |
| 검증·채택 | 2폴드×3시드, 7일 블록 부트스트랩 CI, **≥1% & 분기 70% 승 & 노이즈 2σ** | 두 해 ≥0.5% (11/06~) | ✅ 시드 노이즈 기준 |
| 구성 | 지리 반클러스터링 | 참조 | △ |

교훈: 상위권 격차는 "비법"이 아니라 **노이즈를 채택하지 않는 규율 + 예보 특징의 폭**. 우리 S3·S4 는 2024 단일 해 개선을 채택해 LB 0.

### 올해 공개 저장소 (11/04 조사)

| 저장소 | 내용 | 메모 |
| --- | --- | --- |
| KTHYEONG/oibc-2026 (9위 `_kth_` 추정) | LGBM L1 + SMP×k×용량 가중, 시드 앙상블, 지역 합계 모델, 지리 반클러스터링 구성, **NOAA GFS 원본 광역 상자 요약** | GFS 원본 아이디어는 우리도 채택(JH#23). L1·가중은 우리 검증에서 악화 |
| JungGM/OIBC_test1 | XGB + LGBM L1, 그룹 교환 탐색 | 베이스라인 대비 −6.6% 수준 |
| kimna428/2026_OIBC | 딥러닝 (발전소 간 어텐션, 날씨 트랜스포머) | 비용 큼 |

## 4. 검토 기록 (질문과 답)

- **전이 학습 / 적응 학습?** 원래 형태는 불가(위 표). 실용판으로 ① 최근 데이터 가중(시간 감쇠, 우선순위 2) ② 오래된 발전소 → 신규 발전소 지식 전이(우선순위 6).
- **SHAP / DiCE?** SHAP 은 발표 자료용으로 유용(LightGBM 내장). DiCE(반사실 설명)는 분류 문제용이라 제외.
- **Gurobi?** 상용·학술 라이선스라 공지("상업적 이용 허용") 위반 소지 → HiGHS(MIT) 사용. 구성 최적화 효과 자체도 1~2%라 솔버 성능이 병목 아님.
- **XGBoost / CatBoost / 다른 시드?** LGBM 과 오차 상관 0.98~0.99 → 앙상블 이득 없음. 다양성은 **정보원·구조 차이**에서 나옴.
- **S3 가 로컬만큼 안 오른 이유?** 의심 1순위 구성 최적화 — 검증 기간엔 2024 편입 105개소 실적이 없거나 짧아 배치가 사실상 임의, 평가 기간엔 253개 모두 발전.

## 5. 선행연구 출처

- IEA PVPS Task 16, *Regional solar power forecasting* (2020) — 지역 업스케일링 벤치마크 (ANN, AnEn, QRF, RF, GBRT): [요약](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_PVPS_T16_regional_forecasts_summary.pdf) · [보고서](https://iea-pvps.org/wp-content/uploads/2020/07/IEA_PVPS_T16_regional_forecast.pdf)
- 지역 PV 하루 전 예측, 이탈리아 사례 6개 모델 비교 (Renewable Energy 2022): [PDF](https://art.torvergata.it/retrieve/e291c0da-0e95-cddb-e053-3a05fe0aa144/1-s2.0-S0960148122003184-main.pdf)
- Asiri, Chung, Liang, *Day-Ahead Prediction of Distributed Regional-Scale PV Power* (IEEE Access 2023): [링크](https://doaj.org/article/217fb8cec3464b58a4360c4e6887eaef)
- Pierro et al., *MOS cascade to improve day ahead solar irradiance forecast* (2015): [링크](https://repository.supsi.ch/6504/)
- *Post-processing NWP ensembles for probabilistic solar irradiance forecasting* (EMOS): [arXiv 2101.06717](https://ar5iv.labs.arxiv.org/html/2101.06717)
- *Improving Model Chain Approaches … Post-processing and ML* (2024): [arXiv 2406.04424](https://arxiv.org/html/2406.04424v1)
- Holland et al., 출력제어 탐지·제거와 물리+ML 결합 (EUPVSEC 2021): [PDF](https://www.ise.fraunhofer.de/content/dam/ise/de/documents/publications/conference-paper/38th-eupvsec-2021/Holland_5BV42.pdf)
- Herzberg, 출력제어 필터링 학습 데이터 (WCPEC-8): [PDF](https://www.ise.fraunhofer.de/content/dam/ise/de/documents/publications/conference-paper/wcpec-8/Herzberg_4BO174.pdf)
- 출력제어된 생산량에서 최대 가용 출력 복원 추정기: [arXiv 1705.04132](https://arxiv.org/pdf/1705.04132)
- Yang et al., *Reconciling solar forecasts: Geographical hierarchy* (Solar Energy 2017): [링크](https://bohrium.dp.tech/paper/arxiv/5ac49c2f5828b4988f408e54)
- 교차시간 조정과 일사 예측: [arXiv 2209.07146](https://arxiv.org/pdf/2209.07146)
- GEFCom2014 태양광 트랙 (GBM + kNN, 타 지점 정보 활용): [Huang & Perry](https://ideas.repec.org/a/eee/intfor/v32y2016i3p1081-1086.html) · [다중 분위 회귀](https://www.econbiz.de/Record/a-multiple-quantile-regression-approach-to-the-wind-solar-and-price-tracks-of-gefcom2014/10011622056)
- UM-LDAPS 일사량 하루 전 예보 성능 평가, 전국 37개 지점 검증 (한국태양에너지학회지 2019): [PDF](https://koreascience.kr/article/JAKO202032961435455.pdf)
- WRF·UM-LDAPS 기반 발전단지 예측 (2019): [PDF](https://koreascience.kr/article/JAKO201914456458235.pdf)
- 기상청 자료 + 천리안 위성 딥러닝 일사량 예측 (한국항법학회지 2021): [PDF](https://koreascience.kr/article/JAKO202135649631453.pdf)
