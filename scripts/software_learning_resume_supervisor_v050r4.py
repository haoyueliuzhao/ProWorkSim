"""Own both new Q attempts, adopting the already reserved GPU2 process exactly."""
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
from scripts import software_learning_resume_v050r4 as host
from scripts import software_learning_resume_supervisor_v050r3 as prior
from scripts import software_learning_reservation_adoption_v050r4 as adoption
from scripts import software_learning_resources_v050r3 as resource
from scripts import software_support_v036 as support
from scripts.software_learning_development_resume_supervisor_v049r2 import request_stop as inherited_stop
from scripts.software_learning_development_resume_v049r2g import resources
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import lock, read, reference, write

VERSION = "software-learning-original-Q-supervisor-v0.50-r4"
SOURCE, WORKERS, LIMITS = host.SOURCE, host.WORKERS, host.LIMITS
allowed_resources = resources(host.GPU_ORDER).allowed_resources
worker_env = host.worker_env
task_stop_reason = prior.task_stop_reason
mechanism_pauses = prior.mechanism_pauses
available_cards = resource.available_cards


def initial_states(plan):
    return {name: {"worker": name, "status": "not_started", "attempted": False,
        "planned_slots": [u["slot_id"] for u in host.worker_units(plan, name)],
        "original_worker": host.original_worker(name)} for name in WORKERS}


def eligible_workers(states):
    if set(states) != set(WORKERS):
        raise ValueError("Own exactly two Q recomputations and sixteen original development slots")
    allowed = list(host.UPDATES)
    for branch in ("Q_plus", "Q_minus"):
        if states["update-" + branch]["status"] == "complete":
            allowed.extend(name for name in host.DEVELOPMENT if name.startswith("dev-" + branch + "-"))
    return [name for name in WORKERS if name in allowed and states[name]["status"] == "not_started"
        and states[name].get("attempted") is False]


def training_stop_reason(plan, worker, receipt, *, now):
    from scripts import software_learning_resume_compute_v050r4 as compute
    if worker not in host.UPDATES or receipt is None:
        return None
    budget = plan["q_compute_replay"]["branches"][worker.removeprefix("update-")]
    expected = budget["remaining_seconds"]
    if (not isinstance(receipt, dict) or type(receipt.get("started_at")) not in (int, float)
            or receipt.get("maximum_seconds") != expected
            or receipt.get("replay_budget_sha256") != budget["sha256"]):
        return "training_compute_budget_unbound"
    ended = receipt.get("ended_at")
    reason = compute.training_stop_reason(receipt, now=now if ended is None else ended)
    if reason is None and ended is None and now >= receipt["started_at"] + expected - 30:
        return "training_compute_reclamation_reserve"
    return reason


def request_stop(root, name, process, state, reason):
    if name not in WORKERS or state.get("pid") != process.pid or state.get("worker") != name:
        raise ValueError("Only exact owned r4 workers may receive a stop")
    if isinstance(process, adoption.AdoptedProcess):
        process.assert_owned()
    return inherited_stop(root, name, process, state, reason)


def initial_summary(plan, *, now, observer_pid):
    return {"version": VERSION, "status": "waiting", "started_at": now,
        "observer_pid": observer_pid, "source": plan["source"], "states": initial_states(plan),
        "parent_plan": plan["parent_plan"], "original_r1_plan": plan["original_r1_plan"],
        "resource_policy": plan["resource_policy"], "single_slot_scheduling": plan["single_slot_scheduling"],
        "maximum_residents": None, "external_Q_plus_dependency": False,
        "gpu2_lease": plan["gpu2_lease"], "old_worker_cost_counted_once": True}


def adopt_reserved(root, plan, summary, *, publish, on_owned=None):
    """Publish ownership before handoff; never replace the existing process."""
    binding = plan["gpu2_lease"]
    name = "update-Q_plus"
    process = adoption.AdoptedProcess(binding)
    process.assert_owned()
    observed = adoption.observe_lease(binding)
    if observed.get("status") != "running" or observed.get("worker_entry_at") is not None:
        raise ValueError("Only the exact still-unused live GPU2 lease can be adopted")
    folder = Path(root) / name
    folder.mkdir(exist_ok=False)
    identity = worker_identity(process.pid)
    now = time.time()
    summary["states"][name].update(status="running", attempted=True, pid=process.pid,
        process_identity=identity, gpu=binding["gpu"], gpu_uuid=binding["gpu_uuid"],
        command=binding["actual_command"], launch_cwd=binding["launch_cwd"],
        source_worktree=str(SOURCE), reservation=binding["reservation"],
        lease_binding=binding, launch_mode="adopted_reservation", started_at=now,
        process_started_at=binding["launched_at"], adopted_at=now)
    write(folder / "worker-launch.json", {"actual_command": binding["actual_command"],
        "cwd": binding["launch_cwd"], "source_worktree": str(SOURCE),
        "launch_mode": "adopted_reservation", "lease_binding": binding,
        "actual_log": str(Path(binding["lease_root"]) / "reservation.log"),
        "gpu": binding["gpu"], "gpu_uuid": binding["gpu_uuid"],
        "reservation": binding["reservation"], "original_worker": name, "planned_units": [],
        "worker_entry": {"module": host.MODULE, "function": "run_worker", "run_root": str(root),
            "worker": name, "output": str(folder / "actual")},
        "recorded_at": now, "phase": "before_handoff", "new_popen": False})
    publish()
    guard = TelemetryGuard(binding["gpu"], binding["gpu_uuid"], identity["start_ticks"], worker_pid=process.pid)
    if on_owned is not None:
        on_owned(process, guard)
    receipt = adoption.write_handoff(binding, source_commit=plan["source"]["code_commit"])
    summary["states"][name]["handoff"] = receipt
    publish()
    return process, guard


def supervise(root):
    root = Path(root).resolve()
    plan = host.frozen(root)
    summary = initial_summary(plan, now=time.time(), observer_pid=os.getpid())
    active, logs, guards = {}, {}, {}

    def publish():
        summary.update(observed_at=time.time(),
            closed_worker_gpu_seconds=sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values()),
            running_worker_gpu_seconds=sum(time.time() - summary["states"][n].get("process_started_at", summary["states"][n]["started_at"]) for n in active))
        write(root / "supervisor.json", summary)

    def close(name, reason):
        process, state = active[name], summary["states"][name]
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
        if isinstance(process, adoption.AdoptedProcess):
            observed = adoption.observe_lease(plan["gpu2_lease"], now=ended)
            started = plan["gpu2_lease"]["launched_at"]
            entry = observed.get("worker_entry_at")
            prelease = (ended if entry is None else entry) - started
            formal = 0 if entry is None else ended - entry
            identity = observed.get("process_identity", {})
            exit_known = identity.get("available") is True and identity.get("alive") is False
            state.update(lease_terminal_observation=observed,
                proxy_returncode=process.returncode, exit_code=observed.get("exit_code"),
                resource_prelease_seconds=prelease, formal_worker_gpu_seconds=formal,
                elapsed_gpu_seconds=ended - started, cost_observed_through_at=ended,
                complete_process_cost_known=exit_known,
                exit_code_provenance="bootstrap_receipt_not_waitpid" if observed["status"] == "terminal" else "unknown_no_bound_exit_receipt",
                prelease_included_in_total=True, entry_intent_is_model_call_evidence=False)
            if exit_known:
                state["process_exit_observed_at"] = ended
        if name in host.DEVELOPMENT:
            rows = result.get("rows", [])
            state["single_slot_cost"] = {"slot_id": state["planned_slots"][0],
                "original_worker": state["original_worker"], "elapsed_gpu_seconds": state["elapsed_gpu_seconds"],
                "includes_model_load_and_final_guards": True,
                "formal_result_known": len(rows) == 1 and rows[0].get("R") in (0, 1),
                "usage": copy.deepcopy(rows[0].get("usage")) if len(rows) == 1 else None,
                "complete_worker": complete}
        stream = logs.pop(name, None)
        if stream is not None:
            stream.close()
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
            raise FileExistsError("An attempted r4 worker is never automatically replayed")
        publish()
        try:
            def register_adoption(process, guard):
                active["update-Q_plus"], guards["update-Q_plus"] = process, guard
            adopt_reserved(root, plan, summary, publish=publish, on_owned=register_adoption)
            while True:
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        close(name, None if process.returncode == 0 else "worker_exit_error")
                if mechanism_pauses(root):
                    summary["mechanism_pauses"] = [reference(path) for path in mechanism_pauses(root)]
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
                waiting = eligible_workers(summary["states"])
                if waiting:
                    sample = allowed_resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    cards = available_cards(plan, sample, [summary["states"][n]["gpu"] for n in active])
                    for card in cards:
                        if not waiting or mechanism_pauses(root):
                            break
                        name = waiting.pop(0)
                        if name == "update-Q_plus":
                            raise ValueError("Q-plus must never be replaced by Popen")
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        argv = [plan["native_python"], "-m", host.MODULE, "worker", "--run-root", str(root), "--worker", name, "--output", str(folder / "actual")]
                        logs[name] = (folder / "worker.log").open("x")
                        temporary = folder / "tmp"
                        temporary.mkdir()
                        reservation = resource.launch_target(card)
                        env = worker_env(plan, card["index"], reservation)
                        env.update(TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
                        summary["states"][name].update(attempted=True, launch_intent_at=time.time(),
                            gpu=card["index"], gpu_uuid=card["uuid"], command=argv,
                            source_worktree=str(SOURCE), reservation=reservation, launch_mode="popen")
                        publish()
                        write(folder / "worker-launch.json", {"actual_command": argv, "cwd": str(SOURCE),
                            "launch_mode": "popen", "pythonpath": env["PYTHONPATH"], "gpu": card["index"],
                            "reservation": reservation, "original_worker": host.original_worker(name),
                            "planned_units": host.worker_units(plan, name), "total_residents_after_launch": len(active) + 1,
                            "recorded_at": time.time(), "phase": "before_popen"})
                        process = subprocess.Popen(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                            stdout=logs[name], stderr=subprocess.STDOUT, start_new_session=True)
                        identity = worker_identity(process.pid)
                        summary["states"][name].update(status="running", pid=process.pid,
                            process_identity=identity, started_at=time.time())
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        publish()
                if active:
                    with ThreadPoolExecutor(max_workers=len(active)) as pool:
                        futures = {n: pool.submit(target_resources, summary["states"][n]["gpu"], worker_pid=p.pid) for n, p in active.items()}
                        samples = {n: f.result() for n, f in futures.items()}
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            close(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        if isinstance(process, adoption.AdoptedProcess):
                            observation = adoption.observe_lease(plan["gpu2_lease"])
                            state["lease_observation"] = observation
                            if observation.get("worker_entry_at") is not None:
                                state["worker_entry_at"] = observation["worker_entry_at"]
                                state["started_at"] = observation["worker_entry_at"]
                        guard = guards[name].observe(samples[name], time.time(), process.pid, state["gpu"], own_memory_limit_mib=None)
                        pending = isinstance(process, adoption.AdoptedProcess) and state.get("worker_entry_at") is None
                        current = read(root / name / "actual/task.json") or {"kind": "reservation_wait" if pending else "loading", "started_at": state["started_at"]}
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
                if (isinstance(active[name], adoption.AdoptedProcess)
                        and not (Path(plan["gpu2_lease"]["lease_root"]) / "handoff.json").exists()):
                    # A pre-handoff validation failure cannot release the user's
                    # already reserved GPU2 process or begin model work.
                    active.pop(name)
                    summary["states"][name].update(status="stopped", stop_reason="handoff_not_published_lease_preserved",
                        lease_process_signalled=False, model_entry_dispatched=False)
                    continue
                close(name, "supervisor_interrupted")
            write(root / "mechanism-stops/supervisor-exception.json", {"kind": "execution_fault",
                "reason": "supervisor_interrupted_or_failed", "error": summary["error"], "observed_at": time.time()})
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
