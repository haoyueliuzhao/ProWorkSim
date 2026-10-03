"""Bounded eight-episode software development with durable original trajectories.

Two first-speaker strata use the same restored 9B endpoint, no updates and no
training support. Task timeouts and resource limits remain; cumulative GPU
duration is uncapped. Source/task admission is a separate CPU stage.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from proworksim.audit import code_identity
from proworksim.resource_monitor_v025 import TelemetryGuard, target_resources, worker_identity
from proworksim.software_collaboration_v028 import INTERFACE_REVISION
from proworksim.software_context_v028 import VERSION as CONTEXT_POLICY
from proworksim.storage import digest, json_bytes, read_json
from scripts.run_bounded_v022 import artifact_bytes, rss
from scripts.run_ne_v021 import checked, lock, read, reference, resources, stop_owned, write

VERSION = "software-development-v0.28"
SOURCE = Path(__file__).resolve().parents[1]
CASES = ("marshmallow-interface-dev", "marshmallow-integration-dev")
MEMBERS = ("member_a", "member_b")
SEEDS = (202610030101, 202610030102)
GPUS = [5]
WORKERS = ("worker-0", "worker-1")
TERMINAL_RUN_STATES = {"complete", "closed_with_missing_or_interrupted", "supervisor_interrupted"}
RECOVERY_VERSION = "software-development-recovery-v0.28"
STATISTICS_SCOPE = (
    "Eight-slot completion ledger only. Retained and recovery interface revisions are distinct; "
    "their outcomes must not be treated as one same-protocol effect estimate."
)
LIMITS = {
    "max_new_episodes": 8, "max_parallel_model_instances": 1,
    "max_new_actor_steps": 0, "max_new_critic_steps": 0,
    "minimum_free_gpu_mib": 78000, "gpu_capacity_stability_seconds": 60,
    "own_gpu_memory_mib": 81920, "host_rss_per_worker_bytes": 64 * 1024**3,
    "artifact_bytes": 48 * 1024**3, "minimum_volume_free_bytes": 20 * 1024**3,
    "task_seconds": {"loading": 900, "episode": 2400, "boundary": 600},
    "shutdown_reserve_seconds": 45, "telemetry_grace_seconds": 120,
    "poll_seconds": 5,
}


def assignments():
    result = {}
    for index, first in enumerate(MEMBERS):
        result[f"worker-{index}"] = [
            {"slot_id": f"dev-{case_index}-first-{index}-r{repeat}", "case_id": case,
             "sampling_seed": seed, "first_member": first,
             "role_decision_limits": dict.fromkeys(MEMBERS, 48)}
            for repeat, seed in enumerate(SEEDS) for case_index, case in enumerate(CASES)
        ]
    return result


def available_cards(plan, sample, excluded=()):
    """Admit released capacity; current competing jobs have observed large peaks."""
    if any(sample.get(k, {}).get("returncode") != 0 for k in ("gpus", "processes")):
        return []
    cards, occupied = {}, set()
    try:
        for row in csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True):
            if len(row) != 4:
                return []
            occupied.add(row[0].strip())
        for row in csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True):
            index, uuid, name, free, total, utilization = (s.strip() for s in row)
            index, free, total, utilization = int(index), float(free), float(total), float(utilization)
            if (index in plan["gpu_preference"] and index not in excluded and "A100" in name
                    and uuid not in occupied and 0 <= utilization <= 5 and total >= 81920
                    and plan["limits"]["minimum_free_gpu_mib"] <= free <= total):
                cards[index] = {"index": index, "uuid": uuid, "free_mib": free,
                                "utilization_percent": utilization}
    except (ValueError, TypeError, csv.Error):
        return []
    return [cards[index] for index in plan["gpu_preference"] if index in cards]


def make_plan(data_root, qualification, queue_deadline):
    data_root = Path(data_root).resolve()
    prior = data_root / "runs/domain-v0201-p1-9b/plan.json"
    recipe = data_root / "runs/domain-v025-r1/train_base/actual/resident/owner.json"
    marker = data_root / "runs/domain-v025-r1/checkpoints/base.json"
    return {
        "version": VERSION, "created_at": time.time(), "source": code_identity(),
        "interface_revision": INTERFACE_REVISION, "context_policy": CONTEXT_POLICY,
        "authorization": "2026-10-03 user requested audit revisions and subsequent experiments with original trajectories retained.",
        "purpose": "interface_development", "inherited_resource_budget": False,
        "gpu_preference": GPUS, "worker_gpu_seconds": dict.fromkeys(WORKERS), "total_gpu_seconds": None,
        "limits": LIMITS, "assignments": assignments(), "qualification": reference(qualification),
        "prior_model_plan": reference(prior), "owner_recipe": reference(recipe),
        "checkpoint_marker": reference(marker),
        "queue_deadline_at": queue_deadline,
        "queue_deadline_beijing": datetime.fromtimestamp(queue_deadline, ZoneInfo("Asia/Shanghai")).isoformat(),
        "wall_deadline_at": None,
        "shared_gpu_capacity_allowed": False, "automatic_retries": False,
        "automatic_successors": [], "model_api_calls": 0,
        "source_scope": "New software/harness protocol; unchanged strict original model recipe and full-state restoration. Not an old SQL result replay.",
    }


def _prior_snapshot(prior_run_root):
    """Bind a terminal first run without rerunning or rewriting any old artifact."""
    root = Path(prior_run_root).resolve()
    prior = read_json(root / "plan.json")
    supervisor = read_json(root / "supervisor.json")
    if (prior.get("assignments") != assignments() or prior.get("recovery") is not None
            or supervisor.get("status") not in TERMINAL_RUN_STATES
            or not supervisor.get("ended_at")
            or set(supervisor.get("states", {})) != set(WORKERS)
            or any(state.get("status") in {"waiting", "running"} for state in supervisor["states"].values())):
        raise ValueError("Recovery requires the terminal canonical first run; never freeze an active queue")
    reports, slots = {}, {}
    for worker, canonical in assignments().items():
        actual = root / worker / "actual"
        report_path, progress_path = actual / "report.json", actual / "progress.json"
        worker_report = read_json(report_path) if report_path.exists() else {}
        if worker_report and (worker_report.get("source_before") != prior["source"]
                              or worker_report.get("status") in {"loading", "running"}):
            raise ValueError("Prior worker report must be terminal and bound to its source")
        rows = worker_report.get("rows", [])
        if progress_path.exists():
            progress = read_json(progress_path)
            if worker_report and progress != rows:
                raise ValueError("Terminal prior progress and worker report disagree")
            rows = progress
        if [row.get("slot_id") for row in rows] != [slot["slot_id"] for slot in canonical[:len(rows)]]:
            raise ValueError("Prior worker rows must preserve the canonical slot prefix")
        reports[worker] = {name: reference(path) for name, path in (
            ("report", report_path), ("progress", progress_path)) if path.exists()}
        byslot = {row["slot_id"]: row for row in rows}
        for slot in canonical:
            sid, folder = slot["slot_id"], actual / slot["slot_id"]
            row = byslot.get(sid)
            if row and any(row.get(key) != value for key, value in slot.items()):
                raise ValueError("Prior slot identity, seed or decisions differ from the canonical protocol")
            evidence = {name: reference(path) for name, path in (
                ("entry", folder / "slot-0/entry.json"),
                ("assessment", folder / "slot-0/assessment.json"),
                ("raw_independent_assessment", folder / "slot-0/raw-independent-assessment.json"),
                ("evaluation_guard", folder / "evaluation-guard.json")) if path.exists()}
            if row and row.get("status") == "closed":
                if not {"entry", "assessment", "evaluation_guard"} <= evidence.keys():
                    raise ValueError("Every retained closed slot needs its entry, assessment and evaluation guard")
                entry = read_json(checked(evidence["entry"]))
                guard = read_json(checked(evidence["evaluation_guard"]))
                assessment = read_json(checked(evidence["assessment"]))
                if (entry.get("reward") != row.get("reward") or not entry["reward"].get("eligible")
                        or guard != row.get("evaluation_guard") or not guard.get("learning_unchanged")
                        or not guard.get("rng_restored_exactly") or assessment.get("status") == "unknown"):
                    raise ValueError("Retained results must be evaluable and preserve learning/RNG guards, including R=0")
            slots[sid] = {"worker": worker, "row": row, "row_sha256": digest(json_bytes(row)),
                          "status": row["status"] if row else "not_started",
                          "trajectory_directory": str(folder), "evidence": evidence}
    return {"prior_run_root": str(root), "prior_plan": reference(root / "plan.json"),
            "prior_supervisor": reference(root / "supervisor.json"), "prior_source": prior["source"],
            "prior_interface_revision": prior.get("interface_revision", "software-collaboration-v0.28"),
            "prior_context_policy": prior.get("context_policy", "latest_observation_last4_tool_rounds"),
            "prior_worker_records": reports, "prior_slots": slots}


def make_recovery_plan(data_root, qualification, queue_deadline, prior_run_root, *, context_qualification,
                       reservation_launch=None):
    """Freeze one user-authorized recovery round after the first run terminates."""
    plan = make_plan(data_root, qualification, queue_deadline)
    plan["context_qualification"] = reference(context_qualification)
    snapshot = _prior_snapshot(prior_run_root)
    retained = [slot["slot_id"] for slots in assignments().values() for slot in slots
                if snapshot["prior_slots"][slot["slot_id"]]["status"] == "closed"]
    plan["recovery"] = {"version": RECOVERY_VERSION, "attempt_index": 1,
                        "authorization": "explicit_user_requested_fix_and_recovery",
                        **snapshot, "retained_closed_slot_ids": retained,
                        "execution_slot_ids": {worker: [slot["slot_id"] for slot in slots
                                                         if slot["slot_id"] not in retained]
                                               for worker, slots in assignments().items()},
                        "statistics_scope": STATISTICS_SCOPE}
    _validate_context_qualification(plan)
    if reservation_launch is not None:
        launch_path = Path(reservation_launch).resolve()
        launch, state = read_json(launch_path), read_json(launch_path.parent / "state.json")
        plan["owned_reservation"] = {
            "launch": reference(launch_path), "state_path": str(launch_path.parent / "state.json"),
            "pid": launch["pid"], "start_ticks": launch["start_ticks"],
            "physical_gpu": launch["physical_gpu"], "gpu_uuid": state["gpu_uuid"]}
        _validate_reservation(plan)
    return plan


def _validate_context_qualification(plan):
    qualification = read_json(checked(plan["context_qualification"]))
    if (qualification.get("passed") is not True or qualification.get("source") != plan["source"]
            or qualification.get("model_calls") != 0):
        raise ValueError("Same-source zero-model context failure regression qualification is required")


def validate_recovery(plan, *, check_files=True):
    recovery = plan.get("recovery")
    if recovery is None:
        return
    canonical = assignments()
    canonical_ids = [slot["slot_id"] for slots in canonical.values() for slot in slots]
    context_ref = plan.get("context_qualification", {})
    if (recovery.get("version") != RECOVERY_VERSION or recovery.get("attempt_index") != 1
            or recovery.get("authorization") != "explicit_user_requested_fix_and_recovery"
            or recovery.get("statistics_scope") != STATISTICS_SCOPE
            or set(recovery.get("prior_slots", {})) != set(canonical_ids)
            or set(context_ref) != {"path", "sha256"}
            or not isinstance(context_ref["path"], str) or not isinstance(context_ref["sha256"], str)
            or len(context_ref["sha256"]) != 64):
        raise ValueError("Declare exactly one explicit recovery round for the canonical eight slots")
    retained = [sid for sid in canonical_ids if recovery["prior_slots"][sid]["status"] == "closed"]
    execution = {worker: [slot["slot_id"] for slot in slots if slot["slot_id"] not in retained]
                 for worker, slots in canonical.items()}
    if (recovery.get("retained_closed_slot_ids") != retained or recovery.get("execution_slot_ids") != execution):
        raise ValueError("Recovery must execute exactly canonical slots minus all prior closed results, including R=0")
    if check_files:
        _validate_context_qualification(plan)
        snapshot = _prior_snapshot(recovery["prior_run_root"])
        if any(recovery.get(key) != value for key, value in snapshot.items()):
            raise ValueError("Recovery prior row or artifact reference changed")
        prior_plan = read_json(checked(recovery["prior_plan"]))
        if any(plan.get(key) != prior_plan.get(key) for key in ("checkpoint_marker", "owner_recipe", "prior_model_plan")):
            raise ValueError("Recovery must restore the same original checkpoint, recipe and model profile")


def execution_slots(plan, worker):
    recovery = plan.get("recovery")
    selected = recovery["execution_slot_ids"][worker] if recovery else None
    return [slot for slot in plan["assignments"][worker] if selected is None or slot["slot_id"] in selected]


def _validate_reservation(plan, *, check_files=True):
    owned = plan.get("owned_reservation")
    if owned is None:
        return
    if (not plan.get("recovery") or owned.get("physical_gpu") != 5
            or type(owned.get("pid")) is not int or owned["pid"] <= 0
            or type(owned.get("start_ticks")) is not int or owned["start_ticks"] <= 0
            or not isinstance(owned.get("gpu_uuid"), str) or not owned["gpu_uuid"].startswith("GPU-")):
        raise ValueError("Only the explicitly owned GPU5 recovery reservation may be handed over")
    if check_files:
        launch_path = checked(owned["launch"])
        launch = read_json(launch_path)
        if (any(launch.get(key) != owned[key] for key in ("pid", "start_ticks", "physical_gpu"))
                or Path(owned["state_path"]) != launch_path.parent / "state.json"
                or not launch.get("user_authorization")):
            raise ValueError("Owned reservation launch identity differs")


def _release_reservation_pid(pid, start_ticks):
    """Use a PID descriptor so a recycled PID can never receive our signal."""
    descriptor = os.pidfd_open(pid)
    try:
        identity = worker_identity(pid)
        if not identity.get("alive") or identity.get("start_ticks") != start_ticks:
            raise ValueError("Owned reservation process identity changed before release")
        signal.pidfd_send_signal(descriptor, signal.SIGTERM)
    finally:
        os.close(descriptor)


def consume_owned_reservation(plan, root):
    """Release this run's existing reservation; return idle capacity or resume queuing."""
    owned = plan.get("owned_reservation")
    if owned is None:
        return None
    _validate_reservation(plan)
    state = read_json(Path(owned["state_path"]))
    identity = worker_identity(owned["pid"])
    now = time.time()
    if (now >= plan["queue_deadline_at"] or state.get("status") != "reserved" or state.get("model_calls") != 0
            or any(state.get(key) != owned[key] for key in ("pid", "physical_gpu", "gpu_uuid"))
            or not identity.get("alive") or identity.get("start_ticks") != owned["start_ticks"]
            or now - state.get("ready_at", now) < LIMITS["gpu_capacity_stability_seconds"]
            or not 0 <= now - state.get("heartbeat_at", 0) <= 3 * LIMITS["poll_seconds"]):
        raise ValueError("GPU5 reservation must be alive, stable for 60 seconds and recently observed")
    sample = resources()
    if any(sample.get(key, {}).get("returncode") != 0 for key in ("gpus", "processes")):
        raise ValueError("Cannot verify reserved GPU capacity")
    try:
        gpu_rows = list(csv.reader(io.StringIO(sample["gpus"]["stdout"]), strict=True))
        target = [row for row in gpu_rows if int(row[0].strip()) == 5]
        processes = list(csv.reader(io.StringIO(sample["processes"]["stdout"]), strict=True))
        if (len(target) != 1 or len(target[0]) != 6 or target[0][1].strip() != owned["gpu_uuid"]
                or "A100" not in target[0][2] or float(target[0][4]) < 81920
                or any(len(row) != 4 for row in processes)
                or [int(row[1].strip()) for row in processes if row[0].strip() == owned["gpu_uuid"]] != [owned["pid"]]):
            raise ValueError("Reserved GPU5 identity or exclusive process ownership differs")
    except (IndexError, TypeError, csv.Error) as error:
        raise ValueError("Malformed GPU reservation telemetry") from error
    proof_path = Path(root) / "reservation-handoff.json"
    proof = {"status": "verified_before_release", "owned_reservation": owned, "state_before": state,
             "identity_before": identity, "resources_before": sample, "verified_at": now,
             "model_generation_calls": 0, "accounting_scope": "GPU reservation occupancy; separate from model worker GPU seconds"}
    write(proof_path, proof)
    try:
        _release_reservation_pid(owned["pid"], owned["start_ticks"])
        deadline = time.monotonic() + 30
        while True:
            after = worker_identity(owned["pid"])
            if not after.get("alive") or after.get("start_ticks") != owned["start_ticks"]:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Owned reservation did not exit after SIGTERM")
            time.sleep(0.1)
        released_at = time.time()
        proof.update(status="released", identity_after=after, released_at=released_at,
                     reservation_held_seconds=released_at - state["ready_at"])
        released_sample = resources()
        ready = available_cards(plan, released_sample)
        proof.update(resources_after=released_sample, immediate_capacity_available=bool(ready))
        return ready[0] if ready else None
    except BaseException as error:
        proof.update(status="release_failed", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        write(proof_path, proof)


def validate_plan(plan, *, check_files=True):
    if (plan.get("version") != VERSION or plan.get("assignments") != assignments()
            or plan.get("interface_revision") != INTERFACE_REVISION
            or plan.get("context_policy") != CONTEXT_POLICY
            or plan.get("worker_gpu_seconds") != dict.fromkeys(WORKERS) or plan.get("limits") != LIMITS
            or "total_gpu_seconds" not in plan or plan["total_gpu_seconds"] is not None
            or plan.get("gpu_preference") != GPUS
            or plan.get("purpose") != "interface_development"
            or plan.get("inherited_resource_budget") is not False
            or plan.get("shared_gpu_capacity_allowed") is not False
            or plan.get("automatic_retries") is not False
            or plan.get("automatic_successors") != [] or plan.get("model_api_calls") != 0
            or type(plan.get("queue_deadline_at")) not in (int, float)
            or "wall_deadline_at" not in plan or plan["wall_deadline_at"] is not None):
        raise ValueError("Freeze the complete new eight-slot zero-update software protocol")
    validate_recovery(plan, check_files=check_files)
    _validate_reservation(plan, check_files=check_files)
    if check_files:
        if code_identity() != plan["source"] or plan["source"].get("code_dirty") is not False:
            raise ValueError("Run only the clean frozen source bound in this new plan")
        qualification = read_json(checked(plan["qualification"]))
        if (qualification.get("passed") is not True
                or qualification.get("source") != plan["source"]
                or qualification.get("model_calls") != 0
                or qualification.get("max_context_tokens") != 16384
                or qualification.get("max_output_tokens") != 2048):
            raise ValueError("Passed same-source CPU and actual-tokenizer qualification required")
        prior = read_json(checked(plan["prior_model_plan"]))
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        if (prior["runtime_profile"]["candidate_id"] != "qwen3.5-9b"
                or prior["runtime_profile"]["version"] != "candidate-runtime-v0.20.1"
                or recipe["max_length"] != 16384 or recipe["max_output_tokens"] != 2048
                or recipe["credit_assignment"] != "terminal_mc"):
            raise ValueError("Use the declared existing 9B sampling and full learning-state recipe")
        marker = read_json(checked(plan["checkpoint_marker"]))
        saved = read_json(checked(marker["checkpoint"]))
        if saved["actor_steps"] != 3 or saved["critic_steps"] != 3:
            raise ValueError("The declared inherited endpoint is actor/critic 3/3")
        checked(prior["manifest"])
    return plan


class DurableTransport:
    """Persist each original request before generation, including an interrupted call."""
    def __init__(self, inner, directory, window_id):
        self.inner, self.directory, self.window_id = inner, Path(directory), window_id
        self.counter = 0

    def complete(self, request, **kwargs):
        self.counter += 1
        stem = self.directory / f"call-{self.counter:05d}"
        ledger = {"version": VERSION, "window_id": self.window_id, "started_at": time.time(),
                  "request": copy.deepcopy(request), "request_sha256": digest(json_bytes(request)),
                  "transport_options": copy.deepcopy(kwargs), "status": "generation_not_returned"}
        write(stem.with_suffix(".started.json"), ledger)
        try:
            response = self.inner.complete(request, **kwargs)
            ledger.update(status="returned", response=copy.deepcopy(response))
            return response
        except BaseException as error:
            ledger.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            ledger["ended_at"] = time.time()
            write(stem.with_suffix(".finished.json"), ledger)


class CollectionOwner:
    def __init__(self, owner, directory):
        from proworksim.software_context_v028 import SoftwareContextTransport
        self.owner = owner
        self.software_context_policy = CONTEXT_POLICY
        self.software_context_projection = CONTEXT_POLICY
        self.transport = DurableTransport(
            SoftwareContextTransport(owner, Path(directory) / "context-projections"), directory, owner.window_id)

    def __getattr__(self, name):
        return getattr(self.owner, name)


def task(output, name, kind):
    write(Path(output) / "task.json", {"task": name, "kind": kind,
                                     "started_at": time.time(), "pid": os.getpid()})


def restore(owner, plan, output):
    from proworksim.online_training import tensor_tree_digest
    marker_path = checked(plan["checkpoint_marker"])
    marker = read_json(marker_path)
    original_sha = reference(marker_path)
    saved = read_json(checked(marker["checkpoint"]))
    restored = owner.restore_checkpoint(marker["directory"])
    actual = tensor_tree_digest(owner._state_bundle(), owner.torch)
    if (restored != saved or actual != saved["state_tensor_digest"]
            or owner.freeze_identity() != marker["actor_identity"]
            or owner.actor_steps != 3 or owner.critic_steps != 3
            or reference(marker_path) != original_sha):
        raise ValueError("Complete actor/critic/optimizer/RNG restoration failed")
    proof = {"old_source": marker["source"], "new_source": code_identity(),
             "marker": original_sha, "checkpoint": marker["checkpoint"],
             "strict_restore": True, "state_tensor_digest": actual,
             "actor_identity": owner.freeze_identity(), "actor_steps": 3, "critic_steps": 3,
             "original_marker_unchanged": True, "optimizer_updates": 0,
             "scope": "New software evaluation only; old critic/role recipe preserved but no software training qualification claimed."}
    write(Path(output) / "restore-proof.json", proof)
    return proof


def run_worker(plan_path, output, worker):
    plan = validate_plan(read_json(plan_path))
    if worker not in WORKERS:
        raise ValueError("Unknown declared worker")
    slots = execution_slots(plan, worker)
    if slots and os.environ.get("CUDA_VISIBLE_DEVICES") not in set(map(str, GPUS)):
        raise ValueError("Bind one assigned worker to one declared physical GPU")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source, owner = code_identity(), None
    report = {"version": VERSION, "worker": worker, "status": "loading", "source_before": source,
              "interface_revision": plan["interface_revision"],
              "context_policy": plan["context_policy"],
              "statistics_scope": STATISTICS_SCOPE if plan.get("recovery") else "Single declared interface revision",
              "plan": reference(plan_path), "slots": slots, "rows": [],
              "retained_closed_slot_ids": [slot["slot_id"] for slot in plan["assignments"][worker]
                                           if slot not in slots],
              "started_at": time.time(), "new_actor_steps": 0, "new_critic_steps": 0,
              "model_api_calls": 0, "automatic_successors": []}
    write(output / "report.json", report)
    if not slots:
        report.update(status="retained", ended_at=time.time(), source_after=source, source_unchanged=True, not_started=[])
        write(output / "report.json", report)
        return report
    try:
        from proworksim.deterministic_work_v024 import DeterministicCandidateActor
        from proworksim.software_runtime_v028 import collect_software_window
        task(output, "load-9b", "loading")
        prior = read_json(checked(plan["prior_model_plan"]))
        recipe = read_json(checked(plan["owner_recipe"]))["recipe"]
        snapshot = resources()
        write(output / "preload-resources.json", snapshot)
        if int(os.environ["CUDA_VISIBLE_DEVICES"]) not in [c["index"] for c in available_cards(plan, snapshot)]:
            raise RuntimeError("Admitted GPU no longer has its required free capacity before loading")
        owner = DeterministicCandidateActor.from_candidate(
            prior["model"], manifest=checked(prior["manifest"]), profile=prior["runtime_profile"],
            recipe=recipe, output=output / "resident")
        task(output, "strict-complete-restore", "boundary")
        report["restore"] = restore(owner, plan, output)
        identity = owner.freeze_identity()
        report["status"] = "running"
        for slot in slots:
            task(output, slot["slot_id"], "episode")
            folder = output / slot["slot_id"]
            guard_before = owner.capture_evaluation_state()
            attempt = 1 if plan.get("recovery") else 0
            window_id = ("v028-recovery-1-" if attempt else "v028-") + slot["slot_id"]
            if owner.begin_window(window_id) != identity:
                raise ValueError("Actor changed across frozen software episodes")
            row = {**copy.deepcopy(slot), "status": "started", "started_at": time.time(),
                   "attempt_index": attempt, "interface_revision": plan["interface_revision"],
                   "context_policy": plan["context_policy"],
                   "trajectory_directory": str(folder)}
            report["rows"].append(row)
            write(output / "progress.json", report["rows"])
            write(output / "report.json", report)
            spec = {"window_id": window_id, "harness": "openhands_v16", "usage": "interface_dev",
                    "mode": "frozen_development", "min_class_count": 2,
                    "budget": {"max_slots": 1, "max_model_calls": 96}, "slots": [slot]}
            try:
                entries = collect_software_window(CollectionOwner(owner, folder / "raw-transport"), spec, folder)
                owner.finish_evaluation(entries, folder / "frozen-evaluation")
                guard = owner.finish_evaluation_guard(guard_before)
                write(folder / "evaluation-guard.json", guard)
                if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                    raise ValueError("Frozen learning state or restored RNG changed")
                entry = entries[0]
                row.update(status="closed" if entry["reward"]["eligible"] else "execution_unknown",
                           reward=copy.deepcopy(entry["reward"]), mapping=copy.deepcopy(entry["mapping"]),
                           evaluation_guard=guard, ended_at=time.time())
            except BaseException as error:
                row.update(status="interrupted_or_unassessed", ended_at=time.time(),
                           error={"type": type(error).__name__, "message": str(error)})
                raise
            finally:
                write(output / "progress.json", report["rows"])
                write(output / "report.json", report)
            print(json.dumps({"slot": slot["slot_id"], "status": row["status"],
                              "reward": row.get("reward", {}).get("reward")}), flush=True)
            if row["status"] != "closed":
                report["status"] = "stopped_execution_unknown"
                break
        else:
            report["status"] = "complete"
    except BaseException as error:
        report.update(status="interrupted_or_error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        if owner is not None:
            report.update(final_actor_identity=owner._make_identity(), actor_steps=owner.actor_steps,
                          critic_steps=owner.critic_steps)
        report.update(ended_at=time.time(), source_after=code_identity())
        report["source_unchanged"] = report["source_after"] == source
        report["not_started"] = report["slots"][len(report["rows"]):]
        write(output / "report.json", report)
    return report


def _worker_env(root, name, gpu):
    temporary = root / name / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": str(gpu), "PYTHONHASHSEED": "0",
           "PYTHONPATH": str(SOURCE / "src") + os.pathsep + str(SOURCE),
           "PYTHONDONTWRITEBYTECODE": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "TOKENIZERS_PARALLELISM": "false", "TMPDIR": str(temporary),
           "TMP": str(temporary), "TEMP": str(temporary)}
    env.pop("PROWORKSIM_REPLICA_GPUS", None)
    return env


def supervise(plan_path, root):
    plan = validate_plan(read_json(plan_path))
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root / "plan.json", plan)
    summary = {"version": VERSION, "status": "waiting", "source": code_identity(),
               "interface_revision": plan["interface_revision"],
               "context_policy": plan["context_policy"],
               "statistics_scope": STATISTICS_SCOPE if plan.get("recovery") else "Single declared interface revision",
               "plan": reference(plan_path), "observer_pid": os.getpid(), "started_at": time.time(),
               "states": {name: {"worker": name, "status": "not_started" if execution_slots(plan, name) else "retained",
                                  "attempted": False, "slots": execution_slots(plan, name),
                                  "retained_closed_slot_ids": [slot["slot_id"] for slot in plan["assignments"][name]
                                                               if slot not in execution_slots(plan, name)]}
                          for name in WORKERS},
               "terminated_gpu_seconds": 0.0, "running_gpu_seconds": 0.0}
    active, logs, guards, stable = {}, {}, {}, {}

    def publish():
        if summary["status"] in {"waiting", "running"}:
            summary["status"] = "running" if active else "waiting"
        summary["observed_at"] = time.time()
        summary["terminated_gpu_seconds"] = sum(s.get("elapsed_gpu_seconds", 0) for s in summary["states"].values())
        summary["running_gpu_seconds"] = sum(time.time() - summary["states"][name]["started_at"] for name in active)
        write(root / "supervisor.json", summary)

    def finish(name, reason):
        process = active.pop(name)
        if process.poll() is None:
            stop_owned(process)
        process.wait(timeout=15)
        state = summary["states"][name]
        report = read(root / name / "actual/report.json") or {}
        state.update(ended_at=time.time(), exit_code=process.returncode, stop_reason=reason,
                     status="complete" if process.returncode == 0 and reason is None and report.get("status") == "complete" else "stopped")
        state["elapsed_gpu_seconds"] = state["ended_at"] - state["started_at"]
        state["closed_slots"] = sum(r.get("status") == "closed" for r in report.get("rows", []))
        logs.pop(name).close()
        write(root / name / "state.json", state)

    with lock(root):
        try:
            if plan.get("owned_reservation") and any(execution_slots(plan, worker) for worker in WORKERS):
                admitted = consume_owned_reservation(plan, root)
                if admitted:
                    stable[admitted["index"]] = time.time() - LIMITS["gpu_capacity_stability_seconds"]
            while True:
                now = time.time()
                for name, process in list(active.items()):
                    if process.poll() is not None:
                        finish(name, None if process.returncode == 0 else "worker_exit_error")
                waiting = [n for n, s in summary["states"].items() if not s["attempted"] and s["status"] == "not_started"]
                if waiting and now < plan["queue_deadline_at"]:
                    sample = resources()
                    with (root / "waiting-resources.jsonl").open("a") as stream:
                        stream.write(json.dumps(sample) + "\n")
                    occupied = [summary["states"][n]["gpu"] for n in active]
                    ready = available_cards(plan, sample, occupied)
                    stable = {c["index"]: stable.get(c["index"], now) for c in ready}
                    for card in ready:
                        if not waiting or len(active) >= plan["limits"]["max_parallel_model_instances"]:
                            break
                        if time.time() - stable[card["index"]] < LIMITS["gpu_capacity_stability_seconds"]:
                            continue
                        if code_identity() != plan["source"]:
                            raise ValueError("Frozen source changed while waiting")
                        name = waiting.pop(0)
                        folder = root / name
                        folder.mkdir(exist_ok=False)
                        if shutil.disk_usage(root).free < LIMITS["minimum_volume_free_bytes"]:
                            raise RuntimeError("Insufficient data-volume reserve for original trajectories")
                        argv = [sys.executable, "-m", "scripts.software_development_v028", "worker",
                                "--plan", str(plan_path), "--output", str(folder / "actual"), "--worker", name]
                        logs[name] = (folder / "worker.log").open("x")
                        started = time.time()
                        process = subprocess.Popen(argv, cwd=SOURCE, env=_worker_env(root, name, card["index"]),
                                                   stdin=subprocess.DEVNULL, stdout=logs[name], stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                        identity = worker_identity(process.pid)
                        state = summary["states"][name]
                        state.update(status="running", attempted=True, gpu=card["index"], gpu_uuid=card["uuid"],
                                     pid=process.pid, process_identity=identity, started_at=started,
                                     gpu_budget_seconds=plan["worker_gpu_seconds"][name], command=argv)
                        active[name] = process
                        guards[name] = TelemetryGuard(card["index"], card["uuid"], identity["start_ticks"], worker_pid=process.pid)
                        write(folder / "state.json", state)
                        publish()
                if now >= plan["queue_deadline_at"]:
                    for name in waiting:
                        summary["states"][name]["status"] = "not_started_wait_deadline"
                if active:
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        futures = {name: pool.submit(target_resources, summary["states"][name]["gpu"], worker_pid=p.pid)
                                   for name, p in active.items()}
                        samples = {name: future.result() for name, future in futures.items()}
                    size = artifact_bytes(root)
                    free = shutil.disk_usage(root).free
                    for name, process in list(active.items()):
                        if process.poll() is not None:
                            finish(name, None if process.returncode == 0 else "worker_exit_error")
                            continue
                        state = summary["states"][name]
                        measured = samples[name]
                        guard = guards[name].observe(measured, time.time(), process.pid, state["gpu"],
                                                     own_memory_limit_mib=LIMITS["own_gpu_memory_mib"])
                        current_task = read(root / name / "actual/task.json") or {"kind": "loading", "started_at": state["started_at"]}
                        own_rss = rss(process.pid)
                        reason = guard.get("stop_reason")
                        now = time.time()
                        if current_task.get("kind") not in LIMITS["task_seconds"]:
                            reason = "unknown_task_kind"
                        elif now - current_task["started_at"] >= LIMITS["task_seconds"][current_task["kind"]]:
                            reason = "single_task_budget"
                        elif own_rss > LIMITS["host_rss_per_worker_bytes"]:
                            reason = "host_memory_budget"
                        elif size > LIMITS["artifact_bytes"] or free < LIMITS["minimum_volume_free_bytes"]:
                            reason = "trajectory_storage_reserve"
                        with (root / name / "resources.jsonl").open("a") as stream:
                            stream.write(json.dumps({"sample": measured, "guard": guard, "task": current_task,
                                                     "rss_bytes": own_rss, "artifact_bytes": size}) + "\n")
                        if reason:
                            finish(name, reason)
                publish()
                pending = any(not s["attempted"] and s["status"] == "not_started" for s in summary["states"].values())
                if not active and not pending:
                    break
                time.sleep(LIMITS["poll_seconds"])
            summary["status"] = "complete" if all(s["status"] in {"complete", "retained"} for s in summary["states"].values()) else "closed_with_missing_or_interrupted"
        except BaseException as error:
            summary.update(status="supervisor_interrupted", error={"type": type(error).__name__, "message": str(error)})
            for name in list(active):
                finish(name, "supervisor_interrupted")
            raise
        finally:
            summary["ended_at"] = time.time()
            publish()
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "worker", "supervise"])
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=WORKERS)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--prior-run-root", type=Path)
    parser.add_argument("--context-qualification", type=Path)
    parser.add_argument("--reservation-launch", type=Path)
    parser.add_argument("--queue-deadline", default="2026-10-06T00:00:00+08:00")
    args = parser.parse_args()
    if args.mode == "prepare":
        if not args.data_root or not args.qualification:
            parser.error("prepare requires data-root and qualification")
        if args.prior_run_root and not args.context_qualification:
            parser.error("recovery prepare requires context-qualification")
        deadline = datetime.fromisoformat(args.queue_deadline).timestamp()
        plan = (make_recovery_plan(args.data_root, args.qualification, deadline, args.prior_run_root,
                                  context_qualification=args.context_qualification, reservation_launch=args.reservation_launch)
                if args.prior_run_root else make_plan(args.data_root, args.qualification, deadline))
        validate_plan(plan)
        write(args.output, plan)
    elif args.mode == "worker":
        if not args.plan or not args.worker:
            parser.error("worker requires plan and worker")
        run_worker(args.plan, args.output, args.worker)
    else:
        if not args.plan:
            parser.error("supervise requires plan")
        supervise(args.plan, args.output)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("owned supervisor stop")))
    main()
