"""One CPU preparer, at most two unused prepared tasks, no task/model claims."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_resident_pool_v054 import now, read_ref
from .software_benchmark_supervision_v054 import process_identity
from .storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v054-cpu-native-prewarm-v1"
PATH_FIELDS = ("rootfs_environment", "rootfs_manifest", "environment", "qualification")


def validate_prewarm_policy(policy_ref):
    policy = read_ref(policy_ref)
    if (policy.get("version") != VERSION or policy.get("workers") != 1
            or policy.get("maximum_unused_prepared_tasks") != 2
            or policy.get("minimum_disk_free_bytes") != 64 * 1024**3
            or policy.get("model_loading_authorized") is not False
            or policy.get("model_generation_authorized") is not False
            or policy.get("formal_claims_authorized") is not False
            or policy.get("hidden_grader_authorized") is not False
            or policy.get("automatic_retry_failed_preparation") is not False):
        raise ValueError("Only the fixed two-task CPU preparation policy is supported")
    for key in ("root", "cache_root", "queue_state_path", "stdlib"):
        path = Path(policy[key])
        if not path.is_absolute() or not path.resolve().is_relative_to(ROOT / "runs/software-benchmark-v054"):
            raise ValueError("CPU preparation is limited to the fixed project run roots")
    if policy["cache_root"] != str(ROOT / "runs/software-benchmark-v054/native-lazy-cache"):
        raise ValueError("Use the original shared immutable template cache")
    if policy["docker_socket"] != "unix://" + str(ROOT / "runs/software-panel-v053/docker/docker.sock"):
        raise ValueError("CPU preparation must use the existing local image engine")
    for key in ("source_manifest", "slots", "public_tasks", "registry"):
        read_ref(policy[key])
    return policy


def _cache_paths(instance_id, mapping_reference, cache_root):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", instance_id) or instance_id in {".", ".."}:
        raise ValueError("Invalid fixed instance identity")
    root = Path(cache_root).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Unknown native preparation cache")
    return (root / instance_id / mapping_reference["sha256"][:16], root / "locks" / (instance_id + ".lock"))


@contextmanager
def _shared_lock(path):
    # Existing lazy initialization creates this lock before any template. Do
    # not create lock files in the queue's read-only availability check.
    stream = path.open("rb") if path.exists() else None
    try:
        if stream is not None:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
        yield
    finally:
        if stream is not None:
            stream.close()


def _inspect_cache(root, instance_id, mapping_reference):
    path = root / "lazy-preparation.json"
    if path.exists():
        receipt_ref = reference(path)
        receipt = read_ref(receipt_ref)
        if (receipt.get("status") != "qualified" or receipt.get("baseline_mapping") != mapping_reference
                or receipt.get("slot_claimed") is not False or receipt.get("model_calls") != 0
                or any(not isinstance(receipt.get(key), dict) for key in PATH_FIELDS)):
            raise ValueError("Existing native preparation is not this fixed qualified template")
        return {"status": "qualified", "instance_id": instance_id, "receipt": receipt_ref}
    failure = root / "preparation-failure.json"
    if failure.exists():
        return {"status": "failed", "instance_id": instance_id, "failure": reference(failure),
                "reason": "retained_incomplete_native_preparation"}
    if root.exists():
        return {"status": "failed", "instance_id": instance_id,
                "reason": "incomplete_template_without_active_preparer; explicit repair required"}
    return {"status": "pending", "instance_id": instance_id}


def preparation_state(instance_id, *, mapping_reference, cache_root):
    root, lock = _cache_paths(instance_id, mapping_reference, cache_root)
    try:
        with _shared_lock(lock):
            return _inspect_cache(root, instance_id, mapping_reference)
    except BlockingIOError:
        return {"status": "preparing", "instance_id": instance_id, "reason": "native_task_lock_owned"}


def qualified_paths(instance_id, *, mapping_reference, cache_root):
    """Concurrent readers may consume an immutable cache; never initialize it."""
    root, lock = _cache_paths(instance_id, mapping_reference, cache_root)
    with _shared_lock(lock):
        state = _inspect_cache(root, instance_id, mapping_reference)
        if state["status"] != "qualified":
            raise RuntimeError("CPU environment is not qualified before the formal claim")
        receipt = read_ref(state["receipt"])
        for key in PATH_FIELDS:
            checked(receipt[key])  # Exactly one full four-reference verification in this runner.
        return {key: receipt[key]["path"] for key in PATH_FIELDS}


def _events(policy):
    directory = Path(policy["root"]) / "events"
    rows, prior = [], None
    for sequence, path in enumerate(sorted(directory.glob("*.json")), 1):
        item, value = reference(path), json.loads(path.read_text())
        if (path.name != f"{sequence:08d}.json" or value.get("sequence") != sequence
                or value.get("previous_event") != prior or value.get("version") != VERSION):
            raise ValueError("CPU preparation event chain changed")
        rows.append({**value, "event_reference": item})
        prior = item
    return rows


def _append(policy_ref, fields):
    policy = validate_prewarm_policy(policy_ref)
    directory = Path(policy["root"]) / "events"
    directory.mkdir(parents=True, exist_ok=True)
    # The only writer owns prewarm.lock for its entire lifetime.
    rows = _events(policy)
    value = {**fields, "version": VERSION, "policy": policy_ref, "sequence": len(rows) + 1,
             "previous_event": rows[-1]["event_reference"] if rows else None, "utc": now(),
             "model_calls": 0, "GPU_loads": 0, "formal_claims": 0, "hidden_grader_calls": 0}
    pending = directory / (".pending-" + secrets.token_hex(8))
    write_new(pending, value)
    path = directory / f"{value['sequence']:08d}.json"
    os.link(pending, path)
    pending.unlink()
    descriptor = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return reference(path)


def prewarm_health(policy_ref):
    policy = validate_prewarm_policy(policy_ref)
    rows = _events(policy)
    if any(row.get("policy") != policy_ref for row in rows):
        raise ValueError("CPU preparation event belongs to another policy")
    failures = [row["event_reference"] for row in rows if row["event"] == "failed"]
    pending = {}
    for row in rows:
        if row["event"] == "preparing":
            pending[row["instance_id"]] = row
        elif row["event"] in {"prepared", "deferred", "failed"}:
            pending.pop(row["instance_id"], None)
    for row in pending.values():
        try:
            alive = process_identity(row["host_process"]["pid"]) == row["host_process"]
        except (FileNotFoundError, ProcessLookupError):
            alive = False
        if not alive:
            failures.append(row["event_reference"])
    lifecycle = [row for row in rows if row["event"] in {"worker_started", "worker_stopped"}]
    if lifecycle and lifecycle[-1]["event"] == "worker_started":
        worker = lifecycle[-1]
        try:
            alive = process_identity(worker["host_process"]["pid"]) == worker["host_process"]
        except (FileNotFoundError, ProcessLookupError):
            alive = False
        if not alive:
            failures.append(worker["event_reference"])
    return {"status": "failed" if failures else ("running" if pending else "waiting"),
            "failures": failures, "active_preparation": list(pending),
            "prepared_tasks": len({r["instance_id"] for r in rows if r["event"] == "prepared"}),
            "last_event": rows[-1]["event_reference"] if rows else None}


def select_lookahead(rows, events, registry, cache_root, limit=2):
    """At most two prepared tasks with no formal consumer; no score selection."""
    consumed = {row["slot"]["instance_id"] for row in rows
                if row["generation"]["status"] in {"intent", "running", "closed", "technical_unknown"}
                or row["generation"].get("claimed") is True}
    produced = {row["instance_id"] for row in events if row["event"] == "prepared"}
    spare = max(0, limit - len(produced - consumed))
    if not spare:
        return []
    seen, selected = set(), []
    for row in rows:
        instance = row["slot"]["instance_id"]
        if row["generation"]["status"] != "pending" or instance in seen:
            continue
        seen.add(instance)
        state = preparation_state(instance, mapping_reference=registry[instance]["baseline_mapping"],
                                  cache_root=cache_root)
        if state["status"] == "qualified":
            continue
        selected.append({"instance_id": instance, "slot_index": row["slot"]["slot_index"], "state": state})
        if len(selected) >= spare:
            break
    return selected


class Prewarmer:
    def __init__(self, policy_ref):
        self.policy_ref, self.policy = policy_ref, validate_prewarm_policy(policy_ref)
        self.root = Path(self.policy["root"])
        self.registry = {row["instance_id"]: row for row in read_ref(self.policy["registry"])["entries"]}
        self.slots = read_ref(self.policy["slots"])["slots"]

    def wait(self, reason, **detail):
        atomic_write(self.root / "status.json", json_bytes({"status": "waiting", "reason": reason,
            "policy": self.policy_ref, "utc": now(), **detail, "model_calls": 0, "formal_claims": 0}))

    def tick(self):
        health = prewarm_health(self.policy_ref)
        if health["status"] == "failed":
            return False
        queue = json.loads(Path(self.policy["queue_state_path"]).read_text())
        rows = queue["rows"]
        if [row["slot"] for row in rows] != self.slots:
            raise ValueError("CPU lookahead requires the unchanged original ordered 1500 slots")
        candidates = select_lookahead(rows, _events(self.policy), self.registry, self.policy["cache_root"])
        if not candidates:
            self.wait("two_unused_prepared_tasks_or_no_cold_pending_tasks")
            return True
        first = candidates[0]
        instance = first["instance_id"]
        mapping = self.registry[instance]["baseline_mapping"]
        if first["state"]["status"] == "preparing":
            self.wait("existing_native_task_lock_owned", instance_id=instance)
            return True
        if first["state"]["status"] == "failed":
            _append(self.policy_ref, {"event": "failed", "instance_id": instance,
                    "baseline_mapping": mapping, "reason": first["state"], "automatic_retry": False})
            return False
        if shutil.disk_usage(self.policy["cache_root"]).free < self.policy["minimum_disk_free_bytes"]:
            self.wait("original_64GiB_disk_reserve_gate", instance_id=instance)
            return True
        intent = _append(self.policy_ref, {"event": "preparing", "instance_id": instance,
            "baseline_mapping": mapping, "first_pending_slot_index": first["slot_index"],
            "host_process": process_identity(os.getpid()), "automatic_retry": False})
        try:
            from .software_benchmark_native_lazy_v054 import ensure_native_instance
            paths = ensure_native_instance(instance, mapping_reference=mapping,
                cache_root=self.policy["cache_root"], stdlib=self.policy["stdlib"],
                public_tasks_reference=self.policy["public_tasks"], docker_socket=self.policy["docker_socket"])
            state = preparation_state(instance, mapping_reference=mapping, cache_root=self.policy["cache_root"])
            if state["status"] != "qualified":
                raise RuntimeError("CPU preparation returned without its immutable qualified cache")
            _append(self.policy_ref, {"event": "prepared", "instance_id": instance,
                "baseline_mapping": mapping, "intent": intent, "qualified_receipt": state["receipt"],
                "paths": paths, "formal_task_tests_run": 0, "original_initializer_reused": True})
            return True
        except BlockingIOError:
            _append(self.policy_ref, {"event": "deferred", "instance_id": instance,
                "intent": intent, "reason": "native_task_lock_acquired_by_another_preparer_before_execution"})
            return True
        except Exception as error:
            _append(self.policy_ref, {"event": "failed", "instance_id": instance,
                "baseline_mapping": mapping, "intent": intent,
                "error": {"type": type(error).__name__, "message": str(error)}, "automatic_retry": False})
            return False

    def run(self, *, once=False):
        membership = Path("/proc/self/cgroup").read_text().splitlines()
        group = next(line[3:] for line in membership if line.startswith("0::"))
        if not re.fullmatch(r"(?:/system.slice)?/proworksim-v054-prewarm-[a-f0-9]{8}\.service", group):
            raise ValueError("CPU preparer must run in its dedicated bounded system unit")
        cgroup = Path("/sys/fs/cgroup" + group)
        limits = {name: (cgroup / name).read_text().strip()
                  for name in ("cpu.max", "memory.max", "pids.max")}
        quota, period = limits["cpu.max"].split()
        if (quota == "max" or int(quota) > 4 * int(period)
                or limits["memory.max"] != str(16 * 1024**3) or limits["pids.max"] != "16384"):
            raise ValueError("CPU preparation worker limits are not applied by the kernel")
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_write(self.root / "worker-limits.json", json_bytes({"cgroup": group, "kernel_limits": limits,
            "public_initializer_retains_its_original_separate_4CPU_16GiB_slice": True,
            "heavy_export_and_initializer_phases_are_sequential": True, "GPU_loads": 0}))
        with (self.root / "prewarm.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for source in read_ref(self.policy["source_manifest"])["files"]:
                checked(source)
            _append(self.policy_ref, {"event": "worker_started", "instance_id": "__worker__",
                "host_process": process_identity(os.getpid())})
            # Never repeat an interrupted initialization. Its immutable intent
            # makes health failed if the original owner process is gone.
            try:
                while self.tick():
                    if once:
                        _append(self.policy_ref, {"event": "worker_stopped", "instance_id": "__worker__",
                            "reason": "explicit_single_iteration", "returncode": 0})
                        return 0
                    time.sleep(5)
                return 1
            except Exception as error:
                _append(self.policy_ref, {"event": "failed", "instance_id": "__worker__",
                    "error": {"type": type(error).__name__, "message": str(error)}, "automatic_retry": False})
                raise
