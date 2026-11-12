"""Immutable deployment policy and append-only qualified resident registration.

This module never loads a model, reads weights, claims a task or queries CUDA.
Registration proves deployment preparation, not a new benchmark result.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
POLICY_VERSION = "v054-resident-pool-policy-v1"
INTERLEAVED_POLICY_VERSION = "v054-resident-pool-policy-v2-interleaved"
EVENT_VERSION = "v054-resident-pool-event-v1"
ADMISSION_VERSION = "v054-pool-resident-admission-v1"
_REF_CACHE = {}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_ref(item):
    # These are small immutable JSON receipts, never models/image blobs. Hash
    # once per process and verify the complete stat identity on subsequent
    # queue polls; a changed file must pass its original hash again.
    path = Path(item["path"])
    stat = path.stat()
    identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    key = (str(path), item["sha256"], item["bytes"])
    cached = _REF_CACHE.get(key)
    if cached is None or cached[0] != identity:
        cached = (identity, json.loads(checked(item).read_text()))
        _REF_CACHE[key] = cached
    return copy.deepcopy(cached[1])


def declared_session_capacity(declaration, *, ready=None, identity=None):
    """Only an explicitly frozen MP deployment admits two isolated sessions."""
    protocol = declaration.get("session_protocol")
    if protocol is None:
        if declaration.get("maximum_sessions", 1) != 1:
            raise ValueError("Unversioned residents cannot claim extra session slots")
        return 1
    deployment = read_ref(declaration["source_spec"])
    if (declaration["mode"] != "MATCH_PROJECT" or protocol != "mp-interleave-v1"
            or declaration.get("maximum_sessions") != 2
            or deployment.get("session_protocol") != protocol
            or deployment.get("maximum_sessions") != 2):
        raise ValueError("Session capacity differs from the frozen interleave deployment")
    for value in (ready, identity):
        if value is not None and (value.get("session_protocol") != protocol
                                  or value.get("maximum_sessions") != 2):
            raise ValueError("Live resident identity lacks the declared two-session protocol")
    return 2


def validate_pool_policy(policy_ref):
    policy = read_ref(policy_ref)
    interleaved = policy.get("version") == INTERLEAVED_POLICY_VERSION
    if interleaved and (policy.get("inherit_modes") != ["REF"]
            or policy.get("MP_session_protocol") != "mp-interleave-v1"
            or policy.get("maximum_MP_sessions_per_resident") != 2
            or policy.get("maximum_REF_sessions_per_resident") != 1):
        raise ValueError("Unrecognized fixed two-session MATCH/PROJECT pool policy")
    if (policy.get("version") not in {POLICY_VERSION, INTERLEAVED_POLICY_VERSION}
            or policy.get("physical_gpus") != list(range(8))
            or policy.get("maximum_residents") != 8
            or policy.get("minimum_free_mib") != 46080
            or policy.get("minimum_total_mib") != 81920
            or policy.get("allowed_gpu_names") != ["NVIDIA A800-SXM4-80GB"]
            or policy.get("allow_co_residency") is not True
            or policy.get("require_idle") is not False
            or policy.get("maximum_actual_load_attempts_per_gpu") != 1
            or policy.get("maximum_preparation_calls_per_new_resident") != (6 if interleaved else 2)
            or policy.get("automatic_retry_after_load_failure") is not False
            or policy.get("model_loading_authorized") is not True
            or policy.get("preparation_generation_authorized") is not True
            or policy.get("ref_to_mp_after_all_500_scored") is not True
            or policy.get("training_authorized") is not False):
        raise ValueError("Unrecognized fixed deployment-only pool policy")
    for name in ("pool_root", "queue_state_path"):
        path = Path(policy[name])
        if not path.is_absolute() or not path.resolve().is_relative_to(ROOT / "runs/software-benchmark-v054"):
            raise ValueError("Pool artifacts and queue must remain in the project run root")
    for name in ("source_manifest", "inherited_registry", "inherited_admission",
                 "match_template_declaration", "slots"):
        read_ref(policy[name])
    return policy


def _static_registration(event, policy_ref):
    if (event.get("event") != "register" or event.get("pool_policy") != policy_ref
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", event.get("resident_id", ""))
            or event.get("mode") not in {"REF", "MATCH_PROJECT"}
            or event.get("gpu_index") not in range(8)):
        raise ValueError("Invalid resident registration identity")
    declaration = read_ref(event["declaration"])
    if any(declaration.get(key) != event.get(key) for key in ("mode", "gpu_index", "gpu_uuid", "source_spec")):
        raise ValueError("Registration and deployment identities differ")
    if event["mode"] == "REF" and event["gpu_index"] != 7:
        raise ValueError("REF remains the original singleton on GPU7")
    read_ref(event["source_spec"])
    admission = read_ref(event["admission"])
    if (admission.get("version") != ADMISSION_VERSION or admission.get("passed") is not True
            or admission.get("pool_policy") != policy_ref
            or admission.get("declaration") != event["declaration"]
            or admission.get("source_spec") != event["source_spec"]
            or admission.get("resident_id") != event["resident_id"]
            or admission.get("formal_slots_claimed") != 0):
        raise ValueError("A registration requires bound actual preparation evidence")
    ready = read_ref(admission["ready"])
    if (ready.get("ready") is not True or ready.get("resident") is not True
            or ready.get("source_spec") != event["source_spec"]
            or ready.get("gpu_uuid") != event["gpu_uuid"]
            or ready.get("gpu_index") != event["gpu_index"]
            or ready.get("gpu_lease_held") is not True):
        raise ValueError("Resident readiness does not match its deployment")
    live_identity = read_ref(ready["identity"])
    capacity = declared_session_capacity(declaration, ready=ready, identity=live_identity)
    control = read_ref(admission["check_receipt"])
    policy = read_ref(policy_ref)
    interleaved = policy.get("version") == INTERLEAVED_POLICY_VERSION
    if (capacity == 2 and (not interleaved or admission.get("kind") != "new_interleaved_model_device")):
        raise ValueError("Two-session owner requires its new independently qualified registration")
    if admission.get("kind") == "inherited_live_resident":
        if event["mode"] not in policy.get("inherit_modes", ["REF", "MATCH_PROJECT"]):
            raise ValueError("This pool revision does not inherit that live resident mode")
        inherited = read_ref(policy["inherited_admission"])["admitted_modes"][event["mode"]]
        registry = read_ref(policy["inherited_registry"])
        if (registry["residents"][event["mode"]] != event["declaration"]
                or inherited["resident_spec"] != event["source_spec"]
                or inherited["passed"] is not True
                or inherited["check_receipt"] != admission["check_receipt"]
                or inherited["unsettled_tokens"] != 0
                or admission.get("model_reloaded") is not False):
            raise ValueError("Existing resident inheritance lost its original evidence")
    elif admission.get("kind") == "new_interleaved_model_device":
        spec = read_ref(event["source_spec"])
        identity = control.get("resident_identity", {})
        binding = identity.get("resource_binding", {})
        if (not interleaved or capacity != 2 or event["mode"] != "MATCH_PROJECT"
                or spec.get("version") != "v054-match-resident-spec-v3"
                or spec.get("pool_policy") != policy_ref
                or spec.get("resident_id") != event["resident_id"]
                or admission.get("interleaving_check_receipt") != admission["check_receipt"]
                or control.get("version") != "v054-mp-interleave-control-r1"
                or control.get("status") != "passed"
                or control.get("session_protocol") != "mp-interleave-v1"
                or control.get("maximum_sessions") != 2
                or control.get("declaration") != event["declaration"]
                or control.get("authorization") != spec.get("preparation_permit")
                or control.get("actual_model_generation_requests") != 6
                or control.get("completed_sessions") != 4
                or control.get("unsettled_requests") != 0
                or control.get("formal_slots_claimed") != 0
                or control.get("model_loads") != 1
                or any(control.get(key) is not True for key in (
                    "same_resident_PID_and_model", "isolated_sessions", "per_request_FIFO_serialization",
                    "all_three_outputs_equal", "all_three_token_traces_equal", "all_three_rng_transitions_equal"))
                or control.get("weights_reloaded_between_sessions") is not False
                or binding.get("gpu_uuid") != event["gpu_uuid"]
                or binding.get("gpu_index") != event["gpu_index"]
                or identity != live_identity):
            raise ValueError("Interleaved owner lacks its actual six-request independent-session qualification")
        inherited = read_ref(policy["match_template_declaration"])
        baseline = read_ref(inherited["source_spec"])
        if (spec["contract"] != baseline["contract"]
                or spec["capacity_receipt"] != baseline["capacity_receipt"]
                or spec["model_manifest"] != baseline["model_manifest"]):
            raise ValueError("Interleaving changed original numerical/model/capacity identity")
    elif admission.get("kind") == "new_same_model_device":
        if interleaved or capacity != 1:
            raise ValueError("Sequential preparation cannot qualify a two-session pool revision")
        identity = control.get("resident_identity", {})
        binding = identity.get("resource_binding", {})
        spec = read_ref(event["source_spec"])
        if (event["mode"] != "MATCH_PROJECT"
                or spec.get("version") != "v054-match-resident-spec-v2"
                or spec.get("pool_policy") != policy_ref
                or spec.get("resident_id") != event["resident_id"]
                or control.get("status") != "passed"
                or control.get("declaration") != event["declaration"]
                or control.get("authorization") != spec.get("preparation_permit")
                or control.get("actual_model_generation_requests") != 2
                or control.get("unsettled_requests") != 0
                or control.get("formal_slots_claimed") != 0
                or control.get("same_resident_PID_and_model") is not True
                or control.get("distinct_seeds_and_windows") is not True
                or control.get("capacity_retested") is not False
                or binding.get("gpu_uuid") != event["gpu_uuid"]
                or binding.get("gpu_index") != event["gpu_index"]
                or identity != read_ref(ready["identity"])):
            raise ValueError("New device lacks its actual independent two-session qualification")
        inherited = read_ref(policy["match_template_declaration"])
        baseline = read_ref(inherited["source_spec"])
        if (spec["contract"] != baseline["contract"]
                or spec["capacity_receipt"] != baseline["capacity_receipt"]
                or spec["model_manifest"] != baseline["model_manifest"]):
            raise ValueError("Additional device changed original numerical/model/capacity identity")
    else:
        raise ValueError("Unknown resident admission category")
    return event


def read_pool(policy_ref):
    policy = validate_pool_policy(policy_ref)
    directory = Path(policy["pool_root"]) / "events"
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    active, events, previous, seen = {}, [], None, set()
    for sequence, path in enumerate(paths, 1):
        if path.name != f"{sequence:08d}.json":
            raise ValueError("Pool registration chain has a gap or renamed event")
        event_ref, event = reference(path), json.loads(path.read_text())
        if (event.get("version") != EVENT_VERSION or event.get("sequence") != sequence
                or event.get("previous_event") != previous or event.get("pool_policy") != policy_ref):
            raise ValueError("Pool event chain identity changed")
        resident = event["resident_id"]
        if event["event"] == "register":
            _static_registration(event, policy_ref)
            if (resident in seen or any(x["gpu_uuid"] == event["gpu_uuid"] for x in active.values())
                    or len(active) >= policy["maximum_residents"]):
                raise ValueError("Duplicate physical device/resident or too many residents")
            seen.add(resident)
            active[resident] = {**event, "event_reference": event_ref}
        elif event["event"] == "retire":
            old = active.get(resident)
            closure = read_ref(event["closure"])
            if (old is None or old["mode"] != "REF" or old["gpu_index"] != 7
                    or event.get("registration") != old["event_reference"]
                    or closure.get("registration") != old["event_reference"]
                    or closure.get("all_500_ref_scored") is not True
                    or closure.get("resident_session_idle") is not True
                    or closure.get("old_unit_stopped") is not True
                    or closure.get("old_cgroup_empty") is not True
                    or closure.get("old_launcher_gone") is not True):
                raise ValueError("Only completely closed REF may be retired for one-time conversion")
            active.pop(resident)
        else:
            raise ValueError("Unknown pool event")
        events.append(event_ref)
        previous = event_ref
    return {"events": events, "active": active}


def registrations(policy_ref):
    return list(read_pool(policy_ref)["active"].values())


def validate_registration(event, policy_ref):
    current = read_pool(policy_ref)["active"].get(event["resident_id"])
    comparable = {k: v for k, v in event.items() if k != "event_reference"}
    if current is None or comparable != {k: v for k, v in current.items() if k != "event_reference"}:
        raise ValueError("Resident is not an immutable current pool registration")
    return current


def append_event(policy_ref, fields):
    policy = validate_pool_policy(policy_ref)
    root = Path(policy["pool_root"])
    directory = root / "events"
    directory.mkdir(parents=True, exist_ok=True)
    with (root / "registry.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pool = read_pool(policy_ref)
        event = {**fields, "version": EVENT_VERSION, "pool_policy": policy_ref,
                 "sequence": len(pool["events"]) + 1,
                 "previous_event": pool["events"][-1] if pool["events"] else None, "created_utc": now()}
        if event["event"] == "register":
            _static_registration(event, policy_ref)
            if (len(pool["active"]) >= policy["maximum_residents"]
                    or any(x["gpu_uuid"] == event["gpu_uuid"] for x in pool["active"].values())
                    or any(read_ref(item).get("resident_id") == event["resident_id"]
                           for item in pool["events"])):
                raise ValueError("Resident physical device is already registered")
        elif event["event"] == "retire":
            old = pool["active"].get(event["resident_id"])
            closure = read_ref(event["closure"])
            if (old is None or old["mode"] != "REF" or old["gpu_index"] != 7
                    or event["registration"] != old["event_reference"]
                    or closure.get("registration") != old["event_reference"]
                    or not all(closure.get(key) is True for key in (
                        "all_500_ref_scored", "resident_session_idle", "old_unit_stopped",
                        "old_cgroup_empty", "old_launcher_gone"))):
                raise ValueError("Retirement is not the current REF registration")
        else:
            raise ValueError("Unknown event")
        temp = directory / (".pending-" + secrets.token_hex(8))
        write_new(temp, event)
        target = directory / f"{event['sequence']:08d}.json"
        os.link(temp, target)  # Never replace an existing record; readers see only a complete file.
        temp.unlink()
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return reference(target)


def ref_completion_evidence(state, slots):
    """Mechanical full denominator/known costs/reports gate, independent of scores."""
    expected = {row["slot_id"]: row for row in slots["slots"] if row["arm"] == "REF"}
    rows = [row for row in state["rows"] if row["slot"]["arm"] == "REF"]
    if len(state["rows"]) != 1500 or len(expected) != 500 or len(rows) != 500:
        raise ValueError("REF conversion requires the original complete 500-slot inventory")
    if {row["slot"]["slot_id"]: row["slot"] for row in rows} != expected:
        raise ValueError("REF slot identity changed")
    complete = all(row["generation"]["status"] == "closed"
                   and set(row["scores"]) == {"code"}
                   and row["scores"]["code"]["status"] == "official_report"
                   and type(row["scores"]["code"].get("resolved")) is bool
                   and row["delivery"]["status"] == "not_applicable" for row in rows)
    return {"eligible": complete, "expected_ref_slots": 500,
            "closed_ref_generations": sum(r["generation"]["status"] == "closed" for r in rows),
            "ref_slot_ids_sha256": hashlib.sha256("\n".join(sorted(expected)).encode()).hexdigest(),
            "selection_used_scores": False}
