"""Bind the targeted record/continuation repair without repeating model qualification."""
from __future__ import annotations

import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write
from scripts.software_paired_o1_v033 import checked

SOURCE = Path(__file__).resolve().parents[1]
ALLOWED_SOURCE_CHANGES = frozenset({
    "src/proworksim/member_views.py",
    "src/proworksim/software_runtime_v033.py",
})


def qualify(prior_run_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Require a clean committed repair execution checkout")
    prior = Path(prior_run_root).resolve()
    prior_plan = read_json(prior / "plan.json")
    old = Path(prior_plan["source_root"])
    original_qualification = read_json(checked(prior_plan["qualification"]))
    if (original_qualification.get("passed") is not True
            or original_qualification.get("model_calls") != 0
            or original_qualification.get("source") != prior_plan["source"]):
        raise ValueError("Require the original source-bound v033 CPU qualification")
    original_files = {str(path.relative_to(old)): path for path in (old / "src").rglob("*.py")}
    current_files = {str(path.relative_to(SOURCE)): path for path in (SOURCE / "src").rglob("*.py")}
    if original_files.keys() != current_files.keys():
        raise ValueError("This repair must not add or remove production source modules")
    changed, unchanged = {}, {}
    for relative, path in current_files.items():
        before, after = digest(original_files[relative].read_bytes()), digest(path.read_bytes())
        if before == after:
            unchanged[relative] = after
        else:
            changed[relative] = {"before": before, "after": after}
    if set(changed) != ALLOWED_SOURCE_CHANGES:
        raise ValueError("Only offline member-record interpretation and unstarted-slot collection may change")
    controls = Path(controls).resolve()
    evidence, summaries, files = {}, {}, {}
    for name in ("record", "world", "runner", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        rows = value.get("checks", [])
        if (not rows or any(row.get("returncode") != 0 for row in rows)
                or not value.get("file_sha256") or value.get("model_calls") != 0
                or value.get("gpu_used") is not False):
            raise ValueError("Require passing zero-model CPU evidence: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("CPU evidence must name a source-relative file")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("A checked repair file changed: " + relative)
            files[relative] = expected
        evidence[name] = reference(path)
        summaries[name] = {"checks": rows, "scope": value.get("scope"),
                           "coverage_notice": value.get("coverage_notice")}
    if not ALLOWED_SOURCE_CHANGES <= files.keys():
        raise ValueError("Both changed production files require targeted controls")
    value = {"version": "paired-o1-record-repair-cpu-v0.33r1", "passed": True,
        "source": source, "model_calls": 0, "gpu_used": False,
        "prior_plan": reference(prior / "plan.json"),
        "original_v033_qualification_ref": prior_plan["qualification"],
        "control_refs": evidence, "checks": summaries, "file_sha256": files,
        "changed_source_files": changed, "unchanged_src_sha256": unchanged,
        "new_behavioral_qualification_calls": 0, "new_numerical_qualification_calls": 0,
        "scope": "Targeted offline record interpretation and no-replay continuation controls. "
                 "All other production source, including world contracts, SDK prompts, native parsing, "
                 "shared budgets, sampling and numerical learner, is byte-identical to v033. "
                 "Original learning evidence remains inherited; four original episodes are not resampled."}
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
