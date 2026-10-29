from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_resources_v076 as revised
from proworksim.software_benchmark_episodes_v076 import EpisodeBindings
from proworksim.software_benchmark_grading_v076 import factory

GIB = revised.GIB


def _guard(*args, **kwargs):
    return {"test_scope": "v076"}


def _watchdog():
    return {"fresh": True, "admit": True}


def _physical(memory=900, cpu=20, fresh=True):
    return {"memory_available_bytes": memory * GIB,
            "disk_free_bytes": 3 * 1024 * GIB,
            "host_cpu_utilization_percent": cpu, "cpu_sample_fresh": fresh}


def _actor(index, model="DEEPSEEK"):
    return {"key": "actor-" + str(index), "spec": {"role": "actor",
        "slot_id": f"v064:test-{index}:{model}_REF_B5000K:1"},
        "reserved_cpu": 6, "reserved_memory_bytes": 32 * GIB,
        "reserved_spool_bytes": 4 * GIB}


def test_quota_sum_above_old_cap_is_diagnostic_not_admission():
    actors = [_actor(i) for i in range(40)] + [_actor(i, "QWEN") for i in range(40, 44)]
    state = revised.evaluate(actors, _physical(), _watchdog(), pending=[])
    assert state["reserved_cpu_total_diagnostic"] > 152
    assert state["reserved_memory_bytes_total_diagnostic"] > 832 * GIB
    assert state["admit"] and state["additional_pair_slots"] == 4
    assert state["api_generation_limit"] == 44
    assert state["quota_sum_is_hard_concurrency_gate"] is False


@pytest.mark.parametrize("cpu,fresh,watchdog", [
    (85, True, _watchdog()), (None, False, _watchdog()),
    (20, True, {"fresh": False, "admit": True}),
    (20, True, {"fresh": True, "admit": False}),
])
def test_busy_cpu_stale_sample_or_pressure_blocks_new_admission(cpu, fresh, watchdog):
    state = revised.evaluate([], _physical(cpu=cpu, fresh=fresh), watchdog, pending=[])
    assert not state["admit"] and state["additional_pair_slots"] == 0


def test_memory_floor_reserves_pending_and_two_graders():
    active = [_actor(1), _actor(2)]
    # 256 safety + 64 pending + 32 graders + one32 new =384 GiB.
    low = revised.evaluate(active, _physical(383), _watchdog(), pending=["actor-1", "actor-2"])
    high = revised.evaluate(active, _physical(384), _watchdog(), pending=["actor-1", "actor-2"])
    assert low["additional_pair_slots"] == 0
    assert high["additional_pair_slots"] == 1


def test_pending_materialization_only_uses_exact_trusted_ready(tmp_path):
    active = [_actor(1), _actor(2)]
    ready = tmp_path / "episodes/1/controller-ready.json"
    ready.parent.mkdir(parents=True)
    ready.write_text(json.dumps({"trusted_SDK_imports_complete": True,
        "version": "v064-private-native-controller-r1"}))
    cache = set()
    assert revised.pending_pairs(active, batch_root=tmp_path, materialized=cache) == ["actor-2"]
    ready.unlink()
    assert revised.pending_pairs(active, batch_root=tmp_path, materialized=cache) == ["actor-2"]
    wrong = tmp_path / "episodes/2/controller-ready.json"
    wrong.parent.mkdir(parents=True)
    wrong.write_text('{"trusted_SDK_imports_complete":false}')
    with pytest.raises(ValueError, match="Materialization"):
        revised.pending_pairs(active, batch_root=tmp_path, materialized=cache)


def test_global_lanes_and_api_ceiling_are_distinct():
    actors = [_actor(i) for i in range(48)] + [_actor(i, "QWEN") for i in range(48, 52)]
    state = revised.evaluate(actors, _physical(), _watchdog(), pending=[])
    assert state["api_generation_limit"] == 48
    assert state["additional_pair_slots"] == 0


def test_expanded_cpu_mapping_does_not_expand_physical_cpu_set(monkeypatch):
    monkeypatch.setattr(original, "cpu_set", lambda role, index=0: (role, index))
    policy = revised.policy(_guard, watchdog_guard=_watchdog, capacity_probe=_physical)
    assert policy.cpu_set("actor", 51) == ("actor", 3)
    assert policy.cpu_set("controller", 48) == ("controller", 0)
    assert policy.cpu_set("grader", 3) == ("grader", 3)
    with pytest.raises(ValueError):
        policy.cpu_set("actor", 52)


def test_missing_watchdog_and_new_model_claim_are_forbidden(tmp_path):
    with pytest.raises(TypeError):
        revised.policy(_guard, watchdog_guard=None)
    policy = revised.policy(_guard, watchdog_guard=_watchdog, capacity_probe=_physical)
    with pytest.raises(PermissionError):
        policy._write_claim(tmp_path / "model.json", {"spec": {"role": "model"}})
    assert not (tmp_path / "model.json").exists()


def test_new_episode_and_grading_bindings_preserve_old_sources():
    bindings = EpisodeBindings(_guard, watchdog_guard=_watchdog, capacity_probe=_physical)
    policy = bindings.primary_policy
    assert bindings.api_policy is policy
    for episode in (bindings.qwen, bindings.api):
        assert episode.run_episode.__globals__["policy"] is policy
        assert episode.run_episode.__globals__["capacity"] is policy.physical_capacity
        assert episode.OwnedActorPair._claim.__globals__["policy"] is policy
        assert episode.OwnedActorPair.create_container.__globals__["ROLES"] == {
            "actor": (4, 16 * GIB, 512), "controller": (2, 16 * GIB, 256)}
    grading = factory(_guard, primary_policy=policy)
    assert grading.base.run_request.__globals__["policy"] is policy
    assert original.CONSTRAINTS["maximum_combined_reserved_memory_bytes"] == 832 * GIB
    assert original.CONSTRAINTS["active_actor_limit"] == 12


def test_concurrent_claims_start_no_more_than_four_pairs(tmp_path, monkeypatch):
    rows = {f"actor-{index}": {"role": "actor", "slot_id": f"v064:test-{index}:DEEPSEEK_REF_B5000K:1"}
            for index in range(900001, 900009)}
    auth = {"plan": {"path": "/temporary/test-plan", "sha256": "0" * 64, "bytes": 0}}
    monkeypatch.setattr(original, "require_v066_allowed", lambda *a, **kw: auth)
    policy = revised.policy(_guard, watchdog_guard=_watchdog, capacity_probe=_physical)
    namespace = policy.claim_resource.__globals__
    namespace.update(BATCH_ROOT=tmp_path, _cached_json=lambda ref: {"resources": rows})

    def claim(key):
        try:
            return policy.claim_resource(key)
        except original.ResourceBusy:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, rows))
    assert sum(value is not None for value in results) == 4
    assert len(list((tmp_path / "resource-claims").glob("active-actor-*.json"))) == 4
    for value in results:
        if value:
            body = json.loads(Path(value["path"]).read_bytes())
            assert body["supplemental_resource_revision"] == revised.VERSION
            assert body["reserved_memory_bytes"] == 32 * GIB
