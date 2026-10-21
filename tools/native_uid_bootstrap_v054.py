"""Privileged, finite namespace/ownership bootstrap; no actor RPC or SDK here."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIRST, COUNT = 558752, 65536
OWNER_UID, OWNER_GID = 1021, 1022


def mapped(value, *, group=False):
    if not isinstance(value, int) or value < 0 or value > COUNT:
        raise ValueError("Image numeric ownership is outside the explicitly mapped range")
    return (OWNER_GID if group else OWNER_UID) if value == 0 else FIRST + value - 1


def checked_manifest(path, sha):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Bootstrap only accepts this project's new preparation manifests")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("Bootstrap manifest identity changed")
    value = json.loads(data)
    root = Path(value["prepared_root"]).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Rootfs is outside this project's preparation directory")
    return value, root


def ownership(path, sha):
    manifest, root = checked_manifest(path, sha)
    original_root = root.lstat()
    if not root.is_dir() or original_root.st_uid not in (0, OWNER_UID):
        raise ValueError("Unexpected rootfs owner")
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for item in manifest["entries"]:
            parts = Path(item["path"]).parts
            if not parts or Path(item["path"]).is_absolute() or ".." in parts:
                raise ValueError("Invalid ownership manifest path")
            parent = os.dup(root_fd)
            try:
                for part in parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                    os.close(parent)
                    parent = child
                os.chown(parts[-1], mapped(item["uid"]), mapped(item["gid"], group=True),
                         dir_fd=parent, follow_symlinks=False)
                if item["kind"] != "symlink":
                    descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                         dir_fd=parent)
                    try:
                        os.fchmod(descriptor, item["mode"])
                    finally:
                        os.close(descriptor)
                actual = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                if (actual.st_uid, actual.st_gid) != (mapped(item["uid"]), mapped(item["gid"], group=True)):
                    raise ValueError("Numeric ownership application failed")
            finally:
                os.close(parent)
        os.fchown(root_fd, OWNER_UID, OWNER_GID)
    finally:
        os.close(root_fd)
    print(json.dumps({"numeric_ownership_applied": True, "entries": len(manifest["entries"]),
                      "uid_map": f"0 {OWNER_UID} 1\n1 {FIRST} {COUNT}",
                      "gid_map": f"0 {OWNER_GID} 1\n1 {FIRST} {COUNT}"}))


def clone(path, sha, destination):
    _, root = checked_manifest(path, sha)
    destination = Path(destination)
    parent = destination.parent.resolve(strict=True)
    if (not parent.is_relative_to(ROOT / "runs/software-benchmark-v054")
            or parent.stat().st_uid != OWNER_UID or destination.exists()
            or destination.is_symlink() or destination.name in {"", ".", ".."}):
        raise ValueError("Rootfs clones require a new path in the owner's episode directory")
    subprocess.run(["/bin/cp", "--archive", "--reflink=auto", "--", str(root),
                    str(parent / destination.name)], check=True)


def launch(command):
    if not command or Path(command[0]).resolve() != Path("/usr/bin/unshare"):
        raise ValueError("Bootstrap accepts only the fixed namespace launcher")
    ready_r, ready_w = os.pipe()
    continue_r, continue_w = os.pipe()
    child = os.fork()  # Dedicated bootstrap before any SDK import or threads.
    if child == 0:
        try:
            os.close(ready_r)
            os.close(continue_w)
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.unshare(0x10000000) != 0:  # CLONE_NEWUSER
                raise OSError(ctypes.get_errno(), "unshare user")
            os.write(ready_w, b"R")
            os.close(ready_w)
            if os.read(continue_r, 1) != b"C":
                raise RuntimeError("UID map not admitted")
            os.close(continue_r)
            os.setgroups([])
            os.setgid(0)
            os.setuid(0)
            os.execv(command[0], command)
        except BaseException as error:
            print("namespace bootstrap: " + repr(error), file=sys.stderr)
            os._exit(1)
    os.close(ready_w)
    os.close(continue_r)
    try:
        if os.read(ready_r, 1) != b"R":
            raise RuntimeError("Child did not establish its user namespace")
        Path(f"/proc/{child}/uid_map").write_text(f"0 {OWNER_UID} 1\n1 {FIRST} {COUNT}\n")
        Path(f"/proc/{child}/gid_map").write_text(f"0 {OWNER_GID} 1\n1 {FIRST} {COUNT}\n")
        os.write(continue_w, b"C")
    except BaseException:
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
        raise
    finally:
        os.close(ready_r)
        os.close(continue_w)
    # There is no privileged long-running control process after map creation.
    os.setgroups([])
    os.setgid(OWNER_GID)
    os.setuid(OWNER_UID)
    _, status = os.waitpid(child, 0)
    return os.waitstatus_to_exitcode(status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    own = sub.add_parser("ownership")
    own.add_argument("manifest")
    own.add_argument("sha256")
    copied = sub.add_parser("clone")
    copied.add_argument("manifest")
    copied.add_argument("sha256")
    copied.add_argument("destination")
    run = sub.add_parser("launch")
    run.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.geteuid() != 0 or int(os.environ.get("SUDO_UID", "-1")) != OWNER_UID:
        raise PermissionError("Run only through the existing owner's sudo bootstrap")
    if args.operation == "ownership":
        ownership(args.manifest, args.sha256)
        return 0
    if args.operation == "clone":
        clone(args.manifest, args.sha256, args.destination)
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return launch(command)


if __name__ == "__main__":
    raise SystemExit(main())
