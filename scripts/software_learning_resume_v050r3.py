"""Explicit third Q-minus computation and sixteen original single-slot Q workers.

Only host resource allocation changes. The two interrupted computations and the
original live Q-plus remain immutable, independently owned historical evidence.
"""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, read_json
from scripts import software_learning_resume_v050r2 as prior
from scripts import software_learning_resources_v050r3 as resource
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.run_ne_v021 import reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-original-Q-continuation-v0.50-r3"
MODULE = "scripts.software_learning_resume_v050r3"
SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r3-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r3-cpu-controls.json"
original = prior.original
GPU_ORDER = GPU_PREFERENCE = tuple(range(8))
LIMITS = {**copy.deepcopy(original.LIMITS), **resource.LIMITS_OVERRIDES}
UPDATES = ("update-Q_minus",)
DEVELOPMENT = tuple(f"dev-{branch}-{i}" for branch in ("Q_plus", "Q_minus") for i in range(8))
WORKERS = (*UPDATES, *DEVELOPMENT)
MATERIAL_FILES = prior.MATERIAL_FILES
checked, seal, check_seal = original.checked, original.seal, original.check_seal
external_identity = prior.external_identity
generation_caps = prior.generation_caps


def source_files():
    files = prior.source_files()
    for path in (PROTOCOL, CONTROLS, Path(__file__),
                 SOURCE / "scripts/software_learning_resume_supervisor_v050r3.py",
                 SOURCE / "scripts/software_learning_resume_compute_v050r3.py",
                 SOURCE / "scripts/software_learning_resources_v050r3.py"):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def original_worker(worker):
    if worker == "update-Q_minus":
        return worker
    if worker not in DEVELOPMENT:
        raise ValueError("Only the original sixteen Q development slots are authorized")
    branch, index = worker[4:].rsplit("-", 1)
    return f"dev-{branch}-{int(index) // 4}"


def worker_units(plan, worker):
    if worker == "update-Q_minus":
        return []
    parent = original_worker(worker)
    return [original.worker_units(plan, parent)[int(worker.rsplit("-", 1)[1]) % 4]]


def scheduling_inventory(plan):
    return {worker: {"original_worker": original_worker(worker),
        "units": worker_units(plan, worker)} for worker in DEVELOPMENT}


def _dead(state, label, identity_fn=worker_identity):
    identity = identity_fn(state["pid"])
    old_ticks = state["process_identity"]["start_ticks"]
    dead = identity.get("alive") is False
    reused = identity.get("alive") is True and type(identity.get("start_ticks")) is int and identity["start_ticks"] != old_ticks
    if not (dead or reused):
        raise ValueError("The retained stopped process is still alive or unbound: " + label)
    return {"pid": state["pid"], "start_ticks": state["process_identity"]["start_ticks"],
        "original_process_dead": True}


def derive_inventory(parent_root, *, source_root=SOURCE, check_source=True):
    from scripts import software_learning_resume_compute_v050r3 as compute

    root = Path(parent_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (parent.get("version") != prior.VERSION or parent.get("workers") != list(prior.WORKERS)
            or parent.get("limits") != prior.LIMITS or parent.get("automatic_retries") is not False):
        raise ValueError("Require the exact independently frozen v050r2 continuation")
    supervisor = read_json(root / "supervisor.json")
    states = supervisor.get("states", {})
    if (supervisor.get("status") != "closed_with_unknowns" or not supervisor.get("ended_at")
            or supervisor.get("source") != parent["source"] or set(states) != set(prior.WORKERS)):
        raise ValueError("The second interrupted Q-minus host must be terminal")
    minus = states["update-Q_minus"]
    if (minus.get("status") != "stopped" or minus.get("attempted") is not True
            or minus.get("stop_reason") != "shared_device_free_memory_reserve"
            or minus.get("exit_code") != -9 or not minus.get("ended_at")):
        raise ValueError("Bind the original second memory-reserve interruption, without resuming its gradients")
    _dead(minus, "r2 Q-minus")
    observer = worker_identity(supervisor["observer_pid"])
    if observer.get("alive") is not False:
        raise ValueError("The r2 host must no longer own any worker")
    for name in prior.DEVELOPMENT:
        state = states[name]
        if (state.get("status") != "stopped" or state.get("attempted") is not False
                or state.get("stop_reason") != "unopened_work_paused" or (root / name).exists()):
            raise ValueError("All sixteen original Q development slots must remain unstarted")
    old_root = Path(parent["parent_run_root"]).resolve()
    inherited = prior.derive_inventory(old_root, source_root=source_root, check_source=check_source)
    if parent["external_Q_plus"] != inherited["external_Q_plus"]:
        raise ValueError("The external Q-plus process must retain its original source and owner")
    old_derived = parent["continuation_inventory"]
    for key in ("parent_plan", "parent_source", "parent_source_root", "closed_parent_workers",
                "external_Q_plus", "materials", "B_checkpoint", "B_update", "remaining_development"):
        if inherited[key] != old_derived[key]:
            raise ValueError("An original r1 binding changed: " + key)
    materials = {}
    for name in MATERIAL_FILES:
        if (root / name).read_bytes() != checked(inherited["materials"][name]).read_bytes():
            raise ValueError("The original learning material changed: " + name)
        materials[name] = reference(root / name)
    replay = compute.derive_replay_budget(root)
    return {"version": VERSION, "parent_run_root": str(root), "parent_plan": reference(root / "plan.json"),
        "parent_source": copy.deepcopy(parent["source"]), "parent_source_root": parent["source_root"],
        "parent_supervisor": reference(root / "supervisor.json"),
        "parent_artifacts": [reference(p) for p in sorted(root.rglob("*")) if p.is_file()],
        "original_run_root": str(old_root), "original_plan": inherited["parent_plan"],
        "original_inventory": inherited, "external_Q_plus": inherited["external_Q_plus"],
        "materials": materials, "qminus_compute_replay": replay,
        "single_slot_scheduling": scheduling_inventory(parent),
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "old_cost_counted_once": True, "original_closed_slots_replayed": [],
        "new_training_material": [], "new_direction": False, "old_records_rewritten": False}


def prepare(root, *, parent_root, controls=CONTROLS):
    root, old = Path(root).resolve(), Path(parent_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Use a new independent r3 root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the isolated r3 worktree and controls before model work")
    controls = Path(controls).resolve()
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require the finite zero-model r3 controls")
    derived = derive_inventory(old)
    if proof.get("parent_plan") != derived["parent_plan"]:
        raise ValueError("Controls must bind this exact r2 parent inventory")
    parent = read_json(checked(derived["parent_plan"]))
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, source_root=str(SOURCE), source_files=source_files(),
        created_at=time.time(), workers=list(WORKERS), gpu_preference=list(GPU_PREFERENCE), limits=LIMITS,
        parent_run_root=str(old), parent_source_root=derived["parent_source_root"],
        parent_plan=derived["parent_plan"], original_run_root=derived["original_run_root"],
        original_r1_plan=derived["original_plan"], continuation_inventory=derived,
        qminus_compute_replay=derived["qminus_compute_replay"], external_Q_plus=derived["external_Q_plus"],
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        continuation_generation_caps=generation_caps(), single_slot_scheduling=derived["single_slot_scheduling"],
        resource_policy=copy.deepcopy(resource.RESOURCE_POLICY),
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old]),
        automatic_retries=False, automatic_successors=[], old_queues_remain_paused=True,
        explicit_Q_minus_recomputation_limit=1, precise_gradient_checkpoint_resume=False,
        scope="One authorized third complete Q-minus recomputation from unchanged S*4/4 and the sixteen original Q development slots. Original Q-plus stays with its original host; r1/r2 records remain immutable.")
    plan.pop("plan_sha256")
    root.mkdir(parents=True, exist_ok=False)
    for name, ref in derived["materials"].items():
        (root / name).write_bytes(checked(ref).read_bytes())
    plan.pop("parent_supervisor_initial_observation", None)
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
            or plan.get("continuation_generation_caps") != generation_caps()
            or plan.get("single_slot_scheduling") != scheduling_inventory(plan)
            or plan.get("automatic_retries") is not False or plan.get("explicit_Q_minus_recomputation_limit") != 1
            or plan.get("automatic_successors") != []):
        raise ValueError("Frozen r3 source, inventory, resource or scientific budget changed")
    derived = plan["continuation_inventory"]
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    if parent["source"] != derived["parent_source"] or parent["source_root"] != plan["parent_source_root"]:
        raise ValueError("The stopped r2 source identity changed")
    original_source_agreement(parent, SOURCE)
    for ref in derived["parent_artifacts"]:
        checked(ref)
    for name, ref in derived["materials"].items():
        if (root / name).read_bytes() != checked(ref).read_bytes():
            raise ValueError("Scientific material changed: " + name)
    from scripts import software_learning_resume_compute_v050r3 as compute
    if compute.derive_replay_budget(plan["parent_run_root"]) != plan["qminus_compute_replay"]:
        raise ValueError("The two interrupted compute costs or aggregate allowance changed")
    for key in ("inventory", "design", "s_star_checkpoint", "s_star_recipe", "mapper_specification",
                "task_source_manifest", "source_partition", "training_reward", "development_F",
                "generation_budget", "training_budget", "common", "model_references", "original_plan"):
        if plan[key] != parent[key]:
            raise ValueError("Original scientific contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("The frozen r3 protocol changed")
    return plan


def _external_plan(plan):
    return {**plan, "parent_run_root": plan["original_run_root"],
        "continuation_inventory": plan["continuation_inventory"]["original_inventory"]}


def observe_external(plan, *, prior=None, now=None, identity_fn=worker_identity):
    return globals()["prior"].observe_external(_external_plan(plan), prior=prior, now=now, identity_fn=identity_fn)


def _restored_state(owner, root, branch, output):
    plan = read_json(Path(root) / "plan.json")
    if branch == "S_star":
        path = checked(plan["s_star_checkpoint"])
    elif branch == "Q_minus":
        path = Path(root) / "update-Q_minus/actual/checkpoint/checkpoint.json"
    elif branch == "Q_plus":
        receipt = check_seal(read_json(Path(root) / "external-Q_plus-complete.json"))
        if receipt.get("original_worker_identity") != plan["external_Q_plus"]:
            raise ValueError("Use only the exact original Q-plus completion")
        for name in ("checkpoint", "worker_report", "update_report", "training_compute", "composition"):
            checked(receipt[name])
        path = checked(receipt["checkpoint"])
        if path != Path(plan["original_run_root"]) / "update-Q_plus/actual/checkpoint/checkpoint.json":
            raise ValueError("Q-plus cannot be restored from a different worker")
    else:
        raise ValueError("Only the unchanged S* and completed original Q branches are admissible")
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
    result = bind(original._collect, VERSION=VERSION, DEVELOPMENT=DEVELOPMENT,
        worker_units=worker_units, _restored_state=_restored_state)(owner, plan, root, worker, output)
    return {**result, "original_worker": original_worker(worker),
        "single_slot_binding": worker_units(plan, worker)[0], "host_only_slot_split": True}


def _load_owner(plan, output):
    binding = resource.binding_from_env()
    resource.reserve_before_load(output, binding)
    provider = resources(GPU_ORDER)
    dependencies = SimpleNamespace(**{**vars(original.original.inherited), **vars(provider),
        "available_cards": lambda p, s: resource.preload_cards(p, s, binding=binding, worker_pid=os.getpid())})
    return bind(original.original._load_owner, inherited=dependencies)(plan, output)


def runtime_reservation(root, worker):
    """Bind the environment to the actual pre-Popen intent before CUDA work."""
    root = Path(root).resolve()
    binding = resource.binding_from_env()
    plan = read_json(root / "plan.json")
    state = read_json(root / "supervisor.json")["states"][worker]
    launch = read_json(root / worker / "worker-launch.json")
    expected_command = [plan["native_python"], "-m", MODULE, "worker", "--run-root", str(root),
        "--worker", worker, "--output", str(root / worker / "actual")]
    if (state.get("worker") != worker or state.get("attempted") is not True
            or state.get("status") not in {"not_started", "running"}
            or state.get("reservation") != binding or launch.get("reservation") != binding
            or state.get("gpu") != binding["gpu_index"] or launch.get("gpu") != binding["gpu_index"]
            or state.get("gpu_uuid") != binding["gpu_uuid"]
            or state.get("command") != expected_command or launch.get("actual_command") != expected_command
            or launch.get("cwd") != str(SOURCE)
            or launch.get("original_worker") != original_worker(worker)
            or launch.get("planned_units") != worker_units(plan, worker)):
        raise ValueError("Frozen environment, supervisor and actual launch reservation must agree exactly")
    write(root / worker / "reservation-binding-verified.json", {
        "reservation": binding, "worker": worker, "actual_command": expected_command,
        "original_worker": original_worker(worker), "planned_units": worker_units(plan, worker),
        "verified_before_cuda_or_model_load": True, "verified_at": time.time()})
    return binding


def run_worker(root, worker, output):
    from scripts import software_learning_resume_compute_v050r3 as compute
    if worker not in WORKERS:
        raise ValueError("No collection, B, S* development or Q-plus update may be dispatched")
    reservation = runtime_reservation(root, worker)
    def collect(owner, plan, run, name, out):
        with resource.native_cache_context(owner, out, reservation):
            return _collect(owner, plan, run, name, out)
    def update(owner, plan, run, name, out):
        with resource.native_cache_context(owner, out, reservation):
            return compute.update(owner, plan, run, name, out, restored_state=_restored_state)
    return bind(original.run_worker, VERSION=VERSION, WORKERS=WORKERS, UPDATES=UPDATES,
        GPU_ORDER=GPU_ORDER, frozen=frozen, _load_owner=_load_owner, _collect=collect,
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
        from scripts.software_learning_resume_supervisor_v050r3 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
