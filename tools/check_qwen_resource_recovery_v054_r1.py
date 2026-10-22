"""CPU-only checks for exact exception scope and shared-lock dispatch ordering."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import run_qwen_resource_recovery_v054_r1 as recovery


def main():
    checks = []
    approved = {"allowed_prewarm_failures": [{"sha256": "disk"}, {"sha256": "worker"}],
                "disk_failure_event": {"sha256": "disk"}, "template_failure": {"sha256": "template"}}
    health = {"status": "failed", "active_preparation": [],
              "failures": approved["allowed_prewarm_failures"], "last_event": approved["disk_failure_event"]}
    assert recovery.admitted_prewarm_health(health, approved)["original_failure_preserved"]
    for changed in ({**health, "failures": [*health["failures"], {"sha256": "unreviewed"}]},
                    {**health, "active_preparation": ["another-task"]}, {**health, "last_event": {"sha256": "changed"}}):
        try:
            recovery.admitted_prewarm_health(changed, approved)
        except recovery.fault.SharedIntegrityError:
            pass
        else:
            raise AssertionError("Unknown shared failure was silently deferred")
    checks.append("only_exact_reviewed_prewarm_failure_set_is_deferred")
    proof = {"instance_id": recovery.INSTANCE, "status": "failed", "failure": approved["template_failure"],
             "reason": "retained_incomplete_native_preparation"}
    assert not recovery.prepared_for_dispatch(recovery.INSTANCE, proof, approved)
    for instance, item in (("other", {**proof, "instance_id": "other"}),
                           (recovery.INSTANCE, {**proof, "failure": {"sha256": "changed"}})):
        try:
            recovery.prepared_for_dispatch(instance, item, approved)
        except recovery.fault.SharedIntegrityError:
            pass
        else:
            raise AssertionError("Unreviewed task failure was deferred")
    assert recovery.prepared_for_dispatch("safe", {"instance_id": "safe", "status": "qualified"}, approved)
    checks.append("reviewed_failed_task_stays_unentered_other_failures_remain_hard")

    with tempfile.TemporaryDirectory(prefix="v054-recovery-cpu-") as directory:
        root = Path(directory)
        for mode in ("deny", "allow", "metadata_missing"):
            allow = mode == "allow"
            entered = {"slot": {"slot_id": "entered", "slot_index": 1, "instance_id": "old", "arm": "MATCH"},
                       "generation": {"status": "closed", "attempts": [{"preserved": True}]}, "scores": {}}
            pending = {"slot": {"slot_id": "pending", "slot_index": 2, "instance_id": "safe", "arm": "MATCH"},
                       "generation": {"status": "pending", "attempts": []}, "scores": {}}
            coordinator = object.__new__(recovery.RecoveryCoordinator)
            coordinator.recovery_ref = {"sha256": "recovery"}
            coordinator.recovery = approved
            coordinator.state = {"status": "running", "rows": [entered, pending]}
            coordinator.bindings = {"prewarm_policy": {}, "resident_pool_policy": {}, "capacities": {"MATCH": {}},
                                    "conditions": {"MATCH": {}}, "registry": {}, "scorer_manifest": {}, "authorization": {}}
            coordinator.router_policy = {"old_registration": {}}
            coordinator.activation = coordinator.activation_ref = None
            coordinator.public_entries = {"safe": {"baseline_mapping": {}}}
            coordinator.plan = {"maximum_active_generation_episodes": 1}
            coordinator.root = root / mode
            coordinator._manifest_costs = {}
            coordinator._context = None
            original = deepcopy(entered)
            trace, held = [], {"value": False}
            observed = {"declaration": {"gpu_index": 3, "gpu_uuid": "GPU-test", "mode": "MATCH_PROJECT"},
                        "declaration_reference": {}, "registration": {}, "session_capacity": 1, "active_claims": []}
            pool = {"available": {"gpu3": observed}, "healthy": {"gpu3": observed}, "deferred": []}

            @contextmanager
            def lock():
                assert not held["value"]
                held["value"] = True
                trace.append("lock")
                try:
                    yield
                finally:
                    held["value"] = False
                    trace.append("unlock")

            def snapshot(**kwargs):
                assert held["value"] and kwargs["v054_state"] is coordinator.state
                assert kwargs["v055_state"] == {"fresh_opposite_state": True}
                trace.append("fresh_snapshot")
                return {"free_bytes": 500 * recovery.disk.GiB, "active_peak_reserved_bytes": 0, "metadata_error": None}

            def launch(record, **kwargs):
                assert held["value"]
                trace.append("durable_intent_and_launch")
                assert record["disk_reservation"]["admitted"]
                record["status"] = "running"

            coordinator.start_job = launch
            with patch.object(recovery.disk, "disk_dispatch_lock", lock), \
                    patch.object(recovery.disk, "shared_disk_snapshot", snapshot), \
                    patch.object(recovery.disk, "generation_estimate", return_value={"peak_bytes": recovery.disk.GiB}), \
                    patch.object(recovery.disk, "admission", return_value={"admitted": allow}), \
                    patch.object(recovery.prewarm, "prewarm_health", return_value=health), \
                    patch.object(recovery.prewarm, "preparation_state", return_value={"instance_id": "safe", "status": "qualified"}), \
                    patch("proworksim.software_benchmark_deferred_pool_v054.healthy_residents", return_value=pool), \
                    patch.object(recovery.base, "read", return_value={"fresh_opposite_state": True},
                                 side_effect=OSError("controlled unavailable state") if mode == "metadata_missing" else None), \
                    patch.object(recovery.base, "load_ref", return_value={"resident_id": "retired_gpu6"}), \
                    patch.object(recovery.base, "claim_path", side_effect=lambda slot: root / "no-claims" / slot / "claim.json"), \
                    patch.object(recovery.base, "validate_frozen"), \
                    patch("proworksim.software_benchmark_service_factory_v054.build_service", return_value={}), \
                    patch("proworksim.software_benchmark_slot_factory_v054.build_slot_config", return_value={"path": "fake-config"}):
                coordinator.dispatch_generation()
            assert entered == original
            if mode == "metadata_missing":
                assert pending["generation"] == {"status": "pending", "attempts": []}
                assert coordinator.state["status"] == "running"
                assert coordinator.state["waiting"]["reason"] == "shared_disk_metadata_unavailable"
                assert trace == ["lock", "unlock"]
                checks.append("unavailable_opposite_queue_metadata_waits_without_launch_or_global_pause")
            elif allow:
                assert pending["generation"]["status"] == "running"
                assert trace[:4] == ["lock", "fresh_snapshot", "durable_intent_and_launch", "unlock"]
                checks.append("fresh_two_queue_observation_and_durable_launch_share_lock_entered_row_unchanged")
            else:
                assert pending["generation"] == {"status": "pending", "attempts": []}
                assert not coordinator.root.exists() and "durable_intent_and_launch" not in trace
                checks.append("disk_denial_keeps_pending_slot_without_claim_or_work_directory")
    result = {"version": recovery.VERSION, "passed": True, "checks": checks,
              "model_calls": 0, "GPU_loads": 0, "formal_claims": 0, "services_modified": False,
              "actual_queue_state_written": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
