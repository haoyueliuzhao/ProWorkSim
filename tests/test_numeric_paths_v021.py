"""CPU random official hybrid model; no candidate checkpoint/GPU admission claim."""

import json

import pytest


@pytest.fixture
def tiny():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Installed 5.17.0 generation/cache interface control")
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig
    from peft import LoraConfig, get_peft_model

    old = torch.get_num_threads(), torch.get_float32_matmul_precision()
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    torch.manual_seed(81)
    config = Qwen3_5TextConfig(vocab_size=128, hidden_size=64, intermediate_size=128,
        num_hidden_layers=4, num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        linear_key_head_dim=16, linear_value_head_dim=16, linear_num_key_heads=2,
        linear_num_value_heads=2, layer_types=["linear_attention"] * 3 + ["full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
            "partial_rotary_factor": .5, "mrope_section": [1, 1, 2], "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=127, tie_word_embeddings=False)
    config._attn_implementation = "sdpa"
    network = get_peft_model(Qwen3_5ForCausalLM(config).float(), LoraConfig(r=8,
        lora_alpha=16, lora_dropout=0, target_modules=["q_proj", "v_proj"],
        bias="none", task_type="CAUSAL_LM"))
    network.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    network.enable_input_require_grads()
    network.eval()
    yield torch, network
    torch.set_num_threads(old[0])
    torch.set_float32_matmul_precision(old[1])


def test_actual_cached_teacher_matches_generate_and_observes_real_branch_changes(tiny, tmp_path, monkeypatch):
    torch, model = tiny
    from proworksim.local_model_service import SamplingTrace
    from proworksim.numeric_paths_v021 import run_paths
    from proworksim.online_training import recipe_config, tensor_tree_digest

    # This CPU fixture creates its own initial trace. Production only reads the
    # already archived 8473+146 trace and never invokes generate or multinomial.
    inputs = ((torch.arange(70) * 11 + 9) % 125 + 1)[None, :]
    sampler = SamplingTrace(.7)
    with torch.inference_mode():
        generated = model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs),
            max_new_tokens=6, do_sample=True, temperature=1, top_p=1, top_k=0,
            use_cache=True, logits_processor=[sampler], pad_token_id=0, eos_token_id=None)
    trace = {"input_ids": inputs[0].tolist(), "output_ids": generated[0, inputs.shape[1]:].tolist(),
             "behavior_logprobs": sampler.finish(generated)[0], "sampling_temperature": .7}
    before = tensor_tree_digest({n: p for n, p in model.named_parameters() if p.requires_grad}, torch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Diagnostic tried to draw a new token or call generate")
    monkeypatch.setattr(torch, "multinomial", forbidden)
    monkeypatch.setattr(model, "generate", forbidden)
    result = run_paths(model, trace, torch=torch, device="cpu", recipe=recipe_config(),
                       positions=(0, 1, 2, 5), diagnostic_failure_position=3, output=tmp_path)
    assert result["sampled_new_tokens"] == result["backward_calls"] == result["optimizer_steps"] == 0
    cache = result["paths"]["cache_no_grad"]
    assert cache["comparison_to_original_sampling"]["max_abs_delta"] < 1e-5
    counts = cache["branch_counts"]
    assert counts["prefill:causal_conv1d_fn"] == 3
    assert counts["prefill:torch_chunk_gated_delta_rule"] == 3
    assert counts["cached_decode:causal_conv1d_update"] == 15
    assert counts["cached_decode:torch_recurrent_gated_delta_rule"] == 15
    full = result["paths"]["full_no_grad"]
    assert full["branch_counts"]["full_no_grad:torch_chunk_gated_delta_rule"] == 3
    assert all("recurrent" not in key for key in full["branch_counts"])
    grad = result["paths"]["full_grad"]["gradient_execution"]
    assert grad["grad_enabled"] and grad["model_training"] and grad["logprobs_require_grad"]
    assert all(row["enabled"] for row in grad["gradient_checkpointing_modules"])
    assert any(row["use_reentrant"] is False for row in grad["gradient_checkpointing_modules"])
    assert all(row["p"] == 0 for row in grad["dropout_modules"])
    assert not result["cached_gradient_path"]["executed"]
    assert all(p.grad is None for p in model.parameters())
    assert tensor_tree_digest({n: p for n, p in model.named_parameters() if p.requires_grad}, torch) == before
    assert set(cache["layer_hidden_summaries"]) == {"0", "1", "2", "3", "5"}
    assert set(result["between_paths"]["layer_hidden_full_vs_cache"]) == {"0", "1", "2", "3", "5"}
    assert cache["cache_states_at_selected_positions"]["5"]["sequence_length"] == 75
    saved = json.loads((tmp_path / "paths.json").read_text())
    assert "_hidden_vectors" not in json.dumps(saved)
    assert saved["paths"]["cache_no_grad"]["logit_summaries"]["0"]["elements"] == 128
