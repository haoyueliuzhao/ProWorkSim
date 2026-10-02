# Frozen SWE-smith source tasks, v0.28

Three whole repositories were assigned purposes before any consumer requirement
was derived. This is an executable bounded import, not the full official Docker
benchmark or a set of current-policy trajectories.

| Task | Purpose | Pinned repository |
|---|---|---|
| `sqlparse-comparison-records` | `policy_training` | andialbrecht/sqlparse, `e57923b3aa823c524c807953cecc48cf6eec2cb2` |
| `schema-catalog` | `contribution_development` | keleshev/schema, `24a3045773eac497c659f24b32f24a281be9f286` |
| `textfsm-record-items` | `independent_confirmation` | google/textfsm, `c31b600743895f018e7583f93405a3738a9f4d55` |

`source-partition.json` is the original v0.27 whole-repository partition, retaining
`task_derivation_started=false` as its freeze-time statement. Each later
`derived-task.json` references that partition digest; the source inventory is not
rewritten after derivation. The dataset is `SWE-bench/SWE-smith-py` at revision
`77cab9055d42ab4a5c25c89a8f937096db13558e`, still the sole SWE-smith source family.

Each repository folder retains its original task row, original defect patch,
exact package source, original test module and license, plus the separately
identified project consumer requirement. `consumer-reference.py`, `acceptance.json`
and provenance assets are **controller-only**. `build_case` sends the actor only
the defective package, public contract, consumer stub, public original-test
subset and optional member test file. It never sends reference solutions or
independent expected values.

Use the existing Python environment:

```bash
.venv/bin/python scripts/import_software_sources_v028.py --qualify
.venv/bin/python scripts/import_software_sources_v028.py --download --qualify
```

The optional download verifies fixed archive/shard hashes and compares all three
selected original rows with the pinned Parquet dataset. No image is built and no
package install, model, API teacher or parameter update is involved. The source
adapter exports `build_case`, `run_public_tests`, `assess` and a controller-only
`reference_solution`. Integration into model collection must preserve each task's
purpose, fixed member identity and unchanged source partition.

See [the complete source qualification report](../../docs/experiments/software-sources-v028.md)
for execution results, raw-trace references, limitations and exact isolation
boundaries. Source code and licenses remain under their upstream terms; project
consumer code is separately derived. Dataset card and toolkit MIT license evidence
are in `provenance/`.
