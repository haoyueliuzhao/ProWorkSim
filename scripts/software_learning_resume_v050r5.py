"""Recover only proven pre-model resource failures; retain scientific attempts."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import subprocess
import time
from types import SimpleNamespace

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, read_json
from scripts import software_learning_resume_v050r4 as prior
from scripts import software_learning_resume_v050r2 as external_host
from scripts import software_learning_resources_v050r5 as startup_resource
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-original-Q-continuation-v0.50-r5"
MODULE = "scripts.software_learning_resume_v050r5"
SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r5-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r5-cpu-controls.json"
original = prior.original
resource = startup_resource.prior
GPU_ORDER = GPU_PREFERENCE = tuple(range(8))
LIMITS = copy.deepcopy(prior.LIMITS)
UPDATES = ("update-Q_minus",)
DEVELOPMENT = prior.DEVELOPMENT
WORKERS = (*UPDATES, *DEVELOPMENT)
MATERIAL_FILES = prior.MATERIAL_FILES
checked, seal, check_seal = original.checked, original.seal, original.check_seal
generation_caps = prior.generation_caps
RETRY_POLICY = {"version": VERSION, "automatic_model_retries": False,
    "automatic_verified_zero_model_resource_retries": True,
    "backoff_seconds": [5, 10, 20, 40, 60], "maximum_resource_attempts": None,
    "model_load_intent_disables_retry": True, "archive_before_requeue": True,
    "same_scientific_worker_budget_seed": True, "failed_resource_worker_blocks_other_ready_workers": False}
SCIENTIFIC_KEYS = ("inventory", "design", "s_star_checkpoint", "s_star_recipe", "mapper_specification",
    "task_source_manifest", "source_partition", "training_reward", "development_F",
    "generation_budget", "training_budget", "common", "model_references", "original_plan")


def source_files():
    files = prior.source_files()
    for path in (PROTOCOL, CONTROLS, Path(__file__),
            SOURCE / "scripts/software_learning_resume_supervisor_v050r5.py",
            SOURCE / "scripts/software_learning_resources_v050r5.py",
            SOURCE / "scripts/software_learning_startup_audit_v050r5.py"):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def original_worker(worker):
    if worker not in WORKERS:
        raise ValueError("Only original Q-minus and sixteen development workers are owned")
    return prior.original_worker(worker)


def worker_units(plan, worker):
    original_worker(worker)
    return prior.worker_units(plan, worker)


def scheduling_inventory(plan):
    return {worker: {"original_worker": original_worker(worker),
        "units": worker_units(plan, worker)} for worker in DEVELOPMENT}


def derive_inventory(parent_root, *, source_root=SOURCE, check_source=True):
    from scripts.software_learning_startup_audit_v050r5 import derive_parent_failure

    root = Path(parent_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (parent.get("version") != prior.VERSION or parent.get("workers") != list(prior.WORKERS)
            or parent.get("limits") != LIMITS or parent.get("automatic_retries") is not False):
        raise ValueError("Require the exact r4 parent plan")
    supervisor = read_json(root / "supervisor.json")
    if supervisor.get("source") != parent["source"] or set(supervisor.get("states", {})) != set(prior.WORKERS):
        raise ValueError("The original host/source must remain bound")
    failure = derive_parent_failure(root, plan=parent, states=supervisor["states"])
    plus = external_host.external_identity(supervisor["states"]["update-Q_plus"], parent)
    if supervisor["states"]["update-Q_plus"].get("status") not in {"running", "complete"}:
        raise ValueError("The external Q-plus must remain running or complete")
    guardian = worker_identity(supervisor["observer_pid"])
    if supervisor["states"]["update-Q_plus"]["status"] == "running" and (
            guardian.get("alive") is not True or type(guardian.get("start_ticks")) is not int):
        raise ValueError("Q-plus must retain its own live r4 supervisor")
    inherited = parent["continuation_inventory"]["historical_inventory"]["original_inventory"]
    return {"version": VERSION, "parent_run_root": str(root), "parent_plan": reference(root / "plan.json"),
        "parent_source": parent["source"], "parent_source_root": parent["source_root"],
        "parent_failure": failure, "closed_parent_workers": failure["closed_parent_workers"],
        "external_Q_plus": plus,
        "original_supervisor_process": {"pid": supervisor["observer_pid"], "start_ticks": guardian.get("start_ticks")},
        "B_update": inherited["B_update"], "B_checkpoint": inherited["B_checkpoint"],
        "materials": {name: reference(root / name) for name in MATERIAL_FILES},
        "q_compute_replay": copy.deepcopy(parent["q_compute_replay"]),
        "single_slot_scheduling": scheduling_inventory(parent),
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "original_closed_slots_replayed": [], "new_training_material": [], "new_direction": False,
        "old_records_rewritten": False, "old_worker_cost_counted_once": True,
        "external_Q_plus_owned_by_original_host": True}


def prepare(root, *, parent_root, controls=CONTROLS):
    root, old = Path(root).resolve(), Path(parent_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Use a new independent r5 root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the isolated r5 source and controls before model work")
    controls = Path(controls).resolve()
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require finite zero-model r5 controls")
    derived = derive_inventory(old)
    if proof.get("parent_plan") != derived["parent_plan"]:
        raise ValueError("Controls must bind the exact r4 plan")
    parent = read_json(checked(derived["parent_plan"]))
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, source_root=str(SOURCE), source_files=source_files(),
        created_at=time.time(), workers=list(WORKERS), limits=LIMITS,
        parent_run_root=str(old), parent_source_root=derived["parent_source_root"],
        parent_plan=derived["parent_plan"], continuation_inventory=derived,
        external_Q_plus=derived["external_Q_plus"], q_compute_replay=derived["q_compute_replay"],
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        continuation_generation_caps=generation_caps(), single_slot_scheduling=scheduling_inventory(parent),
        resource_policy=copy.deepcopy(resource.RESOURCE_POLICY), startup_retry_policy=copy.deepcopy(RETRY_POLICY),
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]),
        automatic_retries=False, automatic_verified_resource_retries=True,
        automatic_successors=[], old_queues_remain_paused=True,
        precise_gradient_checkpoint_resume=False, explicit_Q_minus_recomputation_limit=1,
        scope="Finish the same unconsumed r4 Q-minus computation and original sixteen development slots. Retry only proven zero-model resource attempts; observe external r4 Q-plus without taking ownership.")
    for key in ("plan_sha256", "gpu2_lease", "explicit_Q_recomputation_limits", "parent_supervisor_initial_observation"):
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
    from scripts.software_learning_startup_audit_v050r5 import derive_parent_failure

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
            or plan.get("explicit_Q_minus_recomputation_limit") != 1 or plan.get("automatic_successors") != []):
        raise ValueError("Frozen r5 source, inventory, resources or scientific budget changed")
    derived = plan["continuation_inventory"]
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    if parent["source"] != derived["parent_source"] or parent["source_root"] != plan["parent_source_root"]:
        raise ValueError("Original r4 source changed")
    original_source_agreement(parent, SOURCE)
    failure = derive_parent_failure(plan["parent_run_root"], plan=parent)
    if failure != derived["parent_failure"]:
        raise ValueError("The frozen zero-model parent failure evidence changed")
    for name, ref in derived["materials"].items():
        if (root / name).read_bytes() != checked(ref).read_bytes():
            raise ValueError("Scientific material changed: " + name)
    check_seal(plan["q_compute_replay"])
    if plan["q_compute_replay"] != parent["q_compute_replay"] or plan["q_compute_replay"] != derived["q_compute_replay"]:
        raise ValueError("Reuse the unchanged r4 allocation; startup failures consume no compute interval")
    for key in SCIENTIFIC_KEYS:
        if plan[key] != parent[key]:
            raise ValueError("Original scientific contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("Frozen r5 protocol changed")
    return plan


def _completed_external(plan, supervisor, state):
    terminal = external_host._completed_external(plan, supervisor, state)
    compute = read_json(checked(terminal["training_compute"]))
    budget = plan["q_compute_replay"]["branches"]["Q_plus"]
    if (compute.get("maximum_seconds") != budget["remaining_seconds"]
            or compute.get("replay_budget_sha256") != budget["sha256"]
            or compute.get("native_forward_completed") != compute.get("native_forward_started")
            or compute.get("elapsed_seconds", float("inf")) > budget["remaining_seconds"]):
        raise ValueError("External Q-plus must close inside its unchanged r4 compute allocation")
    return terminal


def observe_external(plan, *, prior=None, now=None, identity_fn=worker_identity):
    return bind(external_host.observe_external, LIMITS=LIMITS,
        _completed_external=_completed_external)(plan, prior=prior, now=now, identity_fn=identity_fn)


_restored_state = external_host._restored_state


def _collect(owner, plan, root, worker, output):
    result = bind(prior._collect, VERSION=VERSION, DEVELOPMENT=DEVELOPMENT,
        worker_units=worker_units, _restored_state=_restored_state)(owner, plan, root, worker, output)
    return result


def runtime_reservation(root, worker, output):
    """Small source/process/GPU binding before resource acquisition, without material loads."""
    root, output = Path(root).resolve(), Path(output).resolve()
    plan = check_seal(read_json(root / "plan.json"), "plan_sha256")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=SOURCE, text=True).strip()
    if (worker not in WORKERS or output != root / worker / "actual" or output.exists()
            or plan.get("version") != VERSION or plan.get("workers") != list(WORKERS)
            or plan.get("source_root") != str(SOURCE) or plan["source"].get("code_commit") != head
            or plan["source"].get("code_dirty") is not False or dirty):
        raise ValueError("Startup requires the exact fresh worker, sealed plan and clean source HEAD")
    original.original.inherited.validate_worker_interpreter(plan)
    binding = resource.binding_from_env()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(binding["gpu_index"]):
        raise ValueError("The physical GPU and cache reservation differ")
    state = read_json(root / "supervisor.json")["states"][worker]
    launch = read_json(root / worker / "worker-launch.json")
    expected = [plan["native_python"], "-m", MODULE, "worker", "--run-root", str(root),
        "--worker", worker, "--output", str(output)]
    if (state.get("worker") != worker or state.get("attempted") is not True
            or state.get("status") not in {"not_started", "running"}
            or state.get("reservation") != binding or launch.get("reservation") != binding
            or state.get("gpu") != binding["gpu_index"] or launch.get("gpu") != binding["gpu_index"]
            or state.get("gpu_uuid") != binding["gpu_uuid"]
            or state.get("command") != expected or launch.get("actual_command") != expected
            or launch.get("cwd") != str(SOURCE) or launch.get("source") != plan["source"]
            or launch.get("resource_attempt_number") != state.get("resource_attempt_number")
            or launch.get("original_worker") != original_worker(worker)
            or launch.get("planned_units") != worker_units(plan, worker)
            or (state.get("pid") is not None and state["pid"] != os.getpid())):
        raise ValueError("Startup environment, supervisor and actual launch must agree")
    identity = {"worker": worker, "run_root": str(root), "source": plan["source"],
        "source_root": str(SOURCE), "plan": reference(root / "plan.json"),
        "worker_launch": reference(root / worker / "worker-launch.json"),
        "process_identity": worker_identity(os.getpid()),
        "resource_attempt_number": launch["resource_attempt_number"]}
    write(root / worker / "reservation-binding-verified.json", {
        "reservation": binding, "identity": identity, "actual_command": expected,
        "original_worker": original_worker(worker), "planned_units": worker_units(plan, worker),
        "verified_before_cuda_or_model_load": True, "verified_at": time.time()})
    return binding, identity


def run_worker(root, worker, output):
    from scripts import software_learning_resume_compute_v050r4 as compute

    root, output = Path(root).resolve(), Path(output).resolve()
    reservation, identity = runtime_reservation(root, worker, output)
    startup = root / worker / "startup"
    try:
        ready = startup_resource.acquire_startup_cache(startup, reservation, identity=identity)
    except startup_resource.StartupResourceUnavailable as error:
        write(root / worker / "resource-wait.json", {"version": VERSION, "status": "resource_wait",
            "worker": worker, "identity": identity, "reservation": reservation,
            "source_before": identity["source"], "source_after": code_identity(),
            "retryable": True, "model_started": False, "new_model_calls": 0,
            "new_backward_calls": 0, "new_actor_steps": 0, "new_critic_steps": 0,
            "new_training_interval_seconds": 0, "loader_not_entered": True,
            "resource_receipt": reference(startup / "startup-resource-receipt.json"),
            "raw_fault": error.receipt, "ended_at": time.time()})
        return read_json(root / worker / "resource-wait.json")

    def load_owner(plan, out):
        # This durable intent precedes the actual loader. Any failure after it
        # is a scientific/integrity stop, even if no model forward completed.
        write(startup / "model-load-intent.json", {"version": VERSION, "identity": identity,
            "reservation": reservation, "recorded_at": time.time(), "model_work_may_have_started": True})
        adapter = SimpleNamespace(**{**vars(resource), "reserve_before_load": lambda folder, binding:
            startup_resource.use_startup_cache(folder, startup, ready, binding, identity=identity)})
        return bind(prior._load_owner, resource=adapter)(plan, out)

    def collect(owner, plan, run, name, out):
        with resource.native_cache_context(owner, out, reservation):
            return _collect(owner, plan, run, name, out)

    def update(owner, plan, run, name, out):
        with resource.native_cache_context(owner, out, reservation):
            return compute.update(owner, plan, run, name, out, restored_state=_restored_state)

    return bind(original.run_worker, VERSION=VERSION, WORKERS=WORKERS, UPDATES=UPDATES,
        GPU_ORDER=GPU_ORDER, frozen=frozen, _load_owner=load_owner, _collect=collect,
        _update=update)(root, worker, output)


def worker_env(plan, gpu, binding):
    env = resources(GPU_ORDER).worker_env(plan, gpu)
    env["PYTHONPATH"] = os.pathsep.join([str(SOURCE / "src"), str(SOURCE), plan["runtime_dependency_path"]])
    env["PROWORKSIM_Q_CONTINUATION_SOURCE"] = str(SOURCE)
    return resource.worker_env(env, binding)


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
        from scripts.software_learning_resume_supervisor_v050r5 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
