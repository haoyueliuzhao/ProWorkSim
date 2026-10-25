"""Asynchronously repair the fixed fourteen unknown endpoints under one narrow grant.

The original thirteen interrupted runs stay immutable. Fresh generation and the
single original-terminal reconstruction are separate measurement kinds.
"""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import importlib.util
import json
import signal
import os
import resource
from pathlib import Path, PurePosixPath
import time
import threading
import traceback

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT, BATCH_ROOT = policy.ROOT, policy.BATCH_ROOT
VERSION = "v061-asynchronous-unknown-recovery-coordinator-r1"
SNAPSHOT_RESULT = (
    ROOT
    / "runs/software-benchmark-v061/original-terminal-recovery-r1-20261025/recovery-result.json"
)


def coordinator_limits():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The recovery coordinator must run as the ordinary project user")
    rows = Path("/proc/self/cgroup").read_text().splitlines()
    paths = [line.split(":", 2)[2] for line in rows if line.startswith("0::")]
    if len(paths) != 1:
        raise ValueError("The coordinator requires its own unified cgroup")
    relative = PurePosixPath(paths[0])
    if relative.name != "proworksim-v061-recovery.service" or ".." in relative.parts:
        raise ValueError("Run formal recovery only in the newly owned bounded coordinator unit")
    folder = Path("/sys/fs/cgroup") / str(relative).lstrip("/")
    values = {
        name: (folder / name).read_text().strip()
        for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")
    }
    cpu = values["cpu.max"].split()
    if (
        values["memory.max"] != str(16 * 1024**3)
        or values["memory.swap.max"] != "0"
        or values["pids.max"] != "512"
        or len(cpu) != 2
        or not all(value.isdigit() for value in cpu)
        or int(cpu[1]) <= 0
        or int(cpu[0]) != 4 * int(cpu[1])
    ):
        raise ValueError("Actual coordinator CPU/RAM/PID/swap hard limits differ from the grant")
    return {
        "cgroup": paths[0],
        "actual_limits": values,
        "uid": os.getuid(),
        "host_configuration_changed": False,
    }


def load(ref):
    return json.loads(checked(ref).read_bytes())


def grading_module():
    spec = importlib.util.spec_from_file_location(
        "v061_grading_coordinator", ROOT / "tools/run_recovery_grading_v061.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def prepare():
    plan = policy.create_plan()
    grading = grading_module()
    controls = grading.prepare_controls()
    from proworksim.software_benchmark_snapshot_recovery_v061 import validate_recovery

    snapshot_ref = reference(SNAPSHOT_RESULT)
    snapshot = validate_recovery(snapshot_ref)
    if snapshot.get("measurement_kind") != "original_terminal_snapshot_recovery":
        raise ValueError("The independent original terminal snapshot is not recovered")
    value = {
        "version": VERSION,
        "plan": reference(policy.PLAN_FILE),
        "controls": controls,
        "snapshot_result": snapshot_ref,
        "new_generation_rows": [
            r["slot_index"]
            for r in plan["rows"]
            if r["measurement_kind"] == "fresh_generation_recovery"
        ],
        "new_generation_token_upper_bound": 89000000,
        "new_generation_attempts": 13,
        "original_snapshot_candidates": 1,
        "old_results_overwritten": False,
        "sources": policy.sources(),
        "prepared_without_runtime_operations": True,
    }
    target = BATCH_ROOT / "coordinator-plan.json"
    if target.exists():
        if json.loads(target.read_bytes()) != value:
            raise ValueError("Prepared coordinator plan changed")
        return reference(target)
    return write_new(target, value)


def _event(kind, **values):
    with (BATCH_ROOT / "events.jsonl").open("a") as stream:
        stream.write(
            json.dumps({"unix": time.time(), "kind": kind, **values}, ensure_ascii=False) + "\n"
        )


def _result_is_quiet(result):
    """A local failure may continue only when its owned runtime was cleaned."""
    proof = result.get("quiescence")
    if isinstance(proof, dict) and set(proof) == {"path", "bytes", "sha256"}:
        proof = load(proof)
    return (
        isinstance(proof, dict)
        and proof.get("quiescent") is True
        and not proof.get("cleanup_errors")
    )


def _handle_termination(event):
    if threading.current_thread() is not threading.main_thread():
        return {}
    return {
        sig: signal.signal(sig, lambda *_: event.set()) for sig in (signal.SIGTERM, signal.SIGINT)
    }


def _restore_termination(previous):
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def diagnostic_host_limits():
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 4:
        raise ValueError("The zero-model diagnostic requires four available logical CPUs")
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = 16 * 1024**3 if hard == resource.RLIM_INFINITY else min(hard, 16 * 1024**3)
    if cap < 4 * 1024**3:
        raise ValueError("The inherited address-space limit cannot fit the private SDK diagnostic")
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    os.sched_setaffinity(0, set(allowed[:4]))
    return {
        "address_space_bytes": cap,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "scope": "current ordinary diagnostic process and its children only",
    }


def diagnose(index=1):
    policy.require_v061_allowed("v061.run")
    if index not in (1, 2, 3) or (BATCH_ROOT / "execution-started.json").exists():
        raise ValueError("Diagnostics are limited to three pre-formal preparation pairs")
    if (BATCH_ROOT / "diagnostic-qualification.json").exists():
        raise ValueError("A successful diagnostic already exists; do not run redundant pairs")
    attempts = BATCH_ROOT / "diagnostic-attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    attempt_path = attempts / (str(index) + ".json")
    if attempt_path.exists():
        raise ValueError("This diagnostic attempt already has a retained result")
    host_limits = diagnostic_host_limits()
    from proworksim.software_benchmark_recovery_episode_v061 import run_diagnostic

    cancellation = threading.Event()
    handlers = _handle_termination(cancellation)
    try:
        result_ref = run_diagnostic(index=index, stop_event=cancellation)
    except BaseException as error:
        write_new(attempt_path, {"version": VERSION, "diagnostic_index": index,
            "status": "runtime_exception", "result": None, "actual_host_limits": host_limits,
            "sources": policy.sources(), "error": {"type": type(error).__name__, "message": str(error)},
            "traceback": traceback.format_exc(), "cleanup_not_inferred_without_result": True})
        raise
    finally:
        _restore_termination(handlers)
    record = {
        "version": VERSION,
        "diagnostic_index": index,
        "result": result_ref,
        "sources": policy.sources(),
        "actual_host_limits": host_limits,
    }
    write_new(attempt_path, record)
    result = load(result_ref)
    if result.get("passed") is not True or not _result_is_quiet(result):
        raise ValueError("Zero-model private-container diagnostic did not qualify")
    return write_new(BATCH_ROOT / "diagnostic-qualification.json", record)


def run():
    authorization = policy.require_v061_allowed("v061.run")
    host_limits = coordinator_limits()
    plan_ref = prepare()
    plan = load(plan_ref)
    dispatch_plan = load(plan["plan"])
    if (BATCH_ROOT / "execution-started.json").exists():
        raise ValueError("An entered recovery batch is not automatically replayed")
    diagnostic_qualification = load(reference(BATCH_ROOT / "diagnostic-qualification.json"))
    if diagnostic_qualification.get("sources") != policy.sources():
        raise ValueError("Runtime changed after its zero-model diagnostic")
    diagnostic = diagnostic_qualification["result"]
    diagnostic_proof = load(diagnostic)
    if diagnostic_proof.get("passed") is not True or not _result_is_quiet(diagnostic_proof):
        raise ValueError("A passed, fully cleaned diagnostic is required before formal execution")
    write_new(
        BATCH_ROOT / "execution-started.json",
        {
            "version": VERSION,
            "unix": time.time(),
            "authorization": authorization,
            "coordinator_plan": plan_ref,
            "actual_host_limits": host_limits,
        },
    )
    from proworksim.software_benchmark_recovery_episode_v061 import run_episode
    from proworksim.software_benchmark_ref_resident_v061 import (
        start_residents,
        stop_residents,
        ready_residents,
    )

    grading = grading_module()
    failure = None
    residents = []
    generations, scores, qualifications = {}, {}, {}
    pending_controls = list(plan["controls"])
    pending_generation = [
        row
        for row in dispatch_plan["rows"]
        if row["measurement_kind"] == "fresh_generation_recovery"
    ]
    pending_scores = []
    tasks = list(dispatch_plan["environments"])
    control_completions = {task: {} for task in tasks}
    grade_futures, generation_futures = {}, {}
    free_grade_lanes = [0, 1]
    snapshot_enqueued = False
    last_capacity_check = 0.0
    stop_new = False
    cancel_waiters = threading.Event()
    handlers = _handle_termination(cancel_waiters)
    try:
        residents = start_residents()
        last_capacity_check = time.monotonic()
        with (
            ThreadPoolExecutor(max_workers=2) as generation_pool,
            ThreadPoolExecutor(max_workers=2) as grade_pool,
        ):
            while (
                pending_controls
                or pending_generation
                or pending_scores
                or grade_futures
                or generation_futures
            ):
                if cancel_waiters.is_set():
                    stop_new = True
                    failure = failure or {"kind": "coordinator_cancellation_requested"}
                if not stop_new and time.monotonic() - last_capacity_check > 60:
                    updated = start_residents()
                    residents = updated
                    last_capacity_check = time.monotonic()
                # Scores use slots released by finished controls without waiting for all generation.
                while not stop_new and free_grade_lanes and (pending_scores or pending_controls):
                    lane = free_grade_lanes[0]
                    if pending_scores:
                        result_ref = pending_scores.pop(0)
                        try:
                            request_ref = grading.prepare_score(result_ref, lane=lane)
                        except Exception as error:
                            body = load(result_ref)
                            original_slot = body.get("original_slot_id") or body.get(
                                "slot", {}
                            ).get("slot_id")
                            scores[original_slot] = {
                                "status": "technical_unknown",
                                "generation_result": result_ref,
                                "error": {"type": type(error).__name__, "message": str(error)},
                            }
                            _event(
                                "score_preparation_failed",
                                original_slot_id=original_slot,
                                error=str(error),
                            )
                            continue
                        job_kind = "score"
                    else:
                        eligible = next(
                            (
                                ref
                                for ref in pending_controls
                                if load(ref)["cpuset_cpus"] == grading.selected_cpus(lane)
                            ),
                            None,
                        )
                        if eligible is None:
                            other_lane = next(
                                (
                                    candidate
                                    for candidate in free_grade_lanes
                                    if any(
                                        load(ref)["cpuset_cpus"] == grading.selected_cpus(candidate)
                                        for ref in pending_controls
                                    )
                                ),
                                None,
                            )
                            if other_lane is None:
                                break
                            lane = other_lane
                            eligible = next(
                                ref
                                for ref in pending_controls
                                if load(ref)["cpuset_cpus"] == grading.selected_cpus(lane)
                            )
                        request_ref = eligible
                        pending_controls.remove(eligible)
                        job_kind = "control"
                    free_grade_lanes.remove(lane)
                    future = grade_pool.submit(grading.run_request, request_ref, cancel_waiters)
                    grade_futures[future] = (job_kind, request_ref, lane)
                if (
                    not stop_new
                    and len(generation_futures) < 2
                    and any(
                        qualifications.get(row["instance_id"], {}).get("status") == "qualified"
                        for row in pending_generation
                    )
                ):
                    residents = ready_residents()
                while not stop_new and residents and len(generation_futures) < 2:
                    row = next(
                        (
                            r
                            for r in pending_generation
                            if qualifications.get(r["instance_id"], {}).get("status") == "qualified"
                        ),
                        None,
                    )
                    if row is None:
                        break
                    active_counts = {
                        str(resident["root"]): sum(
                            str(active["root"]) == str(resident["root"])
                            for _, active in generation_futures.values()
                        )
                        for resident in residents
                    }
                    resident = min(
                        residents,
                        key=lambda item: (active_counts[str(item["root"])], str(item["root"])),
                    )
                    pending_generation.remove(row)
                    generation_futures[
                        generation_pool.submit(
                            run_episode, row, resident, stop_event=cancel_waiters
                        )
                    ] = (
                        row,
                        resident,
                    )
                all_futures = list(grade_futures) + list(generation_futures)
                if not all_futures:
                    if stop_new:
                        break
                    # Once all controls closed, only capacity or explicit unsupported-task states remain.
                    blocked = [
                        r
                        for r in pending_generation
                        if qualifications.get(r["instance_id"], {}).get("status") == "not_qualified"
                    ]
                    for row in blocked:
                        pending_generation.remove(row)
                        generations[row["slot_id"]] = {
                            "status": "not_qualified",
                            "reason": qualifications[row["instance_id"]].get("reason"),
                        }
                    if not pending_controls and not pending_scores and not pending_generation:
                        break
                    time.sleep(5)
                    continue
                completed, _ = wait(all_futures, timeout=5, return_when=FIRST_COMPLETED)
                for future in completed:
                    if future in grade_futures:
                        kind, request_ref, lane = grade_futures.pop(future)
                        free_grade_lanes.append(lane)
                        request = load(request_ref)
                        task = load(request["original_config"])["instance_id"]
                        try:
                            completion = future.result()
                        except Exception as error:
                            completion = {"status": "technical_unknown", "error": str(error)}
                        if not grading.trustworthy_cleanup(request_ref):
                            stop_new = True
                            cancel_waiters.set()
                            failure = {"kind": "unproven_grader_cleanup", "request": request_ref}
                        if kind == "score":
                            scores[request["original_slot_id"]] = {
                                "request": request_ref,
                                "completion": completion,
                            }
                        else:
                            control_completions[task][request["patch_kind"]] = completion
                            if len(control_completions[task]) == 2:
                                try:
                                    q = grading.qualify(task)
                                    qualifications[task] = {
                                        "status": "qualified",
                                        "qualification": q,
                                    }
                                except Exception as error:
                                    qualifications[task] = {
                                        "status": "not_qualified",
                                        "reason": str(error),
                                    }
                                if (
                                    task == "scikit-learn__scikit-learn-14894"
                                    and qualifications[task]["status"] == "qualified"
                                    and not snapshot_enqueued
                                ):
                                    pending_scores.append(plan["snapshot_result"])
                                    snapshot_enqueued = True
                        _event(
                            "grading_finished",
                            resource_key=request["resource_key"],
                            status=completion.get("status"),
                        )
                    else:
                        row, resident = generation_futures.pop(future)
                        try:
                            result_ref = future.result()
                            result = load(result_ref)
                            generations[row["slot_id"]] = {
                                "result": result_ref,
                                "status": result.get("status"),
                                "retained_objects": result.get("retained_objects", []),
                            }
                            if not _result_is_quiet(result):
                                stop_new = True
                                cancel_waiters.set()
                                failure = {
                                    "kind": "unproven_generation_cleanup",
                                    "result": result_ref,
                                }
                            elif result.get("status") == "closed":
                                pending_scores.append(result_ref)
                        except Exception as error:
                            generations[row["slot_id"]] = {
                                "status": "technical_unknown",
                                "error": str(error),
                            }
                            stop_new = True
                            cancel_waiters.set()
                            failure = {
                                "kind": "generation_worker_failed_without_trusted_cleanup",
                                "slot": row["slot_id"],
                            }
                        _event(
                            "generation_finished",
                            slot_id=row["slot_id"],
                            resident=resident["identity_value"],
                            status=generations[row["slot_id"]]["status"],
                        )
                if stop_new and not grade_futures and not generation_futures:
                    break
    except Exception as error:
        cancel_waiters.set()
        failure = {"kind": "coordinator_error", "type": type(error).__name__, "message": str(error)}
    finally:
        cancel_waiters.set()
        try:
            resident_closure = stop_residents()
        except Exception as error:
            resident_closure = [{"owned_unit_stopped": False, "error": str(error)}]
        finally:
            _restore_termination(handlers)
    if any(record.get("owned_unit_stopped") is not True for record in resident_closure):
        failure = failure or {"kind": "resident_cleanup_unconfirmed"}
    result = {
        "version": VERSION,
        "plan": plan_ref,
        "diagnostic": diagnostic,
        "qualifications": qualifications,
        "generation": generations,
        "scores": scores,
        "unentered_generation": [row["slot_id"] for row in pending_generation],
        "unentered_controls": pending_controls,
        "unentered_scores": pending_scores,
        "resident_closure": resident_closure,
        "retained_objects": diagnostic_proof.get("retained_objects", []) + [
            {"original_slot_id": slot_id, **item}
            for slot_id, entry in generations.items()
            for item in entry.get("retained_objects", [])
        ],
        "quiescence_does_not_imply_all_owned_objects_removed": True,
        "failure": failure,
        "original_unknowns_overwritten": False,
        "automatic_replay": False,
        "finished_unix": time.time(),
    }
    write_new(BATCH_ROOT / "run-summary.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--diagnostic", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    if sum((args.prepare, args.execute, args.diagnostic is not None)) != 1:
        parser.error("Choose --prepare, --diagnostic N or --execute")
    result = prepare() if args.prepare else diagnose(args.diagnostic) if args.diagnostic else run()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
