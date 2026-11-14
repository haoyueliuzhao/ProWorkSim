"""CPU-only runtime inventory and retained-journal control; never a launch grant."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import shutil

ROOT = Path(__file__).resolve().parents[1]


def reference(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def prepare(output, *, run_control=False):
    from proworksim.software_public_test_retention_v203_2_3 import load_base, retaining_executor
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle_path = ROOT / "config/v203-2-2-public-test-bundle.json"
    pinned = json.loads(bundle_path.read_text())
    files = {}
    for alias, row in pinned["files"].items():
        actual = reference(ROOT / row["source"])
        if actual["sha256"] != row["sha256"] or actual["bytes"] != row["bytes"]:
            raise ValueError("Public bundle no longer matches its declared bytes: " + alias)
        files[alias] = actual
    managed = reference(ROOT / pinned["managed_entry"]["source"])
    if managed["sha256"] != pinned["managed_entry"]["sha256"]:
        raise ValueError("Managed entry no longer matches the pinned bundle")
    from proworksim.software_benchmark_runtime_inputs_v203_2_1 import PUBLIC_FILES
    current = {key: reference(path) for key, path in PUBLIC_FILES.items()}
    control = {"run": False}
    if run_control:
        fixture = output / "public-fixture"
        fixture.mkdir()
        (fixture / "test_retained.py").write_text("def test_real_cpu_command():\n    assert 2 + 2 == 4\n")
        tree = reference(fixture / "test_retained.py")["sha256"]
        sealed_source = output / "sealed-source"
        (sealed_source / "tools").mkdir(parents=True)
        for name in ("public_test_execution_v175.py", "public_test_evidence_v175.py"):
            shutil.copyfile(ROOT / "tools" / name, sealed_source / "tools" / name)
        load_base(sealed_source)
        for path in (sealed_source / "tools").iterdir():
            if path.is_file():
                path.unlink()
        execute = retaining_executor(output / "retained-framework", binding={
            "source_reference": {"kind": "synthetic_cpu_fixture", "version": tree},
            "candidate_tree_sha256": tree}, root=sealed_source)
        entry = {"argv": [sys.executable, "-m", "pytest", "-q", "test_retained.py"]}
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                       "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        value = execute(entry, root=fixture, environment=environment, timeout_seconds=20)
        if value["validation_status"] != "verified" or value["counts"]["passed"] != 1:
            raise AssertionError("Real CPU pytest command did not produce verified evidence")
        retained = value["test_evidence"]["retained_journal"]
        proof = json.loads(Path(retained["binding_receipt"]).read_text())
        raw = Path(proof["journal"]["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != proof["journal"]["sha256"]:
            raise AssertionError("Retained journal bytes do not match receipt")
        parsed = load_base().parse_test_evidence(raw, framework="pytest", token=proof["observer_token"],
            process_group=proof["process_group"], returncode=proof["returncode"], timed_out=proof["timed_out"])
        if parsed["validation_status"] != value["validation_status"] or parsed["counts"] != value["counts"]:
            raise AssertionError("Retained journal replay differs from actual command evidence")
        (output / "public-command-result.json").write_text(json.dumps(value, indent=2) + "\n")
        control = {"run": True, "actual_subprocess": True, "framework": "pytest",
                   "interpreter": sys.executable, "passed": True, "retained_journal_reparsed": True,
                   "private_source_removed_after_preload": True,
                   "task_interpreter_qualification": False, "result": reference(output / "public-command-result.json")}
    report = {
        "version": "v203.2.3-runtime-readiness-r1", "organization": "REVIEW2",
        "conditions": ["K0", "K1", "K2"], "real_runtime_admitted": False,
        "launch_authorized_by_manifest": False, "model_calls": 0, "Docker_operations": 0,
        "queue_operations": 0, "cash_ledger_changes": 0,
        "shared_repaired_bundle": {"manifest": reference(bundle_path), "files": files, "managed_entry": managed},
        "current_frozen_actor_bindings": current,
        "framework_retention_control": control,
        "adapter": reference(ROOT / "src/proworksim/software_public_test_retention_v203_2_3.py"),
        "selector_insertion": "per-worker v117 SummarizingManagedContextTransport.select_for_member after original _select",
        "preserve": ["history_worker_type", "condenser parameters and source history", "fixed REVIEW2 roles and tools"],
        "interpretation": "Preparation receipt only. Separate SDK, task-interpreter and sealed-launch records determine readiness.",
        "required_independent_evidence": [
            "The separately authorized CNY130 fresh four-task K0/K1/K2 panel and exact attempt identities.",
            "Final immutable v203.2.3 bundle source hashes, actual imported controller/actor and v175 aliases.",
            "Final real SDK control showing eligible historical fields removed, selected once, same-byte counting/dispatch and new group closure.",
            "Task-interpreter framework controls with original journals retained and exported.",
            "Fresh source snapshot, launch admission, cash ledger and complete ledger reconciliation after execution."]}
    (output / "readiness.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return {"readiness": str(output / "readiness.json"), "real_runtime_admitted": False,
            "model_calls": 0, "framework_control_passed": control.get("passed")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-cpu-control", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, run_control=args.run_cpu_control), ensure_ascii=False))
