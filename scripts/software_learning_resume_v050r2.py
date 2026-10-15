"""One explicit Q-minus recomputation and the original sixteen Q developments.

The old Q-plus worker keeps its original supervisor and source checkout. This
host only observes that dependency and never signals it. Every scientific
material file is reused byte-for-byte; the interrupted Q-minus update is not
claimed to have a resumable gradient checkpoint.
"""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_resume_v050r1 as parent_host
from scripts import software_learning_v050 as original
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.run_ne_v021 import reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-original-Q-continuation-v0.50-r2"
MODULE = "scripts.software_learning_resume_v050r2"
SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r2-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r2-cpu-controls.json"
GPU_ORDER = tuple(range(8))
GPU_PREFERENCE = (4, 0, 1, 2, 3, 5, 6, 7)
LIMITS = copy.deepcopy(original.LIMITS)
UPDATES = ("update-Q_minus",)
DEVELOPMENT = tuple(n for n in original.DEVELOPMENT if n.startswith(("dev-Q_plus-", "dev-Q_minus-")))
WORKERS = (*UPDATES, *DEVELOPMENT)
MATERIAL_FILES = ("declaration.json", "s_star.json", "precollection-binding.json", "entries.json",
    "source-registry.json", "pretraining-admission.json", "support-before-training.json", "support.json",
    "support-gate.json", "direction.json")
checked, seal, check_seal = original.checked, original.seal, original.check_seal


def source_files():
    files = parent_host.source_files()
    for path in (PROTOCOL, CONTROLS):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def worker_units(plan, worker):
    if worker not in WORKERS:
        raise ValueError("Only Q-minus recomputation and the original Q developments are authorized")
    return original.worker_units(plan, worker) if worker in DEVELOPMENT else []


def generation_caps():
    return {"remaining_original_development_slots": 16, "new_generation_slots_max": 16,
        "new_actual_generation_tokens_max": 8000000, "new_decisions_max": 2048,
        "new_attempts_max": 2048, "new_member_tests_max": 512,
        "including_retained_actual_tokens_upper": 23807260,
        "including_retained_actual_decisions_upper": 3176,
        "including_retained_actual_attempts_upper": 3153,
        "including_retained_actual_tests_upper": 653,
        "old_unspent_tokens_not_transferred": 4192740, "new_training_collection_slots": 0,
        "new_seeds_or_material": 0, "new_model_qualification_calls": 0,
        "old_actual_generation_counted_once": True}


def _terminal_worker(parent_root, name, state, parent):
    folder = Path(parent_root) / name / "actual"
    report = read_json(folder / "report.json")
    if (state.get("status") != "complete" or state.get("attempted") is not True
            or state.get("exit_code") != 0 or not state.get("ended_at")
            or report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != report.get("source_after")
            or report.get("source_after") != parent["source"]):
        raise ValueError("An already completed original worker changed: " + name)
    return {"state": copy.deepcopy(state), "report": reference(folder / "report.json")}


def external_identity(state, parent):
    expected = {"worker": "update-Q_plus", "pid": state.get("pid"),
        "start_ticks": state.get("process_identity", {}).get("start_ticks"),
        "gpu": state.get("gpu"), "gpu_uuid": state.get("gpu_uuid"),
        "started_at": state.get("started_at"), "source": copy.deepcopy(parent["source"])}
    if (state.get("attempted") is not True or type(expected["pid"]) is not int
            or type(expected["start_ticks"]) is not int or expected["gpu"] not in GPU_ORDER
            or type(expected["started_at"]) not in (int, float)):
        raise ValueError("Bind the exact original Q-plus process identity, never a replacement worker")
    return expected


def derive_inventory(parent_root, *, source_root=SOURCE, check_source=True):
    from scripts import software_learning_resume_compute_v050r2 as compute

    root = Path(parent_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (parent.get("version") != parent_host.VERSION or parent.get("limits") != LIMITS
            or parent.get("workers") != list(original.WORKERS) or parent.get("gpu_preference") != list(GPU_ORDER)):
        raise ValueError("This continuation requires the exact original v050r1 plan")
    original.validate_inventory(parent["inventory"])
    supervisor = read_json(root / "supervisor.json")
    states = supervisor.get("states", {})
    if (set(states) != set(original.WORKERS) or supervisor.get("source") != parent["source"]
            or supervisor.get("status") not in {"running", "closed_with_unknowns"}):
        raise ValueError("The original host may only finish its sole already-running Q-plus dependency")
    frozen_workers = {}
    for name in (*original.COLLECTION, "update-B", "dev-S_star-0", "dev-S_star-1", "dev-B-0", "dev-B-1"):
        frozen_workers[name] = _terminal_worker(root, name, states[name], parent)
    for name in DEVELOPMENT:
        state = states[name]
        if (state.get("status") != "stopped" or state.get("attempted") is not False
                or state.get("stop_reason") != "unopened_work_paused" or (root / name).exists()):
            raise ValueError("All original Q-development workers must remain never started")
        frozen_workers[name] = {"state": copy.deepcopy(state)}
    plus = external_identity(states["update-Q_plus"], parent)
    if states["update-Q_plus"].get("status") not in {"running", "complete"}:
        raise ValueError("Q-plus may be observed only while running or after its clean original completion")
    observer = worker_identity(supervisor["observer_pid"])
    if states["update-Q_plus"]["status"] == "running" and (observer.get("alive") is not True
            or type(observer.get("start_ticks")) is not int):
        raise ValueError("The running original Q-plus must retain its live original resource supervisor")
    replay = compute.derive_replay_budget(root)
    minus = states["update-Q_minus"]
    if (minus.get("status") != "stopped" or minus.get("attempted") is not True
            or minus.get("stop_reason") != "shared_device_free_memory_reserve" or minus.get("exit_code") != -9
            or not minus.get("ended_at")):
        raise ValueError("Only the original explicitly stopped memory-reserve Q-minus update may be recomputed")
    live = worker_identity(minus["pid"])
    if live.get("alive") and live.get("start_ticks") == minus["process_identity"]["start_ticks"]:
        raise ValueError("The stopped Q-minus process must not remain alive")
    frozen_workers["update-Q_minus"] = {"state": copy.deepcopy(minus),
        "host_stop_action": reference(checked(minus["host_stop_action"]))}
    materials = {name: reference(root / name) for name in MATERIAL_FILES}
    declaration = read_json(root / "declaration.json")
    entries = parent_host.load_materialized_entries(parent, root)
    if (len(entries) != 24 or [r["slot_id"] for r in entries] != [r["slot_id"] for r in declaration["slots"]]
            or declaration["min_class_count"] != 2):
        raise ValueError("Reuse the original complete 24 by 2 source measure")
    direction = check_seal(read_json(root / "direction.json"), "seal_sha256")
    core = check_seal(direction["direction"], "seal_sha256")
    if (direction.get("selected") is not True or core.get("selected") is None
            or direction.get("frozen_before_any_development") is not True
            or core.get("declaration_sha256") != digest(json_bytes(declaration))
            or core.get("design_sha256") != parent["design"]["sha256"]
            or core.get("source_support_artifact_sha256") != materials["support.json"]["sha256"]):
        raise ValueError("The sole original direction must remain fixed before resumed work")
    b_report = read_json(checked(frozen_workers["update-B"]["report"]))
    b_checkpoint = read_json(root / "update-B/actual/checkpoint/checkpoint.json")
    if b_report.get("checkpoint") != b_checkpoint or b_checkpoint.get("serialized_reload_exact") is not True:
        raise ValueError("Reuse the original completed full B checkpoint")
    if (b_checkpoint.get("actor_steps"), b_checkpoint.get("critic_steps")) != (5, 5):
        raise ValueError("Original B must retain its actual complete 5/5 state")
    return {"version": VERSION, "parent_run_root": str(root), "parent_plan": reference(root / "plan.json"),
        "parent_source": copy.deepcopy(parent["source"]), "parent_source_root": parent["source_root"],
        "closed_parent_workers": frozen_workers, "external_Q_plus": plus,
        "original_supervisor_process": {"pid": supervisor["observer_pid"], "start_ticks": observer.get("start_ticks")},
        "materials": materials, "B_checkpoint": reference(root / "update-B/actual/checkpoint/checkpoint.json"),
        "B_update": b_report["update_report"], "qminus_compute_replay": replay,
        "remaining_development": {name: original.worker_units(parent, name) for name in DEVELOPMENT},
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "parent_supervisor_owned_exclusively_by_original_host": True,
        "original_closed_slots_replayed": [], "new_training_material": [], "new_direction": False}


def prepare(root, *, parent_root, controls=CONTROLS):
    root, old = Path(root).resolve(), Path(parent_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Q continuation needs a fresh independent root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the separate worktree and frozen controls before any resumed worker")
    controls = Path(controls).resolve()
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require the finite zero-model continuation controls")
    derived = derive_inventory(old)
    parent = read_json(checked(derived["parent_plan"]))
    if proof.get("parent_plan") != derived["parent_plan"]:
        raise ValueError("CPU controls must bind this exact parent inventory")
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, source_root=str(SOURCE), source_files=source_files(),
        created_at=time.time(), workers=list(WORKERS), gpu_preference=list(GPU_PREFERENCE),
        parent_run_root=str(old), parent_source_root=derived["parent_source_root"],
        parent_plan=derived["parent_plan"], continuation_inventory=derived,
        qminus_compute_replay=derived["qminus_compute_replay"], external_Q_plus=derived["external_Q_plus"],
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        continuation_generation_caps=generation_caps(),
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]),
        automatic_retries=False, automatic_successors=[], old_queues_remain_paused=True,
        explicit_Q_minus_recomputation_limit=1, precise_gradient_checkpoint_resume=False,
        scope="One newly authorized recomputation of the original stopped Q-minus update from the same S*4/4, plus only the sixteen unstarted Q developments. The original Q-plus remains owned by its original host.")
    plan.pop("plan_sha256")
    root.mkdir(parents=True, exist_ok=False)
    for name, ref in derived["materials"].items():
        (root / name).write_bytes(checked(ref).read_bytes())
    # This is a new observation receipt; it is not a frozen hash of an active file.
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
            or plan.get("continuation_generation_caps") != generation_caps()
            or plan.get("automatic_retries") is not False or plan.get("explicit_Q_minus_recomputation_limit") != 1
            or plan.get("automatic_successors") != []):
        raise ValueError("Frozen Q-continuation source, budget or resource contract changed")
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    # Only immutable parent sources are bound here; Q-plus progress/supervisor stays live.
    derived = plan["continuation_inventory"]
    if parent["source"] != derived["parent_source"] or parent["source_root"] != plan["parent_source_root"]:
        raise ValueError("Original source identity changed")
    original_source_agreement(parent, SOURCE)
    for name, ref in derived["materials"].items():
        if (root / name).read_bytes() != checked(ref).read_bytes():
            raise ValueError("Scientific material changed: " + name)
    for binding in derived["closed_parent_workers"].values():
        for key in ("report", "host_stop_action"):
            if key in binding:
                checked(binding[key])
    for key in ("B_checkpoint", "B_update"):
        checked(derived[key])
    from scripts import software_learning_resume_compute_v050r2 as compute
    if compute.derive_replay_budget(plan["parent_run_root"]) != plan["qminus_compute_replay"]:
        raise ValueError("Original interrupted compute cost or remaining budget changed")
    for key in ("inventory", "design", "s_star_checkpoint", "s_star_recipe", "mapper_specification",
                "task_source_manifest", "source_partition", "training_reward", "development_F",
                "generation_budget", "training_budget", "common", "model_references"):
        if plan[key] != parent[key]:
            raise ValueError("Original scientific or numerical contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("Continuation protocol changed")
    return plan


def _completed_external(plan, supervisor, state):
    root = Path(plan["parent_run_root"])
    folder = root / "update-Q_plus/actual"
    report = read_json(folder / "report.json")
    update_path = checked(report["update_report"])
    checkpoint_path = folder / "checkpoint/checkpoint.json"
    update, checkpoint = read_json(update_path), read_json(checkpoint_path)
    compute = read_json(folder / "training-compute.json")
    baseline = read_json(checked(plan["continuation_inventory"]["B_update"]))
    before = plan["continuation_inventory"]["parent_source"]
    if (state.get("exit_code") != 0 or not state.get("ended_at")
            or report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != before or report.get("source_after") != before
            or update_path != folder / "update/report.json" or report.get("checkpoint") != checkpoint
            or checkpoint.get("serialized_reload_exact") is not True
            or report.get("final_actor_identity") != checkpoint.get("actor_identity")
            or report.get("actor_steps") != checkpoint.get("actor_steps")
            or report.get("critic_steps") != checkpoint.get("critic_steps")
            or any(checkpoint.get(k) not in (4, 5) for k in ("actor_steps", "critic_steps"))
            or update.get("stage") != "complete" or update.get("status") not in {
                "updated", "zero_step_zero_actor_advantage_or_gradient", "zero_step_no_admitted_own_actions"}
            or any(update.get(k) != baseline.get(k) for k in ("advantages", "old_critic_values", "rewards"))
            or compute.get("ended_at") is None or compute.get("elapsed_seconds", float("inf")) > LIMITS["update_worker_seconds"]):
        raise ValueError("Q-plus requires its own original full clean update/checkpoint boundary")
    direction = read_json(checked(plan["continuation_inventory"]["materials"]["direction.json"]))
    composition = check_seal(read_json(folder / "composition-before-update.json"), "seal_sha256")
    if composition.get("weights_by_slot") != direction["plus_weights"]:
        raise ValueError("External Q-plus changed its predeclared composition")
    return {"status": "complete", "original_worker_identity": copy.deepcopy(plan["external_Q_plus"]),
        "original_terminal_state": copy.deepcopy(state), "parent_source": before,
        "original_supervisor_status": supervisor["status"],
        "checkpoint": reference(checkpoint_path), "worker_report": reference(folder / "report.json"),
        "update_report": reference(update_path), "training_compute": reference(folder / "training-compute.json"),
        "composition": reference(folder / "composition-before-update.json"),
        "old_worker_seconds_counted_in_parent_only": state["elapsed_gpu_seconds"],
        "new_model_calls_by_observer": 0, "new_gpu_worker_seconds_by_observer": 0}


def observe_external(plan, *, prior=None, now=None, identity_fn=worker_identity):
    """Read only. This function has no operation that signals the external worker."""
    now = time.time() if now is None else now
    root = Path(plan["parent_run_root"])
    supervisor = read_json(root / "supervisor.json")
    states = supervisor.get("states", {})
    expected = plan["external_Q_plus"]
    state = states.get("update-Q_plus", {})
    parent = {"source": plan["continuation_inventory"]["parent_source"]}
    if (supervisor.get("source") != expected["source"] or external_identity(state, parent) != expected):
        raise ValueError("The external Q-plus process or source identity changed")
    for name, frozen_binding in plan["continuation_inventory"]["closed_parent_workers"].items():
        if states.get(name) != frozen_binding["state"]:
            raise ValueError("The original host attempted or changed already-bound work: " + name)
    observed = identity_fn(expected["pid"])
    same_live = observed.get("alive") is True and observed.get("start_ticks") == expected["start_ticks"]
    if observed.get("alive") is True and observed.get("start_ticks") != expected["start_ticks"]:
        raise ValueError("External PID was reused or cannot be matched to the original start_ticks")
    if state.get("status") == "complete":
        if same_live:
            since = (prior or {}).get("missing_terminal_since", now)
            if now - since > max(30, 3 * LIMITS["poll_seconds"]):
                raise ValueError("A completed external worker still owns its original process identity")
            return {"status": "awaiting_original_worker_exit", "resident_count": 1,
                "excluded_gpu": expected["gpu"], "missing_terminal_since": since, "observed_at": now}
        terminal = _completed_external(plan, supervisor, state)
        return {"status": "complete", "resident_count": 0, "excluded_gpu": None, "terminal": terminal}
    if state.get("status") != "running":
        raise ValueError("External Q-plus failed; no automatic Q-plus recomputation is authorized")
    if same_live:
        guardian = plan["continuation_inventory"]["original_supervisor_process"]
        observed_guardian = identity_fn(guardian["pid"])
        if (supervisor.get("status") != "running" or supervisor.get("observer_pid") != guardian["pid"]
                or observed_guardian.get("alive") is not True
                or observed_guardian.get("start_ticks") != guardian["start_ticks"]):
            raise ValueError("The original live Q-plus lost its original resource-supervisor owner")
    if same_live:
        return {"status": "running", "resident_count": 1, "excluded_gpu": expected["gpu"],
            "pid": expected["pid"], "start_ticks": expected["start_ticks"], "observed_at": now}
    # A process may exit just before the old host publishes its terminal state.
    since = (prior or {}).get("missing_terminal_since", now)
    if now - since > max(30, 3 * LIMITS["poll_seconds"]):
        raise ValueError("External Q-plus ended without a bound original terminal receipt")
    return {"status": "awaiting_original_host_closure", "resident_count": 1,
        "excluded_gpu": expected["gpu"], "missing_terminal_since": since, "observed_at": now}


def _restored_state(owner, root, branch, output):
    plan = read_json(Path(root) / "plan.json")
    if branch == "S_star":
        path = checked(plan["s_star_checkpoint"])
    elif branch == "Q_minus":
        path = Path(root) / "update-Q_minus/actual/checkpoint/checkpoint.json"
    elif branch == "Q_plus":
        receipt = check_seal(read_json(Path(root) / "external-Q_plus-complete.json"))
        if receipt.get("original_worker_identity") != plan["external_Q_plus"]:
            raise ValueError("Only the original completed external Q-plus checkpoint is admissible")
        for name in ("checkpoint", "worker_report", "update_report", "training_compute", "composition"):
            checked(receipt[name])
        path = checked(receipt["checkpoint"])
        if path != Path(plan["parent_run_root"]) / "update-Q_plus/actual/checkpoint/checkpoint.json":
            raise ValueError("Q-plus checkpoint cannot be supplied by another branch or restart")
    else:
        raise ValueError("Only S* for the one recomputation, then the original Q branches may be restored")
    expected = read_json(path)
    task(output, "restore-complete-" + branch, "boundary")
    restored = owner.restore_checkpoint(path.parent)
    steps = (owner.actor_steps, owner.critic_steps)
    if (restored != expected or owner.freeze_identity() != expected["actor_identity"]
            or steps != (expected["actor_steps"], expected["critic_steps"])
            or (branch == "S_star" and steps != (4, 4))
            or (branch != "S_star" and any(step not in (4, 5) for step in steps))):
        raise ValueError("Restore the exact complete designated branch state")
    write(Path(output) / "loaded-state.json", {"branch": branch, "checkpoint": reference(path),
        "restored": restored, "actor_identity": owner.freeze_identity(),
        "actor_steps": owner.actor_steps, "critic_steps": owner.critic_steps})
    return restored


def _collect(owner, plan, root, worker, output):
    if worker not in DEVELOPMENT:
        raise ValueError("No new training collection is authorized")
    collector = bind(original._collect, VERSION=VERSION, DEVELOPMENT=DEVELOPMENT,
        worker_units=worker_units, _restored_state=_restored_state)
    return collector(owner, plan, root, worker, output)


def _load_owner(plan, output):
    return original._load_owner(plan, output)


def run_worker(root, worker, output):
    from scripts import software_learning_resume_compute_v050r2 as compute
    if worker not in WORKERS:
        raise ValueError("No original collection, B, S* development or Q-plus update may be dispatched")
    return bind(original.run_worker, VERSION=VERSION, WORKERS=WORKERS, UPDATES=UPDATES,
        GPU_ORDER=GPU_ORDER, frozen=frozen, _load_owner=_load_owner, _collect=_collect,
        _update=lambda owner, plan, run, name, out: compute.update(
            owner, plan, run, name, out, restored_state=_restored_state))(root, worker, output)


def worker_env(plan, gpu):
    provider = resources(GPU_ORDER)
    env = provider.worker_env(plan, gpu)
    env["PYTHONPATH"] = os.pathsep.join([str(SOURCE / "src"), str(SOURCE), plan["runtime_dependency_path"]])
    env["PROWORKSIM_Q_CONTINUATION_SOURCE"] = str(SOURCE)
    return env


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
        from scripts.software_learning_resume_supervisor_v050r2 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
