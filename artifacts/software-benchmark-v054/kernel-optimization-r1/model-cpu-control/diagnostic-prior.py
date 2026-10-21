"""Bounded pre-service kernel diagnostics on one newly loaded raw model.

The fixed samples contain no benchmark material. Reference functions are used
only before this new resident serves a session. The original actor generation
method and formal contract are never replaced.
"""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import time

from .software_benchmark_candidates_v054 import checked, write_new
from .storage import digest, json_bytes

VERSION = "v054-kernel-model-diagnostic-r1"
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
GATES = {"first_prefill_kl_reference_to_optimized_max": 0.02,
         "first_prefill_logit_nrmse_max": 0.03,
         "all_logits_and_logprobs_finite": True,
         "maximum_requests": 6, "maximum_output_tokens_per_request": 64,
         "maximum_total_tokens": 34432}


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
                        "source": str(Path(inspect.getfile(target)).resolve())}
        current = getattr(current, "__wrapped__", None)
    raise ValueError("Cannot establish the actual kernel decorator implementation")


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


def compare_logits(torch, baseline, candidate):
    if baseline.shape != candidate.shape or not torch.isfinite(candidate).all():
        raise ValueError("Logit shape or finite-value guard failed")
    delta = candidate.float() - baseline.float()
    nrmse = float(delta.square().mean().sqrt() /
                  baseline.float().square().mean().sqrt().clamp_min(1e-6))
    first = baseline.float().log_softmax(-1)
    second = candidate.float().log_softmax(-1)
    kl = float((first.exp() * (first - second)).sum())
    return {"kl_reference_to_optimized": kl, "logit_nrmse": nrmse,
            "max_absolute_logit_difference": float(delta.abs().max()),
            "same_top1": bool(baseline.argmax() == candidate.argmax()),
            "passed": kl <= GATES["first_prefill_kl_reference_to_optimized_max"]
                      and nrmse <= GATES["first_prefill_logit_nrmse_max"]}


def qualify_loaded_owner(owner, plan_reference):
    from transformers.models.qwen3_5 import modeling_qwen3_5 as module
    from .software_calibration_runtime_v051 import CalibrationActor

    plan = json.loads(checked(plan_reference).read_bytes())
    if (plan.get("version") != VERSION or plan.get("requests") != [list(x) for x in REQUESTS]
            or plan.get("gates") != GATES or plan.get("formal_tasks_used") != 0
            or plan.get("weight_update_allowed") is not False):
        raise ValueError("Kernel diagnostic plan differs from its fixed admission design")
    enabled = plan.get("enabled_symbols")
    if not enabled or len(enabled) != len(set(enabled)) or any(x not in SYMBOLS for x in enabled):
        raise ValueError("Kernel selection was not explicitly frozen")
    operator = json.loads(checked(plan["operator_control"]).read_bytes())
    if operator.get("passed") is not True:
        raise ValueError("Independent operator control did not qualify")
    checked(plan["dependencies_manifest"])
    root = Path(plan["diagnostic_output"]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / "started.json", {"version": VERSION, "plan": plan_reference,
        "model_object_id": id(owner.model), "formal_tasks_used": 0,
        "automatic_retry": False, "maximum_requests": 6})
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
    torch = owner.torch
    original_guard = owner.capture_evaluation_state()
    contract = {**owner.contract, "max_output_tokens": 64}
    known_tokens, rows, comparisons, ref_logits = 0, [], {}, {}
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
            first_logits, head_times = [], []

            def observe_head(_module, _inputs, output):
                # CPU collection of one full-vocabulary next-token vector only;
                # no hidden targets, top-k approximation, or output rewriting.
                if not first_logits:
                    value = output.detach().reshape(-1, output.shape[-1])[-1].float().cpu()
                    if not torch.isfinite(value).all():
                        raise ValueError("Non-finite first-prefill logits")
                    first_logits.append(value)
                head_times.append(time.monotonic())

            hook = owner.model.get_output_embeddings().register_forward_hook(observe_head)
            started = time.monotonic()
            write_new(root / label / "intent.json", {"seed": seed, "mode": mode,
                "reserved_tokens": target + 64, "automatic_retry": False})
            try:
                result = clone.generate_native(record)
            finally:
                hook.remove()
            torch.cuda.synchronize()
            elapsed = time.monotonic() - started
            if not first_logits or not all(torch.isfinite(torch.tensor(result["behavior_logprobs"])).tolist()):
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
                "first_logits_sha256": digest(first_logits[0].numpy().tobytes()),
                "guard": guard, "model_object_id": id(owner.model),
                "timing_includes_JIT_when_first_encountered": True,
                "not_a_benchmark_task": True}
            write_new(root / label / "result.json", row)
            rows.append(row)
            if mode == "reference":
                ref_logits[target] = first_logits[0]
            else:
                compared = compare_logits(torch, ref_logits.pop(target), first_logits[0])
                comparisons[str(target)] = compared
                if not compared["passed"]:
                    raise ValueError("Fixed full-vocabulary numerical engineering gate failed")
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
        "formal_tasks_used": 0, "provenance": provenance,
        "numerically_identical_to_reference_claimed": False,
        "task_accuracy_equivalence_claimed": False}
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
