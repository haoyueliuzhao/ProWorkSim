"""Finite CPU controls for zero-model archival, requeue, and external ownership."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r5 as host
from scripts import software_learning_resume_supervisor_v050r5 as supervisor
from scripts.run_ne_v021 import reference, write


def plan_fixture():
    return {"inventory": json.loads(host.original.DESIGN.read_text()),
        "gpu_preference": list(host.GPU_PREFERENCE), "limits": host.LIMITS,
        "source": {"code_commit": "frozen", "code_dirty": False, "source_tree_sha256": "tree"},
        "source_root": str(host.SOURCE), "native_python": "/python",
        "parent_plan": {"path": "/old/plan.json", "sha256": "old"},
        "external_Q_plus": {"gpu": 2}, "resource_policy": host.resource.RESOURCE_POLICY,
        "startup_retry_policy": host.RETRY_POLICY, "single_slot_scheduling": {},
        "prior_artifact_roots": []}


def resource_evidence(root, plan, state, *, pid=123, ticks=456):
    """Produce the exact small JSON contract, without importing torch or querying a GPU."""
    name = state["worker"]
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    binding = state["reservation"]
    launch = {"actual_command": state["command"], "cwd": str(host.SOURCE),
        "source": plan["source"], "reservation": binding,
        "resource_attempt_number": state["resource_attempt_number"],
        "original_worker": host.original_worker(name), "planned_units": host.worker_units(plan, name)}
    if not (folder / "worker-launch.json").exists():
        write(folder / "worker-launch.json", launch)
    process = {"pid": pid, "available": True, "alive": True, "start_ticks": ticks}
    identity = {"worker": name, "run_root": str(root), "source": plan["source"],
        "source_root": str(host.SOURCE), "plan": reference(root / "plan.json"),
        "worker_launch": reference(folder / "worker-launch.json"),
        "process_identity": process, "resource_attempt_number": state["resource_attempt_number"]}
    receipt = {"version": host.startup_resource.VERSION, "status": "resource_unavailable",
        "retryable": True, "reason": "pre_model_cuda_out_of_memory", "phase": "cuda_capacity_snapshot",
        "loader_not_entered": True, "new_model_calls": 0, "new_backward_calls": 0,
        "new_optimizer_steps": 0, "live_reservation_tensors": 0, "same_process_resource_retries": 0,
        "cuda_requeried_after_error": False, "restart_requires_fresh_process": True,
        "output": str(folder / "startup"), "pid": pid, "binding": binding, "identity": identity,
        "error": {"type": "RuntimeError", "message": "CUDA error: out of memory"}}
    write(folder / "startup/startup-resource-receipt.json", receipt)
    write(folder / "startup/task.json", {"pid": pid, "kind": "reservation_wait", "loader_not_entered": True,
        "new_model_calls": 0, "new_backward_calls": 0})
    write(folder / "reservation-binding-verified.json", {"identity": identity, "reservation": binding,
        "verified_before_cuda_or_model_load": True})
    (folder / "startup/native-cache-resources.jsonl").write_text(json.dumps(receipt) + "\n")
    if not (folder / "worker.log").exists():
        (folder / "worker.log").write_text("raw resource error preserved\n")
    write(folder / "resource-wait.json", {"version": host.VERSION, "status": "resource_wait", "worker": name,
        "identity": identity, "reservation": binding, "source_before": plan["source"], "source_after": plan["source"],
        "retryable": True, "model_started": False, "new_model_calls": 0, "new_backward_calls": 0,
        "new_actor_steps": 0, "new_critic_steps": 0, "new_training_interval_seconds": 0,
        "loader_not_entered": True, "resource_receipt": reference(folder / "startup/startup-resource-receipt.json"),
        "raw_fault": receipt})
    state.update(status="running", attempted=True, pid=pid, process_identity=process)
    return receipt, identity


def failed_attempt(tmp_path, *, plan=None, state=None, gpu=0, started=10.0):
    plan = plan or plan_fixture()
    if not (tmp_path / "plan.json").exists():
        write(tmp_path / "plan.json", plan)
    state = state if state is not None else supervisor.initial_states(plan)["update-Q_minus"]
    name = state["worker"]
    state.update(resource_attempt_number=state["resource_attempt_number"] + 1,
        reservation={"gpu_index": gpu, "gpu_uuid": f"GPU-{gpu}", "target_mib": 73728},
        gpu=gpu, gpu_uuid=f"GPU-{gpu}", command=["/python", name], started_at=started,
        resource_attempted=True)
    resource_evidence(tmp_path, plan, state)
    return plan, state


def verified(tmp_path, plan, state):
    return supervisor.verify_resource_failure(tmp_path, state["worker"], state, plan,
        exit_code=0, reason=None, identity_fn=lambda pid: {"pid": pid, "available": True, "alive": False})


def test_inventory_reuses_original_sixteen_units_and_one_unconsumed_Qminus():
    plan = plan_fixture()
    assert host.UPDATES == ("update-Q_minus",) and len(host.WORKERS) == 17
    actual = [u for n in host.DEVELOPMENT for u in host.worker_units(plan, n)]
    old = [u for n in host.prior.DEVELOPMENT for u in host.prior.worker_units(plan, n)]
    assert actual == old and len({u["slot_id"] for u in actual}) == 16
    assert host.generation_caps() == host.prior.generation_caps()
    assert host.LIMITS == host.prior.LIMITS
    with pytest.raises(ValueError):
        host.worker_units(plan, "update-Q_plus")


def test_backoff_is_per_worker_and_does_not_block_ready_other_branch():
    states = supervisor.initial_states(plan_fixture())
    external = {"status": "complete"}
    states["update-Q_minus"].update(next_resource_attempt_at=105, resource_attempt_number=1)
    ready = supervisor.eligible_workers(states, external, now=100)
    assert ready == [n for n in host.DEVELOPMENT if n.startswith("dev-Q_plus-")]
    assert supervisor.eligible_workers(states, external, now=105)[0] == "update-Q_minus"
    states["update-Q_minus"].update(status="complete", model_started=True)
    assert supervisor.eligible_workers(states, external, now=106) == list(host.DEVELOPMENT)
    assert [supervisor.retry_delay(i) for i in range(1, 8)] == [5, 10, 20, 40, 60, 60, 60]


@pytest.mark.parametrize("corruption", ["actual", "marker", "model_trace", "nonzero", "source", "pid", "compute", "unknown_fault"])
def test_only_bound_zero_model_resource_failures_are_retryable(tmp_path, corruption):
    plan, state = failed_attempt(tmp_path)
    folder = tmp_path / state["worker"]
    if corruption == "actual":
        (folder / "actual").mkdir()
    elif corruption == "marker":
        write(folder / "startup/model-load-intent.json", {})
    elif corruption == "model_trace":
        write(folder / "loaded-state.json", {})
    elif corruption == "compute":
        (folder / "resources.jsonl").write_text(json.dumps({"training_compute": {"native_forward_started": 1}}) + "\n")
    else:
        path = folder / "resource-wait.json"
        report = json.loads(path.read_text())
        if corruption == "nonzero":
            report["new_model_calls"] = 1
        elif corruption == "source":
            report["source_after"] = {"code_commit": "other"}
        elif corruption == "pid":
            report["identity"]["process_identity"]["start_ticks"] += 1
        else:
            report["raw_fault"]["reason"] = "unclassified_cuda_fault"
        write(path, report)
    with pytest.raises(ValueError):
        verified(tmp_path, plan, state)
    assert folder.exists() and not (tmp_path / "resource-attempts").exists()


@pytest.mark.parametrize("identity", [{"alive": True, "start_ticks": 456}, {"available": False}, {"alive": True}])
def test_live_or_unknown_process_cannot_requeue(tmp_path, identity):
    plan, state = failed_attempt(tmp_path)
    with pytest.raises(ValueError, match="exited"):
        supervisor.verify_resource_failure(tmp_path, state["worker"], state, plan, exit_code=0,
            reason=None, identity_fn=lambda pid: identity)


def test_two_resource_attempts_archive_all_bytes_once_and_allow_another_card(tmp_path):
    plan, state = failed_attempt(tmp_path, gpu=0, started=10)
    proof = verified(tmp_path, plan, state)
    first = supervisor.archive_resource_attempt(tmp_path, state["worker"], state, proof, ended_at=22)
    assert not (tmp_path / state["worker"]).exists()
    assert state["status"] == "not_started" and state["attempted"] is False
    assert state["next_resource_attempt_at"] == 27
    assert state["resource_attempt_gpu_seconds"] == 12 and state["elapsed_gpu_seconds"] == 0
    for row in first["archive_mapping"]:
        assert reference(Path(row["archived"]["path"])) == row["archived"]
        assert row["original"]["sha256"] == row["archived"]["sha256"]
    failed_attempt(tmp_path, plan=plan, state=state, gpu=3, started=30)
    second = supervisor.archive_resource_attempt(tmp_path, state["worker"], state,
        verified(tmp_path, plan, state), ended_at=34)
    assert second["original_launch_state"]["gpu"] == 3
    assert first["original_launch_state"]["gpu"] == 0
    assert state["resource_attempt_gpu_seconds"] == 16 and state["next_resource_attempt_at"] == 44
    assert len(state["resource_attempt_history"]) == 2
    assert (tmp_path / "resource-attempts/update-Q_minus/attempt-0001/worker.log").read_text() == "raw resource error preserved\n"
    assert not (tmp_path / "mechanism-stops").exists()


def test_archive_never_overwrites_old_attempt(tmp_path):
    plan, state = failed_attempt(tmp_path)
    destination = tmp_path / "resource-attempts/update-Q_minus/attempt-0001"
    destination.mkdir(parents=True)
    (destination / "retained.txt").write_text("old")
    with pytest.raises(FileExistsError):
        supervisor.archive_resource_attempt(tmp_path, state["worker"], state, verified(tmp_path, plan, state), ended_at=12)
    assert (destination / "retained.txt").read_text() == "old"
    assert (tmp_path / state["worker"] / "resource-wait.json").exists()


def test_startup_error_finishes_before_original_worker_or_mechanism_stop(tmp_path, monkeypatch):
    plan, state = failed_attempt(tmp_path)
    receipt, identity = resource_evidence(tmp_path, plan, state)
    monkeypatch.setattr(host, "runtime_reservation", lambda *a: (state["reservation"], identity))
    monkeypatch.setattr(host, "code_identity", lambda: plan["source"])
    def unavailable(*a, **kw):
        raise host.startup_resource.StartupResourceUnavailable(receipt)
    monkeypatch.setattr(host.startup_resource, "acquire_startup_cache", unavailable)
    monkeypatch.setattr(host.original, "run_worker", lambda *a: pytest.fail("original worker must not run"))
    result = host.run_worker(tmp_path, state["worker"], tmp_path / state["worker"] / "actual")
    assert result["status"] == "resource_wait" and result["new_training_interval_seconds"] == 0
    assert not (tmp_path / state["worker"] / "actual").exists()
    assert not (tmp_path / "mechanism-stops").exists()


def test_preacquisition_precedes_full_validation_and_marker_precedes_loader(tmp_path, monkeypatch):
    plan = plan_fixture()
    name = "update-Q_minus"
    trace = []
    monkeypatch.setattr(host, "runtime_reservation", lambda *a: trace.append("small-binding") or ({}, {}))
    monkeypatch.setattr(host.startup_resource, "acquire_startup_cache", lambda *a, **kw: trace.append("acquire") or {})
    monkeypatch.setattr(host, "frozen", lambda *a: trace.append("full-frozen") or plan)
    def fake_loader(plan, out):
        assert (out.parent / "startup/model-load-intent.json").exists()
        trace.append("loader")
        raise RuntimeError("CUDA error: out of memory")
    monkeypatch.setattr(host.prior, "_load_owner", fake_loader)
    def fake_original(root, worker, output):
        plan = frozen(root)  # noqa: F821 -- supplied by the original private binding
        return _load_owner(plan, output)  # noqa: F821
    monkeypatch.setattr(host.original, "run_worker", fake_original)
    with pytest.raises(RuntimeError, match="out of memory"):
        host.run_worker(tmp_path, name, tmp_path / name / "actual")
    assert trace == ["small-binding", "acquire", "full-frozen", "loader"]
    assert not (tmp_path / name / "resource-wait.json").exists()


def test_prepare_retains_original_capacity_plan_and_exact_compute_allocation(tmp_path, monkeypatch):
    old = tmp_path / "old"
    old.mkdir()
    parent = plan_fixture()
    parent.update(original_plan={"path": "/capacity/plan.json", "sha256": "capacity"},
        original_r1_plan={"path": "/r1/plan.json", "sha256": "r1"}, original_run_root="/r1",
        q_compute_replay={"allocation": "unchanged-r4"})
    write(old / "plan.json", parent)
    write(old / "supervisor.json", {"status": "running"})
    proof_path = tmp_path / "controls.json"
    write(proof_path, host.seal({"passed": True, "new_model_calls": 0, "new_gpu_workers": 0,
        "new_backward_calls": 0, "parent_plan": reference(old / "plan.json")}))
    derived = {"parent_plan": reference(old / "plan.json"), "parent_source_root": "/r4-source",
        "external_Q_plus": {"gpu": 2}, "q_compute_replay": parent["q_compute_replay"], "materials": {}}
    monkeypatch.setattr(host, "code_identity", lambda: parent["source"])
    monkeypatch.setattr(host, "source_files", lambda: {})
    monkeypatch.setattr(host, "derive_inventory", lambda root: derived)
    monkeypatch.setattr(host, "PROTOCOL", proof_path)
    plan = host.prepare(tmp_path / "new", parent_root=old, controls=proof_path)
    assert plan["original_plan"] == parent["original_plan"]
    assert plan["parent_plan"] == reference(old / "plan.json")
    assert plan["q_compute_replay"] == parent["q_compute_replay"]
    assert plan["workers"] == list(host.WORKERS) and plan["automatic_retries"] is False
    assert plan["automatic_verified_resource_retries"] is True


def test_external_completion_preserves_original_owner_and_branch_allocation(monkeypatch):
    expected = {"remaining_seconds": 135481, "sha256": "r4-branch"}
    plan = {"q_compute_replay": {"branches": {"Q_plus": expected}}}
    terminal = {"training_compute": {"path": "compute", "sha256": "sha"}, "checkpoint": "full-bound-state"}
    compute = {"maximum_seconds": 135481, "replay_budget_sha256": "r4-branch",
        "native_forward_started": 1286, "native_forward_completed": 1286, "elapsed_seconds": 80000}
    monkeypatch.setattr(host.external_host, "_completed_external", lambda *a: terminal)
    monkeypatch.setattr(host, "checked", lambda ref: ref)
    monkeypatch.setattr(host, "read_json", lambda ref: compute)
    assert host._completed_external(plan, {}, {}) == terminal
    compute["native_forward_completed"] -= 1
    with pytest.raises(ValueError, match="allocation"):
        host._completed_external(plan, {}, {})
    with pytest.raises(ValueError, match="external"):
        supervisor.request_stop("/run", "update-Q_plus", SimpleNamespace(pid=4), {"pid": 4, "worker": "update-Q_plus"}, "test")


def test_supervisor_retries_on_another_card_while_other_ready_work_completes(tmp_path, monkeypatch):
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
    monkeypatch.setattr(host, "observe_external", lambda *a, **kw: {"status": "complete", "resident_count": 0,
        "excluded_gpu": None, "terminal": {"checkpoint": "original-r4", "original_worker_identity": {"pid": 9}}})
    monkeypatch.setattr(supervisor, "artifact_bytes", lambda root: 0)
    monkeypatch.setattr(supervisor.shutil, "disk_usage", lambda root: SimpleNamespace(free=10**15))
    monkeypatch.setattr(supervisor, "worker_env", lambda *a: {"PYTHONPATH": "cpu-test"})
    monkeypatch.setattr(supervisor, "allowed_resources", lambda: {})
    sample_count = {"n": 0}
    def cards(plan, sample, excluded):
        sample_count["n"] += 1
        indices = [0, 1] if sample_count["n"] == 1 else [3, 4]
        return [{"index": n, "uuid": f"GPU-{n}", "free_mib": 78000} for n in indices if n not in excluded]
    monkeypatch.setattr(supervisor, "available_cards", cards)
    monkeypatch.setattr(supervisor, "TelemetryGuard", lambda *a, **kw: None)
    monkeypatch.setattr(supervisor, "target_resources", lambda *a, **kw: {})
    monkeypatch.setattr(supervisor, "request_stop", lambda *a: pytest.fail("no scientific failure is simulated"))
    processes, launches = {}, []
    class Process:
        def __init__(self, command, **kw):
            name = command[command.index("--worker") + 1]
            self.pid = 1000 + len(launches)
            self.returncode, self.waited = 0, False
            processes[self.pid] = self
            folder = tmp_path / name
            state = json.loads((tmp_path / "supervisor.json").read_text())["states"][name]
            launches.append((name, state["gpu"], state["resource_attempt_number"]))
            if name == "update-Q_minus" and state["resource_attempt_number"] == 1:
                resource_evidence(tmp_path, plan, state, pid=self.pid, ticks=self.pid + 10)
            else:
                write(folder / "startup/model-load-intent.json", {"model_work_may_have_started": True})
                write(folder / "actual/report.json", {"status": "complete", "source_before": plan["source"],
                    "source_after": plan["source"], "success_boundary": True, "rows": [{"R": 1, "usage": {"tokens": 1}}]})
        def poll(self):
            return self.returncode
        def wait(self, timeout):
            self.waited = True
            return self.returncode
    monkeypatch.setattr(supervisor.subprocess, "Popen", Process)
    monkeypatch.setattr(supervisor, "worker_identity", lambda pid: {"pid": pid, "available": True,
        "alive": not processes[pid].waited, "start_ticks": pid + 10})
    summary = supervisor.supervise(tmp_path)
    assert summary["status"] == "complete" and summary["dispatch_status"] == "closed"
    assert summary["ready_worker_count"] == 0 and summary["monitoring_active_workers"] == 0
    assert [gpu for name, gpu, number in launches if name == "update-Q_minus"] == [0, 3]
    assert launches[1][0] == "dev-Q_plus-0" and launches[1][1] == 1
    assert len(launches) == 18 and not any(n == "update-Q_plus" for n, _, _ in launches)
    assert not (tmp_path / "mechanism-stops").exists()
    state = summary["states"]["update-Q_minus"]
    archive = host.check_seal(json.loads(host.checked(state["resource_attempt_history"][0]).read_text()))
    assert summary["resource_attempt_gpu_seconds"] == archive["elapsed_gpu_seconds"]
    assert summary["new_worker_gpu_seconds_observed"] == pytest.approx(
        summary["closed_worker_gpu_seconds"] + archive["elapsed_gpu_seconds"])
    assert state["model_started"] is True and state["resource_attempt_number"] == 2


def external_terminal_fixture(tmp_path):
    root = tmp_path / "r4"
    source = {"code_commit": "old-frozen", "code_dirty": False}
    state = {"worker": "update-Q_plus", "status": "complete", "attempted": True,
        "pid": 100, "process_identity": {"start_ticks": 321}, "gpu": 2, "gpu_uuid": "gpu2",
        "started_at": 10, "ended_at": 30, "exit_code": 0, "elapsed_gpu_seconds": 20}
    frozen_state = {"status": "stopped", "attempted": False}
    write(root / "supervisor.json", {"status": "closed_with_unknowns", "observer_pid": 101,
        "source": source, "states": {"update-Q_plus": state, "update-Q_minus": frozen_state}})
    baseline = {"advantages": [1], "old_critic_values": [0], "rewards": [1]}
    write(root / "baseline.json", baseline)
    direction = {"plus_weights": {"slot": {"member": 1.1}}}
    write(root / "direction.json", direction)
    out = root / "update-Q_plus/actual"
    checkpoint = {"actor_steps": 5, "critic_steps": 5, "actor_identity": {"state": "Q_plus"},
        "serialized_reload_exact": True}
    write(out / "checkpoint/checkpoint.json", checkpoint)
    write(out / "update/report.json", {**baseline, "stage": "complete", "status": "updated"})
    write(out / "training-compute.json", {"ended_at": 30, "elapsed_seconds": 19,
        "maximum_seconds": 135481, "replay_budget_sha256": "branch", "native_forward_started": 1286,
        "native_forward_completed": 1286})
    write(out / "composition-before-update.json", host.seal({"weights_by_slot": direction["plus_weights"]}, "seal_sha256"))
    write(out / "report.json", {"status": "complete", "success_boundary": True,
        "source_before": source, "source_after": source, "checkpoint": checkpoint,
        "actor_steps": 5, "critic_steps": 5, "final_actor_identity": checkpoint["actor_identity"],
        "update_report": reference(out / "update/report.json")})
    plan = {**plan_fixture(), "parent_run_root": str(root),
        "external_Q_plus": host.external_host.external_identity(state, {"source": source}),
        "q_compute_replay": {"branches": {"Q_plus": {"remaining_seconds": 135481, "sha256": "branch"}}},
        "continuation_inventory": {"parent_source": source,
            "original_supervisor_process": {"pid": 101, "start_ticks": 654},
            "closed_parent_workers": {"update-Q_minus": {"state": frozen_state}},
            "B_update": reference(root / "baseline.json"), "materials": {"direction.json": reference(root / "direction.json")}}}
    return plan, root, out


def test_external_terminal_requires_dead_process_then_loads_original_complete_checkpoint(tmp_path):
    plan, root, out = external_terminal_fixture(tmp_path)
    pending = host.observe_external(plan, now=100, identity_fn=lambda pid: {"alive": True, "start_ticks": 321})
    assert pending["status"] == "awaiting_original_worker_exit" and pending["excluded_gpu"] == 2
    result = host.observe_external(plan, now=101, identity_fn=lambda pid: {"alive": False})
    assert result["status"] == "complete" and result["excluded_gpu"] is None
    assert result["terminal"]["new_gpu_worker_seconds_by_observer"] == 0
    resumed = tmp_path / "resumed"
    write(resumed / "plan.json", plan)
    supervisor.store_external_terminal(resumed, result["terminal"])
    checkpoint = json.loads((out / "checkpoint/checkpoint.json").read_text())
    paths = []
    owner = SimpleNamespace(actor_steps=5, critic_steps=5,
        restore_checkpoint=lambda p: paths.append(p) or checkpoint,
        freeze_identity=lambda: checkpoint["actor_identity"])
    assert host._restored_state(owner, resumed, "Q_plus", resumed / "fake") == checkpoint
    assert paths == [root / "update-Q_plus/actual/checkpoint"]
    assert not (resumed / "update-Q_plus").exists()


@pytest.mark.parametrize("mutation", ["source", "checkpoint", "exit", "share", "partial_forward"])
def test_external_r4_terminal_rejects_incomplete_or_changed_source(tmp_path, mutation):
    plan, root, out = external_terminal_fixture(tmp_path)
    if mutation in {"source", "checkpoint"}:
        path = out / "report.json"
        value = json.loads(path.read_text())
        value["source_after" if mutation == "source" else "final_actor_identity"] = {"state": "changed"}
    elif mutation == "exit":
        path = root / "supervisor.json"
        value = json.loads(path.read_text())
        value["states"]["update-Q_plus"]["exit_code"] = -9
    else:
        path = out / "training-compute.json"
        value = json.loads(path.read_text())
        value["maximum_seconds" if mutation == "share" else "native_forward_completed"] = 1
    write(path, value)
    with pytest.raises(ValueError):
        host.observe_external(plan, now=100, identity_fn=lambda pid: {"alive": False})
