# predictions — 검증 예측 · 제출 파일

| 폴더 | 내용 |
| --- | --- |
| `val_2023-24/` | 2023-06-01 01:00 ~ 2024-06-01 00:00 검증 예측 (ens_v12 구성, 학습은 그 이전 4년) |
| `val_2024-25/` | 2024-06-01 01:00 ~ 2025-06-01 00:00 검증 예측 (같은 구성) |
| `submissions/` | 리더보드에 제출한 파일 (ens_ref, v3, v5, v7, v9, v9b, v12, v13). 점수는 [SUBMISSIONS.md](../SUBMISSIONS.md) |

검증 CSV 열: `group`, `ts`, `forecast_kwh` (앙상블 = 발전소 모델 0.505 + 그룹 모델 0.495), `site_model_kwh` (site_dv 발전소별 예측의 그룹 합), `group_model_kwh` (l1umx+파생 그룹 모델). 그룹은 참조 구성(G1=A, G2=B). 실적값은 포함하지 않음.
