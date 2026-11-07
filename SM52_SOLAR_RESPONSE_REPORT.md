# SM#52 Solar-Shape Response Report

Date: 2026-11-08 (KST)
Status: **Stage 0 feasibility stop; no model experiment**
Reference candidate: SM46 A1-REF, unchanged.

## What was tested

This run audited whether the provided historical generation can support a leakage-safe plant-level morning/afternoon residual response feature. It did not create or score the feature. The stated hypothesis remains untested.

The source package includes historical generation for 253 plants. After two-year windows, daylight filtering, and the conservative 48-hour embargo, 2023–24 had 106 plants with any daylight observations and 2024–25 had 205. In the 2023 window, only 93 plants had at least 100 observed target days on both solar sides, representing 18.07% of portfolio capacity. G2 had six plants with any history, representing 2.61% of G2 capacity. 2024 support was better but still uneven: 173 plants had at least 100 days on both sides, representing 62.64% of total capacity.

## OOF and leakage status

No strict rolling-origin A1 Site OOF residual artifact or matching manifest exists in this checkout. SM45/SM46 validation predictions are out-of-training-window validation forecasts, not training-row OOF residuals. Using their residuals for training rows, or using in-sample residuals, would violate the registered as-of-time requirement.

No feature-generation code was written, so none of the requested automated leakage tests was run. Leakage behavior is therefore **not verified**, not passed. The audit preserves the right-closed `00:00` previous-target-day rule and uses 48 hours as a planning embargo, but no test claims that the feature path enforces them.

## Model and W results

| Stage | Result |
|---|---|
| 2023 seed7 baseline vs shape-feature W | Not run |
| 2024 seed7 W | Not run |
| G1/G2, peak/nonpeak, AM/PM, monthly W | Not run |
| Site/Group MAE and signed bias | Not run |
| Paired 168-hour bootstrap | Not run |
| Seeds 21/42 confirmation | Not run |
| SM52 submission forecasts / validator | Not generated / not run |

These are not zero effects and must not be interpreted as a model rejection based on score. The hypothesis was stopped because its required evidence and broad primary-year support were unavailable without a substantial, unimplemented rolling OOF pipeline.

## Decision and next step

Retain the existing SM46 A1-REF candidate; SM52 made no change to it or to any submission file. Do not claim improvement or deterioration in W. Before any future restart, establish that a rolling-origin OOF residual pipeline can be generated and audited at an acceptable cost, and decide whether 2023 site/capacity support is sufficient for a feature intended to affect group settlement. If either gate fails, do not train the candidate.

## Repository verification

`compileall -q src` passed. The full pytest run reported 55 passed and 3 failed; the failures are the pre-existing GFS synthetic-time/partial-export cases listed in the feasibility audit. `git diff --check` passed. No model or feature code was changed, so there is no SM52-specific feature test suite.
