"""Two explicitly authorized Q recomputations and sixteen original developments."""
from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import signal
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import worker_identity
from proworksim.storage import digest, read_json
from scripts import software_learning_resume_v050r3 as prior
from scripts import software_learning_resources_v050r3 as resource
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.software_learning_resume_v049r1 import original_source_agreement
from scripts.run_ne_v021 import reference, write
from scripts.software_development_v028 import task

VERSION = "software-learning-original-Q-continuation-v0.50-r4"
MODULE = "scripts.software_learning_resume_v050r4"
SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = SOURCE / "docs/experiments/software-learning-v050-resume-r4-protocol.md"
CONTROLS = SOURCE / "docs/experiments/software-learning-v050-resume-r4-cpu-controls.json"
original = prior.original
GPU_ORDER = GPU_PREFERENCE = tuple(range(8))
LIMITS = copy.deepcopy(prior.LIMITS)
UPDATES = ("update-Q_plus", "update-Q_minus")
DEVELOPMENT = prior.DEVELOPMENT
WORKERS = (*UPDATES, *DEVELOPMENT)
MATERIAL_FILES = prior.MATERIAL_FILES
checked, seal, check_seal = original.checked, original.seal, original.check_seal
generation_caps = prior.generation_caps


def source_files():
    files = prior.source_files()
    for path in (PROTOCOL, CONTROLS, Path(__file__),
                 SOURCE / "scripts/software_learning_resume_supervisor_v050r4.py",
                 SOURCE / "scripts/software_learning_resume_compute_v050r4.py",
                 SOURCE / "scripts/software_learning_reservation_adoption_v050r4.py"):
        files[str(path.relative_to(SOURCE))] = digest(path.read_bytes())
    return files


def original_worker(worker):
    if worker in UPDATES:
        return worker
    return prior.original_worker(worker)


def worker_units(plan, worker):
    return [] if worker in UPDATES else prior.worker_units(plan, worker)


def scheduling_inventory(plan):
    return {worker: {"original_worker": original_worker(worker),
        "units": worker_units(plan, worker)} for worker in DEVELOPMENT}


def _terminal_unstarted(root, plan, supervisor):
    states = supervisor.get("states", {})
    if (supervisor.get("status") != "closed_with_unknowns" or not supervisor.get("ended_at")
            or supervisor.get("source") != plan["source"] or set(states) != set(prior.WORKERS)):
        raise ValueError("The zero-worker r3 supervisor must be terminal and exactly bound")
    if worker_identity(supervisor["observer_pid"]).get("alive") is not False:
        raise ValueError("The previous supervisor must have relinquished ownership")
    for name, state in states.items():
        if (state.get("status") != "stopped" or state.get("attempted") is not False
                or state.get("stop_reason") != "unopened_work_paused"
                or state.get("elapsed_gpu_seconds") != 0 or (root / name).exists()):
            raise ValueError("Every r3 worker must remain unstarted with zero worker cost")


def derive_inventory(parent_root, *, source_root=SOURCE, check_source=True, replay_budget=None):
    from scripts import software_learning_resume_compute_v050r4 as compute

    root = Path(parent_root).resolve()
    parent = check_seal(read_json(root / "plan.json"), "plan_sha256")
    if (parent.get("version") != prior.VERSION or parent.get("workers") != list(prior.WORKERS)
            or parent.get("limits") != prior.LIMITS or parent.get("automatic_retries") is not False):
        raise ValueError("Require the exact independently frozen r3 continuation")
    supervisor = read_json(root / "supervisor.json")
    _terminal_unstarted(root, parent, supervisor)
    inherited = parent["continuation_inventory"]
    r2_root = Path(parent["parent_run_root"]).resolve()
    r2 = check_seal(read_json(checked(parent["parent_plan"])), "plan_sha256")
    r1_root = Path(parent["original_run_root"]).resolve()
    r1 = check_seal(read_json(checked(parent["original_r1_plan"])), "plan_sha256")
    if (r2_root / "plan.json" != Path(parent["parent_plan"]["path"]).resolve()
            or r1_root != Path(r2["parent_run_root"]).resolve()
            or r1["source"] != inherited["original_inventory"]["parent_source"]):
        raise ValueError("The original r1/r2 provenance chain changed")
    # Closed r1 collection/B/S* and B-development evidence is immutable. The old
    # Q-plus is now a stopped historical attempt, never an external dependency.
    old_supervisor = read_json(r1_root / "supervisor.json")
    for name, receipt in inherited["original_inventory"]["closed_parent_workers"].items():
        if old_supervisor["states"][name] != receipt["state"]:
            raise ValueError("An original closed or never-started worker changed: " + name)
        for key in ("report", "host_stop_action"):
            if key in receipt:
                checked(receipt[key])
    prior._dead(old_supervisor["states"]["update-Q_plus"], "original stopped Q-plus")
    prior._dead(old_supervisor["states"]["update-Q_minus"], "original stopped Q-minus")
    prior._dead(read_json(r2_root / "supervisor.json")["states"]["update-Q_minus"], "second stopped Q-minus")
    for ref in inherited["parent_artifacts"]:
        checked(ref)
    materials = {}
    for name in MATERIAL_FILES:
        for old in (r1_root, r2_root):
            if (root / name).read_bytes() != (old / name).read_bytes():
                raise ValueError("Original training material changed: " + name)
        materials[name] = reference(root / name)
    replay = compute.derive_replay_budget(root) if replay_budget is None else check_seal(replay_budget)
    if (replay["allocation"]["parent_plan"] != reference(root / "plan.json")
            or replay["allocation"]["parent_supervisor"] != reference(root / "supervisor.json")):
        raise ValueError("The compute proof must bind this terminal r3 inventory")
    return {"version": VERSION, "parent_run_root": str(root), "parent_plan": reference(root / "plan.json"),
        "parent_source": copy.deepcopy(parent["source"]), "parent_source_root": parent["source_root"],
        "parent_supervisor": reference(root / "supervisor.json"),
        "parent_artifacts": [reference(p) for p in sorted(root.rglob("*")) if p.is_file()],
        "historical_artifacts": [reference(old / "supervisor.json") for old in (r1_root, r2_root)],
        "original_run_root": str(r1_root), "original_r1_plan": parent["original_r1_plan"],
        "historical_inventory": copy.deepcopy(inherited), "materials": materials,
        "q_compute_replay": replay, "single_slot_scheduling": scheduling_inventory(parent),
        "source_agreement": original_source_agreement(parent, source_root) if check_source else None,
        "old_cost_counted_once": True, "parent_new_gpu_worker_seconds": 0,
        "original_closed_slots_replayed": [], "new_training_material": [],
        "new_direction": False, "old_records_rewritten": False, "external_Q_plus_dependency": False}


def prepare(root, *, parent_root, lease_root, controls=CONTROLS):
    from scripts import software_learning_reservation_adoption_v050r4 as adoption

    root, old = Path(root).resolve(), Path(parent_root).resolve()
    if root.exists() or root in old.parents or old in root.parents:
        raise FileExistsError("Use a new independent r4 root")
    source = code_identity()
    if source.get("code_dirty") is not False:
        raise ValueError("Commit the isolated r4 worktree and controls before model work")
    controls = Path(controls).resolve()
    proof = check_seal(read_json(controls))
    if (proof.get("passed") is not True or any(proof.get(k) != 0 for k in
            ("new_model_calls", "new_gpu_workers", "new_backward_calls"))):
        raise ValueError("Require the finite zero-model r4 controls")
    boundary = read_json(checked(proof["compute_boundary_proof"]))
    if boundary.get("status") != "passed" or boundary["budget"] != proof["q_compute_replay"]:
        raise ValueError("Reuse only the successful same-source zero-model compute proof")
    derived = derive_inventory(old, replay_budget=proof["q_compute_replay"])
    if proof.get("parent_plan") != derived["parent_plan"]:
        raise ValueError("Controls must bind this exact r3 parent inventory")
    parent = read_json(checked(derived["parent_plan"]))
    lease = adoption.inspect_lease(lease_root, source_root=SOURCE, run_root=root)
    plan = copy.deepcopy(parent)
    plan.update(version=VERSION, source=source, source_root=str(SOURCE), source_files=source_files(),
        created_at=time.time(), workers=list(WORKERS), gpu_preference=list(GPU_PREFERENCE), limits=LIMITS,
        parent_run_root=str(old), parent_source_root=derived["parent_source_root"],
        parent_plan=derived["parent_plan"], original_run_root=derived["original_run_root"],
        original_r1_plan=derived["original_r1_plan"], continuation_inventory=derived,
        q_compute_replay=derived["q_compute_replay"], gpu2_lease=lease,
        resume_cpu_controls=reference(controls), resume_protocol=reference(PROTOCOL),
        continuation_generation_caps=generation_caps(), single_slot_scheduling=derived["single_slot_scheduling"],
        resource_policy=copy.deepcopy(resource.RESOURCE_POLICY),
        prior_artifact_roots=original.original.inherited.support.dense._artifact_roots([*parent["prior_artifact_roots"], old, Path(lease_root)]),
        automatic_retries=False, automatic_successors=[], old_queues_remain_paused=True,
        explicit_Q_recomputation_limits={"Q_plus": 1, "Q_minus": 1}, precise_gradient_checkpoint_resume=False,
        scope="One authorized recomputation per Q branch from unchanged S*4/4 and the sixteen original development slots; adopt the exact pre-reserved GPU2 process, retain all old attempts unchanged.")
    for key in ("plan_sha256", "parent_supervisor_initial_observation", "external_Q_plus", "qminus_compute_replay", "explicit_Q_minus_recomputation_limit"):
        plan.pop(key, None)
    root.mkdir(parents=True, exist_ok=False)
    for name, ref in derived["materials"].items():
        (root / name).write_bytes(checked(ref).read_bytes())
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
            or plan.get("automatic_retries") is not False
            or plan.get("explicit_Q_recomputation_limits") != {"Q_plus": 1, "Q_minus": 1}
            or plan.get("automatic_successors") != [] or "external_Q_plus" in plan):
        raise ValueError("Frozen r4 source, inventory, resource or scientific budget changed")
    derived = plan["continuation_inventory"]
    parent = check_seal(read_json(checked(plan["parent_plan"])), "plan_sha256")
    if parent["source"] != derived["parent_source"] or parent["source_root"] != plan["parent_source_root"]:
        raise ValueError("The stopped r3 source identity changed")
    original_source_agreement(parent, SOURCE)
    for ref in (*derived["parent_artifacts"], *derived["historical_artifacts"]):
        checked(ref)
    for name, ref in derived["materials"].items():
        if (root / name).read_bytes() != checked(ref).read_bytes():
            raise ValueError("Scientific material changed: " + name)
    check_seal(plan["q_compute_replay"])
    if plan["q_compute_replay"] != derived["q_compute_replay"]:
        raise ValueError("The sealed dual-branch compute allocation changed")
    for key in ("inventory", "design", "s_star_checkpoint", "s_star_recipe", "mapper_specification",
                "task_source_manifest", "source_partition", "training_reward", "development_F",
                "generation_budget", "training_budget", "common", "model_references", "original_plan"):
        if plan[key] != parent[key]:
            raise ValueError("Original scientific contract changed: " + key)
    checked(plan["resume_cpu_controls"])
    if plan["resume_protocol"] != reference(PROTOCOL):
        raise ValueError("The frozen r4 protocol changed")
    return plan


def _restored_state(owner, root, branch, output):
    plan = read_json(Path(root) / "plan.json")
    if branch == "S_star":
        path = checked(plan["s_star_checkpoint"])
    elif branch in ("Q_plus", "Q_minus"):
        path = Path(root) / ("update-" + branch) / "actual/checkpoint/checkpoint.json"
    else:
        raise ValueError("Only unchanged S* and this run's complete Q branches are admissible")
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


_load_owner = prior._load_owner


def runtime_reservation(root, worker):
    from scripts import software_learning_reservation_adoption_v050r4 as adoption

    root = Path(root).resolve()
    binding = resource.binding_from_env()
    plan = read_json(root / "plan.json")
    state = read_json(root / "supervisor.json")["states"][worker]
    launch = read_json(root / worker / "worker-launch.json")
    expected = [plan["native_python"], "-m", MODULE, "worker", "--run-root", str(root),
        "--worker", worker, "--output", str(root / worker / "actual")]
    adopted = launch.get("launch_mode") == "adopted_reservation"
    if adopted:
        lease = plan["gpu2_lease"]
        adoption.validate_owner_records(lease)
        observed = adoption.observe_lease(lease)
        expected = lease["actual_command"]
        if (worker != "update-Q_plus" or os.getpid() != lease["pid"]
                or state.get("pid") != lease["pid"] or state.get("lease_binding") != lease
                or launch.get("lease_binding") != lease or state.get("status") != "running"
                or launch.get("cwd") != lease["launch_cwd"]
                or launch.get("source_worktree") != str(SOURCE)
                or observed.get("status") != "running" or observed.get("phase") != "worker_entry"
                or type(observed.get("worker_entry_at")) not in (int, float)):
            raise ValueError("The adopted worker must be the exact owned pre-reservation process")
    elif worker == "update-Q_plus" or launch.get("cwd") != str(SOURCE):
        raise ValueError("Q-plus requires its original GPU2 pre-reservation process")
    if (state.get("worker") != worker or state.get("attempted") is not True
            or state.get("status") not in {"not_started", "running"}
            or state.get("reservation") != binding or launch.get("reservation") != binding
            or state.get("gpu") != binding["gpu_index"] or launch.get("gpu") != binding["gpu_index"]
            or state.get("gpu_uuid") != binding["gpu_uuid"]
            or state.get("command") != expected or launch.get("actual_command") != expected
            or launch.get("original_worker") != original_worker(worker)
            or launch.get("planned_units") != worker_units(plan, worker)):
        raise ValueError("Frozen environment, supervisor and actual launch reservation must agree exactly")
    write(root / worker / "reservation-binding-verified.json", {
        "reservation": binding, "worker": worker, "actual_command": expected,
        "launch_mode": "adopted_reservation" if adopted else "popen",
        "original_worker": original_worker(worker), "planned_units": worker_units(plan, worker),
        "verified_before_model_load": True, "verified_at": time.time()})
    return binding


def run_worker(root, worker, output):
    from scripts import software_learning_resume_compute_v050r4 as compute

    if worker not in WORKERS:
        raise ValueError("Only two Q updates and sixteen original developments may be dispatched")
    # The GPU2 bootstrap calls this function directly, without CLI main().
    signal.signal(signal.SIGTERM, original.received_signal)
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
    parser.add_argument("--lease-root", type=Path)
    parser.add_argument("--controls", type=Path, default=CONTROLS)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, original.received_signal)
    if args.command == "prepare":
        if args.parent_root is None or args.lease_root is None:
            parser.error("prepare requires --parent-root and --lease-root")
        prepare(args.run_root, parent_root=args.parent_root, lease_root=args.lease_root, controls=args.controls)
    elif args.command == "supervise":
        from scripts.software_learning_resume_supervisor_v050r4 import supervise
        supervise(args.run_root)
    else:
        if args.worker is None or args.output is None:
            parser.error("worker requires --worker and --output")
        run_worker(args.run_root, args.worker, args.output)


if __name__ == "__main__":
    main()
