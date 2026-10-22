"""Host-only disk reservations for future launches; sealed native solver r3 stays unchanged.

Real free space is reduced by every active job's entire estimated peak, even
when part of that peak is already on disk. This deliberately double-counts used
space to protect against asynchronous clone bursts. It is an admission budget,
not a filesystem quota on unrelated users or arbitrary actor-generated files.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import shutil
import time

from . import software_benchmark_queue_native_host_v055_r3 as previous
from . import software_benchmark_queue_v055 as original
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_queue_v055 import ROOT, load, now
from .storage import digest

VERSION = "v055-native-r3-solver-disk-reservation-host-r4"
GiB = 1024**3
POLICY = {
    "generation_floor_bytes": 100 * GiB,
    "preparation_floor_bytes": 128 * GiB,
    "entry_overhead_bytes": 8192,
    "concurrent_clone_count": 2,
    "generation_workspace_margin_bytes": 8 * GiB,
    "unknown_generation_reservation_bytes": 96 * GiB,
    "cold_preparation_reservation_bytes": 128 * GiB,
    "existing_running_jobs_fully_reserved": True,
    "already_allocated_bytes_deliberately_double_counted": True,
    "unknown_metadata_blocks_new_dispatch": True,
}


def generation_reservation(manifest, policy=POLICY):
    """Bound declared source payload plus block/inode overhead, without a tree walk."""
    size, entries = manifest.get("regular_file_bytes"), manifest.get("entries")
    if type(size) is not int or size < 0 or not isinstance(entries, list):
        raise ValueError("Rootfs size metadata unavailable")
    root_bytes = size + len(entries) * policy["entry_overhead_bytes"]
    return root_bytes * policy["concurrent_clone_count"] + policy["generation_workspace_margin_bytes"]


def admission(free_bytes, reserved_bytes, requested_bytes, *, kind, policy=POLICY):
    if any(type(value) is not int or value < 0 for value in (free_bytes, reserved_bytes, requested_bytes)):
        raise ValueError("Disk capacity arithmetic requires nonnegative integer bytes")
    floor = policy["generation_floor_bytes" if kind == "generation" else "preparation_floor_bytes"]
    remaining = free_bytes - reserved_bytes - requested_bytes
    return {"kind": kind, "free_bytes": free_bytes, "active_peak_reserved_bytes": reserved_bytes,
            "requested_peak_bytes": requested_bytes, "minimum_remaining_bytes": floor,
            "estimated_unreserved_bytes_after_launch": remaining, "admitted": remaining >= floor}


@contextmanager
def disk_dispatch_lock():
    """Both experiment hosts hold this through fresh observations and durable intent."""
    path = ROOT / "runs/software-benchmark-v055/disk-dispatch-r4.lock"
    with path.open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def generation_estimate(instance_id, v055_state, cache):
    readiness = v055_state["preparation"][instance_id]["readiness"]
    if readiness.get("status") != "qualified" or not readiness.get("receipt"):
        raise ValueError("Generation needs a qualified template size manifest")
    receipt_ref = readiness["receipt"]
    key = receipt_ref["sha256"]
    if key not in cache:
        receipt = load(receipt_ref)
        manifest_ref = receipt["rootfs_manifest"]
        path = Path(manifest_ref["path"])
        data = path.read_bytes()
        if len(data) != manifest_ref["bytes"] or digest(data) != manifest_ref["sha256"]:
            raise ValueError("Frozen rootfs size manifest changed")
        manifest = json.loads(data)
        if manifest.get("instance_id") != instance_id:
            raise ValueError("Rootfs size belongs to another task")
        cache[key] = {"peak_bytes": generation_reservation(manifest),
            "rootfs_manifest": manifest_ref, "regular_file_bytes": manifest["regular_file_bytes"],
            "entry_count": len(manifest["entries"])}
    return cache[key]


def shared_disk_snapshot(*, v055_state=None, v054_state=None, cache=None):
    """Call inside disk_dispatch_lock; the other host's durable state is read afresh."""
    cache = {} if cache is None else cache
    generations, preparations, legacy, error = [], [], [], None
    try:
        if v055_state is None:
            v055_state = json.loads((ROOT / "runs/software-benchmark-v055/queue-r1/state.json").read_bytes())
        if v054_state is None:
            v054_state = json.loads((ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json").read_bytes())
        for state, target in ((v055_state, generations), (v054_state, legacy)):
            for row in state["rows"]:
                if row["generation"]["status"] not in {"intent", "running"}:
                    continue
                try:
                    amount = generation_estimate(row["slot"]["instance_id"], v055_state, cache)["peak_bytes"]
                except (OSError, ValueError, KeyError, TypeError):
                    amount = POLICY["unknown_generation_reservation_bytes"]
                target.append({"slot_id": row["slot"]["slot_id"], "peak_bytes": amount})
        for name, record in v055_state["preparation"].items():
            if record.get("worker", {}).get("status") == "running":
                preparations.append({"instance_id": name, "peak_bytes": POLICY["cold_preparation_reservation_bytes"]})
    except (OSError, ValueError, KeyError, TypeError) as caught:
        error = {"type": type(caught).__name__, "message": str(caught)}
    rows = [*generations, *preparations, *legacy]
    return {"observed_utc": now(), "policy": POLICY, "free_bytes": shutil.disk_usage(ROOT).free,
        "active_peak_reserved_bytes": sum(row["peak_bytes"] for row in rows),
        "v055_generations": generations, "v055_preparations": preparations,
        "v054_generations": legacy, "metadata_error": error}


class NativeHostCoordinator(previous.NativeHostCoordinator):
    def __init__(self, revision_ref):
        self.revision_ref, self.revision = revision_ref, load(revision_ref)
        if (self.revision.get("version") != VERSION or self.revision.get("disk_policy") != POLICY
                or self.revision.get("unused_ready_backlog_limit") != 8):
            raise ValueError("Unknown disk reservation host policy")
        for item in self.revision["files"]:
            checked(item)
        predecessor = load(self.revision["predecessor_revision"])
        if (predecessor.get("version") != previous.VERSION
                or predecessor["activation"] != self.revision["activation"]
                or predecessor["original_plan"] != self.revision["original_plan"]):
            raise ValueError("Host r4 must retain exactly the previous scientific activation and plan")
        self.activation = self.activation_ref = None
        self._manifest_costs = {}
        self._generation_disk_closed = self._preparation_disk_closed = False
        self._legacy_reservations = []
        self._reservation_error = None
        original.Coordinator.__init__(self, self.revision["original_plan"])
        self.load_activation()
        history = self.state.setdefault("host_revision_history", [])
        if not history or history[-1]["revision"] != revision_ref:
            history.append({"revision": revision_ref, "adopted_utc": now(),
                            "existing_worker_jobs_unchanged": True, "entered_slots_replayed": 0})
        self.state["active_host_revision"] = revision_ref
        self.state["MATCH_dispatch_hold"] = False
        self.save()

    def template_reservation(self, instance_id):
        return generation_estimate(instance_id, self.state, self._manifest_costs)

    def refresh_preparation(self):
        super().refresh_preparation()
        self._generation_disk_closed = self._preparation_disk_closed = False
        self.state["disk_reservation_status"] = self.disk_snapshot()

    def disk_snapshot(self):
        return shared_disk_snapshot(v055_state=self.state, cache=self._manifest_costs)

    def disk_admitted(self, instance_id, *, kind):
        snapshot = self.disk_snapshot()
        self.state["disk_reservation_status"] = snapshot
        try:
            estimate = (self.template_reservation(instance_id) if kind == "generation" else
                        {"peak_bytes": POLICY["cold_preparation_reservation_bytes"],
                         "basis": "cold_template_32GiB_extraction_limit_plus_export_initialization_and_margin"})
            gate = admission(snapshot["free_bytes"], snapshot["active_peak_reserved_bytes"],
                             estimate["peak_bytes"], kind=kind)
        except (OSError, ValueError, KeyError, TypeError) as error:
            estimate = None
            gate = {"kind": kind, "admitted": False,
                    "metadata_error": {"type": type(error).__name__, "message": str(error)}}
        if snapshot["metadata_error"]:
            gate.update(admitted=False, legacy_observation_error=snapshot["metadata_error"])
        gate.update(instance_id=instance_id, observed_utc=now(), estimate=estimate)
        self.state["last_disk_dispatch_admission"] = gate
        return gate

    def launch(self, row, record, *, kind, request=None):
        if kind != "generation":
            return super().launch(row, record, kind=kind, request=request)
        if self._generation_disk_closed:
            return
        with disk_dispatch_lock():
            gate = self.disk_admitted(row["slot"]["instance_id"], kind=kind)
            if not gate["admitted"]:
                # Parent tick's temporary overcount only lowers dispatch this pass.
                self._generation_disk_closed = True
                return
            record["disk_reservation"] = {"host_revision": self.revision_ref, **gate}
            super().launch(row, record, kind=kind, request=request)

    def launch_preparation(self, instance_id):
        if self._preparation_disk_closed:
            return
        if not previous.prewarm_backlog(self.state)["admit_new_preparation"]:
            return
        with disk_dispatch_lock():
            gate = self.disk_admitted(instance_id, kind="preparation")
            if not gate["admitted"]:
                self._preparation_disk_closed = True
                return
            self.state["preparation"][instance_id]["disk_reservation"] = {"host_revision": self.revision_ref, **gate}
            super().launch_preparation(instance_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--predecessor", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--previous-controller", required=True)
    run = commands.add_parser("run")
    run.add_argument("--revision", required=True, type=Path)
    run.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        predecessor_ref = reference(args.predecessor)
        predecessor = load(predecessor_ref)
        if predecessor.get("version") != previous.VERSION:
            raise ValueError("Require exact qualified r3 predecessor")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ref = write_new(args.output, {"version": VERSION, "created_utc": now(),
            "predecessor_revision": predecessor_ref, "original_plan": predecessor["original_plan"],
            "activation": predecessor["activation"], "disk_policy": POLICY, "unused_ready_backlog_limit": 8,
            "previous_controller_unit": args.previous_controller,
            "files": [reference(__file__), reference(ROOT / "tools/run_deepseek_queue_native_host_v055_r4.py"),
                      *predecessor["files"]],
            "scientific_configuration_unchanged": True, "existing_workers_adopted": True,
            "model_calls": 0, "automatic_model_replay": False})
        print(json.dumps(ref))
        return
    ref = reference(args.revision)
    if ref["sha256"] != args.sha256:
        raise ValueError("Host r4 revision SHA mismatch")
    coordinator = NativeHostCoordinator(ref)
    try:
        while not coordinator.tick():
            time.sleep(5)
    finally:
        coordinator.lease.close()


if __name__ == "__main__":
    main()
