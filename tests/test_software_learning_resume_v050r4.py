"""CPU-only controls for the dual-Q owner and pre-reserved-process handoff."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r4 as host
from scripts import software_learning_resume_supervisor_v050r4 as supervisor
from scripts import software_learning_resume_compute_v050r4 as compute
from scripts.run_ne_v021 import write


def plan_fixture():
    return {"inventory": json.loads(host.original.DESIGN.read_text()),
        "gpu_preference": list(host.GPU_PREFERENCE), "limits": host.LIMITS}


def test_original_16_slots_and_exactly_two_new_Q_updates():
    plan = plan_fixture()
    assert host.UPDATES == ("update-Q_plus", "update-Q_minus")
    assert len(host.WORKERS) == 18
    actual = [u for n in host.DEVELOPMENT for u in host.worker_units(plan, n)]
    prior = [u for n in host.prior.DEVELOPMENT for u in host.prior.worker_units(plan, n)]
    assert actual == prior and len({u["slot_id"] for u in actual}) == 16
    assert host.generation_caps() == host.prior.generation_caps()
    assert host.LIMITS == host.prior.LIMITS
    for name in ("collect-0", "update-B", "dev-B-0", "dev-S_star-0"):
        with pytest.raises(ValueError):
            host.worker_units(plan, name)


def test_Q_branch_completion_releases_only_own_development_without_external_dependency():
    states = supervisor.initial_states(plan_fixture())
    assert supervisor.eligible_workers(states) == list(host.UPDATES)
    states["update-Q_plus"].update(status="running", attempted=True)
    assert supervisor.eligible_workers(states) == ["update-Q_minus"]
    states["update-Q_minus"].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(states) == [n for n in host.DEVELOPMENT if n.startswith("dev-Q_minus-")]
    states["update-Q_plus"].update(status="complete")
    assert supervisor.eligible_workers(states) == list(host.DEVELOPMENT)
    states["dev-Q_plus-0"].update(attempted=True)
    assert "dev-Q_plus-0" not in supervisor.eligible_workers(states)


@pytest.mark.parametrize("branch", ["Q_plus", "Q_minus"])
def test_training_guard_uses_exact_branch_allocation(monkeypatch, branch):
    budget = {"remaining_seconds": 100, "sha256": branch}
    plan = {"q_compute_replay": {"branches": {branch: budget}}}
    receipt = {"started_at": 10, "maximum_seconds": 100, "replay_budget_sha256": branch}
    monkeypatch.setattr(compute, "training_stop_reason", lambda r, now: None if now < 110 else "exhausted")
    assert supervisor.training_stop_reason(plan, "update-" + branch, receipt, now=79) is None
    assert supervisor.training_stop_reason(plan, "update-" + branch, receipt, now=80) == "training_compute_reclamation_reserve"
    assert supervisor.training_stop_reason(plan, "update-" + branch, {**receipt, "ended_at": 109}, now=900) is None
    assert supervisor.training_stop_reason(plan, "update-" + branch, {**receipt, "replay_budget_sha256": "other"}, now=20) == "training_compute_budget_unbound"


@pytest.mark.parametrize("branch,steps", [("Q_plus", (4, 4)), ("Q_minus", (5, 5))])
def test_completed_Q_restore_preserves_legal_original_zero_step_boundary(tmp_path, branch, steps):
    write(tmp_path / "plan.json", {})
    checkpoint = {"actor_steps": steps[0], "critic_steps": steps[1], "actor_identity": {"state": branch}}
    path = tmp_path / ("update-" + branch) / "actual/checkpoint/checkpoint.json"
    write(path, checkpoint)
    calls = []
    owner = SimpleNamespace(actor_steps=steps[0], critic_steps=steps[1],
        restore_checkpoint=lambda p: calls.append(p) or checkpoint,
        freeze_identity=lambda: checkpoint["actor_identity"])
    assert host._restored_state(owner, tmp_path, branch, tmp_path / "out") == checkpoint
    assert calls == [path.parent]


def test_adoption_publishes_owned_identity_before_exact_handoff_without_Popen(tmp_path, monkeypatch):
    binding = {"pid": 123, "start_ticks": 44, "gpu": 2, "gpu_uuid": "GPU-2",
        "actual_command": ["python", "/lease/bootstrap.py"], "launch_cwd": "/original",
        "reservation": {"target_mib": 73728}, "launched_at": 1.0, "lease_root": "/lease"}
    plan = {**plan_fixture(), "gpu2_lease": binding, "source": {"code_commit": "frozen"}}
    summary = {"states": supervisor.initial_states(plan)}
    trace = []
    class Process:
        pid = 123
        def __init__(self, actual):
            assert actual == binding
        def assert_owned(self):
            trace.append("identity")
    monkeypatch.setattr(supervisor.adoption, "AdoptedProcess", Process)
    monkeypatch.setattr(supervisor.adoption, "observe_lease", lambda b: {"status": "running", "worker_entry_at": None})
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"alive": True, "start_ticks": 44})
    monkeypatch.setattr(supervisor, "TelemetryGuard", lambda *a, **kw: "guard")
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not replace lease"))
    def publish():
        write(tmp_path / "supervisor.json", summary)
        trace.append("published")
    def handoff(actual, *, source_commit):
        state = json.loads((tmp_path / "supervisor.json").read_text())["states"]["update-Q_plus"]
        assert state["status"] == "running" and state["pid"] == 123
        assert trace[-1] == "registered" and source_commit == "frozen"
        launch = json.loads((tmp_path / "update-Q_plus/worker-launch.json").read_text())
        assert launch["actual_command"] == binding["actual_command"]
        assert launch["cwd"] == "/original" and launch["actual_log"] == "/lease/reservation.log"
        assert launch["worker_entry"]["module"] == host.MODULE
        trace.append("handoff")
        return {"path": "handoff", "sha256": "proof"}
    monkeypatch.setattr(supervisor.adoption, "write_handoff", handoff)
    process, guard = supervisor.adopt_reserved(tmp_path, plan, summary, publish=publish,
        on_owned=lambda p, g: trace.append("registered"))
    assert process.pid == 123 and guard == "guard"
    assert trace == ["identity", "published", "registered", "handoff", "published"]
    assert not (tmp_path / "update-Q_plus/worker.log").exists()


def test_runtime_rejects_Qplus_replacement_and_preserves_normal_worker_contract(tmp_path, monkeypatch):
    plan = plan_fixture()
    plan["native_python"] = "/python"
    binding = {"gpu_index": 2, "gpu_uuid": "gpu2"}
    monkeypatch.setattr(host.resource, "binding_from_env", lambda: binding)
    name = "update-Q_plus"
    command = ["/python", "-m", host.MODULE, "worker", "--run-root", str(tmp_path),
        "--worker", name, "--output", str(tmp_path / name / "actual")]
    state = {"worker": name, "attempted": True, "status": "running", "reservation": binding,
        "gpu": 2, "gpu_uuid": "gpu2", "command": command}
    launch = {"reservation": binding, "gpu": 2, "actual_command": command, "cwd": str(host.SOURCE),
        "original_worker": name, "planned_units": [], "launch_mode": "popen"}
    write(tmp_path / "plan.json", plan)
    write(tmp_path / "supervisor.json", {"states": {name: state}})
    write(tmp_path / name / "worker-launch.json", launch)
    with pytest.raises(ValueError, match="pre-reservation"):
        host.runtime_reservation(tmp_path, name)
    other = "update-Q_minus"
    command[command.index(name)] = other
    command[-1] = str(tmp_path / other / "actual")
    state.update(worker=other)
    launch.update(original_worker=other)
    write(tmp_path / "supervisor.json", {"states": {other: state}})
    write(tmp_path / other / "worker-launch.json", launch)
    assert host.runtime_reservation(tmp_path, other) == binding


def test_terminal_r3_inventory_cannot_hide_attempted_worker(tmp_path, monkeypatch):
    plan = {"source": "r3"}
    state = {"status": "stopped", "attempted": False, "stop_reason": "unopened_work_paused", "elapsed_gpu_seconds": 0}
    summary = {"source": "r3", "status": "closed_with_unknowns", "ended_at": 1, "observer_pid": 100,
        "states": {n: copy.deepcopy(state) for n in host.prior.WORKERS}}
    monkeypatch.setattr(host, "worker_identity", lambda p: {"alive": False})
    host._terminal_unstarted(tmp_path, plan, summary)
    summary["states"]["update-Q_minus"]["attempted"] = True
    with pytest.raises(ValueError, match="unstarted"):
        host._terminal_unstarted(tmp_path, plan, summary)
