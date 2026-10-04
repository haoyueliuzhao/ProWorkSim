"""Narrow CPU recovery/ownership controls; never start or stop a real process."""
import copy
import json
from pathlib import Path

import pytest

from scripts import recover_software_model_selection_v030 as recovery
from scripts import software_model_selection_v030 as canonical
from scripts.run_ne_v021 import reference, write


@pytest.fixture
def previous(tmp_path, monkeypatch):
    monkeypatch.setattr(canonical, "reference", lambda path: {"path": str(path), "sha256": "1" * 64})
    plan = canonical.make_plan(tmp_path / "data", tmp_path / "q.json")
    plan["source"] = {"code_commit": "previous-source", "code_dirty": False, "source_tree_sha256": "2" * 64}
    root = tmp_path / "original"
    proof = tmp_path / "original-proof.json"
    write(proof, {"cpu_fixture": True})
    states = {}
    for candidate in canonical.CANDIDATES:
        is_retained = candidate == recovery.RETAINED
        rows = [{**copy.deepcopy(row), "category": canonical.case_spec(row["case_id"])["category"],
                 "status": "closed", "R": 0, "complete_work": False, "format_errors": 0,
                 "entry": reference(proof), "assessment": reference(proof), "evaluation_guard": reference(proof)}
                for row in plan["inventories"][candidate]] if is_retained else []
        report = {"status": "complete" if is_retained else "interrupted_or_error", "rows": rows,
                  "source_before": plan["source"], "source_after": plan["source"]}
        if is_retained:
            report["qualification"] = {"inference_ready": True, "training_ready": True}
        else:
            report["error"] = copy.deepcopy(recovery.FAILURE)
        write(root / candidate / "actual/report.json", report)
        (root / candidate / "worker.log").write_text("CPU fixture original log\n")
        states[candidate] = {"status": "complete" if is_retained else "stopped", "elapsed_gpu_seconds": 100.0 if is_retained else 10.0}
    write(root / "plan.json", plan)
    write(root / "supervisor.json", {"status": "finite_batch_no_qualified_candidate", "ended_at": 123,
                                     "states": states})
    return root, plan


def test_recovery_retains_all_old_9b_failures_and_rejects_sampled_retries(previous, tmp_path):
    root, plan = previous
    before = (root / recovery.RETAINED / "actual/report.json").read_bytes()
    frozen = recovery.prior_snapshot(root)
    assert frozen["workers"][recovery.RETAINED]["state"]["status"] == "complete"
    made = recovery.make_plan(tmp_path / "data", tmp_path / "q.json", root)
    recovery.validate_plan(made, check_files=False)
    assert made["execution_candidates"] == list(recovery.REOPENED)
    assert made["new_screening_episodes_max"] == 24 and made["cumulative_screening_episodes_max"] == 36
    assert made["canonical_plan"]["inventories"] == plan["inventories"]
    assert (root / recovery.RETAINED / "actual/report.json").read_bytes() == before
    write(root / recovery.REOPENED[0] / "actual/resident/calls/actual-call.json", {"cpu_fixture": True})
    with pytest.raises(ValueError, match="before any real model sampling"):
        recovery.prior_snapshot(root)


def reservation(tmp_path, monkeypatch):
    directory = tmp_path / "reservation"
    launch = {"pid": 120, "start_ticks": 456, "physical_gpu": 5, "gpu_uuid": "GPU-owned", "user_authorization": "CPU fixture"}
    state = {**launch, "status": "reserved", "model_calls": 0, "ready_at": 100.0, "heartbeat_at": 164.0}
    write(directory / "launch.json", launch)
    write(directory / "state.json", state)
    rows = [{"observed_at": float(now), "uuid": "GPU-owned", "pids": [120]} for now in range(100, 165, 2)]
    (directory / "observations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(recovery, "worker_identity", lambda pid: {"alive": True, "start_ticks": 456})
    return directory, launch, state


def test_reservation_requires_stable_fresh_exact_owned_process(tmp_path, monkeypatch):
    directory, launch, state = reservation(tmp_path, monkeypatch)
    assert recovery.reservation_ready(directory, now=164)["continuous_exclusive_seconds"] == 64
    assert recovery.reservation_ready(directory, now=190) is None
    monkeypatch.setattr(recovery, "worker_identity", lambda pid: {"alive": True, "start_ticks": 999})
    assert recovery.reservation_ready(directory, now=164) is None
    state["pid"] = 999
    write(directory / "state.json", state)
    with pytest.raises(ValueError, match="same authorized"):
        recovery.reservation_ready(directory, now=164)


def gpu_sample(pids, *, free=2907):
    return {"gpus": {"returncode": 0, "stdout": f"5, GPU-owned, NVIDIA A100-SXM4-80GB, {free}, 81920, 0\n"},
            "processes": {"returncode": 0, "stdout": "".join(f"GPU-owned, {pid}, 100, fixture\n" for pid in pids)}}


def test_pidfd_handoff_uses_existing_stability_without_second_wait(tmp_path, monkeypatch):
    directory, launch, state = reservation(tmp_path, monkeypatch)
    proof = recovery.reservation_ready(directory, now=164)
    monkeypatch.setattr(recovery, "reservation_ready", lambda directory: copy.deepcopy(proof))
    samples = iter([gpu_sample([120]), gpu_sample([], free=80532)])
    monkeypatch.setattr(recovery, "resources", lambda: next(samples))
    signals = []
    monkeypatch.setattr(recovery, "_release_reservation_pid", lambda pid, ticks: signals.append((pid, ticks)))
    monkeypatch.setattr(recovery, "_await_gone", lambda pid, ticks: {"alive": False})
    plan = {"reservation_directory": str(directory), "canonical_plan": {"limits": canonical.LIMITS, "gpu_preference": list(range(8))}}
    card = recovery.consume_reservation(plan, tmp_path / "new-run")
    assert card["index"] == 5 and signals == [(120, 456)]
    receipt = json.loads((tmp_path / "new-run/reservation-handoff.json").read_text())
    assert receipt["status"] == "released" and receipt["second_empty_card_stability_wait_required"] is False


def test_handoff_never_signals_a_competing_job(tmp_path, monkeypatch):
    directory, _, _ = reservation(tmp_path, monkeypatch)
    proof = recovery.reservation_ready(directory, now=164)
    monkeypatch.setattr(recovery, "reservation_ready", lambda directory: copy.deepcopy(proof))
    monkeypatch.setattr(recovery, "resources", lambda: gpu_sample([120, 999]))
    monkeypatch.setattr(recovery, "_release_reservation_pid", lambda *args: pytest.fail("No signal is authorized"))
    plan = {"reservation_directory": str(directory), "canonical_plan": {"limits": canonical.LIMITS}}
    assert recovery.consume_reservation(plan, tmp_path / "new-run") is None


def test_cancel_stops_owned_watcher_before_owned_child(tmp_path, monkeypatch):
    directory, child, _ = reservation(tmp_path, monkeypatch)
    watcher = {"pid": 100, "start_ticks": 123, "purpose": "CPU watcher"}
    write(directory / "watcher-launch.json", watcher)
    live = {100: 123, 120: 456}
    signals = []
    monkeypatch.setattr(recovery, "worker_identity", lambda pid: {"alive": pid in live, "start_ticks": live.get(pid)})

    def release(pid, ticks):
        assert live[pid] == ticks
        signals.append(pid)
        del live[pid]

    monkeypatch.setattr(recovery, "_release_reservation_pid", release)
    recovery.cancel_reservation({"reservation_directory": str(directory)}, tmp_path / "run")
    assert signals == [100, 120] and (directory / "cancel").exists()


def test_supervisor_launches_only_new_candidates_and_counts_old_cost(previous, tmp_path, monkeypatch):
    root, old = previous
    plan = recovery.make_plan(tmp_path / "data", tmp_path / "q.json", root)
    plan_path = tmp_path / "recovery-plan.json"
    write(plan_path, plan)
    monkeypatch.setattr(recovery, "validate_plan", lambda value: value)
    monkeypatch.setattr(recovery, "code_identity", lambda: plan["source"])
    monkeypatch.setattr(recovery, "implementation_files", lambda: plan["implementation_files_sha256"])
    clock = {"now": 100.0}
    monkeypatch.setattr(recovery.time, "time", lambda: clock["now"])
    monkeypatch.setattr(recovery.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + 60))
    monkeypatch.setattr(recovery, "resources", lambda: gpu_sample([], free=80532))
    monkeypatch.setattr(recovery, "target_resources", lambda *a, **k: {})
    monkeypatch.setattr(recovery, "worker_identity", lambda pid: {"start_ticks": pid})
    monkeypatch.setattr(recovery, "TelemetryGuard", lambda *a, **k: None)
    started = []

    class Process:
        returncode = 0

        def __init__(self, argv, **kwargs):
            candidate = argv[argv.index("--worker") + 1]
            assert candidate in recovery.REOPENED
            started.append(candidate)
            self.pid = 1000 + len(started)
            write(Path(argv[argv.index("--output") + 1]) / "report.json",
                  {"status": "qualification_failed", "qualification": {"inference_ready": False, "training_ready": False}, "rows": []})

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(recovery.subprocess, "Popen", Process)
    result = recovery.supervise(plan_path, tmp_path / "new-run")
    assert started == list(recovery.REOPENED)
    assert (tmp_path / "new-run" / recovery.RETAINED).resolve() == root / recovery.RETAINED
    assert result["states"][recovery.RETAINED]["retained_original"] is True
    assert result["states"][recovery.RETAINED]["elapsed_gpu_seconds"] == 100
    for candidate in recovery.REOPENED:
        state = result["states"][candidate]
        assert state["prior_failed_worker_gpu_seconds"] == 10
        assert state["elapsed_gpu_seconds"] == 10 + state["recovery_worker_gpu_seconds"]
    assert result["status"] == "finite_batch_no_qualified_candidate"
