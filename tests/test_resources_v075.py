import pytest

from proworksim import software_benchmark_dispatch_v066 as original
from proworksim import software_benchmark_resources_v075 as revised
from proworksim.software_benchmark_episodes_v075 import EpisodeBindings
from proworksim.software_benchmark_grading_v075 import factory


def _guard(*args, **kwargs):
    return {"test_scope": "v075"}


def _policy():
    return revised.policy(_guard)


def _physical(module, memory=960):
    # The budget's original-code clone shares this private function namespace.
    original_code = next(cell.cell_contents for cell in module._budget.__closure__
                         if callable(cell.cell_contents) and getattr(cell.cell_contents, "__name__", "") == "_budget")
    original_code.__globals__["physical_capacity"] = lambda: {
        "passed": True, "memory_available_bytes": memory * revised.GIB,
        "disk_free_bytes": 4 * 1024 * revised.GIB}


def test_ten_api_four_qwen_four_models_and_two_graders_fit():
    policy = _policy()
    _physical(policy)
    # Baseline primary is implicit: 4CPU/16GiB; auxiliary is explicit.
    active = [{"reserved_cpu": 12, "reserved_memory_bytes": 96 * revised.GIB}] * 4
    active += [{"reserved_cpu": 6, "reserved_memory_bytes": 32 * revised.GIB}] * 14
    active += [{"reserved_cpu": 4, "reserved_memory_bytes": 16 * revised.GIB}]
    value = policy._budget(active, 8, 32 * revised.GIB)
    assert value["reserved_cpu_after"] == 148
    assert value["reserved_memory_bytes_after"] == 896 * revised.GIB
    assert original.CONSTRAINTS["maximum_combined_reserved_memory_bytes"] == 832 * revised.GIB


def test_eleventh_api_and_physical_low_memory_are_rejected():
    policy = _policy()
    _physical(policy)
    full = [{"reserved_cpu": 144, "reserved_memory_bytes": 880 * revised.GIB}]
    with pytest.raises(original.ResourceBusy):
        policy._budget(full, 6, 32 * revised.GIB)
    _physical(policy, memory=140)
    with pytest.raises(original.ResourceBusy):
        policy._budget([], 6, 32 * revised.GIB)


def test_denied_supplement_never_admits():
    def denied(*args, **kwargs):
        raise PermissionError("not sealed")
    policy = revised.policy(denied)
    with pytest.raises(PermissionError, match="not sealed"):
        policy._budget([], 6, 32 * revised.GIB)


def test_new_claims_record_revision_and_cannot_launch_models(tmp_path):
    policy = _policy()
    value = {"spec": {"role": "actor"}}
    policy._write_claim(tmp_path / "actor.json", value)
    assert value["supplemental_resource_revision"] == revised.VERSION
    with pytest.raises(PermissionError, match="reload"):
        policy._write_claim(tmp_path / "model.json", {"spec": {"role": "model"}})
    assert not (tmp_path / "model.json").exists()


def test_all_three_consumers_bind_same_new_budget_without_old_global_changes():
    bindings = EpisodeBindings(_guard)
    qwen, api = bindings.qwen, bindings.api
    assert qwen.run_episode.__globals__["policy"] is bindings.primary_policy
    assert qwen.OwnedActorPair._claim.__globals__["policy"] is bindings.primary_policy
    assert api.run_episode.__globals__["policy"] is bindings.api_policy
    assert bindings.api_policy.budget_for_actor.__globals__["primary"] is bindings.primary_policy
    grading = factory(_guard, primary_policy=bindings.primary_policy)
    assert grading.base.run_request.__globals__["policy"] is bindings.primary_policy
    assert grading.base.fixed_python is not recovery_original_fixed_python()
    assert original._budget.__globals__["CONSTRAINTS"]["maximum_combined_reserved_memory_bytes"] == 832 * revised.GIB


def recovery_original_fixed_python():
    from proworksim.software_benchmark_grading_recovery_v068 import original_grading
    return original_grading().fixed_python


def test_api_pair_and_container_limits_stay_intact():
    bindings = EpisodeBindings(_guard)
    assert bindings.api_policy.CONSTRAINTS["generation_pair_reserved_memory_bytes"] == 32 * revised.GIB
    assert bindings.api_policy.CONSTRAINTS["generation_pair_reserved_cpu"] == 6
    assert bindings.api.OwnedActorPair.create_container.__globals__["ROLES"] == {
        "actor": (4, 16 * revised.GIB, 512), "controller": (2, 16 * revised.GIB, 256)}
    assert bindings.api_policy.CONSTRAINTS["active_actor_limit"] == 18
    assert bindings.primary_policy.CONSTRAINTS["active_actor_limit"] == 18


def test_api_grader_headroom_uses_revised_primary_budget():
    bindings = EpisodeBindings(_guard)
    _physical(bindings.primary_policy)
    active = [{"reserved_cpu": 128, "reserved_memory_bytes": 816 * revised.GIB, "spec": {"role": "actor"}}]
    admitted = bindings.api_policy.budget_for_actor(active)
    assert admitted["reserved_memory_bytes_after"] == 896 * revised.GIB
    assert admitted["grader_headroom"]["missing_reserved_grader_slots"] == 2


def test_expanded_qwen_lane_uses_existing_cpu_slice(monkeypatch):
    monkeypatch.setattr(original, "cpu_set", lambda role, index=0: (role, index))
    policy = _policy()
    assert policy.cpu_set("actor", 17) == ("actor", 5)
    assert policy.cpu_set("controller", 12) == ("controller", 0)
    assert policy.cpu_set("grader", 3) == ("grader", 3)
    with pytest.raises(ValueError, match="0..17"):
        policy.cpu_set("actor", 18)
