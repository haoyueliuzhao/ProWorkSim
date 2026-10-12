"""Read-only report of the one v049 inventory across original and r1 phases."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from pathlib import Path
import time

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts import software_learning_reporting_v049 as base

VERSION = "software-learning-original-inventory-report-v0.49-r1"
RUN_VERSION = "software-learning-original-inventory-resume-v0.49-r1"


def _referenced(value, issues, *, label):
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        issues.append({"reason": "missing_original_reference", "label": label})
        return None
    path = Path(value["path"])
    if not path.is_file() or digest(path.read_bytes()) != value.get("sha256"):
        issues.append({"reason": "original_reference_missing_or_changed", "label": label, "path": str(path)})
        return None
    return base._read(path, issues)


def merged_inventory(plan):
    """Map each of the original twenty slots to exactly one actual source phase."""
    units = base.inventory(plan)
    retained = plan["resume_inventory"]["retained_slots"]
    remaining = plan["resume_inventory"]["remaining_training_units"]
    old = {row["slot_id"]: row for row in retained}
    new = {row["slot_id"]: row for row in remaining}
    training = {unit["slot_id"] for unit in units if unit["phase"] == "training"}
    if (len(retained) != 5 or len(old) != 5 or len(remaining) != 3 or len(new) != 3
            or set(old) & set(new) or set(old) | set(new) != training
            or len({str(Path(row["episode_folder"]).resolve()) for row in retained}) != 5):
        raise ValueError("Exactly the original five sources plus three unique unstarted slots must fill the eight-slot training inventory")
    for unit in units:
        if unit["phase"] == "training":
            expected = {key: value for key, value in unit.items() if key not in {"phase", "branch", "worker"}}
            actual = old[unit["slot_id"]]["original_unit"] if unit["slot_id"] in old else new[unit["slot_id"]]
            if actual != expected:
                raise ValueError("Continuation cannot change an original root, seed, order or member assignment")
    return units, old


def _rematerialized(root, row, issues):
    """Keep old null/false interpretation alongside the independently saved r1 view."""
    row["original_interpretation"] = {key: copy.deepcopy(row.get(key)) for key in ("validity", "mapped_work", "training_reward")}
    folder = root / "rematerialized-entries" / row["slot_id"]
    entry = base._read(folder / "training-entry.json", issues)
    receipt = base._read(folder / "rematerialization-receipt.json", issues)
    row["rematerialized_references"] = {name: base._ref(folder / name) for name in
        ("training-entry.json", "training-export.json", "rematerialization-receipt.json")}
    if entry is None or receipt is None:
        row["record_interpretation_status"] = "original_preserved_r1_materialization_not_available"
        return row
    source = Path(row["episode_folder"]).resolve()
    invariants = receipt.get("original_observation_target_reward_invariants", {})
    source_checks = receipt.get("source_files_unchanged", {})
    if (entry.get("slot_id") != row["slot_id"] or receipt.get("slot_id") != row["slot_id"]
            or Path(receipt.get("source_folder", "")).resolve() != source
            or Path(entry.get("rollout", {}).get("episode_path", "")).resolve() != source / "episode"
            or not source_checks or not all(value is True for value in source_checks.values())
            or not all(value is True for value in invariants.values())
            or receipt.get("formal_R") != row.get("R_joint")
            or receipt.get("reported_original_usage", {}).get("total_tokens") != row["cost"].get("known_actual_tokens")
            or any(receipt.get(key) != 0 for key in
                   ("new_model_calls", "new_tokenizer_calls", "new_gpu_calls", "new_business_tests_or_acceptances", "new_world_actions"))):
        issues.append({"slot_id": row["slot_id"], "reason": "unverified_r1_rematerialization_source_or_invariants"})
        row["record_interpretation_status"] = "unverified_r1_original_interpretation_retained"
        return row
    row.update(validity=copy.deepcopy(entry["rollout"].get("work_validity")),
        mapped_work=base._mapping_summary(entry, None), training_reward=copy.deepcopy(entry.get("reward")),
        record_interpretation_status="separate_source_bound_r1_materialization",
        record_interpretation_receipt={key: copy.deepcopy(receipt.get(key)) for key in
            ("version", "old_entry_json_effect_equal", "old_export_payload_equal", "member_views", "scope")},
        interpretation_change_is_policy_or_work_gain=False)
    return row


def _generation_phase(rows):
    return {"slots": len(rows), "status_counts": dict(Counter(row["status"] for row in rows)),
        "known_actual_tokens_subtotal": sum(row["cost"]["known_actual_tokens"] for row in rows if base._number(row["cost"].get("known_actual_tokens"))),
        **{key: base._sum_complete(rows, key) for key in ("complete_actual_tokens", "complete_actual_calls", "decisions",
            "prompt_tokens", "completion_tokens", "budget_charged_tokens", "public_member_tests")}}


def combine_costs(original_states, new_states, rows):
    old, new = base._worker_costs(original_states), base._worker_costs(new_states)
    s0 = new_states.get("s0", {})
    reused_s0 = (s0.get("status") == "complete" and s0.get("attempted") is False
                 and s0.get("original_complete_state_reused") is True and s0.get("elapsed_gpu_seconds") == 0)
    complete = (old["complete_worker_seconds"] + new["complete_worker_seconds"]
                if old["complete_worker_seconds"] is not None and new["complete_worker_seconds"] is not None else None)
    return {"original_phase": old, "r1_phase": new,
        "known_closed_worker_seconds": old["known_closed_worker_seconds"] + new["known_closed_worker_seconds"],
        "complete_worker_seconds": complete, "complete_worker_hours": complete / 3600 if complete is not None else None,
        "original_S0_counted_only_in_original_phase": True if reused_s0 else None,
        "retained_generation": _generation_phase([row for row in rows if row["source_phase"] == "original_v049"]),
        "new_generation": _generation_phase([row for row in rows if row["source_phase"] == "resume_r1"]),
        "scope": "Each original/new worker interval and each original generation slot is included once. The reused new S0 state has no worker cost; nested update times and old unspent token budgets are not added."}


def results(root):
    root = Path(root).resolve()
    started, issues = time.monotonic(), []
    plan = read_json(root / "plan.json")
    if plan.get("version") != RUN_VERSION:
        raise ValueError("Read the separately frozen v049-r1 continuation root")
    units, retained = merged_inventory(plan)
    derived = plan["resume_inventory"]
    old_root = Path(plan["original_root"]).resolve()
    old_plan = _referenced(derived["original_plan"], issues, label="original_v049_plan")
    old_supervisor = _referenced(derived["original_supervisor"], issues, label="original_v049_supervisor") or {}
    if old_plan is not None and old_plan.get("version") != "software-learning-window-v0.49":
        raise ValueError("No other historical experiment can fill the v049 inventory")
    supervisor = base._read(root / "supervisor.json", issues) or {}
    old_states, states = old_supervisor.get("states", {}), supervisor.get("states", {})
    workers = {name: {"state": copy.deepcopy(states.get(name, {})),
        "report": base._read(root / name / "actual/report.json", issues), "reference": base._ref(root / name / "actual/report.json")}
        for name in base.WORKERS}
    old_workers = {name: {"state": copy.deepcopy(old_states.get(name, {})),
        "report": base._read(old_root / name / "actual/report.json", issues), "reference": base._ref(old_root / name / "actual/report.json")}
        for name in base.WORKERS}
    rows = []
    for unit in units:
        sid, worker = unit["slot_id"], unit["worker"]
        if sid in retained:
            source = Path(retained[sid]["episode_folder"]).resolve()
            expected = old_root / worker / "actual/episodes" / sid
            if source != expected:
                raise ValueError("Retained slot folder differs from the original worker/slot location")
            row = base._slot(old_root, unit, old_states.get(worker, {}), old_workers[worker]["report"], issues)
            row["source_phase"] = "original_v049"
            row["source_identity"] = (old_plan or {}).get("source")
            for key in ("source_result", "source_manifest"):
                actual = base._ref(source / ("slot-result.json" if key == "source_result" else "episode/manifest.json"))
                if actual is None or actual.get("sha256") != retained[sid].get(key, {}).get("sha256"):
                    issues.append({"slot_id": sid, "reason": "retained_source_reference_changed", "reference": key})
                    row.update(status="technical_unknown", R_joint=None, R_token=None, Q_joint=None, Q_token=None)
                    row["cost"]["complete_actual_tokens"] = None
        else:
            row = base._slot(root, unit, states.get(worker, {}), workers[worker]["report"], issues)
            row["source_phase"] = "resume_r1"
            row["source_identity"] = plan.get("source")
        if unit["phase"] == "training":
            row = _rematerialized(root, row, issues)
        rows.append(row)
    direction = base._read(root / "direction.json", issues)
    if direction is not None and direction.get("seal_sha256") != digest(json_bytes({key: value for key, value in direction.items() if key != "seal_sha256"})):
        issues.append({"reason": "direction_envelope_seal_mismatch"})
        direction = None
    support = base._read(root / "support.json", issues)
    support_summary = None
    if support is not None:
        if support.get("seal_sha256") != digest(json_bytes({key: value for key, value in support.items() if key != "seal_sha256"})):
            issues.append({"reason": "support_seal_mismatch"})
        else:
            support_summary = {key: copy.deepcopy(support.get(key)) for key in ("window_id", "root_order", "member_order", "category_order",
                "roots", "base_learning_material_available", "original_slot_count", "global_member_denominator_factor", "scope")}
    updates = {branch: base._update(root, branch, states.get("update-" + branch, {}), workers["update-" + branch]["report"], issues)
               for branch in base.BRANCHES}
    for branch, update in updates.items():
        update["references"]["update/update-r1-reader-binding.json"] = base._ref(root / ("update-" + branch) / "actual/update-r1-reader-binding.json")
    baseline = updates["B"]["report"].get("after_actor_identity")
    for branch in ("Q_plus", "Q_minus"):
        identity = updates[branch]["report"].get("after_actor_identity")
        updates[branch]["actor_adapter_equal_B"] = identity.get("adapter_sha256") == baseline.get("adapter_sha256") if identity and baseline else None
    update_totals = {key: sum(value[key] for value in updates.values()) if all(base._integer(value[key]) for value in updates.values()) else None
        for key in ("actor_optimizer_steps", "critic_optimizer_steps", "backward_decisions_completed")}
    costs = combine_costs(old_states, states, rows)
    bound_cost = derived.get("retained_actual_cost", {})
    if (costs["original_phase"]["complete_worker_seconds"] is not None
            and costs["original_phase"]["complete_worker_seconds"] != bound_cost.get("worker_gpu_seconds_including_original_S0")):
        issues.append({"reason": "original_worker_cost_differs_from_frozen_continuation_inventory"})
        costs["complete_worker_seconds"] = costs["complete_worker_hours"] = None
    if (costs["retained_generation"]["complete_actual_tokens"] is not None
            and costs["retained_generation"]["complete_actual_tokens"] != bound_cost.get("total_tokens")):
        issues.append({"reason": "retained_generation_cost_differs_from_frozen_five_slot_inventory"})
    original_stops = [{"reference": value, "record": _referenced(value, issues, label="original_stop")}
                      for value in derived.get("original_stops", [])]
    declaration = _referenced(plan.get("declaration"), issues, label="original_declaration")
    value = {"version": VERSION, "run_root": str(root), "original_root": str(old_root),
        "status": supervisor.get("status", "supervisor_record_unavailable"), "generated_at": time.time(),
        "plan": base._ref(root / "plan.json"), "source": {"original_v049": (old_plan or {}).get("source"), "resume_r1": plan.get("source")},
        "source_agreement": copy.deepcopy(derived.get("source_agreement")), "design": plan.get("design"),
        "budget_caps": copy.deepcopy(plan.get("new_budget_caps")), "rows": rows,
        "metrics": base.aggregate_rows(units, rows, direction), "updates": updates, "new_update_totals": update_totals,
        "support": support_summary, "direction": direction, "GPU_worker_cost": costs,
        "workers": {name: {"state": row["state"], "reference": row["reference"], "status": (row["report"] or {}).get("status"),
            "error": (row["report"] or {}).get("error"), "source_before": (row["report"] or {}).get("source_before"),
            "source_after": (row["report"] or {}).get("source_after")} for name, row in workers.items()},
        "original_workers": {name: {"state": row["state"], "reference": row["reference"], "status": (row["report"] or {}).get("status"),
            "source_before": (row["report"] or {}).get("source_before"), "source_after": (row["report"] or {}).get("source_after")} for name, row in old_workers.items()},
        "mechanism_decision_counts": dict(Counter(row["measurement"]["decision"] for row in rows if row["measurement"]["decision"] is not None)),
        "s0": _referenced(plan.get("s0"), issues, label="original_S0"),
        "declaration_reference": copy.deepcopy(plan.get("declaration")),
        "declaration_identity": {key: (declaration or {}).get(key) for key in
            ("window_id", "actor_identity", "actor_identity_sha256", "gamma_fingerprint")},
        "recipe_binding": base._read(old_root / "s0/actual/recipe-binding.json", issues),
        "references": {name: base._ref(root / name) for name in ("supervisor.json", "source-registry.json", "materialization.json",
            "entries.json", "support.json", "direction.json")},
        "original_references": {key: copy.deepcopy(derived.get(key)) for key in
            ("original_plan", "original_supervisor", "original_s0", "original_declaration", "original_checkpoint")},
        "original_stops": original_stops,
        "mechanism_stops": [{"reference": base._ref(path), "record": base._read(path, issues)} for path in sorted((root / "mechanism-stops").glob("*.json"))],
        "evidence_issues": issues, "complete_tensor_checkpoint_comparison_executed": False,
        "original_five_slots_included_once": True, "new_training_slots_maximum": 3, "new_development_slots_maximum": 12,
        "original_unknown_record_interpretations_preserved": True, "record_revision_is_policy_improvement": False,
        "unspent_original_budget_transferred": False, "other_old_experiment_cost_added": 0,
        "automatic_successors": plan.get("automatic_successors"), "old_queues_remain_paused": plan.get("old_queues_remain_paused"),
        "read_only": True, "new_model_calls_by_reporter": 0, "new_backward_calls_by_reporter": 0,
        "new_world_or_acceptance_executions": 0, "reporting_elapsed_seconds": time.monotonic() - started,
        "scope": "Original unique 20-slot v049 inventory: retain five actual originals and run only three formerly unopened training slots plus the same conditional twelve developer slots. Original null record/mapping and stop artifacts stay visible alongside a separate read-only interpretation; that correction is not policy, work or learning benefit."}
    return value


def markdown(value):
    costs = value["GPU_worker_cost"]
    text = base.markdown(value).replace("新GPU worker总小时：", "本窗口两阶段GPU worker合计小时：")
    text = text.replace("本报告只读新v049原件，不运行模型、tokenizer、世界或验收，不加旧历史成本。",
                        "本报告只读同一v049原库存的旧/新阶段，不运行模型、tokenizer、世界或验收；原5槽成本仅计一次，不加其它旧实验成本。")
    lines = text.splitlines()
    lines[0] = "# v049 原库存：r1 只读归因修订与接续报告"
    lines[2:2] = ["原5槽与新3训练槽合并为唯一原8槽，开发仍为原三个分支各4单位，合计原20槽。原unknown解释、原停止、R与全部费用保留；r1解释修订不算策略收益。",
        f"旧阶段GPU worker秒 {costs['original_phase']['complete_worker_seconds']}；新阶段 {costs['r1_phase']['complete_worker_seconds']}；合计 {costs['complete_worker_seconds']}。原S0仅在旧阶段计一次的新复用凭据：{costs['original_S0_counted_only_in_original_phase']}。",
        f"保留原5槽生成：{costs['retained_generation']['complete_actual_calls']}次/{costs['retained_generation']['complete_actual_tokens']}token；新阶段：{costs['new_generation']['complete_actual_calls']}次/{costs['new_generation']['complete_actual_tokens']}token。旧生成不再额外加到20槽合计。", ""]
    lines += ["", "原件与新解释逐槽对照保存在JSON的original_interpretation/record_interpretation_receipt；原阶段及r1阶段源码身份、旧停止凭据和物化来源单列。训练前未更新开发基线仍缺席，完整critic/Adam张量比较未执行。", ""]
    return "\n".join(lines)


def report(root, destination):
    destination = Path(destination).resolve()
    value = results(root)
    if destination in {Path(root).resolve(), Path(value["original_root"]).resolve()}:
        raise ValueError("Write analysis separately from both original and resumed root records")
    destination.mkdir(parents=True, exist_ok=True)
    atomic_write(destination / "software-learning-v049-r1.json", json_bytes(value))
    atomic_write(destination / "software-learning-v049-r1.md", markdown(value).encode())
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    value = report(args.run_root, args.output)
    print(json_bytes({"status": value["status"], "inventory": value["metrics"]["status_counts"],
        "finite_difference": value["metrics"]["finite_difference"], "output": str(Path(args.output).resolve())}).decode(), end="")


if __name__ == "__main__":
    main()
