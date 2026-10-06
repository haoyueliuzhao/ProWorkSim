"""Freeze actual P2 support and all P3 coordinates before any contribution feedback.

This read-only-material operation creates a plan. It does not launch a worker,
execute a model, inspect independent outcomes, or certify post-update utility.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.experience_allocation_v035 import allocation_gate, freeze_allocation_plan
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_ne_v021 import checked, reference, write
from scripts.software_support_v035 import CANDIDATE, POLICY, results, validate_plan


def freeze(run_root, output):
    root, output = Path(run_root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Do not overwrite a postcollection freeze")
    plan = validate_plan(read_json(root / "plan.json"))
    result = results(plan, root)
    actual = root / CANDIDATE / "actual"
    worker = read_json(actual / "report.json")
    supervisor = read_json(root / "supervisor.json")
    state = supervisor["states"][CANDIDATE]
    if (result.get("worker_trusted_and_common_restored") is not True
            or supervisor["status"] != "complete" or state["status"] != "complete"
            or worker["status"] != "complete" or worker.get("common_restored_exactly") is not True
            or any(worker.get(key) != 3 for key in ("initial_actor_steps", "initial_critic_steps", "actor_steps", "critic_steps"))
            or worker.get("new_actor_optimizer_steps") != 0 or worker.get("new_critic_optimizer_steps") != 0
            or worker.get("source_before") != plan["source"] or worker.get("source_after") != plan["source"]):
        raise ValueError("Only the complete trusted unchanged P2 window can freeze P3")
    for name in ("trial-B", "trials", "selection.json", "formal-B", "formal-G-raw", "formal-I-P"):
        if (root / name).exists():
            raise ValueError("Freeze the complete plan before any trial, selection or confirmation feedback")
    collection = actual / "collection"
    entries, declaration, records = [read_json(collection / name) for name in ("entries.json", "declaration.json", "records.json")]
    gate = allocation_gate(entries, declaration, records)
    if gate != read_json(actual / "support-gate.json"):
        raise ValueError("Support gate must reconstruct from the exact original P2 material")
    if gate["status"] != "ready_for_postcollection_freeze":
        raise ValueError("This finite window has no configurable block; retain its support diagnosis")
    material = read_json(checked(worker["training_material_binding"]))
    if material.get("entries_sha256") != digest(json_bytes(entries)) or material.get("declaration_sha256") != digest(json_bytes(declaration)):
        raise ValueError("Use the actual original-token and full-denominator binding")
    common = read_json(actual / "inherited-common.json")
    original = read_json(checked(common["common"]))
    if common["state_tensor_digest"] != original["state_tensor_digest"] or common["actor_identity"] != original["actor_identity"]:
        raise ValueError("Full original common identity differs")
    def units(name):
        return [{"unit_id": row["slot_id"], "root_id": row["case_id"],
                 "seed": row["sampling_seed"], "weight": 1.0} for row in plan["inventories"][name]]
    manifest = {"purpose": "contribution_development", "provenance": "current_model_development",
        "split_manifest_sha256": digest(json_bytes({"inventories": plan["inventories"], "cases": plan["cases"]})),
        "initial_state_sha256": common["state_tensor_digest"], "training_rng_sha256": common["training_rng_sha256"],
        "units": units("development"), "independent_units": units("confirmation")}
    upper = POLICY["P3_upper_inventory"]
    allocation = freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=manifest, budget={"max_unique_trial_updates": upper["unique_trial_updates"],
            "max_development_episodes": upper["development_episodes"], "formal_updates_per_method": 1,
            "independent_episodes_per_method": len(manifest["independent_units"])})
    frozen = {"version": "postcollection-freeze-v0.35", "P2_plan": reference(root / "plan.json"),
        "P2_worker": reference(actual / "report.json"), "P2_supervisor": reference(root / "supervisor.json"),
        "P2_material": {name: reference(collection / name) for name in ("entries.json", "declaration.json", "records.json")},
        "training_material_binding": worker["training_material_binding"],
        "common": reference(actual / "inherited-common.json"), "support_gate": reference(actual / "support-gate.json"),
        "allocation": allocation, "actual_inventory": allocation["actual_inventory"],
        "P2_status_at_freeze": result["status"], "target_model_calls": 0, "optimizer_updates": 0,
        "C_feedback_consumed_by_freezer": False, "predeclared_run_feedback_paths_absent": True,
        "independent_outcomes_read": False,
        "P3_started": False, "automatic_execution": False,
        "next_requirement": "Run shared B as a real complete-window update with actual behavior-probability/target-consumption checks, then its frozen developer panel. All further probes and formal branches restore this same common; never append probe states.",
        "scope": "Actual supported coordinates and complete compute inventory frozen before feedback; no training cost forecast or allocation-effect evidence."}
    write(output, frozen)
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(freeze(args.run_root, args.output)["actual_inventory"])


if __name__ == "__main__":
    main()
