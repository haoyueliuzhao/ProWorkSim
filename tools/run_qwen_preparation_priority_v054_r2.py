"""Independent Qwen host planning adapter for shared preparation headroom.

The original sealed recovery dispatcher is reused. Only this dedicated host
process binds a disk facade; frozen source files and solver processes are never
modified. The original resource-recovery adoption is retained, not repeated.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import run_qwen_resource_recovery_v054_r1 as original
from proworksim import software_benchmark_preparation_priority_v055_r1 as priority
from proworksim import software_benchmark_queue_native_host_v055_r4 as shared_disk
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base = original.base
VERSION = "v054-shared-preparation-demand-planning-host-r2"
TOOL = "tools/run_qwen_preparation_priority_v054_r2.py"
HELPER = "src/proworksim/software_benchmark_preparation_priority_v055_r1.py"
PREVIOUS_UNIT = "proworksim-v054-formal-queue-resource-r1.service"


class PlanningDiskFacade:
    """Preserve the original lock/estimates; add headroom to generation admission."""
    def __init__(self):
        self.demand = None

    def __getattr__(self, name):
        return getattr(shared_disk, name)

    def shared_disk_snapshot(self, **kwargs):
        snapshot = shared_disk.shared_disk_snapshot(**kwargs)
        self.demand = None
        try:
            # Original recovery dispatch supplies these exact states while
            # holding the same global flock through durable intent + launch.
            old, new = kwargs["v054_state"], kwargs["v055_state"]
            if old is None or new is None:
                raise ValueError("Preparation demand requires both current queue states")
            self.demand = priority.preparation_demand(old, new)
            snapshot["preparation_priority"] = self.demand
        except (OSError, ValueError, KeyError, TypeError) as error:
            snapshot["metadata_error"] = {"type": type(error).__name__, "message": str(error),
                                          "scope": "shared_preparation_demand"}
        return snapshot

    def admission(self, *args, **kwargs):
        gate = shared_disk.admission(*args, **kwargs)
        if self.demand is None:
            gate.update(admitted=False, preparation_priority_error="current demand unavailable")
            return gate
        return priority.priority_admission(gate, self.demand)


def validate_revision(ref, *, initial=False):
    revision = base.load_ref(ref)
    if (revision.get("version") != VERSION or revision.get("queue_root") != str(base.QUEUE)
            or revision.get("previous_controller_unit") != PREVIOUS_UNIT
            or revision.get("original_recovery_adoption_repeated") is not False
            or revision.get("model_reload") is not False
            or revision.get("solver_configuration_changed") is not False):
        raise ValueError("Unknown Qwen preparation planning revision")
    expected = {str(base.ROOT / name) for name in (TOOL, HELPER, original.TOOL, original.GUARD)}
    if {row["reference"]["path"] for row in revision["files"]} != expected:
        raise ValueError("Planning source set differs")
    for row in revision["files"]:
        if initial:
            checked(row["reference"])
        if base.stat_id(row["reference"]["path"]) != row["stat"]:
            raise ValueError("Planning source changed after freeze")
    return revision


def freeze(output):
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Planning evidence must stay within the Qwen run root")
    state = base.read(base.QUEUE / "state.json")
    recovery = state["resource_recovery"]["revision"]
    original.validate_recovery(recovery, initial=True)
    files = [reference(base.ROOT / name) for name in (TOOL, HELPER, original.TOOL, original.GUARD)]
    output.parent.mkdir(parents=True, exist_ok=False)
    ref = write_new(output, {"version": VERSION, "created_utc": base.now(), "queue_root": str(base.QUEUE),
        "evidence_root": str(output.parent), "previous_controller_unit": PREVIOUS_UNIT,
        "original_recovery": recovery, "original_recovery_adoption": state["resource_recovery"]["adoption"],
        "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in files],
        "original_dispatcher_reused": True, "isolated_host_process_disk_facade": True,
        "original_recovery_adoption_repeated": False, "solver_configuration_changed": False,
        "model_reload": False, "entered_generation_replayed": False,
        "shared_dispatch_lock": str(base.ROOT / "runs/software-benchmark-v055/disk-dispatch-r4.lock")})
    validate_revision(ref, initial=True)
    return ref


class PlanningCoordinator(original.RecoveryCoordinator):
    def __init__(self, revision_ref):
        self.planning_ref = revision_ref
        self.planning = validate_revision(revision_ref, initial=True)
        # This module binding exists only inside this new dedicated host
        # process. Parent dispatcher identity and frozen source remain exact.
        original.disk = PlanningDiskFacade()
        super().__init__(self.planning["original_recovery"])
        if self.system.active(self.planning["previous_controller_unit"]):
            self.lease.close()
            raise ValueError("Previous Qwen host must be stopped; workers remain active")
        if (self.state["status"] != "running"
                or self.state["resource_recovery"]["adoption"] != self.planning["original_recovery_adoption"]):
            self.lease.close()
            raise ValueError("Planning cannot clear a new shared fault or replace recovery adoption")
        prior_rows = json.dumps(self.state["rows"], sort_keys=True)
        path = Path(self.planning["evidence_root"]) / "planning-adoption.json"
        if not path.exists():
            proof = write_new(path, {"version": VERSION, "utc": base.now(), "revision": revision_ref,
                "original_resource_recovery": self.state["resource_recovery"],
                "prior_host_stopped": True, "controller_lock_owned": True,
                "inflight_generations_preserved": [row["slot"]["slot_id"] for row in self.state["rows"]
                    if row["generation"]["status"] in base.ACTIVE],
                "model_calls": 0, "model_reloads": 0, "formal_claims": 0,
                "original_recovery_adoption_repeated": False, "generation_replayed": False})
        else:
            proof = reference(path)
            if base.load_ref(proof)["revision"] != revision_ref:
                raise ValueError("Existing planning adoption differs")
        history = self.state.setdefault("resource_planning_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adoption": proof})
        self.state["resource_planning_revision"] = revision_ref
        if json.dumps(self.state["rows"], sort_keys=True) != prior_rows:
            raise AssertionError("Planning adoption changed a formal row")
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.planning_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("run")
    command.add_argument("--revision", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.output)))
        return 0
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Planning seal SHA mismatch")
    coordinator = PlanningCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
