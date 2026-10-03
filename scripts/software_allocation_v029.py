"""One finite source-separated current-policy B/G/I allocation experiment.

Eight current-policy sqlparse slots precede a conditional, complete probe grid.
No support means no update. Every probe starts at the same full checkpoint;
only actual schema work selects weights. TextFSM never participates in selection.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.experience_allocation_v027 import (
    bind_allocation, bind_candidate, development_receipt, freeze_allocation_plan,
    select_allocation,
)
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write
from scripts.software_development_v028 import DurableTransport, available_cards, restore, task

VERSION = "software-allocation-v0.29"
SOURCE = Path(__file__).resolve().parents[1]
MEMBERS = ("member_a", "member_b")
SUPPORT_WINDOW = "v029-sqlparse-current-policy-8"
LIMITS = {
    "max_parallel_model_instances": 8, "minimum_free_gpu_mib": 78000,
    "gpu_capacity_stability_seconds": 60, "own_gpu_memory_mib": 81920,
    "host_rss_per_worker_bytes": 64 * 1024**3,
    "artifact_bytes": 128 * 1024**3, "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600, "training": None},
    "poll_seconds": 5,
}


def slots(case_id, prefix, seeds):
    return [{"slot_id": f"{prefix}-{i}", "case_id": case_id, "sampling_seed": seed,
             "first_member": "member_a", "role_decision_limits": dict.fromkeys(MEMBERS, 48)}
            for i, seed in enumerate(seeds)]


def inventories():
    return {
        "support": slots("sqlparse-comparison-records", "support", range(202610290101, 202610290109)),
        "development": slots("schema-catalog", "schema", range(202610290201, 202610290205)),
        "confirmation": slots("textfsm-record-items", "textfsm", range(202610290301, 202610290305)),
        "successor": slots("sqlparse-comparison-records", "successor", range(202610290401, 202610290403)),
    }


def make_plan(data_root, qualification):
    root = Path(data_root).resolve()
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(),
        "authorization": "User requested v0.29 audit revision and experiments, then explicitly authorized GPUs 0-7.",
        "gpu_preference": list(range(8)), "limits": copy.deepcopy(LIMITS),
        "total_gpu_seconds": None, "worker_gpu_seconds": None, "wall_deadline_at": None,
        "queue_deadline_at": None, "automatic_retries": False, "inventories": inventories(),
        "support_window_id": SUPPORT_WINDOW, "min_class_count": 2,
        "eligible_block_order": list(MEMBERS), "max_configured_blocks": 1,
        "max_unique_trial_updates": 19, "max_formal_updates": 3,
        "max_development_episodes": 76, "max_total_episodes": 102,
        "unknown_development_rule": "retain_unknown_and_stop_before_formal_updates",
        "qualification": reference(qualification),
        "prior_model_plan": reference(root / "runs/domain-v0201-p1-9b/plan.json"),
        "owner_recipe": reference(root / "runs/domain-v025-r1/train_base/actual/resident/owner.json"),
        "checkpoint_marker": reference(root / "runs/domain-v025-r1/checkpoints/base.json"),
        "historical_cost": {"full_window_update_gpu_seconds": 41613.2078435421,
                            "decisions": 283, "output_tokens": 92010,
                            "scope": "Measured older v025 update, not a forecast for this software window."},
    }


def validate_plan(plan):
    from proworksim.software_runtime_v029 import _validate_window
    if (plan.get("version") != VERSION or plan.get("source") != code_identity()
            or plan.get("inventories") != inventories() or plan.get("limits") != LIMITS
            or plan.get("gpu_preference") != list(range(8))
            or plan.get("support_window_id") != SUPPORT_WINDOW or plan.get("min_class_count") != 2
            or plan.get("eligible_block_order") != list(MEMBERS) or plan.get("max_configured_blocks") != 1
            or plan.get("max_unique_trial_updates") != 19 or plan.get("max_formal_updates") != 3
            or plan.get("max_development_episodes") != 76 or plan.get("max_total_episodes") != 102
            or plan.get("automatic_retries") is not False
            or plan.get("unknown_development_rule") != "retain_unknown_and_stop_before_formal_updates"
            or any(plan.get(key) is not None for key in ("total_gpu_seconds", "worker_gpu_seconds",
                                                        "wall_deadline_at", "queue_deadline_at"))):
        raise ValueError("Frozen v029 protocol, source, finite inventory or resource declaration differs")
    qualification = read_json(checked(plan["qualification"]))
    if (qualification.get("passed") is not True or qualification.get("source") != plan["source"]
            or qualification.get("model_calls") != 0):
        raise ValueError("Require same-source CPU qualification before model work")
    for key in ("prior_model_plan", "owner_recipe", "checkpoint_marker"):
        checked(plan[key])
    for name, usage, mode in (("support", "policy_training", "current_policy_collection"),
                              ("development", "contribution_development", "frozen_development"),
                              ("confirmation", "independent_confirmation", "frozen_evaluation"),
                              ("successor", "policy_training", "successor_work")):
        _validate_window(window_spec(name, plan["inventories"][name], usage, mode))
    return plan


def window_spec(window_id, rows, usage, mode):
    return {"window_id": window_id, "harness": "openhands_v16", "usage": usage, "mode": mode,
            "min_class_count": 2, "slots": copy.deepcopy(rows),
            "budget": {"max_slots": len(rows), "max_model_calls": 96 * len(rows)}}


class RoutedTransport:
    """Workers constructed in advance share this stable, slot-bound transport."""
    inner = None

    def complete(self, request, **kwargs):
        if self.inner is None:
            raise RuntimeError("No declared software slot is active")
        return self.inner.complete(request, **kwargs)


class CollectionOwner:
    def __init__(self, owner):
        from proworksim.software_context_v028 import VERSION as CONTEXT_POLICY
        self.owner = owner
        self.transport = RoutedTransport()
        self.software_context_policy = CONTEXT_POLICY
        self.software_context_projection = CONTEXT_POLICY

    def __getattr__(self, name):
        return getattr(self.owner, name)


def collect(owner, spec, output, worker_output):
    from proworksim.software_context_v028 import SoftwareContextTransport
    from proworksim.software_runtime_v029 import collect_software_window
    facade = CollectionOwner(owner)
    before = owner.capture_evaluation_state()
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in (
        "recipe", "inference_profile", "base_identity", "software_learning_binding")}
    owner.begin_window(spec["window_id"])

    def boundary(event, row, folder):
        if event == "started":
            task(worker_output, row["slot_id"], "episode")
            directory = folder / "raw-transport"
            facade.transport.inner = DurableTransport(
                SoftwareContextTransport(owner, directory / "context-projections"), directory, owner.window_id)
        else:
            task(worker_output, "close-" + row["slot_id"], "boundary")
            facade.transport.inner = None

    entries = collect_software_window(facade, spec, output, on_slot=boundary)
    owner.finish_evaluation(entries, output / "frozen-collection-close")
    guard = owner.finish_evaluation_guard(before)
    guard["software_binding_unchanged"] = all(getattr(owner, key) == value for key, value in binding.items())
    guard["software_binding_before_sha256"] = digest(json_bytes(binding))
    write(output / "evaluation-guard.json", guard)
    if not guard["learning_unchanged"] or not guard["rng_restored_exactly"] or not guard["software_binding_unchanged"]:
        raise ValueError("Collection changed the common learning state or failed to restore RNG")
    return entries


def require_actual_update(report):
    if (report.get("status") != "updated" or report.get("actor_optimizer_steps") != 1
            or report.get("critic_optimizer_steps") not in (0, 1)):
        raise ValueError("Candidate requires an actual complete actor/critic update; preserve the zero-step or failed report and stop")


def support_gate(entries, declaration, records):
    from proworksim.software_learning_v029 import allocation_gate
    return allocation_gate(entries, declaration, records)


def allocation_plan(plan, gate, common):
    rows = plan["inventories"]
    development = {
        "purpose": "contribution_development", "dataset_id": "schema-catalog",
        "split_manifest_sha256": digest(json_bytes(rows)),
        "initial_state_sha256": common["state_tensor_digest"],
        "training_rng_sha256": common["training_rng_sha256"],
        "units": [{"unit_id": row["slot_id"], "seed": row["sampling_seed"], "weight": 1.0}
                  for row in rows["development"]],
        "independent_unit_ids": [row["slot_id"] for row in rows["confirmation"]],
        "provenance": "current_model_development",
    }
    return freeze_allocation_plan(gate["supports_by_xi"], eligible_blocks=gate["eligible_blocks"],
        development=development, budget={"max_trial_updates_per_method": 15,
        "max_development_evaluations_per_method": 60, "formal_updates_per_method": 1})


def run_worker(plan_path, run_root, worker, output):
    from proworksim.deterministic_work_v024 import DeterministicCandidateActor
    from proworksim.online_training import tensor_tree_digest
    from proworksim.software_learning_v029 import (
        migrate_software_owner, restore_common, update_software_window,
    )
    plan = validate_plan(read_json(plan_path))
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, plan["gpu_preference"])):
        raise ValueError("A worker requires exactly one declared physical GPU")
    output, root = Path(output).resolve(), Path(run_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"version": VERSION, "worker": worker, "status": "loading", "started_at": time.time(),
              "source_before": code_identity(), "new_actor_steps": 0, "new_critic_steps": 0}
    write(output / "report.json", report)
    owner = None
    try:
        task(output, "load-9b", "loading")
        prior = read_json(checked(plan["prior_model_plan"]))
        original = read_json(checked(plan["owner_recipe"]))["recipe"]
        snapshot = resources()
        write(output / "preload-resources.json", snapshot)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [c["index"] for c in available_cards(plan, snapshot)]:
            raise RuntimeError("Assigned GPU capacity changed before model loading")
        owner = DeterministicCandidateActor.from_candidate(prior["model"], manifest=checked(prior["manifest"]),
            profile=prior["runtime_profile"], recipe=original,
            output=output / "resident")
        task(output, "common-state", "boundary")
        if worker == "support":
            restore(owner, plan, output)
            migration = migrate_software_owner(owner)
            write(output / "software-critic-migration.json", migration)
            checkpoint = owner.save_checkpoint(output / "common-state")
            bundle = owner._state_bundle()
            common = {**checkpoint, "directory": str(output / "common-state"),
                      "recipe": owner.recipe,
                      "training_rng_sha256": tensor_tree_digest(
                          {"cpu": bundle["rng_cpu"], "cuda": bundle["rng_cuda"]}, owner.torch)}
            write(output / "common.json", common)
            entries = collect(owner, window_spec(SUPPORT_WINDOW, plan["inventories"]["support"],
                              "policy_training", "current_policy_collection"), output / "collection", output)
            declaration = read_json(output / "collection/declaration.json")
            records = read_json(output / "collection/records.json")
            gate = support_gate(entries, declaration, records)
            write(output / "support-gate.json", gate)
            report["support_status"] = gate["status"]
            if gate["status"] == "ready":
                allocation = allocation_plan(plan, gate, common)
                write(output / "allocation-plan.json", allocation)
                report["unique_candidates"] = len(allocation["candidates"])
        else:
            support = root / "support/actual"
            common = read_json(support / "common.json")
            migrate_software_owner(owner, output / "software-critic-migration.json", expected_steps=None)
            restored = restore_common(owner, common["directory"], window_id=SUPPORT_WINDOW)
            bundle = owner._state_bundle()
            restored["training_rng_sha256"] = tensor_tree_digest(
                {"cpu": bundle["rng_cpu"], "cuda": bundle["rng_cuda"]}, owner.torch)
            if (restored["state_sha256"] != common["state_tensor_digest"]
                    or restored["actor_identity"] != common["actor_identity"]
                    or restored["training_rng_sha256"] != common["training_rng_sha256"]):
                raise ValueError("Candidate full common state restoration differs")
            write(output / "common-restore.json", {**restored, "common": reference(support / "common.json")})
            entries = read_json(support / "collection/entries.json")
            declaration = read_json(support / "collection/declaration.json")
            records = read_json(support / "collection/records.json")
            allocation = read_json(support / "allocation-plan.json")
            formal = worker.startswith("formal-")
            key = worker.removeprefix("formal-") if formal else worker.removeprefix("trial-")
            selection = read_json(root / "selection.json") if formal else None
            composition = (bind_allocation(entries, declaration, records, allocation, selection, method=key)
                           if formal else bind_candidate(entries, declaration, records, allocation, key))
            task(output, "full-window-update-" + worker, "training")
            update = update_software_window(owner, entries, output / "update", declaration=declaration,
                request_evidence_root=support / "collection", composition=composition)
            report.update(new_actor_steps=update["actor_optimizer_steps"],
                          new_critic_steps=update["critic_optimizer_steps"])
            require_actual_update(update)
            task(output, "updated-state", "boundary")
            checkpoint = owner.save_checkpoint(output / "updated-state")
            report["updated_actor_identity"] = checkpoint["actor_identity"]
            if formal:
                for name, usage, mode in (("confirmation", "independent_confirmation", "frozen_evaluation"),
                                          ("successor", "policy_training", "successor_work")):
                    result = collect(owner, window_spec(f"v029-{worker}-{name}", plan["inventories"][name],
                                     usage, mode), output / name, output)
                    report[name] = [{"slot_id": entry["slot_id"], "reward": entry["reward"]} for entry in result]
            else:
                result = collect(owner, window_spec("v029-" + worker + "-schema", plan["inventories"]["development"],
                                 "contribution_development", "frozen_development"), output / "development", output)
                utilities = [entry["reward"].get("reward") if entry["reward"]["eligible"] else None for entry in result]
                receipt = development_receipt(allocation, key, utilities, provenance="current_model_development")
                write(output / "development-receipt.json", receipt)
                report["utilities"] = utilities
        report["status"] = "complete"
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(actor_steps=owner.actor_steps, critic_steps=owner.critic_steps,
                          final_actor_identity=owner._make_identity())
        report.update(ended_at=time.time(), source_after=code_identity())
        write(output / "report.json", report)
    return report


def worker_env(root, name, gpu):
    temporary = root / name / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "PYTHONHASHSEED": "0",
           "PYTHONPATH": str(SOURCE / "src") + os.pathsep + str(SOURCE),
           "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "TOKENIZERS_PARALLELISM": "false", "TMPDIR": str(temporary),
           "TMP": str(temporary), "TEMP": str(temporary)}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def next_stage(stage, states, root):
    """Pure finite DAG advancement after every worker in the current stage closes."""
    if any(state["status"] not in {"complete", "stopped"} for state in states.values()):
        raise ValueError("Cannot advance an unfinished stage")
    if any(state["status"] != "complete" for state in states.values()):
        return "incomplete_execution", []
    support = Path(root) / "support/actual"
    if stage == "support":
        gate = read_json(support / "support-gate.json")
        if gate["status"] != "ready":
            return gate["status"], []
        return "baseline_trial", ["trial-B"]
    if stage == "baseline_trial":
        receipt = read_json(Path(root) / "trial-B/actual/development-receipt.json")
        if any(outcome["utility"] is None for outcome in receipt["outcomes"]):
            return "incomplete_development", []
        allocation = read_json(support / "allocation-plan.json")
        return "trials", ["trial-" + cid for cid in allocation["candidates"] if cid != "B"]
    if stage == "trials":
        allocation = read_json(support / "allocation-plan.json")
        receipts = [read_json(Path(root) / ("trial-" + cid) / "actual/development-receipt.json")
                    for cid in allocation["candidates"]]
        selection = select_allocation(allocation, receipts)
        write(Path(root) / "selection.json", selection)
        if any(outcome["utility"] is None for receipt in receipts for outcome in receipt["outcomes"]):
            return "incomplete_development", []
        return "formal", ["formal-" + method for method in ("B", "G", "I")]
    if stage == "formal":
        return "complete", []
    raise ValueError("Unknown finite experiment stage")


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    summary = {"version": VERSION, "status": "waiting", "stage": "support", "states": {},
               "started_at": time.time(), "observer_pid": os.getpid(), "source": code_identity()}
    active, logs, guards, stable = {}, {}, {}, {}
    stage_names = ["support"]

    def add(names):
        for name in names:
            summary["states"][name] = {"worker": name, "status": "not_started", "attempted": False}

    def publish():
        summary["observed_at"] = time.time()
        summary["worker_gpu_seconds"] = sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values())
        summary["running_gpu_seconds"] = sum(time.time() - summary["states"][n]["started_at"] for n in active)
        write(root / "supervisor.json", summary)

    def finish(name, reason):
        process = active.pop(name)
        if process.poll() is None:
            stop_owned(process)
        process.wait(timeout=15)
        state = summary["states"][name]
        report = read(root / name / "actual/report.json") or {}
        state.update(ended_at=time.time(), exit_code=process.returncode, stop_reason=reason,
                     status="complete" if process.returncode == 0 and reason is None and report.get("status") == "complete" else "stopped")
        state["elapsed_gpu_seconds"] = state["ended_at"] - state["started_at"]
        logs.pop(name).close()
        write(root / name / "state.json", state)

    add(stage_names)
    with lock(root):
        try:
            while True:
                now = time.time()
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        finish(name, None if process.returncode == 0 else "worker_exit_error")
                stage_states = {name: summary["states"][name] for name in stage_names}
                if all(s["status"] in {"complete", "stopped"} for s in stage_states.values()):
                    summary["stage"], stage_names = next_stage(summary["stage"], stage_states, root)
                    if not stage_names:
                        summary["status"] = summary["stage"]
                        break
                    add(stage_names)
                waiting = [n for n in stage_names if summary["states"][n]["status"] == "not_started"]
                if waiting:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    ready = available_cards(plan, sample, [summary["states"][n]["gpu"] for n in active])
                    stable = {c["index"]: stable.get(c["index"], now) for c in ready}
                    for card in ready:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if code_identity() != plan["source"]:
                            raise ValueError("Frozen source changed while queued")
                        if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                            raise RuntimeError("Insufficient storage reserve for original trajectories")
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [sys.executable, "-m", "scripts.software_allocation_v029", "worker", "--plan", str(plan_path),
                                "--run-root", str(root), "--output", str(folder / "actual"), "--worker", name]
                        logs[name] = (folder / "worker.log").open("x")
                        process = subprocess.Popen(argv, cwd=SOURCE, env=worker_env(root, name, card["index"]),
                            stdin=subprocess.DEVNULL, stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", attempted=True, gpu=card["index"],
                            gpu_uuid=card["uuid"], pid=process.pid, process_identity=identity, started_at=time.time(), command=argv)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(folder / "state.json", summary["states"][name])
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        futures = {name: pool.submit(target_resources, summary["states"][name]["gpu"], worker_pid=p.pid)
                                   for name, p in active.items()}
                        samples = {name: future.result() for name, future in futures.items()}
                    size, free = artifact_bytes(root), shutil.disk_usage(root).free
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            finish(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"],
                                                     own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss, reason = rss(process.pid), guard.get("stop_reason")
                        cap = LIMITS["task_seconds"].get(current.get("kind"))
                        if current.get("kind") not in LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif cap is not None and time.time() - current["started_at"] >= cap:
                            reason = "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[name], "guard": guard, "task": current,
                                                     "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(name, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="supervisor_interrupted", error={"type": type(error).__name__, "message": str(error)})
            for name in list(active):
                finish(name, "supervisor_interrupted")
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--worker")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.data_root or not args.qualification:
            parser.error("prepare requires --data-root and --qualification")
        write(args.output, validate_plan(make_plan(args.data_root, args.qualification)))
    elif args.mode == "worker":
        if not args.plan or not args.run_root or not args.worker:
            parser.error("worker requires --plan, --run-root and --worker")
        run_worker(args.plan, args.run_root, args.worker, args.output)
    else:
        if not args.plan:
            parser.error("supervise requires --plan")
        supervise(args.plan, args.output)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned supervisor stop")))
    main()
