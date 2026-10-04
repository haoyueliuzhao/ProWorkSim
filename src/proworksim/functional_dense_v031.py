"""Dense full-attention replay with the original prefill/one-token shapes.

The production path is a pure tensor layer scan with complete differentiable KV
state. No original sampled target, prefix state or gradient is detached/cropped.
The installed Qwen2/Mistral attention, LoRA, norm, MLP and FP32 output head remain
unchanged. This module neither samples tokens nor rewrites behavior probabilities.
"""
from __future__ import annotations

from functools import partial

VERSION = "functional-dense-state-v0.31"
DECODE_BLOCK = 8
CONTRACT = {"version": VERSION, "architectures": ["qwen2", "mistral"],
            "decode_checkpoint_block": DECODE_BLOCK,
            "outer_checkpoint": "one complete pure decoder-layer scan",
            "inner_checkpoint": "complete prefill, blocks of eight one-token transitions, each selected-token head",
            "use_reentrant": False, "past_state_detach": False, "prefix_truncation": False,
            "target_truncation": False, "dtype_change": False, "temperature_change": False,
            "sampling_path_changed": False,
            "capacity_scope": "Actual full-size GPU forward/backward must qualify; CPU graph controls do not establish 16K capacity."}
SUPPORTED_ATTENTION = frozenset({"sdpa", "dense_bf16_explicit_kv_v030"})


def _checkpoint(function, *args, enabled):
    import torch
    from torch.utils.checkpoint import checkpoint

    if enabled and torch.is_grad_enabled():
        return checkpoint(function, *args, use_reentrant=False, preserve_rng_state=True,
                          determinism_check="default")
    return function(*args)


def _structure(model):
    import torch

    network = model.get_base_model() if hasattr(model, "get_base_model") else model
    config = network.config
    if config.model_type not in CONTRACT["architectures"]:
        raise ValueError("Only the declared Qwen2/Mistral dense architectures are supported")
    if (getattr(config, "sliding_window", None) is not None
            or any(kind != "full_attention" for kind in getattr(config, "layer_types", []))
            or getattr(config, "use_sliding_window", False)):
        raise ValueError("Only unchanged full causal attention is admitted; no implicit sliding-window approximation")
    if config._attn_implementation not in SUPPORTED_ATTENTION:
        raise ValueError("The original SDPA causal-mask semantics must remain explicit")
    if config.attention_dropout != 0 or any(isinstance(module, torch.nn.Dropout) and module.p != 0 for module in model.modules()):
        raise ValueError("Deterministic replay requires the original zero dropout")
    if any(parameter.requires_grad and "lora_" not in name for name, parameter in model.named_parameters()):
        raise ValueError("Only the existing LoRA parameters may require gradients")
    if any(parameter.device != next(model.parameters()).device for parameter in model.parameters()):
        raise ValueError("Use the declared single-device model without offload")
    if torch.is_autocast_enabled("cuda") or torch.is_autocast_enabled("cpu"):
        raise ValueError("Ambient autocast cannot change the frozen numerical profile")
    if network.lm_head.weight.dtype != torch.float32:
        raise ValueError("Keep the original frozen FP32 output head")
    return network


def _validate_trace(trace):
    inputs, outputs = trace["input_ids"], trace["output_ids"]
    if (not inputs or not outputs or trace["sampling_temperature"] <= 0
            or any(type(value) is not int or value < 0 for value in inputs + outputs)):
        raise ValueError("All original nonempty integer input/output IDs and positive temperature are required")
    if "raw_output_ids" in trace and outputs != trace["raw_output_ids"]:
        raise ValueError("Every original sampled target, including EOS, must remain unchanged")
    if "output_mask" in trace and trace["output_mask"] != [1] * len(outputs):
        raise ValueError("Every original output target must retain its actor mask")
    return inputs, outputs


class _TransitionKV:
    """One local attention call: immutable tensor inputs and newly returned state.

    The container exists only inside one pure transition. It never survives a
    checkpoint call, so replay cannot append twice to mutable inference state.
    """
    def __init__(self, state, layer_index):
        self.state, self.layer_index, self.next_state = state, layer_index, None

    def update(self, key, value, layer_index, *args, **kwargs):
        import torch

        if layer_index != self.layer_index or args or kwargs or self.next_state is not None:
            raise ValueError("A dense transition updates its own KV tensors exactly once")
        previous = self.state if self.state is not None else (key.new_empty(0), value.new_empty(0))
        self.next_state = torch.cat([previous[0], key], dim=-2), torch.cat([previous[1], value], dim=-2)
        return self.next_state


def _transition(layer, hidden, state, cos, sin):
    residual = hidden
    cache = _TransitionKV(state, layer.self_attn.layer_idx)
    mixed, _ = layer.self_attn(layer.input_layernorm(hidden), position_embeddings=(cos, sin),
                              attention_mask=None, past_key_values=cache)
    if cache.next_state is None:
        raise ValueError("The original attention did not return its complete key/value state")
    hidden = residual + mixed
    hidden = hidden + layer.mlp(layer.post_attention_layernorm(hidden))
    return hidden, *cache.next_state


def _decode_block(layer, hidden, keys, values, cos, sin, *, test_detach=False):
    import torch

    state, outputs = (keys, values), []
    for index in range(hidden.shape[1]):
        if test_detach:
            # Explicit negative graph control, never enabled by learning_logprobs.
            state = tuple(value.detach() for value in state)
        value, *state = _transition(layer, hidden[:, index:index + 1], state,
                                    cos[:, index:index + 1], sin[:, index:index + 1])
        outputs.append(value)
    return torch.cat(outputs, dim=1), *state


def _layer_scan(layer, hidden, prefix_cos, prefix_sin, decode_cos, decode_sin,
                *, prefix_length, checkpointed, test_detach=False):
    import torch

    first, keys, values = _checkpoint(partial(_transition, layer), hidden[:, :prefix_length], None,
                                      prefix_cos, prefix_sin, enabled=checkpointed)
    outputs = [first]
    for start in range(prefix_length, hidden.shape[1], DECODE_BLOCK):
        end = min(start + DECODE_BLOCK, hidden.shape[1])
        offset, width = start - prefix_length, end - start
        block, keys, values = _checkpoint(partial(_decode_block, layer, test_detach=test_detach),
            hidden[:, start:end], keys, values, decode_cos[:, offset:offset + width],
            decode_sin[:, offset:offset + width], enabled=checkpointed)
        outputs.append(block)
    return torch.cat(outputs, dim=1)


def _forward(model, trace, *, checkpointed, test_detach=False):
    import torch

    network = _structure(model)
    prompt, output = _validate_trace(trace)
    backbone, device = network.model, next(model.parameters()).device
    # All outputs are prediction targets. The last target requires the previous
    # hidden state, so feeding that last label as an additional input is needless.
    # This is the same autoregressive dependency as generation; no target is lost.
    ids = torch.tensor([prompt + output[:-1]], dtype=torch.long, device=device)
    hidden = backbone.embed_tokens(ids)
    prefix = len(prompt)
    prefix_positions = torch.arange(prefix, device=device).unsqueeze(0)
    prefix_cos, prefix_sin = backbone.rotary_emb(hidden[:, :prefix], prefix_positions)
    positions = [backbone.rotary_emb(hidden[:, prefix + index:prefix + index + 1],
                 torch.tensor([[prefix + index]], dtype=torch.long, device=device))
                 for index in range(len(output) - 1)]
    if positions:
        decode_cos = torch.cat([value[0] for value in positions], dim=1)
        decode_sin = torch.cat([value[1] for value in positions], dim=1)
    else:
        decode_cos, decode_sin = prefix_cos[:, :0], prefix_sin[:, :0]
    for layer in backbone.layers:
        scan = partial(_layer_scan, layer, prefix_length=prefix, checkpointed=checkpointed, test_detach=test_detach)
        hidden = _checkpoint(scan, hidden, prefix_cos, prefix_sin, decode_cos, decode_sin, enabled=checkpointed)
    probabilities = []
    for index, token in enumerate(output):
        if index == 0:
            def head(value, *, target=token):
                normalized = backbone.norm(value)
                logits = network.lm_head(normalized[:, -1:]).float()[0, -1]
                return (logits / trace["sampling_temperature"]).log_softmax(-1)[target]
            value = hidden[:, :prefix]
        else:
            def head(value, *, target=token):
                logits = network.lm_head(backbone.norm(value)).float()[0, -1]
                return (logits / trace["sampling_temperature"]).log_softmax(-1)[target]
            value = hidden[:, prefix + index - 1:prefix + index]
        probabilities.append(_checkpoint(head, value, enabled=checkpointed))
    return torch.stack(probabilities)


def learning_logprobs(model, trace):
    """Production differentiable replay; original LoRA/prefix/output dependencies."""
    return _forward(model, trace, checkpointed=True)


def reference_logprobs(model, trace, *, detach_past_negative_control=False):
    """CPU complete-graph reference and explicit detached-past negative control."""
    return _forward(model, trace, checkpointed=False, test_detach=detach_past_negative_control)


def native_cache_logprobs(model, trace):
    """Independent installed cached teacher replay, diagnostic only and no-grad.

    The entire original prompt is followed by original target tokens, without
    generate(), multinomial(), re-tokenization, parser intervention or cropping.
    This reference does not certify a GPU differentiable path or 16K capacity.
    """
    import torch
    from transformers.cache_utils import DynamicCache

    generator = _structure(model)
    prompt, output = _validate_trace(trace)
    device = next(model.parameters()).device
    ids = torch.tensor([prompt], dtype=torch.long, device=device)
    kwargs = {"attention_mask": torch.ones_like(ids), "use_cache": True,
              "past_key_values": DynamicCache(config=generator.config), "logits_to_keep": 1}
    kwargs["position_ids"] = generator._prepare_position_ids_for_generation(ids, kwargs)
    probabilities, was_training = [], model.training
    model.eval()
    try:
        with torch.inference_mode(), generator._optimize_model_for_decode():
            for index, token in enumerate(output):
                prepared = model.prepare_inputs_for_generation(ids,
                    next_sequence_length=ids.shape[1] if index == 0 else 1,
                    is_first_iteration=index == 0, **kwargs)
                result = model(**prepared, return_dict=True)
                kwargs = generator._update_model_kwargs_for_generation(result, kwargs,
                    is_encoder_decoder=generator.config.is_encoder_decoder)
                logits = result.logits[:, -1].to(copy=True, dtype=torch.float32, device=device)[0]
                probabilities.append((logits / trace["sampling_temperature"]).log_softmax(-1)[token])
                ids = torch.cat([ids, ids.new_tensor([[token]])], dim=1)
                del result
            return torch.stack(probabilities)
    finally:
        model.train(was_training)
