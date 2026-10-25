import json
import copy
from pathlib import Path

import pytest

from proworksim import software_benchmark_dispatch_v061 as policy
from proworksim.software_benchmark_candidates_v054 import reference


@pytest.fixture
def approved(tmp_path, monkeypatch):
    root = tmp_path
    batch = root / "batch"
    batch.mkdir()
    config = root / "config"
    config.mkdir()
    for name in (
        "v058-offline-rescore-authorization.json",
        "v059-tls-diagnostic-authorization.json",
        "v060-real-tls-rescore-authorization.json",
    ):
        (config / name).write_text(json.dumps({"status": "completed"}))
    monkeypatch.setattr(policy, "ROOT", root)
    monkeypatch.setattr(policy, "BATCH_ROOT", batch)
    monkeypatch.setattr(policy, "PLAN_FILE", batch / "active-plan.json")
    monkeypatch.setattr(policy, "PREVIOUS_PLAN_FILE", batch / "plan.json")
    monkeypatch.setattr(policy, "CPU_POOL_FILE", batch / "host-cpu-pool.json")
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", config / "auth.json")
    monkeypatch.setattr(policy, "sources", lambda: [])
    monkeypatch.setattr(policy, "read_hold", lambda: {"hold": True, "release_authorization": None})
    resources = {
        "score-" + str(i): {
            "role": "score",
            "instance_id": "fixed-task",
            "original_slot_id": "fixed-" + str(i),
        }
        for i in range(3)
    }
    resources["volume-0"] = {"role": "volume", "instance_id": "fixed-task"}
    policy.CPU_POOL_FILE.write_text(json.dumps({"version": "v061-fixed-host-cpu-pool-r1",
        "cpus": list(range(100, 276)), "read_only_capture": True, "host_configuration_changed": False}))
    plan = {
        "version": policy.VERSION,
        "root": str(batch),
        "constraints": policy.CONSTRAINTS,
        "host_cpu_pool": reference(policy.CPU_POOL_FILE),
        "resources": resources,
        "environments": {"fixed-task": {}},
        "rows": [{"slot_id": "fixed-0", "instance_id": "fixed-task"}],
    }
    source = copy.deepcopy(plan)
    source["constraints"]["minimum_free_gpu_mib"] = 66560
    source["constraints"].pop("gpu_memory_utilization")
    policy.PREVIOUS_PLAN_FILE.write_text(json.dumps(source))
    plan.update(source_plan=reference(policy.PREVIOUS_PLAN_FILE), continuation_revision="model-memory-r3")
    policy.PLAN_FILE.write_text(json.dumps(plan))
    auth = {
        "version": policy.VERSION,
        "status": "approved",
        "explicit_rootful_authorization": "Synthetic CPU-only approval fixture",
        "explicit_model_memory_authorization": "Synthetic explicit 0.6 CPU fixture",
        "automatic_release": False,
        "constraints": policy.CONSTRAINTS,
        "sources": [],
        "plan": reference(policy.PLAN_FILE),
    }
    proposal = {
        "version": policy.VERSION,
        "plan": auth["plan"],
        "constraints": policy.CONSTRAINTS,
        "sources": [],
        "operations": sorted(policy.OPERATIONS),
    }
    proposal_path = batch / "proposal.json"
    proposal_path.write_text(json.dumps(proposal))
    auth["proposal"] = reference(proposal_path)
    policy.AUTHORIZATION_FILE.write_text(json.dumps(auth))
    return auth


@pytest.mark.parametrize("status", ["pending", "completed"])
def test_unapproved_or_closed_grant_cannot_consume_resource(approved, status):
    approved["status"] = status
    policy.AUTHORIZATION_FILE.write_text(json.dumps(approved))
    with pytest.raises(policy.SharedServerHold):
        policy.claim_resource("score-0")
    assert not (policy.BATCH_ROOT / "resource-claims").exists()


def test_fixed_scope_and_incident_hold_are_both_required(approved, monkeypatch):
    with pytest.raises(policy.SharedServerHold):
        policy.require_v061_allowed("v061.score", instance_id="foreign-task")
    with pytest.raises(policy.SharedServerHold):
        policy.require_v061_allowed("old.queue.restart")
    monkeypatch.setattr(
        policy,
        "read_hold",
        lambda: {"hold": False, "release_authorization": "unsafe broad release"},
    )
    with pytest.raises(policy.SharedServerHold):
        policy.require_v061_allowed("v061.run")


def test_durable_creation_claims_bound_concurrency_and_prevent_replay(approved):
    first = policy.claim_resource("score-0")
    policy.claim_resource("score-1")
    with pytest.raises(ValueError, match="capacity"):
        policy.claim_resource("score-2")
    assert policy.release_resource(first, quiescent=False) is False
    assert policy.release_resource(first, quiescent=True) is True
    policy.claim_resource("score-2")
    with pytest.raises(ValueError, match="already consumed"):
        policy.claim_resource("score-0")
    assert Path(first["path"]).exists()


def test_foreign_resource_and_mismatched_lease_are_rejected(approved):
    with pytest.raises(ValueError, match="not in the fixed"):
        policy.claim_resource("extra-actor")
    claim = policy.claim_resource("score-0")
    value = policy.load(claim)
    Path(value["lease"]).write_text("different owner")
    with pytest.raises(ValueError, match="another creation"):
        policy.release_resource(claim, quiescent=True)


def test_cleanup_can_release_own_capacity_after_grant_closes(approved):
    claim = policy.claim_resource("score-0")
    approved["status"] = "completed"
    policy.AUTHORIZATION_FILE.write_text(json.dumps(approved))
    assert policy.release_resource(claim, quiescent=True)


def test_source_or_plan_mutation_fails_closed(approved):
    policy.PLAN_FILE.write_text(policy.PLAN_FILE.read_text() + " ")
    with pytest.raises(policy.SharedServerHold, match="changed"):
        policy.require_v061_allowed("v061.run")


def test_frozen_cpu_pool_remains_usable_from_four_cpu_coordinator(approved, monkeypatch):
    monkeypatch.setattr(policy.os, "sched_getaffinity", lambda pid: {100, 101, 102, 103})
    assert len(policy.host_cpu_pool()) == 176
    assert policy.cpu_set("coordinator") == "100,101,102,103"
    roles = [("coordinator", 0), ("actor", 0), ("controller", 0), ("actor", 1),
             ("controller", 1), ("grader", 0), ("grader", 1), ("model", 0), ("model", 1)]
    allocated = [int(cpu) for role, index in roles for cpu in policy.cpu_set(role, index).split(",")]
    assert sorted(allocated) == list(range(100, 148))
    assert len(set(allocated)) == len(allocated)
    assert policy.cpu_set("grader", 1) == "120,121,122,123"
    with pytest.raises(ValueError, match="partition"):
        policy.cpu_set("model", 2)


def test_pool_mutation_is_rejected_before_resource_claim(approved):
    policy.CPU_POOL_FILE.write_text(policy.CPU_POOL_FILE.read_text() + " ")
    with pytest.raises(ValueError, match="Immutable"):
        policy.claim_resource("score-0")
    assert not (policy.BATCH_ROOT / "resource-claims").exists()


@pytest.mark.parametrize("changed", ["seed", "resources", "cpu_pool", "budget", "memory"])
def test_model_memory_equivalence_rejects_unrelated_plan_changes(approved, changed):
    source = policy.load(reference(policy.PREVIOUS_PLAN_FILE))
    active = policy.load(reference(policy.PLAN_FILE))
    assert policy.assert_model_memory_plan_equivalent(source, active)
    if changed == "seed":
        active["rows"][0]["seed"] = 99
    elif changed == "resources":
        active["resources"]["unexpected"] = {"role": "actor"}
    elif changed == "cpu_pool":
        active["host_cpu_pool"] = {"wrong": True}
    elif changed == "budget":
        active["constraints"]["generation_token_upper_bound"] += 1
    else:
        active["constraints"]["grader_memory_bytes"] += 1
    with pytest.raises(ValueError, match="more than"):
        policy.assert_model_memory_plan_equivalent(source, active)
