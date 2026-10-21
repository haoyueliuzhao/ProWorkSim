"""Inference-only FP32 T=1 gated-delta update; no FLA or external kernels.

The fixed Qwen3.5-9B shape is H=32, K=V=128. Other shapes use the
unmodified Transformers reference. Initial state is never modified.
"""
from functools import wraps
import inspect
from pathlib import Path

import torch
import triton
import triton.language as tl


@triton.jit
def _step(Q, K, V, G, BETA, INITIAL, OUT, FINAL,
          QB: tl.constexpr, QH: tl.constexpr, QD: tl.constexpr,
          KB: tl.constexpr, KH: tl.constexpr, KD: tl.constexpr,
          VB: tl.constexpr, VH: tl.constexpr, VD: tl.constexpr,
          GB: tl.constexpr, GH: tl.constexpr,
          BB: tl.constexpr, BH: tl.constexpr,
          SB: tl.constexpr, SH: tl.constexpr, SK: tl.constexpr, SV: tl.constexpr,
          NORMALIZE: tl.constexpr, HAS_INITIAL: tl.constexpr):
    head = tl.program_id(0)
    batch = tl.program_id(1)
    rows = tl.arange(0, 128)
    cols = tl.arange(0, 128)
    q = tl.load(Q + batch * QB + head * QH + rows * QD).to(tl.float32)
    k = tl.load(K + batch * KB + head * KH + rows * KD).to(tl.float32)
    v = tl.load(V + batch * VB + head * VH + cols * VD).to(tl.float32)
    if NORMALIZE:
        q = q * tl.rsqrt(tl.sum(q * q, 0) + 1.0e-6)
        k = k * tl.rsqrt(tl.sum(k * k, 0) + 1.0e-6)
    # Match the reference's q / sqrt(K), keeping all arithmetic FP32.
    q = tl.div_rn(q, 11.313708498984761)
    if HAS_INITIAL:
        state = tl.load(INITIAL + batch * SB + head * SH
                        + rows[:, None] * SK + cols[None, :] * SV).to(tl.float32)
    else:
        state = tl.full((128, 128), 0.0, tl.float32)
    g = tl.load(G + batch * GB + head * GH).to(tl.float32)
    beta = tl.load(BETA + batch * BB + head * BH).to(tl.float32)
    state = state * tl.exp(g)
    memory = tl.sum(state * k[:, None], axis=0)
    delta = (v - memory) * beta
    state = state + k[:, None] * delta[None, :]
    output = tl.sum(state * q[:, None], axis=0)
    tl.store(OUT + (batch * 32 + head) * 128 + cols, output)
    tl.store(FINAL + (batch * 32 + head) * 16384
             + rows[:, None] * 128 + cols[None, :], state)


def _recurrent_fp32(query, key, value, g, beta, initial_state=None,
                    output_final_state=False, use_qk_l2norm_in_kernel=False, **kwargs):
    """Execute the admitted single-token shape; caller handles reference fallback."""
    tensors = (query, key, value, g, beta)
    if any(t.device != query.device or not t.is_cuda for t in tensors):
        raise ValueError("All recurrent inputs must share one CUDA device")
    if torch.is_grad_enabled() and any(t.requires_grad for t in tensors):
        raise ValueError("This kernel is inference-only")
    batch = query.shape[0]
    if initial_state is not None:
        if (initial_state.shape != (batch, 32, 128, 128)
                or initial_state.device != query.device):
            raise ValueError("Invalid recurrent initial state shape/device")
        if torch.is_grad_enabled() and initial_state.requires_grad:
            raise ValueError("This kernel is inference-only")
        strides = initial_state.stride()
    else:
        strides = (0, 0, 0, 0)
    out = torch.empty((batch, 1, 32, 128), device=query.device, dtype=query.dtype)
    state = torch.empty((batch, 32, 128, 128), device=query.device, dtype=torch.float32)
    _step[(32, batch)](query, key, value, g, beta,
        initial_state if initial_state is not None else state, out, state,
        query.stride(0), query.stride(2), query.stride(3),
        key.stride(0), key.stride(2), key.stride(3),
        value.stride(0), value.stride(2), value.stride(3),
        g.stride(0), g.stride(2), beta.stride(0), beta.stride(2),
        *strides, NORMALIZE=bool(use_qk_l2norm_in_kernel), HAS_INITIAL=initial_state is not None,
        num_warps=8, num_stages=1, enable_fp_fusion=False)
    return out, state if output_final_state else None


def _selected_implementation(symbol):
    node = symbol
    seen = set()
    while callable(node) and id(node) not in seen:
        seen.add(id(node))
        if inspect.isfunction(node):
            values = inspect.getclosurevars(node).nonlocals
            if "implementation" in values and "is_new_implementation" in values:
                return values
        node = getattr(node, "__wrapped__", None)
    raise ValueError("Cannot establish reference-only callable provenance")


def install():
    """Install exactly once before constructing a model; leave three references intact."""
    from transformers.models.qwen3_5 import modeling_qwen3_5 as module
    for name in ("causal_conv1d_fn", "causal_conv1d_update", "torch_chunk_gated_delta_rule"):
        selected = _selected_implementation(getattr(module, name))
        if selected["is_new_implementation"] is not False:
            raise ValueError("A non-recurrent optimized implementation is already selected: " + name)
    symbol = module.torch_recurrent_gated_delta_rule
    if _selected_implementation(symbol)["is_new_implementation"] is not False:
        raise ValueError("Recurrent implementation was already replaced")
    original = inspect.unwrap(symbol)
    if original.__module__ != module.__name__:
        raise ValueError("Original recurrent reference has unexpected provenance")
    implementation, is_new_implementation = _recurrent_fp32, True

    @wraps(original)
    def wrapped(query, key, value, g, beta, initial_state=None, output_final_state=False,
                use_qk_l2norm_in_kernel=False, **kwargs):
        applicable = (query.ndim == key.ndim == value.ndim == 4
            and query.shape == key.shape == value.shape
            and query.shape[1:] == (1, 32, 128)
            and g.shape == beta.shape == query.shape[:3]
            and query.is_cuda and query.dtype in (torch.bfloat16, torch.float32, torch.float16))
        if not applicable:
            return original(query, key, value, g, beta, initial_state,
                            output_final_state, use_qk_l2norm_in_kernel, **kwargs)
        if not is_new_implementation:
            raise AssertionError("Frozen implementation unexpectedly disabled")
        return implementation(query, key, value, g, beta, initial_state,
                              output_final_state, use_qk_l2norm_in_kernel, **kwargs)

    module.torch_recurrent_gated_delta_rule = wrapped
    return {"version": "v054-fp32-recurrent-r1", "symbol": "torch_recurrent_gated_delta_rule",
            "source": str(Path(__file__).resolve()), "original_source": inspect.getsourcefile(original),
            "implementation": "_recurrent_fp32", "num_warps": 8, "num_stages": 1,
            "enable_fp_fusion": False, "autotune": False, "other_three_reference": True}
