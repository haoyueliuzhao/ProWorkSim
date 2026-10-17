"""Read-only raw/retained actors for the v051 local inference bridge.

The caller freezes every mode, decoding and budget field before model work.
Both paths use the supported Hugging Face generator, the same BF16 text
backbone/FP32 head and the same FP32 sampling transform.  The reference uses
standard SDPA; the project uses the actual v020 BF16 attention implementation.
This is a local common-condition bridge, not a vendor benchmark reproduction.
No critic, optimizer, learner forward or backward is constructed here.
"""
from __future__ import annotations

import copy
import math
import os
from pathlib import Path
import time
import uuid

from .candidate_runtime_v015 import CHECKPOINTS, XML_SINGLE_CALL_HINT
from .candidate_runtime_v0151 import CHAT_STOP
from .candidate_runtime_v030 import loading_info_record
from .local_model_service import SamplingTrace
from .online_training import DirectContextLimit, DirectModelTransport, reference, sha_file
from .storage import atomic_write, digest, json_bytes, read_json
from .training import normalize_messages

VERSION = "software-calibration-runtime-v0.51"
PATHS = ("reference", "project")
CONTRACT_FIELDS = frozenset({
    "context_limit", "max_output_tokens", "enable_thinking", "preserve_thinking",
    "temperature", "top_p", "top_k", "repetition_penalty", "eos_token_ids",
    "pad_token_id", "max_generation_seconds",
})


def validate_contract(contract):
    """Only a finite explicit decoder is accepted; there are no mode defaults."""
    if not isinstance(contract, dict) or set(contract) != CONTRACT_FIELDS:
        raise ValueError("Freeze exactly the declared v051 inference contract fields")
    for key in ("context_limit", "max_output_tokens"):
        if type(contract[key]) is not int or contract[key] <= 0:
            raise ValueError("Positive integer capacity/output required")
    if contract["max_output_tokens"] >= contract["context_limit"]:
        raise ValueError("Reserve a positive full prompt inside the declared context")
    for key in ("enable_thinking", "preserve_thinking"):
        if type(contract[key]) is not bool:
            raise ValueError("Thinking and history mode must be explicit booleans")
    for key in ("temperature", "top_p", "repetition_penalty", "max_generation_seconds"):
        value = contract[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Decoder values must be finite and positive: " + key)
    if contract["top_p"] > 1 or type(contract["top_k"]) is not int or contract["top_k"] < 0:
        raise ValueError("Invalid top-p/top-k decoder")
    if contract["repetition_penalty"] != 1:
        raise ValueError("No uncalibrated repetition transform in this bridge")
    stops = contract["eos_token_ids"]
    if (not isinstance(stops, list) or len(stops) != 2
            or any(type(token) is not int for token in stops)
            or set(stops) != set(CHAT_STOP["eos_token_ids"])):
        raise ValueError("Retain the frozen Qwen native chat and end-of-text stops")
    if type(contract["pad_token_id"]) is not int or contract["pad_token_id"] not in stops:
        raise ValueError("Declare an explicit native stop token as the pad token")
    return copy.deepcopy(contract)


def generation_options(contract, *, pad_token_id):
    contract = validate_contract(contract)
    if pad_token_id != contract["pad_token_id"]:
        raise ValueError("Actual tokenizer pad token differs from frozen decoder")
    return {
        "max_new_tokens": contract["max_output_tokens"],
        "do_sample": True, "pad_token_id": pad_token_id,
        "eos_token_id": list(contract["eos_token_ids"]),
        "use_cache": True, "repetition_penalty": 1.0,
        "renormalize_logits": False, "temperature": 1.0,
        # CalibrationSamplingTrace owns temperature and both filters exactly
        # once, so its chosen log-probabilities describe the actual sampler.
        "top_p": 1.0, "top_k": 0,
        "typical_p": 1.0, "max_time": contract["max_generation_seconds"],
    }


class CalibrationSamplingTrace(SamplingTrace):
    """Trace after the same installed HF top-k/top-p transforms, in FP32."""

    def __init__(self, contract):
        from transformers.generation.logits_process import TopKLogitsWarper, TopPLogitsWarper
        contract = validate_contract(contract)
        super().__init__(contract["temperature"])
        self.filters = []
        if contract["top_k"]:
            self.filters.append(TopKLogitsWarper(contract["top_k"], min_tokens_to_keep=1))
        if contract["top_p"] < 1:
            self.filters.append(TopPLogitsWarper(contract["top_p"], min_tokens_to_keep=1))

    def __call__(self, input_ids, scores):
        if self.previous is not None:
            self.selected.append(self.previous.gather(1, input_ids[:, -1:]).squeeze(1))
        scaled = scores / self.temperature
        for processor in self.filters:
            scaled = processor(input_ids, scaled)
        self.previous = scaled.log_softmax(dim=-1)
        return scaled


def prepare_native_input(tokenizer, request, contract):
    """Render once upstream of either path; no truncation or selected-ID reuse."""
    contract = validate_contract(contract)
    messages = normalize_messages(request["messages"])
    original = copy.deepcopy(messages)
    tools = copy.deepcopy(request.get("tools", []))
    if tools:
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += "\n" + XML_SINGLE_CALL_HINT
        else:
            messages.insert(0, {"role": "system", "content": XML_SINGLE_CALL_HINT})
    kwargs = {key: contract[key] for key in ("enable_thinking", "preserve_thinking")}
    rendered = tokenizer.apply_chat_template(
        messages, tools=tools, tokenize=False, add_generation_prompt=True, **kwargs,
    )
    ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
    record = {
        "version": VERSION, "contract_sha256": digest(json_bytes(contract)),
        "request_sha256": digest(json_bytes(request)),
        "normalized_messages_sha256": digest(json_bytes(original)),
        "actual_prompt_messages": messages, "rendered_prompt": rendered,
        "rendered_prompt_sha256": digest(rendered.encode()), "input_ids": ids,
        "input_ids_sha256": digest(json_bytes(ids)), "prompt_tokens": len(ids),
        "chat_template_kwargs": kwargs, "single_call_hint_applied": bool(tools),
        "context_limit": contract["context_limit"],
        "requested_output_tokens": contract["max_output_tokens"],
        "fits": len(ids) + contract["max_output_tokens"] <= contract["context_limit"],
    }
    record["sha256"] = digest(json_bytes(record))
    validate_native_input(record, contract)
    return record


def validate_native_input(record, contract):
    contract = validate_contract(contract)
    if (not isinstance(record, dict) or record.get("version") != VERSION
            or record.get("sha256") != digest(json_bytes({k: v for k, v in record.items() if k != "sha256"}))
            or record.get("contract_sha256") != digest(json_bytes(contract))):
        raise ValueError("Frozen native input or decoder identity changed")
    ids = record.get("input_ids")
    if (not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 for i in ids)
            or record.get("input_ids_sha256") != digest(json_bytes(ids))
            or record.get("prompt_tokens") != len(ids)
            or record.get("rendered_prompt_sha256") != digest(record["rendered_prompt"].encode())
            or record.get("context_limit") != contract["context_limit"]
            or record.get("requested_output_tokens") != contract["max_output_tokens"]):
        raise ValueError("Actual native IDs/text/capacity binding is invalid")
    fits = len(ids) + contract["max_output_tokens"] <= contract["context_limit"]
    if record.get("fits") is not fits:
        raise ValueError("Input fit flag differs from actual full-token capacity")
    return fits


def completion_kind(output_ids, contract, elapsed_seconds):
    """Preserve truncated generations and reject any post-EOS tail."""
    contract = validate_contract(contract)
    if not output_ids or len(output_ids) > contract["max_output_tokens"]:
        raise ValueError("A complete generation must retain its actual bounded output")
    ends = [i for i, token in enumerate(output_ids) if token in contract["eos_token_ids"]]
    if ends:
        if ends[0] != len(output_ids) - 1:
            raise ValueError("Generation continued after its first declared EOS; no tail crop")
        return "stop"
    if len(output_ids) == contract["max_output_tokens"]:
        return "length"
    if elapsed_seconds >= contract["max_generation_seconds"]:
        return "time_limit"
    raise ValueError("Generation stopped without an identified EOS/length/time boundary")


def compare_pair_inputs(reference_record, project_record):
    keys = ("contract_sha256", "request_sha256", "actual_prompt_messages", "rendered_prompt",
            "rendered_prompt_sha256", "input_ids", "input_ids_sha256", "prompt_tokens")
    checks = {key: reference_record.get(key) == project_record.get(key) for key in keys}
    return {"passed": all(checks.values()), "checks": checks}


class CalibrationActor:
    """A no-optimizer provider compatible with project DirectModelTransport."""

    def __init__(self, model, tokenizer, *, contract, path, output, identity, torch_module,
                 head_execution, historical_steps=(0, 0)):
        if path not in PATHS:
            raise ValueError("Choose one declared reference/project path")
        self.model, self.tokenizer, self.torch = model, tokenizer, torch_module
        self.contract, self.path = validate_contract(contract), path
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output / "calls").mkdir()
        self.device, self.head_execution = "cuda:0", head_execution
        self.runtime_version = VERSION
        self.inference_profile = {
            "version": VERSION, "path": path,
            "base_storage_dtype": "bfloat16_backbone_float32_lm_head",
            "adapter_storage_dtype": "float32" if identity.get("checkpoint") else None,
            "contract": copy.deepcopy(self.contract),
            "reference_attention": "sdpa", "project_attention": "sdpa_bf16_explicit_kv_v020",
            "prefix_cache": {"enabled": False}, "critic_constructed": False,
            "optimizer_constructed": False, "learning_enabled": False,
        }
        self.inference_profile_sha256 = digest(json_bytes(self.inference_profile))
        self._identity = {**copy.deepcopy(identity), "inference_profile_sha256": self.inference_profile_sha256}
        self.base_identity = {"path": identity.get("model_path"), "manifest": identity["base_manifest"],
                              "revision": identity["base_revision"]}
        self._identity["policy_version"] = "calibration:" + digest(json_bytes(self._identity))
        self._path_switches = 0
        self.recipe = {"max_length": self.contract["context_limit"],
                       "max_output_tokens": self.contract["max_output_tokens"],
                       "temperature": self.contract["temperature"]}
        self.actor_steps, self.critic_steps = historical_steps
        self.phase, self.window_id, self.busy = "idle", None, False
        self.used_window_ids = []
        self._storage = self._inspect_storage()
        atomic_write(self.output / "owner.json", json_bytes({
            "version": VERSION, "actor_identity": self.freeze_identity(),
            "inference_profile": self.inference_profile, "actual_parameter_storage": self._storage,
            "historical_checkpoint_steps": list(historical_steps),
            "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0,
            "optimizer_constructed": False, "critic_constructed": False,
            "checkpoint_restore_scope": "actor tensors only, bound to complete source checkpoint; no learner-state restoration",
        }))

    def _inspect_storage(self):
        result = []
        for name, value in self.model.named_parameters():
            expected = self.torch.float32 if "lora_" in name or name.endswith("lm_head.weight") else self.torch.bfloat16
            if value.requires_grad or value.dtype != expected or value.device.type != "cuda":
                raise ValueError("Calibration requires frozen declared CUDA tensor storage: " + name)
            result.append([name, str(value.dtype), list(value.shape), str(value.device)])
        if not result:
            raise ValueError("Calibration model has no materialized parameters")
        return {"parameter_layout_sha256": digest(json_bytes(result)), "parameter_tensors": len(result)}

    def _verify_execution(self):
        from .candidate_runtime_v020 import ATTENTION, _no_autocast
        _no_autocast(self.torch)
        expected = ATTENTION if self.path == "project" else "sdpa"
        if (self.model.config._attn_implementation != expected
                or self.torch.get_float32_matmul_precision() != "highest"
                or self._inspect_storage() != self._storage):
            raise ValueError("Frozen calibration numerical path changed")
        self.head_execution.verify_installed()

    def freeze_identity(self):
        return copy.deepcopy(self._identity)

    def select_path(self, path):
        """Switch only attention on one raw resident model between paired arms."""
        from .candidate_runtime_v020 import ATTENTION
        if path not in PATHS or self.busy or self._identity.get("checkpoint"):
            raise ValueError("Only an idle raw-release resident may switch calibration paths")
        self._verify_execution()
        if path == self.path:
            return {"changed": False, "path": path, "actor_identity": self.freeze_identity()}
        before = self.freeze_identity()
        self.model.set_attn_implementation(ATTENTION if path == "project" else "sdpa")
        if hasattr(self.model, "_cache"):
            delattr(self.model, "_cache")
        self.path = path
        self.inference_profile["path"] = path
        self.inference_profile_sha256 = digest(json_bytes(self.inference_profile))
        self._identity = {k: v for k, v in self._identity.items() if k not in ("policy_version", "inference_profile_sha256")}
        self._identity["inference_profile_sha256"] = self.inference_profile_sha256
        self._identity["policy_version"] = "calibration:" + digest(json_bytes(self._identity))
        self._verify_execution()
        self._path_switches += 1
        receipt = {"version": VERSION, "changed": True, "path": path,
            "switch_ordinal": self._path_switches, "before_actor_identity": before,
            "after_actor_identity": self.freeze_identity(), "model_reloaded": False,
            "weights_modified": False, "new_model_generations": 0, "new_updates": 0}
        atomic_write(self.output / (f"path-switch-{self._path_switches:03d}.json"), json_bytes(receipt))
        return receipt

    @property
    def transport(self):
        if self.phase != "collecting":
            raise ValueError("Declare an evaluation window before binding transport")
        return DirectModelTransport(self)

    def begin_window(self, window_id):
        if self.busy or self.phase != "idle" or not window_id or window_id in self.used_window_ids:
            raise ValueError("A fresh idle calibration window is required")
        self.window_id, self.phase = window_id, "collecting"
        self.used_window_ids.append(window_id)
        return self.freeze_identity()

    def reseed(self, seed, *, label):
        if self.busy or self.phase != "collecting" or type(seed) is not int or not 0 <= seed < 2**63 or not label:
            raise ValueError("Seed only at a predeclared idle evaluation boundary")
        self.torch.manual_seed(seed)
        return {"seed": seed, "label": label, "actor_identity": self.freeze_identity(), "new_updates": 0}

    def verify_evaluation_guard(self):
        self._verify_execution()
        if self.busy or any(value.grad is not None for value in self.model.parameters()):
            raise ValueError("Evaluation guard requires no in-flight work or gradients")
        actual_adapter = None
        if self._identity.get("checkpoint"):
            from .online_training import tensor_tree_digest
            actual_adapter = tensor_tree_digest({name: value.detach().cpu()
                for name, value in self.model.named_parameters() if "lora_" in name}, self.torch)
            if actual_adapter != self._identity["adapter_sha256"]:
                raise ValueError("Retained checkpoint actor changed during calibration")
        return {"passed": True, "actor_identity": self.freeze_identity(),
            "actual_adapter_sha256": actual_adapter, "all_parameters_frozen": True,
            "all_gradients_absent": True, "optimizer_constructed": False,
            "critic_constructed": False, "new_actor_steps": 0, "new_critic_steps": 0,
            "new_backward_calls": 0}

    def _evaluation_fingerprints(self):
        guard = self.verify_evaluation_guard()
        return {"actor_identity": digest(json_bytes(guard["actor_identity"])),
            "adapter_sha256": guard["actual_adapter_sha256"],
            "readonly_layout": self._storage["parameter_layout_sha256"],
            "historical_steps": digest(json_bytes([self.actor_steps, self.critic_steps])),
            "optimizer_and_critic_absent": not any(hasattr(self, field)
                for field in ("critic", "actor_optimizer", "critic_optimizer"))}

    def capture_evaluation_state(self):
        if self.phase != "idle" or self.busy:
            raise ValueError("Capture only at an idle read-only evaluation boundary")
        return {"learning": self._evaluation_fingerprints(),
            "rng": {"cpu": self.torch.get_rng_state().clone(),
                    "cuda": [value.clone() for value in self.torch.cuda.get_rng_state_all()]},
            "scope": "Read-only actor fingerprint and RNG, not a restored learner state"}

    def finish_evaluation_guard(self, snapshot):
        from .online_training import tensor_tree_digest
        after = self._evaluation_fingerprints()
        torch = self.torch
        observed = {"cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}
        torch.set_rng_state(snapshot["rng"]["cpu"].cpu())
        torch.cuda.set_rng_state_all([value.cpu() for value in snapshot["rng"]["cuda"]])
        restored = {"cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all()}
        before_rng = tensor_tree_digest(snapshot["rng"], torch)
        return {"learning_before_sha256": snapshot["learning"], "learning_after_sha256": after,
            "learning_unchanged": snapshot["learning"] == after,
            "rng_before_sha256": before_rng, "rng_after_collection_sha256": tensor_tree_digest(observed, torch),
            "rng_after_restore_sha256": tensor_tree_digest(restored, torch),
            "rng_restored_exactly": tensor_tree_digest(restored, torch) == before_rng,
            "scope": "No learner exists; frozen actor/layout and absent gradients/optimizers verified. Only Torch RNG restored, no tensor rollback.",
            "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}

    def finish_evaluation(self, entries, output):
        if self.phase != "collecting":
            raise ValueError("An active calibration window is required")
        result = {"version": VERSION, "window_id": self.window_id,
            "status": "evaluation_only_no_learning_computation", "slots": copy.deepcopy(entries),
            "guard": self.verify_evaluation_guard(), "historical_actor_steps": self.actor_steps,
            "historical_critic_steps": self.critic_steps}
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        atomic_write(output / "report.json", json_bytes(result))
        self.phase = "idle"
        return result

    def prepare_request(self, request):
        record = prepare_native_input(self.tokenizer, request, self.contract)
        return record["rendered_prompt"], record["actual_prompt_messages"], record

    def generate_native(self, record):
        if self.phase != "collecting" or self.busy:
            raise ValueError("Generation requires an idle declared evaluation window")
        if not validate_native_input(record, self.contract):
            raise DirectContextLimit("Complete prompt plus output reservation exceeds frozen context")
        self._verify_execution()
        self.busy = True
        started = time.monotonic()
        attempt_id = "generation_" + uuid.uuid4().hex
        attempt_path = self.output / "calls" / (attempt_id + "-started.json")
        attempt = {"version": VERSION, "attempt_id": attempt_id,
            "actor_identity": self.freeze_identity(), "online_window_id": self.window_id,
            "native_input": copy.deepcopy(record), "started_at": time.time(),
            "generation_started": False, "actual_usage": None,
            "reserved_maximum_tokens": record["prompt_tokens"] + self.contract["max_output_tokens"]}
        atomic_write(self.output / "calls" / (attempt_id + "-prepared.json"), json_bytes(attempt))
        try:
            torch = self.torch
            inputs = torch.tensor([record["input_ids"]], dtype=torch.long, device=self.device)
            options = generation_options(self.contract, pad_token_id=self.tokenizer.pad_token_id)
            trace = CalibrationSamplingTrace(self.contract)
            self.model.eval()
            if hasattr(self.model, "_cache"):
                delattr(self.model, "_cache")
            attempt["generation_started"] = True
            atomic_write(attempt_path, json_bytes(attempt))
            with torch.inference_mode():
                if self.path == "project":
                    from .candidate_runtime_v020 import CandidateActor
                    generated, metadata = CandidateActor._generate_tokens(self, inputs, trace, options)
                    metadata.update(adapter_storage_dtype=self.inference_profile["adapter_storage_dtype"],
                        actual_adapter_present=bool(self._identity.get("checkpoint")),
                        reused_generation_code="candidate_runtime_v020.CandidateActor._generate_tokens")
                else:
                    from .candidate_runtime_v020 import Float32SamplingProcessor
                    processor = Float32SamplingProcessor(trace)
                    generated = self.model.generate(input_ids=inputs, attention_mask=torch.ones_like(inputs),
                        logits_processor=[processor], **options)
                    metadata = {"version": VERSION, "entry": "upstream_HF_model.generate",
                        "attention": "sdpa", "sampling_normalization_dtype": "float32",
                        "sampler_input_score_dtypes": sorted(processor.observed_input_dtypes),
                        "normalization_calls": processor.calls}
            output_ids = generated[0, len(record["input_ids"]):].tolist()
            probabilities = trace.finish(generated)[0]
            elapsed = time.monotonic() - started
            finish = completion_kind(output_ids, self.contract, elapsed)
            if len(probabilities) != len(output_ids):
                raise ValueError("Chosen-token sampling record is incomplete")
            self._verify_execution()
            result = {"version": VERSION, "attempt_id": attempt_id,
                "path": self.path, "input": copy.deepcopy(record),
                "actor_identity": self.freeze_identity(), "output_ids": output_ids,
                "raw_generated_text": self.tokenizer.decode(output_ids, skip_special_tokens=False),
                "behavior_logprobs": probabilities, "finish_reason": finish,
                "usage": {"prompt_tokens": len(record["input_ids"]), "completion_tokens": len(output_ids),
                          "total_tokens": len(record["input_ids"]) + len(output_ids)},
                "effective_generation": options, "execution_metadata": metadata,
                "sampling_processor": {"temperature": self.contract["temperature"],
                    "top_k": self.contract["top_k"], "top_p": self.contract["top_p"],
                    "order": ["float32", "temperature", "HF_top_k", "HF_top_p", "log_softmax"],
                    "behavior_logprobs_scope": "actual final filtered sampling distribution"},
                "seconds": elapsed, "max_time_scope": "HF iteration stopping; outer process guard still required",
                "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0}
            atomic_write(self.output / "calls" / (attempt_id + "-complete.json"), json_bytes(result))
            return result
        except Exception as error:
            atomic_write(self.output / "calls" / (attempt_id + "-fault.json"), json_bytes({
                **attempt, "elapsed_seconds": time.monotonic() - started,
                "error": {"type": type(error).__name__, "message": str(error)},
                "actual_usage": None, "automatic_retry_allowed": False}))
            raise
        finally:
            if hasattr(self.model, "_cache"):
                delattr(self.model, "_cache")
            self.busy = False

    def complete(self, request, *, timeout_seconds):
        """Keep actual IDs/usage and a separate native record for world clients."""
        from .candidate_runtime_v017 import parse_candidate_generated
        from .deterministic_work_v024 import deterministic_tool_ids
        call_id = "calibration_" + uuid.uuid4().hex
        started = time.monotonic()
        record, result = None, None
        try:
            if (request.get("temperature") != self.contract["temperature"]
                    or request.get("max_tokens") != self.contract["max_output_tokens"]
                    or request.get("stream")
                    or any(k in request for k in ("top_p", "top_k", "logit_bias", "frequency_penalty", "presence_penalty"))):
                raise ValueError("Request differs from the frozen bridge decoder")
            record = prepare_native_input(self.tokenizer, request, self.contract)
            result = self.generate_native(record)
            message, error = parse_candidate_generated(result["raw_generated_text"], request)
            message = deterministic_tool_ids(message, request, result["raw_generated_text"])
            ids, outputs = record["input_ids"], result["output_ids"]
            body = {"id": call_id, "object": "chat.completion", "model": request["model"],
                "actor_identity": self.freeze_identity(), "online_window_id": self.window_id,
                "system_fingerprint": self._identity["policy_version"],
                "choices": [{"index": 0, "message": message, "finish_reason":
                    "tool_calls" if message.get("tool_calls") and result["finish_reason"] == "stop"
                    else "length" if result["finish_reason"] == "time_limit" else result["finish_reason"]}],
                "native_finish_reason": result["finish_reason"],
                "usage": result["usage"], "raw_generated_text": result["raw_generated_text"],
                "protocol_parse_error": error, "prompt_projection": record,
                "inference_profile": self.inference_profile, "inference_profile_sha256": self.inference_profile_sha256,
                "generation_stop_check": {"raw_output_tokens": len(outputs), "retained_output_tokens": len(outputs),
                    "eos_token_ids": self.contract["eos_token_ids"], "all_generated_tokens_retained": True},
                "effective_generation": result["effective_generation"],
                "token_trace": {"input_ids": ids, "output_ids": outputs, "raw_output_ids": outputs,
                    "input_mask": [0] * len(ids), "output_mask": [1] * len(outputs),
                    "raw_behavior_logprobs": result["behavior_logprobs"], "behavior_logprobs": result["behavior_logprobs"],
                    "sampling_temperature": self.contract["temperature"], "sampling_top_p": self.contract["top_p"],
                    "sampling_top_k": self.contract["top_k"], "source": "actual generation IDs"},
                "service_record": {"transport_kind": "resident_direct", "batch_size": 1,
                    "actual_network_http_calls": 0, "seconds": result["seconds"],
                    "execution_optimization": result["execution_metadata"]}}
            status = 200
        except DirectContextLimit as error:
            status = 400
            body = {"error": {"code": "context_length_exceeded", "message": str(error)},
                    "generation_started": False, "transport_kind": "resident_direct"}
        except Exception as error:
            status = 503
            body = {"error": {"code": "calibration_inference_error", "type": type(error).__name__, "message": str(error)}}
        atomic_write(self.output / "calls" / (call_id + ".json"), json_bytes({
            "request": request, "native_input": record, "native_result": result, "response": body,
            "status": status, "timeout_seconds_declared": timeout_seconds,
            "elapsed_seconds": time.monotonic() - started}))
        return {"http_status": status, "body": body, "raw_body": json_bytes(body).decode(),
                "response_headers": {"x-transport": "resident-direct"}, "response_redactions": []}

    def update_window(self, *args, **kwargs):
        raise ValueError("v051 calibration forbids all learner operations")

    learning_logprobs = update_window
    export_sampling_snapshot = update_window
    save_checkpoint = update_window


def load_actor(model_path, *, manifest, contract, path, output, checkpoint=None):
    """Load raw release or only a declared checkpoint's actor, never optimizers.

    CPU control/tests do not call this function.  Caller provides global resource
    admission, process timeout and plan sealing before allowing any GPU load.
    """
    contract = validate_contract(contract)
    if path not in PATHS or path == "reference" and checkpoint is not None:
        raise ValueError("Reference is raw; checkpoint inference uses the project path")
    if Path(output).exists():
        raise FileExistsError("Calibration output already exists; no overwritten model attempt")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in {str(i) for i in range(8)}:
        raise ValueError("Bind exactly one approved physical GPU before model loading")
    model_path = Path(model_path).resolve()
    identity = read_json(Path(manifest))
    registered = CHECKPOINTS["qwen3.5-9b"]
    if (identity.get("repo_id") != registered["repo_id"]
            or identity.get("declared_hf_revision") != registered["revision"]):
        raise ValueError("Only the frozen raw Qwen3.5-9B release is admitted")
    files = identity.get("files", {})
    if not files or not any(name.endswith(".safetensors") for name in files):
        raise ValueError("Original complete weight manifest required")
    for name, item in files.items():
        target = (model_path / name).resolve()
        if (not target.is_relative_to(model_path) or target.stat().st_size != item["bytes"]
                or sha_file(target) != item["sha256"]):
            raise ValueError("Raw model source changed: " + name)

    import torch
    from transformers import AutoConfig, AutoTokenizer, GenerationConfig, Qwen3_5ForCausalLM
    from .candidate_runtime_v0201 import HeadExecution

    if torch.cuda.device_count() != 1 or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise ValueError("One native BF16 CUDA device is required; no offload/fallback")
    torch.set_num_threads(8)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    config = AutoConfig.from_pretrained(model_path, local_files_only=True)
    if config.model_type != "qwen3_5":
        raise ValueError("Require original official Qwen3.5 text architecture")
    text_config = config.get_text_config()
    if contract["context_limit"] > text_config.max_position_embeddings:
        raise ValueError("Declared context exceeds native model support; no RoPE changes")
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    tokenizer.padding_side = "left"
    tokenizer.pad_token_id = contract["pad_token_id"]
    if tokenizer.eos_token_id != CHAT_STOP["native_end_token_id"]:
        raise ValueError("Original native tokenizer stop changed")
    network, info = Qwen3_5ForCausalLM.from_pretrained(model_path, config=text_config,
        local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa",
        device_map={"": 0}, output_loading_info=True, use_kernels=False)
    if (info.get("missing_keys") or info.get("mismatched_keys") or info.get("error_msgs")
            or any(not key.startswith(("model.visual.", "mtp.")) for key in info.get("unexpected_keys", []))):
        raise ValueError("Official text backbone did not load exactly")
    policy = {"base_manifest": reference(manifest), "base_revision": registered["revision"],
        "model_path": str(model_path),
        "raw_release": checkpoint is None, "trained_adapter_loaded": checkpoint is not None,
        "checkpoint": None, "adapter_sha256": None}
    historical_steps = (0, 0)
    if checkpoint is not None:
        from peft import LoraConfig, get_peft_model
        from .online_training import tensor_tree_digest
        checkpoint_path = Path(checkpoint).resolve()
        saved = read_json(checkpoint_path)
        if (saved.get("actor_steps"), saved.get("critic_steps")) != (4, 4):
            raise ValueError("CAL U accepts only the predeclared S-star 4/4, not a selected v050 endpoint")
        state_path = checkpoint_path.parent / "shared-state.pt"
        if sha_file(state_path) != saved["state"]["sha256"]:
            raise ValueError("Complete source checkpoint bytes changed")
        state = torch.load(state_path, map_location="cpu", weights_only=True)
        if (tensor_tree_digest(state, torch) != saved["state_tensor_digest"]
                or state["actor_identity"] != saved["actor_identity"]
                or saved["actor_identity"]["base_manifest_sha256"] != reference(manifest)["sha256"]):
            raise ValueError("Complete checkpoint source identity is invalid")
        network = get_peft_model(network, LoraConfig(r=8, lora_alpha=16, lora_dropout=0,
            target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"))
        parameters = {name: value for name, value in network.named_parameters() if "lora_" in name}
        if set(parameters) != set(state["actor"]):
            raise ValueError("Checkpoint adapter names differ from the frozen model")
        with torch.no_grad():
            for name, value in parameters.items():
                original = state["actor"][name]
                if value.shape != original.shape or original.dtype != torch.float32:
                    raise ValueError("Checkpoint adapter shape or FP32 dtype changed")
                value.data = value.data.float()
                value.copy_(original.to(value.device))
        actual = tensor_tree_digest({name: value.detach().cpu() for name, value in parameters.items()}, torch)
        if actual != saved["actor_identity"]["adapter_sha256"]:
            raise ValueError("Loaded actor differs from source checkpoint")
        historical_steps = (saved["actor_steps"], saved["critic_steps"])
        policy.update(checkpoint=reference(checkpoint_path), adapter_sha256=actual,
            source_actor_identity=copy.deepcopy(saved["actor_identity"]),
            checkpoint_import_scope="actor tensors only; complete source digest verified; critic/Adam/RNG not installed")
        del state
    for parameter in network.parameters():
        parameter.requires_grad_(False)
    head = network.get_output_embeddings()
    if type(head) is not torch.nn.Linear or head.bias is not None or network.config.tie_word_embeddings:
        raise ValueError("Require original untied bias-free output projection")
    head.to(dtype=torch.float32)
    head_execution = HeadExecution(head, torch)
    from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface
    from transformers.modeling_utils import AttentionInterface
    from .candidate_runtime_v020 import ATTENTION, bf16_attention_forward
    AttentionInterface.register(ATTENTION, bf16_attention_forward)
    AttentionMaskInterface.register(ATTENTION, ALL_MASK_ATTENTION_FUNCTIONS["sdpa"])
    if path == "project":
        network.set_attn_implementation(ATTENTION)
    network.generation_config = GenerationConfig(eos_token_id=list(contract["eos_token_ids"]),
        pad_token_id=tokenizer.pad_token_id, bos_token_id=tokenizer.bos_token_id)
    network.generation_config._from_model_config = False
    network.config.use_cache = False
    network.eval()
    actor = CalibrationActor(network, tokenizer, contract=contract, path=path, output=output,
        identity=policy, torch_module=torch, head_execution=head_execution,
        historical_steps=historical_steps)
    atomic_write(actor.output / "loading.json", json_bytes({**loading_info_record(info),
        "original_weight_manifest": reference(manifest), "checkpoint": policy["checkpoint"],
        "new_optimizer_steps": 0, "new_backward_calls": 0, "critic_constructed": False,
        "optimizer_constructed": False, "raw_has_no_adapter_modules": checkpoint is None}))
    return actor
