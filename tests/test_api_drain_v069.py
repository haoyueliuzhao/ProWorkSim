from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_drain_v069 as module
from proworksim.software_benchmark_candidates_v054 import reference


def test_unit_stop_requires_naturally_quiet_generation_and_all_children():
    progress = {"unix": 100, "phase": "waiting", "capacity_wait_reason": "invalid_concurrency_control",
                "effective_generation_limit": 0, "actual_generation_futures": 0}
    assert module.drain_ready(progress, [], [], [], now=101)[0]
    for index in range(3):
        reasons = [[], [], []]
        reasons[index] = ["still-owned"]
        assert not module.drain_ready(progress, *reasons, now=101)[0]
    assert not module.drain_ready({**progress, "actual_generation_futures": 1}, [], [], [], now=101)[0]
    assert not module.drain_ready(progress, [], [], [], now=400)[0]


def test_exact_user_unit_ownership(tmp_path, monkeypatch):
    monkeypatch.setattr(module.primary, "ROOT", tmp_path)
    entry = tmp_path / "tools/run_api_continuation_v068.py"
    entry.parent.mkdir()
    entry.write_text("fixture")
    old = tmp_path / "old"
    spec = {"unit": module.OLD_UNIT, "role": "api", "user_id": 123,
            "reporting_root": str(old), "entrypoint": reference(entry), "ownership_token": "a" * 32}
    properties = {"Description": "ProWorkSim v068 api coordinator " + "a" * 32,
                  "ExecStart": str(entry) + " --execute", "ControlGroup": "/user/" + module.OLD_UNIT,
                  "ActiveState": "active", "MainPID": "1234"}
    assert module.validate_owned_unit(spec, properties, old_root=old, uid=123) == "active"
    with pytest.raises(ValueError):
        module.validate_owned_unit(spec, {**properties, "Description": "other"}, old_root=old, uid=123)


def fake_grading(tmp_path, monkeypatch):
    grading_root = tmp_path / "physical/grading"
    monkeypatch.setattr(module.primary, "GRADING_ROOT", grading_root)
    monkeypatch.setattr(module.primary, "BATCH_ROOT", tmp_path / "physical")
    calls = []
    def prepare(result_ref, endpoint="code"):
        result = module.load(result_ref)
        key = ("score-" if endpoint == "code" else "delivery-score-") + str(result["slot_index"])
        path = grading_root / key / "request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"slot_id": result["slot_id"], "generation_result": result_ref,
                                   "directory": str(path.parent), "resource_key": key}))
        return reference(path)
    def run(request_ref, stop_event=None):
        calls.append(request_ref)
        request = module.load(request_ref)
        from pathlib import Path
        path = Path(request["directory"]) / "completion.json"
        path.write_text(json.dumps({"status": "process_exited", "returncode": 0}))
        return module.load(reference(path))
    return SimpleNamespace(prepare_score=prepare, run_request=run, trustworthy_cleanup=lambda ref: True), calls


def test_consumed_score_never_replayed_completed_score_imported(tmp_path, monkeypatch):
    grading, calls = fake_grading(tmp_path, monkeypatch)
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"slot_id": "a", "slot_index": 1}))
    result_ref = reference(result)
    row = {"slot_id": "a", "slot_index": 1}
    request = grading.prepare_score(result_ref)
    claims = module.primary.BATCH_ROOT / "resource-claims"
    claims.mkdir(parents=True)
    (claims / "score-1.json").write_text("{}")
    with pytest.raises(RuntimeError, match="cannot be replayed"):
        module._score_once(row, result_ref, "code", grading, None)
    assert calls == []
    completion = module.primary.GRADING_ROOT / "score-1/completion.json"
    completion.write_text('{"status":"process_exited","returncode":0}')
    value, ran = module._score_once(row, result_ref, "code", grading, None)
    assert value["request"] == request and not ran and calls == []


def test_finalizer_one_unused_score_each_poll_and_no_generation(tmp_path, monkeypatch):
    grading, calls = fake_grading(tmp_path, monkeypatch)
    old = tmp_path / "old"
    old.mkdir()
    rows, generation = {}, {}
    for index in (1, 2):
        slot = str(index)
        rows[slot] = {"slot_id": slot, "slot_index": index, "arm": "REF"}
        path = tmp_path / f"result-{index}.json"
        path.write_text(json.dumps({"slot_id": slot, "slot_index": index}))
        generation[slot] = {"status": "closed", "result": reference(path)}
    (old / "run-summary.json").write_text(json.dumps({"generation": generation, "scores": {}, "deliveries": {}}))
    scope = SimpleNamespace(BATCH_ROOT=tmp_path / "new", OLD_API_ROOT=old)
    handoff = {"old_scheduled_slot_ids": ["1", "2"]}
    first = module._finalize_one(scope, handoff, rows, None, grading=grading)
    assert not first["complete"] and len(calls) == 1
    second = module._finalize_one(scope, handoff, rows, None, grading=grading)
    assert second["complete"] and len(calls) == 2
    state = module.load(second["result"])["state"]
    assert state["new_generation"] == 0 and state["generation"] == generation
