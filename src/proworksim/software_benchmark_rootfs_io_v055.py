"""Read bounded Actor outputs without following links; remove only quiet clones."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def checked(value):
    path = Path(value["path"])
    if not path.is_absolute() or reference(path) != value:
        raise ValueError("Retained cleanup evidence changed")
    return path


def read_actor_bytes(rootfs, relative, *, maximum_bytes=16 * 1024**2):
    path = PurePosixPath(relative)
    if (path.is_absolute() or not path.parts or ".." in path.parts
            or type(maximum_bytes) is not int or not 0 < maximum_bytes <= 16 * 1024**2):
        raise ValueError("A bounded relative Actor output path is required")
    descriptor = os.open(rootfs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        output = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=descriptor)
        try:
            info = os.fstat(output)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Actor output is not a regular file")
            if info.st_size > maximum_bytes:
                raise ValueError("Complete Actor output exceeds its explicit bound; preserve the clone")
            chunks, size = [], 0
            while True:
                chunk = os.read(output, min(65536, maximum_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > maximum_bytes:
                    raise ValueError("Actor output grew beyond its explicit bound; preserve the clone")
            return b"".join(chunks)
        finally:
            os.close(output)
    finally:
        os.close(descriptor)


def read_actor_text(rootfs, relative, *, maximum_bytes=16 * 1024**2):
    return read_actor_bytes(rootfs, relative, maximum_bytes=maximum_bytes).decode("utf-8", errors="replace")


def validate_cleanup(request):
    episode = Path(request["episode_root"])
    rootfs = Path(request["rootfs"])
    dedicated = ROOT / "runs/software-benchmark-v055"
    if (not episode.is_absolute() or episode.resolve() != episode
            or not episode.is_relative_to(dedicated) or not rootfs.is_absolute()
            or rootfs.is_symlink() or rootfs.resolve() != rootfs
            or not rootfs.is_relative_to(episode) or rootfs == episode or rootfs.name != "rootfs"):
        raise ValueError("Cleanup must name one real clone inside this episode directory")
    manifest = json.loads(checked(request["rootfs_manifest"]).read_bytes())
    if (manifest.get("prepared_root") != str(rootfs)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("cloned_from_manifest_sha256", ""))):
        raise ValueError("Cleanup cannot delete a cache template or a different clone")
    proof = json.loads(checked(request["quiescence"]).read_bytes())
    if proof.get("outer_launcher_reaped") is not True:
        raise ValueError("Outer launcher must be reaped before cleanup")
    if proof.get("all_quiet") is True:
        scopes = proof.get("stopped") or proof.get("scopes") or []
    elif proof.get("populated") is False:
        scopes = [proof]
    else:
        raise ValueError("Actual process-tree quiescence is required")
    if not scopes:
        raise ValueError("Cleanup proof contains no registered stopped scopes")
    for scope in scopes:
        unit, cgroup = scope.get("unit", ""), scope.get("cgroup", "")
        if (not re.fullmatch(r"proworksim-v054-episode-[a-f0-9]{32}-[a-z]+\.service", unit)
                or scope.get("populated") is not False or scope.get("main_pid") != 0
                or scope.get("active_state") not in {"inactive", "failed"}
                or not cgroup.endswith("/" + unit) or ".." in cgroup.split("/")
                or not (cgroup.startswith("/user.slice/") or re.match(r"^/proworksimv054ep[a-f0-9]{32}\.slice/", cgroup))):
            raise ValueError("Cleanup scope was not actually stopped")
        events = Path("/sys/fs/cgroup" + cgroup) / "cgroup.events"
        if events.exists() and dict(line.split() for line in events.read_text().splitlines()).get("populated") != "0":
            raise ValueError("A live scope prevents rootfs cleanup")
    if not request["retained_evidence"]:
        raise ValueError("Retain task/test/candidate evidence before deleting its clone")
    for evidence in request["retained_evidence"] + [request["rootfs_manifest"], request["quiescence"]]:
        path = checked(evidence)
        if path.is_relative_to(rootfs):
            raise ValueError("Retained evidence cannot be inside the rootfs being removed")
    return rootfs


def remove_validated_root(request):
    rootfs = validate_cleanup(request)
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("This interpreter cannot safely remove linked Actor trees")
    shutil.rmtree(rootfs)
    return {"removed_rootfs": str(rootfs), "removed": not rootfs.exists(),
            "cache_template_removed": False, "quiescence": request["quiescence"],
            "retained_evidence": request["retained_evidence"]}


def cleanup_episode_rootfs(rootfs, episode_root, rootfs_manifest_ref, quiescence_ref, retained_evidence_refs):
    request = {"version": "v054-quiet-clone-cleanup-v1", "rootfs": str(Path(rootfs).absolute()),
               "episode_root": str(Path(episode_root).resolve()), "rootfs_manifest": rootfs_manifest_ref,
               "quiescence": quiescence_ref, "retained_evidence": list(retained_evidence_refs)}
    validate_cleanup(request)
    parent = Path(rootfs).parent
    path = parent / "cleanup-request.json"
    with path.open("xb") as stream:
        stream.write((json.dumps(request, sort_keys=True, indent=2) + "\n").encode())
    helper = ROOT / "tools/cleanup_native_rootfs_v055.py"
    result = subprocess.run(["sudo", "-n", "/usr/bin/python3", str(helper),
                             "--request", str(path), "--sha256", reference(path)["sha256"]],
                            check=True, capture_output=True, text=True, timeout=180)
    receipt = json.loads(result.stdout)
    output = parent / "cleanup-receipt.json"
    with output.open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return reference(output)
