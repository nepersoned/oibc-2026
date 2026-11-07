# 2026 OIBC Challenge

> 태양광 발전소 253개소를 두 그룹(G1, G2)으로 묶고, 그룹별 시간당 발전량을 하루 전에 예측해 **정산금 S를 최대화**하는 대회

---

## 2026-11-07 공식 점수 갱신

사용자가 공식 포털에서 확인한 최신 제출 S4 `SM46 A1-REF` 점수는 **6,448,069,881**이다. 팀 공식 최고는 S2 `ens_v3`의 **6,459,800,168**로 유지되며, S4는 팀 최고보다 11,730,287점 낮다. S4는 weekday-only 달력과 대회 제공 기상만 사용하고 로컬 Validator exit 0을 통과했다. 제출 시각과 순위는 확인되지 않았다.

모델별 공식 점수, 로컬 W, 후보 상태 및 파일 해시는 [MODEL_SCOREBOARD.md](MODEL_SCOREBOARD.md)에서 확인한다. 실험 기록은 [EXPERIMENTS.md](EXPERIMENTS.md), [SEONGMIN_EXPERIMENTS.md](SEONGMIN_EXPERIMENTS.md), 제출 기록은 [SUBMISSIONS.md](SUBMISSIONS.md)를 참고한다.

## 🏁 이전 현황 스냅샷 (2026-11-04 밤)

| 항목 | 값 |
| --- | --- |
| 리더보드 최고 | **6,459,800,168 (51위)** — S2 `ens_v3`, 공식 베이스라인(6,418,396,513) 대비 +4,140만 원 (평가 구간 ≈ −18.9%) |
| 제출 | S1 6,455,051,853 → **S2 6,459,800,168 (51위, 최고)** → S3 `ens_v5` 6,459,111,150 (S2 대비 −69만, 로컬 개선 미재현 — 구성 최적화 의심) |
| 목표 | 7위 6,467,321,891 · 10위 ≈ −21.9% · 1위 ≈ −24.4% |
| 로컬 최고 | **`ens_v5`** — 2024~25 **−23.0%**, 2023~24 **−23.2%** (두 해 모두 검증) |
| 로컬 ↔ LB | S1 감소분 비율 0.98, S2 0.86 → 2023~24 홀드아웃에서도 −22.4% 라 검증연도 과적합은 아님. 평가연도(2025~26) 특성(출력제어 증가 추정)으로 이득이 줄어드는 것으로 봄 |

### 현재 모델 (`ens_v5`)

| 구성원 | 비중 | 입력 | 학습 |
| --- | --- | --- | --- |
| 발전소 모델 (LightGBM, 1800 트리·255 잎) | 50% | 대회 예보(앞뒤 시각·일평균·두 라운드) + 외부 일사(Open-Meteo JMA/ECMWF/GFS 48h, **NOAA GFS 원본 D-1 00z**, **기상청 LDAPS D-1 00z**) 전국평균 + 태양 위치·청천일사 + 발전소 ID + 요일·공휴일 | 2021-01 ~ 2025-05 전부 |
| 그룹 모델 (LightGBM, 15 잎·시드 5 평균) | 50% | 그룹 용량가중 예보 + 전 관측지점 예보 + 위 외부 일사 전국평균 + 요일·공휴일 | 2021-01 ~ 2025-05 전부 |
| 구성 | — | 두 해(2023~25) 잔차로 국소탐색, 50개소 이동 (G1 22,533.8 / G2 20,121.6 kW) | |
| LDAPS 종료 대응 | — | 대상일 2026-04-02 이후는 LDAPS 없는 GFS 모델 예측으로 대체 (`src/splice.py`) | |

### 핵심 발견

1. **오차의 절반은 "그날 하루가 얼마나 맑은가"** — 집합×일 총량을 완벽히 맞히면 W −49% (오라클). 시간대 모양·발전소 편향·구성은 작음.
2. **제공 예보에는 일사량이 없다** → 외부 수치예보 일사량이 결정적. 단, 공지 5항에 따라 **고정 격자/상자 평균 하나로만** 모든 발전소에 같은 값.
3. **신선도가 중요** — 같은 GFS 라도 Open-Meteo 48h 전 발행분보다 **NOAA 원본 D-1 00 UTC 실행분**(마감 전 공개)이 훨씬 효과적. 학습 기간 전체(2021~)를 덮어 학습 기간도 늘릴 수 있게 됨.
4. **앙상블 다양성은 알고리즘이 아니라 정보원에서** — LGBM↔XGB 오차 상관 0.99, 발전소↔그룹 0.89, 외부데이터 유무 0.80. 반년 교차검증으로 고르면 3개 구성원만 남음.
5. 봄철 주말·공휴일 낮 과대예측(+3.3% vs 평일 −1.9%) = 출력제어 흔적 → 요일·공휴일 특징 −0.5%.
6. **모델 앙상블보다 데이터 융합** — 날씨 소스를 한 모델에 같이 넣는 것이 가장 효과적. 소스별 모델을 따로 만들어 섞으면 효과 0. 앙상블은 발전소 vs 그룹 **구조 차이**만 의미 있음.
7. **학습 기간은 외부 일사량이 덮어야 늘릴 수 있다** — GFS 없이 2→3년은 +0.9% 악화, GFS 있으면 −0.9% 개선.

---

## 🚀 빠른 시작 (팀원용)

```bash
git clone https://github.com/nepersoned/oibc-2026.git
cd oibc-2026
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

1. 대회 데이터 `OIBC_2026_DATA.zip` 을 풀어 `data/handover 2/01_participant_dataset/` 가 되게 둡니다 (git 제외).
2. 외부 데이터 수집 (모두 공개·상업 이용 가능, 재수집 가능 — 아래 "외부 소스 기록")
   ```bash
   .venv/Scripts/python.exe src/fetch_external.py     # Open-Meteo (JMA/ECMWF/GFS 48h 전, JMA 추가 변수)   ~10분
   .venv/Scripts/python.exe src/fetch_gfs.py          # NOAA GFS 원본 D-1 00z, 2021~                      ~30분
   .venv/Scripts/python.exe src/fetch_gefs.py         # NOAA GEFS 평균+퍼짐 D-1 00z, 2021~                 ~40분
   .venv/Scripts/python.exe src/fetch_kma.py --um     # 기상청 UM 국지(LDAPS) D-1 00z, 2021~2026.3        ~60분 (.env 에 KMA_API_KEY)
   ```
3. 검증 (2024-06 이전 학습 → 마지막 1년을 대회 식으로 채점)
   ```bash
   # 발전소 모델
   .venv/Scripts/python.exe src/pipeline.py --mode val --fset rich --ext mean --tag 이름        --params '{"n_estimators":1800,"learning_rate":0.03,"num_leaves":255,"min_child_samples":100,"colsample_bytree":0.6}'
   # 그룹 모델 (현재 최고 설정)
   .venv/Scripts/python.exe src/agg_model.py --mode val --ext mean --train-years 4 --min-cov 0.1        --params '{"seeds":5,"num_leaves":15,"n_estimators":2500,"learning_rate":0.015}'        --bu outputs/val_<발전소태그>_sites.parquet --out outputs/val_agg_이름.parquet
   # 앙상블 구성원 선별 (오차 상관 + 반년 교차검증)
   .venv/Scripts/python.exe src/ensemble_select.py --sites <발전소태그들> --groups 이름:경로 ...
   ```
4. 제출 파일: 각 모델 `--mode submit` → `src/ensemble.py fit/submit` → 형식 검사 자동 실행.
5. [SUBMISSIONS.md](SUBMISSIONS.md)에 기록하고 제출. **제출 전에 표에 "예정"으로 먼저 적기** (팀 전체 하루 3회).

### 코드 구조

| 파일 | 역할 |
| --- | --- |
| [`src/features.py`](src/features.py) | 예보 결합(라운드 17 우선·10 보조), 대상일 내 문맥, 전국 요약, 태양 위치·청천일사, 요일·공휴일, 외부 수치예보 로드 (`load_ext`) |
| [`src/model.py`](src/model.py) | 발전소 모델 LightGBM `fit` / `predict` (설비이용률 타깃, 야간 0) |
| [`src/pipeline.py`](src/pipeline.py) | 발전소 모델 학습 → 예측 → 채점/제출 (`--fset rich --ext mean`) |
| [`src/agg_model.py`](src/agg_model.py) | 그룹 모델 — 집합 CF 직접 예측 (집합 용량가중 예보 + 전 관측지점 예보 + 외부 수치예보), 시드 배깅, `algo` lgb/xgb/cat |
| [`src/alt_models.py`](src/alt_models.py) | 다른 각도 구성원: 지역(61) / 아날로그(kNN) / 선형(Ridge) |
| [`src/weather_model.py`](src/weather_model.py) | 날씨 보정 — 예보 → 실측 구름·자외선 (학습 구간 실측은 정답으로만) |
| [`src/daily_model.py`](src/daily_model.py) | 일일 총량 모델 (실험, 미채택) |
| [`src/ensemble.py`](src/ensemble.py) · [`src/ensemble_select.py`](src/ensemble_select.py) | 앙상블 비율 / 구성원 선별 |
| [`src/composition.py`](src/composition.py) | G1/G2 구성 최적화 (국소탐색 + HiGHS MILP) |
| [`src/fetch_external.py`](src/fetch_external.py) · [`src/fetch_gfs.py`](src/fetch_gfs.py) · [`src/fetch_gefs.py`](src/fetch_gefs.py) · [`src/fetch_kma.py`](src/fetch_kma.py) | 외부 수치예보 수집 (Open-Meteo / NOAA GFS / NOAA GEFS / 기상청 LDAPS·천리안) |
| [`src/scoring.py`](src/scoring.py) | 로컬 정산금 S (리더보드와 오차 2%) |
| [`src/validate_submission.py`](src/validate_submission.py) | 공식 제출 형식 검사기 |
| `src/analyze_*.py`, `src/inspect_data.py` | 오라클·잔차·시차 분석 (집계값만 출력) |

### 연구 기록 바로가기

- [모델 점수 대시보드](MODEL_SCOREBOARD.md)
- [통합 실험 로그](EXPERIMENTS.md)
- [오성민 상세 실험 기록](SEONGMIN_EXPERIMENTS.md)
- [공식 제출 기록](SUBMISSIONS.md)

> 📒 **전체 실험 로그: [EXPERIMENTS.md](EXPERIMENTS.md)** (`JH#1` ~ `JH#35`, 실험별 점수·판정) · 제출 기록: [SUBMISSIONS.md](SUBMISSIONS.md)

### 실험 요약 (페널티 W — 작을수록 좋음, 베이스라인 대비)

| 단계 | 2024~25 검증 | 2023~24 홀드아웃 | 로그 |
| --- | --- | --- | --- |
| 공식 baseline | 224,547,074 | 123,997,939 | JH#1 |
| 특징 확장 + 큰 LGBM (대회 데이터만) | −9.9% | | JH#6, JH#8 |
| + 외부 일사 전국평균 (Open-Meteo) + JMA 추가 변수 | −14.7% | | JH#11, JH#14 |
| + 그룹 모델 앙상블 → **S1 (LB 88위)** | −16.7% | | JH#14 |
| + 요일·공휴일, 그룹 모델 배깅 | −17.5% | | JH#18, JH#19 |
| + **NOAA GFS 원본** + 학습 기간 연장(4년) | −20.1% | −18.9% | JH#23~26 |
| + **기상청 LDAPS** (그룹 모델) → **S2 (LB 51위)** | −21.4% | −22.4% | JH#28~30 |
| + LDAPS (발전소 모델) + 두 해 구성 최적화 → **S3 `ens_v5`** | **−23.0%** | **−23.2%** | JH#31~35 |

**효과 없음 / 미채택** (상세는 EXPERIMENTS.md): 학습 가중(k, SMP×k) · L1 목적함수 · GFS 이전 학습 연장 · Optuna(단일 내부연도 과적합) · 날씨 보정 v1(특징) · 일일 총량 재조정 · XGBoost/CatBoost (LGBM 과 오차 상관 0.99) · 발전소 2호기 (상관 0.98) · 지역/아날로그/선형 · 정보원 분리 모델 · **NOAA GEFS** (+0.7%) · 평균 일사를 항상 있는 소스로만 계산 (+1.0%) · 출력 상한 클리핑 · 직전 눈 예보

**검증 방식**: 로컬 채점기(`src/scoring.py`)로 두 해(2024~25, 2023~24)를 모두 확인하고, 앙상블 비율은 반년 교차검증(`src/ensemble_select.py`), 구성은 해를 바꿔 교차 확인한 것만 채택.

### 다음 할 일

- [ ] `ens_v6` (참조 구성 + 발전소 LDAPS + 50:50) — S3 미재현 원인(구성 최적화) 분리
- [ ] 출력제어 대응 (평가연도 괴리 원인 후보) — 봄 휴일 낮 예측 감쇠 등
- [ ] 천리안2A 위성 일사(학습 정답) → 날씨 보정 v2 (MOS)
- [ ] 다른 시드·설정의 발전소/그룹 모델 평균 (분산 감소)
- [ ] 발표용 그림: 오라클 분해, 정보원별 기여, SHAP

---

## 📅 주요 일정

| 항목 | 일시 |
| --- | --- |
| 제출 마감 | **2026.11.13(금) 23:59:59 KST** |
| 코드·발표자료 제출 기한 (요청받은 팀) | **2026.11.23(월)** |
| 예측시점 | 각 대상일 **전날 17:00 KST** |
| 평가 기간 | 8,760시간 (`2025-06-01 01:00` 시작으로 추정) |

---

## 🎯 과제 개요

1. 발전소 253개를 **G1 / G2** 두 그룹으로 나눈다.
2. 평가 기간 8,760시간 동안 각 그룹의 **시간당 발전량(kWh)** 을 예측한다.
3. 그룹 단위로 채점하며, 정산금 S가 큰 순서로 순위를 매긴다.

---

## 📊 평가 기준

### 정산금 S = 매전수익 − 예측 오차 페널티(W)

- 실질적으로는 **오차 페널티 W를 최소화**하는 경쟁입니다.
- 리더보드에는 S(원)가 표시되며, 순위는 S **내림차순**입니다.

### 정산금 계산

```
S = Σ_t SMP(t)·실적(t)  −  0.10 × Σ_g Σ_t SMP(t)·k(t)·|예측(g,t) − 실적(g,t)|
    └──── 매전수익 ────┘     └──────────────── 페널티 W ────────────────┘

k(t) = 3  (ts의 시가 11~15)
     = 1  (그 외)
```

- 매전수익은 253개소 전체 실적 합이라 **구성·예측과 무관한 상수** → 실제 경쟁은 W 최소화
- 평가 구간 k=3 시각은 1,825시간, SMP=0인 시각은 18시간

- **같은 그룹 안에서는** 발전소별 오차가 합쳐지면서 **서로 상쇄될 수 있음**
- **G1과 G2는 따로 계산 후 합산**하므로 그룹 사이의 오차는 상쇄되지 않음
- 출력제어·장애로 줄어든 양도 실적에 그대로 포함되며, 해당 시각은 따로 표시되지 않음
- 평가 실적은 253개소 × 8,760시간이 모두 존재

### 순위 결정

1. 정산금 S가 큰 팀
2. 동점이면 **가중하지 않은 절대오차 합**이 작은 팀
3. 그래도 동점이면 최고 점수 제출 시각이 이른 팀

- 리더보드 점수 = 해당 팀 유효 제출 중 **최고 점수**
- **비공개 리더보드 없음** — 평가 구간 8,760시간 전체를 채점

---

## 🗂️ 제공 데이터

경로: `data/handover 2/01_participant_dataset/` (git 제외). 상세 컬럼 정의는 그 폴더의 `README.md` 참고.

| 파일 | 행 수 | 기간 | 키 |
| --- | --- | --- | --- |
| `sites.csv` | 253 | — | `site_id` |
| `smp.csv` (채점 시각) | 8,760 | 2025-06-01 01:00 ~ 2026-06-01 00:00 | `ts` |
| `train/smp.csv` | 38,688 | 2021-01-01 01:00 ~ 2025-06-01 00:00 | `ts` |
| `train/generation.parquet` | 4,392,566 | 2021-01-19 13:00 ~ 2025-06-01 00:00 | `site_id, ts` |
| `train/forecast_wa.parquet` | 4,710,356 | 학습 구간 | `wa_station, round, ts` |
| `train/forecast_wb.parquet` | 5,621,996 | 학습 구간 | `wb_station, round, ts` |
| `train/observed_wa.parquet` | 2,359,974 | 학습 구간 | `wa_station, ts` |
| `train/observed_wb.parquet` | 2,824,223 | 학습 구간 | `wb_station, ts` |
| `test/forecast_wa.parquet` | 1,068,456 | 평가 구간 | `wa_station, round, ts` |
| `test/forecast_wb.parquet` | 1,278,960 | 평가 구간 | `wb_station, round, ts` |

### 점검 결과 (`src/inspect_data.py`, 집계값만)

- 설비용량 합계 42,655.4 kW → 두 그룹 모두 ≥20,000 kW이므로 **분할 비율은 약 47:53 ~ 53:47 범위로 사실상 고정**
- 참조 구성 `current_group`: A 134개소 / 20,465.7 kW, B 119개소 / 22,189.7 kW
- 용량 분포: 중앙값 99.4 kW, 최대 1,387.5 kW (대형 소수 + 100 kW급 다수)
- 기상 지점: A 61개, B 73개 (`round` 10·17 두 라운드)
- 발전량은 발전소별로 시작 시점이 다름 (최초 기록 연도: 2021년 31 / 2022년 49 / 2023년 68 / 2024년 105개소)
- 발전량 이상치: 음수 40행, 설비이용률 최대 1.034
- 평가 예보 결손: A 264행 (B는 없음) → 대체 필요
- 학습 예보 B: 강수 관련 8개 열 각 1,298행 결측
- `observed_wa`에 키 중복 6건

---

## 📤 제출 파일

### `composition.csv` — 그룹 구성

- 발전소 **253개를 빠짐없이 한 번씩** 포함
- 각 발전소의 그룹은 `G1` 또는 `G2`
- 그룹별 설비용량 = `sites.csv`의 `capacity_kw` 합
- **G1, G2 모두 20,000 kW 이상**이어야 함

### `forecast.csv` — 발전량 예측

- 평가 기간 8,760시간 × 2그룹 = **17,520행**
- `forecast_kwh`에 **음수 · 빈 값 · 무한대 불가**
- 시각에 시간대 표기 필수 — 예: `2025-06-01 01:00:00+09:00`

### 무효 처리

다음 중 하나라도 해당하면 제출이 무효이며, **무효 제출도 횟수에 포함**됩니다.

- 한 그룹의 용량이 20,000 kW 미만
- 발전소 누락 또는 중복
- 시각이 모자라거나 넘침

### 제출 횟수

- 점수가 나오는 제출: **하루 3회, 대회 전체 20회**
- 하루 횟수는 **KST 자정**에 초기화

---

## ⏱️ 시간 규칙

- 시각은 **그 시각에 끝나는 1시간**을 뜻함
  - `2025-05-31 17:00` = 16:00 ~ 17:00의 양
- 강수량·강설량도 누적이 아닌 **그 1시간의 양**
- 학습 데이터의 마지막 7시간(`2025-05-31 18:00` ~ `2025-06-01 00:00`)
  - 학습 표본으로는 사용 **가능**
  - 6월 1일 예측의 **입력으로는 사용 불가**

---

## ✅ 써도 되는 데이터 / ❌ 안 되는 데이터

### 예측시점 (전날 17:00 KST)

| 구분 | 허용 여부 |
| --- | --- |
| 전날 17시 이전에 공개된 값 | ✅ |
| 전날 17시 이전 발표 예보 (대상일 다음 날을 가리키는 값 포함) | ✅ |
| 평가 기간 값이라도 전날 17시 이전에 공개된 것 | ✅ |
| 빈 예보를 전날 17시 이전에 발행된 **다른 예보**로 채우기 | ✅ |
| 평가 기간 1년치 예보를 미리 모아 **정규화** / 그 통계로 **그룹 나누기** | ❌ |
| 평가 기간 **실측 기상**으로 빈 예보 채우기 | ❌ |
| 대상일 당일의 **실제 SMP**를 입력으로 사용 | ❌ (SMP 예측값 또는 전날 17시 이전에 알 수 있는 SMP만) |

### 캘린더 · 위치

- ✅ 요일, 주말, 공휴일, 대체공휴일, 임시공휴일, 선거일
- ✅ 제공된 위경도로 **태양 위치 계산**
- ❌ 좌표로 발전소나 사업자를 **특정**하는 것

### 외부 소스

> 최신 공지 기준으로 **조건부 허용**됩니다.

- 외부 데이터, 코드 패키지, 가중치 없는 모델, **사전학습 모델** 모두 포함
- 허용 조건
  - 자유롭게 공개되어 있고 **상업적 이용이 허용**됨
  - **누구나 같은 주소에서 다시 받을 수 있음** (꾸준히 API 형태로 제공되는 자료 등)
  - **출처와 받는 방법을 기록**해 둘 것
- 사용 불가
  - 올라왔다가 내려간 파일
  - 특정 시점에만 받은 복사본
  - 다시 받아 재현할 수 없는 배포
  - 본인만 가진 파일 (처음에 공개된 적이 있어도 불가)

### 외부 기상을 발전소에 붙이는 방법

- ❌ 발전소마다 다른 격자·관측소를 골라 붙이기
- ❌ 제공된 위경도로 **가장 가까운 점** 고르기
- ✅ 발전소 좌표 없이 **넓은 영역으로 요약**해 **모든 발전소에 같은 값**으로 사용

### 발전 실적

- ❌ 다른 발전소의 **평가 기간** 발전 실적 (이 대회 발전소가 아니어도 불가)
- ✅ 예측시점 이전의 과거 실적 — 공개 · 상업적 이용 가능 · 재다운로드 가능할 때만

### 외부 AI 서비스

- ✅ 코드 작성·분석에 생성형 AI 사용
- ❌ **대회 제공 데이터를 외부 AI 서비스에 넣는 것**
- ❌ 외부 소스를 그 서비스에 올려 대회 데이터와 함께 학습·미세조정하는 것

> ⚠️ 이 저장소에서 AI 코딩 도구를 쓸 때 `data/` 안의 파일 내용이나 데이터 출력(`df.head()` 등)이 AI에 들어가지 않도록 주의합니다.

---

## 👥 참가 자격 및 규정

- 전국 대학(원)생, 개인 또는 팀 (최대 **5명**)
- 여러 팀 **중복 참가 불가**, 계정 중복 생성 시 실격 및 수상 취소
- 계정 중복 및 팀 간 **담합 금지**
  - 제출 결과 유사도가 기준 초과 시 소명 요구, 소명 실패 시 실격
- 최우수상은 **대학생 팀**과 **대학원생 팀** 각 1팀 (대학생 팀은 전원 대학생)
- 시상에는 **발표 평가**가 함께 반영됨
- 사용 가능 언어: **Python, R**
- 제출물의 지적재산권은 참가자에게 있으며, 주최 기관은 수상작에 대한 사용권을 가짐

---

## 📦 코드 및 발표자료 제출

| 항목 | 내용 |
| --- | --- |
| 제출 대상 | 리더보드 상위 7개 팀 (필수) + 요청 시 장려상 수상 팀 |
| 제출물 | 코드 (`.py`, `.ipynb`, `.R`, `.rmd`), 발표자료 (`.pdf`, `.pptx`) |
| 코드 요건 | 전처리 → 학습 → 추론을 **다시 실행할 수 있어야** 함 |
| 제출 기한 | **2026.11.23(월)** |
| 제출처 | competition@dershare.xyz |

---

## 📁 프로젝트 구조

```
.
├── data/          # 대회 제공 데이터 (git 제외)
├── notebooks/     # EDA 및 실험 노트북
├── src/           # 전처리 / 학습 / 추론 코드 (위 "코드 구조" 참고)
├── outputs/       # 발전소별 예측 parquet (git 제외)
├── submissions/   # composition_*.csv, forecast_*.csv (git 제외)
├── SUBMISSIONS.md # 제출 기록
└── README.md
```

> 제공 데이터는 대회 목적 외 사용이 금지되므로 `data/`는 `.gitignore`로 저장소에서 제외합니다.

### 환경 설정

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

대회 페이지에서 받은 `OIBC_2026_DATA.zip`을 저장소 루트에 풀어 `data/handover 2/01_participant_dataset/`가 되게 둡니다.

```bash
.venv/Scripts/python.exe src/inspect_data.py          # 데이터 무결성 점검
.venv/Scripts/python.exe src/scoring.py --pred P.parquet   # 검증 구간 정산금 계산
.venv/Scripts/python.exe src/validate_submission.py --composition C.csv --forecast F.csv   # 제출 형식 검사
```

## 🤝 팀 규칙

- **데이터·예측값은 절대 커밋하지 않기** (`.gitignore`로 막혀 있음 — 공개 저장소)
- **대회 데이터를 외부 AI 서비스(ChatGPT, Claude 등)에 붙여넣지 않기** — 코드만 AI에 보여 주고, 실행·확인은 로컬에서
- 외부 소스를 쓰면 아래 "외부 소스 기록" 표에 출처와 받는 방법을 추가
- 작업은 브랜치를 따서 PR로 합치기

### 외부 소스 기록

| 이름 | 출처 URL | 받는 방법 | 라이선스 (상업적 이용) | 비고 |
| --- | --- | --- | --- | --- |
| Open-Meteo Previous Runs API — JMA Seamless, ECMWF IFS 0.25°, GFS Seamless 의 `shortwave_radiation_previous_day2`, `cloud_cover_previous_day2` | https://previous-runs-api.open-meteo.com/v1/forecast (문서 https://open-meteo.com/en/docs/previous-runs-api) | `python src/fetch_external.py` → `data_ext/` | 데이터 CC BY 4.0 (https://open-meteo.com/en/licence). 무료 API 는 비상업 조건 → **운영진 문의 중** | 유효시각 48시간 전 발행분만 사용 (전날 00시 이전 발행). 한반도 고정 격자 25점(위도 34.75~37.75, 경도 126.5~129.5, 0.75° 간격), 발전소 좌표 미사용, 모든 발전소에 같은 값 |
| **NOAA GFS 0.25°/1° 원본** — `DSWRF:surface`, `TCDC:entire atmosphere` (구간 평균) | https://noaa-gfs-bdp-pds.s3.amazonaws.com (https://registry.opendata.aws/noaa-gfs-bdp-pds/) | `python src/fetch_gfs.py` → `data_ext/gfs_hourly.parquet` | 미국 정부 공개 데이터 (NOAA Open Data, 상업 이용 제한 없음) | **D-1 00 UTC 실행분만** (보통 D-1 03~05 UTC 공개 < 마감 08 UTC), 리드 16~39h. 한반도 고정 상자(34~38°N, 126~129°E) 평균 하나, 발전소 좌표 미사용 |
| **NOAA GEFS 0.5°** — 앙상블 평균(`geavg`)·표준편차(`gespr`)의 DSWRF, TCDC | https://noaa-gefs-pds.s3.amazonaws.com (https://registry.opendata.aws/noaa-gefs/) | `python src/fetch_gefs.py` → `data_ext/gefs_hourly.parquet` | 미국 정부 공개 데이터 | GFS 와 같은 규칙 (D-1 00z, 고정 상자 평균) |
| **기상청 UM 국지모델(UMKR = LDAPS 1.5km)** — 지면 하향단파 `4200`, 직달 `4198`, 산란 `4199` | https://apihub.kma.go.kr/api/typ06/url/um_grib_pt_tmfc.php (API허브 → 수치모델 → 10.4, 공공데이터포털 15139467) | `python src/fetch_kma.py --um` (`.env` 의 `KMA_API_KEY`, 본인 키) | **공공누리 제1유형** (출처표시, 상업 이용 가능). 출처: 기상청 | **D-1 00 UTC 실행만**, 리드 15~39h, 고정 5지점 평균. UM 은 2026-03-31 생산 종료 → 평가 기간 마지막 2개월은 다른 소스로 대체. API 약관: 하루 20,000건·5GB, 단일 키 |
| 천리안2A 위성 하향단파복사(DSR) | https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph_sun_sat_txt (산업특화 → 태양광 5번) | `python src/fetch_kma.py --sat` | 공공누리 제1유형 | **학습 구간 정답(날씨 보정 타깃)으로만** 사용, 예측 입력 아님 |
| LightGBM, XGBoost, CatBoost, pandas, numpy, pyarrow, scikit-learn, scipy(HiGHS), optuna, holidays, eccodes | PyPI | `requirements.txt` | MIT / BSD / Apache-2.0 | |

---

## ☑️ 제출 전 체크리스트

### 파일 형식
- [ ] 253개 발전소가 한 번씩 들어가 있는가
- [ ] G1, G2의 설비용량이 각각 20,000 kW 이상인가
- [ ] 예측이 17,520행이고, 음수·빈 값·무한대가 없는가
- [ ] 시각에 `+09:00` 시간대가 붙어 있는가

### 데이터 누수
- [ ] 각 날짜에 전날 17시 이후에 생긴 값을 쓰지 않았는가
- [ ] 평가 기간 전체 예보로 정규화하거나 그룹을 나누지 않았는가
- [ ] 대상일 실제 SMP를 입력으로 쓰지 않았는가
- [ ] 마지막 7시간 실적을 6월 1일 예측의 입력으로 넣지 않았는가
- [ ] 평가 기간 실측이나 다른 발전소의 평가 기간 실적을 쓰지 않았는가

### 외부 소스 · AI
- [ ] 외부 소스가 공개되어 있고 상업적 이용이 되는가
- [ ] 누구나 같은 주소에서 다시 받을 수 있는가 (한 번만 공개된 자료·개인 복사본 아님)
- [ ] 외부 기상을 발전소 좌표로 나눠 붙이지 않았는가
- [ ] 대회 데이터를 외부 AI 서비스에 담지 않았는가
- [ ] 코드를 다시 실행할 수 있게 출처와 절차를 적어 두었는가
