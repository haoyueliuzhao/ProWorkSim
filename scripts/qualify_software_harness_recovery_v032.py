"""Bind targeted harness controls to an otherwise unchanged numerical runtime."""
import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import checked, reference, write
from scripts.software_harness_recovery_v032 import ALLOWED_SOURCE_REVISIONS

SOURCE = Path(__file__).resolve().parents[1]


def qualify(prior_run_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze a clean harness-recovery execution checkout")
    prior_root, controls = Path(prior_run_root).resolve(), Path(controls).resolve()
    plan = read_json(prior_root / "plan.json")
    parent_cpu = read_json(checked(plan["qualification"]))
    if (parent_cpu.get("passed") is not True or parent_cpu.get("model_calls") != 0
            or parent_cpu.get("source") != plan["source"]):
        raise ValueError("Require the original r2 CPU admission and frozen execution binding")
    old_root = Path(plan["source_root"])
    protected = {str(path.relative_to(old_root)) for prefix in ("src", "scripts")
                 for path in (old_root / prefix).rglob("*.py")}
    for prefix in ("examples/software-sources-v030", "examples/software-v15/upstream"):
        protected.update(str(path.relative_to(old_root)) for path in (old_root / prefix).rglob("*") if path.is_file())
    preserved, revised = {}, {}
    for name in sorted(protected):
        old, current = old_root / name, SOURCE / name
        before, after = digest(old.read_bytes()), digest(current.read_bytes())
        if name in ALLOWED_SOURCE_REVISIONS:
            revised[name] = {"before_sha256": before, "after_sha256": after}
        else:
            if before != after:
                raise ValueError("Undeclared numerical, source, interface or world revision: " + name)
            preserved[name] = after
    if set(revised) != set(ALLOWED_SOURCE_REVISIONS):
        raise ValueError("Every declared harness revision must bind an existing old implementation")
    evidence, checks, fingerprints = {}, {}, {}
    for name in ("interface", "budget", "qualification", "runner", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        rows = value.get("checks") or [value]
        if not rows or any(row.get("returncode") != 0 for row in rows) or not value.get("file_sha256"):
            raise ValueError("Required harness-recovery checks did not pass: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Targeted source references must remain within this checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("Targeted harness source changed since the final checks: " + relative)
            fingerprints[relative] = expected
        evidence[name] = reference(path)
        checks[name] = {"commands": rows, "scope": value.get("scope"), "coverage_notice": value.get("coverage_notice")}
    if not set(ALLOWED_SOURCE_REVISIONS) <= set(fingerprints):
        raise ValueError("Every revised existing file needs an exact final control binding")
    value = {"version": "software-harness-recovery-cpu-v0.32", "passed": True, "model_calls": 0,
             "gpu_used": False, "source": source, "original_r2_plan": reference(prior_root / "plan.json"),
             "inherited_cpu_qualification": plan["qualification"], "inherited_runtime_source": plan["source"],
             "allowed_source_revisions": list(ALLOWED_SOURCE_REVISIONS), "revised_files_sha256": revised,
             "preserved_files_sha256": preserved, "tested_files_sha256": fingerprints,
             "evidence": evidence, "checks": checks,
             "scope": "Public manual, native failure feedback, measured resident budget reservation and terminal diagnostics are revised. Every other old Python source and public asset remains byte-identical. CPU orchestration is not a real-model or training-gain claim. Original results remain unchanged; new worker must restore the exact old common and complete fresh native full-trace admission."}
    write(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-run-root", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.prior_run_root, args.controls, args.output)["passed"])


if __name__ == "__main__":
    main()
