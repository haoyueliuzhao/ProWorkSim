"""CPU-only isolation and admission contracts for the independent API queue."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("v067_api_cpu_fixture", ROOT / "tools/run_api_continuation_v067.py")
fixtures = module("v067_api_shared_fixture", ROOT / "tests/test_full_coordinator_v066.py")


def planned(path, count=8):
    result = fixtures.rows(path, count)
    for row in result:
        row["model_key"] = "DEEPSEEK"
    return result


def cursor(path, qualifications, **fields):
    atomic_write(path, json_bytes({"phase": "running", "qualifications": qualifications,
        "provider_failures": {"DEEPSEEK": {"reason": "api_initialization_unavailable"}},
        "active_generation": [], **fields}))


def execute(path, rows, fixture, api=None, initial_state=None, qualification=None):
    source = path / "primary-cursor.json"
    if qualification is None:
        cursor(source, {"task": {"status": "qualified", "qualification": {"cpu_fixture": True}}})
        qualification = runner.PrimaryQualifications({"task"}, cursor_path=source, poll_seconds=.005)
    progress, events = [], []
    primary_before = source.read_bytes()
    result = runner.execute_api_queue(rows, initial_state=initial_state or {"generation": {}, "retry_zero_generation": {}},
        qualifications=qualification, grading=fixture, run_episode=fixture.episode,
        api_runtime=api or fixtures.API(), stop_event=threading.Event(), progress_sink=progress.append,
        event_sink=lambda kind, **values: events.append((kind, values)), cursor_sink=lambda value: None,
        entered_probe=lambda row: row["slot_id"] in fixture.entered)
    return result, progress, events, primary_before


def test_api_only_queue_reuses_frozen_loop_without_qwen_lifecycle(tmp_path):
    original_root = runner.base.RUN_ROOT
    # A real resident runtime is not imported by this entry point, even to stop it.
    assert "software_benchmark_ref_resident_v066" not in runner.__dict__
    rows = planned(tmp_path)
    fixture = fixtures.Fixture(tmp_path)
    result, _, _, primary = execute(tmp_path, rows, fixture)
    assert result["failure"] is None
    assert len(result["generation"]) == 8 and len(result["scores"]) == 8
    assert fixture.maximum_generation <= 4
    assert result["resident_closure"] == []
    assert result["local_model_lifecycle_operations"] == 0
    assert result["controls_repeated"] == 0
    assert runner.base.RUN_ROOT == original_root
    assert (tmp_path / "primary-cursor.json").read_bytes() == primary
    rows[0]["model_key"] = "QWEN"
    with pytest.raises(ValueError, match="local-model"):
        execute(tmp_path, rows, fixture)


def test_qualification_value_survives_shallow_copy_and_waits_for_primary(tmp_path):
    rows = planned(tmp_path, 1)
    source = tmp_path / "primary-cursor.json"
    cursor(source, {})
    qualifications = runner.PrimaryQualifications({"task"}, cursor_path=source, poll_seconds=.005)
    copied = dict(qualifications.values)
    assert copied["task"].get("status") == "waiting_for_primary_qualification"

    def complete_primary_control():
        time.sleep(.04)
        cursor(source, {"task": {"status": "qualified", "qualification": {"cpu_fixture": True}}})

    worker = threading.Thread(target=complete_primary_control)
    worker.start()
    fixture = fixtures.Fixture(tmp_path)
    result, _, _, _ = execute(tmp_path, rows, fixture, qualification=qualifications)
    worker.join()
    assert copied["task"].get("status") == "qualified"
    assert result["failure"] is None and len(result["generation"]) == 1
    assert result["qualifications"]["task"]["status"] == "qualified"


def test_primary_qualification_stop_preserves_unentered_inventory(tmp_path):
    rows = planned(tmp_path, 1)
    source = tmp_path / "primary-cursor.json"
    cursor(source, {}, phase="stopping", failure={"kind": "shared_safety_stop"})
    qualifications = runner.PrimaryQualifications({"task"}, cursor_path=source, poll_seconds=.005)
    fixture = fixtures.Fixture(tmp_path)
    result, _, _, _ = execute(tmp_path, rows, fixture, qualification=qualifications)
    assert result["failure"]["kind"] == "primary_stopped_with_pending_environment_qualifications"
    assert result["unentered_generation"] == ["slot-0"]
    assert fixture.calls == {} and result["resident_closure"] == []


def test_sidecar_initialization_failure_releases_only_its_own_reservation(tmp_path, monkeypatch):
    from proworksim import software_benchmark_api_scope_v067 as scope
    from proworksim import software_benchmark_deepseek_runtime_v067 as api_module

    events = []
    own_claim = {"owned": "v067-only"}
    monkeypatch.setattr(scope, "require_allowed", lambda operation: events.append(operation) or {})
    monkeypatch.setattr(scope, "verify_host_limits", lambda: events.append("limits") or {})
    monkeypatch.setattr(scope, "reserve_coordinator", lambda: events.append("reserve") or own_claim)
    monkeypatch.setattr(scope, "release_coordinator", lambda ref: events.append(("release", ref)))
    monkeypatch.setattr(runner, "RUN_ROOT", tmp_path / "output")
    # Real historical inputs are read only; no initializations or workers run.
    monkeypatch.setattr(runner, "verify_primary_api_idle", lambda *args: {})
    monkeypatch.setattr(runner.PrimaryQualifications, "refresh", lambda self: None)

    class API:
        def __init__(self, **kwargs):
            events.append("constructor")

        def initialize_for_run(self):
            events.append("initialize")
            raise ValueError("CPU fixture initialization failure")

    class Recorder:
        def __init__(self, *args):
            pass

        def import_records(self, *args, **kwargs):
            pass

        def flush(self, **kwargs):
            pass

    def queue(rows, **kwargs):
        assert kwargs["initial_state"]["provider_failures"]["DEEPSEEK"]["reason"] == "api_initialization_unavailable"
        events.append("isolated_queue")
        return {"failure": None, "generation": {}, "provider_failures": kwargs["initial_state"]["provider_failures"], "exceptions": []}

    monkeypatch.setattr(api_module, "DeepSeekRuntime", API)
    monkeypatch.setattr(runner, "APIUsageRecorder", Recorder)
    monkeypatch.setattr(runner, "execute_api_queue", queue)
    monkeypatch.setattr(runner.base, "grading_module", lambda: None)
    result = runner.run()
    assert result["provider_failures"]["DEEPSEEK"]["error"] == "CPU fixture initialization failure"
    assert events == ["v067.run", "limits", "reserve", "constructor", "initialize", "isolated_queue", ("release", own_claim)]


def test_clean_episode_unknown_is_local_and_api_budget_stop_never_touches_primary(tmp_path):
    rows = planned(tmp_path, 6)
    fixture = fixtures.Fixture(tmp_path, unknown="slot-0")
    result, _, _, primary = execute(tmp_path, rows, fixture)
    assert result["failure"] is None and len(result["generation"]) == 6
    assert result["generation"]["slot-0"]["status"] == "technical_unknown"
    assert len(result["scores"]) == 5
    assert (tmp_path / "primary-cursor.json").read_bytes() == primary
    second = tmp_path / "budget"
    second.mkdir()
    fixture = fixtures.Fixture(second)
    result, _, _, primary = execute(second, planned(second, 6), fixture, fixtures.API("cash_exhausted"))
    assert result["failure"] is None and fixture.calls == {}
    assert result["provider_failures"]["DEEPSEEK"]["reason"] == "api_cash_exhausted"
    assert all(value["not_started_reason"] == "api_monetary_budget_exhausted" for value in result["generation"].values())
    assert result["resident_closure"] == []
    assert (second / "primary-cursor.json").read_bytes() == primary


def test_original_state_preserves_old_api_and_only_exact_zero_generation_retry(tmp_path):
    rows = planned(tmp_path, 4)
    rows[3]["model_key"] = "QWEN"
    old = {"slot-0": {"status": "closed", "entered": True},
        "slot-1": {"status": "technical_unknown", "entered": True, "result": {"old": True}},
        "slot-3": {"status": "closed", "entered": True}}
    retry = {"old_entry": old["slot-1"], "old_result": {"old": True},
        "new_attempt_reason": "verified_zero_model_generation"}
    inventory = {"allowed_generation_slot_ids": ["slot-1", "slot-2"], "generation": old,
        "retry_zero_generation": {"slot-1": retry}, "API_ledger": str(runner.LEDGER),
        "scores": {"slot-0": {"original_score": True}, "slot-3": {}},
        "deliveries": {"slot-0": {"resolved": True}}, "exceptions": []}
    selected, state = runner.original_api_state(rows, inventory, {"inventory": True})
    assert set(state["generation"]) == {"slot-0", "slot-1"}
    assert state["scores"] == {"slot-0": {"original_score": True}}
    assert state["deliveries"] == inventory["deliveries"]
    fixture = fixtures.Fixture(tmp_path)
    result, _, _, _ = execute(tmp_path, selected, fixture, initial_state=state)
    assert result["generation"]["slot-0"] == old["slot-0"]
    assert result["scores"]["slot-0"] == {"original_score": True}
    assert fixture.calls == {"slot-1": 1, "slot-2": 1}
    assert result["generation"]["slot-1"]["prior_zero_generation_attempt"] == retry
    inventory["allowed_generation_slot_ids"].append("slot-0")
    with pytest.raises(ValueError, match="eligibility"):
        runner.original_api_state(rows, inventory, {})


def test_admission_rejects_active_primary_consumed_identity_or_any_previous_request(tmp_path):
    rows = planned(tmp_path, 2)
    source, claims, ledger = tmp_path / "cursor.json", tmp_path / "claims", tmp_path / "ledger.sqlite3"
    claims.mkdir()
    cursor(source, {})
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE requests (slot_id TEXT)")
    state = {"generation": {"slot-0": {"entered": True}}, "retry_zero_generation": {}}
    arguments = {"cursor_path": source, "claims_root": claims, "ledger": ledger}
    assert runner.verify_primary_api_idle(rows, state, **arguments)["eligible_API_slots"] == 1
    cursor(source, {}, active_generation=["slot-1"])
    with pytest.raises(ValueError, match="active"):
        runner.verify_primary_api_idle(rows, state, **arguments)
    cursor(source, {})
    (claims / "actor-1.json").write_text("{}")
    with pytest.raises(ValueError, match="consumed"):
        runner.verify_primary_api_idle(rows, state, **arguments)
    (claims / "actor-1.json").unlink()
    with sqlite3.connect(ledger) as db:
        db.execute("INSERT INTO requests VALUES ('slot-1')")
    with pytest.raises(ValueError, match="provider request"):
        runner.verify_primary_api_idle(rows, state, **arguments)
    cursor(source, {}, provider_failures={})
    with pytest.raises(ValueError, match="initialization"):
        runner.verify_primary_api_idle(rows, state, **arguments)


def test_recorder_filters_old_qwen_writes_only_sidecar_and_keeps_500_denominators(tmp_path, monkeypatch):
    matrix = runner.base.load(reference(runner.policy.MATRIX_FILE))
    api = next(row for row in matrix["rows"] if row["model_key"] == "DEEPSEEK")
    qwen = next(row for row in matrix["rows"] if row["model_key"] == "QWEN")
    record = {"slot_id": api["slot_id"], "group_id": api["group_id"], "entered": True,
        "generation_state": "closed", "code_result": True, "code_status": "scored", "delivery_result": None,
        "usage_capture_complete": True, "calls": [{"call_id": "old-call", "purpose": "actor",
            "prompt_tokens": 8, "completion_tokens": 2, "accounted_cost_cny": "0.01"}], "unresolved_calls": []}
    old_ref = write_new(tmp_path / "old-api.json", record)
    old_qwen = write_new(tmp_path / "old-qwen.json", {**record, "slot_id": qwen["slot_id"]})
    index = write_new(tmp_path / "old-index.json", {"record_files": {api["slot_id"]: old_ref, qwen["slot_id"]: old_qwen}})
    output = tmp_path / "sidecar"
    output.mkdir()
    monkeypatch.setattr(runner, "RUN_ROOT", output)

    class API(fixtures.API):
        @staticmethod
        def preparation_usage():
            return {"calls": [], "unresolved_calls": []}

    recorder = runner.APIUsageRecorder(matrix, API())
    recorder.import_records(index)
    assert set(recorder.records) == {api["slot_id"]}
    recorder.flush(final=True)
    report = json.loads((output / "actual-usage-summary.json").read_bytes())
    assert len(report["groups"]) == 6 and report["planned_episodes"] == 3000
    assert all(group["all_planned"]["planned_episodes"] == 500 for group in report["groups"].values())
    group = report["groups"][api["group_id"]]["all_planned"]
    assert group["actual_average_tokens_full_planned_group"] is None
    assert group["known_tokens_divided_by_entered_lower_bound"] == 10
    assert json.loads((output / "actual-usage-records.json").read_bytes())["record_files"][api["slot_id"]] == old_ref
    assert runner.base.RUN_ROOT == runner.policy.COORDINATOR_RUN_ROOT
