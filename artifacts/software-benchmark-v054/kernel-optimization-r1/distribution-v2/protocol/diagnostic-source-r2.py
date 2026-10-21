"""Bounded pre-service kernel diagnostics on one newly loaded raw model.

The fixed samples contain no benchmark material. Reference functions are used
only before this new resident serves a session. The original actor generation
method and formal contract are never replaced.
"""
from __future__ import annotations

import copy
import inspect
import importlib.util
import json
import os
import sys
from pathlib import Path
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .storage import atomic_write, digest, json_bytes

VERSION = "v054-kernel-model-diagnostic-r2"
SAMPLING = {"temperature": 0.7, "top_k": 0, "top_p": 1.0}
REVISION = {"post_observation_protocol_revision": True,
            "independent_confirmation_claimed": False,
            "formal_task_results_used_for_selection": False,
            "original_failed_results_preserved": True}
PREPARATION_BUDGET = {"previous_actual_requests": 6, "previous_actual_tokens": 1920,
                      "new_diagnostic_maximum_requests": 6,
                      "new_diagnostic_maximum_tokens": 34432,
                      "interleave_maximum_requests": 6,
                      "interleave_maximum_tokens": 61440,
                      "cumulative_maximum_tokens": 97792, "preparation_token_limit": 100000}
SYMBOLS = ("causal_conv1d_fn", "causal_conv1d_update",
           "torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule")
REQUESTS = (
    ("warm_reference", "reference", 128, 202610210601),
    ("warm_optimized", "optimized", 128, 202610210601),
    ("short_reference", "reference", 512, 202610210602),
    ("short_optimized", "optimized", 512, 202610210602),
    ("long_reference", "reference", 16384, 202610210603),
    ("long_optimized", "optimized", 16384, 202610210603),
)
GATES = {"sampling": SAMPLING,
         "full_vocabulary_kl_reference_to_optimized_max": 1e-4,
         "full_vocabulary_max_abs_probability_difference_max": 5e-4,
         "original_raw_temperature": 1.0,
         "original_kl_reference_to_optimized_max": 0.02,
         "original_logit_nrmse_max": 0.03,
         "original_gate_required_for_admission": False,
         "all_logits_and_logprobs_finite": True,
         "maximum_requests": 6, "maximum_output_tokens_per_request": 64,
         "maximum_total_tokens": 34432}
REQUIRED_ENVIRONMENT = {"TRITON_LIBCUDA_PATH": "/opt/host-nvidia",
                        "FLA_DISABLE_TENSOR_CACHE": "1", "USE_HUB_KERNELS": "NO"}


def implementation(symbol):
    """Inspect the decorator's real callable, not its copied __module__."""
    current, seen = symbol, set()
    while callable(current) and id(current) not in seen:
        seen.add(id(current))
        if inspect.isfunction(current):
            values = inspect.getclosurevars(current).nonlocals
            if "implementation" in values and "is_new_implementation" in values:
                target = values["implementation"]
                return {"optimized": values["is_new_implementation"] is True,
                        "module": target.__module__,
                        "source": str(Path(inspect.getsourcefile(inspect.unwrap(target))).resolve()),
                        "wrapper_source": str(Path(inspect.getfile(target)).resolve())}
        current = getattr(current, "__wrapped__", None)
    raise ValueError("Cannot establish the actual kernel decorator implementation")


_INSTALLATION = None


def install_plan_kernels(plan_reference):
    """Install one hash-pinned recurrent implementation before model loading."""
    global _INSTALLATION
    if _INSTALLATION is not None:
        if _INSTALLATION["plan"] != plan_reference:
            raise ValueError("One process cannot install two kernel plans")
        return copy.deepcopy(_INSTALLATION)
    plan = json.loads(checked(plan_reference).read_bytes())
    entry = plan["kernel_install_entrypoint"]
    path = checked(entry["reference"]).resolve()
    overlay = Path(plan["overlay_path"]).resolve()
    if (not path.is_relative_to(overlay) or entry.get("module") != "proworksim_fp32_recurrent"
            or entry.get("function") != "install" or path.name != entry["module"] + ".py"
            or plan.get("enabled_symbols") != ["torch_recurrent_gated_delta_rule"]):
        raise ValueError("Only the explicitly pinned recurrent-only custom installer is allowed")
    checked(plan["dependencies_manifest"])
    if entry["module"] in sys.modules:
        raise ValueError("Kernel installer module was already loaded outside this plan")
    spec = importlib.util.spec_from_file_location(entry["module"], path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[entry["module"]] = module
    spec.loader.exec_module(module)
    result = getattr(module, entry["function"])()
    from transformers.models.qwen3_5 import modeling_qwen3_5 as modeling
    selected = {name: implementation(getattr(modeling, name)) for name in SYMBOLS}
    for name, observed in selected.items():
        if observed["optimized"] != (name == "torch_recurrent_gated_delta_rule"):
            raise ValueError("Installer selected an unexpected optimized symbol: " + name)
    source = Path(selected["torch_recurrent_gated_delta_rule"]["source"])
    if source != path or reference(source) != entry["reference"]:
        raise ValueError("Installed recurrent callable differs from the pinned custom source")
    _INSTALLATION = {"plan": plan_reference, "entrypoint": entry, "installed_once": True,
                     "installer_result": result, "actual_symbols": selected,
                     "installation_precedes_model_load": True}
    return copy.deepcopy(_INSTALLATION)


def fixed_prompt(actor, target):
    from .software_calibration_runtime_v051 import prepare_native_input
    request = {"model": "kernel-preparation-only", "messages": [
        {"role": "system", "content": "This is synthetic runtime preparation, with no repository or task."},
        {"role": "user", "content": ""}], "temperature": 0.7,
        "max_tokens": 64, "stream": False}
    prefix = "Ignore the filler. Count from 1 to 100, separated by commas. Filler:\n"
    suffix = "\nNow start counting from 1."
    low, high = 0, target
    for _ in range(20):
        middle = (low + high) // 2
        request["messages"][-1]["content"] = prefix + " x" * middle + suffix
        record = prepare_native_input(actor.tokenizer, request, actor.contract)
        length = record["prompt_tokens"]
        if length == target:
            return record
        if length < target:
            low = middle + 1
        else:
            high = middle - 1
    raise ValueError("Fixed exact synthetic input length was not constructible")


def logit_summary(torch, value):
    finite = bool(torch.isfinite(value).all())
    return {"sha256": digest(value.numpy().tobytes()), "vocabulary_size": int(value.numel()),
            "finite": finite, "minimum": float(value.min()) if finite else None,
            "maximum": float(value.max()) if finite else None,
            "rms": float(value.square().mean().sqrt()) if finite else None}


def compare_logits(torch, baseline, candidate):
    """Compare the actual unfiltered T=.7 distribution; retain the original gate."""
    finite = bool(torch.isfinite(baseline).all() and torch.isfinite(candidate).all())
    if baseline.shape != candidate.shape or not finite:
        return {"passed": False, "original_gate_passed": False,
                "finite": finite, "shape_equal": baseline.shape == candidate.shape,
                "sampling": dict(SAMPLING), "distribution_finite": False,
                "kl_reference_to_optimized": None, "logit_nrmse": None,
                "max_abs_probability_difference": None,
                "reason": "logit_shape_or_finite_guard_failed"}
    delta = candidate.float() - baseline.float()
    nrmse = float(delta.square().mean().sqrt() /
                  baseline.float().square().mean().sqrt().clamp_min(1e-6))
    raw_first = baseline.float().log_softmax(-1)
    raw_second = candidate.float().log_softmax(-1)
    original_kl = float((raw_first.exp() * (raw_first - raw_second)).sum())
    first = (baseline.float() / SAMPLING["temperature"]).log_softmax(-1)
    second = (candidate.float() / SAMPLING["temperature"]).log_softmax(-1)
    distribution_finite = bool(torch.isfinite(first).all() and torch.isfinite(second).all())
    # Float64 accumulation reduces KL cancellation; the log probabilities are
    # computed with the same FP32 temperature/log_softmax order as the sampler.
    kl = float((first.double().exp() * (first.double() - second.double())).sum())
    probability_difference = float((first.exp() - second.exp()).abs().max())
    return {"kl_reference_to_optimized": kl if distribution_finite else None,
            "max_abs_probability_difference": probability_difference if distribution_finite else None,
            "logit_nrmse": nrmse, "original_raw_kl_reference_to_optimized": original_kl,
            "original_gate_passed": original_kl <= GATES["original_kl_reference_to_optimized_max"]
                                    and nrmse <= GATES["original_logit_nrmse_max"],
            "sampling": dict(SAMPLING), "distribution_finite": distribution_finite,
            "finite": finite, "shape_equal": True,
            "max_absolute_logit_difference": float(delta.abs().max()),
            "same_top1": bool(baseline.argmax() == candidate.argmax()),
            "passed": distribution_finite
                      and kl <= GATES["full_vocabulary_kl_reference_to_optimized_max"]
                      and probability_difference <= GATES["full_vocabulary_max_abs_probability_difference_max"]}


def comparison_positions(reference_ids, optimized_ids, reference_heads, optimized_heads):
    """Position k uses output[:k], so the first divergent sample's logits remain comparable."""
    common = 0
    for first, second in zip(reference_ids, optimized_ids):
        if first != second:
            break
        common += 1
    limit = min(len(reference_ids), len(optimized_ids), reference_heads, optimized_heads, common + 1)
    return common, list(range(limit))


def compare_trajectories(torch, baseline, candidate, reference_ids, optimized_ids):
    common, positions = comparison_positions(reference_ids, optimized_ids, len(baseline), len(candidate))
    aligned = len(baseline) == len(reference_ids) and len(candidate) == len(optimized_ids)
    all_finite = all(bool(torch.isfinite(value).all()) for value in [*baseline, *candidate])
    steps = [{"position": index, "phase": "prefill" if index == 0 else "cache_decode",
              "conditioned_on_same_output_prefix": True,
              "reference_logits": logit_summary(torch, baseline[index]),
              "optimized_logits": logit_summary(torch, candidate[index]),
              **compare_logits(torch, baseline[index], candidate[index])} for index in positions]
    return {"compared_positions": positions, "compared_steps": len(steps),
            "common_output_prefix_tokens": common, "same_output_ids": reference_ids == optimized_ids,
            "reference_output_count": len(reference_ids), "optimized_output_count": len(optimized_ids),
            "reference_head_count": len(baseline), "optimized_head_count": len(candidate),
            "head_output_alignment": aligned, "all_captured_logits_finite": all_finite,
            "first_divergent_output_position": common if common < min(len(reference_ids), len(optimized_ids)) else None,
            "condition_after_first_divergent_sample_excluded": True,
            "same_output_ids_required": False, "sampling_or_generation_modified": False,
            "sampling": dict(SAMPLING), "gates": copy.deepcopy(GATES),
            "original_gate_passed": bool(steps) and aligned and all_finite
                                    and all(x["original_gate_passed"] for x in steps),
            "steps": steps, "passed": bool(steps) and aligned and all_finite and all(x["passed"] for x in steps)}


def persist_pair_comparison(root, target, compared, comparisons):
    """Persist rejection evidence before raising the revised engineering gate."""
    comparisons[str(target)] = compared
    write_new(root / ("comparisons-" + str(target) + ".json"), compared)
    atomic_write(root / "comparisons.json", json_bytes(comparisons))
    if not compared["passed"]:
        raise ValueError("Fixed full-vocabulary numerical engineering gate failed")


def qualify_loaded_owner(owner, plan_reference):
    from transformers.models.qwen3_5 import modeling_qwen3_5 as module
    from .software_calibration_runtime_v051 import CalibrationActor

    plan = json.loads(checked(plan_reference).read_bytes())
    if (plan.get("version") != VERSION or plan.get("requests") != [list(x) for x in REQUESTS]
            or plan.get("gates") != GATES or plan.get("revision") != REVISION
            or plan.get("preparation_budget") != PREPARATION_BUDGET
            or plan.get("formal_tasks_used") != 0
            or plan.get("weight_update_allowed") is not False
            or plan.get("required_environment") != REQUIRED_ENVIRONMENT
            or any(os.environ.get(key) != value for key, value in REQUIRED_ENVIRONMENT.items())):
        raise ValueError("Kernel diagnostic plan differs from its fixed admission design")
    if any(owner.contract.get(key) != value for key, value in SAMPLING.items()):
        raise ValueError("Actual owner sampling differs from the fixed T=.7 unfiltered distribution")
    enabled = plan.get("enabled_symbols")
    if _INSTALLATION is None or _INSTALLATION["plan"] != plan_reference:
        raise ValueError("Pinned kernel installation must precede original model loading")
    if not enabled or len(enabled) != len(set(enabled)) or any(x not in SYMBOLS for x in enabled):
        raise ValueError("Kernel selection was not explicitly frozen")
    operator = json.loads(checked(plan["operator_control"]).read_bytes())
    if (operator.get("passed") is not True
            or set(operator.get("qualified_symbols", [])) != set(enabled)
            or operator.get("dependency_manifest") != plan["dependencies_manifest"]):
        raise ValueError("Independent operator control did not qualify")
    checked(plan["dependencies_manifest"])
    root = Path(plan["diagnostic_output"]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / "started.json", {"version": VERSION, "plan": plan_reference,
        "model_object_id": id(owner.model), "formal_tasks_used": 0,
        "automatic_retry": False, "maximum_requests": 6,
        "revision": REVISION, "gates": GATES, "preparation_budget": PREPARATION_BUDGET})
    selected = {name: getattr(module, name) for name in SYMBOLS}
    originals = {name: inspect.unwrap(value) for name, value in selected.items()}
    provenance = {name: implementation(value) for name, value in selected.items()}
    overlay = Path(plan["overlay_path"]).resolve()
    for name in SYMBOLS:
        if provenance[name]["optimized"] != (name in enabled):
            raise ValueError("Actual optimized kernel selection differs: " + name)
        if name in enabled and not Path(provenance[name]["source"]).is_relative_to(overlay):
            raise ValueError("An optimized kernel came from outside the frozen overlay")
        if originals[name].__module__ != module.__name__:
            raise ValueError("Original reference implementation could not be established")
    write_new(root / "kernel-provenance.json", provenance)
    installation_ref = write_new(root / "kernel-installation.json", _INSTALLATION)
    torch = owner.torch
    original_guard = owner.capture_evaluation_state()
    contract = {**owner.contract, "max_output_tokens": 64}
    known_tokens, rows, comparisons, ref_logits = 0, [], {}, {}
    ref_outputs = {}
    complete = False
    try:
        for label, mode, target, seed in REQUESTS:
            for name in SYMBOLS:
                setattr(module, name, originals[name] if mode == "reference" else selected[name])
            clone = CalibrationActor(owner.model, owner.tokenizer, contract=contract, path=owner.path,
                output=root / label / "actor", identity=copy.deepcopy(owner.freeze_identity()),
                torch_module=torch, head_execution=owner.head_execution)
            record = fixed_prompt(clone, target)
            write_new(root / label / "input.json", record)
            state = clone.capture_evaluation_state()
            clone.begin_window("kernel-diagnostic-" + label)
            clone.reseed(seed, label=label)
            captured_logits, head_times = [], []

            def observe_head(_module, _inputs, output):
                # At most 64 complete next-token vectors in CPU memory, never
                # serialized. Capture does not change logits or sampled output.
                if len(captured_logits) >= GATES["maximum_output_tokens_per_request"]:
                    raise ValueError("Observed more than the fixed 64 output-head steps")
                value = output.detach().reshape(-1, output.shape[-1])[-1].float().cpu().clone()
                captured_logits.append(value)
                head_times.append(time.monotonic())

            hook = owner.model.get_output_embeddings().register_forward_hook(observe_head)
            started = time.monotonic()
            write_new(root / label / "intent.json", {"seed": seed, "mode": mode,
                "reserved_tokens": target + 64, "automatic_retry": False})
            try:
                result = clone.generate_native(record)
            finally:
                hook.remove()
                write_new(root / label / "head-logits-summary.json", {
                    "steps": [logit_summary(torch, value) for value in captured_logits],
                    "vectors_persisted": False, "maximum_vectors": 64})
            torch.cuda.synchronize()
            elapsed = time.monotonic() - started
            if not captured_logits or not all(torch.isfinite(torch.tensor(result["behavior_logprobs"])).tolist()):
                raise ValueError("Missing prefill vector or non-finite actual sampling trace")
            if result["usage"] != {"prompt_tokens": target,
                    "completion_tokens": len(result["output_ids"]),
                    "total_tokens": target + len(result["output_ids"])}:
                raise ValueError("Actual model IDs and token ledger differ")
            known_tokens += result["usage"]["total_tokens"]
            if known_tokens > GATES["maximum_total_tokens"]:
                raise ValueError("Independent diagnostic token budget exceeded")
            clone.finish_evaluation([], root / label / "close")
            guard = clone.finish_evaluation_guard(state)
            if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                raise ValueError("Preparation did not restore its exact read-only guard")
            row = {"label": label, "mode": mode, "prompt_tokens": target,
                "seed": seed, "usage": result["usage"], "finish_reason": result["finish_reason"],
                "wall_seconds": elapsed, "native_seconds": result["seconds"],
                "head_calls": len(head_times),
                "first_head_seconds": head_times[0] - started,
                "after_first_head_seconds": head_times[-1] - head_times[0],
                "decode_cadence_seconds": ((head_times[-1] - head_times[0]) / (len(head_times)-1)
                                            if len(head_times) > 1 else None),
                "output_ids_sha256": digest(json_bytes(result["output_ids"])),
                "first_logits_sha256": digest(captured_logits[0].numpy().tobytes()),
                "captured_logits_count": len(captured_logits),
                "head_logit_summaries": reference(root / label / "head-logits-summary.json"),
                "guard": guard, "model_object_id": id(owner.model),
                "timing_includes_JIT_when_first_encountered": True,
                "not_a_benchmark_task": True}
            write_new(root / label / "result.json", row)
            rows.append(row)
            if mode == "reference":
                ref_logits[target] = captured_logits
                ref_outputs[target] = result["output_ids"]
            else:
                compared = compare_trajectories(torch, ref_logits.pop(target), captured_logits,
                                               ref_outputs.pop(target), result["output_ids"])
                persist_pair_comparison(root, target, compared, comparisons)
        complete = True
    finally:
        for name, value in selected.items():
            setattr(module, name, value)
        restored = owner.finish_evaluation_guard(original_guard)
        write_new(root / "closure.json", {"finished_all_requests": complete,
            "completed_requests": len(rows), "known_actual_tokens": known_tokens,
            "guard": restored, "optimized_functions_restored": all(
                getattr(module, name) is value for name, value in selected.items()),
            "unknown_attempt_not_zeroed": not complete, "automatic_retry": False})
    if not restored["learning_unchanged"] or not restored["rng_restored_exactly"]:
        raise ValueError("Original model preparation state was not restored")
    result = {"version": VERSION, "passed": True, "plan": plan_reference,
        "requests": rows, "comparisons": comparisons, "actual_model_requests": len(rows),
        "known_actual_tokens": known_tokens, "complete_actual_tokens": known_tokens,
        "model_loads": 1, "same_model_object": True, "new_parameter_updates": 0,
        "formal_tasks_used": 0, "provenance": provenance, "kernel_installation": installation_ref,
        "numerically_identical_to_reference_claimed": False,
        "task_accuracy_equivalence_claimed": False,
        "original_gate_is_diagnostic": True,
        "original_gate_passed": all(x["original_gate_passed"] for x in comparisons.values()),
        "revision": REVISION, "gates": GATES, "preparation_budget": PREPARATION_BUDGET}
    result_ref = write_new(root / "receipt.json", result)
    # A new identity is issued only after the original read-only guard closes.
    kernel_identity = {"plan": plan_reference, "qualification": result_ref,
                       "enabled_symbols": enabled, "version": VERSION}
    owner.inference_profile["kernel_runtime"] = kernel_identity
    owner.inference_profile_sha256 = digest(json_bytes(owner.inference_profile))
    owner._identity.update(kernel_runtime=kernel_identity,
        inference_profile_sha256=owner.inference_profile_sha256)
    owner._identity.pop("policy_version", None)
    owner._identity["policy_version"] = "calibration:" + digest(json_bytes(owner._identity))
    write_new(owner.output / "kernel-runtime.json", {"kernel_runtime": kernel_identity,
        "actor_identity": owner.freeze_identity(), "formal_contract_unchanged": owner.contract})
    return result_ref
