"""One resident BF16 base / FP32 LoRA learner, without prefix or replica sampling.

This is a new numerical configuration, not a claim that old FP32 actions recur.
The inherited official loader stores the base in BF16 before PEFT construction;
this module rejects inconsistent storage rather than silently converting it.
"""

import copy

from .candidate_runtime_v017 import CandidateActor as PreviousActor
from .candidate_runtime_v017 import candidate_profile as previous_profile
from .local_model_service import sdpa_explicit_kv_attention_forward
from .online_training import SharedActor, recipe_config
from .storage import digest, json_bytes

VERSION = "candidate-runtime-v0.20"
ATTENTION = "sdpa_bf16_explicit_kv_v020"
PROBABILITY_GATE = {"logprob_max_atol": 0.02, "logprob_mean_atol": 0.002}


def candidate_profile(candidate_id, *, dtype="bfloat16", devices=1):
    if dtype != "bfloat16":
        raise ValueError("v0.20 requires actual BF16 base storage")
    profile = previous_profile(candidate_id, dtype=dtype, devices=devices)
    profile.update(
        version=VERSION,
        attention=ATTENTION,
        matmul_precision="highest",
        base_storage_dtype="bfloat16",
        adapter_storage_dtype="float32",
        adapter_compute_dtype="float32",
        attention_qkv_dtype="bfloat16",
        normalization_dtype="float32",
        critic_dtype="float32",
        autocast=False,
        prefix_cache={"enabled": False},
        sampling={"resident_instances": 1, "replicas": 0, "role_scheduling": "sequential"},
        probability_gate=copy.deepcopy(PROBABILITY_GATE),
        dtype_scope=("Frozen text base parameters stored as BF16; trainable LoRA parameters "
                     "and LoRA matmuls FP32; PEFT casts combined projection back to BF16; "
                     "sampling temperature/log-softmax and full-input selected-token replay FP32. "
                     "Official DeltaNet/RMSNorm/rotary FP32 intermediates are retained."),
    )
    return profile


def _no_autocast(torch):
    if torch.is_autocast_enabled("cuda") or torch.is_autocast_enabled("cpu"):
        raise ValueError("v0.20 forbids ambient autocast; storage and computation are explicit")


def bf16_attention_forward(module, query, key, value, attention_mask, **kwargs):
    import torch

    _no_autocast(torch)
    if any(t.dtype != torch.bfloat16 for t in (query, key, value)):
        raise ValueError("v0.20 full-attention Q/K/V must actually be BF16")
    # The existing implementation requires CUDA and efficient SDPA exclusively.
    # A missing supported kernel raises; there is no Math/CPU/precision fallback.
    return sdpa_explicit_kv_attention_forward(
        module, query, key, value, attention_mask, **kwargs
    )


def inspect_parameter_storage(model, torch, *, frozen_fp32_names=()):
    """Validate every actual parameter; record buffers separately, without casting."""
    counts = {"base": {"tensors": 0, "elements": 0, "bytes": 0},
              "adapter": {"tensors": 0, "elements": 0, "bytes": 0}}
    frozen_fp32_names = set(frozen_fp32_names)
    if frozen_fp32_names:
        counts["lm_head"] = {"tensors": 0, "elements": 0, "bytes": 0}
    if not frozen_fp32_names.issubset(dict(model.named_parameters())):
        raise ValueError("Declared frozen FP32 parameters are absent")
    layout, devices = [], set()
    for name, parameter in model.named_parameters():
        adapter = "lora_" in name
        expected = torch.float32 if adapter or name in frozen_fp32_names else torch.bfloat16
        if parameter.dtype != expected or parameter.requires_grad != adapter:
            raise ValueError("Actual parameter storage/trainability violates v0.20: " + name)
        if parameter.device.type == "meta":
            raise ValueError("Unmaterialized base/adapter parameter: " + name)
        bucket = counts["adapter" if adapter else "lm_head" if name in frozen_fp32_names else "base"]
        bucket["tensors"] += 1
        bucket["elements"] += parameter.numel()
        bucket["bytes"] += parameter.numel() * parameter.element_size()
        devices.add(str(parameter.device))
        layout.append([name, str(parameter.dtype), list(parameter.shape),
                       str(parameter.device), parameter.requires_grad])
    if not counts["base"]["elements"] or not counts["adapter"]["elements"]:
        raise ValueError("Both frozen BF16 base and trainable FP32 LoRA are required")
    buffers = {}
    for _, buffer in model.named_buffers():
        key = str(buffer.dtype)
        buffers.setdefault(key, {"tensors": 0, "elements": 0, "bytes": 0})
        buffers[key]["tensors"] += 1
        buffers[key]["elements"] += buffer.numel()
        buffers[key]["bytes"] += buffer.numel() * buffer.element_size()
    return {"base_dtype": "bfloat16_backbone_float32_lm_head" if frozen_fp32_names else "bfloat16",
            "adapter_dtype": "float32", "counts": counts,
            "parameter_layout_sha256": digest(json_bytes(layout)), "devices": sorted(devices),
            "buffers_by_dtype": buffers,
            "scope": "Actual tensor storage only; excludes cache, activations, gradients, optimizer and allocator overhead"}


class Float32SamplingProcessor:
    """Force the real generator and its saved sampling trace to use FP32 scores."""

    def __init__(self, trace):
        self.trace = trace
        self.observed_input_dtypes = set()
        self.calls = 0

    def __call__(self, input_ids, scores):
        import torch

        _no_autocast(torch)
        self.observed_input_dtypes.add(str(scores.dtype))
        self.calls += 1
        scaled = self.trace(input_ids, scores.float())
        if scaled.dtype != torch.float32 or self.trace.previous.dtype != torch.float32:
            raise ValueError("Sampling temperature and log-softmax must execute in FP32")
        return scaled


class CandidateActor(PreviousActor):
    runtime_version = VERSION
    profile_factory = staticmethod(candidate_profile)
    storage_inspector = staticmethod(inspect_parameter_storage)

    def prepare_model(self, network, torch):
        """Versioned subclasses may prepare an explicitly declared storage partition."""

    def __init__(self, *args, inference_profile, **kwargs):
        import torch
        from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface
        from transformers.modeling_utils import AttentionInterface

        from .local_model_service import configure_attention_runtime

        if kwargs.get("sampling_only", False) or not kwargs.get("require_lora", True):
            raise ValueError("v0.20 uses one shared learner and no readonly sampling replicas")
        _no_autocast(torch)
        if torch.get_default_dtype() != torch.float32:
            raise ValueError("FP32 default required for the declared critic and optimizer construction")
        profile = copy.deepcopy(inference_profile)
        declared = self.profile_factory(profile["candidate_id"], dtype=profile["dtype"],
                                     devices=profile["devices"])
        recipe = recipe_config(kwargs.get("recipe"))
        if any(recipe[key] != value for key, value in PROBABILITY_GATE.items()):
            raise ValueError("v0.20 retains the original .02/.002 probability tolerances")
        if (recipe["max_length"] != declared["max_context_tokens"]
                or recipe["max_output_tokens"] != declared["max_output_tokens"]
                or recipe["temperature"] != declared["temperature"]):
            raise ValueError("Recipe differs from declared candidate interface budget")
        network = args[0] if args else kwargs["model"]
        self.prepare_model(network, torch)
        actual = self.storage_inspector(network, torch)
        device = kwargs.get("device", "cuda")
        if device.startswith("cuda"):
            actual_devices = {p.device.index for p in network.parameters()}
            if any(p.device.type != "cuda" for p in network.parameters()) or actual_devices != set(range(declared["devices"])):
                raise ValueError("Actual parameter placement differs from declared CUDA devices; no offload")
        torch.backends.cudnn.allow_tf32 = False
        numerical = configure_attention_runtime("sdpa_explicit_kv", "highest")
        AttentionInterface.register(ATTENTION, bf16_attention_forward)
        AttentionMaskInterface.register(ATTENTION, ALL_MASK_ATTENTION_FUNCTIONS["sdpa"])
        network.set_attn_implementation(ATTENTION)
        if network.config._attn_implementation != ATTENTION:
            raise ValueError("BF16 efficient-only attention adapter did not install")
        profile.update(declared)
        profile.update(numerical)
        profile.update(
            custom_attention_patch=True,
            attention_adapter_version="bf16-explicit-kv-efficient-v0.20",
            actual_float32_matmul_precision=torch.get_float32_matmul_precision(),
            cuda_matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,
            actual_cudnn_allow_tf32=torch.backends.cudnn.allow_tf32,
            actual_parameter_storage=actual,
            dtype_enforcement="Base/adapter storage verified at construction and execution; QKV/normalization checked when executed",
        )
        SharedActor.__init__(self, *args, inference_profile=profile, **kwargs)
        if any(p.dtype != torch.float32 for p in self.critic.parameters()):
            raise ValueError("Actual critic parameters must be FP32")

    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        import torch

        expected = cls.profile_factory(profile["candidate_id"], dtype=profile["dtype"],
                                     devices=profile["devices"])
        if profile != expected:
            raise ValueError("Undeclared v0.20 execution profile change")
        if torch.cuda.device_count() < profile["devices"]:
            raise ValueError("Declared CUDA devices unavailable; no fallback")
        for index in range(profile["devices"]):
            with torch.cuda.device(index):
                if not torch.cuda.is_bf16_supported(including_emulation=False):
                    raise ValueError("Native BF16 unavailable on declared CUDA device")
        numeric = previous_profile(profile["candidate_id"], dtype="bfloat16",
                                   devices=profile["devices"])
        return super().from_candidate(model_path, manifest=manifest, profile=numeric,
                                      output=output, recipe=recipe)

    def _verify_execution(self):
        _no_autocast(self.torch)
        if self.torch.get_float32_matmul_precision() != "highest":
            raise ValueError("Actual FP32 matmul precision differs from v0.20 declaration")
        if self.model.config._attn_implementation != ATTENTION:
            raise ValueError("Actual attention adapter changed")
        current = self.storage_inspector(self.model, self.torch)
        if current != self.inference_profile["actual_parameter_storage"]:
            raise ValueError("Actual parameter storage changed after declaration")

    def _generate_tokens(self, inputs, trace, options):
        self._verify_execution()
        processor = Float32SamplingProcessor(trace)
        generated = self.model.generate(
            input_ids=inputs, attention_mask=self.torch.ones_like(inputs),
            logits_processor=[processor], **options,
        )
        return generated, {
            "version": self.runtime_version, "resident_instances": 1, "sampling_replicas": 0,
            "cache_scope": "Fresh per-request generation KV only; no prefix cache or cross-role reuse",
            "base_storage_dtype": self.inference_profile["base_storage_dtype"], "adapter_storage_dtype": "float32",
            "sampling_normalization_dtype": "float32",
            "sampler_input_score_dtypes": sorted(processor.observed_input_dtypes),
            "normalization_calls": processor.calls,
        }

    def learning_logprobs(self, trace):
        self._verify_execution()
        result = super().learning_logprobs(trace)
        if result.dtype != self.torch.float32:
            raise ValueError("Actual full-input selected-token normalization must be FP32")
        return result

    def export_sampling_snapshot(self, directory):
        raise ValueError("v0.20 uses one resident sampler; replica snapshot export is disabled")
