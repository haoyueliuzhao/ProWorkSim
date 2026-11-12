"""Actual-capacity admission with bounded startup batches and pressure gating.

Per-container CPU/RAM ceilings are retained, but their sum is diagnostic, not a
claim that idle API workers occupy those ceilings. All creation identities and
the original allocation lock remain shared by Qwen, API and grading.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from types import ModuleType

from . import software_benchmark_dispatch_v066 as original
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = "v076-actual-capacity-bounded-batch-admission-r1"
GIB = original.GIB
GLOBAL_ACTOR_LANES = 52
MAX_API_ACTORS = 48
MAX_QWEN_ACTORS = 4
MAX_STARTING_PAIRS = 4
MEMORY_FLOOR = 256 * GIB
DISK_FLOOR = 128 * GIB
PAIR_MEMORY = 32 * GIB
CPU_BUSY_LIMIT = 85.0
ACTOR_KEY = re.compile(r"actor-([0-9]+)\Z")


class CapacityProbe:
    """Read real host capacity; CPU samples never sleep inside allocation lock."""

    def __init__(self, *, root=original.ROOT, clock=time.monotonic):
        self.root, self.clock = Path(root), clock
        self.lock = threading.Lock()
        self.previous = self.last_cpu = None

    def snapshot(self):
        with self.lock:
            now = self.clock()
            fields = Path("/proc/stat").read_text().splitlines()[0].split()
            if fields[0] != "cpu" or len(fields) < 9:
                raise ValueError("Host CPU counters unavailable")
            values = [int(value) for value in fields[1:9]]
            sample = (now, sum(values), values[3] + values[4])
            if self.previous is None:
                self.previous = sample
            elif now - self.previous[0] >= 1:
                elapsed = now - self.previous[0]
                total, idle = sample[1] - self.previous[1], sample[2] - self.previous[2]
                if total <= 0 or not 0 <= idle <= total:
                    self.last_cpu = None
                else:
                    self.last_cpu = (now, 100.0 * (total - idle) / total, elapsed)
                self.previous = sample
            cpu = self.last_cpu
            fresh = cpu is not None and 0 <= now - cpu[0] <= 10
            memory = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines()
                          if line.startswith("MemAvailable:"))
            return {"observed_unix": time.time(), "memory_available_bytes": memory,
                "disk_free_bytes": shutil.disk_usage(self.root).free,
                "cpu_sample_fresh": fresh, "host_cpu_utilization_percent": cpu[1] if fresh else None,
                "host_cpu_sample_interval_seconds": cpu[2] if fresh else None,
                "load_1m": os.getloadavg()[0]}


def pending_pairs(active, *, batch_root=original.BATCH_ROOT, materialized=None):
    """Only inspect ready files for current owned actor claims, at most 52."""
    cache = materialized if materialized is not None else set()
    waiting = []
    for claim in active:
        if claim.get("spec", {}).get("role") != "actor":
            continue
        key, slot = claim.get("key"), claim.get("spec", {}).get("slot_id")
        match = ACTOR_KEY.fullmatch(key or "")
        if match is None or not isinstance(slot, str):
            raise ValueError("Active actor has no trusted physical identity")
        identity = (key, slot)
        if identity in cache:
            continue
        path = Path(batch_root) / "episodes" / match[1] / "controller-ready.json"
        try:
            ready = json.loads(path.read_bytes())
        except FileNotFoundError:
            waiting.append(key)
            continue
        if (ready.get("trusted_SDK_imports_complete") is not True
                or ready.get("version") not in {"v064-private-native-controller-r1", "v064-private-project-controller-r1"}):
            raise ValueError("Materialization evidence differs from the frozen trusted controller")
        cache.add(identity)
    return waiting


def evaluate(active, physical, watchdog, *, pending):
    """Pure status calculation; quota totals are preserved but never gate work."""
    if not isinstance(watchdog, dict) or watchdog.get("fresh") is not True or watchdog.get("admit") is not True:
        pressure_ok = False
    else:
        pressure_ok = True
    cpu = physical.get("host_cpu_utilization_percent")
    cpu_ok = (physical.get("cpu_sample_fresh") is True and isinstance(cpu, (int, float))
              and not isinstance(cpu, bool) and 0 <= cpu < CPU_BUSY_LIMIT)
    memory, disk = physical.get("memory_available_bytes"), physical.get("disk_free_bytes")
    if any(type(value) is not int or value < 0 for value in (memory, disk)):
        raise ValueError("Actual memory/disk sample is malformed")
    actors = [item for item in active if item.get("spec", {}).get("role") == "actor"]
    api = sum(":DEEPSEEK_" in item["spec"].get("slot_id", "") for item in actors)
    qwen = sum(":QWEN_" in item["spec"].get("slot_id", "") for item in actors)
    if api + qwen != len(actors):
        raise ValueError("An active actor has an unknown model identity")
    graders = sum(item.get("spec", {}).get("role") in {"control", "score", "delivery_score"} for item in active)
    grader_margin = max(0, 2 - graders) * 16 * GIB
    pending_memory = len(pending) * PAIR_MEMORY
    spool = sum(item.get("reserved_spool_bytes", 0) for item in active)
    pair_spool = original.CONSTRAINTS["generation_pair_payload_spool_bytes"]
    slots = {"logical_lanes": max(0, GLOBAL_ACTOR_LANES - len(actors)),
        "starting_batch": max(0, MAX_STARTING_PAIRS - len(pending)),
        "actual_memory": max(0, (memory - MEMORY_FLOOR - pending_memory - grader_margin) // PAIR_MEMORY),
        "actual_disk": max(0, (disk - DISK_FLOOR - spool) // pair_spool)}
    admit = pressure_ok and cpu_ok and memory >= MEMORY_FLOOR + pending_memory and disk >= DISK_FLOOR + spool
    additional = min(slots.values()) if admit else 0
    return {"version": VERSION, "admit": admit, "physical": physical, "watchdog": watchdog,
        "actual_active_api_actors": api, "actual_active_qwen_actors": qwen,
        "actual_active_model_reservations": sum(item.get("spec", {}).get("role") == "model" for item in active),
        "actual_active_graders": graders, "pending_pair_keys": pending,
        "pending_pair_memory_bytes": pending_memory, "minimum_grader_headroom_bytes": grader_margin,
        "physical_memory_floor_bytes": MEMORY_FLOOR, "physical_disk_floor_bytes": DISK_FLOOR,
        "additional_pair_slots": additional, "additional_slots_by_constraint": slots,
        "api_generation_limit": min(MAX_API_ACTORS, api + additional),
        "environment_lane_limit": GLOBAL_ACTOR_LANES, "maximum_starting_pairs": MAX_STARTING_PAIRS,
        "cpu_busy_limit_percent": CPU_BUSY_LIMIT, "cpu_gate_passed": cpu_ok,
        "pressure_gate_passed": pressure_ok,
        "reserved_cpu_total_diagnostic": 4 + sum(item["reserved_cpu"] for item in active),
        "reserved_memory_bytes_total_diagnostic": 16 * GIB + sum(item["reserved_memory_bytes"] for item in active),
        "reserved_payload_spool_bytes": spool,
        "quota_sum_is_actual_usage": False, "quota_sum_is_hard_concurrency_gate": False}


def policy(guard, *, watchdog_guard, capacity_probe=None, authorization_ref=None):
    if not callable(guard) or not callable(watchdog_guard):
        raise TypeError("Both exact deployment authority and a live pressure watchdog are required")
    probe = capacity_probe or CapacityProbe()
    read_probe = probe.snapshot if hasattr(probe, "snapshot") else probe
    if not callable(read_probe):
        raise TypeError("capacity_probe must be callable or expose snapshot()")
    materialized = set()
    constraints = {**original.CONSTRAINTS, "active_actor_limit": GLOBAL_ACTOR_LANES,
        "active_controller_limit": GLOBAL_ACTOR_LANES,
        "maximum_active_generation_episodes": GLOBAL_ACTOR_LANES,
        "maximum_active_containers": 2 * GLOBAL_ACTOR_LANES + 4,
        "maximum_combined_reserved_cpu": None, "maximum_combined_reserved_memory_bytes": None,
        "memory_minimum_free_bytes": MEMORY_FLOOR,
        "quota_sum_is_hard_concurrency_gate": False}
    namespace = clone_namespace(original, CONSTRAINTS=constraints)

    def require_allowed(operation, *, slot_id=None, instance_id=None):
        authority = original.require_v066_allowed(operation, slot_id=slot_id, instance_id=instance_id)
        guard("v076.run", slot_id=slot_id, instance_id=instance_id)
        return authority

    def admission_snapshot(active=None):
        if active is None:
            directory = original.BATCH_ROOT / "resource-claims"
            with (directory / "allocation.lock").open("rb") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH)
                active = [json.loads(path.read_bytes()) for path in directory.glob("active-*.json")]
        waiting = pending_pairs(active, materialized=materialized)
        return evaluate(active, read_probe(), watchdog_guard(), pending=waiting)

    def physical_capacity():
        observation = read_probe()
        status = evaluate([], observation, watchdog_guard(), pending=[])
        return {**observation, "admit": status["admit"], "passed": status["admit"],
                "pressure_gate_passed": status["pressure_gate_passed"]}

    def budget(active, cpu, memory, spool=0):
        guard("v076.run")
        state = admission_snapshot(active)
        is_pair = cpu == 6 and memory == PAIR_MEMORY
        if (not state["admit"] or (is_pair and state["additional_pair_slots"] < 1)
                or state["physical"]["memory_available_bytes"] < MEMORY_FLOOR + state["pending_pair_memory_bytes"] + memory
                or state["physical"]["disk_free_bytes"] < DISK_FLOOR + state["reserved_payload_spool_bytes"] + spool):
            raise original.ResourceBusy("Actual CPU/RAM/disk, pending-start batch or live pressure guard prevents admission")
        return {**state, "reserved_cpu_after": state["reserved_cpu_total_diagnostic"] + cpu,
            "reserved_memory_bytes_after": state["reserved_memory_bytes_total_diagnostic"] + memory,
            "reserved_payload_spool_bytes_after": state["reserved_payload_spool_bytes"] + spool,
            "physical_at_admission": state["physical"], "resource_adapter": reference(__file__),
            "supplemental_authorization": authorization_ref,
            "per_container_limits_changed": False}

    def write_claim(path, value):
        role = value.get("spec", {}).get("role")
        if role == "model":
            raise PermissionError("This continuation cannot create or reload model residents")
        if role == "actor":
            # Called by the original allocator while holding allocation.lock.
            active = [json.loads(p.read_bytes()) for p in Path(path).parent.glob("active-actor-*.json")]
            slot = value["spec"].get("slot_id", "")
            model, limit = ("DEEPSEEK", MAX_API_ACTORS) if ":DEEPSEEK_" in slot else ("QWEN", MAX_QWEN_ACTORS)
            if ":" + model + "_" not in slot:
                raise ValueError("Actor identity has no declared model")
            if sum(":" + model + "_" in item.get("spec", {}).get("slot_id", "") for item in active) >= limit:
                raise original.ResourceBusy("The model-specific actor ceiling is full")
        value.update(supplemental_resource_revision=VERSION,
                     supplemental_resource_adapter=reference(__file__),
                     supplemental_authorization=authorization_ref,
                     quota_sum_is_hard_concurrency_gate=False)
        return original._write_claim(path, value)

    def cpu_set(role, index=0):
        if role in {"actor", "controller"}:
            if type(index) is not int or index not in range(GLOBAL_ACTOR_LANES):
                raise ValueError("The shared actor/controller lane is outside 0..51")
            return original.cpu_set(role, index % 12)
        return original.cpu_set(role, index)

    namespace.update(require_v066_allowed=require_allowed, _budget=budget,
        _write_claim=write_claim, cpu_set=cpu_set, physical_capacity=physical_capacity,
        admission_snapshot=admission_snapshot, capacity_probe=probe)
    value = ModuleType(__name__ + ".private_policy")
    value.__dict__.update(namespace)
    return value
