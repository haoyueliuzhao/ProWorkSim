"""Tiny official Qwen/PEFT numerical qualification of ordered leaf-gradient reuse.

This uses synthetic token fixtures and real backward/AdamW operations, never the
9B model or task sampling. The BF16 CPU control preserves storage/cast semantics,
but uses installed CPU SDPA and does not qualify the production CUDA kernel.
Thresholds are declared below before execution; failed profiles stay failed.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import time

from proworksim.functional_qwen_v022 import learning_logprobs
from proworksim.gradient_bank_v037 import (
    GradientBankWriter, WeightedGradientCache, assign_gradients, load_gradient_bank,
)
from proworksim.online_training import ppo_sum, tensor_tree_digest
from proworksim.storage import atomic_write, digest, json_bytes

VERSION = "tiny-qwen-gradient-reuse-qualification-v0.37"
GATES = {
    "production_exact_weight_cache": "bitwise equal gradients, clipped gradients, parameters and optimizer state",
    "unit_weights": "bitwise equal gradients, clipped gradients, parameters and optimizer state",
    "weighted_gradient": {"max_abs": 2e-6, "relative_l2": 1e-5, "minimum_cosine": 1 - 1e-7},
    "weighted_state": {"max_abs": 2e-6, "relative_l2": 1e-5, "minimum_cosine": 1 - 1e-7},
    "critic": "bitwise equal gradients, parameters and optimizer state for every weight vector",
}
WEIGHTS = {"B": [1.0, 1.0, 1.0], "weighted": [1.3, 0.7, 1.0]}


def _tensor_metrics(reference, actual, torch):
    """Report both absolute and relative errors, including zero-vector behavior."""
    a, b = reference.detach().double().flatten().cpu(), actual.detach().double().flatten().cpu()
    if a.shape != b.shape:
        raise ValueError("Compared tensor shapes differ")
    delta = b - a
    denominator = float(a.norm())
    actual_norm = float(b.norm())
    error = float(delta.norm())
    cosine = (float(torch.dot(a, b)) / (denominator * actual_norm)
              if denominator and actual_norm else (1.0 if not error else 0.0))
    return {"elements": a.numel(), "bitwise_equal": torch.equal(reference, actual),
            "max_abs": float(delta.abs().max()) if a.numel() else 0.0,
            "relative_l2": error / denominator if denominator else (0.0 if not error else None),
            "cosine": max(-1.0, min(1.0, cosine)), "reference_l2": denominator,
            "error_l2": error, "finite": bool(torch.isfinite(a).all() and torch.isfinite(b).all())}


def _flatten(value, torch, prefix=""):
    if isinstance(value, torch.Tensor):
        return {prefix: value}
    if isinstance(value, dict):
        return {name: tensor for key, child in value.items()
                for name, tensor in _flatten(child, torch, prefix + "/" + str(key)).items()}
    if isinstance(value, (tuple, list)):
        return {name: tensor for index, child in enumerate(value)
                for name, tensor in _flatten(child, torch, prefix + "/" + str(index)).items()}
    return {}


def compare_trees(reference, actual, torch, *, exact, gate):
    before, after = _flatten(reference, torch), _flatten(actual, torch)
    if set(before) != set(after) or not before:
        raise ValueError("Compared trees must contain the same nonempty tensor inventory")
    rows = {name: _tensor_metrics(before[name], after[name], torch) for name in before}
    combined = _tensor_metrics(torch.cat([v.detach().double().flatten().cpu() for v in before.values()]),
                               torch.cat([after[n].detach().double().flatten().cpu() for n in before]), torch)
    combined["bitwise_equal"] = all(row["bitwise_equal"] for row in rows.values())
    passed = combined["bitwise_equal"] if exact else (
        combined["finite"] and combined["max_abs"] <= gate["max_abs"]
        and combined["relative_l2"] is not None and combined["relative_l2"] <= gate["relative_l2"]
        and combined["cosine"] >= gate["minimum_cosine"])
    return {"passed": passed, "exact_required": exact, "aggregate": combined, "tensors": rows}


def _fixture(torch, *, profile, device):
    from peft import LoraConfig, get_peft_model
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig

    torch.manual_seed(8037)
    config = Qwen3_5TextConfig(vocab_size=64, hidden_size=32, intermediate_size=64,
        num_hidden_layers=8, num_attention_heads=4, num_key_value_heads=2, head_dim=8,
        linear_key_head_dim=8, linear_value_head_dim=8, linear_num_key_heads=2,
        linear_num_value_heads=2, layer_types=(["linear_attention"] * 3 + ["full_attention"]) * 2,
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
            "partial_rotary_factor": .5, "mrope_section": [1, 1, 0], "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=63, tie_word_embeddings=False)
    config._attn_implementation = "sdpa"
    if device.startswith("cuda"):
        from proworksim.local_model_service import configure_attention_runtime

        configure_attention_runtime("sdpa_explicit_kv", "highest")
        torch.backends.cudnn.allow_tf32 = False
        config._attn_implementation = "sdpa_explicit_kv"
        if profile == "mixed_bf16":
            from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface
            from transformers.modeling_utils import AttentionInterface
            from proworksim.candidate_runtime_v020 import ATTENTION, bf16_attention_forward

            AttentionInterface.register(ATTENTION, bf16_attention_forward)
            AttentionMaskInterface.register(ATTENTION, ALL_MASK_ATTENTION_FUNCTIONS["sdpa"])
            config._attn_implementation = ATTENTION
    dtype = torch.float32 if profile == "fp32" else torch.bfloat16
    base = Qwen3_5ForCausalLM(config).to(device=device, dtype=dtype)
    base.lm_head.float()
    # Same actual FP32 pre-projection promotion as candidate_runtime_v0201.
    base.lm_head.register_forward_pre_hook(lambda _module, args: (args[0].float(),))
    model = get_peft_model(base, LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
        target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"))
    parameters = {n: p for n, p in model.named_parameters() if p.requires_grad}
    with torch.no_grad():
        for name, parameter in parameters.items():
            if parameter.dtype != torch.float32:
                raise ValueError("Tiny trainable LoRA must really remain FP32")
            if "lora_B" in name:
                parameter.normal_(0, .02)
    model.enable_input_require_grads()
    model.train()
    critic = torch.nn.Sequential(torch.nn.Linear(20, 32), torch.nn.Tanh(), torch.nn.Linear(32, 1)).to(device)
    actor_optimizer = torch.optim.AdamW(parameters.values(), lr=1e-5, weight_decay=0)
    critic_optimizer = torch.optim.AdamW(critic.parameters(), lr=1e-3, weight_decay=0)
    # The original common has three optimizer steps. Generate actual nonempty
    # first/second moments with three deterministic fixture-only warmup steps.
    for step in range(3):
        for index, parameter in enumerate(parameters.values()):
            parameter.grad = torch.full_like(parameter, (index + 1) * .001 * (step + 1))
        for index, parameter in enumerate(critic.parameters()):
            parameter.grad = torch.full_like(parameter, (index + 1) * .003 * (step + 1))
        actor_optimizer.step()
        critic_optimizer.step()
    actor_optimizer.zero_grad(set_to_none=True)
    critic_optimizer.zero_grad(set_to_none=True)
    rows = []
    # Both signs and both method classes plus an unaffected residual are covered;
    # prompt length crosses the 64-token chunk and output crosses checkpoint 8.
    for index, (prompt, output, advantage, weight_class) in enumerate(
            [(70, 12, .75, "local"), (73, 11, -.45, "peer"), (67, 4, .2, "residual")]):
        trace = {"input_ids": ((torch.arange(prompt) * 11 + 9 + index) % 61 + 1).tolist(),
                 "output_ids": ((torch.arange(output) * 7 + 4 + index) % 61 + 1).tolist(),
                 "sampling_temperature": .7}
        features = ((torch.arange(20, device=device).float() + index) / 20).tolist()
        with torch.no_grad():
            old = learning_logprobs(model, trace).cpu().tolist()
            value = float(critic(torch.tensor(features, device=device)).squeeze())
        trace["behavior_logprobs"] = old
        rows.append({"call_id": "synthetic-" + str(index), "slot_id": "synthetic-slot",
                     "task": "tiny_qwen_mechanism", "member_id": "member_a",
                     "weight_class": weight_class, "tokens": trace,
                     "critic_features": features, "reward": value + advantage, "advantage": advantage,
                     "actor_denominator": 27, "critic_denominator": 3})
    return model, parameters, critic, actor_optimizer, critic_optimizer, rows


def _snapshot(parameters, critic, actor_optimizer, critic_optimizer, torch):
    return {"actor": {n: p.detach().clone() for n, p in parameters.items()},
            "critic": copy.deepcopy(critic.state_dict()),
            "actor_optimizer": copy.deepcopy(actor_optimizer.state_dict()),
            "critic_optimizer": copy.deepcopy(critic_optimizer.state_dict()),
            "rng_cpu": torch.get_rng_state().clone()}


def _restore(common, parameters, critic, actor_optimizer, critic_optimizer, torch):
    with torch.no_grad():
        for name, parameter in parameters.items():
            parameter.copy_(common["actor"][name])
    critic.load_state_dict(common["critic"])
    actor_optimizer.load_state_dict(copy.deepcopy(common["actor_optimizer"]))
    critic_optimizer.load_state_dict(copy.deepcopy(common["critic_optimizer"]))
    actor_optimizer.zero_grad(set_to_none=True)
    critic_optimizer.zero_grad(set_to_none=True)
    torch.set_rng_state(common["rng_cpu"])


def _grads(parameters):
    return {n: p.grad.detach().clone() for n, p in parameters.items() if p.grad is not None}


def _backward(model, critic, row, weight, torch, device, counters=None):
    probabilities = learning_logprobs(model, row["tokens"])
    if counters is not None:
        counters["actor_forwards"] += 1
    behavior = torch.tensor(row["tokens"]["behavior_logprobs"], device=device)
    loss, _ = ppo_sum(torch, probabilities, behavior, row["advantage"], .2)
    loss = loss / row["actor_denominator"]
    if weight != 1:
        loss = loss * weight
    loss.backward()
    if counters is not None:
        counters["actor_backwards"] += 1
    value = critic(torch.tensor(row["critic_features"], device=device)).squeeze()
    (.5 * (value - row["reward"]).square() / row["critic_denominator"] * .5).backward()


def _step(parameters, critic, actor_optimizer, critic_optimizer, torch):
    result = {"actor_gradient": _grads(parameters), "critic_gradient": _grads(dict(critic.named_parameters()))}
    # A deliberately binding clip exercises global clipping after composition.
    result["actor_preclip_norm"] = float(torch.nn.utils.clip_grad_norm_(list(parameters.values()), .01))
    result["critic_preclip_norm"] = float(torch.nn.utils.clip_grad_norm_(critic.parameters(), .01))
    result["actor_clipped_gradient"] = _grads(parameters)
    actor_optimizer.step()
    critic_optimizer.step()
    result.update(_snapshot(parameters, critic, actor_optimizer, critic_optimizer, torch))
    return result


def qualify_profile(output, *, profile="fp32", device="cpu"):
    import torch

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    model, parameters, critic, ao, co, rows = _fixture(torch, profile=profile, device=device)
    common = _snapshot(parameters, critic, ao, co, torch)
    common_digest = tensor_tree_digest(common, torch)
    binding = {"fixture": VERSION, "profile": profile, "common_sha256": common_digest,
               "gates_sha256": digest(json_bytes(GATES)), "rows_sha256": digest(json_bytes(rows)),
               "normalization": "fixed actor=27 critic=3, original ordered rows"}
    writer = GradientBankWriter(output / "bank", torch=torch, binding=binding, rows=rows,
                                actor_parameters=parameters)
    cache = WeightedGradientCache(output / "exact-weight-cache", torch=torch, binding=binding,
                                  rows=rows, actor_parameters=parameters)
    # Reset actor .grad per row so each stored leaf contribution is isolated.
    # Critic accumulation retains the original row order, unaffected by weights.
    for index, row in enumerate(rows):
        ao.zero_grad(set_to_none=True)
        _backward(model, critic, row, 1.0, torch, device)
        writer.append_actor(index, _grads(parameters))
        cache.put(index, 1.0, _grads(parameters), metadata={"synthetic_control": True})
    manifest = writer.finalize(_grads(dict(critic.named_parameters())), metadata={"tiny_model_only": True})
    bank = load_gradient_bank(output / "bank", torch=torch, expected_binding=binding,
                              expected_rows=rows, expected_manifest_sha256=manifest["manifest_sha256"])
    unit_results, references = {}, {}
    for label, weights in WEIGHTS.items():
        _restore(common, parameters, critic, ao, co, torch)
        for row, weight in zip(rows, weights):
            _backward(model, critic, row, weight, torch, device)
        direct = _step(parameters, critic, ao, co, torch)
        references[label] = direct
        _restore(common, parameters, critic, ao, co, torch)
        assign_gradients(parameters, bank.compose_actor(weights, device=device), torch=torch)
        assign_gradients(dict(critic.named_parameters()), bank.critic_gradients(device=device), torch=torch)
        reused = _step(parameters, critic, ao, co, torch)
        comparisons = {}
        for name in ("actor_gradient", "actor_clipped_gradient", "actor", "actor_optimizer",
                     "critic_gradient", "critic", "critic_optimizer"):
            comparisons[name] = compare_trees(direct[name], reused[name], torch,
                exact=label == "B" or name.startswith("critic"),
                gate=GATES["weighted_gradient" if "gradient" in name else "weighted_state"])
        # AdamW non-tensor settings and integer counters are identity-bound too.
        settings_equal = all(direct[name]["param_groups"] == reused[name]["param_groups"]
                             for name in ("actor_optimizer", "critic_optimizer"))
        unit_results[label] = {"weights": weights, "comparisons": comparisons,
            "optimizer_settings_equal": settings_equal,
            "direct_preclip_norms": {name: direct[name] for name in ("actor_preclip_norm", "critic_preclip_norm")},
            "reused_preclip_norms": {name: reused[name] for name in ("actor_preclip_norm", "critic_preclip_norm")},
            "passed": settings_equal and all(value["passed"] for value in comparisons.values())}
    # Positive candidate: only reuse the gradient of the SAME already-weighted
    # original loss. Scalar multiplication stays before backward on each miss.
    results, counters = {}, {"actor_forwards": 0, "actor_backwards": 0}
    for label, weights in {**WEIGHTS, "weighted_repeated": WEIGHTS["weighted"]}.items():
        _restore(common, parameters, critic, ao, co, torch)
        before_counts, hits, misses = counters.copy(), 0, 0
        for index, (row, weight) in enumerate(zip(rows, weights)):
            if cache.get(index, weight, device=device) is None:
                ao.zero_grad(set_to_none=True)
                _backward(model, critic, row, weight, torch, device, counters)
                cache.put(index, weight, _grads(parameters), metadata={"synthetic_control": True})
                misses += 1
            else:
                hits += 1
        assign_gradients(parameters, cache.compose_actor(weights, device=device), torch=torch)
        assign_gradients(dict(critic.named_parameters()), bank.critic_gradients(device=device), torch=torch)
        reused = _step(parameters, critic, ao, co, torch)
        direct = references["weighted" if label == "weighted_repeated" else label]
        comparisons = {name: compare_trees(direct[name], reused[name], torch, exact=True,
                       gate=GATES["weighted_gradient"])
                       for name in ("actor_gradient", "actor_clipped_gradient", "actor", "actor_optimizer",
                                    "critic_gradient", "critic", "critic_optimizer")}
        observed = {key: counters[key] - before_counts[key] for key in counters}
        settings_equal = all(direct[name]["param_groups"] == reused[name]["param_groups"]
                             for name in ("actor_optimizer", "critic_optimizer"))
        results[label] = {"weights": weights, "comparisons": comparisons, "cache_hits": hits,
            "cache_misses": misses, "actual_compute_calls": observed, "optimizer_settings_equal": settings_equal,
            "passed": settings_equal and all(value["passed"] for value in comparisons.values())
                      and observed == {"actor_forwards": misses, "actor_backwards": misses}}
    report = {"profile": profile, "device": device, "passed": all(r["passed"] for r in results.values()),
              "common_sha256": common_digest, "common_actor_optimizer_steps": [
                  float(state["step"]) for state in common["actor_optimizer"]["state"].values()],
              "nonzero_lora_B": all(bool(p.count_nonzero()) for n, p in parameters.items() if "lora_B" in n),
              "original_decisions": len(rows), "signs": [row["advantage"] for row in rows],
              "bank_manifest_sha256": manifest["manifest_sha256"], "candidates": results,
              "actual_attention_implementation": model.config._attn_implementation,
              "sdpa_backend_policy": "efficient_only_no_fallback" if device.startswith("cuda") else "installed_cpu_sdpa",
              "actual_storage_dtype_elements": {
                  str(dtype): sum(p.numel() for p in model.parameters() if p.dtype == dtype)
                  for dtype in {p.dtype for p in model.parameters()}},
              "candidate": "original weighted-loss gradient cache, no post-backward scaling",
              "unit_rescaling_diagnostic": {"approved_for_production": False,
                  "passed_strict_gate": all(value["passed"] for value in unit_results.values()),
                  "candidates": unit_results,
                  "scope": "Rejected shortcut diagnostic; scalar-after-backward can differ from original mixed-precision scalar-before-backward."},
              "numerical_scope": "Original functional v022 graph; full FP32 or BF16 backbone plus FP32 head/LoRA. CUDA explicitly uses the original efficient-only adapter, with no fallback; CPU uses installed CPU SDPA. This tiny model does not qualify 9B capacity or arbitrary traces."}
    atomic_write(output / "receipt.json", json_bytes(report))
    return report


def qualify(output, *, profiles=("fp32", "mixed_bf16"), device="cpu"):
    import peft
    import torch
    import transformers

    started = time.monotonic()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    previous = torch.get_num_threads(), torch.get_float32_matmul_precision(), torch.get_rng_state()
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    cuda_resource = None
    if device.startswith("cuda"):
        properties = torch.cuda.get_device_properties(device)
        torch.cuda.reset_peak_memory_stats(device)
        cuda_resource = {"logical_device": device, "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
            "device_name": properties.name, "device_capability": list(torch.cuda.get_device_capability(device)),
            "device_total_memory_bytes": properties.total_memory,
            "actual_torch_cuda_version": torch.version.cuda,
            "baseline_allocated_bytes": torch.cuda.memory_allocated(device),
            "baseline_reserved_bytes": torch.cuda.memory_reserved(device)}
    try:
        # Persist the gate before any model fixture is constructed or measured.
        atomic_write(output / "frozen-gates.json", json_bytes({"version": VERSION, "gates": GATES, "weights": WEIGHTS}))
        results = [qualify_profile(output / profile, profile=profile, device=device) for profile in profiles]
    finally:
        if cuda_resource is not None:
            torch.cuda.synchronize(device)
            cuda_resource.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(device),
                                 peak_reserved_bytes=torch.cuda.max_memory_reserved(device))
            atomic_write(output / "cuda-resource.json", json_bytes(cuda_resource))
        torch.set_num_threads(previous[0])
        torch.set_float32_matmul_precision(previous[1])
        torch.set_rng_state(previous[2])
    root = Path(__file__).resolve().parents[1]
    source_files = [Path(__file__).resolve(), root / "src/proworksim/gradient_bank_v037.py",
                    root / "src/proworksim/functional_qwen_v022.py", root / "src/proworksim/online_training.py"]
    report = {"version": VERSION, "passed": all(result["passed"] for result in results),
              "gates": GATES, "profiles": results, "device": device,
              "cuda_resource": cuda_resource,
              "packages": {"torch": str(torch.__version__), "transformers": transformers.__version__, "peft": peft.__version__},
              "source_sha256": {str(p.relative_to(root)): digest(p.read_bytes()) for p in source_files},
              "elapsed_seconds": time.monotonic() - started, "real_model_loaded": False,
              "real_task_samples": 0, "real_model_optimizer_steps": 0,
              "scope": "Finite synthetic official tiny-Qwen exact-weight-cache mechanism/numerical controls. No 9B capacity qualification, frozen experiment replacement or measured task-training benefit. CUDA controls use the original efficient-only attention adapter. The separate scalar-after-backward diagnostic is not the production candidate; its failed strict gates are preserved."}
    atomic_write(output / "receipt.json", json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", choices=("fp32", "mixed_bf16"), default=["fp32", "mixed_bf16"])
    parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cpu")
    args = parser.parse_args()
    report = qualify(args.output, profiles=args.profiles, device=args.device)
    print(json.dumps({"passed": report["passed"], "profiles": {r["profile"]: r["passed"] for r in report["profiles"]},
                      "receipt": str((args.output / "receipt.json").resolve()), "elapsed_seconds": report["elapsed_seconds"]}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
