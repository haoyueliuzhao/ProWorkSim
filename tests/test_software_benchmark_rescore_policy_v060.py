"""Pure file/address controls; no sockets, DNS, Docker, or host configuration."""
import copy
import hashlib
import json

import pytest

from proworksim import software_benchmark_shared_server_hold_v057 as old_hold
from proworksim import software_benchmark_rescore_policy_v060 as policy


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
    diagnostic = root / "config/v059-tls-diagnostic-authorization.json"
    write(previous, {"version": "v058-scoped-offline-dispatch-authorization-r1", "status": "completed"})
    write(diagnostic, {"version": "v059-scoped-tls-diagnostic-authorization-r1", "status": "completed"})
    auth = root / "config/v060-real-tls-rescore-authorization.json"
    monkeypatch.setattr(policy, "ROOT", root)
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", auth)
    monkeypatch.setattr(policy, "V058_AUTHORIZATION_FILE", previous)
    monkeypatch.setattr(policy, "V059_AUTHORIZATION_FILE", diagnostic)
    monkeypatch.setattr(old_hold, "HOLD_FILE", hold)
    refs, images, candidates = {}, {}, []
    for i, task in enumerate(sorted(policy.TASKS), 1):
        images[task] = "sha256:" + str(i) * 64
        for condition in sorted(policy.CONDITIONS):
            name = task + "-" + condition
            lock = write(root / "locks" / (name + ".json"), {"slot": name})
            patch = write(root / "patches" / (name + ".patch"), {"synthetic_patch": name})
            request = {"version": "v056-ref-budget-score-request-r1", "instance_id": task,
                       "condition_id": condition, "arm": "REF", "model": "Qwen/Qwen3.5-9B",
                       "thinking": True, "endpoint": "code", "attempt": 1,
                       "preparation_only": False, "actor_feedback": False,
                       "image": {"instance_id": task, "image_id": images[task]},
                       "patch": patch, "native_candidate_lock": lock}
            ref = write(root / "requests" / (name + ".json"), request)
            candidates.append(ref)
            refs.setdefault(task, ref)
    value = {"version": policy.VERSION, "status": "approved", "automatic_release": False,
             "explicit_rootful_and_egress_authorization": "Synthetic CPU control only; no real approval",
             "tasks": sorted(policy.TASKS), "operations": sorted(policy.OPERATIONS),
             "constraints": copy.deepcopy(policy.EXPECTED_CONSTRAINTS),
             "original_requests": refs, "image_ids": images, "candidate_requests": candidates,
             "run_root": str(root / policy.BATCH_SUBPATH),
             "source_state": {"path": str(root / "frozen-state.json"), "sha256": "0" * 64, "bytes": 0},
             "sources": policy.source_manifest()}
    proposal = {"version": "v060-original-ca-live-rescore-proposal-r1",
                **{key: value[key] for key in ("tasks", "constraints", "original_requests", "image_ids",
                     "candidate_requests", "source_state", "run_root", "sources")}}
    value["proposal"] = write(root / "artifacts" / "proposal.json", proposal)
    write(auth, value)
    return auth, value, hold, previous, diagnostic


def test_missing_pending_or_closed_denies_before_task_resolver(approved, monkeypatch):
    path, value, *_ = approved
    calls = []
    monkeypatch.setenv("PROWORKSIM_V060_APPROVED", "1")
    for body in (None, "[]", "broken", json.dumps(value | {"status": "pending"}),
                 json.dumps(value | {"status": "completed"}),
                 json.dumps(value | {"explicit_rootful_and_egress_authorization": None})):
        if body is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(body)
        with pytest.raises(policy.ScopedRescoreDenied):
            policy.require_v060_rescore_allowed("v060.transport", lambda: calls.append(True))
    assert calls == []


def test_exact_scope_accepts_only_two_tasks_eight_original_candidates(approved):
    _, value, *_ = approved
    for operation in policy.BATCH_OPERATIONS:
        assert policy.require_v060_rescore_allowed(operation) == value
    for operation in policy.TASK_OPERATIONS:
        for task in policy.TASKS:
            assert policy.require_v060_rescore_allowed(operation, lambda task=task: task) == value
        for task in (None, "psf__requests-2931", "psf__requests-5414", ["psf__requests-1766"]):
            with pytest.raises(policy.ScopedRescoreDenied):
                policy.require_v060_rescore_allowed(operation, task)
    for operation in ("v058.rescore.run", "v059.probe", "v060.model", "new_v057_nat", "v060.prepare"):
        with pytest.raises(policy.ScopedRescoreDenied):
            policy.require_v060_rescore_allowed(operation, "psf__requests-1766")
    for ref in value["candidate_requests"]:
        original = json.loads(open(ref["path"]).read())
        assert policy.validate_candidate_request(value, ref) == original
        assert policy.validate_candidate_request(value, original) == original
        with pytest.raises(ValueError, match="differs"):
            policy.validate_candidate_request(value, original | {"condition_id": "changed"})


@pytest.mark.parametrize("key, changed", [
    ("concurrency", 3), ("target_hostname", "example.com"), ("target_ports", [80, 443, 8080]),
    ("host_listener", True), ("tls_termination", True), ("ca_changes", True),
    ("model_calls", False), ("cap_add", ["NET_ADMIN", "NET_BIND_SERVICE", "SYS_ADMIN"]),
    ("maximum_transfer_bytes_per_container", 128 * 1024**2),
    ("maximum_controls", 5), ("maximum_candidate_scores", 9),
    ("maximum_seconds_per_container", 7200), ("maximum_concurrent_tcp_connections_per_container", 17),
])
def test_widened_constraints_deny(approved, key, changed):
    path, value, *_ = approved
    altered = copy.deepcopy(value)
    altered["constraints"][key] = changed
    write(path, altered)
    with pytest.raises(policy.ScopedRescoreDenied, match="constraints"):
        policy.require_v060_rescore_allowed("v060.run")


def test_sources_task_image_candidate_and_patch_are_immutable(approved):
    path, value, *_ = approved
    for altered in (value | {"sources": []},
                    value | {"candidate_requests": value["candidate_requests"][:-1]},
                    value | {"candidate_requests": [value["candidate_requests"][0]] * 8}):
        write(path, altered)
        with pytest.raises(policy.ScopedRescoreDenied):
            policy.require_v060_rescore_allowed("v060.run")
    altered = copy.deepcopy(value)
    altered["image_ids"][sorted(policy.TASKS)[0]] = "sha256:" + "9" * 64
    write(path, altered)
    with pytest.raises(policy.ScopedRescoreDenied, match="image_ids"):
        policy.require_v060_rescore_allowed("v060.run")
    with pytest.raises(ValueError, match="fixed original task"):
        task = sorted(policy.TASKS)[0]
        policy.validate_task_image(altered, task, altered["image_ids"][task])
    write(path, value)
    original = json.loads(open(value["candidate_requests"][0]["path"]).read())
    with open(original["patch"]["path"], "wb") as stream:
        stream.write(b"changed patch")
    with pytest.raises(policy.ScopedRescoreDenied, match="frozen reference"):
        policy.require_v060_rescore_allowed("v060.run")


def test_original_hold_and_both_completed_grants_are_required(approved):
    path, value, hold, previous, diagnostic = approved
    write(hold, {"version": old_hold.VERSION, "hold": False, "automatic_release": False,
                 "release_authorization": "Synthetic broad release"})
    write(path, value | {"sources": policy.source_manifest()})
    with pytest.raises(policy.ScopedRescoreDenied, match="incident-wide hold"):
        policy.require_v060_rescore_allowed("v060.run")
    write(hold, {"version": old_hold.VERSION, "hold": True, "automatic_release": False,
                 "release_authorization": None})
    for label, prior in (("v058", previous), ("v059", diagnostic)):
        old = json.loads(prior.read_text())
        write(prior, old | {"status": "approved"})
        write(path, value | {"sources": policy.source_manifest()})
        with pytest.raises(policy.ScopedRescoreDenied, match="prior " + label):
            policy.require_v060_rescore_allowed("v060.run")
        write(prior, old)


def test_fixed_batch_root_proposal_and_claims_bound_replay_and_global_concurrency(approved):
    path, value, *_ = approved
    task = sorted(policy.TASKS)[0]
    first = policy.claim_container_slot(value, task, "gold")
    second = policy.claim_container_slot(value, task, "empty")
    with pytest.raises(ValueError, match="Two container slots"):
        policy.claim_container_slot(value, task, "candidate", "REF_B0500K")
    assert policy.release_container_slot(first, quiet=False) is False
    with pytest.raises(ValueError, match="Two container slots"):
        policy.claim_container_slot(value, task, "candidate", "REF_B0500K")
    assert policy.release_container_slot(first, quiet=True) is True
    assert policy.release_container_slot(first, quiet=True) is True
    with pytest.raises(ValueError, match="already been consumed"):
        policy.claim_container_slot(value, task, "gold")
    third = policy.claim_container_slot(value, task, "candidate", "REF_B0500K")
    with pytest.raises(ValueError, match="another container"):
        policy.release_container_slot(first, quiet=True)
    assert policy.release_container_slot(second, quiet=True) is True
    # A closed grant cannot create more containers, but exact cleanup remains possible.
    write(path, value | {"status": "completed"})
    with pytest.raises(policy.ScopedRescoreDenied):
        policy.claim_container_slot(value, task, "candidate", "REF_B2000K")
    assert policy.release_container_slot(third, quiet=True) is True
    claims = policy.ROOT / policy.BATCH_SUBPATH / "container-claims"
    assert len([p for p in claims.glob("*.json") if not p.name.startswith("active-")]) == 3


def test_changed_proposal_and_arbitrary_new_batch_root_deny(approved):
    path, value, *_ = approved
    altered = copy.deepcopy(value)
    altered["run_root"] += "-replay"
    write(path, altered)
    with pytest.raises(policy.ScopedRescoreDenied, match="exact reviewed"):
        policy.require_v060_rescore_allowed("v060.run")
    write(path, value)
    proposal = policy.ROOT / "artifacts" / "proposal.json"
    proposal.write_text("{}")
    with pytest.raises(policy.ScopedRescoreDenied, match="frozen reference"):
        policy.require_v060_rescore_allowed("v060.run")
    with pytest.raises(ValueError, match="arbitrary"):
        policy.validate_run_root(policy.ROOT / "runs/software-benchmark-v060/replay", "requests-rescore")


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.0.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
    "::1", "::ffff:8.8.8.8", "httpbin.org", "008.008.008.008", "192.0.2.1",
])
def test_nonpublic_or_nonnumeric_destinations_deny(address):
    with pytest.raises(ValueError):
        policy.validate_ipv4_targets(["8.8.8.8", address])


def test_connect_target_must_match_frozen_literal_and_reviewed_port():
    frozen = policy.validate_ipv4_targets(["8.8.8.8", "1.1.1.1", "8.8.8.8"])
    assert frozen == ("1.1.1.1", "8.8.8.8")
    assert policy.validate_connect_target(("8.8.8.8", 443), frozen) == ("8.8.8.8", 443)
    assert policy.validate_connect_target(("8.8.8.8", 80), frozen) == ("8.8.8.8", 80)
    for target in (("9.9.9.9", 443), ("httpbin.org", 443), ("8.8.8.8", 8080),
                   ("8.8.8.8", "443"), ("8.8.8.8", 443.0), ["8.8.8.8", 443],
                   ("8.8.8.8", 443, 0, 0)):
        with pytest.raises(ValueError):
            policy.validate_connect_target(target, frozen)
