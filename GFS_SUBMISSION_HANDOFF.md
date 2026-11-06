# GFS 제출기간 복구 인계

## 1. 필요한 실행 날짜

공식 제출 시간축은 2025-06-01 01:00 KST부터 2026-06-01 00:00 KST까지 8,760개다. `fetch_gfs.py`의 대상일 규칙은 대상일 D에 D-1 00 UTC 실행을 사용하므로 필요한 초기화 날짜는 2025-05-31부터 2026-05-30까지다. 2026-06-01 00:00 KST는 2026-05-31 대상일의 마지막 시각이며, 해당 대상일의 D-1 실행인 2026-05-30 00 UTC가 마지막 필요 실행이다.

## 2. 현재 캐시와 누락 범위

기존 `data_ext/gfs_hourly_partial_full.parquet`는 2021-01-01 01:00 KST부터 2025-06-02 00:00 KST까지다. 제출기간 전체 2025-06-01~2026-06-01을 제공하지 않으며, 2025-05-31~2026-05-30 초기화 원자료를 별도 확보해야 한다. 기존 연구용 캐시와 `data_ext/gfs_hourly.parquet`는 덮어쓰지 않는다.

## 3. 복구 명령

ecCodes DLL을 허용하는 승인된 Linux 또는 Windows 개발 환경에서 저장소 루트에서 실행한다.

```powershell
python src/fetch_gfs.py `
  --start 2025-05-31 `
  --end 2026-05-30 `
  --workers 24 `
  --raw-dir data_ext/gfs_submit_raw `
  --out data_ext/gfs_submit_hourly.parquet
```

현재 작업 트리의 `--raw-dir`와 `--out`은 기존 기본 경로를 유지하면서 제출 전용 경로를 선택한다. 실패 날짜와 불완전 `.npz`는 성공으로 취급하지 않도록 수집기 검증을 추가한 뒤 실행해야 한다.

## 4. 원본 메시지와 공간 처리

각 날짜의 NOAA GFS `gfs.t00z.pgrb2.1p00.f015`부터 `f039`까지의 `.idx`를 조회하고 DSWRF surface 및 TCDC entire atmosphere의 `ave fcst` 메시지만 byte range로 요청한다. 영역은 위도 34~38°N, 경도 126~129°E의 고정 5×4 격자이며 발전소 좌표를 사용하지 않는다. `gfs_ghi`, `gfs_kcs`, `gfs_tcc`를 계산해 모든 발전소에 동일하게 제공한다.

생성 Parquet의 최소 컬럼은 `ts`, `gfs_ghi3`, `gfs_ghi`, `gfs_kcs`, `gfs_tcc`다. `ts`는 Asia/Seoul 시간대여야 하며 8,760개 제출 시각과 정확히 일치해야 한다.

## 5. 학습 캐시 결합

기존 학습 Parquet와 제출 Parquet를 pandas로 읽어 `ts` 기준으로 결합한다. 중복 시각은 초기화일과 원본 메시지를 확인한 뒤 하나만 남기고, 기존 학습기간 값은 변경하지 않는다. 제출용 결합 파일은 별도 경로에 저장한다. `features.py`에서 제출 실행에만 해당 경로를 선택하도록 `OIBC_GFS_PATH` 같은 환경변수를 사용할 수 있으며 기본 경로 동작은 유지한다.

## 6. 검증 절차

`smp.csv`의 제출 시간축과 left join해 8,760행인지 확인한다. 낮 시간대의 `gfs_ghi`와 전체 `gfs_tcc` 결측률, 일별 누락, 첫 시각·마지막 시각을 출력한다. 각 날짜의 `init`이 대상일 전날 00 UTC인지 확인하고, 동일 실행분의 리드 16~39시간이 사용됐는지 검사한다. HTTP 200 또는 다운로드 성공만으로 D-1 17:00 KST 이전 공개를 입증할 수 없으므로 NOAA 아카이브 공개시각 근거는 별도 수집해야 한다.

## 7. 현재 차단 원인

승인된 Python 3.11에서는 pandas, pyarrow, lightgbm을 기존 site-packages와 함께 사용할 수 있다. uv 독립 환경에 `eccodes 2.50.0` 설치는 가능했지만 `_eccodes` 네이티브 DLL import가 Windows 애플리케이션 제어 정책으로 차단됐다. 정책을 비활성화하거나 우회하지 않는다. 따라서 ecCodes가 정상 동작하는 승인된 Linux/WSL 또는 팀 개발 환경에서 위 명령을 실행해야 한다.

NOAA GFS의 상업적 이용 조건, 과거 자료의 실제 공개시각, 대회 D-1 17:00 KST 조건은 현재 전 기간 증빙이 미완료다. Open-Meteo 무료 API 자료는 사용하지 않는다.
