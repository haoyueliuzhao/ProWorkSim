"""CPU supervisor fixtures; no GPU query, model load or model episode occurs."""

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_development_v028 as runner


def plan():
    return {"version": runner.VERSION, "assignments": runner.assignments(),
            "interface_revision": runner.INTERFACE_REVISION,
            "context_policy": runner.CONTEXT_POLICY,
            "worker_gpu_seconds": dict.fromkeys(runner.WORKERS), "limits": runner.LIMITS,
            "total_gpu_seconds": None, "gpu_preference": runner.GPUS,
            "purpose": "interface_development", "inherited_resource_budget": False,
            "shared_gpu_capacity_allowed": False, "automatic_retries": False,
            "automatic_successors": [], "model_api_calls": 0,
            "queue_deadline_at": 1000000, "wall_deadline_at": None,
            "source": {"code_commit": "CPU_fixture", "code_dirty": False, "source_tree_sha256": "a" * 64}}


def recovery_fixture(tmp_path, monkeypatch):
    """Five terminal closed slots (including R=0), one unknown, two unstarted."""
    source = plan()["source"]
    monkeypatch.setattr(runner, "code_identity", lambda: source)
    for relative in ("runs/domain-v0201-p1-9b/plan.json", "runs/domain-v025-r1/train_base/actual/resident/owner.json",
                     "runs/domain-v025-r1/checkpoints/base.json", "qualification.json"):
        runner.write(tmp_path / relative, {})
    context = tmp_path / "context-qualification.json"
    runner.write(context, {"passed": True, "source": source, "model_calls": 0})
    original = runner.make_plan(tmp_path, tmp_path / "qualification.json", 1000000)
    original["source"] = {**source, "code_commit": "prior_CPU_fixture"}
    original["interface_revision"] = "software-collaboration-v0.28"
    original["context_policy"] = "latest_observation_last4_tool_rounds"
    original["gpu_preference"] = list(range(8))
    original["limits"] = {**original["limits"], "max_parallel_model_instances": 2}
    prior_root = tmp_path / "prior"
    runner.write(prior_root / "plan.json", original)
    runner.write(prior_root / "supervisor.json", {
        "status": "closed_with_missing_or_interrupted", "ended_at": 100,
        "terminated_gpu_seconds": 123, "running_gpu_seconds": 0,
        "states": {"worker-0": {"status": "complete"}, "worker-1": {"status": "stopped"}}})
    for worker, slots in original["assignments"].items():
        rows = []
        for index, slot in enumerate(slots if worker == "worker-0" else slots[:2]):
            unknown = worker == "worker-1" and index == 1
            folder = prior_root / worker / "actual" / slot["slot_id"]
            reward = {"eligible": not unknown, "completed": not unknown and index != 1,
                      "reward": None if unknown else int(index != 1)}
            guard = {"learning_unchanged": True, "rng_restored_exactly": True}
            assessment = {"status": "unknown" if unknown else "complete", "R": reward["reward"]}
            if unknown:
                assessment["execution_failure"] = {"reason": "CPU fixture context_length_exceeded"}
            row = {**slot, "status": "execution_unknown" if unknown else "closed", "reward": reward,
                   "evaluation_guard": guard, "trajectory_directory": str(folder)}
            rows.append(row)
            runner.write(folder / "slot-0/entry.json", {"reward": reward})
            runner.write(folder / "slot-0/assessment.json", assessment)
            runner.write(folder / "slot-0/raw-independent-assessment.json", assessment)
            runner.write(folder / "evaluation-guard.json", guard)
        runner.write(prior_root / worker / "actual/report.json", {
            "status": "complete" if worker == "worker-0" else "stopped_execution_unknown",
            "source_before": original["source"], "rows": rows})
        runner.write(prior_root / worker / "actual/progress.json", rows)
    recovery = runner.make_recovery_plan(tmp_path, tmp_path / "qualification.json", 1000000,
                                        prior_root, context_qualification=context)
    return prior_root, recovery


def test_explicit_recovery_keeps_all_closed_results_and_freezes_remaining_slots(tmp_path, monkeypatch):
    prior_root, spec = recovery_fixture(tmp_path, monkeypatch)
    runner.validate_plan(spec, check_files=False)
    runner.validate_recovery(spec)
    assert runner.execution_slots(spec, "worker-0") == []
    assert runner.execution_slots(spec, "worker-1") == runner.assignments()["worker-1"][1:]
    failed_closed = runner.assignments()["worker-0"][1]["slot_id"]
    assert failed_closed in spec["recovery"]["retained_closed_slot_ids"]
    assert spec["recovery"]["prior_slots"][failed_closed]["row"]["reward"]["reward"] == 0
    assert spec["automatic_retries"] is False
    mutations = [
        lambda p: p["recovery"]["execution_slot_ids"]["worker-1"].pop(),
        lambda p: p["recovery"]["execution_slot_ids"]["worker-0"].append(failed_closed),
        lambda p: p["recovery"]["prior_slots"][failed_closed]["row"]["reward"].update(reward=1),
        lambda p: p["recovery"]["prior_slots"][failed_closed]["evidence"]["entry"].update(sha256="0" * 64),
        lambda p: p["checkpoint_marker"].update(sha256="0" * 64),
        lambda p: p.pop("context_qualification"),
    ]
    for mutate in mutations:
        bad = copy.deepcopy(spec)
        mutate(bad)
        with pytest.raises(ValueError):
            runner.validate_recovery(bad)
    supervisor = read_json(prior_root / "supervisor.json")
    supervisor.update(status="running", ended_at=None)
    runner.write(prior_root / "supervisor.json", supervisor)
    with pytest.raises(ValueError, match="terminal"):
        runner.make_recovery_plan(tmp_path, tmp_path / "qualification.json", 1000000, prior_root,
                                  context_qualification=tmp_path / "context-qualification.json")


def test_retained_worker_returns_without_gpu_or_model_loading(tmp_path, monkeypatch):
    _, spec = recovery_fixture(tmp_path, monkeypatch)
    path = tmp_path / "recovery-plan.json"
    runner.write(path, spec)
    monkeypatch.setattr(runner, "validate_plan", lambda plan: plan)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr(runner, "resources", lambda: pytest.fail("Retained worker must not query a GPU"))
    result = runner.run_worker(path, tmp_path / "retained-worker", "worker-0")
    assert result["status"] == "retained" and result["slots"] == [] and result["rows"] == []
    assert len(result["retained_closed_slot_ids"]) == 4


def test_recovery_supervisor_does_not_queue_the_retained_worker(tmp_path, monkeypatch):
    _, spec = recovery_fixture(tmp_path, monkeypatch)
    spec["queue_deadline_at"] = 0
    path = tmp_path / "recovery-plan.json"
    runner.write(path, spec)
    monkeypatch.setattr(runner, "validate_plan", lambda plan: plan)
    monkeypatch.setattr(runner, "resources", lambda: pytest.fail("Expired queue must not query a GPU"))
    result = runner.supervise(path, tmp_path / "recovery-run")
    retained = result["states"]["worker-0"]
    assert retained["status"] == "retained" and retained["attempted"] is False
    assert retained["slots"] == [] and "gpu" not in retained
    pending = result["states"]["worker-1"]
    assert pending["status"] == "not_started_wait_deadline" and len(pending["slots"]) == 3
    assert result["terminated_gpu_seconds"] == 0


def reservation_fixture(tmp_path, monkeypatch):
    prior, _ = recovery_fixture(tmp_path, monkeypatch)
    folder = tmp_path / "reservation"
    launch = folder / "launch.json"
    runner.write(launch, {"pid": 12345, "start_ticks": 42, "physical_gpu": 5,
                          "user_authorization": "CPU fixture explicit reservation"})
    runner.write(folder / "state.json", {"pid": 12345, "physical_gpu": 5, "gpu_uuid": "GPU-5",
                                        "status": "reserved", "ready_at": 10, "heartbeat_at": 100, "model_calls": 0})
    spec = runner.make_recovery_plan(tmp_path, tmp_path / "qualification.json", 1000000, prior,
                                    context_qualification=tmp_path / "context-qualification.json", reservation_launch=launch)
    monkeypatch.setattr(runner.time, "time", lambda: 100)
    return spec


@pytest.mark.parametrize("foreign_after", [False, True])
def test_owned_reservation_handoff_separates_hold_time_and_handles_competing_job(tmp_path, monkeypatch, foreign_after):
    spec = reservation_fixture(tmp_path, monkeypatch)
    before, after = resources(), resources()
    before["processes"]["stdout"] = "GPU-5, 12345, 78000, CPU-reservation\n"
    if foreign_after:
        after["processes"]["stdout"] = "GPU-5, 67890, 78000, CPU-other-job\n"
    samples, released = iter([before, after]), []
    monkeypatch.setattr(runner, "resources", lambda: next(samples))
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {"pid": pid, "alive": not released, "start_ticks": 42})
    monkeypatch.setattr(runner, "_release_reservation_pid", lambda pid, ticks: released.append((pid, ticks)))
    root = tmp_path / "handoff"
    card = runner.consume_owned_reservation(spec, root)
    assert released == [(12345, 42)]
    assert card is None if foreign_after else card["index"] == 5
    proof = read_json(root / "reservation-handoff.json")
    assert proof["status"] == "released" and proof["reservation_held_seconds"] == 90
    assert proof["model_generation_calls"] == 0
    assert proof["immediate_capacity_available"] is not foreign_after


@pytest.mark.parametrize("bad_identity", [True, False])
def test_reservation_identity_or_exclusive_ownership_failure_never_signals(tmp_path, monkeypatch, bad_identity):
    spec = reservation_fixture(tmp_path, monkeypatch)
    sample = resources()
    sample["processes"]["stdout"] = "GPU-5, 12345, 78000, CPU-reservation\nGPU-5, 67890, 1, CPU-other-job\n"
    monkeypatch.setattr(runner, "resources", lambda: sample)
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {
        "pid": pid, "alive": True, "start_ticks": 99 if bad_identity else 42})
    monkeypatch.setattr(runner, "_release_reservation_pid", lambda *args: pytest.fail("Unsafe release"))
    with pytest.raises(ValueError):
        runner.consume_owned_reservation(spec, tmp_path / "handoff")


@pytest.mark.parametrize("identity_matches", [False, True])
def test_reservation_signal_targets_only_verified_pid_descriptor(monkeypatch, identity_matches):
    actions = []
    monkeypatch.setattr(runner.os, "pidfd_open", lambda pid: 77, raising=False)
    monkeypatch.setattr(runner.os, "close", lambda descriptor: actions.append(("close", descriptor)))
    monkeypatch.setattr(runner.signal, "pidfd_send_signal", lambda fd, sig: actions.append(("signal", fd, sig)), raising=False)
    monkeypatch.setattr(runner, "worker_identity", lambda pid: {"alive": True, "start_ticks": 42 if identity_matches else 43})
    if identity_matches:
        runner._release_reservation_pid(12345, 42)
        assert actions == [("signal", 77, runner.signal.SIGTERM), ("close", 77)]
    else:
        with pytest.raises(ValueError, match="identity"):
            runner._release_reservation_pid(12345, 42)
        assert actions == [("close", 77)]


def resources():
    return {"gpus": {"returncode": 0, "stdout": (
        "0, GPU-0, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "4, GPU-4, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        "5, GPU-5, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n")},
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
    assert [c["index"] for c in runner.available_cards(plan(), resources())] == [5]
    assert runner.available_cards(plan(), resources(), excluded=[5]) == []
    occupied = resources()
    occupied["processes"]["stdout"] = "GPU-5, 11, 100, another-fixture\n"
    assert runner.available_cards(plan(), occupied) == []
    incomplete = resources()
    incomplete["processes"]["returncode"] = 1
    assert runner.available_cards(plan(), incomplete) == []
    malformed = resources()
    malformed["gpus"]["stdout"] = "5, GPU-5, A100, nan, 81920, 0\n"
    assert runner.available_cards(plan(), malformed) == []


def test_capacity_admission_uses_only_gpu5_even_if_all_cards_are_idle():
    sample = resources()
    sample["gpus"]["stdout"] = "".join(
        f"{index}, GPU-{index}, NVIDIA A100-SXM4-80GB, 81000, 81920, 0\n"
        for index in range(8))
    assert [card["index"] for card in runner.available_cards(plan(), sample)] == [5]


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
            assert sum(process.returncode is None for process in processes.values()) <= 1
            from pathlib import Path
            destination = Path(argv[argv.index("--output") + 1])
            self.destination = destination
            destination.mkdir(parents=True)
            (destination / "report.json").write_text(json.dumps({"status": "complete", "rows": [{"status": "closed"}] * 4}))
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
    assert {gpu for gpu, _ in observed} == {5}
    assert all(state["gpu_budget_seconds"] is None for state in summary["states"].values())
    assert all(state["elapsed_gpu_seconds"] >= elapsed for state in summary["states"].values())
    if expected_status == "complete":
        assert all(state["status"] == "complete" and state["closed_slots"] == 4
                   for state in summary["states"].values())
    else:
        assert all(state["stop_reason"] == "single_task_budget" for state in summary["states"].values())
