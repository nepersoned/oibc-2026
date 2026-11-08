# SM#58 GFS Publication Evidence

Date: 2026-11-08 (KST)
Audit implementation: `src/analysis/sm58_gfs_index_audit.py`
Local detailed audit: `outputs/sm58/gfs_index_head_audit.csv` (not committed)

## Evidence and status

| Requirement | Evidence | Status | Limit |
|---|---|---|---|
| Public source | NOAA GFS AWS registry names the public `noaa-gfs-bdp-pds` bucket; anonymous HTTPS/S3 access succeeds. | VERIFIED for present access | This does not archive historical public-bucket policy snapshots. |
| Commercial reuse | NOAA NODD FAQ describes the data as public-use and without restrictions; source is NOAA public-domain forecast data. | VERIFIED at source level | Competition-specific interpretation can still be clarified with organizers. |
| Same-source re-download | GRIB2 and `.idx` objects are accessible from the same stable NOAA AWS URL pattern; the NOAA registry documents no-account access. | VERIFIED | Individual objects can be absent/late and must be filtered. |
| D−1 17:00 KST cutoff | Per-run HTTP HEAD of both `.idx` and GRIB objects; current S3 `Last-Modified` no later than 08:00 UTC is required. | CONDITIONAL | S3 metadata establishes current-object bucket timestamp, not first NOAA operational publication. Backfill/history caveat remains. |
| Official schedule / delay notices | NCEP's 2021 GFSv16 implementation notice states an added 8–11 minute delivery delay for atmos pgrb2 products (increasing from f000 to f384). Current production status separately reports 30-day rolling averages. | CONDITIONAL | The implementation notice documents a specific change, not a continuing maximum-latency SLA for every later date. Current averages are not used to certify older runs. |
| Fixed-grid all-site use | All layer values are means over the same 20 points: 34–38°N × 126–129°E at 1° spacing. No plant coordinates select GFS inputs. | VERIFIED by implementation design | No station-specific spatial extraction is used. |

Official source references: [NCEP production status](https://www.nco.ncep.noaa.gov/pmb/nwprod/prodstat/production_status.html), [GFS product inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/), [GFS NOMADS inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/nomads/), [NCEP GFS implementation history](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs/implementations.php), [NOAA GFS AWS registry](https://registry.opendata.aws/noaa-gfs-bdp-pds/), [NOAA NODD FAQ](https://www.noaa.gov/big-data-project-frequently-asked-questions), [AWS S3 object metadata](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html).

The rolling-average production page observed on 2026-11-08 showed recent 00Z forecast completion around 05:13 UTC and associated 12/24/36-hour jobs around 03:43–03:49 UTC. This is recent production behavior only; it is neither a historic guarantee nor a stated maximum delay. The official GFSv16 implementation history records an 8–11 minute increase in atmos pgrb2 delivery latency starting with the 2021-03-22 12 UTC implementation; it is useful historical context but does not cover every possible later outage. `Last-Modified` is an object creation or modification time, not an explicit first-publication timestamp. NOAA's NODD FAQ also notes that some public-cloud holdings can be backfilled. Therefore eligible-run timestamps provide conditional object-level cutoff evidence, not proof of an operational SLA. No comprehensive historical daily delay archive for 2021–2026 was located.

## Object-level audit

The HEAD-only scan covered 1,977 initialization dates from 2020-12-31 through 2026-05-30 and nine leads (f015, f018, …, f039): 17,793 index-object probes plus corresponding GRIB-object probes. HEAD transferred no GRIB payload. The index objects had 17,759 HTTP 200 and 34 HTTP 404 responses across the full scan. Both index and GRIB objects were HTTP 200 for all dates in the 2021-06 through 2026-05 windows relevant to the pilot and evaluation. The audit CSV stores separate status, `Content-Length`, URL, and `Last-Modified` fields for index and payload objects.

Eligibility maps target date D to initialization D−1 at 00 UTC. Both the index and GRIB object must be HTTP 200 and have `Last-Modified` ≤ D−1 08:00 UTC. Any run failing this rule is omitted from both A and B; validation/evaluation comparisons use a common hour mask. The 95% support threshold in the preregistration is an experiment-design gate, not an OIBC rule.

| Target window | Target days | All 9 leads with both objects before cutoff | Coverage | Late index objects | Late GRIB objects |
|---|---:|---:|---:|---:|---:|
| 2021-01–2025-05 broad archive | 1,612 | 1,550 | 96.1538% | 499 | 501 |
| 2021-06–2025-05 training union | 1,461 | 1,457 | 99.7262% | 19 | 22 |
| 2021-06–2023-05 training for 2023–24 | 730 | 726 | 99.4521% | 19 | 22 |
| 2023-06–2024-05 validation | 366 | 366 | 100.0000% | 0 | 0 |
| 2022-06–2024-05 training for 2024–25 | 731 | 728 | 99.5896% | 16 | 18 |
| 2024-06–2025-05 validation | 365 | 365 | 100.0000% | 0 | 0 |
| 2025-06–2026-05 evaluation | 365 | 365 | 100.0000% | 0 | 0 |

All `.idx` and GRIB objects in the listed validation/evaluation windows returned HTTP 200. Late object counts are per lead object; their distinct target dates are excluded at day level. The full row-level cutoff output is in the ignored audit CSV and its condensed JSON in `outputs/sm58/gfs_actual_object_coverage_summary.json`.

Example row from the actual-object audit: initialization 2024-06-01 f018 had `.idx` Last-Modified 03:38:18 UTC and GRIB Last-Modified 03:38:16 UTC. This run maps to target date 2024-06-02 and has an 08:00 UTC cutoff, so both current objects meet it. The period result is based on the complete row-level audit, not this example alone.

## Interpretation

The corrected rule interpretation does not require a unique NOAA first-publication timestamp for every file when usable object-level evidence exists, nor a separate organizer approval as a prerequisite. It does require evidence for the cutoff, commercial compatibility, and re-downloadability. On the current evidence, the chosen run windows clear the preregistered support threshold, so the pilot can proceed as an exploratory local experiment. The source's cutoff status remains **conditional**, and the research result cannot by itself establish competition approval or submission eligibility.
