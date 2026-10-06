"""CPU-only qualification of four new roots and four unchanged retained panel roots."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from proworksim import software_tasks_v035 as retained
from proworksim import software_tasks_v036 as source
from proworksim.storage import atomic_write, digest, json_bytes, read_json


def source_binding():
    """Verify immutable retained roots and purpose boundaries without model work."""
    partition = source.source_partition()
    manifest = read_json(source.ASSETS / "source-manifest.json")
    old_manifest = read_json(retained.ASSETS / "source-manifest.json")
    if manifest["source_environments"] != old_manifest["source_environments"]:
        raise ValueError("The three pinned environment/commit/license/purpose bindings must remain identical")
    if manifest["retained_v035_manifest"]["sha256"] != digest((retained.ASSETS / "source-manifest.json").read_bytes()):
        raise ValueError("The archived v035 source manifest changed")
    cases = {name: source.build_case(name) for name in source.TASK_IDS}
    old_identity = {}
    for name in source.RETAINED_CASE_IDS:
        if cases[name] != retained.build_case(name):
            raise ValueError("Retained contract, code, test driver or source identity changed: " + name)
        old_identity[name] = {"complete_case_equal": True,
                              "source_contract_sha256": digest(json_bytes(cases[name]["source_contract"])),
                              "initial_files_sha256": digest(json_bytes(cases[name]["files"]))}
    for name, case in cases.items():
        if (case["purpose"] != source.CASE_PURPOSES[name]
                or case["training_eligible"] is not (name == source.TRAINING_CASE_ID)
                or case["task_definitions"] != {} or case["initial_owners"] != {}
                or "acceptance.json" in case["files"]
                or any(path.startswith(("reference/", "controls/")) for path in case["files"])):
            raise ValueError("A root changed purpose or exposed private reference/control material: " + name)
    return {"passed": True, "source_partition_sha256": partition["sha256"],
            "retained_root_identity": old_identity,
            "root_counts": {"policy_training": 1, "contribution_development": 4, "independent_confirmation": 4},
            "case_contracts": {name: case["source_contract"] for name, case in cases.items()},
            "scope": "Exact retained root/source identity and new purpose-bound task material; no generation or task assignment"}


def qualify(output, *, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    binding = source_binding()
    atomic_write(output / "source-binding.json", json_bytes(binding))
    jobs = []
    for case_id in source.NEW_CASE_IDS:
        variants = {**source.dependency_controls(case_id), **source.provenance_controls(case_id)}
        jobs.extend((case_id, name, files) for name, files in variants.items())
    for case_id in (*retained.CONTRIBUTION_CASE_IDS, *retained.CONFIRMATION_CASE_IDS):
        jobs.append((case_id, "retained_joint_reference", source.reference_solution(case_id)))

    def run(job):
        case_id, variant, files = job
        folder = output / "program-controls" / case_id / variant
        result = source.assess_files(case_id, files, run_root=folder)
        atomic_write(folder / "assessment.json", json_bytes(result))
        if result["executed"] is not True:
            raise ValueError("Actual sandbox execution incomplete: " + case_id + "/" + variant)
        expected = variant in {"joint_reference", "retained_joint_reference"}
        if result["passed"] is not expected:
            raise ValueError("Unexpected complete contract result: " + case_id + "/" + variant)
        if expected and not all(result[key] is True for key in (
            "content_correct", "required_process_satisfied", "process_observation_complete")):
            raise ValueError("Joint reference lacks real complete content/API observations: " + case_id)
        if variant in {"library_bypass", "product_bypass"} and (
            result["content_correct"] is not True or result["required_process_satisfied"] is not False
                or result["process_observation_complete"] is not True):
            raise ValueError("Functional provenance negative control did not isolate the required API edge: " + case_id + "/" + variant)
        if variant == "shared_api_only" and not all(row["passed"] is True for row in result["independent_acceptance"]["checks"] if row["group"] == "shared_api"):
            raise ValueError("The isolated real shared API reference did not meet its declared interface")
        witnesses = []
        if expected:
            _, case_row, _ = source._entry(case_id)
            for check in result["independent_acceptance"]["checks"]:
                if check["group"] != "consumer" or check["expected"]["source_api_used"].get(case_row["product_api"]) is not True:
                    continue
                observed = check["observed"]
                returns = [event["value"] for event in observed["source_api_trace"]
                           if event["api"] == case_row["product_api"] and event.get("json_value_recorded") is True]
                if not returns or observed["source_api_used"][case_row["product_api"]] is not True:
                    raise ValueError("The real reusable product return was not observed: " + case_id)
                witnesses.append({"case_id": check["case_id"], "product_api": case_row["product_api"],
                    "actual_product_returns": returns, "consumer_output": observed["value"],
                    "source_api_used": observed["source_api_used"], "complete_contract_passed": check["passed"]})
        atomic_write(folder / "product-witnesses.json", json_bytes({"witnesses": witnesses,
            "scope": "Finite actual code-object call/return and result observations; not arbitrary-code causal necessity or model utility"}))
        return {"case_id": case_id, "purpose": source.CASE_PURPOSES[case_id], "variant": variant,
            "passed": result["passed"], "content_correct": result["content_correct"],
            "required_process_satisfied": result["required_process_satisfied"],
            "process_observation_complete": result["process_observation_complete"],
            "assessment": str((folder / "assessment.json").resolve()),
            "product_witnesses": str((folder / "product-witnesses.json").resolve()),
            "private_case_count": len(result["independent_acceptance"]["checks"]),
            "public_and_upstream_case_count": len(result["public_acceptance"]["tests"])}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(run, jobs))
    result = {"version": "software-source-qualification-v0.36", "passed": True,
        "model_calls": 0, "target_model_calls": 0, "gpu_used": False, "optimizer_updates": 0,
        "workers": workers, "elapsed_cpu_controller_wall_seconds": time.monotonic() - started,
        "source_binding": str((output / "source-binding.json").resolve()),
        "new_root_count": 4, "retained_panel_roots_checked": 4,
        "new_root_program_variants": 24, "retained_panel_joint_references": 4,
        "actual_program_variants": len(rows), "actual_isolated_program_executions": 2 * len(rows),
        "rows": rows,
        "scope": "One CPU program qualification of four new contracts plus existing unused panel references. Original/shared-only/consumer-only, functional library-bypass/product-bypass and joint controls are offline fixtures only; none is a current-policy episode, actor target, Mapper development example from the confirmation pool, or independent algorithm-effect result."}
    atomic_write(output / "program-controls.json", json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2, 3, 4), default=4)
    args = parser.parse_args()
    result = qualify(args.output, workers=args.workers)
    print(json.dumps({key: result[key] for key in ("passed", "actual_program_variants", "actual_isolated_program_executions", "target_model_calls", "gpu_used")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
