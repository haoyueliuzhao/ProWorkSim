"""Retire a fixed, completed SWE-smith image-download batch, never Docker images."""
from contextlib import ExitStack
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import reclaim_loaded_image_layers_v054 as common

ROOT = common.ROOT
BASE = ROOT / "runs/software-panel-v053"
GROUPS = ("prefetch-ranks09-24-v1", "prefetch-ranks25-32-v1", "parallel-images")
OUTPUT = BASE / "historical-download-retirement-r1"
VERSION = "v053-completed-image-download-retirement-r1"


def legacy_stat(identity):
    return {"device": identity["dev"], "inode": identity["ino"], "bytes": identity["size"],
            "mtime_ns": identity["mtime_ns"], "ctime_ns": identity["ctime_ns"]}


def consumers(selected):
    found = []
    known = {"transfer-layers.py", "load-ready-batch.py", "load-ready-watcher.py",
             "build-standard-archive.py", "image-prefetch-supervisor.py"}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / "cmdline").read_bytes().decode(errors="replace").split("\0")
            scoped = any(str(BASE) in arg for arg in args)
            if not scoped:
                try:
                    scoped = (proc / "cwd").resolve().is_relative_to(BASE)
                except (OSError, RuntimeError):
                    scoped = False
            if scoped and any(Path(arg).name in known or (arg.endswith(".py") and
                    ("download" in Path(arg).name or "prefetch" in Path(arg).name)) for arg in args):
                found.append({"pid": int(proc.name), "kind": "legacy_downloader_or_loader"})
            # Only this user's processes or explicitly project-scoped commands.
            if not scoped and proc.stat().st_uid != os.getuid():
                continue
            for fd in (proc / "fd").iterdir():
                try:
                    target = os.readlink(fd)
                except OSError:
                    continue
                if target in selected:
                    found.append({"pid": int(proc.name), "kind": "open_payload", "path": target})
        except (OSError, RuntimeError):
            continue
    if found:
        raise ValueError("Historical payload still has a live consumer: " + str(found[:10]))
    return []


def images():
    receipts, ids = [], set()
    for group in GROUPS:
        path = BASE / group / "docker-load-receipt.json"
        receipt = common.read(path)
        if receipt.get("passed") is not True:
            raise ValueError("Legacy image batch did not complete")
        for row in receipt["image_identities"].values():
            if row["matches"] is not True or row["expected"] != row["actual"]:
                raise ValueError("Legacy loaded image differs")
            ids.add(row["expected"])
        receipts.append(common.reference(path))
    result = subprocess.run(["/usr/bin/docker", "--host", common.SOCKET, "image", "ls", "--no-trunc", "--quiet"],
                            capture_output=True, text=True, check=True, timeout=30)
    missing = sorted(ids - set(result.stdout.splitlines()))
    if missing:
        raise ValueError("Legacy image missing from current Docker: " + str(missing))
    return {"load_receipts": receipts, "current_unique_image_count": len(ids),
            "all_required_image_ids_currently_loaded": True, "image_ids": sorted(ids)}


def plan():
    proofs = {}
    for group in GROUPS[:2]:
        index_path = BASE / group / "layer-index.partial.json"
        index = common.read(index_path)
        if index["available_layer_digests_verified"] is not True:
            raise ValueError("Legacy layer verification is incomplete")
        for proof in index["layers"].values():
            path = Path(proof["path"])
            if path.parent not in {BASE / group / "blobs" for group in GROUPS} or proof["bytes"] < 1024**2:
                continue
            proofs[str(path)] = {"path": str(path), "bytes": proof["bytes"], "sha256": proof["sha256"],
                                 "prior_stat": proof["stat"], "retained_proof": common.reference(index_path)}
    archive_path = BASE / "parallel-images/eight-image-archive-receipt.json"
    archive = common.read(archive_path)
    for item in archive["inputs_and_snapshot_stats"].values():
        path = Path(item["path"])
        if path.parent == BASE / "parallel-images/blobs" and path.name.endswith(".tar.gz") and item["stat"]["bytes"] >= 1024**2:
            proofs[str(path)] = {"path": str(path), "bytes": item["stat"]["bytes"],
                "sha256": item["digest_already_verified"].split(":")[-1],
                "prior_stat": item["stat"], "retained_proof": common.reference(archive_path)}
    selected = []
    for path, proof in sorted(proofs.items()):
        if not Path(path).exists():
            continue
        if Path(path).lstat().st_nlink != 1:
            continue  # Retain shared hardlinks; do not claim their blocks freed.
        identity = common.identity(Path(path))
        if legacy_stat(identity) != proof["prior_stat"]:
            raise ValueError("Verified historical payload identity changed: " + path)
        selected.append({**proof, "identity": identity, "allocated_bytes": Path(path).stat().st_blocks * 512})
    path = Path(archive["path"])
    if path != BASE / "parallel-images/eight-original-images.docker.tar":
        raise ValueError("Unexpected legacy load archive path")
    archive_id = common.identity(path)
    if archive_id["size"] != archive["bytes"]:
        raise ValueError("Completed load archive size differs")
    selected.append({"path": str(path), "bytes": archive["bytes"],
        "sha256": archive["sha256_computed_while_writing"], "identity": archive_id,
        "allocated_bytes": path.stat().st_blocks * 512, "retained_proof": common.reference(archive_path)})
    paths = {row["path"] for row in selected}
    consumers(paths)
    frozen = common.frozen_payload_dependencies(paths)
    if frozen["selected_payload_dependencies"]:
        raise ValueError("Current frozen execution uses a selected historical payload")
    return common.write_new(OUTPUT / "plan.json", {"version": VERSION, "utc": common.utc(),
        "source": common.reference(__file__), "common_helper": common.reference(common.__file__),
        "loaded_images": images(), "frozen_dependencies": frozen, "live_consumers": [],
        "payloads": selected, "payload_count": len(selected),
        "payload_bytes": sum(row["bytes"] for row in selected),
        "allocated_bytes": sum(row["allocated_bytes"] for row in selected),
        "Docker_images_storage_and_models_preserved": True,
        "all_configs_manifests_SHA_logs_and_experiment_records_preserved": True})


def apply(path, sha):
    ref = common.reference(path)
    if ref["sha256"] != sha:
        raise ValueError("Legacy cleanup plan SHA differs")
    value = common.read(path)
    if (value["version"] != VERSION or value["source"] != common.reference(__file__)
            or value["common_helper"] != common.reference(common.__file__)):
        raise ValueError("Legacy cleanup source differs")
    with ExitStack() as stack:
        lock_path = OUTPUT / "retirement.lock"
        with lock_path.open("ab"):
            pass
        common.exclusive(stack, lock_path)
        if (OUTPUT / "completion.json").exists():
            raise ValueError("Legacy payload retirement already completed")
        for row in value["payloads"]:
            path = Path(row["path"])
            if not ((path.parent in {BASE / group / "blobs" for group in GROUPS}
                     and re.fullmatch(r"[a-f0-9]{64}\.tar\.gz", path.name))
                    or path == BASE / "parallel-images/eight-original-images.docker.tar"):
                raise ValueError("Legacy payload escaped exact scope")
            common.exclusive(stack, path)
            if common.identity(path) != row["identity"] or common.reference(row["retained_proof"]["path"]) != row["retained_proof"]:
                raise ValueError("Legacy payload or proof changed")
        paths = {row["path"] for row in value["payloads"]}
        consumers(paths)
        loaded = images()
        frozen = common.frozen_payload_dependencies(paths)
        if frozen["selected_payload_dependencies"]:
            raise ValueError("A current binding uses a selected payload")
        intent = common.write_new(OUTPUT / "intent.json", {"version": VERSION, "utc": common.utc(),
            "plan": ref, "loaded_images": loaded, "frozen_dependencies": frozen,
            "live_consumers": [], "exclusive_payload_locks_held": True})
        for row in value["payloads"]:
            Path(row["path"]).unlink()
        return common.write_new(OUTPUT / "completion.json", {"version": VERSION, "utc": common.utc(),
            "plan": ref, "intent": intent, "removed_payload_count": len(value["payloads"]),
            "removed_payload_bytes": value["payload_bytes"], "released_allocated_bytes": value["allocated_bytes"],
            "Docker_images_storage_models_configs_records_modified": False,
            "model_calls": 0, "services_signalled": 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("plan")
    command = commands.add_parser("apply")
    command.add_argument("--plan", type=Path, required=True)
    command.add_argument("--sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(plan() if args.operation == "plan" else apply(args.plan, args.sha256)))


if __name__ == "__main__":
    main()
