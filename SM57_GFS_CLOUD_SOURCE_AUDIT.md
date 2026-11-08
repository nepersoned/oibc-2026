# SM#57 GFS Cloud Source Audit

Date: 2026-11-08 (KST)  
Branch reference: `seongmin` at `b97195d33924e79c6e4d53a6b246cb767ef5bf1d`  
Read-only reference: `origin/main` at `793f5f6662f074dbc8e50d3b0f925b9b214c3683`

## Decision

**Source feasibility is partial; the controlled pilot is blocked before training.** NOAA's current GFS GRIB2 inventory identifies low, middle, high and total cloud cover. Directly inspected archive indexes show all four cloud fields and DSWRF at sampled dates/leads. But the available evidence does not establish the operational publication time for every historical D-1 00 UTC run before the competition's D-1 17:00 KST cutoff, and does not establish full-period vertical-cloud coverage/missingness. OIBC eligibility therefore remains **unconfirmed**. No model was trained and no result is claimed.

## Duplicate-research audit

Compared the `origin/main` experiment log and code for JH#43, #48, #60, #66 and #67:

| Prior work | Existing GFS information | Vertical cloud layers? |
|---|---|---|
| JH#43 | Group GFS extension: longwave, humidity, larger fixed box, spatial spread | No listed LCDC/MCDC/HCDC |
| JH#48 | JH#43 extension with recent weighting | No listed LCDC/MCDC/HCDC |
| JH#60 | Site model with GFS extension and 20 fixed-grid points including cloud, plus other sources | Code uses point TCDC; no layer fields |
| JH#66 | 15 derived cross-source features, including cloud disagreement/range/minimum, grid spread, time summaries | No explicit layer fields |
| JH#67 | Site model with UM/ENS plus JH#66 derived features | No explicit layer fields |

`origin/main:src/fetch_gfs.py` defines only `DSWRF:surface` and `TCDC:entire atmosphere`; `fetch_gfs2.py` adds other GFS summaries but no vertical cloud layers; `fetch_gfs_pts.py` uses TCDC at fixed points. `features.py` contains no LCDC/MCDC/HCDC feature mapping. The proposed layer family is therefore distinct from the audited JH experiments, although it is not evidence of incremental value.

## Field and archive audit

NOAA's GRIB2 parameter table lists LCDC (parameter 0-6-3), MCDC (0-6-4), HCDC (0-6-5), and TCDC (0-6-1), all in percent. The official GFS v16 implementation notice documents a transition to separate cloud-layer fields. NOAA's GFS product inventory lists the 1.0-degree `pgrb2` product and forecast-hour naming scheme. See [NCEP GRIB2 cloud table](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-6.shtml), [GFS v16 implementation material](https://www.emc.ncep.noaa.gov/users/impldocs/GFS.v16_Implementation.pdf), and [NCEP GFS product inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/).

The official NCEP index files were fetched as small text indexes only (no GRIB fields or competition rows were sent to an external service). For sampled 00 UTC runs on 2021-04-01, 2022-01-15, 2023-01-15, 2024-01-15, 2025-01-15, 2025-06-15, 2026-01-15 and 2026-05-15, the `f018` and `f039` indexes included LCDC, MCDC, HCDC, TCDC and DSWRF. For the sampled index entries, the cloud layers have instantaneous lead messages and 6-hour average messages (e.g. 12–18 h at f018, 36–39 h at f039); DSWRF is represented as an accumulated-period average. The SM loader's existing DSWRF/TCDC hourly construction therefore cannot simply be assumed valid for layer fields: a layer aggregation/interpolation definition would need to be preregistered and validated.

The same-path archive returned 404 for sampled 2021-01-15 files and 200 for the later samples. This is not a complete date coverage audit. The local `data_ext` has legacy GFS products and partial Parquet files for DSWRF/TCDC; it contains no LCDC/MCDC/HCDC source artifact. No full-run download, all-lead/all-day index scan, or missingness rate was produced. **Historical and 2025–26 re-collection is demonstrated only for the sampled URLs, not established for every target date.**

The target mapping for target day D is run D−1 at 00 UTC (09:00 KST), with target hours 01–24 KST corresponding to forecast leads 16–39. Sampled f018 and f039 demonstrate endpoint presence only; no claim is made that every intermediate lead/date is complete.

## Rule and release-time audit

| Requirement | Evidence found | Status |
|---|---|---|
| Public access | NOAA NODD states its hosted datasets are free and open; sampled NOAA AWS index URLs were anonymously retrievable. [NOAA NODD FAQ](https://www.noaa.gov/big-data-project-frequently-asked-questions) | Supported for sampled source access |
| Commercial use | NOAA describes its data as public domain/open absent an explicit exception. [NOAA FAQ](https://www.noaa.gov/office-education/outreach-communication/faq) | General NOAA policy supports use; product-specific/OIBC authorization is not independently established |
| Re-download from same address | Sampled `.idx` files were retrievable at the same NOAA AWS bucket path; some sampled older path (2021-01-15) returned 404. | Partial only; not all dates |
| Published before D−1 17:00 KST | Repository code comments say 00Z products are “usually” available at 03–05 UTC. This is not date/run-specific evidence. Current AWS object/index responses provide no historical operational release timestamp. | **Unverified; blocking** |
| Fixed grid independent of plant coordinates | Existing SM GFS extractor selects a fixed 34–38N, 126–129E box; it does not query plant coordinates. | Supported for existing extractor design; new feature not implemented |
| Same feature supplied to all plants | Existing fixed-box GFS summary is common to all sites. | Supported as a prospective design constraint |
| OIBC approval | The supplied task states the integration notice criteria; no separate notice artifact or official approval for this GFS product was located in this checkout. | **Unconfirmed** |

NOAA product inventory and general open-data statements establish source availability and general reuse terms, not the actual publication time of each archived operational forecast. D-1 00 UTC initialization by itself is not proof of release before D-1 17:00 KST. The existing source's “usually 03–05 UTC” comment is only a typical-time claim, not a qualifying date-level audit.

## Coverage conclusion

No all-day/all-lead availability scan or cloud-layer feature extraction was performed, so 2021–2025 training and 2025–26 evaluation missingness percentages are **not available**. Local GFS products cover selected dates/periods and only contain the previously engineered DSWRF/TCDC fields. It would be unsound to report 0% missingness or assume the existing GFS coverage rates apply to new layer fields.

## Gate result

The variables exist in the sampled GRIB2 product and are not duplicates of the checked JH inputs. However, publication-cutoff evidence, full-period date/lead completeness, and explicit OIBC authorization are unresolved. Per SM#57's gate, this is sufficient to **stop before feature implementation and training**. Do not promote GFS layer features to a submission candidate.

To reopen the gate, obtain a trustworthy date/run-level dissemination record (not archive upload time alone), complete a date × lead audit for both training and evaluation windows, document the layer averaging/interpolation rules, and confirm the competition's source eligibility.
