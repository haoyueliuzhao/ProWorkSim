"""Explicit FP32/high and exact-prefix execution; original probability gates remain."""

import copy

from .candidate_runtime_v017 import CandidateActor as PreviousActor
from .candidate_runtime_v017 import candidate_profile as previous_profile
from .online_training import SharedActor
from .prefix_cache_v019 import ExactPrefixCache

VERSION = "candidate-runtime-v0.19"
PREFIX = {
    "version": "exact-token-prefix-v0.19",
    "prefix_tokens": 2048,
    "max_entries": 8,
    "identity_scope": "Exact actor identity and exact full cached token prefix; no cross-policy reuse",
    "learning": "Full original input replay with original probability tolerances; no cached training graph",
}


def candidate_profile(candidate_id, *, dtype="float32", devices=1):
    profile = previous_profile(candidate_id, dtype=dtype, devices=devices)
    if dtype != "float32":
        raise ValueError("This throughput profile retains the original FP32 path")
    profile.update(
        version=VERSION,
        attention="sdpa_explicit_kv",
        matmul_precision="high",
        prefix_cache=copy.deepcopy(PREFIX),
    )
    return profile


class CandidateActor(PreviousActor):
    def __init__(self, *args, inference_profile, **kwargs):
        import torch

        from .local_model_service import configure_attention_runtime

        torch.backends.cudnn.allow_tf32 = False
        numerical = configure_attention_runtime("sdpa_explicit_kv", "high")
        network = args[0] if args else kwargs["model"]
        network.set_attn_implementation("sdpa_explicit_kv")
        if network.config._attn_implementation != "sdpa_explicit_kv":
            raise ValueError(
                "Optimized full attention did not install its explicit efficient backend"
            )
        profile = copy.deepcopy(inference_profile)
        profile.update(numerical)
        profile.update(
            version=VERSION,
            attention="sdpa_explicit_kv",
            custom_attention_patch=True,
            matmul_precision="high",
            actual_float32_matmul_precision=torch.get_float32_matmul_precision(),
            cuda_matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,
            prefix_cache=copy.deepcopy(PREFIX),
        )
        self.prefix_cache = ExactPrefixCache(
            prefix_tokens=PREFIX["prefix_tokens"],
            max_entries=PREFIX["max_entries"],
            matmul_precision="high",
        )
        # The inherited strict loader constructs cls with factual numeric metadata.
        # Initialize once, without the older constructor overwriting this profile.
        SharedActor.__init__(self, *args, inference_profile=profile, **kwargs)

    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        expected = candidate_profile(
            profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
        )
        if profile != expected:
            raise ValueError("Undeclared v0.19 execution profile change")
        original = previous_profile(
            profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
        )
        return super().from_candidate(
            model_path, manifest=manifest, profile=original, output=output, recipe=recipe
        )

    def _generate_tokens(self, inputs, trace, options):
        kwargs, metadata = self.prefix_cache.prepare(
            self.model, inputs, self.torch.ones_like(inputs), self.freeze_identity()
        )
        generated = self.model.generate(**kwargs, logits_processor=[trace], **options)
        return generated, {
            "cache_scope": "Immutable exact prefix snapshot cloned per request; discarded before learning or actor change",
            "prefix_cache": metadata,
        }

    def clear_generation_cache(self):
        super().clear_generation_cache()
        if getattr(self, "phase", None) != "collecting":
            self.prefix_cache.clear()
