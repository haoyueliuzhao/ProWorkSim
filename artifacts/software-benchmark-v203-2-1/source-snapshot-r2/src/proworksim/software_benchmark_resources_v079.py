"""Eight API startup slots, with the live Qwen queue taking refill priority.

Only the new API coordinator uses this private function namespace. The running
Qwen allocator, per-container ceilings, shared lock and aggregate parent remain
unchanged. A Qwen vacancy stops new API admissions until it has been refilled.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import software_benchmark_resources_v076 as previous
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = "v079-eight-starting-API-pairs-with-Qwen-refill-priority-r1"
GIB = previous.GIB
MAX_STARTING_PAIRS = 8
MAX_API_ACTORS = previous.MAX_API_ACTORS
MAX_QWEN_ACTORS = previous.MAX_QWEN_ACTORS
GLOBAL_ACTOR_LANES = previous.GLOBAL_ACTOR_LANES
CapacityProbe = previous.CapacityProbe
PRIMARY_PROGRESS = (previous.original.ROOT /
    "runs/software-benchmark-v076/adaptive-concurrency-r1/primary-coordinator/progress.json")

_evaluate_eight = private_function(previous.evaluate,
    VERSION=VERSION, MAX_STARTING_PAIRS=MAX_STARTING_PAIRS)


def qwen_refill_target(progress_path=PRIMARY_PROGRESS):
    """Reserve four Qwen places while its work remains, including startup gaps."""
    try:
        value = json.loads(Path(progress_path).read_bytes())
    except (OSError, ValueError, TypeError):
        return MAX_QWEN_ACTORS
    if value.get("failure") is not None:
        return MAX_QWEN_ACTORS
    pending, active = value.get("pending_generation"), value.get("active_generation")
    if (value.get("phase") == "closed" and pending in (None, 0)
            and active in (None, 0)):
        return 0
    if (type(pending) is int and pending >= 0
            and type(active) is int and active >= 0):
        return min(MAX_QWEN_ACTORS, pending + active)
    return MAX_QWEN_ACTORS


def evaluate(active, physical, watchdog, *, pending, qwen_target=MAX_QWEN_ACTORS):
    """Physical headroom stays intact; Qwen vacancies suppress API additions."""
    if type(qwen_target) is not int or not 0 <= qwen_target <= MAX_QWEN_ACTORS:
        raise ValueError("Qwen refill target must be within its original four places")
    result = _evaluate_eight(active, physical, watchdog, pending=pending)
    missing = max(0, qwen_target-result["actual_active_qwen_actors"])
    result.update(qwen_refill_target=qwen_target, qwen_missing_actor_slots=missing,
                  qwen_refill_priority=bool(missing),
                  previous_Qwen_starting_pair_limit=previous.MAX_STARTING_PAIRS,
                  existing_Qwen_tasks_cancelled=False,
                  existing_API_tasks_cancelled=False)
    if missing:
        # Old Qwen must first wait for any already-starting API pairs to finish
        # SDK admission. Never refill those API startup slots while Qwen waits.
        result["additional_pair_slots"] = 0
        result["api_generation_limit"] = result["actual_active_api_actors"]
        result["additional_slots_by_constraint"] = {
            **result["additional_slots_by_constraint"], "Qwen_refill_priority": 0}
    return result


def policy(guard, *, watchdog_guard, capacity_probe=None, authorization_ref=None,
           qwen_target=None):
    """Bind the new API authority and eight-slot batch without mutating v076."""
    if not callable(guard):
        raise TypeError("The new API authority is required")
    target = qwen_refill_target if qwen_target is None else qwen_target
    if not callable(target):
        if type(target) is not int or not 0 <= target <= MAX_QWEN_ACTORS:
            raise ValueError("Qwen refill target must be an integer or callable")
        fixed_target = target
        def target():
            return fixed_target
    namespace = clone_namespace(previous,
        VERSION=VERSION, MAX_STARTING_PAIRS=MAX_STARTING_PAIRS,
        __file__=__file__, __name__=__name__)

    def scoped_guard(operation, **identity):
        if operation != "v076.run":
            raise PermissionError("Unexpected operation in the frozen resource adapter")
        return guard("v079.run", **identity)

    def observed_evaluate(active, physical, watchdog, *, pending):
        return evaluate(active, physical, watchdog, pending=pending, qwen_target=target())

    namespace["evaluate"] = observed_evaluate
    adapted = namespace["policy"](scoped_guard, watchdog_guard=watchdog_guard,
        capacity_probe=capacity_probe, authorization_ref=authorization_ref)
    original_write = adapted._write_claim

    def write_claim(path, value):
        if (value.get("spec", {}).get("role") == "actor"
                and ":DEEPSEEK_" not in value["spec"].get("slot_id", "")):
            raise PermissionError("This startup expansion may create only API actors")
        value["API_starting_pair_limit"] = MAX_STARTING_PAIRS
        value["Qwen_refill_priority"] = True
        return original_write(path, value)

    adapted.claim_resource.__globals__["_write_claim"] = write_claim
    adapted._write_claim = write_claim
    return adapted
