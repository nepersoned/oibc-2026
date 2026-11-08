# JH Handoff Request — ens_v12

To close the S9 `ens_v12` eligibility and code-verification gaps before the 2026-11-13 deadline, please provide these five evidence bundles, in priority order. No model rerun or new source download is requested for this audit.

| Priority | Exact file or evidence requested | Why it is needed |
|---|---|---|
| 1 | Archived official OIBC integrated notice sections 5–10, plus the original organizer/Q&A response that defines allowable external data and specifically covers **ECMWF ENS via dynamical.org, KMA UM regional/global, NOAA GFS and KMA LDAPS/UMKR**. Include date and unedited text/screenshot/export. | Resolve the conflict between the public challenge page's general external-data prohibition and the repository's later conditional-source policy; establish S9's actual governing rule. |
| 2 | S9 per-model/per-segment input manifest (CSV/JSON): source URL/bucket, provider, license/terms reference, exact variable/feature names, target-day mapping, init/run/lead, file/object ID and SHA256, publication/cutoff evidence, missing-run mask, and whether the feature is shared identically across plants. Include `data_ext/gfs_pubtime_audit.csv`, `data_ext/ldaps_availability_log.csv`, any ECMWF ENS run/STAC manifest, and the S9-specific source mapping if these exist. | Verify source eligibility, 17:00 cutoff, stable re-download path, fixed-grid application and no future observations. Include GFS, ECMWF ENS, LDAPS, UM regional/global, WA/WB and JH#66 derived columns. |
| 3 | Final S9 execution bundle: exact Git commit, Python/OS and lockfile or `pip freeze`, commands/configs, train date windows, LightGBM parameters, seed(s), feature column order, reference composition hash, and 0.505/0.495 ensemble definition. | Reconstruct the actual training and inference procedure rather than infer it from JH experiment summaries or generic source code. |
| 4 | April–May 2026 fallback evidence: Site and Group primary/fallback model IDs and artifact hashes, exact cutoff/splice mapping, pre-splice prediction files or hashes, and final splice log including missing-feature/default checks. | Confirm the intended post-LDAPS/UM replacement was used for every forecast row and no absent external inputs were silently replaced by invalid defaults. |
| 5 | The exact submitted S9 package: `predictions/submissions/composition_ens_v12.csv`, `predictions/submissions/forecast_ens_v12.csv` as uploaded or an immutable archive link with SHA256, submission-time portal/log confirmation, and—if retained—the trained model artifacts or deterministic rebuild package. | Tie the tracked `origin/main` CSV hashes to the actual S9 upload and support any code verification request. |

The tracked files currently available for comparison are:

- `predictions/submissions/composition_ens_v12.csv` — SHA256 `933b670900ef0ee6c09eff7452d04c626e2945109430c5f98ba9a982bebda463`
- `predictions/submissions/forecast_ens_v12.csv` — SHA256 `5ecb1f8daf3277b64ea47730c900e2685a50acfcf1fed39a9910c16139129123`

Please preserve the originals and provide the evidence files as a separate archive or read-only location; do not overwrite the submitted CSVs.
