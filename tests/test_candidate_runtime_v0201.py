"""Random CPU tensors only; no candidate load or GPU capacity claim."""

from types import SimpleNamespace

import pytest


@pytest.fixture
def runtime():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("peft")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Installed official Transformers interface control")
    old = torch.get_num_threads(), torch.get_float32_matmul_precision(), torch.backends.cudnn.allow_tf32
    torch.set_num_threads(1)
    yield torch
    torch.set_num_threads(old[0])
    torch.set_float32_matmul_precision(old[1])
    torch.backends.cudnn.allow_tf32 = old[2]


def test_official_tiny_constructor_upcasts_only_head_and_records_real_forward(runtime, tmp_path):
    torch = runtime
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig
    from peft import LoraConfig, get_peft_model
    from proworksim.candidate_runtime_v0201 import CandidateActor, candidate_profile
    from proworksim.candidate_runtime_v0151 import candidate_profile as loader_profile

    config = Qwen3_5TextConfig(vocab_size=128, hidden_size=64, intermediate_size=128,
        num_hidden_layers=4, num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        linear_key_head_dim=16, linear_value_head_dim=16, linear_num_key_heads=2,
        linear_num_value_heads=2, layer_types=["linear_attention"] * 3 + ["full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
            "partial_rotary_factor": .5, "mrope_section": [1, 1, 2], "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=127, tie_word_embeddings=False)
    network = get_peft_model(Qwen3_5ForCausalLM(config).bfloat16(), LoraConfig(r=8,
        lora_alpha=16, lora_dropout=0, target_modules=["q_proj", "v_proj"],
        bias="none", task_type="CAUSAL_LM"))
    head = network.get_output_embeddings()
    original = head.weight.detach().float().clone()
    owner = CandidateActor(network, object(), output=tmp_path / "tiny-constructor",
        device="cpu", torch_module=torch, recipe={"max_length": 16384, "max_output_tokens": 2048},
        base_identity={"manifest": {"sha256": "random-cpu"}},
        inference_profile=loader_profile("qwen3.5-9b", dtype="bfloat16"))
    expected = candidate_profile("qwen3.5-9b")
    assert all(owner.inference_profile[k] == v for k, v in expected.items())
    assert torch.equal(original, head.weight) and head.weight.dtype == torch.float32
    assert network.get_input_embeddings().weight.dtype == torch.bfloat16
    storage = owner.inference_profile["actual_parameter_storage"]
    assert storage["counts"]["lm_head"] == {"tensors": 1, "elements": 8192, "bytes": 32768}
    assert storage["lm_head"]["buffers"] == []
    assert all(p.dtype == torch.float32 for p in owner.actor_parameters.values())
    # Only the head executes; official hybrid backbone never forwards on CPU.
    inputs = torch.randn(1, 3, 64).bfloat16().requires_grad_()
    result = head(inputs)
    assert result.dtype == torch.float32
    assert torch.equal(result, torch.nn.functional.linear(inputs.float(), original))
    result.mean().backward()
    assert inputs.grad is not None and head.weight.grad is None
    record = owner.execution_diagnostics()["lm_head_execution"]
    assert record["completed_forward_calls"] == 1
    assert record["source_input_dtypes"] == ["torch.bfloat16"]
    assert record["compute_input_dtypes"] == record["output_dtypes"] == ["torch.float32"]
    owner.head_execution.before_handle.remove()
    with pytest.raises(ValueError, match="contract was removed"):
        owner._verify_execution()


def test_tiny_peft_actual_sampling_full_replay_and_gradients(runtime, tmp_path):
    torch = runtime
    from transformers import PretrainedConfig
    from peft import LoraConfig, get_peft_model
    from proworksim.candidate_runtime_v0201 import CandidateActor, candidate_profile
    from proworksim.local_model_service import SamplingTrace
    from proworksim.online_training import probability_check

    class Tiny(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.config = PretrainedConfig(attention_dropout=0, tie_word_embeddings=False)
            self.embed = torch.nn.Embedding(8, 8, dtype=torch.bfloat16)
            self.q_proj = torch.nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
            self.v_proj = torch.nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
            self.lm_head = torch.nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
            self.generation_config = SimpleNamespace(eos_token_id=99)
        def get_output_embeddings(self): return self.lm_head
        def get_input_embeddings(self): return self.embed
        def set_attn_implementation(self, value): self.config._attn_implementation = value
        def gradient_checkpointing_enable(self, **kwargs): pass
        def forward(self, input_ids, logits_to_keep=0, **kwargs):
            hidden = self.q_proj(self.embed(input_ids)) + self.v_proj(self.embed(input_ids))
            logits = self.lm_head(hidden)
            return SimpleNamespace(logits=logits[:, -logits_to_keep:] if logits_to_keep else logits)
        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            result = input_ids
            for _ in range(max_new_tokens):
                scores = logits_processor[0](result, self(result).logits[:, -1])
                result = torch.cat([result, torch.multinomial(scores.softmax(-1), 1)], 1)
            return result

    torch.manual_seed(30)
    network = get_peft_model(Tiny(), LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
                            target_modules=["q_proj", "v_proj"], bias="none"))
    owner = CandidateActor(network, object(), output=tmp_path / "tiny-probabilities",
        device="cpu", torch_module=torch, recipe={"max_length": 16384, "max_output_tokens": 2048},
        base_identity={"manifest": {"sha256": "random-cpu"}},
        inference_profile=candidate_profile("qwen3.5-9b"))
    inputs = torch.tensor([[1, 2, 3]])
    sampler = SamplingTrace(.7)
    with torch.inference_mode():
        generated, metadata = owner._generate_tokens(inputs, sampler, {"max_new_tokens": 5})
    behavior = sampler.finish(generated)[0]
    trace = {"input_ids": inputs[0].tolist(), "output_ids": generated[0, 3:].tolist(),
             "sampling_temperature": .7}
    current = owner.learning_logprobs(trace)
    assert current.dtype == torch.float32
    assert probability_check(current.detach().tolist(), behavior, owner.recipe)["passed"]
    assert metadata["version"] == "candidate-runtime-v0.20.1"
    assert metadata["lm_head_execution"]["calls_in_this_generation"] == 5
    (-current.mean()).backward()
    gradients = [p.grad for p in owner.actor_parameters.values() if p.grad is not None]
    assert gradients and all(g.dtype == torch.float32 and torch.isfinite(g).all() for g in gradients)
    assert sum(int(torch.count_nonzero(g)) for g in gradients) > 0
    assert owner.actor_steps == owner.critic_steps == 0 and owner.actor_optimizer.state == {}
    assert network.get_output_embeddings().weight.grad is None
    network.config.tie_word_embeddings = True
    with pytest.raises(ValueError, match="untied frozen"):
        owner._verify_execution()
