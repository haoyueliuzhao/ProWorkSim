"""Bounded two-resident C1 development; no retries, successors or learning.

Each process owns one physical card and a fixed eight-slot partition. Targeted
telemetry keeps other projects' slow GPU queries out of active-worker health.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.storage import read_json
from scripts.collaboration_carrier_v026 import (
    RESOURCE_CAPS,
    TASK_CAPS,
    VERSION,
    validate_plan,
    validate_cpu_qualification,
)
from scripts.evaluate_work_v022 import reference, write
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_credit_v024 import ready_cards
from scripts.run_ne_v021 import lock, read, resources, stop_owned

SHUTDOWN_RESERVE = 60


def card_uuid(sample, gpu):
    for row in csv.reader(io.StringIO(sample["gpus"]["stdout"])):
        if len(row) == 6 and int(row[0].strip()) == gpu:
            return row[1].strip()
    raise ValueError("Admitted physical card has no UUID")


def worker_environment(plan, root, worker, gpu):
    source = Path(__file__).resolve().parents[1]
    temporary = root / worker / "tmp"
    env = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": str(gpu),
        "PYTHONHASHSEED": plan["python_hash_seed"],
        "PYTHONPATH": str(source / "src") + os.pathsep + str(source),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "TMPDIR": str(temporary),
        "TMP": str(temporary),
        "TEMP": str(temporary),
    }
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def storage_preflight(plan, root, worker):
    temporary = root / worker / "tmp"
    temporary.mkdir(mode=0o700)
    if temporary.stat().st_dev == Path("/tmp").stat().st_dev:
        raise ValueError("Carrier temporary files must use the data volume, not the system disk")
    if shutil.disk_usage(temporary).free < plan["minimum_temp_free_bytes"]:
        raise ValueError("Insufficient data-volume temporary reserve")
    code = """import json, pathlib, tempfile
from proworksim.domains.executable_project import execute
result = execute(code={"models":[{"name":"probe", "sql":"SELECT 1 AS x"}], "config":{"exports":["probe"]}})
assert result["status"] == "success" and result["tables"]["probe"]["rows"] == [[1]]
print(json.dumps({"temporary_directory":tempfile.gettempdir(), "sql_status":result["status"], "database_file_created":result["database"]["file_created"]}))
"""
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=worker_environment(plan, root, worker, ""),
        text=True,
        capture_output=True,
        timeout=90,
        check=True,
    )
    proof = json.loads(done.stdout)
    if Path(proof["temporary_directory"]).resolve() != temporary:
        raise ValueError("Actual SQL temporary-directory selection differs")
    proof.update(free_bytes=shutil.disk_usage(temporary).free, model_calls=0, actor_loaded=False)
    write(root / worker / "storage-preflight.json", proof)


def stop_reason(plan, state, task, *, now, root_started, own_rss, all_rss, size, free_bytes):
    if task.get("kind") not in TASK_CAPS:
        return "unapproved_task_kind"
    if now - task["started_at"] >= TASK_CAPS[task["kind"]] - SHUTDOWN_RESERVE:
        return "task_time_budget"
    if now - state["started_at"] >= state["budget_seconds"] - SHUTDOWN_RESERVE:
        return "worker_gpu_budget"
    if now - root_started >= plan["max_wall_seconds"] - SHUTDOWN_RESERVE:
        return "wall_time_budget"
    if own_rss > plan["host_rss_bytes"] or all_rss > 2 * plan["host_rss_bytes"]:
        return "host_rss_limit"
    if size >= plan["artifact_bytes"]:
        return "artifact_limit"
    if free_bytes < plan["minimum_temp_free_bytes"]:
        return "temporary_volume_reserve"
    return None


def verify_completed_worker(plan, root, worker, expected_slots, source):
    report = read_json(root / worker / "actual/report.json")
    marker = read_json(Path(plan["checkpoint_marker"]["path"]))
    rows = report.get("rows", [])
    if (
        report.get("status") != "complete"
        or report.get("actor_steps") != 3
        or report.get("critic_steps") != 3
        or report.get("source_unchanged") is not True
        or report.get("source_before") != source
        or report.get("source_after") != source
        or report.get("final_actor_identity") != marker["actor_identity"]
        or report.get("new_actor_steps") != 0
        or report.get("new_critic_steps") != 0
        or report.get("learning_probability_recomputation") is not False
        or report.get("not_started") != []
        or len(rows) != 8
        or [row["slot_id"] for row in rows] != [slot["slot_id"] for slot in expected_slots]
        or any(
            row.get("status") != "closed"
            or row.get("assessment", {}).get("eligible") is not True
            or row.get("evaluation_guard", {}).get("learning_unchanged") is not True
            or row.get("evaluation_guard", {}).get("rng_restored_exactly") is not True
            for row in rows
        )
    ):
        raise ValueError(
            "Worker did not preserve the exact frozen endpoint and all eight known evaluation outcomes"
        )


def finish(root, worker, state, process, reason):
    if process.poll() is None:
        stop_owned(process)
    # Reap an owned SIGKILL result before recording terminal status.
    if process.poll() is None:
        process.wait(timeout=10)
    state.update(
        ended_at=time.time(),
        exit_code=process.poll(),
        stop_reason=reason,
        status="complete" if process.returncode == 0 and reason is None else "stopped",
    )
    state["elapsed_gpu_seconds"] = state["ended_at"] - state["started_at"]
    state["task"] = read(root / worker / "actual/task.json") or state.get("task")
    report = read(root / worker / "actual/report.json") or {}
    state["completed_slot_count"] = sum(
        row.get("status") == "closed" for row in report.get("rows", [])
    )
    write(root / worker / "state.json", state)


def run(plan_path, root):
    plan = read_json(plan_path)
    catalog, assigned = validate_plan(plan)
    source = code_identity()
    if source["code_dirty"]:
        raise ValueError("Commit and freeze the entire new carrier protocol before model execution")
    root.mkdir(parents=True, exist_ok=False)
    with lock(root):
        states, active, logs, guards = {}, {}, {}, {}
        summary = {
            "version": VERSION,
            "status": "preflight",
            "source": source,
            "plan": reference(plan_path),
            "observer_pid": os.getpid(),
            "started_at": time.time(),
            "caps": RESOURCE_CAPS,
            "task_caps": TASK_CAPS,
            "max_parallel_model_instances": 2,
            "per_episode_model_instances": 1,
            "parameter_updates": 0,
            "model_api_calls": 0,
            "automatic_successors": [],
            "no_automatic_second_attempt": True,
            "telemetry_grace_seconds": 120,
            "shutdown_reserve_seconds": SHUTDOWN_RESERVE,
            "checkpoint_marker": plan["checkpoint_marker"],
            "qualification": plan["qualification"],
            "cpu_qualification_passed_before_queue": True,
            "worker_assignments": assigned,
        }

        def publish():
            summary["worker_statuses"] = {key: state["status"] for key, state in states.items()}
            summary["observed_at"] = time.time()
            summary["terminated_gpu_seconds"] = sum(
                state.get("elapsed_gpu_seconds", 0.0) for state in states.values()
            )
            summary["running_gpu_seconds"] = sum(
                time.time() - states[key]["started_at"] for key in active
            )
            write(root / "supervisor.json", summary)

        for worker, budget in RESOURCE_CAPS.items():
            (root / worker).mkdir()
            states[worker] = {
                "worker": worker,
                "status": "waiting",
                "attempted": False,
                "budget_seconds": budget,
                "source": source,
                "created_at": time.time(),
                "slots": assigned[worker],
            }
            write(root / worker / "state.json", states[worker])
        publish()
        last_size, size = 0.0, 0
        try:
            for worker in RESOURCE_CAPS:
                storage_preflight(plan, root, worker)
            summary["status"] = "running"
            with ThreadPoolExecutor(max_workers=2) as pool:
                while True:
                    now = time.time()
                    if now - last_size >= 30:
                        size, last_size = artifact_bytes(root), now
                    free_bytes = shutil.disk_usage(root).free
                    all_rss = sum(rss(process.pid) for process in active.values())
                    future_samples = {
                        worker: pool.submit(
                            target_resources,
                            states[worker]["gpu"],
                            worker_pid=process.pid,
                            gpu_timeout_seconds=5,
                            process_timeout_seconds=5,
                        )
                        for worker, process in active.items()
                        if process.poll() is None
                    }
                    for worker, process in list(active.items()):
                        state = states[worker]
                        sample = (
                            future_samples[worker].result() if worker in future_samples else None
                        )
                        if process.poll() is not None:
                            reason = None if process.returncode == 0 else "worker_failed"
                            if reason is None:
                                try:
                                    verify_completed_worker(
                                        plan, root, worker, assigned[worker], source
                                    )
                                except (ValueError, KeyError, OSError) as error:
                                    reason = "unqualified_frozen_endpoint"
                                    state["verification_error"] = str(error)
                            if sample is not None:
                                with (root / worker / "resources.jsonl").open("a") as file:
                                    file.write(
                                        json.dumps({"sample": sample, "natural_exit": True}) + "\n"
                                    )
                            finish(root, worker, state, process, reason)
                            logs.pop(worker).close()
                            del active[worker]
                            continue
                        now = time.time()
                        observed = guards[worker].observe(
                            sample,
                            now,
                            process.pid,
                            state["gpu"],
                            own_memory_limit_mib=plan["own_gpu_memory_mib"],
                        )
                        current_task = read(root / worker / "actual/task.json") or {
                            "kind": "loading",
                            "task": "startup",
                            "started_at": state["started_at"],
                        }
                        own_rss = rss(process.pid)
                        reason = stop_reason(
                            plan,
                            state,
                            current_task,
                            now=now,
                            root_started=summary["started_at"],
                            own_rss=own_rss,
                            all_rss=all_rss,
                            size=size,
                            free_bytes=free_bytes,
                        )
                        reason = reason or observed["stop_reason"]
                        state.update(task=current_task, telemetry=observed)
                        with (root / worker / "resources.jsonl").open("a") as file:
                            file.write(
                                json.dumps(
                                    {
                                        "sample": sample,
                                        "task": current_task,
                                        "rss_bytes": own_rss,
                                        "all_lines_rss_bytes": all_rss,
                                        "artifact_bytes": size,
                                        "temporary_free_bytes": free_bytes,
                                        "telemetry": observed,
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                        write(root / worker / "state.json", state)
                        if reason:
                            finish(root, worker, state, process, reason)
                            logs.pop(worker).close()
                            del active[worker]
                    # Global ceilings affect queued workers as well. Per-worker
                    # unknown results stop only its own fixed partition.
                    global_stop = None
                    if (
                        time.time() - summary["started_at"]
                        >= plan["max_wall_seconds"] - SHUTDOWN_RESERVE
                    ):
                        global_stop = "wall_time_budget"
                    elif size >= plan["artifact_bytes"]:
                        global_stop = "artifact_limit"
                    elif free_bytes < plan["minimum_temp_free_bytes"]:
                        global_stop = "temporary_volume_reserve"
                    waiting = [key for key, state in states.items() if state["status"] == "waiting"]
                    if global_stop:
                        for worker in waiting:
                            states[worker].update(
                                status="not_started_" + global_stop, ended_at=time.time()
                            )
                            write(root / worker / "state.json", states[worker])
                        waiting = []
                    if waiting:
                        if code_identity() != source or reference(plan_path) != summary["plan"]:
                            raise ValueError("Frozen source or plan changed while waiting")
                        sample = resources()
                        excluded = [states[key]["gpu"] for key in active]
                        choices = ready_cards(sample, training=False, excluded=excluded)
                        for worker in waiting:
                            if len(active) >= 2 or not choices:
                                states[worker].update(
                                    last_admission_observation=sample, ready_cards=choices
                                )
                                write(root / worker / "state.json", states[worker])
                                continue
                            confirmed = resources()
                            choices = ready_cards(confirmed, training=False, excluded=excluded)
                            if not choices:
                                continue
                            # A changed qualification artifact cannot retain its
                            # earlier admission while the supervisor waits for GPU.
                            if code_identity() != source or reference(plan_path) != summary["plan"]:
                                raise ValueError(
                                    "Frozen source or plan changed during GPU admission"
                                )
                            admission = validate_cpu_qualification(
                                plan, catalog, current_source=source
                            )
                            gpu = choices[0]
                            state = states[worker]
                            state["cpu_qualification_admission"] = admission
                            command = [
                                sys.executable,
                                "-m",
                                "scripts.collaboration_carrier_v026",
                                "--plan",
                                str(plan_path),
                                "--worker",
                                worker,
                                "--output",
                                str(root / worker / "actual"),
                            ]
                            state.update(
                                status="launch_intent",
                                attempted=True,
                                gpu=gpu,
                                gpu_uuid=card_uuid(confirmed, gpu),
                                started_at=time.time(),
                                command=command,
                                admission_resources=confirmed,
                            )
                            write(root / worker / "state.json", state)
                            logs[worker] = (root / worker / "model.log").open("x")
                            process = subprocess.Popen(
                                command,
                                cwd=Path(__file__).resolve().parents[1],
                                env=worker_environment(plan, root, worker, gpu),
                                stdin=subprocess.DEVNULL,
                                stdout=logs[worker],
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                            )
                            active[worker] = process
                            identity = worker_identity(process.pid)
                            if not identity.get("available") or identity.get("alive") is not True:
                                raise ValueError("Cannot bind actual new worker process identity")
                            state.update(
                                status="running",
                                pid=process.pid,
                                worker_start_ticks=identity["start_ticks"],
                            )
                            guards[worker] = TelemetryGuard(
                                gpu,
                                state["gpu_uuid"],
                                identity["start_ticks"],
                                grace_seconds=120,
                                worker_pid=process.pid,
                            )
                            excluded.append(gpu)
                            choices = [candidate for candidate in choices if candidate != gpu]
                            write(root / worker / "state.json", state)
                    publish()
                    if not active and all(
                        state["status"] != "waiting" for state in states.values()
                    ):
                        break
                    time.sleep(5)
            summary.update(
                status="complete"
                if all(state["status"] == "complete" for state in states.values())
                else "closed_with_incomplete_workers",
                ended_at=time.time(),
            )
        except BaseException as error:
            for worker, process in list(active.items()):
                finish(root, worker, states[worker], process, "supervisor_interrupted")
                logs.pop(worker).close()
                del active[worker]
            for worker, state in states.items():
                if state["status"] == "waiting":
                    state.update(status="not_started_supervisor_interrupted", ended_at=time.time())
                    write(root / worker / "state.json", state)
            summary.update(
                status="supervisor_error",
                error={"type": type(error).__name__, "message": str(error)},
                ended_at=time.time(),
            )
        finally:
            publish()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    result = run(args.plan.resolve(), args.run_root.resolve())
    raise SystemExit(0 if result["status"] == "complete" else 2)
