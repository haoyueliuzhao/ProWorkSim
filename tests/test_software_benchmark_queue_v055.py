"""Focused no-API controls for independent six-arm scheduling/isolation."""
import copy
import json

import pytest

from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_network_v055 import direct_environment_command, validate_actor_ready
from proworksim.software_benchmark_queue_v055 import CONDITIONS, VERSION, Coordinator, validate_plan
from proworksim.software_benchmark_scorer_v055 import condition_identity


def put(path, value):
    path.write_text(json.dumps(value))
    return reference(path)


def test_actor_requires_real_offline_namespace():
    ready = {"type": "ready", "isolation": {"pid": 1, "network_interfaces": ["lo"],
        "capabilities_all_zero": True, "no_new_privileges": True, "dumpable": False,
        "private_proc_pid1_root": "/", "nvidia_nodes": []},
        "rootfs_binding": {"official_task_admitted": True},
        "trusted_preload_counters": {"network_attempts": 0, "weight_files_opened": 0, "gpu_device_opens": 0}}
    assert validate_actor_ready(ready)["reverse_proxy"] is False
    bad = copy.deepcopy(ready)
    bad["isolation"]["network_interfaces"].append("eth0")
    with pytest.raises(ValueError):
        validate_actor_ready(bad)


def test_direct_child_environment_does_not_mutate_parent(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.local:1")
    import os
    command = direct_environment_command(["python", "controller.py"])
    assert "HTTPS_PROXY" in command and "NO_PROXY=*" in command
    assert os.environ["HTTPS_PROXY"] == "http://invalid.local:1"
    assert command[-2:] == ["python", "controller.py"]


def test_all_six_conditions_have_distinct_cache_identity():
    values = []
    for condition in CONDITIONS:
        arm, mode = condition.split("-", 1)
        request = {"condition_id": condition, "arm": arm, "thinking": mode == "thinking",
                   "slot_id": "v055-example-" + condition, "actor_feedback": False, "model": "deepseek-flash"}
        values.append(json.dumps(condition_identity(request), sort_keys=True))
    assert len(set(values)) == 6
    request["model"] = "deepseek-v4-flash"
    with pytest.raises(ValueError):
        condition_identity(request)


def test_plan_keeps_full_paired_panel_and_budget_fair_order(tmp_path, monkeypatch):
    import proworksim.software_benchmark_queue_v055 as queue
    monkeypatch.setattr(queue, "RUN_ROOT", tmp_path)
    slots = [{"slot_id": f"v055-{index}-{condition}", "condition_id": condition,
              "instance_id": f"task-{index}", "arm": condition.split("-", 1)[0]}
             for index in range(500) for condition in sorted(CONDITIONS)]
    conditions = {condition: put(tmp_path / (condition + ".json"), {"condition_id": condition})
                  for condition in CONDITIONS}
    plan = {"version": VERSION, "execution_authorized": True, "conditions": conditions,
        "slots": put(tmp_path / "slots.json", {"slots": slots}), "frozen_sources": [],
        "generation_concurrency": 24, "scoring_concurrency": 4, "maximum_api_concurrency": 64,
        "budget_cny": 2000, "ledger_path": str(tmp_path / "ledger.sqlite"), "queue_root": str(tmp_path / "queue")}
    plan["template"] = put(tmp_path / "template.json", {"all_solver_admissions_passed": True,
        "max_api_concurrency": 64, "ledger_path": plan["ledger_path"]})
    assert len(validate_plan(plan)[0]) == 3000
    slots[0], slots[6] = slots[6], slots[0]
    plan["slots"] = put(tmp_path / "unfair.json", {"slots": slots})
    with pytest.raises(ValueError, match="six-condition task blocks"):
        validate_plan(plan)


def test_worker_missing_is_deferred_without_retry(tmp_path, monkeypatch):
    import proworksim.software_benchmark_queue_v055 as queue
    coordinator = object.__new__(Coordinator)
    coordinator.state = {"exceptions": []}
    row = {"slot": {"slot_id": "v055-first"}}
    record = {"status": "running", "directory": str(tmp_path), "unit": "unit.service", "job": {"sha256": "a"}}
    monkeypatch.setattr(queue, "active", lambda unit: False)
    coordinator.collect(row, record, kind="generation")
    assert record["status"] == "technical_unknown"
    assert len(coordinator.state["exceptions"]) == 1
    coordinator.collect(row, record, kind="generation")
    assert len(coordinator.state["exceptions"]) == 1


def test_active_worker_is_adopted_without_new_launch(tmp_path, monkeypatch):
    import proworksim.software_benchmark_queue_v055 as queue
    coordinator = object.__new__(Coordinator)
    coordinator.state = {"exceptions": []}
    record = {"status": "running", "directory": str(tmp_path), "unit": "unit.service"}
    monkeypatch.setattr(queue, "active", lambda unit: True)
    coordinator.collect({"slot": {"slot_id": "v055-active"}}, record, kind="generation")
    assert record["status"] == "running" and not coordinator.state["exceptions"]
