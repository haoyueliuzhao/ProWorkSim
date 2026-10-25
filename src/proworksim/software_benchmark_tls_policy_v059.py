"""Fail-closed approval and destination checks for two bounded TLS diagnostics.

This module does not resolve DNS, open sockets, create containers, or authorize
ordinary scoring. The runner and transport enforce the recorded resource and
connection limits after this project-level check; OS isolation remains separate.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import re

from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_FILE = ROOT / "config/v059-tls-diagnostic-authorization.json"
V058_AUTHORIZATION_FILE = ROOT / "config/v058-offline-rescore-authorization.json"
VERSION = "v059-scoped-tls-diagnostic-authorization-r1"
TASKS = frozenset(("psf__requests-1766", "psf__requests-1921"))
TASK_OPERATIONS = frozenset((
    "v059.container.create", "v059.container.start", "v059.transport", "v059.probe",
))
BATCH_OPERATIONS = frozenset(("v059.prepare", "v059.resolve", "v059.run"))
OPERATIONS = TASK_OPERATIONS | BATCH_OPERATIONS
TARGET_HOST = "httpbin.org"
TARGET_PORT = 443
EXPECTED_CONSTRAINTS = {
    "concurrency": 1,
    "maximum_containers": 2,
    "containers_per_task": 1,
    "per_container_cpus": 2,
    "per_container_memory_bytes": 4 * 1024**3,
    "per_container_swap_bytes": 0,
    "per_container_pids": 64,
    "network_mode": "none",
    "effective_egress": "Docker exec transport to frozen public IPv4 httpbin.org:443",
    "target_hostname": TARGET_HOST,
    "target_ports": [TARGET_PORT],
    "dns": "existing resolver; one frozen resolution before container creation",
    "host_listener": False,
    "container_listener": "127.0.0.1:443",
    "maximum_tcp_connections_per_container": 2,
    "maximum_tcp_connections_total": 4,
    "maximum_transfer_bytes_per_container": 2 * 1024**2,
    "maximum_transfer_bytes_total": 4 * 1024**2,
    "maximum_seconds_per_container": 120,
    "connect_timeout_seconds": 10,
    "idle_timeout_seconds": 15,
    "automatic_retry": False,
    "host_mounts": False,
    "host_devices": False,
    "published_ports": False,
    "privileged": False,
    "cap_add": ["NET_BIND_SERVICE"],
    "cap_drop": ["ALL"],
    "no_new_privileges": True,
    "daemon_start_or_restart": False,
    "host_configuration_changes": False,
    "host_namespace_or_mount_operations": False,
    "host_route_or_firewall_changes": False,
    "model_calls": 0,
    "official_scoring_calls": 0,
    "candidate_changes": False,
    "official_test_changes": False,
    "ca_changes": False,
    "tls_termination": False,
    "tls_verification_disabled": False,
}
SOURCE_PATHS = (
    "src/proworksim/software_benchmark_tls_policy_v059.py",
    "src/proworksim/software_benchmark_tls_transport_v059.py",
    "tools/check_legacy_requests_tls_v059.py",
    "tools/run_offline_scorer_v058.py",
    "src/proworksim/software_benchmark_grading_environment_v058.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
    "config/v058-offline-rescore-authorization.json",
)
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


class TLSDiagnosticDenied(SharedServerHold):
    """The exact limited Docker and egress operation has not been authorized."""


def source_manifest():
    result = []
    for name in SOURCE_PATHS:
        path = ROOT / name
        data = path.read_bytes()
        result.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    return result


def _denied(operation, reason):
    raise TLSDiagnosticDenied(f"v059 TLS diagnostic blocks {operation}: {reason}")


def _checked_json(reference):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256", "bytes"}:
        raise ValueError("Expected an exact immutable project reference")
    path = Path(reference["path"])
    if not path.is_absolute() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Trusted TLS inputs must be inside the project")
    data = path.read_bytes()
    if (type(reference["bytes"]) is not int or len(data) != reference["bytes"]
            or hashlib.sha256(data).hexdigest() != reference["sha256"]):
        raise ValueError("Trusted TLS input differs from its frozen reference")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Expected an immutable JSON object")
    return value


def validate_task_image(authorization, instance_id, image_id):
    """Check an image against the exact original request, without Docker access."""
    if instance_id not in TASKS or not isinstance(image_id, str) or IMAGE_ID.fullmatch(image_id) is None:
        raise ValueError("Only exact original images for the two diagnostic tasks are allowed")
    requests = authorization.get("original_requests")
    images = authorization.get("image_ids")
    if not isinstance(requests, dict) or set(requests) != TASKS or not isinstance(images, dict) or set(images) != TASKS:
        raise ValueError("Both original task/image bindings must be present")
    original = _checked_json(requests[instance_id])
    image = original.get("image", {})
    if (original.get("instance_id") != instance_id or image.get("instance_id") != instance_id
            or image.get("image_id") != image_id or images[instance_id] != image_id):
        raise ValueError("Diagnostic image differs from its fixed original task")
    return original


def require_tls_diagnostic_allowed(operation, instance_id=None):
    """Read explicit reviewed approval before any real diagnostic resource call."""
    if operation not in OPERATIONS:
        _denied(operation, "operation is outside the diagnostic-only allowlist")
    try:
        authorization = json.loads(AUTHORIZATION_FILE.read_bytes())
    except (OSError, ValueError) as error:
        _denied(operation, "authorization unavailable: " + type(error).__name__)
    if not isinstance(authorization, dict) or authorization.get("version") != VERSION:
        _denied(operation, "unrecognized authorization")
    if authorization.get("status") != "approved":
        _denied(operation, "explicit Docker and restricted-egress approval is pending or closed")
    approval = authorization.get("explicit_rootful_and_egress_authorization")
    if not isinstance(approval, str) or not approval.strip() or authorization.get("automatic_release") is not False:
        _denied(operation, "explicit Docker and egress approval is required; automatic release is forbidden")
    for name, expected in (("tasks", TASKS), ("operations", OPERATIONS)):
        actual = authorization.get(name)
        if (not isinstance(actual, list) or any(not isinstance(item, str) for item in actual)
                or len(actual) != len(expected) or set(actual) != expected):
            _denied(operation, "fixed " + name + " differ")
    if json.dumps(authorization.get("constraints"), sort_keys=True) != json.dumps(EXPECTED_CONSTRAINTS, sort_keys=True):
        _denied(operation, "reviewed diagnostic constraints differ")
    hold = read_hold()
    if (hold.get("hold") is not True or hold.get("automatic_release") is not False
            or hold.get("release_authorization") is not None):
        _denied(operation, "the incident-wide hold must remain unchanged")
    try:
        previous = json.loads(V058_AUTHORIZATION_FILE.read_bytes())
        if (previous.get("version") != "v058-scoped-offline-dispatch-authorization-r1"
                or previous.get("status") != "completed"):
            _denied(operation, "the prior v058 authorization must remain completed")
        if authorization.get("sources") != source_manifest():
            _denied(operation, "diagnostic source binding changed after approval")
        for task in TASKS:
            validate_task_image(authorization, task, authorization.get("image_ids", {}).get(task))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        _denied(operation, "fixed diagnostic inputs are invalid: " + str(error))
    if callable(instance_id):
        try:
            instance_id = instance_id()
        except Exception as error:
            _denied(operation, "task resolver failed: " + type(error).__name__)
    if ((instance_id is None and operation in TASK_OPERATIONS)
            or (instance_id is not None and (not isinstance(instance_id, str) or instance_id not in TASKS))):
        _denied(operation, "an allowed diagnostic task is required")
    return authorization


def validate_ipv4_targets(addresses):
    """Validate a bounded DNS result without resolving or connecting to anything."""
    if not isinstance(addresses, (list, tuple)) or not 1 <= len(addresses) <= 16:
        raise ValueError("Require a bounded, nonempty frozen public IPv4 result")
    result = set()
    for address in addresses:
        if not isinstance(address, str):
            raise ValueError("Only literal public IPv4 text is allowed")
        try:
            ip = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError as error:
            raise ValueError("Only literal public IPv4 text is allowed") from error
        if (str(ip) != address or not ip.is_global or ip.is_private or ip.is_loopback
                or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            raise ValueError("Non-public or special-use network destinations are forbidden")
        result.add(address)
    return tuple(sorted(result, key=lambda value: int(ipaddress.IPv4Address(value))))


def validate_connect_target(address, frozen_addresses):
    """A socket address must be an approved literal IP:443, never a new hostname."""
    targets = validate_ipv4_targets(frozen_addresses)
    if (not isinstance(address, tuple) or len(address) != 2 or type(address[1]) is not int
            or address[1] != TARGET_PORT or address[0] not in targets):
        raise ValueError("Connection target is outside the frozen httpbin.org:443 resolution")
    return address
