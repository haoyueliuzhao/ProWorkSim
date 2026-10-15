"""CPU-only contracts for two complete Q attempts with all old cost retained."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.storage import read_json
from scripts import software_learning_resume_compute_v050r4 as compute
from scripts.run_ne_v021 import reference, write
from test_software_learning_resume_compute_v050r3 import stopped_chain


def terminal_chain(tmp_path, *, rows=3, gradients=(2, 2), plus_gradient=2):
    first, second = stopped_chain(tmp_path, rows=rows, gradient_counts=gradients)
    plan = read_json(first / "plan.json")
    direction = read_json(first / "direction.json")
    core = {k: v for k, v in direction["direction"].items() if k != "seal_sha256"}
    plus_weights = {"original-slot": {"member_001": 1.1, "member_002": 1.0}}
    core["plus_weights_by_slot"] = plus_weights
    direction.update(direction=compute.original.seal(core, "seal_sha256"), plus_weights=plus_weights)
    direction.pop("seal_sha256")
    write(first / "direction.json", compute.original.seal(direction, "seal_sha256"))
    for name in compute.COPIED_INPUTS:
        (second / name).write_bytes((first / name).read_bytes())
    replay = compute.prior.prior.derive_replay_budget(first)
    second_plan = read_json(second / "plan.json")
    second_plan.update(qminus_compute_replay=replay)
    second_plan.pop("plan_sha256")
    write(second / "plan.json", compute.original.seal(second_plan, "plan_sha256"))
    second_output = second / "update-Q_minus/actual"
    receipt = read_json(second_output / "training-compute.json")
    receipt["replay_budget_sha256"] = replay["sha256"]
    write(second_output / "training-compute.json", receipt)
    write(second_output / "recompute-binding.json", {"budget": replay,
        "numeric_path": compute.numeric_path_receipt(compute.SOURCE), "partial_state_reused": False})
    output = first / "update-Q_plus/actual"
    for name in ("loaded-state.json", "update-original-updater-binding.json", "update-v050-learning-binding.json"):
        write(output / name, read_json(first / "update-Q_minus/actual" / name))
    checkpoint = read_json(compute.original.checked(plan["s_star_checkpoint"]))
    admission = read_json(first / "pretraining-admission.json")
    receipt = compute.original.training_compute_receipt(admission)
    receipt.update(started_at=1792002725.803326, native_forward_started=rows + plus_gradient,
        native_forward_completed=rows + plus_gradient - 1, native_gradient_forward_started=plus_gradient,
        native_no_grad_forward_started=rows)
    write(output / "training-compute.json", receipt)
    error = {"type": "KeyboardInterrupt", "message": "signal 15"}
    write(output / "update/report.json", {"status": "interrupted", "stage": "backward", "admitted_decisions": rows,
        "backward_decisions_completed": plus_gradient - 1, "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
        "training_happened": False, "actor_update_enabled": True, "behavior_probability_passed": True,
        "before_actor_identity": checkpoint["actor_identity"], "after_actor_identity": checkpoint["actor_identity"],
        "recipe": plan["s_star_recipe"], "interruption": error})
    write(output / "report.json", {"worker": "update-Q_plus", "status": "execution_error", "error": error,
        "success_boundary": False, "new_actor_steps": 0, "new_critic_steps": 0, "actor_steps": 4, "critic_steps": 4})
    write(output / "task.json", {"task": f"learning-forward-{rows + plus_gradient:06d}", "pid": 3124120})
    composition = compute.original.seal({"weights_by_slot": plus_weights,
        "entries_sha256": reference(first / "entries.json")["sha256"]}, "seal_sha256")
    for name in ("composition-before-update.json", "update/composition.json"):
        write(output / name, composition)
    (output / "update/shared-before.pt").write_bytes(b"Never load this fixture")
    host_path = first / "host-stop-actions/update-Q_plus.json"
    identity = {"pid": 3124120, "start_ticks": 442690332}
    write(host_path, {"worker": "update-Q_plus", "pid": 3124120, "process_identity": identity,
        "reason": "shared_device_free_memory_reserve", "requested_at": 1792074560.1297007,
        "host_pid": 465916, "stop_procedure_returned_at": 1792074564.950956, "process_returncode": -2})
    state = {"worker": "update-Q_plus", "status": "stopped", "attempted": True, "exit_code": -2,
        "ended_at": 1792074564.9529374, "pid": 3124120, "process_identity": identity, "host_stop_action": reference(host_path)}
    write(first / "mechanism-stops/update-Q_plus-supervisor.json", {"worker": "update-Q_plus",
        "kind": "execution_fault", "reason": "shared_device_free_memory_reserve",
        "observed_at": state["ended_at"], "worker_state": state})
    write(first / "mechanism-stops/update-Q_plus-execution.json", {"worker": "update-Q_plus",
        "kind": "execution_fault", "error": error, "observed_at": 1792074560.1447089})
    write(first / "supervisor.json", {"observer_pid": 465916, "states": {"update-Q_plus": state},
        "status": "closed_with_unknowns"})
    third = tmp_path / "r3"
    minus = compute.prior.derive_replay_budget(second)
    workers = ["update-Q_minus", *(f"dev-{b}-{i}" for b in compute.BRANCHES for i in range(8))]
    write(third / "plan.json", compute.original.seal({"version": compute.PARENT_VERSION,
        "parent_run_root": str(second), "parent_plan": reference(second / "plan.json"),
        "qminus_compute_replay": minus, "s_star_checkpoint": plan["s_star_checkpoint"],
        "workers": workers, "source": {"frozen": "r3"}}, "plan_sha256"))
    write(third / "supervisor.json", {"status": "closed_with_unknowns", "ended_at": 1792074571.1259,
        "source": {"frozen": "r3"}, "closed_worker_gpu_seconds": 0, "running_worker_gpu_seconds": 0,
        "states": {w: {"worker": w, "status": "stopped", "attempted": False,
            "stop_reason": "unopened_work_paused", "elapsed_gpu_seconds": 0} for w in workers}})
    for name in compute.COPIED_INPUTS:
        (third / name).write_bytes((second / name).read_bytes())
    return first, second, third


def test_actual_arithmetic_counts_all_three_old_attempts_and_zero_r3(tmp_path):
    _, _, third = terminal_chain(tmp_path, rows=643, gradients=(192, 46), plus_gradient=346)
    budget = compute.derive_replay_budget(third)
    a = budget["allocation"]
    assert a["B_complete_interval_seconds"] == 111012.14107847214
    assert a["prior_Q_seconds_upper"] == {"Q_plus": 71839.14961147308, "Q_minus": 64586.59382510185}
    assert a["branch_seconds"] == {"Q_plus": 135481, "Q_minus": 135481}
    assert a["prior_all_compute_seconds_upper"] == 247437.88451504707
    assert a["aggregate_seconds_upper"] == 518399.8845150471
    assert a["r3_unstarted_reserved_seconds_charged"] == 0
    plus, minus = (budget["branches"][b] for b in compute.BRANCHES)
    assert plus["prior_native_forward_started"] == 989 and plus["prior_native_forward_completed"] == 988
    assert plus["prior_actor_backward_completed_lower"] == 345
    assert plus["prior_actor_backward_charged_upper"] == 346
    assert plus["cumulative_upper"] == {"forward": 2281, "actor_backward": 989, "critic_backward": 989}
    assert minus["cumulative_upper"] == {"forward": 2816, "actor_backward": 881, "critic_backward": 881}
    assert all(b["original_branch_48h_enforced"] is False for b in budget["branches"].values())


@pytest.mark.parametrize("mutation", ["actor", "forward", "signal", "owner", "checkpoint", "state", "r3_attempt", "r3_cost", "material"])
def test_modified_boundary_is_rejected(tmp_path, mutation):
    first, _, third = terminal_chain(tmp_path)
    output = first / "update-Q_plus/actual"
    path = output / "update/report.json"
    data = read_json(path)
    if mutation == "actor":
        data["actor_optimizer_steps"] = 1
    elif mutation == "forward":
        path = output / "training-compute.json"
        data = read_json(path)
        data["native_forward_completed"] += 1
    elif mutation == "signal":
        data["interruption"]["message"] = "signal 9"
    elif mutation == "owner":
        path = first / "supervisor.json"
        data = read_json(path)
        data["observer_pid"] += 1
    elif mutation == "checkpoint":
        (output / "update/gradients.pt").write_bytes(b"Never load")
    elif mutation == "state":
        data["after_actor_identity"] = {"changed": True}
    elif mutation.startswith("r3_"):
        path = third / "supervisor.json"
        data = read_json(path)
        if mutation == "r3_cost":
            data["closed_worker_gpu_seconds"] = 1
        else:
            data["states"]["update-Q_minus"]["attempted"] = True
    else:
        path = third / "entries.json"
        data = {"changed": True}
    write(path, data)
    with pytest.raises(ValueError):
        compute.derive_replay_budget(third)


@pytest.mark.parametrize("branch", compute.BRANCHES)
def test_branch_receipt_total_guard_and_deadline_prevent_dispatch(tmp_path, monkeypatch, branch):
    _, _, third = terminal_chain(tmp_path)
    budget = compute.derive_replay_budget(third)
    replay = budget["branches"][branch]
    admission = read_json(third / "pretraining-admission.json")
    receipt = compute.training_compute_receipt(admission, replay=replay, started_at=1000)
    assert compute.training_stop_reason(receipt, now=1001) is None
    for field, value in (("maximum_seconds", 135482), ("aggregate_compute_seconds_cap", 518401),
                         ("original_branch_48h_enforced", True), ("prior_elapsed_seconds_upper", 0)):
        changed = {**receipt, field: value}
        assert compute.training_stop_reason(changed, now=1001) == "replay_compute_interval_changed"
    changed = {**receipt, "native_gradient_forward_started": 4}
    assert compute.training_stop_reason(changed, now=1001) == "cumulative_actor_backward_cap_exceeded"
    changed = {**receipt, "native_forward_started": 13}
    assert compute.training_stop_reason(changed, now=1001) == "cumulative_forward_cap_exceeded"
    output = tmp_path / "new"
    write(output / "training-compute.json", receipt)
    calls = []
    def native(tokens):
        calls.append(tokens)
        return tokens
    owner = SimpleNamespace(torch=SimpleNamespace(is_grad_enabled=lambda: True), learning_logprobs=native)
    monkeypatch.setattr(compute.time, "time", lambda: 136480)
    with compute.training_progress(owner, output):
        assert owner.learning_logprobs("same") == "same"
        monkeypatch.setattr(compute.time, "time", lambda: 136481)
        with pytest.raises(RuntimeError, match="interval_exhausted"):
            owner.learning_logprobs("forbidden")
    assert calls == ["same"] and owner.learning_logprobs is native
    admission["decisions"].reverse()
    with pytest.raises(ValueError, match="reorder"):
        compute.training_compute_receipt(admission, replay=replay)


@pytest.mark.parametrize("branch", compute.BRANCHES)
def test_each_new_wrapper_calls_original_H1_once_with_its_frozen_direction(tmp_path, monkeypatch, branch):
    from proworksim import software_learning_v050r1 as learner
    _, _, third = terminal_chain(tmp_path)
    budget = compute.derive_replay_budget(third)
    root = tmp_path / "r4"
    root.mkdir()
    for name in compute.COPIED_INPUTS:
        (root / name).write_bytes((third / name).read_bytes())
    output = root / ("update-" + branch) / "actual"
    plan = {"q_compute_replay": budget, "parent_source_root": str(compute.SOURCE), "design": {"sha256": "same-design"}}
    admission, entries, direction = (read_json(root / name) for name in ("pretraining-admission.json", "entries.json", "direction.json"))
    baseline = read_json(compute.original.checked(direction["B_update"]))
    calls = []
    owner = SimpleNamespace(recipe={}, actor_steps=4, critic_steps=4, begin_window=lambda w: calls.append(("begin", w)),
        learning_logprobs=lambda tokens: tokens, torch=SimpleNamespace(is_grad_enabled=lambda: True),
        save_checkpoint=lambda path: {"path": str(path)})
    def restore(actual_owner, actual_root, which, actual_output):
        assert actual_owner is owner and actual_root == root and actual_output == output
        calls.append(("restore", which))
    def update(actual_owner, actual_entries, folder, **kwargs):
        assert actual_owner is owner and actual_entries == entries
        assert kwargs["composition"] == direction[branch.removeprefix("Q_") + "_weights"]
        assert kwargs["observe_support_gradients"] is False
        calls.append(("native", "unchanged-H1"))
        for _ in admission["decisions"]:
            owner.learning_logprobs("same-tokens")
        report = {**baseline, "status": "updated", "stage": "complete", "post_update_additional_actor_forwards": 0}
        write(folder / "report.json", report)
        return report
    monkeypatch.setattr(learner, "prepare_training_admission", lambda *args: admission)
    monkeypatch.setattr(learner, "bind_composition", lambda entries, declaration, weights, **kw: copy.deepcopy(weights))
    monkeypatch.setattr(learner, "update_software_window", update)
    result = compute.update(owner, plan, root, "update-" + branch, output,
        restored_state=restore, load_entries=lambda *args: entries)
    assert calls == [("restore", "S_star"), ("begin", "same-window"), ("native", "unchanged-H1")]
    assert result["branch"] == branch and result["new_actor_steps"] == result["new_critic_steps"] == 1
    accounting = read_json(output / "recompute-accounting.json")
    assert accounting["cumulative_actor_optimizer_steps"] == 1
    assert accounting["aggregate_with_other_new_reservation_seconds_upper"] < 518400
    with pytest.raises(FileExistsError, match="again"):
        compute.update(owner, plan, root, "update-" + branch, output)


def test_original_numerical_source_and_code_objects_are_reused():
    receipt = compute.numeric_path_receipt(compute.SOURCE)
    assert receipt["original_H1_code_object_identical"] is True
    assert receipt["original_prepare_code_object_identical"] is True
    assert receipt["original_r1_update_window_identical"] is True
    assert receipt["critic_reweighted"] is False
    assert receipt["tensor_files_loaded"] == receipt["model_calls"] == 0
