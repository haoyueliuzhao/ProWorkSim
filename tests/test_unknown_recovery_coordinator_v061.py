import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import reference

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "v061_coordinator_test", ROOT / "tools/run_unknown_recovery_v061.py"
)
coordinator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinator)


def simulated_batch(
    tmp_path, monkeypatch, *, local_failure=False, unsafe_failure=False, resident_count=2
):
    monkeypatch.setattr(coordinator, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(coordinator, "coordinator_limits", lambda: {"fixture": "bounded"})
    monkeypatch.setattr(
        coordinator.policy,
        "require_v061_allowed",
        lambda *args, **kwargs: {"approved": "cpu fixture"},
    )
    monkeypatch.setattr(coordinator.policy, "sources", lambda: [])

    def write(name, body):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
        return reference(path)

    tasks = ("scikit-learn__scikit-learn-14894", "other-task")
    configs = {task: write(task + "-config.json", {"instance_id": task}) for task in tasks}
    rows = [
        {"slot_id": key, "instance_id": tasks[1], "measurement_kind": "fresh_generation_recovery"}
        for key in ("fast", "slow")
    ]
    dispatch = write(
        "dispatch-plan.json", {"rows": rows, "environments": {task: {} for task in tasks}}
    )
    controls = []
    for task in tasks:
        for lane, kind in enumerate(("gold", "empty")):
            controls.append(
                write(
                    "control-" + task + "-" + kind + ".json",
                    {
                        "resource_key": "control-" + task + "-" + kind,
                        "original_config": configs[task],
                        "patch_kind": kind,
                        "cpuset_cpus": str(lane),
                    },
                )
            )
    snapshot = write(
        "snapshot.json",
        {"slot": {"slot_id": "snapshot"}, "original_slot_id": "snapshot", "instance_id": tasks[0]},
    )
    plan = write(
        "coordinator-plan.json",
        {"plan": dispatch, "controls": controls, "snapshot_result": snapshot},
    )
    monkeypatch.setattr(coordinator, "prepare", lambda: plan)
    diagnostic = write(
        "diagnostic.json", {"passed": True, "quiescence": {"quiescent": True, "cleanup_errors": []}}
    )
    write("diagnostic-qualification.json", {"result": diagnostic, "sources": []})
    order = []
    slow_running, fast_scored = threading.Event(), threading.Event()

    def run_request(ref, cancel_event=None):
        request = coordinator.load(ref)
        key = request["resource_key"]
        order.append(key)
        if key == "score-fast":
            assert slow_running.is_set()
            fast_scored.set()
        return {"status": "process_exited", "returncode": 0}

    def prepare_score(ref, lane=0):
        result = coordinator.load(ref)
        old = result["original_slot_id"]
        return write(
            "score-" + old + ".json",
            {
                "resource_key": "score-" + old,
                "original_slot_id": old,
                "original_config": configs[result["instance_id"]],
            },
        )

    grader = SimpleNamespace(
        run_request=run_request,
        prepare_score=prepare_score,
        selected_cpus=lambda lane: str(lane),
        trustworthy_cleanup=lambda ref: True,
        qualify=lambda task: write(task + "-qualification.json", {"passed": True}),
    )
    monkeypatch.setattr(coordinator, "grading_module", lambda: grader)
    episode = ModuleType("proworksim.software_benchmark_recovery_episode_v061")
    episode.run_diagnostic = lambda: write(
        "diagnostic.json", {"passed": True, "quiescence": {"quiescent": True, "cleanup_errors": []}}
    )

    def run_episode(row, resident, stop_event=None):
        key = row["slot_id"]
        if key == "slow":
            slow_running.set()
            if not local_failure and not unsafe_failure:
                assert fast_scored.wait(2), (
                    "Grading did not interleave with another active generation"
                )
        else:
            assert slow_running.wait(2)
        status = (
            "technical_unknown" if key == "fast" and (local_failure or unsafe_failure) else "closed"
        )
        order.append("generation-" + key)
        return write(
            "generation-" + key + ".json",
            {
                "status": status,
                "original_slot_id": key,
                "instance_id": row["instance_id"],
                "retained_objects": [{"role": "actor", "container_id": "stopped-original", "name": "own-evidence"}]
                    if local_failure and key == "fast" else [],
                "quiescence": {
                    "quiescent": not (unsafe_failure and key == "fast"),
                    "cleanup_errors": [],
                },
            },
        )

    episode.run_episode = run_episode
    resident = ModuleType("proworksim.software_benchmark_ref_resident_v061")
    resident.start_residents = lambda: [
        {"root": str(tmp_path / str(i)), "identity_value": str(i)} for i in range(resident_count)
    ]
    resident.ready_residents = resident.start_residents
    resident.stop_residents = lambda: (
        order.append("resident-cleanup") or [{"owned_unit_stopped": True}]
    )
    monkeypatch.setitem(sys.modules, episode.__name__, episode)
    monkeypatch.setitem(sys.modules, resident.__name__, resident)
    return order


def test_scoring_interleaves_with_generation_without_replaying_old_candidates(
    tmp_path, monkeypatch
):
    order = simulated_batch(tmp_path, monkeypatch)
    result = coordinator.run()
    assert result["failure"] is None
    assert len(result["scores"]) == 3 and len(result["generation"]) == 2
    assert order.index("score-fast") < order.index("generation-slow")
    assert result["original_unknowns_overwritten"] is False
    assert order[-1] == "resident-cleanup"
    with pytest.raises(ValueError, match="not automatically replayed"):
        coordinator.run()


def test_quiet_local_generation_failure_does_not_cancel_independent_job(tmp_path, monkeypatch):
    order = simulated_batch(tmp_path, monkeypatch, local_failure=True)
    result = coordinator.run()
    assert result["failure"] is None
    assert result["generation"]["fast"]["status"] == "technical_unknown"
    assert "score-fast" not in order and "score-slow" in order
    assert result["retained_objects"] == [{"original_slot_id": "fast", "role": "actor", "container_id": "stopped-original", "name": "own-evidence"}]


def test_single_resident_supports_two_independent_interleaved_episodes(tmp_path, monkeypatch):
    order = simulated_batch(tmp_path, monkeypatch, resident_count=1)
    result = coordinator.run()
    assert result["failure"] is None and len(result["generation"]) == 2
    assert order.index("score-fast") < order.index("generation-slow")


def test_termination_handler_only_requests_own_cleanup():
    import signal

    event = threading.Event()
    previous = coordinator._handle_termination(event)
    try:
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert event.is_set()
    finally:
        coordinator._restore_termination(previous)


def test_unproven_owned_cleanup_stops_new_work_but_finishes_existing_jobs(tmp_path, monkeypatch):
    simulated_batch(tmp_path, monkeypatch, unsafe_failure=True)
    result = coordinator.run()
    assert result["failure"]["kind"] == "unproven_generation_cleanup"
    assert len(result["generation"]) == 2
    assert result["resident_closure"] == [{"owned_unit_stopped": True}]


@pytest.mark.parametrize("failed", [False, True])
def test_diagnostic_result_directory_exists_before_runtime_and_failure_is_retained(tmp_path, monkeypatch, failed):
    monkeypatch.setattr(coordinator, "BATCH_ROOT", tmp_path)
    monkeypatch.setattr(coordinator.policy, "require_v061_allowed", lambda *args: {})
    monkeypatch.setattr(coordinator.policy, "sources", lambda: [])
    monkeypatch.setattr(coordinator, "diagnostic_host_limits", lambda: {"cpu": "fixture"})
    module = ModuleType("proworksim.software_benchmark_recovery_episode_v061")
    called = []
    def run_diagnostic(index=1, stop_event=None):
        assert (tmp_path / "diagnostic-attempts").is_dir()
        called.append(index)
        if failed:
            raise RuntimeError("controlled diagnostic error")
        path = tmp_path / "diagnostic-result.json"
        path.write_text(json.dumps({"passed": True, "quiescence": {"quiescent": True, "cleanup_errors": []}}))
        return reference(path)
    module.run_diagnostic = run_diagnostic
    monkeypatch.setitem(sys.modules, module.__name__, module)
    if failed:
        with pytest.raises(RuntimeError, match="controlled diagnostic error"):
            coordinator.diagnose(1)
    else:
        coordinator.diagnose(1)
        assert (tmp_path / "diagnostic-qualification.json").is_file()
    retained = json.loads((tmp_path / "diagnostic-attempts/1.json").read_text())
    if failed:
        assert retained["status"] == "runtime_exception"
        assert "controlled diagnostic error" in retained["traceback"]
    with pytest.raises(ValueError, match="already|successful"):
        coordinator.diagnose(1)
    assert called == [1]
