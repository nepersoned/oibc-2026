# SM#48 — Composition-Aware Group Refit

## 요약 및 결정

SM45에서 고정한 optimized composition으로 Group LightGBM(seed 100)을 재학습하고, 고정된 SM45 Site 3-seed 예측과 alpha=0.2로 결합했다. 본 실험의 목표였던 Group refit은 검증·제출기간 모두 실제 실행했다. 2024-12~2025-05 재사용 홀드아웃에서 B2는 B1 Site-only보다 W가 611,665원 낮았지만, paired block-bootstrap 95% CI가 0을 포함하고 6개월 중 2개월에서 악화했다. 그러므로 SM48을 기본 후보로 채택하지 않고, 기존 검증 완료 SM46 A1-REF를 기본으로 유지한다.

제출 형식 검토를 위한 별도 SM48 파일은 생성했으며 공식 Validator 종료 코드 0이다. 이 파일은 진단용 대안이며, 검증기간 재사용·구성 선택 편향이 남아 있어 이를 제출 권고로 해석하지 않는다. 공식 포털 업로드는 수행하지 않았다.

## 사전등록 및 설계

사전등록은 [SM48_PREREGISTRATION.md](SM48_PREREGISTRATION.md)에 저장했다. B0는 A1-REF, B1은 A1-COMP Site-only, B2는 동일한 optimized composition과 Site3에 새 Group 모델을 alpha=0.2로 결합한 후보이다. B2−B1은 고정된 composition에서 Group 결합 효과를 비교하며, B2−B0는 composition과 Group 학습 표본 변화가 함께 들어가는 전체 파이프라인 비교다.

- Site: SM45 weekday-only seed 7/21/42 평균을 검증과 제출기간 모두 그대로 재사용. 재학습하지 않음.
- Group: LightGBM seed 100, train-years=2, min_cov=0.3, alpha=0.2, 기존 `PARAMS`, `ext none`, fixed composition.
- 구성: `outputs/sm45/composition_a1_site_only.csv`, SHA256 `2ff0c07c5ee59ce66238575b14b8340a53daf34aec89c577f644aaa7bf357872`. 재최적화하지 않음.
- 달력·외부원천: weekday-only, WA/WB 및 제공 입력만. `holidays`, `EXTRA_OFF`, WX2, SM42 신규 피처와 외부 기상 비활성화. Site/Group feature audit에서 weekday 열은 포함되고 공휴일 및 `ext_`, `phys_`, `sp_`, `hat_` 열은 제외됨.
- 정산 W: `scoring.py`와 독립 시간별 penalty 합이 모든 후보·기간에서 일치하도록 검사했다.

## 학습 라벨·coverage 감사

| 평가 시작 연도 | 구성 | G1 coverage ≥0.3 | G2 coverage ≥0.3 | G1 평균/중앙 coverage | G2 평균/중앙 coverage |
|---|---|---:|---:|---:|---:|
| 2023 | Reference | 3,562 | 0 | 0.1955 / 0.1470 | 0.0195 / 0.0216 |
| 2023 | SM45 fixed | 3,014 | 0 | 0.1891 / 0.1422 | 0.0201 / 0.0223 |
| 2024 | Reference | 12,346 | 2,889 | 0.5104 / 0.4071 | 0.1121 / 0.0261 |
| 2024 | SM45 fixed | 11,798 | 3,540 | 0.4735 / 0.3938 | 0.1356 / 0.0270 |

2023 평가용 학습창은 2021-06-01 01:00부터 2023-06-01 00:00 KST까지이며 발전량 입력 961,115행이다. fixed composition에서도 G2의 `coverage >= 0.3` 라벨은 0건이다. 그 해 B2의 Group G2 출력은 유효한 G2 라벨로 학습된 결과가 아니며 외삽 위험이 있다. 2024 학습창(2022-06-01 01:00~2024-06-01 00:00 KST, 1,933,922행)은 G1/G2 각각 11,798/3,540개 eligible hour다. Reference 대비 fixed composition의 G2 라벨은 651개 늘고 G1은 548개 줄었다. 이 표본 변화는 B2−B0가 순수한 Group 효과가 아님을 보여준다.

실제 모델 학습 입력은 내부 주간 표본 제한을 거쳐 2023년 1,595행, 2024년 7,983행이었고 각각 300개 Group feature를 사용했다. Group target은 기존 정의(`관측 발전량 합 / 관측 설비용량`) 및 고정용량 추론을 그대로 유지했다. 평가기간 실적 또는 사후 coverage로 예측을 보정하지 않았다.

## 정산 결과

단위: 원. 2023은 composition이 2024년 실적으로 선택된 이후의 회고 진단이다. 2024 전체기간 및 2024-12~2025-05 기간도 이미 반복 사용된 구간이며 신규 독립 검증이 아니다.

| 구간 | B0 A1-REF | B1 A1-COMP Site-only | B2 fixed comp + Group refit | B2−B1 | B2−B0 |
|---|---:|---:|---:|---:|---:|
| 2023 전체 (회고) | 106,673,757 | 107,077,100 | 106,740,431 | −336,669 | +66,674 |
| 2024 전체 (진단) | 197,526,260 | 196,397,961 | 194,338,244 | −2,059,717 | −3,188,016 |
| 2024-12~2025-05 재사용 구간 | 87,757,370 | 86,870,948 | 86,259,282 | −611,665 | −1,498,088 |

2024 전체기간에서 B2는 B1보다 1.05%, B0보다 1.61% 낮았다. 그러나 회고적인 2023 전체에서는 B2가 B0보다 66,674원 높았다.

### 그룹·시간대 분해

| 구간/후보 | G1 W | G2 W | 11~15시 W | 비피크 W |
|---|---:|---:|---:|---:|
| 2024 전체 B0 | 93,693,778 | 103,832,482 | 163,019,883 | 34,506,377 |
| 2024 전체 B1 | 98,106,024 | 98,291,937 | 161,946,076 | 34,451,886 |
| 2024 전체 B2 | 97,274,255 | 97,063,989 | 160,413,061 | 33,925,183 |
| 재사용 구간 B0 | 39,935,290 | 47,822,080 | 72,555,179 | 15,202,191 |
| 재사용 구간 B1 | 41,195,304 | 45,675,644 | 71,699,268 | 15,171,680 |
| 재사용 구간 B2 | 41,143,565 | 45,115,718 | 71,351,281 | 14,908,002 |

2024 전체의 Site-hour signed bias(예측−실적)는 B0 −111,891 kWh, B1 −217,073 kWh, B2 −267,647 kWh였다. 재사용 구간에서는 각각 +321,870, +218,592, +235,673 kWh였다. 재사용 구간의 관측 Site-hour MAE는 각각 5.4178, 5.4104, 5.4097 kWh였다. MAE 개선은 작으며 Group W 개선과 동등한 목적 지표로 취급하지 않는다. Site-hour 평가의 관측 마스크는 세 모델에서 동일했다.

### 재사용 6개월 구간 월별 차이

| 월 | B2−B1 W | B2−B0 W |
|---|---:|---:|
| 2024-12 | −502,670 | −37,978 |
| 2025-01 | −411,885 | −576,247 |
| 2025-02 | +226,408 | −285,948 |
| 2025-03 | −24,944 | −207,438 |
| 2025-04 | −417,245 | −176,688 |
| 2025-05 | +518,669 | −213,789 |

B2는 B1보다 6개월 중 4개월에서 개선, 2개월에서 악화했다. 반면 B0보다 낮은 W는 여섯 달 모두에서 관찰됐지만 그 차이는 이미 사용된 기간에 대한 탐색 결과다.

## 불확실성·해석

168시간 paired moving-block bootstrap 5,000회, seed 7:

| 비교 | 평균 ΔW | 95% CI | 0 포함 |
|---|---:|---:|---|
| B2−B1 | −653,403 | [−1,944,103, +670,232] | 예 |
| B2−B0 | −1,572,265 | [−2,295,761, −851,975] | 아니오 |

B2−B1의 평균 bootstrap 개선은 0을 배제하지 못한다. 반복 검증 및 이전에 composition을 선택한 데 따른 selection/reuse bias도 남는다. B2−B0 CI는 0을 배제하지만, 이 비교는 composition과 Group 학습 데이터 구성이 동시에 바뀌므로 Group refit의 인과 효과를 분리하지 않는다. 따라서 사전등록된 안정성 기준으로 신규 기본 후보 채택을 뒷받침하지 못한다.

## 제출기간 후보 및 검증

최종 Group 제출 추론은 2년 학습창의 대회 제공 실적 및 WA/WB로 실행했고, SM46 weekday Site seed 평균을 재사용했다. SM45 composition으로 Group을 다시 적합한 뒤 기존 redistribute 로직으로 alpha=0.2 결합했다.

- `outputs/sm48/composition_sm48_final.csv`
- `outputs/sm48/forecast_sm48_final.csv`
- Validator: exit code 0; 8,760 KST 시각 × 2 그룹 = 17,520행
- 253개 발전소 예측 전체, 중복·누락 없음, 유한·비음수 예측, 저장 후 재적재 값 일치
- 그룹 용량: G1 21,161.64 kW, G2 21,493.73 kW
- 외부 기상 및 외부 공휴일 미사용. 포털 업로드 안 함.

제출기간 파일은 형식상 유효한 독립 후보로 생성했지만, 기본 제출 권고는 SM46 A1-REF다. B2의 W 이점은 이미 반복 검증된 표본에 한정되고 B2−B1 bootstrap CI가 0을 포함하며 월별 방향도 일관되지 않는다. SM46 A1-REF 원본은 변경하지 않았다.

## 재현 및 산출물

- Group validation: `outputs/sm48/group_b2_2024.parquet`, `outputs/sm48/group_b2_2023.parquet`
- Group submission prediction: `outputs/sm48/group_b2_submit.parquet`
- Full results and 5,000 bootstrap draws summary: `outputs/sm48/results.json`
- Hashes and configuration: `outputs/sm48/manifest.json`
- 재현 실행 명령(검증별):
  `python src/agg_model.py --mode val --train-years 2 --ext none --min-cov 0.3 --params '{}' --composition outputs/sm45/composition_a1_site_only.csv --val-start YYYY-06-01 --val-end YYYY+1-06-01 --out outputs/sm48/group_b2_YYYY.parquet`
- 제출기간 Group 명령:
  `python src/agg_model.py --mode submit --train-years 2 --ext none --min-cov 0.3 --params '{}' --composition outputs/sm45/composition_a1_site_only.csv --out outputs/sm48/group_b2_submit.parquet`
- 제출 검증 명령:
  `python src/validate_submission.py --composition outputs/sm48/composition_sm48_final.csv --forecast outputs/sm48/forecast_sm48_final.csv`
- 이 작업으로 수정한 코드/문서만 Git에 포함하며 데이터·예측·CSV는 무시 규칙 아래 로컬 보존한다.

## 제한 및 최종 권고

2023은 2024 정보로 선택된 구성에 대한 회고 진단이고, 그 연도 Group G2 라벨은 없다. 2024 및 하반기 검증 구간은 반복 사용된 검증 데이터다. 따라서 현재 결과는 Group refit 아이디어를 추가 실험할 근거이지, 독립 일반화 개선의 증명이 아니다. 기존 SM46 A1-REF를 보존·유지하고 SM48을 기본 제출 후보로 승격하지 않는다.

### 사전등록과 실행의 절차 차이

사전등록 초안에는 2023 진단을 진행하는 조건으로 G2의 충분한 라벨 수를 요구하는 문장이 들어갔다. 실제로 fixed composition의 2023 G2 `coverage >= 0.3`은 0건이었다. 사용자 지시에서는 2023 모델을 회고 진단으로 실행하고, G2 라벨이 없을 경우 외삽을 기록하도록 명시했으므로 해당 지시에 따라 2023 Group fit을 수행했다. 이 절차 차이는 사후에 숨기지 않는다. 2023 수치는 후보 선택이나 독립 일반화 주장에 사용하지 않았고, 해석상 외삽 진단으로만 보고한다.
