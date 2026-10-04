"""Bind a narrow path-admission repair to the unchanged v031 model/runtime."""

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import checked, reference, write

SOURCE = Path(__file__).resolve().parents[1]


def qualify(prior_run_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Freeze a clean path-recovery execution checkout")
    prior_root, controls = Path(prior_run_root).resolve(), Path(controls).resolve()
    prior_plan = read_json(prior_root / "plan.json")
    parent_cpu = read_json(checked(prior_plan["qualification"]))
    if (parent_cpu.get("passed") is not True or parent_cpu.get("model_calls") != 0
            or parent_cpu.get("source") != prior_plan["source"]):
        raise ValueError("Require the original v031 CPU admission and frozen execution binding")
    old_root = Path(prior_plan["source_root"])
    protected = {str(path.relative_to(old_root)) for path in (old_root / "src").rglob("*.py")}
    protected.update(parent_cpu["tested_files_sha256"])
    for prefix in ("examples/software-sources-v030", "examples/software-v15/upstream"):
        protected.update(str(path.relative_to(old_root)) for path in (old_root / prefix).rglob("*") if path.is_file())
    preserved = {}
    for name in sorted(protected):
        old, current = old_root / name, SOURCE / name
        if old.read_bytes() != current.read_bytes():
            raise ValueError("Existing runtime, learner, interface, world or source evidence changed: " + name)
        preserved[name] = digest(current.read_bytes())
    evidence, checks, fingerprints = {}, {}, {}
    for name in ("module", "runner", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        rows = value.get("checks") or [value]
        if not rows or any(row.get("returncode") != 0 for row in rows) or not value.get("file_sha256"):
            raise ValueError("Required targeted path-recovery checks did not pass: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("Targeted source references must remain within this checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("Targeted path-recovery source changed: " + relative)
            fingerprints[relative] = expected
        evidence[name] = reference(path)
        checks[name] = {"commands": rows, "scope": value.get("scope"), "coverage_notice": value.get("coverage_notice")}
    value = {"version": "software-path-recovery-cpu-v0.31r2", "passed": True, "model_calls": 0,
             "gpu_used": False, "source": source, "original_v031_plan": reference(prior_root / "plan.json"),
             "inherited_cpu_qualification": prior_plan["qualification"],
             "inherited_runtime_source": prior_plan["source"], "preserved_files_sha256": preserved,
             "tested_files_sha256": fingerprints, "evidence": evidence, "checks": checks,
             "scope": "New path-contract and bounded correction controller checks only. All original v031 source modules, sampled model interface, numerical learner, world and assets remain byte-identical. Original native/16K GPU results are not reclassified; worker must bind their complete numerical proof and restore exact original common before fresh admission."}
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
