"""Account two stopped Q-minus attempts and one same-material recomputation.

The original 48-hour Q-minus branch cap is explicitly replaced for this attempt
by redistribution within the unchanged aggregate 144-hour training interval cap.
B is charged its completed interval; Q-plus keeps its full original 48 hours.
The numerical H1 function, rows, composition, and optimizer-count caps do not change.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import math
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts import software_learning_resume_compute_v050r2 as prior
from scripts import software_learning_resume_v050r1 as previous
from scripts import software_learning_v050 as original
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-Qminus-recompute-v0.50-r3"
PARENT_VERSION = "software-learning-original-Q-continuation-v0.50-r2"
SOURCE = Path(__file__).resolve().parents[1]
WORKER = prior.WORKER
COPIED_INPUTS = prior.COPIED_INPUTS
NUMERIC_SOURCES = prior.NUMERIC_SOURCES
MAX_R3_INTERVAL_SECONDS = 170001
TIME_POLICY = "B-actual-plus-Qplus-full48h-within-original-total144h"


def _stream_reference(path):
    """Hash immutable material without loading a billion-byte JSON into memory."""
    path = Path(path).resolve()
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return {"path": str(path), "sha256": hasher.hexdigest()}


def _bound_reference(path, expected):
    actual = _stream_reference(path)
    if actual["sha256"] != expected.get("sha256") or Path(expected["path"]).resolve() != Path(path).resolve():
        raise ValueError("Frozen prior evidence changed: " + str(path))
    return actual


def _attempt(root, plan, maximum):
    output = root / WORKER / "actual"
    compute = read_json(output / "training-compute.json")
    report = read_json(output / "update/report.json")
    stop_path = root / "mechanism-stops" / (WORKER + "-supervisor.json")
    stop = read_json(stop_path)
    state = stop.get("worker_state", {})
    host_path = root / "host-stop-actions" / (WORKER + ".json")
    host = read_json(host_path)
    task = read_json(output / "task.json")
    rows = compute.get("admitted_rows")
    completed = report.get("backward_decisions_completed")
    gradient = compute.get("native_gradient_forward_started")
    if (type(rows) is not int or not 0 < rows <= original.LIMITS["max_admitted_rows_per_update"]
            or report.get("admitted_decisions") != rows or type(completed) is not int
            or type(gradient) is not int or not 0 <= completed < rows or gradient != completed + 1
            or compute.get("native_no_grad_forward_started") != rows
            or compute.get("native_forward_started") != rows + gradient
            or compute.get("native_forward_completed") != rows + gradient
            or compute.get("maximum_seconds") != maximum or compute.get("ended_at") is not None
            or compute.get("forward_upper") != 2 * rows + 6
            or any(compute.get(key) != rows for key in ("actor_backward_upper", "critic_backward_upper"))
            or any(compute.get(key) != 1 for key in ("actor_steps_upper", "critic_steps_upper"))
            or report.get("stage") != "backward" or report.get("status") != "preparing"
            or report.get("training_happened") is not False or report.get("actor_update_enabled") is not True
            or report.get("behavior_probability_passed") is not True
            or any(report.get(key) != 0 for key in ("actor_optimizer_steps", "critic_optimizer_steps"))):
        raise ValueError("Only a bound pre-optimizer interruption can be recomputed")
    if (stop.get("worker") != WORKER or stop.get("kind") != "execution_fault"
            or stop.get("reason") != "shared_device_free_memory_reserve"
            or state.get("worker") != WORKER or state.get("status") != "stopped"
            or state.get("attempted") is not True or state.get("exit_code") != -9
            or stop.get("observed_at") != state.get("ended_at")
            or host.get("worker") != WORKER or host.get("reason") != stop["reason"]
            or host.get("process_returncode") != -9 or host.get("pid") != state.get("pid")
            or host.get("process_identity") != state.get("process_identity")
            or task.get("pid") != state.get("pid")
            or task.get("task") != f"learning-backward-or-bookkeeping-{rows + gradient:06d}"
            or not host.get("requested_at", float("inf")) <= host.get("stop_procedure_returned_at", -1) <= state["ended_at"]):
        raise ValueError("The stopped worker and host termination receipt must be fully bound")
    _bound_reference(host_path, state["host_stop_action"])
    elapsed = state["ended_at"] - compute["started_at"]
    if not math.isfinite(elapsed) or not 0 < elapsed < maximum:
        raise ValueError("Interrupted interval must be positive and within its prior authorization")
    tensors = sorted(str(p.relative_to(output)) for p in output.rglob("*")
        if p.is_file() and p.suffix in {".pt", ".pth", ".bin", ".safetensors"})
    if tensors != ["update/shared-before.pt"] or any(output.rglob("*checkpoint*")):
        raise ValueError("Unexpected checkpoint or accumulated-gradient state needs separate disposition")
    loaded = read_json(output / "loaded-state.json")
    expected = read_json(original.checked(plan["s_star_checkpoint"]))
    if (loaded.get("branch") != "S_star" or loaded.get("checkpoint") != plan["s_star_checkpoint"]
            or loaded.get("restored") != expected or loaded.get("actor_identity") != expected.get("actor_identity")
            or (loaded.get("actor_steps"), loaded.get("critic_steps")) != (4, 4)
            or (expected.get("actor_steps"), expected.get("critic_steps")) != (4, 4)
            or report.get("before_actor_identity") != expected.get("actor_identity")
            or report.get("recipe") != plan.get("s_star_recipe")):
        raise ValueError("Both attempts must restore the same complete S_star 4/4 and recipe")
    binding = read_json(output / "update-original-updater-binding.json")
    if (binding.get("original_source", {}).get("sha256") != plan["source_files"]["src/proworksim/online_training.py"]
            or binding.get("code_object_identical") is not True):
        raise ValueError("The attempt must bind the unchanged original H1 source")
    evidence = {name: reference(output / name) for name in ("training-compute.json", "update/report.json",
        "task.json", "loaded-state.json", "composition-before-update.json", "update/composition.json",
        "update-v050-learning-binding.json", "update-original-updater-binding.json")}
    return {"root": str(root), "training_started_at": compute["started_at"],
        "training_ended_at_upper": state["ended_at"], "elapsed_seconds_upper": elapsed,
        "native_forward_started": compute["native_forward_started"],
        "native_forward_completed": compute["native_forward_completed"],
        "backward_completed_lower": completed, "backward_charged_upper": gradient,
        "actor_optimizer_steps": 0, "critic_optimizer_steps": 0, "admitted_rows": rows,
        "partial_row_backward_exact": False, "tensor_filenames_inspected_only": tensors,
        "evidence": evidence, "stop": reference(stop_path), "host_stop": reference(host_path)}


def derive_replay_budget(parent_run_root):
    """Bind r2 and original r1; reserve all Q-plus time without reading its status."""
    root = Path(parent_run_root).resolve()
    plan = original.check_seal(read_json(root / "plan.json"), "plan_sha256")
    first_root = Path(plan["parent_run_root"]).resolve()
    first_plan = original.check_seal(read_json(first_root / "plan.json"), "plan_sha256")
    prior_budget = original.check_seal(plan["qminus_compute_replay"])
    if (plan.get("version") != PARENT_VERSION or first_plan.get("version") != previous.VERSION
            or plan.get("limits") != original.LIMITS or first_plan.get("limits") != original.LIMITS
            or plan.get("training_budget") != first_plan.get("training_budget")
            or plan.get("s_star_checkpoint") != first_plan.get("s_star_checkpoint")
            or plan.get("s_star_recipe") != first_plan.get("s_star_recipe")):
        raise ValueError("Only the frozen r2-to-r1 Q-minus chain and original limits are eligible")
    _bound_reference(first_root / "plan.json", plan["parent_plan"])
    _bound_reference(first_root / "plan.json", prior_budget["parent_plan"])
    if prior_budget.get("version") != prior.VERSION or Path(prior_budget["parent_run_root"]).resolve() != first_root:
        raise ValueError("The second attempt must bind the original first-attempt budget")
    r1 = _attempt(first_root, first_plan, original.LIMITS["update_worker_seconds"])
    r2 = _attempt(root, plan, prior_budget["remaining_seconds"])
    first_compute = read_json(first_root / WORKER / "actual/training-compute.json")
    second_compute = read_json(root / WORKER / "actual/training-compute.json")
    if (r1["admitted_rows"] != r2["admitted_rows"]
            or prior_budget.get("prior_elapsed_seconds_upper") != r1["elapsed_seconds_upper"]
            or prior_budget.get("prior_native_forward_started") != r1["native_forward_started"]
            or prior_budget.get("prior_native_forward_completed") != r1["native_forward_completed"]
            or prior_budget.get("prior_actor_backward_charged_upper") != r1["backward_charged_upper"]
            or prior_budget.get("prior_critic_backward_charged_upper") != r1["backward_charged_upper"]
            or prior_budget.get("prior_actor_backward_completed_lower") != r1["backward_completed_lower"]
            or prior_budget.get("prior_critic_backward_completed_lower") != r1["backward_completed_lower"]
            or prior_budget.get("remaining_seconds") != 172800 - r1["elapsed_seconds_upper"]
            or second_compute.get("replay_version") != prior.VERSION
            or second_compute.get("replay_budget_sha256") != prior_budget["sha256"]
            or second_compute.get("prior_elapsed_seconds_upper") != r1["elapsed_seconds_upper"]
            or second_compute.get("prior_native_forward_started") != r1["native_forward_started"]
            or second_compute.get("prior_actor_backward_charged_upper") != r1["backward_charged_upper"]
            or second_compute.get("prior_critic_backward_charged_upper") != r1["backward_charged_upper"]
            or first_compute["admitted_rows"] != prior_budget["admitted_rows_per_attempt"]):
        raise ValueError("Both old attempts must be counted exactly once, including uncertain backward rows")
    for name, expected in prior_budget["prior_evidence"].items():
        _bound_reference(first_root / WORKER / "actual" / name, expected)
    _bound_reference(first_root / "mechanism-stops" / (WORKER + "-supervisor.json"), prior_budget["prior_stop"])
    refs = {}
    for name in COPIED_INPUTS:
        expected = prior_budget["inputs"][name]
        _bound_reference(first_root / name, expected)
        current = _stream_reference(root / name)
        if current["sha256"] != expected["sha256"]:
            raise ValueError("Both prior attempts must retain the exact original material: " + name)
        refs[name] = current
    replay_binding = read_json(root / WORKER / "actual/recompute-binding.json")
    if replay_binding.get("budget") != prior_budget or replay_binding.get("partial_state_reused") is not False:
        raise ValueError("The second attempt must be an exact S_star recomputation, not partial-gradient reuse")
    numeric = numeric_path_receipt(plan["source_root"])
    if numeric != replay_binding.get("numeric_path"):
        raise ValueError("The frozen r2 numerical source evidence changed")
    for name in NUMERIC_SOURCES:
        expected = numeric["source_files_identical"][name]
        if first_plan["source_files"].get(name) != expected or plan["source_files"].get(name) != expected:
            raise ValueError("The two plans must bind identical numerical sources: " + name)
    first_output = first_root / WORKER / "actual"
    output = root / WORKER / "actual"
    for name in ("loaded-state.json", "update-v050-learning-binding.json"):
        if read_json(first_output / name) != read_json(output / name):
            raise ValueError("The prior state or learning binding differs: " + name)
    direction = original.check_seal(read_json(root / "direction.json"), "seal_sha256")
    core = original.check_seal(direction["direction"], "seal_sha256")
    if (direction.get("selected") is not True or direction.get("frozen_before_any_development") is not True
            or direction.get("minus_weights") != core.get("minus_weights_by_slot")):
        raise ValueError("The sole original Q-minus direction must remain frozen")
    compositions = [original.check_seal(read_json(folder / name), "seal_sha256")
        for folder in (first_output, output) for name in ("composition-before-update.json", "update/composition.json")]
    if (any(value != compositions[0] for value in compositions)
            or compositions[0].get("weights_by_slot") != direction["minus_weights"]
            or compositions[0].get("entries_sha256") != refs["entries.json"]["sha256"]):
        raise ValueError("No omission, reorder, or reweighting of original Q-minus material is permitted")
    b_output = first_root / "update-B/actual"
    b_compute = read_json(b_output / "training-compute.json")
    b_report = read_json(b_output / "report.json")
    b_update = read_json(b_output / "update/report.json")
    b_seconds = b_compute.get("elapsed_seconds")
    if (b_report.get("status") != "complete" or b_report.get("success_boundary") is not True
            or b_compute.get("ended_at") is None or type(b_seconds) not in (int, float)
            or not math.isfinite(b_seconds) or not 0 < b_seconds <= 172800
            or b_seconds != b_compute["ended_at"] - b_compute["started_at"]
            or b_report.get("new_actor_steps") != 1 or b_report.get("new_critic_steps") != 1
            or b_update.get("actor_optimizer_steps") != 1 or b_update.get("critic_optimizer_steps") != 1
            or b_update.get("backward_decisions_completed") != r1["admitted_rows"]
            or b_compute.get("native_gradient_forward_started") != r1["admitted_rows"]
            or b_compute.get("native_forward_completed") != b_compute.get("native_forward_started")):
        raise ValueError("B must retain its exact completed original training interval")
    _bound_reference(b_output / "update/report.json", direction["B_update"])
    _bound_reference(b_output / "update/report.json", b_report["update_report"])
    budget = plan["training_budget"]
    if (budget.get("aggregate_worker_seconds") != 518400 or budget.get("per_branch_worker_seconds") != 172800
            or budget.get("per_branch_actor_optimizer") != 1 or budget.get("per_branch_critic_optimizer") != 1):
        raise ValueError("Original aggregate 144-hour and optimizer ceilings must remain unchanged")
    old_seconds = r1["elapsed_seconds_upper"] + r2["elapsed_seconds_upper"]
    available = 518400 - b_seconds - 172800 - old_seconds
    remaining = min(MAX_R3_INTERVAL_SECONDS, math.floor(available))
    if remaining <= 0:
        raise ValueError("No shared 144-hour training interval remains for Q-minus")
    count = r1["admitted_rows"]
    forwards = r1["native_forward_started"] + r2["native_forward_started"]
    lower = r1["backward_completed_lower"] + r2["backward_completed_lower"]
    upper = r1["backward_charged_upper"] + r2["backward_charged_upper"]
    cumulative = {"forward": forwards + 2 * count + 6, "actor_backward": upper + count, "critic_backward": upper + count}
    if cumulative["forward"] > 6150 or max(cumulative["actor_backward"], cumulative["critic_backward"]) > 3072:
        raise ValueError("All old and new work together exceed an original same-branch count cap")
    return original.seal({"version": VERSION, "worker": WORKER, "parent_run_root": str(root),
        "original_run_root": str(first_root), "parent_plan": reference(root / "plan.json"),
        "original_plan": reference(first_root / "plan.json"), "inputs": refs, "prior_attempts": [r1, r2],
        "prior_elapsed_seconds_upper": old_seconds, "remaining_seconds": remaining,
        "remaining_seconds_exact": available, "original_branch_seconds_cap": 172800,
        "original_branch_remaining_seconds": 172800 - old_seconds,
        "original_branch_48h_enforced": False, "time_policy": TIME_POLICY,
        "aggregate_compute_seconds_cap": 518400, "B_complete_interval_seconds": b_seconds,
        "Q_plus_reserved_seconds": 172800, "Q_plus_live_status_read": False,
        "B_compute": reference(b_output / "training-compute.json"), "B_report": reference(b_output / "report.json"),
        "aggregate_fixed_other_seconds": b_seconds + 172800,
        "new_branch_total_seconds_upper": old_seconds + remaining,
        "aggregate_seconds_upper": b_seconds + 172800 + old_seconds + remaining,
        "admitted_rows_per_attempt": count, "prior_native_forward_started": forwards,
        "prior_native_forward_completed": forwards, "prior_actor_backward_completed_lower": lower,
        "prior_critic_backward_completed_lower": lower, "prior_actor_backward_charged_upper": upper,
        "prior_critic_backward_charged_upper": upper, "prior_partial_row_backward_exact": False,
        "prior_actor_optimizer_steps": 0, "prior_critic_optimizer_steps": 0,
        "new_forward_upper": 2 * count + 6, "new_actor_backward_upper": count, "new_critic_backward_upper": count,
        "cumulative_upper": cumulative, "tensor_filenames_inspected_only": ["update/shared-before.pt"],
        "restart_from_complete_S_star": True, "resume_partial_gradients_or_RNG": False,
        "new_direction_or_material": False, "same_single_scientific_Qminus_branch": True,
        "prior_cost_counted_once": True, "numeric_path": numeric})


def numeric_path_receipt(parent_source_root):
    return prior.numeric_path_receipt(parent_source_root)


def training_compute_receipt(admission, *, replay, started_at=None):
    original.check_seal(replay)
    if replay.get("version") != VERSION or admission != read_json(original.checked(replay["inputs"]["pretraining-admission.json"])):
        raise ValueError("Recomputation cannot replace, omit or reorder the admitted rows")
    receipt = original.training_compute_receipt(admission, started_at=started_at)
    receipt.update(maximum_seconds=replay["remaining_seconds"], replay_version=VERSION,
        replay_budget_sha256=replay["sha256"], prior_elapsed_seconds_upper=replay["prior_elapsed_seconds_upper"],
        original_branch_seconds_cap=172800, original_branch_48h_enforced=False,
        original_branch_remaining_seconds=replay["original_branch_remaining_seconds"],
        time_policy=TIME_POLICY, aggregate_compute_seconds_cap=518400,
        B_complete_interval_seconds=replay["B_complete_interval_seconds"], Q_plus_reserved_seconds=172800,
        aggregate_fixed_other_seconds=replay["aggregate_fixed_other_seconds"],
        prior_native_forward_started=replay["prior_native_forward_started"],
        prior_actor_backward_charged_upper=replay["prior_actor_backward_charged_upper"],
        prior_critic_backward_charged_upper=replay["prior_critic_backward_charged_upper"],
        cumulative_forward_cap=6150, cumulative_actor_backward_cap=3072, cumulative_critic_backward_cap=3072,
        old_cost_counted_once=True, restart_from_S_star=True)
    if (receipt["forward_upper"] + receipt["prior_native_forward_started"] > 6150
            or receipt["actor_backward_upper"] + receipt["prior_actor_backward_charged_upper"] > 3072
            or receipt["critic_backward_upper"] + receipt["prior_critic_backward_charged_upper"] > 3072):
        raise ValueError("Cumulative branch budget cannot admit a full same-material recomputation")
    reason = training_stop_reason(receipt, now=receipt["started_at"])
    if reason:
        raise ValueError(reason)
    return receipt


def training_stop_reason(receipt, now=None):
    now = time.time() if now is None else now
    if receipt.get("replay_version") != VERSION:
        return "replay_compute_receipt_identity"
    maximum = receipt.get("maximum_seconds")
    old = receipt.get("prior_elapsed_seconds_upper", float("nan"))
    b_seconds = receipt.get("B_complete_interval_seconds", float("nan"))
    fixed = receipt.get("aggregate_fixed_other_seconds", float("nan"))
    if (type(maximum) is not int or not 0 < maximum <= MAX_R3_INTERVAL_SECONDS
            or not math.isfinite(old) or old <= 0 or not math.isfinite(b_seconds) or not 0 < b_seconds <= 172800
            or receipt.get("time_policy") != TIME_POLICY or receipt.get("original_branch_48h_enforced") is not False
            or receipt.get("original_branch_seconds_cap") != 172800
            or receipt.get("original_branch_remaining_seconds") != 172800 - old
            or receipt.get("aggregate_compute_seconds_cap") != 518400
            or receipt.get("Q_plus_reserved_seconds") != 172800 or fixed != b_seconds + 172800
            or maximum != min(MAX_R3_INTERVAL_SECONDS, math.floor(518400 - fixed - old))):
        return "replay_compute_interval_changed"
    if now - receipt["started_at"] >= maximum:
        return "cumulative_update_interval_exhausted"
    forwards = receipt.get("native_forward_started", 0)
    gradient_forwards = receipt.get("native_gradient_forward_started", 0)
    if (receipt.get("cumulative_forward_cap") != 6150 or forwards > receipt["forward_upper"]
            or forwards + receipt["prior_native_forward_started"] > 6150):
        return "cumulative_forward_cap_exceeded"
    for kind in ("actor", "critic"):
        if (receipt.get("cumulative_" + kind + "_backward_cap") != 3072
                or gradient_forwards > receipt[kind + "_backward_upper"]
                or gradient_forwards + receipt["prior_" + kind + "_backward_charged_upper"] > 3072):
            return "cumulative_" + kind + "_backward_cap_exceeded"
    return None


@contextmanager
def training_progress(owner, output):
    path = Path(output) / "training-compute.json"
    with original.training_progress(owner, output):
        metered = owner.learning_logprobs

        def guarded(*args, **kwargs):
            reason = training_stop_reason(read_json(path))
            if reason:
                raise RuntimeError(reason)
            return metered(*args, **kwargs)

        owner.learning_logprobs = guarded
        try:
            yield
        finally:
            owner.learning_logprobs = metered


def _load_original_entries(plan, root):
    r2_plan = read_json(Path(plan["parent_run_root"]) / "plan.json")
    first = Path(r2_plan["parent_run_root"]).resolve()
    return previous.load_materialized_entries(read_json(first / "plan.json"), first)


def update(owner, plan, root, worker, output, *, restored_state=None, load_entries=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if worker != WORKER or output != root / WORKER / "actual":
        raise ValueError("Only the unique original Q-minus branch can be recomputed")
    replay = derive_replay_budget(plan["parent_run_root"])
    if replay != plan.get("qminus_compute_replay"):
        raise ValueError("The frozen two-attempt computation, source, or cumulative budget changed")
    for name, expected in replay["inputs"].items():
        if _stream_reference(root / name)["sha256"] != expected["sha256"]:
            raise ValueError("Recomputation requires exact original input bytes: " + name)
    if ((output / "training-compute.json").exists() or (output / "update").exists()
            or (output / "checkpoint").exists()):
        raise FileExistsError("This isolated recomputation may not be replayed again")
    numeric = numeric_path_receipt(plan["parent_source_root"])
    write(output / "recompute-binding.json", {"version": VERSION, "budget": replay,
        "numeric_path": numeric, "scientific_branch": "Q_minus", "partial_state_reused": False})
    adapter = previous.private_adapter(original._update, import_modules={
        "proworksim.software_learning_v050": "proworksim.software_learning_v050r1"}, dependencies={
        "_restored_state": restored_state or original._restored_state,
        "load_materialized_entries": load_entries or _load_original_entries,
        "training_compute_receipt": lambda admission: training_compute_receipt(admission, replay=replay),
        "training_progress": training_progress})
    try:
        result = adapter(owner, plan, root, worker, output)
        compute = read_json(output / "training-compute.json")
        reason = training_stop_reason(compute, now=compute["ended_at"])
        if reason:
            raise RuntimeError(reason)
        return {**result, "recompute_binding": reference(output / "recompute-binding.json")}
    finally:
        path = output / "training-compute.json"
        if path.exists():
            compute = read_json(path)
            report_path = output / "update/report.json"
            report = read_json(report_path) if report_path.exists() else {}
            lower = report.get("backward_decisions_completed", 0)
            complete = report.get("stage") == "complete"
            conservative = lower if complete else max(lower, compute.get("native_gradient_forward_started", 0))
            observed_at = time.time()
            end = compute.get("ended_at") or observed_at
            total = replay["prior_elapsed_seconds_upper"] + end - compute["started_at"]
            write(output / "recompute-accounting.json", {
                "version": VERSION, "scientific_branch": "Q_minus", "prior_budget_sha256": replay["sha256"],
                "new_compute": reference(path), "observed_at": observed_at,
                "cumulative_elapsed_seconds_upper": total, "original_branch_seconds_cap": 172800,
                "original_branch_48h_enforced": False, "time_policy": TIME_POLICY,
                "aggregate_with_full_Qplus_reservation_seconds_upper": replay["aggregate_fixed_other_seconds"] + total,
                "aggregate_compute_seconds_cap": 518400,
                "cumulative_native_forward_started": replay["prior_native_forward_started"] + compute.get("native_forward_started", 0),
                "cumulative_native_forward_completed": replay["prior_native_forward_completed"] + compute.get("native_forward_completed", 0),
                "cumulative_actor_backward_completed_lower": replay["prior_actor_backward_completed_lower"] + lower,
                "cumulative_critic_backward_completed_lower": replay["prior_critic_backward_completed_lower"] + lower,
                "cumulative_actor_backward_charged_upper": replay["prior_actor_backward_charged_upper"] + conservative,
                "cumulative_critic_backward_charged_upper": replay["prior_critic_backward_charged_upper"] + conservative,
                "cumulative_actor_optimizer_steps": report.get("actor_optimizer_steps", 0),
                "cumulative_critic_optimizer_steps": report.get("critic_optimizer_steps", 0),
                "new_partial_row_backward_exact": complete, "prior_partial_row_backward_exact": False,
                "old_cost_counted_once": True, "old_record_changed": False,
                "new_report": reference(report_path) if report_path.exists() else None})
