"""Offline profile/dispatch contracts; the GPU microprobe is separate evidence."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from proworksim.local_model_service import (
    configure_attention_runtime,
    sdpa_explicit_kv_attention_forward,
    service_parser,
)
from proworksim.storage import digest, json_bytes


def test_efficient_candidate_and_matmul_precision_are_explicit_cli_choices():
    parser = service_parser()
    common = ["--model", "/readonly", "--revision", "base", "--output", "/new"]
    defaults = parser.parse_args(common)
    assert defaults.attention == "sdpa" and defaults.matmul_precision == "highest"
    selected = parser.parse_args(
        common + ["--attention", "sdpa_explicit_kv", "--matmul-precision", "high"]
    )
    assert selected.attention == "sdpa_explicit_kv" and selected.matmul_precision == "high"
    with pytest.raises(SystemExit):
        parser.parse_args(common + ["--matmul-precision", "medium"])


def test_explicit_kv_dispatch_keeps_group_values_and_uses_only_efficient_backend():
    torch = pytest.importorskip("torch")

    # CPU data with explicitly simulated CUDA dispatch metadata. No GPU tensor.
    class SimulatedCUDA:
        def __init__(self, value):
            self.value = value
            self.device = SimpleNamespace(type="cuda")

        @property
        def shape(self):
            return self.value.shape

        def repeat_interleave(self, count, dim):
            return SimulatedCUDA(self.value.repeat_interleave(count, dim=dim))

    q = SimulatedCUDA(torch.zeros(1, 28, 2, 128))
    k = SimulatedCUDA(torch.arange(4 * 2 * 128).reshape(1, 4, 2, 128).float())
    v = SimulatedCUDA(k.value + 1)
    module = SimpleNamespace(num_key_value_groups=7, is_causal=True)
    seen = {}

    @contextmanager
    def only_efficient(backends):
        seen["backends"] = backends
        yield

    def actual_dispatch(query, key, value, **kwargs):
        seen.update(key=key.value.clone(), value=value.value.clone(), kwargs=kwargs)
        return torch.zeros_like(query.value)

    with (
        patch("torch.nn.attention.sdpa_kernel", only_efficient),
        patch("torch.nn.functional.scaled_dot_product_attention", actual_dispatch),
    ):
        result, weights = sdpa_explicit_kv_attention_forward(module, q, k, v, None, scaling=0.125)
    assert seen["backends"] == [torch.nn.attention.SDPBackend.EFFICIENT_ATTENTION]
    assert torch.equal(seen["key"], k.value.repeat_interleave(7, dim=1))
    assert torch.equal(seen["value"], v.value.repeat_interleave(7, dim=1))
    assert k.shape[1] == v.shape[1] == 4  # No cache or parameter layout mutation.
    assert seen["kwargs"]["enable_gqa"] is False and seen["kwargs"]["is_causal"] is True
    assert seen["kwargs"]["scale"] == 0.125 and seen["kwargs"]["dropout_p"] == 0
    assert tuple(result.shape) == (1, 2, 28, 128) and weights is None
    mask = torch.ones(1, 1, 2, 5, dtype=torch.bool)
    with (
        patch("torch.nn.attention.sdpa_kernel", only_efficient),
        patch("torch.nn.functional.scaled_dot_product_attention", actual_dispatch),
    ):
        sdpa_explicit_kv_attention_forward(module, q, k, v, mask)
    assert seen["kwargs"]["is_causal"] is False
    assert tuple(seen["kwargs"]["attn_mask"].shape) == (1, 1, 2, 2)

    def unavailable(*args, **kwargs):
        raise RuntimeError("no efficient kernel; do not fall back")

    with (
        patch("torch.nn.attention.sdpa_kernel", only_efficient),
        patch("torch.nn.functional.scaled_dot_product_attention", unavailable),
    ):
        with pytest.raises(RuntimeError, match="do not fall back"):
            sdpa_explicit_kv_attention_forward(module, q, k, v, None)
    assert not torch.cuda.is_initialized()


def test_efficient_profile_rejects_cpu_instead_of_silent_cpu_math():
    torch = pytest.importorskip("torch")
    q = torch.zeros(1, 28, 2, 128)
    kv = torch.zeros(1, 4, 2, 128)
    with pytest.raises(ValueError, match="no CPU math fallback"):
        sdpa_explicit_kv_attention_forward(SimpleNamespace(num_key_value_groups=7), q, kv, kv, None)
    assert not torch.cuda.is_initialized()


def test_profile_registers_both_attention_and_original_sdpa_mask_and_records_tf32():
    torch = pytest.importorskip("torch")
    from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS

    previous = torch.get_float32_matmul_precision()
    try:
        highest = configure_attention_runtime("sdpa_explicit_kv", "highest")
        assert ALL_ATTENTION_FUNCTIONS["sdpa_explicit_kv"] is sdpa_explicit_kv_attention_forward
        assert (
            ALL_MASK_ATTENTION_FUNCTIONS["sdpa_explicit_kv"] is ALL_MASK_ATTENTION_FUNCTIONS["sdpa"]
        )
        assert highest["sdpa_backend_policy"] == "efficient_only_no_fallback"
        assert highest["actual_float32_matmul_precision"] == "highest"
        assert highest["cuda_matmul_allow_tf32"] is False
        high = configure_attention_runtime("sdpa_explicit_kv", "high")
        assert high["actual_float32_matmul_precision"] == "high"
        assert high["cuda_matmul_allow_tf32"] is True
        assert digest(json_bytes(high)) != digest(json_bytes(highest))
        assert isinstance(high["cudnn_allow_tf32"], bool)
    finally:
        torch.set_float32_matmul_precision(previous)
    assert not torch.cuda.is_initialized()
