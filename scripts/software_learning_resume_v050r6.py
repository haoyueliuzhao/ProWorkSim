"""Route only sixteen original developments under a shared four-resident cap.

Both Q updates retain their original hosts, processes, source and compute clocks.
This adapter has no update worker and admits their exact complete checkpoints only.
"""
from __future__ import annotations

import argparse
import copy
import math
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, read_json
from scripts import software_learning_resume_v050r5 as prior
from scripts.software_learning_development_resume_v049r2g import bind
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.software_development_v028 import task
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-original-development-continuation-v0.50-r6"
MODULE = "scripts.software_learning_resume_v050r6"
SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r6-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r6-cpu-controls.json"
original = prior.original
resource, startup_resource = prior.resource, prior.startup_resource
GPU_ORDER = GPU_PREFERENCE = prior.GPU_ORDER
LIMITS = {**copy.deepcopy(prior.LIMITS), "max_parallel_model_instances": 4}
UPDATES = ()
DEVELOPMENT = WORKERS = prior.DEVELOPMENT
BRANCHES = ("Q_plus", "Q_minus")
MATERIAL_FILES = prior.MATERIAL_FILES
RETRY_POLICY = copy.deepcopy(prior.RETRY_POLICY)
SCIENTIFIC_KEYS = prior.SCIENTIFIC_KEYS
HANDOFF_FILE = "mechanism-stops/administrative-concurrency-r6.json"
HANDOFF_VERSION = "software-learning-v050-administrative-concurrency-handoff-r6"
checked, seal, check_seal = prior.checked, prior.seal, prior.check_seal
generation_caps = prior.generation_caps


def source_files():
    files = prior.source_files()
    for path in (PROTOCOL, CONTROLS, Path(__file__),
            SOURCE / "scripts/software_learning_resume_supervisor_v050r6.py",
            SOURCE / "tests/test_software_learning_resume_v050r6.py",
            SOURCE / "tests/test_software_learning_resume_supervisor_v050r6.py"):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def original_worker(worker):
    if worker not in WORKERS:
        raise ValueError("Only the sixteen original development workers are owned")
    return prior.original_worker(worker)


def worker_units(plan, worker):
    original_worker(worker)
    return prior.worker_units(plan, worker)


def scheduling_inventory(plan):
    return {name: {"original_worker": original_worker(name), "units": worker_units(plan, name)}
        for name in DEVELOPMENT}


def external_identity(branch, state, source):
    expected = {"worker": "update-" + branch, "pid": state.get("pid"),
        "start_ticks": state.get("process_identity", {}).get("start_ticks"),
        "gpu": state.get("gpu"), "gpu_uuid": state.get("gpu_uuid"),
        "started_at": state.get("started_at"), "source": copy.deepcopy(source)}
    if (branch not in BRANCHES or state.get("worker") != expected["worker"]
            or state.get("attempted") is not True or type(expected["pid"]) is not int
            or type(expected["start_ticks"]) is not int or expected["gpu"] not in GPU_ORDER
            or not isinstance(expected["gpu_uuid"], str)
            or type(expected["started_at"]) not in (int, float)):
        raise ValueError("Bind only the original external update process and physical GPU")
    return expected


def _handoff(root, parent, supervisor):
    path = Path(root) / HANDOFF_FILE
    receipt = read_json(path)
    if (receipt.get("version") != HANDOFF_VERSION or receipt.get("kind") != "administrative_handoff"
            or receipt.get("parent_plan") != reference(Path(root) / "plan.json")
            or receipt.get("source") != parent["source"]
            or receipt.get("transferred_workers") != list(DEVELOPMENT)
            or receipt.get("all_transferred_workers_unstarted") is not True
            or receipt.get("resource_attempts_for_transferred_workers") != 0
            or receipt.get("maximum_total_residents") != 4
            or receipt.get("count_external_Q_plus_and_Q_minus") is not True
            or receipt.get("signals_sent") != []
            or receipt.get("active_update_workers_interrupted") is not False
            or receipt.get("old_records_rewritten") is not False
            or any(receipt.get(k) != 0 for k in ("new_scientific_slots", "new_seeds", "new_update_budget"))):
        raise ValueError("Require the exact zero-work administrative development handoff")
    states = supervisor.get("states", {})
    if (set(states) != set(prior.WORKERS) or supervisor.get("source") != parent["source"]
            or supervisor.get("status") not in {"running", "closed_with_unknowns"}):
        raise ValueError("The original r5 supervisor must retain its own Q-minus")
    for name in DEVELOPMENT:
        state = states[name]
        if (state.get("worker") != name or state.get("status") != "stopped"
                or state.get("attempted") is not False or state.get("model_started") is not False
                or state.get("stop_reason") != "unopened_work_paused"
                or state.get("resource_attempt_number") != 0 or state.get("elapsed_gpu_seconds") != 0
                or (Path(root) / name).exists()):
            raise ValueError("Every transferred development must remain completely unstarted: " + name)
    if sorted(Path(root).joinpath("mechanism-stops").glob("*.json")) != [path]:
        raise ValueError("A genuine r5 mechanism fault cannot be hidden by an administrative handoff")
    return reference(path)


def derive_inventory(parent_root, *, source_root=SOURCE, check_source=True, identity_fn=worker_identity):
    root = Path(parent_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (parent.get("version") != prior.VERSION or parent.get("workers") != list(prior.WORKERS)
            or parent.get("limits") != prior.LIMITS or parent.get("automatic_retries") is not False
            or parent.get("automatic_verified_resource_retries") is not True):
        raise ValueError("Require the exact r5 parent without changing its active update")
    supervisor = read_json(root / "supervisor.json")
    handoff = _handoff(root, parent, supervisor)
    minus = external_identity("Q_minus", supervisor["states"]["update-Q_minus"], parent["source"])
    if supervisor["states"]["update-Q_minus"].get("status") not in {"running", "complete"}:
        raise ValueError("The original Q-minus must still be active or complete")
    guardian = identity_fn(supervisor["observer_pid"])
    if supervisor["states"]["update-Q_minus"]["status"] == "running" and (
            guardian.get("alive") is not True or type(guardian.get("start_ticks")) is not int):
        raise ValueError("The running Q-minus must keep its original live r5 guardian")
    plus_parent = check_seal(read_json(checked(parent["parent_plan"])), "plan_sha256")
    updates = {
        "Q_plus": {"identity": copy.deepcopy(parent["external_Q_plus"]),
            "run_root": parent["parent_run_root"], "source_root": plus_parent["source_root"],
            "plan": parent["parent_plan"],
            "supervisor_process": copy.deepcopy(parent["continuation_inventory"]["original_supervisor_process"])},
        "Q_minus": {"identity": minus, "run_root": str(root), "source_root": parent["source_root"],
            "plan": reference(root / "plan.json"),
            "supervisor_process": {"pid": supervisor["observer_pid"], "start_ticks": guardian.get("start_ticks")}}}
    marker = read_json(checked(handoff))
    for branch, field in (("Q_plus", "original_Q_plus"), ("Q_minus", "active_Q_minus")):
        if marker[field] != {k: updates[branch]["identity"][k] for k in ("pid", "start_ticks", "gpu")}:
            raise ValueError("Administrative handoff cannot substitute either live update")
    result = {"version": VERSION, "parent_run_root": str(root),
        "parent_plan": reference(root / "plan.json"), "parent_source": parent["source"],
        "parent_source_root": parent["source_root"], "administrative_handoff": handoff,
        "closed_parent_workers": {n: {"state": copy.deepcopy(supervisor["states"][n])} for n in DEVELOPMENT},
        "external_updates": updates, "B_update": parent["continuation_inventory"]["B_update"],
        "B_checkpoint": parent["continuation_inventory"]["B_checkpoint"],
        "materials": {name: reference(root / name) for name in MATERIAL_FILES},
        "q_compute_replay": copy.deepcopy(parent["q_compute_replay"]),
        "single_slot_scheduling": scheduling_inventory(parent),
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "original_closed_slots_replayed": [], "new_training_material": [], "new_direction": False,
        "old_records_rewritten": False, "old_worker_cost_counted_once": True,
        "external_updates_owned_by_original_hosts": True, "new_update_workers": 0,
        "new_model_qualification_calls": 0, "maximum_total_residents": 4}
    # Use the existing exact r4 observer for its bound parent states and guardian.
    prior.observe_external(parent, identity_fn=identity_fn)
    return result


def prepare(root, *, parent_root, controls=CONTROLS):
    root, old = Path(root).resolve(), Path(parent_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Use a new independent r6 development root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the isolated r6 source and controls before model work")
    controls = Path(controls).resolve()
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require finite zero-model r6 controls")
    derived = derive_inventory(old)
    if proof.get("parent_plan") != derived["parent_plan"]:
        raise ValueError("Controls must bind the exact r5 plan")
    parent = read_json(checked(derived["parent_plan"]))
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, source_root=str(SOURCE), source_files=source_files(),
        created_at=time.time(), workers=list(WORKERS), limits=copy.deepcopy(LIMITS),
        parent_run_root=str(old), parent_source_root=derived["parent_source_root"],
        parent_plan=derived["parent_plan"], continuation_inventory=derived,
        external_updates=derived["external_updates"], q_compute_replay=derived["q_compute_replay"],
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        continuation_generation_caps=generation_caps(), single_slot_scheduling=scheduling_inventory(parent),
        resource_policy=copy.deepcopy(resource.RESOURCE_POLICY), startup_retry_policy=copy.deepcopy(RETRY_POLICY),
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]),
        automatic_retries=False, automatic_verified_resource_retries=True, automatic_successors=[],
        old_queues_remain_paused=True, precise_gradient_checkpoint_resume=False,
        new_update_workers=0, new_training_compute_seconds=0, maximum_total_residents=4,
        scope="Only original sixteen Q developments. Both updates remain external and count toward four total residents; no update, replay, new seed or qualification.")
    for key in ("plan_sha256", "explicit_Q_minus_recomputation_limit", "explicit_Q_recomputation_limits",
            "parent_supervisor_initial_observation"):
        plan.pop(key, None)
    root.mkdir(parents=True, exist_ok=False)
    for name, ref in derived["materials"].items():
        (root / name).write_bytes(checked(ref).read_bytes())
    write(root / "parent-supervisor-observed-at-freeze.json", read_json(old / "supervisor.json"))
    plan["parent_supervisor_initial_observation"] = reference(root / "parent-supervisor-observed-at-freeze.json")
    plan = seal(plan, "plan_sha256")
    write(root / "plan.json", plan)
    return plan


def frozen(root):
    root = Path(root).resolve()
    plan = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("source_root") != str(SOURCE) or plan.get("source_files") != source_files()
            or plan.get("limits") != LIMITS or plan.get("workers") != list(WORKERS)
            or plan.get("gpu_preference") != list(GPU_PREFERENCE)
            or plan.get("resource_policy") != resource.RESOURCE_POLICY
            or plan.get("startup_retry_policy") != RETRY_POLICY
            or plan.get("continuation_generation_caps") != generation_caps()
            or plan.get("single_slot_scheduling") != scheduling_inventory(plan)
            or plan.get("automatic_retries") is not False or plan.get("automatic_verified_resource_retries") is not True
            or plan.get("automatic_successors") != [] or plan.get("new_update_workers") != 0
            or plan.get("new_training_compute_seconds") != 0 or plan.get("maximum_total_residents") != 4):
        raise ValueError("Frozen r6 development source, four-resident cap or original budget changed")
    derived = plan["continuation_inventory"]
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    if (parent["source"] != derived["parent_source"] or parent["source_root"] != plan["parent_source_root"]
            or plan["external_updates"] != derived["external_updates"]):
        raise ValueError("Original update owners or source bindings changed")
    original_source_agreement(parent, SOURCE)
    supervisor = read_json(Path(plan["parent_run_root"]) / "supervisor.json")
    if _handoff(plan["parent_run_root"], parent, supervisor) != derived["administrative_handoff"]:
        raise ValueError("The administrative handoff receipt changed")
    for name, entry in derived["closed_parent_workers"].items():
        if supervisor["states"][name] != entry["state"]:
            raise ValueError("The old host changed transferred unstarted inventory")
    for name, ref in derived["materials"].items():
        if (root / name).read_bytes() != checked(ref).read_bytes():
            raise ValueError("Scientific material changed: " + name)
    check_seal(plan["q_compute_replay"])
    if plan["q_compute_replay"] != parent["q_compute_replay"] or plan["q_compute_replay"] != derived["q_compute_replay"]:
        raise ValueError("Both existing compute allocations must remain exact")
    for key in SCIENTIFIC_KEYS:
        if plan[key] != parent[key]:
            raise ValueError("Original scientific contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("Frozen r6 protocol changed")
    return plan


def _validate_complete(plan, branch, supervisor, state):
    binding = plan["external_updates"][branch]
    root = Path(binding["run_root"])
    folder = root / ("update-" + branch) / "actual"
    report = read_json(folder / "report.json")
    update_path = checked(report["update_report"])
    checkpoint_path = folder / "checkpoint/checkpoint.json"
    update, checkpoint = read_json(update_path), read_json(checkpoint_path)
    compute = read_json(folder / "training-compute.json")
    baseline = read_json(checked(plan["continuation_inventory"]["B_update"]))
    budget = check_seal(plan["q_compute_replay"]["branches"][branch])
    before = binding["identity"]["source"]
    if (state.get("status") != "complete" or state.get("exit_code") != 0 or not state.get("ended_at")
            or report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != before or report.get("source_after") != before
            or update_path != folder / "update/report.json" or report.get("checkpoint") != checkpoint
            or checkpoint_path.is_symlink() or checkpoint_path.parent.is_symlink()
            or checkpoint.get("serialized_reload_exact") is not True
            or report.get("final_actor_identity") != checkpoint.get("actor_identity")
            or report.get("actor_steps") != checkpoint.get("actor_steps")
            or report.get("critic_steps") != checkpoint.get("critic_steps")
            or any(checkpoint.get(k) not in (4, 5) for k in ("actor_steps", "critic_steps"))
            or update.get("stage") != "complete" or update.get("status") not in {
                "updated", "zero_step_zero_actor_advantage_or_gradient", "zero_step_no_admitted_own_actions"}
            or any(update.get(k) != baseline.get(k) for k in ("advantages", "old_critic_values", "rewards"))
            or update.get("recipe") != plan["s_star_recipe"]):
        raise ValueError("External update must reach its exact clean source/checkpoint/critic boundary")
    for kind in ("actor", "critic"):
        steps = update.get(kind + "_optimizer_steps")
        if type(steps) is not int or steps not in (0, 1) or checkpoint[kind + "_steps"] != 4 + steps:
            raise ValueError("External update changed the original one-step boundary")
    counts = ("native_forward_started", "native_forward_completed", "native_gradient_forward_started",
        "native_no_grad_forward_started")
    if any(type(compute.get(k)) is not int or compute[k] < 0 for k in counts):
        raise ValueError("External native compute counters must be exact nonnegative integers")
    n = budget["admitted_rows_per_attempt"]
    post = update.get("post_update_additional_actor_forwards", 0)
    backward = update.get("backward_decisions_completed", 0)
    if (type(post) is not int or not 0 <= post <= 6 or type(backward) is not int or not 0 <= backward <= n
            or update.get("admitted_decisions") != n
            or type(update.get("actor_update_enabled")) is not bool
            or compute["native_gradient_forward_started"] != (backward if update["actor_update_enabled"] else 0)
            or compute["native_no_grad_forward_started"] != n + post
            or compute["native_forward_started"] != n + post + compute["native_gradient_forward_started"]
            or compute["native_forward_completed"] != compute["native_forward_started"]
            or compute.get("admitted_rows") != n or compute.get("forward_upper") != 2 * n + 6
            or any(compute.get(k + "_backward_upper") != n for k in ("actor", "critic"))
            or any(compute.get(k + "_steps_upper") != 1 for k in ("actor", "critic"))
            or compute.get("maximum_seconds") != budget["remaining_seconds"]
            or compute.get("replay_budget_sha256") != budget["sha256"]
            or compute.get("global_allocation_sha256") != budget["global_allocation_sha256"]
            or compute.get("branch") != branch or compute.get("old_cost_counted_once") is not True):
        raise ValueError("External native counts or original compute allocation changed")
    started, ended, elapsed = (compute.get(k) for k in ("started_at", "ended_at", "elapsed_seconds"))
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (started, ended, elapsed))
            or elapsed != ended - started or not 0 <= elapsed < budget["remaining_seconds"]):
        raise ValueError("External update must finish within its unchanged compute interval")
    from scripts import software_learning_resume_compute_v050r4 as compute_host
    if compute_host.training_stop_reason(compute, now=ended) is not None:
        raise ValueError("External update violated the original aggregate compute limits")
    direction = check_seal(read_json(checked(plan["continuation_inventory"]["materials"]["direction.json"])), "seal_sha256")
    core = check_seal(direction["direction"], "seal_sha256")
    sign = "plus" if branch == "Q_plus" else "minus"
    composition = check_seal(read_json(folder / "composition-before-update.json"), "seal_sha256")
    updated_composition = check_seal(read_json(folder / "update/composition.json"), "seal_sha256")
    recompute = read_json(folder / "recompute-binding.json")
    loaded = read_json(folder / "loaded-state.json")
    sstar = read_json(checked(plan["s_star_checkpoint"]))
    if (composition != updated_composition or composition.get("weights_by_slot") != direction[sign + "_weights"]
            or direction[sign + "_weights"] != core[sign + "_weights_by_slot"]
            or composition.get("entries_sha256") != budget["inputs"]["entries.json"]["sha256"]
            or recompute.get("budget") != budget or recompute.get("scientific_branch") != branch
            or recompute.get("partial_state_reused") is not False
            or loaded.get("branch") != "S_star" or loaded.get("checkpoint") != plan["s_star_checkpoint"]
            or loaded.get("restored") != sstar or loaded.get("actor_identity") != sstar["actor_identity"]
            or (loaded.get("actor_steps"), loaded.get("critic_steps")) != (4, 4)):
        raise ValueError("External branch changed its original direction, rows or complete S_star")
    return {"status": "complete", "branch": branch,
        "original_worker_identity": copy.deepcopy(binding["identity"]),
        "original_terminal_state": copy.deepcopy(state), "parent_source": before,
        "original_supervisor_status": supervisor["status"], "checkpoint": reference(checkpoint_path),
        "worker_report": reference(folder / "report.json"), "update_report": reference(update_path),
        "training_compute": reference(folder / "training-compute.json"),
        "composition": reference(folder / "composition-before-update.json"),
        "updated_composition": reference(folder / "update/composition.json"),
        "recompute_binding": reference(folder / "recompute-binding.json"),
        "loaded_state": reference(folder / "loaded-state.json"),
        "old_worker_seconds_counted_in_parent_only": state["elapsed_gpu_seconds"],
        "new_model_calls_by_observer": 0, "new_gpu_worker_seconds_by_observer": 0}


def _observe_branch(plan, branch, *, previous=None, now=None, identity_fn=worker_identity):
    now = time.time() if now is None else now
    binding = plan["external_updates"][branch]
    expected = binding["identity"]
    supervisor = read_json(Path(binding["run_root"]) / "supervisor.json")
    state = supervisor.get("states", {}).get("update-" + branch, {})
    if (supervisor.get("source") != expected["source"]
            or external_identity(branch, state, expected["source"]) != expected):
        raise ValueError("External update source/process/GPU identity changed")
    observed = identity_fn(expected["pid"])
    live = observed.get("alive") is True and observed.get("start_ticks") == expected["start_ticks"]
    if observed.get("alive") is True and not live:
        raise ValueError("External update PID was reused or lost its bound start_ticks")
    if observed.get("alive") not in (True, False):
        raise ValueError("External update process liveness is unknown")
    if state.get("status") == "complete" and not live:
        return {"status": "complete", "resident_count": 0, "excluded_gpu": None,
            "terminal": _validate_complete(plan, branch, supervisor, state)}
    if state.get("status") not in {"running", "complete"}:
        raise ValueError("External update failed; no restart or recomputation is authorized")
    if live and state["status"] == "running":
        guardian = binding["supervisor_process"]
        owner = identity_fn(guardian["pid"])
        if (supervisor.get("status") != "running" or supervisor.get("observer_pid") != guardian["pid"]
                or owner.get("alive") is not True or owner.get("start_ticks") != guardian["start_ticks"]):
            raise ValueError("External update lost its original live resource guardian")
        return {"status": "running", "resident_count": 1, "excluded_gpu": expected["gpu"],
            "pid": expected["pid"], "start_ticks": expected["start_ticks"], "observed_at": now}
    since = (previous or {}).get("missing_terminal_since", now)
    if now - since > max(30, 3 * LIMITS["poll_seconds"]):
        raise ValueError("External update did not reach a bound terminal receipt and original process exit")
    return {"status": "awaiting_original_worker_exit" if live else "awaiting_original_host_closure",
        "resident_count": 1, "excluded_gpu": expected["gpu"], "missing_terminal_since": since, "observed_at": now}


def observe_externals(plan, *, prior=None, now=None, identity_fn=worker_identity):
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    supervisor = read_json(Path(plan["parent_run_root"]) / "supervisor.json")
    if _handoff(plan["parent_run_root"], parent, supervisor) != plan["continuation_inventory"]["administrative_handoff"]:
        raise ValueError("The exact administrative handoff changed")
    for name, entry in plan["continuation_inventory"]["closed_parent_workers"].items():
        if supervisor["states"][name] != entry["state"]:
            raise ValueError("Original transferred inventory changed")
    # Keep all existing r4 parent/failure/guardian checks; add stronger exact
    # completed-update accounting symmetrically for the two immutable branches.
    globals()["prior"].observe_external(parent, prior=(prior or {}).get("Q_plus"), now=now, identity_fn=identity_fn)
    result = {branch: _observe_branch(plan, branch, previous=(prior or {}).get(branch), now=now,
        identity_fn=identity_fn) for branch in BRANCHES}
    for branch, previous in (prior or {}).items():
        if previous.get("status") == "complete":
            def stable(value):
                value = copy.deepcopy(value)
                value.get("terminal", {}).pop("original_supervisor_status", None)
                return value
            if stable(result[branch]) != stable(previous):
                raise ValueError("An external terminal receipt cannot regress or change")
    return result


def _restored_state(owner, root, branch, output):
    if branch not in BRANCHES:
        raise ValueError("This development host cannot restore S_star for an update")
    root = Path(root)
    plan = read_json(root / "plan.json")
    receipt = check_seal(read_json(root / ("external-" + branch + "-complete.json")))
    binding = plan["external_updates"][branch]
    if (receipt.get("status") != "complete" or receipt.get("branch") != branch
            or receipt.get("original_worker_identity") != binding["identity"]):
        raise ValueError("Require the immutable original external branch completion receipt")
    for name in ("checkpoint", "worker_report", "update_report", "training_compute", "composition",
            "updated_composition", "recompute_binding", "loaded_state"):
        checked(receipt[name])
    path = checked(receipt["checkpoint"])
    expected_path = Path(binding["run_root"]) / ("update-" + branch) / "actual/checkpoint/checkpoint.json"
    if path != expected_path or path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Only the exact external checkpoint location is admissible")
    expected = read_json(path)
    task(output, "restore-complete-" + branch, "boundary")
    restored = owner.restore_checkpoint(path.parent)
    if (restored != expected or owner.freeze_identity() != expected["actor_identity"]
            or (owner.actor_steps, owner.critic_steps) != (expected["actor_steps"], expected["critic_steps"])
            or any(step not in (4, 5) for step in (owner.actor_steps, owner.critic_steps))):
        raise ValueError("Restore only the exact complete original external branch state")
    write(Path(output) / "loaded-state.json", {"branch": branch, "checkpoint": reference(path),
        "external_completion": reference(root / ("external-" + branch + "-complete.json")),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps})
    return restored


def _collect(owner, plan, root, worker, output):
    return bind(prior.prior._collect, VERSION=VERSION, DEVELOPMENT=DEVELOPMENT,
        original_worker=original_worker, worker_units=worker_units, _restored_state=_restored_state)(
            owner, plan, root, worker, output)


def runtime_reservation(root, worker, output):
    return bind(prior.runtime_reservation, VERSION=VERSION, SOURCE=SOURCE, MODULE=MODULE,
        WORKERS=WORKERS, original_worker=original_worker, worker_units=worker_units)(root, worker, output)


def run_worker(root, worker, output):
    original_worker(worker)
    return bind(prior.run_worker, VERSION=VERSION, WORKERS=WORKERS, UPDATES=UPDATES,
        runtime_reservation=runtime_reservation, frozen=frozen, _collect=_collect,
        _restored_state=_restored_state)(root, worker, output)


def worker_env(plan, gpu, binding):
    return bind(prior.worker_env, SOURCE=SOURCE, GPU_ORDER=GPU_ORDER)(plan, gpu, binding)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "supervise", "worker"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--parent-root", type=Path)
    parser.add_argument("--controls", type=Path, default=CONTROLS)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, original.received_signal)
    if args.command == "prepare":
        if args.parent_root is None:
            parser.error("prepare requires --parent-root")
        prepare(args.run_root, parent_root=args.parent_root, controls=args.controls)
    elif args.command == "supervise":
        from scripts.software_learning_resume_supervisor_v050r6 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
