"""Freeze passing P0 source/presentation controls and inherited numerical evidence."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write
from scripts.software_local_feasibility_v034 import (
    CANDIDATES, checked, inventory, presentation_binding, validate_inventory,
)
from scripts.software_paired_o1_v033 import inherited_candidate

SOURCE = Path(__file__).resolve().parents[1]


def qualify(data_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Require a clean committed v034 execution snapshot")
    controls = Path(controls).resolve()
    evidence, summaries, files = {}, {}, {}
    for name in ("presentation", "world", "runner", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        checks = value.get("checks", [])
        if (not checks or any(row.get("returncode") != 0 for row in checks)
                or not value.get("file_sha256") or value.get("model_calls") != 0
                or value.get("gpu_used") is not False):
            raise ValueError("Require passing targeted zero-model CPU evidence: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("CPU source references must stay inside the checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("A CPU-checked P0 file changed: " + relative)
            files[relative] = expected
        evidence[name] = reference(path)
        summaries[name] = {"checks": checks, "scope": value.get("scope"),
                           "coverage_notice": value.get("coverage_notice")}
    presentation = presentation_binding(data_root)
    audit = read_json(presentation["audit_report"]["path"])
    route_budget = read_json(checked(presentation["reference_route_budget"]))
    if (audit.get("passed") is not True or audit.get("model_calls") != 0
            or audit.get("gpu_used") is not False or audit.get("weights_loaded") is not False
            or audit.get("totals", {}).get("unique_calls") != 16
            or audit.get("totals", {}).get("missing_stages") != 0):
        raise ValueError("Require the one predeclared native-token presentation audit")
    slots = validate_inventory(inventory())
    parents = {candidate: inherited_candidate(data_root, candidate) for candidate in CANDIDATES}
    from proworksim.software_tasks_v034 import ASSETS, TASK_IDS, build_case
    cases = {task_id: build_case(task_id) for task_id in TASK_IDS}
    if (set(TASK_IDS) != {row["case_id"] for row in slots}
            or any(case["purpose"] != "model_interface_development"
                   or case["training_eligible"] is not False or case["task_definitions"] != {}
                   or case["initial_owners"] != {} for case in cases.values())):
        raise ValueError("Require the two new empty-task development roots, never training material")
    asset_files = {str(path.relative_to(SOURCE)): digest(path.read_bytes())
                   for path in sorted(ASSETS.rglob("*")) if path.is_file()}
    if not asset_files.keys() <= files.keys():
        raise ValueError("Every frozen source asset must be bound to P0 CPU qualification")
    result = {"version": "software-local-feasibility-cpu-v0.34", "passed": True,
        "source": source, "model_calls": 0, "gpu_used": False, "file_sha256": files,
        "controls": evidence, "checks": summaries, "presentation": presentation,
        "presentation_measurements": audit["totals"],
        "reference_route_budget": {
            key: route_budget[key] for key in (
                "passed", "model_calls", "gpu_used", "weights_loaded", "reference_routes",
                "unique_scripted_calls", "native_request_measurements", "limits", "limitations")},
        "behavior_distribution_preserved": False,
        "source_assets_sha256": asset_files,
        "source_contracts": {task_id: case["source_contract"] for task_id, case in cases.items()},
        "inventories": {candidate: slots for candidate in CANDIDATES},
        "inherited_learning_evidence": parents,
        "new_P1_episodes": 8, "new_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
        "automatic_P2_P3_execution": False,
        "scope": "One predeclared input audit and exact contract deduplication plus a declared public-test "
                 "feedback projection, not lossless latest-feedback preservation; new flat-domain roots, "
                 "joint/one-side/dependency and real-world legal-route CPU controls with separately derived "
                 "native budget witnesses; eight T development "
                 "slots on inherited current actors. No new model qualification, numerical update, "
                 "behavioral-invariance, independent-source, training-support or allocation-effect claim."}
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
