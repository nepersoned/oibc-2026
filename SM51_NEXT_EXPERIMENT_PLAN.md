# SM#51 Next Experiment Plan

## Single hypothesis

**H1:** A regularized, plant-specific morning–afternoon response to solar azimuth, estimated only from past observed generation, adds site-level forecast information beyond shared solar geometry and supplied WA/WB weather, and reduces reference-composition settlement W on forward dates.

This is a *historical solar-shape response proxy*. It must not be called measured panel azimuth or tilt. It is selected as the next hypothesis because the provided `sites.csv` has capacity and shifted coordinates but no panel-orientation field, while existing Site models use shared solar geometry and do not include an orientation observation. SM#11, SM#12, SM#41 F2, SM#42 F3 and SM#50 already covered daily correction, direct external irradiance, cloud attenuation, forecast revision and uncertainty-regime diagnostics; those variants are not repeated.

## Inputs and feature definition

- Competition-provided historical generation, capacity, timestamps, WA/WB forecasts, site metadata and the existing solar elevation/azimuth calculation only.
- For each site, estimate one signed morning-versus-afternoon solar-azimuth response coefficient from prior-only, time-ordered out-of-fold site residuals. Use a fixed shrinkage rule toward zero/fleet mean; store an eligibility/missingness flag and shrink sparse histories rather than assigning a fabricated orientation.
- Estimate the coefficient from daylight samples with valid forecasts and generation, normalized by site capacity. Control the residual construction for existing solar elevation, clear-sky geometry and supplied weather so the proxy represents persistent site-specific shape left after the baseline. Do not infer or reconstruct original coordinates.
- For every model-training row, the coefficient must be calculated only from residuals whose target times precede that row's feature cutoff. For validation, fit the signature on the two-year training window only. Respect the official day-ahead information cutoff; if generation release latency is undocumented, exclude at least the immediately preceding target day from history.

## Comparison and evaluation

1. Freeze the SM46 A1-REF reference composition, weekday calendar, WA/WB-only source controls, rich LightGBM parameters, 2-year window, Group seed100 prediction/settings and alpha=0.2. No composition, loss, seed or weather-source changes.
2. Baseline: same-feature Site3 + frozen Group100 blend. Candidate: add only the preregistered solar-shape coefficient and eligibility flag to the Site model, using the same Site seeds 7/21/42 and alpha=0.2.
3. Use strict rolling-origin folds to construct training residuals and site signatures. Within each evaluation fold, no target generation from that fold may affect a feature. First selection period 2023–24; follow-up 2024–25 with the formula and shrinkage rule frozen before examining that result.
4. Score identical reference composition, observed site-hour mask, SMP, peak multiplier and official `src/scoring.py` W. Cross-check with an independent hourly sum. Report whole-period, G1/G2, 11–15, monthly W, site/group MAE, signed bias, eligibility and coverage distribution, and 168-hour paired block bootstrap.
5. Pre-register rejection rules: no adoption if 2023 W fails to improve, 2024 direction reverses, monthly W worsens by more than 5%, the bootstrap interval includes zero, or any as-of-time/feature-lineage check fails. The historical windows have been reused; these results are not an untouched independent test.

## Required artifacts and gates

- Preserve feature-generation code, per-fold cutoffs, training-only residual/signature manifests, input hashes and forecast hashes.
- Before model work, verify target-day and 17:00 availability semantics, generation reporting delay, minimum site history, and that the fixed shrinkage procedure is estimable without validation outcomes.
- Recover an authentic ens_v3 prediction/manifest bundle from its original owner if a direct leaderboard-gap residual comparison is desired. Without it, any improvement claim is local A1-REF versus candidate only.
- No external GFS/LDAPS/Open-Meteo or external calendar data unless the organizer provides explicit permission. No future actuals, forecast-period observation coverage, reconstructed plant coordinates, composition search, dynamic alpha, or portal submission.

## Cost and expected information

This is a medium/high-cost feature experiment because training residuals need rolling-origin generation and profile estimates must be strictly prior-only. The expected new information is whether persistent site-specific solar response explains shape errors that shared solar geometry and site-independent weather features miss. An inconclusive result is acceptable; it should close this hypothesis rather than trigger an unregistered sweep over profile formulas.
