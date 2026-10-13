"""Frozen v050 dependency graph, CPU support gate and inherited live resource guards."""
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
from scripts import software_learning_v050 as host
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_v049r2 import received_signal
from scripts.software_learning_development_resume_supervisor_v049r2 import request_stop
from scripts.software_learning_development_resume_v049r2g import resources
from scripts.software_allocation_v037 import live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-supervisor-v0.50"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
GPU_ORDER = host.GPU_ORDER
_provider = resources(GPU_ORDER)
worker_env, allowed_resources, available_cards = _provider.worker_env, _provider.allowed_resources, _provider.available_cards


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def initial_states(plan):
    return {name: {"worker": name, "status": "not_started", "attempted": False,
        "planned_slots": [u["slot_id"] for u in host.worker_units(plan, name)]} for name in WORKERS}


def _check_states(states):
    if set(states) != set(WORKERS):
        raise ValueError("Only predeclared v050 workers may be supervised")


def validate_direction(direction):
    if (not isinstance(direction, dict) or type(direction.get("selected")) is not bool
            or direction.get("reliable_base_material") is not True):
        raise ValueError("Direction requires explicit outcome and reliable pretraining support")
    return direction


def eligible_workers(states, gate=None, direction=None):
    _check_states(states)
    def complete(name):
        return states[name]["status"] == "complete"
    allowed = ["s_star"] if not complete("s_star") else list(host.COLLECTION)
    if all(complete(name) for name in host.COLLECTION) and gate is not None:
        if type(gate.get("run_B50")) is not bool:
            raise ValueError("Support-only release must be explicit")
        if gate["run_B50"]:
            allowed.append("update-B")
    if complete("update-B") and direction is not None:
        validate_direction(direction)
        allowed.extend(name for name in host.DEVELOPMENT if name.startswith(("dev-S_star-", "dev-B-")))
        if direction["selected"]:
            allowed.extend(["update-Q_plus", "update-Q_minus"])
            for branch in ("Q_plus", "Q_minus"):
                if complete("update-" + branch):
                    allowed.extend(name for name in host.DEVELOPMENT if name.startswith("dev-" + branch + "-"))
    return [name for name in WORKERS if name in allowed and states[name]["status"] == "not_started"
            and states[name].get("attempted") is False]


def _disable(states, names, reason):
    for name in names:
        if states[name]["status"] not in {"not_started", "not_applicable"} or states[name].get("attempted") is not False:
            raise ValueError("A conditional gate cannot erase attempted work")
        states[name].update(status="not_applicable", reason=reason, elapsed_gpu_seconds=0, generation_slots_executed=0)
    return list(names)


def apply_support_gate(states, gate):
    _check_states(states)
    if not all(states[name]["status"] == "complete" for name in host.COLLECTION) or type(gate.get("run_B50")) is not bool:
        raise ValueError("All 24 slots must close before the support-only release")
    return [] if gate["run_B50"] else _disable(states, (*host.UPDATES, *host.DEVELOPMENT), "no_reliable_multiclass_support")


def apply_not_applicable(states, direction):
    _check_states(states)
    validate_direction(direction)
    if states["update-B"]["status"] != "complete":
        raise ValueError("Actual B must close before gradient-direction branching")
    names = ["update-Q_plus", "update-Q_minus", *[n for n in host.DEVELOPMENT if n.startswith(("dev-Q_plus-", "dev-Q_minus-"))]]
    return [] if direction["selected"] else _disable(states, names, "actual_direction_degenerate")


def read_direction(root, states, plan):
    if states["update-B"]["status"] != "complete":
        raise ValueError("Direction cannot be read until original B is complete")
    root = Path(root)
    direction = read(root / "direction.json")
    validate_direction(direction)
    host.check_seal(direction, "seal_sha256")
    report = read(root / "update-B/actual/report.json") or {}
    if (report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != report.get("source_after") or report.get("source_after") != plan["source"]
            or direction.get("frozen_before_any_development") is not True or direction.get("B_update") != report.get("update_report")):
        raise ValueError("Direction must bind actual completed B before any development")
    for key, expected in (("B_update", root / "update-B/actual/update/report.json"), ("support", root / "support.json")):
        if host.checked(direction[key]).resolve() != expected.resolve():
            raise ValueError("Direction source lies outside this single window")
    return copy.deepcopy(direction)


def training_stop_reason(worker, receipt, *, now):
    if worker not in host.UPDATES or receipt is None:
        return None
    if (not isinstance(receipt, dict) or type(receipt.get("started_at")) not in (int, float)
            or receipt.get("maximum_seconds") != LIMITS["update_worker_seconds"]):
        return "training_compute_budget_unbound"
    ended = receipt.get("ended_at")
    if (now if ended is None else ended) - receipt["started_at"] >= LIMITS["update_worker_seconds"]:
        return "training_compute_budget"
    return None


def task_stop_reason(current, *, now, rss_bytes):
    cap = LIMITS["task_seconds"].get(current.get("kind"))
    if cap is None:
        return "unknown_task_kind"
    if now - current["started_at"] >= cap:
        return "episode_hard_deadline" if current["kind"] == "episode" else "single_task_budget"
    if rss_bytes > LIMITS["host_rss_per_worker_bytes"]:
        return "host_memory_budget"
    return None


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = {
        "version": VERSION,
        "status": "waiting",
        "started_at": time.time(),
        "observer_pid": os.getpid(),
        "source": plan["source"],
        "states": initial_states(plan),
        "support_gate": None,
    }
    active, logs, guards, stable = {}, {}, {}, {}
    direction, gate = None, None

    def publish():
        summary.update(
            observed_at=time.time(),
            closed_worker_gpu_seconds=sum(
                s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()
            ),
            running_worker_gpu_seconds=sum(
                time.time() - summary["states"][n]["started_at"] for n in active
            ),
        )
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process = active[name]
        state = summary["states"][name]
        if process.poll() is None:
            request_stop(root, name, process, state, reason)
        process.wait(timeout=15)
        active.pop(name)
        result = read(root / name / "actual/report.json") or {}
        complete = (
            process.returncode == 0
            and reason is None
            and result.get("status") == "complete"
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and result.get("success_boundary") is True
        )
        ended = time.time()
        state.update(
            status="complete" if complete else "stopped",
            stop_reason=reason,
            exit_code=process.returncode,
            ended_at=ended,
            elapsed_gpu_seconds=ended - state["started_at"],
        )
        logs.pop(name).close()
        if not complete:
            normal_pause = (
                process.returncode == 0
                and reason is None
                and result.get("source_before") == result.get("source_after") == plan["source"]
                and result.get("status") in {"measurement_pending", "global_pause", "paused_before_next_slot"}
            )
            kind = result.get("status") if normal_pause else "execution_fault"
            if kind not in {"measurement_pending", "global_pause", "paused_before_next_slot"}:
                kind = "execution_fault"
            write(
                root / "mechanism-stops" / (name + "-supervisor.json"),
                {
                    "kind": kind,
                    "reason": reason or result.get("status", "worker_incomplete"),
                    "worker": name,
                    "observed_at": ended,
                    "worker_state": state,
                },
            )
        publish()

    with lock(root):
        if (root / "supervisor.json").exists():
            raise FileExistsError(
                "A started v050 learning inventory is never automatically replayed"
            )
        publish()
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
                if all(summary["states"][name]["status"] == "complete" for name in host.COLLECTION) and gate is None and not mechanism_pauses(root):
                    summary["cpu_support_gate"] = {"status": "running", "started_at": time.time()}
                    publish()
                    gate = host.run_support_gate(root)
                    summary["support_gate"] = reference(root / "support-gate.json")
                    summary["cpu_support_gate"].update(status="complete", ended_at=time.time())
                    apply_support_gate(summary["states"], gate)
                    publish()
                if summary["states"]["update-B"]["status"] == "complete" and not mechanism_pauses(root):
                    try:
                        current_direction = read_direction(root, summary["states"], plan)
                        current_ref = reference(root / "direction.json")
                        if direction is not None and summary["direction"] != current_ref:
                            raise ValueError("The predevelopment frozen direction changed")
                        direction = current_direction
                        summary["direction"] = current_ref
                        apply_not_applicable(summary["states"], direction)
                    except (OSError, ValueError, KeyError, TypeError) as error:
                        write(root / "mechanism-stops/direction-binding.json", {
                            "kind": "measurement_pending", "reason": "missing_or_inconsistent_direction_binding",
                            "error": str(error), "observed_at": time.time()})
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [
                        reference(path) for path in mechanism_pauses(root)
                    ]
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(
                                status="stopped",
                                stop_reason="unopened_work_paused",
                                elapsed_gpu_seconds=0,
                            )
                if all(s["status"] in {"complete", "stopped", "not_applicable"} for s in summary["states"].values()):
                    summary["status"] = (
                        "complete"
                        if all(s["status"] in {"complete", "not_applicable"} for s in summary["states"].values())
                        else "closed_with_unknowns"
                    )
                    break
                size = sum(
                    artifact_bytes(Path(path))
                    for path in support.dense._artifact_roots([*plan["prior_artifact_roots"], root])
                )
                free = shutil.disk_usage(root).free
                if size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                    for name in list(active):
                        close(name, "trajectory_storage_reserve")
                    for state in summary["states"].values():
                        if state["status"] == "not_started":
                            state.update(
                                status="stopped",
                                stop_reason="trajectory_storage_reserve",
                                elapsed_gpu_seconds=0,
                            )
                    summary["status"] = "trajectory_storage_reserve"
                    break
                waiting = eligible_workers(summary["states"], gate, direction)
                if not waiting:
                    stable.clear()
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(
                        plan, sample, [summary["states"][n]["gpu"] for n in active]
                    )
                    now = time.time()
                    stable = {c["index"]: stable.get(c["index"], now) for c in cards}
                    for card in cards:
                        if not waiting or len(active) >= LIMITS["max_parallel_model_instances"]:
                            break
                        if now - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if mechanism_pauses(root):
                            break
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [
                            plan["native_python"],
                            "-m",
                            "scripts.software_learning_v050",
                            "worker",
                            "--run-root",
                            str(root),
                            "--worker",
                            name,
                            "--output",
                            str(folder / "actual"),
                        ]
                        logs[name] = (folder / "worker.log").open("x")
                        temporary = folder / "tmp"
                        temporary.mkdir()
                        env = worker_env(plan, card["index"])
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        summary["states"][name].update(attempted=True, launch_intent_at=time.time(),
                            gpu=card["index"], gpu_uuid=card["uuid"], command=argv)
                        publish()
                        process = subprocess.Popen(
                            argv,
                            cwd=SOURCE,
                            env=env,
                            stdin=subprocess.DEVNULL,
                            stdout=logs[name],
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(
                            status="running",
                            attempted=True,
                            gpu=card["index"],
                            gpu_uuid=card["uuid"],
                            pid=process.pid,
                            process_identity=identity,
                            started_at=time.time(),
                            command=argv,
                        )
                        active[name] = process
                        stable.pop(card["index"], None)
                        guards[name] = TelemetryGuard(
                            card["index"],
                            card["uuid"],
                            identity["start_ticks"],
                            worker_pid=process.pid,
                        )
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=3) as pool:
                        futures = {
                            n: pool.submit(
                                target_resources, summary["states"][n]["gpu"], worker_pid=p.pid
                            )
                            for n, p in active.items()
                        }
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        guard = guards[name].observe(
                            samples[name],
                            time.time(),
                            process.pid,
                            state["gpu"],
                            own_memory_limit_mib=LIMITS["own_gpu_memory_mib"],
                        )
                        current = read(root / name / "actual/task.json") or {
                            "kind": "loading",
                            "started_at": state["started_at"],
                        }
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or live_free_stop_reason(
                            samples[name], state["gpu"]
                        )
                        reason = reason or task_stop_reason(current, now=time.time(), rss_bytes=own_rss)
                        compute = read(root / name / "actual/training-compute.json")
                        reason = reason or training_stop_reason(name, compute, now=time.time())
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(
                                json.dumps(
                                    {
                                        "sample": samples[name],
                                        "guard": guard,
                                        "task": current,
                                        "training_compute": compute,
                                        "rss_bytes": own_rss,
                                        "artifact_bytes": size,
                                        "volume_free_bytes": free,
                                    }
                                )
                                + "\n"
                            )
                        if reason:
                            close(name, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as error:
            summary.update(
                status="interrupted", error={"type": type(error).__name__, "message": str(error)}
            )
            for name in list(active):
                close(name, "supervisor_interrupted")
            write(root / "mechanism-stops/supervisor-exception.json", {
                "kind": "execution_fault", "reason": "supervisor_interrupted_or_failed",
                "error": summary["error"], "observed_at": time.time()})
            for state in summary["states"].values():
                if state["status"] == "not_started":
                    state.update(status="stopped", stop_reason="unopened_work_paused", elapsed_gpu_seconds=0)
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
    signal.signal(signal.SIGTERM, received_signal)
    supervise(args.run_root)


if __name__ == "__main__":
    main()
