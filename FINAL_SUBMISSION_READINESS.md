# Final Submission Readiness Audit

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `0bfce1d986f4b59e073e8b876522c12dbef3aea7`

## Summary

- Highest recorded official score: **S2 `ens_v3`, 6,459,800,168**. It remains the team's score leader; local records do not contain an authentic ens_v3 submission file, prediction bundle, or manifest, and its recorded external weather inputs conflict with the public outside-data restriction absent an organizer exception.
- Most conservative locally verified candidate: **S4 / SM46 A1-REF**. Its provided-data lineage is documented, all 13 manifest-listed source/seed artifacts checked here match, its submission CSV hashes match the manifest, and the official local format validator exits 0.
- Format validation and rule eligibility are separate. The validator checks file shape and values; it does not approve model data lineage or external-source use.
- The exact remaining submission count is **not determined from repository records**; confirm it in the official portal.
- No model training, candidate changes, CSV rewrites, or portal actions were performed.

## Submission and candidate readiness

Official scores below are those recorded in `MODEL_SCOREBOARD.md` and `SUBMISSIONS.md`; they were not refreshed from a portal session during this audit. `—` means no local artifact hash is available.

| Model | Official score S | Input data lineage | Reproducibility evidence | Rule status | Submission files / SHA256 | Validator | Still needs confirmation |
|---|---:|---|---|---|---|---|---|
| S1 `ens_ref` | 6,455,051,853 | Team log: provided forecasts plus external irradiance/JMA; Site 61.5% + Group 38.5%, reference composition | No concrete CSV, model bundle, or manifest found in this checkout; training window/runtime unverified | **Not confirmed**; external sources recorded, no organizer exception located | Log has wildcard `submissions/*_ens_ref.csv`; no local file/hash | Not runnable locally | Original submission/model bundle and any organizer rule exception |
| S2 `ens_v3` | **6,459,800,168** | Team log: Group GFS+LDAPS 56%, Site GFS 44%, reference composition; Group falls back to GFS after LDAPS ends 2026-04-02 | No ens_v3 CSV, OOF prediction, model bundle, or matching manifest found; exact training period, full feature lineage, package/runtime, and hashes unavailable | **Not confirmed; conflicts with the published outside-data rule on recorded lineage** unless the organizers issued an applicable exception | Log has wildcard `submissions/*_ens_v3.csv`; no local file/hash | Not runnable locally | Original bundle, exact training/config record, and written organizer clarification/permission |
| S3 `ens_v5` | 6,459,111,150 | Team log: GFS+LDAPS Site/Group 50/50, 50-site optimized composition, GFS fallback after 2026-04-02 | No concrete CSV, model bundle, or manifest found in this checkout; full training window/environment not verified | **Not confirmed; conflicts with the published outside-data rule on recorded lineage** unless an applicable exception exists | Log has wildcard `submissions/*_ens_v5.csv`; no local file/hash | Not runnable locally | Original bundle and any written organizer clarification/permission |
| S4 / SM46 A1-REF | 6,448,069,881 | Provided WA/WB forecasts, generation history, site metadata, SMP and timestamp-derived weekday; no external weather or holiday data. Two-year pre-submission training window; weekday calendar; reference composition; Site3 + Group100, 80/20 | `manifest_a1_ref.json`, code commit `c5ee70a79fe703c6a5046ea07afc1a9414531b69`, Python 3.11.15 / LightGBM 4.7.0 / pandas 3.1.1 / NumPy 2.4.6. Manifest-listed data and seed prediction hashes checked: **13/13 match** | **Consistent with the published provided-data restriction** based on the recorded/local lineage; this is a lineage audit, not a separate organizer ruling | [`outputs/sm46/composition_sm46_a1_ref.csv`](outputs/sm46/composition_sm46_a1_ref.csv) — `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd`<br>[`outputs/sm46/forecast_sm46_a1_ref.csv`](outputs/sm46/forecast_sm46_a1_ref.csv) — `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` | **Exit 0**; 253 sites; G1 20,465.7 kW, G2 22,189.7 kW; 8,760 KST timestamps; 17,520 group-hours; no duplicate/missing keys, NaN, Inf, or negative forecast | Portal score remains as recorded; validator checks format only. Verify portal's remaining submission allowance separately. |

The public [DataEn OIBC 2026 challenge page](https://dataen.ai/en/challenge) states that data outside the competition-provided data may not be used and that models trained on external data may not be used (see the “유의사항” section). This published rule is why the externally sourced S1–S3 lineage is not marked cleared. No organizer exception or written permission for those inputs was found in the local record examined here.

## SM46 A1-REF file audit

Expected and current SHA256 values match:

| File | Relative path | SHA256 | Status |
|---|---|---|---|
| Composition | `outputs/sm46/composition_sm46_a1_ref.csv` | `374a7e01adf59d0724741121ceea09d434416530358107a6f62931471331dcfd` | Match |
| Forecast | `outputs/sm46/forecast_sm46_a1_ref.csv` | `8365c1fc7a075a54a10eec0cc1a8da9b93404852c5e1837b69a26ad8e3a09008` | Match |
| Candidate manifest | `outputs/sm46/manifest_a1_ref.json` | `7c06c08f571e56fc9e6156e2a8044dc3a8b1b7cc9cb580037a5011a3d7cdd68a` | Match |

The manifest records the reference composition, validator exit code 0, the 2025-06-01 01:00 through 2026-06-01 00:00 KST forecast window, training/configuration metadata, and input/code hashes. Of its manifest-listed source and seed prediction files that were present and checked, all **13 of 13** matched. The existing S4 CSVs were only read and validated; they were not regenerated or modified.

Exact validation command:

```powershell
.\.venv\Scripts\python.exe src\validate_submission.py --composition outputs\sm46\composition_sm46_a1_ref.csv --forecast outputs\sm46\forecast_sm46_a1_ref.csv
```

Result: exit code **0**. The validator checks composition membership/uniqueness and minimum group capacity; forecast group/time coverage, timezone, duplicates and finite nonnegative values. This does not evaluate prediction accuracy or independently decide data-rule compliance.

## Final handoff decision

### A. Highest recorded official score

**S2 `ens_v3` — 6,459,800,168.** Preserve this as the leaderboard score leader. Its score record does not establish rule eligibility or reproducibility. The recorded GFS/LDAPS lineage needs an organizer clarification, and the original prediction/model/manifest bundle is absent locally.

### B. Most conservative verified candidate

**S4 / SM46 A1-REF.** The exact local composition and forecast files above have matching hashes and pass the format validator. The available manifest and source lineage use competition-provided inputs, weekday-only calendar, and no external weather or holiday data. It is not the highest-scoring recorded submission; its official score is 11,730,287 points below ens_v3.

The submission ledger records at least four historical submissions, but this audit does not infer remaining attempts. Check the portal before any further manual submission. No automatic upload was made.
