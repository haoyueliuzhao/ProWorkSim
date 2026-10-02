"""Bounded eight-episode software development with durable original trajectories.

Two first-speaker strata use the same restored 9B endpoint, no updates and no
training support. Each process gets a fresh budget; historical GPU queues are
neither resumed nor extended. Source/task admission is a separate CPU stage.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write

VERSION = "software-development-v0.28"
SOURCE = Path(__file__).resolve().parents[1]
CASES = ("marshmallow-interface-dev", "marshmallow-integration-dev")
MEMBERS = ("member_a", "member_b")
SEEDS = (202610030101, 202610030102)
GPUS = [0, 4, 5, 7]
CAPS = {"worker-0": 10800, "worker-1": 10800}
LIMITS = {
    "max_new_episodes": 8, "max_parallel_model_instances": 2,
    "max_new_actor_steps": 0, "max_new_critic_steps": 0,
    "minimum_free_gpu_mib": 78000, "gpu_capacity_stability_seconds": 60,
    "own_gpu_memory_mib": 81920, "host_rss_per_worker_bytes": 64 * 1024**3,
    "artifact_bytes": 48 * 1024**3, "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600},
    "shutdown_reserve_seconds": 45, "telemetry_grace_seconds": 120,
    "poll_seconds": 5,
}


def assignments():
    result = {}
    for index, first in enumerate(MEMBERS):
        result[f"worker-{index}"] = [
            {"slot_id": f"dev-{case_index}-first-{index}-r{repeat}", "case_id": case,
             "sampling_seed": seed, "first_member": first,
             "role_decision_limits": dict.fromkeys(MEMBERS, 48)}
            for repeat, seed in enumerate(SEEDS) for case_index, case in enumerate(CASES)
        ]
    return result


def available_cards(plan, sample, excluded=()):
    """Admit released capacity; current competing jobs have observed large peaks."""
    if any(sample.get(k, {}).get("returncode") != 0 for k in ("gpus", "processes")):
        return []
    cards, occupied = {}, set()
    try:
        for row in csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True):
            if len(row) != 4:
                return []
            occupied.add(row[0].strip())
        for row in csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True):
            index, uuid, name, free, total, utilization = (s.strip() for s in row)
            index, free, total, utilization = int(index), float(free), float(total), float(utilization)
            if (index in plan["gpu_preference"] and index not in excluded and "A100" in name
                    and uuid not in occupied and 0 <= utilization <= 5 and total >= 81920
                    and plan["limits"]["minimum_free_gpu_mib"] <= free <= total):
                cards[index] = {"index": index, "uuid": uuid, "free_mib": free,
                                "utilization_percent": utilization}
    except (ValueError, TypeError, csv.Error):
        return []
    return [cards[index] for index in plan["gpu_preference"] if index in cards]


def make_plan(data_root, qualification, queue_deadline):
    data_root = Path(data_root).resolve()
    prior = data_root / "runs/domain-v0201-p1-9b/plan.json"
    recipe = data_root / "runs/domain-v025-r1/train_base/actual/resident/owner.json"
    marker = data_root / "runs/domain-v025-r1/checkpoints/base.json"
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(),
        "authorization": "2026-10-03 user requested audit revisions and subsequent experiments with original trajectories retained.",
        "purpose": "interface_development", "inherited_resource_budget": False,
        "gpu_preference": GPUS, "worker_gpu_seconds": CAPS, "total_gpu_seconds": sum(CAPS.values()),
        "limits": LIMITS, "assignments": assignments(), "qualification": reference(qualification),
        "prior_model_plan": reference(prior), "owner_recipe": reference(recipe),
        "checkpoint_marker": reference(marker),
        "queue_deadline_at": queue_deadline,
        "queue_deadline_beijing": datetime.fromtimestamp(queue_deadline, ZoneInfo("Asia/Shanghai")).isoformat(),
        "wall_deadline_at": queue_deadline + max(CAPS.values()) + 300,
        "shared_gpu_capacity_allowed": False, "automatic_retries": False,
        "automatic_successors": [], "model_api_calls": 0,
        "source_scope": "New software/harness protocol; unchanged strict original model recipe and full-state restoration. Not an old SQL result replay.",
    }


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("assignments") != assignments()
            or plan.get("worker_gpu_seconds") != CAPS or plan.get("limits") != LIMITS
            or plan.get("total_gpu_seconds") != sum(CAPS.values())
            or plan.get("gpu_preference") != GPUS
            or plan.get("purpose") != "interface_development"
            or plan.get("inherited_resource_budget") is not False
            or plan.get("shared_gpu_capacity_allowed") is not False
            or plan.get("automatic_retries") is not False
            or plan.get("automatic_successors") != [] or plan.get("model_api_calls") != 0
            or type(plan.get("queue_deadline_at")) not in (int, float)
            or plan.get("wall_deadline_at") != plan["queue_deadline_at"] + max(CAPS.values()) + 300):
        raise ValueError("Freeze the complete new eight-slot zero-update software protocol")
    if check_files:
        if code_identity() != plan["source"] or plan["source"].get("code_dirty") is not False:
            raise ValueError("Run only the clean frozen source bound in this new plan")
        qualification = read_json(checked(plan["qualification"]))
        if (qualification.get("passed") is not True
                or qualification.get("source") != plan["source"]
                or qualification.get("model_calls") != 0
                or qualification.get("max_context_tokens") != 16384
                or qualification.get("max_output_tokens") != 2048):
            raise ValueError("Passed same-source CPU and actual-tokenizer qualification required")
        prior = read_json(checked(plan["prior_model_plan"]))
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        if (prior["runtime_profile"]["candidate_id"] != "qwen3.5-9b"
                or prior["runtime_profile"]["version"] != "candidate-runtime-v0.20.1"
                or recipe["max_length"] != 16384 or recipe["max_output_tokens"] != 2048
                or recipe["credit_assignment"] != "terminal_mc"):
            raise ValueError("Use the declared existing 9B sampling and full learning-state recipe")
        marker = read_json(checked(plan["checkpoint_marker"]))
        saved = read_json(checked(marker["checkpoint"]))
        if saved["actor_steps"] != 3 or saved["critic_steps"] != 3:
            raise ValueError("The declared inherited endpoint is actor/critic 3/3")
        checked(prior["manifest"])
    return plan


class DurableTransport:
    """Persist each original request before generation, including an interrupted call."""
    def __init__(self, inner, directory, window_id):
        self.inner, self.directory, self.window_id = inner, Path(directory), window_id
        self.counter = 0

    def complete(self, request, **kwargs):
        self.counter += 1
        stem = self.directory / f"call-{self.counter:05d}"
        ledger = {"version": VERSION, "window_id": self.window_id, "started_at": time.time(),
                  "request": copy.deepcopy(request), "request_sha256": digest(json_bytes(request)),
                  "transport_options": copy.deepcopy(kwargs), "status": "generation_not_returned"}
        write(stem.with_suffix(".started.json"), ledger)
        try:
            response = self.inner.complete(request, **kwargs)
            ledger.update(status="returned", response=copy.deepcopy(response))
            return response
        except BaseException as error:
            ledger.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            ledger["ended_at"] = time.time()
            write(stem.with_suffix(".finished.json"), ledger)


class CollectionOwner:
    def __init__(self, owner, directory):
        self.owner = owner
        self.transport = DurableTransport(owner.transport, directory, owner.window_id)

    def __getattr__(self, name):
        return getattr(self.owner, name)


def task(output, name, kind):
    write(Path(output) / "task.json", {"task": name, "kind": kind,
                                     "started_at": time.time(), "pid": os.getpid()})


def restore(owner, plan, output):
    from proworksim.online_training import tensor_tree_digest
    marker_path = checked(plan["checkpoint_marker"])
    marker = read_json(marker_path)
    original_sha = reference(marker_path)
    saved = read_json(checked(marker["checkpoint"]))
    restored = owner.restore_checkpoint(marker["directory"])
    actual = tensor_tree_digest(owner._state_bundle(), owner.torch)
    if (restored != saved or actual != saved["state_tensor_digest"]
            or owner.freeze_identity() != marker["actor_identity"]
            or owner.actor_steps != 3 or owner.critic_steps != 3
            or reference(marker_path) != original_sha):
        raise ValueError("Complete actor/critic/optimizer/RNG restoration failed")
    proof = {"old_source": marker["source"], "new_source": code_identity(),
             "marker": original_sha, "checkpoint": marker["checkpoint"],
             "strict_restore": True, "state_tensor_digest": actual,
             "actor_identity": owner.freeze_identity(), "actor_steps": 3, "critic_steps": 3,
             "original_marker_unchanged": True, "optimizer_updates": 0,
             "scope": "New software evaluation only; old critic/role recipe preserved but no software training qualification claimed."}
    write(Path(output) / "restore-proof.json", proof)
    return proof


def run_worker(plan_path, output, worker):
    plan = validate_plan(read_json(plan_path))
    if worker not in CAPS or os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPUS)):
        raise ValueError("Bind one assigned worker to one declared physical GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source, owner = code_identity(), None
    report = {"version": VERSION, "worker": worker, "status": "loading", "source_before": source,
              "plan": reference(plan_path), "slots": plan["assignments"][worker], "rows": [],
              "started_at": time.time(), "new_actor_steps": 0, "new_critic_steps": 0,
              "model_api_calls": 0, "automatic_successors": []}
    write(output / "report.json", report)
    try:
        from proworksim.deterministic_work_v024 import DeterministicCandidateActor
        from proworksim.software_runtime_v028 import collect_software_window
        task(output, "load-9b", "loading")
        prior = read_json(checked(plan["prior_model_plan"]))
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        snapshot = resources()
        write(output / "preload-resources.json", snapshot)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [c["index"] for c in available_cards(plan, snapshot)]:
            raise RuntimeError("Admitted GPU no longer has its required free capacity before loading")
        owner = DeterministicCandidateActor.from_candidate(
            prior["model"], manifest=checked(prior["manifest"]), profile=prior["runtime_profile"],
            recipe=recipe, output=output / "resident")
        task(output, "strict-complete-restore", "boundary")
        report["restore"] = restore(owner, plan, output)
        identity = owner.freeze_identity()
        report["status"] = "running"
        for slot in plan["assignments"][worker]:
            task(output, slot["slot_id"], "episode")
            folder = output / slot["slot_id"]
            guard_before = owner.capture_evaluation_state()
            window_id = "v028-" + slot["slot_id"]
            if owner.begin_window(window_id) != identity:
                raise ValueError("Actor changed across frozen software episodes")
            row = {**copy.deepcopy(slot), "status": "started", "started_at": time.time(),
                   "trajectory_directory": str(folder)}
            report["rows"].append(row)
            write(output / "progress.json", report["rows"])
            write(output / "report.json", report)
            spec = {"window_id": window_id, "harness": "openhands_v16", "usage": "interface_dev",
                    "mode": "frozen_development", "min_class_count": 2,
                    "budget": {"max_slots": 1, "max_model_calls": 96}, "slots": [slot]}
            try:
                entries = collect_software_window(CollectionOwner(owner, folder / "raw-transport"), spec, folder)
                owner.finish_evaluation(entries, folder / "frozen-evaluation")
                guard = owner.finish_evaluation_guard(guard_before)
                write(folder / "evaluation-guard.json", guard)
                if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                    raise ValueError("Frozen learning state or restored RNG changed")
                entry = entries[0]
                row.update(status="closed" if entry["reward"]["eligible"] else "execution_unknown",
                           reward=copy.deepcopy(entry["reward"]), mapping=copy.deepcopy(entry["mapping"]),
                           evaluation_guard=guard, ended_at=time.time())
            except BaseException as error:
                row.update(status="interrupted_or_unassessed", ended_at=time.time(),
                           error={"type": type(error).__name__, "message": str(error)})
                raise
            finally:
                write(output / "progress.json", report["rows"])
                write(output / "report.json", report)
            print(json.dumps({"slot": slot["slot_id"], "status": row["status"],
                              "reward": row.get("reward", {}).get("reward")}), flush=True)
            if row["status"] != "closed":
                report["status"] = "stopped_execution_unknown"
                break
        else:
            report["status"] = "complete"
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps,
                          critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        report["source_unchanged"] = report["source_after"] == source
        report["not_started"] = report["slots"][len(report["rows"]):]
        write(output / "report.json", report)
    return report


def _worker_env(root, name, gpu):
    temporary = root / name / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "PYTHONHASHSEED": "0",
           "PYTHONPATH": str(SOURCE / "src") + os.pathsep + str(SOURCE),
           "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "TOKENIZERS_PARALLELISM": "false", "TMPDIR": str(temporary),
           "TMP": str(temporary), "TEMP": str(temporary)}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    summary = {"version": VERSION, "status": "waiting", "source": code_identity(),
               "plan": reference(plan_path), "observer_pid": os.getpid(), "started_at": time.time(),
               "states": {name: {"worker": name, "status": "not_started", "attempted": False,
                                  "slots": plan["assignments"][name]} for name in CAPS},
               "terminated_gpu_seconds": 0.0, "running_gpu_seconds": 0.0}
    active, logs, guards, stable = {}, {}, {}, {}

    def publish():
        if summary["status"] in {"waiting", "running"}:
            summary["status"] = "running" if active else "waiting"
        summary["observed_at"] = time.time()
        summary["terminated_gpu_seconds"] = sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values())
        summary["running_gpu_seconds"] = sum(time.time() - summary["states"][name]["started_at"] for name in active)
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
        state["closed_slots"] = sum(r.get("status") == "closed" for r in report.get("rows", []))
        logs.pop(name).close()
        write(root / name / "state.json", state)

    with lock(root):
        try:
            while True:
                now = time.time()
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        finish(name, None if process.returncode == 0 else "worker_exit_error")
                waiting = [n for n, s in summary["states"].items() if not s["attempted"] and s["status"] == "not_started"]
                if waiting and now < plan["queue_deadline_at"]:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    occupied = [summary["states"][n]["gpu"] for n in active]
                    ready = available_cards(plan, sample, occupied)
                    stable = {c["index"]: stable.get(c["index"], now) for c in ready}
                    for card in ready:
                        if not waiting or len(active) >= 2:
                            break
                        if time.time() - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if code_identity() != plan["source"]:
                            raise ValueError("Frozen source changed while waiting")
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                            raise RuntimeError("Insufficient data-volume reserve for original trajectories")
                        argv = [sys.executable, "-m", "scripts.software_development_v028", "worker",
                                "--plan", str(plan_path), "--output", str(folder / "actual"), "--worker", name]
                        logs[name] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE, env=_worker_env(root, name, card["index"]),
                                                   stdin=subprocess.DEVNULL, stdout=logs[name], stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                        identity = worker_identity(process.pid)
                        state = summary["states"][name]
                        state.update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
                                     pid=process.pid, process_identity=identity, started_at=started,
                                     gpu_budget_seconds=CAPS[name], command=argv)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(folder / "state.json", state)
                        publish()
                if now >= plan["queue_deadline_at"]:
                    for name in waiting:
                        summary["states"][name]["status"] = "not_started_wait_deadline"
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {name: pool.submit(target_resources, summary["states"][name]["gpu"], worker_pid=p.pid)
                                   for name, p in active.items()}
                        samples = {name: future.result() for name, future in futures.items()}
                    size = artifact_bytes(root)
                    free = shutil.disk_usage(root).free
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            finish(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        measured = samples[name]
                        guard = guards[name].observe(measured, time.time(), process.pid, state["gpu"],
                                                     own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current_task = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason")
                        now = time.time()
                        if now - state["started_at"] >= CAPS[name] - LIMITS["shutdown_reserve_seconds"]:
                            reason = "worker_gpu_time_budget"
                        elif now >= plan["wall_deadline_at"] - LIMITS["shutdown_reserve_seconds"]:
                            reason = "wall_deadline"
                        elif current_task.get("kind") not in LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif now - current_task["started_at"] >= LIMITS["task_seconds"][current_task["kind"]]:
                            reason = "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": measured, "guard": guard, "task": current_task,
                                                     "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(name, reason)
                publish()
                pending = any(not s["attempted"] and s["status"] == "not_started" for s in summary["states"].values())
                if not active and not pending:
                    break
                time.sleep(LIMITS["poll_seconds"])
            summary["status"] = "complete" if all(s["status"] == "complete" for s in summary["states"].values()) else "closed_with_missing_or_interrupted"
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
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=list(CAPS))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--queue-deadline", default="2026-10-04T00:00:00+08:00")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.data_root or not args.qualification:
            parser.error("prepare requires data-root and qualification")
        plan = make_plan(args.data_root, args.qualification, datetime.fromisoformat(args.queue_deadline).timestamp())
        validate_plan(plan)
        write(args.output, plan)
    elif args.mode == "worker":
        if not args.plan or not args.worker:
            parser.error("worker requires plan and worker")
        run_worker(args.plan, args.output, args.worker)
    else:
        if not args.plan:
            parser.error("supervise requires plan")
        supervise(args.plan, args.output)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned supervisor stop")))
    main()
