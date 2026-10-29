# Qwen admission binding recovery (v084)

2026-10-29. This revision repairs a deployment binding error and continues only unused original Qwen task identities. It does not change the model, task panel, seed, token budgets, context/output limits, tool schema, or candidate selection.

## Observed failure

The v080 coordinator stopped at 13:44:44 (Asia/Shanghai) with `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`. Its summary preserves 226 generation records, 110 score records and 47 delivery records. Four scheduled episodes also have terminal `technical_unknown` results and successful cleanup receipts; the coordinator stopped before incorporating them in its summary. They are retained as consumed episodes, not regenerated. The summary leaves 2,770 original identities unentered.

The exact v080 unit is inactive with MainPID 0. The four existing model residents (model-1, model-3, model-4, model-5) retain their original PID/start-tick identities and cgroups. There are no active Qwen episode resource claims, while the four model claims remain. No model unit was stopped or reloaded during this repair.

## Confirmed defect and boundary of attribution

`clone_namespace()` first installs keyword overrides, then clones functions declared by the source module. That second step silently overwrites callable overrides with cloned old functions. Inspection of the actual admission function proves that v080 calls the original v076 `pending_pairs` reader and evaluator rather than the intended safe replacements. v079 also uses the old reader; its evaluator was installed after cloning and therefore works as intended.

The old reader passes the contents of `controller-ready.json` directly to `json.loads`. The status writer can expose an empty or partially written file. The intended v080 reader classifies such a marker as pending, but the deployed binding never reached it. This is a directly reproduced binding defect consistent with the recorded parse failure. The old summary does not contain a complete exception traceback, so this document does not claim to identify the exact transient file that caused that specific stop.

## Repair

v084 installs the safe reader and evaluator **after** cloning the private namespace, then checks their identities through the real `admission_snapshot.__globals__` binding before returning the policy. Incomplete, malformed, missing, unreadable, or unqualified startup markers remain pending and do not admit a new materialized actor. Valid fully decoded markers alone enter the materialization cache. Invalid physical actor identities still fail closed.

The separate v084 scope, preparation tool, launcher and runner preserve frozen v076/v080 sources. Preparation imports the stopped summary, incorporates terminal results missing from it, carries score/delivery/usage records forward and audits original physical identities. Any consumed or scheduled identity without a trusted result remains technical unknown; it is never automatically replayed. Only previously unused identities enter the generation queue. Existing original score identities are reused only when unconsumed.

The new ordinary-user coordinator retains four generation workers, one scoring worker, 4 CPU and 32 GiB memory limits. It discovers the four existing residents and creates no replacement model services. Model-visible configuration and shared-server settings remain unchanged. Preparation and launch remain separate actions, performed by the main operator after review; implementation validation does not start experiments.

## Necessary validation

`tests/test_qwen_recovery_v084.py`: **7 passed**. Tests exercise actual episode/policy admission with empty JSON, partial JSON, invalid UTF-8 and a non-object marker, then a valid marker and cached completion. They assert the actual reader/evaluator binding, unchanged frozen bindings, rejection of API identities, and unchanged worker counts and owner bounds. The tests perform no model/API/Docker calls.

Machine-readable evidence: `artifacts/software-benchmark-v084/binding-recovery-evidence-r1/report.json`. Earlier runtime sources and original task records were not modified.

## Deployment observation, 2026-10-29 14:53:41 (Asia/Shanghai)

The main operator prepared and launched v084 successfully at approximately 14:40:29. The subsequent read-only observation found a fresh progress file (0.70 seconds old), `phase=running`, `failure=null`, four active generation futures and four actual Qwen actor claims. This confirms restored queue operation at the observation time; it is not a claim that all individual episodes succeed.

The first four scheduling events, at 14:41:00–14:41:17, bound the following original task identities to the existing model residents. Each resident's host PID and start tick matched its original readiness record; its original model child PID remained present in the same resident cgroup, and no closed marker existed.

| First task slot | Resident | Original host PID | Original model child PID | Identity at observation |
| --- | --- | ---: | ---: | --- |
| 304 | model-1 | 756444 | 756461 | Matched |
| 307 | model-3 | 4107048 | 4107055 | Matched |
| 308 | model-4 | 405407 | 405448 | Matched |
| 311 | model-5 | 441948 | 442032 | Matched |

All six runtime source files still matched their sealed SHA-256 and byte size. In particular, the resource adapter containing the post-clone safe binding remained `dc6d33c75fbc6b10a1cab9c838a670f1b3db4b73300d18a2b198fa959df8939a`. The running deployment therefore retains the source containing the previously verified real-admission binding and its startup identity assertion; this observation does not inspect the process's Python heap or repeat the CPU tests.

Slot 308 had separately ended as `technical_unknown` after seven model calls because the controller did not produce a trusted closed episode. Its receipt explicitly has `batch_stop_required=false`; the main queue continued with four active tasks. That isolated episode requires later investigation and must not be counted as normal model failure or described as an absence of task-level anomalies.

Evidence: `artifacts/software-benchmark-v084/binding-recovery-evidence-r1/deployment-observation.json`. This verification only read project records, the exact four model process identities and source hashes, then added this report. It did not call a model, change a source file, repeat CPU tests, or stop/operate a service.
