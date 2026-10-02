"""CPU supervisor fixtures; no GPU query, model load or model episode occurs."""

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_development_v028 as runner


def plan():
    return {"version": runner.VERSION, "assignments": runner.assignments(),
            "worker_gpu_seconds": runner.CAPS, "limits": runner.LIMITS,
            "total_gpu_seconds": sum(runner.CAPS.values()), "gpu_preference": runner.GPUS,
            "purpose": "interface_development", "inherited_resource_budget": False,
            "shared_gpu_capacity_allowed": False, "automatic_retries": False,
            "automatic_successors": [], "model_api_calls": 0,
            "queue_deadline_at": 1000000, "wall_deadline_at": 1000000 + max(runner.CAPS.values()) + 300,
            "source": {"code_commit": "CPU_fixture", "code_dirty": False, "source_tree_sha256": "a" * 64}}


def resources():
    return {"gpus": {"returncode": 0, "stdout": (
        "0, GPU-0, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "4, GPU-4, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "5, GPU-5, NVIDIA A100-SXM4-80GB, 29000, 81920, 90\n")},
        "processes": {"returncode": 0, "stdout": ""}}


def test_exact_eight_slots_keep_first_speaker_strata_and_new_budget():
    spec = plan()
    runner.validate_plan(spec, check_files=False)
    slots = [slot for worker in spec["assignments"].values() for slot in worker]
    assert len(slots) == len({s["slot_id"] for s in slots}) == 8
    assert spec["total_gpu_seconds"] == 21600
    for worker, values in spec["assignments"].items():
        assert len({s["first_member"] for s in values}) == 1
        assert len(values) == 4 and len({s["sampling_seed"] for s in values}) == 2
        assert all(sum(s["role_decision_limits"].values()) == 96 for s in values)
    for mutate in (
        lambda p: p.update(inherited_resource_budget=True),
        lambda p: p["assignments"]["worker-0"].pop(),
        lambda p: p.update(total_gpu_seconds=28800),
        lambda p: p.update(automatic_retries=True),
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


def test_supervisor_starts_two_owned_workers_and_calls_keyword_only_telemetry(tmp_path, monkeypatch):
    spec = plan()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(spec))
    clock = iter(range(100, 100000, 61))
    monkeypatch.setattr(runner.time, "time", lambda: next(clock))
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    monkeypatch.setattr(runner, "validate_plan", lambda p: p)
    monkeypatch.setattr(runner, "code_identity", lambda: spec["source"])
    monkeypatch.setattr(runner, "resources", resources)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {"pid": pid, "start_ticks": 5})
    processes, observed = {}, []

    class Process:
        def __init__(self, argv, **kwargs):
            self.pid = 90000 + len(processes)
            self.returncode = None
            processes[self.pid] = self
            from pathlib import Path
            destination = Path(argv[argv.index("--output") + 1])
            destination.mkdir(parents=True)
            (destination / "report.json").write_text(json.dumps({"status": "complete", "rows": [{"status": "closed"}] * 4}))

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            return self.returncode

    def target(gpu, *, worker_pid):
        observed.append((gpu, worker_pid))
        processes[worker_pid].returncode = 0
        return {"explicit_CPU_fixture": True}

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    monkeypatch.setattr(runner, "target_resources", target)
    summary = runner.supervise(path, tmp_path / "run")
    assert summary["status"] == "complete" and len(observed) == 2
    assert {gpu for gpu, _ in observed} == {0, 4}
    assert all(state["status"] == "complete" and state["closed_slots"] == 4
               for state in summary["states"].values())
