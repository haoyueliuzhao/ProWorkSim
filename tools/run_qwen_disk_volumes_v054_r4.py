"""Independent Qwen primary-volume host using registered two-volume accounting."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import run_qwen_disk_stage_v054_r3 as phase
from proworksim import software_benchmark_disk_volumes_v055_r1 as volumes
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base, original = phase.base, phase.original
VERSION = "v054-two-volume-planning-host-r4"
TOOL = "tools/run_qwen_disk_volumes_v054_r4.py"
PREVIOUS_UNIT = "proworksim-v054-formal-queue-disk-stage-r3.service"


def validate_revision(ref, *, initial=False):
    revision = base.load_ref(ref)
    if (revision.get("version") != VERSION or revision.get("queue_root") != str(base.QUEUE)
            or revision.get("previous_controller_unit") != PREVIOUS_UNIT
            or revision.get("Qwen_target_volume") != "primary"
            or revision.get("original_recovery_adoption_repeated") is not False
            or revision.get("model_reload") is not False
            or revision.get("inflight_directories_moved") is not False):
        raise ValueError("Unknown Qwen two-volume host revision")
    for row in revision["files"]:
        if initial:
            checked(row["reference"])
        if base.stat_id(row["reference"]["path"]) != row["stat"]:
            raise ValueError("Two-volume host source or registration changed")
    expected = {str(base.ROOT / TOOL), str(Path(volumes.__file__).resolve()), revision["volume_registration"]["path"]}
    if not expected <= {row["reference"]["path"] for row in revision["files"]}:
        raise ValueError("Two-volume source or registration missing from freeze")
    return revision


def freeze(predecessor, volume, output):
    prior_ref, volume_ref = reference(predecessor), reference(volume)
    prior = phase.validate_revision(prior_ref, initial=True)
    volumes.configure(volume_ref)
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Qwen volume evidence must remain within its run root")
    refs = [row["reference"] for row in prior["files"]]
    refs += [reference(__file__), reference(volumes.__file__), volume_ref, base.load_ref(volume_ref)["marker"]]
    output.parent.mkdir(parents=True, exist_ok=False)
    result = write_new(output, {"version": VERSION, "created_utc": base.now(), "queue_root": str(base.QUEUE),
        "evidence_root": str(output.parent), "previous_controller_unit": PREVIOUS_UNIT,
        "predecessor_planning": prior_ref, "original_recovery": prior["original_recovery"],
        "original_recovery_adoption": prior["original_recovery_adoption"],
        "volume_registration": volume_ref, "volume_policy": volumes.VOLUME_POLICY,
        "Qwen_target_volume": "primary", "new_Qwen_launch_two_clone_estimate_retained": True,
        "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in refs],
        "original_dispatcher_and_preparation_priority_reused": True,
        "original_recovery_adoption_repeated": False, "model_reload": False,
        "inflight_directories_moved": False, "entered_generation_replayed": False})
    validate_revision(result, initial=True)
    return result


class VolumeCoordinator(original.RecoveryCoordinator):
    def __init__(self, revision_ref):
        self.volume_revision_ref = revision_ref
        self.volume_revision = validate_revision(revision_ref, initial=True)
        volumes.configure(self.volume_revision["volume_registration"])
        phase.previous.shared_disk = phase.StageDelegate(volumes)
        original.disk = phase.previous.PlanningDiskFacade()
        super().__init__(self.volume_revision["original_recovery"])
        if self.system.active(PREVIOUS_UNIT):
            self.lease.close()
            raise ValueError("Previous Qwen host must stop; worker/model processes remain")
        if (self.state["status"] != "running"
                or self.state["resource_recovery"]["adoption"] != self.volume_revision["original_recovery_adoption"]
                or self.state.get("resource_planning_revision") not in
                    [self.volume_revision["predecessor_planning"], revision_ref]):
            self.lease.close()
            raise ValueError("Volume planning cannot replace an unrelated state or clear a shared fault")
        prior_rows = json.dumps(self.state["rows"], sort_keys=True)
        path = Path(self.volume_revision["evidence_root"]) / "planning-adoption.json"
        if path.exists():
            proof = reference(path)
            if base.load_ref(proof)["revision"] != revision_ref:
                raise ValueError("Existing volume adoption differs")
        else:
            proof = write_new(path, {"version": VERSION, "utc": base.now(), "revision": revision_ref,
                "predecessor_planning": self.volume_revision["predecessor_planning"],
                "volume_registration": self.volume_revision["volume_registration"],
                "original_resource_recovery": self.state["resource_recovery"],
                "inflight_generations_preserved": [row["slot"]["slot_id"] for row in self.state["rows"]
                    if row["generation"]["status"] in base.ACTIVE],
                "controller_lock_owned": True, "previous_host_stopped": True,
                "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
                "generation_replayed": False, "inflight_directories_moved": False})
        history = self.state.setdefault("resource_planning_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adoption": proof})
        self.state["resource_planning_revision"] = revision_ref
        if json.dumps(self.state["rows"], sort_keys=True) != prior_rows:
            raise AssertionError("Volume planning adoption changed a formal row")
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.volume_revision_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--predecessor", type=Path, required=True)
    command.add_argument("--volume", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("run")
    command.add_argument("--revision", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.predecessor, args.volume, args.output)))
        return 0
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Qwen volume revision SHA differs")
    coordinator = VolumeCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
