"""Narrow approval checks for the two remaining Requests rescoring tasks.

This module only reads sealed project files. It cannot authorize itself or
release the incident-wide hold. Container counts and connection/byte/deadline
budgets are additionally enforced by the sealed runner and transport.
"""
from __future__ import annotations

import hashlib
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import uuid

from .software_benchmark_shared_server_hold_v057 import SharedServerHold, read_hold

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION_FILE = ROOT / "config/v060-real-tls-rescore-authorization.json"
V058_AUTHORIZATION_FILE = ROOT / "config/v058-offline-rescore-authorization.json"
V059_AUTHORIZATION_FILE = ROOT / "config/v059-tls-diagnostic-authorization.json"
VERSION = "v060-scoped-original-ca-rescore-authorization-r1"
TASKS = frozenset(("psf__requests-1766", "psf__requests-1921"))
CONDITIONS = frozenset(("REF_B0500K", "REF_B2000K", "REF_B5000K", "REF_B10000K"))
TASK_OPERATIONS = frozenset((
    "v060.container.create", "v060.container.start", "v060.transport",
    "v060.admission.worker", "v060.scorer.score_request", "v060.rescore.run_one",
))
BATCH_OPERATIONS = frozenset(("v060.resolve", "v060.run", "v060.rescore.reconcile"))
OPERATIONS = TASK_OPERATIONS | BATCH_OPERATIONS
TARGET_HOST = "httpbin.org"
TARGET_PORTS = (80, 443)
BATCH_SUBPATH = "runs/software-benchmark-v060/original-ca-rescore-r1-20261025"
EXPECTED_CONSTRAINTS = {
    "concurrency": 2,
    "maximum_containers": 12,
    "maximum_controls": 4,
    "maximum_candidate_scores": 8,
    "per_container_cpus": 4,
    "per_container_memory_bytes": 16 * 1024**3,
    "per_container_swap_bytes": 0,
    "per_container_pids": 512,
    "network_mode": "none",
    "effective_egress": "Docker exec raw TCP transport to frozen public IPv4 httpbin.org:80,443",
    "target_hostname": TARGET_HOST,
    "target_ports": list(TARGET_PORTS),
    "dns": "existing resolver; one frozen resolution before container creation",
    "host_listener": False,
    "container_listener": "127.0.0.1:80,443",
    "maximum_tcp_connections_per_container": 512,
    "maximum_tcp_connections_total": 6144,
    "maximum_concurrent_tcp_connections_per_container": 16,
    "maximum_transfer_bytes_per_container": 64 * 1024**2,
    "maximum_transfer_bytes_total": 768 * 1024**2,
    "maximum_test_seconds_per_container": 1800,
    "maximum_transport_seconds_per_container": 1800,
    "maximum_seconds_per_container": 3600,
    "maximum_supervisor_seconds_per_worker": 3900,
    "connect_timeout_seconds": 10,
    "idle_timeout_seconds": 60,
    "automatic_transport_retry": False,
    "automatic_container_retry": False,
    "host_mounts": False,
    "host_devices": False,
    "published_ports": False,
    "privileged": False,
    "cap_add": ["NET_ADMIN", "NET_BIND_SERVICE"],
    "cap_drop": ["ALL"],
    "no_new_privileges": True,
    "daemon_start_or_restart": False,
    "host_configuration_changes": False,
    "host_namespace_or_mount_operations": False,
    "host_route_or_firewall_changes": False,
    "model_calls": 0,
    "candidate_changes": False,
    "official_test_changes": False,
    "ca_changes": False,
    "tls_termination": False,
    "tls_verification_disabled": False,
    "candidate_scores_require_task_gold_empty_qualification": True,
    "old_scoring_records_overwritten": False,
}
SOURCE_PATHS = (
    "src/proworksim/software_benchmark_rescore_policy_v060.py",
    "src/proworksim/software_benchmark_tcp_transport_v060.py",
    "src/proworksim/software_benchmark_tls_transport_v059.py",
    "src/proworksim/software_benchmark_tls_policy_v059.py",
    "src/proworksim/software_benchmark_grading_environment_v060.py",
    "src/proworksim/software_benchmark_scorer_v060.py",
    "src/proworksim/software_benchmark_grading_qualification_v060.py",
    "tools/check_legacy_requests_environment_v060.py",
    "tools/repair_legacy_requests_rescore_v060.py",
    "tools/reconcile_legacy_requests_rescore_v060.py",
    "tools/run_offline_scorer_v058.py",
    "src/proworksim/software_benchmark_grading_environment_v058.py",
    "src/proworksim/software_benchmark_grading_qualification_v058.py",
    "src/proworksim/software_benchmark_scorer_v058.py",
    "tools/repair_ref_grading_environment_v058.py",
    "src/proworksim/software_benchmark_queue_v056.py",
    "tools/analyze_ref_budget_results_v056.py",
    "src/proworksim/software_benchmark_shared_server_hold_v057.py",
    "config/v057-shared-server-hold.json",
    "config/v058-offline-rescore-authorization.json",
    "config/v059-tls-diagnostic-authorization.json",
)
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ScopedRescoreDenied(SharedServerHold):
    """This exact Docker and restricted-egress scope has not been approved."""


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def source_manifest():
    return [reference(ROOT / name) for name in SOURCE_PATHS]


def _checked_bytes(ref):
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "bytes"}:
        raise ValueError("Expected an exact immutable project reference")
    if not isinstance(ref["path"], str):
        raise ValueError("Project reference path must be text")
    path = Path(ref["path"])
    if not path.is_absolute() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Trusted rescoring inputs must be inside the project")
    data = path.read_bytes()
    if (type(ref["bytes"]) is not int or len(data) != ref["bytes"]
            or hashlib.sha256(data).hexdigest() != ref["sha256"]):
        raise ValueError("Trusted rescoring input differs from its frozen reference")
    return data


def _checked_json(ref):
    value = json.loads(_checked_bytes(ref))
    if not isinstance(value, dict):
        raise ValueError("Expected an immutable JSON object")
    return value


def validate_task_image(authorization, instance_id, image_id):
    """Check the exact old task image using read-only original request evidence."""
    if instance_id not in TASKS or not isinstance(image_id, str) or IMAGE_ID.fullmatch(image_id) is None:
        raise ValueError("Only exact original images for the two rescoring tasks are allowed")
    requests = authorization.get("original_requests")
    images = authorization.get("image_ids")
    if not isinstance(requests, dict) or set(requests) != TASKS or not isinstance(images, dict) or set(images) != TASKS:
        raise ValueError("Both original task/image bindings must be present")
    original = _checked_json(requests[instance_id])
    image = original.get("image", {})
    if (original.get("instance_id") != instance_id or image.get("instance_id") != instance_id
            or image.get("image_id") != image_id or images[instance_id] != image_id):
        raise ValueError("Rescoring image differs from its fixed original task")
    return original


def _validate_candidates(authorization):
    references = authorization.get("candidate_requests")
    if not isinstance(references, list) or len(references) != 8:
        raise ValueError("Exactly eight original candidate requests must be sealed")
    candidates, identities = [], set()
    for ref in references:
        request = _checked_json(ref)
        task, condition = request.get("instance_id"), request.get("condition_id")
        if (task not in TASKS or condition not in CONDITIONS
                or (task, condition) in identities
                or request.get("version") != "v056-ref-budget-score-request-r1"
                or request.get("arm") != "REF" or request.get("model") != "Qwen/Qwen3.5-9B"
                or request.get("thinking") is not True or request.get("endpoint") != "code"
                or type(request.get("attempt")) is not int or request["attempt"] != 1
                or request.get("preparation_only") is not False or request.get("actor_feedback") is not False):
            raise ValueError("Candidate request is not one of the eight fixed REF budget slots")
        if request.get("image", {}).get("image_id") != authorization["image_ids"][task]:
            raise ValueError("Candidate image differs from its fixed task")
        _checked_bytes(request.get("patch"))
        _checked_json(request.get("native_candidate_lock"))
        identities.add((task, condition))
        candidates.append(request)
    if identities != {(task, condition) for task in TASKS for condition in CONDITIONS}:
        raise ValueError("The exact two-task by four-budget panel is required")
    return candidates


def validate_candidate_request(authorization, original_request):
    """Require an unchanged original request or its exact frozen file reference.

    Runtime request additions are validated by the scorer separately; call this
    with the original request referenced by that recovery request.
    """
    candidates = _validate_candidates(authorization)
    if isinstance(original_request, dict) and set(original_request) == {"path", "sha256", "bytes"}:
        if original_request not in authorization["candidate_requests"]:
            raise ValueError("Original request reference is not in the approved eight-candidate panel")
        original_request = _checked_json(original_request)
    if not isinstance(original_request, dict) or original_request not in candidates:
        raise ValueError("Candidate differs from every sealed original request")
    return original_request


def batch_root(authorization):
    expected = (ROOT / BATCH_SUBPATH).resolve()
    if authorization.get("run_root") != str(expected):
        raise ValueError("Only the exact reviewed v060 batch root is allowed")
    return expected


def validate_run_root(path, area):
    """Pure path check for the fixed controls or candidate-score directory."""
    if area not in ("environment-admission", "requests-rescore"):
        raise ValueError("Unknown fixed rescoring area")
    expected = (ROOT / BATCH_SUBPATH / area).resolve()
    if Path(path).resolve() != expected:
        raise ValueError("Fresh arbitrary batch roots cannot replay this limited grant")
    return expected


def _validate_proposal(authorization):
    root = batch_root(authorization)
    proposal = _checked_json(authorization.get("proposal"))
    if proposal.get("version") != "v060-original-ca-live-rescore-proposal-r1":
        raise ValueError("Unrecognized immutable proposal")
    for field in ("tasks", "constraints", "original_requests", "image_ids", "candidate_requests",
                  "source_state", "run_root", "sources"):
        if proposal.get(field) != authorization.get(field):
            raise ValueError("Approved scope differs from the immutable proposal: " + field)
    if proposal.get("run_root") != str(root):
        raise ValueError("Proposal refers to another batch root")


def claim_container_slot(authorization, instance_id, kind, condition_id=None):
    """Consume one of exactly twelve attempts and one of two global active slots.

    Called immediately before Docker create, after all pure validation. Even a
    failed or uncertain create consumes the attempt. Leases are durable rather
    than PID-based, so a crashed worker cannot silently free a possibly live
    container. Only confirmed cleanup may release its matching lease.
    """
    current = require_v060_rescore_allowed("v060.container.create", instance_id)
    if current != authorization:
        raise ValueError("Authorization changed before the container claim")
    if kind in ("gold", "empty") and condition_id is None:
        key = "control-" + instance_id + "-" + kind
    elif kind == "candidate" and isinstance(condition_id, str) and condition_id in CONDITIONS:
        key = "candidate-" + instance_id + "-" + condition_id
    else:
        raise ValueError("Container claim is outside the four-control/eight-candidate plan")
    root = batch_root(authorization)
    claims = root / "container-claims"
    claims.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock_fd = os.open(claims / "allocation.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        claim_path = claims / (key + ".json")
        if claim_path.exists():
            raise ValueError("This exact container attempt has already been consumed")
        lease = next((claims / ("active-" + str(i) + ".json") for i in range(2)
                      if not (claims / ("active-" + str(i) + ".json")).exists()), None)
        if lease is None:
            raise ValueError("Two container slots remain active or have uncertain cleanup")
        record = {"version": VERSION, "key": key, "instance_id": instance_id, "kind": kind,
                  "condition_id": condition_id, "token": uuid.uuid4().hex,
                  "lease_path": str(lease), "authorization": reference(AUTHORIZATION_FILE)}
        data = json.dumps(record, sort_keys=True).encode()
        for path in (claim_path, lease):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                remaining = memoryview(data)
                while remaining:
                    count = os.write(fd, remaining)
                    if count <= 0:
                        raise OSError("Container claim write made no progress")
                    remaining = remaining[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
        directory_fd = os.open(claims, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return reference(claim_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def release_container_slot(claim_reference, *, quiet):
    """Release only the matching active lease after verified owned cleanup.

    This cleanup operation is permitted even after the approval closes; it
    never permits another create and never deletes the consumed attempt file.
    """
    if quiet is not True:
        return False
    record = _checked_json(claim_reference)
    claims = (ROOT / BATCH_SUBPATH / "container-claims").resolve()
    claim_path = Path(claim_reference["path"]).resolve()
    lease = Path(record.get("lease_path", "")).resolve()
    if (claim_path.parent != claims or record.get("version") != VERSION
            or claim_path.name != str(record.get("key")) + ".json"
            or lease not in (claims / "active-0.json", claims / "active-1.json")):
        raise ValueError("Unrecognized container cleanup lease")
    fd = os.open(claims / "allocation.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if not lease.exists():
            return True
        if lease.read_bytes() != Path(claim_reference["path"]).read_bytes():
            raise ValueError("Cleanup cannot release another container's active slot")
        lease.unlink()
        return True
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _denied(operation, reason):
    raise ScopedRescoreDenied(f"v060 scoped rescoring blocks {operation}: {reason}")


def require_v060_rescore_allowed(operation, instance_id=None):
    """Check explicit approval before any real resource or egress operation.

    Pure proposal preparation is deliberately not a privileged entrypoint and
    does not call this function. No environment variable can bypass this gate.
    """
    if operation not in OPERATIONS:
        _denied(operation, "operation is outside the fixed rescoring allowlist")
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
        _denied(operation, "reviewed rescoring constraints differ")
    hold = read_hold()
    if (hold.get("hold") is not True or hold.get("automatic_release") is not False
            or hold.get("release_authorization") is not None):
        _denied(operation, "the incident-wide hold must remain unchanged")
    try:
        for label, path, version in (
            ("v058", V058_AUTHORIZATION_FILE, "v058-scoped-offline-dispatch-authorization-r1"),
            ("v059", V059_AUTHORIZATION_FILE, "v059-scoped-tls-diagnostic-authorization-r1"),
        ):
            previous = json.loads(path.read_bytes())
            if previous.get("version") != version or previous.get("status") != "completed":
                _denied(operation, "the prior " + label + " authorization must remain completed")
        if authorization.get("sources") != source_manifest():
            _denied(operation, "rescoring source binding changed after approval")
        _validate_proposal(authorization)
        for task in TASKS:
            validate_task_image(authorization, task, authorization.get("image_ids", {}).get(task))
        _validate_candidates(authorization)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        _denied(operation, "fixed rescoring inputs are invalid: " + str(error))
    if callable(instance_id):
        try:
            instance_id = instance_id()
        except Exception as error:
            _denied(operation, "task resolver failed: " + type(error).__name__)
    if ((instance_id is None and operation in TASK_OPERATIONS)
            or (instance_id is not None and (not isinstance(instance_id, str) or instance_id not in TASKS))):
        _denied(operation, "an allowed rescoring task is required")
    return authorization


def validate_ipv4_targets(addresses):
    """Validate a bounded frozen DNS result without network access."""
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
    """Require the sealed destination ports and a frozen public numeric address."""
    targets = validate_ipv4_targets(frozen_addresses)
    if (not isinstance(address, tuple) or len(address) != 2 or type(address[1]) is not int
            or address[1] not in TARGET_PORTS or address[0] not in targets):
        raise ValueError("Connection target is outside the frozen httpbin.org port resolution")
    return address
