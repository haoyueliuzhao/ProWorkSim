"""Immutable-image to native-worker rootfs preparation, without host link traversal."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import uuid

VERSION = "v054-native-rootfs-v1"
RUNTIME_ROOTS = {"dev", "proc", "sys"}


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(name):
    name = name.removeprefix("./")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\0" in name:
        raise ValueError("Rootfs archive member escapes its root")
    return path


def extract_rootfs(archive_path, destination, *, max_bytes=32 * 1024**3):
    """Write regular files before symlinks, so archive links are never followed."""
    root = Path(destination)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries, symlinks, hardlinks, directories = {}, [], [], []
    total = 0
    with tarfile.open(archive_path, mode="r|*") as archive:
        for item in archive:
            path = relative(item.name)
            if not path.parts or path.parts[0] in RUNTIME_ROOTS:
                continue
            name = path.as_posix()
            if name in entries:
                raise ValueError("Duplicate rootfs archive entry")
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            record = {"path": name, "mode": item.mode, "uid": item.uid, "gid": item.gid}
            if item.isdir():
                destination.mkdir(exist_ok=True)
                directories.append((destination, item.mode))
                record["kind"] = "directory"
            elif item.issym():
                if "\0" in item.linkname:
                    raise ValueError("Invalid rootfs symlink target")
                symlinks.append((destination, item.linkname))
                record.update(kind="symlink", target=item.linkname)
            elif item.islnk():
                target = relative(item.linkname).as_posix()
                hardlinks.append((destination, target))
                record.update(kind="hardlink", target=target)
            elif item.isfile():
                total += item.size
                if total > max_bytes:
                    raise ValueError("Rootfs deployment limit exceeded; no partial source admitted")
                source = archive.extractfile(item)
                assert source is not None
                hasher = hashlib.sha256()
                written = 0
                with destination.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024**2), b""):
                        output.write(chunk)
                        hasher.update(chunk)
                        written += len(chunk)
                if written != item.size:
                    raise ValueError("Truncated rootfs archive payload")
                destination.chmod(item.mode)
                record.update(kind="file", bytes=written, sha256=hasher.hexdigest())
            else:
                raise ValueError("Unexpected rootfs device/socket outside rebuilt runtime roots")
            entries[name] = record
    while hardlinks:
        remaining = []
        for destination, name in hardlinks:
            target = root / name
            if target.exists() and target.is_file() and not target.is_symlink():
                os.link(target, destination)
            else:
                remaining.append((destination, name))
        if len(remaining) == len(hardlinks):
            raise ValueError("Unresolved or invalid rootfs hardlink")
        hardlinks = remaining
    for destination, target in symlinks:
        # Existing implicit parent directories reveal an unsafe/conflicting
        # archive which tried to write through a declared symlink.
        if destination.exists() or destination.is_symlink():
            raise ValueError("Rootfs symlink conflicts with an extracted file/directory")
        destination.symlink_to(target)
    for directory, mode in reversed(directories):
        directory.chmod(mode)
    return {
        "entries": [entries[name] for name in sorted(entries)],
        "regular_file_bytes": total,
        "rebuilt_runtime_roots": sorted(RUNTIME_ROOTS),
        "ownership_policy": "mapped_host_owner_for_private_user_namespace_root",
        "original_uid_gid_retained_in_manifest": True,
    }


def image_environment(config_bytes, *, image_id, public_python):
    config_sha = digest(config_bytes)
    if image_id != "sha256:" + config_sha:
        raise ValueError("Image config bytes do not match the admitted immutable image ID")
    image = json.loads(config_bytes)
    if image.get("os") != "linux" or image.get("architecture") != "amd64":
        raise ValueError("Expected the pinned linux/amd64 image")
    config = image["config"]
    original_user = config.get("User") or ""
    if original_user not in {"", "root", "0", "0:0", "root:root"}:
        raise ValueError("Non-root image User requires a separately admitted UID mapping")
    if config.get("Volumes"):
        raise ValueError("Image-declared volumes require explicit rootfs coverage preparation")
    if not public_python.startswith("/") or ".." in PurePosixPath(public_python).parts:
        raise ValueError("Public interpreter must come from the actual image preflight")
    original = {}
    for item in config.get("Env") or []:
        key, separator, value = item.partition("=")
        if not separator or key in original:
            raise ValueError("Invalid or ambiguous image environment")
        original[key] = value
    environment = {key: value for key, value in original.items()
                   if key.lower() not in {"http_proxy", "https_proxy", "all_proxy"}}
    if "PATH" not in environment:
        raise ValueError("Image PATH must be explicit; do not guess the test interpreter")
    python_dir = str(PurePosixPath(public_python).parent)
    environment["PATH"] = ":".join(
        [python_dir] + [part for part in environment["PATH"].split(":") if part != python_dir])
    environment.setdefault("HOME", "/root")
    environment.setdefault("USER", "root")
    environment.setdefault("LOGNAME", "root")
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("LC_ALL", "C.UTF-8")
    environment.setdefault("TMPDIR", "/tmp")
    if "/envs/" in python_dir:
        prefix = str(PurePosixPath(python_dir).parent)
        environment["CONDA_PREFIX"] = prefix
        environment["CONDA_DEFAULT_ENV"] = PurePosixPath(prefix).name
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["NVIDIA_VISIBLE_DEVICES"] = "void"
    return {
        "version": "v054-native-public-environment-v1", "kind": "official_image",
        "image_id": image_id, "source_config_sha256": config_sha,
        "original_image_user": original_user, "original_image_environment": original,
        "environment": environment, "public_python": public_python,
        "derivation": "Pinned image config only; select admitted public interpreter, CPU/offline actor",
    }


def prepare_rootfs(*, environment, controller, config_blob, destination,
                   minimum_free_bytes=64 * 1024**3):
    """Export an already loaded image without starting any task process."""
    destination = Path(destination).resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    image = environment["image"]
    public_env = image_environment(
        Path(config_blob).read_bytes(), image_id=image["image_id"],
        public_python=environment["public_python"])
    if shutil.disk_usage(destination).free < minimum_free_bytes:
        raise RuntimeError("Native rootfs disk reserve gate")
    inspection = json.loads(controller.run("image", "inspect", image["image_id"]).stdout)[0]
    if inspection["Id"] != image["image_id"]:
        raise ValueError("Loaded image changed before rootfs export")
    name = "pws-v054-rootfs-" + uuid.uuid4().hex
    container = controller.run(
        "create", "--pull", "never", "--name", name, "--network", "none",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--entrypoint", "/bin/true", image["image_id"]).stdout.decode().strip()
    archive_path = destination / "rootfs.tar"
    archive_hash, archive_bytes = hashlib.sha256(), 0
    try:
        process = subprocess.Popen(
            [controller.cli, "--host", controller.socket, "export", container],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "DOCKER_HOST": controller.socket,
                 "NO_PROXY": "*", "no_proxy": "*"})
        try:
            with archive_path.open("xb") as output:
                while chunk := process.stdout.read(8 * 1024**2):
                    if shutil.disk_usage(destination).free < minimum_free_bytes:
                        raise RuntimeError("Native rootfs disk reserve gate during export")
                    output.write(chunk)
                    archive_hash.update(chunk)
                    archive_bytes += len(chunk)
            if process.wait(timeout=120) != 0:
                raise RuntimeError("Private Docker rootfs export failed")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
    finally:
        controller.remove(container)
    tree = extract_rootfs(archive_path, destination / "rootfs")
    manifest = {
        "version": VERSION, "prepared_root": str(destination / "rootfs"),
        "image_id": image["image_id"], "manifest_digest": image["manifest_digest"],
        "instance_id": environment["task"]["instance_id"],
        "base_commit": environment["task"]["base_commit"],
        "archive_sha256": archive_hash.hexdigest(), "archive_bytes": archive_bytes,
        "source_environment_sha256": digest(canonical(environment)), **tree,
        "original_image_user": public_env["original_image_user"],
        "official_grading_image_modified": False, "containers_started": 0,
        "native_real_task_control_passed": False, "numeric_ownership_equivalence_admitted": False,
        "model_calls": 0,
    }
    manifest_path = destination / "rootfs-manifest.json"
    manifest_path.write_bytes(canonical(manifest))
    public_env.update(rootfs_manifest=str(manifest_path),
                      rootfs_manifest_sha256=digest(manifest_path.read_bytes()))
    (destination / "public-environment.json").write_bytes(canonical(public_env))
    archive_path.unlink()
    return manifest_path
