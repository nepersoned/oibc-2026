# SM42 최종 결정

SM42 F3 3-seed는 2024 점 추정이 개선됐지만 2023 W가 SM41보다 높고 2024의 paired bootstrap 95% 상한이 양수다. 지정된 시간순 채택 조건을 충족하지 못하므로 **SM41 기존 피처 3-seed + SM39 그룹 alpha=0.2**를 유지한다. F4는 2023 seed7 선택에서 기각. F5·L1·F4 2024/다중시드 및 새로운 제출기간 학습은 실행하지 않았다. F2의 더 낮은 2024 W를 사후 재선택하지 않았다.

SM41의 기존 두 제출 파일을 보존한 채 byte-identical 사본을 `submissions/composition_sm42_final.csv`, `submissions/forecast_sm42_final.csv`로 만들었다. `src/validate_submission.py` 종료 0, 253 사이트, G1 134개 20,465.655kW, G2 119개 22,189.715kW, 8,760 KST 시각×2그룹=17,520행 및 유효성 검사 통과. 구성 SHA256 `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd`, 예측 SHA256 `ed9d14e194259971802ef1e1530f0bd38b05455cf3ca66a7815abaedbd63fd8d`이며 SM41 원본의 해시와 같다. SM41은 이전 작업에서 full-grid 재배분 보존 및 저장 후 재로드를 검사했다. 제출기간 실적이 없어 실제 W는 알 수 없다. 공식 포털 업로드는 하지 않았다.
