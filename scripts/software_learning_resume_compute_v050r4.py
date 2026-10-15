"""Two complete Q recomputations within the original aggregate 144-hour cap.

All interrupted attempts are charged once. No gradients, RNG, or partial state
are restored; only the original complete S_star and frozen H1 are used.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts import software_learning_resume_compute_v050r3 as prior
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-Q-recompute-v0.50-r4"
PARENT_VERSION = "software-learning-original-Q-continuation-v0.50-r3"
TIME_POLICY = "B-actual-plus-all-old-Q-intervals-then-equal-two-Q-within-total144h"
SOURCE = Path(__file__).resolve().parents[1]
BRANCHES = ("Q_plus", "Q_minus")
COPIED_INPUTS = prior.COPIED_INPUTS
NUMERIC_SOURCES = prior.NUMERIC_SOURCES
original, previous = prior.original, prior.previous
_stream_reference, _bound_reference = prior._stream_reference, prior._bound_reference
numeric_path_receipt = prior.numeric_path_receipt


def _plus_attempt(root, plan):
    worker = "update-Q_plus"
    output = root / worker / "actual"
    compute = read_json(output / "training-compute.json")
    report = read_json(output / "update/report.json")
    outer = read_json(output / "report.json")
    task = read_json(output / "task.json")
    stop_path = root / "mechanism-stops" / (worker + "-supervisor.json")
    execution_path = root / "mechanism-stops" / (worker + "-execution.json")
    host_path = root / "host-stop-actions" / (worker + ".json")
    stop, execution, host = map(read_json, (stop_path, execution_path, host_path))
    state = stop.get("worker_state", {})
    rows, gradient = compute.get("admitted_rows"), compute.get("native_gradient_forward_started")
    completed = report.get("backward_decisions_completed")
    if (type(rows) is not int or not 0 < rows <= 3072 or report.get("admitted_decisions") != rows
            or type(gradient) is not int or type(completed) is not int or not 0 <= completed < rows
            or gradient != completed + 1 or compute.get("native_no_grad_forward_started") != rows
            or compute.get("native_forward_started") != rows + gradient
            or compute.get("native_forward_completed") != rows + gradient - 1
            or compute.get("maximum_seconds") != 172800 or compute.get("ended_at") is not None
            or compute.get("forward_upper") != 2 * rows + 6
            or any(compute.get(k) != rows for k in ("actor_backward_upper", "critic_backward_upper"))
            or any(compute.get(k) != 1 for k in ("actor_steps_upper", "critic_steps_upper"))
            or report.get("status") != "interrupted" or report.get("stage") != "backward"
            or report.get("training_happened") is not False or report.get("actor_update_enabled") is not True
            or report.get("behavior_probability_passed") is not True
            or any(report.get(k) != 0 for k in ("actor_optimizer_steps", "critic_optimizer_steps"))):
        raise ValueError("Q-plus must bind its interrupted, unfinished gradient forward before any optimizer")
    error = {"type": "KeyboardInterrupt", "message": "signal 15"}
    if (stop.get("worker") != worker or stop.get("kind") != "execution_fault"
            or stop.get("reason") != "shared_device_free_memory_reserve"
            or state.get("worker") != worker or state.get("status") != "stopped"
            or state.get("attempted") is not True or state.get("exit_code") != -2
            or stop.get("observed_at") != state.get("ended_at")
            or host.get("worker") != worker or host.get("reason") != stop["reason"]
            or host.get("process_returncode") != -2 or host.get("pid") != state.get("pid")
            or host.get("process_identity") != state.get("process_identity")
            or task.get("pid") != state.get("pid")
            or task.get("task") != f"learning-forward-{rows + gradient:06d}"
            or execution.get("worker") != worker or execution.get("kind") != "execution_fault"
            or execution.get("error") != error or report.get("interruption") != error
            or outer.get("worker") != worker or outer.get("status") != "execution_error"
            or outer.get("error") != error or outer.get("success_boundary") is not False
            or any(outer.get(k) != 0 for k in ("new_actor_steps", "new_critic_steps"))
            or not host.get("requested_at", math.inf) <= execution.get("observed_at", -1)
            <= host.get("stop_procedure_returned_at", -1) <= state["ended_at"]):
        raise ValueError("Q-plus signal and host termination must be fully bound")
    _bound_reference(host_path, state["host_stop_action"])
    supervisor = read_json(root / "supervisor.json")
    if (supervisor.get("observer_pid") != host.get("host_pid")
            or supervisor.get("states", {}).get(worker) != state
            or supervisor.get("status") != "closed_with_unknowns"):
        raise ValueError("Q-plus termination must name its actual original supervisor")
    elapsed = state["ended_at"] - compute["started_at"]
    if not math.isfinite(elapsed) or not 0 < elapsed < 172800:
        raise ValueError("Q-plus prior interval must be within its original authorization")
    tensors = sorted(str(p.relative_to(output)) for p in output.rglob("*")
        if p.is_file() and p.suffix in {".pt", ".pth", ".bin", ".safetensors"})
    if tensors != ["update/shared-before.pt"] or any(output.rglob("*checkpoint*")):
        raise ValueError("Q-plus checkpoint or accumulated gradients require separate disposition")
    loaded = read_json(output / "loaded-state.json")
    expected = read_json(original.checked(plan["s_star_checkpoint"]))
    if (loaded.get("branch") != "S_star" or loaded.get("checkpoint") != plan["s_star_checkpoint"]
            or loaded.get("restored") != expected or loaded.get("actor_identity") != expected.get("actor_identity")
            or (loaded.get("actor_steps"), loaded.get("critic_steps")) != (4, 4)
            or (expected.get("actor_steps"), expected.get("critic_steps")) != (4, 4)
            or (outer.get("actor_steps"), outer.get("critic_steps")) != (4, 4)
            or report.get("before_actor_identity") != expected.get("actor_identity")
            or report.get("after_actor_identity") != expected.get("actor_identity")
            or report.get("recipe") != plan.get("s_star_recipe")):
        raise ValueError("Q-plus must preserve the same complete S_star 4/4 and recipe")
    binding = read_json(output / "update-original-updater-binding.json")
    if (binding.get("original_source", {}).get("sha256") != plan["source_files"]["src/proworksim/online_training.py"]
            or binding.get("code_object_identical") is not True):
        raise ValueError("Q-plus must retain the original H1 numerical function")
    evidence = {name: reference(output / name) for name in ("training-compute.json", "update/report.json",
        "report.json", "task.json", "loaded-state.json", "composition-before-update.json", "update/composition.json",
        "update-v050-learning-binding.json", "update-original-updater-binding.json")}
    return {"root": str(root), "training_started_at": compute["started_at"],
        "training_ended_at_upper": state["ended_at"], "elapsed_seconds_upper": elapsed,
        "native_forward_started": rows + gradient, "native_forward_completed": rows + gradient - 1,
        "backward_completed_lower": completed, "backward_charged_upper": gradient,
        "actor_optimizer_steps": 0, "critic_optimizer_steps": 0, "admitted_rows": rows,
        "partial_row_backward_exact": False, "tensor_filenames_inspected_only": tensors,
        "evidence": evidence, "stop": reference(stop_path), "host_stop": reference(host_path),
        "execution_stop": reference(execution_path)}


def derive_replay_budget(parent_run_root):
    """Read the terminal r3/r2/r1 chain once and freeze both branch allocations."""
    root = Path(parent_run_root).resolve()
    plan = original.check_seal(read_json(root / "plan.json"), "plan_sha256")
    parent = Path(plan["parent_run_root"]).resolve()
    minus = prior.derive_replay_budget(parent)
    if (plan.get("version") != PARENT_VERSION or plan.get("qminus_compute_replay") != minus
            or plan.get("s_star_checkpoint") != read_json(parent / "plan.json").get("s_star_checkpoint")):
        raise ValueError("The r3 plan must retain the frozen, unconsumed Q-minus allocation")
    _bound_reference(parent / "plan.json", plan["parent_plan"])
    supervisor = read_json(root / "supervisor.json")
    workers = ["update-Q_minus", *(f"dev-{b}-{i}" for b in BRANCHES for i in range(8))]
    if (plan.get("workers") != workers or supervisor.get("status") != "closed_with_unknowns"
            or not supervisor.get("ended_at") or supervisor.get("source") != plan.get("source")
            or set(supervisor.get("states", {})) != set(workers)
            or supervisor.get("closed_worker_gpu_seconds") != 0
            or supervisor.get("running_worker_gpu_seconds") != 0):
        raise ValueError("The r3 host must be terminal with zero new GPU-worker cost")
    for worker, state in supervisor["states"].items():
        if (state.get("worker") != worker or state.get("attempted") is not False
                or state.get("status") != "stopped" or state.get("stop_reason") != "unopened_work_paused"
                or state.get("elapsed_gpu_seconds") != 0 or (root / worker).exists()):
            raise ValueError("No r3 worker may have started or consumed the old reservation")
    first = Path(minus["original_run_root"])
    first_plan = original.check_seal(read_json(first / "plan.json"), "plan_sha256")
    plus = _plus_attempt(first, first_plan)
    if plus["admitted_rows"] != minus["admitted_rows_per_attempt"]:
        raise ValueError("Both branches must use every identical original admitted row")
    inputs = {}
    for name, expected in minus["inputs"].items():
        actual = _stream_reference(root / name)
        if actual["sha256"] != expected["sha256"]:
            raise ValueError("The r3 frozen material changed: " + name)
        inputs[name] = actual
    direction = original.check_seal(read_json(root / "direction.json"), "seal_sha256")
    core = original.check_seal(direction["direction"], "seal_sha256")
    if direction.get("plus_weights") != core.get("plus_weights_by_slot"):
        raise ValueError("Only the original frozen Q-plus direction may be recomputed")
    compositions = [original.check_seal(read_json(first / "update-Q_plus/actual" / name), "seal_sha256")
        for name in ("composition-before-update.json", "update/composition.json")]
    if (compositions[0] != compositions[1] or compositions[0].get("weights_by_slot") != direction["plus_weights"]
            or compositions[0].get("entries_sha256") != inputs["entries.json"]["sha256"]):
        raise ValueError("No omission, reorder, or reweighting of Q-plus is permitted")
    old = {"Q_plus": plus["elapsed_seconds_upper"], "Q_minus": minus["prior_elapsed_seconds_upper"]}
    b_seconds = minus["B_complete_interval_seconds"]
    spent = b_seconds + old["Q_minus"] + old["Q_plus"]
    exact = 518400 - spent
    remaining = math.floor(exact / 2)
    if remaining <= 0:
        raise ValueError("No aggregate interval remains for two full attempts")
    allocation = original.seal({"version": VERSION, "time_policy": TIME_POLICY,
        "aggregate_compute_seconds_cap": 518400, "B_complete_interval_seconds": b_seconds,
        "prior_Q_seconds_upper": old, "prior_all_compute_seconds_upper": spent,
        "remaining_seconds_exact": exact, "branch_seconds": {b: remaining for b in BRANCHES},
        "aggregate_seconds_upper": spent + 2 * remaining, "unallocated_seconds": exact - 2 * remaining,
        "original_branch_48h_enforced": False, "r3_unstarted_reserved_seconds_charged": 0,
        "parent_run_root": str(root), "parent_plan": reference(root / "plan.json"),
        "parent_supervisor": reference(root / "supervisor.json"), "original_run_root": str(first),
        "B_compute": minus["B_compute"], "B_report": minus["B_report"],
        "Q_minus_prior_budget": minus, "Q_plus_prior_attempt": plus,
        "prior_cost_counted_once": True})
    branches = {}
    for branch in BRANCHES:
        attempts = [plus] if branch == "Q_plus" else minus["prior_attempts"]
        count = plus["admitted_rows"]
        forwards = sum(a["native_forward_started"] for a in attempts)
        completed = sum(a["native_forward_completed"] for a in attempts)
        lower = sum(a["backward_completed_lower"] for a in attempts)
        upper = sum(a["backward_charged_upper"] for a in attempts)
        cumulative = {"forward": forwards + 2 * count + 6, "actor_backward": upper + count,
            "critic_backward": upper + count}
        if cumulative["forward"] > 6150 or max(cumulative["actor_backward"], cumulative["critic_backward"]) > 3072:
            raise ValueError("Old and new branch work exceed the original count cap")
        branches[branch] = original.seal({"version": VERSION, "branch": branch, "worker": "update-" + branch,
            "parent_run_root": str(root), "original_run_root": str(first), "inputs": inputs,
            "global_allocation": allocation, "global_allocation_sha256": allocation["sha256"],
            "prior_attempts": attempts, "prior_elapsed_seconds_upper": old[branch],
            "remaining_seconds": remaining, "original_branch_seconds_cap": 172800,
            "original_branch_remaining_seconds": 172800 - old[branch], "original_branch_48h_enforced": False,
            "admitted_rows_per_attempt": count, "prior_native_forward_started": forwards,
            "prior_native_forward_completed": completed, "prior_actor_backward_completed_lower": lower,
            "prior_critic_backward_completed_lower": lower, "prior_actor_backward_charged_upper": upper,
            "prior_critic_backward_charged_upper": upper, "prior_actor_optimizer_steps": 0,
            "prior_critic_optimizer_steps": 0, "new_forward_upper": 2 * count + 6,
            "new_actor_backward_upper": count, "new_critic_backward_upper": count,
            "cumulative_upper": cumulative, "restart_from_complete_S_star": True,
            "resume_partial_gradients_or_RNG": False, "new_direction_or_material": False,
            "prior_cost_counted_once": True, "numeric_path": minus["numeric_path"]})
    return original.seal({"version": VERSION, "allocation": allocation, "branches": branches})


def training_compute_receipt(admission, *, replay, started_at=None):
    original.check_seal(replay)
    allocation = original.check_seal(replay["global_allocation"])
    branch = replay.get("branch")
    if (replay.get("version") != VERSION or branch not in BRANCHES
            or replay.get("worker") != "update-" + branch
            or allocation["sha256"] != replay.get("global_allocation_sha256")
            or admission != read_json(original.checked(replay["inputs"]["pretraining-admission.json"]))):
        raise ValueError("Cannot change, omit, or reorder original branch admission")
    receipt = original.training_compute_receipt(admission, started_at=started_at)
    receipt.update(maximum_seconds=replay["remaining_seconds"], replay_version=VERSION,
        replay_budget_sha256=replay["sha256"], branch=branch, time_policy=TIME_POLICY,
        global_allocation_sha256=allocation["sha256"], prior_Q_seconds_upper=allocation["prior_Q_seconds_upper"],
        prior_elapsed_seconds_upper=replay["prior_elapsed_seconds_upper"],
        B_complete_interval_seconds=allocation["B_complete_interval_seconds"],
        aggregate_compute_seconds_cap=518400, original_branch_seconds_cap=172800,
        original_branch_remaining_seconds=replay["original_branch_remaining_seconds"], original_branch_48h_enforced=False,
        prior_native_forward_started=replay["prior_native_forward_started"],
        prior_actor_backward_charged_upper=replay["prior_actor_backward_charged_upper"],
        prior_critic_backward_charged_upper=replay["prior_critic_backward_charged_upper"],
        cumulative_forward_cap=6150, cumulative_actor_backward_cap=3072, cumulative_critic_backward_cap=3072,
        old_cost_counted_once=True, restart_from_S_star=True)
    if (receipt["forward_upper"] + receipt["prior_native_forward_started"] > 6150
            or receipt["actor_backward_upper"] + receipt["prior_actor_backward_charged_upper"] > 3072
            or receipt["critic_backward_upper"] + receipt["prior_critic_backward_charged_upper"] > 3072):
        raise ValueError("Cumulative branch counts cannot admit the full recomputation")
    reason = training_stop_reason(receipt, now=receipt["started_at"])
    if reason:
        raise ValueError(reason)
    return receipt


def training_stop_reason(receipt, now=None):
    if receipt.get("replay_version") != VERSION or receipt.get("branch") not in BRANCHES:
        return "replay_compute_receipt_identity"
    maximum = receipt.get("maximum_seconds")
    old = receipt.get("prior_Q_seconds_upper", {})
    b_seconds = receipt.get("B_complete_interval_seconds", math.nan)
    if (set(old) != set(BRANCHES) or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in old.values())
            or type(b_seconds) not in (int, float) or not math.isfinite(b_seconds) or not 0 < b_seconds <= 172800
            or type(maximum) is not int or maximum <= 0
            or maximum != math.floor((518400 - b_seconds - old["Q_minus"] - old["Q_plus"]) / 2)
            or receipt.get("time_policy") != TIME_POLICY or receipt.get("original_branch_48h_enforced") is not False
            or receipt.get("original_branch_seconds_cap") != 172800
            or receipt.get("prior_elapsed_seconds_upper") != old[receipt["branch"]]
            or receipt.get("original_branch_remaining_seconds") != 172800 - old[receipt["branch"]]
            or receipt.get("aggregate_compute_seconds_cap") != 518400):
        return "replay_compute_interval_changed"
    if (time.time() if now is None else now) - receipt["started_at"] >= maximum:
        return "cumulative_update_interval_exhausted"
    forwards, gradients = receipt.get("native_forward_started", 0), receipt.get("native_gradient_forward_started", 0)
    if (receipt.get("cumulative_forward_cap") != 6150 or forwards > receipt["forward_upper"]
            or forwards + receipt["prior_native_forward_started"] > 6150):
        return "cumulative_forward_cap_exceeded"
    for kind in ("actor", "critic"):
        if (receipt.get("cumulative_" + kind + "_backward_cap") != 3072
                or gradients > receipt[kind + "_backward_upper"]
                or gradients + receipt["prior_" + kind + "_backward_charged_upper"] > 3072):
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
    first = Path(plan["q_compute_replay"]["allocation"]["original_run_root"])
    return previous.load_materialized_entries(read_json(first / "plan.json"), first)


def update(owner, plan, root, worker, output, *, restored_state=None, load_entries=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    branch = worker.removeprefix("update-")
    if branch not in BRANCHES or worker != "update-" + branch or output != root / worker / "actual":
        raise ValueError("Only the two original Q branches can be recomputed")
    global_budget = original.check_seal(plan["q_compute_replay"])
    replay = original.check_seal(global_budget["branches"][branch])
    if global_budget.get("version") != VERSION or replay.get("global_allocation") != global_budget["allocation"]:
        raise ValueError("The frozen shared computation allocation changed")
    for name, expected in replay["inputs"].items():
        if _stream_reference(root / name)["sha256"] != expected["sha256"]:
            raise ValueError("Recomputation requires exact original input bytes: " + name)
    if ((output / "training-compute.json").exists() or (output / "update").exists() or (output / "checkpoint").exists()):
        raise FileExistsError("This isolated recomputation may not be replayed again")
    numeric = numeric_path_receipt(plan["parent_source_root"])
    write(output / "recompute-binding.json", {"version": VERSION, "budget": replay,
        "numeric_path": numeric, "scientific_branch": branch, "partial_state_reused": False})
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
            upper = lower if complete else max(lower, compute.get("native_gradient_forward_started", 0))
            observed = time.time()
            new_seconds = (compute.get("ended_at") or observed) - compute["started_at"]
            allocation = global_budget["allocation"]
            other = next(b for b in BRANCHES if b != branch)
            write(output / "recompute-accounting.json", {"version": VERSION, "scientific_branch": branch,
                "prior_budget_sha256": replay["sha256"], "global_allocation_sha256": allocation["sha256"],
                "new_compute": reference(path), "observed_at": observed,
                "cumulative_elapsed_seconds_upper": replay["prior_elapsed_seconds_upper"] + new_seconds,
                "original_branch_48h_enforced": False, "time_policy": TIME_POLICY,
                "aggregate_with_other_new_reservation_seconds_upper": allocation["prior_all_compute_seconds_upper"]
                    + allocation["branch_seconds"][other] + new_seconds,
                "aggregate_compute_seconds_cap": 518400,
                "cumulative_native_forward_started": replay["prior_native_forward_started"] + compute.get("native_forward_started", 0),
                "cumulative_native_forward_completed": replay["prior_native_forward_completed"] + compute.get("native_forward_completed", 0),
                "cumulative_actor_backward_completed_lower": replay["prior_actor_backward_completed_lower"] + lower,
                "cumulative_critic_backward_completed_lower": replay["prior_critic_backward_completed_lower"] + lower,
                "cumulative_actor_backward_charged_upper": replay["prior_actor_backward_charged_upper"] + upper,
                "cumulative_critic_backward_charged_upper": replay["prior_critic_backward_charged_upper"] + upper,
                "cumulative_actor_optimizer_steps": report.get("actor_optimizer_steps", 0),
                "cumulative_critic_optimizer_steps": report.get("critic_optimizer_steps", 0),
                "new_partial_row_backward_exact": complete, "prior_partial_row_backward_exact": False,
                "old_cost_counted_once": True, "old_record_changed": False,
                "new_report": reference(report_path) if report_path.exists() else None})
