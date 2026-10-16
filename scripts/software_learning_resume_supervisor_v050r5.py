"""Requeue only archived zero-model resource attempts; observe external Q-plus."""
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
from scripts import software_learning_resume_v050r5 as host
from scripts import software_learning_resume_supervisor_v050r3 as prior
from scripts import software_learning_resume_supervisor_v050r4 as compute_guard
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_supervisor_v049r2 import request_stop as inherited_stop
from scripts.software_learning_development_resume_v049r2g import resources
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-original-Q-supervisor-v0.50-r5"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
resource = host.resource
allowed_resources = resources(host.GPU_ORDER).allowed_resources
worker_env = host.worker_env
task_stop_reason, mechanism_pauses = prior.task_stop_reason, prior.mechanism_pauses
available_cards = resource.available_cards
training_stop_reason = compute_guard.training_stop_reason
store_external_terminal = prior.store_external_terminal
RESOURCE_FILES = {"worker-launch.json", "reservation-binding-verified.json", "resource-wait.json",
    "worker.log", "resources.jsonl", "startup/startup-resource-receipt.json",
    "startup/native-cache-resources.jsonl", "startup/task.json"}
RESOURCE_REQUIRED = RESOURCE_FILES - {"resources.jsonl"}


def initial_states(plan):
    return {name: {"worker": name, "status": "not_started", "attempted": False,
        "resource_attempted": False, "model_started": False, "scientific_attempted": False,
        "resource_attempt_history": [], "resource_attempt_gpu_seconds": 0,
        "resource_attempt_number": 0, "next_resource_attempt_at": 0,
        "planned_slots": [u["slot_id"] for u in host.worker_units(plan, name)],
        "original_worker": host.original_worker(name)} for name in WORKERS}


def eligible_workers(states, external, *, now=None):
    now = time.time() if now is None else now
    if set(states) != set(WORKERS):
        raise ValueError("Only original Q-minus and sixteen developments are owned")
    if not isinstance(external, dict) or external.get("status") not in {
            "running", "awaiting_original_host_closure", "awaiting_original_worker_exit", "complete"}:
        return []
    allowed = ["update-Q_minus"]
    if external["status"] == "complete":
        allowed.extend(name for name in host.DEVELOPMENT if name.startswith("dev-Q_plus-"))
    if states["update-Q_minus"]["status"] == "complete":
        allowed.extend(name for name in host.DEVELOPMENT if name.startswith("dev-Q_minus-"))
    return [name for name in WORKERS if name in allowed and states[name]["status"] == "not_started"
        and states[name].get("attempted") is False and states[name].get("model_started") is False
        and now >= states[name].get("next_resource_attempt_at", 0)]


def retry_delay(attempt_number):
    if type(attempt_number) is not int or attempt_number < 1:
        raise ValueError("Resource attempt count must be positive")
    delays = host.RETRY_POLICY["backoff_seconds"]
    return delays[min(attempt_number - 1, len(delays) - 1)]


def request_stop(root, name, process, state, reason):
    if name not in WORKERS or state.get("pid") != process.pid or state.get("worker") != name:
        raise ValueError("Never signal the external r4 Q-plus or any foreign process")
    return inherited_stop(root, name, process, state, reason)


def verify_resource_failure(root, name, state, plan, *, exit_code, reason, identity_fn=worker_identity):
    """Require positive zero-model proof, exact launch identity, and an exited PID."""
    root = Path(root).resolve()
    folder = root / name
    if (name not in WORKERS or state.get("worker") != name or exit_code != 0 or reason is not None
            or state.get("status") != "running" or state.get("attempted") is not True
            or state.get("model_started") is not False or state.get("scientific_attempted") is not False
            or (folder / "actual").exists() or (folder / "startup/model-load-intent.json").exists()
            or list((root / "mechanism-stops").glob(name + "-*.json"))):
        raise ValueError("Only clean zero-model resource exits can be retried")
    paths = list(folder.rglob("*"))
    if any(p.is_symlink() for p in paths):
        raise ValueError("A resource attempt must contain only its original regular evidence")
    files = {str(p.relative_to(folder)) for p in paths if p.is_file()}
    if not RESOURCE_REQUIRED <= files or not files <= RESOURCE_FILES:
        raise ValueError("Unexpected model, native compute, tensor or unknown startup evidence")
    report = read(folder / "resource-wait.json")
    receipt = read(folder / "startup/startup-resource-receipt.json")
    verified = read(folder / "reservation-binding-verified.json")
    launch = read(folder / "worker-launch.json")
    identity = report.get("identity", {})
    process = identity.get("process_identity", {})
    if (report.get("version") != host.VERSION or report.get("status") != "resource_wait"
            or report.get("worker") != name or report.get("model_started") is not False
            or report.get("source_before") != plan["source"] or report.get("source_after") != plan["source"]
            or any(report.get(k) != 0 for k in ("new_model_calls", "new_backward_calls", "new_actor_steps",
                "new_critic_steps", "new_training_interval_seconds"))
            or report.get("retryable") is not True or report.get("loader_not_entered") is not True
            or report.get("reservation") != state["reservation"]
            or report.get("raw_fault") != receipt
            or report.get("resource_receipt") != reference(folder / "startup/startup-resource-receipt.json")
            or receipt.get("version") != host.startup_resource.VERSION
            or receipt.get("status") != "resource_unavailable" or receipt.get("retryable") is not True
            or receipt.get("reason") not in {"pre_model_cuda_out_of_memory", "frozen_startup_capacity_unavailable"}
            or receipt.get("phase") not in {"cuda_capacity_snapshot", "cuda_cache_allocation",
                "cuda_cache_verification", "cuda_startup_peak_reset"}
            or receipt.get("loader_not_entered") is not True
            or any(receipt.get(k) != 0 for k in ("new_model_calls", "new_backward_calls", "new_optimizer_steps",
                "live_reservation_tensors", "same_process_resource_retries"))
            or receipt.get("cuda_requeried_after_error") is not False
            or receipt.get("restart_requires_fresh_process") is not True
            or receipt.get("output") != str(folder / "startup")
            or receipt.get("pid") != state.get("pid") or receipt.get("binding") != state["reservation"]
            or receipt.get("identity") != identity or verified.get("identity") != identity
            or verified.get("reservation") != state["reservation"]
            or verified.get("verified_before_cuda_or_model_load") is not True
            or identity.get("worker") != name or identity.get("run_root") != str(root)
            or identity.get("source") != plan["source"] or identity.get("source_root") != str(SOURCE)
            or identity.get("plan") != reference(root / "plan.json")
            or identity.get("worker_launch") != reference(folder / "worker-launch.json")
            or identity.get("resource_attempt_number") != state["resource_attempt_number"]
            or process.get("pid") != state.get("pid")
            or process.get("start_ticks") != state["process_identity"]["start_ticks"]
            or type(process.get("start_ticks")) is not int
            or launch.get("actual_command") != state.get("command")
            or launch.get("source") != plan["source"] or launch.get("cwd") != str(SOURCE)
            or launch.get("reservation") != state["reservation"]
            or launch.get("resource_attempt_number") != state["resource_attempt_number"]
            or launch.get("original_worker") != host.original_worker(name)
            or launch.get("planned_units") != host.worker_units(plan, name)):
        raise ValueError("Resource failure classification, source, launch or zero-work proof is unbound")
    telemetry = folder / "resources.jsonl"
    if telemetry.exists() and any(json.loads(line).get("training_compute") is not None
            for line in telemetry.read_text().splitlines()):
        raise ValueError("Any native compute evidence prohibits a resource retry")
    task = read(folder / "startup/task.json")
    if (task.get("pid") != state["pid"] or task.get("kind") != "reservation_wait"
            or task.get("loader_not_entered") is not True
            or any(task.get(k) != 0 for k in ("new_model_calls", "new_backward_calls"))):
        raise ValueError("Startup task must positively exclude model work")
    observed = identity_fn(state["pid"])
    dead = observed.get("alive") is False
    reused = (observed.get("alive") is True and type(observed.get("start_ticks")) is int
        and observed["start_ticks"] != state["process_identity"]["start_ticks"])
    if not (dead or reused):
        raise ValueError("The failed resource process has not demonstrably exited")
    return {"version": VERSION, "verified": True, "worker": name,
        "resource_attempt_number": state["resource_attempt_number"],
        "source": plan["source"], "identity": identity, "process_observation": observed,
        "original_process_exited": True, "new_model_calls": 0, "new_backward_calls": 0,
        "new_optimizer_steps": 0, "new_training_interval_seconds": 0,
        "loader_not_entered": True, "retryable": True,
        "original_files": [reference(folder / name) for name in sorted(files)]}


def archive_resource_attempt(root, name, state, proof, *, ended_at):
    """Move the entire resource-only folder, recording every old/new path and SHA."""
    root = Path(root).resolve()
    folder = root / name
    number = state["resource_attempt_number"]
    if (proof.get("verified") is not True or proof.get("worker") != name
            or proof.get("resource_attempt_number") != number or proof.get("original_process_exited") is not True):
        raise ValueError("Archival requires the bound verified resource failure")
    destination = root / "resource-attempts" / name / f"attempt-{number:04d}"
    if destination.exists():
        raise FileExistsError("Never overwrite a retained resource attempt")
    elapsed = ended_at - state["started_at"]
    if elapsed < 0:
        raise ValueError("Resource attempt time cannot be negative")
    mapping = []
    for old in proof["original_files"]:
        relative = Path(old["path"]).relative_to(folder)
        if reference(folder / relative) != old:
            raise ValueError("Resource evidence changed before archival")
        mapping.append({"original": old, "archived": {"path": str(destination / relative), "sha256": old["sha256"]}})
    destination.parent.mkdir(parents=True, exist_ok=True)
    folder.rename(destination)
    for row in mapping:
        if reference(Path(row["archived"]["path"])) != row["archived"]:
            raise ValueError("Resource evidence changed during archival")
    receipt = host.seal({"version": VERSION, "worker": name, "resource_attempt_number": number,
        "original_root": str(folder), "archived_root": str(destination), "archive_mapping": mapping,
        "all_original_bytes_preserved": True, "original_paths_moved_not_retained_in_place": True,
        "classification": proof, "original_launch_state": copy.deepcopy(state),
        "started_at": state["started_at"], "ended_at": ended_at, "elapsed_gpu_seconds": elapsed,
        "exit_code": 0, "new_model_calls": 0, "new_backward_calls": 0,
        "new_optimizer_steps": 0, "new_training_interval_seconds": 0,
        "next_resource_attempt_at": ended_at + retry_delay(number),
        "resource_cost_included_once_separately_from_formal_worker": True})
    path = destination / "archive-mapping.json"
    write(path, receipt)
    history = [*state.get("resource_attempt_history", []), reference(path)]
    prior_cost = state.get("resource_attempt_gpu_seconds", 0) + elapsed
    for key in ("pid", "process_identity", "gpu", "gpu_uuid", "reservation", "command", "started_at",
            "launch_intent_at", "source_worktree", "external_residents_at_launch", "exit_code", "ended_at", "stop_reason"):
        state.pop(key, None)
    state.update(status="not_started", attempted=False, model_started=False, scientific_attempted=False,
        resource_attempted=True, resource_attempt_history=history, resource_attempt_gpu_seconds=prior_cost,
        elapsed_gpu_seconds=0, next_resource_attempt_at=receipt["next_resource_attempt_at"],
        last_resource_failure=reference(path))
    return receipt


def initial_summary(plan, *, now, observer_pid):
    return {"version": VERSION, "status": "waiting", "started_at": now,
        "observer_pid": observer_pid, "source": plan["source"], "states": initial_states(plan),
        "parent_plan": plan["parent_plan"], "external_Q_plus_binding": plan["external_Q_plus"],
        "external_Q_plus_owned_by_original_host": True, "external_process_signalled": False,
        "new_worker_cost_excludes_external_observation": True,
        "resource_policy": plan["resource_policy"], "startup_retry_policy": plan["startup_retry_policy"],
        "single_slot_scheduling": plan["single_slot_scheduling"], "maximum_residents": None,
        "old_worker_cost_counted_once_in_parent": True,
        "attempted_field_means_current_process_launch_not_model_entry": True}


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = initial_summary(plan, now=time.time(), observer_pid=os.getpid())
    active, logs, guards = {}, {}, {}
    external = None

    def publish():
        now = time.time()
        summary.update(observed_at=now,
            closed_worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            resource_attempt_gpu_seconds=sum(s.get("resource_attempt_gpu_seconds", 0) for s in summary["states"].values()),
            running_worker_gpu_seconds=sum(now - summary["states"][n]["started_at"] for n in active))
        ready = eligible_workers(summary["states"], external, now=now)
        backed_off = [name for name, state in summary["states"].items()
            if state["status"] == "not_started" and state.get("next_resource_attempt_at", 0) > now]
        paused = bool(mechanism_pauses(root))
        terminal = all(s["status"] in {"complete", "stopped"} for s in summary["states"].values())
        summary.update(monitoring_active_workers=len(active), ready_worker_count=len(ready),
            resource_backoff_workers=backed_off,
            dispatch_status="paused" if paused else "closed" if terminal else "ready" if ready
                else "resource_backoff" if backed_off else "awaiting_dependency_or_active_workers")
        summary["new_worker_gpu_seconds_observed"] = sum(summary[k] for k in
            ("closed_worker_gpu_seconds", "resource_attempt_gpu_seconds", "running_worker_gpu_seconds"))
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process, state = active[name], summary["states"][name]
        if process.poll() is None:
            request_stop(root, name, process, state, reason)
        process.wait(timeout=15)
        active.pop(name)
        guards.pop(name, None)
        logs.pop(name).close()
        ended = time.time()
        if (root / name / "resource-wait.json").exists():
            try:
                proof = verify_resource_failure(root, name, state, plan,
                    exit_code=process.returncode, reason=reason, identity_fn=worker_identity)
            except (OSError, ValueError, KeyError, TypeError) as error:
                state["resource_retry_rejected"] = {"type": type(error).__name__, "message": str(error)}
            else:
                archive_resource_attempt(root, name, state, proof, ended_at=ended)
                publish()
                return
        result = read(root / name / "actual/report.json") or {}
        marker = (root / name / "startup/model-load-intent.json").exists()
        state.update(model_started=marker, scientific_attempted=marker)
        complete = (process.returncode == 0 and reason is None and result.get("status") == "complete"
            and result.get("source_before") == result.get("source_after") == plan["source"]
            and result.get("success_boundary") is True and marker)
        state.update(status="complete" if complete else "stopped", stop_reason=reason,
            exit_code=process.returncode, ended_at=ended, elapsed_gpu_seconds=ended - state["started_at"])
        if name in host.DEVELOPMENT:
            rows = result.get("rows", [])
            state["single_slot_cost"] = {"slot_id": state["planned_slots"][0],
                "original_worker": state["original_worker"], "elapsed_gpu_seconds": state["elapsed_gpu_seconds"],
                "resource_attempt_gpu_seconds": state["resource_attempt_gpu_seconds"],
                "resource_attempt_seconds_are_separate": True,
                "includes_model_load_and_final_guards": True,
                "formal_result_known": len(rows) == 1 and rows[0].get("R") in (0, 1),
                "usage": copy.deepcopy(rows[0].get("usage")) if len(rows) == 1 else None,
                "complete_worker": complete}
        if not complete:
            normal = (process.returncode == 0 and reason is None
                and result.get("source_before") == result.get("source_after") == plan["source"]
                and result.get("status") in {"measurement_pending", "global_pause", "paused_before_next_slot"})
            write(root / "mechanism-stops" / (name + "-supervisor.json"), {
                "kind": result.get("status") if normal else "execution_fault",
                "reason": reason or result.get("status", "worker_incomplete"), "worker": name,
                "observed_at": ended, "worker_state": copy.deepcopy(state)})
        publish()

    def pause_unopened(reason):
        for state in summary["states"].values():
            if state["status"] == "not_started":
                state.update(status="stopped", stop_reason=reason, elapsed_gpu_seconds=0)

    with lock(root):
        if (root / "supervisor.json").exists():
            raise FileExistsError("Only in-process verified resource retries are automatic; never replay an existing host")
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
                            "error": str(error), "observed_at": time.time(), "external_process_signalled": False,
                            "original_worker_identity": plan["external_Q_plus"]})
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [reference(p) for p in mechanism_pauses(root)]
                    pause_unopened("unopened_work_paused")
                if all(s["status"] in {"complete", "stopped"} for s in summary["states"].values()):
                    summary["status"] = "complete" if all(s["status"] == "complete" for s in summary["states"].values()) else "closed_with_unknowns"
                    break
                size = sum(artifact_bytes(Path(path)) for path in support.dense._artifact_roots([*plan["prior_artifact_roots"], root]))
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
                    summary["last_resource_sample_at"] = time.time()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    excluded = [summary["states"][name]["gpu"] for name in active]
                    if external.get("excluded_gpu") is not None:
                        excluded.append(external["excluded_gpu"])
                    cards = available_cards(plan, sample, excluded)
                    for card in cards:
                        if not waiting or mechanism_pauses(root):
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
                        state = summary["states"][name]
                        state.update(attempted=True, resource_attempted=True, launch_intent_at=time.time(),
                            gpu=card["index"], gpu_uuid=card["uuid"], command=argv,
                            source_worktree=str(SOURCE), external_residents_at_launch=external["resident_count"],
                            reservation=reservation, resource_attempt_number=state["resource_attempt_number"] + 1)
                        publish()
                        write(folder / "worker-launch.json", {"actual_command": argv, "cwd": str(SOURCE),
                            "source": plan["source"], "pythonpath": env["PYTHONPATH"], "gpu": card["index"],
                            "reservation": reservation, "original_worker": host.original_worker(name),
                            "planned_units": host.worker_units(plan, name),
                            "resource_attempt_number": state["resource_attempt_number"],
                            "new_model_budget": False, "total_residents_after_launch": len(active) + external["resident_count"] + 1,
                            "recorded_at": time.time(), "phase": "before_popen"})
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                            stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        state.update(status="running", pid=process.pid, process_identity=identity, started_at=started)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=len(active)) as pool:
                        futures = {name: pool.submit(target_resources, summary["states"][name]["gpu"], worker_pid=p.pid) for name, p in active.items()}
                        samples = {name: f.result() for name, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        marker = (root / name / "startup/model-load-intent.json").exists()
                        state.update(model_started=marker, scientific_attempted=marker)
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"], own_memory_limit_mib=None)
                        current = read(root / name / "actual/task.json") or read(root / name / "startup/task.json") or {
                            "kind": "reservation_wait", "started_at": state["started_at"]}
                        # Resource "ready" precedes full frozen validation and
                        # cannot consume the model loader's 900-second clock.
                        if not marker:
                            current = {**current, "kind": "reservation_wait"}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason") or task_stop_reason(current, now=time.time(), rss_bytes=own_rss)
                        compute = read(root / name / "actual/training-compute.json")
                        reason = reason or training_stop_reason(plan, name, compute, now=time.time())
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[name], "guard": guard, "task": current,
                                "training_compute": compute, "rss_bytes": own_rss, "artifact_bytes": size, "volume_free_bytes": free}) + "\n")
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
                "reason": "supervisor_interrupted_or_failed", "error": summary["error"], "observed_at": time.time(),
                "external_process_signalled": False})
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
