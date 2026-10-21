"""Reclaim only finished v054+v055 shared native rootfs payloads.

The non-root watcher selects candidates; every finite privileged operation
re-proves nine terminal consumers, service/PID/cgroup quiescence and template
identity while holding the original preparation lock. No service is signalled.
Old receipts, manifests, Docker images and all episode artifacts are retained.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ROOT = Path("/data0/zhuxinrui/projects/ProWorkSim")
CACHE = ROOT / "runs/software-benchmark-v054/native-lazy-cache"
OUTPUT = ROOT / "runs/software-benchmark-v055/cache-reclamation-r1"
UID, GID = 1021, 1022
REGISTRY_SHA = "fb0b7ce800a0c07d1068386ca71b84c85e7e7a47fabaae20098e88b992842b1b"
OLD = ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json"
NEW = ROOT / "runs/software-benchmark-v055/queue-r1/state.json"
VERSION = "v055-nine-consumer-cache-reclamation-r1"
OLD_ARMS = {"REF", "MATCH", "PROJECT"}
NEW_CONDITIONS = {f"{arm}-{mode}" for arm in OLD_ARMS for mode in ("thinking", "nonthinking")}


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def checked(item):
    path = Path(item["path"])
    if not path.is_absolute() or not path.resolve().is_relative_to(ROOT):
        raise ValueError("Evidence must remain in this project")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["sha256"] or len(raw) != item["bytes"]:
        raise ValueError("Immutable evidence reference changed")
    return json.loads(raw)


def write_new(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        if os.geteuid() == 0:
            os.fchown(descriptor, UID, GID)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(Path(path).parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return ref(path)


def scores(row):
    value = row["scores"]
    return list(value.values()) if isinstance(value, dict) else value


def terminal(row):
    return (row["generation"]["status"] in {"closed", "technical_unknown"}
            and all(score["status"] in {"official_report", "technical_unknown"} for score in scores(row))
            and (row["generation"]["status"] != "closed" or bool(scores(row))))


def snapshot():
    return json.loads(OLD.read_bytes()), json.loads(NEW.read_bytes())


def task_rows(old, new, name):
    a = [row for row in old["rows"] if row["slot"]["instance_id"] == name]
    b = [row for row in new["rows"] if row["slot"]["instance_id"] == name]
    if (len(a) != 3 or len(b) != 6 or {r["slot"]["arm"] for r in a} != OLD_ARMS
            or {r["slot"]["condition_id"] for r in b} != NEW_CONDITIONS
            or not all(terminal(row) for row in [*a, *b])):
        raise ValueError("All exact old three and new six consumers must be terminal")
    prep = new.get("preparation", {}).get(name, {})
    if (prep.get("worker", {}).get("status") == "running"
            or prep.get("readiness", {}).get("status") == "preparing"):
        raise ValueError("A current preparer still owns this task")
    return a, b, prep


def projection(a, b, prep):
    # Per-task equality tolerates unrelated queue progress while preventing a
    # consumer transition or a replacement attempt during this operation.
    value = {"v054": a, "v055": b, "preparation": prep}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def system_show(units, manager="user"):
    units = sorted(set(units))
    if not units:
        return {}
    if any(not re.fullmatch(r"proworksim-[A-Za-z0-9_.-]+\.service", u) for u in units):
        raise ValueError("Unexpected service name in immutable evidence")
    command = ["/usr/bin/systemctl"] + (["--user"] if manager == "user" else [])
    command += ["show", "--property=Id,InvocationID,LoadState,ActiveState,MainPID,ControlGroup,KillMode", *units]
    options = {}
    if manager == "user" and os.geteuid() == 0:
        options = {"user": UID, "group": GID, "extra_groups": []}
    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": f"/run/user/{UID}",
             "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{UID}/bus"}, **options)
    found = {}
    for block in result.stdout.strip().split("\n\n"):
        item = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if item.get("Id"):
            found[item["Id"]] = item
    if set(found) != set(units):
        raise RuntimeError("Systemd did not return every requested unit identity")
    return found


def process_identity(pid):
    try:
        raw = Path(f"/proc/{int(pid)}/stat").read_text()
    except FileNotFoundError:
        return None
    return {"pid": int(pid), "start_ticks": int(raw[raw.rfind(")") + 2:].split()[19])}


def populated(group):
    if (not isinstance(group, str) or not group.startswith("/") or ".." in group.split("/")
            or not (group.startswith("/user.slice/") or re.fullmatch(
                r"/proworksimv054ep[a-f0-9]{32}\.slice/proworksim-v054-episode-[a-f0-9]{32}-[a-z]+\.service", group))):
        raise ValueError("Unexpected episode cgroup")
    try:
        events = dict(line.split() for line in (Path("/sys/fs/cgroup" + group) / "cgroup.events").read_text().splitlines())
    except FileNotFoundError:
        return False
    return events.get("populated") != "0"


def quiet_consumers(a, b, prep):
    proofs, scopes, jobs = [], [], set()
    for attempt in [prep.get("worker", {}), *prep.get("attempts", [])]:
        if attempt.get("unit"):
            jobs.add(attempt["unit"])
        if attempt.get("job"):
            jobs.add(checked(attempt["job"])["unit"])
    for cohort, rows in (("v054", a), ("v055", b)):
        for row in rows:
            generation = row["generation"]
            for attempt in generation.get("attempts", []):
                if attempt.get("job"):
                    jobs.add(checked(attempt["job"])["unit"])
                # Old preclaim retries can have separate lifecycle evidence.
                # Conservatively retain these templates for an explicit audit
                # rather than treating the final attempt as proof for all.
                if attempt.get("result") != generation.get("result"):
                    raise ValueError("Additional historical generation attempts require separate audit")
            result = checked(generation["result"])
            if result.get("resource_release", {}).get("released") is not True:
                raise ValueError("Historical resource release is unproven")
            qref = result.get("quiescence")
            if qref is None:
                claim = hashlib.sha256(row["slot"]["slot_id"].encode()).hexdigest()
                qref = ref(ROOT / f"runs/software-benchmark-{cohort}/episode-claims" / claim / "quiescence.json")
            quiet = checked(qref)
            if quiet.get("all_quiet") is not True or quiet.get("errors") or not quiet.get("scopes"):
                raise ValueError("Historical complete writer quiescence is unproven")
            scopes.extend(quiet["scopes"])
            proofs.append({"slot_id": row["slot"]["slot_id"], "generation_status": generation["status"],
                           "result": generation["result"], "quiescence": qref,
                           "score_statuses": [score["status"] for score in scores(row)]})
            jobs.update(item["unit"] for item in [generation, *scores(row)] if item.get("unit"))
    observed = {}
    for manager in ("user", "system"):
        units = [scope["unit"] for scope in scopes if scope.get("manager", "user") == manager]
        if manager == "user":
            units += list(jobs)
        observed[manager] = system_show(units, manager)
    for unit in jobs:
        state = observed["user"][unit]
        if state.get("ActiveState") not in {"inactive", "failed"} or state.get("MainPID") != "0":
            raise RuntimeError("An original generation or grading worker remains alive")
    for scope in scopes:
        state = observed[scope.get("manager", "user")][scope["unit"]]
        collected = state.get("LoadState") == "not-found"
        if (state.get("InvocationID") not in ("", scope["invocation_id"])
                or state.get("ControlGroup") not in ("", scope["cgroup"])
                or (collected and state.get("InvocationID") != "")
                or (not collected and state.get("KillMode") != "control-group")
                or state.get("ActiveState") not in {"inactive", "failed"}
                or state.get("MainPID") != "0" or populated(scope["cgroup"])):
            raise RuntimeError("A registered scope is not currently quiet")
        for key in ("main", "outer_launcher"):
            if process_identity(scope[key]["pid"]) == scope[key]:
                raise RuntimeError("A registered process remains alive")
    return {"nine_consumers": proofs, "current_systemd_observations": observed,
            "registered_scope_count": len(scopes), "all_scope_cgroups_empty": True,
            "all_registered_main_and_outer_launcher_identities_absent": True}


def registry():
    path = ROOT / "config/v054-public-test-registry.json"
    item = ref(path)
    if item["sha256"] != REGISTRY_SHA:
        raise ValueError("Original fixed registry differs")
    return {entry["instance_id"]: entry for entry in checked(item)["entries"]}


def no_mounts_under(path):
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        mounted = Path(line.split()[4].replace("\\040", " ").replace("\\134", "\\"))
        if mounted == path or mounted.is_relative_to(path):
            raise ValueError("A mount exists inside the proposed rootfs payload")


def privileged_one(name, source_sha):
    if os.geteuid() != 0 or os.environ.get("SUDO_UID") != str(UID):
        raise PermissionError("Only the project owner may invoke the finite privileged helper")
    if ref(__file__)["sha256"] != source_sha or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("Collector source seal or instance identity differs")
    def timed_out(signum, frame):
        raise TimeoutError("Finite privileged reclamation exceeded 600 seconds")
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(600)
    mapping = registry()[name]["baseline_mapping"]
    entry = CACHE / name / mapping["sha256"][:16]
    rootfs = entry / "rootfs"
    tombstone = entry / "cache-eviction-v055-r1.json"
    if tombstone.exists():
        return {"instance_id": name, "status": "already_reclaimed", "tombstone": ref(tombstone)}
    # This is the same lock used by ensure_native_instance and qualified_paths.
    lock = os.open(CACHE / "locks" / (name + ".lock"), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old, new = snapshot()
        a, b, prep = task_rows(old, new, name)
        initial_projection = projection(a, b, prep)
        proof = quiet_consumers(a, b, prep)
        receipt_ref = ref(entry / "lazy-preparation.json")
        receipt = checked(receipt_ref)
        if (receipt.get("status") != "qualified" or receipt.get("baseline_mapping") != mapping
                or receipt.get("slot_claimed") is not False or receipt.get("model_calls") != 0):
            raise ValueError("Only the exact qualified zero-model template may be reclaimed")
        manifests = {key: checked(receipt[key]) for key in
                     ("rootfs_environment", "rootfs_manifest", "environment", "qualification")}
        if (Path(manifests["rootfs_manifest"]["prepared_root"]) != rootfs
                or rootfs.resolve() != rootfs or entry.resolve() != entry
                or not rootfs.is_dir() or rootfs.is_symlink() or not shutil.rmtree.avoids_symlink_attacks):
            raise ValueError("Payload must be exactly this template's real rootfs directory")
        before = rootfs.lstat()
        if not stat.S_ISDIR(before.st_mode) or before.st_dev != CACHE.stat().st_dev:
            raise ValueError("Unexpected payload type or device")
        no_mounts_under(rootfs)
        old2, new2 = snapshot()
        if projection(*task_rows(old2, new2, name)) != initial_projection:
            raise RuntimeError("A task consumer changed during final admission")
        intent_path = OUTPUT / (name + ".intent.json")
        if intent_path.exists():
            raise ValueError("An unfinished reclamation intent requires explicit recovery; never blind retry")
        intent = write_new(intent_path, {"version": VERSION, "instance_id": name, "started_utc": now(),
            "source": ref(__file__), "cache_directory": str(entry), "payload": str(rootfs),
            "payload_inode": before.st_ino, "payload_device": before.st_dev,
            "baseline_mapping": mapping, "lazy_preparation": receipt_ref,
            "retained_manifests": {key: receipt[key] for key in manifests},
            "logical_regular_file_bytes": manifests["rootfs_manifest"].get("regular_file_bytes"),
            "rootfs_tar_preserved_if_present": (entry / "rootfs.tar").exists(),
            "terminal_task_projection_sha256": initial_projection, "proof": proof,
            "free_bytes_before": shutil.disk_usage(CACHE).free,
            "only_payload_removed": "rootfs", "delete_Docker_images": False,
            "delete_episode_results_or_patches": False, "new_model_calls": 0})
        current = rootfs.lstat()
        if (current.st_ino, current.st_dev) != (before.st_ino, before.st_dev):
            raise RuntimeError("Payload inode changed after immutable intent")
        shutil.rmtree(rootfs)  # fd-based symlink-safe implementation, no ignore_errors.
        if rootfs.exists() or rootfs.is_symlink():
            raise RuntimeError("Payload removal did not complete")
        result = {"version": VERSION, "instance_id": name, "status": "reclaimed", "completed_utc": now(),
            "intent": intent, "payload_absent": True, "free_bytes_after": shutil.disk_usage(CACHE).free,
            "space_change_not_attributed_exclusively_to_gc": True,
            "historical_qualification_metadata_unchanged": True,
            "future_new_experiments_require_explicit_new_cache_generation": True,
            "existing_v054_v055_consumers_are_all_terminal": True,
            "old_lazy_readers_do_not_interpret_this_tombstone": True}
        tomb = write_new(tombstone, result)
        done = write_new(OUTPUT / (name + ".completed.json"), {**result, "tombstone": tomb})
        return {"instance_id": name, "status": "reclaimed", "completion": done,
                "logical_bytes": manifests["rootfs_manifest"].get("regular_file_bytes")}
    finally:
        os.close(lock)
        signal.alarm(0)


def candidate_ids(old, new):
    groups = defaultdict(list)
    for row in [*old["rows"], *new["rows"]]:
        groups[row["slot"]["instance_id"]].append(row)
    return sorted(name for name, rows in groups.items() if len(rows) == 9 and all(terminal(row) for row in rows))


def cycle(limit, requested=None, expected_source_sha=None):
    old, new = snapshot()
    names = [requested] if requested else candidate_ids(old, new)
    if not requested and (OUTPUT / "status.json").exists():
        cursor = json.loads((OUTPUT / "status.json").read_bytes()).get("cursor_after_instance", "")
        names = [name for name in names if name > cursor] + [name for name in names if name <= cursor]
    source_sha = ref(__file__)["sha256"]
    if expected_source_sha is not None and source_sha != expected_source_sha:
        raise ValueError("The sealed collector source changed after startup")
    results, reclaimed, attempted, last = [], 0, 0, None
    for name in names:
        if attempted >= limit:
            break
        if (OUTPUT / (name + ".completed.json")).exists():
            continue
        if any((OUTPUT / (name + suffix)).exists()
               for suffix in (".failed.json", ".intent.json", ".dispatch-uncertain.json")):
            # Durable exception set: never spin on partial deletes or uncertain
            # helper exits. Their explicit recovery is separate from this loop.
            continue
        attempted += 1
        last = name
        command = ["sudo", "-n", "/usr/bin/python3", "-I", str(Path(__file__).resolve()),
                   "--privileged-one", name, "--source-sha256", source_sha]
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=620)
            result = json.loads(proc.stdout)
        except Exception as error:
            result = {"instance_id": name, "status": "deferred", "automatic_retry": False,
                      "error": {"type": type(error).__name__, "message": str(error)}}
            marker = OUTPUT / (name + ".dispatch-uncertain.json")
            if not marker.exists():
                write_new(marker, {**result, "observed_utc": now(), "source_sha256": source_sha})
        results.append(result)
        reclaimed += result.get("status") == "reclaimed"
    status = {"version": VERSION, "observed_utc": now(), "candidate_count": len(names),
              "attempted_this_cycle": attempted, "reclaimed_this_cycle": reclaimed,
              "cursor_after_instance": last or "", "results": results, "new_model_calls": 0,
              "free_bytes": shutil.disk_usage(CACHE).free}
    temp = OUTPUT / f".status-{os.getpid()}.json"
    temp.write_text(json.dumps(status, indent=2) + "\n")
    os.replace(temp, OUTPUT / "status.json")
    print(json.dumps({key: status[key] for key in ("observed_utc", "candidate_count", "reclaimed_this_cycle", "free_bytes")}), flush=True)


def main():
    if ROOT != EXPECTED_ROOT:
        raise ValueError("This collector belongs only to the fixed ProWorkSim workspace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--privileged-one")
    parser.add_argument("--source-sha256")
    parser.add_argument("--instance")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()
    if args.privileged_one:
        try:
            result = privileged_one(args.privileged_one, args.source_sha256)
        except Exception as error:
            result = {"instance_id": args.privileged_one, "status": "deferred",
                      "error": {"type": type(error).__name__, "message": str(error)}}
            # Preserve the first post-intent failure independently of the
            # watcher's replaceable status; interrupted/partial removal never
            # becomes an automatic retry on a later cycle.
            if re.fullmatch(r"[A-Za-z0-9_.-]+", args.privileged_one):
                intent = OUTPUT / (args.privileged_one + ".intent.json")
                failed = OUTPUT / (args.privileged_one + ".failed.json")
                if intent.exists() and not failed.exists():
                    write_new(failed, {**result, "version": VERSION,
                                      "observed_utc": now(), "intent": ref(intent),
                                      "automatic_retry_authorized": False})
        print(json.dumps(result))
        return
    if (os.geteuid() != UID or not 1 <= args.batch_size <= 4 or (args.watch and args.instance)
            or args.source_sha256 != ref(__file__)["sha256"]):
        raise ValueError("Run the bounded watcher as the project user; batch size 1..4")
    OUTPUT.mkdir(exist_ok=True)
    with (OUTPUT / "collector.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            cycle(args.batch_size, args.instance, args.source_sha256)
            if not args.watch:
                return
            time.sleep(60)


if __name__ == "__main__":
    main()
