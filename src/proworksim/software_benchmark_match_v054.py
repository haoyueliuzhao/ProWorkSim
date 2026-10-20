"""Native OpenHands MATCH transport over the unchanged project raw generator.

Only request rendering and transport/accounting are new. Numerical generation
is delegated to CalibrationActor.generate_native with its original contract.
Formal dispatch is disabled unless a caller supplies separate authorization.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
import threading
import time

from .storage import atomic_write, digest, json_bytes

VERSION = "software-benchmark-match-v054"
CONTRACT = {
    "context_limit": 18432, "max_output_tokens": 2048,
    "enable_thinking": False, "preserve_thinking": False,
    "temperature": 0.7, "top_p": 1.0, "top_k": 0, "repetition_penalty": 1.0,
    "eos_token_ids": [248044, 248046], "pad_token_id": 248044,
    "max_generation_seconds": 600,
}
TOOL_NAMES = frozenset({"terminal", "file_editor", "task_tracker", "finish", "think"})


class DispatchStopped(BaseException):
    """A terminal boundary; SDK retries must not turn it into another sample."""


class AccountingFault(DispatchStopped):
    """Unknown execution/accounting remains unknown, with reservation retained."""


def write_new(path, value):
    path = Path(path)
    body = json_bytes(value)
    with path.open("xb") as stream:
        stream.write(body)
    return {"path": str(path), "sha256": digest(body)}


def normalize_native_messages(messages):
    """Preserve the SDK's text/history fields and convert tool JSON arguments."""
    rows = copy.deepcopy(messages)
    for row in rows:
        if row.get("role") not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported native message role")
        if row.get("content") is None:
            row["content"] = ""
        content = row["content"]
        if not isinstance(content, str) and not (
                isinstance(content, list)
                and all(isinstance(part, dict) and part.get("type") == "text"
                        and isinstance(part.get("text"), str) for part in content)):
            raise ValueError("Only the SDK's text/string blocks are allowed")
        for call in row.get("tool_calls") or []:
            arguments = call["function"]["arguments"]
            if isinstance(arguments, str):
                call["function"]["arguments"] = json.loads(arguments)
            if not isinstance(call["function"]["arguments"], dict):
                raise ValueError("Native function arguments must be an object")
    return rows


def prepare_native_input(tokenizer, request, contract=CONTRACT):
    """Use the raw model template without project text or tool restrictions.

    The original native-input schema is retained so the unchanged numerical
    provider can validate it. Its new rendering identity is explicitly recorded.
    """
    from .software_calibration_runtime_v051 import (
        VERSION as GENERATOR_SCHEMA, validate_contract, validate_native_input,
    )
    contract = validate_contract(contract)
    messages = normalize_native_messages(request["messages"])
    tools = copy.deepcopy(request.get("tools") or [])
    kwargs = {key: contract[key] for key in ("enable_thinking", "preserve_thinking")}
    rendered = tokenizer.apply_chat_template(
        messages, tools=tools, tokenize=False, add_generation_prompt=True, **kwargs)
    ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
    record = {
        "version": GENERATOR_SCHEMA,
        "renderer_version": VERSION + "-unmodified-native-template",
        "contract_sha256": digest(json_bytes(contract)),
        "request_sha256": digest(json_bytes(request)),
        "normalized_messages_sha256": digest(json_bytes(messages)),
        "actual_prompt_messages": messages, "rendered_prompt": rendered,
        "rendered_prompt_sha256": digest(rendered.encode()),
        "input_ids": ids, "input_ids_sha256": digest(json_bytes(ids)),
        "prompt_tokens": len(ids), "chat_template_kwargs": kwargs,
        "single_call_hint_applied": False,
        "context_limit": contract["context_limit"],
        "requested_output_tokens": contract["max_output_tokens"],
        "fits": len(ids) + contract["max_output_tokens"] <= contract["context_limit"],
    }
    record["sha256"] = digest(json_bytes(record))
    validate_native_input(record, contract)
    return record


def serialize_sdk_request(messages, tools, *, add_security_risk_prediction=False,
                          formatted_messages=None):
    if formatted_messages is None:
        raise ValueError("Supply messages from the official SDK format_messages_for_llm")
    return {
        "model": "raw-qwen3.5-9b-v054-match",
        "messages": copy.deepcopy(formatted_messages),
        "tools": [
            dict(tool.to_openai_tool(
                add_security_risk_prediction=add_security_risk_prediction))
            for tool in (tools or [])
        ],
        "temperature": CONTRACT["temperature"],
        "max_tokens": CONTRACT["max_output_tokens"],
        "stream": False, "tool_choice": "auto",
    }


@dataclass
class EpisodeLedger:
    identity: dict
    token_limit: int = 500000
    attempt_limit: int = 128
    decision_limit: int = 128
    attempts: int = 0
    decisions: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    inflight: dict | None = None
    calls: list = field(default_factory=list)

    @property
    def actual(self):
        return self.prompt_tokens + self.completion_tokens

    def admit(self, native, usage_id):
        if self.inflight is not None:
            raise AccountingFault("An unresolved attempt cannot be replayed")
        if usage_id not in {"agent", "condenser"}:
            raise ValueError("Only the single agent and its own condenser may call")
        if self.attempts >= self.attempt_limit:
            raise DispatchStopped("all_model_attempt_limit")
        if usage_id == "agent":
            if self.decisions >= self.decision_limit:
                raise DispatchStopped("agent_decision_limit")
            self.decisions += 1
        if native["fits"] is not True:
            raise DispatchStopped("full_context_preexecution_rejection")
        reservation = native["prompt_tokens"] + CONTRACT["max_output_tokens"]
        if reservation > self.token_limit - self.actual:
            raise DispatchStopped("full_input_and_output_reservation_insufficient")
        return reservation

    def reserve(self, native, usage_id, request_ref, reservation):
        if self.inflight is not None or reservation != native["prompt_tokens"] + 2048:
            raise AccountingFault("Invalid or overlapping reservation")
        self.attempts += 1
        self.inflight = {
            "attempt": self.attempts, "usage_id": usage_id,
            "reservation": reservation, "request": request_ref,
            "native_input_sha256": native["sha256"],
        }

    def settle(self, native, result, response_ref):
        usage = result.get("usage", {})
        ids = result.get("output_ids")
        if (self.inflight is None or result.get("actor_identity") != self.identity
                or result.get("input") != native
                or self.inflight["native_input_sha256"] != native["sha256"]
                or not isinstance(ids, list)
                or any(type(token) is not int or token < 0 for token in ids)
                or not 0 < len(ids) <= CONTRACT["max_output_tokens"]
                or any(type(usage.get(key)) is not int for key in
                       ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != native["prompt_tokens"]
                or usage["completion_tokens"] != len(ids)
                or usage["total_tokens"] != usage["prompt_tokens"] + len(ids)
                or usage["total_tokens"] > self.inflight["reservation"]
                or not isinstance(result.get("raw_generated_text"), str)
                or not result.get("attempt_id")
                or any(call["native_attempt_id"] == result["attempt_id"] for call in self.calls)
                or result.get("finish_reason") not in {"stop", "length", "time_limit"}
                or (result.get("finish_reason") == "length" and len(ids) != 2048)
                or (result.get("finish_reason") == "stop"
                    and (ids[-1] not in CONTRACT["eos_token_ids"]
                         or any(token in CONTRACT["eos_token_ids"] for token in ids[:-1])))):
            raise AccountingFault("Actual identity, complete output and usage cannot settle")
        self.prompt_tokens += usage["prompt_tokens"]
        self.completion_tokens += usage["completion_tokens"]
        self.calls.append({
            **self.inflight, "response": response_ref,
            "native_attempt_id": result["attempt_id"], "usage": copy.deepcopy(usage),
            "native_finish_reason": result["finish_reason"],
        })
        self.inflight = None

    def snapshot(self):
        usage = {}
        for call in self.calls:
            totals = usage.setdefault(call["usage_id"], {"prompt_tokens": 0, "completion_tokens": 0})
            for key in totals:
                totals[key] += call["usage"][key]
        return {
            "attempts": self.attempts, "decisions": self.decisions,
            "known_actual_tokens": self.actual,
            "complete_actual_tokens": self.actual if self.inflight is None else None,
            "uncertain_reserved_tokens": self.inflight["reservation"] if self.inflight else 0,
            "inflight": copy.deepcopy(self.inflight), "calls": copy.deepcopy(self.calls),
            "per_usage_id": usage, "all_model_attempt_limit": self.attempt_limit,
            "agent_decision_limit": self.decision_limit, "token_limit": self.token_limit,
            "local_dollar_cost_estimate": None, "automatic_retry": False,
        }


class MatchBridge:
    """One ledger and generator shared by agent and condenser LLM copies."""

    def __init__(self, owner, *, codec, folder, slot_id,
                 execution_authorized=False, allow_programmed_fixture=False):
        from .software_calibration_runtime_v051 import CalibrationActor
        identity = owner.freeze_identity()
        self.formal = isinstance(owner, CalibrationActor)
        if (owner.path != "project" or owner.contract != CONTRACT
                or identity.get("raw_release") is not True
                or identity.get("checkpoint") is not None
                or identity.get("adapter_sha256") is not None
                or identity.get("trained_adapter_loaded", False)):
            raise ValueError("MATCH requires the same raw project numerical owner")
        if not self.formal and not (
                allow_programmed_fixture and getattr(owner, "programmed_fixture", False)):
            raise ValueError("A programmed owner must be explicitly identified as a CPU fixture")
        if self.formal and (
                identity.get("base_revision") != "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
                or identity.get("base_manifest", {}).get("sha256")
                != "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6"
                or owner.inference_profile.get("base_storage_dtype")
                != "bfloat16_backbone_float32_lm_head"
                or owner.inference_profile.get("path") != "project"
                or owner.inference_profile.get("contract") != CONTRACT):
            raise ValueError("The real owner does not match the pinned raw source and project profile")
        if execution_authorized and not self.formal:
            raise ValueError("A programmed fixture cannot be admitted as a formal model")
        if execution_authorized:
            from .software_benchmark_codec_v054 import VERSION as CODEC_VERSION, UnixSocketCodec
            if (not isinstance(codec, UnixSocketCodec)
                    or codec.expected_identity.get("version") != CODEC_VERSION
                    or codec.expected_identity.get("vllm_version") != "0.32.0"
                    or codec.expected_identity.get("tool_call_parser") != "qwen3_coder"
                    or codec.expected_identity.get("tokenizer_source_manifest_sha256")
                    != identity.get("base_manifest", {}).get("sha256")
                    or owner.generate_native.__func__ is not CalibrationActor.generate_native):
                raise ValueError("Formal MATCH requires the unchanged generator and pinned external codec")
        self.owner, self.codec = owner, codec
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.slot_id = slot_id
        self.authorized = execution_authorized
        self.fixture = allow_programmed_fixture and not self.formal
        self.identity = identity
        self.ledger = EpisodeLedger(identity)
        self.started = time.monotonic()
        self.halted = None
        self.lock = threading.Lock()
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "version": VERSION, "slot_id": self.slot_id, "actor_identity": self.identity,
            "formal_native_owner": self.formal, "programmed_fixture": self.fixture,
            "formal_execution_authorized": self.authorized, "halted": self.halted,
            **self.ledger.snapshot(),
        }))

    def prepare(self, request):
        if self.owner.freeze_identity() != self.identity:
            raise AccountingFault("The bound raw owner identity changed")
        return prepare_native_input(self.owner.tokenizer, request, self.owner.contract)

    def complete_request(self, request, *, usage_id):
        """One provider attempt, with its actual cost settled before decoding."""
        with self.lock:
            if self.halted:
                raise DispatchStopped("episode_already_stopped:" + self.halted)
            if not self.authorized and not self.fixture:
                raise DispatchStopped("formal_model_execution_not_authorized")
            if (request.get("temperature") != CONTRACT["temperature"]
                    or request.get("max_tokens") != 2048 or request.get("stream")
                    or any(key in request for key in
                           ("top_p", "top_k", "logit_bias", "presence_penalty",
                            "frequency_penalty", "stop"))):
                raise ValueError("Request cannot override the project numerical contract")
            names = {tool["function"]["name"] for tool in request.get("tools", [])}
            if ((usage_id == "agent" and names != TOOL_NAMES)
                    or (usage_id == "condenser" and names)):
                raise ValueError("Agent keeps all native tools; condenser uses no tools")
            try:
                if time.monotonic() - self.started >= 5400:
                    raise DispatchStopped("soft_deadline_before_generation")
                native = self.prepare(request)
                reservation = self.ledger.admit(native, usage_id)
                index = self.ledger.attempts + 1
                request_ref = write_new(self.folder / f"request-{index:04d}.json", {
                    "slot_id": self.slot_id, "usage_id": usage_id,
                    "request": request, "native_input": native,
                })
                self.ledger.reserve(native, usage_id, request_ref, reservation)
                self.save()
                result = self.owner.generate_native(native)
                response_ref = write_new(
                    self.folder / f"native-response-{index:04d}.json", result)
                self.ledger.settle(native, result, response_ref)
                self.save()
                if time.monotonic() - self.started >= 6000:
                    raise DispatchStopped("hard_deadline_after_generation")
                # The codec must be the same pinned official parser as REF.
                decoded = self.codec.decode(request=request, result=result)
                message = decoded["message"]
                if not isinstance(message, dict) or message.get("role") != "assistant":
                    raise ValueError("Official parser returned no assistant message")
                finish = result["finish_reason"]
                if finish == "time_limit":
                    finish = "length"
                elif finish == "stop" and message.get("tool_calls"):
                    finish = "tool_calls"
                body = {
                    "id": "v054-match-" + result["attempt_id"],
                    "object": "chat.completion", "model": request["model"],
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                    "usage": result["usage"], "native_finish_reason": result["finish_reason"],
                }
                write_new(self.folder / f"sdk-response-{index:04d}.json", {
                    "body": body, "codec": decoded.get("codec_identity"),
                    "native_response": response_ref,
                })
                return body
            except BaseException as error:
                self.halted = f"{type(error).__name__}:{error}"
                self.save()
                if isinstance(error, DispatchStopped):
                    raise
                raise AccountingFault(self.halted) from error

    def sdk_completion(self, messages, tools, *, usage_id, kwargs, formatted_messages):
        from litellm.types.utils import ModelResponse
        from openhands.sdk.llm import Message
        from openhands.sdk.llm.llm_response import LLMResponse
        from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage

        unexpected = set(kwargs) - {"add_security_risk_prediction", "on_token", "call_context"}
        if unexpected:
            raise ValueError("Unfrozen SDK generation kwargs: " + ",".join(sorted(unexpected)))
        request = serialize_sdk_request(
            messages, tools,
            add_security_risk_prediction=bool(kwargs.get("add_security_risk_prediction")),
            formatted_messages=formatted_messages)
        body = self.complete_request(request, usage_id=usage_id)
        raw = ModelResponse(**body)
        totals = self.ledger.snapshot()["per_usage_id"][usage_id]
        return LLMResponse(
            message=Message.from_llm_chat_message(raw.choices[0].message), raw_response=raw,
            metrics=MetricsSnapshot(model_name=request["model"],
                                    accumulated_token_usage=TokenUsage(
                                        model=request["model"], **totals)))


@lru_cache(maxsize=1)
def sdk_llm_type():
    from openhands.sdk import LLM
    from pydantic import PrivateAttr

    class NativeMatchLLM(LLM):
        _bridge: object = PrivateAttr(default=None)

        def resolve_runtime_metadata(self):
            return None

        def completion(self, messages, tools=None, **kwargs):
            return self._bridge.sdk_completion(
                messages, tools or [], usage_id=self.usage_id, kwargs=kwargs,
                formatted_messages=self.format_messages_for_llm(messages))

        async def acompletion(self, messages, tools=None, **kwargs):
            # The provider is synchronous and each episode serializes dispatch.
            # No implicit retry, provider fallback or second generation occurs.
            return self.completion(messages, tools, **kwargs)

        def get_token_count(self, messages, tools=None, **kwargs):
            if not messages:
                return 0
            request = serialize_sdk_request(
                messages, tools,
                add_security_risk_prediction=bool(kwargs.get("add_security_risk_prediction")),
                formatted_messages=self.format_messages_for_llm(messages))
            return self._bridge.prepare(request)["prompt_tokens"]

    return NativeMatchLLM


def build_llm(bridge):
    llm = sdk_llm_type()(
        model="openai/Qwen3.5-9B", usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        max_input_tokens=16384, max_output_tokens=2048, temperature=0.7,
    )
    llm._bridge = bridge
    return llm
