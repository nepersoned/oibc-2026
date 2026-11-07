# SM#47 Preregistration — Calendar-Safe L1 vs L2 Pilot

Registered 2026-11-07 KST before the SM47 L1 model fit. Branch `seongmin`; starting revision `c5ee70a79fe703c6a5046ea07afc1a9414531b69`.

## Prior experiment and distinction

`EXPERIMENTS.md` records JH#7 as rich + L1 with W 204,815,516 KRW, worse than JH#6 rich + default objective at 204,043,129 KRW, and marks it failed. The log does not specify seed, calendar feature source, external-data configuration, validation window, Site/Group blend, or detailed LightGBM parameters. It is evidence against L1 as a default choice, but not a reproducible controlled comparison under SM46.

SM47 is a deliberately narrow pilot under the later SM46 setup: weekday-only calendar, participant WA/WB only, no external weather, reference composition, current rich Site features with `site_code` removed, two-year time-forward training, and a fixed existing weekday Group seed100 forecast at alpha 0.2. Stage A changes only the Site objective at seed 7. Because the historical JH#7 details are incomplete, this distinguishes the implementation context, not a claim that the earlier L1 result was invalid.

## Fixed comparison

- C0: existing A1 weekday Site seed7 prediction for 2023–24; `objective=regression` (LightGBM L2 default).
- C1: freshly fit same Site inputs/period/settings, seed7, `objective=regression_l1`.
- Both are redistributed against the same frozen SM45 A1 weekday Group seed100 prediction for 2023 with alpha 0.2 and reference composition.
- No Group refit, alpha/feature/seed tuning, weighting, new data, or composition changes.
- W is computed over the exact observed site-hour mask, SMP and peak-hour weights. Official `scoring.score` must match independent hourly penalties within `1e-5` KRW.

## Sequential stop rules

1. Run Stage A only: 2023–24 Site seed7 L2 vs L1.
2. If C1 W is not strictly below C0 W, stop immediately. Do not fit 2024 or seeds21/42, do not bootstrap, and do not make a new submission candidate.
3. Only if Stage A improves, run 2024 seed7. Continue only if both years improve.
4. Only if both single-seed periods improve, run 5,000 paired 168-hour bootstrap on 2024, seed7. Continue only if the 95% CI upper bound is below zero.
5. Only after all above pass, fit L1 seeds21/42 and compare the 3-seed candidate with the frozen SM46 A1-REF 3-seed predictions in both years.

Final candidate adoption still requires the existing SM45 criteria: both-year improvement vs SM46 A1-REF, 2024 bootstrap upper bound <0, no complete-month worsening >5%, no leakage/format issues, and complete reproducibility. No validation result will be used to tune the L1 model.

## Protection and compliance

Do not overwrite or modify any SM46/SM41 submission CSV or their prediction artifacts. Use only competition-provided training generation and WA/WB forecasts; test forecasts only for inference. `OIBC_CAL_MODE=weekday`; `OIBC_GFS=0`, `OIBC_GEFS=0`, `OIBC_UM=0`, `OIBC_SRC=prov`, `OIBC_SPATIAL=none`, `OIBC_PHYSICS=none`, `OIBC_EXT_SOURCES=no_openmeteo`; `OIBC_WX2` unset. Site and Group use `--ext none`. No `holidays`, `EXTRA_OFF`, future generation, or observed test weather.

The existing SM46 forecasts and compositions are immutable controls. If Stage A stops, no SM47 forecast CSV is generated and SM46 A1-REF remains the recommended candidate. No portal submission.
