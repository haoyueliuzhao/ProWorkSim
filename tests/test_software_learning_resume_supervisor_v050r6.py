"""Finite CPU controls for the global cap and unchanged zero-model retry boundary."""
import json
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r6 as host
from scripts import software_learning_resume_supervisor_v050r6 as supervisor
from scripts.run_ne_v021 import reference, write


def plan_fixture():
    return {"inventory": json.loads(host.original.DESIGN.read_text()),
        "gpu_preference": list(host.GPU_PREFERENCE), "limits": host.LIMITS,
        "source": {"code_commit": "frozen", "code_dirty": False, "source_tree_sha256": "tree"},
        "source_root": str(host.SOURCE), "native_python": "/python",
        "parent_plan": {"path": "/old/plan.json", "sha256": "old"},
        "external_updates": {branch: {"identity": {"gpu": gpu}}
            for branch, gpu in (("Q_plus", 2), ("Q_minus", 1))},
        "resource_policy": host.resource.RESOURCE_POLICY,
        "startup_retry_policy": host.RETRY_POLICY, "single_slot_scheduling": {},
        "prior_artifact_roots": []}


def observations(residents=0):
    return {branch: {"status": "running", "resident_count": 1, "excluded_gpu": gpu}
        if index < residents else {"status": "complete", "resident_count": 0,
            "excluded_gpu": None, "terminal": {"branch": branch, "checkpoint": "bound-" + branch}}
        for index, (branch, gpu) in enumerate((("Q_plus", 2), ("Q_minus", 1)))}


def states_with_active(count):
    states = supervisor.initial_states(plan_fixture())
    for gpu, state in enumerate(list(states.values())[:count]):
        state.update(status="running", attempted=True, gpu=gpu)
    return states


@pytest.mark.parametrize("external_count", [0, 1, 2])
@pytest.mark.parametrize("owned_count", [0, 1, 2, 3, 4])
def test_global_cap_zero_through_four_includes_both_external_updates(owned_count, external_count):
    states, external = states_with_active(owned_count), observations(external_count)
    if owned_count + external_count > 4:
        with pytest.raises(ValueError, match="cap"):
            supervisor.resident_capacity(states, external)
    else:
        actual = supervisor.resident_accounting(states, external)
        assert actual["total_residents"] == owned_count + external_count
        assert actual["slots_available"] == 4 - owned_count - external_count
        assert actual["maximum_residents"] == actual["max_residents"] == 4


def test_unknown_external_identity_counts_conservatively_or_rejects_release():
    states = states_with_active(2)
    assert supervisor.resident_capacity(states, None) == 0
    unknown = observations(2)
    unknown["Q_plus"].update(status="fault", error="identity unavailable")
    assert supervisor.resident_capacity(states, unknown) == 0
    assert supervisor.eligible_workers(states, unknown) == []
    unknown["Q_plus"]["resident_count"] = 0
    with pytest.raises(ValueError, match="occupies"):
        supervisor.resident_capacity(states, unknown)
    with pytest.raises(ValueError, match="Both"):
        supervisor.resident_capacity(states, {"Q_plus": unknown["Q_plus"]})


def test_launch_intent_already_occupies_place_and_release_one_admits_one():
    states, external = states_with_active(3), observations(1)
    assert supervisor.resident_capacity(states, external) == 0
    name = list(states)[0]
    states[name].update(status="complete")
    assert supervisor.resident_capacity(states, external) == 1
    next_name = list(states)[3]
    states[next_name].update(status="not_started", attempted=True, gpu=7)
    assert supervisor.resident_capacity(states, external) == 0
    states[next_name]["status"] = "running"
    assert supervisor.resident_capacity(states, external) == 0


def test_branch_readiness_is_independent_and_resource_backoff_does_not_block_peer():
    states = states_with_active(0)
    external = observations(2)
    assert supervisor.eligible_workers(states, external, now=100) == []
    external["Q_minus"] = observations(0)["Q_minus"]
    ready = supervisor.eligible_workers(states, external, now=100)
    assert len(ready) == 8 and all(name.startswith("dev-Q_minus-") for name in ready)
    states[ready[0]].update(next_resource_attempt_at=105, resource_attempt_number=1)
    assert supervisor.eligible_workers(states, external, now=100) == ready[1:]
    assert supervisor.eligible_workers(states, external, now=105) == ready
    external["Q_plus"] = observations(0)["Q_plus"]
    assert len(supervisor.eligible_workers(states, external, now=105)) == 16
    assert set(states) == set(host.DEVELOPMENT) and host.UPDATES == ()


def test_wait_reasons_distinguish_dependency_concurrency_and_free_gpu():
    states = states_with_active(0)
    assert supervisor.dispatch_diagnostics(states, observations(2), now=100)["dispatch_status"] == "awaiting_dependencies"
    assert supervisor.dispatch_diagnostics(states, observations(0), now=100,
        resource_wait=True)["dispatch_status"] == "resource_wait"
    full = states_with_active(4)
    diagnostic = supervisor.dispatch_diagnostics(full, observations(0), now=100)
    assert diagnostic["dispatch_status"] == "concurrency_wait" and diagnostic["slots_available"] == 0


def test_exclude_external_gpus_until_exact_complete_and_reject_forged_exclusion():
    states, plan = states_with_active(1), plan_fixture()
    assert supervisor.excluded_gpus(states, None, plan) == [0, 1, 2]
    assert supervisor.excluded_gpus(states, observations(2), plan) == [0, 1, 2]
    assert supervisor.excluded_gpus(states, observations(0), plan) == [0]
    external = observations(2)
    external["Q_plus"]["excluded_gpu"] = None
    with pytest.raises(ValueError, match="bound physical"):
        supervisor.excluded_gpus(states, external, plan)


def test_terminal_receipts_separate_branches_and_cannot_be_replaced(tmp_path):
    for branch, external in observations(0).items():
        ref = supervisor.store_external_terminal(tmp_path, branch, external["terminal"])
        assert ref["path"].endswith("external-" + branch + "-complete.json")
        assert supervisor.store_external_terminal(tmp_path, branch, external["terminal"]) == ref
        changed = {**external["terminal"], "checkpoint": "different"}
        with pytest.raises(ValueError, match="changed"):
            supervisor.store_external_terminal(tmp_path, branch, changed)
    with pytest.raises(ValueError, match="own branch"):
        supervisor.store_external_terminal(tmp_path, "Q_plus", observations(0)["Q_minus"]["terminal"])


@pytest.mark.parametrize("worker", ["update-Q_plus", "update-Q_minus"])
def test_supervisor_cannot_signal_either_external_update(worker):
    with pytest.raises(ValueError, match="external"):
        supervisor.request_stop("/run", worker, SimpleNamespace(pid=10),
            {"pid": 10, "worker": worker}, "test")


def resource_evidence(root, plan, state, *, pid, ticks):
    """Small inherited zero-model startup contract; no torch, GPU or model calls."""
    name, folder = state["worker"], root / state["worker"]
    binding = state["reservation"]
    process = {"pid": pid, "available": True, "alive": True, "start_ticks": ticks}
    identity = {"worker": name, "run_root": str(root), "source": plan["source"],
        "source_root": str(host.SOURCE), "plan": reference(root / "plan.json"),
        "worker_launch": reference(folder / "worker-launch.json"), "process_identity": process,
        "resource_attempt_number": state["resource_attempt_number"]}
    receipt = {"version": host.startup_resource.VERSION, "status": "resource_unavailable",
        "retryable": True, "reason": "pre_model_cuda_out_of_memory", "phase": "cuda_capacity_snapshot",
        "loader_not_entered": True, "new_model_calls": 0, "new_backward_calls": 0,
        "new_optimizer_steps": 0, "live_reservation_tensors": 0, "same_process_resource_retries": 0,
        "cuda_requeried_after_error": False, "restart_requires_fresh_process": True,
        "output": str(folder / "startup"), "pid": pid, "binding": binding, "identity": identity}
    write(folder / "startup/startup-resource-receipt.json", receipt)
    write(folder / "startup/task.json", {"pid": pid, "kind": "reservation_wait", "loader_not_entered": True,
        "new_model_calls": 0, "new_backward_calls": 0})
    write(folder / "reservation-binding-verified.json", {"identity": identity, "reservation": binding,
        "verified_before_cuda_or_model_load": True})
    (folder / "startup/native-cache-resources.jsonl").write_text(json.dumps(receipt) + "\n")
    write(folder / "resource-wait.json", {"version": host.VERSION, "status": "resource_wait", "worker": name,
        "identity": identity, "reservation": binding, "source_before": plan["source"], "source_after": plan["source"],
        "retryable": True, "model_started": False, "new_model_calls": 0, "new_backward_calls": 0,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_training_interval_seconds": 0,
        "loader_not_entered": True, "resource_receipt": reference(folder / "startup/startup-resource-receipt.json"),
        "raw_fault": receipt})


@pytest.mark.parametrize("outcome", ["complete", "resource_retry", "model_failure"])
def test_full_loop_multicard_burst_and_retry_never_exceed_four(tmp_path, monkeypatch, outcome):
    plan = plan_fixture()
    write(tmp_path / "plan.json", plan)
    clock = {"now": 100.0, "sleeps": 0}
    def now():
        clock["now"] += .01
        return clock["now"]
    def sleep(seconds):
        clock["now"] += max(5, seconds)
        clock["sleeps"] += 1
        assert clock["sleeps"] < 30
    monkeypatch.setattr(supervisor.time, "time", now)
    monkeypatch.setattr(supervisor.time, "sleep", sleep)
    monkeypatch.setattr(host, "frozen", lambda root: plan)
    def observe(*args, **kwargs):
        result = observations(0)
        if clock["sleeps"] < 2:
            result["Q_minus"] = observations(2)["Q_minus"]
        return result
    monkeypatch.setattr(host, "observe_externals", observe)
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda root: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda root: SimpleNamespace(free=10**15))
    monkeypatch.setattr(supervisor, "worker_env", lambda *args: {"PYTHONPATH": "cpu-test"})
    monkeypatch.setattr(supervisor, "allowed_resources", lambda: {})
    monkeypatch.setattr(supervisor, "available_cards", lambda plan, sample, excluded: [
        {"index": n, "uuid": f"GPU-{n}", "free_mib": 78000} for n in range(8) if n not in excluded])
    monkeypatch.setattr(supervisor, "TelemetryGuard", lambda *args, **kwargs: None)
    monkeypatch.setattr(supervisor, "target_resources", lambda *args, **kwargs: {})
    monkeypatch.setattr(supervisor, "request_stop", lambda *args: pytest.fail("No process signals are needed"))
    processes, launches = {}, []
    first = host.WORKERS[0]
    class Process:
        def __init__(self, command, **kwargs):
            name = command[command.index("--worker") + 1]
            self.pid, self.returncode, self.waited = 1000 + len(launches), 0, False
            processes[self.pid] = self
            summary = json.loads((tmp_path / "supervisor.json").read_text())
            state = summary["states"][name]
            assert summary["total_residents"] <= 4 and summary["slots_available"] >= 0
            assert summary["owned_residents"] + summary["external_residents"] == summary["total_residents"]
            if clock["sleeps"] < 2:
                assert state["gpu"] != 1 and name.startswith("dev-Q_plus-")
            launches.append((name, state["resource_attempt_number"], summary["total_residents"]))
            folder = tmp_path / name
            if name == first and outcome == "resource_retry" and state["resource_attempt_number"] == 1:
                resource_evidence(tmp_path, plan, state, pid=self.pid, ticks=self.pid + 10)
            else:
                write(folder / "startup/model-load-intent.json", {"model_work_may_have_started": True})
                if name == first and outcome == "model_failure":
                    self.returncode = 1
                else:
                    write(folder / "actual/report.json", {"status": "complete", "source_before": plan["source"],
                        "source_after": plan["source"], "success_boundary": True,
                        "rows": [{"R": 1, "usage": {"tokens": 1}}]})
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            self.waited = True
            return self.returncode
    monkeypatch.setattr(supervisor.subprocess, "Popen", Process)
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"pid": pid, "available": True,
        "alive": not processes[pid].waited, "start_ticks": pid + 10})
    summary = supervisor.supervise(tmp_path)
    assert all(name.startswith("dev-") for name, _, _ in launches)
    assert max(total for _, _, total in launches) == 4
    assert summary["external_process_signalled"] is False
    if outcome == "model_failure":
        assert summary["status"] == "closed_with_unknowns"
        assert summary["states"][first]["model_started"] is True
        assert summary["states"][first]["resource_attempt_number"] == 1
        assert (tmp_path / "mechanism-stops" / (first + "-supervisor.json")).exists()
        assert any(state["attempted"] is False for state in summary["states"].values())
    else:
        assert summary["status"] == "complete" and summary["dispatch_status"] == "closed"
        assert all(state["status"] == "complete" for state in summary["states"].values())
        assert len(launches) == 16 + (outcome == "resource_retry")
        assert not (tmp_path / "mechanism-stops").exists()
        for branch in supervisor.BRANCHES:
            assert (tmp_path / ("external-" + branch + "-complete.json")).exists()
    if outcome == "resource_retry":
        state = summary["states"][first]
        assert state["resource_attempt_number"] == 2 and len(state["resource_attempt_history"]) == 1
        receipt = host.check_seal(json.loads(host.checked(state["resource_attempt_history"][0]).read_text()))
        assert summary["resource_attempt_gpu_seconds"] == receipt["elapsed_gpu_seconds"]
        assert summary["new_worker_gpu_seconds_observed"] == pytest.approx(
            summary["closed_worker_gpu_seconds"] + receipt["elapsed_gpu_seconds"])
        assert launches[1][0] != first  # other ready work proceeds before retry
        for mapping in receipt["archive_mapping"]:
            assert mapping["original"]["sha256"] == mapping["archived"]["sha256"]


def test_old_supervisor_bindings_are_not_mutated():
    assert supervisor.previous.WORKERS != supervisor.WORKERS
    assert "update-Q_minus" in supervisor.previous.WORKERS
    assert supervisor.previous.host.VERSION.endswith("r5")
    assert supervisor.verify_resource_failure.__code__ is supervisor.previous.verify_resource_failure.__code__
    assert supervisor.archive_resource_attempt.__code__ is supervisor.previous.archive_resource_attempt.__code__
    assert host.LIMITS["max_parallel_model_instances"] == 4
    assert supervisor.previous.host.LIMITS["max_parallel_model_instances"] is None
