"""Focused R1 controls: real tiny optimizer/RNG state, no repeated world/model run."""

import copy

import pytest

from proworksim import composition_recovery_v025 as recovery
from proworksim.composition_training_v025 import validate_composition
from proworksim.online_training import prepare_window, tensor_tree_digest
from proworksim.storage import json_bytes, read_json
from test_composition_training_v025 import actual_window as shared_window_fixture, features
from test_online_training_v13 import _owner

actual_window = shared_window_fixture


def test_restore_exact_two_step_state_original_admission_weights_and_window(
    actual_window, tmp_path
):
    f = actual_window
    torch = f["torch"]
    source = f["collector"]
    assert source.actor_steps == source.critic_steps == 2 and source.phase == "collecting"
    original = prepare_window(
        f["entries"], f["identity"], source.window_id, source.recipe, features
    )
    _, material = validate_composition(f["entries"], original, f["unit"])
    old = tmp_path / "old-failed-fixture"
    old.mkdir()
    saved = source._state_bundle()
    torch.save(saved, old / "shared-before.pt")
    documents = {
        "entries": f["entries"],
        "declaration": f["declaration"],
        "composition": f["unit"],
        "admission": original,
        "composition_admission": material,
        "update_report": {"before_actor_identity": f["identity"]},
        "behavior_checks": [
            {"call_id": r["call_id"], "passed": True} for r in original["decisions"]
        ],
    }
    refs = {}
    for name, data in documents.items():
        p = old / (name + ".json")
        p.write_bytes(json_bytes(data))
        refs[name] = recovery.reference(p)
    refs["shared_before"] = recovery.reference(old / "shared-before.pt")
    binding = {
        "version": recovery.VERSION,
        "original_run": str(old),
        "inputs": refs,
        "no_step_proof": {"explicit_CPU_fixture": True},
        "original_total_gpu_seconds": 0,
        "original_window_id": source.window_id,
        "scheduled_slots": 8,
        "admitted_decisions": 16,
        "required_actor_steps_before": 2,
        "required_critic_steps_before": 2,
    }
    fresh = _owner(tmp_path, torch, "restored-owner", base_identity=f["base"])
    with torch.no_grad():
        for p in fresh.actor_parameters.values():
            p.fill_(9)
            p.grad = torch.ones_like(p)
        for p in fresh.critic.parameters():
            p.fill_(5)
            p.grad = torch.ones_like(p)
    fresh.actor_optimizer.param_groups[0]["lr"] = 0.77
    fresh.critic_optimizer.param_groups[0]["lr"] = 0.66
    torch.manual_seed(123456)

    def forbidden_begin(*args, **kwargs):
        raise AssertionError("R1 must not begin or duplicate the existing window ID")

    fresh.begin_window = forbidden_begin
    entries, composition, proof = recovery._restore_bound_state(
        fresh, binding, tmp_path / "r1", feature_function=features
    )
    assert tensor_tree_digest(fresh._state_bundle(), torch) == tensor_tree_digest(saved, torch)
    assert fresh.actor_steps == fresh.critic_steps == fresh.policy_revision == 2
    assert (
        fresh.window_id == saved["last_window_id"]
        and fresh.used_window_ids == saved["used_window_ids"]
    )
    assert fresh.phase == "collecting" and all(
        p.grad is None for p in fresh.actor_parameters.values()
    )
    assert all(p.grad is None for p in fresh.critic.parameters())
    assert json_bytes(entries) == json_bytes(f["entries"]) and composition == f["unit"]
    assert proof["restoration"]["exact_state_restored"]
    assert not proof["restoration"]["partial_gradients_reused"]
    assert not proof["restoration"]["new_training_model_calls"]
    assert proof["admission_reconstruction"]["sha256"] == refs["admission"]["sha256"]
    assert proof["composition_reconstruction"]["all_unit_weights"]
    assert read_json(tmp_path / "r1/restoration-proof.json") == proof
    # All original bytes remain unchanged, and a used/restored owner cannot
    # restore again while collecting. No new optimizer step is executed here.
    for ref in refs.values():
        assert recovery.reference(ref["path"]) == ref
    with pytest.raises(ValueError, match="idle full learner"):
        recovery._restore_bound_state(
            fresh, binding, tmp_path / "repeat", feature_function=features
        )
    changed = copy.deepcopy(original)
    changed["decisions"][0]["actor_denominator"] += 1
    (old / "admission.json").write_bytes(json_bytes(changed))
    another = _owner(tmp_path, torch, "bad-input-owner", base_identity=f["base"])
    with pytest.raises(ValueError, match="immutable original"):
        recovery._restore_bound_state(another, binding, tmp_path / "bad", feature_function=features)


def test_no_step_gate_rejects_existing_marker_live_worker_and_changed_counts(tmp_path, monkeypatch):
    old = tmp_path / "old"
    (old / "train_base/actual/update").mkdir(parents=True)
    source = {"code_commit": recovery.OLD_COMMIT, "code_dirty": False}
    identity = {"pid": 123, "start_ticks": 456, "uid": 789}
    stage = {
        "stage": "train_base",
        "status": "stopped",
        "exit_code": -15,
        "ended_at": 10,
        "pid": 123,
        "source": source,
        "task": {"kind": "update"},
        "stop_reason": "task_time_budget",
    }
    guard = {
        "last_stop_reason": "resource_query_failed",
        "worker_identity": identity,
        "original_supervisor_identity": {**identity, "pid": 124},
    }
    summary = {"status": "closed_with_incomplete_stages", "ended_at": 11}
    report = {
        "window_id": recovery.WINDOW_ID,
        "stage": "backward",
        "status": "preparing",
        "scheduled_slots": 16,
        "admitted_decisions": 283,
        "backward_decisions_completed": 266,
        "actor_optimizer_steps": 0,
        "critic_optimizer_steps": 0,
        "training_happened": False,
        "behavior_probability_passed": True,
    }
    monkeypatch.setattr(recovery, "original_process_alive", lambda _: False)
    result = recovery.prove_no_step(old, stage, guard, report, summary)
    assert result["admitted"] and result["terminal_live_tensor_read"] is False
    marker = old / "train_base/actual/update/gradients-before-clip.pt"
    marker.write_bytes(b"fixture marker")
    with pytest.raises(ValueError, match="pre-step artifact"):
        recovery.prove_no_step(old, stage, guard, report, summary)
    marker.unlink()
    with pytest.raises(ValueError, match="266/283"):
        recovery.prove_no_step(old, stage, guard, {**report, "actor_optimizer_steps": 1}, summary)
    monkeypatch.setattr(recovery, "original_process_alive", lambda _: True)
    with pytest.raises(ValueError, match="dead original"):
        recovery.prove_no_step(old, stage, guard, report, summary)
