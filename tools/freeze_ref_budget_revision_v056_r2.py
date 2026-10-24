"""Seal the pending-only protocol correction without changing any scientific condition."""
from __future__ import annotations

import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v056/runtime-r2"
MANAGED_ONLY = {"src/proworksim/software_benchmark_managed_v056.py",
                "src/proworksim/software_benchmark_managed_worker_v056.py",
                "src/proworksim/software_benchmark_public_tests_v056.py"}


def main():
    old_ref = reference(ROOT / "artifacts/software-benchmark-v056/runtime-r1/bindings.json")
    old = json.loads(checked(old_ref).read_bytes())
    proof_ref = reference(ROOT / "artifacts/software-benchmark-v056/empty-tools-protocol-r2/result.json")
    proof = json.loads(checked(proof_ref).read_bytes())
    equality = json.loads(checked(proof["tokenizer_equivalence"]).read_bytes())
    if (proof.get("passed") is not True or proof.get("benchmark_generation_replayed") is not False
            or proof.get("neutral_generation_requests_started") != 1
            or equality.get("all_input_ids_equal") is not True
            or equality.get("matches_original_failed_request_exact_input") is not True):
        raise ValueError("Exact tokenizer equality and one separate neutral HTTP control must pass")
    OUT.mkdir(parents=True, exist_ok=False)
    files = [reference(path) for directory in (ROOT / "src/proworksim", ROOT / "tools")
             for path in sorted(directory.rglob("*"))
             if path.is_file() and path.suffix in {".py", ".sh"} and "__pycache__" not in path.parts
             and str(path.relative_to(ROOT)) not in MANAGED_ONLY]
    source = write_new(OUT / "source-manifest.json", {
        "version": "v056-ref-budget-source-manifest-r2", "files": files,
        "predecessor": old["frozen_sources"], "protocol_control": proof_ref,
        "old_entered_slots_replayed": False, "scientific_conditions_changed": False,
        "excluded_managed_only_not_imported_by_REF": sorted(MANAGED_ONLY)})
    new = dict(old, frozen_sources=source,
               queue_root=str(ROOT / "runs/software-benchmark-v056/queue-r2"),
               runtime_revision="v056-r2-empty-tools-normalization",
               predecessor_binding=old_ref, protocol_control=proof_ref,
               preparation_actual_tokens=proof["known_neutral_actual_tokens"])
    print(json.dumps(write_new(OUT / "bindings.json", new)))


if __name__ == "__main__":
    main()
