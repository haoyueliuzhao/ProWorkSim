"""Actual tiny-Qwen control; absent optional ML packages skip in the light venv."""
import pytest


def test_tiny_qwen_original_backward_and_ordered_bank_adam_match(tmp_path):
    pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("peft")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Original installed Qwen3.5 5.17.0 implementation required")
    from scripts.qualify_gradient_reuse_v037 import qualify

    report = qualify(tmp_path / "qualification", profiles=("fp32", "mixed_bf16"))
    assert report["passed"] is True
    result = report["profiles"][0]
    assert result["common_actor_optimizer_steps"] and set(result["common_actor_optimizer_steps"]) == {3.0}
    assert result["nonzero_lora_B"] is True
    assert result["candidates"]["B"]["comparisons"]["actor_gradient"]["aggregate"]["bitwise_equal"] is True
    assert result["candidates"]["weighted"]["comparisons"]["critic_optimizer"]["aggregate"]["bitwise_equal"] is True
    mixed = report["profiles"][1]
    assert mixed["passed"] is True
    assert mixed["unit_rescaling_diagnostic"]["approved_for_production"] is False
    assert mixed["unit_rescaling_diagnostic"]["passed_strict_gate"] is False
    for profile in report["profiles"]:
        repeated = profile["candidates"]["weighted_repeated"]
        assert repeated["cache_hits"] == 3
        assert repeated["cache_misses"] == 0
        assert repeated["actual_compute_calls"] == {"actor_forwards": 0, "actor_backwards": 0}
    assert report["real_task_samples"] == report["real_model_optimizer_steps"] == 0
