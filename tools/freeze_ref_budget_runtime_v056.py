"""Freeze the new experiment's scorer metadata and runtime bindings before dispatch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/software-benchmark-v056/runtime-r1"
MANAGED_ONLY = {"src/proworksim/software_benchmark_managed_v056.py",
                "src/proworksim/software_benchmark_managed_worker_v056.py",
                "src/proworksim/software_benchmark_public_tests_v056.py"}


def scorer():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "scorer-manifest-r2.json"
    code = ("from proworksim.software_benchmark_scorer_v056 import installation_manifest; "
            "from proworksim.software_benchmark_candidates_v054 import write_new; "
            "print(write_new(" + repr(str(target)) + ", installation_manifest()))")
    subprocess.run([
        str(ROOT / "tools/run_benchmark_runtime_v054.sh"), "--write-project", "/usr/bin/env",
        "PYTHONPATH=" + str(ROOT / "src"), "HF_HUB_OFFLINE=1", "HF_DATASETS_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1", "NO_PROXY=*", "no_proxy=*", "HTTP_PROXY=", "HTTPS_PROXY=",
        "ALL_PROXY=", "http_proxy=", "https_proxy=", "all_proxy=",
        str(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/python"), "-B", "-c", code], check=True)


def bindings():
    plan = reference(ROOT / "artifacts/software-benchmark-v056/plan.json")
    json.loads(checked(plan).read_bytes())
    cpu = ROOT / "runs/software-benchmark-v056/runtime-cpu-control-r1/result.json"
    proof = json.loads(cpu.read_bytes())
    if proof.get("passed") is not True:
        raise ValueError("The real v056 namespace/worker/cleanup control must pass")
    sdk = ROOT / "artifacts/software-benchmark-v056/sdk-construction-control-r2/result.json"
    if json.loads(sdk.read_bytes()).get("passed") is not True:
        raise ValueError("Actual native SDK construction must pass before formal dispatch")
    files = []
    for base in (ROOT / "src/proworksim", ROOT / "tools"):
        files.extend(reference(p) for p in sorted(base.rglob("*"))
                     if p.is_file() and p.suffix in {".py", ".sh"} and "__pycache__" not in p.parts
                     and str(p.relative_to(ROOT)) not in MANAGED_ONLY)
    source = write_new(OUT / "source-manifest.json", {
        "version": "v056-ref-budget-source-manifest-r1", "files": files,
        "official_sdk_and_vllm": "Pinned existing installations and actual resident identity",
        "old_snapshots_modified": False,
        "excluded_managed_only_not_imported_by_REF": sorted(MANAGED_ONLY)})
    from proworksim.software_benchmark_scorer_v056 import LIMITS
    value = {"version": "v056-ref-budget-bindings-r1", "plan": plan,
        "frozen_sources": source, "actual_cpu_control": reference(cpu),
        "actual_sdk_control": reference(sdk),
        "scorer_manifest": reference(OUT / "scorer-manifest-r2.json"),
        "images": reference(ROOT / "runs/software-benchmark-v054/images/preparation-r1/image-inventory.json"),
        "scorer_request_base": {
            "dataset": reference(ROOT / "artifacts/software-benchmark-v054/source/trusted-evaluation.json"),
            "docker_cli": reference(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/docker"),
            "docker_socket": str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
            "trusted_output_root": str(ROOT / "runs/software-benchmark-v056/official-output"),
            "limits": LIMITS},
        "max_generation": 6, "max_scoring": 2,
        "disk_floor_bytes": 128 * 1024**3,
        "generation_reservation_bytes": 64 * 1024**3,
        "scoring_reservation_bytes": 64 * 1024**3,
        "cold_preparation_reservation_bytes": 128 * 1024**3,
        "automatic_generation_retry": False,
        "exception_policy": "defer per-slot errors; do not reuse a model-entered claim"}
    print(json.dumps(write_new(OUT / "bindings.json", value)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("scorer", "bindings"))
    args = parser.parse_args()
    (scorer if args.phase == "scorer" else bindings)()


if __name__ == "__main__":
    main()
