"""Replay the sole interrupted Q-minus from the same S*, within its old caps.

Only host provenance and cumulative accounting change. The original v050r1
learner still validates every source and executes the unchanged numerical H1
function. Interrupted gradients are never restored or credited as completed.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
from pathlib import Path
import time

from proworksim.storage import digest, read_json
from scripts import software_learning_resume_v050r1 as previous
from scripts import software_learning_v050 as original
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-Qminus-recompute-v0.50-r2"
SOURCE = Path(__file__).resolve().parents[1]
WORKER = "update-Q_minus"
COPIED_INPUTS = ("entries.json", "source-registry.json", "pretraining-admission.json",
    "support-before-training.json", "support.json", "support-gate.json", "direction.json",
    "declaration.json", "s_star.json", "precollection-binding.json")
NUMERIC_SOURCES = ("src/proworksim/online_training.py", "src/proworksim/software_learning_v049.py",
    "src/proworksim/software_learning_v049r1.py", "src/proworksim/software_learning_v050.py",
    "src/proworksim/software_learning_v050r1.py", "src/proworksim/software_member_views_v050.py",
    "scripts/software_learning_v050.py", "scripts/software_learning_resume_v050r1.py")


def derive_replay_budget(parent_run_root):
    """Bind terminal JSON evidence; inspect tensor filenames without loading them."""
    root = Path(parent_run_root).resolve()
    plan = original.check_seal(read_json(root / "plan.json"), "plan_sha256")
    output = root / WORKER / "actual"
    compute = read_json(output / "training-compute.json")
    report = read_json(output / "update/report.json")
    stop = read_json(root / "mechanism-stops" / (WORKER + "-supervisor.json"))
    state = stop.get("worker_state", {})
    admission = read_json(root / "pretraining-admission.json")
    rows = admission.get("decisions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("The stopped branch must retain its original admitted rows")
    count = len(rows)
    completed = report.get("backward_decisions_completed")
    started = compute.get("native_gradient_forward_started")
    if (plan.get("version") != previous.VERSION or plan.get("limits") != original.LIMITS
            or stop.get("worker") != WORKER or stop.get("reason") != "shared_device_free_memory_reserve"
            or stop.get("kind") != "execution_fault" or state.get("worker") != WORKER
            or state.get("status") != "stopped" or state.get("attempted") is not True
            or state.get("exit_code") != -9 or stop.get("observed_at") != state.get("ended_at")
            or compute.get("ended_at") is not None or compute.get("maximum_seconds") != original.LIMITS["update_worker_seconds"]
            or compute.get("admitted_rows") != count or report.get("admitted_decisions") != count
            or compute.get("forward_upper") != 2 * count + 6
            or any(compute.get(key) != count for key in ("actor_backward_upper", "critic_backward_upper"))
            or any(compute.get(key) != 1 for key in ("actor_steps_upper", "critic_steps_upper"))
            or report.get("stage") != "backward" or report.get("status") != "preparing"
            or report.get("training_happened") is not False or report.get("actor_update_enabled") is not True
            or report.get("behavior_probability_passed") is not True
            or any(report.get(key) != 0 for key in ("actor_optimizer_steps", "critic_optimizer_steps"))
            or type(completed) is not int or type(started) is not int or not 0 <= completed < count
            or started != completed + 1 or compute.get("native_no_grad_forward_started") != count
            or compute.get("native_forward_started") != count + started
            or compute.get("native_forward_completed") != compute.get("native_forward_started")):
        raise ValueError("Only the bound pre-optimizer Q-minus interruption may be recomputed")
    tensor_files = sorted(str(p.relative_to(output)) for p in output.rglob("*")
        if p.is_file() and p.suffix in {".pt", ".pth", ".safetensors"})
    if tensor_files != ["update/shared-before.pt"] or (output / "checkpoint").exists():
        raise ValueError("Unexpected checkpoint/gradient evidence needs a new disposition")
    loaded = read_json(output / "loaded-state.json")
    expected = read_json(original.checked(plan["s_star_checkpoint"]))
    if (loaded.get("branch") != "S_star" or loaded.get("checkpoint") != plan["s_star_checkpoint"]
            or loaded.get("restored") != expected or loaded.get("actor_identity") != expected.get("actor_identity")
            or (loaded.get("actor_steps"), loaded.get("critic_steps")) != (4, 4)
            or (expected.get("actor_steps"), expected.get("critic_steps")) != (4, 4)
            or report.get("before_actor_identity") != expected.get("actor_identity")
            or report.get("recipe") != plan.get("s_star_recipe")):
        raise ValueError("The interrupted attempt must have restored the unchanged complete S*4/4")
    prior_seconds = state["ended_at"] - compute["started_at"]
    remaining = original.LIMITS["update_worker_seconds"] - prior_seconds
    if not math.isfinite(prior_seconds) or not 0 < prior_seconds < original.LIMITS["update_worker_seconds"]:
        raise ValueError("No branch interval remains inside the original 48-hour cap")
    upper = {"forward": compute["native_forward_started"] + 2 * count + 6,
        "actor_backward": started + count, "critic_backward": started + count}
    if (upper["forward"] > original.LIMITS["max_forward_calls_per_update"]
            or upper["actor_backward"] > original.LIMITS["max_actor_backward_calls_per_update"]
            or upper["critic_backward"] > original.LIMITS["max_critic_backward_calls_per_update"]):
        raise ValueError("Old and recomputed work together exceed an original branch cap")
    refs = {name: reference(root / name) for name in COPIED_INPUTS}
    evidence = {name: reference(output / name) for name in ("training-compute.json", "update/report.json",
        "loaded-state.json", "composition-before-update.json", "update/composition.json",
        "update-v050-learning-binding.json", "update-original-updater-binding.json")}
    return original.seal({"version": VERSION, "worker": WORKER, "parent_run_root": str(root),
        "parent_plan": reference(root / "plan.json"), "inputs": refs, "prior_evidence": evidence,
        "prior_stop": reference(root / "mechanism-stops" / (WORKER + "-supervisor.json")),
        "prior_training_started_at": compute["started_at"], "prior_training_ended_at_upper": state["ended_at"],
        "prior_elapsed_seconds_upper": prior_seconds, "remaining_seconds": remaining,
        "original_branch_seconds_cap": original.LIMITS["update_worker_seconds"],
        "admitted_rows_per_attempt": count, "prior_native_forward_started": compute["native_forward_started"],
        "prior_native_forward_completed": compute["native_forward_completed"],
        "prior_actor_backward_completed_lower": completed, "prior_critic_backward_completed_lower": completed,
        "prior_actor_backward_charged_upper": started, "prior_critic_backward_charged_upper": started,
        "prior_partial_row_backward_exact": False, "prior_actor_optimizer_steps": 0, "prior_critic_optimizer_steps": 0,
        "new_forward_upper": 2 * count + 6, "new_actor_backward_upper": count, "new_critic_backward_upper": count,
        "cumulative_upper": upper, "tensor_filenames_inspected_only": tensor_files,
        "restart_from_complete_S_star": True, "resume_partial_gradients_or_RNG": False,
        "new_direction_or_material": False, "same_single_scientific_Qminus_branch": True,
        "prior_cost_counted_once": True})


def numeric_path_receipt(parent_source_root):
    """CPU-only byte/code-object guard, without importing torch or tensor loading."""
    from proworksim import online_training, software_learning_v050, software_learning_v050r1
    parent = Path(parent_source_root).resolve()
    compared = {}
    for name in NUMERIC_SOURCES:
        old, new = parent / name, SOURCE / name
        if old.read_bytes() != new.read_bytes():
            raise ValueError("The original H1 numerical or provenance source changed: " + name)
        compared[name] = digest(new.read_bytes())
    if (software_learning_v050._numeric_update.__code__ is not online_training.SharedActor.update_window.__code__
            or software_learning_v050.prepare_window.__code__ is not online_training.prepare_window.__code__
            or software_learning_v050r1.update_window is not software_learning_v050.update_window):
        raise ValueError("The replay must execute the original H1 function and preparation code objects")
    return {"version": VERSION, "source_files_identical": compared,
        "original_H1_code_object_identical": True, "original_prepare_code_object_identical": True,
        "original_r1_update_window_identical": True, "critic_reweighted": False,
        "numerical_recipe_changed": False, "tensor_files_loaded": 0, "model_calls": 0}


def training_compute_receipt(admission, *, replay, started_at=None):
    original.check_seal(replay)
    if admission != read_json(original.checked(replay["inputs"]["pretraining-admission.json"])):
        raise ValueError("Recomputation cannot replace, omit or reorder the admitted rows")
    receipt = original.training_compute_receipt(admission, started_at=started_at)
    receipt.update(maximum_seconds=replay["remaining_seconds"], replay_version=VERSION,
        replay_budget_sha256=replay["sha256"], prior_elapsed_seconds_upper=replay["prior_elapsed_seconds_upper"],
        original_branch_seconds_cap=replay["original_branch_seconds_cap"],
        prior_native_forward_started=replay["prior_native_forward_started"],
        prior_actor_backward_charged_upper=replay["prior_actor_backward_charged_upper"],
        prior_critic_backward_charged_upper=replay["prior_critic_backward_charged_upper"],
        cumulative_forward_cap=original.LIMITS["max_forward_calls_per_update"],
        cumulative_actor_backward_cap=original.LIMITS["max_actor_backward_calls_per_update"],
        cumulative_critic_backward_cap=original.LIMITS["max_critic_backward_calls_per_update"],
        old_cost_counted_once=True, restart_from_S_star=True)
    if (receipt["forward_upper"] + receipt["prior_native_forward_started"] > receipt["cumulative_forward_cap"]
            or receipt["actor_backward_upper"] + receipt["prior_actor_backward_charged_upper"] > receipt["cumulative_actor_backward_cap"]
            or receipt["critic_backward_upper"] + receipt["prior_critic_backward_charged_upper"] > receipt["cumulative_critic_backward_cap"]):
        raise ValueError("Cumulative branch budget cannot admit a full same-material recomputation")
    return receipt


def training_stop_reason(receipt, now=None):
    """Host guard for the remaining interval and old-plus-new call accounting."""
    now = time.time() if now is None else now
    if receipt.get("replay_version") != VERSION:
        return "replay_compute_receipt_identity"
    maximum = receipt["maximum_seconds"]
    if (not math.isfinite(maximum) or maximum <= 0
            or receipt["prior_elapsed_seconds_upper"] + maximum != receipt["original_branch_seconds_cap"]):
        return "replay_compute_interval_changed"
    if now - receipt["started_at"] >= maximum:
        return "cumulative_update_interval_exhausted"
    forwards = receipt.get("native_forward_started", 0)
    gradient_forwards = receipt.get("native_gradient_forward_started", 0)
    if (forwards > receipt["forward_upper"]
            or forwards + receipt["prior_native_forward_started"] > receipt["cumulative_forward_cap"]):
        return "cumulative_forward_cap_exceeded"
    for kind in ("actor", "critic"):
        if (gradient_forwards > receipt[kind + "_backward_upper"]
                or gradient_forwards + receipt["prior_" + kind + "_backward_charged_upper"]
                > receipt["cumulative_" + kind + "_backward_cap"]):
            return "cumulative_" + kind + "_backward_cap_exceeded"
    return None


@contextmanager
def training_progress(owner, output):
    """Add only an administrative guard around the unchanged forward meter."""
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
    parent = Path(plan["parent_run_root"]).resolve()
    return previous.load_materialized_entries(read_json(parent / "plan.json"), parent)


def update(owner, plan, root, worker, output, *, restored_state=None, load_entries=None):
    """Private host adapter; restore S* and repeat all original rows exactly once."""
    root, output = Path(root).resolve(), Path(output).resolve()
    if worker != WORKER or output != root / WORKER / "actual":
        raise ValueError("Only the unique original Q-minus branch can be recomputed")
    replay = derive_replay_budget(plan["parent_run_root"])
    if replay != plan.get("qminus_compute_replay"):
        raise ValueError("The frozen old computation, source inputs or cumulative budget changed")
    for name, ref in replay["inputs"].items():
        if (root / name).read_bytes() != original.checked(ref).read_bytes():
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
            write(output / "recompute-accounting.json", {
                "version": VERSION, "scientific_branch": "Q_minus", "prior_budget_sha256": replay["sha256"],
                "new_compute": reference(path), "observed_at": observed_at,
                "cumulative_elapsed_seconds_upper": replay["prior_elapsed_seconds_upper"] + (end - compute["started_at"]),
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
