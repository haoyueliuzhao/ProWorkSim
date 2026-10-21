"""One CPU control for original high numeric IDs within existing subordinate ranges."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/software-benchmark-v054/native-sparse-uid-control-r1"
HELPER = ROOT / "tools/native_uid_bootstrap_v054.py"


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    return reference(path)


def main():
    spec = importlib.util.spec_from_file_location("sparse_uid_bootstrap", HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    rootfs = OUTPUT / "rootfs"
    rootfs.mkdir(exist_ok=False)
    entries = []
    for name, uid, gid in (("root.txt", 0, 0), ("low.txt", 1000, 100),
                           ("high.txt", 197609, 197121)):
        (rootfs / name).write_text("synthetic UID control\n")
        entries.append({"path": name, "kind": "file", "mode": 0o644, "uid": uid, "gid": gid})
    manifest = {"prepared_root": str(rootfs), "entries": entries,
                "numeric_ownership_equivalence_admitted": False}
    manifest_path = OUTPUT / "rootfs-manifest.json"
    write_new(manifest_path, manifest)
    planned = helper.mapping_for_manifest(manifest)
    assert helper.mapped(1000, planned) == helper.FIRST + 999
    assert helper.mapped(100, planned, group=True) == helper.FIRST + 99
    assert helper.mapped(197609, planned) == helper.FIRST + helper.COUNT - 1
    assert planned["unmapped_unobserved_uids"] == [65536]
    try:
        helper.mapped(65536, planned)
        raise AssertionError("Borrowed unobserved guest ID must not alias the high ID")
    except ValueError:
        pass
    before = reference(manifest_path)
    command = ["sudo", "-n", "/usr/bin/python3", str(HELPER), "ownership",
               str(manifest_path), before["sha256"]]
    applied = subprocess.run(command, check=True, capture_output=True, text=True)
    ownership = json.loads(applied.stdout)
    assert ownership["uid_gid_mapping"] == planned
    manifest.update(numeric_ownership_equivalence_admitted=True, ownership_receipt=ownership)
    manifest_path.write_text(json.dumps(manifest) + "\n")
    public = OUTPUT / "public-environment.json"
    write_new(public, {"rootfs_manifest": str(manifest_path),
                       "rootfs_manifest_sha256": reference(manifest_path)["sha256"]})
    tampered = json.loads(json.dumps(manifest))
    tampered["ownership_receipt"]["uid_gid_mapping"]["uid_map"][-1][1] -= 1
    try:
        helper.admitted_mapping(tampered)
        raise AssertionError("Namespace must reject a different ownership map")
    except ValueError:
        pass
    code = (
        "import json,os,pathlib\n"
        "root=pathlib.Path(" + repr(str(rootfs)) + ")\n"
        "expected=" + repr(entries) + "\n"
        "observed={}\n"
        "assert os.getuid()==0 and os.getgid()==0\n"
        "for entry in expected:\n"
        " p=root/entry['path']; s=p.stat(); observed[entry['path']]=[s.st_uid,s.st_gid]\n"
        " assert observed[entry['path']]==[entry['uid'],entry['gid']]\n"
        "os.chown(root/'high.txt',197609,197121)\n"
        "print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'observed':observed,"
        "'uid_map':pathlib.Path('/proc/self/uid_map').read_text(),"
        "'gid_map':pathlib.Path('/proc/self/gid_map').read_text()}))\n")
    completed = subprocess.run([
        "sudo", "-n", "/usr/bin/python3", str(HELPER), "launch",
        "--environment-manifest", str(public), "--rootfs", str(rootfs), "--",
        "/usr/bin/unshare", "--mount", "--pid", "--fork", "/usr/bin/python3", "-c", code,
    ], check=True, capture_output=True, text=True)
    observed = json.loads(completed.stdout)
    for key in ("uid_map", "gid_map"):
        assert [list(map(int, line.split())) for line in observed[key].splitlines()] == planned[key]
    for entry in entries:
        actual = (rootfs / entry["path"]).stat()
        assert actual.st_uid == helper.mapped(entry["uid"], planned)
        assert actual.st_gid == helper.mapped(entry["gid"], planned, group=True)
    legacy_manifest = {"entries": [entry for entry in entries if entry["uid"] < helper.COUNT]}
    legacy = helper.mapping_for_manifest(legacy_manifest)
    assert helper.map_text(legacy["uid_map"]) == "0 1021 1\n1 558752 65536"
    assert helper.map_text(legacy["gid_map"]) == "0 1022 1\n1 558752 65536"
    receipt = write_new(OUTPUT / "receipt.json", {
        "passed": True, "model_calls": 0, "gpu_launches": 0, "formal_slot_claims": 0,
        "low_uid_mapping_preserved": True, "high_uid_gid_preserved": True,
        "legacy_low_only_mapping_unchanged": True, "mapping_drift_rejected": True,
        "existing_subordinate_range_only": True, "server_global_allocations_changed": False,
        "original_high_uid": 197609, "original_high_gid": 197121,
        "uid_gid_mapping": planned, "actual_namespace": observed,
        "rootfs_payload_reexported": False, "large_rootfs_payload_rehashed": False,
        "control_scope": "Synthetic files plus one real user/mount/PID namespace; no task tests",
        "sources": [reference(HELPER), reference(ROOT / "tools/run_native_worker_mapped_v054.sh"),
                    reference(Path(__file__))]})
    old = json.loads((OUTPUT / "prior-sources.json").read_text())
    artifact = ROOT / "artifacts/software-benchmark-v054/native-environment/sparse-uid-control-r1.json"
    value = json.loads(Path(receipt["path"]).read_text())
    value.update(previous_sources=[{key: item[key] for key in ("path", "bytes", "sha256")} for item in old],
                 previous_source_copies=[reference(Path(item["preserved_at"])) for item in old],
                 sources=value["sources"][:2], control_receipt=receipt)
    published = write_new(artifact, value)
    print(json.dumps(published))


if __name__ == "__main__":
    main()
