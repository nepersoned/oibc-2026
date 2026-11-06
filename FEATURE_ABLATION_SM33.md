# SM#33 — FA3 / FA4 and FA1 Multi-seed Validation

All runs used `no_openmeteo`, GFS-only external cache, `rich + ext mean`, the two-year training window, reference composition, existing LightGBM parameters, and official group settlement scoring. Seed was passed as `random_state` 7, 21, or 42. No submission files were created.

## Main W results

| Experiment | Features | 2023~24 W | 2024~25 W |
|---|---:|---:|---:|
| FS0 seed=7 | 105 | 110,008,344 | 193,476,373 |
| FA3 seed=7 | 101 | 109,227,630 | 194,980,982 |
| FA4 seed=7 | 104 | 108,597,670 | 195,094,092 |
| FS0 seed=21 | 105 | 107,039,359 | 193,434,044 |
| FA1 seed=21 | 101 | 106,930,012 | 191,358,450 |
| FS0 seed=42 | 105 | 108,797,285 | 192,944,901 |
| FA1 seed=42 | 101 | 106,474,397 | 193,461,132 |

Candidate deltas against their same-seed FS0 controls:

| Candidate | 2023~24 ΔW | 2024~25 ΔW |
|---|---:|---:|
| FA3 seed=7 | -780,714 (-0.710%) | +1,504,609 (+0.778%) |
| FA4 seed=7 | -1,410,675 (-1.282%) | +1,617,719 (+0.836%) |
| FA1 seed=7 | -665,147 (-0.605%) | -1,263,672 (-0.653%) |
| FA1 seed=21 | -109,347 (-0.102%) | -2,075,594 (-1.073%) |
| FA1 seed=42 | -2,322,888 (-2.135%) | +516,231 (+0.268%) |

All candidates had identical scoring rows: 1,256,595 site-hours in 2023~24 and 2,170,645 in 2024~25. Every prediction passed missing, NaN, infinity, and negative-value checks.

## Midday and groups

| Period | Model | 11~15 W | G1 W | G2 W |
|---|---|---:|---:|---:|
| 2023~24 | FS0 s7 | 91,647,874 | 84,584,375 | 25,423,969 |
| 2023~24 | FA3 s7 | 90,897,443 | 83,881,047 | 25,346,583 |
| 2023~24 | FA4 s7 | 90,146,818 | 83,359,064 | 25,238,606 |
| 2024~25 | FS0 s7 | 159,672,125 | 91,567,579 | 101,908,794 |
| 2024~25 | FA3 s7 | 161,206,712 | 92,633,849 | 102,347,133 |
| 2024~25 | FA4 s7 | 161,355,145 | 92,561,498 | 102,532,594 |

FA1 same-seed group W changes were: seed 7, 2023~24 G1/G2 -624,028/-41,119 and 2024~25 -688,500/-575,172; seed 21, -327,494/+218,147 and -609,143/-1,466,452; seed 42, -2,120,343/-202,545 and +412,689/+103,542. The official W is group-aggregated before absolute error; these group figures are not site-level error sums.

## 7-day paired bootstrap

`ΔW = W(candidate) - W(same-seed FS0)`; 10,000 resamples of contiguous seven-day blocks:

| Period | Candidate | 95% ΔW interval | 0 included |
|---|---|---:|---|
| 2023~24 | FA3 s7 | [-2,592,400, +755,664] | Yes |
| 2023~24 | FA4 s7 | [-3,094,773, +94,264] | Yes |
| 2023~24 | FA1 s7 | [-2,524,177, +765,733] | Yes |
| 2023~24 | FA1 s21 | [-1,440,574, +1,261,669] | Yes |
| 2023~24 | FA1 s42 | [-3,938,752, -639,390] | No |
| 2024~25 | FA3 s7 | [-580,229, +3,753,902] | Yes |
| 2024~25 | FA4 s7 | [-298,168, +3,760,665] | Yes |
| 2024~25 | FA1 s7 | [-3,067,962, +967,049] | Yes |
| 2024~25 | FA1 s21 | [-3,983,804, -168,865] | No |
| 2024~25 | FA1 s42 | [-1,561,087, +2,542,895] | Yes |

Monthly worst positive changes were FA3 +4.98% (2023-12) and +4.46% (2024-08), FA4 +1.97% (2023-09) and +3.81% (2024-10). FA1 seed changes varied: seed 7 +4.97% / +1.76%, seed 21 +5.20% / +0.98%, seed 42 +2.31% / +2.41% (2023~24 / 2024~25). These repeatedly used validation years are not independent final tests.

## Decisions

- **FA3: 기각.** Four visibility context variables improved 2023~24 but worsened 2024~25; both bootstrap intervals include zero.
- **FA4: 기각.** Rain-probability removal has the same one-year improvement/one-year degradation pattern and no bootstrap-confirmed advantage.
- **FA1: 보류.** Seed 7 improved both years, seed 21 improved both years, but seed 42 worsened 2024~25. The multi-seed direction is not stable enough for adoption, even though some intervals exclude zero.

The next priority is **A: site_code removal/generalization diagnostics**, because prior audit found 99 unseen evaluation sites (73.13% of evaluation capacity) in 2023~24 and 48 (22.25%) in 2024~25. This is more directly tied to an observed coverage issue than switching to CatBoost. A later 2-year versus 4-year window comparison should follow; CatBoost is deferred until the feature coverage issue is isolated.
