"""Tiny real Qwen2/Mistral CPU controls, not actual 14B/24B GPU qualification."""
import copy

import pytest


@pytest.fixture(params=["qwen2", "mistral"])
def fixture(request):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Control binds the installed original 5.17.0 dense implementations")
    from peft import LoraConfig, get_peft_model
    from transformers import MistralConfig, MistralForCausalLM, Qwen2Config, Qwen2ForCausalLM
    from proworksim.candidate_runtime_v0201 import HeadExecution

    previous = torch.get_num_threads(), torch.get_float32_matmul_precision()
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    torch.manual_seed(81)
    cls, config_cls = ((Qwen2ForCausalLM, Qwen2Config) if request.param == "qwen2" else (MistralForCausalLM, MistralConfig))
    config = config_cls(vocab_size=97, hidden_size=32, intermediate_size=64,
        num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, head_dim=8,
        attention_dropout=0.0, max_position_embeddings=512, sliding_window=None,
        pad_token_id=0, eos_token_id=96, tie_word_embeddings=False)
    config._attn_implementation = "sdpa"
    model = get_peft_model(cls(config).float(), LoraConfig(r=4, lora_alpha=8, lora_dropout=0,
                          target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"))
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if "lora_B" in name:
                parameter.normal_(0, .03)
    model.head_execution = HeadExecution(model.get_output_embeddings(), torch)
    model.enable_input_require_grads()
    model.train()
    output = ((torch.arange(11) * 7 + 4) % 94 + 1).tolist() + [96]
    trace = {"input_ids": ((torch.arange(37) * 11 + 9) % 94 + 1).tolist(),
             "output_ids": output, "raw_output_ids": list(output), "output_mask": [1] * len(output),
             "sampling_temperature": .7}
    yield torch, model, trace
    torch.set_num_threads(previous[0])
    torch.set_float32_matmul_precision(previous[1])


def test_native_cache_checkpoint_gradients_and_detached_past_negative_control(fixture):
    torch, model, trace = fixture
    from proworksim.functional_dense_v031 import learning_logprobs, native_cache_logprobs, reference_logprobs

    original = copy.deepcopy(trace)
    parameters = {name: parameter for name, parameter in model.named_parameters() if parameter.requires_grad}
    reference = reference_logprobs(model, trace)
    reference_grad = torch.autograd.grad(-reference.mean(), tuple(parameters.values()))
    actual = learning_logprobs(model, trace)
    actual_grad = torch.autograd.grad(-actual.mean(), tuple(parameters.values()))
    assert torch.equal(actual, reference)
    assert all(torch.allclose(a, b, atol=2e-6, rtol=1e-4) for a, b in zip(reference_grad, actual_grad, strict=True))
    assert all(torch.isfinite(value).all() for value in actual_grad)
    assert sum(int(torch.count_nonzero(value)) for value in actual_grad) > 0
    cached = native_cache_logprobs(model, trace)
    assert torch.allclose(reference.detach(), cached, atol=2e-6, rtol=1e-5)
    assert model.training  # Independent diagnostic restored the caller's mode.
    detached = reference_logprobs(model, trace, detach_past_negative_control=True)
    detached_grad = torch.autograd.grad(-detached.mean(), tuple(parameters.values()))
    assert torch.equal(detached, reference)
    discrepancy = torch.linalg.vector_norm(torch.cat([(a - b).flatten() for a, b in zip(reference_grad, detached_grad, strict=True)]))
    normal = torch.linalg.vector_norm(torch.cat([value.flatten() for value in reference_grad]))
    assert float(discrepancy / normal) > .01
    assert trace == original and actual.shape == (len(trace["raw_output_ids"]),)
    assert trace["output_ids"][-1] == model.config.eos_token_id
    (-learning_logprobs(model, trace).mean()).backward()
    assert all(torch.allclose(parameter.grad, gradient, atol=2e-6, rtol=1e-4)
               for parameter, gradient in zip(parameters.values(), reference_grad, strict=True))
    print({"architecture": model.config.model_type, "cache_forward_max_delta": float((cached - reference.detach()).abs().max()),
           "checkpoint_gradient_max_delta": max(float((a - b).abs().max()) for a, b in zip(reference_grad, actual_grad, strict=True)),
           "detached_past_relative_gradient_error": float(discrepancy / normal), "retained_targets": len(trace["output_ids"])})


def test_prefix_dependency_and_finite_difference_are_real(fixture):
    torch, model, trace = fixture
    from proworksim.functional_dense_v031 import reference_logprobs

    embedded = []
    handle = model.get_input_embeddings().register_forward_hook(lambda module, args, output: embedded.append(output))
    try:
        full = reference_logprobs(model, trace)
        gradient = torch.autograd.grad(-full[-1], embedded[-1])[0]
        assert float(gradient[:, :len(trace["input_ids"])].norm()) > 1e-7
        detached = reference_logprobs(model, trace, detach_past_negative_control=True)
        lost = torch.autograd.grad(-detached[-1], embedded[-1])[0]
        assert torch.count_nonzero(lost[:, :len(trace["input_ids"])]).item() == 0
    finally:
        handle.remove()
    name = "base_model.model.model.layers.0.self_attn.v_proj.lora_B.default.weight"
    parameter = dict(model.named_parameters())[name]
    probability = reference_logprobs(model, trace)
    derivative = torch.autograd.grad(-probability.mean(), parameter)[0]
    direction = derivative / derivative.norm()
    expected = float((derivative * direction).sum())
    saved = parameter.detach().clone()
    epsilon, losses = .005, []
    with torch.no_grad():
        for sign in (1, -1):
            parameter.copy_(saved + sign * epsilon * direction)
            losses.append(float(-reference_logprobs(model, trace).mean()))
        parameter.copy_(saved)
    numerical = (losses[0] - losses[1]) / (2 * epsilon)
    assert numerical == pytest.approx(expected, abs=1e-4, rel=.03)


def test_bf16_backbone_fp32_head_uses_original_cached_forward_shapes(fixture):
    torch, model, trace = fixture
    from proworksim.functional_dense_v031 import learning_logprobs, native_cache_logprobs

    for name, parameter in model.named_parameters():
        if "lora_" not in name and not name.endswith("lm_head.weight"):
            parameter.data = parameter.data.to(torch.bfloat16)
    with torch.no_grad():
        functional = learning_logprobs(model, trace)
    cached = native_cache_logprobs(model, trace)
    assert functional.dtype == torch.float32 and cached.dtype == torch.float32
    assert torch.equal(functional, cached)
    assert all(parameter.dtype == torch.float32 for name, parameter in model.named_parameters() if "lora_" in name)
    assert model.get_output_embeddings().weight.dtype == torch.float32


def test_modified_targets_and_sliding_attention_are_rejected(fixture):
    _, model, trace = fixture
    from proworksim.functional_dense_v031 import learning_logprobs

    cropped = copy.deepcopy(trace)
    cropped["output_ids"] = cropped["output_ids"][:-1]
    with pytest.raises(ValueError, match="original sampled target"):
        learning_logprobs(model, cropped)
    model.config.sliding_window = 64
    with pytest.raises(ValueError, match="sliding"):
        learning_logprobs(model, trace)
