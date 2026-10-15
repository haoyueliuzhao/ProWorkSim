"""CPU contracts for a same-Qminus full replay and its cumulative accounting."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes, read_json
from scripts import software_learning_resume_compute_v050r2 as compute
from scripts.run_ne_v021 import reference, write


def stopped_fixture(tmp_path):
    root = tmp_path / "parent"
    output = root / compute.WORKER / "actual"
    checkpoint = {"actor_steps": 4, "critic_steps": 4, "actor_identity": {"same": "Sstar4"}}
    write(tmp_path / "Sstar/checkpoint.json", checkpoint)
    recipe = {"same": "original H1"}
    plan = compute.original.seal({"version": compute.previous.VERSION, "limits": compute.original.LIMITS,
        "s_star_checkpoint": reference(tmp_path / "Sstar/checkpoint.json"), "s_star_recipe": recipe}, "plan_sha256")
    write(root / "plan.json", plan)
    for name in compute.COPIED_INPUTS:
        write(root / name, {"fixture": name})
    write(root / "pretraining-admission.json", {"decisions": [{"row": i} for i in range(3)]})
    receipt = compute.original.training_compute_receipt(read_json(root / "pretraining-admission.json"), started_at=100)
    receipt.update(native_forward_started=5, native_forward_completed=5,
        native_gradient_forward_started=2, native_no_grad_forward_started=3)
    write(output / "training-compute.json", receipt)
    write(output / "update/report.json", {"status": "preparing", "stage": "backward", "admitted_decisions": 3,
        "backward_decisions_completed": 1, "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
        "training_happened": False, "actor_update_enabled": True, "behavior_probability_passed": True,
        "before_actor_identity": checkpoint["actor_identity"], "recipe": recipe})
    write(output / "loaded-state.json", {"branch": "S_star", "checkpoint": plan["s_star_checkpoint"],
        "restored": checkpoint, "actor_identity": checkpoint["actor_identity"], "actor_steps": 4, "critic_steps": 4})
    for name in ("composition-before-update.json", "update/composition.json",
                 "update-v050-learning-binding.json", "update-original-updater-binding.json"):
        write(output / name, {"fixture": name})
    (output / "update/shared-before.pt").write_bytes(b"Never load this fixture as a tensor")
    write(root / "mechanism-stops" / (compute.WORKER + "-supervisor.json"), {
        "worker": compute.WORKER, "kind": "execution_fault", "reason": "shared_device_free_memory_reserve",
        "observed_at": 120, "worker_state": {"worker": compute.WORKER, "status": "stopped",
            "attempted": True, "exit_code": -9, "ended_at": 120}})
    return root


def test_old_incomplete_row_is_charged_but_never_claimed_completed(tmp_path):
    parent = stopped_fixture(tmp_path)
    budget = compute.derive_replay_budget(parent)
    assert budget["prior_elapsed_seconds_upper"] == 20
    assert budget["remaining_seconds"] == 172780
    assert budget["prior_actor_backward_completed_lower"] == budget["prior_critic_backward_completed_lower"] == 1
    assert budget["prior_actor_backward_charged_upper"] == budget["prior_critic_backward_charged_upper"] == 2
    assert budget["cumulative_upper"] == {"forward": 17, "actor_backward": 5, "critic_backward": 5}
    assert budget["tensor_filenames_inspected_only"] == ["update/shared-before.pt"]
    assert budget["resume_partial_gradients_or_RNG"] is False


@pytest.mark.parametrize("mutation", ["actor_step", "critic_step", "row_completed", "missing_forward",
    "checkpoint", "gradients", "time_exhausted", "wrong_stop", "different_Sstar", "different_recipe"])
def test_unbound_interruption_cannot_be_replayed(tmp_path, mutation):
    parent = stopped_fixture(tmp_path)
    output = parent / compute.WORKER / "actual"
    path = output / "update/report.json"
    data = read_json(path)
    if mutation == "actor_step":
        data["actor_optimizer_steps"] = 1
    elif mutation == "critic_step":
        data["critic_optimizer_steps"] = 1
    elif mutation == "row_completed":
        data["backward_decisions_completed"] = 2
    elif mutation == "missing_forward":
        path = output / "training-compute.json"
        data = read_json(path)
        data["native_forward_completed"] -= 1
    elif mutation == "checkpoint":
        (output / "checkpoint").mkdir()
    elif mutation == "gradients":
        (output / "update/gradients-before-clip.pt").write_bytes(b"do not load")
    elif mutation == "time_exhausted":
        path = parent / "mechanism-stops" / (compute.WORKER + "-supervisor.json")
        data = read_json(path)
        data["observed_at"] = data["worker_state"]["ended_at"] = 172900
    elif mutation == "wrong_stop":
        path = parent / "mechanism-stops" / (compute.WORKER + "-supervisor.json")
        data = read_json(path)
        data["reason"] = "unknown termination"
    elif mutation == "different_Sstar":
        path = output / "loaded-state.json"
        data = read_json(path)
        data["actor_steps"] = 5
    else:
        data["recipe"] = {"different": True}
    write(path, data)
    with pytest.raises(ValueError):
        compute.derive_replay_budget(parent)


def test_admission_order_and_old_plus_new_caps_are_enforced(tmp_path):
    parent = stopped_fixture(tmp_path)
    budget = compute.derive_replay_budget(parent)
    admission = read_json(parent / "pretraining-admission.json")
    receipt = compute.training_compute_receipt(admission, replay=budget, started_at=1000)
    assert receipt["maximum_seconds"] == 172780
    assert compute.training_stop_reason(receipt, now=173779) is None
    assert compute.training_stop_reason(receipt, now=173780) == "cumulative_update_interval_exhausted"
    assert compute.training_stop_reason(receipt, now=173781) == "cumulative_update_interval_exhausted"
    admission["decisions"].reverse()
    with pytest.raises(ValueError, match="reorder"):
        compute.training_compute_receipt(admission, replay=budget)
    altered = {k: v for k, v in budget.items() if k != "sha256"}
    altered["prior_actor_backward_charged_upper"] = 3071
    with pytest.raises(ValueError, match="Cumulative"):
        compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"),
            replay=compute.original.seal(altered))


@pytest.mark.parametrize(("changes", "reason"), [
    ({"replay_version": "other"}, "replay_compute_receipt_identity"),
    ({"maximum_seconds": 172800}, "replay_compute_interval_changed"),
    ({"native_forward_started": 13}, "cumulative_forward_cap_exceeded"),
    ({"native_gradient_forward_started": 4}, "cumulative_actor_backward_cap_exceeded"),
])
def test_supervisor_observer_rejects_extra_work(tmp_path, changes, reason):
    parent = stopped_fixture(tmp_path)
    budget = compute.derive_replay_budget(parent)
    receipt = compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"),
        replay=budget, started_at=1000)
    receipt.update(changes)
    assert compute.training_stop_reason(receipt, now=1001) == reason


def test_forward_wrapper_preserves_owner_and_blocks_expired_dispatch(tmp_path, monkeypatch):
    parent = stopped_fixture(tmp_path)
    budget = compute.derive_replay_budget(parent)
    receipt = compute.training_compute_receipt(read_json(parent / "pretraining-admission.json"),
        replay=budget, started_at=1000)
    output = tmp_path / "attempt"
    write(output / "training-compute.json", receipt)
    calls = []
    def original(tokens):
        calls.append(tokens)
        return "same-return"
    owner = SimpleNamespace(torch=SimpleNamespace(is_grad_enabled=lambda: True), learning_logprobs=original)
    monkeypatch.setattr(compute.time, "time", lambda: 1001)
    with compute.training_progress(owner, output):
        assert owner.learning_logprobs("same-tokens") == "same-return"
        monkeypatch.setattr(compute.time, "time", lambda: 173781)
        with pytest.raises(RuntimeError, match="interval_exhausted"):
            owner.learning_logprobs("must-not-dispatch")
    assert calls == ["same-tokens"]
    assert owner.learning_logprobs is original
    after = read_json(output / "training-compute.json")
    assert after["native_forward_started"] == after["native_forward_completed"] == 1


def test_numeric_H1_and_reader_code_objects_are_original():
    proof = compute.numeric_path_receipt(compute.SOURCE)
    assert proof["original_H1_code_object_identical"] is True
    assert proof["original_prepare_code_object_identical"] is True
    assert proof["original_r1_update_window_identical"] is True
    assert proof["critic_reweighted"] is False
    assert proof["tensor_files_loaded"] == proof["model_calls"] == 0


def test_update_dispatches_original_adapter_from_Sstar_once_with_frozen_material(tmp_path, monkeypatch):
    from proworksim import software_learning_v050r1 as learner
    parent = stopped_fixture(tmp_path)
    root = tmp_path / "recompute"
    output = root / compute.WORKER / "actual"
    declaration = {"window_id": "same-window", "gamma_identity": {"mapper_spec_sha256": "same-mapper"}}
    entries = [{"slot_id": "original-slot", "active_members": ["member_001", "member_002"]}]
    write(parent / "entries.json", entries)
    write(parent / "declaration.json", declaration)
    core = compute.original.seal({"source_support_artifact_sha256": reference(parent / "support.json")["sha256"],
        "declaration_sha256": digest(json_bytes(declaration)), "design_sha256": "same-design",
        "minus_weights_by_slot": {"original-slot": {"member_001": 0.9, "member_002": 1.0}}}, "seal_sha256")
    baseline = {"advantages": [2, 2, 2], "old_critic_values": [1, 1, 1], "rewards": [3, 3, 3]}
    write(tmp_path / "B-report.json", baseline)
    write(parent / "direction.json", compute.original.seal({"selected": True, "direction": core,
        "minus_weights": core["minus_weights_by_slot"], "B_update": reference(tmp_path / "B-report.json")}, "seal_sha256"))
    for name in compute.COPIED_INPUTS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((parent / name).read_bytes())
    plan = {"parent_run_root": str(parent), "parent_source_root": str(compute.SOURCE),
        "qminus_compute_replay": compute.derive_replay_budget(parent), "design": {"sha256": "same-design"}}
    admission = read_json(parent / "pretraining-admission.json")
    calls = []
    owner = SimpleNamespace(recipe={}, actor_steps=4, critic_steps=4,
        begin_window=lambda window: calls.append(("begin", window)),
        learning_logprobs=lambda tokens: tokens, torch=SimpleNamespace(is_grad_enabled=lambda: True),
        save_checkpoint=lambda path: {"same-boundary": str(path)})

    def restore(actual_owner, actual_root, branch, actual_output):
        assert actual_owner is owner and actual_root == root and actual_output == output
        calls.append(("restore", branch))

    def native_update(actual_owner, actual_entries, folder, **kwargs):
        assert actual_owner is owner and actual_entries == entries
        assert kwargs["request_evidence_root"] == root
        assert kwargs["observe_support_gradients"] is False
        assert kwargs["composition"] == core["minus_weights_by_slot"]
        calls.append(("native", "same-H1"))
        for _ in admission["decisions"]:
            owner.learning_logprobs("same-tokens")
        report = {**baseline, "status": "updated", "stage": "complete", "backward_decisions_completed": 3,
            "actor_optimizer_steps": 1, "critic_optimizer_steps": 1, "post_update_additional_actor_forwards": 0}
        write(folder / "report.json", report)
        return report

    monkeypatch.setattr(learner, "prepare_training_admission", lambda *args: admission)
    monkeypatch.setattr(learner, "bind_composition", lambda actual_entries, actual_declaration, weights, **kw: copy.deepcopy(weights))
    monkeypatch.setattr(learner, "update_software_window", native_update)
    old_update = compute.original._update
    result = compute.update(owner, plan, root, compute.WORKER, output,
        restored_state=restore, load_entries=lambda actual_plan, actual_root: entries)
    assert calls == [("restore", "S_star"), ("begin", "same-window"), ("native", "same-H1")]
    assert result["branch"] == "Q_minus" and result["new_actor_steps"] == result["new_critic_steps"] == 1
    accounting = read_json(output / "recompute-accounting.json")
    assert accounting["cumulative_actor_backward_completed_lower"] == 4
    assert accounting["cumulative_actor_backward_charged_upper"] == 5
    assert accounting["cumulative_actor_optimizer_steps"] == 1
    assert compute.original._update is old_update
    with pytest.raises(FileExistsError, match="again"):
        compute.update(owner, plan, root, compute.WORKER, output)
    with pytest.raises(ValueError, match="Only"):
        compute.update(owner, plan, root, "update-Q_plus", output)
