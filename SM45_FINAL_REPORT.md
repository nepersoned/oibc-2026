# SM#45 Final Report — Calendar-Safe Forecasting & Robust Composition

Date: 2026-11-07 (KST)
Branch: `seongmin`
Starting revision: `62c1da1425296d11baf43c715ef4a659e6f6dba0`

## 1. Executed phases

- **A — Calendar audit and mode implementation:** completed.
- **B — Calendar-safe refits:** A1 weekday-only and A2 calendar-none each trained fresh Site LightGBM seeds 7/21/42 and Group LightGBM seed 100 for both time-forward validation years.
- **C — Site-only vs Site+Group:** completed using the same A1 site forecasts; no retraining for this comparison.
- **D — Limited composition search:** completed as one preregistered deterministic search on 2024-06 through 2024-11 A1 Site-only residuals, then one fixed 2024-12 through 2025-05 holdout evaluation.
- **Not run:** submission-period retraining/prediction, final CSV creation, and validator. No candidate met the multi-year adoption rule. Official portal submission was not performed.

The requested 2026 online-briefing slide deck was not present in either checkout. A local 13-page PDF is a 2023 presentation (“5th Solar Power Generation Prediction Competition”), not the 2026 deck; it was not represented as the requested source. The user-provided slide summaries were treated as hypotheses. The local 2023 PDF render artifacts are not part of this report.

## 2. Calendar-safe implementation

`src/features.py` now accepts `OIBC_CAL_MODE=legacy|weekday|none`. If the new variable is unset, the existing `OIBC_CAL=1/0` behavior remains the default for backward compatibility.

- `legacy`: previous weekday/holiday/off-day/run features, for comparison only.
- `weekday`: `dow` and `is_weekend`, derived from `features.target_day(ts)` only.
- `none`: no calendar columns.

The right-closed convention is preserved: a timestamp at 00:00 maps to the previous target day. In `weekday` and `none`, code does not call `off_days()`, import `holidays`, or read `EXTRA_OFF`. Site and Group feature construction use the same process-level mode. Tests check midnight semantics, no holiday-source access, legacy feature names, and stable train/inference columns.

The current market submission files from SM#41 were preserved byte-for-byte; their known SHA256 values were not overwritten.

## 3. External-information and rule audit

The participant package README describes site coordinates as shifted by up to 2 km and rounded, and forbids using them to identify the plant/operator/original location. These experiments used provided coordinates only in the pre-existing solar geometry and in the preregistered daylight-coverage denominator; no external weather was joined to coordinates and no location was reconstructed.

The root repository README says weekdays, weekends, public/substitute/temporary holidays, and election days are allowed “per announcement.” However, that README is not itself the organizer’s rule. The official DataEn challenge page prohibits external data beyond the competition-provided data, and the reviewed official page did not state a calendar exception. No official organizer text specifically permitting the `holidays` package or `EXTRA_OFF` was available in the checkout or official page. Therefore:

- `weekday` and `none`: use only provided timestamps; calendar inputs are data-lineage safe under the published rule.
- `legacy`: uses external holiday-date data; its status is **unresolved** pending a specific official exception. It is retained only as a performance reference and is not called submission-cleared.
- No outside weather or post-forecast actuals were used. Historical generation was used only in model training / the preregistered historical composition fit and validation.

Official references: [DataEn OIBC rules](https://dataen.ai/en/challenge) and [DataEn 2026 challenge overview](https://dataen.ai/en/challenge/2026). The page prohibits external data and future realized information, but does not resolve the specific holiday-calendar question.

## 4. A0/A1/A2 W comparison

All values are KRW. A0 is the recorded SM#41 Site3+Group1 blend on reference composition. Its W reproduces the provided SM#41 values. A1/A2 figures below are actual newly trained predictions. B0 is Site-only; B1 is the fixed 80/20 Site+Group blend. Δ is versus A0/SM#41.

| Model | 2023–24 W | Δ vs SM41 | 2024–25 W | Δ vs SM41 |
|---|---:|---:|---:|---:|
| A0 SM41 legacy, Site3 + Group1 | 106,754,876 | baseline | 197,534,279 | baseline |
| A1 weekday, Site-only (B0) | 107,248,930 | +494,054 (+0.463%) | 199,015,602 | +1,481,323 (+0.750%) |
| A1 weekday, Site3 + Group (B1) | 106,673,757 | −81,119 (−0.076%) | 197,526,260 | −8,019 (−0.004%) |
| A2 none, Site-only (B0) | 106,966,355 | +211,479 (+0.198%) | 199,791,618 | +2,257,339 (+1.143%) |
| A2 none, Site3 + Group (B1) | 106,419,015 | −335,861 (−0.315%) | 198,329,815 | +795,536 (+0.403%) |

Per-period detail (G1/G2 W and 11–15 W):

| Year/model | G1 W | G2 W | 11–15 W |
|---|---:|---:|---:|
| 2023 A0 B1 | 79,417,053 | 27,337,822 | 88,886,367 |
| 2023 A1 B0 | 79,933,804 | 27,315,126 | 89,545,713 |
| 2023 A1 B1 | 79,437,385 | 27,236,372 | 88,965,726 |
| 2023 A2 B0 | 79,661,697 | 27,304,658 | 89,072,034 |
| 2023 A2 B1 | 79,189,405 | 27,229,610 | 88,566,909 |
| 2024 A0 B1 | 93,807,603 | 103,726,676 | 163,021,141 |
| 2024 A1 B0 | 94,338,816 | 104,676,787 | 164,085,589 |
| 2024 A1 B1 | 93,693,778 | 103,832,482 | 163,019,883 |
| 2024 A2 B0 | 94,757,215 | 105,034,403 | 164,565,471 |
| 2024 A2 B1 | 94,178,369 | 104,151,446 | 163,608,243 |

For 2024, Site MAE / signed bias and observed-sum Group MAE / signed bias (kWh) were:

| Model | Site MAE | Site bias | Group MAE | Group bias |
|---|---:|---:|---:|---:|
| A0 B1 | 5.9291 | −0.0953 | 382.505 | −6.247 |
| A1 B0 | 5.9092 | −0.1000 | 385.522 | −12.390 |
| A1 B1 | 5.9092 | −0.1000 | 382.277 | −6.386 |
| A2 B0 | 5.9424 | −0.0802 | 387.757 | −9.932 |
| A2 B1 | 5.9424 | −0.0802 | 384.280 | −5.411 |

Group MAE uses the sum over actually observed sites; it is not comparable to a full-group-capacity target without accounting for missing observed sites. G2 had no eligible Group training labels in the 2023 window, so 2023 Group predictions for G2 are extrapolations.

## 5. Site-only vs Group blend and stability

On 2024, Group blending reduced point W relative to Site-only by 1,489,342 KRW (A1) and 1,461,803 KRW (A2). The 5,000-replicate paired 168-hour block bootstrap intervals for `blend − Site-only` were:

- A1: mean −1,486,477; 95% CI [−3,379,577, +410,371] KRW.
- A2: mean −1,430,067; 95% CI [−3,245,810, +357,128] KRW.
- Baseline A0 blend vs its Site-only diagnostic: mean −1,895,412; 95% CI [−3,812,066, +27,971] KRW.

All intervals include zero. 2024 A1 B1 vs SM41 had mean difference +4,806 and 95% CI [−1,277,865, +1,287,139]. A2 B1 vs SM41 had mean +724,525 and CI [−1,339,154, +2,797,839]. Neither calendar-safe blend establishes a significant improvement over SM41. No complete month for A1/A2 B0/B1 worsened more than 5%; worst complete-month increase vs SM41 was 4.43% (A1 B0, July 2024) and 4.77% (A2 B0, April 2025).

The measured Group-vs-observed-sum error correlation was high (~0.993–0.995), but the inference target still scales normalized CF by fixed full-group capacity while validation sums only available site observations. It is a useful diagnostic relation, not evidence that Group predictions equal the observed subset.

## 6. Limited composition experiment

The one deterministic local search used A1 weekday Site3 predictions only. Selection was fixed to right-closed `(2024-06-01 00:00, 2024-12-01 00:00]`; holdout was `(2024-12-01 00:00, 2025-06-01 00:00]`. A mover needed at least 80% observed daylight-hour coverage in selection (`elev > 0` from existing solar geometry); 224 sites met this. The selected configuration changed 10 sites and retained 20,100 kW group minimums (G1 21,161.64 kW; G2 21,493.73 kW).

| Window | Reference W | Candidate W | Δ W | Δ % |
|---|---:|---:|---:|---:|
| Selection Jun–Nov 2024 | 111,374,750 | 109,527,013 | −1,847,737 | −1.658% |
| Fixed holdout Dec 2024–May 2025 | 87,640,852 | 86,870,948 | −769,904 | −0.878% |
| 2023–24 retrospective diagnostic | 107,248,930 | 107,077,100 | −171,830 | −0.160% |

Holdout paired 168-hour block bootstrap (5,000 draws, seed 7): mean Δ −771,725 KRW; 95% CI [−1,108,829, −455,768]. Every complete holdout month improved, with monthly changes from −0.294% to −1.532%. In the full 2024–25 year, candidate composition W was 196,397,961, about 1,136,318 lower than SM41. In 2023–24, it remained 322,224 higher than SM41. Thus the fixed later holdout gain is strong within this split, but the overall two-year comparison is not consistently better than SM41. The 2024 calendar was previously used in research and this split does not remove broader selection bias.

Missing actual site-hours were omitted from composition residual aggregation; they were not asserted to be zero-error. The reference Group model was not blended into the new composition because its training labels and group features correspond to reference composition; doing so would require a separate Group refit.

## 7. Candidate decision and files

**Decision: no SM45 submission candidate is promoted.** A1 Group blend edges SM41 on both W point estimates, but the improvements are negligible and its paired interval includes zero. A1 Site-only is worse than SM41 in both full years. The composition candidate improves the fixed 2024 holdout decisively and helps the retrospective A1 2023 diagnostic, but its full 2023 W is still worse than SM41. It therefore does not establish the stable two-year improvement required for adoption. A2 is also not a consistent improvement.

No `composition_sm45_final.csv` or `forecast_sm45_final.csv` was created; no final validator was run. Research composition output exists at `outputs/sm45/composition_a1_site_only.csv`, with metrics at `outputs/sm45/composition_a1_site_only.json`. The full comparison is `outputs/sm45/comparison.csv` / `.json`. The model and score evidence is reproducible from the per-seed Parquet files under ignored `outputs/`.

SM41 remains the historical performance benchmark, but its holiday-derived feature legality is unresolved. This report does not certify SM41 or any other model for submission. No official portal upload occurred.

## 8. Tests, reproducibility, and caveats

- Python: repository `.venv`, Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6.
- New relevant tests: `5 passed`; pandas emitted deprecation warnings for `.dt.dayofweek` but results passed.
- Independent hourly W checks matched `src/scoring.py` for evaluated variants within the configured 1e-5 KRW tolerance.
- A1/A2 test prediction artifacts, Group predictions, comparison JSON/CSV, and composition diagnostics are in ignored `outputs/sm45/`; no raw source data or large prediction artifact is committed.
- Unrelated historical GFS tests were not run or changed.
- The bootstrap quantifies time-block variability on a repeatedly used historical year; it does not remove multiple-testing or validation-selection bias.
- Since no submission candidate was cleared, this run did not generate new submission-period forecasts or claim full submission validator success.

## 9. Follow-up priority

1. Obtain a direct organizer notice clarifying whether public holiday calendars / `holidays` data are explicitly allowed.
2. If composition remains of interest, test the preregistered portfolio construction on a genuinely newer untouched period; keep reference Group out unless it is retrained for the selected composition.
3. Treat holiday-free, timestamp-only calendar models as the safe code path until rule clarification; do not elevate a point-score winner without another clean time-forward W evaluation.
