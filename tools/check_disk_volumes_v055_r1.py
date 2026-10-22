"""Necessary CPU controls plus one read-only live dual-volume observation."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import run_qwen_disk_volumes_v054_r4 as qwen
from proworksim import software_benchmark_disk_volumes_v055_r1 as module
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volume", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    volume_ref = reference(args.volume)
    configured = module.configure(volume_ref)
    identities = configured["identity"]
    primary = module.ROOT / "runs/software-benchmark-v054/formal-queue-r1"
    assert module._placement({"worker_directory": str(primary)}, family="v054", volumes=identities)[0] == "primary"
    assert module._placement({"directory": str(module.SECONDARY_ROOT)}, family="v055", volumes=identities)[0] == "secondary"
    wrong = deepcopy(identities)
    wrong["secondary"]["device"] = wrong["primary"]["device"]
    try:
        module._placement({"directory": str(module.SECONDARY_ROOT)}, family="v055", volumes=wrong)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong actual worker device accepted")
    old = {"rows": [{"slot": {"slot_id": "old"}, "generation": {"fixture_volume": "primary"}}]}
    new = {"rows": [{"slot": {"slot_id": "new-primary"}, "generation": {"fixture_volume": "primary"}},
                    {"slot": {"slot_id": "new-secondary"}, "generation": {"fixture_volume": "secondary"}}],
           "preparation": {"cold": {"worker": {"fixture_volume": "primary"}}}}
    snapshot = {"v054_generations": [{"slot_id": "old", "peak_bytes": 100}],
                "v055_generations": [{"slot_id": "new-primary", "peak_bytes": 200},
                                     {"slot_id": "new-secondary", "peak_bytes": 300}],
                "v055_preparations": [{"instance_id": "cold", "peak_bytes": 50}]}

    def placement(record, **kwargs):
        label = record["fixture_volume"]
        return label, {"device": identities[label]["device"]}

    grouped, errors = module.partition_snapshot(snapshot, old, new, identities, placement=placement)
    assert not errors
    assert grouped["primary"]["active_peak_reserved_bytes"] == 350
    assert grouped["secondary"]["active_peak_reserved_bytes"] == 300
    broken = deepcopy(new)
    broken["rows"][1]["generation"] = {}
    refused, errors = module.partition_snapshot(snapshot, old, broken, identities, placement=placement)
    assert errors and refused["primary"]["active_peak_reserved_bytes"] == 650
    assert refused["secondary"]["active_peak_reserved_bytes"] == 300
    misplaced = deepcopy(new)
    misplaced["preparation"]["cold"]["worker"]["fixture_volume"] = "secondary"
    _, errors = module.partition_snapshot(snapshot, old, misplaced, identities, placement=placement)
    assert errors
    with patch.object(module, "_live_identity", side_effect=ValueError("controlled mount loss")):
        missing = module.shared_disk_snapshot(v054_state=old, v055_state=new)
        assert missing["metadata_error"] and missing["free_bytes"] == 0 and missing["silent_primary_fallback"] is False
    assert qwen.VolumeCoordinator.dispatch_generation is qwen.original.RecoveryCoordinator.dispatch_generation
    delegate = qwen.phase.StageDelegate(module)
    assert delegate.disk_dispatch_lock is module.stages.disk_dispatch_lock
    assert delegate.POLICY is module.stages.POLICY
    with module.disk_dispatch_lock():
        live = module.shared_disk_snapshot(cache={})
    assert live["metadata_error"] is None
    assert live["target_volume"] == "primary"
    assert live["active_peak_reserved_bytes"] == live["volumes"]["primary"]["active_peak_reserved_bytes"]
    result = {"version": module.VERSION, "passed": True, "volume_registration": volume_ref,
        "checks": ["actual_registered_mount_marker_owner_source_and_device_match",
                   "actual_worker_directory_device_routes_primary_and_secondary",
                   "old_and_new_generations_plus_preparation_charge_only_their_volume",
                   "unknown_worker_placement_blocks_instead_of_freeing_reservations",
                   "preparation_cannot_move_to_secondary",
                   "mount_identity_loss_refuses_dispatch_without_primary_fallback",
                   "Qwen_original_dispatcher_lock_and_policy_identity_unchanged"],
        "live_observation": {"observed_utc": live["observed_utc"], "target_volume": live["target_volume"],
            "metadata_error": live["metadata_error"], "volumes": {key: {
                "path": value["path"], "device": value["device"], "free_bytes": value["free_bytes"],
                "active_peak_reserved_bytes": value["active_peak_reserved_bytes"],
                "active_reservation_count": len(value["active_reservations"])} for key, value in live["volumes"].items()}},
        "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
        "services_modified": False, "actual_queue_state_written": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps(write_new(args.output, result)))


if __name__ == "__main__":
    main()
