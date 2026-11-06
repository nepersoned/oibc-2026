# SM#37-A — noext 발전소별 예측 2개 연도 재생성

승인된 Python 3.11 실행기와 기존 `.venv/Lib/site-packages`를 사용해 noext rich 모델을 실제 재학습했다. 환경변수는 `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`이며 `ext=none`, `train-years=2`, `--drop-features site_code`, `random_state=7`, reference composition을 고정했다.

```powershell
$env:PYTHONPATH = (Resolve-Path .venv\Lib\site-packages).Path
$env:OIBC_EXT_SOURCES = "no_openmeteo"
$env:OIBC_SPATIAL = "none"
$env:OIBC_PHYSICS = "none"
$py = "C:\Users\ehfal\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe"
& $py src/pipeline.py --mode val --fset rich --ext none --train-years 2 --drop-features site_code --params '{"random_state":7}' --val-start 2023-06-01 --val-end 2024-06-01 --tag sm37_noext_repro
& $py src/pipeline.py --mode val --fset rich --ext none --train-years 2 --drop-features site_code --params '{"random_state":7}' --val-start 2024-06-01 --val-end 2025-06-01 --tag sm37_noext_repro
```

| 항목 | 2023~24 | 2024~25 |
|---|---:|---:|
| 학습 행 수 | 961,115 | 1,933,922 |
| 평가 시간 수 | 8,784 | 8,760 |
| 관측 평가 발전소 수 | 253 | 253 |
| 관측 site-hours | 1,256,595 | 2,170,645 |
| 예측 파일 행 수 | 2,222,352 | 2,216,280 |
| Reference W | 107,999,596원 | 201,164,873원 |
| 학습 성공 | 예 | 예 |

2023~24는 윤년 2024-02-29를 포함해 8,784시간이다. 두 파일 모두 예측 키 중복 0, 관측 실적 행 예측 누락 0, NaN/Inf/음수 0이다. 2024~25 W는 기존 noext 기록과 일치했다. 2023~24 W는 현재 환경에서 생성한 유효 결과이며, 이전 구성 최적화의 W=0은 빈 입력에 의한 무효 계산이었다.

SHA256:

- `outputs/val_sm37_noext_repro_2023_sites.parquet`: `c346a74ba7ecd8ac8495c3700256bfcc3288621b829e9cacd61d32d9f7fd8da6`
- `outputs/val_sm37_noext_repro_sites.parquet`: `1bee1c8c58083c4cd25bfdb77ce414e1d573a62130ebada75df964ea73257241`

예측 Parquet은 Git에 추가하지 않는다. 상세 결과는 반복 사용된 연구 검증 구간이며 독립적인 최종 테스트나 제출기간 성능을 의미하지 않는다.
