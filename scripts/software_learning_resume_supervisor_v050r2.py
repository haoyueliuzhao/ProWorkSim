"""Own only new Q-minus/Q-development workers; observe the original Q-plus."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from scripts import software_learning_resume_v050r2 as host
from scripts import software_learning_supervisor_v050 as previous
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_supervisor_v049r2 import request_stop as inherited_stop
from scripts.software_learning_development_resume_v049r2g import resources
from scripts.software_allocation_v037 import live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-original-Q-supervisor-v0.50-r2"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
_resources = resources(host.GPU_ORDER)
allowed_resources, worker_env = _resources.allowed_resources, host.worker_env
task_stop_reason = previous.task_stop_reason


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def initial_states(plan):
    return {name: {"worker": name, "status": "not_started", "attempted": False,
        "planned_slots": [u["slot_id"] for u in host.worker_units(plan, name)]} for name in WORKERS}


def eligible_workers(states, external):
    if set(states) != set(WORKERS):
        raise ValueError("Only one Q-minus recomputation and four original Q-development shards are owned")
    if not isinstance(external, dict) or external.get("status") not in {
            "running", "awaiting_original_host_closure", "awaiting_original_worker_exit", "complete"}:
        return []
    allowed = ["update-Q_minus"]
    if external["status"] == "complete":
        allowed.extend(n for n in host.DEVELOPMENT if n.startswith("dev-Q_plus-"))
    if states["update-Q_minus"]["status"] == "complete":
        allowed.extend(n for n in host.DEVELOPMENT if n.startswith("dev-Q_minus-"))
    return [name for name in WORKERS if name in allowed and states[name]["status"] == "not_started"
        and states[name].get("attempted") is False]


def resident_capacity(active, external):
    count = external.get("resident_count")
    if type(count) is not int or count not in (0, 1):
        raise ValueError("External Q-plus residency must be explicit")
    if external.get("status") != "complete" and count != 1:
        raise ValueError("Pending or running original Q-plus retains one resident place")
    return max(0, LIMITS["max_parallel_model_instances"] - len(active) - count)


def available_cards(plan, sample, excluded=()):
    cards = _resources.available_cards(plan, sample, excluded)
    # Capacity/identity filters are unchanged. The user explicitly prefers GPU4.
    return sorted(cards, key=lambda card: host.GPU_PREFERENCE.index(card["index"]))


def training_stop_reason(plan, worker, receipt, *, now):
    from scripts import software_learning_resume_compute_v050r2 as compute
    if worker != "update-Q_minus" or receipt is None:
        return None
    expected = plan["qminus_compute_replay"]["remaining_seconds"]
    if (not isinstance(receipt, dict) or type(receipt.get("started_at")) not in (int, float)
            or receipt.get("maximum_seconds") != expected
            or receipt.get("replay_budget_sha256") != plan["qminus_compute_replay"]["sha256"]):
        return "training_compute_budget_unbound"
    ended = receipt.get("ended_at")
    return compute.training_stop_reason(receipt, now=now if ended is None else ended)


def request_stop(root, name, process, state, reason):
    if name not in WORKERS or state.get("pid") != process.pid or state.get("worker") != name:
        raise ValueError("This supervisor never owns or signals the original Q-plus process")
    return inherited_stop(root, name, process, state, reason)


def store_external_terminal(root, terminal):
    path = Path(root) / "external-Q_plus-complete.json"
    if path.exists():
        saved = host.check_seal(read(path))
        # The old host can publish its final top-level status after the worker's
        # terminal state. That publication is not a checkpoint/result mutation.
        variable = {"sha256", "original_supervisor_status"}
        if {k: v for k, v in saved.items() if k not in variable} != {k: v for k, v in terminal.items() if k not in variable}:
            raise ValueError("The original Q-plus terminal checkpoint or worker receipt changed")
    else:
        write(path, host.seal(terminal))
    return reference(path)


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(),
        "observer_pid": os.getpid(), "source": plan["source"], "states": initial_states(plan),
        "parent_plan": plan["parent_plan"], "external_Q_plus_binding": plan["external_Q_plus"],
        "external_Q_plus_owned_by_original_host": True,
        "new_worker_cost_excludes_external_observation": True}
    active, logs, guards, stable = {}, {}, {}, {}
    external = None

    def publish():
        summary.update(observed_at=time.time(),
            closed_worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            running_worker_gpu_seconds=sum(time.time() - summary["states"][n]["started_at"] for n in active))
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process = active[name]
        state = summary["states"][name]
        if process.poll() is None:
            request_stop(root, name, process, state, reason)
        process.wait(timeout=15)
        active.pop(name)
        result = read(root / name / "actual/report.json") or {}
        complete = (process.returncode == 0 and reason is None and result.get("status") == "complete"
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and result.get("success_boundary") is True)
        ended = time.time()
        state.update(status="complete" if complete else "stopped", stop_reason=reason,
            exit_code=process.returncode, ended_at=ended, elapsed_gpu_seconds=ended - state["started_at"])
        logs.pop(name).close()
        if not complete:
            normal_pause = (process.returncode == 0 and reason is None
                and result.get("source_before") == result.get("source_after") == plan["source"]
                and result.get("status") in {"measurement_pending", "global_pause", "paused_before_next_slot"})
            kind = result.get("status") if normal_pause else "execution_fault"
            write(root / "mechanism-stops" / (name + "-supervisor.json"), {"kind": kind,
                "reason": reason or result.get("status", "worker_incomplete"), "worker": name,
                "observed_at": ended, "worker_state": copy.deepcopy(state)})
        publish()

    def pause_unopened(reason):
        for state in summary["states"].values():
            if state["status"] == "not_started":
                state.update(status="stopped", stop_reason=reason, elapsed_gpu_seconds=0)

    with lock(root):
        if (root / "supervisor.json").exists():
            raise FileExistsError("A started Q continuation is never automatically replayed")
        publish()
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
                try:
                    external = host.observe_external(plan, prior=external)
                    if external["status"] == "complete":
                        summary["external_Q_plus_terminal"] = store_external_terminal(root, external["terminal"])
                    summary["external_Q_plus_observation"] = copy.deepcopy(external)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    external = {"status": "fault", "resident_count": 1,
                        "excluded_gpu": plan["external_Q_plus"]["gpu"], "error": str(error)}
                    summary["external_Q_plus_observation"] = copy.deepcopy(external)
                    path = root / "mechanism-stops/external-Q_plus.json"
                    if not path.exists():
                        write(path, {"kind": "global_pause", "reason": "external_dependency_failed_or_unbound",
                            "error": str(error), "observed_at": time.time(),
                            "external_process_signalled": False,
                            "original_worker_identity": plan["external_Q_plus"]})
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [reference(path) for path in mechanism_pauses(root)]
                    pause_unopened("unopened_work_paused")
                if all(s["status"] in {"complete", "stopped"} for s in summary["states"].values()):
                    summary["status"] = ("complete" if all(s["status"] == "complete" for s in summary["states"].values())
                        else "closed_with_unknowns")
                    break
                size = sum(artifact_bytes(Path(path)) for path in
                    support.dense._artifact_roots([*plan["prior_artifact_roots"], root]))
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for name in list(active):
                        close(name, "trajectory_storage_reserve")
                    pause_unopened("trajectory_storage_reserve")
                    summary["status"] = "trajectory_storage_reserve"
                    break
                waiting = eligible_workers(summary["states"], external)
                if not waiting:
                    stable.clear()
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    excluded = [summary["states"][n]["gpu"] for n in active]
                    if external.get("excluded_gpu") is not None:
                        excluded.append(external["excluded_gpu"])
                    cards = available_cards(plan, sample, excluded)
                    now = time.time()
                    stable = {c["index"]: stable.get(c["index"], now) for c in cards}
                    for card in cards:
                        if not waiting or resident_capacity(active, external) <= 0:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if mechanism_pauses(root):
                            break
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [plan["native_python"], "-m", host.MODULE, "worker", "--run-root", str(root),
                            "--worker", name, "--output", str(folder / "actual")]
                        logs[name] = (folder / "worker.log").open("x")
                        temporary = folder / "tmp"
                        temporary.mkdir()
                        env = worker_env(plan, card["index"])
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        summary["states"][name].update(attempted=True, launch_intent_at=time.time(),
                            gpu=card["index"], gpu_uuid=card["uuid"], command=argv,
                            source_worktree=str(SOURCE), external_residents_at_launch=external["resident_count"])
                        publish()
                        write(folder / "worker-launch.json", {"actual_command": argv, "cwd": str(SOURCE),
                            "pythonpath": env["PYTHONPATH"], "gpu": card["index"],
                            "external_Q_plus_observation": copy.deepcopy(external),
                            "total_residents_after_launch": len(active) + external["resident_count"] + 1,
                            "recorded_at": time.time(), "phase": "before_popen"})
                        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                            stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", pid=process.pid, process_identity=identity,
                            started_at=time.time())
                        active[name] = process
                        stable.pop(card["index"], None)
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {n: pool.submit(target_resources, summary["states"][n]["gpu"], worker_pid=p.pid)
                            for n, p in active.items()}
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"],
                            own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or live_free_stop_reason(samples[name], state["gpu"])
                        reason = reason or task_stop_reason(current, now=time.time(), rss_bytes=own_rss)
                        compute = read(root / name / "actual/training-compute.json")
                        reason = reason or training_stop_reason(plan, name, compute, now=time.time())
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[name], "guard": guard, "task": current,
                                "training_compute": compute, "rss_bytes": own_rss, "artifact_bytes": size,
                                "volume_free_bytes": free, "external_Q_plus_residents": external.get("resident_count")}) + "\n")
                        if reason:
                            close(name, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(status="interrupted", error={"type": type(error).__name__, "message": str(error)})
            for name in list(active):
                close(name, "supervisor_interrupted")
            write(root / "mechanism-stops/supervisor-exception.json", {"kind": "execution_fault",
                "reason": "supervisor_interrupted_or_failed", "error": summary["error"],
                "observed_at": time.time(), "external_process_signalled": False})
            pause_unopened("unopened_work_paused")
            raise
        finally:
            for stream in logs.values():
                stream.close()
            summary["ended_at"] = time.time()
            publish()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, host.original.received_signal)
    supervise(args.run_root)


if __name__ == "__main__":
    main()
