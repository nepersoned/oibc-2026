# SM#68 Peak Delta Transfer to JH ens_v12

## 판정: 입력 정합성 일부 확인, 점수 계산 전 중단

SM67의 피크 전문가가 만든 증분만 JH ens_v12에 이전하는 2024–25 파일럿을 준비했다. **모델은 학습하지 않았고, 혼합 배율 탐색·제출 파일 생성·포털 제출은 하지 않았다.** 현재 실행 환경에서 SM67 Parquet를 읽지 못해 delta의 행 정합성 및 W를 계산할 수 없었다. 결과적으로 사전 고정 2024 게이트를 판정할 수 없으므로 bootstrap과 2023 평가는 실행하지 않았다.

## 고정한 기준과 입력 계보

- 시작 브랜치/HEAD 확인: `seongmin` / `e0ddee1420903b9881d2ab7149a36649e63d2872` (요구값과 일치)
- 읽기 전용 JH 기준: `origin/main` = `793f5f6662f074dbc8e50d3b0f925b9b214c3683` (요구값과 일치)
- JH 검증 CSV는 `git show origin/main:<path>`로 해당 커밋에서 읽었다. 2024 파일 SHA256 `58388ca4328444443812116176cafdf07584f944e0ede11208524b39b95e233e`; SM56 기록과 일치.
- JH composition SHA256 `933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463`; SM56 기록과 일치. 로컬 `sites.csv`의 reference 구성과 253개 사이트 배정이 같은 것을 확인했다. 자동 그룹 변환은 하지 않았다.
- JH CSV의 필수 열, 중복 `(group, ts)` 키, 유한 예측값을 스크립트가 확인했다. SM56 정렬 감사에는 2024–25의 17,520행, 두 그룹 × 8,760시각 및 2024-06-01 01:00–2025-06-01 00:00 KST가 기록돼 있다.
- SM67 2024 A/B Parquet의 실제 SHA256은 각각 `6544136f63ab9236926b61f21e4a129e9cc04ca2d4480288b460d65452fce9` 및 `5b306a657002e675e8908496208e388cc8ebe97df22ca880315029a5cbec9767`. `outputs/sm67/result_2024.json`에 기록된 해시와 일치한다.
- 2023 SM67 파일도 로컬 해시는 각각 `fb13f95768ba5805b91b05903691139e4fc34f99f6feb5435087468f906526c8` 및 `5f34709128c976cf9a76ea40c93de4b7ffe8db05504654696b5b4113ffde09d5`였으나, 2024 선행 게이트 미통과로 내용을 읽거나 분석하지 않았다.

SM56은 SM 예측 전체를 JH와 고정 비율로 섞었다. SM68은 그 방식과 다르게 `SM67 candidate − SM67 baseline` delta만 추출해 0.505를 한 번 적용하도록 고정했다. SM67 후보 자체가 이미 해당 시간의 50:50 피크 전문가 혼합이므로 delta에 추가 0.5를 곱하지 않는다. 지원 시각 밖에는 JH 원본을 보존하고, 피크에만 0 미만 하한을 적용하도록 구현했다.

## 실행 결과 및 차단 지점

| 점검/지표 | 결과 |
|---|---|
| seongmin 및 origin/main SHA | 통과 |
| JH 2024 CSV SHA/schema/중복/유한값 | 통과 |
| JH composition SHA 및 reference 배정 | 통과 |
| SM67 A/B 파일 SHA | 통과 |
| SM67 A/B `(site_id, ts)` 키, 253개 사이트/시각, 비피크 delta 0 | **Not Run** — Parquet를 읽지 못함 |
| 2024 W A/B, G1/G2, peak/nonpeak, 월별 | **Not Run** |
| 2024 전체 개선율 ≥0.5% 및 양 그룹 개선 게이트 | **판정 불가** |
| 168시간 paired bootstrap | **Not Run** — 게이트 판정 불가 |
| 2023 observed-mask 진단 | **Not Run** — 2024 게이트 불통과/미판정 |

기본 Python은 pandas 3.0.3이지만 `pyarrow`와 `fastparquet`가 없어 `read_parquet`에서 중단했다. 저장소 `.venv`에는 pandas/pyarrow가 있으나 pandas C 확장 모듈을 Windows Application Control이 차단해 해당 인터프리터로 읽는 것도 실패했다. 이를 우회하거나 예측을 재생성하지 않았다. 기존 SM56의 2024 JH 기준 common-mask W는 167,076,206원으로 기록돼 있지만, SM68 실행에서 이를 새로 재계산해 대조하지 못했다. SM56이 기록한 JH 원 실험 W 167,041,881원과의 +34,325원 차이는 기존 감사에서 원인이 미확정이다.

따라서 SM67 전체 site-grid 완전성, 지원 타임스탬프, 실제 변경 행·클리핑 건수, delta 통계 및 후보 W에 관한 수치를 만들지 않았다. SM67의 기존 결과(2024 SM 기준 A/B 차이)는 SM68의 JH 이전 효과가 아니므로 이 보고서의 점수로 대체하지 않는다.

## 재현 코드 및 확인

- 분석: `src/analysis/sm68_peak_delta_transfer.py`
- 순수 delta 이전 규칙 단위 점검: `tests/test_sm68_peak_delta_transfer.py` (2개 직접 실행 통과)
- `python -m compileall` 대상 파일 확인 통과
- pytest는 현재 기본 Python에 설치되어 있지 않다. 저장소 `.venv`의 pytest는 pandas C 확장 실행 차단 때문에 이 환경에서 사용하지 못했다.
- 전체 Parquet 분석은 실행하지 못했으므로 이 산출물은 완료된 성능 실험이 아니라, 입력 파일 해시를 확인하고 실패 시 중단하는 재현 스크립트와 차단 보고서다.

**결정:** SM67 peak delta가 ens_v12에 추가 가치를 주는지 현재 증거로 판정하지 않는다. 계수·모델을 바꾸지 말고, 동일 아티팩트로 Parquet 읽기가 가능한 승인된 Python 환경에서 2024 선행 게이트부터 재실행해야 한다. GFS 조건부 적격성은 SM58의 기존 CONDITIONAL 상태를 유지한다.
