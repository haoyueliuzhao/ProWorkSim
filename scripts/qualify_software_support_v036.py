"""Bind completed CPU controls and all frozen v036 source bytes to a clean checkout."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write

SOURCE = Path(__file__).resolve().parents[1]


def qualify(data_root, controls, output):
    from proworksim.software_tasks_v036 import TASK_IDS, CASE_PURPOSES, build_case
    from scripts.software_support_v036 import inherited_candidate, inventories
    identity = code_identity()
    if identity["code_dirty"] is not False:
        raise ValueError("Require the exact clean committed execution snapshot")
    controls = Path(controls).resolve()
    evidence, coverage, files = {}, {}, {}
    for name in ("sources", "member-tests", "methods", "integration", "execution", "cold-archive", "final-static"):
        relative_receipt = ("final-static.json" if name == "final-static" else
                            "methods/qualification-checks.json" if name == "methods" else name + "/checks.json")
        path = controls / relative_receipt
        value = read_json(path)
        checks = value.get("checks", [])
        if (not checks or any(row.get("returncode") != 0 for row in checks)
                or not value.get("file_sha256")
                or value.get("target_model_calls", value.get("model_calls")) != 0):
            raise ValueError("Require passing zero-target-model CPU controls: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Controlled implementation references must remain in the checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("CPU-checked bytes changed: " + relative)
            files[relative] = expected
        evidence[name] = reference(path)
        coverage[name] = {key: value.get(key) for key in ("scope", "checks", "target_model_calls", "gpu_used",
            "synthetic_tiny_cpu_model_calls", "execution_device", "cuda_initialized_before", "cuda_initialized_after")}
    required = [p for folder in ("src/proworksim", "scripts", "tests")
                for p in (SOURCE / folder).glob("*v036.py")]
    required += [p for p in (SOURCE / "examples/software-sources-v036").rglob("*") if p.is_file()]
    if not {str(p.relative_to(SOURCE)) for p in required} <= files.keys():
        raise ValueError("Every new implementation, test and source asset must be bound to CPU/static controls")
    production_path = controls / "member-tests/production-interpreter-checks.json"
    production = read_json(production_path)
    if (production.get("passed") is not True or production.get("target_model_calls") != 0
            or any(check.get("returncode") != 0 for check in production["checks"])
            or any(digest((SOURCE / name).read_bytes()) != expected for name, expected in production["file_sha256"].items())):
        raise ValueError("Require the actual production-interpreter member/archival CPU check")
    evidence["production_interpreter"] = reference(production_path)
    coverage["production_interpreter"] = {key: production[key] for key in ("reason", "interpreters", "scope")}
    resident_path = controls / "resident-environment.json"
    resident = read_json(resident_path)
    if (resident.get("same_stdlib_as_auxiliary_train_cpu_checks") is not True
            or resident.get("target_model_calls") != 0 or resident.get("model_constructed") is not False):
        raise ValueError("Bind the actual inherited resident separately from auxiliary CPU environments")
    evidence["actual_resident_environment"] = reference(resident_path)
    coverage["actual_resident_environment"] = resident
    rows = inventories()
    if {name: len(panel) for name, panel in rows.items()} != {"support": 16, "development": 16, "confirmation": 16}:
        raise ValueError("Keep one sixteen-slot support and two four-root by four-seed panels")
    cases = {key: build_case(key) for key in TASK_IDS}
    groups = {}
    for name, purpose in (("support", "policy_training"), ("development", "contribution_development"),
                          ("confirmation", "independent_confirmation")):
        groups[name] = {row["case_id"] for row in rows[name]}
        if len(groups[name]) != (1 if name == "support" else 4):
            raise ValueError("Incorrect source-root count")
        for row in rows[name]:
            case = cases[row["case_id"]]
            if (CASE_PURPOSES[row["case_id"]] != purpose or case["purpose"] != purpose
                    or case["training_eligible"] is not (name == "support")
                    or case["task_definitions"] != {} or case["initial_owners"] != {}):
                raise ValueError("Root purpose and autonomous task formation changed")
    if any(groups[a] & groups[b] for a in groups for b in groups if a != b):
        raise ValueError("Root purposes overlap")
    inherited = inherited_candidate(data_root)
    result = {"version": "software-support-cpu-v0.36", "passed": True, "source": identity,
        "target_model_calls": 0, "gpu_used": False, "new_target_model_updates": 0,
        "scope": "Read-only clean-source qualification of finite CPU controls. Synthetic program/SDK/tiny CPU learning evidence stays distinct from the unexecuted production 9B path.",
        "file_sha256": files, "controls": evidence, "coverage": coverage,
        "inherited_learning_evidence": inherited, "inventories": rows,
        "source_contracts": {key: case["source_contract"] for key, case in cases.items()},
        "old_v035_slots_training_or_support_admitted": False,
        "P2_optimizer_updates": 0, "repeat_near_16k_or_carrier_qualification": False,
        "automatic_unfrozen_P3_execution": False,
        "automatic_frozen_P3_execution_explicitly_authorized": True}
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
