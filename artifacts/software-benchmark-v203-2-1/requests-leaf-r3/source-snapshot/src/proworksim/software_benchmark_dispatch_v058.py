"""Reviewed, narrow v058 dispatch authorization; the incident-wide hold remains.

This is a project workflow guard, not a replacement for OS permissions. It only
reads configuration and sealed project files. It neither creates authorization
nor starts resources, changes a daemon, or releases the old v057 hold.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_FILE = ROOT / "config/v058-offline-rescore-authorization.json"
VERSION = "v058-scoped-offline-dispatch-authorization-r1"
TASKS = frozenset(("psf__requests-2931", "psf__requests-5414"))
TASK_OPERATIONS = frozenset((
    "v058.admission.worker", "v058.admission.run_one",
    "v058.container.create", "v058.container.start", "v058.scorer.score_request",
    "v058.rescore.run_one",
))
BATCH_OPERATIONS = frozenset((
    "v058.admission.prepare", "v058.admission.execute",
    "v058.rescore.prepare", "v058.rescore.run", "v058.rescore.reconcile",
))
OPERATIONS = TASK_OPERATIONS | BATCH_OPERATIONS
EXPECTED_CONSTRAINTS = {
    "concurrency": 2,
    "per_container_cpus": 4,
    "per_container_memory_bytes": 16 * 1024**3,
    "per_container_swap_bytes": 0,
    "network_mode": "none",
    "host_mounts": False,
    "host_devices": False,
    "host_network_helper": False,
    "privileged": False,
    "cap_add": ["NET_ADMIN"],
    "cap_drop": ["ALL"],
    "no_new_privileges": True,
    "daemon_start_or_restart": False,
    "system_service_changes": False,
    "host_configuration_changes": False,
    "model_calls": 0,
    "candidate_changes": False,
    "official_test_changes": False,
    "maximum_controls": 8,
    "maximum_candidate_scores": 8,
}
SOURCE_PATHS = (
    "src/proworksim/software_benchmark_dispatch_v058.py",
    "src/proworksim/software_benchmark_grading_environment_v058.py",
    "src/proworksim/software_benchmark_grading_qualification_v058.py",
    "src/proworksim/software_benchmark_scorer_v058.py",
    "tools/check_ref_grading_environment_v058.py",
    "tools/repair_ref_grading_environment_v058.py",
    "tools/run_offline_scorer_v058.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
)


class ScopedDispatchDenied(SharedServerHold):
    """The current operation has no exact reviewed v058 authorization."""


def source_manifest():
    """Return identities of the exact project files covered by the authorization."""
    sources = []
    for name in SOURCE_PATHS:
        path = ROOT / name
        data = path.read_bytes()
        sources.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return sources


def _denied(entrypoint, reason):
    raise ScopedDispatchDenied(f"v058 scoped dispatch blocks {entrypoint}: {reason}")


def require_v058_dispatch_allowed(entrypoint, instance_id=None):
    """Fail closed unless this exact task and operation have a sealed human approval.

    The authorization does not itself reserve CPU/RAM or count completed jobs.
    The sealed controllers enforce the immutable four-control/eight-score plan,
    resource limits and no-replay rules; the provider enforces Docker options.
    A zero-argument instance resolver is evaluated only after the authorization
    and source checks, so a pending operation need not read its task plan first.
    """
    if entrypoint not in OPERATIONS:
        _denied(entrypoint, "operation is outside the fixed v058 allowlist")
    try:
        value = json.loads(AUTHORIZATION_FILE.read_bytes())
    except (OSError, ValueError) as error:
        _denied(entrypoint, "authorization unavailable or invalid: " + type(error).__name__)
    if not isinstance(value, dict) or value.get("version") != VERSION:
        _denied(entrypoint, "unrecognized authorization format")
    if value.get("status") != "approved":
        _denied(entrypoint, "pending explicit rootful-container-operation approval")
    authorization = value.get("explicit_rootful_container_authorization")
    if not isinstance(authorization, str) or not authorization.strip():
        _denied(entrypoint, "explicit rootful-container-operation approval is absent")
    if value.get("automatic_release") is not False:
        _denied(entrypoint, "automatic release is forbidden")
    for key, expected in (("tasks", TASKS), ("operations", OPERATIONS)):
        actual = value.get(key)
        if (not isinstance(actual, list) or any(not isinstance(item, str) for item in actual)
                or len(actual) != len(expected) or set(actual) != expected):
            _denied(entrypoint, "authorization changes the fixed " + key)
    # Canonical JSON also distinguishes booleans from numeric zero/one.
    if json.dumps(value.get("constraints"), sort_keys=True) != json.dumps(EXPECTED_CONSTRAINTS, sort_keys=True):
        _denied(entrypoint, "reviewed runtime constraints differ")
    hold = read_hold()
    if (hold.get("hold") is not True or hold.get("automatic_release") is not False
            or hold.get("release_authorization") is not None):
        _denied(entrypoint, "the incident-wide hold must remain intact")
    try:
        sources = source_manifest()
    except OSError as error:
        _denied(entrypoint, "sealed source unavailable: " + type(error).__name__)
    if value.get("sources") != sources:
        _denied(entrypoint, "source binding changed after approval")
    if callable(instance_id):
        try:
            instance_id = instance_id()
        except Exception as error:
            _denied(entrypoint, "instance resolver failed: " + type(error).__name__)
    if ((instance_id is None and entrypoint in TASK_OPERATIONS)
            or (instance_id is not None
                and (not isinstance(instance_id, str) or instance_id not in TASKS))):
        _denied(entrypoint, "an explicitly allowed instance is required")
    return value
