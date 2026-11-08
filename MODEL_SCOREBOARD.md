# Model Scoreboard

최종 갱신: 2026-11-08. 공식 점수는 높을수록 좋고, 로컬 정산 페널티 W는 낮을수록 좋다. 공식 S는 제출 평가기간 점수이며 로컬 W와 평가기간이 다르므로 직접 비교하지 않는다. 제출 날짜는 확인된 날짜만 기록하고 시각·순위는 제공되지 않으면 비워 둔다.

## 1. 공식 리더보드 제출

| ID | 모델 | 입력 데이터 | 로컬 W (KRW) | Official S | 구성 요약 | 제출일 | 상태 | 실험 | 파일·무결성 |
|---|---|---|---:|---:|---|---|---|---|---|
| S1 | `ens_ref` | 대회 예보 + 외부 일사/JMA | 2024–25 187,133,757 | 6,455,051,853 | Site 61.5% + Group 38.5%, reference | 2026-11-04 | 제출 완료 | JH#14 | `origin/main:predictions/submissions/*_ens_ref.csv` |
| S2 | `ens_v3` | GFS + LDAPS, 종료 이후 GFS 대체 | 2024–25 CV 176,485,314 | 6,459,800,168 | Group 56% + Site 44%, reference | 2026-11-04 | 제출 완료; S9에 최고 기록 양도 | JH#29 | `origin/main:predictions/submissions/*_ens_v3.csv` |
| S3 | `ens_v5` | GFS + LDAPS | 2023–24 95,250,073; 2024–25 172,800,313‡ | 6,459,111,150 | Site 50% + Group 50%, 50-site optimized composition | 2026-11-04 | 제출 완료; S2/S9보다 낮음 | JH#35 | `origin/main:predictions/submissions/*_ens_v5.csv` |
| S4 | `ens_v7` | GFS + LDAPS + clear-sky baseline | 2024–25 174,068,299 | 6,456,638,652 | Site 65% + Group 35%, reference | 2026-11-06 | 제출 완료 | JH#49 | `origin/main:predictions/submissions/*_ens_v7.csv` |
| S5 | SM emergency noext | 대회 제공 예보, 외부 기상 없음 | — | 6,442,981,587 | noext emergency candidate | 2026-11-07 | 제출 완료; 팀 최고 아님 | SM 제출 기록 | 경로·해시는 현재 원격 기록 참조 |
| S6 | `ens_v9` | GFS + LDAPS + ENS + UM | 2024–25 170,776,176; 2023–24 95,337,337 | 6,449,742,170 | Site 41% + Group 59%; 4–5월 UM 결측 버그 | 2026-11-07 | 제출 완료; 결측 문제 기록 | JH#61 | `origin/main:predictions/submissions/*_ens_v9.csv` |
| S7 | `ens_v9b` | GFS + LDAPS + ENS; UM regional/global 4–5월 제외 | S6과 동일 CV 기록 | 6,457,699,036 | v9 spring replacement; reference | 2026-11-07 | 제출 완료; 이후 S9에 최고 기록 양도 | JH#62 | `origin/main:predictions/submissions/*_ens_v9b.csv` |
| S8 | SM46 A1-REF | 대회 WA/WB + 제공 site/time; weekday only | 2023–24 106,673,757; 2024–25 197,526,260 | 6,448,069,881 | Site3 (7/21/42) + Group100, 80/20, reference, no external weather/holiday | 2026-11-07 (시각 미제공) | 제출 완료; 데이터 계보 보수 후보 | SM#46 | `outputs/sm46/composition_sm46_a1_ref.csv`; `outputs/sm46/forecast_sm46_a1_ref.csv`; manifest hashes below |
| S9 | `ens_v12` | ENS + KMA UM + LDAPS + derived weather features | 2023–24 93,377,951; 2024–25 167,041,881 | **6,460,690,768** | Site `site_dv` 50.5% + Group `l1umx+derived` 49.5%, reference | 2026-11-08 | **팀 공식 최고**; source-rule status not independently confirmed | JH#68 | `origin/main@793f5f6:predictions/submissions/composition_ens_v12.csv` + `forecast_ens_v12.csv` |
| S10 | `ens_v13` | ens_v12 + spring-holiday daytime scaling | — | 6,458,895,617 | Spring holiday 10–16 adjustment | 2026-11-08 | 제출 완료; S9보다 낮음 | JH#73 | `origin/main@793f5f6:predictions/submissions/composition_ens_v13.csv` + `forecast_ens_v13.csv` |

S1–S10 상세 및 제출 기록은 [SUBMISSIONS.md](SUBMISSIONS.md)와 read-only `origin/main@793f5f6`을 참고한다. S8 점수는 사용자 제공 포털 확인, S9/S10은 당시 팀 저장소 로그를 근거로 반영했다. 포털의 현재 순위와 남은 제출 횟수는 이 기록에서 추정하지 않는다.

## 2. 연구용 후보 (공식 미제출)

| 실험/후보 | 입력·변경 | 2023–24 W | 2024–25 W | Official S | 상태 | 상세·파일 |
|---|---|---:|---:|---:|---|---|
| SM#41 baseline | Site3 + Group1, legacy calendar | 106,754,876 | 197,534,279 | — | 실험 기준 | [비교](FINAL_MODEL_COMPARISON_SM41.md) |
| SM#42 F3 | cloud revision/disagreement Site3+Group | 106,949,376 | 196,517,774 | — | CI 불확실, 미채택 | [선택](SM42_FEATURE_SELECTION.md) |
| SM#43 | Group 5-seed, Site 고정 | 106,739,743 | 197,493,336 | — | CI가 0 포함, SM41 유지 | [보고서](SM43_GROUP_BAGGING_REPORT.md) |
| SM#44 | coverage / CF target | — | — | — | 지원 기준 미달로 후보 학습 미실행 | [보고서](SM44_GROUP_TARGET_COVERAGE.md) |
| SM#45 A1 weekday blend | calendar-safe Site3+Group | 106,673,757 | 197,526,260 | — | 비교 후보; 승격 근거 불충분 | [보고서](SM45_FINAL_REPORT.md) |
| SM#46 A1-REF | same weekday reference candidate as S8 | 106,673,757 | 197,526,260 | 6,448,069,881 (S8) | 공식 제출 완료 | `outputs/sm46/composition_sm46_a1_ref.csv`; `outputs/sm46/forecast_sm46_a1_ref.csv` |
| SM#46 A1-COMP | Site-only optimized composition | 107,077,100 | 196,397,961 | — | 공식 미제출 | `outputs/sm46/composition_sm46_a1_comp.csv`; `outputs/sm46/forecast_sm46_a1_comp.csv` |
| SM#47 L1 seed7 | L1 Site + Group100 | 106,266,107 | 202,920,302 | — | 2024 악화, 조기 중단 | [보고서](SM47_L1_EXPERIMENT_REPORT.md) |
| SM#48 B2 | optimized composition + refit Group | 106,740,431 (회고) | 194,338,244 | — | 공식 미제출; 재사용 평가기간 | [보고서](SM48_COMPOSITION_GROUP_REFIT.md); `outputs/sm48/manifest.json` |
| SM#49 | candidate stress test, no training | — | — | — | A1-REF 권고, 감사 | [비교](outputs/sm49/FINAL_CANDIDATE_COMPARISON.md); [선정](outputs/sm49/FINAL_SELECTION_RECOMMENDATION.md) |
| SM#50 | forecast uncertainty regime diagnostic | — | — | — | 진단 완료; 동적 alpha·새 모델 미채택 | [사전등록](SM50_PREREGISTRATION.md); [결과](SM50_FORECAST_UNCERTAINTY_DIAGNOSTIC.md) |
| SM#51 | leaderboard gap / artifact audit | — | — | — | 준비 단계; ens_v3 OOF 없음, 신규 학습 없음 | [우선순위](SM51_RESEARCH_PRIORITIZATION.md); [아티팩트](SM51_ARTIFACT_AVAILABILITY_AUDIT.md) |
| SM#52 | historical solar-shape response feasibility | — | — | — | Stage 0 중단; strict OOF 없음·2023 support 부족, 학습 미실행 | [타당성](SM52_FEASIBILITY_AUDIT.md); [사전등록](SM52_PREREGISTRATION.md); [결과](SM52_SOLAR_RESPONSE_REPORT.md) |
| SM#53 | historical generation AM/PM profile, seed7 | — | 199,849,640 | — | 연구용; fixed 20% Group blend worsened by 872,544, not adopted; no submission | [사전등록](SM53_PREREGISTRATION.md); [결과](SM53_HISTORICAL_PROFILE_REPORT.md); `outputs/sm53/pilot_2024.json` |
| SM#54 | settlement error decomposition | — | — | — | 당시 SHA gate로 중단; SM55에서 Markdown 오기로 정정 후 기존 예측 분해 완료 | [사전등록](SM54_PREREGISTRATION.md); [중단 보고](SM54_SETTLEMENT_ERROR_DECOMPOSITION.md); [SM55 정정](SM55_ARTIFACT_PROVENANCE_AUDIT.md) |
| SM#55 | SM53 settlement loss decomposition (same frozen predictions) | — | 199,849,640* | — | 진단 완료; Markdown SHA typo 정정; cancellation benefit fell 2.226m, explaining W +872,544 arithmetically; no new candidate/official score | [계보 감사](SM55_ARTIFACT_PROVENANCE_AUDIT.md); [분해](SM55_SETTLEMENT_DECOMPOSITION.md) |
| SM#56 | ens_v12 vs SM46 prediction-level complementarity | — | — | — | Fixed-alpha diagnostic only; no stable W gain; 2023 G2 actual coverage weak; no training/submission | [사전등록](SM56_PREREGISTRATION.md); [정렬 감사](SM56_ARTIFACT_ALIGNMENT_AUDIT.md); [결과](SM56_COMPLEMENTARITY_REPORT.md) |
| SM#57 | GFS vertical cloud fields feasibility | — | — | — | Source audit only; sampled GRIB fields exist, but date-level cutoff, full coverage and OIBC eligibility unresolved; training not run | [사전등록](SM57_PREREGISTRATION.md); [원천 감사](SM57_GFS_CLOUD_SOURCE_AUDIT.md); [결정](SM57_NEXT_DECISION.md) |

\* 재사용된 SM#53 로컬 W를 분해 목적으로 재현한 값이며, 새 모델 점수는 아니다.

## 3. 파일 무결성

| Artifact | Relative path | SHA256 |
|---|---|---|
| S8 composition | `outputs/sm46/composition_sm46_a1_ref.csv` | `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` |
| S8 forecast | `outputs/sm46/forecast_sm46_a1_ref.csv` | `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` |
| S8 manifest | `outputs/sm46/manifest_a1_ref.json` | `7c06c08f571e56fc9e6156e2a8044dc3a8b1b7cc9cb580037a5011a3d7cdd68a` |
| SM41 legacy forecast (protected; local path not verified here) | Path not verified | `ed9d14e194259971802ef1e1530f0bd38b05455cf3ca66a7815abaedbd63fd8d` |
| SM46 A1-COMP | `outputs/sm46/manifest_a1_comp.json` | `7dfeec5b81f4960420e64e112e6d3a5dc4af46054107ddd7fad64ee89c7dfc6a` |
| SM48 B2 | `outputs/sm48/manifest.json` | `acf73c1688bdf9aa31143b85d37bd012c90a06dce1e7c04ad96db97fd6adee8e` |
| SM49 candidate audit manifest | `outputs/sm49/submission_files_manifest.json` | local ignored manifest; see its candidate hashes |

## 4. 최신 최고 모델

**공식 팀 최고는 S9 `ens_v12` — 6,460,690,768**이다. S10 `ens_v13`은 6,458,895,617로 S9보다 1,795,151점 낮다. SM46 A1-REF (S8, 6,448,069,881)는 제공데이터 기반으로 로컬 파일·validator가 확인된 보수 후보이며, S9의 리더보드 점수와 규정 적합성·재현성은 별도로 관리한다. ens_v12의 외부 source/cutoff lineage는 [SM56 감사](SM56_ARTIFACT_ALIGNMENT_AUDIT.md)에서 미확정으로 남겼다.

‡ S3의 2023 값은 reference composition 진단이며 모델 구성의 평가 단위가 달라 두 해 W를 단일 공통 성능표처럼 해석하지 않는다. 로컬 W와 공식 S는 별도 기간·목표 지표다. S1–S7, S9–S10의 세부는 `origin/main@793f5f6` 팀 로그, S8 점수는 사용자가 제공한 포털 확인을 근거로 한다.
