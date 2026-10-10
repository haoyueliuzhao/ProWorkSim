# v0.45 authored organization diagnostic tasks

These four new roots were authored for this project from the 2026-10-10 audit specifications. They are **not reports of existing real-world bugs** and are not four independent upstream repositories. LA/HA share the artificial event-interface family; LB/HB share the artificial rule-interface family. Thus there are four task roots, two authored families, and zero new independent external repository sources. “Local” and “higher coordination opportunity” describe proposed contract structures; they do not establish difficulty or a benefit from collaboration.

| Label | Root | Public application API | Editable production files |
|---|---|---|---|
| LA | sc-event-utc-boundary-la-v045 | utc_date_key | event_time.py |
| HA | sc-event-import-atomic-ha-v045 | new_state/apply_batch/snapshot/restore/replay | event_store.py, recovery.py |
| LB | sc-rule-range-local-lb-v045 | evaluate | rules.py |
| HB | sc-rule-migration-hb-v045 | migrate_v1_to_v2/evaluate_v2 | migration.py, rule_v2.py |

Each directory freezes its public contract, incomplete initial application, public checks, same-contract private acceptance, separate complete reference, negative controls, and initial provenance. All initial artifacts/diagnostics and CPU witnesses are environment authorship, never current-member work. Initial diagnostics are actual finite public executions, shared with all initial and newly born members. `upstream_regressions` remains only the existing wire label for preserved **authored** API checks; no external upstream suite is claimed.

`source-partition.json` freezes development use with training, Contribution and independent confirmation eligibility false. `source-manifest.json` binds every per-root byte plus the generic API/diagnostic drivers. Its parent repository commit denotes authoring context; task files are identified by their manifest hashes and the eventual v045 source commit.

The model receives only initial/ and readonly/ files, the public contract, the generated public test driver and an initially empty optional `test_member.py`. Reference implementations, private inputs, counterexamples and initial-gap descriptions are excluded. Public/private expected tables were authored independently from the implementation and are not populated by executing its output.

A finite CPU witness is `reference_solution(root)`, write each declared production file, `run_tests`, `fix_patch`, `submit`; no task ownership, messages, extra members or fixed roles are required. Negative controls cover invalid-input relaxation (LA), nonatomic batches and lost revisions (HA), boolean/integer confusion and skipped nested validation (LB), null/missing confusion and input mutation (HB). Private checks enforce business properties, not evidence of teamwork. No model, tokenizer, GPU or gradient is invoked by fixture construction or business CPU controls.
