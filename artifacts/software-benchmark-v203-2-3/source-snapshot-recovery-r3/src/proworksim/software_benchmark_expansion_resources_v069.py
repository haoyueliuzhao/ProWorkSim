"""API-5M expansion using the original lock and total resource budget.

Logical actor lanes 12..17 share the original lane-0..5 CPU slices. Per-pair
CPU/RAM quotas are unchanged; model CPU lanes and model identities are untouched.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import os
from pathlib import Path

from . import software_benchmark_dispatch_v066 as primary
from .software_benchmark_candidates_v054 import checked, reference

REVISION = "v069-api5m-shared-cpu-resource-expansion-r1"
ROOT, BATCH_ROOT, GIB = primary.ROOT, primary.BATCH_ROOT, primary.GIB
VERSION = primary.VERSION  # Original resource format, with explicit extra authorization.
CONSTRAINTS = {**primary.CONSTRAINTS, "active_actor_limit": 18,
    "active_controller_limit": 18, "maximum_active_generation_episodes": 18,
    "maximum_active_containers": 40}
ResourceBusy = primary.ResourceBusy
ALLOWED_ROLES = frozenset(("actor", "controller", "volume"))


def __getattr__(name):
    return getattr(primary, name)


def scope():
    from . import software_benchmark_api_expansion_scope_v069
    return software_benchmark_api_expansion_scope_v069


def ordinary_user():
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The expansion resource owner must remain an ordinary user")


def require_v066_allowed(operation, *, slot_id=None, instance_id=None):
    ordinary_user()
    scope().require_allowed("v069.run", slot_id=slot_id, instance_id=instance_id)
    return primary.require_v066_allowed(operation, slot_id=slot_id, instance_id=instance_id)


def cpu_set(role, index=0):
    if role in {"actor", "controller"}:
        if type(index) is not int or index not in range(18):
            raise ValueError("Expansion actor/controller lane must be within 0..17")
        return primary.cpu_set(role, index % 12)
    return primary.cpu_set(role, index)


def grader_headroom(active):
    actual = sum(item.get("spec", {}).get("role") in {"score", "delivery_score", "control"} for item in active)
    missing = max(0, 2 - actual)
    return {"active_graders": actual, "missing_reserved_grader_slots": missing,
        "cpu": 4 * missing, "memory_bytes": 16 * GIB * missing}


def budget_for_actor(active):
    margin = grader_headroom(active)
    admitted = primary._budget(active, 6 + margin["cpu"], 32 * GIB + margin["memory_bytes"],
                               CONSTRAINTS["generation_pair_payload_spool_bytes"])
    return {**admitted, "grader_headroom": margin,
        "headroom_is_admission_margin_not_duplicate_claim": True,
        "actual_reserved_cpu_after": admitted["reserved_cpu_after"] - margin["cpu"],
        "actual_reserved_memory_bytes_after": admitted["reserved_memory_bytes_after"] - margin["memory_bytes"]}


def _bound_spec(key):
    auth = require_v066_allowed("v066.run")
    plan = primary._cached_json(auth["plan"])
    spec = plan["resources"].get(key)
    if not spec or spec.get("role") not in ALLOWED_ROLES or spec.get("diagnostic"):
        raise ValueError("Expansion cannot claim models, graders or diagnostic identities")
    row = next((r for r in plan["rows"] if r["slot_id"] == spec.get("slot_id")), None)
    if (row is None or row["model_key"] != "DEEPSEEK" or row["input_plus_output_tokens"] != 5_000_000
            or spec.get("instance_id") != row["instance_id"]):
        raise ValueError("Only the original DeepSeek 5M REF/PROJECT inventory may expand")
    require_v066_allowed("v066.run", slot_id=row["slot_id"], instance_id=row["instance_id"])
    return auth, spec, row


def validate_owned_claim(claim_ref, *, slot_id=None, instance_id=None):
    value = primary.load(claim_ref)
    spec = value.get("spec", {})
    if (Path(claim_ref["path"]).resolve() != BATCH_ROOT / "resource-claims" / (value.get("key", "") + ".json")
            or value.get("version") != VERSION or value.get("expansion_revision") != REVISION
            or value.get("expansion_authorization") != reference(scope().AUTH_FILE)
            or value.get("authorization") != reference(primary.AUTHORIZATION_FILE)
            or value.get("plan") != reference(primary.PLAN_FILE)
            or spec.get("role") not in ALLOWED_ROLES
            or slot_id not in (None, spec.get("slot_id"))
            or instance_id not in (None, spec.get("instance_id"))
            or type(value.get("lane")) is not int or value["lane"] not in range(18)):
        raise ValueError("Foreign or unapproved expansion claim")
    expected_cpu, expected_memory = (6, 32 * GIB) if spec["role"] == "actor" else (0, 0)
    if value.get("reserved_cpu") != expected_cpu or value.get("reserved_memory_bytes") != expected_memory:
        raise ValueError("The original complete pair reservation cannot be weakened")
    return value


def authorize_cleanup(claims, *, slot_id, instance_id):
    ordinary_user()
    scope().require_allowed("v069.drain", slot_id=slot_id, instance_id=instance_id)
    primary.require_v066_allowed("v066.run", slot_id=slot_id, instance_id=instance_id)
    for claim_ref in claims.values():
        validate_owned_claim(claim_ref, slot_id=slot_id, instance_id=instance_id)


def claim_resource(key, *, lane=None):
    auth, spec, row = _bound_spec(key)
    directory = BATCH_ROOT / "resource-claims"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / "allocation.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = directory / (key + ".json")
        if path.exists():
            raise ValueError("A physical creation identity is never reused")
        active = [primary.load(reference(p)) for p in directory.glob("active-*.json")]
        role, parent_actor, lease = spec["role"], None, None
        reserved_cpu = reserved_memory = reserved_spool = 0
        admission = None
        if role == "actor":
            if lane is not None and (type(lane) is not int or lane not in range(18)):
                raise ValueError("Requested expansion lane is out of scope")
            if sum(item.get("spec", {}).get("role") == "actor" for item in active) >= 18:
                raise ResourceBusy("All eighteen global actor-pair slots are reserved")
            choices = range(18) if lane is None else [lane]
            selected = next((n for n in choices if not (directory / f"active-actor-{n}.json").exists()), None)
            if selected is None:
                raise ResourceBusy("No global actor lane is free")
            admission = budget_for_actor(active)
            reserved_cpu, reserved_memory = 6, 32 * GIB
            reserved_spool = CONSTRAINTS["generation_pair_payload_spool_bytes"]
            lease = directory / f"active-actor-{selected}.json"
        else:
            parent_actor = "actor-" + str(row["slot_index"])
            actor_ref = reference(directory / (parent_actor + ".json"))
            actor = validate_owned_claim(actor_ref, slot_id=row["slot_id"], instance_id=row["instance_id"])
            selected = actor["lane"]
            actor_lease = directory / f"active-actor-{selected}.json"
            if (actor.get("lease") != str(actor_lease) or not actor_lease.exists()
                    or actor_lease.read_bytes() != checked(actor_ref).read_bytes()
                    or (directory / (parent_actor + ".released.json")).exists()):
                raise ResourceBusy("The exact active expansion actor must precede its child resources")
            if lane is not None and lane != selected:
                raise ValueError("Controller/volume must share its actor's exact lane")
        value = {"version": VERSION, "key": key, "spec": copy.deepcopy(spec),
            "authorization": reference(primary.AUTHORIZATION_FILE), "plan": auth["plan"],
            "expansion_authorization": reference(scope().AUTH_FILE), "expansion_revision": REVISION,
            "expansion_policy_source": reference(__file__), "lease": str(lease) if lease else None,
            "lane": selected, "parent_actor_key": parent_actor, "reserved_cpu": reserved_cpu,
            "reserved_memory_bytes": reserved_memory, "reserved_spool_bytes": reserved_spool,
            "admission": admission, "CPU_sharing": {"logical_lane": selected,
                "original_CPU_lane": selected % 12, "exclusive_CPU_guarantee": False,
                "actor_cpuset": cpu_set("actor", selected), "controller_cpuset": cpu_set("controller", selected)},
            "docker_name": "pws-v066-" + hashlib.sha256((str(BATCH_ROOT) + ":" + key).encode()).hexdigest()[:24]}
        raw = primary._write_claim(path, value)
        if lease is not None:
            with lease.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return reference(path)


def release_resource(claim_ref, *, quiescent):
    ordinary_user()
    claim = validate_owned_claim(claim_ref)
    authorize_cleanup({claim["spec"]["role"]: claim_ref}, slot_id=claim["spec"]["slot_id"],
                      instance_id=claim["spec"]["instance_id"])
    return primary.release_resource(claim_ref, quiescent=quiescent)
