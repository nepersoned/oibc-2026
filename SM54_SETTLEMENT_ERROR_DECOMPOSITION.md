# SM#54 Settlement Error Decomposition — Artifact Gate Stop

Date: 2026-11-08 (KST)
Branch: `seongmin`
Starting revision: `303a17ad6839088672342049471386cce6216a88`
Status: **stopped before scoring because the frozen Group prediction SHA256 did not match its SM53 manifest.**

## 1. Integrity audit

The two Site predictions and both already-saved redistributed blends exist and match the hashes recorded by SM53. The Group prediction path exists, but its bytes do not match the hash recorded in `outputs/sm53/pilot_2024.json`.

| Artifact | Path | Manifest / expected SHA256 | Current SHA256 | Result |
|---|---|---|---|---|
| Baseline Site seed7 | `outputs/val_sm45_a1_s7_sites.parquet` | `dcbdae2be77aab72a864f8c973ada8d3c0d8e9a78e62541d700095bc06e43f26` | same | Match |
| Candidate Site seed7 | `outputs/val_sm53_profile_s7_sites.parquet` | `1ba0066f6457f8eb242673124ca882ef98c3a09c167b04815dc8f853a08eacf4` | same | Match |
| Frozen Group seed100 | `outputs/sm45/group_a1_2024.parquet` | `651b2f296316139af6ccf6aecabdd3071b1710de6fff35df18ecd20bb63b58b7` | `651b2f296316139af6ccf6aecabdd3073b1710de6fff35df18ecd20bb63b58b7` | **Mismatch** |
| Baseline redistributed blend | `outputs/sm53/baseline_blend_2024.parquet` | `a0332f098ef64959c7b47f04ebfd3e2e6c72fb75d0660aea2822f908b6ea4cfa` | same | Match |
| Candidate redistributed blend | `outputs/sm53/candidate_blend_2024.parquet` | `69d9422d79a5806b5d378fb5bc4d39fbcfe109775b2f86124e994c8a1055208a` | same | Match |

The mismatch is in the Group artifact's digest, with `...b3071b171...` recorded and `...b3073b171...` present. Per the preregistered rule, analysis stopped here. No alternate Group file was searched for or substituted, no predictions were regenerated, and no model was trained.

## 2. Requested decomposition status

| Metric | Baseline | Candidate | Δ |
|---|---:|---:|---:|
| Site MAE | Not recomputed | Not recomputed | Not Run |
| Weighted individual W | Not Run | Not Run | Not Run |
| Group settlement W | Not recomputed | Not recomputed | Not Run |
| Cancellation benefit | Not Run | Not Run | Not Run |
| G1 W | Not recomputed | Not recomputed | Not Run |
| G2 W | Not recomputed | Not recomputed | Not Run |
| Peak W | Not recomputed | Not recomputed | Not Run |

SM53's previous report recorded baseline blended W `198,977,095.7827` KRW, candidate blended W `199,849,639.9321` KRW, and a difference of `+872,544.1494` KRW. These are cited as prior reported values only; SM54 did **not** reproduce them because the frozen Group hash gate failed. Consequently no new statement can be made about whether the difference came from increased weighted individual error, reduced cancellation benefit, or both.

The previously reported Site MAE improvement and G1/G2/peak W deltas are likewise not revalidated by SM54. The identity `ΔW_group = ΔW_individual − ΔC_cancel` remains the planned accounting method, not a computed result in this run.

## 3. Decision and next step

The observed mismatch is an artifact-provenance discrepancy, not evidence about the error mechanism. From the registered next-step options, recommend **stopping additional model experiments and focusing on official submission management**; the existing SM46 candidate remains the established choice. If the decomposition is revisited, first reconcile the Group artifact's provenance in a separate audit and preregister that follow-up. Do not tune any correction on the 2024 outcomes. No official score or new submission was produced.

The existing SM46, SM48, ens_v3, and submission files were not modified. No output CSV or model file was created.
