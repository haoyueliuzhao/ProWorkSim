"""Independent host binding for the sealed REF-generation-terminal pool overlay.

Only newly launched original-source episode workers receive the overlay. The
GPU6 kernel snapshot route, live workers, slot configuration and scoring remain
owned by their existing frozen dispatch paths.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import run_qwen_disk_volumes_v054_r4 as previous
from proworksim import software_benchmark_ref_handoff_pool_v054_r1 as pool_overlay
from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

base = previous.base
VERSION = "v054-ref-handoff-host-r5"
TOOL = "tools/run_qwen_ref_handoff_v054_r5.py"
EPISODE_TOOL = "tools/run_benchmark_episode_ref_handoff_v054_r1.py"
PREVIOUS_UNIT = "proworksim-v054-formal-queue-disk-volumes-r4.service"


def validate_revision(ref, *, initial=False):
    revision = base.load_ref(ref)
    if (revision.get("version") != VERSION
            or revision.get("queue_root") != str(base.QUEUE)
            or revision.get("previous_controller_unit") != PREVIOUS_UNIT
            or revision.get("episode_wrapper") != str(base.ROOT / EPISODE_TOOL)
            or revision.get("model_reload_at_host_adoption") is not False
            or revision.get("inflight_worker_modified") is not False
            or revision.get("scientific_configuration_changed") is not False
            or revision.get("entered_generation_replayed") is not False
            or revision.get("GPU6_snapshot_route_changed") is not False):
        raise ValueError("Unknown REF handoff host revision")
    expected = {str(base.ROOT / name) for name in (TOOL, EPISODE_TOOL)}
    expected |= {str(Path(pool_overlay.__file__).resolve()), revision["pool_overlay"]["path"],
                 revision["predecessor_planning"]["path"]}
    if not expected <= {row["reference"]["path"] for row in revision["files"]}:
        raise ValueError("REF handoff host lacks its frozen overlay/worker/source identity")
    for row in revision["files"]:
        if initial:
            checked(row["reference"])
        if base.stat_id(row["reference"]["path"]) != row["stat"]:
            raise ValueError("REF handoff host source or overlay changed after freeze")
    return revision


def freeze(predecessor, overlay, output):
    predecessor_ref, overlay_ref = reference(predecessor), reference(overlay)
    prior = previous.validate_revision(predecessor_ref, initial=True)
    pool_overlay.install(overlay_ref)
    overlay_body = base.load_ref(overlay_ref)
    state = base.read(base.QUEUE / "state.json")
    bindings = base.load_ref(state["bindings"])
    if (state.get("resource_planning_revision") != predecessor_ref
            or bindings["resident_pool_policy"] != overlay_body["target_pool_policy"]):
        raise ValueError("Handoff overlay is not bound to the current Qwen pool/planning revision")
    output = Path(output).resolve()
    if not output.parent.is_relative_to(base.ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Handoff revision must stay in Qwen run evidence")
    refs = [row["reference"] for row in prior["files"]]
    refs += [row["reference"] for row in overlay_body["files"]]
    refs += [predecessor_ref, overlay_ref, reference(base.ROOT / TOOL),
             reference(base.ROOT / EPISODE_TOOL), reference(pool_overlay.__file__)]
    refs = list({item["path"]: item for item in refs}.values())
    output.parent.mkdir(parents=True, exist_ok=False)
    result = write_new(output, {
        "version": VERSION, "created_utc": base.now(), "queue_root": str(base.QUEUE),
        "evidence_root": str(output.parent), "previous_controller_unit": PREVIOUS_UNIT,
        "predecessor_planning": predecessor_ref, "pool_overlay": overlay_ref,
        "episode_wrapper": str(base.ROOT / EPISODE_TOOL),
        "files": [{"reference": item, "stat": base.stat_id(item["path"])} for item in refs],
        "model_reload_at_host_adoption": False, "inflight_worker_modified": False,
        "scientific_configuration_changed": False, "entered_generation_replayed": False,
        "GPU6_snapshot_route_changed": False, "scoring_route_changed": False,
        "resource_planning_revision_preserved": True,
        "only_exact_original_generation_entry_wrapped": True,
    })
    validate_revision(result, initial=True)
    return result


def route_new_worker(argv, *, kind, revision_ref, revision):
    """Match the exact original entry; preserve env-wrapped GPU6 argv verbatim."""
    source = [str(base.HOST_PYTHON), str(base.ROOT / "tools/run_benchmark_episode_v054.py")]
    if kind != "generation" or list(argv[:2]) != source:
        return list(argv), False
    overlay = revision["pool_overlay"]
    return [source[0], revision["episode_wrapper"],
            "--host-revision", revision_ref["path"], "--host-sha256", revision_ref["sha256"],
            "--overlay", overlay["path"], "--overlay-sha256", overlay["sha256"],
            "--", *argv[2:]], True


class HandoffCoordinator(previous.VolumeCoordinator):
    def __init__(self, revision_ref):
        self.handoff_revision_ref = revision_ref
        self.handoff_revision = validate_revision(revision_ref, initial=True)
        # Stop only the old coordinator during root-controlled deployment.
        # This check precedes even the parent's idempotent adoption/save.
        if base.Systemd().active(PREVIOUS_UNIT):
            raise ValueError("Previous Qwen controller must stop; workers and models remain")
        pool_overlay.install(self.handoff_revision["pool_overlay"])
        super().__init__(self.handoff_revision["predecessor_planning"])
        existing = self.state.get("ref_handoff_host")
        if existing is not None and existing.get("revision") != revision_ref:
            self.lease.close()
            raise ValueError("Another handoff host already owns this queue")
        rows_before = json.dumps(self.state["rows"], sort_keys=True)
        path = Path(self.handoff_revision["evidence_root"]) / "host-adoption.json"
        if path.exists():
            proof = reference(path)
            if base.load_ref(proof)["revision"] != revision_ref:
                self.lease.close()
                raise ValueError("Existing handoff adoption has a different revision")
        else:
            proof = write_new(path, {
                "version": VERSION, "utc": base.now(), "revision": revision_ref,
                "pool_overlay": self.handoff_revision["pool_overlay"],
                "resource_planning_revision": self.state["resource_planning_revision"],
                "inflight_generations_preserved": [row["slot"]["slot_id"] for row in self.state["rows"]
                    if row["generation"]["status"] in base.ACTIVE],
                "controller_lock_owned": True, "previous_host_stopped": True,
                "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
                "generation_replayed": False, "worker_processes_signalled": False,
            })
        self.state["ref_handoff_host"] = {"revision": revision_ref, "adoption": proof}
        if json.dumps(self.state["rows"], sort_keys=True) != rows_before:
            raise AssertionError("Handoff host adoption changed a formal row")
        self.save()

    def validate_state(self):
        super().validate_state()
        validate_revision(self.handoff_revision_ref)

    def start_job(self, record, *, kind, directory, argv):
        routed, changed = route_new_worker(argv, kind=kind,
            revision_ref=self.handoff_revision_ref, revision=self.handoff_revision)
        if changed:
            record["ref_handoff_host_revision"] = self.handoff_revision_ref
            record["ref_handoff_pool_overlay"] = self.handoff_revision["pool_overlay"]
        return super().start_job(record, kind=kind, directory=directory, argv=routed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    command = commands.add_parser("freeze")
    command.add_argument("--predecessor", type=Path, required=True)
    command.add_argument("--overlay", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("run")
    command.add_argument("--revision", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.operation == "freeze":
        print(json.dumps(freeze(args.predecessor, args.overlay, args.output)))
        return 0
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Handoff host revision SHA differs")
    coordinator = HandoffCoordinator(ref)
    try:
        return coordinator.run()
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
