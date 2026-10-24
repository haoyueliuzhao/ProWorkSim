import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def module():
    path = Path(__file__).resolve().parents[1] / "tools/prepare_ref_budget_cache_v056.py"
    spec = importlib.util.spec_from_file_location("ref_budget_cache_test", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_absent_payload_is_evicted_not_qualified(monkeypatch, tmp_path):
    cache = module()
    monkeypatch.setattr(cache, "STATE", tmp_path)
    folder = tmp_path / "task"
    folder.mkdir()
    plan_ref, mapping = {"sha256": "plan"}, {"sha256": "mapping"}
    (folder / "qualified.json").write_text(json.dumps({"plan": plan_ref,
        "baseline_mapping": mapping, "rootfs": str(tmp_path / "absent-rootfs")}))
    result = cache.status_for(plan_ref, {"task_ids": ["task"]}, {"task": mapping}, "task")
    assert result["status"] == "evicted"


def test_low_disk_leaves_task_unclaimed(monkeypatch, tmp_path):
    cache = module()
    monkeypatch.setattr(cache, "STATE", tmp_path / "state")
    monkeypatch.setattr(cache.shutil, "disk_usage", lambda _: SimpleNamespace(free=255 * 1024**3))
    monkeypatch.setattr(cache, "ensure_native_instance", lambda *a, **k: pytest.fail("No preparation expected"))
    result = cache.prepare_one({}, {"task_ids": ["task"]}, {}, "task")
    assert result["status"] == "resource_wait"
    assert not (cache.STATE / "task").exists()


def test_outside_panel_is_never_prepared(monkeypatch, tmp_path):
    cache = module()
    monkeypatch.setattr(cache, "STATE", tmp_path)
    with pytest.raises(ValueError, match="outside"):
        cache.prepare_one({}, {"task_ids": ["task"]}, {}, "not-selected")


def _final_consumers(cache, monkeypatch, tmp_path):
    plan_ref = {"sha256": "plan"}
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps({"plan": plan_ref}))
    slots = [{"slot_id": f"task-{i}", "instance_id": "task", "condition_id": f"budget-{i}"}
             for i in range(4)]
    slot_path = tmp_path / "slots.json"
    slot_path.write_text(json.dumps({"slots": slots}))
    plan = {"task_ids": ["task"], "slots": {"path": str(slot_path)}}
    state = {"version": "v056-ref-budget-queue-r1", "binding": {"path": str(binding)},
             "rows": [], "jobs": {}}
    for i, slot in enumerate(slots):
        path = tmp_path / f"result-{i}.json"
        path.write_text(json.dumps({"slot_id": slot["slot_id"], "resource_release": {
            "released": True, "populated": False, "slice": "slice"}, "finally_stopped_scopes": []}))
        job_id = f"job-{i}"
        state["jobs"][job_id] = {"instance_id": "task", "slot_id": slot["slot_id"],
            "status": "completed", "host_process": {"pid": 10 + i, "start_ticks": 100}}
        state["rows"].append({"slot": slot, "generation": {"status": "closed",
            "quiescent": True, "result": {"path": str(path)}, "job_id": job_id},
            "score": {"status": "not_applicable"}})
    monkeypatch.setattr(cache, "checked", lambda ref: Path(ref["path"]))
    monkeypatch.setattr(cache, "_cgroup_quiet", lambda _: True)
    monkeypatch.setattr(cache, "_process_gone", lambda _: True)
    return plan_ref, plan, state


def test_reclaim_requires_all_four_exact_consumers(monkeypatch, tmp_path):
    cache = module()
    plan_ref, plan, state = _final_consumers(cache, monkeypatch, tmp_path)
    assert len(cache.reclaim_evidence(plan_ref, plan, state, "task")) == 4
    state["rows"].pop()
    with pytest.raises(ValueError, match="four fixed"):
        cache.reclaim_evidence(plan_ref, plan, state, "task")


def test_reclaim_refuses_unproved_or_live_writers(monkeypatch, tmp_path):
    cache = module()
    plan_ref, plan, state = _final_consumers(cache, monkeypatch, tmp_path)
    state["rows"][0]["generation"]["quiescent"] = False
    with pytest.raises(ValueError, match="quiescence"):
        cache.reclaim_evidence(plan_ref, plan, state, "task")
    state["rows"][0]["generation"]["quiescent"] = True
    monkeypatch.setattr(cache, "_process_gone", lambda _: False)
    with pytest.raises(ValueError, match="outer worker"):
        cache.reclaim_evidence(plan_ref, plan, state, "task")


def test_reclaim_waits_for_scoring_quiescence(monkeypatch, tmp_path):
    cache = module()
    plan_ref, plan, state = _final_consumers(cache, monkeypatch, tmp_path)
    state["rows"][0]["score"] = {"status": "deferred", "quiescent": False}
    with pytest.raises(ValueError, match="scorer lacks"):
        cache.reclaim_evidence(plan_ref, plan, state, "task")
