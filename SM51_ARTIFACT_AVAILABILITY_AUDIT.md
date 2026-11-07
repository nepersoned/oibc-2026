# SM#51 Artifact Availability Audit

Date: 2026-11-08 (KST)  
Branch: `seongmin`  
Starting revision: `fcb7041e448e1b729fd1bca28d4d22e5e5929638`

## Finding: ens_v3 OOF predictions are NOT AVAILABLE

The checkout, ignored local `outputs/`, `submissions/`, model manifests, experiment reports and execution logs were searched for ens_v3-specific validation predictions. No ens_v3 per-site or per-group OOF prediction, matching manifest, or execution log was found. The submission log records the path pattern `submissions/*_ens_v3.csv`, but no matching file exists in this checkout. That record is not an OOF artifact.

The known ens_v3 description is limited to the team records: JH#29/S2, reference composition, Group (GFS + LDAPS) 56% and Site (GFS) 44%, with GFS group fallback after LDAPS availability ends on 2026-04-02. Its recorded 176,485,314 KRW is a 2024–25 half-year CV result. The exact prediction columns, row-level mask, member model files, full training windows, and input/prediction hashes could not be verified from local artifacts. Do not treat the SM#20 partial NOAA `ens_v2` approximation, SM#40 `ensemble_test.parquet`, or any SM forecast as ens_v3.

## Existing comparison artifacts

The following SM45 A1 weekday/reference predictions are present and were reused in SM#50. They are useful for diagnosing A1-REF only; they cannot form a paired ens_v3 comparison.

| Artifact | Rows / columns | SHA256 | Use and limits |
|---|---|---|---|
| `outputs/sm45/2023_A1_B0_site_only_sites.parquet` | 2,222,352; `site_id, ts, kwh` | `72e49d8288cb4352804c8b4c585e94a04bc2e90bd4b69c91f36e2d61d7439985` | A1 weekday Site3 validation forecast, 2023–24 |
| `outputs/sm45/2024_A1_B0_site_only_sites.parquet` | 2,216,280; `site_id, ts, kwh` | `d2058c8841618d5380e4b05131ae3c361ff2a0f53e4b74f2188eb2db29fc05d1` | A1 weekday Site3 validation forecast, 2024–25 |
| `outputs/sm45/group_a1_2023.parquet` | 17,568; `group, ts, cf_hat, pred` | `22dc17b9581073a370a0dc4dd1d5fabcb75e281fd3a9b3fb4a76cf57f6052598` | A1 weekday Group seed100 forecast, 2023–24 |
| `outputs/sm45/group_a1_2024.parquet` | 17,520; `group, ts, cf_hat, pred` | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | A1 weekday Group seed100 forecast, 2024–25 |
| `outputs/sm45/manifest.json` | SM45 runtime/config and report/input hashes | `554ec9223b97ddf6a8831354f9bc1fccfe91aa1e0eadfc0dc2697f7b3706f820` | Records Python 3.11.15, LightGBM 4.7.0, pandas 3.1.1, NumPy 2.4.6; it is not an ens_v3 manifest |
| `outputs/sm50/diagnostics.json` | Aggregate uncertainty diagnostic | `ac54789d8bdd9351605866def8151096ae6e333d1ab3aeda21901a9fdf6325be` | Same-mask A1 Site/Group regime diagnostics; no ens_v3 rows |
| `outputs/sm50/regime_scores.csv` | Regime × period × model settlement summaries | `23cd965e21f32916f722f0ff617a6ce396eddf3932c3c4de9b9ef0fad1b12ce6` | Contains G1/G2, peak/nonpeak and signed-error fields for A1 diagnostic bins |
| `outputs/sm50/regime_monthly_w.csv` | Regime × month × model W summaries | `d1b81a3b8b0ad6c7d9fc4580aff5a5f6e94319e1fe715995c8375ba343157263` | Reused validation periods; no ens_v3 comparison |
| `outputs/sm50/residual_correlations.csv` | Site/Group residual correlations by regime | `5c4425477ccee16b9dd7cf117d37ba4aef4951a17573465e3856bb166322993d` | A1 Site/Group only |

SM46 submission Parquets are submission-period forecasts, not historical OOF. `outputs/sm44/coverage_audit.json` and `SM44_GROUP_TARGET_COVERAGE.md` document Group coverage: in the 2023 window only six G2 plants had any generation and maximum G2 coverage was 2.61%; by the 2024 window 75 G2 sites reported and 2,889 Group labels met `min_cov=0.3`. These are coverage audits, not ens_v3 predictions. The local participant `sites.csv` contains site ID, group, capacity, shifted lat/lon and station mapping/distance; it has no panel tilt or azimuth field.

## What can and cannot be diagnosed

| Requested diagnostic | Existing evidence | Status |
|---|---|---|
| Peak and month/season loss | SM45 full-year tables and SM50 peak/nonpeak and monthly W aggregates for A1 | Available for A1 only; not paired with ens_v3 |
| Group signed bias | SM45 reports observed-sum bias; SM50 stores signed error by regime for A1 | Available for A1 only; the observed-capacity vs fixed-capacity Group target caveat remains |
| Forecast revision vs error | SM50 compares train-only-cut cloud disagreement/revision regimes against A1 Site/Group W | Available for A1 only; descriptive association, not causal attribution |
| Site/Group error correlation | SM50 saved residual-correlation summary | Available for A1 only; correlations are high (about 0.78–0.90) |
| Daily total error and extreme error dates | No paired ens_v3 artifact or saved common-mask daily comparison was found | Not available as a model-to-model diagnosis |
| Per-site observation-rate ranking matched to both models | Source generation and metadata exist; no saved paired ens_v3 coverage/residual table was found | Not available for a fair ens_v3 comparison |

Historical actuals may support retrospective diagnostics, but they cannot reconstruct official-period outcomes or make unmatched models comparable. No external data, model training, or output regeneration was used in this audit.

## Conclusion

**ens_v3 validation predictions: NOT AVAILABLE.** The local evidence supports a precise official score comparison and an A1-REF diagnostic, but not a same-period residual, peak, seasonal, site, or error-cancellation comparison against ens_v3. Recovery of an authentic ens_v3 prediction/manifest bundle from its original owner is required before attributing the leaderboard gap to any feature or model component.
