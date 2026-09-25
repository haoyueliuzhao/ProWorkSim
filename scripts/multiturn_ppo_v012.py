"""D3 bounded full-member, full-decision PPO window; no success-only selection.

Default execution only prepares the fixed inventory. GPU execution additionally
requires all predeclared data/learning-signal gates and probability checks. The
CPU self-check validates arithmetic and ownership, never real model learning.
"""

import argparse
import copy
import gc
import hashlib
import json
import math
import os
import resource
import subprocess
import time
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.member_views import member_view
from proworksim.storage import atomic_write, digest, json_bytes, read_json as read_stored_json

VERSION = "multiturn-ppo-v0.12"
MEMBERS = ["provider", "implementer", "reviewer"]
RECIPE = {
    "clip": 0.2,
    "gamma": 1.0,
    "advantage": "MC terminal trusted return minus frozen pre-update centralized observed-history critic",
    "advantage_normalization": "none",
    "actor_normalization": "fixed slots x fixed members x each member all output tokens",
    "critic_normalization": "fixed slots x fixed members x each member actual decisions",
    "critic_coefficient": 0.5,
    "entropy_coefficient": 0.0,
    "kl_coefficient": 0.0,
    "actor_lr": 1e-6,
    "critic_lr": 1e-3,
    "weight_decay": 0.0,
    "gradient_clip": 1.0,
    "epochs": 1,
    "optimizer_steps": 1,
    "optimizer": "AdamW beta=(.9,.999),epsilon=1e-8",
    "lora": {"r": 8, "alpha": 16, "dropout": 0.0, "target_modules": ["q_proj", "v_proj"]},
    "seed": 20260925,
    "max_length": 16384,
    "logprob_max_atol": 0.02,
    "logprob_mean_atol": 0.002,
    "max_rss_bytes": 64 * 1024**3,
    "expected_dtype": "float32",
    "expected_batch_size": 1,
    "replay": "single original input+output teacher forcing; use_cache=False, output-only logits, nonreentrant gradient checkpointing",
    "composition": "Q=B; configurable q/b only in CPU materialization tests in this version",
    "critic_architecture": "30 structural past-history features -> Linear32 -> Tanh -> Linear1; seeded default initialization",
    "training_mode": "HF train mode activates gradient checkpointing; all model dropout must be zero; eval probability gate and actual grad-forward gate both required",
}


def read_json(path):
    return read_stored_json(Path(path))


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            h.update(block)
    return h.hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha_file(path), "bytes": path.stat().st_size}


def rss_bytes():
    return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def resource_state():
    result = {
        "at": time.time(),
        "rss_bytes": rss_bytes(),
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        "shared_gpu_authorized": True,
    }
    try:
        p = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.free,utilization.gpu",
                "--format=csv",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        result["gpu"] = {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        result["gpu_error"] = str(error)
    return result


def past_features(events, before_sequence, member_id, member_ids):
    """Only actual observed prefix structure. Never read terminal truth or values."""
    latest, counts, refs = {}, {m: [0, 0] for m in member_ids}, {}
    for event in events:
        if event["sequence"] >= before_sequence:
            break
        member = event.get("worker_id")
        if member not in counts:
            continue
        if event["kind"] == "public_observation":
            latest[member] = event["payload"]
            refs[member] = event["sequence"]
        elif event["kind"] == "tool_call":
            ok = event["payload"].get("response", {}).get("ok")
            if type(ok) is bool:
                counts[member][0 if ok else 1] += 1
    features = []
    for member in member_ids:
        observation = latest.get(member, {})
        works = observation.get("work_items", {})
        works = list(works.values()) if isinstance(works, dict) else []
        features.extend(
            [len(works) / 10.0]
            + [
                sum(w.get("status") == status for w in works) / 10.0
                for status in ["open", "active", "pending", "accepted", "blocked"]
            ]
        )
        workspaces = observation.get("workspaces", {})
        features.append(sum(len(v) for v in workspaces.values() if isinstance(v, dict)) / 100.0)
        features.extend(x / 100.0 for x in counts[member])
    features.extend(float(member == member_id) for member in member_ids)
    return features, {
        "before_event_sequence": before_sequence,
        "latest_observation_sequences": refs,
        "scope": "centralized actually observed history counts; no content values, future events, terminal reward or evaluator truth",
    }


def probability_check(actual, behavior):
    if (
        len(actual) != len(behavior)
        or not actual
        or any(not math.isfinite(x) for x in actual + behavior)
    ):
        raise ValueError("Finite full actual behavior probabilities required")
    delta = [x - y for x, y in zip(actual, behavior)]
    maximum = max(map(abs, delta))
    mean = sum(map(abs, delta)) / len(delta)
    return {
        "actual_behavior_logprobs": behavior,
        "recomputed_logprobs": actual,
        "signed_delta": delta,
        "max_abs_delta": maximum,
        "mean_abs_delta": mean,
        "passed": maximum <= RECIPE["logprob_max_atol"] and mean <= RECIPE["logprob_mean_atol"],
    }


def token_ppo(torch, new_logp, old_logp, advantage, mask, *, composition=1.0, eligible=False):
    """Composition and PPO probability ratios remain different variables."""
    ratio = (new_logp - old_logp).exp()
    unclipped = ratio * advantage
    clipped = ratio.clamp(1 - RECIPE["clip"], 1 + RECIPE["clip"]) * advantage
    raw = -torch.minimum(unclipped, clipped)
    base = (raw * mask).sum()
    weight = composition if eligible else 1.0
    weighted = base * weight
    residual = base + (weight - 1) * base
    return weighted, {
        "base": base,
        "residual": residual,
        "ppo_ratio": ratio,
        "composition_weight": weight,
    }


def prepare_inventory(path):
    spec = read_json(path)
    if spec.get("version") != "multiturn-ppo-inventory-v0.12" or spec.get("member_ids") != MEMBERS:
        raise ValueError("Freeze the declared three-member D3 inventory")
    slots = spec.get("slots", [])
    if len(slots) != 4 or len({s["slot_id"] for s in slots}) != 4:
        raise ValueError("Exactly four predeclared Qwen repeat1 slots are required")
    expected = spec["expected_policy"]
    required = {
        "system_fingerprint",
        "inference_profile_sha256",
        "weight_manifest_sha256",
        "service_manifest_sha256",
    }
    if set(expected) != required or any(not isinstance(v, str) or not v for v in expected.values()):
        raise ValueError("Full immutable behavior identity required")
    result = {
        "version": VERSION,
        "inventory": reference(path),
        "recipe": copy.deepcopy(RECIPE),
        "fixed_slot_ids": [s["slot_id"] for s in slots],
        "fixed_member_ids": MEMBERS,
        "slots": [],
        "decisions": [],
        "gates": {},
        "errors": [],
        "learning_gain_measured": False,
    }
    gate = spec["d0_gate"]
    gate_data = read_json(gate["path"])
    gate_value = gate_data
    if not isinstance(gate["field_path"], list) or not gate["field_path"]:
        raise ValueError("Explicit D0 gate field path required")
    for key in gate["field_path"]:
        gate_value = gate_value[key]
    result["gates"]["independent_d0_passed"] = (
        sha_file(gate["path"]) == gate["sha256"] and gate_value is True
    )
    result["d0_gate_reference"] = reference(gate["path"])
    service = read_json(spec["service_manifest"])
    result["service_manifest_reference"] = reference(spec["service_manifest"])
    profile = service.get("inference_profile", {})
    result["gates"]["frozen_service_identity"] = (
        sha_file(spec["service_manifest"]) == expected["service_manifest_sha256"]
        and service.get("policy_version") == expected["system_fingerprint"]
        and service.get("adapter") is None
        and service.get("inference_profile_sha256")
        == expected["inference_profile_sha256"]
        == digest(json_bytes(profile))
        and profile.get("dtype") == "float32"
        and profile.get("actual_parameter_dtype") == "torch.float32"
        and profile.get("max_batch") == 1
    )
    rewards = []
    windows = []
    multi = set()
    weight_manifests = set()
    for slot in slots:
        saved = {
            "slot_id": slot["slot_id"],
            "declared_path": slot["team_rollout"],
            "members": {},
            "errors": [],
        }
        result["slots"].append(saved)
        try:
            rollout = read_json(slot["team_rollout"])
            saved["reference"] = reference(slot["team_rollout"])
            if saved["reference"]["sha256"] != slot["team_rollout_sha256"]:
                raise ValueError("Frozen TeamRollout bytes changed")
            if rollout.get("version") != "team-rollout-v0.12":
                raise ValueError("Actual TeamRollout required")
            manifest_path = Path(rollout["episode_path"]) / "manifest.json"
            actual_manifest = read_json(manifest_path)
            if (
                sha_file(manifest_path) != rollout["manifest_sha256"]
                or actual_manifest != rollout["manifest"]
            ):
                raise ValueError("TeamRollout differs from actual closed episode manifest")
            if (
                actual_manifest["source_start"] != actual_manifest["source_end"]
                or actual_manifest["source_start"]["code_dirty"]
            ):
                raise ValueError("Behavior episode source was not one clean freeze")
            experience = actual_manifest["experience"]
            history_path = Path(rollout["episode_path"]) / experience["path"]
            if sha_file(history_path) != experience["sha256"]:
                raise ValueError("Actual closed episode history bytes changed")
            if (
                read_json(history_path)["events"][experience["start"] : experience["end"]]
                != rollout["events"]
            ):
                raise ValueError("TeamRollout events differ from fixed original episode interval")
            windows.append(rollout["window"])
            if sorted(rollout["members"]) != sorted(MEMBERS):
                raise ValueError("Do not drop or add target members")
            reward = rollout["reward_eligibility"]
            saved["reward"] = reward
            if (
                reward.get("eligible") is not True
                or type(reward.get("reward")) not in (int, float)
                or not math.isfinite(reward["reward"])
            ):
                raise ValueError("Untrusted/unknown reward in fixed slot; not silently excluded")
            rewards.append(reward["reward"])
            if (
                rollout.get("work_validity", {})
                .get("components", {})
                .get("record", {})
                .get("value")
                is not True
            ):
                raise ValueError(
                    "Record validity is not established; other work-validity failures do not filter baseline RL"
                )
            for member in MEMBERS:
                policy = rollout["manifest"]["policies"][member]
                config = policy.get("config", {})
                identity = config.get("weight_identity", {})
                if (
                    rollout["members"][member]["origin"] != "target_model"
                    or policy.get("implementation") != "proworksim.model_policy.ModelPolicy"
                    or config.get("backend_id") != "local-qwen-http"
                    or config.get("model_revision") != expected["system_fingerprint"]
                    or identity.get("manifest_sha256") != expected["weight_manifest_sha256"]
                ):
                    raise ValueError(
                        "Current local base target membership/weight identity mismatch"
                    )
                weight_manifests.add(identity["manifest"])
                view = member_view(rollout, member)
                sampled = [d for d in view["decisions"] if d.get("actor_required", True)]
                saved["members"][member] = {
                    "own_action_count": view["own_action_count"],
                    "own_action_tokens": view["own_action_tokens"],
                    "complete_actor_trajectory": view["complete_actor_trajectory"],
                    "diagnostics": view["diagnostics"],
                }
                if sampled and (
                    not view["complete_actor_trajectory"]
                    or not all(d["actor_trainable"] for d in sampled)
                ):
                    raise ValueError("Incomplete required real actor trajectory: " + member)
                if len(sampled) >= 2:
                    multi.add(member)
                starts = {
                    e["payload"]["call_id"]: e["sequence"]
                    for e in rollout["events"]
                    if e["kind"] == "model_call" and e["payload"].get("stage") == "started"
                }
                count_tokens = sum(len(d["tokens"]["output_ids"]) for d in sampled)
                for decision in sampled:
                    response = decision["actual_response"]
                    trace = decision["tokens"]
                    if (
                        response.get("system_fingerprint") != expected["system_fingerprint"]
                        or response.get("inference_profile_sha256")
                        != expected["inference_profile_sha256"]
                        or response.get("inference_profile") != profile
                        or response.get("service_record", {}).get("batch_size") != 1
                    ):
                        raise ValueError(
                            "Actual response behavior precision/batch/identity mismatch"
                        )
                    ledger_path = Path(spec["service_records"]) / (response["id"] + ".json")
                    if Path(response["id"]).name != response["id"]:
                        raise ValueError("Unsafe service completion ID")
                    ledger = read_json(ledger_path)
                    if (
                        ledger.get("response") != response
                        or ledger.get("request") != decision["actual_input"]
                    ):
                        raise ValueError(
                            "Original service ledger differs from actual member decision"
                        )
                    n, m = len(trace["input_ids"]), len(trace["output_ids"])
                    if n + m > RECIPE["max_length"]:
                        raise ValueError(
                            "Original sequence exceeds16384; no crop or short-decision selection"
                        )
                    if (
                        trace.get("sampling_temperature") != 0.3
                        or trace.get("sampling_top_p") != 1
                        or trace.get("sampling_top_k") != 0
                    ):
                        raise ValueError("Unexpected actual sampling distribution")
                    effective = response.get("effective_generation", {})
                    if any(
                        effective.get(k) != v
                        for k, v in {
                            "do_sample": True,
                            "temperature": 1.0,
                            "top_p": 1.0,
                            "top_k": 0,
                            "repetition_penalty": 1.0,
                        }.items()
                    ):
                        raise ValueError("Unexpected generation processor distribution")
                    features, provenance = past_features(
                        rollout["events"], starts[decision["call_id"]], member, MEMBERS
                    )
                    result["decisions"].append(
                        {
                            "slot_id": slot["slot_id"],
                            "rollout_id": rollout["rollout_id"],
                            "member_id": member,
                            "call_id": decision["call_id"],
                            "opportunity_id": decision["opportunity_id"],
                            "input_sha256": decision["input_sha256"],
                            "service_completion_id": response["id"],
                            "service_reference": reference(ledger_path),
                            "tokens": copy.deepcopy(trace),
                            "labels": decision["labels"],
                            "loss_mask": decision["loss_mask"],
                            "reward": reward["reward"],
                            "critic_features": features,
                            "critic_feature_provenance": provenance,
                            "actor_denominator": len(slots) * len(MEMBERS) * count_tokens,
                            "critic_denominator": len(slots) * len(MEMBERS) * len(sampled),
                            "composition_weight": 1.0,
                            "scope": "All required real completions; malformed generated decisions remain targets",
                        }
                    )
        except (ValueError, KeyError, TypeError, OSError) as error:
            saved["errors"].append(str(error))
            result["errors"].append({"slot_id": slot["slot_id"], "error": str(error)})
    result["gates"]["all_four_complete_trusted_slots"] = not result["errors"] and len(rewards) == 4
    result["gates"]["four_exact_situations_same_gamma_policy"] = (
        len(windows) == 4
        and len({w["xi_id"] for w in windows}) == 4
        and len(
            {
                (w["gamma_fingerprint"], w["team_policy_fingerprint"], w["window_id"])
                for w in windows
            }
        )
        == 1
    )
    result["gates"]["at_least_two_members_multiturn"] = len(multi) >= 2
    result["gates"]["credible_return_differences"] = (
        len(rewards) == 4 and max(rewards) - min(rewards) > 1e-8
    )
    result["gates"]["shared_unmodified_base"] = len(weight_manifests) == 1
    result["weight_manifest"] = next(iter(weight_manifests)) if len(weight_manifests) == 1 else None
    result["expected_policy"] = expected
    result["all_pre_gpu_gates_passed"] = all(result["gates"].values())
    result["status"] = (
        "prepared_eligible_no_training"
        if result["all_pre_gpu_gates_passed"]
        else "not_run_data_or_learning_signal_gate"
    )
    result["required_generation_count"] = len(result["decisions"])
    return result


def verify_base(model_path, prepared):
    if (model_path / "adapter_config.json").exists() or any(model_path.glob("adapter_model.*")):
        raise ValueError("Base must not contain an updated adapter")
    path = Path(prepared["weight_manifest"])
    manifest = read_json(path)
    if sha_file(path) != prepared["expected_policy"]["weight_manifest_sha256"]:
        raise ValueError("Base manifest changed")
    if manifest.get("declared_hf_revision") != prepared["expected_policy"]["system_fingerprint"]:
        raise ValueError("Base revision differs")
    files = manifest.get("files", {})
    if not files or not any(n.endswith(".safetensors") for n in files):
        raise ValueError("Complete base weights required")
    for name, item in files.items():
        p = (model_path / name).resolve()
        if (
            not p.is_relative_to(model_path)
            or p.stat().st_size != item["bytes"]
            or sha_file(p) != item["sha256"]
        ):
            raise ValueError("Base bytes differ: " + name)
    return {"manifest": reference(path), "verified_files": files}


def selected_logprobs(model, row, torch, device):
    trace = row["tokens"]
    ids = trace["input_ids"] + trace["output_ids"]
    m = len(trace["output_ids"])
    inputs = torch.tensor([ids], dtype=torch.long, device=device)
    logits = (
        model(
            input_ids=inputs,
            attention_mask=torch.ones_like(inputs),
            use_cache=False,
            logits_to_keep=m + 1,
        )
        .logits[0, :-1]
        .float()
        / 0.3
    )
    if logits.shape[0] != m:
        raise ValueError("Output-only logits lost actual targets")
    chosen = torch.tensor(trace["output_ids"], dtype=torch.long, device=device)
    return logits.log_softmax(-1).gather(1, chosen[:, None]).squeeze(1)


def cpu_self_check():
    import torch

    torch.manual_seed(RECIPE["seed"])
    # A small differentiable fixture, not a language-model rollout or model score.
    actor = torch.nn.Parameter(
        torch.tensor([[0.2, -0.1], [0.4, 0.8], [-0.3, 0.5], [0.1, 0.2]], dtype=torch.float64)
    )
    critic = torch.nn.Linear(2, 1, dtype=torch.float64)
    optimizer = torch.optim.AdamW([actor, *critic.parameters()], lr=0.01, weight_decay=0)
    optimizer.zero_grad()
    (actor.square().sum() + sum(p.square().sum() for p in critic.parameters())).backward()
    optimizer.step()
    common_actor = actor.detach().clone()
    common_critic = copy.deepcopy(critic.state_dict())
    common_optim = copy.deepcopy(optimizer.state_dict())
    old = common_actor.log_softmax(-1)[:, 0].detach()
    adv = torch.tensor([0.7, -0.4, 0.2, -0.8], dtype=torch.float64)
    mask = torch.tensor([1.0, 1.0, 0.0, 1.0], dtype=torch.float64)
    features = torch.tensor([[0.1, 0.2], [0.5, 0.4]], dtype=torch.float64)
    returns = torch.tensor([0.0, 1.0], dtype=torch.float64)
    from proworksim.support_weights import materialize_weights

    slot_ids = ["eligible_A", "eligible_B", "no_actions", "failure"]
    support = {
        "slot_ids": slot_ids,
        "window": {"window_id": "explicit_cpu_fixture"},
        "blocks": {
            "provider": {
                "b": {"A": 0.5, "B": 0.5},
                "eligible_slots": {"eligible_A": "A", "eligible_B": "B"},
                "base_actor_mask": dict(zip(slot_ids, [True, True, False, True])),
                "v": 0.5,
            }
        },
    }
    baseline_weights = materialize_weights(support, {"provider": {"A": 0.5, "B": 0.5}})
    changed_weights = materialize_weights(support, {"provider": {"A": 0.75, "B": 0.25}})
    outputs = []
    for materialization in [None, baseline_weights, changed_weights]:
        a = torch.nn.Parameter(common_actor.clone())
        v = torch.nn.Linear(2, 1, dtype=torch.float64)
        v.load_state_dict(common_critic)
        opt = torch.optim.AdamW([a, *v.parameters()], lr=0.01, weight_decay=0)
        opt.load_state_dict(copy.deepcopy(common_optim))
        opt.zero_grad()
        logp = a.log_softmax(-1)[:, 0]
        raw = -torch.minimum((logp - old).exp() * adv, (logp - old).exp().clamp(0.8, 1.2) * adv)
        base = (raw * mask).sum() / 12
        if materialization is None:
            actor_loss = base
        else:
            parts = []
            for i, slot_id in enumerate(slot_ids):
                weighted, _ = token_ppo(
                    torch,
                    logp[i : i + 1],
                    old[i : i + 1],
                    adv[i : i + 1],
                    mask[i : i + 1],
                    composition=materialization["members"]["provider"]["weights"][slot_id],
                    eligible=slot_id in support["blocks"]["provider"]["eligible_slots"],
                )
                parts.append(weighted)
            actor_loss = torch.stack(parts).sum() / 12
        critic_loss = 0.5 * ((v(features).squeeze(-1) - returns) ** 2).mean()
        loss = actor_loss + 0.5 * critic_loss
        loss.backward()
        grads = [p.grad.clone() for p in [a, *v.parameters()]]
        opt.step()
        outputs.append(
            {
                "loss": loss.detach(),
                "grads": grads,
                "params": [p.detach().clone() for p in [a, *v.parameters()]],
                "optimizer": copy.deepcopy(opt.state_dict()),
            }
        )

    def equal(a, b):
        if torch.is_tensor(a):
            return torch.equal(a, b)
        if isinstance(a, dict):
            return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)):
            return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
        return a == b

    checks = {
        name: equal(outputs[0][name], outputs[1][name])
        for name in ["loss", "grads", "params", "optimizer"]
    }
    new = torch.tensor([-0.2, -0.4], dtype=torch.float64, requires_grad=True)
    old2 = torch.tensor([-0.3, -0.35], dtype=torch.float64)
    weighted, details = token_ppo(
        torch, new, old2, torch.tensor(0.6), torch.ones(2), composition=1.5, eligible=True
    )
    checks["q_over_b_residual"] = torch.allclose(weighted, details["residual"], rtol=0, atol=1e-15)
    failure, fd = token_ppo(
        torch, new, old2, torch.tensor(-0.5), torch.ones(2), composition=1.5, eligible=False
    )
    checks["failure_retains_base_weight"] = (
        torch.equal(failure, fd["base"]) and fd["composition_weight"] == 1
    )
    empty, _ = token_ppo(
        torch, new, old2, torch.tensor(1.0), torch.zeros(2), composition=1.5, eligible=True
    )
    empty.backward()
    checks["no_own_action_zero_gradient"] = bool((new.grad == 0).all())
    checks["input_positions_zero_target_gradient"] = bool((outputs[0]["grads"][0][2] == 0).all())
    checks["ppo_and_composition_ratios_distinct"] = not bool(
        torch.all(details["ppo_ratio"] == details["composition_weight"])
    )
    checks["critic_not_composition_weighted"] = equal(
        outputs[0]["grads"][1:], outputs[2]["grads"][1:]
    )
    checks["composition_changes_actor_only"] = not equal(
        outputs[0]["grads"][0], outputs[2]["grads"][0]
    )

    def evidence(value):
        if torch.is_tensor(value):
            return {
                "dtype": str(value.dtype),
                "shape": list(value.shape),
                "values": value.detach().cpu().tolist(),
            }
        if isinstance(value, dict):
            return {str(key): evidence(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [evidence(item) for item in value]
        return value

    return {
        "scope": "CPU float64 synthetic arithmetic only; no real rollout, GPU, PPO training or ability claim",
        "comparison_evidence": evidence(outputs),
        "common_optimizer_state": evidence(common_optim),
        "checks": checks,
        "all_passed": all(checks.values()),
        "torch": torch.__version__,
        "cuda_initialized": torch.cuda.is_initialized(),
        "recipe": RECIPE,
        "baseline_materialization": baseline_weights,
        "perturbed_materialization": changed_weights,
    }


def train(prepared, model_path, output, report, save):
    import torch
    import peft
    import transformers
    from peft import LoraConfig, PeftModel, get_peft_model, get_peft_model_state_dict
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM

    torch.manual_seed(RECIPE["seed"])
    torch.set_num_threads(8)
    report["base_identity"] = verify_base(model_path, prepared)
    if not torch.cuda.is_available():
        raise ValueError("No GPU; no hidden device fallback")
    torch.cuda.reset_peak_memory_stats()

    def guard():
        value = max(rss_bytes(), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        report["rss_peak_observed_bytes"] = max(value, report.get("rss_peak_observed_bytes", 0))
        if value > RECIPE["max_rss_bytes"]:
            raise RuntimeError("Predeclared64GiB RSS guard exceeded")

    def state(model):
        return {
            k: v.detach().cpu().contiguous().clone()
            for k, v in get_peft_model_state_dict(model).items()
        }

    def state_digest(values):
        h = hashlib.sha256()
        for k, v in sorted(values.items()):
            h.update(json_bytes([k, str(v.dtype), list(v.shape)]))
            h.update(v.contiguous().view(torch.uint8).numpy().tobytes())
        return h.hexdigest()

    def optimizer_digest(tree):
        hashed = hashlib.sha256()

        def visit(value):
            if torch.is_tensor(value):
                tensor = value.detach().cpu().contiguous()
                hashed.update(json_bytes(["tensor", str(tensor.dtype), list(tensor.shape)]))
                hashed.update(tensor.reshape(-1).view(torch.uint8).numpy().tobytes())
            elif isinstance(value, dict):
                hashed.update(b"dict")
                for key in sorted(value, key=str):
                    hashed.update(json_bytes([type(key).__name__, key]))
                    visit(value[key])
            elif isinstance(value, (list, tuple)):
                hashed.update(json_bytes([type(value).__name__, len(value)]))
                for item in value:
                    visit(item)
            else:
                hashed.update(json_bytes(value))

        visit(tree)
        return hashed.hexdigest()

    profile = read_json(prepared["service_manifest_reference"]["path"])["inference_profile"]

    def base():
        return AutoModelForCausalLM.from_pretrained(
            model_path,
            local_files_only=True,
            dtype=torch.float32,
            attn_implementation=profile["attention"],
        ).to("cuda")

    model = get_peft_model(
        base(),
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0,
            target_modules=["q_proj", "v_proj"],
            bias="none",
            task_type="CAUSAL_LM",
        ),
    ).eval()
    model.config.use_cache = False
    if (
        any(isinstance(module, torch.nn.Dropout) and module.p != 0 for module in model.modules())
        or getattr(model.config, "attention_dropout", 0) != 0
    ):
        raise ValueError("All base and LoRA dropout must be fixed zero for this replay contract")
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    rows = prepared["decisions"]
    width = len(rows[0]["critic_features"])
    critic = (
        torch.nn.Sequential(torch.nn.Linear(width, 32), torch.nn.Tanh(), torch.nn.Linear(32, 1))
        .to("cuda")
        .eval()
    )
    actor_named_parameters = [(name, p) for name, p in model.named_parameters() if p.requires_grad]
    if not actor_named_parameters or any("lora_" not in name for name, _ in actor_named_parameters):
        raise ValueError("Only declared shared LoRA actor parameters may be updated")
    actor_parameters = [p for _, p in actor_named_parameters]
    actor_optimizer = torch.optim.AdamW(actor_parameters, lr=RECIPE["actor_lr"], weight_decay=0)
    critic_optimizer = torch.optim.AdamW(
        critic.parameters(), lr=RECIPE["critic_lr"], weight_decay=0
    )
    before = state(model)
    save_file(before, output / "actor-before.safetensors")
    save_file(
        {k: v.detach().cpu() for k, v in critic.state_dict().items()},
        output / "critic-before.safetensors",
    )
    torch.save(
        {"actor": actor_optimizer.state_dict(), "critic": critic_optimizer.state_dict()},
        output / "optimizers-before.pt",
    )
    report["before_optimizer_sha256"] = optimizer_digest(
        {"actor": actor_optimizer.state_dict(), "critic": critic_optimizer.state_dict()}
    )
    report["before_actor_sha256"] = state_digest(before)
    report["libraries"] = {
        "torch": torch.__version__,
        "peft": peft.__version__,
        "transformers": transformers.__version__,
    }
    checks = []
    advantages = []
    baselines = []
    with torch.no_grad():
        for row in rows:
            guard()
            lp = selected_logprobs(model, row, torch, "cuda")
            check = probability_check(lp.cpu().tolist(), row["tokens"]["behavior_logprobs"])
            checks.append({"call_id": row["call_id"], **check})
            value = float(critic(torch.tensor(row["critic_features"], device="cuda")).squeeze())
            baselines.append(value)
            advantages.append(row["reward"] - value)
            del lp
    atomic_write(output / "behavior-probability-check.json", json_bytes(checks))
    report["behavior_probability_passed"] = all(c["passed"] for c in checks)
    report["advantages"] = advantages
    report["old_critic_values"] = baselines
    if not report["behavior_probability_passed"]:
        report["status"] = "not_run_probability_gate"
        save("probability_gate")
        return
    if (
        not all(math.isfinite(v) for v in advantages)
        or max(advantages) - min(advantages) <= 1e-8
        or max(map(abs, advantages)) <= 1e-8
    ):
        report["status"] = "not_run_advantage_gate"
        save("advantage_gate")
        return
    actor_optimizer.zero_grad(set_to_none=True)
    critic_optimizer.zero_grad(set_to_none=True)
    model.train()  # HF activates checkpointing in train mode; every dropout was checked zero.
    gradient_checks = []
    loss_rows = []
    for row, advantage in zip(rows, advantages):
        guard()
        lp = selected_logprobs(model, row, torch, "cuda")
        check = probability_check(lp.detach().cpu().tolist(), row["tokens"]["behavior_logprobs"])
        gradient_checks.append({"call_id": row["call_id"], **check})
        if not check["passed"]:
            atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
            report["status"] = "not_run_gradient_probability_gate"
            save("gradient_probability_gate")
            return
        old = torch.tensor(row["tokens"]["behavior_logprobs"], device="cuda")
        actor_sum, extra = token_ppo(torch, lp, old, advantage, torch.ones_like(lp))
        actor_loss = actor_sum / row["actor_denominator"]
        value = critic(torch.tensor(row["critic_features"], device="cuda")).squeeze()
        critic_loss = 0.5 * (value - row["reward"]).square() / row["critic_denominator"]
        loss = actor_loss + RECIPE["critic_coefficient"] * critic_loss
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite full PPO loss")
        loss.backward()
        report["backward_decisions_completed"] = report.get("backward_decisions_completed", 0) + 1
        loss_rows.append(
            {
                "slot_id": row["slot_id"],
                "member_id": row["member_id"],
                "call_id": row["call_id"],
                "actor_loss": float(actor_loss.detach()),
                "critic_loss": float(critic_loss.detach()),
                "composition_weight": 1.0,
                "ppo_ratio_min": float(extra["ppo_ratio"].detach().min()),
                "ppo_ratio_max": float(extra["ppo_ratio"].detach().max()),
            }
        )
        del lp, old, actor_sum, extra, actor_loss, critic_loss, value, loss
        guard()
        save("backward")
    atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
    atomic_write(output / "losses.json", json_bytes(loss_rows))
    gradients = {
        **{
            "actor." + n: p.grad.detach().cpu().contiguous()
            for n, p in model.named_parameters()
            if p.requires_grad and p.grad is not None
        },
        **{
            "critic." + n: p.grad.detach().cpu().contiguous()
            for n, p in critic.named_parameters()
            if p.grad is not None
        },
    }
    save_file(gradients, output / "gradients-before-clip.safetensors")
    actor_norm = torch.nn.utils.clip_grad_norm_(actor_parameters, 1.0)
    critic_norm = torch.nn.utils.clip_grad_norm_(critic.parameters(), 1.0)
    if not torch.isfinite(actor_norm) or not torch.isfinite(critic_norm) or actor_norm <= 0:
        raise ValueError("Nonfinite/zero actor or nonfinite critic gradient")
    report["gradient_norms"] = {"actor": float(actor_norm), "critic": float(critic_norm)}
    actor_optimizer.step()
    report["actor_optimizer_steps"] = 1
    report["training_happened"] = True
    save("actor_updated_pending_critic")
    critic_optimizer.step()
    report["critic_optimizer_steps"] = 1
    after = state(model)
    report["after_actor_sha256"] = state_digest(after)
    report["changed_actor_elements"] = sum(int((after[k] != before[k]).sum()) for k in after)
    if not report["changed_actor_elements"]:
        raise ValueError("Actor step did not change actual parameters")
    model.eval()
    model.save_pretrained(output / "actor", safe_serialization=True, save_embedding_layers=False)
    critic_after = {k: v.detach().cpu().contiguous() for k, v in critic.state_dict().items()}
    save_file(critic_after, output / "critic-after.safetensors")
    optimizer_after = {
        "actor": actor_optimizer.state_dict(),
        "critic": critic_optimizer.state_dict(),
    }
    report["after_optimizer_sha256"] = optimizer_digest(optimizer_after)
    torch.save(optimizer_after, output / "optimizers-after.pt")
    del optimizer_after
    with torch.no_grad():
        updated = selected_logprobs(model, rows[0], torch, "cuda").cpu().tolist()
    report["after_critic_sha256"] = state_digest(critic_after)
    report["peak_gpu_bytes"] = torch.cuda.max_memory_allocated()
    save("updated_saved")
    del actor_optimizer, critic_optimizer, model, critic, actor_parameters, actor_named_parameters
    gc.collect()
    torch.cuda.empty_cache()
    restored = PeftModel.from_pretrained(base(), output / "actor", is_trainable=False).eval()
    report["reloaded_actor_sha256"] = state_digest(state(restored))
    with torch.no_grad():
        reloaded = selected_logprobs(restored, rows[0], torch, "cuda").cpu().tolist()
    reload_check = probability_check(reloaded, updated)
    atomic_write(output / "reload-probability-check.json", json_bytes(reload_check))
    if (
        report["reloaded_actor_sha256"] != report["after_actor_sha256"]
        or not reload_check["passed"]
    ):
        raise ValueError("Saved actor reload failed")
    from safetensors.torch import load_file

    restored_critic = torch.nn.Sequential(
        torch.nn.Linear(width, 32), torch.nn.Tanh(), torch.nn.Linear(32, 1)
    )
    restored_critic.load_state_dict(load_file(output / "critic-after.safetensors"))
    report["reloaded_critic_sha256"] = state_digest(restored_critic.state_dict())
    if report["reloaded_critic_sha256"] != report["after_critic_sha256"]:
        raise ValueError("Saved critic reload failed")
    restored_optimizers = torch.load(
        output / "optimizers-after.pt", map_location="cpu", weights_only=True
    )
    report["reloaded_optimizer_sha256"] = optimizer_digest(restored_optimizers)
    if report["reloaded_optimizer_sha256"] != report["after_optimizer_sha256"]:
        raise ValueError("Saved optimizer tensors or parameter groups differ after reload")
    report["restored_optimizer_steps"] = {
        name: sorted({float(item["step"]) for item in data["state"].values()})
        for name, data in restored_optimizers.items()
    }
    if report["restored_optimizer_steps"] != {"actor": [1.0], "critic": [1.0]}:
        raise ValueError("Saved optimizer step states differ")
    report["optimizer_after_reference"] = reference(output / "optimizers-after.pt")
    report["reload_function_scope"] = (
        "First real selected decision only; all actor/critic parameters checked by digest and both saved optimizer step states verified"
    )
    report["status"] = "one_full_window_update_saved_and_reloaded"
    save("complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-training", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--cpu-self-check", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("Use a new independent output path")
    if (args.cpu_self_check or args.prepare_only) and args.execute_training:
        parser.error("CPU arithmetic is not actual training")
    if not args.cpu_self_check and args.inventory is None:
        parser.error("Frozen inventory required")
    if args.execute_training and args.model is None:
        parser.error("Read-only model required")
    output = args.output.resolve()
    if args.model and (
        output == args.model.resolve() or output.is_relative_to(args.model.resolve())
    ):
        parser.error("Output must be outside source model")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "version": VERSION,
        "source_before": code_identity(),
        "started_at": time.time(),
        "recipe": RECIPE,
        "training_happened": False,
        "actor_optimizer_steps": 0,
        "critic_optimizer_steps": 0,
        "learning_gain_measured": False,
    }

    def save(stage):
        report["stage"] = stage
        atomic_write(output / "progress.json", json_bytes(report))

    try:
        if args.cpu_self_check:
            result = cpu_self_check()
            atomic_write(output / "cpu-self-check.json", json_bytes(result))
            report.update(status="cpu_arithmetic_only", checks_passed=result["all_passed"])
            return 0 if result["all_passed"] else 1
        prepared = prepare_inventory(args.inventory)
        atomic_write(output / "prepared.json", json_bytes(prepared))
        report.update(
            status=prepared["status"],
            gates=prepared["gates"],
            required_generation_count=prepared["required_generation_count"],
        )
        save("prepared")
        if not prepared["all_pre_gpu_gates_passed"] or not args.execute_training:
            return 0
        report["resources_before"] = resource_state()
        train(prepared, args.model.resolve(), output, report, save)
        return 0 if report["status"] == "one_full_window_update_saved_and_reloaded" else 1
    except Exception as error:
        report.update(
            status="experiment_error", error={"type": type(error).__name__, "message": str(error)}
        )
        return 1
    finally:
        report.update(source_after=code_identity(), ended_at=time.time())
        if args.execute_training:
            report["resources_after"] = resource_state()
        atomic_write(output / "report.json", json_bytes(report))
        print(
            json.dumps(
                {
                    k: report.get(k)
                    for k in [
                        "status",
                        "training_happened",
                        "actor_optimizer_steps",
                        "critic_optimizer_steps",
                        "checks_passed",
                    ]
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
