"""Read-only merge of the original v050 first slot and its remaining inventory."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts import software_learning_reporting_v050 as previous
from scripts import software_learning_resume_v050r1 as host
from scripts.run_ne_v021 import write

VERSION = "software-learning-resume-reporting-v0.50-r1"
base = previous.previous


def inventory(plan):
    units = previous.inventory(plan)
    derived = plan["resume_inventory"]
    kept = derived["retained_slots"]
    remaining = derived["remaining_training_units"]
    if (len(kept) != 1 or kept[0]["slot_id"] != host.FIRST_SLOT
            or kept[0]["original_unit"] != plan["inventory"]["training_slots"][0]
            or remaining != plan["inventory"]["training_slots"][1:]):
        raise ValueError("Merge exactly the original first slot and 23 unchanged unstarted units")
    return units


def merged_costs(old_states, new_states):
    old, new = previous._worker_costs(old_states), previous._worker_costs(new_states)
    complete = (old["complete_worker_seconds"] + new["complete_worker_seconds"]
        if old["complete_worker_seconds"] is not None and new["complete_worker_seconds"] is not None else None)
    return {"original_phase": old, "resume_phase": new,
        "known_closed_worker_seconds": old["known_closed_worker_seconds"] + new["known_closed_worker_seconds"],
        "complete_worker_seconds": complete, "complete_worker_hours": complete / 3600 if complete is not None else None,
        "original_S_star_and_collector_counted_once": True,
        "nested_update_time_added": False, "unused_old_generation_budget_transferred": False}


def results(root):
    root = Path(root).resolve()
    started, issues = time.monotonic(), []
    plan = host.check_seal(read_json(root / "plan.json"), "plan_sha256")
    if plan.get("version") != host.VERSION:
        raise ValueError("Report only the isolated original-v050 continuation")
    old_root = Path(plan["original_root"])
    host.checked(plan["resume_of"])
    old = read_json(host.checked(plan["resume_inventory"]["original_supervisor"]))
    old_report = base._read(old_root / "collect-0/actual/report.json", issues)
    current = base._read(root / "supervisor.json", issues) or {}
    states, old_states = current.get("states", {}), old.get("states", {})
    reports = {name: base._read(root / name / "actual/report.json", issues) for name in host.WORKERS if name != "s_star"}
    units, rows = inventory(plan), []
    for unit in units:
        retained = unit["slot_id"] == host.FIRST_SLOT
        row = base._slot(old_root if retained else root, unit,
            (old_states if retained else states).get(unit["worker"], {}),
            old_report if retained else reports[unit["worker"]], issues)
        row["source_phase"] = "original_v050" if retained else "resume_r1"
        if retained:
            row["original_interpretation"] = {k: copy.deepcopy(row.get(k)) for k in ("validity", "mapped_work", "training_reward")}
            original = plan["resume_inventory"]["retained_slots"][0]
            for key in ("source_result", "source_manifest", "source_guard", "source_measurement"):
                host.checked(original[key])
            entry = read_json(host.checked(plan["retained_export"]["training-entry.json"]))
            row.update(validity=copy.deepcopy((entry.get("rollout") or {}).get("work_validity")),
                mapped_work=base._mapping_summary(entry, None), training_reward=entry.get("reward"),
                retained_export=copy.deepcopy(plan["retained_export"]),
                original_collector_execution_error_preserved=True,
                original_outer_collection_guard_missing=True,
                original_per_slot_guard_preserved=True)
        rows.append(row)
    direction = base._read(root / "direction.json", issues)
    if direction is not None:
        host.check_seal(direction, "seal_sha256")
    gate = base._read(root / "support-gate.json", issues)
    if gate is not None:
        host.check_seal(gate)
    updates = {branch: base._update(root, branch, states.get("update-" + branch, {}), reports["update-" + branch], issues)
        for branch in ("B", "Q_plus", "Q_minus")}
    for branch, update in updates.items():
        update["training_compute_budget_receipt"] = base._read(root / ("update-" + branch) / "actual/training-compute.json", issues)
    return {"version": VERSION, "run_root": str(root), "original_root": str(old_root),
        "status": current.get("status"), "source": plan["source"], "generated_at": time.time(),
        "rows": rows, "metrics": previous.aggregate_rows(units, rows, direction), "updates": updates,
        "support_gate": gate, "direction": direction,
        "support": base._read(root / "support.json", issues),
        "support_before_training": base._read(root / "support-before-training.json", issues),
        "GPU_worker_cost": merged_costs(old_states, states), "states": states,
        "original_states_preserved": old_states, "original_status_preserved": old["status"],
        "generation_budget": plan["generation_budget"], "remaining_generation_budget": plan["new_budget_caps"],
        "training_budget": plan["training_budget"], "evidence_issues": issues,
        "original_mechanism_stops": plan["resume_inventory"]["original_stops"],
        "mechanism_stops": [{"reference": base._ref(p), "record": base._read(p, issues)}
            for p in sorted((root / "mechanism-stops").glob("*.json"))],
        "read_only": True, "new_model_calls_by_reporter": 0, "new_backward_calls_by_reporter": 0,
        "new_world_or_acceptance_executions": 0, "reporting_elapsed_seconds": time.monotonic() - started,
        "automatic_successors": [], "old_queues_remain_paused": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write(args.output, results(args.run_root))


if __name__ == "__main__":
    main()
