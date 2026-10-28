"""One CPU-only comparison of the real normalizer in both project Pythons."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proworksim import software_benchmark_qualification_reuse_v066 as reuse  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402


def probe():
    components = []
    for name in reuse.COMPONENTS:
        base = ROOT / "src/proworksim" / ("software_benchmark_" + name)
        old, new = Path(str(base) + "_v064.py"), Path(str(base) + "_v066.py")
        digest = reuse.compare_sources(old.read_text(), new.read_text(), scorer=name == "scorer")
        components.append({"component": name, "old": reference(old), "new": reference(new),
                           "normalized_AST_sha256": digest})
    small = reuse.normalized_ast("def f(): return 1\n")
    return {"python": sys.version, "normalizer": reference(reuse.__file__), "components": components,
            "minimal_empty_fields_AST_sha256": hashlib.sha256(small.encode()).hexdigest()}


def run(output):
    script = str(Path(__file__).resolve())
    python = str(ROOT / ".venv/bin/python")
    commands = [[python, "-B", script, "--probe"],
        [python, "-B", str(ROOT / "tools/run_offline_scorer_v058.py"), script, "--probe"]]
    observations = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        observations.append(json.loads(completed.stdout))
    a, b = observations
    if (a["normalizer"] != b["normalizer"] or a["components"] != b["components"]
            or a["minimal_empty_fields_AST_sha256"] != b["minimal_empty_fields_AST_sha256"]):
        raise ValueError("Actual normalizer differs between the project and private Python")
    value = {"version": "v066-cross-python-ast-control-r1", "passed": True,
        "control_script": reference(__file__), "commands": commands, "observations": observations,
        "matching_component_pairs": len(a["components"]), "old_fixture_tests_repeated": 0,
        "old_qualifications_revalidated": 0, "old_proof_files_modified": False,
        "API_calls": 0, "Docker_operations": 0, "GPU_operations": 0}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return write_new(output, value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--probe", action="store_true")
    choice.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(probe() if args.probe else run(args.output)))
