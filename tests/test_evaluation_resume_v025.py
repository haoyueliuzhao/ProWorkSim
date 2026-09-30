"""CPU-only controls for evaluation recovery; no model, signals or process launch."""

import copy
from pathlib import Path

import pytest

from proworksim.storage import read_json
from scripts.run_evaluation_resume_v025 import (
    other_stop_reason,
    validate,
    verify_completed_stage,
    worker_environment,
)
from scripts.evaluate_work_v022 import write


def test_new_worker_environment_routes_temp_and_imports_without_inheriting_replicas(
    tmp_path, monkeypatch
):
    plan_path = tmp_path / "worker-plan.json"
    write(plan_path, {"python_hash_seed": "123"})
    from scripts.evaluate_work_v022 import reference

    plan = {"worker_checkout": str(tmp_path / "frozen"), "worker_plan": reference(plan_path)}
    monkeypatch.setenv("PROWORKSIM_REPLICA_GPUS", "0,1")
    monkeypatch.setenv("PYTHONPATH", "/wrong-source")
    env = worker_environment(plan, tmp_path / "resume", 3)
    assert env["CUDA_VISIBLE_DEVICES"] == "3" and "PROWORKSIM_REPLICA_GPUS" not in env
    assert env["TMPDIR"] == env["TMP"] == env["TEMP"] == str(tmp_path / "resume/tmp")
    assert env["PYTHONPATH"].split(":") == [str(tmp_path / "frozen/src"), str(tmp_path / "frozen")]


def test_no_update_task_and_data_volume_reserve_are_enforced(tmp_path, monkeypatch):
    import scripts.run_evaluation_resume_v025 as module
    from collections import namedtuple

    Usage = namedtuple("Usage", "total used free")
    plan = {"run_root": str(tmp_path), "wall_deadline_at": 100000, "minimum_temp_free_bytes": 1024}
    summary, state = {"started_at": 0}, {"started_at": 0, "budget_seconds": 16000}
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: Usage(4096, 0, 4096))

    def stop(kind):
        return other_stop_reason(
            plan, summary, state, {"kind": kind, "started_at": 0}, now=100, host_rss=0, size=0
        )

    assert stop("episode") is None
    assert stop("update") == "unapproved_task_kind"
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: Usage(4096, 4096, 0))
    assert stop("episode") == "temporary_volume_reserve"


def test_changed_endpoint_cannot_be_published_as_success(tmp_path):
    from scripts.evaluate_work_v022 import reference

    marker = tmp_path / "marker.json"
    write(marker, {"actor_identity": {"adapter": "original"}})
    plan = {"worker_source": {"code_commit": "frozen"}, "base_marker": reference(marker)}
    result = {
        "status": "complete",
        "actor_steps": 3,
        "critic_steps": 3,
        "source_unchanged": True,
        "source_before": plan["worker_source"],
        "source_after": plan["worker_source"],
        "final_actor_identity": {"adapter": "original"},
    }
    path = tmp_path / "confirm_base/actual/report.json"
    write(path, result)
    verify_completed_stage(plan, tmp_path, "confirm_base")
    result["actor_steps"] = 4
    write(path, result)
    with pytest.raises(ValueError, match="3/3"):
        verify_completed_stage(plan, tmp_path, "confirm_base")


def test_real_bound_plan_keeps_previous_cost_and_only_remaining_evaluation_budget():
    # Small metadata and checkpoint-file digest reads only, no tensor deserialization.
    plan = read_json(Path("examples/id-vtdo-v25/r2-plan.json"))
    if not Path(plan["prior_supervisor"]["path"]).exists():
        pytest.skip("Local archived R1 evidence is not available in this checkout")
    validate(plan)
    changed = copy.deepcopy(plan)
    changed["resource_caps"]["confirm_base"] = 16200
    with pytest.raises(ValueError, match="subtract previous"):
        validate(changed)
    changed = copy.deepcopy(plan)
    changed["max_new_actor_steps"] = 1
    with pytest.raises(ValueError, match="no further training"):
        validate(changed)
