"""One explicitly bounded first-decision REINFORCE LoRA update.

The three episode names are fixed before viewing rewards. Only each first actual
local-base generation is differentiated; all later behavior is fixed continuation.
This is neither full multi-turn Agentic RL nor a learning-gain comparison.
GPU imports and computation occur only in main after immutable input admission.
"""

import argparse
import copy
import gc
import hashlib
import inspect
import json
import math
import os
import subprocess
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import assess_historical_episode
from proworksim.rewards import episode_reward
from proworksim.storage import atomic_write, json_bytes, read_json

VERSION = "first-decision-reinforce-v0.11"
REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"
EPISODE_NAMES = ["finance-direct-qwen-1", "finance-direct-qwen-2", "finance-direct-qwen-3"]
ROLE, NODE = "analyst", "FINANCE::reconcile"
BASELINE, TEMPERATURE = 0.5, 0.3
PROCESS = [
    {
        "requirement_id": "source-adoption",
        "kind": "required_source_adoption",
        "work_node": NODE,
        "aliases": ["ledger", "statement", "definitions"],
    }
]
REWARD = {
    "version": "reward-spec-v0.11",
    "reward_id": "first-decision-finance-v011",
    "objectives": [{"kind": "content", "work_node": NODE, "weight": 1}],
    "process_requirements": ["source-adoption"],
}


def sha_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def file_reference(path):
    path = Path(path)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha_file(path)}


def resources():
    result = {
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        "recorded_at": time.time(),
        "shared_gpu_authorized": True,
    }
    for key, command in {
        "gpu": [
            "nvidia-smi",
            "--query-gpu=index,name,memory.used,memory.free,utilization.gpu",
            "--format=csv",
        ],
        "compute_processes": [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv",
        ],
    }.items():
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=20, check=False
            )
            result[key] = {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            result[key] = {"error_type": type(error).__name__, "message": str(error)}
    return result


def extract_first_decision(manifest, history, reward, *, capture_matches, max_length=8192):
    """Pure admission of saved actual token records; never tokenize report text."""
    record = {
        "episode_id": manifest.get("episode_id"),
        "eligible": False,
        "exclusions": [],
        "reward_result": copy.deepcopy(reward),
        "reward": reward.get("reward"),
        "role": ROLE,
    }
    if (
        not isinstance(capture_matches, dict)
        or not capture_matches
        or any(value is not True for value in capture_matches.values())
    ):
        record["exclusions"].append(
            {"kind": "public_capture_unverified", "actual_matches": copy.deepcopy(capture_matches)}
        )
        return record
    if not reward.get("eligible"):
        record["exclusions"].append(
            {"kind": "reward_ineligible", "reasons": copy.deepcopy(reward.get("exclusions", []))}
        )
        return record
    if (
        type(reward.get("reward")) not in (int, float)
        or not math.isfinite(reward["reward"])
        or not 0 <= reward["reward"] <= 1
    ):
        raise ValueError("Eligible reward must preserve an actual finite result")
    policy = manifest.get("policies", {}).get(ROLE, {})
    config = policy.get("config", {})
    if (
        policy.get("implementation") != "proworksim.model_policy.ModelPolicy"
        or config.get("backend_id") != "local-qwen-http"
        or config.get("model") != "Qwen2.5-7B-Instruct"
        or config.get("model_revision") != REVISION
        or config.get("temperature") != TEMPERATURE
        or config.get("action_protocol") != "single_decision_json"
        or not isinstance(config.get("weight_identity"), dict)
    ):
        raise ValueError("Trajectory is not the declared unmodified local Qwen behavior policy")
    identity = config["weight_identity"]
    if (
        set(identity) - {"path", "manifest", "manifest_sha256"}
        or not {"path", "manifest"} <= set(identity)
        or any(not isinstance(value, str) or not value for value in identity.values())
    ):
        raise ValueError(
            "Behavior identity must identify only immutable base files, without an updated adapter"
        )
    if NODE not in manifest.get("responsibility", {}).get("work_nodes", []):
        raise ValueError("Episode did not predeclare this financial work-node responsibility")
    if manifest.get("status") != "closed" or reward.get("episode_id") != manifest["episode_id"]:
        raise ValueError("Reward does not bind this closed episode")
    interval = manifest["experience"]
    events = history["events"][interval["start"] : interval["end"]]
    starts = [
        event
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_call"
        and event["payload"].get("stage") == "started"
    ]
    if not starts:
        record["exclusions"].append({"kind": "no_actual_first_model_decision"})
        return record
    first = starts[0]["payload"]
    if first.get("decision_index") != 1 or first.get("model_revision") != REVISION:
        raise ValueError("Episode prefix is not the first draw from the declared base policy")
    call_id = first["call_id"]
    attempts = [
        event["payload"]
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_attempt"
        and event["payload"].get("call_id") == call_id
        and event["payload"].get("stage") == "finished"
    ]
    if len(attempts) != 1 or attempts[0].get("status") != "success":
        record["exclusions"].append(
            {
                "kind": "first_decision_service_retry_or_unavailable",
                "attempt_statuses": [a.get("status") for a in attempts],
            }
        )
        return record
    responses = [
        event
        for event in events
        if event.get("worker_id") == ROLE
        and event.get("kind") == "model_response"
        and event["payload"].get("call_id") == call_id
    ]
    if len(responses) != 1:
        record["exclusions"].append({"kind": "first_actual_model_response_unavailable"})
        return record
    response = responses[0]["payload"]["response"]
    if response != attempts[0]["response"]["body"]:
        raise ValueError("Recorded completion differs from its actual transport response")
    if response.get("model") != config["model"] or response.get("system_fingerprint") != REVISION:
        raise ValueError("Actual backend identity differs from declared base weights")
    trace = response.get("token_trace")
    if not isinstance(trace, dict):
        record["exclusions"].append({"kind": "actual_token_trace_missing"})
        return record
    for key in ("input_ids", "output_ids"):
        if (
            not isinstance(trace.get(key), list)
            or not trace[key]
            or any(type(value) is not int or value < 0 for value in trace[key])
        ):
            raise ValueError("Actual token IDs are missing or malformed; never reconstructed")
    n, m = len(trace["input_ids"]), len(trace["output_ids"])
    if trace.get("input_mask") != [0] * n or trace.get("output_mask") != [1] * m:
        raise ValueError("Only full real input-zero/output-one token masks are admitted")
    logs = trace.get("behavior_logprobs")
    if (
        not isinstance(logs, list)
        or len(logs) != m
        or any(type(x) not in (int, float) or not math.isfinite(x) or x > 1e-6 for x in logs)
    ):
        record["exclusions"].append({"kind": "actual_behavior_logprobs_missing_or_invalid"})
        return record
    if (
        trace.get("sampling_temperature") != TEMPERATURE
        or trace.get("sampling_top_p") != 1.0
        or trace.get("sampling_top_k") != 0
    ):
        raise ValueError("Behavior sampling distribution differs from the frozen REINFORCE policy")
    effective = response.get("effective_generation", {})
    if any(
        effective.get(key) != value
        for key, value in {
            "do_sample": True,
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 0,
            "repetition_penalty": 1.0,
        }.items()
    ):
        raise ValueError("Service sampling included an unsupported extra transform")
    if (
        trace.get("source")
        != "actual generation token IDs and sampling logits, not retokenized text"
    ):
        raise ValueError("Token trace lacks the declared actual generation provenance")
    usage = response.get("usage", {})
    if (
        usage.get("prompt_tokens") != n
        or usage.get("completion_tokens") != m
        or usage.get("total_tokens") != n + m
    ):
        raise ValueError("Actual recorded token IDs disagree with observed usage")
    record.update(
        model_call_id=call_id,
        service_completion_id=response["id"],
        model_response_sequence=responses[0]["sequence"],
        policy_identity=copy.deepcopy(policy),
        first_response=copy.deepcopy(response),
        token_trace=copy.deepcopy(trace),
        input_tokens=n,
        output_tokens=m,
        sequence_tokens=n + m,
        labels=[-100] * n + list(trace["output_ids"]),
        loss_mask=[0] * n + [1] * m,
        advantage=reward["reward"] - BASELINE,
        continuation="All subsequent target/model/world/colleague actions are fixed recorded behavior; no gradient through them",
    )
    if n + m > max_length:
        record["exclusions"].append(
            {"kind": "length_limit", "actual": n + m, "maximum": max_length, "truncated": False}
        )
        return record
    record["eligible"] = True
    return record


def compare_logprobs(recomputed, behavior, max_atol, mean_atol):
    if len(recomputed) != len(behavior) or not recomputed:
        raise ValueError("Probability records require equal nonempty token sequences")
    if any(not math.isfinite(value) for value in [*recomputed, *behavior]):
        raise ValueError("Nonfinite token log probability")
    signed = [float(a) - float(b) for a, b in zip(recomputed, behavior)]
    absolute = [abs(value) for value in signed]
    return {
        "recomputed_logprobs": recomputed,
        "actual_behavior_logprobs": behavior,
        "signed_delta": signed,
        "max_abs_delta": max(absolute),
        "mean_abs_delta": sum(absolute) / len(absolute),
        "sequence_sum_delta": sum(signed),
        "max_atol": max_atol,
        "mean_atol": mean_atol,
        "passed": max(absolute) <= max_atol and sum(absolute) / len(absolute) <= mean_atol,
    }


def prepare(episodes, output, max_length):
    if len(episodes) != 3 or [Path(p).resolve().parent.name for p in episodes] != EPISODE_NAMES:
        raise ValueError(
            "Use the three predeclared finance-direct-qwen-1/2/3 episode directories in order"
        )
    rows, source_records = [], []
    for path in episodes:
        path = Path(path).resolve()
        manifest = read_json(path / "manifest.json")
        assessment = assess_historical_episode(path, process_requirements=PROCESS)
        reward = episode_reward(assessment, REWARD)
        case_path = path.parent / "record.json"
        case_record = read_json(case_path) if case_path.is_file() else {}
        capture_matches = case_record.get("public_capture_matches")
        if manifest.get("status") != "closed":
            row = {
                "episode_id": manifest.get("episode_id"),
                "eligible": False,
                "exclusions": [{"kind": "episode_not_closed"}],
                "reward_result": reward,
            }
        else:
            history_path = (path / manifest["experience"]["path"]).resolve()
            if (
                not history_path.is_relative_to(path)
                or sha_file(history_path) != manifest["experience"]["sha256"]
            ):
                raise ValueError("Episode experience differs from its fixed manifest")
            history = read_json(history_path)
            row = extract_first_decision(
                manifest, history, reward, capture_matches=capture_matches, max_length=max_length
            )
            if row["eligible"]:
                before, after = manifest["source_start"], manifest["source_end"]
                if before != after or before.get("code_dirty") is not False:
                    raise ValueError(
                        "Training input is not a frozen unchanged model-development execution"
                    )
            source_records.append(
                {
                    "episode": str(path),
                    "manifest": file_reference(path / "manifest.json"),
                    "experience": file_reference(history_path),
                    "case_record": file_reference(case_path) if case_path.is_file() else None,
                    "public_capture_matches": capture_matches,
                }
            )
        row["case_record"] = file_reference(case_path) if case_path.is_file() else None
        row["public_capture_matches"] = copy.deepcopy(capture_matches)
        row["episode_path"] = str(path)
        row["episode_name"] = path.parent.name
        rows.append(row)
        atomic_write(output / (path.parent.name + "-assessment.json"), json_bytes(assessment))
        atomic_write(output / (path.parent.name + "-reward.json"), json_bytes(reward))
    identities = [row["policy_identity"] for row in rows if row["eligible"]]
    if identities and any(identity != identities[0] for identity in identities):
        raise ValueError("Selected first decisions did not share one unchanged behavior policy")
    result = {
        "predeclared": EPISODE_NAMES,
        "selection": "Not conditioned on success/reward; no replacement episodes",
        "records": rows,
        "source_files": source_records,
        "eligible": sum(row["eligible"] for row in rows),
        "excluded": sum(not row["eligible"] for row in rows),
    }
    atomic_write(output / "targets.json", json_bytes(result))
    return result


def verify_weights(model_path, row):
    model_path = Path(model_path).resolve()
    if (model_path / "adapter_config.json").exists() or any(model_path.glob("adapter_model.*")):
        raise ValueError(
            "Training requires the unmodified base directory, not a pre-updated adapter"
        )
    identity = row["policy_identity"]["config"]["weight_identity"]
    manifest_path = Path(identity["manifest"]).resolve()
    manifest = read_json(manifest_path)
    if (
        identity.get("manifest_sha256") is not None
        and sha_file(manifest_path) != identity["manifest_sha256"]
    ):
        raise ValueError(
            "Behavior weight manifest differs from the hash frozen in model configuration"
        )
    if manifest.get("declared_hf_revision") != REVISION:
        raise ValueError("Weight hash manifest revision differs from behavior")
    files = manifest.get("files", {})
    if not files or not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Full base weight hashes are required")
    checked = {}
    for name, expected in files.items():
        file = (model_path / name).resolve()
        if (
            not file.is_relative_to(model_path)
            or file.stat().st_size != expected["bytes"]
            or sha_file(file) != expected["sha256"]
        ):
            raise ValueError("Base file differs from recorded behavior identity: " + name)
        checked[name] = {"bytes": expected["bytes"], "sha256": expected["sha256"]}
    return {
        "model": str(model_path),
        "revision": REVISION,
        "behavior_weight_manifest": file_reference(manifest_path),
        "checked_files": checked,
        "claim": "Matches declared frozen local service base files; behavior trace has real scores. This is trusted-service provenance, not cryptographic attestation of remote memory.",
    }


def protocol(args):
    return {
        "version": VERSION,
        "episodes": EPISODE_NAMES,
        "reward_spec": REWARD,
        "process_requirements": PROCESS,
        "baseline": BASELINE,
        "loss": "mean admitted episodes [-(reward - 0.5) * sum output-token log p_theta(token|prefix; temperature=0.3)]",
        "sample_scope": "First real target-model generation only; remaining behavior fixed; real failures retained, infrastructure/unknown reward excluded and reported",
        "optimizer": {
            "kind": "AdamW",
            "steps": 1,
            "learning_rate": 1e-6,
            "weight_decay": 0,
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "gradient_clip_norm": 1.0,
        },
        "lora": {
            "r": 8,
            "alpha": 16,
            "dropout": 0,
            "target_modules": ["q_proj", "v_proj"],
            "bias": "none",
        },
        "seed": 20260924,
        "max_length": args.max_length,
        "context_truncation": False,
        "sequence_logprob_normalization": "sum, not mean-token CE",
        "logprob_tolerance": {
            "max_absolute_nats": args.logprob_max_atol,
            "mean_absolute_nats": args.logprob_mean_atol,
            "applied_before_any_update": True,
        },
        "execution": "model.eval with gradients enabled; full causal context, only output targets; whole-forward nonreentrant activation recomputation; no inference generation",
        "not_claimed": [
            "Full multi-turn Agentic RL",
            "Three-arm training comparison",
            "Held-out performance improvement",
            "API provider parameter training",
            "Exact BF16 sampling-probability bitwise equivalence",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", nargs=3, required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--logprob-max-atol", type=float, default=0.2)
    parser.add_argument("--logprob-mean-atol", type=float, default=0.03)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Output requires a new independent destination")
    if args.max_length < 1 or any(
        not math.isfinite(x) or x < 0 for x in (args.logprob_max_atol, args.logprob_mean_atol)
    ):
        parser.error("Invalid fixed length or probability tolerance")
    model_path, output = args.model.resolve(), args.output.resolve()
    protected = [model_path, *[p.resolve() for p in args.episode]]
    if any(output == path or output.is_relative_to(path) for path in protected):
        parser.error("Output must be outside source model and episode archives")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": protocol(args),
        "source_before": code_identity(),
        "started_at": time.time(),
        "resources_before": resources(),
        "training_happened": False,
        "optimizer_steps": 0,
        "learning_gain_measured": False,
    }
    atomic_write(output / "protocol.json", json_bytes(report["protocol"]))

    def save(stage):
        report["stage"] = stage
        atomic_write(output / "progress.json", json_bytes(report))

    try:
        prepared = prepare(args.episode, output, args.max_length)
        admitted = [row for row in prepared["records"] if row["eligible"]]
        report.update(
            selected_episodes=3,
            eligible_episodes=len(admitted),
            excluded_episodes=3 - len(admitted),
            exclusions=[
                {"episode_name": row["episode_name"], "reasons": row["exclusions"]}
                for row in prepared["records"]
                if not row["eligible"]
            ],
        )
        if not admitted:
            report["status"] = "no_eligible_episodes"
            save("admission")
            return 1
        report["base_identity"] = verify_weights(model_path, admitted[0])
        save("validated_inputs")
        if args.prepare_only:
            report["status"] = "prepared_no_training"
            return 0

        import torch
        import transformers
        import peft
        from peft import LoraConfig, PeftModel, get_peft_model, get_peft_model_state_dict
        from safetensors.torch import save_file
        from torch.utils.checkpoint import checkpoint
        from transformers import AutoModelForCausalLM

        if not torch.cuda.is_available():
            raise ValueError(
                "This fixed experiment requires an available CUDA device; no silent CPU fallback"
            )
        torch.manual_seed(20260924)
        torch.set_num_threads(8)
        report["libraries"] = {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
        }
        report["device"] = torch.cuda.get_device_name()
        torch.cuda.reset_peak_memory_stats()

        def load_base():
            network = AutoModelForCausalLM.from_pretrained(
                model_path, local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa"
            ).to("cuda")
            if "logits_to_keep" not in inspect.signature(network.forward).parameters:
                raise ValueError(
                    "Declared model implementation must support output-only logits without cropping context"
                )
            network.config.use_cache = False
            return network

        base = load_base()
        model = get_peft_model(
            base,
            LoraConfig(
                r=8,
                lora_alpha=16,
                lora_dropout=0,
                target_modules=["q_proj", "v_proj"],
                bias="none",
                task_type="CAUSAL_LM",
            ),
        )
        model.eval()  # Evaluation mode controls dropout, NOT autograd.
        parameters = [
            (name, value) for name, value in model.named_parameters() if value.requires_grad
        ]
        if not parameters or any("lora_" not in name for name, _ in parameters):
            raise ValueError("Only the declared LoRA adapter may be trainable")

        def adapter_state(network):
            return {
                name: tensor.detach().cpu().contiguous().clone()
                for name, tensor in get_peft_model_state_dict(network).items()
            }

        def tensor_digest(values):
            hashed = hashlib.sha256()
            for name, tensor in sorted(values.items()):
                hashed.update(json_bytes([name, str(tensor.dtype), list(tensor.shape)]))
                hashed.update(tensor.contiguous().view(torch.uint8).numpy().tobytes())
            return hashed.hexdigest()

        def selected_logprobs(network, row):
            trace = row["token_trace"]
            ids = trace["input_ids"] + trace["output_ids"]
            if max(ids) >= network.config.vocab_size:
                raise ValueError("Recorded token is outside this exact base vocabulary")
            inputs = torch.tensor([ids], device="cuda", dtype=torch.long)
            targets = torch.tensor(trace["output_ids"], device="cuda", dtype=torch.long)
            # m+1 logits: final real input -> output1, ... output(m-1) -> outputm.
            logits = (
                network(
                    input_ids=inputs,
                    attention_mask=torch.ones_like(inputs),
                    use_cache=False,
                    logits_to_keep=len(targets) + 1,
                )
                .logits[0, :-1]
                .float()
                / TEMPERATURE
            )
            if logits.shape[0] != len(targets):
                raise ValueError("Output logit selection did not preserve every target")
            return torch.log_softmax(logits, dim=-1).gather(1, targets[:, None]).squeeze(1)

        before = adapter_state(model)
        save_file(before, output / "adapter-before.safetensors")
        report["before_adapter_sha256"] = tensor_digest(before)
        comparisons = []
        for row in admitted:
            with torch.no_grad():
                actual = selected_logprobs(model, row).cpu().tolist()
            comparison = {
                "episode_name": row["episode_name"],
                **compare_logprobs(
                    actual,
                    row["token_trace"]["behavior_logprobs"],
                    args.logprob_max_atol,
                    args.logprob_mean_atol,
                ),
            }
            comparisons.append(comparison)
        atomic_write(output / "behavior-probability-check.json", json_bytes(comparisons))
        if not all(row["passed"] for row in comparisons):
            report["status"] = "behavior_probability_mismatch"
            save("probability_check_failed_no_update")
            return 1
        report["behavior_probability_checks"] = [
            {
                key: row[key]
                for key in (
                    "episode_name",
                    "max_abs_delta",
                    "mean_abs_delta",
                    "sequence_sum_delta",
                    "passed",
                )
            }
            for row in comparisons
        ]
        optimizer = torch.optim.AdamW(
            [value for _, value in parameters],
            lr=1e-6,
            betas=(0.9, 0.999),
            eps=1e-8,
            weight_decay=0,
        )
        optimizer.zero_grad(set_to_none=True)
        losses = []
        with torch.enable_grad():
            for row in admitted:
                # Nonreentrant activation recomputation works while module.eval
                # remains set; no hidden dropout or mean-token normalization.
                dummy = torch.zeros((), device="cuda", requires_grad=True)
                logp = checkpoint(
                    lambda marker, selected=row, network=model: (
                        selected_logprobs(network, selected) + marker * 0
                    ),
                    dummy,
                    use_reentrant=False,
                )
                loss = -row["advantage"] * logp.sum() / len(admitted)
                if not torch.isfinite(loss):
                    raise ValueError("Nonfinite actual REINFORCE loss")
                loss.backward()
                losses.append(
                    {
                        "episode_name": row["episode_name"],
                        "reward": row["reward"],
                        "advantage": row["advantage"],
                        "output_tokens": len(logp),
                        "logprob_sum": float(logp.detach().sum()),
                        "loss_contribution": float(loss.detach()),
                    }
                )
        gradients = {
            "pre_clip." + name: value.grad.detach().cpu().contiguous().clone()
            for name, value in parameters
            if value.grad is not None
        }
        norm = torch.nn.utils.clip_grad_norm_([value for _, value in parameters], 1.0)
        if not torch.isfinite(norm) or float(norm) == 0:
            raise ValueError("Expected a finite nonzero gradient from the admitted real outcomes")
        gradients.update(
            {
                "post_clip." + name: value.grad.detach().cpu().contiguous().clone()
                for name, value in parameters
                if value.grad is not None
            }
        )
        save_file(gradients, output / "actual-gradients.safetensors")
        atomic_write(output / "losses.json", json_bytes(losses))
        optimizer.step()
        report.update(
            training_happened=True,
            optimizer_steps=1,
            losses=losses,
            total_loss=sum(row["loss_contribution"] for row in losses),
            gradient_norm_before_clip=float(norm),
            gradient_clip_limit=1.0,
            gradient_file=file_reference(output / "actual-gradients.safetensors"),
        )
        after = adapter_state(model)
        report["after_adapter_sha256"] = tensor_digest(after)
        report["changed_adapter_elements"] = sum(
            int((after[name] != before[name]).sum()) for name in after
        )
        if (
            report["before_adapter_sha256"] == report["after_adapter_sha256"]
            or not report["changed_adapter_elements"]
        ):
            raise ValueError("Optimizer step did not change actual adapter parameters")
        checkpoint_path = output / "adapter"
        model.save_pretrained(checkpoint_path, safe_serialization=True, save_embedding_layers=False)
        with torch.no_grad():
            updated_probabilities = selected_logprobs(model, admitted[0]).cpu().tolist()
        save("adapter_saved")
        del optimizer, model, base, parameters, logp, loss, dummy, norm
        gc.collect()
        torch.cuda.empty_cache()
        base = load_base()
        restored = PeftModel.from_pretrained(base, checkpoint_path, is_trainable=False)
        restored.eval()
        restored_state = adapter_state(restored)
        report["reloaded_adapter_sha256"] = tensor_digest(restored_state)
        with torch.no_grad():
            restored_probabilities = selected_logprobs(restored, admitted[0]).cpu().tolist()
        functional = compare_logprobs(
            restored_probabilities,
            updated_probabilities,
            args.logprob_max_atol,
            args.logprob_mean_atol,
        )
        atomic_write(output / "reload-probability-check.json", json_bytes(functional))
        report["reload_parameter_match"] = (
            report["reloaded_adapter_sha256"] == report["after_adapter_sha256"]
        )
        report["reload_functional_check"] = {
            key: functional[key] for key in ("max_abs_delta", "mean_abs_delta", "passed")
        }
        report["peak_gpu_bytes"] = torch.cuda.max_memory_allocated()
        if not report["reload_parameter_match"] or not functional["passed"]:
            raise ValueError("Adapter reload verification failed; measured differences preserved")
        report["status"] = "one_update_saved_and_reloaded"
        save("complete")
        return 0
    except Exception as error:
        report.update(
            status="experiment_error", error={"type": type(error).__name__, "message": str(error)}
        )
        save("error")
        return 1
    finally:
        report.update(
            ended_at=time.time(), source_after=code_identity(), resources_after=resources()
        )
        atomic_write(output / "report.json", json_bytes(report))
        print(
            json.dumps(
                {
                    key: report.get(key)
                    for key in (
                        "status",
                        "eligible_episodes",
                        "excluded_episodes",
                        "training_happened",
                        "optimizer_steps",
                        "learning_gain_measured",
                    )
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
