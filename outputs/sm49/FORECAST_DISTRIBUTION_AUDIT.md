# SM#49 Forecast Distribution Audit

## Data reviewed

This is a structural audit of the three frozen 2025-06-01 01:00 to 2026-06-01 00:00 KST forecasts. The actual output series and the provided test WA/WB files were inspected; no future generation or observed weather was loaded. Future W cannot be calculated because the test period has no observed generation.

## Daily cycle and capacity-relative behavior

Mean generation is across the 8,760 forecast hours, not normalized per site. Night is defined as hours 00–05 and 21–23; edge hours 06 and 19–20 are shown separately by the hourly means in `audit_results.json`. Daytime mean is hours 07–17. Capacity factor is `group forecast_kWh / group capacity_kW` for the one-hour settlement interval.

| Candidate / group | Capacity kW | Mean kWh/h | Maximum kWh | Max CF | P99 CF | Night mean kWh/h | 07–17 mean kWh/h | Daytime zero hours / 4,015 | Longest consecutive daytime zero run |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A G1 | 20,465.7 | 3,186 | 15,938 | 0.779 | 0.712 | 0 | 6,752 | 177 | 2 h |
| A G2 | 22,189.7 | 3,608 | 17,721 | 0.799 | 0.736 | 0 | 7,638 | 167 | 2 h |
| B G1 | 21,161.6 | 3,324 | 16,491 | 0.779 | 0.714 | 0 | 7,046 | 202 | 2 h |
| B G2 | 21,493.7 | 3,452 | 17,028 | 0.792 | 0.727 | 0 | 7,308 | 202 | 2 h |
| C G1 | 21,161.6 | 3,328 | 16,535 | 0.781 | 0.716 | 0 | 7,053 | 177 | 2 h |
| C G2 | 21,493.7 | 3,459 | 17,089 | 0.795 | 0.732 | 0 | 7,322 | 174 | 2 h |

No forecast exceeds its group's nominal one-hour capacity: maximum CF is below 0.80 for every group/candidate. The hourly mean profile rises from zero overnight, is low at hours 06 and 19–20, peaks at hour 13, then returns to zero at 21–23. This shape is consistent with a solar production cycle; no obvious dawn/dusk time shift or nonzero overnight block was detected. Exact hourly means are recorded in `audit_results.json`.

All candidates have about 48–49% exact-zero hours over the year, which aligns with nighttime zeros. During 07–17, 167–202 of 4,015 hours are zero per group; the longest consecutive daytime zero run is only two hours. This does not show a long daytime stuck-zero segment. It is a structural signal for cloudy/low-output forecasts and is not adjusted based on validation scores. Longest exact constant run restricted to 07–17 was also two hours.

## Seasonal energy distribution

Forecast totals in MWh (JJA = Jun–Aug, SON = Sep–Nov, DJF = Dec–Feb, MAM = Mar–May):

| Candidate / group | DJF | MAM | JJA | SON |
|---|---:|---:|---:|---:|
| A G1 | 5.75 | 8.17 | 8.47 | 5.52 |
| A G2 | 6.51 | 9.15 | 9.66 | 6.29 |
| B G1 | 6.06 | 8.44 | 8.83 | 5.79 |
| B G2 | 6.22 | 8.75 | 9.26 | 6.01 |
| C G1 | 6.05 | 8.49 | 8.83 | 5.78 |
| C G2 | 6.20 | 8.82 | 9.27 | 6.00 |

All three candidates have the same expected seasonal ordering and broadly similar profile. Composition changes alter which group receives energy. C and B are very close in predicted totals because their Site predictions and composition are shared; C's group-level model changes the hourly portfolio forecasts by a mean +4.0 kWh/h in G1 and +7.0 kWh/h in G2 relative to B. Mean absolute hourly changes are 38.8 and 41.7 kWh, with maxima 607.6 and 651.0 kWh.

## Candidate-to-candidate hourly differences

| Contrast | G1 signed mean Δ kWh/h | G1 mean absolute Δ | G2 signed mean Δ kWh/h | G2 mean absolute Δ |
|---|---:|---:|---:|---:|
| C − B | +4.0 | 38.8 | +7.0 | 41.7 |
| C − A | +142.1 | 144.4 | −149.7 | 153.1 |
| B − A | +138.1 | 144.0 | −156.7 | 162.3 |

For C−A and B−A, both portfolio composition and (for C) Group blending differ; these are not isolated causal effects. The forecast differences are bounded and smoothly vary with the daylight hours; they do not show large all-day constant offsets.

## Provided WA/WB forecast gaps

The official test forecast package covers 61 WA stations, 73 WB stations, rounds 10 and 17, and 8,760 timestamps. WB has all 1,278,960 expected station-round-hour rows. WA contains 1,068,456 of 1,068,720 expected rows: 264 missing station-round-hour keys (182 round-10 and 82 round-17). None of the station-hour keys is missing from both rounds, so the existing `prep_forecast()` round-17/round-10 fallback has a value available at each station-hour. Feature lags/leads can still produce edge NaNs by construction, and LightGBM supports these; the frozen outputs nevertheless contain a complete 2,216,280 site-hour grid for all candidates, with finite nonnegative values. The 264 sparse forecast rows did not cause missing/invalid output records.

This is an input-completeness audit, not evidence that forecast error is low. No post-submission observed weather or actual generation was used to repair, calibrate, or select predictions.
