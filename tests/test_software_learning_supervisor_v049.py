"""Finite dependency/resource policy tests; no process, model or GPU launch."""
import copy

import pytest

from proworksim.storage import digest, json_bytes
from scripts import software_learning_supervisor_v049 as supervisor
from scripts.run_ne_v021 import reference, write


def states(*complete):
    return {name: {"worker": name, "status": "complete" if name in complete else "not_started",
                   "attempted": name in complete} for name in supervisor.WORKERS}


def test_s0_collection_and_B_are_strict_dependencies_with_parallel_pair():
    value = states()
    assert supervisor.eligible_workers(value) == ["s0"]
    value["s0"].update(status="running", attempted=True)
    assert supervisor.eligible_workers(value) == []
    value["s0"]["status"] = "complete"
    assert supervisor.eligible_workers(value) == ["collect-LA", "collect-LB"]
    value["collect-LA"].update(status="complete", attempted=True, R=0)
    assert supervisor.eligible_workers(value) == ["collect-LB"]
    value["collect-LB"].update(status="complete", attempted=True, R=1)
    assert supervisor.eligible_workers(value) == ["update-B"]
    value["update-B"].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(value) == []


def test_supported_direction_releases_matched_Q_and_B_dev_then_each_Q_dev():
    value = states("s0", "collect-LA", "collect-LB", "update-B")
    direction = {"selected": True, "reliable_base_material": True}
    assert supervisor.eligible_workers(value, direction) == ["update-Q_plus", "update-Q_minus", "dev-B"]
    assert supervisor.apply_not_applicable(value, direction) == []
    value["update-Q_plus"].update(status="complete", attempted=True)
    value["update-Q_minus"].update(status="running", attempted=True)
    assert supervisor.eligible_workers(value, direction) == ["dev-B", "dev-Q_plus"]
    value["update-Q_minus"]["status"] = "complete"
    assert supervisor.eligible_workers(value, direction) == ["dev-B", "dev-Q_plus", "dev-Q_minus"]


@pytest.mark.parametrize("reliable", [False, True])
def test_absent_support_never_adds_samples_or_uses_saved_Q_quota(reliable):
    value = states("s0", "collect-LA", "collect-LB", "update-B")
    direction = {"selected": False, "reliable_base_material": reliable}
    disabled = supervisor.apply_not_applicable(value, direction)
    assert set(disabled) == {"update-Q_plus", "update-Q_minus", "dev-Q_plus", "dev-Q_minus"} | (set() if reliable else {"dev-B"})
    assert supervisor.eligible_workers(value, direction) == (["dev-B"] if reliable else [])
    assert all(value[name]["attempted"] is False and value[name]["elapsed_gpu_seconds"] == 0 for name in disabled)
    assert [name for name in value if name.startswith("collect-")] == ["collect-LA", "collect-LB"]


def test_no_support_cannot_relabel_a_started_branch_as_unattempted():
    value = states("s0", "collect-LA", "collect-LB", "update-B")
    value["update-Q_plus"].update(status="running", attempted=True)
    with pytest.raises(ValueError, match="cannot erase"):
        supervisor.apply_not_applicable(value, {"selected": False, "reliable_base_material": True})
    with pytest.raises(ValueError, match="consistent booleans"):
        supervisor.eligible_workers(value, {"selected": True, "reliable_base_material": False})


def test_each_training_step_has_bound_but_no_whole_window_deadline():
    assert supervisor.task_stop_reason({"kind": "training_step", "started_at": 10000}, now=10899, rss_bytes=0) is None
    assert supervisor.task_stop_reason({"kind": "training_step", "started_at": 10000}, now=10900, rss_bytes=0) == "single_task_budget"
    assert supervisor.task_stop_reason({"kind": "episode", "started_at": 10000}, now=16000, rss_bytes=0) == "episode_hard_deadline"
    assert supervisor.LIMITS["task_seconds"] == {"loading": 900, "episode": 6000, "boundary": 600, "training_step": 900}
    assert supervisor.GPU_ORDER == (3, 4, 5, 7) and supervisor.LIMITS["max_parallel_model_instances"] == 3
    assert supervisor.LIMITS["gpu_capacity_stability_seconds"] == 60
    assert supervisor.LIMITS["minimum_free_gpu_mib"] == supervisor.LIMITS["own_gpu_memory_mib"] == 57344
    assert supervisor.LIMITS["minimum_live_free_gpu_mib"] == 6144
    assert supervisor.LIMITS["host_rss_per_worker_bytes"] == 64 * 1024**3
    assert supervisor.LIMITS["artifact_bytes"] == 128 * 1024**3
    assert supervisor.LIMITS["minimum_volume_free_bytes"] == 20 * 1024**3


def test_direction_must_bind_completed_B_original_artifacts(tmp_path):
    value = states("s0", "collect-LA", "collect-LB", "update-B")
    plan = {"source": {"fixture": "frozen-v049"}}
    update = tmp_path / "update-B/actual/update/report.json"
    write(update, {"status": "zero_step_zero_actor_advantage_or_gradient", "fixture_only": True})
    write(tmp_path / "support.json", {"fixture_only": True})
    report = {"status": "complete", "success_boundary": True, "source_before": plan["source"],
        "source_after": plan["source"], "update_report": reference(update)}
    write(tmp_path / "update-B/actual/report.json", report)
    direction = {"selected": False, "reliable_base_material": True,
        "frozen_before_any_development": True, "B_update": report["update_report"],
        "support": reference(tmp_path / "support.json")}
    direction["seal_sha256"] = digest(json_bytes(direction))
    write(tmp_path / "direction.json", direction)
    assert supervisor.read_direction(tmp_path, value, plan) == direction
    changed = copy.deepcopy(direction)
    changed["selected"] = True
    write(tmp_path / "direction.json", changed)
    with pytest.raises(ValueError, match="seal"):
        supervisor.read_direction(tmp_path, value, plan)
    value["update-B"]["status"] = "running"
    with pytest.raises(ValueError, match="complete original boundary"):
        supervisor.read_direction(tmp_path, value, plan)


def test_old_or_already_attempted_workers_can_never_be_released():
    value = states()
    value["s0"]["attempted"] = True
    assert supervisor.eligible_workers(value) == []
    value["old-training-queue"] = {"status": "not_started"}
    with pytest.raises(ValueError, match="nine predeclared"):
        supervisor.eligible_workers(value)
