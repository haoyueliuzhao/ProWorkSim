"""Permit host replacement of only a fresh public-test clone's old /testbed tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def prepare(manifest_path, expected_sha256):
    if os.geteuid() != 0 or int(os.environ.get("SUDO_UID", "-1")) != 1021:
        raise ValueError("Only this project's existing owner may invoke the finite replacement helper")
    manifest_path = Path(manifest_path).absolute()
    if manifest_path.resolve() != manifest_path or manifest_path.is_symlink():
        raise ValueError("Replacement manifest cannot traverse links")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Fresh clone manifest identity changed")
    manifest = json.loads(raw)
    rootfs = Path(manifest["prepared_root"])
    testbed, test_run = rootfs / "testbed", rootfs.parent.parent
    if (rootfs.resolve() != rootfs or rootfs.is_symlink() or rootfs.name != "rootfs"
            or rootfs.parent.name != "actor" or manifest_path != rootfs.parent / "rootfs-manifest.json"
            or not rootfs.is_relative_to(ROOT / "runs/software-benchmark-v056")
            or not re.fullmatch(r"public-test-[1-9][0-9]*", test_run.name)
            or testbed.resolve() != testbed or testbed.is_symlink() or not testbed.is_dir()
            or not re.fullmatch(r"[a-f0-9]{64}", manifest.get("cloned_from_manifest_sha256", ""))
            or manifest.get("numeric_ownership_equivalence_admitted") is not True
            or any((test_run / name).exists() for name in ("worker.stderr", "worker-ready.json", "execution.json"))):
        raise ValueError("Only an unstarted fresh public-test clone may replace its old public tree")
    receipt = rootfs.parent / "public-tree-replacement.json"
    # Claim before mutation; this helper cannot be replayed after a worker starts.
    with receipt.open("x") as stream:
        json.dump({"state": "claimed", "testbed": str(testbed), "manifest_sha256": expected_sha256}, stream)
    subprocess.run(["/bin/chown", "-h", "-R", "-P", "1021:1022", "--", str(testbed)], check=True)
    value = {"state": "old_public_tree_replacement_prepared", "testbed": str(testbed),
             "manifest_sha256": expected_sha256, "host_uid": 1021, "host_gid": 1022,
             "scope": "old public tree in a fresh test clone, immediately replaced by the managed bundle",
             "immutable_template_changed": False, "actor_started": False, "model_calls": 0}
    receipt.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.manifest, args.sha256)))


if __name__ == "__main__":
    main()
