"""Source-bound original v049 inventory continuation under the retained resource guards.

S0 is already complete and is never launched. Only original unstarted collection,
short updates and development inventory remain eligible.
No whole-window training time cap is introduced: each original numerical call
has its declared 900-second guard and every state boundary has 600 seconds.
"""
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
from proworksim.storage import digest, json_bytes
from scripts import software_learning_resume_v049r1 as host
from scripts import software_organization_v048 as inherited
from scripts import software_support_v036 as support
from scripts.software_allocation_v037 import available_cards, live_free_stop_reason
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-original-inventory-resume-supervisor-v0.49-r1"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
GPU_ORDER = (3, 4, 5, 7)
worker_env, allowed_resources = inherited.worker_env, inherited.allowed_resources


def mechanism_pauses(root):
    return sorted((Path(root) / "mechanism-stops").glob("*.json"))


def _check_states(states):
    if set(states) != set(WORKERS):
        raise ValueError("Only the nine predeclared v049 workers may be supervised")


def validate_direction(direction):
    if (not isinstance(direction, dict) or type(direction.get("selected")) is not bool
            or type(direction.get("reliable_base_material")) is not bool
            or direction["selected"] and not direction["reliable_base_material"]):
        raise ValueError("Direction selection and reliable-base decision require explicit consistent booleans")
    return direction


def eligible_workers(states, direction=None):
    """Fixed dependencies, without success scores or extra support collection."""
    _check_states(states)
    def completed(name):
        return states[name]["status"] == "complete"
    allowed = []
    if not completed("s0"):
        allowed = ["s0"]
    else:
        allowed.extend(["collect-LA", "collect-LB"])
        if completed("collect-LA") and completed("collect-LB"):
            allowed.append("update-B")
        if completed("update-B") and direction is not None:
            validate_direction(direction)
            if direction["reliable_base_material"]:
                allowed.append("dev-B")
                if direction["selected"]:
                    allowed.extend(["update-Q_plus", "update-Q_minus"])
                    for branch in ("Q_plus", "Q_minus"):
                        if completed("update-" + branch):
                            allowed.append("dev-" + branch)
    # Queue order is the predeclared worker order; Q± and dev-B can overlap.
    return [name for name in WORKERS if name in allowed and states[name]["status"] == "not_started"
            and states[name].get("attempted") is not True]


def apply_not_applicable(states, direction):
    """Unused conditional inventory remains explicitly never attempted."""
    _check_states(states)
    validate_direction(direction)
    if states["update-B"]["status"] != "complete":
        raise ValueError("Only a completed B receipt can resolve conditional inventory")
    disabled = []
    reason = "no_admissible_I_direction"
    if not direction["reliable_base_material"]:
        disabled = ["update-Q_plus", "update-Q_minus", "dev-B", "dev-Q_plus", "dev-Q_minus"]
        reason = "no_reliable_base_material"
    elif not direction["selected"]:
        disabled = ["update-Q_plus", "update-Q_minus", "dev-Q_plus", "dev-Q_minus"]
    for name in disabled:
        state = states[name]
        if state["status"] not in {"not_started", "not_applicable"} or state.get("attempted") is True:
            raise ValueError("Conditional no-support decision cannot erase attempted work")
        state.update(status="not_applicable", attempted=False, reason=reason,
                     elapsed_gpu_seconds=0, generation_slots_executed=0)
    return disabled


def read_direction(root, states, plan):
    if states["update-B"]["status"] != "complete":
        raise ValueError("A direction is unreadable until B reaches its complete original boundary")
    root = Path(root)
    direction = read(root / "direction.json")
    validate_direction(direction)
    if direction.get("seal_sha256") != digest(json_bytes({key: value for key, value in direction.items() if key != "seal_sha256"})):
        raise ValueError("Frozen direction wrapper seal changed")
    report = read(root / "update-B/actual/report.json") or {}
    if (report.get("status") != "complete" or report.get("success_boundary") is not True
            or report.get("source_before") != report.get("source_after") or report.get("source_after") != plan["source"]
            or direction.get("frozen_before_any_development") is not True
            or direction.get("B_update") != report.get("update_report")):
        raise ValueError("Direction must bind the completed B update before any development")
    for key in ("B_update", "support"):
        host.checked(direction[key])
    if Path(direction["B_update"]["path"]).resolve() != (root / "update-B/actual/update/report.json").resolve():
        raise ValueError("Direction points outside this B update")
    if Path(direction["support"]["path"]).resolve() != (root / "support.json").resolve():
        raise ValueError("Direction points outside this collected support")
    return copy.deepcopy(direction)


def task_stop_reason(current, *, now, rss_bytes):
    cap = LIMITS["task_seconds"].get(current.get("kind"))
    if cap is None:
        return "unknown_task_kind"
    if now - current["started_at"] >= cap:
        return "episode_hard_deadline" if current["kind"] == "episode" else "single_task_budget"
    if rss_bytes > LIMITS["host_rss_per_worker_bytes"]:
        return "host_memory_budget"
    return None


def initial_states(plan):
    value = {name: {"worker": name, "status": "not_started", "attempted": False} for name in WORKERS}
    value["s0"].update(status="complete", attempted=False, original_complete_state_reused=True,
        source_receipt=plan["resume_inventory"]["original_s0"], elapsed_gpu_seconds=0)
    for name in ("collect-LA", "collect-LB"):
        units = [row for row in plan["resume_inventory"]["remaining_training_units"]
                 if row["root"] == name.removeprefix("collect-")]
        value[name]["remaining_original_slot_ids"] = [row["slot_id"] for row in units]
        if not units:
            value[name].update(status="complete", attempted=False, all_original_slots_already_closed=True,
                               elapsed_gpu_seconds=0)
    return value


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
        "original_supervisor": plan["resume_inventory"]["original_supervisor"],
        "original_costs": plan["resume_inventory"]["retained_actual_cost"],
        "new_worker_cost_scope": "Only this continuation; original S0/closed workers are never added to new worker seconds",
    }
    active, logs, guards, stable = {}, {}, {}, {}
    direction = None

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
        process = active.pop(name)
        state = summary["states"][name]
        if process.poll() is None:
            support.continuation._stop_worker(process, state)
        process.wait(timeout=15)
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
                "A started v049 resume inventory is never automatically replayed"
            )
        publish()
        try:
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
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
                waiting = eligible_workers(summary["states"], direction)
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
                            "scripts.software_learning_resume_v049r1",
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
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(
                                json.dumps(
                                    {
                                        "sample": samples[name],
                                        "guard": guard,
                                        "task": current,
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
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    supervise(args.run_root)


if __name__ == "__main__":
    main()
