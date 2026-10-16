"""One pre-model native-cache attempt; retry only in a fresh host-owned process.

This adapter neither loads a model nor dispatches numerical work. A caller must
validate its small launch/source binding first, acquire here, then run the full
frozen-material check and unchanged loader in this same process. CUDA failures
are recorded using CPU-only data; an unhealthy CUDA context is never queried a
second time while handling an error.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import time

from proworksim.storage import read_json
from scripts import software_learning_resources_v050r3 as prior
from scripts.run_ne_v021 import reference, write

VERSION = "software-learning-startup-resources-v0.50-r5"
RECEIPT = "startup-resource-receipt.json"
RESOURCE_POLICY = copy.deepcopy(prior.RESOURCE_POLICY)
LIMITS_OVERRIDES = copy.deepcopy(prior.LIMITS_OVERRIDES)


class StartupResourceUnavailable(RuntimeError):
    """A fully recorded zero-model attempt which the host may requeue."""

    def __init__(self, receipt):
        self.receipt = copy.deepcopy(receipt)
        super().__init__(receipt["reason"])


def _cuda_oom(error, torch):
    """Recognize typed CUDA OOM or the two specific CUDA runtime messages."""
    oom_type = getattr(torch.cuda, "OutOfMemoryError", None)
    if isinstance(oom_type, type) and isinstance(error, oom_type):
        return True
    if not isinstance(error, RuntimeError):
        return False
    first_line = str(error).splitlines()[0] if str(error) else ""
    return (first_line == "CUDA error: out of memory"
            or first_line.startswith("CUDA out of memory."))


def _persist(output, record):
    write(output / RECEIPT, record)
    with (output / "native-cache-resources.jsonl").open("a") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    write(output / "task.json", {
        "task": "own-native-cache-" + record["status"],
        "kind": "reservation_wait" if record["retryable"] else record["status"],
        "started_at": record["started_at"], "pid": record["pid"],
        "new_model_calls": 0, "new_backward_calls": 0,
        "loader_not_entered": True, "phase": record["phase"],
    })


def acquire_startup_cache(output, binding, *, torch=None, identity=None):
    """Attempt once, returning ready evidence or raising a typed retryable error.

    ``identity`` is the caller's verified run/worker/source binding. No material,
    checkpoint, model loader, random generator or native model call is accessed.
    A failed attempt must end its process; this function never sleeps or retries.
    """
    binding = prior.validate_binding(binding)
    output = Path(output).resolve()
    if any((output / name).exists() for name in (RECEIPT, "cache-reservation.json")):
        raise FileExistsError("Use a new archived startup attempt, never overwrite one")
    output.mkdir(parents=True, exist_ok=True)
    record = {
        "version": VERSION, "status": "acquiring", "phase": "cuda_capacity_snapshot",
        "started_at": time.time(), "pid": os.getpid(), "output": str(output),
        "binding": binding, "identity": copy.deepcopy(identity),
        "new_model_calls": 0, "new_backward_calls": 0, "new_optimizer_steps": 0,
        "loader_not_entered": True, "retryable": False,
        "allocation_attempts": 0, "live_reservation_tensors": 0,
        "empty_cache_called": False, "cuda_requeried_after_error": False,
        "same_process_resource_retries": 0,
    }
    write(output / "task.json", {
        "task": "own-native-cache-reservation_wait", "kind": "reservation_wait",
        "started_at": record["started_at"], "pid": record["pid"],
        "new_model_calls": 0, "new_backward_calls": 0, "loader_not_entered": True,
    })
    if torch is None:
        import torch
    target = binding["target_mib"] * prior.MIB
    try:
        before = prior.cuda_snapshot(torch)
        record["last_successful_snapshot"] = before
        capacity = before["device_free_bytes"] + before["reserved_bytes"]
        required = target + RESOURCE_POLICY["allocation_margin_mib"] * prior.MIB
        if capacity < required:
            record.update(status="resource_unavailable", retryable=True,
                reason="frozen_startup_capacity_unavailable", ended_at=time.time(),
                available_capacity_bytes=capacity, required_capacity_bytes=required,
                restart_requires_fresh_process=True)
            _persist(output, record)
            raise StartupResourceUnavailable(record)
        record.update(phase="cuda_cache_allocation", allocation_attempts=1)
        # fill_cache's finally drops all temporary tensors on every exit. It
        # leaves only reusable native allocator cache, not persistent ballast.
        prior.fill_cache(torch, target)
        record["phase"] = "cuda_cache_verification"
        after = prior.cuda_snapshot(torch)
        record["last_successful_snapshot"] = after
        if after["allocated_bytes"] != before["allocated_bytes"]:
            raise RuntimeError("Reservation leaked live temporary CUDA tensors")
        if after["reserved_bytes"] < target:
            raise RuntimeError("Reservation did not establish the frozen cache target")
        record.update(startup_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            startup_peak_reserved_bytes=torch.cuda.max_memory_reserved())
        record["phase"] = "cuda_startup_peak_reset"
        torch.cuda.reset_peak_memory_stats()
    except StartupResourceUnavailable:
        raise
    except RuntimeError as error:
        retryable = _cuda_oom(error, torch)
        record.update(status="resource_unavailable" if retryable else "fault",
            retryable=retryable, ended_at=time.time(),
            reason="pre_model_cuda_out_of_memory" if retryable else "startup_resource_fault",
            error={"type": type(error).__name__, "message": str(error)},
            restart_requires_fresh_process=retryable)
        # Deliberately no CUDA API, cleanup allocation, synchronize or snapshot.
        _persist(output, record)
        if retryable:
            raise StartupResourceUnavailable(record) from error
        raise
    record.update(status="ready", stage="preload_cache_ready", phase="cache_ready",
        ended_at=time.time(), startup_peak_counters_reset_before_model_load=True, **after)
    _persist(output, record)
    write(output / "cache-reservation.json", record)
    return record


def use_startup_cache(output, startup, receipt, binding, *, identity=None):
    """Transfer ready evidence to the original loader without another allocation.

    The native allocator cache remains in this exact process. The original
    loader still performs its own exact GPU/PID capacity admission afterwards.
    This function is not a replacement for that check or for frozen materials.
    """
    output, startup = Path(output).resolve(), Path(startup).resolve()
    binding = prior.validate_binding(binding)
    if (output == startup or output in startup.parents or startup in output.parents
            or receipt != read_json(startup / RECEIPT)
            or receipt != read_json(startup / "cache-reservation.json")
            or receipt.get("version") != VERSION or receipt.get("status") != "ready"
            or receipt.get("phase") != "cache_ready" or receipt.get("retryable") is not False
            or receipt.get("pid") != os.getpid() or receipt.get("output") != str(startup)
            or receipt.get("binding") != binding or receipt.get("identity") != identity
            or receipt.get("new_model_calls") != 0 or receipt.get("new_backward_calls") != 0
            or receipt.get("new_optimizer_steps") != 0 or receipt.get("loader_not_entered") is not True
            or receipt.get("live_reservation_tensors") != 0
            or receipt.get("startup_peak_counters_reset_before_model_load") is not True
            or receipt.get("reserved_bytes", 0) < binding["target_mib"] * prior.MIB):
        raise ValueError("Reuse only this process's exact ready startup cache evidence")
    if (output / "cache-reservation.json").exists():
        raise FileExistsError("Startup cache was already transferred to this model attempt")
    output.mkdir(parents=True, exist_ok=True)
    transferred = {**receipt, "startup_cache_source": reference(startup / "cache-reservation.json"),
        "startup_receipt_source": reference(startup / RECEIPT),
        "transferred_to_output": str(output), "transferred_at": time.time(),
        "same_process_preacquired_cache": True, "additional_reservation_attempts": 0}
    write(output / "cache-reservation.json", transferred)
    write(output / "task.json", {"task": "own-native-cache-loading", "kind": "loading",
        "started_at": time.time(), "pid": os.getpid(),
        "new_model_calls": 0, "new_backward_calls": 0})
    return transferred
