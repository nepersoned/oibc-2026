# SM#49 Final Selection Recommendation

## Recommendation

**Use Candidate A, SM46 A1-REF, if one final submission must be chosen under the existing preregistered conservative policy.** It is the reference composition and passed the local format validator. The pair is:

- Composition: `C:\Users\ehfal\Documents\Codex\2026-11-05\oibc-2026-0-ml-research-engineer\work\oibc-2026\outputs\sm46\composition_sm46_a1_ref.csv`
- Forecast: `C:\Users\ehfal\Documents\Codex\2026-11-05\oibc-2026-0-ml-research-engineer\work\oibc-2026\outputs\sm46\forecast_sm46_a1_ref.csv`
- Composition SHA256: `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd`
- Forecast SHA256: `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008`

Do not substitute another candidate's composition. The recommendation is a risk choice under available evidence, not a claim that A has the best expected leaderboard score.

## Why A remains the primary choice

A is the only one of the three candidates using the reference grouping. It is the safer decision where the optimized composition's validation reuse is a material concern. It also has a small point W advantage over the SM41 legacy baseline on both full-year score periods (−81,119 in 2023–24 and −8,019 in 2024–25), although the previous SM46 report says the 2024 paired confidence interval does not establish that difference as reliable.

Candidate C has the best observed point W in 2024–25 (3.188M below A) and on the previously inspected Dec–May segment (1.498M below A). That is meaningful evidence and should not be discarded. But 2024 full-year performance includes June–November used during composition selection; the half-year segment and 2024 interval have also been revisited repeatedly. The C−B bootstrap interval for adding the Group model at the same optimized composition includes zero. C also exceeds A's 2023 W by 66,674, and the 2023 Group fit had no eligible G2 labels. Future submission performance is unknown.

Candidate B is a useful diagnostic that isolates the optimized Site-only portfolio from Group blending, but the composition itself was selected from reused validation residuals. It is not the conservative default.

## Remaining risk and submission procedure

The local Validator only checks file format, time grid, group capacities, and value validity. The current official DataEn rules forbid non-provided external data and information produced after the previous-day 17:00 KST cutoff; the models' manifests and feature lists show weekday-only calendar inputs and no external weather/holiday feature families. The supplied test period contains 264 missing WA station-round rows; none is missing from both rounds, and the established round fallback yielded complete finite forecasts. This does not eliminate model-shift risk between validation's observed-site mask and the all-site submission period.

The 2026 briefing slide deck was not found in the checked repository. This decision uses the rule and scoring facts supplied by the user and the participant package, without treating a 2023 slide as 2026 material. The official [DataEn 2026 OIBC page](https://dataen.ai/en/challenge/2026) confirms the 17:00 KST cutoff and external-data prohibition.

The number of remaining official submissions cannot be read from local files. Check it in the portal before upload. No portal action was taken. A, B, and C are all validator-passing local files; their exact pairs and hashes are listed in `SUBMISSION_READINESS_AUDIT.md` and `submission_files_manifest.json`.
