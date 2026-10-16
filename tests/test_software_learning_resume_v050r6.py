"""Finite CPU controls for read-only update dependencies and original inventory."""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import software_learning_resume_v050r6 as host
from scripts.run_ne_v021 import reference, write


def test_only_original_sixteen_units_and_one_changed_limit():
    plan = {"inventory": json.loads(host.original.DESIGN.read_text())}
    assert host.UPDATES == () and len(host.WORKERS) == 16
    assert [host.worker_units(plan, n) for n in host.WORKERS] == [
        host.prior.worker_units(plan, n) for n in host.prior.DEVELOPMENT]
    assert host.generation_caps() == host.prior.generation_caps()
    assert {k: v for k, v in host.LIMITS.items() if v != host.prior.LIMITS[k]} == {
        "max_parallel_model_instances": 4}
    for name in ("update-Q_plus", "update-Q_minus", "collect-0", "dev-B-0"):
        with pytest.raises(ValueError):
            host.worker_units(plan, name)


def external_fixture(tmp_path, branch="Q_minus"):
    source = {"code_commit": "original", "code_dirty": False}
    state = {"worker": "update-" + branch, "pid": 101, "process_identity": {"start_ticks": 1001},
        "gpu": 2, "gpu_uuid": "GPU-2", "started_at": 50, "attempted": True, "status": "running"}
    summary = {"source": source, "states": {state["worker"]: state}, "status": "running", "observer_pid": 102}
    write(tmp_path / "supervisor.json", summary)
    binding = {"run_root": str(tmp_path), "identity": host.external_identity(branch, state, source),
        "supervisor_process": {"pid": 102, "start_ticks": 1002}}
    plan = {"external_updates": {branch: binding}}
    def identities(pid):
        return {"alive": True, "start_ticks": 1001 if pid == 101 else 1002}
    return plan, summary, state, identities


def test_running_external_counts_and_excludes_gpu_without_touching_process(tmp_path):
    plan, _, _, identities = external_fixture(tmp_path)
    got = host._observe_branch(plan, "Q_minus", now=100, identity_fn=identities)
    assert got["status"] == "running" and got["resident_count"] == 1 and got["excluded_gpu"] == 2


@pytest.mark.parametrize("fault", ["pid_reused", "guardian_dead", "gpu_changed", "source_changed", "failed"])
def test_external_identity_and_owner_faults_do_not_release_capacity(tmp_path, fault):
    plan, summary, state, identities = external_fixture(tmp_path)
    if fault == "pid_reused":
        def identities(pid):
            return {"alive": True, "start_ticks": 9999}
    elif fault == "guardian_dead":
        def identities(pid):
            return {"alive": pid == 101, "start_ticks": 1001}
    elif fault == "gpu_changed":
        state["gpu"] = 3
    elif fault == "source_changed":
        summary["source"] = {"changed": True}
    else:
        state["status"] = "stopped"
    write(tmp_path / "supervisor.json", summary)
    with pytest.raises(ValueError):
        host._observe_branch(plan, "Q_minus", now=100, identity_fn=identities)


def test_terminal_requires_original_pid_exit_and_bounded_receipt_race(tmp_path, monkeypatch):
    plan, summary, state, identities = external_fixture(tmp_path)
    state["status"] = "complete"
    write(tmp_path / "supervisor.json", summary)
    got = host._observe_branch(plan, "Q_minus", now=100, identity_fn=identities)
    assert got["status"] == "awaiting_original_worker_exit" and got["resident_count"] == 1
    with pytest.raises(ValueError):
        host._observe_branch(plan, "Q_minus", previous=got, now=200, identity_fn=identities)
    monkeypatch.setattr(host, "_validate_complete", lambda *args: {"exact": True})
    got = host._observe_branch(plan, "Q_minus", now=110, identity_fn=lambda pid: {"alive": False})
    assert got == {"status": "complete", "resident_count": 0, "excluded_gpu": None, "terminal": {"exact": True}}


def test_exited_worker_without_terminal_still_counts_and_then_faults(tmp_path):
    plan, _, _, _ = external_fixture(tmp_path)
    got = host._observe_branch(plan, "Q_minus", now=100, identity_fn=lambda pid: {"alive": False})
    assert got["status"] == "awaiting_original_host_closure" and got["resident_count"] == 1
    with pytest.raises(ValueError):
        host._observe_branch(plan, "Q_minus", previous=got, now=200, identity_fn=lambda pid: {"alive": False})


def test_parent_aggregate_closure_can_follow_immutable_branch_receipt(tmp_path, monkeypatch):
    write(tmp_path / "plan.json", host.seal({}, "plan_sha256"))
    write(tmp_path / "supervisor.json", {})
    plan = {"parent_plan": reference(tmp_path / "plan.json"), "parent_run_root": str(tmp_path),
        "continuation_inventory": {"administrative_handoff": {}, "closed_parent_workers": {}}}
    monkeypatch.setattr(host, "_handoff", lambda *a: {})
    monkeypatch.setattr(host.prior, "observe_external", lambda *a, **k: {})
    previous = {b: {"status": "complete", "resident_count": 0, "excluded_gpu": None,
        "terminal": {"original_supervisor_status": "running", "checkpoint": "exact"}} for b in host.BRANCHES}
    current = copy.deepcopy(previous)
    for observation in current.values():
        observation["terminal"]["original_supervisor_status"] = "closed_with_unknowns"
    monkeypatch.setattr(host, "_observe_branch", lambda p, b, **kw: current[b])
    assert host.observe_externals(plan, prior=previous) == current
    current["Q_minus"]["terminal"]["checkpoint"] = "substitution"
    with pytest.raises(ValueError):
        host.observe_externals(plan, prior=previous)


def handoff_fixture(tmp_path):
    parent = {"source": {"original": True}}
    write(tmp_path / "plan.json", parent)
    states = {name: {"worker": name, "status": "stopped", "attempted": False,
        "model_started": False, "stop_reason": "unopened_work_paused", "resource_attempt_number": 0,
        "elapsed_gpu_seconds": 0} for name in host.DEVELOPMENT}
    states["update-Q_minus"] = {"status": "running"}
    summary = {"source": parent["source"], "states": states, "status": "running"}
    marker = {"version": host.HANDOFF_VERSION, "kind": "administrative_handoff",
        "parent_plan": reference(tmp_path / "plan.json"), "source": parent["source"],
        "transferred_workers": list(host.DEVELOPMENT), "all_transferred_workers_unstarted": True,
        "resource_attempts_for_transferred_workers": 0, "maximum_total_residents": 4,
        "count_external_Q_plus_and_Q_minus": True, "signals_sent": [],
        "active_update_workers_interrupted": False, "old_records_rewritten": False,
        "new_scientific_slots": 0, "new_seeds": 0, "new_update_budget": 0}
    write(tmp_path / host.HANDOFF_FILE, marker)
    return parent, summary


def test_handoff_accepts_only_exact_unstarted_inventory_and_administrative_marker(tmp_path):
    parent, summary = handoff_fixture(tmp_path)
    expected = reference(tmp_path / host.HANDOFF_FILE)
    assert host._handoff(tmp_path, parent, summary) == expected
    summary["status"] = "closed_with_unknowns"
    assert host._handoff(tmp_path, parent, summary) == expected
    write(tmp_path / "mechanism-stops/real-fault.json", {"kind": "execution_fault"})
    with pytest.raises(ValueError):
        host._handoff(tmp_path, parent, summary)


@pytest.mark.parametrize("fault", ["attempted", "model_started", "folder", "resource_attempt"])
def test_handoff_rejects_any_development_attempt(tmp_path, fault):
    parent, summary = handoff_fixture(tmp_path)
    name = host.DEVELOPMENT[0]
    if fault == "folder":
        (tmp_path / name).mkdir()
    elif fault == "resource_attempt":
        summary["states"][name]["resource_attempt_number"] = 1
    else:
        summary["states"][name][fault] = True
    with pytest.raises(ValueError):
        host._handoff(tmp_path, parent, summary)


def complete_fixture(tmp_path, branch="Q_minus", actor_enabled=True):
    plan, summary, state, _ = external_fixture(tmp_path, branch)
    folder = tmp_path / ("update-" + branch) / "actual"
    state.update(status="complete", ended_at=2000, exit_code=0, elapsed_gpu_seconds=1950)
    summary["status"] = "closed_with_unknowns"
    recipe = {"frozen": "H1"}
    baseline = {"advantages": [1.0, 2.0], "old_critic_values": [0.0, 0.0], "rewards": [1, 2]}
    write(tmp_path / "B.json", baseline)
    sstar = {"actor_identity": {"state": "4/4"}, "actor_steps": 4, "critic_steps": 4}
    write(tmp_path / "S_star.json", sstar)
    budget = host.seal({"branch": branch, "remaining_seconds": 159200, "admitted_rows_per_attempt": 2,
        "global_allocation_sha256": "allocation", "inputs": {"entries.json": {"sha256": "entries"}}})
    weights = {"slot": {"001": 1.1 if branch == "Q_plus" else 0.9}}
    sign = "plus" if branch == "Q_plus" else "minus"
    core = host.seal({sign + "_weights_by_slot": weights}, "seal_sha256")
    direction = host.seal({"direction": core, sign + "_weights": weights}, "seal_sha256")
    write(tmp_path / "direction.json", direction)
    plan.update(s_star_recipe=recipe, s_star_checkpoint=reference(tmp_path / "S_star.json"),
        continuation_inventory={"B_update": reference(tmp_path / "B.json"),
            "materials": {"direction.json": reference(tmp_path / "direction.json")}},
        q_compute_replay={"branches": {branch: budget}})
    checkpoint = {"actor_identity": {"state": "Q"}, "actor_steps": 5 if actor_enabled else 4,
        "critic_steps": 5, "serialized_reload_exact": True}
    update = {**baseline, "stage": "complete", "status": "updated", "recipe": recipe,
        "actor_optimizer_steps": int(actor_enabled), "critic_optimizer_steps": 1,
        "actor_update_enabled": actor_enabled, "admitted_decisions": 2,
        "post_update_additional_actor_forwards": 2, "backward_decisions_completed": 2}
    write(folder / "update/report.json", update)
    write(folder / "checkpoint/checkpoint.json", checkpoint)
    report = {"status": "complete", "success_boundary": True, "source_before": summary["source"],
        "source_after": summary["source"], "update_report": reference(folder / "update/report.json"),
        "checkpoint": checkpoint, "final_actor_identity": checkpoint["actor_identity"],
        "actor_steps": checkpoint["actor_steps"], "critic_steps": checkpoint["critic_steps"]}
    write(folder / "report.json", report)
    compute = {"started_at": 100, "ended_at": 1000, "elapsed_seconds": 900,
        "maximum_seconds": 159200, "admitted_rows": 2, "forward_upper": 10,
        "actor_backward_upper": 2, "critic_backward_upper": 2, "actor_steps_upper": 1, "critic_steps_upper": 1,
        "replay_version": "software-learning-Q-recompute-v0.50-r4", "replay_budget_sha256": budget["sha256"],
        "branch": branch, "time_policy": "B-actual-plus-all-old-Q-intervals-then-equal-two-Q-within-total144h",
        "global_allocation_sha256": "allocation", "prior_Q_seconds_upper": {"Q_plus": 50000, "Q_minus": 50000},
        "prior_elapsed_seconds_upper": 50000, "B_complete_interval_seconds": 100000,
        "aggregate_compute_seconds_cap": 518400, "original_branch_seconds_cap": 172800,
        "original_branch_remaining_seconds": 122800, "original_branch_48h_enforced": False,
        "prior_native_forward_started": 1, "prior_actor_backward_charged_upper": 1,
        "prior_critic_backward_charged_upper": 1, "cumulative_forward_cap": 6150,
        "cumulative_actor_backward_cap": 3072, "cumulative_critic_backward_cap": 3072,
        "old_cost_counted_once": True, "native_forward_started": 4 + 2 * actor_enabled,
        "native_forward_completed": 4 + 2 * actor_enabled,
        "native_gradient_forward_started": 2 * actor_enabled, "native_no_grad_forward_started": 4}
    write(folder / "training-compute.json", compute)
    composition = host.seal({"weights_by_slot": weights, "entries_sha256": "entries"}, "seal_sha256")
    write(folder / "composition-before-update.json", composition)
    write(folder / "update/composition.json", composition)
    write(folder / "recompute-binding.json", {"budget": budget, "scientific_branch": branch, "partial_state_reused": False})
    write(folder / "loaded-state.json", {"branch": "S_star", "checkpoint": plan["s_star_checkpoint"],
        "restored": sstar, "actor_identity": sstar["actor_identity"], "actor_steps": 4, "critic_steps": 4})
    return plan, summary, state, folder


@pytest.mark.parametrize("branch,actor_enabled", [("Q_plus", True), ("Q_minus", True), ("Q_minus", False)])
def test_original_complete_update_and_critic_only_boundary_are_read_only(tmp_path, branch, actor_enabled):
    plan, summary, state, folder = complete_fixture(tmp_path, branch, actor_enabled)
    terminal = host._validate_complete(plan, branch, summary, state)
    assert terminal["checkpoint"] == reference(folder / "checkpoint/checkpoint.json")
    assert terminal["new_model_calls_by_observer"] == terminal["new_gpu_worker_seconds_by_observer"] == 0


@pytest.mark.parametrize("filename,key,value", [
    ("training-compute.json", "maximum_seconds", 172800),
    ("training-compute.json", "native_forward_completed", 5),
    ("training-compute.json", "native_gradient_forward_started", 1),
    ("training-compute.json", "prior_actor_backward_charged_upper", 3072),
    ("training-compute.json", "elapsed_seconds", 901),
    ("report.json", "source_after", {"changed": True}),
    ("report.json", "success_boundary", False),
    ("loaded-state.json", "actor_steps", 5),
    ("recompute-binding.json", "partial_state_reused", True),
])
def test_incomplete_or_changed_external_update_never_releases_development(tmp_path, filename, key, value):
    plan, summary, state, folder = complete_fixture(tmp_path)
    data = json.loads((folder / filename).read_text())
    data[key] = value
    write(folder / filename, data)
    with pytest.raises(ValueError):
        host._validate_complete(plan, "Q_minus", summary, state)


def test_opposite_direction_or_changed_old_critic_is_rejected(tmp_path):
    plan, summary, state, folder = complete_fixture(tmp_path)
    composition = host.seal({"weights_by_slot": {"slot": {"001": 1.1}}, "entries_sha256": "entries"}, "seal_sha256")
    write(folder / "composition-before-update.json", composition)
    write(folder / "update/composition.json", composition)
    with pytest.raises(ValueError):
        host._validate_complete(plan, "Q_minus", summary, state)
    plan, summary, state, folder = complete_fixture(tmp_path)
    update = json.loads((folder / "update/report.json").read_text())
    update["old_critic_values"] = [1, 2]
    write(folder / "update/report.json", update)
    report = json.loads((folder / "report.json").read_text())
    report["update_report"] = reference(folder / "update/report.json")
    write(folder / "report.json", report)
    with pytest.raises(ValueError):
        host._validate_complete(plan, "Q_minus", summary, state)


def test_restore_uses_external_checkpoint_and_rejects_training_branch(tmp_path):
    plan, summary, state, folder = complete_fixture(tmp_path)
    terminal = host._validate_complete(plan, "Q_minus", summary, state)
    write(tmp_path / "external-Q_minus-complete.json", host.seal(terminal))
    write(tmp_path / "plan.json", plan)
    checkpoint = json.loads((folder / "checkpoint/checkpoint.json").read_text())
    seen = []
    owner = SimpleNamespace(actor_steps=5, critic_steps=5,
        freeze_identity=lambda: checkpoint["actor_identity"],
        restore_checkpoint=lambda path: seen.append(path) or checkpoint)
    output = tmp_path / "development"
    output.mkdir()
    assert host._restored_state(owner, tmp_path, "Q_minus", output) == checkpoint
    assert seen == [folder / "checkpoint"]
    assert not (tmp_path / "update-Q_plus").exists()
    with pytest.raises(ValueError):
        host._restored_state(owner, tmp_path, "S_star", output)
