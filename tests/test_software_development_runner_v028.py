"""CPU supervisor fixtures; no GPU query, model load or model episode occurs."""

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_development_v028 as runner


def plan():
    return {"version": runner.VERSION, "assignments": runner.assignments(),
            "worker_gpu_seconds": dict.fromkeys(runner.WORKERS), "limits": runner.LIMITS,
            "total_gpu_seconds": None, "gpu_preference": runner.GPUS,
            "purpose": "interface_development", "inherited_resource_budget": False,
            "shared_gpu_capacity_allowed": False, "automatic_retries": False,
            "automatic_successors": [], "model_api_calls": 0,
            "queue_deadline_at": 1000000, "wall_deadline_at": None,
            "source": {"code_commit": "CPU_fixture", "code_dirty": False, "source_tree_sha256": "a" * 64}}


def resources():
    return {"gpus": {"returncode": 0, "stdout": (
        "0, GPU-0, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "4, GPU-4, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "5, GPU-5, NVIDIA A100-SXM4-80GB, 29000, 81920, 90\n")},
        "processes": {"returncode": 0, "stdout": ""}}


def test_exact_eight_slots_keep_first_speaker_strata_and_uncapped_gpu_duration():
    spec = plan()
    runner.validate_plan(spec, check_files=False)
    slots = [slot for worker in spec["assignments"].values() for slot in worker]
    assert len(slots) == len({s["slot_id"] for s in slots}) == 8
    assert spec["total_gpu_seconds"] is None
    assert spec["worker_gpu_seconds"] == {"worker-0": None, "worker-1": None}
    assert spec["wall_deadline_at"] is None
    for worker, values in spec["assignments"].items():
        assert len({s["first_member"] for s in values}) == 1
        assert len(values) == 4 and len({s["sampling_seed"] for s in values}) == 2
        assert all(sum(s["role_decision_limits"].values()) == 96 for s in values)
    for mutate in (
        lambda p: p.update(inherited_resource_budget=True),
        lambda p: p["assignments"]["worker-0"].pop(),
        lambda p: p.update(total_gpu_seconds=28800),
        lambda p: p.update(total_gpu_seconds=0),
        lambda p: p.update(total_gpu_seconds=float("inf")),
        lambda p: p.pop("total_gpu_seconds"),
        lambda p: p.update(worker_gpu_seconds={"worker-0": 10800, "worker-1": 10800}),
        lambda p: p.update(worker_gpu_seconds={"worker-0": 0, "worker-1": 0}),
        lambda p: p.update(worker_gpu_seconds={"worker-0": float("inf"), "worker-1": float("inf")}),
        lambda p: p.update(automatic_retries=True),
        lambda p: p.update(wall_deadline_at=p["queue_deadline_at"] + 11100),
        lambda p: p.pop("wall_deadline_at"),
    ):
        bad = copy.deepcopy(spec)
        mutate(bad)
        with pytest.raises(ValueError, match="eight-slot"):
            runner.validate_plan(bad, check_files=False)


def test_capacity_admission_rejects_competing_or_low_or_unknown_capacity():
    assert [c["index"] for c in runner.available_cards(plan(), resources())] == [0, 4]
    assert [c["index"] for c in runner.available_cards(plan(), resources(), excluded=[0])] == [4]
    occupied = resources()
    occupied["processes"]["stdout"] = "GPU-0, 11, 100, another-fixture\n"
    assert [c["index"] for c in runner.available_cards(plan(), occupied)] == [4]
    incomplete = resources()
    incomplete["processes"]["returncode"] = 1
    assert runner.available_cards(plan(), incomplete) == []
    malformed = resources()
    malformed["gpus"]["stdout"] = "0, GPU-0, A100, nan, 81920, 0\n"
    assert runner.available_cards(plan(), malformed) == []


def test_capacity_admission_includes_all_eight_cards():
    sample = resources()
    sample["gpus"]["stdout"] = "".join(
        f"{index}, GPU-{index}, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        for index in range(8))
    assert [card["index"] for card in runner.available_cards(plan(), sample)] == list(range(8))


def test_original_request_is_durable_before_generation_and_error_is_retained(tmp_path):
    request = {"messages": [{"role": "user", "content": "Original fixture input"}], "max_tokens": 2048}

    def complete(value, **kwargs):
        recorded = read_json(tmp_path / "call-00001.started.json")
        assert recorded["request"] == value == request
        assert recorded["status"] == "generation_not_returned"
        raise RuntimeError("Explicit interrupted CPU transport fixture")

    transport = runner.DurableTransport(SimpleNamespace(complete=complete), tmp_path, "CPU-window")
    with pytest.raises(RuntimeError, match="interrupted"):
        transport.complete(request, timeout_seconds=600)
    ended = read_json(tmp_path / "call-00001.finished.json")
    assert ended["request"] == request and ended["status"] == "interrupted_or_error"
    assert ended["error"]["type"] == "RuntimeError"
    assert "response" not in ended


@pytest.mark.parametrize("elapsed,task_age,expected_status", [
    (0, 0, "complete"),
    (10801, 0, "complete"),
    (10801, 901, "closed_with_missing_or_interrupted"),
])
def test_supervisor_keeps_task_limits_without_worker_duration_cap(tmp_path, monkeypatch,
                                                                 elapsed, task_age, expected_status):
    spec = plan()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(spec))
    clock = [100]
    monkeypatch.setattr(runner.time, "time", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda _: clock.__setitem__(0, clock[0] + 61))
    monkeypatch.setattr(runner, "validate_plan", lambda p: p)
    monkeypatch.setattr(runner, "code_identity", lambda: spec["source"])
    monkeypatch.setattr(runner, "resources", resources)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {"pid": pid, "start_ticks": 5})
    monkeypatch.setattr(runner, "rss", lambda _: 0)
    monkeypatch.setattr(runner, "TelemetryGuard", lambda *a, **kw: SimpleNamespace(observe=lambda *a, **kw: {}))
    monkeypatch.setattr(runner, "stop_owned", lambda process: setattr(process, "returncode", -15))
    processes, observed = {}, []

    class Process:
        def __init__(self, argv, **kwargs):
            self.pid = 90000 + len(processes)
            self.returncode = None
            processes[self.pid] = self
            from pathlib import Path
            destination = Path(argv[argv.index("--output") + 1])
            self.destination = destination
            destination.mkdir(parents=True)
            (destination / "report.json").write_text(json.dumps({"status": "complete", "rows": [{"status": "closed"}] * 4}))
            if len(processes) == 2:
                clock[0] += elapsed

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            return self.returncode

    def target(gpu, *, worker_pid):
        observed.append((gpu, worker_pid))
        process = processes[worker_pid]
        (process.destination / "task.json").write_text(json.dumps({"kind": "loading", "started_at": clock[0] - task_age}))
        if observed.count((gpu, worker_pid)) == 2:
            process.returncode = 0
        return {"explicit_CPU_fixture": True}

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    monkeypatch.setattr(runner, "target_resources", target)
    summary = runner.supervise(path, tmp_path / "run")
    assert summary["status"] == expected_status
    assert len(observed) == (4 if expected_status == "complete" else 2)
    assert {gpu for gpu, _ in observed} == {0, 4}
    assert all(state["gpu_budget_seconds"] is None for state in summary["states"].values())
    assert all(state["elapsed_gpu_seconds"] >= elapsed for state in summary["states"].values())
    if expected_status == "complete":
        assert all(state["status"] == "complete" and state["closed_slots"] == 4
                   for state in summary["states"].values())
    else:
        assert all(state["stop_reason"] == "single_task_budget" for state in summary["states"].values())
