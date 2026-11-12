"""Private, consistently shared 896 GiB admission for the v075 continuation.

The old authority, identities, lock, per-object limits and actual host floors
remain unchanged.  A supplemental guard authorizes the additional aggregate
reservation before every new admission; no frozen module global is mutated.
"""
from __future__ import annotations

from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from . import software_benchmark_expansion_resources_v069 as expansion
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = "v075-consistent-896GiB-admission-r1"
GIB = original.GIB
MEMORY_CAP = 896 * GIB
CPU_CAP = 152


def _module(name, namespace):
    value = ModuleType(name)
    value.__dict__.update(namespace)
    return value


def policy(guard, *, authorization_ref=None):
    """Return a private primary allocator; ``guard`` must bind new deployment."""
    if not callable(guard):
        raise TypeError("A separately sealed v075 scope guard is required")
    constraints = {**original.CONSTRAINTS,
        "maximum_combined_reserved_memory_bytes": MEMORY_CAP,
        "maximum_combined_reserved_cpu": CPU_CAP,
        "active_actor_limit": 18, "active_controller_limit": 18,
        "maximum_active_generation_episodes": 18, "maximum_active_containers": 40}
    namespace = clone_namespace(original, CONSTRAINTS=constraints)

    def require_allowed(operation, *, slot_id=None, instance_id=None):
        # Original guards validate their original 832 GiB plan. The new scope
        # authorizes the explicitly recorded host-admission amendment only.
        authority = original.require_v066_allowed(operation, slot_id=slot_id,
                                                   instance_id=instance_id)
        guard("v075.run", slot_id=slot_id, instance_id=instance_id)
        return authority

    raw_budget = namespace["_budget"]

    def budget(active, cpu, memory, spool=0):
        guard("v075.run")
        value = raw_budget(active, cpu, memory, spool)
        return {**value, "supplemental_resource_revision": VERSION,
            "combined_cpu_cap": CPU_CAP, "combined_memory_cap_bytes": MEMORY_CAP,
            "resource_adapter": reference(__file__),
            "supplemental_authorization": authorization_ref,
            "per_object_limits_changed": False}

    raw_writer = original._write_claim

    def write_claim(path, value):
        if value.get("spec", {}).get("role") == "model":
            raise PermissionError("The aggregate continuation cannot create or reload a model")
        value.update(supplemental_resource_revision=VERSION,
                     supplemental_resource_adapter=reference(__file__),
                     supplemental_authorization=authorization_ref)
        return raw_writer(path, value)

    def cpu_set(role, index=0):
        if role in {"actor", "controller"}:
            if type(index) is not int or index not in range(18):
                raise ValueError("The shared actor/controller lane is outside 0..17")
            return original.cpu_set(role, index % 12)
        return original.cpu_set(role, index)

    namespace.update(require_v066_allowed=require_allowed, _budget=budget,
                     _write_claim=write_claim, cpu_set=cpu_set)
    return _module(__name__ + ".primary", namespace)


def api_policy(guard, *, authorization_ref=None, primary=None):
    """Keep the original eighteen lanes and 32 GiB actor/controller pairs."""
    primary = primary or policy(guard, authorization_ref=authorization_ref)
    constraints = {**expansion.CONSTRAINTS,
        "maximum_combined_reserved_memory_bytes": MEMORY_CAP,
        "maximum_combined_reserved_cpu": CPU_CAP}
    namespace = clone_namespace(expansion, primary=primary, CONSTRAINTS=constraints)
    return _module(__name__ + ".api", namespace)
