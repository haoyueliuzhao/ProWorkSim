"""Continue the fixed v031 DAG: two old-trace proofs, then selection and report.

The numerical workers each execute once, without sampling or optimizer steps.
Their original reports remain untouched; controller admission proofs carry the
entire assigned-process cost, including loading, imports, cleanup and failures.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
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
from proworksim.storage import digest, json_bytes, read_json
from scripts import probe_dense_replay_v031 as probe
from scripts import software_model_selection_v030 as original
from scripts import software_model_selection_v031 as selection
from scripts.recover_software_model_selection_v030 import _await_gone, cancel_reservation
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write
from scripts.software_development_v028 import _release_reservation_pid, available_cards

VERSION = "continue-model-selection-v0.31"
SOURCE = Path(__file__).resolve().parents[1]
EXECUTED = selection.EXECUTED
LIMITS = selection.LIMITS
GPU_ORDER = selection.GPU_ORDER
GATES = ("all_full_tokens_retained", "all_behavior_and_gradient_probability_passed",
         "full_backward_completed", "original_actor_identity_matched", "common_restored_exactly")
BINDINGS = ("candidate_id", "profile_sha256", "source", "tested_files_sha256", "original_trace_refs")


def terminal_proof(binding, state, worker_report_path):
    """Close even a killed/missing-report attempt without inventing a pass."""
    path = Path(worker_report_path)
    worker_ref, report, error = None, {}, None
    if path.is_file():
        worker_ref = reference(path)
        try:
            report = read_json(path)
            if not isinstance(report, dict):
                raise ValueError("Worker report is not an object")
        except (ValueError, OSError) as exception:
            report, error = {}, str(exception)
    reason = state.get("stop_reason")
    if reason is None:
        if state.get("exit_code") != 0:
            reason = "worker_exit_error"
        elif not report:
            reason = "worker_report_unreadable" if error else "worker_report_missing"
        elif any(report.get(key) != binding[key] for key in BINDINGS):
            reason = "worker_binding_mismatch"
        elif not report.get("ended_at") or report.get("status") != "passed" or report.get("passed") is not True:
            reason = "worker_numeric_proof_failed"
        elif any(report.get(key) is not True for key in (*GATES, "source_unchanged", "original_trace_files_unchanged")):
            reason = "worker_numeric_gate_failed"
        elif report.get("new_model_calls") != 0 or report.get("optimizer_steps") != 0:
            reason = "worker_contract_violated"
    value = {**copy.deepcopy(report), **copy.deepcopy(binding), "version": VERSION,
             "status": "passed" if reason is None else "failed", "passed": reason is None,
             "worker_report": worker_ref, "worker_body_seconds": report.get("actual_worker_gpu_seconds"),
             "artifact_directory": str(path.resolve().parent.parent),
             "probe_ledger_directory": str(path.resolve().parent.parent.parent),
             "actual_worker_gpu_seconds": state["actual_worker_gpu_seconds"],
             "started_at": state.get("started_at"), "ended_at": state["ended_at"],
             "controller_reason": reason, "controller_worker_state": copy.deepcopy(state),
             "new_model_calls": report.get("new_model_calls", 0), "optimizer_steps": report.get("optimizer_steps", 0),
             "counter_evidence": "worker_report" if report else "frozen_probe_contract",
             "zero_counter_contract": "The bound old-trace probe contains no sampler or optimizer.step; controller launches only that module.",
             "capacity_proven": False}
    value["controller_worker_state"]["status"] = value["status"]
    for key in GATES:
        value[key] = report.get(key) is True
    if error:
        value["worker_report_read_error"] = error
    return value


def _gpu_processes(sample, gpu_uuid):
    if sample.get("processes", {}).get("returncode") != 0:
        return None
    try:
        rows = list(csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True))
        if any(len(row) != 4 for row in rows):
            return None
        return [int(row[1]) for row in rows if row[0].strip() == gpu_uuid]
    except (ValueError, csv.Error):
        return None


def _bounded_resources(deadline):
    """Each query consumes only the remaining handoff allowance."""
    sample = {"time": time.time()}
    queries = (("gpus", "--query-gpu=index,uuid,name,memory.free,memory.total,utilization.gpu"),
               ("processes", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name"))
    for key, query in queries:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            sample[key] = {"returncode": None, "stdout": "", "stderr": "handoff observation deadline"}
            continue
        try:
            result = subprocess.run(["nvidia-smi", query, "--format=csv,noheader,nounits"],
                                    capture_output=True, text=True, timeout=min(1.0, remaining), check=False)
            sample[key] = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        except (OSError, subprocess.TimeoutExpired) as exception:
            sample[key] = {"returncode": None, "stdout": "", "stderr": str(exception)}
    sample["finished_at"] = time.time()
    return sample


def released_capacity(plan, launch, *, seconds=5.0):
    """Reuse the reservation stability proof only within a five-second handoff."""
    if not 0 < seconds <= 5:
        raise ValueError("Reservation handoff observation is bounded to at most five seconds")
    started = time.monotonic()
    deadline = started + seconds
    observations, card, reason = [], None, "release_observation_timeout"
    while time.monotonic() < deadline:
        sample = _bounded_resources(deadline)
        observations.append(sample)
        pids = _gpu_processes(sample, launch["gpu_uuid"])
        if pids:
            reason = "competing_process_after_release"
            break
        ready = next((row for row in available_cards(plan, sample)
                      if row["index"] == launch["physical_gpu"] and row["uuid"] == launch["gpu_uuid"]), None)
        if ready is not None and time.monotonic() <= deadline:
            card, reason = ready, None
            break
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.1, remaining))
    return card, {"observations": observations, "elapsed_seconds": time.monotonic() - started,
                  "allowance_seconds": seconds, "reason": reason,
                  "immediate_capacity_available": card is not None,
                  "second_empty_card_stability_wait_required": card is None}


def reservation_ready(directory):
    """Bind one declared reservation on any authorized physical GPU, unchanged gates."""
    directory = Path(directory)
    launch, state = read(directory / "launch.json"), read(directory / "state.json")
    if not launch or not state or state.get("status") != "reserved":
        return None
    fields = ("pid", "start_ticks", "physical_gpu", "gpu_uuid")
    if (any(launch.get(key) != state.get(key) for key in fields)
            or type(launch.get("physical_gpu")) is not int or launch["physical_gpu"] not in GPU_ORDER
            or type(launch.get("pid")) is not int or type(launch.get("start_ticks")) is not int
            or not launch.get("user_authorization") or state.get("model_calls") != 0):
        raise ValueError("Declared reservation must bind the same authorized physical GPU, UUID and child PID identity")
    now = time.time()
    identity = worker_identity(launch["pid"])
    if not identity.get("alive") or identity.get("start_ticks") != launch["start_ticks"]:
        return None
    if (now - state.get("ready_at", now) < LIMITS["gpu_capacity_stability_seconds"]
            or not 0 <= now - state.get("heartbeat_at", 0) <= 15):
        return None
    rows = [json.loads(line) for line in (directory / "observations.jsonl").read_text().splitlines() if line.strip()]
    rows = [row for row in rows if state["ready_at"] <= row["observed_at"] <= now]
    previous = state["ready_at"]
    for row in rows:
        if (row.get("uuid") != launch["gpu_uuid"] or row.get("pids") != [launch["pid"]]
                or not 0 <= row["observed_at"] - previous <= 15):
            return None
        previous = row["observed_at"]
    if not rows or now - previous > 15:
        return None
    return {"launch": launch, "state": state, "identity": identity,
            "launch_reference": reference(directory / "launch.json"),
            "observations_reference": reference(directory / "observations.jsonl"),
            "continuous_exclusive_seconds": now - state["ready_at"]}


def _reservation_directories(value):
    values = [] if value is None else [value] if isinstance(value, (str, Path)) else list(value)
    directories = [str(Path(path).resolve()) for path in values]
    if len(set(directories)) != len(directories):
        raise ValueError("A reservation directory may only be declared once")
    return directories


def _cancel_declared_reservation(plan, root):
    """Generalize the old GPU5-only cancellation to the declared bound card."""
    directory = Path(plan["reservation_directory"])
    # The original helper safely closes the watcher and GPU5 child. Other cards
    # need the same explicit launch/identity check before their pidfd release.
    cancel_reservation(plan, root)
    child = read(directory / "launch.json")
    if (child and type(child.get("physical_gpu")) is int and child["physical_gpu"] in GPU_ORDER
            and child["physical_gpu"] != 5 and child.get("user_authorization")):
        identity = worker_identity(child["pid"])
        if identity.get("alive") and identity.get("start_ticks") == child["start_ticks"]:
            _release_reservation_pid(child["pid"], child["start_ticks"])
            receipt_path = Path(root) / "reservation-cancel.json"
            receipt = read(receipt_path)
            receipt["signals"].append({"kind": "reservation_child", "launch": child,
                                       "after": _await_gone(child["pid"], child["start_ticks"])})
            write(receipt_path, receipt)


def handoff_reservation(plan, root):
    """Stop only the authorized reservation child, retaining its original files."""
    directory = plan.get("reservation_directory")
    if not directory:
        return None
    proof = reservation_ready(directory)
    if proof is None:
        return None
    launch = proof["launch"]
    sample = resources()
    if sample.get("gpus", {}).get("returncode") != 0 or _gpu_processes(sample, launch["gpu_uuid"]) != [launch["pid"]]:
        return None
    try:
        rows = list(csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True))
        target = [row for row in rows if len(row) == 6 and row[0].strip() == str(launch["physical_gpu"])]
        if (len(target) != 1 or target[0][1].strip() != launch["gpu_uuid"]
                or "A100" not in target[0][2] or not float(target[0][4]) >= 81920):
            return None
    except (ValueError, csv.Error):
        return None
    receipt = Path(root) / "reservation-handoff.json"
    proof.update(status="verified_before_release", resources_before=sample, verified_at=time.time())
    write(receipt, proof)
    # Keep the watcher alive to reap its child. This sentinel prevents a retry
    # even if the owned child's release itself fails. Never signal other PIDs.
    (Path(directory) / "cancel").touch()
    _release_reservation_pid(launch["pid"], launch["start_ticks"])
    proof.update(identity_after=_await_gone(launch["pid"], launch["start_ticks"]),
                 status="released", released_at=time.time())
    write(receipt, proof)
    card, observation = released_capacity(plan["canonical_plan"], launch)
    proof.update(observation)
    write(receipt, proof)
    return card


def _stop_worker(process, state):
    if process.poll() is not None:
        return
    identity = worker_identity(process.pid)
    if identity.get("start_ticks") != state["process_identity"].get("start_ticks"):
        raise RuntimeError("Refuse to signal a worker whose PID identity changed")
    stop_owned(process)
    process.wait(timeout=15)


def supervise_probes(resource_plan, prior, bindings, root, recovery_root, reservation_directory):
    """Single-attempt, at-most-two numerical workers; queue time is uncapped."""
    root = Path(root)
    states = {name: {"candidate_id": name, "status": "not_started", "attempted": False,
                     "actual_worker_gpu_seconds": 0.0} for name in EXECUTED}
    summary = {"version": VERSION, "status": "waiting", "started_at": time.time(),
               "source": resource_plan["source"], "observer_pid": os.getpid(), "states": states,
               "max_parallel_model_instances": 2, "automatic_retries": False,
               "queue_deadline_at": None, "wall_deadline_at": None, "worker_gpu_seconds_limit": None}
    active, logs, guards, stable = {}, {}, {}, {}
    directories = _reservation_directories(reservation_directory)
    reservations = [{"canonical_plan": resource_plan, "reservation_directory": directory,
                     "receipt_directory": root / "reservation-handoffs" / str(index), "done": False}
                    for index, directory in enumerate(directories)]
    summary["reservation_directories"] = directories
    summary["gpu_preference"] = resource_plan["gpu_preference"]
    proofs = {}

    def publish():
        summary.update(observed_at=time.time(), completed_worker_gpu_seconds=sum(
            state["actual_worker_gpu_seconds"] for state in states.values()),
            running_gpu_seconds=sum(time.time() - states[name]["started_at"] for name in active))
        write(root / "supervisor.json", summary)

    def close(candidate, reason):
        process = active.get(candidate)
        state = states[candidate]
        if process is not None:
            _stop_worker(process, state)
            process.wait(timeout=15)
        ended = time.time()
        state.update(status="failed", ended_at=ended, stop_reason=reason,
                     exit_code=process.returncode if process is not None else None,
                     actual_worker_gpu_seconds=max(0.0, ended - state["started_at"]) if state.get("started_at") else 0.0)
        value = terminal_proof(bindings[candidate], state, root / candidate / "actual/report.json")
        state["status"] = value["status"]
        destination = root / candidate / "admission-proof.json"
        write(destination, value)
        proofs[candidate] = str(destination)
        write(root / candidate / "state.json", state)
        active.pop(candidate, None)
        if candidate in logs:
            logs.pop(candidate).close()

    def launch(candidate, card, *, reserved=False):
        if states[candidate]["attempted"]:
            raise ValueError("A numerical probe can never be retried")
        if code_identity() != resource_plan["source"] or probe.implementation_hashes() != bindings[candidate]["tested_files_sha256"]:
            raise ValueError("Frozen numerical implementation changed while queued")
        checked(resource_plan["qualification"])
        for ref in bindings[candidate]["original_trace_refs"]:
            checked(ref)
        folder = root / candidate
        folder.mkdir(exist_ok=False)
        argv = [sys.executable, "-m", "scripts.probe_dense_replay_v031", "--candidate", candidate,
                "--data-root", resource_plan["data_root"], "--prior-recovery-root", str(recovery_root),
                "--output", str(folder / "actual")]
        state = states[candidate]
        state.update(attempted=True, started_at=time.time(), gpu=card["index"], gpu_uuid=card["uuid"],
                     command=argv, reservation_handoff=reserved)
        logs[candidate] = (folder / "worker.log").open("x")
        try:
            process = subprocess.Popen(argv, cwd=SOURCE,
                env=original.worker_env(resource_plan, root, candidate, card["index"]),
                stdin=subprocess.DEVNULL, stdout=logs[candidate], stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exception:
            state["launch_error"] = {"type": type(exception).__name__, "message": str(exception)}
            close(candidate, "worker_launch_failed")
            return
        identity = worker_identity(process.pid)
        state.update(status="running", pid=process.pid, process_identity=identity)
        active[candidate] = process
        guards[candidate] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
        write(folder / "state.json", state)
        publish()

    def storage_reason():
        size = prior["prior_artifact_bytes"] + artifact_bytes(root)
        free = shutil.disk_usage(root).free
        return ("trajectory_storage_reserve" if size > LIMITS["artifact_bytes"]
                or free < LIMITS["minimum_volume_free_bytes"] else None), size

    with lock(root):
        try:
            while True:
                for candidate, process in list(active.items()):
                    if process.poll() is not None:
                        close(candidate, None if process.returncode == 0 else "worker_exit_error")
                if all(state["status"] in {"passed", "failed"} for state in states.values()):
                    summary["status"] = "completed"
                    break
                waiting = [name for name in EXECUTED if states[name]["status"] == "not_started"]
                disk_reason, size = storage_reason()
                if disk_reason:
                    for candidate in [*active, *waiting]:
                        close(candidate, disk_reason)
                    continue
                if waiting and len(active) < 2:
                    for reservation in reservations:
                        if reservation["done"] or not waiting or len(active) >= 2:
                            continue
                        card = handoff_reservation(reservation, reservation["receipt_directory"])
                        receipt = read(reservation["receipt_directory"] / "reservation-handoff.json") or {}
                        reservation["done"] = receipt.get("status") == "released"
                        if reservation["done"] and card is None:
                            stable.pop(receipt["launch"]["physical_gpu"], None)
                        if card is not None:
                            launch(waiting.pop(0), card, reserved=True)
                    if waiting and len(active) < 2:
                        sample = resources()
                        with (root / "waiting-resources.jsonl").open("a") as stream:
                            stream.write(json.dumps(sample) + "\n")
                        cards = available_cards(resource_plan, sample, [states[name]["gpu"] for name in active])
                        now = time.time()
                        stable = {card["index"]: stable.get(card["index"], now) for card in cards}
                        for card in cards:
                            if not waiting or len(active) >= 2:
                                break
                            if now - stable[card["index"]] >= LIMITS["gpu_capacity_stability_seconds"]:
                                launch(waiting.pop(0), card)
                if not waiting:
                    for reservation in reservations:
                        if not reservation["done"]:
                            _cancel_declared_reservation(reservation, reservation["receipt_directory"])
                            reservation["done"] = True
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {name: pool.submit(target_resources, states[name]["gpu"], worker_pid=process.pid)
                                   for name, process in active.items()}
                        samples = {name: future.result() for name, future in futures.items()}
                    disk_reason, size = storage_reason()
                    for candidate, process in list(active.items()):
                        if process.poll() is not None:
                            close(candidate, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = states[candidate]
                        guard = guards[candidate].observe(samples[candidate], time.time(), process.pid, state["gpu"],
                                                         own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current_task = read(root / candidate / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss, reason = rss(process.pid), guard.get("stop_reason") or disk_reason
                        kind = current_task.get("kind")
                        if kind not in {"loading", "qualification_update", "boundary"}:
                            reason = reason or "unknown_task_kind"
                        elif LIMITS["task_seconds"][kind] is not None and time.time() - current_task["started_at"] >= LIMITS["task_seconds"][kind]:
                            reason = reason or "single_task_budget"
                        if own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = reason or "host_memory_budget"
                        with (root / candidate / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": samples[candidate], "guard": guard, "task": current_task,
                                                     "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            close(candidate, reason)
                summary["status"] = "running" if active else "waiting"
                publish()
                time.sleep(LIMITS["poll_seconds"])
        except BaseException as exception:
            summary.update(status="supervisor_interrupted", error={"type": type(exception).__name__, "message": str(exception)})
            for candidate in EXECUTED:
                if states[candidate]["status"] not in {"passed", "failed"}:
                    close(candidate, "supervisor_interrupted")
            raise
        finally:
            for reservation in reservations:
                if not reservation["done"]:
                    _cancel_declared_reservation(reservation, reservation["receipt_directory"])
                    reservation["done"] = True
            write(root / "numeric-probe-reports.json", proofs)
            summary["ended_at"] = time.time()
            publish()
    return proofs


def continue_selection(data_root, cpu_qualification, original_root, recovery_root,
                       probe_root, run_root, reservation_directory, report_repo, *, publish=False):
    data_root, cpu_qualification, original_root, recovery_root, probe_root, run_root, report_repo = (
        Path(path).resolve() for path in (data_root, cpu_qualification, original_root, recovery_root,
                                        probe_root, run_root, report_repo))
    for new in (probe_root, run_root):
        if new.exists():
            raise FileExistsError("A new probe and selection directory are required: " + str(new))
        if any(new == old or new in old.parents or old in new.parents
               for old in (original_root, recovery_root, run_root if new == probe_root else probe_root)):
            raise ValueError("New and historical run directories must not overlap")
    resource_plan = original.validate_plan(original.make_plan(data_root, cpu_qualification))
    reservation_directory = _reservation_directories(reservation_directory)
    priority = []
    for directory in reservation_directory:
        declaration = read(Path(directory) / "launch.json") or {}
        index = declaration.get("physical_gpu")
        if type(index) is int and index in GPU_ORDER and index not in priority:
            priority.append(index)
    resource_plan["gpu_preference"] = priority + [index for index in GPU_ORDER if index not in priority]
    prior = selection.prior_snapshot(original_root, recovery_root)
    selection.comparison_proof(prior)
    if any(original.download_state(resource_plan, name).get("status") != "ready" for name in EXECUTED):
        raise ValueError("Both fixed model manifests must already be complete")
    bindings = {candidate: {"candidate_id": candidate, "source": resource_plan["source"],
        "profile_sha256": digest(json_bytes(selection.backend_profile(candidate))),
        "tested_files_sha256": probe.implementation_hashes(), "original_trace_refs": [reference(
            recovery_root / candidate / "actual/qualification" / f"native-call-{probe.FAILED_TRACE_INDEX[candidate] + 1}" / "response.json")]}
        for candidate in EXECUTED}
    probe_root.mkdir(parents=True, exist_ok=False)
    state = {"version": VERSION, "status": "probing", "started_at": time.time(), "source": resource_plan["source"],
             "cpu_qualification": reference(cpu_qualification), "original_root": str(original_root),
             "recovery_root": str(recovery_root), "probe_root": str(probe_root), "run_root": str(run_root),
             "report_repo": str(report_repo), "publish": publish,
             "implementation_sha256": digest(Path(__file__).read_bytes()), "probe_bindings": bindings}
    write(probe_root / "continuation.json", state)
    try:
        proofs = supervise_probes(resource_plan, prior, bindings, probe_root, recovery_root, reservation_directory)
        plan = selection.make_plan(data_root, cpu_qualification, original_root, recovery_root, proofs)
        selection.validate_plan(plan)
        plan_path = probe_root / "selection-plan.json"
        write(plan_path, plan)
        state.update(status="selection", numeric_probe_reports=reference(probe_root / "numeric-probe-reports.json"),
                     selection_plan=reference(plan_path))
        write(probe_root / "continuation.json", state)
        if run_root.exists():
            raise FileExistsError("Selection destination was created while probes ran: " + str(run_root))
        outcome = selection.finish(plan_path, run_root, report_repo, publish=publish)
        state.update(status=outcome["status"], finish=outcome)
    except BaseException as exception:
        state.update(status="continuation_failed", error={"type": type(exception).__name__, "message": str(exception)})
        raise
    finally:
        state["ended_at"] = time.time()
        write(probe_root / "continuation.json", state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-root", "cpu-qualification", "original-root", "recovery-root", "probe-root", "run-root", "report-repo"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--reservation-directory", type=Path, action="append",
                        help="Declared owned reservation; repeat in preferred handoff order")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Continuation received signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    result = continue_selection(**vars(args))
    print(json.dumps({key: result[key] for key in ("version", "status", "probe_root", "run_root")}))


if __name__ == "__main__":
    main()
