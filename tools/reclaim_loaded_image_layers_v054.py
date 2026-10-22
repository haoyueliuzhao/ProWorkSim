"""Explicitly retire only verified compressed layer downloads already in Docker.

Config blobs, manifests, download proofs, Docker images/storage and all experiment
records remain. A generated, SHA-pinned plan is required for the deleting mode.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runs/software-benchmark-v054/images/preparation-r1"
PAYLOAD = SOURCE / "blobs"
OUTPUT = ROOT / "runs/software-benchmark-v054/download-payload-retirement-r1"
SOCKET = "unix://" + str(ROOT / "runs/software-panel-v053/docker/docker.sock")
VERSION = "v054-loaded-image-layer-download-retirement-r1"


def read(path):
    return json.loads(Path(path).read_bytes())


def reference(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    return reference(path)


def utc():
    return datetime.now(timezone.utc).isoformat()


def identity(path):
    item = path.lstat()
    if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
        raise ValueError("Payload is not an exclusive regular download file")
    return {"dev": item.st_dev, "ino": item.st_ino, "size": item.st_size,
            "mtime_ns": item.st_mtime_ns, "ctime_ns": item.st_ctime_ns}


def exclusive(stack, path):
    stream = stack.enter_context(path.open("rb"))
    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def active_download_consumers():
    found = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit() or int(path.name) == os.getpid():
            continue
        try:
            args = (path / "cmdline").read_bytes().decode(errors="replace").split("\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        in_project = any(str(ROOT) in arg for arg in args)
        if not in_project:
            try:
                in_project = (path / "cwd").resolve().is_relative_to(ROOT)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                in_project = False
        if not in_project:
            continue
        scripts = [Path(arg).name for arg in args if arg.endswith(".py")]
        if any(any(word in name for word in ("verified_image_prepare", "load_verified_images",
                    "verified_apiba", "verified_registry_ranges", "prefetch", "domestic_asset_download")) for name in scripts):
            found.append({"pid": int(path.name), "scripts": scripts})
    return found


def frozen_payload_dependencies(selected):
    """Check actual per-file freeze sets, not historical descriptor strings."""
    sources = []
    old = read(ROOT / "runs/software-benchmark-v054/formal-queue-r1/state.json")
    bindings_refs = [old["bindings"]]
    policy = read(old["kernel_router"]["policy"]["path"])
    activation = read(policy["activation_path"])
    bindings_refs.append(activation["new_bindings"])
    paths = set()
    for ref in bindings_refs:
        binding = read(ref["path"])
        sources.append(ref)
        paths.update(item["reference"]["path"] for item in binding["frozen_files"])
        manifest = binding["source_manifest"]
        sources.append(manifest)
        paths.update(item["path"] for item in read(manifest["path"])["files"])
    plan = ROOT / "artifacts/software-benchmark-v055/manifests/queue-plan.json"
    sources.append(reference(plan))
    paths.update(item["path"] for item in read(plan)["frozen_sources"])
    return {"source_sets": sources, "checked_frozen_paths": len(paths),
            "selected_payload_dependencies": sorted(paths & selected)}


def current_loaded_evidence(inventory):
    result = subprocess.run(["/usr/bin/docker", "--host", SOCKET, "image", "ls", "--no-trunc", "--quiet"],
                            capture_output=True, text=True, check=True, timeout=30)
    present = set(result.stdout.splitlines())
    required = {image["image_id"] for image in inventory["images"]}
    missing = sorted(required - present)
    if missing:
        raise ValueError("Some pinned official images are no longer loaded: " + str(missing[:3]))
    return {"queried_utc": utc(), "required_official_images_present": len(required),
            "docker_image_id_count": len(present), "missing_required_images": missing,
            "docker_image_ids_sha256": hashlib.sha256("\n".join(sorted(present)).encode()).hexdigest()}


def locked_context(stack):
    exclusive(stack, SOURCE / "preparation.lock")
    exclusive(stack, SOURCE.parent / "offline-load-r1/controller.lock")
    consumers = active_download_consumers()
    if consumers:
        raise ValueError("Historical download/load consumer remains active: " + str(consumers))


def plan():
    inventory = read(SOURCE / "image-inventory.json")
    offline = read(SOURCE.parent / "offline-load-r1/state.json")
    if (len(inventory["images"]) != 500 or inventory["loaded_count"] != 500
            or any(image.get("status") != "loaded" for image in inventory["images"])
            or offline["status"] != "all_500_loaded"):
        raise ValueError("The fixed 500-image load is incomplete")
    configs = {image["config"]["digest"] for image in inventory["images"]}
    layers = {item["digest"]: item for image in inventory["images"] for item in image["layers"]}
    selected = []
    with ExitStack() as stack:
        locked_context(stack)
        loaded = current_loaded_evidence(inventory)
        for digest, descriptor in sorted(layers.items()):
            if digest in configs or descriptor["size"] < 1024**2:
                continue
            path = PAYLOAD / (digest.split(":")[1] + ".blob")
            if not path.exists():
                continue
            exclusive(stack, path.with_name(path.name + ".download.lock"))
            observed = identity(path)
            proof_path = path.with_name(path.name + ".verified.json")
            proof = read(proof_path)
            if (observed != proof["file_identity"] or proof["expected_bytes"] != descriptor["size"]
                    or proof["expected_sha256"] != digest.split(":")[1]):
                raise ValueError("Historical verification identity differs: " + str(path))
            selected.append({"path": str(path), "digest": digest, "bytes": descriptor["size"],
                             "allocated_bytes": path.stat().st_blocks * 512, "identity": observed,
                             "retained_verification_receipt": reference(proof_path)})
        frozen = frozen_payload_dependencies({item["path"] for item in selected})
        if frozen["selected_payload_dependencies"]:
            raise ValueError("A selected payload is directly frozen by a current execution binding")
        value = {"version": VERSION, "created_utc": utc(), "scope_root": str(PAYLOAD),
            "inventory": reference(SOURCE / "image-inventory.json"),
            "completed_offline_load": reference(SOURCE.parent / "offline-load-r1/state.json"),
            "current_loaded_images": loaded, "frozen_dependency_check": frozen,
            "active_download_consumers": [], "layer_count": len(selected), "payloads": selected,
            "payload_bytes": sum(row["bytes"] for row in selected),
            "allocated_bytes": sum(row["allocated_bytes"] for row in selected),
            "config_blobs_retained": True, "all_metadata_and_experiment_records_retained": True,
            "docker_storage_and_images_modified": False,
            "rebuild_basis": "Pinned registry descriptors and SHA receipts retained; loaded Docker images remain available.",
            "source": reference(__file__)}
        return write_new(OUTPUT / "plan.json", value)


def apply(path, sha256):
    plan_ref = reference(path)
    if plan_ref["sha256"] != sha256:
        raise ValueError("Retirement plan identity differs")
    value = read(path)
    if (value.get("version") != VERSION or value.get("scope_root") != str(PAYLOAD)
            or value["source"] != reference(__file__) or value["layer_count"] != len(value["payloads"])):
        raise ValueError("Unsupported explicit retirement plan")
    if (OUTPUT / "completion.json").exists():
        raise ValueError("Retirement already completed; do not replay")
    with ExitStack() as stack:
        locked_context(stack)
        for row in value["payloads"]:
            p = Path(row["path"])
            if p.parent != PAYLOAD or not re.fullmatch(r"[a-f0-9]{64}\.blob", p.name) or p.stem != row["digest"].split(":")[1]:
                raise ValueError("Payload escapes the exact allowlist")
            exclusive(stack, p.with_name(p.name + ".download.lock"))
            if identity(p) != row["identity"] or reference(row["retained_verification_receipt"]["path"]) != row["retained_verification_receipt"]:
                raise ValueError("A payload or its retained proof changed")
        inventory = read(value["inventory"]["path"])
        loaded = current_loaded_evidence(inventory)
        frozen = frozen_payload_dependencies({row["path"] for row in value["payloads"]})
        if frozen["selected_payload_dependencies"]:
            raise ValueError("A current binding newly references a selected payload")
        intent = write_new(OUTPUT / "intent.json", {"version": VERSION, "utc": utc(), "plan": plan_ref,
            "current_loaded_images": loaded, "frozen_dependency_check": frozen,
            "exclusive_loader_and_all_selected_download_locks_held": True, "active_download_consumers": []})
        removed = []
        for row in value["payloads"]:
            Path(row["path"]).unlink()
            removed.append(row["digest"])
        return write_new(OUTPUT / "completion.json", {"version": VERSION, "utc": utc(), "plan": plan_ref,
            "intent": intent, "removed_layer_count": len(removed), "removed_layer_digests": removed,
            "released_allocated_bytes": value["allocated_bytes"], "retired_payload_bytes": value["payload_bytes"],
            "configuration_blobs_metadata_experiment_records_preserved": True,
            "docker_images_storage_modified": False, "model_calls": 0, "services_signalled": 0})


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
