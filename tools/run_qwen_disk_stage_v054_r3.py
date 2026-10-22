"""Qwen host-only disk-stage adapter retaining sealed dispatcher and preparation priority."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path

import run_qwen_preparation_priority_v054_r2 as previous
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base = previous.base
original = previous.original
VERSION = "v054-disk-stage-planning-host-r3"
TOOL = "tools/run_qwen_disk_stage_v054_r3.py"
PREVIOUS_UNIT = "proworksim-v054-formal-queue-preparation-r2.service"
BASE_DISK = previous.shared_disk


class StageDelegate:
    """Keep the original frozen policy identity; new stages are separately sealed."""
    POLICY = BASE_DISK.POLICY

    def __init__(self, stage):
        self.stage = stage

    def __getattr__(self, name):
        return getattr(self.stage, name)

    def generation_estimate(self, instance_id, v055_state, cache):
        # The original Qwen dispatcher does not pass the selected arm here.
        # Keep its conservative two-clone launch estimate. The common active
        # snapshot has row.slot.arm and can safely apply exact per-arm stages.
        return BASE_DISK.generation_estimate(instance_id, v055_state, cache)


def validate_revision(ref, *, initial=False):
    revision = base.load_ref(ref)
    if (revision.get("version") != VERSION or revision.get("queue_root") != str(base.QUEUE)
            or revision.get("previous_controller_unit") != PREVIOUS_UNIT
            or revision.get("original_recovery_adoption_repeated") is not False
            or revision.get("model_reload") is not False
            or revision.get("solver_configuration_changed") is not False
            or not revision.get("stage_module", "").startswith("proworksim.software_benchmark_")):
        raise ValueError("Unknown Qwen disk-stage host revision")
    for row in revision["files"]:
        if initial:
            checked(row["reference"])
        if base.stat_id(row["reference"]["path"]) != row["stat"]:
            raise ValueError("Qwen disk-stage source changed")
    stage_path = base.ROOT / "src" / Path(*revision["stage_module"].split(".")).with_suffix(".py")
    required = {str(base.ROOT / TOOL), str(stage_path)}
    if not required <= {item["reference"]["path"] for item in revision["files"]}:
        raise ValueError("Disk-stage module is not in the sealed source set")
    return revision


def freeze(output, stage_module):
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Disk-stage evidence must stay within Qwen runs")
    stage = importlib.import_module(stage_module)
    state = base.read(base.QUEUE / "state.json")
    prior_ref = state["resource_planning_revision"]
    prior = previous.validate_revision(prior_ref, initial=True)
    refs = [row["reference"] for row in prior["files"]]
    refs += [reference(__file__), reference(stage.__file__)]
    output.parent.mkdir(parents=True, exist_ok=False)
    ref = write_new(output, {"version": VERSION, "created_utc": base.now(), "queue_root": str(base.QUEUE),
        "evidence_root": str(output.parent), "previous_controller_unit": PREVIOUS_UNIT,
        "predecessor_planning": prior_ref, "original_recovery": prior["original_recovery"],
        "original_recovery_adoption": prior["original_recovery_adoption"], "stage_module": stage_module,
        "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in refs],
        "original_dispatcher_and_preparation_priority_reused": True,
        "new_Qwen_launch_reservation_remains_two_clones": True,
        "active_reservations_use_exact_arm_and_validated_stage": True,
        "original_recovery_adoption_repeated": False, "solver_configuration_changed": False,
        "model_reload": False, "entered_generation_replayed": False})
    validate_revision(ref, initial=True)
    return ref


class StageCoordinator(original.RecoveryCoordinator):
    def __init__(self, revision_ref):
        self.stage_ref = revision_ref
        self.stage_revision = validate_revision(revision_ref, initial=True)
        stage = importlib.import_module(self.stage_revision["stage_module"])
        previous.shared_disk = StageDelegate(stage)
        original.disk = previous.PlanningDiskFacade()
        super().__init__(self.stage_revision["original_recovery"])
        if self.system.active(PREVIOUS_UNIT):
            self.lease.close()
            raise ValueError("Previous Qwen host must stop; workers remain active")
        if (self.state["status"] != "running"
                or self.state["resource_recovery"]["adoption"] != self.stage_revision["original_recovery_adoption"]
                or self.state.get("resource_planning_revision") not in
                    [self.stage_revision["predecessor_planning"], revision_ref]):
            self.lease.close()
            raise ValueError("Disk-stage planning cannot replace an unrelated state or shared fault")
        rows_before = json.dumps(self.state["rows"], sort_keys=True)
        path = Path(self.stage_revision["evidence_root"]) / "planning-adoption.json"
        if path.exists():
            proof = reference(path)
            if base.load_ref(proof)["revision"] != revision_ref:
                raise ValueError("Existing disk-stage adoption differs")
        else:
            proof = write_new(path, {"version": VERSION, "utc": base.now(), "revision": revision_ref,
                "predecessor_planning": self.stage_revision["predecessor_planning"],
                "original_resource_recovery": self.state["resource_recovery"],
                "inflight_generations_preserved": [row["slot"]["slot_id"] for row in self.state["rows"]
                    if row["generation"]["status"] in base.ACTIVE],
                "controller_lock_owned": True, "prior_host_stopped": True,
                "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
                "generation_replayed": False, "original_recovery_adoption_repeated": False})
        history = self.state.setdefault("resource_planning_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adoption": proof})
        self.state["resource_planning_revision"] = revision_ref
        if json.dumps(self.state["rows"], sort_keys=True) != rows_before:
            raise AssertionError("Disk-stage adoption changed a formal row")
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.stage_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--stage-module", required=True)
    command = commands.add_parser("run")
    command.add_argument("--revision", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.output, args.stage_module)))
        return 0
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Disk-stage host seal SHA differs")
    coordinator = StageCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
