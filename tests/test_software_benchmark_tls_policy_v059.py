"""Synthetic-file and address checks; no Docker, DNS, sockets, or root actions."""
import copy
import hashlib
import json

import pytest

from proworksim import software_benchmark_shared_server_hold_v057 as old_hold
from proworksim import software_benchmark_tls_policy_v059 as policy


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode()
    path.write_bytes(data)
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


@pytest.fixture
def approved(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for name in policy.SOURCE_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic source\n")
    hold = root / "config/v057-shared-server-hold.json"
    write(hold, {"version": old_hold.VERSION, "hold": True,
                 "automatic_release": False, "release_authorization": None})
    previous = root / "config/v058-offline-rescore-authorization.json"
    write(previous, {"version": "v058-scoped-offline-dispatch-authorization-r1", "status": "completed"})
    auth = root / "config/v059-tls-diagnostic-authorization.json"
    monkeypatch.setattr(policy, "ROOT", root)
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", auth)
    monkeypatch.setattr(policy, "V058_AUTHORIZATION_FILE", previous)
    monkeypatch.setattr(old_hold, "HOLD_FILE", hold)
    refs, images = {}, {}
    for i, task in enumerate(sorted(policy.TASKS), 1):
        images[task] = "sha256:" + str(i) * 64
        refs[task] = write(root / "requests" / (task + ".json"), {
            "instance_id": task, "image": {"instance_id": task, "image_id": images[task]}})
    value = {"version": policy.VERSION, "status": "approved", "automatic_release": False,
             "explicit_rootful_and_egress_authorization": "Synthetic control only; no real approval",
             "tasks": sorted(policy.TASKS), "operations": sorted(policy.OPERATIONS),
             "constraints": copy.deepcopy(policy.EXPECTED_CONSTRAINTS),
             "original_requests": refs, "image_ids": images, "sources": policy.source_manifest()}
    write(auth, value)
    return auth, value, hold, previous


def test_missing_pending_or_incomplete_approval_denies_without_resolving_task(approved, monkeypatch):
    path, value, _, _ = approved
    calls = []
    monkeypatch.setenv("PROWORKSIM_V059_APPROVED", "1")
    for body in (None, "[]", "broken", json.dumps(value | {"status": "pending"}),
                 json.dumps(value | {"status": "completed"}),
                 json.dumps(value | {"explicit_rootful_and_egress_authorization": None})):
        if body is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(body)
        with pytest.raises(policy.TLSDiagnosticDenied):
            policy.require_tls_diagnostic_allowed("v059.transport", lambda: calls.append(True))
    assert calls == []


def test_approved_scope_is_diagnostic_only_and_bound_to_original_images(approved):
    _, value, _, _ = approved
    for operation in policy.BATCH_OPERATIONS:
        assert policy.require_tls_diagnostic_allowed(operation) == value
    for operation in policy.TASK_OPERATIONS:
        for task in policy.TASKS:
            assert policy.require_tls_diagnostic_allowed(operation, lambda task=task: task) == value
            original = policy.validate_task_image(value, task, value["image_ids"][task])
            assert original["instance_id"] == task
        for task in (None, "psf__requests-2931", "psf__requests-5414", ["psf__requests-1766"]):
            with pytest.raises(policy.TLSDiagnosticDenied):
                policy.require_tls_diagnostic_allowed(operation, task)
    for operation in ("v058.rescore.run", "v059.score", "v059.model", "new_v057_nat"):
        with pytest.raises(policy.TLSDiagnosticDenied):
            policy.require_tls_diagnostic_allowed(operation, "psf__requests-1766")


def test_modified_scope_and_original_image_inputs_fail_closed(approved):
    path, value, _, _ = approved
    for key, changed in (("concurrency", 2), ("target_hostname", "example.com"),
                         ("target_ports", [80, 443]), ("host_listener", True),
                         ("tls_termination", True), ("ca_changes", True),
                         ("model_calls", False), ("cap_add", ["NET_BIND_SERVICE", "SYS_ADMIN"]),
                         ("maximum_transfer_bytes_per_container", 4 * 1024**2)):
        altered = copy.deepcopy(value)
        altered["constraints"][key] = changed
        write(path, altered)
        with pytest.raises(policy.TLSDiagnosticDenied, match="constraints"):
            policy.require_tls_diagnostic_allowed("v059.run")
    write(path, value | {"sources": []})
    with pytest.raises(policy.TLSDiagnosticDenied, match="source binding"):
        policy.require_tls_diagnostic_allowed("v059.run")
    altered = copy.deepcopy(value)
    task = sorted(policy.TASKS)[0]
    altered["image_ids"][task] = "sha256:" + "9" * 64
    write(path, altered)
    with pytest.raises(policy.TLSDiagnosticDenied, match="fixed original task"):
        policy.require_tls_diagnostic_allowed("v059.run")
    write(path, value)
    request = policy.ROOT / "requests" / (task + ".json")
    request.write_text("{}")
    with pytest.raises(policy.TLSDiagnosticDenied, match="frozen reference"):
        policy.require_tls_diagnostic_allowed("v059.run")


def test_original_global_hold_and_closed_previous_scope_are_required(approved):
    path, value, hold, previous = approved
    write(hold, {"version": old_hold.VERSION, "hold": False, "automatic_release": False,
                 "release_authorization": "Synthetic broad release"})
    write(path, value | {"sources": policy.source_manifest()})
    with pytest.raises(policy.TLSDiagnosticDenied, match="incident-wide hold"):
        policy.require_tls_diagnostic_allowed("v059.run")
    write(hold, {"version": old_hold.VERSION, "hold": True, "automatic_release": False,
                 "release_authorization": None})
    write(previous, {"version": "v058-scoped-offline-dispatch-authorization-r1", "status": "approved"})
    write(path, value | {"sources": policy.source_manifest()})
    with pytest.raises(policy.TLSDiagnosticDenied, match="prior v058"):
        policy.require_tls_diagnostic_allowed("v059.run")


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
    "::1", "::ffff:8.8.8.8", "httpbin.org", "008.008.008.008", "192.0.2.1",
])
def test_special_addresses_cannot_enter_the_frozen_resolution(address):
    with pytest.raises(ValueError):
        policy.validate_ipv4_targets(["8.8.8.8", address])


def test_connect_requires_exact_frozen_public_ipv4_and_https_port():
    frozen = policy.validate_ipv4_targets(["8.8.8.8", "1.1.1.1", "8.8.8.8"])
    assert frozen == ("1.1.1.1", "8.8.8.8")
    assert policy.validate_connect_target(("8.8.8.8", 443), frozen) == ("8.8.8.8", 443)
    for target in (("9.9.9.9", 443), ("httpbin.org", 443), ("8.8.8.8", 80),
                   ("8.8.8.8", "443"), ("8.8.8.8", 443.0), ["8.8.8.8", 443],
                   ("8.8.8.8", 443, 0, 0)):
        with pytest.raises(ValueError):
            policy.validate_connect_target(target, frozen)
    for addresses in ([], ["8.8.8.8"] * 17, "8.8.8.8", [123]):
        with pytest.raises(ValueError):
            policy.validate_ipv4_targets(addresses)
