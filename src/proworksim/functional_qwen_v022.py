"""One functional-state Qwen3.5 teacher learner with non-reentrant recomputation.

All prefix and decode-state tensors retain their autograd dependencies. The
checkpoint-free form is a small-model reference, not a second GPU candidate.
No installed model methods, inference cache or shared training code are patched.
"""

from functools import partial

VERSION = "functional-qwen-state-v0.22"
DECODE_BLOCK = 8
CONTRACT = {"version": VERSION, "decode_checkpoint_block": DECODE_BLOCK,
            "outer_checkpoint": "one full functional decoder-layer scan",
            "inner_checkpoint": "complete prefill; blocks of 8 one-token transitions; each selected-token head",
            "use_reentrant": False, "past_state_detach": False, "prefix_truncation": False,
            "target_truncation": False, "dtype_change": False}


def _checkpoint(function, *args, enabled):
    import torch
    from torch.utils.checkpoint import checkpoint

    if enabled and torch.is_grad_enabled():
        return checkpoint(function, *args, use_reentrant=False, preserve_rng_state=True,
                          determinism_check="default")
    return function(*args)


def _linear_mix(module, hidden, state):
    import torch
    from torch.nn import functional as F
    from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen

    batch, length, _ = hidden.shape
    mixed = module.in_proj_qkv(hidden).transpose(1, 2)
    z = module.in_proj_z(hidden).reshape(batch, length, -1, module.head_v_dim)
    b, a = module.in_proj_b(hidden), module.in_proj_a(hidden)
    if state is None:
        # Same values as the original prefill cache copy, but a new tensor/view
        # retaining the source graph rather than writing a persistent buffer.
        conv = F.pad(mixed, (max(module.conv_kernel_size - length, 0), 0))
        new_conv = conv[..., -module.conv_kernel_size:]
        mixed = qwen.causal_conv1d_fn(conv if length < module.conv_kernel_size else mixed,
                    module.conv1d.weight.squeeze(1), module.conv1d.bias, activation=module.activation)
        mixed = mixed[:, :, -length:]
        recurrent = None
    else:
        if length != 1:
            raise ValueError("Decode transition must process one original token")
        conv, recurrent = state
        joined = torch.cat([conv, mixed], dim=-1).to(module.conv1d.weight.dtype)
        new_conv = joined[..., -conv.shape[-1]:]
        updated = F.conv1d(joined, module.conv1d.weight, module.conv1d.bias,
                           padding=0, groups=joined.shape[1])[:, :, -length:]
        if module.activation is not None:
            updated = qwen.ACT2FN[module.activation](updated)
        mixed = updated.to(mixed.dtype)
    query, key, value = torch.split(mixed.transpose(1, 2),
        [module.key_dim, module.key_dim, module.value_dim], dim=-1)
    query = query.reshape(batch, length, -1, module.head_k_dim)
    key = key.reshape(batch, length, -1, module.head_k_dim)
    value = value.reshape(batch, length, -1, module.head_v_dim)
    beta = b.sigmoid()
    g = -module.A_log.float().exp() * F.softplus(a.float() + module.dt_bias)
    if module.num_v_heads // module.num_k_heads > 1:
        query = query.repeat_interleave(module.num_v_heads // module.num_k_heads, dim=2)
        key = key.repeat_interleave(module.num_v_heads // module.num_k_heads, dim=2)
    rule = qwen.torch_chunk_gated_delta_rule if state is None else qwen.torch_recurrent_gated_delta_rule
    result, new_recurrent = rule(query, key, value, g=g, beta=beta,
        initial_state=recurrent, output_final_state=True, use_qk_l2norm_in_kernel=True)
    result = module.norm(result.reshape(-1, module.head_v_dim), z.reshape(-1, module.head_v_dim))
    result = module.out_proj(result.reshape(batch, length, -1))
    return result, (new_conv, new_recurrent)


def _full_attention(module, hidden, state, position_embeddings):
    import torch
    from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen

    shape = hidden.shape[:-1]
    heads = (*shape, -1, module.head_dim)
    query, gate = torch.chunk(module.q_proj(hidden).view(*shape, -1, module.head_dim * 2), 2, dim=-1)
    gate = gate.reshape(*shape, -1)
    query = module.q_norm(query.view(heads)).transpose(1, 2)
    key = module.k_norm(module.k_proj(hidden).view(heads)).transpose(1, 2)
    value = module.v_proj(hidden).view(heads).transpose(1, 2)
    query, key = qwen.apply_rotary_pos_emb(query, key, *position_embeddings)
    if state is None:
        old_key = key.new_empty(0)
        old_value = value.new_empty(0)
    else:
        old_key, old_value = state
    keys, values = torch.cat([old_key, key], dim=-2), torch.cat([old_value, value], dim=-2)
    attention = qwen.ALL_ATTENTION_FUNCTIONS.get_interface(
        module.config._attn_implementation, qwen.eager_attention_forward)
    result, _ = attention(module, query, keys, values, None,
        dropout=0.0 if not module.training else module.attention_dropout, scaling=module.scaling)
    result = result.reshape(*shape, -1).contiguous() * torch.sigmoid(gate)
    return module.o_proj(result), (keys, values)


def _transition(layer, hidden, state, cos, sin):
    residual = hidden
    normalized = layer.input_layernorm(hidden)
    if layer.block_type == "linear_attention":
        mixed, next_state = _linear_mix(layer.linear_attn, normalized, state)
    elif layer.block_type == "full_attention":
        mixed, next_state = _full_attention(layer.self_attn, normalized, state, (cos, sin))
    else:
        raise ValueError("Unsupported block type; no alternative numerical path")
    hidden = residual + mixed
    hidden = hidden + layer.mlp(layer.post_attention_layernorm(hidden))
    return hidden, *next_state


def _decode_segment(layer, hidden, state_a, state_b, cos, sin, *, test_detach=False):
    import torch

    state, outputs = (state_a, state_b), []
    for i in range(hidden.shape[1]):
        if test_detach:
            # Deliberate negative control only. Never reached by learning_logprobs.
            state = tuple(value.detach() for value in state)
        output, *state = _transition(layer, hidden[:, i:i+1], state, cos[:, i:i+1], sin[:, i:i+1])
        outputs.append(output)
    return torch.cat(outputs, dim=1), *state


def _layer_scan(layer, hidden, prefix_cos, prefix_sin, decode_cos, decode_sin,
                *, prefix_length, checkpointed, test_detach=False):
    import torch

    initial = partial(_transition, layer)
    first, state_a, state_b = _checkpoint(initial, hidden[:, :prefix_length], None,
        prefix_cos, prefix_sin, enabled=checkpointed)
    outputs = [first]
    for start in range(prefix_length, hidden.shape[1], DECODE_BLOCK):
        end = min(start + DECODE_BLOCK, hidden.shape[1])
        offset = start - prefix_length
        scan = partial(_decode_segment, layer, test_detach=test_detach)
        block, state_a, state_b = _checkpoint(scan, hidden[:, start:end], state_a, state_b,
            decode_cos[:, offset:offset + end-start], decode_sin[:, offset:offset + end-start], enabled=checkpointed)
        outputs.append(block)
    return torch.cat(outputs, dim=1)


def _structure(model):
    import torch

    network = model.get_base_model() if hasattr(model, "get_base_model") else model
    if network.config.model_type != "qwen3_5_text":
        raise ValueError("Functional N1 requires the installed dense Qwen3.5 text architecture")
    if any(isinstance(module, torch.nn.Dropout) and module.p != 0 for module in model.modules()) or network.config.attention_dropout != 0:
        raise ValueError("Functional fixed-policy replay requires the original zero dropout")
    if any(p.requires_grad and "lora_" not in name for name, p in model.named_parameters()):
        raise ValueError("Only the original shared LoRA may require gradients")
    if any(p.device != next(model.parameters()).device for p in model.parameters()):
        raise ValueError("N1 is the declared single-device candidate; no offload or multi-device path")
    if torch.is_autocast_enabled("cuda") or torch.is_autocast_enabled("cpu"):
        raise ValueError("No ambient autocast or precision changes in N1")
    return network


def _forward(model, trace, *, checkpointed, test_detach=False):
    import torch

    network = _structure(model)
    backbone = network.model
    prompt, output = trace["input_ids"], trace["output_ids"]
    if not prompt or not output or trace["sampling_temperature"] <= 0:
        raise ValueError("All original input/output tokens and positive sampling temperature required")
    device = next(model.parameters()).device
    # Every output is a target. The final target needs no following prediction;
    # no output target is cropped or excluded from the objective.
    ids = torch.tensor([prompt + output[:-1]], dtype=torch.long, device=device)
    hidden = backbone.embed_tokens(ids)
    p = len(prompt)
    prefix_positions = torch.arange(p, device=device)[None, None].expand(3, 1, -1)
    prefix_cos, prefix_sin = backbone.rotary_emb(hidden[:, :p], prefix_positions)
    decoded_positions = []
    for i in range(len(output) - 1):
        position = torch.full((3, 1, 1), p + i, dtype=torch.long, device=device)
        decoded_positions.append(backbone.rotary_emb(hidden[:, p+i:p+i+1], position))
    if decoded_positions:
        decode_cos = torch.cat([value[0] for value in decoded_positions], dim=1)
        decode_sin = torch.cat([value[1] for value in decoded_positions], dim=1)
    else:
        decode_cos, decode_sin = prefix_cos[:, :0], prefix_sin[:, :0]
    for layer in backbone.layers:
        scan = partial(_layer_scan, layer, prefix_length=p, checkpointed=checkpointed, test_detach=test_detach)
        hidden = _checkpoint(scan, hidden, prefix_cos, prefix_sin, decode_cos, decode_sin, enabled=checkpointed)
    probabilities = []
    for position, token in enumerate(output):
        # Bind the token value now: deferred checkpoint recomputation must not
        # read a loop variable subsequently changed by another target.
        def head_target(value, *, target=token):
            normalized = backbone.norm(value)
            logits = network.lm_head(normalized).float()[0, -1]
            return (logits / trace["sampling_temperature"]).log_softmax(-1)[target]
        # Original generation computes norm on the full prefill, but projects
        # only the final position. Later steps each consume one hidden vector.
        if position == 0:
            def first_target(value, *, target=token):
                normalized = backbone.norm(value)
                logits = network.lm_head(normalized[:, -1:]).float()[0, -1]
                return (logits / trace["sampling_temperature"]).log_softmax(-1)[target]
            probability = _checkpoint(first_target, hidden[:, :p], enabled=checkpointed)
        else:
            probability = _checkpoint(head_target, hidden[:, p + position - 1:p + position], enabled=checkpointed)
        probabilities.append(probability)
    return torch.stack(probabilities)


def learning_logprobs(model, trace):
    """The sole production candidate, keeping all original target dependencies."""
    return _forward(model, trace, checkpointed=True)


def reference_logprobs(model, trace, *, detach_past_negative_control=False):
    """Uncheckpointed complete graph / explicit bad-gradient control for CPU tests."""
    return _forward(model, trace, checkpointed=False, test_detach=detach_past_negative_control)
