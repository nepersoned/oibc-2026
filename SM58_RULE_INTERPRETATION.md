# SM#58 Rule Interpretation

Date: 2026-11-08 (KST)
Scope: GFS 00 UTC D−1 run, fixed 1° grid, LCDC/MCDC/HCDC.

## Applying the OIBC criteria

SM57's pilot gate was stricter than the supplied integrated notice in two ways: it treated an individual first-public timestamp for every file and separate source-specific OIBC approval as mandatory. SM58 replaces those with the notice's evidence alternatives: use object-level evidence where available; otherwise use an official dissemination schedule plus official delay guidance, and exclude runs that cannot be shown to meet the cutoff. A 100% complete archive is not a prerequisite; missing runs require a predeclared consistent treatment.

The source still needs public access, commercial-use compatibility, re-downloadability from the same endpoint, D−1 17:00 KST availability evidence, a fixed grid independent of plant coordinates, and identical weather inputs across sites. Uncertain interpretation of the competition notice is recorded as a question for organizers rather than treated as an automatic rejection.

## Evidence distinctions

The official NCEP production-status page explicitly says its average start/stop times use a rolling 30-day average. On the page observed 2026-11-08, the 00 UTC GFS forecast event and 12/24/36-hour product jobs had recent average completion times around 03:43–05:13 UTC, before the 08:00 UTC deadline. This is evidence about recent production behavior, not a historical guarantee or a formal maximum-latency schedule. The official GFS v16 implementation history also documents an 8–11 minute added delivery delay for atmos pgrb2 beginning 2021-03-22; that records a specific implementation change, not a continuous historical SLA. [NCEP current production status](https://www.nco.ncep.noaa.gov/pmb/nwprod/prodstat/production_status.html), [NCEP GFS implementation history](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs/implementations.php)

The NCEP GFS inventory confirms the 1° GRIB2 product path and forecast-hour naming; the NOMADS inventory confirms 00/06/12/18 UTC cycles. Neither page states a maximum delay or a binding release SLA. [GFS inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/), [GFS NOMADS inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/nomads/)

The GFS AWS Registry entry identifies the public NOAA NODD bucket and anonymous re-download path; NOAA's NODD FAQ describes its public-use terms. AWS defines S3 `Last-Modified` as object creation or last modification. Together, an anonymously accessible current index and GRIB object with timestamps before 08:00 UTC is run-specific evidence that those current versions were in the public bucket by the cutoff. It does not prove the exact first availability in NOAA's production system, and NOAA notes that some NODD holdings may be backfilled. A later timestamp is not evidence that an earlier operational copy was unavailable; for this audit it is conservatively excluded. [NOAA GFS AWS Registry](https://registry.opendata.aws/noaa-gfs-bdp-pds/), [NOAA NODD FAQ](https://www.noaa.gov/big-data-project-frequently-asked-questions), [AWS S3 metadata](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingMetadata.html)

The production-status page is not used as a proxy for historical dates. The run-level audit checks both each `.idx` sidecar and its corresponding GRIB payload object's current S3 Last-Modified value. The index identifies message byte ranges; the GRIB payload contains the features. This timestamp evidence is not represented as a NOAA SLA or proof of earliest dissemination. If S3 versioning or archived bucket migration evidence indicates a post hoc backfill, the affected run must be downgraded and excluded.

## Eligibility labels

- **VERIFIED:** direct, reproducible evidence satisfies the specific criterion for the audited object/run.
- **CONDITIONAL:** official product/source evidence supports the criterion but leaves a stated limitation (for example, no maximum latency guarantee).
- **UNVERIFIED:** the available evidence does not establish the criterion.

SM58 does not assume separate OIBC approval is required. The exact scope of the organizer's source wording remains a question if it is ambiguous after applying the published criteria.
