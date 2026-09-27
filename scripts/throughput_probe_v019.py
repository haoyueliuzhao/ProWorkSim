"""Bounded real-request execution diagnostics; no world rewards or optimizer steps."""

import argparse
import copy
import time
import types
from pathlib import Path

from proworksim.storage import atomic_write, digest, json_bytes, read_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--devices", type=int, required=True)
    p.add_argument("--request-record", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-output", type=int, default=64)
    p.add_argument("--include-high-diagnostic", action="store_true")
    p.add_argument("--backward-all", action="store_true")
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    import torch
    from proworksim.audit import code_identity

    source_before = code_identity()
    from proworksim.candidate_runtime_v019 import CandidateActor, candidate_profile
    from proworksim.prefix_cache_v019 import ExactPrefixCache
    from proworksim.online_training import SharedActor, reference

    owner = CandidateActor.from_candidate(
        a.model,
        manifest=a.manifest,
        profile=candidate_profile(a.candidate, devices=a.devices),
        output=a.output / "resident",
        recipe={
            "seed": 2026093041,
            "max_length": 16384,
            "max_output_tokens": 2048,
            "diagnostic_max_groups": 0,
            "post_update_max_decisions": 0,
            "max_rss_bytes": 192 * 1024**3,
        },
    )
    initial_profile = copy.deepcopy(owner.inference_profile)
    variants = [("fp32-highest-baseline", "highest", 0), ("fp32-high-prefix2048", "high", 2048)]
    if a.include_high_diagnostic:
        variants += [
            ("fp32-highest-prefix2048", "highest", 2048),
            ("fp32-high-diagnostic", "high", 0),
        ]
    report = {
        "version": "bounded-throughput-probe-v0.19",
        "candidate": a.candidate,
        "requests": [reference(p) for p in a.request_record],
        "max_output_override": a.max_output,
        "world_actions": 0,
        "optimizer_steps": 0,
        "source_before": source_before,
        "sampling_seed_base": 202609271900,
        "scope": "Diagnostic resampling of fixed public original requests; not an episode, capacity certification, old reward repair or learning gain. High is an explicit separate numerical candidate and cannot be deployed without original gates.",
        "variants": [],
    }
    baseline_outputs = {}
    baseline_traces = {}
    for name, precision, prefix in variants:
        torch.set_float32_matmul_precision(precision)
        owner.prefix_cache.clear()
        owner.inference_profile = {
            **copy.deepcopy(initial_profile),
            "diagnostic_execution_variant": name,
            "matmul_precision": precision,
            "actual_float32_matmul_precision": torch.get_float32_matmul_precision(),
            "cuda_matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
            "prefix_cache": {"prefix_tokens": prefix, "max_entries": 8},
        }
        owner.inference_profile_sha256 = digest(json_bytes(owner.inference_profile))
        owner._identity = owner._make_identity()
        if prefix:
            owner.prefix_cache = ExactPrefixCache(
                prefix_tokens=prefix, max_entries=8, matmul_precision=precision
            )
            owner._generate_tokens = types.MethodType(CandidateActor._generate_tokens, owner)
        else:
            owner._generate_tokens = types.MethodType(SharedActor._generate_tokens, owner)
        variant = {
            "name": name,
            "precision": precision,
            "prefix_tokens": prefix,
            "actual_profile": copy.deepcopy(owner.inference_profile),
            "actor_identity": owner.freeze_identity(),
            "calls": [],
        }
        report["variants"].append(variant)
        owner.begin_window("diagnostic-" + name)
        for i, path in enumerate(a.request_record):
            original = read_json(path)
            request = copy.deepcopy(original["request"])
            request["max_tokens"] = a.max_output
            for repeat in range(2):
                owner.reseed(202609271900 + i, label=f"{name}-{i}-{repeat}")
                for gpu in range(torch.cuda.device_count()):
                    torch.cuda.synchronize(gpu)
                started = time.perf_counter()
                response = owner.complete(request, timeout_seconds=600)
                for gpu in range(torch.cuda.device_count()):
                    torch.cuda.synchronize(gpu)
                row = {
                    "request": reference(path),
                    "repeat": repeat,
                    "http_status": response["http_status"],
                    "wall_seconds": time.perf_counter() - started,
                    "response_id": response["body"].get("id"),
                    "service": response["body"].get("service_record"),
                    "usage": response["body"].get("usage"),
                }
                variant["calls"].append(row)
                if response["http_status"] != 200:
                    row["error"] = response["body"]
                    atomic_write(a.output / "report.json", json_bytes(report))
                    continue
                trace = response["body"]["token_trace"]
                if name == "fp32-highest-baseline":
                    baseline_outputs[i] = trace["output_ids"]
                row["same_output_as_highest_baseline"] = trace[
                    "output_ids"
                ] == baseline_outputs.get(i)
                if repeat == 1:
                    owner.model.eval()
                    t = time.perf_counter()
                    with torch.no_grad():
                        replay = owner.learning_logprobs(trace)
                    actual = replay.detach().cpu()
                    behavior = torch.tensor(trace["behavior_logprobs"])
                    difference = (actual - behavior).abs()
                    row["behavior_check"] = {
                        "max_abs": float(difference.max()),
                        "mean_abs": float(difference.mean()),
                        "passed": bool(difference.max() <= 0.02 and difference.mean() <= 0.002),
                        "max_atol": 0.02,
                        "mean_atol": 0.002,
                        "seconds": time.perf_counter() - t,
                    }
                    del replay, actual, behavior, difference
                    if name == "fp32-highest-baseline":
                        baseline_traces[i] = copy.deepcopy(trace)
                        reference_seconds = row["behavior_check"]["seconds"]
                    else:
                        # Compare identical original input AND output token work,
                        # even if the new numerical profile samples a different suffix.
                        t = time.perf_counter()
                        with torch.no_grad():
                            reference_values = owner.learning_logprobs(baseline_traces[i])
                        for gpu in range(torch.cuda.device_count()):
                            torch.cuda.synchronize(gpu)
                        reference_seconds = time.perf_counter() - t
                        del reference_values
                    same_work = baseline_traces[i]
                    row["fixed_work_replay"] = {
                        "token_sha256": digest(
                            json_bytes([same_work["input_ids"], same_work["output_ids"]])
                        ),
                        "input_tokens": len(same_work["input_ids"]),
                        "output_tokens": len(same_work["output_ids"]),
                        "seconds": reference_seconds,
                        "scope": "Same baseline actual input/output sequence; extra diagnostic forward only, not a replacement behavior probability",
                    }
                    # One actual full-input backward for each variant, no optimizer step.
                    if (i == 0 or a.backward_all) and row["behavior_check"]["passed"]:
                        owner.prefix_cache.clear()
                        owner.model.train()
                        owner.actor_optimizer.zero_grad(set_to_none=True)
                        t = time.perf_counter()
                        gradlogps = owner.learning_logprobs(trace)
                        grad_difference = (
                            gradlogps.detach().cpu() - torch.tensor(trace["behavior_logprobs"])
                        ).abs()
                        (-gradlogps.mean()).backward()
                        for gpu in range(torch.cuda.device_count()):
                            torch.cuda.synchronize(gpu)
                        gradients = [
                            v.grad for v in owner.actor_parameters.values() if v.grad is not None
                        ]
                        row["backward_check"] = {
                            "seconds": time.perf_counter() - t,
                            "max_abs": float(grad_difference.max()),
                            "mean_abs": float(grad_difference.mean()),
                            "original_probability_passed": bool(
                                grad_difference.max() <= 0.02 and grad_difference.mean() <= 0.002
                            ),
                            "finite": all(bool(torch.isfinite(g).all()) for g in gradients),
                            "nonzero_elements": sum(int(torch.count_nonzero(g)) for g in gradients),
                            "optimizer_steps": 0,
                        }
                        owner.actor_optimizer.zero_grad(set_to_none=True)
                        owner.model.eval()
                        del gradlogps, grad_difference, gradients
                atomic_write(a.output / "report.json", json_bytes(report))
                print(
                    json_bytes(
                        {
                            "variant": name,
                            "request": i,
                            "repeat": repeat,
                            "seconds": row["wall_seconds"],
                            "behavior": row.get("behavior_check"),
                            "backward": row.get("backward_check"),
                            "same_output": row["same_output_as_highest_baseline"],
                        }
                    ).decode(),
                    flush=True,
                )
        owner.finish_evaluation([], a.output / name / "closed")
        variant["status"] = "complete"
    report["status"] = "complete"
    report["source_after"] = code_identity()
    report["source_unchanged"] = source_before == report["source_after"]
    atomic_write(a.output / "report.json", json_bytes(report))


if __name__ == "__main__":
    main()
