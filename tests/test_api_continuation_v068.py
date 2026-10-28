"""CPU fixtures for recovery-only API identities and dynamic shared capacity."""
import importlib.util
from pathlib import Path
import threading
import time

import pytest

from proworksim import software_benchmark_deepseek_runtime_v068 as runtime
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("v068_api_cpu_fixture", ROOT / "tools/run_api_continuation_v068.py")
fixtures = module("v068_shared_fixture", ROOT / "tests/test_full_coordinator_v066.py")
GIB = 1024**3


def rows(path, count=8):
    result = fixtures.rows(path, count)
    for row in result:
        row["model_key"] = "DEEPSEEK"
    return result


def claim(role, cpu, memory, slot=None):
    return {"spec": {"role": role, "slot_id": slot}, "reserved_cpu": cpu,
        "reserved_memory_bytes": memory * GIB, "reserved_spool_bytes": 4 * GIB if role == "actor" else 0}


def capacity(active=(), *, admit=True, memory=1024, disk=1024):
    return {"active": list(active), "physical": {"admit": admit,
        "memory_available_bytes": memory * GIB, "disk_free_bytes": disk * GIB,
        "load_1m": 10 if admit else 204}, "observed_unix": 1}


def qualifications(path, *, ready=True):
    atomic_write(path, json_bytes({"phase": "running", "failure": None,
        "qualifications": {"task": {"status": "qualified", "qualification": {"CPU_fixture": True}}} if ready else {}}))
    return runner.PrimaryQualifications({"task"}, cursor_path=path, poll_seconds=.005)


class API(fixtures.API):
    def budget_status(self):
        return {**super().budget_status(), "inflight_count": 0}


def test_capacity_counts_real_qwen_models_graders_and_auxiliary_inside_existing_caps():
    active = [claim("model", 12, 96) for _ in range(4)]
    active += [claim("actor", 6, 32, f"qwen-{index}") for index in range(6)]
    active += [claim("actor", 6, 32, f"api-{index}") for index in range(2)]
    active += [claim("score", 4, 16) for _ in range(2)]
    active += [claim("auxiliary_coordinator", 4, 16)]
    value = runner.resource_limit(capacity(active), {"api-0", "api-1"})
    assert value["actual_active_api_actors"] == 2
    assert value["actual_active_qwen_actors"] == 6
    assert value["actual_active_model_reservations"] == 4
    assert value["actual_active_grader_reservations"] == 2
    assert value["actual_active_auxiliary_reservations"] == 1
    assert value["combined_reserved_cpu"] == 112
    assert value["combined_reserved_memory_bytes"] == 704 * GIB
    assert value["resource_generation_limit"] == 6
    assert value["environment_lane_limit"] == 12 and value["ledger_remote_request_cap"] == 64
    assert value["cpu_reservation_generation_ceiling"] == 8
    assert value["memory_reservation_generation_ceiling"] == 6
    assert set(value["capacity_limiting_constraints"]) == {"environment_lanes", "reserved_memory"}
    assert runner.resource_limit(capacity(active, admit=False), {"api-0", "api-1"})["resource_generation_limit"] == 2
    assert runner.resource_limit(capacity([claim("auxiliary_coordinator", 4, 16)]), set(), qwen_reserved_lanes=0)["resource_generation_limit"] == 12
    assert runner.resource_limit(capacity(active, memory=128), {"api-0", "api-1"})["additional_resource_slots"] == 0
    assert runner.cpu_utilization(None, None)["host_cpu_utilization_percent"] is None
    cpu = runner.cpu_utilization({"total_ticks": 100, "idle_ticks": 89, "monotonic_seconds": 1},
        {"total_ticks": 200, "idle_ticks": 178, "monotonic_seconds": 4})
    assert cpu == {"host_cpu_utilization_percent": 11.0, "host_cpu_sample_interval_seconds": 3}


def test_pending_qwen_has_two_lanes_without_double_counting_active_actors(tmp_path):
    planned = rows(tmp_path, 1)
    path = tmp_path / "primary.json"
    q = qualifications(path)
    primary = {"phase": "starting", "failure": None, "qualifications": {},
        "pending_generation": ["qwen-pending"], "active_generation": []}
    atomic_write(path, json_bytes(primary))
    active = []
    admission = runner.DynamicAdmission(planned, {"generation": {}, "retry_zero_generation": {}},
        q, threading.Event(), API(), lambda *args, **kwargs: None, lambda value: None,
        control_file=tmp_path / "control.json", capacity_probe=lambda: capacity(active), poll_seconds=0)
    q.poll_seconds = 0
    admission.refresh_capacity()
    assert admission.observation["effective_generation_limit"] == 10
    assert admission.observation["qwen_lane_reservation"] == 2
    assert admission.observation["qwen_additional_reserved_lanes"] == 2
    assert "primary_qwen_lane_reservation" in admission.observation["capacity_limiting_constraints"]
    active.extend(claim("actor", 6, 32, f"qwen-{index}") for index in range(2))
    admission.refresh_capacity()
    assert admission.observation["effective_generation_limit"] == 10
    assert admission.observation["qwen_additional_reserved_lanes"] == 0
    active.extend(claim("actor", 6, 32, f"qwen-{index}") for index in range(2, 4))
    admission.refresh_capacity()
    assert admission.observation["effective_generation_limit"] == 8
    active.clear()
    primary["pending_generation"] = []
    primary["phase"] = "closed"
    atomic_write(path, json_bytes(primary))
    admission.refresh_capacity()
    assert admission.observation["effective_generation_limit"] == 12
    assert admission.observation["qwen_lane_reservation"] == 0


def test_control_changes_one_to_sixty_four_and_invalid_control_drains_without_cancellation(tmp_path):
    planned = rows(tmp_path, 3)
    q = qualifications(tmp_path / "primary.json")
    control = tmp_path / "control.json"
    stopped = threading.Event()
    admission = runner.DynamicAdmission(planned, {"generation": {}, "retry_zero_generation": {}},
        q, stopped, API(), lambda *args, **kwargs: None, lambda value: None,
        control_file=control, capacity_probe=lambda: capacity(), poll_seconds=0)
    admission.event("generation_scheduled", slot_id="slot-0")
    assert admission.limit() == 12
    assert admission.observation["configured_generation_limit"] == 32
    atomic_write(control, json_bytes({"desired": 1}))
    assert admission.limit() == 1
    atomic_write(control, json_bytes({"desired": 64}))
    assert admission.limit() == 12
    assert admission.observation["configured_generation_limit"] == 64
    atomic_write(control, json_bytes({"desired": 65}))
    assert admission.limit() == 0
    assert admission.observation["concurrency_control_error"]
    assert admission.active == {"slot-0"} and not stopped.is_set()


def test_capacity_and_live_qualification_wait_do_not_trigger_frozen_missing_evidence_stop(tmp_path):
    planned = rows(tmp_path, 8)
    fixture = fixtures.Fixture(tmp_path)
    primary = tmp_path / "primary.json"
    q = qualifications(primary, ready=False)
    ready = threading.Event()
    progress, cursors = [], []

    def external_progress():
        time.sleep(.03)
        qualifications(primary)
        time.sleep(.03)
        ready.set()

    worker = threading.Thread(target=external_progress)
    worker.start()
    result = runner.execute_api_queue(planned,
        initial_state={"generation": {}, "retry_zero_generation": {}}, qualifications=q,
        grading=fixture, run_episode=fixture.episode, api_runtime=API(), stop_event=threading.Event(),
        progress_sink=progress.append, event_sink=lambda *args, **kwargs: None, cursor_sink=cursors.append,
        entered_probe=lambda row: row["slot_id"] in fixture.entered, control_file=tmp_path / "control.json",
        capacity_probe=lambda: capacity(admit=ready.is_set()), poll_seconds=.005)
    worker.join()
    assert result["failure"] is None and len(result["generation"]) == 8
    assert result["resident_closure"] == [] and result["local_model_lifecycle_operations"] == 0
    waiting = [value for value in progress if value.get("capacity_wait_reason") == "shared_resource_capacity"]
    assert waiting and waiting[0]["configured_generation_limit"] == 32
    assert waiting[0]["environment_lane_limit"] == 12
    assert waiting[0]["ledger_remote_request_cap"] == 64
    assert waiting[0]["resource_generation_limit"] == 0
    assert waiting[0]["actual_generation_futures"] == 0 and waiting[0]["api_inflight_requests"] == 0
    assert cursors[0]["phase"] == "starting" and cursors[0]["active_generation"] == []
    assert fixture.maximum_generation <= 12 and fixture.maximum_generation > 4


def test_api_budget_stop_still_closes_when_shared_physical_capacity_unavailable(tmp_path):
    planned = rows(tmp_path, 2)
    fixture = fixtures.Fixture(tmp_path)
    result = runner.execute_api_queue(planned, initial_state={"generation": {}, "retry_zero_generation": {}},
        qualifications=qualifications(tmp_path / "primary.json"), grading=fixture,
        run_episode=fixture.episode, api_runtime=API("cash_exhausted"), stop_event=threading.Event(),
        progress_sink=lambda value: None, event_sink=lambda *args, **kwargs: None, cursor_sink=lambda value: None,
        entered_probe=lambda row: False, control_file=tmp_path / "control.json",
        capacity_probe=lambda: capacity(admit=False), poll_seconds=.005)
    assert result["failure"] is None and fixture.calls == {}
    assert result["provider_failures"]["DEEPSEEK"]["reason"] == "api_cash_exhausted"
    assert result["resident_closure"] == []


def test_runtime_checks_current_inventory_not_old_api_allowlist_and_refuses_consumed_actor(tmp_path):
    original = [{"slot_id": f"slot-{index}", "slot_index": index, "model_key": "DEEPSEEK" if index % 2 else "QWEN",
        "seed": index, "configuration": {"frozen": index}} for index in range(6000)]
    inventory = {"allowed_generation_slot_ids": ["slot-3", "slot-4"],
        "allowed_generation_slot_indices": [3, 4], "API_ledger": str(runtime.LEDGER)}
    selected = runtime.select_eligible_api_rows(inventory, original, original, {"slot-1"}, claims_root=tmp_path)
    assert set(selected) == {"slot-3"}
    with pytest.raises(ValueError, match="request evidence"):
        runtime.select_eligible_api_rows(inventory, original, original, {"slot-3"}, claims_root=tmp_path)
    (tmp_path / "actor-3.json").write_text("{}")
    with pytest.raises(ValueError, match="consumed actor"):
        runtime.select_eligible_api_rows(inventory, original, original, set(), claims_root=tmp_path)
    (tmp_path / "actor-3.json").unlink()
    revised = [{**row, "seed": -1} if row["slot_id"] == "slot-3" else row for row in original]
    with pytest.raises(ValueError, match="model-visible"):
        runtime.select_eligible_api_rows(inventory, revised, original, set(), claims_root=tmp_path)


def test_runtime_uses_new_authority_without_mutating_frozen_adapter(monkeypatch):
    calls = []
    frozen_identity = runtime.frozen.IDENTITY_FILE
    instance = runtime.DeepSeekRuntime(scope_guard=lambda operation, **kwargs: calls.append((operation, kwargs)))
    monkeypatch.setattr(runtime.policy, "require_v066_allowed", lambda operation, **kwargs: calls.append((operation, kwargs)))
    instance._require_allowed(slot_id="original", instance_id="task")
    assert [item[0] for item in calls] == ["v068.api.request", "v066.api.request"]
    assert runtime.frozen.IDENTITY_FILE == frozen_identity
    assert runtime.IDENTITY_FILE != frozen_identity
    assert instance.cancel_all()["qwen_touched"] is False
    assert instance.client is None


def test_merged_history_keeps_consumed_zero_request_actor_and_local_unknown_not_replayed(tmp_path):
    planned = rows(tmp_path, 4)
    old = {"slot-0": {"entered": True, "status": "closed"},
        "slot-1": {"entered": False, "status": "technical_unknown", "actor_identity_consumed": True}}
    inventory = {"generation": old, "scores": {"slot-0": {"original_score": True}}, "deliveries": {},
        "retry_zero_generation": {}, "allowed_generation_slot_ids": ["slot-2", "slot-3"],
        "API_ledger": str(runner.LEDGER)}
    selected, initial = runner.original_api_state(planned, inventory, {"CPU_inventory": True})
    fixture = fixtures.Fixture(tmp_path, unknown="slot-2")
    result = runner.execute_api_queue(selected, initial_state=initial,
        qualifications=qualifications(tmp_path / "primary.json"), grading=fixture,
        run_episode=fixture.episode, api_runtime=API(), stop_event=threading.Event(),
        progress_sink=lambda value: None, event_sink=lambda *args, **kwargs: None, cursor_sink=lambda value: None,
        entered_probe=lambda row: row["slot_id"] in fixture.entered,
        control_file=tmp_path / "control.json", capacity_probe=lambda: capacity(), poll_seconds=.005)
    assert result["failure"] is None
    assert fixture.calls == {"slot-2": 1, "slot-3": 1}
    assert result["generation"]["slot-0"] == old["slot-0"]
    assert result["generation"]["slot-1"] == old["slot-1"]
    assert result["generation"]["slot-2"]["status"] == "technical_unknown"
    assert result["scores"]["slot-0"] == {"original_score": True}
    assert "slot-3" in result["scores"]


def test_shared_safety_stop_blocks_new_actors_even_if_qualified_and_capacity_available(tmp_path):
    planned = rows(tmp_path, 1)
    path = tmp_path / "primary.json"
    q = qualifications(path)
    atomic_write(path, json_bytes({"phase": "stopping", "failure": {"kind": "integrity_failure"},
        "qualifications": {"task": {"status": "qualified", "qualification": {"CPU_fixture": True}}}}))
    fixture = fixtures.Fixture(tmp_path)
    result = runner.execute_api_queue(planned, initial_state={"generation": {}, "retry_zero_generation": {}},
        qualifications=q, grading=fixture, run_episode=fixture.episode, api_runtime=API(),
        stop_event=threading.Event(), progress_sink=lambda value: None,
        event_sink=lambda *args, **kwargs: None, cursor_sink=lambda value: None,
        entered_probe=lambda row: False, control_file=tmp_path / "control.json",
        capacity_probe=lambda: capacity(), poll_seconds=.005)
    assert result["failure"]["kind"] == "primary_shared_safety_stop"
    assert fixture.calls == {} and result["resident_closure"] == []


def test_user_stop_during_capacity_wait_retains_unentered_slots_and_explicit_reason(tmp_path):
    planned = rows(tmp_path, 2)
    fixture = fixtures.Fixture(tmp_path)
    stopped = threading.Event()

    def cancel_after_wait_started():
        time.sleep(.02)
        stopped.set()

    worker = threading.Thread(target=cancel_after_wait_started)
    worker.start()
    result = runner.execute_api_queue(planned, initial_state={"generation": {}, "retry_zero_generation": {}},
        qualifications=qualifications(tmp_path / "primary.json"), grading=fixture,
        run_episode=fixture.episode, api_runtime=API(), stop_event=stopped,
        progress_sink=lambda value: None, event_sink=lambda *args, **kwargs: None,
        cursor_sink=lambda value: None, entered_probe=lambda row: False,
        control_file=tmp_path / "control.json", capacity_probe=lambda: capacity(admit=False), poll_seconds=.005)
    worker.join()
    assert result["failure"]["kind"] == "api_coordinator_cancelled_during_admission_wait"
    assert set(result["unentered_generation"]) == {"slot-0", "slot-1"}
    assert fixture.calls == {} and result["resident_closure"] == []
