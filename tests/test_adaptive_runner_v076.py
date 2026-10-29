"""CPU-only adaptive runner controls: no Docker, API, GPU or user service calls."""
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("adaptive_runner_cpu_fixture", ROOT / "tools/run_adaptive_v076.py")


def test_effective_limit_respects_available_starting_batch_and_lower_control(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"desired": 44}))
    state = {"admit": True, "api_generation_limit": 4,
             "actual_active_qwen_actors": 3, "additional_pair_slots": 1}
    admission = runner.AdaptiveAdmission("api", SimpleNamespace(admission_snapshot=lambda: dict(state)),
        SimpleNamespace(admission=lambda: {"fresh": True, "admit": True}), None, control,
        lambda *a, **kw: None)
    monkeypatch.setattr(runner.time, "monotonic", lambda: 100.0)
    assert admission.limit() == 4  # The desired/ramp ceiling alone would wrongly admit 12.
    state["api_generation_limit"] = 9
    assert admission.limit() == 9
    control.write_text(json.dumps({"desired": 2}))
    assert admission.limit() == 2
    control.write_text(json.dumps({"desired": 0}))
    assert admission.limit() == 0
    primary = runner.AdaptiveAdmission("primary", admission.policy, admission.watchdog, None,
                                       tmp_path / "primary-control.json", lambda *a, **kw: None)
    assert primary.limit() == 4
    state["additional_pair_slots"] = 0
    assert primary.limit() == 3  # API actor count is not the Qwen headroom.


def test_registry_pressure_cancellation_is_exact_local_and_one_shot(tmp_path):
    events = []
    registry = runner.EpisodeRegistry(lambda kind, **kw: events.append((kind, kw)))
    row = {"slot_id": "v064:fixture:DEEPSEEK_REF_B5000K:1", "slot_index": 1, "model_key": "DEEPSEEK"}
    local = registry.add(row)
    pair = registry.snapshot()[0]
    parent = threading.Event()
    stop = runner.LocalStop(parent, local)
    assert not registry.abort({**pair, "ownership_token": "foreign"}, {})
    assert not stop.is_set() and not parent.is_set()
    reason = {"reason": "host_memory_emergency", "technical_unknown": True, "automatic_retry": False}
    assert registry.abort(pair, reason)
    assert stop.is_set() and not parent.is_set() and len(events) == 1
    assert not registry.abort(pair, reason)
    registration = registry.remove(row["slot_id"])
    assert registration["pressure_abort"] == reason and not registry.snapshot()
    assert not registry.abort(pair, reason)
    with pytest.raises(ValueError):
        registry.add({**row, "model_key": "QWEN"})
    original = write_new(tmp_path / "original.json", {"slot_id": row["slot_id"], "status": "closed",
        "known_actual_tokens": 123, "candidate": {"unchanged": True}, "quiescence": {"quiescent": True}})
    before = Path(original["path"]).read_bytes()
    retained = runner.pressure_result(original, registration, tmp_path, row)
    value = json.loads(Path(retained["path"]).read_bytes())
    assert value["status"] == "technical_unknown" and value["pressure_original_result"] == original
    assert value["known_actual_tokens"] == 123 and value["candidate"] == {"unchanged": True}
    assert Path(original["path"]).read_bytes() == before and not value["automatic_retry"]


def test_delivery_reconciliation_uses_real_signature_and_prepared_request_once():
    row = {"slot_id": "slot-1"}
    request, result = {"prepared": "delivery"}, {"result": "immutable"}
    disposition = {"status": "waiting_for_delivery_score", "scoring_request": request}
    calls = []
    class Grading:
        def delivery_disposition(self, result_ref, code_request_ref=None):
            calls.append((result_ref, code_request_ref))
            return disposition
        def prepare_score(self, *args, **kwargs):
            raise AssertionError("Do not prepare the same returned delivery request twice")
    inventory = {"delivery_reconciliation": [{"slot_id": row["slot_id"], "generation_result": result,
                                                "code_request": {"code": True}}]}
    state = {"deliveries": {}, "pending_score_jobs": []}
    runner.reconcile_deliveries([row], inventory, state, Grading())
    runner.reconcile_deliveries([row], inventory, state, Grading())
    assert calls == [(result, {"code": True})]
    assert state["deliveries"] == {row["slot_id"]: disposition}
    assert state["pending_score_jobs"] == [("delivery", row, request, True)]


def test_runtime_preflight_and_identity_bind_new_inventory_without_mutating_frozen_paths(tmp_path, monkeypatch):
    from proworksim import software_benchmark_deepseek_runtime_v072 as prior
    prior_path = prior._preflight.__globals__["INVENTORY_FILE"]
    prior_identity = prior._identity.__globals__["IDENTITY_FILE"]
    monkeypatch.setattr(runner.scope, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(runner.scope, "API_ROOT", tmp_path / "api")
    write_new(tmp_path / "api-inventory.json", {"CPU_fixture": True})
    runtime = runner.runtime_api()
    preflight = inspect.getclosurevars(runtime.read_only_preflight.__func__).nonlocals["preflight"]
    identity = inspect.getclosurevars(runtime.logical_resident.__func__).nonlocals["identity"]
    assert preflight.__globals__["INVENTORY_FILE"] == tmp_path / "api-inventory.json"
    assert runtime.inventory_ref == reference(tmp_path / "api-inventory.json")
    assert identity.__globals__["IDENTITY_FILE"] == tmp_path / "api/api-runtime/identity.json"
    assert prior._preflight.__globals__["INVENTORY_FILE"] == prior_path
    assert prior._identity.__globals__["IDENTITY_FILE"] == prior_identity
    assert runtime.client is None and runtime.counter is None


@pytest.mark.parametrize("failure", ["watchdog_start", "bindings", "api_initialize"])
def test_bootstrap_failure_closes_watchdog_and_releases_only_acquired_auxiliary(tmp_path, monkeypatch, failure):
    calls = []
    slot = "v064:fixture:DEEPSEEK_REF_B5000K:1"
    row = {"slot_id": slot, "model_key": "DEEPSEEK", "input_plus_output_tokens": 5_000_000}
    inventory = {"generation": {}, "scores": {}, "deliveries": {}, "allowed_generation_slot_ids": [slot]}
    for name, value in (("api-inventory.json", inventory), ("plan.json", {"rows": [row]}),
                        ("matrix.json", {}), ("auth.json", {})):
        write_new(tmp_path / name, value)
    monkeypatch.setattr(runner.scope, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(runner.scope, "API_ROOT", tmp_path / "api")
    monkeypatch.setattr(runner.scope, "AUTH_FILE", tmp_path / "auth.json")
    monkeypatch.setattr(runner.original, "PLAN_FILE", tmp_path / "plan.json")
    monkeypatch.setattr(runner.original, "MATRIX_FILE", tmp_path / "matrix.json")
    monkeypatch.setattr(runner.scope, "require_allowed", lambda *a, **kw: {})
    monkeypatch.setattr(runner.scope, "verify_host_limits", lambda *a: {})
    def reserve():
        calls.append("reserve")
        return {"owned_reservation": True}
    monkeypatch.setattr(runner.scope, "reserve_api_coordinator", reserve)
    monkeypatch.setattr(runner.scope, "release_api_coordinator", lambda ref: calls.append(("release", ref)))
    class Watchdog:
        def __init__(self, **kwargs):
            assert kwargs['require_parent'] is True
            assert callable(kwargs['parent_probe'])
        def start(self):
            calls.append("watch_start")
            if failure == "watchdog_start":
                raise RuntimeError(failure)
        def close(self):
            calls.append("watch_close")
        def admission(self):
            return {"fresh": True, "admit": True}
    class Bindings:
        def __init__(self, *args, **kwargs):
            if failure == "bindings":
                raise RuntimeError(failure)
            self.primary_policy = object()
    class API:
        def initialize_for_run(self):
            raise RuntimeError("api_initialize")
    monkeypatch.setitem(sys.modules, "proworksim.software_benchmark_pressure_v076", SimpleNamespace(PressureWatchdog=Watchdog))
    monkeypatch.setitem(sys.modules, "proworksim.software_benchmark_episodes_v076", SimpleNamespace(EpisodeBindings=Bindings))
    monkeypatch.setitem(sys.modules, "proworksim.software_benchmark_grading_v076", SimpleNamespace(factory=lambda *a, **kw: object()))
    monkeypatch.setattr(runner, "runtime_api", lambda: API())
    with pytest.raises(RuntimeError, match=failure):
        runner.run("api")
    assert calls[-1] == "watch_close"
    if failure == "api_initialize":
        assert calls == ["watch_start", "reserve", ("release", {"owned_reservation": True}), "watch_close"]
    else:
        assert "reserve" not in calls


def test_real_queue_keeps_resource_burst_limit_and_continues_after_local_unknown(tmp_path):
    fixtures = module("adaptive_queue_existing_fixture", ROOT / "tests/test_full_coordinator_v066.py")
    planned = fixtures.rows(tmp_path, 8)
    for row in planned:
        row["model_key"] = "DEEPSEEK"
    fixture = fixtures.Fixture(tmp_path, unknown="slot-0")
    admission = runner.AdaptiveAdmission("api", SimpleNamespace(admission_snapshot=lambda: {
        "admit": True, "api_generation_limit": 4}),
        SimpleNamespace(admission=lambda: {"fresh": True, "admit": True}), None,
        tmp_path / "desired.json", lambda *a, **kw: None)
    queue, _ = runner.qwen_base.recovery_function()
    queue = runner.private_function(queue, _executor_pair=runner.executors)
    result = queue(planned, controls=[], qualifications={"task": {"status": "qualified"}},
        grading=fixture, runtime=fixtures.Runtime(), run_episode=fixture.episode,
        api_runtime=fixtures.API(), stop_event=threading.Event(),
        progress_sink=lambda value: None, cursor_sink=lambda value: None,
        event_sink=admission.record, generation_limit=admission.limit,
        entered_probe=lambda row: row["slot_id"] in fixture.entered, model_exhausted=lambda _: False)
    assert result["failure"] is None and len(result["generation"]) == 8
    assert result["generation"]["slot-0"]["status"] == "technical_unknown"
    assert len(result["scores"]) == 7 and fixture.maximum_generation <= 4
    assert fixture.maximum_grading <= 3 and all(value == 1 for value in fixture.calls.values())
