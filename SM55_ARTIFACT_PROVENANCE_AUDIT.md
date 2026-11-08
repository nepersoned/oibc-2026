# SM#55 Artifact Provenance Audit

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `0868efc1b1ee5a3a6d9fd29ea829af32ae997e28`

## Finding

The SM54 stop was triggered by a **documentation typo**, not by changed Group prediction bytes. The actual `outputs/sm45/group_a1_2024.parquet` SHA256 is `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7`. It matches the hash in SM50, SM51, and `outputs/sm53/pilot_2024.json`. SM53's narrative report and the copied SM54 preregistration/report had `...b3071b171...`, where the correct digest contains `...b3073b171...`.

The original SM54 stop record is preserved as a historical record. This SM55 report resolves the discrepancy and resumes analysis using only the existing validated predictions.

## Cross-record checks

| Record/artifact | Current or recorded SHA256 | Finding |
|---|---|---|
| `outputs/sm45/manifest.json` | `554ec9223b97ddf6a8831354f9bc1fccfe91aa1e0eadfc0dc2697f7b3706f820` | Matches the manifest digest recorded in SM50; current manifest records SM45 runtime/source/output metadata. |
| SM50 Group 2024 prediction record | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | Matches the file. |
| SM51 Group artifact table | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | Matches the file; records 17,520 rows and schema. |
| `outputs/sm53/pilot_2024.json` Group hash | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | Matches the file. |
| SM53/SM54 Markdown Group hash | `651b2f296316139af6ccf6aecabdd3071b1710de6fff35df18ecd20bb63b58b7` | Typo: `1` appears where actual/manifest value has `3`. |

SM45's manifest hash table does not directly list the 2024 Group Parquet hash; the prediction hash is independently recorded in the downstream SM50/SM51 artifact tables and the SM53 JSON manifest. The manifest itself is the same file version referenced by SM50.

## Local artifact validation

| Artifact | SHA256 | Rows / schema | Time range | Key checks |
|---|---|---|---|---|
| Baseline Site seed7 `outputs/val_sm45_a1_s7_sites.parquet` | `dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26` | 2,216,280; `site_id, ts, kwh` | 2024-06-01 01:00–2025-06-01 00:00 KST | 253×8,760; unique keys |
| Candidate Site seed7 `outputs/val_sm53_profile_s7_sites.parquet` | `1ba0066f6457f8eb242673124ca882ef98c3a09c167b04815dc8f853a08eacf4` | 2,216,280; `site_id, ts, kwh` | same | 253×8,760; unique keys |
| Frozen Group seed100 `outputs/sm45/group_a1_2024.parquet` | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | 17,520; `group, ts, cf_hat, pred` | same | G1/G2 × 8,760; unique keys |
| Baseline blend `outputs/sm53/baseline_blend_2024.parquet` | `a0332f098ef64959c7b47f04ebfd3e2e6c72fb75d0660aea2822f908b6ea4cfa` | 2,216,280; `site_id, ts, kwh` | same | 253×8,760; unique keys |
| Candidate blend `outputs/sm53/candidate_blend_2024.parquet` | `69d9422d79a5806b5d378fb5bc4d39fbcfe109775b2f86124e994c8a1055208a` | 2,216,280; `site_id, ts, kwh` | same | 253×8,760; unique keys |

Both stored blend forecasts were compared row-for-row with a fresh in-memory call to the existing SM39 `redistribute()` using the verified Site and Group inputs, reference composition, and alpha 0.2. Maximum absolute difference was **0.0 kWh** for both blends. The existing Parquet files were not rewritten.

The common actual mask has 2,170,645 observed site-hours; settlement evaluation has 17,520 group-hours. No external inputs or newly generated predictions were used.

## Integrity conclusion

The mismatch was a character-level transcription error confined to SM53/SM54 Markdown references. The Group forecast itself is unchanged and its content hash is corroborated by three independent local records (SM50, SM51, SM53 JSON) plus direct hashing. Proceeding to SM55's arithmetic decomposition is therefore supported. The JSON manifest was not modified. The SM53 JSON manifest's current SHA256 is `035071b3f1582d2a2909b13a2d311a34e6d52e218b2a7789d5a7d9adc77b97bc`; the SM45 manifest SHA256 is `554ec9223b97ddf6a8831354f9bc1fccfe91aa1e0eadfc0dc2697f7b3706f820`.
