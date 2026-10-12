"""Synthetic unique-inventory/unknown-cost controls; no historical model reads."""
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes
from scripts import software_learning_reporting_v049 as base
from scripts.software_learning_resume_reporting_v049r1 import combine_costs, merged_inventory, report
from test_software_learning_reporting_v049 import _plan, _rows


OLD_SECONDS = 2162.429730653763  # Explicit synthetic arithmetic constant, no GPU measurement here.


def _states(old=False):
    value = {worker: {"status": "not_applicable", "attempted": False, "elapsed_gpu_seconds": 0}
             for worker in base.WORKERS}
    if old:
        elapsed = {"s0": 10, "collect-LA": 1000, "collect-LB": OLD_SECONDS - 1010}
    else:
        elapsed = {"collect-LA": 100, "collect-LB": 200, "update-B": 300, "dev-B": 400}
        value["s0"] = {"status": "complete", "attempted": False, "elapsed_gpu_seconds": 0,
                       "original_complete_state_reused": True}
    for worker, seconds in elapsed.items():
        value[worker] = {"status": "complete", "attempted": True, "elapsed_gpu_seconds": seconds, "gpu": 3}
    return value


def test_unique_original_five_plus_three_inventory_and_GPU_intervals_added_once(tmp_path):
    plan = _plan()
    training = plan["inventory"]["training_slots"]
    plan["resume_inventory"] = {"retained_slots": [{"slot_id": unit["slot_id"], "original_unit": unit,
        "episode_folder": str(tmp_path / "original" / unit["slot_id"])} for unit in training[:5]],
        "remaining_training_units": training[5:]}
    units, retained = merged_inventory(plan)
    rows = _rows(units)
    for row in rows:
        row["source_phase"] = "original_v049" if row["slot_id"] in retained else "resume_r1"
    costs = combine_costs(_states(old=True), _states(), rows)
    assert len(units) == 20 and len({unit["slot_id"] for unit in units}) == 20
    assert costs["original_phase"]["complete_worker_seconds"] == OLD_SECONDS
    assert costs["r1_phase"]["complete_worker_seconds"] == 1000
    assert costs["complete_worker_seconds"] == OLD_SECONDS + 1000
    assert costs["retained_generation"]["complete_actual_tokens"] == 500
    assert costs["new_generation"]["complete_actual_tokens"] == 1500
    assert costs["original_S0_counted_only_in_original_phase"]


def test_report_preserves_old_unknown_view_and_new_partial_cost_and_conditional_null(tmp_path):
    old_root, root, destination = tmp_path / "original-v049", tmp_path / "resume-r1", tmp_path / "analysis"
    parent = _plan()
    atomic_write(old_root / "plan.json", json_bytes(parent))
    atomic_write(old_root / "supervisor.json", json_bytes({"status": "closed_with_unknowns", "states": _states(old=True)}))
    atomic_write(old_root / "s0.json", json_bytes({"state_tensor_digest": digest(b"synthetic-S0")}))
    atomic_write(old_root / "declaration.json", json_bytes({"explicit_cpu_fixture": True}))
    atomic_write(old_root / "mechanism-stops/old-record-pending.json", json_bytes({"kind": "measurement_pending", "old_value": None}))
    units = base.inventory(parent)
    training = parent["inventory"]["training_slots"]
    retained = []
    first_sid = training[0]["slot_id"]
    for unit in units:
        if unit["branch"] in {"Q_plus", "Q_minus"}:
            continue
        is_old = unit["phase"] == "training" and unit["slot_id"] in {row["slot_id"] for row in training[:5]}
        target_root = old_root if is_old else root
        folder = target_root / unit["worker"] / "actual/episodes" / unit["slot_id"]
        if unit["branch"] == "B" and unit["unit_id"] == parent["inventory"]["development_units_shared_by_branches"][-1]["unit_id"]:
            atomic_write(folder / "organization-evidence.json", json_bytes({"total_usage": {
                "prompt_tokens": 15, "completion_tokens": 2, "total_tokens": 17, "attempts": 2,
                "output_bearing_calls": 1, "budget_charged_tokens": 90, "uncertain_usage_attempts": 1, "decisions": 2}}))
            continue
        reward = 1 if unit["slot_id"] == first_sid or unit["phase"] == "development" else 0
        raw = {**unit, "status": "closed", "R_joint": reward, "R_token": reward, "Q_joint": float(reward), "Q_token": float(reward),
            "administrative_censoring": False, "submitted": bool(reward),
            "usage": {"prompt_tokens": 90, "completion_tokens": 10, "total_tokens": 100, "attempts": 1,
                "output_bearing_calls": 1, "budget_charged_tokens": 100, "uncertain_usage_attempts": 0, "decisions": 1},
            "team_budget": {"tests": {"used": 0}}}
        atomic_write(folder / "slot-result.json", json_bytes(raw))
        atomic_write(folder / "episode/manifest.json", json_bytes({"explicit_cpu_fixture": True, "slot_id": unit["slot_id"]}))
        if is_old:
            original_unit = next(row for row in training if row["slot_id"] == unit["slot_id"])
            retained.append({"slot_id": unit["slot_id"], "original_unit": original_unit, "episode_folder": str(folder),
                "source_result": base._ref(folder / "slot-result.json"), "source_manifest": base._ref(folder / "episode/manifest.json")})
        if unit["slot_id"] == first_sid:
            old_entry = {"slot_id": first_sid, "reward": {"eligible": True, "reward": reward},
                "rollout": {"episode_path": str(folder / "episode"), "work_validity": {"value": None}},
                "mapping": {"status": "unmapped", "class_id": None}}
            atomic_write(folder / "training-entry.json", json_bytes(old_entry))
            revised = {**old_entry, "rollout": {**old_entry["rollout"], "work_validity": {"value": True}},
                "mapping": {"status": "mapped", "class_id": "local_lineage_delivery"}}
            material = root / "rematerialized-entries" / first_sid
            atomic_write(material / "training-entry.json", json_bytes(revised))
            atomic_write(material / "rematerialization-receipt.json", json_bytes({"slot_id": first_sid, "source_folder": str(folder),
                "source_files_unchanged": {"manifest": True}, "original_observation_target_reward_invariants": {"reward": True},
                "formal_R": reward, "reported_original_usage": raw["usage"], "new_model_calls": 0, "new_tokenizer_calls": 0,
                "new_gpu_calls": 0, "new_business_tests_or_acceptances": 0, "new_world_actions": 0,
                "old_entry_json_effect_equal": False, "scope": "Explicit synthetic record interpretation control"}))
    derived = {"retained_slots": retained, "remaining_training_units": training[5:],
        "original_plan": base._ref(old_root / "plan.json"), "original_supervisor": base._ref(old_root / "supervisor.json"),
        "original_s0": base._ref(old_root / "s0.json"), "original_declaration": base._ref(old_root / "declaration.json"),
        "retained_actual_cost": {"total_tokens": 500, "worker_gpu_seconds_including_original_S0": OLD_SECONDS},
        "original_stops": [base._ref(old_root / "mechanism-stops/old-record-pending.json")]}
    plan = {**parent, "version": "software-learning-original-inventory-resume-v0.49-r1", "original_root": str(old_root),
        "resume_inventory": derived, "s0": derived["original_s0"], "declaration": derived["original_declaration"],
        "new_budget_caps": {"new_training_slots": 3}}
    atomic_write(root / "plan.json", json_bytes(plan))
    atomic_write(root / "supervisor.json", json_bytes({"status": "closed_with_unknowns", "states": _states()}))
    direction = {"selected": False, "reliable_base_material": True, "epsilon": None}
    direction["seal_sha256"] = digest(json_bytes(direction))
    atomic_write(root / "direction.json", json_bytes(direction))
    atomic_write(root / "update-B/actual/update/report.json", json_bytes({"status": "updated", "actor_optimizer_steps": 1,
        "critic_optimizer_steps": 1, "backward_decisions_completed": 16, "after_actor_identity": {"adapter_sha256": digest(b"fake")}}))
    atomic_write(root / "update-B/actual/update/software-consumption.json", json_bytes({"elapsed_seconds": 99999}))
    value = report(root, destination)
    assert value["metrics"]["status_counts"] == {"closed": 11, "technical_unknown": 1, "conditional_not_applicable": 8}
    assert value["metrics"]["generation"]["known_actual_tokens_subtotal"] == 1117
    assert value["metrics"]["generation"]["complete_actual_tokens"] is None
    assert value["metrics"]["branches"]["B"]["F"] is None and value["metrics"]["finite_difference"] is None
    assert value["GPU_worker_cost"]["complete_worker_seconds"] == OLD_SECONDS + 1000
    first = next(row for row in value["rows"] if row["slot_id"] == first_sid)
    assert first["original_interpretation"]["validity"]["value"] is None and first["validity"]["value"] is True
    assert first["record_interpretation_status"] == "separate_source_bound_r1_materialization"
    assert first["interpretation_change_is_policy_or_work_gain"] is False
    assert value["original_stops"][0]["record"]["old_value"] is None
    assert value["new_update_totals"]["actor_optimizer_steps"] == 1
    assert value["new_model_calls_by_reporter"] == 0
    assert Path(destination / "software-learning-v049-r1.md").is_file()
