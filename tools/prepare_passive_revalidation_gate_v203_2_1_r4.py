"""Bind original first-two evidence to a corrected, score-independent gate."""
from __future__ import annotations

import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/software-benchmark-v203-2-1/passive-pilot12-r2"
OUT = ROOT / "artifacts/software-benchmark-v203-2-1/capture-recovery-r4"


def prepare():
    from proworksim import software_benchmark_scope_v203_2_1_r4 as scope
    original = BASE / "api-coordinator/engineering-gate.json"
    value = {"version": "v203.2.1-first-two-archive-revalidation-gate-r4",
        "passed": True, "predeclared_indices": [2032200, 2032201],
        "scores_used_for_gate": False, "new_model_calls": 0,
        "original_gate": reference(original),
        "measurements": [reference(OUT / f"{i}-measurement.json") for i in (2032200, 2032201)],
        "generation_results": [reference(BASE / f"episodes/{i}/result.json") for i in (2032200, 2032201)],
        "usage_records": [reference(BASE / f"api-coordinator/usage-records/{i}.json") for i in (2032200, 2032201)],
        "parser_source": reference(ROOT / "tools/analyze_passive_capture_v203_2_1_r4.py"),
        "original_failed_analysis_and_gate_preserved": True,
        "source_of_recovered_evidence": "untouched_hash_verified_controller_output_archives",
        "thresholds_changed": False, "original_model_attempts_replayed": False}
    # Validate before publishing a passed gate. The validator independently
    # checks source refs, original usage, identities and predecessor cleanup.
    scope.validate_revalidation(value)
    result = write_new(scope.REVALIDATION_FILE, value)
    return {"gate": result, "model_calls": 0, "old_state_modified": False}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
