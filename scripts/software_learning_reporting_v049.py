"""Read-only, planned-inventory v049 learning report; no model or world replay."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import math
from pathlib import Path
import time

from proworksim.storage import atomic_write, digest, json_bytes, read_json
from scripts.software_organization_reporting_v047 import cost_values, outcome_values

VERSION = "software-learning-reporting-v0.49"
BRANCHES = ("B", "Q_plus", "Q_minus")
WORKERS = ("s0", "collect-LA", "collect-LB", "update-B", "update-Q_plus", "update-Q_minus",
           "dev-B", "dev-Q_plus", "dev-Q_minus")
UNUSED = {"not_started", "conditional_not_applicable"}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _integer(value):
    return type(value) is int and value >= 0


def _ref(path):
    path = Path(path)
    if not path.is_file():
        return None
    value = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": digest(value), "bytes": len(value)}


def _read(path, issues):
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except (OSError, ValueError, TypeError) as error:
        issues.append({"path": str(path), "reason": "unreadable_original_record", "error": str(error)})
        return None


def inventory(plan):
    design = plan["inventory"]
    training, development = design["training_slots"], design["development_units_shared_by_branches"]
    if len(training) != 8 or len(development) != 4 or design["branches"] != list(BRANCHES):
        raise ValueError("The original eight training and twelve conditional development slots must remain explicit")
    units = [{**copy.deepcopy(row), "phase": "training", "branch": "S0", "worker": "collect-" + row["root"]}
             for row in training]
    for branch in BRANCHES:
        units.extend({**copy.deepcopy(row), "slot_id": row["unit_id"] + "-" + branch,
                      "phase": "development", "branch": branch, "worker": "dev-" + branch} for row in development)
    if len({row["slot_id"] for row in units}) != 20:
        raise ValueError("A planned episode cannot appear twice")
    return units


def _partial_usage(folder, issues):
    evidence = _read(folder / "organization-evidence.json", issues)
    if isinstance(evidence, dict) and isinstance(evidence.get("total_usage"), dict):
        return copy.deepcopy(evidence["total_usage"]), "original_partial_organization_evidence"
    wrapper = _read(folder / "team-budget.json", issues)
    if wrapper is None:
        snapshot = _read(folder / "runtime-state.json", issues) or {}
        wrapper = snapshot.get("team_budget")
    budget = (wrapper or {}).get("model")
    if not isinstance(budget, dict) or not isinstance(budget.get("records"), dict):
        return {}, "no_recoverable_usage_evidence"
    usage = {"decisions": budget.get("decisions"), "attempts": budget.get("attempts"),
        "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "output_bearing_calls": 0,
        "budget_charged_tokens": budget.get("charged_tokens"), "uncertain_usage_attempts": 0}
    for record in budget["records"].values():
        charge = record.get("charge", {})
        actual = charge.get("reported_usage", {})
        if charge.get("usage_status") == "reported_actual_trace" and all(_integer(actual.get(key)) for key in
                ("prompt_tokens", "completion_tokens", "total_tokens")):
            if actual["prompt_tokens"] + actual["completion_tokens"] != actual["total_tokens"]:
                issues.append({"path": str(folder), "reason": "partial_ledger_usage_arithmetic_mismatch"})
                return {}, "inconsistent_partial_ledger"
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[key] += actual[key]
            usage["output_bearing_calls"] += int(actual["completion_tokens"] > 0)
        elif record.get("attempt_started") is True:
            usage["uncertain_usage_attempts"] += 1
    return usage, "settled_actual_ledger_subtotal_only_unsettled_attempts_remain_unknown"


def _cost(row, *, status, issues, path):
    if status in UNUSED:
        return {"known_actual_tokens": 0, "complete_actual_tokens": 0, "budget_charged_tokens": 0,
            "uncertain_usage_attempts": 0, "status": "never_started_no_generation_cost",
            "prompt_tokens": 0, "completion_tokens": 0, "attempts_started": 0,
            "known_output_bearing_calls": 0, "complete_actual_calls": 0, "decisions": 0,
            "public_member_tests": 0}
    try:
        cost = cost_values(row)
    except (ValueError, TypeError, KeyError) as error:
        issues.append({"path": str(path), "reason": "usage_inconsistent", "error": str(error)})
        cost = {"known_actual_tokens": None, "complete_actual_tokens": None, "budget_charged_tokens": None,
                "uncertain_usage_attempts": None, "status": "inconsistent_original_cost_evidence"}
    usage = row.get("usage") or {}
    tests = (row.get("team_budget") or {}).get("tests", {}).get("used")
    counts = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "attempts_started": usage.get("attempts"), "known_output_bearing_calls": usage.get("output_bearing_calls"),
        "decisions": usage.get("decisions"), "public_member_tests": tests}
    counts = {key: value if _integer(value) else None for key, value in counts.items()}
    calls = counts["known_output_bearing_calls"]
    counts["complete_actual_calls"] = calls if cost["complete_actual_tokens"] is not None and calls == counts["attempts_started"] else None
    return {**cost, **counts}


def _mapping_summary(entry, export):
    mapping = (entry or {}).get("mapping") or (export or {}).get("mapping")
    if not isinstance(mapping, dict):
        return None
    evidence = mapping.get("evidence", {})
    return {key: copy.deepcopy(mapping.get(key)) for key in
            ("spec_id", "status", "class_id", "composition_support_eligible", "member_projections", "reason")} | {
        "delivery_chain": copy.deepcopy(evidence.get("delivery_chain")),
        "task_and_responsibility_event_counts": dict(Counter(event.get("kind", "unknown") for event in
            evidence.get("task_and_responsibility_events", []))),
        "actual_input_binding_count": len(evidence["actual_inputs"]) if isinstance(evidence.get("actual_inputs"), (dict, list)) else None,
        "input_issues": copy.deepcopy(evidence.get("input_issues")),
        "evidence_sha256": mapping.get("evidence_sha256"), "causal_or_learning_value_claimed": False}


def _slot(root, unit, state, worker_report, issues):
    folder = root / unit["worker"] / "actual/episodes" / unit["slot_id"]
    saved = _read(folder / "slot-result.json", issues)
    progress = _read(root / unit["worker"] / "actual/progress.json", issues)
    candidates = [row for row in (progress or []) if isinstance(row, dict) and row.get("slot_id") == unit["slot_id"]] if isinstance(progress, list) else []
    if isinstance(worker_report, dict):
        candidates += [row for row in worker_report.get("rows", []) if row.get("slot_id") == unit["slot_id"]]
    invalid = False
    if saved is not None:
        if (saved.get("slot_id") != unit["slot_id"] or saved.get("sampling_seed") != unit["sampling_seed"]
                or saved.get("purpose") != unit["purpose"] or saved.get("first_member") != unit["first_member"]):
            issues.append({"slot_id": unit["slot_id"], "reason": "slot_result_differs_from_frozen_inventory"})
            invalid = True
        for candidate in candidates:
            if any(key in candidate and candidate[key] != saved.get(key) for key in
                   ("R_joint", "R_token", "Q_joint", "Q_token", "usage", "actor_identity", "status")):
                issues.append({"slot_id": unit["slot_id"], "reason": "progress_or_worker_result_disagrees_with_original_slot"})
                invalid = True
    if saved is None and not folder.exists() and not candidates:
        status = "conditional_not_applicable" if state.get("status") == "not_applicable" and state.get("attempted") is False else "not_started"
        row = {}
    else:
        row = saved or {}
        status = "closed" if not invalid and row.get("status") == "closed" else "technical_unknown"
        if not saved:
            usage, origin = _partial_usage(folder, issues)
            row = {"status": "technical_unknown", "usage": usage, "partial_usage_origin": origin}
            if candidates:
                issues.append({"slot_id": unit["slot_id"], "reason": "summary_exists_without_authoritative_slot_result"})
    metrics = dict.fromkeys(("R_joint", "R_token", "Q_joint", "Q_token"))
    if status == "closed":
        try:
            metrics = outcome_values(row)
            if metrics["R_joint"] is None:
                status = "technical_unknown"
            elif metrics["Q_joint"] is None:
                issues.append({"slot_id": unit["slot_id"], "reason": "quality_unavailable_for_closed_formal_result"})
        except (ValueError, TypeError, KeyError) as error:
            issues.append({"slot_id": unit["slot_id"], "reason": "inconsistent_formal_outcomes", "error": str(error)})
            status, metrics = "technical_unknown", dict.fromkeys(metrics)
    cost_row = {**row, "status": "closed" if status == "closed" else "technical_unknown"}
    if invalid:
        cost_row.pop("total_actual_tokens", None)
    measurement = _read(folder / "mechanical-measurement.json", issues) or {}
    feedback = measurement.get("feedback") or {}
    stop = measurement.get("stop_assessment") or {}
    entry = _read(folder / "training-entry.json", issues)
    export = _read(folder / "training-export.json", issues) if entry is None else None
    guard = _read(folder / "evaluation-guard.json", issues)
    return {**copy.deepcopy(unit), "status": status, **metrics,
        "administrative_censoring": row.get("administrative_censoring") if status not in UNUSED else None,
        "outcome_scope": row.get("outcome_scope"), "submitted": row.get("submitted"),
        "complete_delivery": row.get("complete_delivery"), "actor_identity": row.get("actor_identity"),
        "episode_start_steps": row.get("episode_start_steps"), "learning_binding": row.get("learning_binding"),
        "cost": _cost(cost_row, status=status, issues=issues, path=folder),
        "usage_by_member": copy.deepcopy(row.get("usage_by_member")),
        "partial_usage_origin": row.get("partial_usage_origin"),
        "mapped_work": _mapping_summary(entry, export),
        "training_reward": copy.deepcopy((entry or {}).get("reward")),
        "validity": copy.deepcopy((entry or {}).get("rollout", {}).get("work_validity")) if entry else None,
        "measurement": {"decision": measurement.get("decision"), "global_violations": stop.get("global_violations"),
            "unresolved": stop.get("unresolved"), "feedback_denominators": feedback.get("denominators"),
            "page_denominators": feedback.get("page_denominators"), "local_resource_rejections": stop.get("local_resource_rejections"),
            "context_blocked_feedback_ids": stop.get("context_blocked_feedback_ids"),
            "actual_input_gate": copy.deepcopy(feedback.get("mechanism_gate_inputs"))},
        "evaluation_guard": {key: (guard or {}).get(key) for key in
            ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")},
        "references": {name: _ref(folder / name) for name in ("slot-result.json", "team-budget.json", "organization-evidence.json",
            "mechanical-measurement.json", "evaluation-guard.json", "training-entry.json", "training-export.json")},
        "episode_folder": str(folder), "conditional_reason": state.get("reason") if status == "conditional_not_applicable" else None}


def _sum_complete(rows, key):
    values = [row["cost"].get(key) for row in rows]
    return sum(values) if all(_number(value) for value in values) else None


def aggregate_rows(units, rows, direction=None):
    """Use every fixed unit; a missing paired result never becomes zero."""
    if ([row["slot_id"] for row in rows] != [unit["slot_id"] for unit in units]
            or len({row["slot_id"] for row in rows}) != len(units)):
        raise ValueError("Aggregation requires each frozen original unit exactly once in order")
    counts = dict(Counter(row["status"] for row in rows))
    branches = {}
    for branch in BRANCHES:
        panel = [row for row in rows if row["phase"] == "development" and row["branch"] == branch]
        if len(panel) != 4:
            raise ValueError("Each post-update branch has exactly four planned paired development units")
        values = {}
        for metric in ("R_joint", "Q_joint", "R_token", "Q_token"):
            observed = [row.get(metric) if row["status"] == "closed" else None for row in panel]
            values[metric] = {"planned_denominator": 4, "known": sum(value is not None for value in observed),
                "values": observed, "mean": sum(observed) / 4 if all(value is not None for value in observed) else None}
        branches[branch] = {"status_counts": dict(Counter(row["status"] for row in panel)),
            "F": values["R_joint"]["mean"], "Q": values["Q_joint"]["mean"], "metrics": values,
            "administrative_joint_known": sum(row.get("administrative_censoring") is True and row.get("R_joint") is not None for row in panel),
            "complete_actual_tokens": _sum_complete(panel, "complete_actual_tokens"),
            "known_actual_tokens_subtotal": sum(row["cost"]["known_actual_tokens"] for row in panel if _number(row["cost"].get("known_actual_tokens"))),
            "slot_ids": [row["slot_id"] for row in panel]}
    base = branches["B"]["F"]
    contrasts = {branch + "_minus_B": branches[branch]["F"] - base if branches[branch]["F"] is not None and base is not None else None
                 for branch in ("Q_plus", "Q_minus")}
    selected = isinstance(direction, dict) and direction.get("selected") is True
    epsilon = direction.get("epsilon") if selected else None
    plus, minus = branches["Q_plus"]["F"], branches["Q_minus"]["F"]
    fd = (plus - minus) / (2 * epsilon) if selected and _number(epsilon) and epsilon > 0 and plus is not None and minus is not None else None
    paired = []
    for unit in [unit for unit in units if unit["phase"] == "development" and unit["branch"] == "B"]:
        pair = {branch: next(row for row in rows if row.get("unit_id") == unit["unit_id"] and row["branch"] == branch)
                for branch in BRANCHES}
        outcomes = {branch: pair[branch].get("R_joint") if pair[branch]["status"] == "closed" else None for branch in BRANCHES}
        paired.append({"unit_id": unit["unit_id"], "root": unit["root"], "sampling_seed": unit["sampling_seed"],
            "R_joint": outcomes, "Q_joint": {branch: pair[branch].get("Q_joint") for branch in BRANCHES},
            "complete_actual_tokens": {branch: pair[branch]["cost"].get("complete_actual_tokens") for branch in BRANCHES},
            "Q_plus_minus_B": outcomes["Q_plus"] - outcomes["B"] if outcomes["Q_plus"] is not None and outcomes["B"] is not None else None,
            "Q_minus_minus_B": outcomes["Q_minus"] - outcomes["B"] if outcomes["Q_minus"] is not None and outcomes["B"] is not None else None,
            "Q_plus_minus_Q_minus": outcomes["Q_plus"] - outcomes["Q_minus"] if outcomes["Q_plus"] is not None and outcomes["Q_minus"] is not None else None})
    return {"planned_slots": len(units), "status_counts": counts,
        "training_status_counts": dict(Counter(row["status"] for row in rows if row["phase"] == "training")),
        "administrative_joint_known": sum(row.get("administrative_censoring") is True and row.get("R_joint") is not None for row in rows),
        "all_applicable_slots_closed": all(row["status"] in {"closed", "conditional_not_applicable"} for row in rows),
        "branches": branches, "paired_development": paired, "contrasts": contrasts,
        "finite_difference": fd, "epsilon": epsilon, "F_binary_resolution": .25,
        "generation": {"known_actual_tokens_subtotal": sum(row["cost"]["known_actual_tokens"] for row in rows if _number(row["cost"].get("known_actual_tokens"))),
            "slots_without_known_usage": [row["slot_id"] for row in rows if row["cost"].get("known_actual_tokens") is None],
            **{key: _sum_complete(rows, key) for key in ("complete_actual_tokens", "budget_charged_tokens", "uncertain_usage_attempts",
                "prompt_tokens", "completion_tokens", "attempts_started", "known_output_bearing_calls", "complete_actual_calls", "decisions", "public_member_tests")},
            "scope": "Whole original team episodes including trusted failures and work after first submission. Known partial actual use is a subtotal; incomplete full cost is null. Unstarted conditional stock has zero incurred generation cost, not zero utility."},
        "estimand": "Formal R_joint under the fixed token-and-time policy; administrative R_token/Q_token remain null.",
        "unupdated_state_development_executed": False, "B_improvement_over_pretraining_claimed": False,
        "scope": "One local finite Contribution sensitivity direction; not full I-P/I-S, independent confirmation, causal cooperation attribution or proof that a zero finite difference means C=0."}


def _worker_costs(states):
    known, complete, rows = 0., True, []
    for worker in WORKERS:
        state = states.get(worker, {})
        elapsed = state.get("elapsed_gpu_seconds")
        unused = state.get("attempted") is False and state.get("status") in {"not_started", "not_applicable", "stopped"}
        if unused:
            elapsed = 0.
        elif not _number(elapsed) or elapsed < 0:
            elapsed, complete = None, False
        if elapsed is not None:
            known += elapsed
        rows.append({"worker": worker, "status": state.get("status"), "attempted": state.get("attempted"),
            "physical_gpu": state.get("gpu"), "elapsed_gpu_seconds": elapsed,
            "started_at": state.get("started_at"), "ended_at": state.get("ended_at"), "exit_code": state.get("exit_code")})
    return {"workers": rows, "known_closed_worker_seconds": known,
        "complete_worker_seconds": known if complete else None, "complete_worker_hours": known / 3600 if complete else None,
        "scope": "Original supervisor assigned-GPU worker intervals, including S0 loading, collection, full training and development. Sum each new worker once; nested update/episode durations are not added. This is not GPU utilization or a hardware-residency trace."}


def _update(root, branch, state, worker_report, issues):
    folder = root / ("update-" + branch) / "actual"
    update = _read(folder / "update/report.json", issues)
    consumption = _read(folder / "update/software-consumption.json", issues)
    signals = _read(folder / "update/signal-diagnostics.json", issues)
    checkpoint = _read(folder / "checkpoint/checkpoint.json", issues)
    unused = state.get("attempted") is False and state.get("status") in {"not_started", "not_applicable", "stopped"}
    def steps(key):
        value = (update or {}).get(key)
        return value if _integer(value) else 0 if unused else None
    fields = ("status", "stage", "before_actor_identity", "after_actor_identity", "actor_steps_total", "critic_steps_total",
        "behavior_probability_passed", "old_critic_values", "advantages", "rewards", "gradient_norms", "changed_actor_elements",
        "actor_update_enabled", "zero_signal_window", "admitted_decisions", "admitted_output_tokens", "post_update_additional_actor_forwards")
    return {"branch": branch, "worker_status": state.get("status"), "worker_error": (worker_report or {}).get("error"),
        "report": {key: (update or {}).get(key) for key in fields}, "consumption": consumption,
        "actor_optimizer_steps": steps("actor_optimizer_steps"), "critic_optimizer_steps": steps("critic_optimizer_steps"),
        "backward_decisions_completed": steps("backward_decisions_completed"),
        "checkpoint": checkpoint, "signals": signals,
        "recipe": copy.deepcopy((update or {}).get("recipe")),
        "references": {str(path.relative_to(folder)): _ref(path) for path in (
            folder / "report.json", folder / "loaded-state.json", folder / "update/report.json", folder / "update/software-consumption.json",
            folder / "update/admission.json", folder / "update/losses.json", folder / "update/signal-diagnostics.json",
            folder / "update/support-gradients.json", folder / "update-original-updater-binding.json", folder / "checkpoint/checkpoint.json")}}


def results(root):
    root = Path(root).resolve()
    started = time.monotonic()
    issues = []
    plan = read_json(root / "plan.json")
    if plan.get("version") != "software-learning-window-v0.49":
        raise ValueError("Read only a new v049 learning root; old experimental results cannot fill this inventory")
    units = inventory(plan)
    supervisor = _read(root / "supervisor.json", issues) or {}
    states = supervisor.get("states", {})
    workers = {name: {"state": copy.deepcopy(states.get(name, {})),
        "report": _read(root / name / "actual/report.json", issues),
        "reference": _ref(root / name / "actual/report.json")} for name in WORKERS}
    rows = [_slot(root, unit, states.get(unit["worker"], {}), workers[unit["worker"]]["report"], issues) for unit in units]
    direction = _read(root / "direction.json", issues)
    if direction is not None and direction.get("seal_sha256") != digest(json_bytes({key: value for key, value in direction.items() if key != "seal_sha256"})):
        issues.append({"path": str(root / "direction.json"), "reason": "direction_envelope_seal_mismatch"})
        direction = None
    support = _read(root / "support.json", issues)
    support_summary = None
    if support is not None:
        if support.get("seal_sha256") != digest(json_bytes({key: value for key, value in support.items() if key != "seal_sha256"})):
            issues.append({"path": str(root / "support.json"), "reason": "support_seal_mismatch"})
        else:
            support_summary = {key: copy.deepcopy(support.get(key)) for key in ("window_id", "root_order", "member_order", "category_order",
                "roots", "base_learning_material_available", "original_slot_count", "global_member_denominator_factor", "scope")}
    updates = {branch: _update(root, branch, states.get("update-" + branch, {}), workers["update-" + branch]["report"], issues) for branch in BRANCHES}
    base_identity = updates["B"]["report"].get("after_actor_identity")
    for branch in ("Q_plus", "Q_minus"):
        identity = updates[branch]["report"].get("after_actor_identity")
        updates[branch]["actor_adapter_equal_B"] = identity.get("adapter_sha256") == base_identity.get("adapter_sha256") if identity and base_identity else None
    update_totals = {key: sum(value[key] for value in updates.values()) if all(_integer(value[key]) for value in updates.values()) else None
                     for key in ("actor_optimizer_steps", "critic_optimizer_steps", "backward_decisions_completed")}
    measurements = {row["slot_id"]: row["measurement"] for row in rows if row["measurement"]["decision"] is not None}
    value = {"version": VERSION, "run_root": str(root), "status": supervisor.get("status", "supervisor_record_unavailable"),
        "generated_at": time.time(), "plan": _ref(root / "plan.json"), "source": plan.get("source"),
        "design": plan.get("design"), "budget_caps": {"planned_generation_slots": 20,
            "maximum_actual_generation_tokens": plan["inventory"].get("maximum_actual_generation_tokens"),
            "per_episode": plan["inventory"].get("per_episode"), "training_cost_separate": True},
        "rows": rows, "metrics": aggregate_rows(units, rows, direction), "updates": updates, "new_update_totals": update_totals,
        "support": support_summary, "direction": direction, "workers": {name: {"state": row["state"], "reference": row["reference"],
            "status": (row["report"] or {}).get("status"), "error": (row["report"] or {}).get("error"),
            "source_before": (row["report"] or {}).get("source_before"), "source_after": (row["report"] or {}).get("source_after")} for name, row in workers.items()},
        "GPU_worker_cost": _worker_costs(states), "mechanism_decision_counts": dict(Counter(row["decision"] for row in measurements.values())),
        "s0": _read(root / "s0.json", issues), "recipe_binding": _read(root / "s0/actual/recipe-binding.json", issues),
        "references": {name: _ref(root / name) for name in ("supervisor.json", "s0.json", "declaration.json", "support.json", "direction.json", "precollection-binding.json")},
        "mechanism_stops": [{"reference": _ref(path), "record": _read(path, issues)} for path in sorted((root / "mechanism-stops").glob("*.json"))],
        "evidence_issues": issues, "complete_tensor_checkpoint_comparison_executed": False,
        "automatic_successors": plan.get("automatic_successors"), "old_queues_remain_paused": plan.get("old_queues_remain_paused"),
        "old_execution_cost_added": 0, "read_only": True,
        "new_model_calls_by_reporter": 0, "new_backward_calls_by_reporter": 0, "new_world_or_acceptance_executions": 0,
        "reporting_elapsed_seconds": time.monotonic() - started,
        "scope": "All original v049 planned inventory, original formal joint outcomes and complete incurred costs. No old run fills a new slot; unknown stays null. Mapping adoption facts are not causal or learning-contribution labels; B has no unupdated-state development comparator."}
    return value


def markdown(value):
    metrics, generation = value["metrics"], value["metrics"]["generation"]
    lines = ["# v049 Γ1/O1 真实学习窗口报告", "", f"原运行状态：`{value['status']}`。固定库存20槽，状态：`{metrics['status_counts']}`。",
        f"实际费用已知部分 {generation['known_actual_tokens_subtotal']} token；完整实际费用 {generation['complete_actual_tokens']}；完整实际调用 {generation['complete_actual_calls']}。",
        f"新GPU worker总小时：{value['GPU_worker_cost']['complete_worker_hours']}（含S0、采集、学习、开发；不重复加嵌套时长）。", "",
        "## 更新后配对开发", "", "F使用正式R_joint；每分支原4单位全部已知才计算均值。行政关闭的R_token/Q_token仍保留null。", "",
        "| 分支 | 状态 | F | Q | 完整回合token |", "|---|---|---:|---:|---:|"]
    for branch, result in metrics["branches"].items():
        lines.append(f"| {branch} | {result['status_counts']} | {result['F']} | {result['Q']} | {result['complete_actual_tokens']} |")
    lines += ["", f"Q+−B：{metrics['contrasts']['Q_plus_minus_B']}；Q−−B：{metrics['contrasts']['Q_minus_minus_B']}；epsilon：{metrics['epsilon']}；有限差分：{metrics['finite_difference']}。",
        "二元F分辨率为0.25。未更新状态没有开发执行，不能推断B相对训练前收益；零差不是精确C=0。", "", "## 原20槽库存", "",
        "| 槽 | 阶段/分支 | 状态 | R_joint | Q_joint | 行政删失 | 完整token | 已知token |", "|---|---|---|---:|---:|---|---:|---:|"]
    for row in value["rows"]:
        lines.append(f"| {row['slot_id']} | {row['phase']}/{row['branch']} | {row['status']} | {row['R_joint']} | {row['Q_joint']} | {row['administrative_censoring']} | {row['cost']['complete_actual_tokens']} | {row['cost']['known_actual_tokens']} |")
    lines += ["", "## 学习剂量与完整状态", "", "| 分支 | 更新状态 | actor步 | critic步 | 完整反向决定 | actor梯度norm | actor与B同值 |", "|---|---|---:|---:|---:|---:|---|"]
    for branch, row in value["updates"].items():
        norms = row["report"].get("gradient_norms") or {}
        lines.append(f"| {branch} | {row['report']['status']} | {row['actor_optimizer_steps']} | {row['critic_optimizer_steps']} | {row['backward_decisions_completed']} | {norms.get('actor')} | {row.get('actor_adapter_equal_B')} |")
    lines += ["", "前向、反向、optimizer、支持观察、完整原材料规模和保存恢复凭据详见JSON中的updates/consumption及原文件引用。这里未加载checkpoint张量比较critic/Adam，不把参数摘要比较写成额外模型实验。", "",
        "## 真实支持", "", "| root/member | M | 实际重复 | 基础轨迹 | n支持 | v | 类数量/计数 | b |", "|---|---:|---:|---:|---:|---:|---|---|"]
    for root, group in (value.get("support") or {}).get("roots", {}).items():
        for member, block in group["blocks"].items():
            lines.append(f"| {root}/{member} | {block['M']} | {block['actual_repeats']} | {block['base_training_trajectory_count']} | {block['n_positive']} | {block['v']} | {len(block['b'])}/{block['n_by_class']} | {block['b']} |")
    lines += ["", "各成员原优势、mask、未映射/缺证原因及梯度方向检查保存在JSON。可信失败、未提交与残余材料不按成功筛掉；缺失槽不转移质量。原工作采用链只作Mapper事实，不能直接解释为正Contribution或一般协作收益。", "",
        "## 记录边界", "", f"机械判断：`{value['mechanism_decision_counts']}`；读原件时发现的问题数：{len(value['evidence_issues'])}。",
        "本报告只读新v049原件，不运行模型、tokenizer、世界或验收，不加旧历史成本。未开始与条件不适用均保留，未知结果和完整费用保持null。完整JSON包含所有源文件引用、worker成本、recipe/S0身份、配对逐单位差及未决记录。", ""]
    return "\n".join(lines)


def report(root, destination):
    destination = Path(destination).resolve()
    if destination == Path(root).resolve():
        raise ValueError("Write analysis to a separate destination, never over original run records")
    value = results(root)
    destination.mkdir(parents=True, exist_ok=True)
    atomic_write(destination / "software-learning-v049.json", json_bytes(value))
    atomic_write(destination / "software-learning-v049.md", markdown(value).encode())
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
