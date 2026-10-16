"""Own sixteen original development slots under a global four-resident cap."""
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
from scripts import software_learning_resume_v050r6 as host
from scripts import software_learning_resume_supervisor_v050r5 as previous
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_v049r2g import bind, resources
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-development-supervisor-v0.50-r6"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
MAX_RESIDENTS = 4
BRANCHES = ("Q_plus", "Q_minus")
resource = host.resource
allowed_resources = resources(host.GPU_ORDER).allowed_resources
worker_env = host.worker_env
available_cards = resource.available_cards
mechanism_pauses = previous.mechanism_pauses
task_stop_reason = bind(previous.task_stop_reason, LIMITS=LIMITS)
initial_states = bind(previous.initial_states, WORKERS=WORKERS, host=host)
retry_delay = bind(previous.retry_delay, host=host)
request_stop = bind(previous.request_stop, WORKERS=WORKERS)
verify_resource_failure = bind(previous.verify_resource_failure, WORKERS=WORKERS,
    host=host, SOURCE=SOURCE, VERSION=VERSION)
archive_resource_attempt = bind(previous.archive_resource_attempt, host=host,
    VERSION=VERSION, retry_delay=retry_delay)


def external_residency(externals):
    """Pending and unavailable identities retain their reservation until proven closed."""
    if externals is None:
        return 2
    if not isinstance(externals, dict) or set(externals) != set(BRANCHES):
        raise ValueError("Both original external update identities must be represented")
    count = 0
    for branch in BRANCHES:
        observation = externals[branch]
        if not isinstance(observation, dict):
            raise ValueError("External residency is unbound")
        status = observation.get("status")
        resident = observation.get("resident_count")
        if type(resident) is not int or resident not in (0, 1):
            raise ValueError("Each external update has explicit zero or one residency")
        if status == "complete":
            if resident != 0 or not isinstance(observation.get("terminal"), dict):
                raise ValueError("Only validated terminal checkpoints release residency")
        elif status in {"running", "awaiting_original_host_closure",
                "awaiting_original_worker_exit", "fault", "pending"}:
            if resident != 1:
                raise ValueError("A pending or unknown external update still occupies one place")
        else:
            raise ValueError("Unclassified external status cannot release capacity")
        count += resident
    return count


def resident_accounting(states, externals):
    # The pre-Popen reservation is already occupied. runtime_reservation retains
    # the original not_started/running vocabulary, so attempted disambiguates it.
    own = sum(state.get("status") == "running" or
        (state.get("status") == "not_started" and state.get("attempted") is True)
        for state in states.values())
    external = external_residency(externals)
    total = own + external
    if total > MAX_RESIDENTS:
        raise ValueError("Global resident count exceeds the frozen user cap")
    return {"max_residents": MAX_RESIDENTS, "maximum_residents": MAX_RESIDENTS,
        "owned_residents": own, "external_residents": external,
        "total_residents": total, "slots_available": MAX_RESIDENTS - total}


def resident_capacity(states, externals):
    return resident_accounting(states, externals)["slots_available"]


def excluded_gpus(states, externals, plan):
    used = {state["gpu"] for state in states.values() if state.get("status") == "running"
        or (state.get("status") == "not_started" and state.get("attempted") is True)}
    external_residency(externals)
    for branch in BRANCHES:
        observed = None if externals is None else externals[branch]
        if observed is None or observed["status"] != "complete":
            bound = plan["external_updates"][branch]["identity"]["gpu"]
            if observed is not None and observed.get("excluded_gpu") != bound:
                raise ValueError("Pending external residency must exclude its bound physical GPU")
            used.add(bound)
    return sorted(used)


def eligible_workers(states, externals, *, now=None):
    now = time.time() if now is None else now
    if set(states) != set(WORKERS):
        raise ValueError("This host owns only the original sixteen development slots")
    external_residency(externals)
    if externals is None or any(row["status"] == "fault" for row in externals.values()):
        return []
    ready_branches = {branch for branch, row in externals.items() if row["status"] == "complete"}
    return [name for name in WORKERS if any(name.startswith("dev-" + branch + "-")
        for branch in ready_branches) and states[name]["status"] == "not_started"
        and states[name].get("attempted") is False and states[name].get("model_started") is False
        and now >= states[name].get("next_resource_attempt_at", 0)]


def dispatch_diagnostics(states, externals, *, now, paused=False, resource_wait=False):
    accounting = resident_accounting(states, externals)
    ready = eligible_workers(states, externals, now=now)
    backed_off = [name for name, state in states.items() if state["status"] == "not_started"
        and state.get("next_resource_attempt_at", 0) > now]
    terminal = all(state["status"] in {"complete", "stopped"} for state in states.values())
    status = ("paused" if paused else "closed" if terminal else
        "concurrency_wait" if ready and accounting["slots_available"] == 0 else
        "resource_wait" if ready and resource_wait else "ready" if ready else
        "resource_backoff" if backed_off else
        "active_workers" if accounting["owned_residents"] else "awaiting_dependencies")
    return {**accounting, "ready_worker_count": len(ready),
        "resource_backoff_workers": backed_off, "dispatch_status": status}


def store_external_terminal(root, branch, terminal):
    if branch not in BRANCHES or terminal.get("branch") != branch:
        raise ValueError("Every external checkpoint receipt must bind its own branch")
    path = Path(root) / ("external-" + branch + "-complete.json")
    if path.exists():
        saved = host.check_seal(read(path))
        variable = {"sha256", "original_supervisor_status"}
        if {k: v for k, v in saved.items() if k not in variable} != {
                k: v for k, v in terminal.items() if k not in variable}:
            raise ValueError("The bound external checkpoint or worker receipt changed")
    else:
        write(path, host.seal(terminal))
    return reference(path)


def initial_summary(plan, *, now, observer_pid):
    if plan["limits"].get("max_parallel_model_instances") != MAX_RESIDENTS:
        raise ValueError("The frozen plan must enforce the user cap of four")
    return {"version": VERSION, "status": "waiting", "started_at": now,
        "observer_pid": observer_pid, "source": plan["source"], "states": initial_states(plan),
        "parent_plan": plan["parent_plan"], "external_update_bindings": plan["external_updates"],
        "external_updates_owned_by_original_hosts": True, "external_process_signalled": False,
        "new_worker_cost_excludes_external_observation": True,
        "resource_policy": plan["resource_policy"], "startup_retry_policy": plan["startup_retry_policy"],
        "single_slot_scheduling": plan["single_slot_scheduling"], "maximum_residents": MAX_RESIDENTS,
        "old_worker_cost_counted_once_in_parent": True,
        "attempted_field_means_current_process_launch_not_model_entry": True,
        "owned_update_workers": [], "new_training_budget": 0}


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = initial_summary(plan, now=time.time(), observer_pid=os.getpid())
    active, logs, guards = {}, {}, {}
    externals = None
    resource_wait = False

    def publish():
        now = time.time()
        summary.update(observed_at=now,
            closed_worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            resource_attempt_gpu_seconds=sum(s.get("resource_attempt_gpu_seconds", 0) for s in summary["states"].values()),
            running_worker_gpu_seconds=sum(now - summary["states"][n]["started_at"] for n in active))
        summary.update(monitoring_active_workers=len(active), **dispatch_diagnostics(
            summary["states"], externals, now=now,
            paused=bool(mechanism_pauses(root)), resource_wait=resource_wait))
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
                    externals = host.observe_externals(plan, prior=externals)
                    resident_accounting(summary["states"], externals)
                    excluded_gpus(summary["states"], externals, plan)
                    for branch, observed in externals.items():
                        if observed["status"] == "complete":
                            summary["external_" + branch + "_terminal"] = store_external_terminal(
                                root, branch, observed["terminal"])
                    summary["external_update_observations"] = copy.deepcopy(externals)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    # Preserve already validated terminal observations; an unknown
                    # update never frees a resident place or a physical card.
                    externals = {branch: row if isinstance(row, dict) and row.get("status") == "complete"
                        and row.get("resident_count") == 0 and isinstance(row.get("terminal"), dict)
                        else {"status": "fault", "resident_count": 1,
                            "excluded_gpu": plan["external_updates"][branch]["identity"]["gpu"],
                            "error": str(error)}
                        for branch, row in ((branch, (externals or {}).get(branch)) for branch in BRANCHES)}
                    summary["external_update_observations"] = copy.deepcopy(externals)
                    path = root / "mechanism-stops/external-updates.json"
                    if not path.exists():
                        write(path, {"kind": "global_pause", "reason": "external_dependency_failed_or_unbound",
                            "error": str(error), "observed_at": time.time(), "external_process_signalled": False,
                            "original_worker_identities": plan["external_updates"]})
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
                waiting = eligible_workers(summary["states"], externals)
                resource_wait = False
                if waiting and resident_capacity(summary["states"], externals) > 0:
                    sample = allowed_resources()
                    summary["last_resource_sample_at"] = time.time()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    excluded = excluded_gpus(summary["states"], externals, plan)
                    cards = available_cards(plan, sample, excluded)
                    resource_wait = not cards
                    for card in cards:
                        # Recompute before EVERY Popen, including zero-model retries.
                        if not waiting or mechanism_pauses(root) or resident_capacity(summary["states"], externals) <= 0:
                            break
                        if card["index"] in excluded_gpus(summary["states"], externals, plan):
                            continue
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
                            source_worktree=str(SOURCE), external_residents_at_launch=external_residency(externals),
                            reservation=reservation, resource_attempt_number=state["resource_attempt_number"] + 1)
                        publish()
                        write(folder / "worker-launch.json", {"actual_command": argv, "cwd": str(SOURCE),
                            "source": plan["source"], "pythonpath": env["PYTHONPATH"], "gpu": card["index"],
                            "reservation": reservation, "original_worker": host.original_worker(name),
                            "planned_units": host.worker_units(plan, name),
                            "resource_attempt_number": state["resource_attempt_number"],
                            "new_model_budget": False, "total_residents_after_launch": resident_accounting(summary["states"], externals)["total_residents"],
                            "maximum_residents": MAX_RESIDENTS,
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
                        reason = reason or ("unexpected_training_compute_evidence" if compute is not None else None)
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
