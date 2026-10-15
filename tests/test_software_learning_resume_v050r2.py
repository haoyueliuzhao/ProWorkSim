"""Finite CPU controls for the external-Q-plus/owned-Q-minus continuation."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r2 as host
from scripts import software_learning_resume_supervisor_v050r2 as supervisor
from scripts import software_learning_resume_compute_v050r2 as compute
from scripts.run_ne_v021 import reference, write


def inventory_plan():
    return {"inventory": json.loads(host.original.DESIGN.read_text()),
        "gpu_preference": list(host.GPU_PREFERENCE), "limits": host.LIMITS}


def external_fixture(tmp_path, *, complete=False):
    root = tmp_path / "parent"
    source = {"code_commit": "original-frozen", "code_dirty": False}
    state = {"worker": "update-Q_plus", "status": "complete" if complete else "running",
        "attempted": True, "pid": 100, "process_identity": {"start_ticks": 321},
        "gpu": 2, "gpu_uuid": "gpu2", "started_at": 10}
    if complete:
        state.update(ended_at=30, exit_code=0, elapsed_gpu_seconds=20)
    frozen_state = {"status": "stopped", "attempted": False, "stop_reason": "unopened_work_paused"}
    snapshot = {"status": "closed_with_unknowns" if complete else "running", "observer_pid": 101,
        "source": source, "states": {"update-Q_plus": state, "dev-Q_plus-0": frozen_state}}
    write(root / "supervisor.json", snapshot)
    expected = host.external_identity(state, {"source": source})
    directory = root / "update-Q_plus/actual"
    before = {"advantages": [1], "old_critic_values": [0], "rewards": [1]}
    write(root / "baseline.json", before)
    direction = {"plus_weights": {"slot": {"member": 1.1}}}
    write(root / "direction.json", direction)
    if complete:
        checkpoint = {"actor_steps": 5, "critic_steps": 5, "actor_identity": {"branch": "Q_plus"},
            "serialized_reload_exact": True}
        write(directory / "checkpoint/checkpoint.json", checkpoint)
        write(directory / "update/report.json", {**before, "stage": "complete", "status": "updated"})
        write(directory / "training-compute.json", {"ended_at": 30, "elapsed_seconds": 19})
        write(directory / "composition-before-update.json", host.seal({"weights_by_slot": direction["plus_weights"]}, "seal_sha256"))
        write(directory / "report.json", {"status": "complete", "success_boundary": True,
            "source_before": source, "source_after": source, "checkpoint": checkpoint,
            "actor_steps": 5, "critic_steps": 5, "final_actor_identity": checkpoint["actor_identity"],
            "update_report": reference(directory / "update/report.json")})
    plan = {**inventory_plan(), "parent_run_root": str(root), "external_Q_plus": expected,
        "continuation_inventory": {"parent_source": source,
            "original_supervisor_process": {"pid": 101, "start_ticks": 654},
            "closed_parent_workers": {"dev-Q_plus-0": {"state": frozen_state}},
            "B_update": reference(root / "baseline.json"),
            "materials": {"direction.json": reference(root / "direction.json")}}}
    return plan, root


def live_identity(pid):
    return {"alive": True, "start_ticks": 321 if pid == 100 else 654}


def dead_identity(pid):
    return {"alive": False}


def test_only_original16_Q_development_units_and_one_recomputation():
    plan = inventory_plan()
    assert host.WORKERS == ("update-Q_minus", "dev-Q_plus-0", "dev-Q_plus-1", "dev-Q_minus-0", "dev-Q_minus-1")
    units = [u for name in host.DEVELOPMENT for u in host.worker_units(plan, name)]
    assert len(units) == len({u["slot_id"] for u in units}) == 16
    assert all(u["sampling_seed"] in range(202610130601, 202610130609) for u in units)
    assert host.generation_caps()["including_retained_actual_tokens_upper"] == 23807260
    for worker in ("s_star", "collect-0", "update-B", "update-Q_plus", "dev-B-0"):
        with pytest.raises(ValueError):
            host.worker_units(plan, worker)


def test_running_external_counts_resident_and_never_releases_its_development(tmp_path):
    plan, _ = external_fixture(tmp_path)
    observed = host.observe_external(plan, now=100, identity_fn=live_identity)
    assert observed["status"] == "running" and observed["resident_count"] == 1 and observed["excluded_gpu"] == 2
    states = supervisor.initial_states(plan)
    assert supervisor.eligible_workers(states, observed) == ["update-Q_minus"]
    assert supervisor.resident_capacity({}, observed) == 2
    assert supervisor.resident_capacity({"one": 1, "two": 2}, observed) == 0
    states["update-Q_minus"].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(states, observed) == ["dev-Q_minus-0", "dev-Q_minus-1"]


def test_complete_external_releases_GPU_and_Qplus_shards_only_after_full_guard(tmp_path):
    plan, _ = external_fixture(tmp_path, complete=True)
    observed = host.observe_external(plan, now=100, identity_fn=dead_identity)
    assert observed["status"] == "complete" and observed["resident_count"] == 0 and observed["excluded_gpu"] is None
    assert supervisor.resident_capacity({}, observed) == 3
    assert supervisor.eligible_workers(supervisor.initial_states(plan), observed) == ["update-Q_minus", "dev-Q_plus-0", "dev-Q_plus-1"]
    receipt = supervisor.store_external_terminal(tmp_path / "resume", observed["terminal"])
    assert json.loads(Path(receipt["path"]).read_text())["new_gpu_worker_seconds_by_observer"] == 0


def test_complete_but_still_live_retains_resident_and_blocks_Qplus(tmp_path):
    plan, _ = external_fixture(tmp_path, complete=True)
    result = host.observe_external(plan, now=100, identity_fn=live_identity)
    assert result["status"] == "awaiting_original_worker_exit" and result["resident_count"] == 1
    assert result["excluded_gpu"] == 2
    assert supervisor.eligible_workers(supervisor.initial_states(plan), result) == ["update-Q_minus"]
    with pytest.raises(ValueError, match="still owns"):
        host.observe_external(plan, prior=result, now=131, identity_fn=live_identity)


def test_exit_before_old_supervisor_closes_waits_without_guessing_terminal(tmp_path):
    plan, _ = external_fixture(tmp_path)
    first = host.observe_external(plan, now=100, identity_fn=dead_identity)
    assert first["status"] == "awaiting_original_host_closure" and first["resident_count"] == 1
    assert supervisor.eligible_workers(supervisor.initial_states(plan), first) == ["update-Q_minus"]
    with pytest.raises(ValueError, match="without a bound"):
        host.observe_external(plan, prior=first, now=131, identity_fn=dead_identity)


@pytest.mark.parametrize("complete", [False, True])
def test_reused_PID_is_a_new_integrity_pause_even_if_old_state_complete(tmp_path, complete):
    plan, _ = external_fixture(tmp_path, complete=complete)
    with pytest.raises(ValueError, match="reused"):
        host.observe_external(plan, identity_fn=lambda pid: {"alive": True, "start_ticks": 999})


@pytest.mark.parametrize("mutation", ["source", "pid", "old_development_started", "stopped_external", "guardian_lost"])
def test_external_or_parent_identity_failure_never_releases_new_work(tmp_path, mutation):
    plan, root = external_fixture(tmp_path)
    path = root / "supervisor.json"
    data = json.loads(path.read_text())
    if mutation == "source":
        data["source"]["code_commit"] = "other"
    elif mutation == "pid":
        data["states"]["update-Q_plus"]["pid"] = 400
    elif mutation == "old_development_started":
        data["states"]["dev-Q_plus-0"]["attempted"] = True
    elif mutation == "stopped_external":
        data["states"]["update-Q_plus"]["status"] = "stopped"
    else:
        data["status"] = "interrupted"
    write(path, data)
    with pytest.raises(ValueError):
        host.observe_external(plan, identity_fn=live_identity)


@pytest.mark.parametrize("mutation", ["source_after", "checkpoint_actor", "weight", "advantage", "worker_exit"])
def test_external_terminal_requires_original_result_checkpoint_and_composition(tmp_path, mutation):
    plan, root = external_fixture(tmp_path, complete=True)
    folder = root / "update-Q_plus/actual"
    path = folder / "report.json"
    data = json.loads(path.read_text())
    if mutation == "source_after":
        data["source_after"] = {"code_commit": "changed"}
    elif mutation == "checkpoint_actor":
        data["final_actor_identity"] = {"branch": "B"}
    elif mutation == "weight":
        write(folder / "composition-before-update.json", host.seal({"weights_by_slot": {}}, "seal_sha256"))
    elif mutation == "advantage":
        update = json.loads((folder / "update/report.json").read_text())
        update["advantages"] = [2]
        write(folder / "update/report.json", update)
        data["update_report"] = reference(folder / "update/report.json")
    else:
        state = json.loads((root / "supervisor.json").read_text())
        state["states"]["update-Q_plus"]["exit_code"] = -9
        write(root / "supervisor.json", state)
    write(path, data)
    with pytest.raises(ValueError):
        host.observe_external(plan, identity_fn=dead_identity)


def test_external_terminal_snapshot_accepts_only_later_host_top_level_status(tmp_path):
    plan, _ = external_fixture(tmp_path, complete=True)
    terminal = host.observe_external(plan, identity_fn=dead_identity)["terminal"]
    supervisor.store_external_terminal(tmp_path / "new", terminal)
    changed_status = {**copy.deepcopy(terminal), "original_supervisor_status": "running"}
    supervisor.store_external_terminal(tmp_path / "new", changed_status)
    bad = copy.deepcopy(terminal)
    bad["checkpoint"]["sha256"] = "changed"
    with pytest.raises(ValueError):
        supervisor.store_external_terminal(tmp_path / "new", bad)


def test_original_Qplus_can_never_be_signalled_by_new_supervisor(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(supervisor, "inherited_stop", lambda *a: calls.append(a))
    with pytest.raises(ValueError, match="never owns"):
        supervisor.request_stop(tmp_path, "update-Q_plus", SimpleNamespace(pid=100), {"pid": 100, "worker": "update-Q_plus"}, "stop")
    assert calls == []
    supervisor.request_stop(tmp_path, "update-Q_minus", SimpleNamespace(pid=200), {"pid": 200, "worker": "update-Q_minus"}, "reserve")
    assert len(calls) == 1


def test_GPU4_preference_keeps_all_original_capacity_guards_and_worktree_imports():
    plan = {**inventory_plan(), "runtime_dependency_path": "/original-sdk-deps"}
    sample = {"gpus": {"returncode": 0, "stdout": "0, gpu0, NVIDIA A100, 60000, 81920, 0\n4, gpu4, NVIDIA A100, 60000, 81920, 100\n5, gpu5, NVIDIA A100, 57343, 81920, 0\n"},
        "processes": {"returncode": 0, "stdout": "gpu4, 333, python, 18000\n"}}
    cards = supervisor.available_cards(plan, sample)
    assert [c["index"] for c in cards] == [4, 0]
    assert [c["index"] for c in supervisor.available_cards(plan, sample, [4])] == [0]
    env = host.worker_env(plan, 4)
    assert env["CUDA_VISIBLE_DEVICES"] == "4"
    assert env["PYTHONPATH"].split(":")[:2] == [str(host.SOURCE / "src"), str(host.SOURCE)]
    assert host.GPU_ORDER == tuple(range(8)) and host.LIMITS["gpu_capacity_stability_seconds"] == 60
    for kind, seconds in (("loading", 900), ("training_step", 900), ("boundary", 600), ("episode", 6000)):
        assert supervisor.task_stop_reason({"kind": kind, "started_at": 0}, now=seconds, rss_bytes=0) is not None


def test_remaining_compute_interval_must_match_frozen_replay_budget(monkeypatch):
    plan = {"qminus_compute_replay": {"remaining_seconds": 100, "sha256": "frozen"}}
    receipt = {"started_at": 10, "maximum_seconds": 100, "replay_budget_sha256": "frozen"}
    monkeypatch.setattr(compute, "training_stop_reason", lambda r, now: None if now < 110 else "exhausted")
    assert supervisor.training_stop_reason(plan, "update-Q_minus", receipt, now=109) is None
    assert supervisor.training_stop_reason(plan, "update-Q_minus", receipt, now=110) == "exhausted"
    assert supervisor.training_stop_reason(plan, "dev-Q_plus-0", receipt, now=110) is None
    receipt["maximum_seconds"] = 172800
    assert supervisor.training_stop_reason(plan, "update-Q_minus", receipt, now=110) == "training_compute_budget_unbound"


def test_worker_has_no_path_to_original_B_or_Qplus_update():
    for name in ("collect-0", "update-B", "update-Q_plus", "dev-S_star-0", "dev-B-0", "s_star"):
        with pytest.raises(ValueError):
            host.run_worker("unused", name, "unused")


def test_development_loader_reads_only_bound_external_Qplus_checkpoint(tmp_path):
    plan, _ = external_fixture(tmp_path, complete=True)
    root = tmp_path / "new"
    write(root / "plan.json", plan)
    terminal = host.observe_external(plan, identity_fn=dead_identity)["terminal"]
    supervisor.store_external_terminal(root, terminal)
    checkpoint = json.loads(Path(terminal["checkpoint"]["path"]).read_text())
    calls = []
    owner = SimpleNamespace(actor_steps=5, critic_steps=5,
        restore_checkpoint=lambda path: calls.append(path) or checkpoint,
        freeze_identity=lambda: checkpoint["actor_identity"])
    assert host._restored_state(owner, root, "Q_plus", root / "fake") == checkpoint
    assert calls == [Path(plan["parent_run_root"]) / "update-Q_plus/actual/checkpoint"]
    assert not (root / "update-Q_plus").exists()


def test_finite_fake_supervisor_waits60s_prefers4_and_counts_external(tmp_path, monkeypatch):
    plan = {**inventory_plan(), "source": {"fixture": True}, "parent_plan": {}, "prior_artifact_roots": [],
        "native_python": "/fixture/python", "runtime_dependency_path": "/fixture/deps",
        "external_Q_plus": {"pid": 100, "gpu": 2}}
    monkeypatch.setattr(host, "frozen", lambda unused: plan)
    monkeypatch.setattr(host, "observe_external", lambda *a, **k: {"status": "running", "resident_count": 1, "excluded_gpu": 2})
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda p: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda p: SimpleNamespace(free=10**15))
    clock = {"now": 0.0}
    monkeypatch.setattr(supervisor.time, "time", lambda: clock["now"])
    monkeypatch.setattr(supervisor.time, "sleep", lambda unused: clock.update(now=clock["now"] + 30))
    monkeypatch.setattr(supervisor, "allowed_resources", lambda: {"fixture": True})
    observed = []
    monkeypatch.setattr(supervisor, "available_cards", lambda plan, sample, excluded:
        observed.append(list(excluded)) or [{"index": 4, "uuid": "gpu4"}])
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"start_ticks": 500, "alive": True})
    monkeypatch.setattr(supervisor, "target_resources", lambda *a, **kw: {"fixture": True})
    launches = []
    class Process:
        pid = 200
        returncode = 1
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            return self.returncode
    def popen(argv, **kwargs):
        launches.append((list(argv), kwargs["cwd"], kwargs["env"]["PYTHONPATH"], clock["now"]))
        return Process()
    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    # An immediate fake failure stops unopened work; no GPU or external signal occurs.
    result = supervisor.supervise(tmp_path)
    assert result["status"] == "closed_with_unknowns"
    assert len(launches) == 1 and launches[0][0][2] == host.MODULE
    assert launches[0][1] == host.SOURCE and launches[0][3] >= 60
    assert all(2 in excluded for excluded in observed)
    state = result["states"]["update-Q_minus"]
    assert state["gpu"] == 4 and state["external_residents_at_launch"] == 1
    assert all(result["states"][n]["attempted"] is False for n in host.DEVELOPMENT)
