"""Resident shared-actor online PPO with auditable real token ownership.

The learner sees saved experience and environment rewards. The direct transport
sees only public model requests. No business planner or reference answer lives
here; collection belongs to an injected, separately versioned world runner.
"""

import copy
import hashlib
import json
import math
import os
import resource
import time
import uuid
from pathlib import Path

from .local_model_service import SamplingTrace, completed_tokens, parse_generated, prepare_prompt
from .member_views import member_view
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "shared-online-ppo-v0.13"
DEFAULT_RECIPE = {
    "actor_lr": 1e-5,
    "critic_lr": 1e-3,
    "clip": 0.2,
    "gamma": 1.0,
    "critic_coefficient": 0.5,
    "entropy_coefficient": 0.0,
    "kl_coefficient": 0.0,
    "gradient_clip": 1.0,
    "epochs": 1,
    "temperature": 0.7,
    "max_output_tokens": 512,
    "max_length": 8192,
    "logprob_max_atol": 0.02,
    "logprob_mean_atol": 0.002,
    "max_rss_bytes": 64 * 1024**3,
    "seed": 20260926,
    "members": ["provider", "implementer", "reviewer"],
    "lora": {"r": 8, "alpha": 16, "dropout": 0.0, "target_modules": ["q_proj", "v_proj"]},
}


def recipe_config(overrides=None):
    overrides = overrides or {}
    if set(overrides) - set(DEFAULT_RECIPE):
        raise ValueError("Unknown online recipe fields")
    result = {**copy.deepcopy(DEFAULT_RECIPE), **copy.deepcopy(overrides)}
    for key in ("actor_lr", "critic_lr", "clip", "gradient_clip", "temperature",
                "logprob_max_atol", "logprob_mean_atol"):
        if type(result[key]) not in (int, float) or not math.isfinite(result[key]) or result[key] <= 0:
            raise ValueError("Positive finite recipe value required: " + key)
    for key in ("max_output_tokens", "max_length", "max_rss_bytes", "seed"):
        if type(result[key]) is not int or result[key] <= 0:
            raise ValueError("Positive integer recipe value required: " + key)
    if result["gamma"] != 1 or result["epochs"] != 1:
        raise ValueError("This recipe implements one full-window MC update, gamma=1")
    if result["critic_coefficient"] != 0.5 or result["entropy_coefficient"] != 0 or result["kl_coefficient"] != 0:
        raise ValueError("Critic/entropy/KL coefficients are fixed in this version")
    if result["lora"] != DEFAULT_RECIPE["lora"]:
        raise ValueError("This version fixes one q/v LoRA r8 alpha16 dropout0")
    if result["members"] != DEFAULT_RECIPE["members"] or result["clip"] >= 1:
        raise ValueError("Declared roles or clipping interval differ from this recipe")
    return result


def sha_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            hasher.update(block)
    return hasher.hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha_file(path), "bytes": path.stat().st_size}


def tensor_tree_digest(value, torch):
    hasher = hashlib.sha256()

    def visit(item):
        if torch.is_tensor(item):
            data = item.detach().cpu().contiguous()
            hasher.update(json_bytes(["tensor", str(data.dtype), list(data.shape)]))
            hasher.update(data.reshape(-1).view(torch.uint8).numpy().tobytes())
        elif isinstance(item, dict):
            hasher.update(b"dict")
            for key in sorted(item, key=str):
                hasher.update(json_bytes([type(key).__name__, key]))
                visit(item[key])
        elif isinstance(item, (list, tuple)):
            hasher.update(json_bytes([type(item).__name__, len(item)]))
            for child in item:
                visit(child)
        else:
            hasher.update(json_bytes(item))

    visit(value)
    return hasher.hexdigest()


def probability_check(actual, behavior, recipe):
    if not actual or len(actual) != len(behavior) or any(not math.isfinite(x) for x in actual + behavior):
        raise ValueError("Finite full behavior probability sequence required")
    delta = [a - b for a, b in zip(actual, behavior)]
    maximum, mean = max(map(abs, delta)), sum(map(abs, delta)) / len(delta)
    return {
        "actual_behavior_logprobs": behavior,
        "recomputed_logprobs": actual,
        "signed_delta": delta,
        "max_abs_delta": maximum,
        "mean_abs_delta": mean,
        "passed": maximum <= recipe["logprob_max_atol"] and mean <= recipe["logprob_mean_atol"],
    }


def selected_logprobs(model, trace, torch, device):
    """All original output tokens, no text reconstruction or token cropping."""
    ids = trace["input_ids"] + trace["output_ids"]
    count = len(trace["output_ids"])
    inputs = torch.tensor([ids], dtype=torch.long, device=device)
    logits = model(
        input_ids=inputs, attention_mask=torch.ones_like(inputs), use_cache=False,
        logits_to_keep=count + 1,
    ).logits[0, :-1].float() / trace["sampling_temperature"]
    if logits.shape[0] != count:
        raise ValueError("Output-only logits lost original token targets")
    targets = torch.tensor(trace["output_ids"], dtype=torch.long, device=device)
    return logits.log_softmax(-1).gather(1, targets[:, None]).squeeze(1)


def ppo_sum(torch, current, behavior, advantage, clip):
    ratio = (current - behavior).exp()
    return -torch.minimum(ratio * advantage, ratio.clamp(1 - clip, 1 + clip) * advantage).sum(), ratio


def prepare_window(entries, actor_identity, window_id, recipe, feature_function=None):
    """Keep every scheduled slot; isolate missing evidence without renormalizing.

    Reward-zero, refused calls and malformed assistant responses are valid action
    targets when their complete original own-token evidence is recoverable.
    """
    if feature_function is None:
        from .critic_features import past_features
        feature_function = past_features
    if not entries or len({e["slot_id"] for e in entries}) != len(entries):
        raise ValueError("Nonempty unique scheduled online slots required")
    rows, summaries = [], []
    for entry in entries:
        members = entry.get("active_members")
        if not members or len(set(members)) != len(members) or set(members) - set(recipe["members"]):
            raise ValueError("Each slot declares unique active target members")
        summary = {"slot_id": entry["slot_id"], "active_members": members, "exclusions": [], "members": {}}
        summaries.append(summary)
        rollout = entry.get("rollout")
        reward = entry.get("reward", rollout.get("reward_eligibility") if rollout else None)
        if rollout is None or not isinstance(reward, dict):
            summary["exclusions"].append("episode_or_reward_record_missing")
            continue
        summary["reward"] = copy.deepcopy(reward)
        if reward != rollout["reward_eligibility"]:
            raise ValueError("Collection reward differs from attached historical reward")
        if rollout["window"]["window_id"] != window_id:
            raise ValueError("Rollout belongs to another online window")
        if not reward.get("eligible") or type(reward.get("reward")) not in (int, float) or not math.isfinite(reward["reward"]):
            summary["exclusions"].append("reward_unknown_or_ineligible")
            continue
        if reward.get("episode_id") != rollout["rollout_id"] or reward.get("manifest_sha256") != rollout["manifest_sha256"]:
            raise ValueError("Reward does not bind exact historical rollout")
        if rollout["work_validity"]["components"]["record"]["value"] is not True:
            summary["exclusions"].append("record_validity_not_true")
            continue
        for member in members:
            view = member_view(rollout, member)
            info = {"all_decisions": len(view["decisions"]), "own_action_tokens": view["own_action_tokens"], "exclusions": []}
            summary["members"][member] = info
            required = [r for r in view["decisions"] if r["actor_required"]]
            if not required and view["no_own_actions"]:
                info["exclusions"].append("no_own_sampled_actions")
                continue
            if not view["complete_actor_trajectory"] or view["origin"] != "target_model":
                info["exclusions"].append("complete_current_target_trajectory_unavailable")
                info["diagnostics"] = view["diagnostics"]
                continue
            own_rows = []
            for decision in required:
                response, trace = decision["actual_response"], decision["tokens"]
                config = decision["policy_identity"]["config"]
                if (config.get("weight_identity") != actor_identity
                        or config.get("model_revision") != actor_identity["policy_version"]
                        or response.get("actor_identity") != actor_identity
                        or response.get("system_fingerprint") != actor_identity["policy_version"]
                        or response.get("online_window_id") != window_id):
                    raise ValueError("Behavior actor identity/window differs from resident actor")
                if (trace.get("sampling_temperature") != recipe["temperature"]
                        or trace.get("sampling_top_p") != 1 or trace.get("sampling_top_k") != 0):
                    raise ValueError("Behavior distribution differs from frozen online recipe")
                if len(trace["input_ids"]) + len(trace["output_ids"]) > recipe["max_length"]:
                    info["exclusions"].append("full_actual_sequence_exceeds_frozen_max_length")
                    break
                starts = [e for e in rollout["events"] if e.get("worker_id") == member
                          and e["kind"] == "model_call" and e["payload"].get("stage") == "started"
                          and e["payload"].get("call_id") == decision["call_id"]]
                if len(starts) != 1:
                    raise ValueError("Unique original model-call start required for past features")
                features, provenance = feature_function(
                    rollout["events"], starts[0]["sequence"], member, recipe["members"]
                )
                own_rows.append({
                    "slot_id": entry["slot_id"], "member_id": member, "call_id": decision["call_id"],
                    "reward": float(reward["reward"]), "tokens": trace,
                    "critic_features": features, "critic_provenance": provenance,
                    "actor_denominator": len(entries) * len(members) * view["own_action_tokens"],
                    "critic_denominator": len(entries) * len(members) * len(required),
                    "actual_response_sha256": decision["response_sha256"],
                })
            if not info["exclusions"]:
                rows.extend(own_rows)
    return {"version": VERSION, "window_id": window_id, "actor_identity": actor_identity,
            "slots": summaries, "decisions": rows, "slot_count": len(entries),
            "normalization": "fixed scheduled slots x active members x member all output tokens; exclusions never change denominators"}


class DirectContextLimit(ValueError):
    """An actual tokenized input rejected before any generation begins."""


class DirectModelTransport:
    """Public request-only transport bound to one actual actor/window identity."""

    def __init__(self, owner):
        self.owner = owner
        self.identity = copy.deepcopy(owner.freeze_identity())
        self.window_id = owner.window_id

    def complete(self, request, *, timeout_seconds):
        if self.identity != self.owner.freeze_identity() or self.window_id != self.owner.window_id:
            raise ValueError("Stale role transport cannot sample after a shared-policy/window refresh")
        return self.owner.complete(request, timeout_seconds=timeout_seconds)


class SharedActor:
    """Exactly one resident LoRA actor and actor optimizer across all roles/windows."""

    def __init__(self, model, tokenizer, *, output, base_identity, inference_profile,
                 recipe=None, device="cuda", torch_module=None, require_lora=True):
        if torch_module is None:
            import torch as torch_module
        self.torch, self.model, self.tokenizer = torch_module, model, tokenizer
        torch = self.torch
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / "calls").mkdir()
        self.recipe = recipe_config(recipe)
        self.device = device
        # Metadata is JSON data, never a library-specific str subclass in a
        # torch checkpoint. TorchVersion otherwise needs unsafe pickle globals.
        self.base_identity = json.loads(json_bytes(base_identity))
        self.inference_profile = json.loads(json_bytes(inference_profile))
        self.inference_profile_sha256 = digest(json_bytes(self.inference_profile))
        self.actor_parameters = {n: p for n, p in model.named_parameters() if p.requires_grad}
        if not self.actor_parameters or (require_lora and any("lora_" not in n for n in self.actor_parameters)):
            raise ValueError("Only one declared trainable LoRA actor is supported")
        if any(isinstance(m, torch.nn.Dropout) and m.p != 0 for m in model.modules()) or getattr(model.config, "attention_dropout", 0) != 0:
            raise ValueError("Sampling and replay require zero base/adapter dropout")
        self.model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        self.model.config.use_cache = False
        if hasattr(self.model, "enable_input_require_grads"):
            self.model.enable_input_require_grads()
        self.model.eval()
        width = len(self.recipe["members"]) * 10
        self.critic = torch.nn.Sequential(torch.nn.Linear(width, 32), torch.nn.Tanh(), torch.nn.Linear(32, 1)).to(device)
        # A random baseline must not manufacture the first policy-learning signal.
        torch.nn.init.zeros_(self.critic[-1].weight)
        torch.nn.init.zeros_(self.critic[-1].bias)
        self.actor_optimizer = torch.optim.AdamW(list(self.actor_parameters.values()), lr=self.recipe["actor_lr"], weight_decay=0)
        self.critic_optimizer = torch.optim.AdamW(self.critic.parameters(), lr=self.recipe["critic_lr"], weight_decay=0)
        self.actor_steps = self.critic_steps = self.policy_revision = 0
        self.critic_has_nonzero_reward_history = False
        self.window_id = None
        self.used_window_ids = []
        self.phase = "idle"
        self.busy = False
        self.cache_clear_count = 0
        self._identity = self._make_identity()
        atomic_write(self.output / "owner.json", json_bytes({
            "version": VERSION, "base_identity": self.base_identity,
            "inference_profile": self.inference_profile,
            "recipe": self.recipe, "initial_actor_identity": self._identity,
            "actor_optimizer_ownership": "one shared optimizer, reused across all windows",
            "transport_kind": "resident_direct", "actual_network_http_calls": 0,
            "base_generation_config": (self.model.generation_config.to_dict()
                if hasattr(self.model.generation_config, "to_dict") else vars(self.model.generation_config)),
            "critic_initialization": "seeded hidden layer; exactly zero final layer/output",
        }))

    @classmethod
    def from_pretrained(cls, model_path, *, weight_manifest, output, recipe=None,
                        attention="sdpa_explicit_kv", matmul_precision="high", startup_reserve_gib=0):
        import torch
        import transformers
        import peft
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig, get_peft_model
        from .local_model_service import configure_attention_runtime, load_with_startup_reservation

        recipe = recipe_config(recipe)
        torch.manual_seed(recipe["seed"])
        torch.set_num_threads(8)
        model_path = Path(model_path).resolve()
        manifest = read_json(Path(weight_manifest))
        files = manifest.get("files", {})
        if not files or not any(name.endswith(".safetensors") for name in files):
            raise ValueError("Complete original base file manifest required")
        for name, record in files.items():
            path = (model_path / name).resolve()
            if not path.is_relative_to(model_path) or path.stat().st_size != record["bytes"] or sha_file(path) != record["sha256"]:
                raise ValueError("Base file identity differs: " + name)
        if not torch.cuda.is_available():
            raise ValueError("Declared resident GPU learner has no CUDA; no hidden fallback")
        numerical = configure_attention_runtime(attention, matmul_precision)
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        output = Path(output)
        # Reserve helper writes alongside owner, whose directory remains new.
        startup = output.parent / (output.name + "-startup-resource.json")
        if startup.exists() or output.exists():
            raise FileExistsError("Resident owner/startup outputs already exist")

        def attach(base):
            return get_peft_model(base, LoraConfig(
                r=8, lora_alpha=16, lora_dropout=0, target_modules=["q_proj", "v_proj"],
                bias="none", task_type="CAUSAL_LM",
            ))

        network, _ = load_with_startup_reservation(
            lambda: AutoModelForCausalLM.from_pretrained(
                model_path, local_files_only=True, dtype=torch.float32, attn_implementation=attention,
            ), torch=torch, reserve_gib=startup_reserve_gib, record_path=startup, on_device=attach,
        )
        profile = {
            "version": "resident-online-inference-v0.13", "dtype": "float32",
            "attention": attention, "max_batch": 1, "native_tool_prompt": "single_call",
            "max_context_tokens": recipe["max_length"], "seed": recipe["seed"],
            "torch": str(torch.__version__), "transformers": str(transformers.__version__), "peft": str(peft.__version__),
            **numerical,
        }
        return cls(network, tokenizer, output=output, recipe=recipe, device="cuda",
                   inference_profile=profile, base_identity={
                       "path": str(model_path), "manifest": reference(weight_manifest),
                       "revision": manifest.get("declared_hf_revision"),
                   })

    def actor_state(self):
        return {n: p.detach().cpu().contiguous().clone() for n, p in self.actor_parameters.items()}

    def _make_identity(self):
        sha = tensor_tree_digest(self.actor_state(), self.torch)
        return {
            "version": "shared-actor-identity-v0.13",
            "policy_version": "online-actor-" + str(self.policy_revision) + ":" + sha,
            "adapter_sha256": sha,
            "base_manifest_sha256": self.base_identity["manifest"]["sha256"],
            "inference_profile_sha256": self.inference_profile_sha256,
        }

    def freeze_identity(self):
        return copy.deepcopy(self._identity)

    @property
    def transport(self):
        if self.phase != "collecting":
            raise ValueError("Role transports may only be bound inside a declared window")
        return DirectModelTransport(self)

    def clear_generation_cache(self):
        # Dynamic generation state is local to generate(); also discard a possible
        # HF reusable cache so a future profile cannot accidentally cross updates.
        if hasattr(self.model, "_cache"):
            delattr(self.model, "_cache")
        self.cache_clear_count += 1

    def begin_window(self, window_id):
        if (self.busy or self.phase != "idle" or not isinstance(window_id, str)
                or not window_id or window_id in self.used_window_ids):
            raise ValueError("Window boundary requires an idle shared learner")
        if self._make_identity() != self._identity:
            raise ValueError("Actor parameters changed outside the shared optimizer boundary")
        self.window_id, self.phase = window_id, "collecting"
        self.used_window_ids.append(window_id)
        self.clear_generation_cache()
        return self.freeze_identity()

    def reseed(self, seed, *, label):
        """Host-declared episode-boundary seed; never chooses/resamples an action."""
        if self.phase != "collecting" or self.busy:
            raise ValueError("Sampling seed changes require an idle collection boundary")
        if type(seed) is not int or not 0 <= seed < 2**63 or not isinstance(label, str) or not label:
            raise ValueError("A finite integer seed and explicit episode label are required")
        torch = self.torch

        def rng():
            return {"cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()
                    if self.device.startswith("cuda") else []}

        before = tensor_tree_digest(rng(), torch)
        torch.manual_seed(seed)
        after = tensor_tree_digest(rng(), torch)
        record = {"version": "episode-sampling-seed-v0.13", "seed": seed, "label": label,
                  "online_window_id": self.window_id, "actor_identity": self.freeze_identity(),
                  "rng_before_sha256": before, "rng_after_sha256": after,
                  "scope": "Host-predeclared episode boundary; no policy update or action resampling"}
        directory = self.output / "sampling-seeds"
        directory.mkdir(exist_ok=True)
        atomic_write(directory / (uuid.uuid4().hex + ".json"), json_bytes(record))
        return record

    def finish_evaluation(self, entries, output):
        """Close a frozen interaction window without any learner forward/backward."""
        if self.phase != "collecting" or self.busy:
            raise ValueError("Evaluation boundary requires completed collection")
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        actual_identity = self._make_identity()
        if actual_identity != self._identity:
            raise ValueError("Actor changed during a frozen evaluation window")
        report = {
            "version": VERSION, "window_id": self.window_id,
            "status": "evaluation_only_no_learning_computation",
            "before_actor_identity": self.freeze_identity(),
            "after_actor_identity": self.freeze_identity(),
            "scheduled_slots": len(entries),
            "slots": [{"slot_id": entry["slot_id"], "active_members": entry["active_members"],
                       "reward": copy.deepcopy(entry.get("reward"))} for entry in entries],
            "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
            "training_happened": False, "probability_recomputation_executed": False,
            "actor_or_critic_learning_forward_executed": False,
            "actor_steps_total": self.actor_steps, "critic_steps_total": self.critic_steps,
            "transport_kind": "resident_direct", "actual_network_http_calls": 0,
        }
        self.clear_generation_cache()
        self.phase = "idle"
        atomic_write(output / "report.json", json_bytes(report))
        return report

    def _resource_guard(self):
        resident = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        high = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        if max(resident, high) > self.recipe["max_rss_bytes"]:
            raise RuntimeError("Predeclared host RSS resource guard exceeded")
        return {"rss_bytes": resident, "rss_peak_bytes": high}

    def complete(self, request, *, timeout_seconds):
        if self.phase != "collecting" or self.busy:
            raise ValueError("Sampling and shared actor updates may not overlap")
        torch = self.torch
        self.busy = True
        started = time.monotonic()
        call_id = "resident_" + uuid.uuid4().hex
        ledger = {"request": copy.deepcopy(request), "actor_identity": self.freeze_identity(),
                  "online_window_id": self.window_id, "timeout_seconds_declared": timeout_seconds,
                  "transport": "synchronous resident call; no HTTP or hidden retry"}
        try:
            temperature = request.get("temperature")
            maximum = request.get("max_tokens")
            if temperature != self.recipe["temperature"] or type(maximum) is not int or not 0 < maximum <= self.recipe["max_output_tokens"]:
                raise ValueError("Request sampling temperature/output budget differs from frozen recipe")
            if request.get("stream") or any(key in request for key in ("top_p", "top_k", "logit_bias", "frequency_penalty", "presence_penalty")):
                raise ValueError("Unsupported undeclared distribution transform")
            rendered, messages, projection = prepare_prompt(request, self.tokenizer, self.inference_profile.get("native_tool_prompt", "single_call"))
            ids = self.tokenizer(rendered, add_special_tokens=False)["input_ids"]
            if len(ids) + maximum > self.recipe["max_length"]:
                raise DirectContextLimit("Full real prompt plus requested output exceeds context limit; no crop")
            ledger.update(rendered_prompt=rendered, actual_prompt_messages=messages, prompt_projection=projection)
            inputs = torch.tensor([ids], dtype=torch.long, device=self.device)
            options = {
                "max_new_tokens": maximum, "do_sample": True, "pad_token_id": self.tokenizer.pad_token_id,
                "use_cache": True, "repetition_penalty": 1.0, "renormalize_logits": False,
                "temperature": 1.0, "top_p": 1.0, "top_k": 0, "typical_p": 1.0,
            }
            self.clear_generation_cache()
            self.model.eval()
            self._resource_guard()
            if self.device.startswith("cuda"):
                torch.cuda.reset_peak_memory_stats()
            trace = SamplingTrace(temperature)
            with torch.inference_mode():
                generated = self.model.generate(
                    input_ids=inputs, attention_mask=torch.ones_like(inputs),
                    logits_processor=[trace], **options,
                )
            probabilities = trace.finish(generated)
            tokens, finished = completed_tokens(generated[0, len(ids):].tolist(), self.model.generation_config.eos_token_id)
            raw = self.tokenizer.decode(tokens, skip_special_tokens=False)
            message, parse_error = parse_generated(raw)
            body = {
                "id": call_id, "object": "chat.completion", "created": int(time.time()),
                "model": request["model"], "system_fingerprint": self._identity["policy_version"],
                "actor_identity": self.freeze_identity(), "online_window_id": self.window_id,
                "choices": [{"index": 0, "message": message, "finish_reason":
                    ("tool_calls" if message.get("tool_calls") else "stop") if finished else "length", "logprobs": None}],
                "usage": {"prompt_tokens": len(ids), "completion_tokens": len(tokens), "total_tokens": len(ids) + len(tokens)},
                "raw_generated_text": raw, "protocol_parse_error": parse_error,
                "inference_profile": self.inference_profile,
                "inference_profile_sha256": self.inference_profile_sha256,
                "prompt_projection": projection,
                "token_trace": {"input_ids": ids, "output_ids": tokens,
                    "input_mask": [0] * len(ids), "output_mask": [1] * len(tokens),
                    "behavior_logprobs": probabilities[0][:len(tokens)],
                    "sampling_temperature": temperature, "sampling_top_p": 1.0, "sampling_top_k": 0,
                    "source": "actual generation token IDs and sampling logits, not retokenized text"},
                "effective_generation": options,
                "service_record": {"transport_kind": "resident_direct", "actual_network_http_calls": 0, "batch_size": 1, "batch_row_index": 0, "prefix_width": len(ids),
                    "cache_scope": "fresh per request; cleared before and after each generation/update",
                    "seconds": time.monotonic() - started, "resource": self._resource_guard()},
            }
            if self.device.startswith("cuda"):
                body["service_record"]["peak_gpu_allocated_bytes"] = torch.cuda.max_memory_allocated()
            status = 200
        except DirectContextLimit as error:
            body = {"error": {"code": "context_length_exceeded", "message": str(error),
                    "prompt_tokens": len(ids), "requested_output": maximum, "context_limit": self.recipe["max_length"]},
                    "transport_kind": "resident_direct", "generation_started": False,
                    "actor_identity": self.freeze_identity(), "online_window_id": self.window_id}
            status = 400
        except Exception as error:
            body = {"error": {"code": "resident_inference_error", "type": type(error).__name__, "message": str(error)}}
            status = 503
        finally:
            self.clear_generation_cache()
            self.busy = False
        ledger.update(response=body, status=status, elapsed_seconds=time.monotonic() - started)
        atomic_write(self.output / "calls" / (call_id + ".json"), json_bytes(ledger))
        return {"http_status": status, "raw_body": json_bytes(body).decode(), "body": body,
                "response_headers": {"x-transport": "resident-direct"}, "response_redactions": []}

    def _state_bundle(self):
        torch = self.torch
        return {
            "version": VERSION, "recipe": copy.deepcopy(self.recipe),
            "actor": self.actor_state(),
            "critic": {k: v.detach().cpu().clone() for k, v in self.critic.state_dict().items()},
            "actor_optimizer": copy.deepcopy(self.actor_optimizer.state_dict()),
            "critic_optimizer": copy.deepcopy(self.critic_optimizer.state_dict()),
            "rng_cpu": torch.get_rng_state(),
            "rng_cuda": torch.cuda.get_rng_state_all() if self.device.startswith("cuda") else [],
            "policy_revision": self.policy_revision, "actor_steps": self.actor_steps,
            "critic_steps": self.critic_steps,
            "critic_has_nonzero_reward_history": self.critic_has_nonzero_reward_history,
            "actor_identity": self.freeze_identity(), "base_identity": self.base_identity,
            "inference_profile": self.inference_profile, "last_window_id": self.window_id,
            "used_window_ids": list(self.used_window_ids),
        }

    def save_checkpoint(self, directory):
        """One common boundary checkpoint, including both persistent optimizers/RNG."""
        if self.busy or self.phase != "idle":
            raise ValueError("Shared checkpoints require a complete window boundary")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=False)
        state = self._state_bundle()
        path = directory / "shared-state.pt"
        self.torch.save(state, path)
        restored = self.torch.load(path, map_location=self.device, weights_only=True)
        if tensor_tree_digest(restored, self.torch) != tensor_tree_digest(state, self.torch):
            raise ValueError("Shared checkpoint did not serialize/reload exactly")
        summary = {
            "version": VERSION, "state": reference(path), "actor_identity": self.freeze_identity(),
            "actor_steps": self.actor_steps, "critic_steps": self.critic_steps,
            "state_tensor_digest": tensor_tree_digest(state, self.torch),
            "serialized_reload_exact": True,
            "scope": "All actor/critic and optimizer/RNG tensors reloaded; no claim of fresh environment success",
        }
        if hasattr(self.model, "save_pretrained"):
            self.model.save_pretrained(directory / "adapter", safe_serialization=True, save_embedding_layers=False)
        atomic_write(directory / "checkpoint.json", json_bytes(summary))
        return summary

    def restore_checkpoint(self, directory):
        if self.busy or self.phase != "idle":
            raise ValueError("Restore requires an idle learner")
        directory = Path(directory)
        record = read_json(directory / "checkpoint.json")
        path = directory / "shared-state.pt"
        if sha_file(path) != record["state"]["sha256"]:
            raise ValueError("Shared checkpoint bytes changed")
        state = self.torch.load(path, map_location=self.device, weights_only=True)
        if (state["version"] != VERSION or state["recipe"] != self.recipe
                or state["base_identity"] != self.base_identity
                or state["inference_profile"] != self.inference_profile
                or set(state["actor"]) != set(self.actor_parameters)):
            raise ValueError("Shared checkpoint actor/base/recipe/profile differs")
        with self.torch.no_grad():
            for name, parameter in self.actor_parameters.items():
                parameter.copy_(state["actor"][name].to(parameter.device))
        self.critic.load_state_dict(state["critic"])
        self.actor_optimizer.load_state_dict(state["actor_optimizer"])
        self.critic_optimizer.load_state_dict(state["critic_optimizer"])
        self.torch.set_rng_state(state["rng_cpu"].cpu())
        if self.device.startswith("cuda"):
            self.torch.cuda.set_rng_state_all([v.cpu() for v in state["rng_cuda"]])
        for name in ("policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history"):
            setattr(self, name, state[name])
        self.window_id = state["last_window_id"]
        self.used_window_ids = list(state["used_window_ids"])
        self._identity = self._make_identity()
        self.clear_generation_cache()
        if self._identity != state["actor_identity"]:
            raise ValueError("Reloaded actor identity differs from exact saved tensors")
        return record

    def update_window(self, entries, output, *, feature_function=None, update_actor=True):
        """One complete-window PPO accumulation; no old D0 or reward-diversity gate."""
        if self.phase != "collecting" or self.busy:
            raise ValueError("Update follows a finished collection with no active model calls")
        torch = self.torch
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        self.phase = "updating"
        self.clear_generation_cache()
        before = self.actor_state()
        before_steps = self.actor_steps, self.critic_steps
        report = {
            "version": VERSION, "window_id": self.window_id, "status": "preparing",
            "before_actor_identity": self.freeze_identity(), "recipe": self.recipe,
            "actor_optimizer_steps": 0, "critic_optimizer_steps": 0,
            "training_happened": False, "backward_decisions_completed": 0,
            "transport_kind": "resident_direct", "actual_network_http_calls": 0,
            "composition": "Q=B, all admitted actor targets have composition weight 1",
            "advantage": "terminal credible reward minus frozen pre-update zero-initialized observed-history critic; no normalization",
        }

        def save(stage):
            report["stage"] = stage
            report["resource"] = self._resource_guard()
            atomic_write(output / "report.json", json_bytes(report))

        try:
            self.model.eval()
            prepared = prepare_window(entries, self.freeze_identity(), self.window_id, self.recipe, feature_function)
            atomic_write(output / "admission.json", json_bytes(prepared))
            rows = prepared["decisions"]
            report.update(admitted_decisions=len(rows), scheduled_slots=len(entries),
                          admitted_output_tokens=sum(len(r["tokens"]["output_ids"]) for r in rows))
            torch.save(self._state_bundle(), output / "shared-before.pt")
            save("admission")
            if not rows:
                report["status"] = "zero_step_no_admitted_own_actions"
                return report
            checks, values, advantages = [], [], []
            with torch.no_grad():
                for row in rows:
                    self._resource_guard()
                    probabilities = selected_logprobs(self.model, row["tokens"], torch, self.device)
                    check = probability_check(probabilities.cpu().tolist(), row["tokens"]["behavior_logprobs"], self.recipe)
                    checks.append({"call_id": row["call_id"], **check})
                    value = float(self.critic(torch.tensor(row["critic_features"], dtype=torch.float32, device=self.device)).squeeze())
                    values.append(value)
                    advantages.append(row["reward"] - value)
                    del probabilities
            atomic_write(output / "behavior-probability-check.json", json_bytes(checks))
            report.update(behavior_probability_passed=all(c["passed"] for c in checks),
                          old_critic_values=values, advantages=advantages,
                          rewards=[r["reward"] for r in rows])
            if not report["behavior_probability_passed"]:
                report["status"] = "zero_step_probability_mismatch"
                return report
            if not all(math.isfinite(v) for v in advantages):
                raise ValueError("Nonfinite true MC advantage")
            # No random/unsupported initial critic noise can create an actor update.
            zero_signal = not self.critic_has_nonzero_reward_history and all(r["reward"] == 0 for r in rows)
            if zero_signal and any(abs(value) > 1e-12 for value in values):
                raise ValueError("Critic before any nonzero reward history must predict exactly zero")
            actor_enabled = update_actor and not zero_signal and any(a != 0 for a in advantages)
            report.update(zero_signal_window=zero_signal, actor_update_enabled=actor_enabled,
                          critic_had_nonzero_reward_history=self.critic_has_nonzero_reward_history)
            if not update_actor:
                report["status"] = "frozen_actor_evaluation_no_update"
                return report
            self.actor_optimizer.zero_grad(set_to_none=True)
            self.critic_optimizer.zero_grad(set_to_none=True)
            self.model.train()  # All dropout zero; HF enables gradient checkpointing only in train mode.
            gradient_checks, losses = [], []
            for row, advantage in zip(rows, advantages):
                self._resource_guard()
                actor_loss_value, ratio_range = 0.0, None
                if actor_enabled:
                    probabilities = selected_logprobs(self.model, row["tokens"], torch, self.device)
                    check = probability_check(probabilities.detach().cpu().tolist(), row["tokens"]["behavior_logprobs"], self.recipe)
                    gradient_checks.append({"call_id": row["call_id"], **check})
                    if not check["passed"]:
                        atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
                        self.actor_optimizer.zero_grad(set_to_none=True)
                        self.critic_optimizer.zero_grad(set_to_none=True)
                        report["status"] = "zero_step_gradient_probability_mismatch"
                        return report
                    behavior = torch.tensor(row["tokens"]["behavior_logprobs"], device=self.device)
                    total, ratio = ppo_sum(torch, probabilities, behavior, advantage, self.recipe["clip"])
                    actor_loss = total / row["actor_denominator"]
                    if not torch.isfinite(actor_loss):
                        raise ValueError("Nonfinite actor loss")
                    actor_loss.backward()
                    actor_loss_value = float(actor_loss.detach())
                    ratio_range = [float(ratio.detach().min()), float(ratio.detach().max())]
                    del probabilities, behavior, total, ratio, actor_loss
                value = self.critic(torch.tensor(row["critic_features"], dtype=torch.float32, device=self.device)).squeeze()
                critic_loss = 0.5 * (value - row["reward"]).square() / row["critic_denominator"]
                if not torch.isfinite(critic_loss):
                    raise ValueError("Nonfinite critic loss")
                (critic_loss * self.recipe["critic_coefficient"]).backward()
                losses.append({"call_id": row["call_id"], "slot_id": row["slot_id"],
                               "member_id": row["member_id"], "actor_loss": actor_loss_value,
                               "critic_loss": float(critic_loss.detach()), "ppo_ratio_range": ratio_range,
                               "composition_weight": 1.0})
                report["backward_decisions_completed"] += 1
                del value, critic_loss
                save("backward")
            atomic_write(output / "gradient-probability-check.json", json_bytes(gradient_checks))
            atomic_write(output / "losses.json", json_bytes(losses))
            gradients = {"actor": {n: p.grad.detach().cpu().clone() for n, p in self.actor_parameters.items() if p.grad is not None},
                         "critic": {n: p.grad.detach().cpu().clone() for n, p in self.critic.named_parameters() if p.grad is not None}}
            torch.save(gradients, output / "gradients-before-clip.pt")
            actor_norm = torch.nn.utils.clip_grad_norm_(list(self.actor_parameters.values()), self.recipe["gradient_clip"])
            critic_norm = torch.nn.utils.clip_grad_norm_(self.critic.parameters(), self.recipe["gradient_clip"])
            if not torch.isfinite(actor_norm) or not torch.isfinite(critic_norm):
                raise ValueError("Nonfinite shared actor/critic gradient; no optimizer step")
            report["gradient_norms"] = {"actor": float(actor_norm), "critic": float(critic_norm)}
            if actor_enabled and actor_norm > 0:
                self.actor_optimizer.step()
                self.actor_steps += 1
                self.policy_revision += 1
                report.update(actor_optimizer_steps=1, training_happened=True)
                # Preserve an accurately attributed partial update if a later operation fails.
                self._identity = self._make_identity()
                save("actor_updated_pending_critic")
            if critic_norm > 0:
                self.critic_optimizer.step()
                self.critic_steps += 1
                self.critic_has_nonzero_reward_history |= any(r["reward"] != 0 for r in rows)
                report["critic_optimizer_steps"] = 1
            after = self.actor_state()
            report["changed_actor_elements"] = sum(int((after[k] != before[k]).sum()) for k in before)
            if report["actor_optimizer_steps"] and not report["changed_actor_elements"]:
                raise ValueError("An optimizer step occurred but no actor parameter changed")
            report["status"] = "updated" if report["actor_optimizer_steps"] else "zero_step_zero_actor_advantage_or_gradient"
            report["actor_enabled_without_step"] = actor_enabled and not report["actor_optimizer_steps"]
            report["stage"] = "complete"
            return report
        except (KeyboardInterrupt, SystemExit) as error:
            report.update(status="interrupted", interruption={"type": type(error).__name__, "message": str(error)})
            raise
        except Exception as error:
            report.update(status="window_update_error", error={"type": type(error).__name__, "message": str(error)})
            raise
        finally:
            self.model.eval()
            self.clear_generation_cache()
            self.phase = "idle"
            self._identity = self._make_identity()
            report.update(after_actor_identity=self.freeze_identity(),
                          actor_optimizer_steps=self.actor_steps - before_steps[0],
                          critic_optimizer_steps=self.critic_steps - before_steps[1],
                          actor_steps_total=self.actor_steps, critic_steps_total=self.critic_steps,
                          cache_clear_count=self.cache_clear_count)
            # Always persist the true update counters, even if resource inspection fails.
            atomic_write(output / "report.json", json_bytes(report))


def run_online_windows(owner, protocol, output_dir, collector):
    """Collect new live interactions after each synchronous shared-policy update."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    mode = protocol.get("mode", "online")
    if mode not in {"online", "evaluate"}:
        raise ValueError("Online runner mode must be explicitly online or evaluate")
    windows = protocol["windows"]
    if not windows or len({w["window_id"] for w in windows}) != len(windows):
        raise ValueError("Unique predeclared online windows required")
    atomic_write(output_dir / "protocol.json", json_bytes(protocol))
    report = {"version": VERSION, "protocol_sha256": digest(json_bytes(protocol)),
              "transport_kind": "resident_direct", "actual_network_http_calls": 0,
              "mode": mode, "windows": [], "status": "running"}
    try:
        owner.save_checkpoint(output_dir / "initial-checkpoint")
        for index, spec in enumerate(windows):
            identity = owner.begin_window(spec["window_id"])
            directory = output_dir / ("window-" + str(index))
            directory.mkdir()
            record = {"window_id": spec["window_id"], "before_actor_identity": identity, "status": "collecting"}
            report["windows"].append(record)
            atomic_write(output_dir / "report.json", json_bytes(report))
            entries = collector(owner, copy.deepcopy(spec), directory / "collection")
            if [e["slot_id"] for e in entries] != [s["slot_id"] for s in spec["slots"]]:
                raise ValueError("Collector changed the scheduled slot order or dropped a failure")
            update = (owner.finish_evaluation(entries, directory / "evaluation")
                      if mode == "evaluate" else owner.update_window(entries, directory / "update"))
            checkpoint = owner.save_checkpoint(directory / "checkpoint")
            record.update(status="complete", update=update, checkpoint=checkpoint,
                          after_actor_identity=owner.freeze_identity())
            atomic_write(output_dir / "report.json", json_bytes(report))
            if update["status"] in {"zero_step_probability_mismatch", "zero_step_gradient_probability_mismatch"}:
                report["status"] = "stopped_probability_mismatch"
                break
        else:
            report["status"] = "complete"
    except (KeyboardInterrupt, SystemExit) as error:
        report.update(status="interrupted", interruption={"type": type(error).__name__, "message": str(error)})
        raise
    except Exception as error:
        report.update(status="error", error={"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report.update(actor_steps_total=owner.actor_steps, critic_steps_total=owner.critic_steps,
                      final_actor_identity=owner.freeze_identity())
        atomic_write(output_dir / "report.json", json_bytes(report))
    return report
