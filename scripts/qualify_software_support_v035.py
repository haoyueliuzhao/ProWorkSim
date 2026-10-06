"""Bind the new P2 CPU evidence to one clean, frozen execution checkout."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]


def qualify(data_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Require a clean committed v035 execution snapshot")
    controls = Path(controls).resolve()
    evidence, coverage, files = {}, {}, {}
    for name in ("world", "mapper", "learning", "runner", "allocation", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        checks = value.get("checks", [])
        target_calls = value.get("target_model_calls", value.get("model_calls"))
        cpu_model_with_unobserved_cuda = (name == "learning" and value.get("gpu_used") is None
            and value.get("gpu_model_execution") is False and value.get("cuda_initialization_observed") is False
            and value.get("execution_device") == "cpu")
        if (not checks or any(row.get("returncode") != 0 for row in checks)
                or not value.get("file_sha256") or target_calls != 0
                or not (value.get("gpu_used") is False or cpu_model_with_unobserved_cuda)):
            raise ValueError("Require passing targeted zero-target-model CPU evidence: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("CPU implementation references must stay inside the checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("CPU-checked bytes changed: " + relative)
            files[relative] = expected
        evidence[name] = reference(path)
        coverage[name] = {key: value.get(key) for key in ("scope", "coverage_notice", "checks", "target_model_calls",
            "synthetic_tiny_cpu_model_calls", "gpu_used", "gpu_model_execution", "execution_device", "cuda_initialization_observed")}
    from proworksim.software_tasks_v035 import ASSETS, TASK_IDS, build_case
    cases = {task_id: build_case(task_id) for task_id in TASK_IDS}
    asset_files = {str(path.relative_to(SOURCE)): digest(path.read_bytes())
                   for path in sorted(ASSETS.rglob("*")) if path.is_file()}
    if not asset_files.keys() <= files.keys():
        raise ValueError("Every new source asset must be bound to CPU controls")
    # The P1 result is evidence for selecting the inherited carrier, never P2 material.
    p1_path = Path(data_root) / "docs/experiments/software-local-feasibility-v034.json"
    p1 = read_json(p1_path)
    if (p1.get("status") != "complete" or p1.get("next_stage", {}).get("local_carrier_for_p2_design") != "qwen3.5-9b"
            or p1.get("optimizer_steps") != 0):
        raise ValueError("Require the completed unchanged P1 decision for 9B")
    from scripts.software_support_v035 import inherited_candidate, inventories
    inherited = inherited_candidate(data_root)
    rows = inventories()
    purposes = {"support": "policy_training", "development": "contribution_development",
                "confirmation": "independent_confirmation"}
    if {name: len(rows[name]) for name in purposes} != {"support": 16, "development": 4, "confirmation": 4}:
        raise ValueError("Freeze 16 support slots and two distinct four-unit later panels")
    for name, purpose in purposes.items():
        if name != "support" and len({row["case_id"] for row in rows[name]}) != 2:
            raise ValueError("Development and independent panels each need two roots")
        for row in rows[name]:
            case = cases[row["case_id"]]
            if (case["purpose"] != purpose or case["training_eligible"] is not (purpose == "policy_training")
                    or case["task_definitions"] != {} or case["initial_owners"] != {}):
                raise ValueError("Source purpose and autonomous task formation must be exact")
    roots = [{row["case_id"] for row in rows[name]} for name in purposes]
    if any(roots[i] & roots[j] for i in range(3) for j in range(i)):
        raise ValueError("Purpose-separated root inventories cannot overlap")
    result = {"version": "software-support-cpu-v0.35", "passed": True, "source": source,
        "target_model_calls": 0, "gpu_used": False, "new_target_model_updates": 0,
        "qualification_command_scope": "Read-only CPU source/evidence binding; gpu_used=false refers to this qualification command. The earlier tiny CPU control did not measure CUDA initialization/resource telemetry; its null observation remains explicit in coverage.learning.",
        "file_sha256": files, "controls": evidence, "coverage": coverage,
        "P1_carrier_evidence": reference(p1_path), "inherited_learning_evidence": inherited,
        "source_assets_sha256": asset_files,
        "source_contracts": {task_id: case["source_contract"] for task_id, case in cases.items()},
        "inventories": rows, "new_P2_episodes": 16, "P2_optimizer_updates": 0,
        "near_16k_qualification_repeated": False, "automatic_unfrozen_P3_execution": False,
        "scope": "New source/Mapper/current-window bindings and v030 allocation-consumption interface controls; tiny CPU learning is separate from target-model work. No P1 relabeling, new model qualification, sampled current support, post-update contribution feedback or independent allocation gain is claimed."}
    write(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.data_root, args.controls, args.output)["passed"])


if __name__ == "__main__":
    main()
