from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_resources_v076 as previous
from proworksim import software_benchmark_resources_v079 as revised
from proworksim.software_benchmark_episodes_v079 import EpisodeBindings

GIB = revised.GIB


def _physical(memory=900, cpu=20):
    return {"memory_available_bytes": memory*GIB, "disk_free_bytes": 3000*GIB,
            "host_cpu_utilization_percent": cpu, "cpu_sample_fresh": True}


def _watchdog():
    return {"fresh": True, "admit": True}


def _guard(operation, **identity):
    assert operation == "v079.run"
    return {"CPU_test": True}


def _actor(index, model="DEEPSEEK"):
    return {"key": f"actor-{index}", "spec": {"role": "actor",
        "slot_id": f"v064:test-{index}:{model}_REF_B5000K:1"},
        "reserved_cpu": 6, "reserved_memory_bytes": 32*GIB,
        "reserved_spool_bytes": 4*GIB}


def test_four_ready_qwen_let_api_start_four_more_beside_four_starting():
    active = [_actor(i) for i in range(40)] + [_actor(i, "QWEN") for i in range(40, 44)]
    pending = [f"actor-{i}" for i in range(4)]
    old = previous.evaluate(active, _physical(), _watchdog(), pending=pending)
    new = revised.evaluate(active, _physical(), _watchdog(), pending=pending)
    assert old["additional_pair_slots"] == 0
    assert new["additional_pair_slots"] == 4 and new["api_generation_limit"] == 44
    assert new["maximum_starting_pairs"] == 8
    assert not new["qwen_refill_priority"]
    assert previous.MAX_STARTING_PAIRS == 4


def test_missing_qwen_pauses_api_refill_until_original_four_return():
    api = [_actor(i) for i in range(10)]
    qwen = [_actor(i, "QWEN") for i in range(10, 14)]
    missing = revised.evaluate(api+qwen[:3], _physical(), _watchdog(), pending=[])
    full = revised.evaluate(api+qwen, _physical(), _watchdog(), pending=[])
    assert missing["admit"] is True  # Grading can still use physical headroom.
    assert missing["qwen_refill_priority"] and missing["qwen_missing_actor_slots"] == 1
    assert missing["api_generation_limit"] == 10 and missing["additional_pair_slots"] == 0
    assert full["api_generation_limit"] == 18 and full["additional_pair_slots"] == 8


def test_eight_startup_slots_retain_real_memory_and_cpu_and_pressure_gates():
    actors = [_actor(i) for i in range(7)]
    pending = [item["key"] for item in actors]
    low = revised.evaluate(actors, _physical(543), _watchdog(), pending=pending, qwen_target=0)
    high = revised.evaluate(actors, _physical(544), _watchdog(), pending=pending, qwen_target=0)
    assert low["additional_pair_slots"] == 0 and high["additional_pair_slots"] == 1
    for physical, watchdog in [(_physical(cpu=85), _watchdog()),
                                (_physical(), {"fresh": False, "admit": True}),
                                (_physical(), {"fresh": True, "admit": False})]:
        state = revised.evaluate([], physical, watchdog, pending=[], qwen_target=0)
        assert not state["admit"] and state["additional_pair_slots"] == 0


def test_qwen_tail_and_closed_queue_release_only_unneeded_refill_places(tmp_path):
    path = tmp_path / "progress.json"
    assert revised.qwen_refill_target(path) == 4
    path.write_text(json.dumps({"phase": "running", "pending_generation": 0,
                               "active_generation": 2, "failure": None}))
    assert revised.qwen_refill_target(path) == 2
    path.write_text(json.dumps({"phase": "closed", "active_generation": 0, "failure": None}))
    assert revised.qwen_refill_target(path) == 0
    path.write_text(json.dumps({"phase": "stopped", "active_generation": 0,
                               "pending_generation": 0, "failure": {"unknown": True}}))
    assert revised.qwen_refill_target(path) == 4


def _fixture_policy(tmp_path, monkeypatch, count, *, target):
    rows = {f"actor-{index}": {"role": "actor",
            "slot_id": f"v064:test-{index}:DEEPSEEK_REF_B5000K:1"}
            for index in range(900001, 900001+count)}
    auth = {"plan": {"path": "/temporary/plan", "sha256": "0"*64, "bytes": 0}}
    monkeypatch.setattr(original, "require_v066_allowed", lambda *a, **kw: auth)
    policy = revised.policy(_guard, watchdog_guard=_watchdog,
                            capacity_probe=_physical, qwen_target=target)
    policy.claim_resource.__globals__.update(BATCH_ROOT=tmp_path,
                                            _cached_json=lambda ref: {"resources": rows})
    return policy, rows


def test_atomic_shared_lock_admits_at_most_eight_initializations(tmp_path, monkeypatch):
    policy, rows = _fixture_policy(tmp_path, monkeypatch, 16, target=0)
    def claim(key):
        try:
            return policy.claim_resource(key)
        except original.ResourceBusy:
            return None
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(claim, rows))
    assert sum(item is not None for item in results) == 8
    assert len(list((tmp_path / "resource-claims").glob("active-actor-*.json"))) == 8
    for item in filter(None, results):
        value = json.loads(Path(item["path"]).read_bytes())
        assert value["supplemental_resource_revision"] == revised.VERSION
        assert value["API_starting_pair_limit"] == 8
        assert value["reserved_cpu"] == 6 and value["reserved_memory_bytes"] == 32*GIB
        assert value["supplemental_resource_adapter"]["path"].endswith("software_benchmark_resources_v079.py")
    assert previous.MAX_STARTING_PAIRS == 4
    assert original.CONSTRAINTS["active_actor_limit"] == 12


def test_qwen_priority_is_rechecked_inside_actual_claim_lock(tmp_path, monkeypatch):
    policy, rows = _fixture_policy(tmp_path, monkeypatch, 1, target=4)
    claims = tmp_path / "resource-claims"
    claims.mkdir()
    for index in range(3):
        (claims / f"active-actor-{index}.json").write_text(json.dumps(_actor(index, "QWEN")))
    with pytest.raises(original.ResourceBusy):
        policy.claim_resource(next(iter(rows)))
    assert not (claims / (next(iter(rows))+".json")).exists()
    # This priority does not block a grader's 4CPU/16GiB admission.
    admission = policy._budget([_actor(i, "QWEN") for i in range(3)], 4, 16*GIB)
    assert admission["qwen_refill_priority"]


def test_api_binding_keeps_parent_and_object_limits_and_refuses_qwen():
    bindings = EpisodeBindings(_guard, watchdog_guard=_watchdog,
                               capacity_probe=_physical, qwen_target=0)
    assert bindings.primary_policy is bindings.api_policy
    assert bindings.api.run_episode.__globals__["policy"] is bindings.api_policy
    assert bindings.api.run_episode.__globals__["capacity"] is bindings.api_policy.physical_capacity
    assert bindings.api.OwnedActorPair._claim.__globals__["policy"] is bindings.api_policy
    assert bindings.api.OwnedActorPair.create_container.__globals__["ROLES"] == {
        "actor": (4, 16*GIB, 512), "controller": (2, 16*GIB, 256)}
    with pytest.raises(PermissionError):
        bindings.run_qwen({}, {})
    with pytest.raises(ValueError):
        bindings.run_api({"model_key": "DEEPSEEK", "input_plus_output_tokens": 10_000_000}, {})


def test_new_policy_refuses_accidental_qwen_creation(tmp_path):
    policy = revised.policy(_guard, watchdog_guard=_watchdog,
                            capacity_probe=_physical, qwen_target=0)
    with pytest.raises(PermissionError, match="only API"):
        policy._write_claim(tmp_path / "wrong.json", _actor(1, "QWEN"))
    assert not (tmp_path / "wrong.json").exists()
