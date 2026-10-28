"""CPU-only bindings and immutable inventory filtering for bounded API recovery."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3

from proworksim import software_benchmark_deepseek_budget_v072 as budget
from proworksim import software_benchmark_deepseek_runtime_v067 as wire
from proworksim import software_benchmark_deepseek_runtime_v072 as runtime

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module("v072_inventory_fixture", ROOT / "tools/prepare_api_continuation_v072.py")
runner = module("v072_runner_fixture", ROOT / "tools/run_api_continuation_v072.py")
launcher = module("v072_launcher_fixture", ROOT / "tools/launch_api_continuation_v072.py")


def test_runtime_updates_preflight_and_transport_admission_without_mutating_frozen_globals(tmp_path, monkeypatch):
    frozen_status = wire.budget_status
    assert runtime._preflight.__globals__["frozen"].budget_status is budget.budget_status
    assert runtime._transport.__globals__["budget_status"] is budget.budget_status
    ledger = tmp_path / "unconsumed-fixture.sqlite3"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE requests (slot_id TEXT)")

    @contextmanager
    def reader():
        with sqlite3.connect(ledger) as db:
            yield db

    class Transport:
        def __init__(self, **kwargs):
            self.authorize = kwargs["authorize"]

    monkeypatch.setitem(runtime._transport.__globals__, "_ledger_read", reader)
    monkeypatch.setitem(runtime._transport.__globals__, "HostDeepSeekTransport", Transport)
    monkeypatch.setitem(runtime._transport.__globals__, "budget_status", lambda: {
        "state": "ready", "can_start_generation": True, "bounded_uncertain_count": 2})
    guard_calls = []
    instance = runtime.DeepSeekRuntime(scope_guard=lambda operation, **kwargs: guard_calls.append(operation))
    row = {"slot_id": "v064:fixture:DEEPSEEK_REF_B5000K:1", "slot_index": 1,
        "condition_id": "DEEPSEEK_REF_B5000K", "instance_id": "fixture", "model_key": "DEEPSEEK",
        "arm": "REF", "input_plus_output_tokens": 5_000_000, "seed": 1, "configuration": {"fixture": True}}
    instance.client, instance.rows = object(), {row["slot_id"]: row}
    instance.schemas = {"tool_names": {"REF": ["terminal"]}}
    transport = instance.transport_factory(row, tmp_path)
    result = transport.authorize({"request_id": row["slot_id"] + ":0001", "slot_id": row["slot_id"],
        "condition": row["condition_id"], "usage_id": "agent", "wire": {"max_tokens": 32768,
            "tools": [{"type": "function", "function": {"name": "terminal"}}]}})
    assert result == {"condition_id": row["condition_id"], "token_budget": 5_000_000}
    assert guard_calls == ["v072.api.request", "v072.api.request"]
    assert wire.budget_status is frozen_status


def test_inventory_preserves_scheduled_or_consumed_but_drops_unentered_provider_pause_placeholders():
    prior = {"old": {"status": "closed", "entered": True}}
    closed = {"new": {"status": "closed", "entered": True},
        "uncertain": {"status": "technical_unknown", "entered": True},
        "scheduled_zero": {"status": "not_started", "entered": False},
        "untouched": {"status": "not_started", "entered": False, "not_started_reason": "api_shared_halted"},
        "environment": {"status": "not_started", "entered": False, "not_started_reason": "environment_not_qualified"}}
    result = prepare.retained_generation(prior, closed, {"new", "uncertain", "scheduled_zero"})
    assert set(result) == {"old", "new", "uncertain", "scheduled_zero", "environment"}
    assert result["uncertain"] is closed["uncertain"] and "untouched" not in result


def test_report_paths_and_launcher_identity_are_owned_by_new_source_scope():
    assert runner.UsageRecorder.save_record.__globals__["RUN_ROOT"] == runner.RUN_ROOT
    assert runner.UsageRecorder.flush.__globals__["RUN_ROOT"] == runner.RUN_ROOT
    assert runner.frozen.APIUsageRecorder.save_record.__globals__["RUN_ROOT"] != runner.RUN_ROOT
    assert launcher.ROLES == ("api",)
    assert launcher.UNITS == {"api": "proworksim-v072-api-5m.service"}
    assert launcher.ENTRYPOINTS == {"api": "run_api_continuation_v072.py"}
    assert launcher.SPEC == runner.RUN_ROOT / "coordinator-unit.json"


def test_fully_reserved_unknown_ledger_allows_other_episodes_and_local_unknown_keeps_coverage(tmp_path, monkeypatch):
    budget_fixture = module("v072_money_integration_fixture", ROOT / "tests/test_deepseek_budget_v072.py")
    budget_fixture.fixture(tmp_path, monkeypatch)
    fixtures = module("v072_queue_integration_fixture", ROOT / "tests/test_full_coordinator_v066.py")
    planned = fixtures.rows(tmp_path, 2)
    for row in planned:
        row.update(model_key="DEEPSEEK", input_plus_output_tokens=5_000_000)
    from proworksim.storage import atomic_write, json_bytes
    import threading
    primary = tmp_path / "primary.json"
    atomic_write(primary, json_bytes({"phase": "running", "failure": None,
        "qualifications": {"task": {"status": "qualified", "qualification": {"CPU_fixture": True}}}}))
    qualifications = runner.frozen.PrimaryQualifications({"task"}, cursor_path=primary, poll_seconds=.005)
    fixture = fixtures.Fixture(tmp_path, unknown="slot-0")

    class API(fixtures.API):
        budget_status = staticmethod(budget.budget_status)

    result = runner.frozen.execute_api_queue(planned, initial_state={"generation": {}, "retry_zero_generation": {}},
        qualifications=qualifications, grading=fixture, run_episode=fixture.episode, api_runtime=API(),
        stop_event=threading.Event(), progress_sink=lambda value: None,
        event_sink=lambda *args, **kwargs: None, cursor_sink=lambda value: None,
        entered_probe=lambda row: row["slot_id"] in fixture.entered,
        control_file=tmp_path / "control.json", poll_seconds=.005,
        capacity_probe=lambda: {"active": [], "old_generation_futures": 0,
            "physical": {"admit": True, "memory_available_bytes": 2048 * 1024**3,
                "disk_free_bytes": 2048 * 1024**3}, "observed_unix": 1})
    assert result["failure"] is None and result["provider_failures"] == {}
    assert result["generation"]["slot-0"]["status"] == "technical_unknown"
    assert result["generation"]["slot-1"]["status"] == "closed"
    assert fixture.calls == {"slot-0": 1, "slot-1": 1}
    assert budget.budget_status()["uncertain_reserved_CNY"] == "10.48576"
