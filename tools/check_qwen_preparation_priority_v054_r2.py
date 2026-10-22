"""One CPU-only control of the actual isolated host facade delegation."""
from copy import deepcopy
import json
from unittest.mock import patch

import run_qwen_preparation_priority_v054_r2 as adapter


def main():
    old, new = {"controlled": "old-current"}, {"controlled": "new-current"}
    original_states = deepcopy((old, new))
    demand = {"selected_task_ids": ["cold"], "priority_reserve_required": True,
              "consumer_inventory": {}, "running_preparation_count": 0}
    facade = adapter.PlanningDiskFacade()
    snapshot = {"free_bytes": 300 * adapter.shared_disk.GiB, "metadata_error": None}
    with patch.object(adapter.shared_disk, "shared_disk_snapshot", return_value=snapshot) as delegated, \
            patch.object(adapter.priority, "preparation_demand", return_value=demand) as demand_call:
        observed = facade.shared_disk_snapshot(v054_state=old, v055_state=new)
        assert delegated.call_args.kwargs["v054_state"] is old
        assert delegated.call_args.kwargs["v055_state"] is new
        assert demand_call.call_args.args == (old, new)
        assert observed["preparation_priority"] == demand
    GiB = adapter.shared_disk.GiB
    denied = facade.admission(260 * GiB, 0, 20 * GiB, kind="generation")
    assert not denied["admitted"] and denied["minimum_remaining_bytes"] == 256 * GiB
    accepted = facade.admission(300 * GiB, 0, 20 * GiB, kind="generation")
    assert accepted["admitted"] and accepted["minimum_remaining_bytes"] == 256 * GiB
    preparation = facade.admission(280 * GiB, 0, 128 * GiB, kind="preparation")
    assert preparation["admitted"] and preparation["minimum_remaining_bytes"] == 128 * GiB
    facade.demand = {**demand, "priority_reserve_required": False}
    ordinary = facade.admission(160 * GiB, 0, 20 * GiB, kind="generation")
    assert ordinary["admitted"] and ordinary["minimum_remaining_bytes"] == 100 * GiB
    facade.demand = None
    assert not facade.admission(500 * GiB, 0, 20 * GiB, kind="generation")["admitted"]
    assert (old, new) == original_states
    assert adapter.PlanningCoordinator.dispatch_generation is adapter.original.RecoveryCoordinator.dispatch_generation
    assert facade.disk_dispatch_lock is adapter.shared_disk.disk_dispatch_lock
    assert facade.POLICY is adapter.shared_disk.POLICY
    print(json.dumps({"version": adapter.VERSION, "passed": True,
        "checks": ["actual_facade_delegates_exact_current_states_and_shared_lock",
                   "cold_demand_changes_only_generation_floor_to_256GiB",
                   "preparation_floor_remains_128GiB_and_no_demand_generation_remains_100GiB",
                   "unavailable_demand_denies_admission",
                   "original_dispatcher_function_and_input_state_are_unchanged"],
        "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
        "services_modified": False, "actual_queue_state_written": False}, indent=2))


if __name__ == "__main__":
    main()
