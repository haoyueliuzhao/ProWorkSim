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
from scripts import software_learning_resume_v050r3 as host
from scripts import software_learning_supervisor_v050 as previous
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_supervisor_v049r2 import request_stop as inherited_stop
from scripts.software_learning_development_resume_v049r2g import resources
from scripts import software_learning_resources_v050r3 as resource
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-original-Q-supervisor-v0.50-r3"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
_resources = resources(host.GPU_ORDER)
allowed_resources, worker_env = _resources.allowed_resources, host.worker_env


def task_stop_reason(current, *, now, rss_bytes):
    # Pure allocation waiting occurs before the model is loaded. It cannot
    # consume an episode or training interval and never retries model work.
    if current.get("kind") == "reservation_wait":
        return "host_memory_budget" if rss_bytes > LIMITS["host_rss_per_worker_bytes"] else None
    return previous.task_stop_reason(current, now=now, rss_bytes=rss_bytes)


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def initial_states(plan):
    return {name: {"worker": name, "status": "not_started", "attempted": False,
        "planned_slots": [u["slot_id"] for u in host.worker_units(plan, name)],
        "original_worker": host.original_worker(name)} for name in WORKERS}


def eligible_workers(states, external):
    if set(states) != set(WORKERS):
        raise ValueError("Only one Q-minus recomputation and sixteen original single-slot Q-development workers are owned")
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
    """Only distinct physical cards limit concurrency; there is no resident cap."""
    count = external.get("resident_count")
    if type(count) is not int or count not in (0, 1):
        raise ValueError("External Q-plus residency must be explicit")
    if external.get("status") != "complete" and count != 1:
        raise ValueError("Pending original Q-plus retains its bound physical card")
    used = {state["gpu"] for state in active.values()}
    if external.get("excluded_gpu") is not None:
        used.add(external["excluded_gpu"])
    return len(set(host.GPU_ORDER) - used)


def available_cards(plan, sample, excluded=()):
    return resource.available_cards(plan, sample, excluded)


def training_stop_reason(plan, worker, receipt, *, now):
    from scripts import software_learning_resume_compute_v050r3 as compute
    if worker != "update-Q_minus" or receipt is None:
        return None
    expected = plan["qminus_compute_replay"]["remaining_seconds"]
    if (not isinstance(receipt, dict) or type(receipt.get("started_at")) not in (int, float)
            or receipt.get("maximum_seconds") != expected
            or receipt.get("replay_budget_sha256") != plan["qminus_compute_replay"]["sha256"]):
        return "training_compute_budget_unbound"
    ended = receipt.get("ended_at")
    reason = compute.training_stop_reason(receipt, now=now if ended is None else ended)
    if reason is None and ended is None and now >= receipt["started_at"] + expected - 30:
        return "training_compute_reclamation_reserve"
    return reason


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


def initial_summary(plan, *, now, observer_pid):
    return {"version": VERSION, "status": "waiting", "started_at": now,
        "observer_pid": observer_pid, "source": plan["source"], "states": initial_states(plan),
        "parent_plan": plan["parent_plan"], "external_Q_plus_binding": plan["external_Q_plus"],
        "external_Q_plus_owned_by_original_host": True,
        "new_worker_cost_excludes_external_observation": True,
        "original_r1_plan": plan["original_r1_plan"], "resource_policy": plan["resource_policy"],
        "single_slot_scheduling": plan["single_slot_scheduling"], "maximum_residents": None}


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = initial_summary(plan, now=time.time(), observer_pid=os.getpid())
    active, logs, guards = {}, {}, {}
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
        if name in host.DEVELOPMENT:
            rows = result.get("rows", [])
            state["single_slot_cost"] = {"slot_id": state["planned_slots"][0],
                "original_worker": state["original_worker"],
                "elapsed_gpu_seconds": state["elapsed_gpu_seconds"],
                "includes_model_load_and_final_guards": True,
                "formal_result_known": len(rows) == 1 and rows[0].get("R") in (0, 1),
                "usage": copy.deepcopy(rows[0].get("usage")) if len(rows) == 1 else None,
                "complete_worker": complete}
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
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    excluded = [summary["states"][n]["gpu"] for n in active]
                    if external.get("excluded_gpu") is not None:
                        excluded.append(external["excluded_gpu"])
                    cards = available_cards(plan, sample, excluded)
                    for card in cards:
                        if not waiting:
                            break
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
                        reservation = resource.launch_target(card)
                        env = worker_env(plan, card["index"], reservation)
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        summary["states"][name].update(attempted=True, launch_intent_at=time.time(),
                            gpu=card["index"], gpu_uuid=card["uuid"], command=argv,
                            source_worktree=str(SOURCE), external_residents_at_launch=external["resident_count"],
                            reservation=reservation)
                        publish()
                        write(folder / "worker-launch.json", {"actual_command": argv, "cwd": str(SOURCE),
                            "pythonpath": env["PYTHONPATH"], "gpu": card["index"],
                            "external_Q_plus_observation": copy.deepcopy(external),
                            "reservation": reservation, "original_worker": host.original_worker(name),
                            "planned_units": host.worker_units(plan, name),
                            "total_residents_after_launch": len(active) + external["resident_count"] + 1,
                            "recorded_at": time.time(), "phase": "before_popen"})
                        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                            stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", pid=process.pid, process_identity=identity,
                            started_at=time.time())
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=len(active)) as pool:
                        futures = {n: pool.submit(target_resources, summary["states"][n]["gpu"], worker_pid=p.pid)
                            for n, p in active.items()}
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"],
                            own_memory_limit_mib=None)
                        current = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason")
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
