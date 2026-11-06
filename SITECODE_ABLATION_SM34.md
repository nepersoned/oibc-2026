# SM#34 — `site_code` Generalization Ablation

## Setup

SC0 and SC1 used the SM#33 seed=7 settings: `OIBC_EXT_SOURCES=no_openmeteo`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, `rich + ext mean`, two-year training, the GFS partial cache, reference composition, and the existing LightGBM parameters with `random_state=7`. SC0 retains 105 features; SC1 removes only `site_code` and uses 104 features. `cap`, `lat`, and `lon` remain. The pipeline now passes categorical metadata only for selected columns, so SC1 does not pass a removed `site_code` to LightGBM.

## W comparison

| Period | SC0 W | SC1 W | ΔW | Change |
|---|---:|---:|---:|---:|
| 2023~24 | 110,008,344 | 100,357,213 | -9,651,132 | -8.773% |
| 2024~25 | 193,476,373 | 189,522,283 | -3,954,090 | -2.044% |

All predictions passed missing, NaN, infinity, and negative checks. The observed scoring rows were identical: 1,256,595 site-hours in 2023~24 and 2,170,645 in 2024~25.

Midday W was 91,647,874 → 83,417,879 (2023~24) and 159,672,125 → 156,279,174 (2024~25). Group W was:

| Period | Model | G1 W | G2 W |
|---|---|---:|---:|
| 2023~24 | SC0 | 84,584,375 | 25,423,969 |
| 2023~24 | SC1 | 74,974,246 | 25,382,967 |
| 2024~25 | SC0 | 91,567,579 | 101,908,794 |
| 2024~25 | SC1 | 89,652,186 | 99,870,097 |

The largest positive monthly change was +0.00% in the 2023~24 comparison (every month improved; the least improvement was June, -0.41%) and +2.70% in 2024-10 for 2024~25. Daily W improved on 60.38% of days in 2023~24 and 52.33% in 2024~25.

## Paired 7-day bootstrap

With `ΔW = SC1 - SC0`, 10,000 contiguous seven-day block resamples produced:

| Period | 95% ΔW interval | 0 included |
|---|---:|---|
| 2023~24 | [-13,531,920, -5,461,153] | No |
| 2024~25 | [-7,702,209, -165,415] | No |

This is strong evidence within these repeated research periods, but not an independent final test.

## Seen / unseen diagnostic

Seen means the site had at least one generation row in the preceding two-year training window. Unseen values below are diagnostic site-level error decompositions, not official group W; group W is calculated after aggregating all site predictions within a group and then taking the absolute error.

| Period | Seen sites | Unseen sites | Unseen capacity share |
|---|---:|---:|---:|
| 2023~24 | 106 | 99 | 73.13% |
| 2024~25 | 205 | 48 | 22.25% |

In 2023~24, SC1 reduced unseen G1 weighted site absolute error from 68.812M to 67.945M and unseen G2 increased 34.889M to 35.134M. Signed error changed from +944,340 to +81,367 kWh in unseen G1 and +144,191 to -300,371 kWh in unseen G2. Seen G1 weighted site absolute error changed 79.534M → 79.293M; seen G2 5.181M → 5.223M.

In 2024~25, SC1 changed unseen G1 weighted site absolute error 10.406M → 10.302M and unseen G2 65.776M → 67.137M. Signed error changed +119,091 → +144,200 kWh in unseen G1 and +295,595 → -225,364 kWh in unseen G2. Seen G1 changed 175.383M → 173.401M; seen G2 118.909M → 119.428M.

The reductions in total group W therefore cannot be attributed to a simple reduction of every site's absolute error. Removing `site_code` changes prediction bias and group-level error cancellation, especially for the high-capacity unseen set in 2023~24.

## Decision

SC1 is **promising for the current research setup**: it improves group W in both periods and both paired intervals exclude zero. This is not proof that `site_code` causes the error, nor an independent final-test result. The next priority is a time-forward validation of the site-generalization behavior, followed by a 2-year versus 4-year training-window comparison. Multi-seed LightGBM can follow; CatBoost is deferred until this coverage effect is isolated.
