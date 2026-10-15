"""Finite CPU controls for the external-Q-plus/owned-Q-minus continuation."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r3 as host
from scripts import software_learning_resume_supervisor_v050r3 as supervisor
from scripts import software_learning_resume_compute_v050r3 as compute
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
    plan = {**inventory_plan(), "parent_run_root": str(root.parent / "r2"), "original_run_root": str(root), "external_Q_plus": expected,
        "continuation_inventory": {"original_inventory": {"parent_source": source,
            "original_supervisor_process": {"pid": 101, "start_ticks": 654},
            "closed_parent_workers": {"dev-Q_plus-0": {"state": frozen_state}},
            "B_update": reference(root / "baseline.json"),
            "materials": {"direction.json": reference(root / "direction.json")}}}}
    return plan, root


def live_identity(pid):
    return {"alive": True, "start_ticks": 321 if pid == 100 else 654}


def dead_identity(pid):
    return {"alive": False}


def test_only_original16_Q_development_units_and_one_recomputation():
    plan = inventory_plan()
    assert len(host.WORKERS) == 17 and host.WORKERS[0] == "update-Q_minus"
    assert all(len(host.worker_units(plan, worker)) == 1 for worker in host.DEVELOPMENT)
    original_units = [u for name in host.prior.DEVELOPMENT for u in host.original.worker_units(plan, name)]
    actual_units = [u for name in host.DEVELOPMENT for u in host.worker_units(plan, name)]
    assert actual_units == original_units
    assert host.original_worker("dev-Q_minus-7") == "dev-Q_minus-1"
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
    assert supervisor.resident_capacity({}, observed) == 7
    assert supervisor.resident_capacity({"one": {"gpu": 0}, "two": {"gpu": 1}}, observed) == 5
    states["update-Q_minus"].update(status="complete", attempted=True)
    assert supervisor.eligible_workers(states, observed) == [n for n in host.DEVELOPMENT if n.startswith("dev-Q_minus-")]


def test_complete_external_releases_GPU_and_Qplus_shards_only_after_full_guard(tmp_path):
    plan, _ = external_fixture(tmp_path, complete=True)
    observed = host.observe_external(plan, now=100, identity_fn=dead_identity)
    assert observed["status"] == "complete" and observed["resident_count"] == 0 and observed["excluded_gpu"] is None
    assert supervisor.resident_capacity({}, observed) == 8
    assert supervisor.eligible_workers(supervisor.initial_states(plan), observed) == ["update-Q_minus", *[n for n in host.DEVELOPMENT if n.startswith("dev-Q_plus-")]]
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


def test_immediate_free_descending_GPU_policy_and_retained_integrity_timeouts():
    plan = {**inventory_plan(), "runtime_dependency_path": "/original-sdk-deps"}
    sample = {"gpus": {"returncode": 0, "stdout": "0, gpu0, NVIDIA A100, 60000, 81920, 0\n4, gpu4, NVIDIA A100, 50000, 81920, 100\n5, gpu5, NVIDIA A100, 46079, 81920, 0\n"},
        "processes": {"returncode": 0, "stdout": "gpu4, 333, 18000, python\n"}}
    cards = supervisor.available_cards(plan, sample)
    assert [c["index"] for c in cards] == [0, 4]
    assert [c["index"] for c in supervisor.available_cards(plan, sample, [0])] == [4]
    binding = host.resource.launch_target(cards[1])
    env = host.worker_env(plan, 4, binding)
    assert env["CUDA_VISIBLE_DEVICES"] == "4"
    assert env["PYTHONPATH"].split(":")[:2] == [str(host.SOURCE / "src"), str(host.SOURCE)]
    assert host.LIMITS["gpu_capacity_stability_seconds"] == 0
    assert host.LIMITS["max_parallel_model_instances"] is None
    assert host.LIMITS["own_gpu_memory_mib"] is None
    for kind, seconds in (("loading", 900), ("training_step", 900), ("boundary", 600), ("episode", 6000)):
        assert supervisor.task_stop_reason({"kind": kind, "started_at": 0}, now=seconds, rss_bytes=0) is not None
    assert supervisor.task_stop_reason({"kind": "reservation_wait", "started_at": 0}, now=10**9, rss_bytes=0) is None
    assert supervisor.task_stop_reason({"kind": "reservation_wait", "started_at": 0}, now=10**9,
        rss_bytes=host.LIMITS["host_rss_per_worker_bytes"] + 1) == "host_memory_budget"


def test_remaining_compute_interval_must_match_frozen_replay_budget(monkeypatch):
    plan = {"qminus_compute_replay": {"remaining_seconds": 100, "sha256": "frozen"}}
    receipt = {"started_at": 10, "maximum_seconds": 100, "replay_budget_sha256": "frozen"}
    monkeypatch.setattr(compute, "training_stop_reason", lambda r, now: None if now < 110 else "exhausted")
    assert supervisor.training_stop_reason(plan, "update-Q_minus", receipt, now=79) is None
    assert supervisor.training_stop_reason(plan, "update-Q_minus", receipt, now=80) == "training_compute_reclamation_reserve"
    assert supervisor.training_stop_reason(plan, "update-Q_minus", {**receipt, "ended_at": 109}, now=200) is None
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
    assert calls == [Path(plan["original_run_root"]) / "update-Q_plus/actual/checkpoint"]
    assert not (root / "update-Q_plus").exists()


@pytest.mark.parametrize("external_complete, expected_launches", [(True, 8), (False, 7)])
def test_single_slot_dispatch_has_no_artificial_concurrency_cap_or_stability_delay(tmp_path, monkeypatch, external_complete, expected_launches):
    plan = {**inventory_plan(), "source": {"fixture": True}, "parent_plan": {}, "original_r1_plan": {},
        "resource_policy": host.resource.RESOURCE_POLICY, "single_slot_scheduling": {}, "prior_artifact_roots": [],
        "native_python": "/fixture/python", "runtime_dependency_path": "/fixture/deps",
        "external_Q_plus": {"pid": 100, "gpu": 2}}
    monkeypatch.setattr(host, "frozen", lambda unused: plan)
    external = {"status": "complete" if external_complete else "running", "resident_count": 0 if external_complete else 1,
        "excluded_gpu": None if external_complete else 2, "terminal": {}}
    monkeypatch.setattr(host, "observe_external", lambda *a, **k: external)
    monkeypatch.setattr(supervisor, "store_external_terminal", lambda *a: {})
    actual_initial = supervisor.initial_states(plan)
    actual_initial["update-Q_minus"].update(status="complete", attempted=True)
    monkeypatch.setattr(supervisor, "initial_states", lambda unused: copy.deepcopy(actual_initial))
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda p: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda p: SimpleNamespace(free=10**15))
    clock = {"now": 0.0}
    monkeypatch.setattr(supervisor.time, "time", lambda: clock["now"])
    monkeypatch.setattr(supervisor.time, "sleep", lambda unused: clock.update(now=clock["now"] + 30))
    sample = {"gpus": {"returncode": 0, "stdout": "".join(
        f"{i}, gpu{i}, NVIDIA A100, {60000+i}, 81920, 0\n" for i in range(8))},
        "processes": {"returncode": 0, "stdout": ""}}
    monkeypatch.setattr(supervisor, "allowed_resources", lambda: sample)
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"start_ticks": 500, "alive": True})
    monkeypatch.setattr(supervisor, "target_resources", lambda *a, **kw: {"fixture": True})
    launches = []
    class Process:
        returncode = 1
        def __init__(self, pid):
            self.pid = pid
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            return self.returncode
    def popen(argv, **kwargs):
        launches.append((list(argv), kwargs["cwd"], kwargs["env"]["CUDA_VISIBLE_DEVICES"], clock["now"]))
        return Process(200 + len(launches))
    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    result = supervisor.supervise(tmp_path)
    assert result["status"] == "closed_with_unknowns"
    assert len(launches) == expected_launches
    assert all(row[0][2] == host.MODULE and row[1] == host.SOURCE and row[3] == 0 for row in launches)
    expected_gpus = list(reversed(range(8)))
    if not external_complete:
        expected_gpus.remove(2)
    assert [int(row[2]) for row in launches] == expected_gpus
    states = [state for name, state in result["states"].items() if name in host.DEVELOPMENT and state["attempted"]]
    assert len({state["planned_slots"][0] for state in states}) == expected_launches
    assert all(len(state["planned_slots"]) == 1 and state["single_slot_cost"]["complete_worker"] is False for state in states)
    assert not (tmp_path / "update-Q_plus").exists()
    assert result["maximum_residents"] is None


def test_original_scientific_caps_are_unchanged_but_host_resource_keys_differ():
    allowed = set(host.resource.LIMITS_OVERRIDES)
    assert {k: v for k, v in host.LIMITS.items() if k not in allowed} == {
        k: v for k, v in host.original.LIMITS.items() if k not in allowed}
    caps = host.generation_caps()
    assert (caps["new_generation_slots_max"], caps["new_actual_generation_tokens_max"],
        caps["new_decisions_max"], caps["new_attempts_max"], caps["new_member_tests_max"]) == (16, 8000000, 2048, 2048, 512)


def test_preload_calls_the_unchanged_original_loader_with_private_resource_bindings(monkeypatch, tmp_path):
    calls = []
    binding = {"fixture": True}
    monkeypatch.setattr(host.resource, "binding_from_env", lambda: binding)
    monkeypatch.setattr(host.resource, "reserve_before_load", lambda output, current: calls.append(("reserve", output, current)))
    def fake_bind(function, **dependencies):
        assert function is host.original.original._load_owner
        assert callable(dependencies["inherited"].available_cards)
        return lambda plan, output: calls.append(("load", plan, output)) or "owner"
    monkeypatch.setattr(host, "bind", fake_bind)
    assert host._load_owner({"fixture": True}, tmp_path) == "owner"
    assert [row[0] for row in calls] == ["reserve", "load"]


def test_prepare_preserves_capacity_original_plan_and_separately_binds_r1(tmp_path, monkeypatch):
    old = tmp_path / "r2"
    old.mkdir()
    parent = {**inventory_plan(), "original_plan": {"path": "capacity-plan", "sha256": "capacity"},
        "prior_artifact_roots": [], "source": {"fixture": "old"}}
    write(old / "plan.json", host.seal(parent, "plan_sha256"))
    protocol = tmp_path / "protocol.md"
    protocol.write_text("fixture protocol")
    controls = tmp_path / "controls.json"
    write(controls, host.seal({"passed": True, "parent_plan": reference(old / "plan.json"),
        "new_model_calls": 0, "new_gpu_workers": 0, "new_backward_calls": 0}))
    derived = {"parent_plan": reference(old / "plan.json"), "parent_source_root": "/r2-source",
        "original_run_root": "/r1", "original_plan": {"path": "r1-plan", "sha256": "r1"},
        "qminus_compute_replay": {"fixture": "budget"}, "external_Q_plus": {"fixture": "external"},
        "single_slot_scheduling": host.scheduling_inventory(parent), "materials": {}}
    monkeypatch.setattr(host, "code_identity", lambda: {"code_commit": "fixture", "code_dirty": False})
    monkeypatch.setattr(host, "source_files", lambda: {})
    monkeypatch.setattr(host, "PROTOCOL", protocol)
    monkeypatch.setattr(host, "derive_inventory", lambda root: derived)
    result = host.prepare(tmp_path / "r3", parent_root=old, controls=controls)
    assert result["original_plan"] == parent["original_plan"]
    assert result["original_r1_plan"] == derived["original_plan"]
    assert result["parent_run_root"] == str(old)
    assert result["original_run_root"] == "/r1"

    summary = supervisor.initial_summary(result, now=1, observer_pid=123)
    assert summary["original_r1_plan"] == derived["original_plan"]
    assert summary["parent_plan"] == reference(old / "plan.json")
    assert len(summary["states"]) == 17


@pytest.mark.parametrize("identity, accepted", [
    ({"alive": False}, True),
    ({"alive": True, "start_ticks": 2}, True),
    ({"alive": True, "start_ticks": 1}, False),
    ({"alive": None, "start_ticks": None}, False),
])
def test_interrupted_process_must_be_definitively_dead_or_reused(identity, accepted):
    state = {"pid": 100, "process_identity": {"start_ticks": 1}}
    if accepted:
        assert host._dead(state, "fixture", identity_fn=lambda pid: identity)["original_process_dead"] is True
    else:
        with pytest.raises(ValueError, match="alive or unbound"):
            host._dead(state, "fixture", identity_fn=lambda pid: identity)


@pytest.mark.parametrize("mutation", [None, "environment", "state_uuid", "launch_target", "command", "unit"])
def test_reservation_binds_environment_state_actual_launch_before_model(tmp_path, monkeypatch, mutation):
    worker = "dev-Q_minus-7"
    plan = {**inventory_plan(), "native_python": "/fixture/python"}
    binding = host.resource.launch_target({"index": 4, "uuid": "gpu4", "free_mib": 50000})
    command = [plan["native_python"], "-m", host.MODULE, "worker", "--run-root", str(tmp_path),
        "--worker", worker, "--output", str(tmp_path / worker / "actual")]
    state = {"worker": worker, "attempted": True, "status": "not_started", "reservation": copy.deepcopy(binding),
        "gpu": 4, "gpu_uuid": "gpu4", "command": list(command)}
    launch = {"reservation": copy.deepcopy(binding), "gpu": 4, "actual_command": list(command),
        "cwd": str(host.SOURCE), "original_worker": host.original_worker(worker),
        "planned_units": host.worker_units(plan, worker)}
    if mutation == "environment":
        binding = host.resource.launch_target({"index": 4, "uuid": "gpu4", "free_mib": 51000})
    elif mutation == "state_uuid":
        state["gpu_uuid"] = "changed"
    elif mutation == "launch_target":
        launch["reservation"]["target_mib"] += 1024
    elif mutation == "command":
        launch["actual_command"][2] = host.prior.MODULE
    elif mutation == "unit":
        launch["planned_units"][0]["sampling_seed"] += 1
    write(tmp_path / "plan.json", plan)
    write(tmp_path / "supervisor.json", {"states": {worker: state}})
    write(tmp_path / worker / "worker-launch.json", launch)
    monkeypatch.setattr(host.resource, "binding_from_env", lambda: binding)
    if mutation is None:
        assert host.runtime_reservation(tmp_path, worker) == binding
        assert json.loads((tmp_path / worker / "reservation-binding-verified.json").read_text())["verified_before_cuda_or_model_load"] is True
    else:
        with pytest.raises(ValueError, match="reservation must agree"):
            host.runtime_reservation(tmp_path, worker)
        assert not (tmp_path / worker / "reservation-binding-verified.json").exists()
    assert not (tmp_path / worker / "actual").exists()
