"""Tiny real Torch replay worker controls; no dense checkpoint or GPU is loaded."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.online_training import SharedActor, tensor_tree_digest
from proworksim.software_learning_v029 import migrate_software_owner
from proworksim.storage import digest, read_json
from scripts import probe_dense_replay_v031 as probe
from test_functional_dense_v031 import fixture  # noqa: F401 -- shared real CPU architecture fixture


def build_owner(fixture, tmp_path):  # noqa: F811
    torch, model, trace = fixture
    owner = SharedActor(model, SimpleNamespace(), output=tmp_path / "resident",
        base_identity={"manifest": {"sha256": digest(b"explicit-tiny-cpu-fixture")}},
        inference_profile={"candidate_id": "tiny-" + model.config.model_type}, device="cpu", torch_module=torch)
    migrate_software_owner(owner, expected_steps=None)
    common_dir = tmp_path / "common"
    common = owner.save_checkpoint(common_dir)
    actual = probe.native_cache_logprobs(owner.model, trace).cpu().tolist()
    trace.update(behavior_logprobs=actual, raw_behavior_logprobs=list(actual), input_mask=[0] * len(trace["input_ids"]))
    return owner, trace, common_dir, common


def test_full_replay_control_preserves_all_targets_has_real_gradients_and_exact_restore(fixture, tmp_path, monkeypatch):  # noqa: F811
    owner, trace, common_dir, common = build_owner(fixture, tmp_path)
    original = copy.deepcopy(trace)
    monkeypatch.setattr(owner.actor_optimizer, "step", lambda: pytest.fail("No actor optimizer step allowed"))
    monkeypatch.setattr(owner.critic_optimizer, "step", lambda: pytest.fail("No critic optimizer step allowed"))
    result = probe.evaluate_owner(owner, trace, tmp_path / "probe", common_dir=common_dir,
                                  common_record=common, report={"cpu_fixture": True})
    assert result["passed"] and result["full_backward_completed"]
    assert result["all_behavior_and_gradient_probability_passed"] and result["all_full_tokens_retained"]
    assert result["optimizer_steps"] == result["new_model_calls"] == 0
    assert result["common_restored_exactly"] and result["gradients_cleared"]
    assert result["before_restore_state_unchanged"]
    assert trace == original and len(result["paths"]) == 4
    assert all(row["returned_targets"] == len(original["output_ids"]) for row in result["paths"].values())
    assert tensor_tree_digest(owner._state_bundle(), owner.torch) == common["state_tensor_digest"]
    assert not list((owner.output / "calls").glob("*.json"))
    assert read_json(tmp_path / "probe/functional-parameter-gradients.json")["total_nonzero_elements"] > 0


def test_failed_gradient_path_retains_partial_evidence_and_restores_common(fixture, tmp_path, monkeypatch):  # noqa: F811
    owner, trace, common_dir, common = build_owner(fixture, tmp_path)
    original = probe.learning_logprobs

    def fail_only_gradient(model, trace):
        if owner.torch.is_grad_enabled():
            raise RuntimeError("Explicit tiny CPU gradient-path failure")
        return original(model, trace)

    monkeypatch.setattr(probe, "learning_logprobs", fail_only_gradient)
    result = probe.evaluate_owner(owner, trace, tmp_path / "probe", common_dir=common_dir,
                                  common_record=common, report={"cpu_fixture": True})
    assert not result["passed"] and not result["full_backward_completed"]
    assert result["common_restored_exactly"] and result["gradients_cleared"]
    assert result["optimizer_steps"] == result["new_model_calls"] == 0
    assert result["paths"]["functional_no_grad"]["status"] == "completed"
    assert result["paths"]["functional_train_backward"]["status"] == "error"
    assert (tmp_path / "probe/original_full_no_grad-logprobs.json").exists()
    assert (tmp_path / "probe/errors.log").exists()
    assert tensor_tree_digest(owner._state_bundle(), owner.torch) == common["state_tensor_digest"]
