"""Two finite sampling processes, one complete declaration and one learner.

No episode is retried or transferred after assignment. The child never owns an
optimizer. Its actual completion and identity/source guards precede any update.
"""

import copy
import os
from pathlib import Path
import subprocess
import sys
import time

from .audit import code_identity
from .harness_collection import (
    close_prepared_slot,
    collection_declaration,
    finish_collection,
    prepare_slot,
    run_prepared_slot,
)
from .online_support import bind_rollout, expected_window
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "fixed-window-two-replicas-v0.19"
POLL_SECONDS = 0.2


def write(path, value):
    atomic_write(Path(path), json_bytes(value))


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def checked(reference_value, expected_path):
    path = Path(reference_value["path"])
    if path.resolve() != Path(expected_path).resolve() or digest(path.read_bytes()) != reference_value["sha256"]:
        raise ValueError("Parallel evidence path or bytes changed")
    return read_json(path)


def assignment(slot_count):
    if type(slot_count) is not int or slot_count < 2:
        raise ValueError("Two-replica collection requires at least two fixed slots")
    return [(index + 1 - slot_count) % 2 for index in range(slot_count)]


def resolve_replica_environment(overrides=None):
    env = {**os.environ, **(overrides or {})}
    parent = [v.strip() for v in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if v.strip()]
    target = env.get("PROWORKSIM_REPLICA_GPUS", "")
    child = [v.strip() for v in target.split(",") if v.strip()]
    if (not parent or not child or len(parent) != len(child)
            or len(set(parent)) != len(parent) or len(set(child)) != len(child)
            or set(parent) & set(child)):
        raise ValueError("Declare disjoint parent/replica physical GPU lists with equal device counts")
    env["CUDA_VISIBLE_DEVICES"] = ",".join(child)
    return env


def verify_owner(owner, expected):
    actual = owner._make_identity()
    if actual != expected or owner.freeze_identity() != expected or owner.busy:
        raise ValueError("Parent sampling changed its frozen actor or left an active call")
    return {"passed": True, "actor_identity": actual}


def validate_prepared(ready, indices, window_spec, expected_identity, source):
    if (ready.get("actor_identity") != expected_identity
            or ready.get("window_id") != window_spec["window_id"]
            or ready.get("source") != source
            or ready.get("guard", {}).get("passed") is not True):
        raise ValueError("Replica prepared source/actor/window guard differs")
    rows = ready.get("slots", [])
    if [r.get("index") for r in rows] != indices:
        raise ValueError("Replica prepared slot inventory differs")
    for row in rows:
        if row["spec"]["slot_id"] != window_spec["slots"][row["index"]]["slot_id"]:
            raise ValueError("Replica prepared another slot")
    return {r["index"]: r["spec"] for r in rows}


def validate_barrier(declaration, config, prepared):
    if (declaration.get("actor_identity") != config["actor_identity"]
            or declaration.get("window_id") != config["window_spec"]["window_id"]
            or declaration["gamma_identity"].get("source") != config["source"]
            or [r["slot_id"] for r in declaration["slots"]]
            != [r["slot_id"] for r in config["window_spec"]["slots"]]):
        raise ValueError("Replica cannot sample under a different full-window declaration")
    for item in prepared:
        index = item["index"]
        declared = {k: v for k, v in declaration["slots"][index].items() if k != "window"}
        if item["spec"] != declared:
            raise ValueError("Replica prepared world differs from declared full window")
        expected_window(declaration, item["row"]["slot_id"])


def persist_result(item, result, rank):
    entry, record, summary = result
    folder = item["folder"]
    compact = {
        "version": VERSION, "index": item["index"], "rank": rank,
        "entry": {k: v for k, v in entry.items() if k != "rollout"},
        "record": {k: v for k, v in record.items() if k not in {"rollout", "mapping"}},
        "summary": summary,
        "rollout": reference(folder / "team-rollout.json") if entry.get("rollout") else None,
        "mapping": reference(folder / "mapping.json") if record.get("mapping") else None,
    }
    write(folder / "parallel-result.json", compact)
    return compact


def unknown_result(row, spec, reason):
    sid = row["slot_id"]
    return (
        {"slot_id": sid, "rollout": None, "reward": None, "active_members": spec["active_members"]},
        {"slot_id": sid, "status": "interrupted"},
        {"slot_id": sid, "status": "interrupted", "error": {"type": "ReplicaEvidenceMissing", "message": reason}},
    )


def read_slot_result(output, index, rank, row, spec, declaration):
    folder = output / f"slot-{index}"
    path = folder / "parallel-result.json"
    if not path.exists():
        return unknown_result(row, spec, "Assigned slot has no complete result; never reassigned or resampled")
    value = read_json(path)
    entry, record, summary = value["entry"], value["record"], value["summary"]
    sid = row["slot_id"]
    if (value.get("index") != index or value.get("rank") != rank
            or any(r.get("slot_id") != sid for r in (entry, record, summary))
            or entry.get("active_members") != spec["active_members"]):
        raise ValueError("Parallel result duplicated, moved or bound to another slot")
    rollout = checked(value["rollout"], folder / "team-rollout.json") if value["rollout"] else None
    mapping = checked(value["mapping"], folder / "mapping.json") if value["mapping"] else None
    if rollout is not None:
        bind_rollout(declaration, sid, rollout, mapping=mapping)
        if entry.get("reward") != rollout["reward_eligibility"]:
            raise ValueError("Parallel reward differs from original fixed rollout")
        record.update(rollout=rollout, mapping=mapping)
    elif entry.get("reward") is not None or record.get("status") == "closed":
        raise ValueError("Known parallel result is missing original rollout")
    entry["rollout"] = rollout
    return entry, record, summary


def merge_results(output, window_spec, specs, ranks, declaration):
    return [read_slot_result(output, i, ranks[i], row, specs[i], declaration)
            for i, row in enumerate(window_spec["slots"])]


def _progress(output, slots):
    summaries = []
    for i in range(len(slots)):
        path = output / f"slot-{i}/parallel-result.json"
        if path.exists():
            summaries.append(read_json(path)["summary"])
    write(output / "progress.json", summaries)


def collect_window(owner, window_spec, output_dir, *, replica_command=None, replica_environment=None):
    """Collect once per fixed slot; return only after child exit and real guards."""
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / "window-spec.json", window_spec)
    slots = window_spec["slots"]
    ranks = assignment(len(slots))
    # Resolve the environment before model/child construction or actor work.
    env = resolve_replica_environment(replica_environment)
    started_at = time.time()
    identity, source = owner.freeze_identity(), code_identity()
    parent_steps = (owner.actor_steps, owner.critic_steps)
    resource_before = owner._resource_guard()
    verify_owner(owner, identity)
    control = output / "replica-1"
    control.mkdir()
    snapshot_path = control / "snapshot"
    snapshot_started = time.time()
    snapshot = owner.export_sampling_snapshot(snapshot_path)
    snapshot_seconds = time.time() - snapshot_started
    config = {
        "version": VERSION, "parent_pid": os.getpid(), "source": source,
        "actor_identity": identity, "window_spec": copy.deepcopy(window_spec),
        "indices": [i for i, rank in enumerate(ranks) if rank == 1],
        "ranks": ranks, "output": str(output), "control": str(control),
        "snapshot_path": str(snapshot_path), "snapshot": snapshot,
    }
    write(control / "config.json", config)
    command = list(replica_command or [sys.executable, "-m", "scripts.sampling_replica_v019"])
    command += ["--config", str(control / "config.json")]
    launch = {"command": command, "started_at": time.time(),
              "CUDA_VISIBLE_DEVICES": env["CUDA_VISIBLE_DEVICES"], "launch_attempt_count": 1}
    write(control / "launch.json", launch)
    prepared, process, declaration = [], None, None
    try:
        with (control / "process.log").open("x") as log:
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT)
        launch["pid"] = process.pid
        write(control / "launch.json", launch)
        for i, row in enumerate(slots):
            if ranks[i] == 0:
                prepared.append(prepare_slot(owner, window_spec, row, i, output))
        ready_path = control / "prepared.json"
        while not ready_path.exists():
            if process.poll() is not None:
                raise RuntimeError("Replica exited before the complete declaration barrier; no slot sampled")
            time.sleep(POLL_SECONDS)
        ready = read_json(ready_path)
        specs = {item["index"]: item["spec"] for item in prepared}
        specs.update(validate_prepared(ready, config["indices"], window_spec, identity, source))
        execution = {"version": VERSION, "replicas": 2,
                     "partition": "alternate_slots_last_slot_on_parent", "ranks": ranks,
                     "replica_optimizer": False, "merge_order": "original_slot_order"}
        declaration = collection_declaration(owner, window_spec,
                                            [specs[i] for i in range(len(slots))], execution=execution)
        write(output / "declaration.json", declaration)
        barrier_at = time.time()
        write(control / "start.json", {"declaration": reference(output / "declaration.json"),
                                      "prepared": reference(ready_path), "started_at": time.time()})
        for item in prepared:
            result = run_prepared_slot(owner, item, declaration)
            persist_result(item, result, 0)
            _progress(output, slots)
        parent_sampling_finished_at = time.time()
        # The learner is still collecting; no update or checkpoint until child exit.
        launch.update(exit_code=process.wait(), ended_at=time.time())
        write(control / "launch.json", launch)
        results = merge_results(output, window_spec, specs, ranks, declaration)
        child_guard = read_json(control / "guard.json") if (control / "guard.json").exists() else {}
        source_after = code_identity()
        parent_guard = verify_owner(owner, identity)
        parent_guard.update(steps_before=list(parent_steps),
                            steps_after=[owner.actor_steps, owner.critic_steps],
                            optimizer_steps_unchanged=parent_steps == (owner.actor_steps, owner.critic_steps))
        child_calls = sorted((control / "resident/calls").glob("*.json"))
        child_ok = (launch["exit_code"] == 0 and child_guard.get("passed") is True
                    and child_guard.get("actor_identity") == identity
                    and child_guard.get("source_before") == source
                    and child_guard.get("source_after") == source
                    and child_guard.get("optimizer_owned") is False
                    and child_guard.get("final", {}).get("optimizer_absent") is True
                    and child_guard.get("final", {}).get("local_optimizer_updates") == 0)
        guard = {"version": VERSION, "passed": child_ok and source_after == source and parent_guard["optimizer_steps_unchanged"],
                 "parent": parent_guard, "child": child_guard,
                 "source_before": source, "source_after": source_after,
                 "child_exit_code": launch["exit_code"], "child_finished_before_update": True,
                 "partition": ranks, "last_logical_slot_rank": ranks[-1],
                 "started_at": started_at, "ended_at": time.time(),
                 "timing_seconds": {"snapshot_export": snapshot_seconds,
                    "prepare_and_barrier": barrier_at - started_at,
                    "parent_sampling": parent_sampling_finished_at - barrier_at,
                    "collection_including_cold_replica": time.time() - started_at},
                 "resource_before": resource_before, "resource_after": owner._resource_guard(),
                 "parent_cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                 "child_cuda_visible_devices": env["CUDA_VISIBLE_DEVICES"],
                 "child_calls": {"directory": str(control / "resident/calls"),
                                 "files": [reference(path) for path in child_calls]},
                 "child_launch": reference(control / "launch.json")}
        write(output / "parallel-guard.json", guard)
        write(output / "parallel/report.json", guard)
        entries = finish_collection(output, identity, declaration, results,
                                    extra={"parallel_execution": guard})
        if not guard["passed"]:
            raise RuntimeError("Parallel source/actor/child-exit guard failed; evidence retained, no learner update")
        return entries
    except BaseException as error:
        write(control / "abort.json", {"type": type(error).__name__, "message": str(error)})
        if not (output / "parallel/report.json").exists():
            write(output / "parallel/report.json", {"version": VERSION, "passed": False,
                "error": {"type": type(error).__name__, "message": str(error)},
                "declaration_barrier_reached": declaration is not None,
                "planned_slots": [r["slot_id"] for r in slots], "partition": ranks,
                "actor_identity": identity, "source_before": source})
        if process is not None and process.poll() is None:
            # This is our own finite child. Finish its active request, then it
            # observes abort before another slot. Never signal other jobs.
            process.wait()
        if process is not None:
            launch.update(exit_code=process.returncode, ended_at=time.time())
            write(control / "launch.json", launch)
        raise
    finally:
        for item in prepared:
            close_prepared_slot(item)
