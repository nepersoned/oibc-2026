# SM#44 Group Target Coverage & Training Reliability

## 1. Result and experiment gate

SM#44 did **not** train G1 or G2. The preregistered support gate failed on the 2023 training window before candidate fitting. G1 (`min_cov=0.1`, weight=`coverage²`) has zero G2 labels; G2 (`min_cov=0.5`) has zero labels for both groups. The pre-registered minimum was 200 rows per group and 100 daylight rows per group in each training window. The thresholds were not lowered and the CF target was not changed.

Therefore there are no candidate W values, month results, prediction correlations, or confidence intervals for G1/G2. The proper recommendation remains **SM#41**, subject to the holiday-data rules issue in §7. No submission-period fit or CSV was made, and no portal upload occurred.

Coverage audit code and machine-readable results:

- `src/analysis/sm44_coverage_audit.py`
- `outputs/sm44/coverage_audit.json`
- `outputs/sm44/coverage_threshold_counts.csv`

The preregistered hypotheses and gate are in `SM44_PREREGISTRATION.md`.

## 2. Label definition and full-window coverage

`src/agg_model.py::targets()` computes group-hour `act = sum(observed site generation)`, `cap_avail = sum(capacity of reporting sites)`, `coverage = cap_avail / full reference-group capacity`, and `CF = act / cap_avail`. Its threshold then removes rows below `min_cov`. The Group fit is a single LightGBM over the retained group-hour rows, with a G2 indicator; a missing group in training leaves no direct label support for that indicator.

Coverage quantiles below include every group-hour in each two-year training window, assigning zero when no site in that group reported. `p10/p50/p90` are the 10th, 50th and 90th percentiles.

| Evaluation window | Group | Mean | p10 | p50 | p90 | p95 | Max |
|---|---|---:|---:|---:|---:|---:|---:|
| 2023–24 | G1 | 0.196 | 0.089 | 0.147 | 0.379 | 0.397 | 0.407 |
| 2023–24 | G2 | 0.013 | 0.000 | 0.017 | 0.026 | 0.026 | 0.026 |
| 2024–25 | G1 | 0.510 | 0.199 | 0.407 | 0.875 | 0.875 | 0.941 |
| 2024–25 | G2 | 0.112 | 0.017 | 0.026 | 0.397 | 0.414 | 0.626 |

There were 17,520 group-hours per group in the 2023 training window and 17,544 in the 2024 window (leap year). G1 had some reporting in every hour in both windows. G2 had reporting in 11,894/17,520 hours in 2023 and 17,544/17,544 in 2024, but its reported capacity was extremely low in 2023.

## 3. Eligible label counts and day/night split

Daylight uses the existing Group-model rule `solar elevation > -2°`; night is the remaining group-hours. Counts are based on training-window data only.

| Window | Group | Coverage threshold | Eligible labels | Daylight | Night |
|---|---|---:|---:|---:|---:|
| 2023–24 | G1 | 0.1 | 15,254 | 7,722 | 7,532 |
| 2023–24 | G1 | 0.3 (G0) | 3,562 | 1,829 | 1,733 |
| 2023–24 | G1 | 0.5 | 0 | 0 | 0 |
| 2023–24 | G2 | 0.1 / 0.3 / 0.5 | **0 at all three** | 0 | 0 |
| 2024–25 | G1 | 0.1 | 17,544 | 9,099 | 8,445 |
| 2024–25 | G1 | 0.3 (G0) | 12,346 | 6,386 | 5,960 |
| 2024–25 | G1 | 0.5 | 8,005 | 4,071 | 3,934 |
| 2024–25 | G2 | 0.1 | 5,746 | 2,794 | 2,952 |
| 2024–25 | G2 | 0.3 (G0) | 2,889 | 1,538 | 1,351 |
| 2024–25 | G2 | 0.5 | 349 | 219 | 130 |

### Why 2023 G2 has no `min_cov=0.3` rows

It is not an edge effect of the 0.3 cutoff: G2's maximum coverage in the entire 2023 training window is only 0.0261 (2.61%), below even the proposed G1 threshold 0.1. Only 6 of the 119 G2 sites have any generation rows in that window. Five of those six contribute 92.8% of the observed G2 capacity exposure. The available observations thus cover at most about 2.6% of full G2 capacity and are concentrated among very few sites. No `min_cov` choice among the preregistered 0.1/0.3/0.5 candidates can supply 2023 G2 training labels.

By 2024's training window, 75 G2 sites have some reported rows. Coverage reaches 0.626 at its maximum, enough to yield 2,889 G0 labels at 0.3, but only 349 labels at 0.5. The sharp shift reflects changed reporting coverage in the supplied generation data, not a model change.

## 4. CF distribution and coverage relationship

CF summaries below are for eligible group-hours after each threshold. CF is a fraction; its target remains observed generation divided by capacity of reporting sites.

| Window | Group | Threshold | Mean CF | Median CF | p90 CF | Std CF |
|---|---|---:|---:|---:|---:|---:|
| 2023–24 | G1 | 0.1 | 0.162 | 0.0036 | 0.574 | 0.235 |
| 2023–24 | G1 | 0.3 | 0.168 | 0.0058 | 0.601 | 0.244 |
| 2023–24 | G1 | 0.5 | — | — | — | — |
| 2024–25 | G1 | 0.1 | 0.154 | 0.0061 | 0.542 | 0.223 |
| 2024–25 | G1 | 0.3 | 0.155 | 0.0060 | 0.551 | 0.226 |
| 2024–25 | G1 | 0.5 | 0.145 | 0.0043 | 0.526 | 0.215 |
| 2024–25 | G2 | 0.1 | 0.146 | 0.0018 | 0.544 | 0.225 |
| 2024–25 | G2 | 0.3 | 0.172 | 0.0106 | 0.616 | 0.249 |
| 2024–25 | G2 | 0.5 | 0.236 | 0.0694 | 0.700 | 0.281 |

Coverage and CF Pearson correlations across reported group-hours were close to zero: 2023 G1 `+0.003`, G2 `−0.045`; 2024 G1 `−0.032`, G2 `+0.017`. This does not establish coverage independence; it only shows a weak linear relation in these two observed windows. CF is zero-heavy (for example, G1 median CF is below 0.006 at threshold 0.3), while the means are much higher.

## 5. Site representation and scaling mismatch

Across all generation rows in the window, the top one and top five sites' shares of observed capacity exposure were:

| Window | Group | Sites with any records | Top 1 share | Top 5 share | Exposure HHI |
|---|---|---:|---:|---:|---:|
| 2023–24 | G1 | 100 | 2.5% | 12.3% | 0.0149 |
| 2023–24 | G2 | **6** | **22.1%** | **92.8%** | **0.1853** |
| 2024–25 | G1 | 130 | 6.1% | 18.1% | 0.0141 |
| 2024–25 | G2 | 75 | 13.1% | 40.9% | 0.0537 |

G0 trains on a reporting-site CF but scales predicted CF by the fixed capacity of the entire reference group. The W scorer, by contrast, forms actuals by summing only observed site-hours for each group and compares them with the redistributed site prediction on that same observed mask. Full reference capacity and capacity observed in evaluation are different quantities. Applying observed evaluation capacity to rescale forecasts would leak outcomes and was not done. In 2023 G2, the training CF's denominator represents at most 2.61% of the group; treating that as representative of the full group is unsupported by the available labels.

## 6. W comparison and unrun candidate status

The control row reuses the SM#43 verified evaluation artifact: same SM#41 Site 3-seed predictions, existing Group seed100 (`min_cov=0.3`), reference composition and alpha 0.2. The W is identical to SM#41. SM41/Group1 hourly penalties were cross-checked against `src/scoring.py` in that run. G1 and G2 did not pass the preregistered pre-fit support test, so they have no W metrics; bootstrap or candidate-to-baseline error correlation would be meaningless and is reported as not run.

| Candidate | 2023–24 W | 2024–25 W | G1/G2, peak, monthly W | 2024 bootstrap CI | Status |
|---|---:|---:|---|---|---|
| G0 (SM41 Site3 + Group1) | 106,754,876 | 197,534,279 | measured; same as SM41 | N/A (identical baseline) | evaluated control |
| G1 (`min_cov=.1`, `coverage²`) | Not Run | Not Run | Not Run | Not Run | rejected before fit: 2023 G2 has 0 labels |
| G2 (`min_cov=.5`) | Not Run | Not Run | Not Run | Not Run | rejected before fit: 2023 G1/G2 each have 0 labels |

Control diagnostics copied from the verified identical SM41 evaluation:

| Metric | 2023–24 | 2024–25 |
|---|---:|---:|
| Total W | 106,754,876 | 197,534,279 |
| G1 W | 79,417,053 | 93,807,603 |
| G2 W | 27,337,822 | 103,726,676 |
| 11:00–15:00 W | 88,886,367 | 163,021,141 |
| Observed site-hours scored | 1,256,595 | 2,170,645 |

The complete G0 monthly baseline W values are in the preserved `outputs/sm43/comparison.json`; no G1/G2 monthly comparisons exist. Reusing these values is not a claim that a candidate improved.

## 7. Competition rule and calendar lineage audit

The [official OIBC 2026 page](https://dataen.ai/en/challenge) says participants may use only data provided for the competition and prohibits external data. The [official notice page](https://dataen.ai/en/notice) did not expose a holiday-calendar exception in its accessible content. The repository comment at `src/features.py` saying “공지상 사용 허용” is not accompanied by a notice ID, date, URL, or saved source, so it does not substantiate an exception. Repository README text describing conditional external-data permission conflicts with the current official competition page.

| Calendar input | Provenance | Finding |
|---|---|---|
| `dow` and weekend | Derived from the supplied forecast timestamp | No additional calendar dataset is read; compatible with using supplied timestamps, although the rule does not name individual calendar transforms. |
| `is_hol` | `holidays` package Korean holiday calendar, years 2020–2026 | Third-party holiday-date data not present in the supplied package. The official page's general external-data prohibition applies; no specific holiday exception was found. Treat as **prohibited under the published general rule**, pending any organizer clarification. |
| Additional `EXTRA_OFF` dates | Hand-coded temporary/election holiday dates in `src/features.py` | Also external calendar information, with no cited official exception. Treat as **prohibited under the published general rule**, pending organizer clarification. |
| `is_off`, `off_run` | Derived using weekends plus the holiday set above | Inherits the external holiday-data concern. |

No calendar feature was switched off during this target-coverage experiment, per preregistration. This is a data-lineage issue affecting the inherited SM41/G0 baseline too; it was not resolved by these coverage results. A calendar-off model ablation or organizer ruling is needed before representing that feature set as competition-compliant.

All SM44 coverage calculations used only package generation, site metadata, timestamps, and existing solar geometry. No evaluation-period generation entered audit, fit, or candidate selection. No external meteorological source was loaded.

## 8. Decision, file protection, and reproducibility

- **Final candidate: retain SM#41; no SM#44 model is adopted.** G1 and G2 failed the pre-registered support gate. No hyperparameter was changed after seeing counts.
- No submission-period training, CSV generation, or validation was performed because there is no qualifying candidate.
- The original SM41 forecast and composition files remain unchanged; verified hashes are `ed9d14e194259971802ef1e1530f0bd38b05455cf3ca66a7815abaedbd63fd8d` and `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd`.
- Reproduce the audit with `.venv/Scripts/python.exe src/analysis/sm44_coverage_audit.py`. Input hashes and all quantiles, CF summaries, threshold/daylight counts, and site concentration data are in ignored `outputs/sm44/coverage_audit.json` and `coverage_threshold_counts.csv`.
- No Group model was newly trained. GFS-related existing test failures were not changed or reclassified here.
