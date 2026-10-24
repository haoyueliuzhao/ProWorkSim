"""Prepare fixed v056 tasks from existing local images, before any model claim."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import traceback

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
from proworksim.software_benchmark_native_lazy_v054 import ensure_native_instance
from proworksim.software_benchmark_supervision_v054 import process_identity
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runs/software-benchmark-v056/cache-preparation-r1"
CACHE = ROOT / "runs/software-benchmark-v054/v056-budget-cache-r1"
VERSION = "v056-ref-budget-cache-preparation-r1"
COLD_PEAK_BYTES = 128 * 1024**3
FLOOR_BYTES = 128 * 1024**3


def now():
    return datetime.now(timezone.utc).isoformat()


def load_plan(plan_reference):
    plan = json.loads(checked(plan_reference).read_bytes())
    if (plan.get("version") != "v056-ref-budget-plan-r1"
            or plan.get("planned_distinct_tasks") != 50
            or len(plan.get("task_ids", [])) != 50 or len(set(plan["task_ids"])) != 50
            or plan.get("cache_root") != str(CACHE)
            or plan.get("cache_prewarm_ahead_tasks") != 2
            or plan.get("disk_minimum_free_bytes") != FLOOR_BYTES):
        raise ValueError("Unexpected frozen REF budget plan or cache policy")
    registry = json.loads(checked(plan["public_test_registry"]).read_bytes())
    mappings = {row["instance_id"]: row["baseline_mapping"] for row in registry["entries"]}
    if not set(plan["task_ids"]) <= set(mappings):
        raise ValueError("Every selected task needs its existing pinned baseline mapping")
    return plan, mappings


def stat_identity(path):
    value = Path(path).stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def status_for(plan_reference, plan, mappings, instance_id):
    if instance_id not in plan["task_ids"]:
        raise ValueError("Task is outside the frozen panel")
    directory = STATE / instance_id
    ready = directory / "qualified.json"
    failure = directory / "failure.json"
    if ready.exists():
        body = json.loads(ready.read_bytes())
        if body.get("plan") != plan_reference or body.get("baseline_mapping") != mappings[instance_id]:
            raise ValueError("Preparation belongs to another panel or task mapping")
        rootfs = Path(body["rootfs"])
        if not rootfs.is_dir() or rootfs.is_symlink():
            return {"status": "evicted", "instance_id": instance_id, "receipt": reference(ready)}
        for key, identity in body["metadata_stat_identities"].items():
            if stat_identity(key) != identity:
                raise ValueError("Prepared environment metadata changed after qualification")
        return {"status": "qualified", "instance_id": instance_id,
                "receipt": body["preparation_receipt"], "v056_receipt": reference(ready),
                **body["paths"]}
    if failure.exists():
        return {"status": "failed", "instance_id": instance_id, "failure": reference(failure)}
    if (directory / "started.json").exists():
        return {"status": "preparing_or_interrupted", "instance_id": instance_id,
                "started": reference(directory / "started.json"), "automatic_retry": False}
    return {"status": "pending", "instance_id": instance_id}


@contextmanager
def prepare_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "preparer.lock").open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def prepare_one(plan_reference, plan, mappings, instance_id, *, active_reserved_bytes=0):
    if type(active_reserved_bytes) is not int or active_reserved_bytes < 0:
        raise ValueError("Explicit nonnegative concurrent disk reservation required")
    try:
        with prepare_lock():
            previous = status_for(plan_reference, plan, mappings, instance_id)
            if previous["status"] != "pending":
                return previous
            free = shutil.disk_usage(ROOT).free
            gate = {"free_bytes": free, "other_active_reserved_bytes": active_reserved_bytes,
                    "cold_preparation_peak_bytes": COLD_PEAK_BYTES,
                    "minimum_remaining_bytes": FLOOR_BYTES,
                    "admitted": free - active_reserved_bytes - COLD_PEAK_BYTES >= FLOOR_BYTES}
            if not gate["admitted"]:
                return {"status": "resource_wait", "instance_id": instance_id, "disk_admission": gate}
            directory = STATE / instance_id
            directory.mkdir(exist_ok=False)
            mapping = mappings[instance_id]
            checked(mapping)
            # Old tombstones and qualifications never supply this new generation's payload.
            destination = CACHE / instance_id / mapping["sha256"][:16]
            if destination.exists():
                raise ValueError("Unexpected pre-existing v056 payload without its preparation intent")
            started = write_new(directory / "started.json", {
                "version": VERSION, "utc": now(), "plan": plan_reference,
                "instance_id": instance_id, "baseline_mapping": mapping,
                "cache_generation": str(CACHE), "disk_admission": gate,
                "host_process": process_identity(os.getpid()),
                "maximum_parallel_preparers": 1, "model_calls": 0,
                "old_cache_payload_or_workspace_reused": False})
            reservation = STATE / "active-reservation.json"
            atomic_write(reservation, json_bytes({"active": True, "started": started,
                "instance_id": instance_id, "peak_bytes": COLD_PEAK_BYTES,
                "host_process": process_identity(os.getpid())}))
            try:
                socket = plan["docker_socket"]
                if not socket.startswith("unix://"):
                    socket = "unix://" + socket
                paths = ensure_native_instance(instance_id, mapping_reference=mapping,
                    cache_root=CACHE, stdlib=plan["stdlib"],
                    public_tasks_reference=plan["public_tasks"], docker_socket=socket)
                receipt = reference(destination / "lazy-preparation.json")
                body = json.loads(checked(receipt).read_bytes())
                manifest = json.loads(checked(body["rootfs_manifest"]).read_bytes())
                rootfs = Path(manifest["prepared_root"])
                if not rootfs.is_dir() or rootfs != destination / "rootfs":
                    raise ValueError("Qualified receipt lacks its actual new-generation payload")
                metadata = [row["path"] for key, row in body.items()
                            if key in {"rootfs_environment", "rootfs_manifest", "environment", "qualification"}]
                metadata.append(receipt["path"])
                write_new(directory / "qualified.json", {
                    "version": VERSION, "utc": now(), "plan": plan_reference,
                    "status": "qualified", "instance_id": instance_id,
                    "baseline_mapping": mapping, "preparation_receipt": receipt,
                    "rootfs": str(rootfs), "paths": paths,
                    "metadata_stat_identities": {p: stat_identity(p) for p in metadata},
                    "cold_preparation_intent": started, "model_calls": 0,
                    "benchmark_tests_run": 0, "hidden_grader_called": False,
                    "actual_public_initialization_passed": True,
                    "immutable_images_and_prior_mechanism_evidence_reused": True})
            except BaseException as error:
                write_new(directory / "failure.json", {"version": VERSION, "utc": now(),
                    "plan": plan_reference, "instance_id": instance_id, "status": "failed",
                    "error_type": type(error).__name__, "error": str(error),
                    "traceback": traceback.format_exc(), "model_calls": 0,
                    "entered_formal_slot": False, "automatic_retry": False})
            finally:
                atomic_write(reservation, json_bytes({"active": False, "started": started,
                    "instance_id": instance_id, "peak_bytes": 0, "closed_utc": now()}))
            return status_for(plan_reference, plan, mappings, instance_id)
    except BlockingIOError:
        return {"status": "resource_wait", "instance_id": instance_id,
                "reason": "another_preparer_holds_the_exclusive_lock"}


def _process_gone(identity):
    if (not isinstance(identity, dict) or type(identity.get("pid")) is not int
            or type(identity.get("start_ticks")) is not int):
        raise ValueError("Task worker lacks its exact process identity")
    try:
        current = process_identity(identity["pid"])
    except FileNotFoundError:
        return True
    return current != identity


def _cgroup_quiet(cgroup):
    if (not isinstance(cgroup, str) or ".." in cgroup.split("/")
            or not (cgroup.startswith("/user.slice/")
                    or re.fullmatch(r"/proworksimv054ep[a-f0-9]{32}\.slice(?:/[^/]+)?", cgroup))):
        raise ValueError("Unknown task cgroup identity")
    events = Path("/sys/fs/cgroup" + cgroup) / "cgroup.events"
    try:
        fields = dict(line.split() for line in events.read_text().splitlines())
    except FileNotFoundError:
        return True
    return fields.get("populated") == "0"


def reclaim_evidence(plan_reference, plan, state, instance_id):
    """Only all four final consumers, with live process checks, can release a template."""
    if instance_id not in plan["task_ids"] or state.get("version") != "v056-ref-budget-queue-r1":
        raise ValueError("Unknown task or queue version")
    binding = json.loads(checked(state["binding"]).read_bytes())
    if binding.get("plan") != plan_reference:
        raise ValueError("Queue snapshot belongs to another frozen plan")
    slots = json.loads(checked(plan["slots"]).read_bytes())["slots"]
    expected = {row["slot_id"]: row for row in slots if row["instance_id"] == instance_id}
    rows = [row for row in state["rows"] if row["slot"]["instance_id"] == instance_id]
    if len(expected) != 4 or len(rows) != 4 or {r["slot"]["slot_id"] for r in rows} != set(expected):
        raise ValueError("Reclamation requires the exact four fixed budget conditions")
    evidence = []
    jobs = state["jobs"]
    for row in rows:
        if row["slot"] != expected[row["slot"]["slot_id"]]:
            raise ValueError("Task condition identity differs from the fixed slots")
        generation, scoring = row["generation"], row["score"]
        if generation.get("status") not in {"closed", "deferred"} or generation.get("quiescent") is not True:
            raise ValueError("A generation is unfinished or lacks writer-quiescence evidence")
        if scoring.get("status") not in {"official_report", "deferred", "not_applicable"}:
            raise ValueError("A scorer still needs this task lifecycle")
        if scoring.get("status") != "not_applicable" and scoring.get("quiescent") is not True:
            raise ValueError("A scorer lacks complete shutdown evidence")
        result = json.loads(checked(generation["result"]).read_bytes())
        release = result.get("resource_release", {})
        if (result.get("slot_id") != row["slot"]["slot_id"]
                or result.get("cleanup_errors") or result.get("exception_closure_error")
                or release.get("released") is not True or release.get("populated") is not False
                or not _cgroup_quiet("/" + release["slice"])):
            raise ValueError("Actor resource slice or exception shutdown is not proved quiet")
        for scope in result.get("finally_stopped_scopes", []):
            if scope.get("populated") is not False or not _cgroup_quiet(scope["cgroup"]):
                raise ValueError("A recorded actor/controller scope is still populated")
        job_evidence = []
        for stage in (generation, scoring):
            job_id = stage.get("job_id")
            if job_id is None:
                if stage is scoring and stage.get("status") == "not_applicable":
                    continue
                raise ValueError("Consumer lacks a complete outer-worker identity")
            job = jobs[job_id]
            if (job.get("instance_id") != instance_id or job.get("slot_id") != row["slot"]["slot_id"]
                    or job.get("status") not in {"completed", "deferred"}
                    or not _process_gone(job["host_process"])):
                raise ValueError("An outer worker remains active or has unknown identity")
            if job.get("cgroup") is not None and not _cgroup_quiet(job["cgroup"]):
                raise ValueError("An outer worker cgroup remains active")
            job_evidence.append({"job_id": job_id, "host_process": job["host_process"], "gone": True})
        if scoring.get("receipt"):
            checked(scoring["receipt"])
        evidence.append({"slot_id": row["slot"]["slot_id"], "generation_status": generation["status"],
            "score_status": scoring["status"], "generation_result": generation["result"],
            "scoring_receipt": scoring.get("receipt"), "resource_release": release, "jobs": job_evidence})
    return evidence


def reclaim_one(plan_reference, plan, mappings, state_reference, instance_id):
    result = {"version": VERSION, "instance_id": instance_id, "status": "deferred",
              "plan": plan_reference, "queue_snapshot": state_reference}
    try:
        if instance_id not in plan["task_ids"]:
            raise ValueError("Task is outside the frozen panel")
        with prepare_lock():
            task_lock = CACHE / "locks" / (instance_id + ".lock")
            if not task_lock.is_file():
                raise ValueError("Original new-generation task lock is absent")
            with task_lock.open("r+b") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                directory = STATE / instance_id
                completed = directory / "reclaimed.json"
                if completed.exists():
                    return {**result, "status": "already_reclaimed", "receipt": reference(completed)}
                state = json.loads(checked(state_reference).read_bytes())
                consumers = reclaim_evidence(plan_reference, plan, state, instance_id)
                ready = json.loads((directory / "qualified.json").read_bytes())
                if ready["plan"] != plan_reference or ready["baseline_mapping"] != mappings[instance_id]:
                    raise ValueError("Preparation identity differs from the four completed consumers")
                source = json.loads(checked(ready["preparation_receipt"]).read_bytes())
                manifest = json.loads(checked(source["rootfs_manifest"]).read_bytes())
                rootfs = CACHE / instance_id / mappings[instance_id]["sha256"][:16] / "rootfs"
                if (rootfs.is_symlink() or not rootfs.is_dir() or rootfs.resolve() != rootfs
                        or manifest.get("prepared_root") != str(rootfs)
                        or ready.get("rootfs") != str(rootfs)
                        or manifest.get("baseline_mapping") != mappings[instance_id]):
                    raise ValueError("Only the exact qualified new-generation rootfs may be removed")
                for line in Path("/proc/self/mountinfo").read_text().splitlines():
                    mount = line.split()[4].replace("\\040", " ").replace("\\134", "\\")
                    if mount == str(rootfs) or mount.startswith(str(rootfs) + "/"):
                        raise ValueError("Mounted rootfs cannot be reclaimed")
                identity = stat_identity(rootfs)
                intent = directory / "reclaim-intent.json"
                if intent.exists():
                    raise ValueError("A prior deletion intent requires independent reconciliation")
                intent_ref = write_new(intent, {**result, "utc": now(), "status": "deletion_intent",
                    "rootfs": str(rootfs), "rootfs_stat_identity": identity,
                    "preparation_receipt": ready["preparation_receipt"], "consumers": consumers,
                    "preparer_lock_held": True, "task_cache_lock_held": True,
                    "source": reference(__file__), "only_rootfs_deleted": True})
                if stat_identity(rootfs) != identity:
                    raise ValueError("Rootfs identity changed before deletion")
                subprocess.run(["sudo", "-n", "/bin/rm", "-rf", "--", str(rootfs)],
                               check=True, capture_output=True, text=True, timeout=300)
                if rootfs.exists() or rootfs.is_symlink():
                    raise ValueError("Rootfs removal did not complete")
                tombstone = write_new(rootfs.parent / "cache-eviction-v056-r1.json", {
                    "version": "v056-ref-budget-template-eviction-r1", "utc": now(),
                    "instance_id": instance_id, "rootfs": str(rootfs), "intent": intent_ref,
                    "payload_absent": True, "qualification_metadata_preserved": True,
                    "experiments_candidates_scores_models_images_preserved": True})
                receipt = write_new(completed, {**result, "utc": now(), "status": "reclaimed",
                    "intent": intent_ref, "tombstone": tombstone})
                return {**result, "status": "reclaimed", "receipt": receipt}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return {**result, "reason": str(error), "error_type": type(error).__name__,
                "other_task_dispatch_blocked": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--instance-id")
    parser.add_argument("--max-tasks", type=int, default=2)
    parser.add_argument("--active-reserved-bytes", type=int, default=0)
    parser.add_argument("--status-only", action="store_true")
    parser.add_argument("--reclaim", action="store_true")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--state-sha256")
    args = parser.parse_args()
    plan_reference = reference(args.plan)
    if plan_reference["sha256"] != args.plan_sha256:
        raise ValueError("Frozen plan identity changed")
    plan, mappings = load_plan(plan_reference)
    if args.reclaim:
        if not args.instance_id or args.state is None or not args.state_sha256 or args.status_only:
            raise ValueError("Reclaim requires one task and its immutable final queue snapshot")
        state_ref = reference(args.state)
        if state_ref["sha256"] != args.state_sha256:
            raise ValueError("Queue snapshot identity differs")
        print(json.dumps(reclaim_one(plan_reference, plan, mappings, state_ref, args.instance_id),
                         ensure_ascii=False), flush=True)
        return 0
    if not 1 <= args.max_tasks <= plan["cache_prewarm_ahead_tasks"]:
        raise ValueError("Prepare at most the fixed two-task lookahead per invocation")
    selected = [args.instance_id] if args.instance_id else plan["task_ids"][:args.max_tasks]
    results = []
    for instance in selected:
        body = (status_for(plan_reference, plan, mappings, instance) if args.status_only else
                prepare_one(plan_reference, plan, mappings, instance,
                            active_reserved_bytes=args.active_reserved_bytes))
        results.append(body)
        print(json.dumps(body, ensure_ascii=False), flush=True)
    if any(row["status"] in {"failed", "preparing_or_interrupted", "evicted"} for row in results):
        return 1
    return 75 if any(row["status"] == "resource_wait" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
