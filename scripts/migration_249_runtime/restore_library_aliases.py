"""Restore source library filenames in the private runtime, after byte matching.

The migration packer copied shared-library symlink contents to SONAME files.
Some frozen references name the original versioned regular file instead. This
utility creates only missing hard-link aliases with the exact expected bytes;
it never touches host /usr, replaces a file, or installs another library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def restore(sysroot, runtime, *, apply=False):
    root = Path(sysroot).resolve(strict=True)
    if root == Path("/") or not (root.parent / "manifest.json").is_file():
        raise ValueError("An existing migration private sysroot is required")
    references = json.loads(Path(runtime).read_bytes())["os_library_refs"]
    planned = []
    # Validate every candidate before making any change.
    for reference in references:
        original = Path(reference["path"])
        if (original.parent != Path("/usr/lib/x86_64-linux-gnu")
                or ".." in original.parts):
            raise ValueError("Only declared original shared-library paths are supported")
        target = root / original.relative_to("/")
        if not target.parent.resolve().is_relative_to(root):
            raise ValueError("Library destination escapes the private sysroot")
        if target.exists():
            source = target
        else:
            if target.is_symlink():
                raise ValueError("Do not replace an existing dangling library alias")
            match = re.fullmatch(r"(.+\.so\.\d+)(?:\.\d+)+", original.name)
            if match is None:
                raise ValueError("No unambiguous SONAME for " + str(original))
            source = target.with_name(match[1])
        actual = source.resolve(strict=True)
        if not actual.is_relative_to(root) or not actual.is_file():
            raise ValueError("Library source must be a private-runtime regular file")
        raw = actual.read_bytes()
        if len(raw) != reference["bytes"] or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("Private payload differs from original library: " + str(original))
        planned.append({"original_reference": reference, "source": str(actual),
                        "target": str(target), "missing": not target.exists()})
    created = []
    if apply:
        for row in planned:
            if row["missing"]:
                os.link(row["source"], row["target"])
                created.append(row["target"])
    return {"version": "server-249-private-library-aliases-v1", "applied": apply,
            "checked_libraries": planned, "created_hardlinks": created,
            "existing_payload_changed": False, "host_usr_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sysroot", default="/data0/zhuxinrui/proworksim-runtime/sysroot")
    parser.add_argument("--runtime", default="artifacts/software-bridge-v052/source-qualification/runtime.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(restore(args.sysroot, args.runtime, apply=args.apply), indent=2))
