"""Synthetic aggregation counterexamples only; no original/model records read."""
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes
from scripts.software_learning_reporting_v049 import BRANCHES, WORKERS, aggregate_rows, inventory, report


def _plan():
    members = ["member_001", "member_002"]
    training = [{"slot_id": f"train-{root}-{index}", "root": root, "sampling_seed": 100 + 4 * ri + index,
        "first_member": members[ri], "members": members, "purpose": "policy_training"}
        for ri, root in enumerate(("LA", "LB")) for index in range(4)]
    development = [{"unit_id": f"dev-{root}-{index}", "root": root, "sampling_seed": 200 + 2 * ri + index,
        "first_member": members[ri], "members": members, "purpose": "policy_development"}
        for ri, root in enumerate(("DA", "DB")) for index in range(2)]
    return {"version": "software-learning-window-v0.49", "source": {"synthetic_cpu_fixture": True},
        "inventory": {"training_slots": training, "development_units_shared_by_branches": development,
            "branches": list(BRANCHES), "maximum_actual_generation_tokens": 10000000, "per_episode": {"tokens": 500000}},
        "automatic_successors": [], "old_queues_remain_paused": True}


def _rows(units):
    rows = []
    values = {"B": [1, 0, 1, 0], "Q_plus": [1, 1, 1, 1], "Q_minus": [0, 0, 0, 0]}
    seen = dict.fromkeys(BRANCHES, 0)
    for unit in units:
        reward = 0
        if unit["phase"] == "development":
            reward = values[unit["branch"]][seen[unit["branch"]]]
            seen[unit["branch"]] += 1
        rows.append({**unit, "status": "closed", "R_joint": reward, "R_token": reward,
            "Q_joint": float(reward), "Q_token": float(reward), "administrative_censoring": False,
            "cost": {"known_actual_tokens": 100, "complete_actual_tokens": 100, "budget_charged_tokens": 100,
                "uncertain_usage_attempts": 0, "prompt_tokens": 90, "completion_tokens": 10,
                "attempts_started": 1, "known_output_bearing_calls": 1, "complete_actual_calls": 1,
                "decisions": 1, "public_member_tests": 0}})
    return rows


def test_joint_estimand_keeps_administrative_known_result_and_fixed_paired_denominators():
    units = inventory(_plan())
    rows = _rows(units)
    administrative = next(row for row in rows if row["branch"] == "Q_plus")
    administrative.update(administrative_censoring=True, R_token=None, Q_token=None)
    value = aggregate_rows(units, rows, {"selected": True, "epsilon": .1})
    assert value["planned_slots"] == 20 and value["status_counts"] == {"closed": 20}
    assert value["branches"]["B"]["F"] == .5 and value["branches"]["Q_plus"]["F"] == 1.
    assert value["branches"]["Q_minus"]["F"] == 0.
    assert value["branches"]["Q_plus"]["metrics"]["R_token"]["mean"] is None
    assert value["administrative_joint_known"] == 1
    assert value["contrasts"] == {"Q_plus_minus_B": .5, "Q_minus_minus_B": -.5}
    assert value["finite_difference"] == 5.
    assert value["generation"]["complete_actual_tokens"] == 2000
    assert len(value["paired_development"]) == 4 and value["F_binary_resolution"] == .25
    assert not value["B_improvement_over_pretraining_claimed"]


def test_unknown_partial_cost_and_unused_conditional_branches_never_become_zero_utility():
    units = inventory(_plan())
    rows = _rows(units)
    missing = next(row for row in rows if row["branch"] == "B")
    missing.update(status="technical_unknown", R_joint=None, R_token=None, Q_joint=None, Q_token=None)
    missing["cost"].update(known_actual_tokens=17, complete_actual_tokens=None, budget_charged_tokens=90,
        uncertain_usage_attempts=1, complete_actual_calls=None)
    for row in rows:
        if row["branch"] in {"Q_plus", "Q_minus"}:
            row.update(status="conditional_not_applicable", R_joint=None, R_token=None, Q_joint=None, Q_token=None)
            row["cost"] = dict.fromkeys(row["cost"], 0)
    value = aggregate_rows(units, rows, {"selected": False, "epsilon": None})
    assert value["branches"]["B"]["F"] is None
    assert value["branches"]["Q_plus"]["F"] is None and value["branches"]["Q_minus"]["F"] is None
    assert value["finite_difference"] is None and all(result is None for result in value["contrasts"].values())
    assert value["generation"]["complete_actual_tokens"] is None
    assert value["generation"]["known_actual_tokens_subtotal"] == 1117
    assert value["generation"]["budget_charged_tokens"] == 1190
    assert value["status_counts"] == {"closed": 11, "technical_unknown": 1, "conditional_not_applicable": 8}
    assert not value["all_applicable_slots_closed"]


def test_report_reads_only_new_synthetic_root_and_counts_worker_intervals_once(tmp_path):
    root, destination = tmp_path / "new-run", tmp_path / "analysis"
    plan = _plan()
    atomic_write(root / "plan.json", json_bytes(plan))
    units, rows = inventory(plan), _rows(inventory(plan))
    active = {"s0": 1, "collect-LA": 2, "collect-LB": 3, "update-B": 4, "dev-B": 5}
    states = {worker: {"status": "complete" if worker in active else "not_applicable", "attempted": worker in active,
        "elapsed_gpu_seconds": active.get(worker, 0), "gpu": 3 if worker in active else None,
        "reason": "no_admissible_I_direction" if worker not in active else None} for worker in WORKERS}
    atomic_write(root / "supervisor.json", json_bytes({"status": "complete", "states": states}))
    direction = {"selected": False, "reliable_base_material": True, "epsilon": None}
    direction["seal_sha256"] = digest(json_bytes(direction))
    atomic_write(root / "direction.json", json_bytes(direction))
    for unit, row in zip(units, rows):
        if unit["branch"] in {"Q_plus", "Q_minus"}:
            continue
        folder = root / unit["worker"] / "actual/episodes" / unit["slot_id"]
        raw = {**unit, "status": "closed", **{key: row[key] for key in ("R_joint", "R_token", "Q_joint", "Q_token")},
            "administrative_censoring": False, "submitted": bool(row["R_joint"]),
            "usage": {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100,
                "budget_charged_tokens": 100, "uncertain_usage_attempts": 0,
                "attempts": 1, "output_bearing_calls": 1, "decisions": 1}, "team_budget": {"tests": {"used": 0}}}
        atomic_write(folder / "slot-result.json", json_bytes(raw))
    update = {"status": "updated", "actor_optimizer_steps": 1, "critic_optimizer_steps": 1,
        "backward_decisions_completed": 16, "after_actor_identity": {"adapter_sha256": digest(b"synthetic-updated")},
        "advantages": [1.], "gradient_norms": {"actor": .2, "critic": .1}, "recipe": {"epochs": 1}}
    atomic_write(root / "update-B/actual/update/report.json", json_bytes(update))
    atomic_write(root / "update-B/actual/update/software-consumption.json", json_bytes({"elapsed_seconds": 999,
        "actor_forwards_completed": 32, "actor_backward_decisions_completed": 16, "critic_backward_decisions_completed": 16}))
    value = report(root, destination)
    assert value["GPU_worker_cost"]["complete_worker_seconds"] == 15
    assert value["metrics"]["status_counts"] == {"closed": 12, "conditional_not_applicable": 8}
    assert value["metrics"]["generation"]["complete_actual_tokens"] == 1200
    assert value["new_update_totals"]["actor_optimizer_steps"] == value["new_update_totals"]["critic_optimizer_steps"] == 1
    assert value["metrics"]["branches"]["B"]["F"] == .5 and value["metrics"]["finite_difference"] is None
    assert value["references"]["declaration.json"] is None
    assert value["old_execution_cost_added"] == value["new_model_calls_by_reporter"] == 0
    assert not value["complete_tensor_checkpoint_comparison_executed"]
    output = (destination / "software-learning-v049.json").read_text()
    assert "input_ids" not in output and Path(destination / "software-learning-v049.md").is_file()
