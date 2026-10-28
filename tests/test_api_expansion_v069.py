"""CPU contracts for non-replaying 5M handoff and the shared eighteen-lane pool."""
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_runtime_v069 as runtime
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.storage import atomic_write, json_bytes

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


runner = module("api69_runner_fixture", ROOT / "tools/run_api_expansion_v069.py")
old = module("api69_old_fixture", ROOT / "tools/run_api_continuation_v068.py")
launcher = module("api69_launch_fixture", ROOT / "tools/launch_api_expansion_v069.py")
fixtures = module("api69_scheduler_fixture", ROOT / "tests/test_full_coordinator_v066.py")
GIB = 1024**3


def claim(role, cpu, memory, slot=None):
    return {"spec": {"role": role, "slot_id": slot}, "reserved_cpu": cpu,
        "reserved_memory_bytes": memory * GIB, "reserved_spool_bytes": 4 * GIB if role == "actor" else 0}


def capacity(active=(), old_futures=0):
    return {"active": list(active), "old_generation_futures": old_futures,
        "physical": {"admit": True, "memory_available_bytes": 2048 * GIB, "disk_free_bytes": 2048 * GIB},
        "observed_unix": 1}


def test_capacity_counts_live_models_coord_drain_grader_headroom_and_old_unclaimed_futures():
    common = [claim("model", 12, 96) for _ in range(2)]
    common += [claim("auxiliary_coordinator", 4, 16) for _ in range(2)]
    common += [claim("actor", 6, 32, f"v064:task:QWEN_REF:{i}") for i in range(4)]
    assert runner.resource_limit(capacity(common), set())["resource_generation_limit"] == 13
    common.append(claim("model", 12, 96))
    assert runner.resource_limit(capacity(common), set())["resource_generation_limit"] == 10
    common.pop(2)  # Old API coordinator's reservation has actually been released.
    value = runner.resource_limit(capacity(common), set())
    assert value["resource_generation_limit"] == 11
    assert value["additional_grader_capacity_reserved"] == 2
    common.append(claim("actor", 6, 32, "v064:old:DEEPSEEK_REF_B10000K:1"))
    value = runner.resource_limit(capacity(common, old_futures=2), set())
    assert value["old_active_api_actors"] == 1
    assert value["old_unclaimed_generation_futures_reserved"] == 1
    assert value["resource_generation_limit"] == 9


def test_old_zero_control_pauses_without_signalling_or_consuming_active_identity(tmp_path):
    planned = fixtures.rows(tmp_path, 1)
    planned[0]["model_key"] = "DEEPSEEK"
    primary = tmp_path / "primary.json"
    atomic_write(primary, json_bytes({"phase": "running", "failure": None, "qualifications": {}}))
    q = old.PrimaryQualifications({"task"}, cursor_path=primary, poll_seconds=0)
    stopped = threading.Event()
    control = tmp_path / "control.json"
    atomic_write(control, json_bytes({"desired": 0, "administrative_pause": "CPU handoff fixture"}))
    admission = old.DynamicAdmission(planned, {"generation": {}, "retry_zero_generation": {}},
        q, stopped, fixtures.API(), lambda *args, **kwargs: None, lambda value: None,
        control_file=control, capacity_probe=lambda: capacity(), poll_seconds=0)
    admission.event("generation_scheduled", slot_id="slot-0")
    assert admission.limit() == 0 and not stopped.is_set()
    assert admission.active == {"slot-0"} and admission.pending == set()
    assert admission.observation["configured_generation_limit"] is None
    assert admission.observation["concurrency_control_error"] == "desired must be an integer from 1 through 64"


def test_inventory_only_admits_original_5M_and_never_old_scheduled_or_consumed(tmp_path):
    matrix = runner.base.load(reference(runner.policy.PLAN_FILE))
    target = [row for row in matrix["rows"] if row["model_key"] == "DEEPSEEK" and row["input_plus_output_tokens"] == 5_000_000]
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}")
    selected = target[20]
    inventory = {"allowed_generation_slot_ids": [selected["slot_id"]],
        "allowed_generation_slot_indices": [selected["slot_index"]], "generation": {},
        "excluded_old_scheduled_slot_ids": [target[0]["slot_id"]], "retry_zero_generation": {},
        "API_ledger": str(runtime.LEDGER), "handoff": reference(handoff)}
    targets, rows, state = runner.selected_inventory(matrix["rows"], inventory, {"fixture": True})
    assert len(targets) == 1000 and rows == [selected] and state["generation"] == {}
    result = runtime.select_eligible_api_rows(inventory, matrix["rows"], matrix["rows"], {target[0]["slot_id"]}, claims_root=tmp_path)
    assert set(result) == {selected["slot_id"]}
    (tmp_path / f"actor-{selected['slot_index']}.json").write_text("{}")
    with pytest.raises(ValueError, match="consumed actor"):
        runtime.select_eligible_api_rows(inventory, matrix["rows"], matrix["rows"], set(), claims_root=tmp_path)
    (tmp_path / f"actor-{selected['slot_index']}.json").unlink()
    inventory["excluded_old_scheduled_slot_ids"].append(selected["slot_id"])
    with pytest.raises(ValueError, match="Old scheduled|old scheduled"):
        runtime.select_eligible_api_rows(inventory, matrix["rows"], matrix["rows"], set(), claims_root=tmp_path)


def test_private_queue_can_exceed_twelve_without_mutating_frozen_globals(tmp_path):
    planned = fixtures.rows(tmp_path, 18)
    for row in planned:
        row.update(model_key="DEEPSEEK", input_plus_output_tokens=5_000_000)
    primary = tmp_path / "primary.json"
    atomic_write(primary, json_bytes({"phase": "running", "failure": None,
        "qualifications": {"task": {"status": "qualified", "qualification": {"CPU_fixture": True}}}}))
    q = runner.PrimaryQualifications({"task"}, cursor_path=primary, poll_seconds=.005)
    fixture = fixtures.Fixture(tmp_path)
    original = runner.base.execute_queue.__globals__["_executor_pair"]
    result = runner.execute_api_queue(planned, initial_state={"generation": {}, "retry_zero_generation": {}},
        qualifications=q, grading=fixture, run_episode=fixture.episode, api_runtime=fixtures.API(),
        stop_event=threading.Event(), progress_sink=lambda value: None, event_sink=lambda *args, **kwargs: None,
        cursor_sink=lambda value: None, entered_probe=lambda row: row["slot_id"] in fixture.entered,
        control_file=tmp_path / "control.json", capacity_probe=lambda: capacity(), poll_seconds=.005)
    assert result["failure"] is None and len(result["generation"]) == 18
    assert 12 < fixture.maximum_generation <= 18
    assert fixture.maximum_grading <= 3 and result["resident_closure"] == []
    assert runner.base.execute_queue.__globals__["_executor_pair"] is original
    assert runner.execute_queue.__globals__["_executor_pair"] is runner.expansion_executors


def test_drain_monitor_outlives_natural_queue_stop_and_isolates_one_poll_error():
    queue_stop, lifecycle_stop = threading.Event(), threading.Event()
    queue_stop.set()
    calls, errors = [], []

    def poll(*, stop_event):
        calls.append(stop_event)
        if len(calls) == 1:
            raise RuntimeError("CPU fixture temporary observation error")
        return {"complete": True, "status": "closed"}

    monitor = runner.DrainMonitor(poll, lifecycle_stop, lambda *args, **kwargs: errors.append((args, kwargs)), interval=.005)
    monitor.start()
    assert monitor.done.wait(1)
    monitor.close()
    assert len(calls) == 2 and calls[0] is lifecycle_stop
    assert errors[0][0] == ("predecessor_drain_exception",)
    assert not monitor.thread.is_alive()


def test_launcher_only_prepares_new_API_unit_without_scope_authorization_or_manager(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "run_api_expansion_v069.py").write_text("# CPU fixture\n")
    root = tmp_path / "expansion"
    scope = SimpleNamespace(ROOT=tmp_path, BATCH_ROOT=root, API_ROOT=root / "api-coordinator",
        API_UNIT="proworksim-v069-api-5m.service", cpu_affinity=lambda: [168, 169, 170, 171],
        AUTHORIZATION_FILE=tmp_path / "not-yet-approved.json")
    monkeypatch.setattr(launcher, "recovery_scope", lambda: scope)
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: pytest.fail("CPU preparation contacted a manager"))
    prepared = launcher.prepare()
    assert set(prepared["units"]) == {"api"}
    command = prepared["units"]["api"]["command"]
    assert "--unit=proworksim-v069-api-5m.service" in command
    assert "--property=CPUAffinity=168 169 170 171" in command
    assert "--property=MemoryMax=16G" in command and "--property=CPUQuota=400%" in command
    assert command[-2:] == [str(tools / "run_api_expansion_v069.py"), "--execute"]
    with pytest.raises(ValueError):
        launcher.launch("primary")
