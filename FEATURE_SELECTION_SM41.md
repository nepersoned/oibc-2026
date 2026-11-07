# SM41 feature selection

사전 고정: `SM41_PREREGISTRATION.md`. F2만 선별했다. WA와 WB의 `ghi_cs × [1 − 0.75 × (clip(cloud,0,100)/100)^3.4]`는 동일 발행 예보와 태양기하에서 계산한 proxy이고, 실제 GHI 관측이 아니다. 2023 선택 기간 site+group W 107,551,309→107,305,580원(-0.228%)이어서 고정 수식으로 2024를 1회 평가했다. 2024 W 198,736,384→197,450,676원(-0.647%), 11–15시 163,878,324→163,225,430원이다. G1/G2는 각각 94,445,389→93,860,343원, 104,290,995→103,590,333원이다.

2024 paired moving-block bootstrap 168시간, 5,000회, seed 7에서 95% CI는 [-3,410,128, +631,194]원으로 0을 포함한다. 2024 완전한 월 기준 최대 악화는 2025-04 +1.42%, 2023은 2024-04 +4.15%다. 2025-06의 단일 자정 시각은 완전한 월이 아니다. 따라서 두 연도 점 추정은 개선이나 지정된 불확실성 기준을 통과하지 못했다. F2는 현재 최종 채택하지 않는다. 선택 과정과 과거 반복 사용된 2024를 고려하면 이 CI에도 선택편향이 남는다.

2023 학습 로그 gain 상위 15에 WA proxy 1위, WB proxy 12위가 있었고, 2024에서는 WA proxy가 1위였다. 개별 중요도의 정량값·SHAP·블록 permutation 및 F2 내부 단독 제거는 아직 측정하지 않았으며, 어느 단일 proxy가 개선을 유발했는지 주장할 수 없다. 다른 F1/F3/F4/F5/F6는 무효가 아니라 미실험이다. 2023 실적 관측률 56.55%, G2 학습 타깃이 없는 SM39 집계 모델, 2024 관측률 97.94% 및 반복 사용이라는 한계가 있다. 파일 `outputs/sm41/comparison.json`, 월별 CSV와 시간별 예측 페널티에 결과·입력 SHA256을 저장했다.

## 재현 및 검증

SM41 실행 코드는 `src/analysis/sm41_cloud_experiment.py`, 시간순 스크리닝과 비교는 `sm41_screen.py`, `sm41_compare.py`; 다중 시드는 `sm41_seed_runner.py`, `sm41_feature_seed_runner.py`와 `sm41_four_way.py`다. 각각의 예측과 결과는 Git 제외 `outputs/sm41/`와 기존 outputs에 있고, 예측 SHA256과 실행 명령 manifest가 있다. 원본 데이터와 모델·대량 예측은 Git에 포함하지 않는다. `python -m compileall -q src tests` 성공, 관련 테스트 4개 통과. 전체 pytest 40통과·3실패: 기존 SM40에 기록된 `test_export_gfs_partial` 2개와 `test_gfs_time_conversion::test_build_hourly_synthetic_day` 1개가 동일하게 실패했다. 이 세 테스트는 SM41 변경과 무관한 GFS 기간 격자 불일치다.

## Multi-seed 후 최종 선택

SM40 대비 F2 3-seed는 2023 -0.452%, 2024 -0.938%, 2024 bootstrap 95% [-3,519,169,-360,498]원으로 수치 채택 기준을 충족한다. 그러나 F2를 기존 피처 3-seed에 더한 변화가 2023 +310,364원 악화, 2024 -662,052원 개선이어서 시간순으로 일관된 증분 이득을 보여주지 못했다. 2023에서 더 낮은 W를 낸 기존 피처 3-seed를 최종 후보로 택하고 F2는 후속 시간순 검증 대상으로 보류한다. 이 결론은 단일 F2 seed의 높은 gain 자체와 별개다. SHAP·permutation 및 피처별 개별 ablation은 미실시다.
