"""Finite synthetic host controls; no CUDA, model, Docker daemon or task execution."""
from pathlib import Path
import signal

import pytest

from scripts import software_panel_host_v053 as host


def row(index):
    return {"slot_id": f"slot-{index}", "task_id": f"task-{index}",
            "seed": index + 100, "repeat_index": 1, "role": "main"}


def card(index, free=60000):
    return {"index": index, "uuid": f"GPU-{index:08x}-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": "NVIDIA A800 80GB", "free_mib": free, "total_mib": 81920}


def test_real_resource_binding_and_uuid_command_are_explicit_and_quoted(tmp_path):
    cards = host.resources.select_cards([card(3), card(4, 46079)], excluded=[])
    assert [candidate["index"] for candidate in cards] == [3]
    binding = host.resources.binding_for(cards[0])
    assert binding["gpu_index"] == 3 and binding["target_mib"] == 58976
    root = tmp_path / "a directory's snapshot"
    plan = {"source_root": str(root), "dependency_paths": ["/deps"], "native_python": "/python",
            "runtime_launcher": "/runtime/run.sh"}
    command = host.worker_command(plan, tmp_path / "plan.json", "slot", tmp_path / "attempt", binding)
    assert command[:4] == ["/runtime/run.sh", "--write-project", "--gpu", "3"]
    assert "CUDA_VISIBLE_DEVICES=" + cards[0]["uuid"] in command
    assert "PYTORCH_CUDA_ALLOC_CONF=backend:native" in command
    assert command[command.index("-c") + 1] == "cd " + host.shlex.quote(str(root)) + ' && exec "$@"'
    assert command[-1] == str(tmp_path / "attempt")


@pytest.mark.parametrize("entered", [False, True])
def test_resource_wait_requeue_requires_zero_entry_and_keeps_order(tmp_path, entered):
    current = row(1)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    plan_ref = {"path": "/fixture/plan", "sha256": "a" * 64, "bytes": 1}
    report = {
        "row": current, "source_plan": plan_ref, "status": "resource_wait",
        "loader_not_entered": True, "model_loader_entered": False,
        "resident_exists": False, "model_calls": 0, "known_actual_tokens": 0,
        "fresh_process_resource_retry_allowed": True,
        "resource_receipt": {"retryable": True, "loader_not_entered": True},
    }
    host.native.write(attempt / "report.json", report)
    if entered:
        host.native.write(attempt / "model-entered.json", {})
    slot = {**current, "status": "running", "attempts": [{
        "path": str(attempt), "pid": 123, "started_at": 0}], "R_code": None}
    reason = host.settle_attempt(slot, row=current, plan_ref=plan_ref, exit_code=75, now=10)
    if entered:
        assert reason and slot["status"] == "technical_unknown"
    else:
        assert reason is None and slot["status"] == "resource_wait"
        state = {"slots": [slot, {**row(2), "status": "pending"}]}
        assert host.pending_slots(state, 69) == []
        assert [item["slot_id"] for item in host.pending_slots(state, 70)] == ["slot-1", "slot-2"]
    assert slot["R_code"] is None


def test_deadlines_and_cleanup_never_target_unlabelled_foreign_containers(tmp_path, monkeypatch):
    attempt = {"started_at": 0}
    assert host.guard_reason(attempt, {"phase": "generation", "at": 0}, 661) == "generation_deadline"
    assert host.guard_reason(attempt, {"phase": "scoring", "at": 5900,
                                      "episode_started_at": 0}, 6001) == "episode_hard_deadline"
    assert host.guard_reason(attempt, {"phase": "reservation", "at": 0}, 900) is None
    calls = []

    def foreign(hostname, method, path):
        calls.append((method, path))
        return [{"Id": "a" * 64, "Labels": {"proworksim.version": "software-panel-docker-v053-v1"}}]

    monkeypatch.setattr(host, "docker_request", foreign)
    with pytest.raises(ValueError, match="exact owned episode labels"):
        host.cleanup_containers({"backend_config": {"docker_host": "unix:///fixture"}},
                                "slot-1", tmp_path)
    assert len(calls) == 1 and calls[0][0] == "GET"
    assert "proworksim.worker_root" in calls[0][1] and "proworksim.slot_id" in calls[0][1]


def test_scheduler_runs_frozen_order_with_max_four_and_retains_zero_scores(tmp_path, monkeypatch):
    rows = [row(index) for index in range(5)]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    plan = {
        "version": host.VERSION, "limits": host.native.LIMITS, "phase_limits": host.PHASE_SECONDS,
        "max_residents": 4, "panel_ref": {"sha256": "a" * 64},
        "source_root": str(tmp_path), "dependency_paths": [], "runtime_launcher": "/runtime",
        "native_python": "/python", "backend_config": {"docker_host": "unix:///fixture"},
    }
    monkeypatch.setattr(host.runner, "validate_plan", lambda *a, **k: (plan, {"slots": rows}))
    monkeypatch.setattr(host, "verify_frozen_stats", lambda *a: None)
    monkeypatch.setattr(host, "query_gpus", lambda: [card(index) for index in range(8)])
    monkeypatch.setattr(host, "cleanup_containers", lambda *a: {"removed_container_ids": []})
    clock = [0.0]
    monkeypatch.setattr(host.time, "time", lambda: clock[0])
    monkeypatch.setattr(host.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    launches = []

    class Process:
        def __init__(self, command, **kwargs):
            assert kwargs["start_new_session"] is True
            self.pid = 10000 + len(launches)
            self.returncode = 0
            slot_id = command[command.index("--slot-id") + 1]
            directory = Path(command[-1])
            directory.mkdir()
            selected = next(item for item in rows if item["slot_id"] == slot_id)
            host.native.write(directory / "model-entered.json", {})
            host.native.write(directory / "report.json", {
                "source_plan": host.native.ref(plan_path), "row": selected,
                "status": "complete", "R_code": selected["seed"] % 2,
                "verdict": {"decision": "continue", "failure_type": "model_failure"},
            })
            launches.append((clock[0], slot_id, command[3]))

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(host.subprocess, "Popen", Process)
    assert host.supervise(plan_path, tmp_path / "run") == 0
    state = host.read(tmp_path / "run/state.json")
    assert state["status"] == "complete" and state["active"] == {}
    assert [item[1] for item in launches] == [item["slot_id"] for item in rows]
    assert len([item for item in launches if item[0] == 0]) == 4
    assert len({item[2] for item in launches[:4]}) == 4
    assert launches[4][0] >= 60
    assert [item["R_code"] for item in state["slots"]] == [0, 1, 0, 1, 0]
    assert all(len(item["attempts"]) == 1 for item in state["slots"])


def test_source_drift_pauses_before_any_worker_and_preserves_full_inventory(tmp_path, monkeypatch):
    rows = [row(index) for index in range(5)]
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}")
    plan = {
        "version": host.VERSION, "limits": host.native.LIMITS, "phase_limits": host.PHASE_SECONDS,
        "max_residents": 4, "panel_ref": {"sha256": "a" * 64},
    }
    monkeypatch.setattr(host.runner, "validate_plan", lambda *a, **k: (plan, {"slots": rows}))

    def drift(*args):
        raise ValueError("synthetic source changed")

    monkeypatch.setattr(host, "verify_frozen_stats", drift)
    monkeypatch.setattr(host.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(host, "query_gpus", lambda: pytest.fail("No dispatch after source drift"))
    assert host.supervise(plan_path, tmp_path / "run") == 78
    state = host.read(tmp_path / "run/state.json")
    assert state["status"] == "paused" and len(state["slots"]) == 5
    assert all(item["attempts"] == [] and item["R_code"] is None for item in state["slots"])


def test_process_signal_only_uses_the_owned_new_session_leader(monkeypatch):
    process = type("Process", (), {"pid": 12345, "poll": lambda self: None})()
    calls = []
    monkeypatch.setattr(host.os, "killpg", lambda pid, number: calls.append((pid, number)))
    host.signal_owned_process(process, signal.SIGTERM)
    assert calls == [(12345, signal.SIGTERM)]
