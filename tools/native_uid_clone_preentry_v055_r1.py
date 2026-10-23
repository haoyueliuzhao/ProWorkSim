"""Privileged clone admission for one exact qualified legacy template and six slots."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "runs/software-benchmark-v055/pre-entry-recovery-r1"


def checked(reference):
    path = Path(reference["path"])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("Exact clone evidence changed")
    return json.loads(raw)


def exact_source(plan, manifest_path, manifest_sha, destination, slot_id):
    template = plan["template"]
    match = [row for row in plan["slots"] if row["slot_id"] == slot_id]
    if len(match) != 1 or len(plan["slots"]) != 6 or plan["recovery_root"] != str(RECOVERY):
        raise ValueError("Clone is outside the fixed six-slot recovery")
    if Path(destination).resolve() != Path(match[0]["output_directory"]) / "actor/rootfs":
        raise ValueError("Clone destination is not this slot's new actor root")
    if (Path(manifest_path).resolve() != Path(template["manifest"]["path"]).resolve()
            or manifest_sha != template["manifest"]["sha256"]):
        raise ValueError("Unregistered source manifest")
    manifest = checked(template["manifest"])
    source = Path(manifest["prepared_root"]).resolve(strict=True)
    if source != Path(template["prepared_root"]) or source.stat().st_dev != template["device"]:
        raise ValueError("Exact template root or device changed")
    qualification = checked(template["qualification"])
    if (qualification.get("passed") is not True or qualification.get("instance_id") != "astropy__astropy-12907"
            or qualification.get("baseline_mapping") != template["baseline_mapping"]):
        raise ValueError("Exact source initialization qualification changed")
    return manifest, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or int(os.environ.get("SUDO_UID", "-1")) != 1021:
        raise PermissionError("Use only the existing owner's sudo bootstrap")
    plan = checked({"path": str(RECOVERY / "plan.json"), "sha256": args.plan_sha256})
    sources = {item["path"]: item for item in plan["sources"]}
    helper = ROOT / "tools/native_uid_bootstrap_v055.py"
    for path in (Path(__file__).resolve(), helper):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sources[str(path)]["sha256"]:
            raise ValueError("Finite clone helper source changed")
    source = plan["template"]["manifest"]
    admitted = exact_source(plan, source["path"], source["sha256"], args.destination, args.slot_id)
    spec = importlib.util.spec_from_file_location("sealed_original_uid_bootstrap", helper)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    def read_exact(path, sha):
        if str(path) != source["path"] or sha != source["sha256"]:
            raise ValueError("Original clone requested another manifest")
        return admitted
    original.checked_manifest = read_exact
    original.clone(source["path"], source["sha256"], args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
