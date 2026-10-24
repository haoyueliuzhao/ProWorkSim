"""Privileged, finite namespace/ownership bootstrap; no actor RPC or SDK here."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIRST, COUNT = 558752, 65536
OWNER_UID, OWNER_GID = 1021, 1022


def mapping_for_manifest(manifest):
    """Retain low IDs; borrow unobserved high-end slots for observed large IDs.

    Guest IDs are never rewritten. Only their host subordinate-ID placement
    changes, and ownership and namespace launch use this same recorded plan.
    """
    result = {"version": "v054-observed-sparse-uid-gid-v1",
              "host_subordinate_first": FIRST, "host_subordinate_count": COUNT,
              "guest_root_host_uid": OWNER_UID, "guest_root_host_gid": OWNER_GID}
    for key, owner in (("uid", OWNER_UID), ("gid", OWNER_GID)):
        observed = {0}
        for item in manifest["entries"]:
            number = item[key]
            if type(number) is not int or not 0 <= number < 2**32 - 1:
                raise ValueError("Invalid original numeric image ownership")
            observed.add(number)
        high = sorted(number for number in observed if number > COUNT)
        available = (number for number in range(COUNT, 0, -1) if number not in observed)
        borrowed = []
        for number in high:
            slot = next(available, None)
            if slot is None:
                raise ValueError("Observed IDs exceed the existing subordinate allocation")
            borrowed.append((slot, number))
        rows, start = [[0, owner, 1]], 1
        for slot in sorted(pair[0] for pair in borrowed):
            if slot > start:
                rows.append([start, FIRST + start - 1, slot - start])
            start = slot + 1
        if start <= COUNT:
            rows.append([start, FIRST + start - 1, COUNT - start + 1])
        rows.extend([number, FIRST + slot - 1, 1] for slot, number in borrowed)
        rows.sort(key=lambda row: row[0])
        result[key + "_map"] = rows
        result["observed_" + key + "s"] = sorted(observed)
        result["unmapped_unobserved_" + key + "s"] = sorted(slot for slot, _ in borrowed)
        if len(rows) > 340 or len(map_text(rows).encode()) >= 4096:
            raise ValueError("Sparse mapping exceeds this kernel's finite map-write bound")
    return result


def map_text(rows):
    return "\n".join(" ".join(map(str, row)) for row in rows)


def mapped(value, mapping, *, group=False):
    for guest, host, length in mapping["gid_map" if group else "uid_map"]:
        if guest <= value < guest + length:
            return host + value - guest
    raise ValueError("Image numeric ownership has no admitted host mapping")


def check_subordinate_allocation():
    owner = pwd.getpwuid(OWNER_UID).pw_name
    for name in ("subuid", "subgid"):
        allocated = False
        for line in Path("/etc/" + name).read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            account, first, count = line.split(":")
            if (account in {owner, str(OWNER_UID)} and int(first) <= FIRST
                    and FIRST + COUNT <= int(first) + int(count)):
                allocated = True
        if not allocated:
            raise ValueError("Existing owner subordinate allocation no longer covers this plan")


def admitted_mapping(manifest):
    mapping = mapping_for_manifest(manifest)
    receipt = manifest.get("ownership_receipt", {})
    if (manifest.get("numeric_ownership_equivalence_admitted") is not True
            or receipt.get("numeric_ownership_applied") is not True):
        raise ValueError("Namespace launch requires completed numeric ownership")
    if receipt.get("uid_gid_mapping") is not None:
        if receipt["uid_gid_mapping"] != mapping:
            raise ValueError("Recorded ownership mapping differs from the observed IDs")
    elif (mapping["unmapped_unobserved_uids"] or mapping["unmapped_unobserved_gids"]):
        raise ValueError("High original IDs require an explicit sparse ownership receipt")
    # Previously qualified low-ID templates retain their exact original map.
    if any(receipt.get(key) != map_text(mapping[key]) for key in ("uid_map", "gid_map")):
        raise ValueError("Ownership and namespace map text differ")
    return mapping


def checked_manifest(path, sha):
    path = Path(path).resolve()
    if not any(path.is_relative_to(ROOT / prefix) for prefix in ("runs/software-benchmark-v056", "runs/software-benchmark-v054/native-lazy-cache",
         "runs/software-benchmark-v054/v056-budget-cache-r1")):
        raise ValueError("Bootstrap only accepts this project's new preparation manifests")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("Bootstrap manifest identity changed")
    value = json.loads(data)
    root = Path(value["prepared_root"]).resolve()
    if not any(root.is_relative_to(ROOT / prefix) for prefix in ("runs/software-benchmark-v056", "runs/software-benchmark-v054/native-lazy-cache",
         "runs/software-benchmark-v054/v056-budget-cache-r1")):
        raise ValueError("Rootfs is outside this project's preparation directory")
    return value, root


def ownership(path, sha):
    manifest, root = checked_manifest(path, sha)
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v056"):
        raise ValueError("Existing v054 cache is read-only in v056")
    check_subordinate_allocation()
    mapping = mapping_for_manifest(manifest)  # Validate every ID before any chown.
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
                os.chown(parts[-1], mapped(item["uid"], mapping), mapped(item["gid"], mapping, group=True),
                         dir_fd=parent, follow_symlinks=False)
                if item["kind"] != "symlink":
                    descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                         dir_fd=parent)
                    try:
                        os.fchmod(descriptor, item["mode"])
                    finally:
                        os.close(descriptor)
                actual = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                if (actual.st_uid, actual.st_gid) != (mapped(item["uid"], mapping), mapped(item["gid"], mapping, group=True)):
                    raise ValueError("Numeric ownership application failed")
            finally:
                os.close(parent)
        os.fchown(root_fd, OWNER_UID, OWNER_GID)
    finally:
        os.close(root_fd)
    print(json.dumps({"numeric_ownership_applied": True, "entries": len(manifest["entries"]),
                      "uid_map": map_text(mapping["uid_map"]),
                      "gid_map": map_text(mapping["gid_map"]), "uid_gid_mapping": mapping}))


def clone(path, sha, destination):
    manifest, root = checked_manifest(path, sha)
    admitted_mapping(manifest)
    destination = Path(destination)
    parent = destination.parent.resolve(strict=True)
    if (not parent.is_relative_to(ROOT / "runs/software-benchmark-v056")
            or parent.stat().st_uid != OWNER_UID or destination.exists()
            or destination.is_symlink() or destination.name in {"", ".", ".."}):
        raise ValueError("Rootfs clones require a new path in the owner's episode directory")
    subprocess.run(["/bin/cp", "--archive", "--reflink=auto", "--", str(root),
                    str(parent / destination.name)], check=True)


def launch(command, environment_manifest, expected_root):
    if not command or Path(command[0]).resolve() != Path("/usr/bin/unshare"):
        raise ValueError("Bootstrap accepts only the fixed namespace launcher")
    public_path = Path(environment_manifest).resolve(strict=True)
    if not public_path.is_relative_to(ROOT / "runs/software-benchmark-v056"):
        raise ValueError("Namespace public environment is outside this project")
    public = json.loads(public_path.read_bytes())
    manifest, root = checked_manifest(public["rootfs_manifest"], public["rootfs_manifest_sha256"])
    if Path(expected_root).resolve(strict=True) != root:
        raise ValueError("Worker rootfs differs from its numeric ownership manifest")
    check_subordinate_allocation()
    mapping = admitted_mapping(manifest)
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
        Path(f"/proc/{child}/uid_map").write_text(map_text(mapping["uid_map"]) + "\n")
        Path(f"/proc/{child}/gid_map").write_text(map_text(mapping["gid_map"]) + "\n")
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
    run.add_argument("--environment-manifest", required=True)
    run.add_argument("--rootfs", required=True)
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
    return launch(command, args.environment_manifest, args.rootfs)


if __name__ == "__main__":
    raise SystemExit(main())
