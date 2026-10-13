"""Read-only v050 full-inventory paired evaluation; never impute missing outcomes."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts import software_learning_reporting_v049 as previous
from scripts import software_learning_v050 as host
from scripts.software_learning_development_resume_v049r2g import bind
from scripts.run_ne_v021 import write

VERSION = "software-learning-reporting-v0.50"
BRANCHES, WORKERS = host.BRANCHES, host.WORKERS
_sum_complete, _number = previous._sum_complete, previous._number
_worker_costs = bind(previous._worker_costs, WORKERS=WORKERS)


def inventory(plan):
    host.validate_inventory(plan["inventory"])
    training = [{**copy.deepcopy(unit), "phase": "training", "branch": "S_star",
                 "worker": host.COLLECTION[i % 3]} for i, unit in enumerate(plan["inventory"]["training_slots"])]
    development = [{**copy.deepcopy(unit), "phase": "development", "branch": branch,
                    "slot_id": unit["unit_id"] + "-" + branch, "worker": f"dev-{branch}-{i // 4}"}
                   for branch in BRANCHES for i, unit in enumerate(plan["inventory"]["development_units_shared_by_branches"])]
    return training + development


def aggregate_rows(units, rows, direction=None):
    if ([row["slot_id"] for row in rows] != [unit["slot_id"] for unit in units]
            or len({row["slot_id"] for row in rows}) != 56):
        raise ValueError("Each of the 56 frozen units is represented once in order")
    branches = {}
    for branch in BRANCHES:
        panel = [row for row in rows if row["phase"] == "development" and row["branch"] == branch]
        if len(panel) != 8:
            raise ValueError("All four states use the exact same eight planned units")
        metrics = {}
        for metric in ("R_joint", "Q_joint", "R_token", "Q_token"):
            values = [row.get(metric) if row["status"] == "closed" else None for row in panel]
            metrics[metric] = {"planned_denominator": 8, "known": sum(x is not None for x in values),
                "values": values, "mean": sum(values) / 8 if all(x is not None for x in values) else None}
        branches[branch] = {"F": metrics["R_joint"]["mean"], "Q": metrics["Q_joint"]["mean"], "metrics": metrics,
            "status_counts": dict(Counter(row["status"] for row in panel)),
            "complete_actual_tokens": _sum_complete(panel, "complete_actual_tokens"),
            "known_actual_tokens_subtotal": sum(row["cost"]["known_actual_tokens"] for row in panel if _number(row["cost"].get("known_actual_tokens")))}
    def difference(left, right):
        a, b = branches[left]["F"], branches[right]["F"]
        return a - b if a is not None and b is not None else None
    selected = isinstance(direction, dict) and direction.get("selected") is True
    epsilon = direction.get("epsilon") if selected else None
    plus_minus = difference("Q_plus", "Q_minus")
    contrasts = {"B_minus_S_star": difference("B", "S_star"), "Q_plus_minus_B": difference("Q_plus", "B"),
                 "Q_minus_minus_B": difference("Q_minus", "B")}
    paired = []
    for unit in [u for u in units if u["phase"] == "development" and u["branch"] == "S_star"]:
        pair = {branch: next(row for row in rows if row.get("unit_id") == unit["unit_id"] and row["branch"] == branch) for branch in BRANCHES}
        values = {branch: pair[branch].get("R_joint") if pair[branch]["status"] == "closed" else None for branch in BRANCHES}
        paired.append({"unit_id": unit["unit_id"], "root": unit["root"], "sampling_seed": unit["sampling_seed"],
                       "R_joint": values, "Q_joint": {b: pair[b].get("Q_joint") for b in BRANCHES},
                       "B_minus_S_star": values["B"] - values["S_star"] if all(values[b] is not None for b in ("B", "S_star")) else None})
    return {"planned_slots": 56, "status_counts": dict(Counter(row["status"] for row in rows)),
        "training_status_counts": dict(Counter(row["status"] for row in rows if row["phase"] == "training")),
        "all_applicable_slots_closed": all(row["status"] in {"closed", "conditional_not_applicable"} for row in rows),
        "branches": branches, "paired_development": paired, "contrasts": contrasts,
        "finite_difference": plus_minus / (2 * epsilon) if plus_minus is not None and _number(epsilon) and epsilon > 0 else None,
        "epsilon": epsilon, "F_binary_resolution": .125,
        "generation": {"known_actual_tokens_subtotal": sum(row["cost"]["known_actual_tokens"] for row in rows if _number(row["cost"].get("known_actual_tokens"))),
            **{key: _sum_complete(rows, key) for key in ("complete_actual_tokens", "budget_charged_tokens", "uncertain_usage_attempts", "prompt_tokens", "completion_tokens", "attempts_started", "known_output_bearing_calls", "complete_actual_calls", "decisions", "public_member_tests")}},
        "estimand": "Equal eight-unit formal joint policy results; unknown and administrative token-only counterfactuals stay null",
        "scope": "One frozen direction on four artificial development families; zero finite difference is not proof C=0; no independent confirmation"}


def results(root):
    root = Path(root).resolve()
    issues, started = [], time.monotonic()
    plan = read_json(root / "plan.json")
    if plan.get("version") != host.VERSION:
        raise ValueError("Report only the new v050 root")
    host.check_seal(plan, "plan_sha256")
    units = inventory(plan)
    supervisor = previous._read(root / "supervisor.json", issues) or {}
    states = supervisor.get("states", {})
    reports = {name: previous._read(root / name / "actual/report.json", issues) for name in WORKERS}
    rows = [previous._slot(root, unit, states.get(unit["worker"], {}), reports[unit["worker"]], issues) for unit in units]
    direction = previous._read(root / "direction.json", issues)
    if direction is not None:
        host.check_seal(direction, "seal_sha256")
    gate = previous._read(root / "support-gate.json", issues)
    if gate is not None:
        host.check_seal(gate)
    updates = {branch: previous._update(root, branch, states.get("update-" + branch, {}), reports["update-" + branch], issues)
               for branch in ("B", "Q_plus", "Q_minus")}
    for branch, row in updates.items():
        row["training_compute_budget_receipt"] = previous._read(root / ("update-" + branch) / "actual/training-compute.json", issues)
    return {"version": VERSION, "run_root": str(root), "status": supervisor.get("status"), "source": plan["source"],
        "generated_at": time.time(), "rows": rows, "metrics": aggregate_rows(units, rows, direction),
        "updates": updates, "support_gate": gate, "direction": direction,
        "support": previous._read(root / "support.json", issues),
        "support_before_training": previous._read(root / "support-before-training.json", issues),
        "GPU_worker_cost": _worker_costs(states), "states": states,
        "generation_budget": plan["generation_budget"], "training_budget": plan["training_budget"],
        "references": {name: previous._ref(root / name) for name in ("plan.json", "supervisor.json", "s_star.json", "declaration.json", "support-gate.json", "direction.json", "entries.json")},
        "mechanism_stops": [{"reference": previous._ref(p), "record": previous._read(p, issues)} for p in sorted((root / "mechanism-stops").glob("*.json"))],
        "evidence_issues": issues, "old_execution_cost_added": 0, "read_only": True,
        "new_model_calls_by_reporter": 0, "new_backward_calls_by_reporter": 0, "new_world_or_acceptance_executions": 0,
        "reporting_elapsed_seconds": time.monotonic() - started, "automatic_successors": [], "old_queues_remain_paused": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write(args.output, results(args.run_root))


if __name__ == "__main__":
    main()
