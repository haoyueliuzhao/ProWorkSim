"""CPU controls for the real installed hybrid cache; no candidate/GPU speed claim."""

import pytest

from proworksim.prefix_cache_v019 import ExactPrefixCache


def identity(version="v0"):
    return {"policy_version": version, "adapter_sha256": version,
            "base_manifest_sha256": "base", "inference_profile_sha256": "profile"}


def test_profile_is_bounded_and_metadata_contains_no_prompt_content():
    for length in (0, 255, 1024, True):
        with pytest.raises(ValueError, match="declared prefix length"):
            ExactPrefixCache(prefix_tokens=length)
    with pytest.raises(ValueError, match="eight"):
        ExactPrefixCache(max_entries=9)
    with pytest.raises(ValueError, match="precision"):
        ExactPrefixCache(matmul_precision="medium")
    cache = ExactPrefixCache()
    assert cache.snapshot()["entries"] == []
    assert cache.clear()["removed_entries"] == 0


@pytest.fixture
def tiny():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Installed official Transformers 5.17.0 control")
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig

    old_threads, old_precision = torch.get_num_threads(), torch.get_float32_matmul_precision()
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    torch.manual_seed(109)
    config = Qwen3_5TextConfig(
        vocab_size=128, hidden_size=64, intermediate_size=128, num_hidden_layers=4,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        linear_key_head_dim=16, linear_value_head_dim=16,
        linear_num_key_heads=2, linear_num_value_heads=2,
        layer_types=["linear_attention"] * 3 + ["full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
                         "partial_rotary_factor": 0.5, "mrope_section": [1, 1, 2],
                         "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=127,
    )
    config._attn_implementation = "sdpa"
    with torch.device("cpu"):
        model = Qwen3_5ForCausalLM(config).float().eval()
    ids = ((torch.arange(273, device="cpu") * 11 + 9) % 125 + 1)[None, :]
    yield torch, model, ids
    torch.set_num_threads(old_threads)
    torch.set_float32_matmul_precision(old_precision)


def test_real_hybrid_generate_keeps_full_prompt_and_original_sampling_trace(tiny):
    torch, model, ids = tiny
    from proworksim.local_model_service import SamplingTrace
    from proworksim.online_training import selected_logprobs

    mask = torch.ones_like(ids)
    cache = ExactPrefixCache(prefix_tokens=256)
    rng = torch.get_rng_state().clone()
    kwargs, cold = cache.prepare(model, ids, mask, identity())
    assert torch.equal(rng, torch.get_rng_state())
    assert kwargs["input_ids"] is ids and kwargs["attention_mask"] is mask
    assert cold["suffix_tokens"] == 17 and not cold["hit"]
    assert kwargs["past_key_values"].get_seq_length() == 256
    # Official hybrid states are present, including non-croppable recurrent state.
    assert kwargs["past_key_values"].layers[0].recurrent_states[0] is not None
    assert not kwargs["past_key_values"].layers[0].is_croppable

    def generate(parameters):
        trace = SamplingTrace(0.7)
        torch.manual_seed(810)
        with torch.inference_mode():
            output = model.generate(
                **parameters, use_cache=True, max_new_tokens=6,
                do_sample=True, temperature=1.0, top_p=1.0, top_k=0,
                logits_processor=[trace], pad_token_id=0, eos_token_id=127,
            )
        return output, trace.finish(output)[0]

    original, original_logp = generate({"input_ids": ids, "attention_mask": mask})
    lengths = []
    handle = model.register_forward_pre_hook(
        lambda module, args, kwargs: lengths.append(kwargs["input_ids"].shape[1]),
        with_kwargs=True,
    )
    cached, cached_logp = generate(kwargs)
    handle.remove()
    assert lengths[0] == 17  # The official generate path consumes only the exact suffix.
    assert torch.equal(cached, original) and torch.equal(cached[:, :ids.shape[1]], ids)
    assert max(abs(a - b) for a, b in zip(cached_logp, original_logp)) < 1e-5
    # Training still receives the full original input, not suffix-only token IDs.
    trace = {"input_ids": ids[0].tolist(), "output_ids": cached[0, ids.shape[1]:].tolist(),
             "sampling_temperature": 0.7}
    with torch.inference_mode():
        recomputed = selected_logprobs(model, trace, torch, "cpu").tolist()
    assert max(abs(a - b) for a, b in zip(cached_logp, recomputed)) < 1e-5
    restored, warm = cache.prepare(model, ids, mask, identity())
    assert warm["hit"] and restored["past_key_values"].get_seq_length() == 256
    assert kwargs["past_key_values"].get_seq_length() > 256
    warm_output, warm_logp = generate(restored)
    assert torch.equal(cached, warm_output) and cached_logp == warm_logp


def test_prefix_match_clone_isolation_lru_and_actor_invalidation(tiny):
    torch, model, ids = tiny
    cache = ExactPrefixCache(prefix_tokens=256, max_entries=2)
    first, _ = cache.prepare(model, ids, torch.ones_like(ids), identity())
    state = first["past_key_values"].layers[0].recurrent_states[0]
    with torch.inference_mode():
        state.add_(7)  # A mutated per-request clone must not poison future requests.
    suffix_changed = ids.clone()
    suffix_changed[0, -1] = 77
    second, hit = cache.prepare(model, suffix_changed, torch.ones_like(ids), identity())
    assert hit["hit"]
    assert not torch.equal(state, second["past_key_values"].layers[0].recurrent_states[0])
    for value in (78, 79):
        different = ids.clone()
        different[0, 0] = value
        _, miss = cache.prepare(model, different, torch.ones_like(ids), identity())
        assert not miss["hit"]
    assert len(cache.snapshot()["entries"]) == 2
    _, evicted = cache.prepare(model, ids, torch.ones_like(ids), identity())
    assert not evicted["hit"]
    _, changed = cache.prepare(model, ids, torch.ones_like(ids), identity("v1"))
    assert not changed["hit"] and changed["invalidation"]["removed_entries"] == 2
    assert len(cache.snapshot()["entries"]) == 1
    short = ids[:, :256]
    skipped, record = cache.prepare(model, short, torch.ones_like(short), identity("v1"))
    assert "past_key_values" not in skipped and record["status"] == "skipped_short_prompt"
    bad_mask = torch.ones_like(ids)
    bad_mask[0, 0] = 0
    with pytest.raises(ValueError, match="unpadded"):
        cache.prepare(model, ids, bad_mask, identity("v1"))
    model.train()
    with pytest.raises(ValueError, match="FP32 eval"):
        cache.prepare(model, ids, torch.ones_like(ids), identity("v1"))
