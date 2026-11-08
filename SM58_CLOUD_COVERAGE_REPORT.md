# SM#58 Cloud-Layer Coverage Report

Date: 2026-11-08 (KST)
Input audit: `src/analysis/sm58_gfs_index_audit.py`
Detailed HEAD and sample-index outputs: ignored under `outputs/sm58/`

## Fields and hourly mapping

The official NOAA GRIB2 cloud parameter table identifies LCDC (parameter 0-6-3), MCDC (0-6-4), HCDC (0-6-5), and TCDC (0-6-1), each in percent. The sampled GFS 1° GRIB2 `.idx` lines identify the cloud-layer fields at their respective low-, middle-, and high-cloud layer levels. Instantaneous `N hour fcst` messages are present separately from `a-b hour ave fcst` messages. DSWRF appears as an average-flux field, consistent with the existing GFS pipeline. NOAA's March 2021 GFSv16 notice documents an additional 8–11 minutes of atmos pgrb2 delivery latency, increasing with forecast lead; it is historical rollout evidence, not an ongoing maximum-delay guarantee. [NOAA GRIB2 cloud parameter table](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-6.shtml), [NCEP GFS implementation history](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs/implementations.php)

Target hours `01:00` through right-closed `24:00` KST map to leads f016–f039 from the previous-day 00 UTC initialization. Layer means are calculated over the fixed 20 points at 34–38°N × 126–129°E, then linearly interpolated between instantaneous 3-hour forecast messages at f015, f018, …, f039. f015 is only the left interpolation anchor. The averages are not substituted for instantaneous fields. Values are clipped to the physical 0–100% interval only if a decoded value falls outside it.

## Index sample and daily object coverage

The monthly field scan fetched `.idx` text only for 63 sample dates × 9 leads (567 requests; 22,888,609 response bytes; no GRIB field payload). It found instantaneous LCDC/MCDC/HCDC in 558/567 lead samples each and corresponding averages in 558/567. The nine missing layer-field samples were all on the single 2021-03-22 transition date. Sampled runs from 2021-04-15 through 2026-05-15 contained all three instantaneous layers at every sampled lead. TCDC was present in 567/567 samples and DSWRF average in 567/567; DSWRF instantaneous was absent as expected for this flux field.

The complete HEAD scan covered 1,977 initialization dates × 9 leads. Both index and GRIB objects returned HTTP 200 for every date in the 2021-06 through 2026-05 target windows. A target day is retained only if all required index and GRIB objects have `Last-Modified` no later than the D−1 08:00 UTC cutoff. Coverage is based on public-object availability and cutoff, not on forecast accuracy.

The broad archive rows below report **object/cutoff** coverage. Daily layer-field presence was checked from every index used by the 2022-06–2025-05 controlled-pilot extraction, and monthly only outside that interval. The 2025-06–2026-05 evaluation window therefore has 100% index/GRIB object cutoff support and monthly sampled layer-field presence; full daily vertical-field coverage there was not downloaded or asserted because SM#58 creates no submission prediction. A 2021-03-22 sample index had no layer fields, while monthly samples from 2021-04 onward did; that early transition is outside the controlled pilot's two-year training windows.

| Window (target dates) | Days | All 9 object pairs before cutoff | Eligible coverage |
|---|---:|---:|---:|
| Broad 2021-01-01–2025-05-31 archive | 1,612 | 1,550 | 96.1538% |
| Training union 2021-06-01–2025-05-31 | 1,461 | 1,457 | 99.7262% |
| Training for 2023–24 validation 2021-06-01–2023-05-31 | 730 | 726 | 99.4521% |
| Validation 2023–24 2023-06-01–2024-05-31 | 366 | 366 | 100.0000% |
| Training for 2024–25 validation 2022-06-01–2024-05-31 | 731 | 728 | 99.5896% |
| Validation 2024–25 2024-06-01–2025-05-31 | 365 | 365 | 100.0000% |
| Evaluation 2025–26 2025-06-01–2026-05-31 | 365 | 365 | 100.0000% |

Late or missing days are omitted from both baseline and candidate. There is no rule that every historical day must exist; the 95% threshold is a preregistered practical threshold for the pilot, not a competition requirement.

## Pilot extraction coverage

The controlled pilot is limited to training target days 2022-06-01–2024-05-31 and evaluation target days 2024-06-01–2025-05-31. Daily layer coverage, row counts, timestamps, downloaded message-range bytes, skipped dates, and output SHA256 are captured in the local extraction manifest `outputs/sm58/gfs_cloud_layers.json`. It requested 2,315,981,204 bytes of selected message ranges, never full GRIB files, and produced 26,232 hourly rows. Of 1,096 requested target days, 1,093 had eligible runs; the three skipped initialization dates were 2022-11-30, 2023-01-20, and 2023-05-01. No eligible run lacked a required instantaneous layer field. Training support was 728/731 days (99.5896%); validation support was 365/365 days (100%). The A/B scoring mask then retained 8,672 validation timestamps (88 fewer than a complete 8,760-hour year) because the common existing-GFS feature inputs were unavailable at those hours; both arms used the same mask. The pilot W and diagnostics are in [SM58_CONTROLLED_PILOT.md](SM58_CONTROLLED_PILOT.md).
