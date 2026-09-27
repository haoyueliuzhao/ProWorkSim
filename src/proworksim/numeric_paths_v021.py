"""Observe fixed-token Qwen execution paths without generating or updating policy.

The cache replay is a no-gradient diagnostic only. No past cache is detached and
then presented as a differentiable training path; cached-gradient/backward are
explicitly untested. Only compact selected-position summaries are serialized.
"""

import copy
import inspect
import os
from pathlib import Path
import sys
import time

from .online_training import probability_check, reference
from .storage import atomic_write, digest, json_bytes

VERSION = "fixed-token-numeric-paths-v0.21"
FIXED_POSITIONS = (0, 1, 2, 31, 73, 145)
BRANCHES = ("causal_conv1d_fn", "causal_conv1d_update",
            "torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule")


def _write(path, value):
    atomic_write(Path(path), json_bytes(value))


def tensor_metadata(tensor):
    if tensor is None:
        return None
    if isinstance(tensor, dict):
        return {str(k): tensor_metadata(v) for k, v in tensor.items()}
    if isinstance(tensor, (list, tuple)):
        return [tensor_metadata(v) for v in tensor]
    return {"shape": list(tensor.shape), "dtype": str(tensor.dtype), "device": str(tensor.device),
            "requires_grad": tensor.requires_grad,
            "grad_fn": type(tensor.grad_fn).__name__ if tensor.grad_fn is not None else None}


def small_values(tensor):
    result = tensor_metadata(tensor)
    if tensor is not None:
        detached = tensor.detach()
        if detached.ndim == 0:
            first = last = detached.reshape(1)
        else:
            first = detached[tuple(0 for _ in detached.shape[:-1])][:4]
            last = detached[tuple(size - 1 for size in detached.shape[:-1])][-4:]
        result["first4"] = first.cpu().tolist()
        result["last4"] = last.cpu().tolist()
    return result


def vector_summary(tensor):
    import torch

    values = tensor.detach().float().reshape(-1)
    stats = torch.stack([values.min(), values.max(), values.mean(), values.square().mean().sqrt()])
    low, high, mean, rms = stats.cpu().tolist()
    return {"dtype": str(tensor.dtype), "elements": values.numel(), "min": low,
            "max": high, "mean": mean, "rms": rms, "first8": values[:8].cpu().tolist()}


def cache_metadata(cache):
    if cache is None:
        return None
    rows = []
    for i, layer in enumerate(cache.layers):
        row = {"layer": i, "class": type(layer).__name__, "record_past": getattr(layer, "record_past", None)}
        for name in ("keys", "values", "conv_states", "recurrent_states"):
            value = getattr(layer, name, None)
            row[name] = ([tensor_metadata(x) for x in value] if isinstance(value, (list, tuple))
                         else tensor_metadata(value))
        rows.append(row)
    return {"class": type(cache).__name__, "sequence_length": cache.get_seq_length(), "layers": rows}


class PathObserver:
    """Observe actual Python reference function entry, layer outputs and inputs.

    The profiler sees reference code objects through upstream dispatch decorators;
    missing entries remain missing evidence rather than being guessed from shapes.
    """

    def __init__(self, model, trace, positions):
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen

        self.model, self.trace = model, trace
        self.positions = tuple(positions)
        self.output_position = None  # None is the complete-sequence pass.
        self.current_layer = None
        self.phase = "full"
        self.branch_counts, self.branch_by_layer = {}, {}
        self.hidden, self.inputs, self.cached_states = {}, {}, {}
        self._hidden_vectors = {}
        self.handles = []
        self.codes = {}
        for name in BRANCHES:
            function = inspect.unwrap(getattr(qwen, name))
            self.codes[function.__code__] = name
        from transformers import cache_utils
        from transformers.generation import utils as generation
        from transformers.integrations import hub_kernels
        self.source_refs = {name: reference(inspect.getsourcefile(module)) for name, module in
                            (("qwen", qwen), ("cache", cache_utils), ("generation", generation), ("kernel_dispatch", hub_kernels))}
        self.observed_reference_entries = 0

    def _profile(self, frame, event, arg):
        if event != "call":
            return
        name = self.codes.get(frame.f_code)
        if name is not None:
            self.observed_reference_entries += 1
            key = self.phase + ":" + name
            self.branch_counts[key] = self.branch_counts.get(key, 0) + 1
            layer_key = str(self.current_layer) + ":" + key
            self.branch_by_layer[layer_key] = self.branch_by_layer.get(layer_key, 0) + 1

    def _indices(self, length):
        if self.output_position is not None:
            return [(self.output_position, length - 1)] if self.output_position in self.positions else []
        prompt = len(self.trace["input_ids"])
        return [(p, prompt - 1 + p) for p in self.positions]

    def _pre(self, index, module, args, kwargs):
        self.current_layer = index
        if self.output_position is None or self.output_position in self.positions:
            key = "full" if self.output_position is None else str(self.output_position)
            mask = kwargs.get("attention_mask")
            self.inputs.setdefault(key, {})[str(index)] = {
                "hidden": tensor_metadata(args[0]), "mask": small_values(mask),
                "position_ids": small_values(kwargs.get("position_ids")),
                "use_cache": kwargs.get("use_cache"),
                "cache_supplied": kwargs.get("past_key_values") is not None,
            }

    def _post(self, index, module, args, output):
        hidden = output[0] if isinstance(output, tuple) else output
        for position, offset in self._indices(hidden.shape[1]):
            vector = hidden[0, offset]
            self.hidden.setdefault(str(position), {})[str(index)] = vector_summary(vector)
            # Small internal CPU vectors enable exact layer-wise comparisons;
            # only their scalar deltas, never these full vectors, are written.
            self._hidden_vectors[(position, index)] = vector.detach().float().cpu().clone()

    def __enter__(self):
        if sys.getprofile() is not None:
            raise ValueError("Refuse to overwrite an existing Python profiler")
        backbone = self.model.get_base_model().model if hasattr(self.model, "get_base_model") else self.model.model
        for index, layer in enumerate(backbone.layers):
            self.handles.append(layer.register_forward_pre_hook(
                lambda module, args, kwargs, i=index: self._pre(i, module, args, kwargs), with_kwargs=True))
            self.handles.append(layer.register_forward_hook(
                lambda module, args, output, i=index: self._post(i, module, args, output)))
        sys.setprofile(self._profile)
        return self

    def __exit__(self, *exc):
        sys.setprofile(None)
        for handle in self.handles:
            handle.remove()
        return False

    def snapshot(self):
        return {"branch_counts": self.branch_counts, "branch_counts_by_layer": self.branch_by_layer,
                "actual_reference_function_entries": self.observed_reference_entries,
                "reference_entry_scope": "Actual installed Python reference code execution; no entry does not identify an alternative kernel",
                "source_refs": self.source_refs, "layer_hidden_summaries": self.hidden,
                "layer_inputs": self.inputs, "cache_states_at_selected_positions": self.cached_states}


def _logit_summary(logits, target, temperature):
    import torch

    vector = logits.detach().float()
    top = torch.topk(vector, min(8, vector.numel()))
    return {**vector_summary(logits), "selected_token_id": target,
            "selected_raw_logit": float(vector[target]),
            "temperature": temperature, "scaled_logsumexp": float((vector / temperature).logsumexp(-1)),
            "top8_ids": top.indices.cpu().tolist(), "top8_raw_logits": top.values.cpu().tolist()}


def _gpu_sync(torch, device):
    if str(device).startswith("cuda"):
        torch.cuda.synchronize()


def cache_teacher_replay(model, trace, observer, *, torch, device):
    """Original generation prefill/one-token prepares, substituting recorded tokens.

    No generate(), multinomial(), or resampling. State is only used under
    no_grad. All actual prefix masks/positions use installed generation helpers.
    """
    from transformers.cache_utils import DynamicCache

    generator = model.get_base_model() if hasattr(model, "get_base_model") else model
    ids = torch.tensor([trace["input_ids"]], dtype=torch.long, device=device)
    kwargs = {"attention_mask": torch.ones_like(ids), "use_cache": True,
              "past_key_values": DynamicCache(config=generator.config), "logits_to_keep": 1}
    kwargs["position_ids"] = generator._prepare_position_ids_for_generation(ids, kwargs)
    logprobs, logits_summaries = [], {}
    model.eval()
    with torch.inference_mode(), generator._optimize_model_for_decode():
        for position, token in enumerate(trace["output_ids"]):
            observer.output_position = position
            observer.phase = "prefill" if position == 0 else "cached_decode"
            prepared = model.prepare_inputs_for_generation(
                ids, next_sequence_length=ids.shape[1] if position == 0 else 1,
                is_first_iteration=position == 0, **kwargs)
            outputs = model(**prepared, return_dict=True)
            kwargs = generator._update_model_kwargs_for_generation(outputs, kwargs,
                        is_encoder_decoder=generator.config.is_encoder_decoder)
            # Exactly the generation path's FP32 pre-processor input and sole temperature.
            logits = outputs.logits[:, -1].to(copy=True, dtype=torch.float32, device=ids.device)[0]
            chosen = (logits / trace["sampling_temperature"]).log_softmax(-1)[token]
            logprobs.append(chosen)
            if position in observer.positions:
                logits_summaries[str(position)] = _logit_summary(logits, token, trace["sampling_temperature"])
                observer.cached_states[str(position)] = cache_metadata(kwargs["past_key_values"])
            ids = torch.cat([ids, ids.new_tensor([[token]])], dim=1)
            del outputs
        result = torch.stack(logprobs).detach().cpu().tolist()
    # Do not carry a teacher replay cache into any learning path.
    del kwargs
    return result, logits_summaries


def full_replay(model, trace, observer, *, torch, device, grad_enabled):
    """The original full-input learner forward, with or without a gradient graph."""
    model.train(grad_enabled)
    ids = torch.tensor([trace["input_ids"] + trace["output_ids"]], dtype=torch.long, device=device)
    count = len(trace["output_ids"])
    observer.output_position, observer.phase = None, "full_grad" if grad_enabled else "full_no_grad"
    with torch.set_grad_enabled(grad_enabled):
        outputs = model(input_ids=ids, attention_mask=torch.ones_like(ids), use_cache=False,
                        logits_to_keep=count + 1)
        logits = outputs.logits[0, :-1].float()
        targets = torch.tensor(trace["output_ids"], dtype=torch.long, device=logits.device)
        probabilities = (logits / trace["sampling_temperature"]).log_softmax(-1).gather(1, targets[:, None]).squeeze(1)
        summaries = {str(p): _logit_summary(logits[p], trace["output_ids"][p], trace["sampling_temperature"])
                     for p in observer.positions}
        checkpoints = [{"module": name, "enabled": module.gradient_checkpointing,
                        "use_reentrant": getattr(getattr(module, "_gradient_checkpointing_func", None), "keywords", {}).get("use_reentrant")}
                       for name, module in model.named_modules() if hasattr(module, "gradient_checkpointing")]
        graph = {"grad_enabled": grad_enabled, "model_training": model.training,
                 "gradient_checkpointing_modules": checkpoints,
                 "dropout_modules": [{"module": name, "p": module.p} for name, module in model.named_modules() if isinstance(module, torch.nn.Dropout)],
                 "config_attention_dropout": getattr(model.config, "attention_dropout", None),
                 "logprobs_dtype": str(probabilities.dtype), "logprobs_require_grad": probabilities.requires_grad,
                 "logprobs_grad_fn": type(probabilities.grad_fn).__name__ if probabilities.grad_fn is not None else None,
                 "backward_executed": False, "optimizer_steps": 0}
        result = probabilities.detach().cpu().tolist()
    del outputs, logits, probabilities
    return result, summaries, graph


def _hidden_comparison(left, right):
    result = {}
    for key in sorted(set(left) & set(right)):
        difference = (left[key] - right[key]).abs()
        result.setdefault(str(key[0]), {})[str(key[1])] = {
            "max_abs_delta": float(difference.max()), "mean_abs_delta": float(difference.mean())}
    return result


def run_paths(model, trace, *, torch, device, recipe, positions=FIXED_POSITIONS,
              diagnostic_failure_position=None, output=None):
    """CPU-testable core. Caller is responsible for checkpoint/actor identity checks."""
    requested = sorted(set(p for p in positions if 0 <= p < len(trace["output_ids"])))
    selected = sorted(set(requested + ([diagnostic_failure_position] if diagnostic_failure_position is not None else [])))
    if any(type(p) is not int or not 0 <= p < len(trace["output_ids"]) for p in selected):
        raise ValueError("Selected summary position is outside the saved output")
    report = {"version": VERSION, "fixed_positions": requested,
              "diagnostic_extra_failure_position": diagnostic_failure_position,
              "paths": {}, "sampled_new_tokens": 0, "backward_calls": 0, "optimizer_steps": 0,
              "cached_gradient_path": {"executed": False,
                "reason": "Official conv/recurrent cache has in-place copy/update; preservation of complete past LoRA dependencies is not established. No detached cache is offered as a learner."}}
    hidden = {}
    for name in ("cache_no_grad", "full_no_grad", "full_grad"):
        if output is not None:
            _write(Path(output) / "task.json", {"task": name, "started_at": time.time(), "pid": os.getpid()})
        started = time.monotonic()
        if hasattr(model, "_cache"):
            delattr(model, "_cache")
        if str(device).startswith("cuda"):
            torch.cuda.reset_peak_memory_stats()
        observer = PathObserver(model, trace, selected)
        with observer:
            if name == "cache_no_grad":
                probabilities, summaries = cache_teacher_replay(model, trace, observer, torch=torch, device=device)
                graph = {"grad_enabled": False, "autograd_context": "inference_mode_matching_original_sampler",
                         "model_training": False, "logprobs_require_grad": False,
                         "backward_executed": False, "optimizer_steps": 0}
            else:
                probabilities, summaries, graph = full_replay(model, trace, observer, torch=torch,
                                                              device=device, grad_enabled=name == "full_grad")
        _gpu_sync(torch, device)
        row = {"status": "complete", "elapsed_seconds": time.monotonic() - started,
               "comparison_to_original_sampling": probability_check(probabilities, trace["behavior_logprobs"], recipe),
               "logit_summaries": summaries, "gradient_execution": graph, **observer.snapshot()}
        if str(device).startswith("cuda"):
            row["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["paths"][name] = row
        hidden[name] = observer._hidden_vectors
        if output is not None:
            _write(Path(output) / (name + ".json"), row)
            _write(Path(output) / "paths.json", report)
    cache_p = report["paths"]["cache_no_grad"]["comparison_to_original_sampling"]["recomputed_logprobs"]
    full_p = report["paths"]["full_no_grad"]["comparison_to_original_sampling"]["recomputed_logprobs"]
    grad_p = report["paths"]["full_grad"]["comparison_to_original_sampling"]["recomputed_logprobs"]
    report["between_paths"] = {
        "full_vs_cache": probability_check(full_p, cache_p, recipe),
        "full_grad_vs_full_no_grad": probability_check(grad_p, full_p, recipe),
        "layer_hidden_full_vs_cache": _hidden_comparison(hidden["full_no_grad"], hidden["cache_no_grad"]),
        "layer_hidden_grad_vs_no_grad": _hidden_comparison(hidden["full_grad"], hidden["full_no_grad"]),
    }
    cache_ok = report["paths"]["cache_no_grad"]["comparison_to_original_sampling"]["passed"]
    full_ok = report["paths"]["full_no_grad"]["comparison_to_original_sampling"]["passed"]
    report["direction"] = (
        "Cached replay does not match original sampling within the unchanged gate: first investigate replay/record/position/state conventions; no DeltaNet attribution."
        if not cache_ok else
        "Cached replay matches the original gate and full replay does not: focus next on observed incremental/full execution differences; this is not a layer-specific cause or cached-gradient admission."
        if not full_ok else
        "Both no-grad paths meet the original gate on this saved sequence; inspect grad-enabled correspondence separately. No training admission follows from one fixed trace."
    )
    model.eval()
    if output is not None:
        _write(Path(output) / "paths.json", report)
    return report


def diagnose(owner, saved_call, saved_numeric, output):
    """Strict production wrapper around the one archived 8473+146 trace."""
    record, body = saved_call, saved_call["response"]
    trace = copy.deepcopy(body["token_trace"])
    if (len(trace["input_ids"]) != 8473 or len(trace["output_ids"]) != 146
            or trace["raw_output_ids"] != trace["output_ids"]
            or trace["raw_behavior_logprobs"] != trace["behavior_logprobs"]
            or body["actor_identity"] != record["actor_identity"]
            or owner.freeze_identity() != body["actor_identity"]):
        raise ValueError("N requires the exact archived v0.20.1 actor and original token trace")
    owner._verify_execution()
    if owner.inference_profile != body["inference_profile"]:
        raise ValueError("Actual numerical profile differs from original sampling")
    numeric_row = saved_numeric["rows"][0]
    if (numeric_row["response_id"] != body["id"] or
            numeric_row["probability"]["actual_behavior_logprobs"] != trace["behavior_logprobs"]):
        raise ValueError("Archived numeric failure is not associated with this actual response")
    failure = max(range(len(trace["output_ids"])), key=lambda p: abs(numeric_row["probability"]["signed_delta"][p]))
    original_identity = owner.freeze_identity()
    report = run_paths(owner.model, trace, torch=owner.torch, device=owner.device, recipe=owner.recipe,
                       diagnostic_failure_position=failure, output=output)
    report["actor_before"] = original_identity
    report["actor_after"] = owner._make_identity()
    report["actor_unchanged"] = report["actor_after"] == original_identity
    report["actual_parameter_gradients_present"] = any(p.grad is not None for p in owner.actor_parameters.values())
    report["actor_steps"] = owner.actor_steps
    report["critic_steps"] = owner.critic_steps
    report["original_token_trace_sha256"] = digest(json_bytes(trace))
    if not report["actor_unchanged"] or report["actual_parameter_gradients_present"] or owner.actor_steps or owner.critic_steps:
        raise ValueError("A forward-only diagnostic changed actor/optimizer/gradient state")
    _write(Path(output) / "paths.json", report)
    return report
