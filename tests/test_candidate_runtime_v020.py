"""CPU fixtures only: storage/normalization, not candidate capacity or admission."""

from types import SimpleNamespace

import pytest

from proworksim.candidate_runtime_v020 import ATTENTION, CandidateActor, candidate_profile


def recipe():
    return {"max_length": 16384, "max_output_tokens": 2048}


@pytest.fixture
def torch_runtime():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    pytest.importorskip("peft")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Official installed v5.17.0 interface control")
    state = (torch.get_num_threads(), torch.get_float32_matmul_precision(),
             torch.backends.cudnn.allow_tf32)
    torch.set_num_threads(1)
    yield torch
    torch.set_num_threads(state[0])
    torch.set_float32_matmul_precision(state[1])
    torch.backends.cudnn.allow_tf32 = state[2]


def test_profile_is_one_resident_without_prefix_and_preserves_old_probability_gate():
    profile = candidate_profile("qwen3.5-9b")
    assert profile["dtype"] == profile["base_storage_dtype"] == "bfloat16"
    assert profile["adapter_storage_dtype"] == profile["normalization_dtype"] == "float32"
    assert profile["sampling"] == {"resident_instances": 1, "replicas": 0,
                                   "role_scheduling": "sequential"}
    assert profile["prefix_cache"] == {"enabled": False}
    assert profile["probability_gate"] == {"logprob_max_atol": .02, "logprob_mean_atol": .002}
    with pytest.raises(ValueError, match="actual BF16"):
        candidate_profile("qwen3.5-9b", dtype="float32")
    modified = {**profile, "adapter_storage_dtype": "bfloat16"}
    with pytest.raises(ValueError, match="Undeclared"):
        CandidateActor.from_candidate("never-read", manifest="never-read", profile=modified,
                                      output="never-created", recipe=recipe())


def test_actual_tiny_official_load_storage_and_constructor_no_forward(torch_runtime, tmp_path):
    torch = torch_runtime
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig
    from peft import LoraConfig, get_peft_model
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS
    from proworksim.candidate_runtime_v020 import bf16_attention_forward, inspect_parameter_storage
    from proworksim.candidate_runtime_v0151 import candidate_profile as numeric_profile

    config = Qwen3_5TextConfig(
        vocab_size=128, hidden_size=64, intermediate_size=128, num_hidden_layers=4,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        linear_key_head_dim=16, linear_value_head_dim=16,
        linear_num_key_heads=2, linear_num_value_heads=2,
        layer_types=["linear_attention"] * 3 + ["full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
                         "partial_rotary_factor": .5, "mrope_section": [1, 1, 2],
                         "mrope_interleaved": True}, pad_token_id=0, eos_token_id=127,
    )
    original = Qwen3_5ForCausalLM(config).float()
    original.save_pretrained(tmp_path / "random-tiny-base")
    # Same official dtype load API as production; random local tiny weights only.
    base = Qwen3_5ForCausalLM.from_pretrained(
        tmp_path / "random-tiny-base", dtype=torch.bfloat16, local_files_only=True,
        attn_implementation="sdpa", use_kernels=False,
    )
    network = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
                            target_modules=["q_proj", "v_proj"], bias="none",
                            task_type="CAUSAL_LM"))
    storage = inspect_parameter_storage(network, torch)
    assert storage["counts"]["base"]["bytes"] == 2 * storage["counts"]["base"]["elements"]
    assert storage["counts"]["adapter"]["bytes"] == 4 * storage["counts"]["adapter"]["elements"]
    owner = CandidateActor(
        network, object(), output=tmp_path / "owner", device="cpu", torch_module=torch,
        recipe=recipe(), base_identity={"manifest": {"sha256": "random-cpu-tiny"}},
        inference_profile=numeric_profile("qwen3.5-9b", dtype="bfloat16"),
    )
    expected = candidate_profile("qwen3.5-9b")
    assert all(owner.inference_profile.get(k) == v for k, v in expected.items())
    assert owner.inference_profile["actual_parameter_storage"] == storage
    assert all(p.dtype == torch.float32 for p in owner.critic.parameters())
    assert ALL_ATTENTION_FUNCTIONS[ATTENTION] is bf16_attention_forward
    assert ALL_MASK_ATTENTION_FUNCTIONS[ATTENTION] is ALL_MASK_ATTENTION_FUNCTIONS["sdpa"]
    assert base.model.layers[-1].self_attn.config._attn_implementation == ATTENTION
    assert not hasattr(owner, "prefix_cache")
    assert all(p.device.type == "cpu" for p in network.parameters())
    with pytest.raises(ValueError, match="replica"):
        owner.export_sampling_snapshot(tmp_path / "forbidden")
    # Strict wrapper rejects wrong precision before any backend invocation.
    q = torch.zeros(1, 4, 2, 16)
    with pytest.raises(ValueError, match="actually be BF16"):
        bf16_attention_forward(SimpleNamespace(), q, q, q, None)
    with pytest.raises(ValueError, match="requires CUDA"):
        bf16_attention_forward(SimpleNamespace(), q.bfloat16(), q.bfloat16(), q.bfloat16(), None)
    # No silent conversion when a caller provides a different actual base dtype.
    first_base = next(p for n, p in network.named_parameters() if "lora_" not in n)
    first_base.data = first_base.data.float()
    with pytest.raises(ValueError, match="storage/trainability"):
        inspect_parameter_storage(network, torch)


def test_real_peft_cpu_sampling_replay_and_backward_have_explicit_dtypes(torch_runtime, tmp_path):
    torch = torch_runtime
    from peft import LoraConfig, get_peft_model
    from transformers import PretrainedConfig
    from proworksim.local_model_service import SamplingTrace
    from proworksim.online_training import probability_check

    class Tiny(torch.nn.Module):
        """Token-local LM fixture; no attention/backend/candidate claim."""
        def __init__(self):
            super().__init__()
            self.config = PretrainedConfig(attention_dropout=0, use_cache=False)
            self.embed = torch.nn.Embedding(8, 8, dtype=torch.bfloat16)
            self.q_proj = torch.nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
            self.v_proj = torch.nn.Linear(8, 8, bias=False, dtype=torch.bfloat16)
            self.generation_config = SimpleNamespace(eos_token_id=99)

        def set_attn_implementation(self, value):
            self.config._attn_implementation = value  # No attention layer in this fixture.

        def gradient_checkpointing_enable(self, **kwargs):
            self.checkpoint_options = kwargs

        def forward(self, input_ids, logits_to_keep=0, **kwargs):
            logits = self.q_proj(self.embed(input_ids)) + self.v_proj(self.embed(input_ids))
            return SimpleNamespace(logits=logits[:, -logits_to_keep:] if logits_to_keep else logits)

        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            result = input_ids
            for _ in range(max_new_tokens):
                scores = self(result).logits[:, -1]
                assert scores.dtype == torch.bfloat16
                scores = logits_processor[0](result, scores)
                assert scores.dtype == torch.float32
                result = torch.cat([result, torch.multinomial(scores.softmax(-1), 1)], 1)
            return result

    torch.manual_seed(30)
    model = get_peft_model(Tiny(), LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
                                            target_modules=["q_proj", "v_proj"], bias="none"))
    owner = CandidateActor(model, object(), output=tmp_path / "tiny-owner", recipe=recipe(),
        device="cpu", torch_module=torch, base_identity={"manifest": {"sha256": "fixture"}},
        inference_profile=candidate_profile("qwen3.5-9b"))
    inputs = torch.tensor([[1, 2, 3]])
    sampling = SamplingTrace(.7)
    with torch.inference_mode():
        generated, metadata = owner._generate_tokens(inputs, sampling, {"max_new_tokens": 5})
    behavior = sampling.finish(generated)[0]
    trace = {"input_ids": inputs[0].tolist(), "output_ids": generated[0, 3:].tolist(),
             "sampling_temperature": .7}
    current = owner.learning_logprobs(trace)
    assert current.dtype == torch.float32
    assert probability_check(current.detach().tolist(), behavior, owner.recipe)["passed"]
    assert metadata["sampler_input_score_dtypes"] == ["torch.bfloat16"]
    assert metadata["normalization_calls"] == len(trace["output_ids"]) == 5
    (-current.mean()).backward()
    gradients = [p.grad for p in owner.actor_parameters.values() if p.grad is not None]
    assert gradients and all(g.dtype == torch.float32 and torch.isfinite(g).all() for g in gradients)
    assert sum(int(torch.count_nonzero(g)) for g in gradients) > 0
    assert all(p.grad is None for n, p in model.named_parameters() if "lora_" not in n)
    assert owner.actor_steps == owner.critic_steps == 0
    assert owner.actor_optimizer.state == {}  # No optimizer step in this diagnostic.
    with torch.autocast("cpu", dtype=torch.bfloat16):
        with pytest.raises(ValueError, match="ambient autocast"):
            owner.learning_logprobs(trace)
