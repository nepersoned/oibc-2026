# SM#58 Next Decision

## Decision

The source audit corrected SM57's evidence gate and supported a controlled local pilot using only runs whose current NOAA S3 index and GRIB objects were retrievable and had `Last-Modified` at or before the preregistered cutoff. This is conditional object-level evidence: it does not prove first operational publication and NOAA does not provide a comprehensive historical maximum-delay SLA in the material reviewed.

The pilot's GFS low-, middle-, and high-cloud features reduced the single-seed 2024–25 observed-mask reference-group W by 2,062,677 KRW (1.094%). Both G1 and G2 and aggregate peak W improved. However, the paired 168-hour bootstrap interval for B−A was [−5,786,434, +1,308,454] KRW and includes zero. The same validation period was reused, so the result is not independent evidence.

**Disposition: exploratory signal; no candidate promotion, no multi-seed follow-up on this reused period, and no submission change.** The NOAA source-level commercial/public-use and re-download criteria are supported, but the operational cutoff interpretation remains conditional; clarify the organizer's interpretation if GFS is ever considered for an official submission.

## Next single research direction

Pause new external-weather work pending organizer clarification. Use already permitted WA/WB features and existing frozen Site/Group predictions to conduct a pre-registered, time-forward **settlement-error reconciliation diagnostic**: estimate whether group-hour residual offsets can be predicted from training-only data without using evaluation residuals, then assess only in a later untouched chronological holdout. Do not fit a calibration to the reused 2024–25 period. This is distinct from SM50's descriptive uncertainty bins, SM54/55's retrospective arithmetic decomposition, and SM56's fixed-alpha model mixing; any predictive correction would require a new preregistration and leakage audit before training.
