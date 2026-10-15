"""Own reusable CUDA cache for the isolated r3 workers; never control foreign jobs.

Imports are CPU-only. CUDA is imported only by a real worker's reservation call.
No tensor survives a resource helper, so the original model can reuse its cache.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
import io
import json
import math
import os
from pathlib import Path
import time

from scripts.run_ne_v021 import write

VERSION = "software-learning-resources-v0.50-r3"
MIB = 1024**2
ENVIRONMENT = "PROWORKSIM_V050R3_RESERVATION"
RESOURCE_POLICY = {
    "version": VERSION, "minimum_free_gpu_mib": 45 * 1024,
    "minimum_cache_target_mib": 44 * 1024, "maximum_cache_target_mib": 72 * 1024,
    "launch_unreserved_mib": 1024, "allocation_margin_mib": 256,
    "cache_refill_chunk_mib": 256, "reservation_poll_seconds": 5,
    "max_parallel_model_instances": None, "gpu_capacity_stability_seconds": 0,
    "minimum_live_free_gpu_mib": 0, "own_gpu_memory_mib": None,
    "foreign_processes_controlled": False, "numerical_path_changed": False,
    "preload_resource_only_retries": True, "model_or_training_retries": False,
}
LIMITS_OVERRIDES = {key: RESOURCE_POLICY[key] for key in (
    "minimum_free_gpu_mib", "max_parallel_model_instances",
    "gpu_capacity_stability_seconds", "minimum_live_free_gpu_mib", "own_gpu_memory_mib")}


def resource_policy():
    return dict(RESOURCE_POLICY)


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Finite resource value required")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Finite resource value required") from error
    if not math.isfinite(result) or result < 0:
        raise ValueError("Finite nonnegative resource value required")
    return result


def _rows(sample, key, columns):
    result = sample.get(key, {})
    if result.get("returncode") != 0:
        raise ValueError("Incomplete resource observation")
    rows = list(csv.reader(io.StringIO(result["stdout"]), strict=True))
    if any(len(row) != columns for row in rows):
        raise ValueError("Incomplete resource rows")
    return [[cell.strip() for cell in row] for row in rows]


def available_cards(plan, sample, excluded=()):
    """Only actual device free memory admits a new process, with no stable wait."""
    try:
        processes = _rows(sample, "processes", 4)
        occupied = set()
        for uuid, pid, memory, name in processes:
            if int(pid) <= 0 or not uuid or not name:
                raise ValueError("Invalid process row")
            _number(memory)
            occupied.add(uuid)
        cards, seen = [], set()
        for index, uuid, name, free, total, usage in _rows(sample, "gpus", 6):
            index = int(index)
            free, total, usage = map(_number, (free, total, usage))
            if index in seen or free > total or usage > 100 or not uuid:
                raise ValueError("Invalid or duplicate GPU observation")
            seen.add(index)
            if (index in range(8) and index in plan["gpu_preference"] and index not in excluded
                    and "A100" in name and total >= 81920
                    and free >= RESOURCE_POLICY["minimum_free_gpu_mib"]):
                cards.append({"index": index, "uuid": uuid, "free_mib": free,
                    "total_mib": total, "utilization_percent": usage, "shared": uuid in occupied})
        return sorted(cards, key=lambda card: (-card["free_mib"], card["index"]))
    except (KeyError, ValueError, TypeError, csv.Error):
        return []


def launch_target(card):
    free = _number(card["free_mib"])
    target = min(RESOURCE_POLICY["maximum_cache_target_mib"],
                 math.floor(free - RESOURCE_POLICY["launch_unreserved_mib"]))
    if free < RESOURCE_POLICY["minimum_free_gpu_mib"] or target < RESOURCE_POLICY["minimum_cache_target_mib"]:
        raise ValueError("Insufficient physical capacity for the frozen cache target")
    result = {"version": VERSION, "gpu_index": card["index"], "gpu_uuid": card["uuid"],
        "sampled_free_mib": free, "target_mib": target}
    return validate_binding(result)


def validate_binding(binding):
    if (not isinstance(binding, dict) or binding.get("version") != VERSION
            or type(binding.get("gpu_index")) is not int or binding["gpu_index"] not in range(8)
            or not isinstance(binding.get("gpu_uuid"), str) or not binding["gpu_uuid"]
            or type(binding.get("target_mib")) is not int):
        raise ValueError("Invalid frozen reservation identity")
    free = _number(binding.get("sampled_free_mib"))
    expected = min(RESOURCE_POLICY["maximum_cache_target_mib"], math.floor(free - 1024))
    if free < 46080 or binding["target_mib"] != expected or not 45056 <= expected <= 73728:
        raise ValueError("Frozen launch cache target changed")
    return dict(binding)


def worker_env(base_env, binding):
    binding = validate_binding(binding)
    if base_env.get("CUDA_VISIBLE_DEVICES") != str(binding["gpu_index"]):
        raise ValueError("Reservation must bind the sole worker GPU")
    env = dict(base_env)
    # Pin only allocation policy, never dtype/attention/math/precision. Native
    # unlimited splitting is necessary to reuse a large startup cache segment.
    env["PYTORCH_CUDA_ALLOC_CONF"] = "backend:native"
    env["PYTORCH_ALLOC_CONF"] = "backend:native"
    env.pop("PYTORCH_NO_CUDA_MEMORY_CACHING", None)
    env[ENVIRONMENT] = json.dumps(binding, sort_keys=True)
    return env


def binding_from_env(environ=None):
    env = os.environ if environ is None else environ
    binding = validate_binding(json.loads(env[ENVIRONMENT]))
    if env.get("CUDA_VISIBLE_DEVICES") != str(binding["gpu_index"]):
        raise ValueError("Reservation/GPU environment mismatch")
    return binding


def preload_cards(plan, sample, *, binding, worker_pid):
    """Count only this pre-reserved worker's exact GPU/PID capacity at reload check.

    The measured sample is never modified. The returned effective free is solely
    an admission quantity; the original free and own contribution are explicit.
    """
    binding = validate_binding(binding)
    try:
        if type(worker_pid) is not int or worker_pid <= 0:
            raise ValueError("Positive exact worker PID required")
        own = [row for row in _rows(sample, "processes", 4)
               if row[0] == binding["gpu_uuid"] and int(row[1]) == worker_pid]
        if len(own) != 1:
            raise ValueError("Exact pre-reserved worker process missing")
        own_memory = _number(own[0][2])
        matches = [row for row in _rows(sample, "gpus", 6)
                   if int(row[0]) == binding["gpu_index"] and row[1] == binding["gpu_uuid"]]
        if len(matches) != 1:
            raise ValueError("Assigned GPU identity changed")
        index, uuid, name, free, total, usage = matches[0]
        free, total, usage = map(_number, (free, total, usage))
        if (int(index) not in plan["gpu_preference"] or "A100" not in name or total < 81920
                or usage > 100 or free > total or own_memory > total
                or own_memory < binding["target_mib"]
                or free + own_memory < binding["target_mib"]):
            raise ValueError("Own reusable startup capacity is not established")
        return [{"index": int(index), "uuid": uuid, "free_mib": free,
                 "effective_own_capacity_mib": free + own_memory,
                 "own_reserved_process_mib": own_memory, "shared": True}]
    except (KeyError, ValueError, TypeError, csv.Error):
        return []


def cuda_snapshot(torch):
    free, total = torch.cuda.mem_get_info()
    return {"allocated_bytes": torch.cuda.memory_allocated(),
            "reserved_bytes": torch.cuda.memory_reserved(),
            "device_free_bytes": free, "device_total_bytes": total}


def _append(output, record):
    path = Path(output) / "native-cache-resources.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps({"version": VERSION, "at": time.time(), **record}) + "\n")


def _task(output, kind):
    write(Path(output) / "task.json", {"task": "own-native-cache-" + kind,
        "kind": kind, "started_at": time.time(), "pid": os.getpid(),
        "new_model_calls": 0, "new_backward_calls": 0})


def fill_cache(torch, target_bytes):
    """Release every temporary tensor before returning, including on OOM.

    Startup uses one splittable segment. A later refill holds small temporary
    chunks only inside this helper; it cannot trap memory during model execution.
    """
    if type(target_bytes) is not int or target_bytes <= 0:
        raise ValueError("Positive integral target required")
    blocks = []
    try:
        if torch.cuda.memory_reserved() == 0:
            blocks.append(torch.empty((target_bytes,), dtype=torch.uint8, device="cuda"))
        else:
            limit = math.ceil(target_bytes / (256 * MIB)) + 1
            for _ in range(limit):
                if torch.cuda.memory_reserved() >= target_bytes:
                    break
                size = min(256 * MIB, target_bytes - torch.cuda.memory_allocated())
                if size <= 0:
                    raise RuntimeError("Allocated memory exceeds reusable cache target")
                blocks.append(torch.empty((size,), dtype=torch.uint8, device="cuda"))
            if torch.cuda.memory_reserved() < target_bytes:
                raise RuntimeError("Bounded cache refill failed to reach frozen target")
    finally:
        blocks.clear()


def reserve_before_load(output, binding, *, torch=None, sleep=time.sleep):
    """Retry only zero-model resource allocation; a model failure is never retried."""
    binding = validate_binding(binding)
    if torch is None:
        import torch
    target = binding["target_mib"] * MIB
    attempt = 0
    while True:
        _task(output, "reservation_wait")
        before = cuda_snapshot(torch)
        # Existing own cache is reusable even after a previous allocation race.
        capacity = before["device_free_bytes"] + before["reserved_bytes"]
        if capacity < target + RESOURCE_POLICY["allocation_margin_mib"] * MIB:
            _append(output, {"stage": "preload_capacity_wait", "binding": binding,
                "new_model_calls": 0, "allocation_attempts": attempt, **before})
            sleep(RESOURCE_POLICY["reservation_poll_seconds"])
            continue
        attempt += 1
        try:
            fill_cache(torch, target)
        except torch.cuda.OutOfMemoryError as error:
            _append(output, {"stage": "preload_allocation_race", "binding": binding,
                "new_model_calls": 0, "allocation_attempts": attempt,
                "error": {"type": type(error).__name__, "message": str(error)},
                **cuda_snapshot(torch)})
            sleep(RESOURCE_POLICY["reservation_poll_seconds"])
            continue
        after = cuda_snapshot(torch)
        if after["allocated_bytes"] != before["allocated_bytes"]:
            raise RuntimeError("Reservation leaked live temporary CUDA tensors")
        record = {"stage": "preload_cache_ready", "binding": binding,
            "allocation_attempts": attempt, "new_model_calls": 0,
            "live_reservation_tensors": 0, "empty_cache_called": False,
            "startup_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "startup_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "startup_peak_counters_reset_before_model_load": True, **after}
        # A synthetic uint8 reservation peak must not masquerade as model tensor
        # compute memory. Reserved peaks still truthfully include the own cache.
        torch.cuda.reset_peak_memory_stats()
        _append(output, record)
        write(Path(output) / "cache-reservation.json", record)
        _task(output, "loading")
        return record


@contextmanager
def native_cache_context(owner, output, binding):
    """Wrap native boundaries without changing their args/results, RNG or count."""
    binding = validate_binding(binding)
    torch, target = owner.torch, binding["target_mib"] * MIB
    overrides = {}

    def check(stage):
        before = cuda_snapshot(torch)
        try:
            if before["reserved_bytes"] < target:
                fill_cache(torch, target)
        except BaseException as error:
            _append(output, {"stage": stage + "_resource_error", "binding": binding,
                "error": {"type": type(error).__name__, "message": str(error)},
                "numerical_call_dispatched": False, **cuda_snapshot(torch)})
            raise
        after = cuda_snapshot(torch)
        if before["allocated_bytes"] != after["allocated_bytes"]:
            raise RuntimeError("Live reservation tensor crossed a native boundary")
        _append(output, {"stage": stage, "binding": binding, "live_reservation_tensors": 0,
            "refill_performed": before["reserved_bytes"] < target, **after})

    def wrap(name, original):
        def observed(*args, **kwargs):
            check("before_" + name)
            try:
                return original(*args, **kwargs)
            finally:
                # Never allocate after a differentiable forward while its graph
                # awaits the unchanged actor/critic backwards.
                _append(output, {"stage": "after_" + name, "binding": binding,
                    **cuda_snapshot(torch)})
        return observed

    try:
        check("owner_loaded")
        for name in ("learning_logprobs", "_generate_tokens"):
            if hasattr(owner, name):
                overrides[name] = (name in owner.__dict__, owner.__dict__.get(name))
                setattr(owner, name, wrap(name, getattr(owner, name)))
        yield
    finally:
        for name, (existed, value) in overrides.items():
            if existed:
                setattr(owner, name, value)
            else:
                delattr(owner, name)
