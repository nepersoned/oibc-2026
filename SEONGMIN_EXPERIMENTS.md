# 오성민 개인 실험 기록

기준 커밋 `a5c7247`; 공식 최고는 JH#29/S2 `ens_v3`. 데이터와 예측은 Git에 넣지 않는다. 실험 커밋은 아래 기록 다음 커밋의 부모/이력을 확인한다.

## 사전 채택 기준 (실험 전 고정)

동일 관측 집합과 공식 식에서 W가 감소하고, 시계열상 가중치 선택 이후의 평가 구간과 다른 연도 양쪽에서 감소해야 한다. 날짜별 7일 블록 부트스트랩 95% 신뢰구간의 W 차이(후보−기준) 상한은 0 미만이어야 한다. 어느 월에서도 W가 기준 대비 5% 넘게 악화되면 채택하지 않는다(기준 W가 0인 달은 별도 검토). 최소 두 시드와 제출 형식·데이터 공개시점·누수 점검을 통과해야 한다. 반복 사용한 두 검증 연도는 완전한 독립 테스트가 아니다. 위 조건을 충족해도 공식 LB 개선을 보장하지 않는다.

| ID | 가설 / 기존과의 차이 | 데이터·기간 | W / ΔW / 월별 | 판정 |
|---|---|---|---|---|
| SM#1 | ens_v3를 동일 입력과 CV로 재현 | 대회 데이터는 로컬 압축파일 존재. 외부 예보 및 기존 예측 산출물 없음; 2023-06~2025-05 | 미산출 | 차단: 예보 출처의 실제 공개 시점·사용 조건, KMA 키 및 재현 입력 필요 |
| SM#2 | 총량/형태 오라클과 구조적 하한을 동일 관측 집합으로 비교 | ens_v3 그룹 예측 및 동일 실적/SMP 필요 | 미산출 | 미검증: 입력 예측 부재. 합성 데이터 단위 테스트만 수행 |

SM#2 재현: `python src/analysis/settlement_decomposition.py --pred-group outputs/val_ens_v3_group.parquet --start 2024-06-01 --end 2025-06-01` (각 그룹·시각의 `pred`는 실적 관측 발전소 범위에 맞춘 값이어야 한다). 출력은 로컬 화면에만 표시하며 입력·결과는 Git에서 제외한다. 오라클은 사후 실적을 사용하므로 진단 전용이다. 실험 커밋 ID는 `git log -- SEONGMIN_EXPERIMENTS.md`로 확인한다.

## SM#3 — 데이터 배치 및 기준 모델 실행 점검 (미검증)

- 가설: 대회 데이터만 사용하는 기존 2년 기준 파이프라인을 실행해 로컬 학습·채점 환경을 확인한다. 이는 ens_v3 재현 또는 개선 실험이 아니다.
- 데이터: 다운로드의 `OIBC_2026_DATA.zip`을 Git 제외 `data/handover 2/01_participant_dataset/`에 추출했다. 학습 발전량·학습 및 평가 기상 예보·SMP·발전소 파일의 존재를 확인했다. 원본과 예측을 커밋하지 않았다.
- 학습/평가: 설정상 2022-06~2024-05 학습, 2024-06~2025-05 평가. 실제 학습 전에 실패했으므로 관측 커버리지, W, ΔW, 월별 성능은 미산출이다.
- 명령: `.venv\Scripts\python.exe src/pipeline.py --mode val --tag sm_baseline --train-years 2`. 설치한 Python 3.11 환경의 pandas 네이티브 확장 로딩이 Windows 애플리케이션 제어 정책에 차단되어 `ImportError: DLL load failed ... application control policy`로 종료됐다. 상세 로그는 Git 제외 `outputs/sm_baseline_environment.log`. 시스템 정책을 우회하지 않는다.
- 별도의 기존 Python 환경은 pyarrow가 없었다. Codex 제공 Python은 pandas·numpy는 있으나 pyarrow·scipy·lightgbm이 없다. 기존 출처의 설치 파일을 관리자가 승인하거나 허용된 환경을 제공해야 한다.
- ens_v3 입력인 `data_ext/openmeteo_ecmwf_ifs025.parquet`, `openmeteo_jma_seamless.parquet`, `openmeteo_gfs_seamless.parquet`, `openmeteo_jma_extra.parquet`, `gfs_hourly.parquet`, `kma_um_hourly.parquet`와 기존 ens_v3 예측/모델은 로컬 검색 범위에서 찾지 못했다. `.env` 또는 환경 변수에 KMA 키가 설정됐는지 여부만 확인했고 키 값은 읽거나 출력하지 않았다.
- 누수·규정: 데이터 원본은 로컬에만 두고 외부 수집은 실행하지 않았다. 예보 발행과 실제 이용 가능시각, Open-Meteo 이용 조건과 LDAPS 복구는 미확인이다. 타임스탬프 단위의 누수 검사와 제출 형식 검사는 실행할 예측이 없어 미완료다.
- 판정: **미검증**. 예측 파일이 없으므로 일별 오라클과 구성 과적합 검증도 수행하지 않았다. 재개 순서: 승인된 학습 환경 → 소스 조건과 외부 기상 자료 확보 → ens_v3 두 연도 재현 → 사후 진단 및 시간순 구성 평가.
