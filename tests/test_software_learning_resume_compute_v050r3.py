"""CPU-only contracts for the two-interruption, fixed-total r3 budget."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_resume_compute_v050r3 as compute
from scripts.run_ne_v021 import reference, write


def stopped_chain(tmp_path, *, rows=3, gradient_counts=(2, 2)):
    first, second = tmp_path / "r1", tmp_path / "r2"
    checkpoint = {"actor_steps": 4, "critic_steps": 4, "actor_identity": {"same": "Sstar4"}}
    write(tmp_path / "Sstar/checkpoint.json", checkpoint)
    recipe = {"same": "original H1"}
    training_budget = {"aggregate_worker_seconds": 518400, "per_branch_worker_seconds": 172800,
        "per_branch_actor_optimizer": 1, "per_branch_critic_optimizer": 1}
    sources = {name: reference(compute.SOURCE / name)["sha256"] for name in compute.NUMERIC_SOURCES}
    plan = compute.original.seal({"version": compute.previous.VERSION, "limits": compute.original.LIMITS,
        "s_star_checkpoint": reference(tmp_path / "Sstar/checkpoint.json"), "s_star_recipe": recipe,
        "source_files": sources, "source_root": str(compute.SOURCE), "training_budget": training_budget}, "plan_sha256")
    write(first / "plan.json", plan)
    for name in compute.COPIED_INPUTS:
        write(first / name, {"fixture": name})
    admission = {"decisions": [{"row": i} for i in range(rows)]}
    write(first / "pretraining-admission.json", admission)
    entries = [{"slot_id": "original-slot", "active_members": ["member_001", "member_002"]}]
    declaration = {"window_id": "same-window", "gamma_identity": {"mapper_spec_sha256": "same-mapper"}}
    write(first / "entries.json", entries)
    write(first / "declaration.json", declaration)
    weights = {"original-slot": {"member_001": 0.9, "member_002": 1.0}}
    b_start = 1791891179.1762383
    b_end = 1792002191.3173168
    b_output = first / "update-B/actual"
    b_update = {"advantages": [2] * rows, "old_critic_values": [1] * rows, "rewards": [3] * rows,
        "actor_optimizer_steps": 1, "critic_optimizer_steps": 1, "backward_decisions_completed": rows}
    write(b_output / "update/report.json", b_update)
    write(b_output / "training-compute.json", {"started_at": b_start, "ended_at": b_end,
        "elapsed_seconds": b_end - b_start, "native_gradient_forward_started": rows,
        "native_forward_started": 2 * rows + 2, "native_forward_completed": 2 * rows + 2})
    write(b_output / "report.json", {"status": "complete", "success_boundary": True,
        "new_actor_steps": 1, "new_critic_steps": 1, "update_report": reference(b_output / "update/report.json")})
    core = compute.original.seal({"source_support_artifact_sha256": reference(first / "support.json")["sha256"],
        "declaration_sha256": digest(json_bytes(declaration)), "design_sha256": "same-design",
        "minus_weights_by_slot": weights}, "seal_sha256")
    write(first / "direction.json", compute.original.seal({"selected": True, "direction": core,
        "minus_weights": weights, "frozen_before_any_development": True,
        "B_update": reference(b_output / "update/report.json")}, "seal_sha256"))
    composition = compute.original.seal({"weights_by_slot": weights,
        "entries_sha256": reference(first / "entries.json")["sha256"]}, "seal_sha256")

    def stop(root, local_plan, index, receipt):
        output = root / compute.WORKER / "actual"
        started = [1792002724.686521, 1792047749.9954946][index]
        ended = [1792044614.6065538, 1792070446.669287][index]
        gradient = gradient_counts[index]
        receipt.update(started_at=started, native_forward_started=rows + gradient,
            native_forward_completed=rows + gradient, native_gradient_forward_started=gradient,
            native_no_grad_forward_started=rows)
        write(output / "training-compute.json", receipt)
        write(output / "update/report.json", {"status": "preparing", "stage": "backward", "admitted_decisions": rows,
            "backward_decisions_completed": gradient - 1, "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
            "training_happened": False, "actor_update_enabled": True, "behavior_probability_passed": True,
            "before_actor_identity": checkpoint["actor_identity"], "recipe": recipe})
        write(output / "loaded-state.json", {"branch": "S_star", "checkpoint": local_plan["s_star_checkpoint"],
            "restored": checkpoint, "actor_identity": checkpoint["actor_identity"], "actor_steps": 4, "critic_steps": 4})
        for name in ("composition-before-update.json", "update/composition.json"):
            write(output / name, composition)
        write(output / "update-v050-learning-binding.json", {"same": "numeric binding"})
        write(output / "update-original-updater-binding.json", {
            "original_source": {"sha256": sources["src/proworksim/online_training.py"]}, "code_object_identical": True})
        (output / "update/shared-before.pt").write_bytes(b"Do not load this fixture as a tensor")
        pid = 123 + index
        identity = {"pid": pid, "start_ticks": 100 + index}
        write(output / "task.json", {"task": f"learning-backward-or-bookkeeping-{rows + gradient:06d}", "pid": pid})
        host_path = root / "host-stop-actions" / (compute.WORKER + ".json")
        write(host_path, {"worker": compute.WORKER, "pid": pid, "process_identity": identity,
            "reason": "shared_device_free_memory_reserve", "process_returncode": -9,
            "requested_at": ended - 6, "stop_procedure_returned_at": ended - 0.01})
        write(root / "mechanism-stops" / (compute.WORKER + "-supervisor.json"), {
            "worker": compute.WORKER, "kind": "execution_fault", "reason": "shared_device_free_memory_reserve",
            "observed_at": ended, "worker_state": {"worker": compute.WORKER, "status": "stopped",
                "attempted": True, "exit_code": -9, "ended_at": ended, "pid": pid,
                "process_identity": identity, "host_stop_action": reference(host_path)}})

    stop(first, plan, 0, compute.original.training_compute_receipt(admission))
    replay = compute.prior.derive_replay_budget(first)
    second_plan = compute.original.seal({**{k: v for k, v in plan.items() if k != "plan_sha256"},
        "version": compute.PARENT_VERSION, "parent_run_root": str(first),
        "parent_plan": reference(first / "plan.json"), "qminus_compute_replay": replay}, "plan_sha256")
    write(second / "plan.json", second_plan)
    for name in compute.COPIED_INPUTS:
        (second / name).write_bytes((first / name).read_bytes())
    stop(second, second_plan, 1, compute.prior.training_compute_receipt(admission, replay=replay))
    write(second / compute.WORKER / "actual/recompute-binding.json", {
        "budget": replay, "numeric_path": compute.numeric_path_receipt(compute.SOURCE), "partial_state_reused": False})
    return first, second


def test_real_count_and_time_arithmetic_counts_both_attempts_once(tmp_path):
    _, parent = stopped_chain(tmp_path, rows=643, gradient_counts=(192, 46))
    replay = compute.derive_replay_budget(parent)
    assert replay["prior_elapsed_seconds_upper"] == 64586.59382510185
    assert replay["original_branch_remaining_seconds"] == 108213.40617489815
    assert replay["remaining_seconds_exact"] == 170001.265096426
    assert replay["remaining_seconds"] == 170001
    assert replay["original_branch_48h_enforced"] is False
    assert replay["prior_native_forward_started"] == 1524
    assert replay["prior_actor_backward_completed_lower"] == 236
    assert replay["prior_actor_backward_charged_upper"] == replay["prior_critic_backward_charged_upper"] == 238
    assert replay["cumulative_upper"] == {"forward": 2816, "actor_backward": 881, "critic_backward": 881}
    assert replay["Q_plus_reserved_seconds"] == 172800
    assert replay["Q_plus_live_status_read"] is False
    assert replay["aggregate_seconds_upper"] == 518399.734903574
    assert replay["aggregate_seconds_upper"] <= replay["aggregate_compute_seconds_cap"]
    assert replay["new_branch_total_seconds_upper"] > replay["original_branch_seconds_cap"]
    assert replay["resume_partial_gradients_or_RNG"] is False


@pytest.mark.parametrize(("attempt", "mutation"), [
    ("r1", "actor_step"), ("r2", "critic_step"), ("r1", "row_completed"),
    ("r2", "missing_forward"), ("r1", "checkpoint"), ("r2", "gradients"),
    ("r1", "wrong_stop"), ("r2", "host_identity"), ("r2", "different_Sstar"),
    ("r2", "different_recipe"), ("r1", "material"), ("r2", "material"),
    ("r2", "numeric_binding"), ("r2", "prior_budget"), ("r1", "B_interval"),
])
def test_modified_old_boundary_or_material_is_rejected(tmp_path, attempt, mutation):
    first, second = stopped_chain(tmp_path)
    root = first if attempt == "r1" else second
    output = root / compute.WORKER / "actual"
    path = output / "update/report.json"
    data = read_json(path)
    if mutation == "actor_step":
        data["actor_optimizer_steps"] = 1
    elif mutation == "critic_step":
        data["critic_optimizer_steps"] = 1
    elif mutation == "row_completed":
        data["backward_decisions_completed"] += 1
    elif mutation == "missing_forward":
        path = output / "training-compute.json"
        data = read_json(path)
        data["native_forward_completed"] -= 1
    elif mutation == "checkpoint":
        (output / "checkpoint").mkdir()
    elif mutation == "gradients":
        (output / "update/gradients-before-clip.pt").write_bytes(b"never load")
    elif mutation == "wrong_stop":
        path = root / "mechanism-stops" / (compute.WORKER + "-supervisor.json")
        data = read_json(path)
        data["reason"] = "unknown termination"
    elif mutation == "host_identity":
        path = root / "host-stop-actions" / (compute.WORKER + ".json")
        data = read_json(path)
        data["process_identity"]["start_ticks"] += 1
    elif mutation == "different_Sstar":
        path = output / "loaded-state.json"
        data = read_json(path)
        data["actor_steps"] = 5
    elif mutation == "different_recipe":
        data["recipe"] = {"different": True}
    elif mutation == "material":
        path = root / "entries.json"
        data = {"different": "material"}
    elif mutation == "numeric_binding":
        path = output / "recompute-binding.json"
        data = read_json(path)
        data["numeric_path"]["original_H1_code_object_identical"] = False
    elif mutation == "prior_budget":
        path = output / "training-compute.json"
        data = read_json(path)
        data["prior_actor_backward_charged_upper"] = 0
    else:
        path = first / "update-B/actual/training-compute.json"
        data = read_json(path)
        data["elapsed_seconds"] -= 1
    write(path, data)
    with pytest.raises(ValueError):
        compute.derive_replay_budget(second)


def test_admission_order_and_counts_cannot_expand(tmp_path):
    _, parent = stopped_chain(tmp_path)
    replay = compute.derive_replay_budget(parent)
    admission = read_json(parent / "pretraining-admission.json")
    admission["decisions"].reverse()
    with pytest.raises(ValueError, match="reorder"):
        compute.training_compute_receipt(admission, replay=replay)
    replay = {k: v for k, v in replay.items() if k != "sha256"}
    replay["prior_actor_backward_charged_upper"] = 3071
    with pytest.raises(ValueError, match="Cumulative"):
        compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"),
            replay=compute.original.seal(replay))


@pytest.mark.parametrize(("changes", "reason"), [
    ({"replay_version": "other"}, "replay_compute_receipt_identity"),
    ({"maximum_seconds": 170002}, "replay_compute_interval_changed"),
    ({"original_branch_48h_enforced": True}, "replay_compute_interval_changed"),
    ({"Q_plus_reserved_seconds": 170000}, "replay_compute_interval_changed"),
    ({"aggregate_compute_seconds_cap": 518401}, "replay_compute_interval_changed"),
    ({"prior_elapsed_seconds_upper": 0}, "replay_compute_interval_changed"),
    ({"native_forward_started": 13}, "cumulative_forward_cap_exceeded"),
    ({"native_gradient_forward_started": 4}, "cumulative_actor_backward_cap_exceeded"),
])
def test_guard_keeps_total_reservation_and_count_caps(tmp_path, changes, reason):
    _, parent = stopped_chain(tmp_path)
    replay = compute.derive_replay_budget(parent)
    receipt = compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"), replay=replay, started_at=1000)
    receipt.update(changes)
    assert compute.training_stop_reason(receipt, now=1001) == reason


def test_dispatch_stops_at_remaining_interval_and_restores_owner(tmp_path, monkeypatch):
    _, parent = stopped_chain(tmp_path)
    replay = compute.derive_replay_budget(parent)
    receipt = compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"), replay=replay, started_at=1000)
    output = tmp_path / "attempt"
    write(output / "training-compute.json", receipt)
    calls = []

    def native(tokens):
        calls.append(tokens)
        return "same-result"

    owner = SimpleNamespace(torch=SimpleNamespace(is_grad_enabled=lambda: True), learning_logprobs=native)
    monkeypatch.setattr(compute.time, "time", lambda: 171000)
    with compute.training_progress(owner, output):
        assert owner.learning_logprobs("same") == "same-result"
        monkeypatch.setattr(compute.time, "time", lambda: 171001)
        with pytest.raises(RuntimeError, match="interval_exhausted"):
            owner.learning_logprobs("must-not-dispatch")
    assert calls == ["same"]
    assert owner.learning_logprobs is native


def test_numeric_code_objects_stay_original():
    receipt = compute.numeric_path_receipt(compute.SOURCE)
    assert receipt["original_H1_code_object_identical"] is True
    assert receipt["original_prepare_code_object_identical"] is True
    assert receipt["original_r1_update_window_identical"] is True
    assert receipt["critic_reweighted"] is False
    assert receipt["tensor_files_loaded"] == receipt["model_calls"] == 0


def test_new_wrapper_calls_original_H1_once_and_never_reuses_partial_gradients(tmp_path, monkeypatch):
    from proworksim import software_learning_v050r1 as learner
    _, parent = stopped_chain(tmp_path)
    root = tmp_path / "r3"
    output = root / compute.WORKER / "actual"
    root.mkdir()
    for name in compute.COPIED_INPUTS:
        (root / name).write_bytes((parent / name).read_bytes())
    replay = compute.derive_replay_budget(parent)
    plan = {"parent_run_root": str(parent), "parent_source_root": str(compute.SOURCE),
        "qminus_compute_replay": replay, "design": {"sha256": "same-design"}}
    entries = read_json(root / "entries.json")
    admission = read_json(root / "pretraining-admission.json")
    direction = read_json(root / "direction.json")
    baseline = read_json(compute.original.checked(direction["B_update"]))
    calls = []
    owner = SimpleNamespace(recipe={}, actor_steps=4, critic_steps=4,
        begin_window=lambda window: calls.append(("begin", window)), learning_logprobs=lambda tokens: tokens,
        torch=SimpleNamespace(is_grad_enabled=lambda: True), save_checkpoint=lambda path: {"path": str(path)})

    def restore(actual_owner, actual_root, branch, actual_output):
        assert actual_owner is owner and actual_root == root and actual_output == output
        calls.append(("restore", branch))

    def native_update(actual_owner, actual_entries, folder, **kwargs):
        assert actual_owner is owner and actual_entries == entries
        assert kwargs["request_evidence_root"] == root and kwargs["observe_support_gradients"] is False
        assert kwargs["composition"] == direction["minus_weights"]
        calls.append(("native", "same-H1"))
        for _ in admission["decisions"]:
            owner.learning_logprobs("same-tokens")
        report = {**baseline, "status": "updated", "stage": "complete", "post_update_additional_actor_forwards": 0}
        write(folder / "report.json", report)
        return report

    monkeypatch.setattr(learner, "prepare_training_admission", lambda *args: admission)
    monkeypatch.setattr(learner, "bind_composition", lambda entries, declaration, weights, **kw: copy.deepcopy(weights))
    monkeypatch.setattr(learner, "update_software_window", native_update)
    old_update = compute.original._update
    result = compute.update(owner, plan, root, compute.WORKER, output,
        restored_state=restore, load_entries=lambda actual_plan, actual_root: entries)
    assert calls == [("restore", "S_star"), ("begin", "same-window"), ("native", "same-H1")]
    assert result["branch"] == "Q_minus" and result["new_actor_steps"] == result["new_critic_steps"] == 1
    accounting = read_json(output / "recompute-accounting.json")
    assert accounting["cumulative_actor_backward_completed_lower"] == 5
    assert accounting["cumulative_actor_backward_charged_upper"] == 7
    assert accounting["cumulative_actor_optimizer_steps"] == 1
    assert accounting["original_branch_48h_enforced"] is False
    assert accounting["aggregate_with_full_Qplus_reservation_seconds_upper"] <= 518400
    assert compute.original._update is old_update
    with pytest.raises(FileExistsError, match="again"):
        compute.update(owner, plan, root, compute.WORKER, output)
    with pytest.raises(ValueError, match="Only"):
        compute.update(owner, plan, root, "update-Q_plus", output)
