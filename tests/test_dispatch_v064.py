import json
import os
from pathlib import Path

import pytest

from proworksim import software_benchmark_dispatch_v064 as policy
from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_benchmark_shared_server_hold_v057 import SharedServerHold


@pytest.fixture
def claims(tmp_path, monkeypatch):
    monkeypatch.setattr(policy, "BATCH_ROOT", tmp_path)
    authorization = tmp_path / "authorization.json"
    authorization.write_text("{}")
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", authorization)
    resources = {}
    for index in range(12):
        for role in ("actor", "controller", "volume", "score"):
            resources[f"{role}-{index}"] = {"role": role, "slot_id": f"slot-{index}"}
    for index in range(6):
        resources[f"model-{index}"] = {"role": "model", "model_index": index}
    plan = write_new(tmp_path / "plan.json", {"resources": resources})
    monkeypatch.setattr(policy, "require_v064_allowed", lambda *_: {"plan": plan})
    monkeypatch.setattr(policy, "physical_capacity", lambda: {
        "passed": True, "memory_available_bytes": 2048 * policy.GIB,
        "disk_free_bytes": 2048 * policy.GIB})
    return tmp_path / "resource-claims"


def test_read_only_cpu_pool_partitions_are_disjoint(monkeypatch):
    monkeypatch.setattr(policy, "host_cpu_pool", lambda: list(range(176)))
    assert policy.cpu_set("actor", 0) == "4,5,6,7"
    assert policy.cpu_set("controller", 11) == "74,75"
    assert policy.cpu_set("grader", 3) == "88,89,90,91"
    assert policy.cpu_set("model", 5) == ",".join(map(str, range(152, 164)))
    slices = [("coordinator", 0)]
    slices += [(role, index) for index in range(12) for role in ("actor", "controller")]
    slices += [("grader", index) for index in range(4)] + [("model", index) for index in range(6)]
    selected = [int(cpu) for role, index in slices for cpu in policy.cpu_set(role, index).split(",")]
    assert len(selected) == len(set(selected)) == 164
    with pytest.raises(ValueError):
        policy.cpu_set("actor", 12)


def test_pending_or_foreign_grant_never_reaches_resource_claim(tmp_path, monkeypatch):
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps({"version": policy.VERSION, "status": "pending"}))
    monkeypatch.setattr(policy, "AUTHORIZATION_FILE", path)
    with pytest.raises(SharedServerHold, match="pending"):
        policy.require_v064_allowed("v064.run")
    with pytest.raises(SharedServerHold, match="outside"):
        policy.require_v064_allowed("v062.run")


def test_pair_capacity_reserved_once_and_release_order_cannot_free_controller(claims):
    actor = policy.claim_resource("actor-0")
    body = policy.load(actor)
    assert body["reserved_cpu"] == 6 and body["reserved_memory_bytes"] == 20 * policy.GIB
    volume = policy.claim_resource("volume-0")
    controller = policy.claim_resource("controller-0")
    assert policy.load(controller)["lane"] == body["lane"]
    assert policy.load(controller)["reserved_cpu"] == 0
    assert len(list(claims.glob("active-*.json"))) == 1
    assert policy.release_resource(actor, quiescent=False) is False
    assert policy.release_resource(actor, quiescent=True) is True
    assert Path(body["lease"]).exists()
    assert policy.release_resource(controller, quiescent=True) is True
    assert not Path(body["lease"]).exists()
    assert policy.release_resource(volume, quiescent=True) is True
    with pytest.raises(ValueError, match="already consumed"):
        policy.claim_resource("actor-0")
    replacement_lane = policy.load(policy.claim_resource("actor-1"))["lane"]
    assert replacement_lane == body["lane"]


def test_volume_cannot_start_before_capacity_or_after_actor_release(claims):
    with pytest.raises(FileNotFoundError):
        policy.claim_resource("volume-0")
    assert not (claims / "volume-0.json").exists()
    actor = policy.claim_resource("actor-0")
    policy.release_resource(actor, quiescent=True)
    with pytest.raises(policy.ResourceBusy):
        policy.claim_resource("volume-0")
    assert not (claims / "volume-0.json").exists()


def test_combined_models_pairs_graders_reject_before_consuming_identity(claims):
    for index in range(5):
        policy.reserve_model(index)
    for index in range(12):
        policy.claim_resource(f"actor-{index}")
    for index in range(4):
        policy.claim_resource(f"score-{index}")
    # 5 residents + 12 whole pairs + 4 graders + coordinator = 152 CPU, 800 GiB.
    active = [policy.load(policy.reference(path)) for path in claims.glob("active-*.json")]
    assert 4 + sum(item["reserved_cpu"] for item in active) == 152
    assert 16 * policy.GIB + sum(item["reserved_memory_bytes"] for item in active) == 800 * policy.GIB
    with pytest.raises(policy.ResourceBusy, match="Combined"):
        policy.reserve_model(5)
    assert not (claims / "model-5.json").exists()
    with pytest.raises(policy.ResourceBusy, match="lane"):
        policy.claim_resource("score-4")
    assert not (claims / "score-4.json").exists()


def test_memory_and_physical_floors_are_independent_admission_guards(claims, monkeypatch):
    with pytest.raises(policy.ResourceBusy, match="Combined"):
        policy._budget([], 0, 817 * policy.GIB)
    monkeypatch.setattr(policy, "physical_capacity", lambda: {
        "passed": True, "memory_available_bytes": 128 * policy.GIB,
        "disk_free_bytes": 2048 * policy.GIB})
    with pytest.raises(policy.ResourceBusy, match="memory/disk"):
        policy.claim_resource("actor-0")
    assert not (claims / "actor-0.json").exists()


def test_model_reservation_releases_only_its_own_once_consumed_identity(claims):
    model = policy.reserve_model(3)
    assert policy.load(model)["lane"] == 3
    assert policy.release_model(model, quiescent=False) is False
    assert policy.release_model(model, quiescent=True) is True
    with pytest.raises(ValueError, match="already consumed"):
        policy.reserve_model(3)
    actor = policy.claim_resource("actor-0")
    with pytest.raises(ValueError, match="Not a model"):
        policy.release_model(actor, quiescent=True)


def test_source_cache_detects_same_size_rewrite_even_if_mtime_restored(tmp_path):
    path = tmp_path / "source.json"
    path.write_text('{"x":1}')
    ref, stamp = policy.reference(path), path.stat()
    assert policy.load(ref) == {"x": 1}
    path.write_text('{"x":2}')
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(ValueError, match="frozen identity"):
        policy.checked(ref)


def test_payload_spool_is_reserved_on_disk_without_changing_pair_ram(claims, monkeypatch):
    monkeypatch.setattr(policy, "physical_capacity", lambda: {
        "passed": True, "memory_available_bytes": 2048 * policy.GIB,
        "disk_free_bytes": 134 * policy.GIB})
    first = policy.load(policy.claim_resource("actor-0"))
    assert first["reserved_spool_bytes"] == 4 * policy.GIB
    assert first["reserved_memory_bytes"] == 20 * policy.GIB
    with pytest.raises(policy.ResourceBusy, match="memory/disk"):
        policy.claim_resource("actor-1")
    assert not (claims / "actor-1.json").exists()
