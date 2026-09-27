"""Real CPU Qwen/PEFT graph controls; no 9B/GPU qualification or new samples."""

import pytest


@pytest.fixture
def fixture():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Installed original Qwen3.5 5.17.0 implementation")
    from peft import LoraConfig, get_peft_model
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig

    before = torch.get_num_threads(), torch.get_float32_matmul_precision()
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    torch.manual_seed(81)
    config = Qwen3_5TextConfig(vocab_size=64, hidden_size=32, intermediate_size=64,
        num_hidden_layers=8, num_attention_heads=4, num_key_value_heads=2, head_dim=8,
        linear_key_head_dim=8, linear_value_head_dim=8, linear_num_key_heads=2,
        linear_num_value_heads=2, layer_types=(["linear_attention"] * 3 + ["full_attention"]) * 2,
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
            "partial_rotary_factor": .5, "mrope_section": [1, 1, 0], "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=63, tie_word_embeddings=False)
    config._attn_implementation = "sdpa"
    model = get_peft_model(Qwen3_5ForCausalLM(config).float(), LoraConfig(r=8,
        lora_alpha=16, lora_dropout=0, target_modules=["q_proj", "v_proj"],
        bias="none", task_type="CAUSAL_LM"))
    # A nonzero adapter CPU fixture checks both A and B derivatives and past
    # first-full-attention effects propagated through later recurrent blocks.
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if "lora_B" in name:
                parameter.normal_(0, .02)
    model.train()
    trace = {"input_ids": ((torch.arange(70) * 11 + 9) % 61 + 1).tolist(),
             "output_ids": ((torch.arange(12) * 7 + 4) % 61 + 1).tolist(),
             "sampling_temperature": .7}
    yield torch, model, trace
    torch.set_num_threads(before[0])
    torch.set_float32_matmul_precision(before[1])


def test_complete_graph_checkpoint_gradient_finite_difference_and_detach_control(fixture):
    torch, model, trace = fixture
    from proworksim.functional_qwen_v022 import learning_logprobs, reference_logprobs
    from proworksim.numeric_paths_v021 import PathObserver, cache_teacher_replay

    parameters = {n: p for n, p in model.named_parameters() if p.requires_grad}
    reference = reference_logprobs(model, trace)
    reference_grad = torch.autograd.grad(-reference.mean(), tuple(parameters.values()))
    candidate = learning_logprobs(model, trace)
    candidate_grad = torch.autograd.grad(-candidate.mean(), tuple(parameters.values()))
    assert torch.equal(reference, candidate)
    assert all(torch.allclose(a, b, atol=2e-6, rtol=1e-4) for a, b in zip(reference_grad, candidate_grad))
    assert all(torch.isfinite(g).all() for g in candidate_grad)
    assert sum(int(torch.count_nonzero(g)) for g in candidate_grad) > 0
    # Forward equivalence to the independent installed original cache replay.
    with PathObserver(model, trace, ()) as observer:
        cached, _ = cache_teacher_replay(model, trace, observer, torch=torch, device="cpu")
    assert torch.allclose(reference.detach(), torch.tensor(cached), atol=1e-5, rtol=1e-5)
    model.train()
    # Finite differences along the fixed first attention's V-B gradient direction.
    name = "base_model.model.model.layers.3.self_attn.v_proj.lora_B.default.weight"
    index = list(parameters).index(name)
    parameter, derivative = parameters[name], reference_grad[index]
    direction = derivative / derivative.norm()
    expected = float((derivative * direction).sum())
    assert expected > 1e-5
    epsilon = .01
    original = parameter.detach().clone()
    losses = []
    with torch.no_grad():
        for sign in (1, -1):
            parameter.copy_(original + sign * epsilon * direction)
            losses.append(float(-reference_logprobs(model, trace).mean()))
        parameter.copy_(original)
    numerical = (losses[0] - losses[1]) / (2 * epsilon)
    assert numerical == pytest.approx(expected, abs=2e-4, rel=.02)
    detached = reference_logprobs(model, trace, detach_past_negative_control=True)
    detached_grad = torch.autograd.grad(-detached.mean(), tuple(parameters.values()))
    assert torch.equal(detached, reference)  # Same forward alone is not sufficient.
    discrepancy = torch.linalg.vector_norm(torch.cat([(a-b).flatten() for a, b in zip(reference_grad, detached_grad)]))
    reference_norm = torch.linalg.vector_norm(torch.cat([g.flatten() for g in reference_grad]))
    assert float(discrepancy / reference_norm) > .05
    assert all(p.grad is None for p in parameters.values())
    # Exercise the actual .backward API used by the future diagnostic/learner.
    final = learning_logprobs(model, trace)
    (-final.mean()).backward()
    assert all(torch.allclose(p.grad, expected, atol=2e-6, rtol=1e-4)
               for p, expected in zip(parameters.values(), reference_grad))
    for parameter in parameters.values():
        parameter.grad = None
    print({"forward_max_delta": float((candidate-reference).abs().max()),
           "gradient_max_delta": max(float((a-b).abs().max()) for a, b in zip(reference_grad, candidate_grad)),
           "finite_difference": numerical, "analytic_directional_derivative": expected,
           "detach_relative_gradient_error": float(discrepancy/reference_norm)})
