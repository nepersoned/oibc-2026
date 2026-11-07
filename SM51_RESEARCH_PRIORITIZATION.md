# SM#51 Leaderboard Gap Diagnosis & Research Prioritization

Date: 2026-11-08 (KST)  
Branch: `seongmin`  
No model training, ensemble tuning, submission generation, or portal action was performed.

## Official gap: known score difference, unknown error cause

| Model | Official score S | Local validation W on record | Meaning |
|---|---:|---:|---|
| S2 `ens_v3` | 6,459,800,168 | 176,485,314 KRW (2024–25 half-year CV) | Official team best; its OOF forecast artifact is not present locally |
| S4 SM46 A1-REF | 6,448,069,881 | 106,673,757 (2023–24); 197,526,260 KRW (2024–25) | Official submission; weekday Site3 + Group100, fixed 80/20, reference composition |

The official score difference is **11,730,287 points** in favor of ens_v3. That is a confirmed leaderboard ordering, not a decomposition of physical error or a recoverable W difference. The recorded ens_v3 local W is from a half-year CV configuration; A1-REF has two full right-closed validation years. Data sources, training/validation construction, observed-site masks and group-model behavior differ, so even the arithmetic local-W gap (21,040,946 KRW against A1-REF 2024–25) is not a valid paired estimate. Official-period generation is unavailable; absolute official W or revenue is not inferred.

ens_v3 uses GFS and LDAPS inputs according to JH#29/S2 records. Whether those external sources meet the current competition's permitted-input rules remains unresolved without an applicable organizer ruling. Their presence in the team-best model does not establish that they are allowed for a new candidate.

## What the existing A1 evidence says

- SM50 reused A1 weekday Site3 and Group seed100 forecasts on a common observed site-hour mask. Site-only W was 107,248,930 / 199,015,602 KRW for 2023–24 / 2024–25; Group-only was 123,344,894 / 216,273,013; fixed alpha=0.2 blend was 106,673,757 / 197,526,260. Group-only was worse across all forecast-uncertainty bins.
- Peak/nonpeak and monthly W are recorded in SM45 and the ignored SM50 aggregates; the scored errors are dominated by daylight/peak loss because the settlement multiplier and solar production are concentrated there. The aggregates are A1-only and cannot identify which weather regimes or dates explain ens_v3's higher official score.
- SM50's provider disagreement and cloud-revision associations did not yield a stable Site-vs-Group preference across both years after month and peak/offpeak checks. Site/Group residual correlation was about 0.78–0.90, limiting independent cancellation.
- SM45's 2024 A1 Group observed-sum signed bias was −6.386 kWh for the blend and −12.390 kWh for Site-only; the corresponding Group MAE was 382.277 / 385.522 kWh. The Group target is based on reporting capacity while inference scales to fixed full-group capacity, so observed-sum errors do not equal full-group errors.
- Coverage is a structural weakness: the 2023 Group training window has zero eligible G2 labels at `min_cov=0.3`; the 2024 window has 2,889. SM44's pre-registered coverage alternatives were rejected before model fit. The shortage cannot be repaired by lowering thresholds after observing validation scores.
- No matched daily-total error ranking, extreme-date comparison, or site-specific error/coverage table for ens_v3 exists. Those items remain unavailable for a leaderboard-gap explanation.

These results describe existing candidates. They do not imply that A1 or ens_v3 caused any specific official-score difference.

## Candidate comparison

| Priority | Candidate | Error to address and difference from prior work | Data / reproducibility | Rule, leakage and cost | New information and decision |
|---:|---|---|---|---|---|
| 1 | **B — infer a site-specific solar-shape response from past generation** | Address plant-to-plant morning/afternoon and seasonal shape errors. Existing models calculate shared solar elevation/azimuth, but `sites.csv` has no panel tilt/azimuth. SM34 removed `site_code`; SM37-B/SM45 optimized composition from residuals. Neither estimates a time-valid plant-specific solar response. | Provided generation, capacity, timestamp, WA/WB forecast and existing solar geometry are present. Feasible as a proxy; actual panel orientation is not observable. | Potentially rule-safe because it uses competition inputs only. High leakage risk unless signatures for every training row are produced from earlier-only OOF residuals and validation signatures use only pre-cutoff data. Medium/high cost. | **Highest novelty among compliant options.** Test one regularized morning–afternoon solar-azimuth asymmetry signature; call it a response proxy, not measured orientation. |
| 2 | **E — align training with group settlement loss** | Address the difference between site-level L2 training and group-level absolute-error settlement. JH#7 and SM47 already tested Site L1 and worsened in 2024; repeating Site L1/quantile is not recommended. The new question would be group-aggregated loss/reconciliation, not another site L1 objective. | Provided actuals, fixed composition, SMP/k and time-valid site predictions; feasible in an offline prototype. | No external inputs. High overfit risk: only two groups, observation masks vary, and Group CF scales reporting capacity at fit but fixed capacity at inference. High cost. | Valuable objective-alignment question, but defer until a valid per-site OOF benchmark and label/mask protocol are available. |
| 3 | **D — improve Group coverage and target reliability** | Address zero G2 support in 2023 and partial-label representativeness. SM27 tried Group A2 coverage correction; SM44 audited G0/G1/G2 and did not fit candidates after its support gate failed; SM43 only bagged seeds. Do not repeat those exact variants. | Package generation and capacity history exist, but 2023 G2 is not empirically identified at the required coverage. A new method needs a defensible transfer/pooling source. | Competition inputs only. High risk of pretending sparse observed plants represent the full group; method work is medium/high cost. | Important weakness, but little new supervised information is available without a justified cross-group/site transfer design. |
| 4 | **A — improve supplied-forecast daily irradiance/energy proxies** | Address daily total and cloud attenuation. SM11 daily calibration did not improve; SM12 direct JMA irradiance was unstable and used external inputs; SM41 F2/SM42 F3/SM50 already cover cloud attenuation, revision and disagreement. Only a distinct, preregistered construction would avoid repeating prior work. | WA/WB, timestamp, site metadata and solar geometry are present. | Package-only version can be rule-safe. Moderate target leakage risk in daily totals; medium cost. | Lower novelty than B; pursue only if it uses a clearly new physical aggregation and can be isolated from prior F2/F3 results. |
| 5 | **C — robust portfolio composition under uneven observation** | Address cancellation under sparse plant residuals. SM37-B and SM45 already ran constrained composition search; SM45 used daylight-coverage eligibility and a fixed 10-site move, but broad validation reuse remains. | Provided history and composition constraints are available. | No external data required, but high selection/multiple-testing risk and high cost; unobserved residuals cannot be set to zero. | Do not rerun local search. Only revisit with a new untouched forward period or a pre-fixed sparse/robust objective. |

## Prioritization decision

The current gap diagnosis is **artifact-limited**: the official score difference is real, but matched residual evidence for ens_v3 is absent. The most defensible next modeling hypothesis is Candidate B, because it adds a plant-specific, competition-data-only signal that is not represented by the current shared solar geometry and does not repeat the failed Site L1, cloud disagreement, Group bagging, or composition searches.

External GFS/LDAPS/Open-Meteo experiments remain out of new-candidate scope until organizers' permitted-input rules are clarified. The next experiment should report local W improvement against A1-REF only; it must not claim to close the official leaderboard gap unless an authentic same-window ens_v3 forecast becomes available.
