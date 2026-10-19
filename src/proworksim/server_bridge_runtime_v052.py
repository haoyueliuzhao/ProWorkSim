"""Explicit new v052 execution identity for the migrated server.

Preparation copies the existing environment declaration and verifies its small
executable/library references. It neither rescans interpreter trees nor runs any
old task. Invoke inside the migration private runtime, where the original Python
and library paths remain available. Old scientific runtime identities stay frozen.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import platform

from .storage import digest, json_bytes

VERSION = "server-249-v052-test-runtime-v1"
BINDING_VERSION = "server-249-v052-repository-test-binding-v1"
LEGACY_VERSION = "v052-final-r3-test-runtime-v1"
ENVIRONMENT_FIELDS = (
    "python_invocation", "python_executable", "original_environment", "python_version",
    "pip_freeze", "site_packages", "runtime_file_trees", "os_library_refs",
    "target_packages_installed",
)
SOURCE_FILENAMES = (
    ("runner", "software_calibration_repo_tests_v051.py"),
    ("shell_helper", "software_calibration_shell_v051.py"),
    ("bridge_sources", "software_bridge_sources_v052.py"),
    ("openhands_bridge", "software_bridge_openhands_v052.py"),
    ("server_adapter", "server_bridge_runtime_v052.py"),
)


def _ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": digest(raw), "bytes": len(raw)}


def _checked(reference):
    path = Path(reference["path"])
    if not path.is_absolute() or _ref(path) != reference:
        raise ValueError("The server runtime requires intact absolute source references")
    return path


def current_sources():
    root = Path(__file__).resolve().parent
    return {key: _ref(root / name) for key, name in SOURCE_FILENAMES}


def current_host_policy():
    from .software_calibration_shell_v051 import filesystem_policy

    host = platform.uname()
    return {"kernel": {"system": host.system, "release": host.release,
                       "version": host.version, "machine": host.machine},
            "filesystem_policy": filesystem_policy()}


def execution_protocol(runtime):
    return {"version": VERSION,
            "sources": {key: runtime[key] for key, _ in SOURCE_FILENAMES},
            "kernel": runtime["kernel"], "filesystem_policy": runtime["filesystem_policy"]}


def require_task_protocol(task, runtime):
    if task.get("bridge_execution_protocol") != execution_protocol(runtime):
        raise ValueError("New server execution requires its own source/kernel/filesystem identity")


def _original_runtime(reference):
    from .software_bridge_sources_v052 import HELPER_SHA, RUNNER_SHA

    original = json.loads(_checked(reference).read_bytes())
    if (original.get("version") != LEGACY_VERSION or original.get("fixture_only") is not False
            or original["runner"]["sha256"] != RUNNER_SHA
            or original["shell_helper"]["sha256"] != HELPER_SHA):
        raise ValueError("Reuse only the immutable original v052 environment declaration")
    return original


def validate_runtime(runtime):
    if (runtime.get("version") != VERSION or runtime.get("fixture_only") is not False
            or runtime.get("new_execution_protocol") is not True):
        raise ValueError("Declare the explicit new server runtime protocol")
    original = _original_runtime(runtime["original_runtime"])
    if any(runtime.get(key) != original.get(key) for key in ENVIRONMENT_FIELDS):
        raise ValueError("The copied original Python/dependency environment declaration changed")
    for key, reference in current_sources().items():
        if runtime.get(key) != reference:
            raise ValueError("The current server runtime source changed: " + key)
    for key, value in current_host_policy().items():
        if runtime.get(key) != value:
            raise ValueError("The current server kernel/filesystem policy changed: " + key)
    # These finite checks fail clearly outside the private runtime. The large
    # runtime_file_trees declaration is retained as prior migration evidence.
    _checked(runtime["python_executable"])
    _checked(runtime["original_environment"])
    if _ref(runtime["python_invocation"]) != runtime["python_executable"]:
        raise ValueError("The original CPU interpreter invocation resolves differently")
    for reference in runtime["os_library_refs"]:
        _checked(reference)
    for site in runtime["site_packages"]:
        if not Path(site).is_dir():
            raise ValueError("Use the migration private runtime with the original CPU environment")
        for target in ("boltons", "parse", "xmltodict"):
            if (Path(site) / target).exists() or (Path(site) / (target + ".py")).exists():
                raise ValueError("A correct CAL2 target package cannot be installed in the runtime")


def prepare_runtime(*, original_runtime, output):
    """Write one explicit manifest; no qualification, model call or task resume."""
    original_ref = _ref(original_runtime)
    runtime = copy.deepcopy(_original_runtime(original_ref))
    runtime.update(
        version=VERSION, original_runtime=original_ref, **current_sources(), **current_host_policy(),
        new_execution_protocol=True,
        qualification_and_formal_entry="proworksim.software_bridge_sources_v052.run_repository_tests",
        candidate_origin_scope="Fresh source-bound child; namespace/Landlock filesystem policy recorded explicitly",
        environment_verification={
            "executable_and_os_library_references_checked": True,
            "original_environment_declaration_copied_unchanged": True,
            "runtime_file_trees_rehashed": False,
            "tree_evidence_basis": "Existing migration evidence; no new full-tree equivalence claim",
        },
        old_task_resume_authorized=False, old_records_changed=False,
        new_model_calls=0, new_test_executions=0,
    )
    validate_runtime(runtime)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(json_bytes(runtime))
    return {"runtime_manifest": _ref(output), "version": VERSION,
            "filesystem_policy": runtime["filesystem_policy"], "kernel": runtime["kernel"],
            "new_test_executions": 0, "new_model_calls": 0, "old_task_resume_authorized": False}
