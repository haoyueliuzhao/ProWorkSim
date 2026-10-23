"""Necessary CPU-only guards for the finite six-slot pre-entry recovery."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    runner = load("deepseek_preentry_recovery_v055_r1")
    clone = load("native_uid_clone_preentry_v055_r1")
    checks = []
    def rejects(name, action):
        try:
            action()
        except (ValueError, FileNotFoundError):
            checks.append(name)
        else:
            raise AssertionError(name)
    rows = []
    for arm in ("REF", "MATCH", "PROJECT"):
        for thinking in ("thinking", "nonthinking"):
            condition = arm + "-" + thinking
            sid = "v055-" + condition + "-astropy__astropy-12907"
            rows.append({"slot_id": sid, "condition_id": condition, "instance_id": runner.EXPECTED_INSTANCE,
                "output_directory": str(runner.RECOVERY / "workers" / hashlib.sha256(sid.encode()).hexdigest()[:24] / "episode")})
    plan = {"recovery_root": str(runner.RECOVERY), "maximum_recovery_slots": 6, "slots": rows}
    runner.validate_scope(plan)
    checks.append("exact_six_original_conditions_admitted")
    bad = copy.deepcopy(plan)
    bad["slots"][0]["instance_id"] = "another-task"
    rejects("unrelated_task_rejected", lambda: runner.validate_scope(bad))
    bad2 = copy.deepcopy(plan)
    bad2["slots"] = bad2["slots"][:5]
    rejects("wrong_slot_count_rejected", lambda: runner.validate_scope(bad2))
    bad3 = copy.deepcopy(plan)
    bad3["slots"][0]["output_directory"] = "/tmp/reuse-old"
    rejects("old_or_arbitrary_output_rejected", lambda: runner.validate_scope(bad3))
    result = {"entered": False, "finally_stopped_scopes": []}
    state = {"phase": "claimed", "entered": False, "started": None}
    routing = {"actual_controller_routing_count": 0}
    runner.assert_preentry(result, state, routing, 0)
    checks.append("zero_model_claimed_only_boundary_admitted")
    rejects("entered_slot_rejected", lambda: runner.assert_preentry({**result, "entered": True}, state, routing, 0))
    rejects("any_API_history_rejected", lambda: runner.assert_preentry(result, state, routing, 1))
    rejects("controller_started_rejected", lambda: runner.assert_preentry(result, state, {"actual_controller_routing_count": 1}, 0))
    with tempfile.TemporaryDirectory(prefix="pws-preentry-control-") as tmp:
        path = Path(tmp)
        source = path / "source"
        source.mkdir()
        manifest = path / "manifest.json"
        manifest.write_text(json.dumps({"prepared_root": str(source)}))
        qualification = path / "qualification.json"
        qualification.write_text(json.dumps({"passed": True, "instance_id": runner.EXPECTED_INSTANCE,
                                              "baseline_mapping": {"sha256": "fixture"}}))
        plan["template"] = {"manifest": runner.reference(manifest), "prepared_root": str(source),
                            "device": source.stat().st_dev, "qualification": runner.reference(qualification),
                            "baseline_mapping": {"sha256": "fixture"}}
        destination = rows[0]["output_directory"] + "/actor/rootfs"
        sha = plan["template"]["manifest"]["sha256"]
        clone.exact_source(plan, manifest, sha, destination, rows[0]["slot_id"])
        checks.append("exact_qualified_source_identity_admitted_without_copy")
        rejects("unregistered_manifest_rejected", lambda: clone.exact_source(plan, path / "other", sha, destination, rows[0]["slot_id"]))
        rejects("arbitrary_destination_rejected", lambda: clone.exact_source(plan, manifest, sha, "/tmp/other", rows[0]["slot_id"]))
        changed = copy.deepcopy(plan)
        changed["template"]["device"] += 1
        rejects("source_device_change_rejected", lambda: clone.exact_source(changed, manifest, sha, destination, rows[0]["slot_id"]))
    out = ROOT / "artifacts/software-benchmark-v055/exception-reconciliation-r1/preentry-recovery-controls.json"
    with out.open("x") as stream:
        json.dump({"passed": True, "checks": checks, "real_model_calls": 0, "systemd_calls": 0,
                   "rootfs_copies": 0, "queue_or_claim_changes": 0, "fixture_only": True}, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": len(checks), "output": str(out)}))


if __name__ == "__main__":
    main()
