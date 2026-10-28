"""Finish old owned API work before stopping its otherwise idle dispatcher.

No active model task is cancelled.  Existing scoring identities are imported,
never replayed; at most one previously unused score is run per poll.  All new
bookkeeping is under v069, while old unused scoring identities retain their
original resource limits and global allocation lock.
"""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import subprocess
import threading
import time

from . import software_benchmark_dispatch_v066 as primary
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import atomic_write, json_bytes

VERSION = "v069-owned-predecessor-natural-drain-r1"
OLD_UNIT = "proworksim-v068-api-continuation.service"
_LOCK = threading.Lock()


def load(ref):
    return json.loads(checked(ref).read_bytes())


def drain_ready(progress, active_owned_claims, reserved_requests, unfinished_prepared_scores, *, now):
    """A paused thread and fully settled children are required before unit stop."""
    observed = progress.get("unix")
    if (not isinstance(observed, (int, float)) or now - observed > 180
            or observed > now + 5 or progress.get("phase") != "waiting"
            or progress.get("capacity_wait_reason") != "invalid_concurrency_control"
            or progress.get("effective_generation_limit") != 0
            or progress.get("actual_generation_futures") != 0):
        return False, "predecessor_generation_not_naturally_drained"
    if active_owned_claims:
        return False, "predecessor_owned_resources_still_active"
    if reserved_requests:
        return False, "predecessor_API_requests_still_reserved"
    if unfinished_prepared_scores:
        return False, "predecessor_prepared_grading_not_yet_quiet"
    return True, "owned_generation_and_prepared_graders_naturally_complete"


def validate_owned_unit(spec, properties, *, old_root, uid):
    expected_entrypoint = primary.ROOT / "tools/run_api_continuation_v068.py"
    if (spec.get("unit") != OLD_UNIT or spec.get("role") != "api" or spec.get("user_id") != uid
            or spec.get("reporting_root") != str(old_root)
            or spec.get("entrypoint", {}).get("path") != str(expected_entrypoint)
            or not isinstance(spec.get("ownership_token"), str) or len(spec["ownership_token"]) != 32):
        raise ValueError("The predecessor unit specification is not this project's exact owned API unit")
    checked(spec["entrypoint"])
    if properties.get("ActiveState") == "inactive" and properties.get("MainPID") == "0":
        return "inactive"
    if (properties.get("Description") != "ProWorkSim v068 api coordinator " + spec["ownership_token"]
            or str(expected_entrypoint) not in properties.get("ExecStart", "")
            or not properties.get("ControlGroup", "").endswith("/" + OLD_UNIT)
            or properties.get("ActiveState") not in {"active", "deactivating"}
            or not properties.get("MainPID", "").isdigit() or int(properties["MainPID"]) <= 0):
        raise ValueError("The live user unit no longer matches the exact predecessor ownership")
    return properties["ActiveState"]


def _manager(arguments):
    from .software_benchmark_ref_resident_v066 import user_manager_environment
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Only the existing ordinary-user manager may be used")
    return subprocess.run(["systemctl", "--user", *arguments], env=user_manager_environment(),
                          capture_output=True, text=True, timeout=20)


def _show():
    result = _manager(["show", OLD_UNIT, "--no-pager",
        "--property=Description,ExecStart,ControlGroup,ActiveState,SubState,MainPID"])
    if result.returncode != 0:
        raise RuntimeError("Cannot inspect the exact predecessor user unit")
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def _owned_observation(scope, handoff, rows):
    scheduled = set(handoff["old_scheduled_slot_ids"])
    directory = primary.BATCH_ROOT / "resource-claims"
    with (directory / "allocation.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        active = [json.loads(path.read_bytes()) for path in directory.glob("active-*.json")]
    owned = [item["key"] for item in active if item.get("spec", {}).get("slot_id") in scheduled]
    ledger = primary.PREDECESSOR_ROOT / "api-budget/ledger.sqlite3"
    with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        reserved = [slot for (slot,) in db.execute("SELECT DISTINCT slot_id FROM requests WHERE status='reserved'")
                    if slot in scheduled]
    # A score prepared by the old loop may have started just before its blocking
    # admission wait.  Require its completed cleanup, including its process exit.
    unfinished = []
    for slot in scheduled:
        for prefix in ("score-", "delivery-score-"):
            key = prefix + str(rows[slot]["slot_index"])
            folder = primary.GRADING_ROOT / key
            if not (folder / "request.json").exists():
                continue
            completion, quiet = folder / "completion.json", folder / "quiescence.json"
            if not completion.exists() or not quiet.exists():
                unfinished.append(key)
                continue
            value = json.loads(quiet.read_bytes())
            if (value.get("quiescent") is not True or value.get("cleanup_errors") != []
                    or value.get("create_result_unknown") is not False):
                unfinished.append(key)
    progress = json.loads((scope.OLD_API_ROOT / "progress.json").read_bytes())
    ready, reason = drain_ready(progress, owned, reserved, unfinished, now=time.time())
    return {"ready": ready, "reason": reason, "progress": progress,
            "active_owned_claims": owned, "reserved_old_API_slots": reserved,
            "unfinished_prepared_scores": unfinished}


def _score_once(row, result_ref, endpoint, grading, stop_event):
    key = ("score-" if endpoint == "code" else "delivery-score-") + str(row["slot_index"])
    folder = primary.GRADING_ROOT / key
    request_path = folder / "request.json"
    request_ref = reference(request_path) if request_path.exists() else grading.prepare_score(result_ref, endpoint=endpoint)
    request = load(request_ref)
    if request.get("slot_id") != row["slot_id"] or request.get("generation_result") != result_ref:
        raise ValueError("Old grading request is not this exact original candidate")
    consumed = (primary.BATCH_ROOT / "resource-claims" / (key + ".json")).exists() or (folder / "started.json").exists()
    completion_path = folder / "completion.json"
    if completion_path.exists():
        if not grading.trustworthy_cleanup(request_ref):
            raise RuntimeError("Existing predecessor score cleanup is unproven")
        return {"request": request_ref, "completion": load(reference(completion_path))}, False
    if consumed:
        raise RuntimeError("Consumed predecessor score lacks a completion; it cannot be replayed")
    if stop_event is not None and stop_event.is_set():
        return None, False
    completion = grading.run_request(request_ref, stop_event=stop_event)
    if completion.get("status") == "not_started_cancelled":
        return None, False
    if not grading.trustworthy_cleanup(request_ref):
        raise RuntimeError("New predecessor finalizer score cleanup is unproven")
    return {"request": request_ref, "completion": completion}, True


def _finalize_one(scope, handoff, rows, stop_event, *, grading=None):
    if grading is None:
        from . import software_benchmark_grading_recovery_v068 as grading
    directory = scope.BATCH_ROOT / "predecessor-drain"
    checkpoint = directory / "checkpoint.json"
    summary_path = scope.OLD_API_ROOT / "run-summary.json"
    if not summary_path.exists():
        return {"complete": False, "status": "waiting_for_predecessor_shutdown_summary"}
    summary_ref = reference(summary_path)
    summary = load(summary_ref)
    scheduled = set(handoff["old_scheduled_slot_ids"])
    state = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else {
        "version": VERSION, "predecessor_summary": summary_ref,
        "generation": {s: v for s, v in summary["generation"].items() if s in scheduled},
        "scores": {s: v for s, v in summary["scores"].items() if s in scheduled},
        "deliveries": {s: v for s, v in summary["deliveries"].items() if s in scheduled},
        "exceptions": [], "new_generation": 0, "original_results_modified": False}
    if state["predecessor_summary"] != summary_ref:
        raise ValueError("The stopped predecessor summary changed")
    used_new_score = False
    for slot in sorted(scheduled, key=lambda value: rows[value]["slot_index"]):
        if stop_event is not None and stop_event.is_set():
            break
        row = rows[slot]
        entry = state["generation"].get(slot)
        if entry is None:
            # Preserve missing generation as an unresolved identity. Never rerun.
            state["exceptions"].append({"slot_id": slot, "kind": "scheduled_generation_missing_terminal_record"})
            continue
        if entry.get("status") != "closed":
            continue
        result_ref = entry["result"]
        if slot not in state["scores"]:
            try:
                value, ran = _score_once(row, result_ref, "code", grading, stop_event)
            except Exception as error:
                key = "score-" + str(row["slot_index"])
                if (primary.BATCH_ROOT / "resource-claims" / (key + ".json")).exists():
                    raise  # Consumed identity or uncertain cleanup is never hidden.
                value, ran = {"status": "technical_unknown", "error": str(error)}, False
                state["exceptions"].append({"slot_id": slot, "kind": "old_code_preparation", "error": str(error)})
            if value is None:
                break
            state["scores"][slot] = value
            used_new_score |= ran
        if row["arm"] == "PROJECT":
            delivery = state["deliveries"].get(slot)
            if delivery is None or delivery.get("status") in {"waiting_for_own_code_score", "requires_separate_official_score"}:
                try:
                    delivery = grading.delivery_disposition(result_ref, state["scores"][slot].get("request"))
                except Exception as error:
                    delivery = {"status": "technical_unknown", "resolved": None, "error": str(error)}
                    state["exceptions"].append({"slot_id": slot, "kind": "old_delivery_evidence", "error": str(error)})
                state["deliveries"][slot] = delivery
                if delivery.get("scoring_request") is not None and not used_new_score:
                    value, ran = _score_once(row, result_ref, "delivery", grading, stop_event)
                    if value is not None:
                        state["deliveries"][slot] = {"status": "official_attempt_completed", **value}
                    used_new_score |= ran
        if used_new_score:
            break
    # Count unfinished endpoints without relabeling technical unknown as failure.
    pending = []
    for slot, entry in state["generation"].items():
        if entry.get("status") != "closed":
            continue
        if slot not in state["scores"]:
            pending.append({"slot_id": slot, "endpoint": "code"})
        if rows[slot]["arm"] == "PROJECT":
            delivery = state["deliveries"].get(slot)
            if delivery is None or delivery.get("status") in {"waiting_for_own_code_score", "requires_separate_official_score"}:
                pending.append({"slot_id": slot, "endpoint": "delivery"})
    state["pending"] = pending
    directory.mkdir(parents=True, exist_ok=True)
    atomic_write(checkpoint, json_bytes(state))
    if pending or (stop_event is not None and stop_event.is_set()):
        return {"complete": False, "status": "old_score_finalization_pending", "finalizer_pending": len(pending),
                "checkpoint": reference(checkpoint)}
    complete = directory / "complete.json"
    if not complete.exists():
        write_new(complete, {"version": VERSION, "finished_unix": time.time(),
            "state": state, "predecessor_summary": summary_ref, "new_generation": 0,
            "old_coordinator_stopped_after_children_quiet": True})
    return {"complete": True, "status": "predecessor_drained_and_finalized", "finalizer_pending": 0,
            "result": reference(complete)}


def poll(*, stop_event=None):
    """One bounded pass, intended for the new coordinator's joined worker thread."""
    if not _LOCK.acquire(blocking=False):
        return {"complete": False, "status": "another_finalizer_poll_in_progress"}
    try:
        from . import software_benchmark_api_expansion_scope_v069 as scope
        scope.require_allowed("v069.drain")
        folder = scope.BATCH_ROOT / "predecessor-drain"
        complete = folder / "complete.json"
        if complete.exists():
            return {"complete": True, "status": "predecessor_drained_and_finalized", "result": reference(complete)}
        if stop_event is not None and stop_event.is_set():
            return {"complete": False, "status": "finalizer_stop_requested"}
        handoff = load(reference(scope.HANDOFF_FILE))
        rows = {row["slot_id"]: row for row in load(handoff["original_plan"])["rows"]}
        spec_ref = reference(scope.OLD_API_ROOT / "coordinator-unit.json")
        spec = load(spec_ref)
        properties = _show()
        state = validate_owned_unit(spec, properties, old_root=scope.OLD_API_ROOT, uid=os.getuid())
        if state != "inactive":
            if state == "deactivating":
                return {"complete": False, "status": "waiting_for_owned_predecessor_exit"}
            observation = _owned_observation(scope, handoff, rows)
            if not observation["ready"]:
                return {"complete": False, "status": observation["reason"], "observation": observation}
            folder.mkdir(parents=True, exist_ok=True)
            intent = folder / "stop-intent.json"
            if not intent.exists():
                write_new(intent, {"version": VERSION, "unit": OLD_UNIT, "unit_spec": spec_ref,
                    "unit_properties": properties, "observation": observation,
                    "owning_user": os.getuid(), "new_generation": 0, "active_tasks_cancelled": False})
            result = _manager(["stop", "--no-block", OLD_UNIT])
            if result.returncode != 0:
                raise RuntimeError("The exact drained predecessor unit did not accept its normal stop")
            return {"complete": False, "status": "owned_drained_predecessor_stop_requested"}
        # Old finally owns releasing its coordinator claim.  Never remove it here.
        old_lease = primary.BATCH_ROOT / "resource-claims/active-v068-coordinator.json"
        if old_lease.exists():
            return {"complete": False, "status": "waiting_for_predecessor_owned_reservation_release"}
        return _finalize_one(scope, handoff, rows, stop_event)
    finally:
        _LOCK.release()
