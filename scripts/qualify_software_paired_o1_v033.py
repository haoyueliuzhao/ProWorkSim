"""Bind targeted v033 CPU controls and unchanged inherited learning evidence."""
import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.storage import digest, read_json
from scripts.run_ne_v021 import reference, write
from scripts.software_paired_o1_v033 import CANDIDATES, inherited_candidate, inventory

SOURCE = Path(__file__).resolve().parents[1]


def qualify(data_root, controls, output):
    source = code_identity()
    if source["code_dirty"] is not False:
        raise ValueError("Require a clean v033 execution snapshot")
    controls = Path(controls).resolve()
    evidence, checks, fingerprints = {}, {}, {}
    for name in ("interface", "world", "runner", "occupancy", "final-static"):
        path = controls / (name + "/checks.json" if name != "final-static" else "final-static.json")
        value = read_json(path)
        rows = value.get("checks") or [value]
        if (not rows or any(row.get("returncode") != 0 for row in rows)
                or not value.get("file_sha256") or value.get("model_calls", 0) != 0):
            raise ValueError("Missing passing zero-model targeted CPU checks: " + name)
        for relative, expected in value["file_sha256"].items():
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise ValueError("CPU source evidence must remain inside the frozen checkout")
            if digest((SOURCE / relative).read_bytes()) != expected:
                raise ValueError("A CPU-checked file changed: " + relative)
            fingerprints[relative] = expected
        evidence[name] = reference(path)
        checks[name] = {"commands": rows, "scope": value.get("scope"), "coverage_notice": value.get("coverage_notice")}
    parents = {candidate: inherited_candidate(data_root, candidate) for candidate in CANDIDATES}
    slots = inventory()
    if len(slots) != 8 or {row["condition"] for row in slots} != {"S", "T"}:
        raise ValueError("Freeze the full eight-slot paired inventory per model")
    value = {"version": "paired-o1-cpu-v0.33", "passed": True, "model_calls": 0, "gpu_used": False,
             "source": source, "inventory": slots, "candidates": list(CANDIDATES),
             "new_episodes": 16, "fresh_technical_quiz_calls": 0, "repeat_near_16k_stress": False,
             "inherited_learning_evidence": parents, "tested_files_sha256": fingerprints,
             "evidence": evidence, "checks": checks,
             "scope": "New matched world, optional remark, recoverable format feedback and team-budget CPU/SDK controls. Original numerical implementations and full model evidence are bound without new qualification sampling. Work behavior is measured in the declared sixteen episodes, not used as a repeated technical gate; no training-support or allocation-effect claim."}
    write(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(qualify(args.data_root, args.controls, args.output)["passed"])


if __name__ == "__main__":
    main()
