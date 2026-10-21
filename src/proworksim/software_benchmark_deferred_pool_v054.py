"""Host-only health filtering; immutable pool evidence remains a shared gate.

No model request, slot claim, cancellation, service signal or registry mutation
is performed here. The sealed Coordinator must validate its global source and
execution bindings before calling this helper, as its original tick does.
"""
from __future__ import annotations

import re
import subprocess

from .software_benchmark_resident_pool_v054 import registrations, validate_pool_policy
from .software_benchmark_resident_session_v054 import (
    admitted_resident, admin_client, interleaved_status,
)

VERSION = "v054-deferred-live-pool-health-r1"


class SharedPoolIntegrityError(RuntimeError):
    """Global immutable policy/chain/admission damage cannot be filtered away."""


def _live_claims(observed, status):
    """Retain the frozen single-/two-session health semantics, with bounded RPC."""
    declaration, capacity = observed["declaration"], observed["session_capacity"]
    if capacity == 2:
        return interleaved_status(status)
    active = status.get("active_claim")
    if declaration["mode"] == "MATCH_PROJECT":
        healthy = (status.get("resident") is True and "poisoned" in status
                   and status["poisoned"] is None
                   and ((status.get("state") == "idle" and active is None
                         and status.get("inflight") is None)
                        or (status.get("state") == "busy" and isinstance(active, str)
                            and re.fullmatch(r"[a-f0-9]{32}", active) is not None)))
    else:
        healthy = status.get("poisoned") is False
    if not healthy:
        raise RuntimeError("Resident live health is poisoned or invalid")
    return [active] if active is not None else []


def healthy_residents(pool_policy_reference):
    """Return independently healthy resources; never repair or revive a resident.

    All immutable registrations are validated before probing any live resource.
    This deliberately preserves the original factory/worker registration gates:
    missing/corrupt historical qualification evidence is a shared integrity fault,
    while a bad current PID, live ready file, admin socket or poisoned status is
    confined to the affected resident. Full healthy residents remain in `healthy`
    but only residents with an unoccupied session appear in `available`.
    """
    try:
        policy = validate_pool_policy(pool_policy_reference)
        active = registrations(pool_policy_reference)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        raise SharedPoolIntegrityError("Immutable pool evidence failed: " + str(error)) from error
    available, healthy, deferred = {}, {}, []
    for registration in active:
        resident_id = registration["resident_id"]
        try:
            observed = admitted_resident(
                registration["declaration"], query=False,
                pool_policy_reference=pool_policy_reference,
                registration_reference=registration["event_reference"])
            if observed is None:
                raise FileNotFoundError("Registered resident's current ready file is absent")
            # A separate bounded status call avoids a failed REF resource holding
            # this independent resource scan for its full 45-second RPC default.
            status = admin_client(observed["declaration"], observed["identity"], timeout=2).call("status")
            claims = _live_claims(observed, status)
            observed = {**observed, "status": status, "active_claims": claims}
            if (observed["registration"] != registration["event_reference"]
                    or observed["resident_id"] != resident_id
                    or observed["preparation_only"] is not False):
                raise ValueError("Live health no longer binds the exact admitted registration")
            healthy[resident_id] = observed
            if len(claims) < observed["session_capacity"]:
                available[resident_id] = observed
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
            # Recheck immutable evidence after a live failure. If it changed
            # during this scan, treating the error as resource-local would hide
            # a global gate that the unchanged factory/worker will also enforce.
            try:
                validate_pool_policy(pool_policy_reference)
                registrations(pool_policy_reference)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as shared:
                raise SharedPoolIntegrityError("Immutable pool evidence changed during health scan: " + str(shared)) from shared
            deferred.append({"resident_id": resident_id, "registration": registration["event_reference"],
                "mode": registration["mode"], "gpu_index": registration["gpu_index"],
                "status": "deferred_live_resource_fault", "error_type": type(error).__name__,
                "error": str(error)[:2048], "automatic_restart": False,
                "other_residents_cancelled": False, "formal_slot_claimed": False})
    return {"version": VERSION, "pool_policy": pool_policy_reference,
            "status": "ready" if available else "waiting",
            "reason": ("healthy_session_capacity_available" if available else
                       "healthy_residents_at_capacity" if healthy else "no_healthy_registered_resident"),
            "available": available, "healthy": healthy, "deferred": deferred,
            "registered_residents": len(active), "maximum_residents": policy["maximum_residents"],
            "model_calls": 0, "services_modified": False, "formal_slots_claimed": 0}
