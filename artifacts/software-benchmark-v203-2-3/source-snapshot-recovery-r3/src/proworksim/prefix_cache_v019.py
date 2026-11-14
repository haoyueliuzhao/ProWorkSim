"""Bounded exact-token prefix snapshots for the installed Qwen3.5 text cache.

This helper changes only how the already selected prompt is evaluated. It does
not select messages, add role content, sample, parse output, or create learning
traces. Pass its FULL input_ids and attention_mask to model.generate, alongside
the caller's unchanged SamplingTrace and generation options. Transformers 5.17
slices the unprocessed suffix using the cloned cache's sequence length.

A hybrid recurrent cache cannot be cropped back from a completed request. Each
entry is built by a separate prefix-only forward and never passed to generation;
each request receives a deep copy. Prefix lengths are multiples of the installed
DeltaNet reference chunk size (64), but different prefill partitions can still
change FP32 rounding. Exact key matching is NOT a claim of bitwise-equivalent
logits: real-model output/logprob and full-sequence learning checks must admit a
new numerical profile before this helper is used in an experiment.
"""

from collections import OrderedDict
import copy
import importlib.metadata
import time

from .storage import digest, json_bytes

VERSION = "exact-token-prefix-cache-v0.19"
TRANSFORMERS_VERSION = "5.17.0"
PREFIX_LENGTHS = (256, 2048, 3072, 4096)


def _identity(value):
    if not isinstance(value, dict) or not value.get("policy_version"):
        raise ValueError("A complete current actor identity is required")
    required = {"adapter_sha256", "base_manifest_sha256", "inference_profile_sha256"}
    if not required <= set(value) or any(not isinstance(value[k], str) or not value[k] for k in required):
        raise ValueError("Actor identity must bind weights, base and inference profile")
    return digest(json_bytes(value))


def _tensor_bytes(cache):
    """Declared tensor payload, excluding allocator overhead and transient clones."""
    sizes, seen = {}, set()
    for layer in cache.layers:
        for name in ("keys", "values", "conv_states", "recurrent_states"):
            value = getattr(layer, name, None)
            tensors = value.values() if isinstance(value, dict) else (value,)
            for tensor in tensors:
                if tensor is not None and id(tensor) not in seen:
                    seen.add(id(tensor))
                    device = str(tensor.device)
                    sizes[device] = sizes.get(device, 0) + tensor.numel() * tensor.element_size()
    return sizes


class ExactPrefixCache:
    """At most eight immutable prefix snapshots, bound to one model and actor.

    ``prepare`` returns ``(generate_kwargs, record)``. Merge generation controls
    into kwargs without replacing input_ids/attention_mask/past_key_values. No
    output may be retokenized or relabeled; the existing actor must keep the full
    original prompt token list in its learning trace. Call ``clear`` on a weight
    update/restore; an identity or model-object change also clears automatically.
    This object is for the existing synchronous one-request actor only.
    """

    def __init__(self, *, prefix_tokens=2048, max_entries=8, matmul_precision="highest"):
        if type(prefix_tokens) is not int or prefix_tokens not in PREFIX_LENGTHS:
            raise ValueError("Choose one declared prefix length: 256, 2048, 3072 or 4096")
        if type(max_entries) is not int or not 1 <= max_entries <= 8:
            raise ValueError("At most eight retained prefixes are supported")
        if matmul_precision not in {"highest", "high"}:
            raise ValueError("Declare high or highest matmul precision explicitly")
        self.matmul_precision = matmul_precision
        self.prefix_tokens = prefix_tokens
        self.max_entries = max_entries
        self._entries = OrderedDict()
        self._actor = None
        self._model = None
        self._hits = self._misses = self._skips = self._clears = 0

    def clear(self, *, reason="explicit_actor_boundary"):
        count = len(self._entries)
        self._entries.clear()
        self._actor = self._model = None
        self._clears += 1
        return {"reason": reason, "removed_entries": count}

    def snapshot(self):
        return {
            "version": VERSION,
            "prefix_tokens": self.prefix_tokens,
            "max_entries": self.max_entries,
            "matmul_precision": self.matmul_precision,
            "actor_identity_sha256": self._actor,
            "entries": [
                {"prefix_sha256": digest(json_bytes(list(key))),
                 "prefix_tokens": len(key), "tensor_bytes_by_device": _tensor_bytes(value)}
                for key, value in self._entries.items()
            ],
            "hits": self._hits, "misses": self._misses, "skips": self._skips,
            "clear_count": self._clears,
            "cache_scope": "Exact prefix-only states; no suffix state, prompt rewriting or cross-actor reuse",
        }

    def prepare(self, model, input_ids, attention_mask, actor_identity):
        import torch
        from transformers.cache_utils import DynamicCache

        if importlib.metadata.version("transformers") != TRANSFORMERS_VERSION:
            raise ValueError("Prefix-cache API is validated only for Transformers 5.17.0")
        config = model.config.get_text_config()
        if config.model_type != "qwen3_5_text" or config.is_encoder_decoder:
            raise ValueError("Only the installed decoder-only Qwen3.5 text implementation is supported")
        if model.training or any(p.is_floating_point() and p.dtype != torch.float32 for p in model.parameters()):
            raise ValueError("Prefix snapshots require the unchanged FP32 eval model")
        if torch.get_float32_matmul_precision() != self.matmul_precision:
            raise ValueError("Actual matmul precision differs from the declared cache profile")
        if input_ids.ndim != 2 or input_ids.shape[0] != 1 or input_ids.dtype != torch.long:
            raise ValueError("Only one unpadded full token sequence is supported")
        if attention_mask.shape != input_ids.shape or not bool((attention_mask == 1).all()):
            raise ValueError("Keep the full, unpadded all-one attention mask")
        actor = _identity(actor_identity)
        invalidation = None
        if self._actor is not None and (actor != self._actor or model is not self._model):
            invalidation = self.clear(reason="actor_identity_or_model_object_changed")
        self._actor, self._model = actor, model
        tokens = tuple(input_ids[0].detach().cpu().tolist())
        kwargs = {"input_ids": input_ids, "attention_mask": attention_mask}
        record = {
            "version": VERSION, "actor_identity_sha256": actor,
            "full_input_sha256": digest(json_bytes(list(tokens))),
            "full_input_tokens": len(tokens), "configured_prefix_tokens": self.prefix_tokens,
            "invalidation": invalidation,
            "original_input_preserved": True, "prefix_snapshot_contains_suffix": False,
        }
        # generate needs logits from at least one prompt token after the cache.
        if len(tokens) <= self.prefix_tokens:
            self._skips += 1
            return kwargs, {**record, "status": "skipped_short_prompt", "hit": False,
                            "reused_prefix_tokens": 0, "suffix_tokens": len(tokens)}
        prefix = tokens[:self.prefix_tokens]
        hit = prefix in self._entries
        started = time.perf_counter()
        if hit:
            self._hits += 1
            self._entries.move_to_end(prefix)
        else:
            self._misses += 1
            with torch.inference_mode():
                output = model(
                    input_ids=input_ids[:, :self.prefix_tokens],
                    attention_mask=attention_mask[:, :self.prefix_tokens],
                    use_cache=True, logits_to_keep=1, return_dict=True,
                )
                cache = output.past_key_values
                if not isinstance(cache, DynamicCache) or cache.get_seq_length() != self.prefix_tokens:
                    raise ValueError("Prefix forward did not return an exact-length official DynamicCache")
                if getattr(cache, "offloading", False):
                    raise ValueError("Cache offloading is outside this profile")
                # Keep a detached private snapshot; neither outputs nor request clones alias it.
                snapshot = copy.deepcopy(cache)
                del output, cache
            if len(self._entries) == self.max_entries:
                self._entries.popitem(last=False)
            self._entries[prefix] = snapshot
        with torch.inference_mode():
            restored = copy.deepcopy(self._entries[prefix])
        if restored.get_seq_length() != self.prefix_tokens:
            raise ValueError("Stored prefix cache was mutated")
        kwargs["past_key_values"] = restored
        return kwargs, {
            **record, "status": "hit" if hit else "built_prefix_snapshot", "hit": hit,
            "prefix_sha256": digest(json_bytes(list(prefix))),
            "reused_prefix_tokens": self.prefix_tokens if hit else 0,
            "prefilled_prefix_tokens": 0 if hit else self.prefix_tokens,
            "cache_sequence_length": self.prefix_tokens,
            "suffix_tokens": len(tokens) - self.prefix_tokens,
            "snapshot_tensor_bytes_by_device": _tensor_bytes(self._entries[prefix]),
            "prepare_host_elapsed_seconds": time.perf_counter() - started,
            "timing_scope": "Host interval without added CUDA synchronization; benchmark whole generation with explicit synchronization separately",
            "numerical_admission": "Required separately: full-input/outputs/raw logprobs and uncached learning recomputation; no tolerance change here",
        }
