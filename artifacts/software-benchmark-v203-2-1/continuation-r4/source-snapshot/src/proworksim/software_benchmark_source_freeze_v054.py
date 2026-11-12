"""Freeze small scientific sources transitively; never rehash model or image payloads."""
from __future__ import annotations

import json
from pathlib import Path

from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v054-scientific-source-manifest-v1"
MANIFEST = ROOT / "artifacts/software-benchmark-v054/runner/source-manifest.json"


def source_paths():
    paths = set((ROOT / "src/proworksim").rglob("*.py"))
    paths.update((ROOT / "scripts").rglob("*.py"))
    paths.update((ROOT / "artifacts/software-learning-v050/resume-r6-source/scripts").rglob("*.py"))
    for pattern in ("*v054*.py", "*v054*.sh"):
        paths.update((ROOT / "tools").glob(pattern))
    # Operational status reporting may evolve without changing solving conditions.
    paths.discard(ROOT / "tools/benchmark_preparation_status_v054.py")
    paths.update(path for path in (ROOT / "config").glob("v054-*.json")
                 if not path.name.startswith("v054-condition-"))
    paths.add(ROOT / "artifacts/software-benchmark-v054/manifests/native-interface.json")
    paths.add(ROOT / "artifacts/software-benchmark-v054/native-environment/ref-host-cuda-toolchain.json")
    for package in ("openhands-sdk/openhands/sdk", "openhands-tools/openhands/tools"):
        base = ROOT / "runs/v016-sdk/upstream" / package
        for pattern in ("*.py", "*.j2", "*.jinja", "*.jinja2", "*.md"):
            paths.update(base.rglob(pattern))
    return sorted(path.resolve() for path in paths if path.is_file())


def freeze_sources(output=MANIFEST):
    paths = source_paths()
    return write_new(output, {
        "version": VERSION, "scope": "all project Python, scripts, v054 launchers/config and official SDK tools/templates",
        "condition_files_excluded_to_avoid_reference_cycle": True,
        "large_model_or_image_payloads_hashed": False,
        "files": [reference(path) for path in paths],
        "model_calls": 0, "formal_execution_authorized": False,
    })


def verify_sources(manifest_reference):
    if Path(manifest_reference["path"]) != MANIFEST:
        raise ValueError("Only the frozen scientific source manifest is accepted")
    manifest = json.loads(checked(manifest_reference).read_text())
    if manifest.get("version") != VERSION:
        raise ValueError("Unrecognized scientific source manifest")
    paths = {checked(item) for item in manifest["files"]}
    required = {ROOT / "src/proworksim" / name for name in (
        "software_benchmark_world_v054.py", "software_benchmark_managed_v054.py",
        "software_benchmark_runner_v054.py", "software_benchmark_exact_transport_v054.py",
        "software_benchmark_owner_ipc_v054.py", "software_benchmark_source_freeze_v054.py")}
    if not required <= paths:
        raise ValueError("Scientific interface/numerical sources are not completely frozen")
    return {"source_manifest": manifest_reference, "verified_small_files": len(paths),
            "large_model_or_image_payloads_hashed": False}
