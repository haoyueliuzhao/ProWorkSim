"""CPU-only adapter control; shared stage arithmetic is controlled separately."""
import importlib
import json
from unittest.mock import patch

import run_qwen_disk_stage_v054_r3 as adapter


def main():
    stage = importlib.import_module("proworksim.software_benchmark_disk_stages_v055_r1")
    delegate = adapter.StageDelegate(stage)
    original_disk = adapter.previous.shared_disk
    old, new = {"rows": []}, {"rows": [], "preparation": {}}
    demand = {"selected_task_ids": ["cold"], "priority_reserve_required": True,
              "consumer_inventory": {}, "running_preparation_count": 0}
    try:
        adapter.previous.shared_disk = delegate
        facade = adapter.previous.PlanningDiskFacade()
        with patch.object(stage, "shared_disk_snapshot", return_value={"metadata_error": None}) as snapshot, \
                patch.object(adapter.previous.priority, "preparation_demand", return_value=demand):
            observed = facade.shared_disk_snapshot(v054_state=old, v055_state=new)
            assert snapshot.call_args.kwargs["v054_state"] is old
            assert snapshot.call_args.kwargs["v055_state"] is new
            assert observed["preparation_priority"] == demand
        with patch.object(adapter.BASE_DISK, "generation_estimate", return_value={"peak_bytes": 123}) as estimate:
            assert facade.generation_estimate("task", new, {}) == {"peak_bytes": 123}
            assert estimate.call_args.args[0] == "task"
        GiB = adapter.BASE_DISK.GiB
        assert not facade.admission(260 * GiB, 0, 20 * GiB, kind="generation")["admitted"]
        facade.demand = {**demand, "priority_reserve_required": False}
        assert facade.admission(160 * GiB, 0, 20 * GiB, kind="generation")["admitted"]
        assert facade.disk_dispatch_lock is stage.disk_dispatch_lock
        assert facade.POLICY is adapter.BASE_DISK.POLICY
        assert adapter.StageCoordinator.dispatch_generation is adapter.original.RecoveryCoordinator.dispatch_generation
    finally:
        adapter.previous.shared_disk = original_disk
    print(json.dumps({"version": adapter.VERSION, "passed": True,
        "checks": ["actual_r2_preparation_facade_delegates_both_states_to_stage_snapshot",
                   "new_Qwen_launch_uses_conservative_two_clone_base_estimate",
                   "preparation_priority_256GiB_and_ordinary_100GiB_floors_preserved",
                   "shared_lock_original_policy_identity_and_dispatcher_preserved"],
        "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
        "services_modified": False, "actual_queue_state_written": False}, indent=2))


if __name__ == "__main__":
    main()
