"""Key-free episode/SDK adapter and trusted-host DeepSeek broker operations.

Controllers receive only an injected broker callable. API keys and the cash
ledger live in HostDeepSeekTransport's client, never in the actor/controller.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time

from . import software_benchmark_deepseek_contract_v064 as api
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_deepseek_interfaces_v055 import (
    NATIVE_TOOLS, ReasoningHistory, RemoteEpisodeBoundary as LegacyBoundary, native_llm_type,
)
from .software_benchmark_deepseek_prefix_v055_r2 import (
    count_incomplete_prefix, pending_tail_tool_ids, restore_prefix_reasoning,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "v064-key-free-remote-episode-adapter-r1"
BUDGETS = frozenset((5_000_000, 7_500_000, 10_000_000))


class RemoteEpisodeBoundary(LegacyBoundary):
    """No HTTP request was made for this call; its team reservation may cancel."""

    before_dispatch_proven = True

    def __init__(self, classification):
        super().__init__(classification)
        self.classification = classification


class EpisodeLedger:
    def __init__(self, token_budget):
        self.token_budget = token_budget
        self.calls, self.inflight = [], None
        self.attempts = self.decisions = self.actual = 0

    def snapshot(self):
        per_usage = {}
        for call in self.calls:
            value = per_usage.setdefault(call["usage_id"], {"prompt_tokens": 0, "completion_tokens": 0})
            for key in value:
                value[key] += call["usage"][key]
        return {
            "version": VERSION, "attempts": self.attempts, "decisions": self.decisions,
            "known_actual_tokens": self.actual,
            "complete_actual_tokens": self.actual if self.inflight is None else None,
            "uncertain_reserved_tokens": self.inflight["reservation"] if self.inflight else 0,
            "inflight": copy.deepcopy(self.inflight), "calls": copy.deepcopy(self.calls),
            "per_usage_id": per_usage, "token_limit": self.token_budget,
            "all_model_attempt_limit": 512, "agent_decision_limit": 512,
            "reasoning_tokens_included_in_completion_tokens": True,
            "seed_supported_by_provider": False, "automatic_retry": False,
        }


class DeepSeekEpisodeAdapter:
    model = api.MODEL
    thinking = True

    def __init__(self, *, post, arm, slot_id, condition_id, token_budget, folder,
                 allowed_tool_names, soft_at=None, hard_at=None):
        if arm not in {"REF", "PROJECT"} or type(token_budget) is not int or token_budget not in BUDGETS:
            raise ValueError("Use a frozen v064 arm and per-episode token budget")
        self.post, self.arm = post, arm
        self.slot_id, self.condition_id = slot_id, condition_id
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.allowed_tool_names = frozenset(allowed_tool_names)
        self.limits = {"context_limit": api.CONTEXT_TOKENS, "max_output_tokens": api.MAX_OUTPUT_TOKENS}
        self.maximum_input_tokens, self.maximum_output_tokens = api.MAX_INPUT_TOKENS, api.MAX_OUTPUT_TOKENS
        self.soft_at, self.hard_at = soft_at, hard_at
        self.ledger, self.history = EpisodeLedger(token_budget), ReasoningHistory()
        self.lock, self.halted = threading.Lock(), None
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "slot_id": self.slot_id, "condition_id": self.condition_id, "arm": self.arm,
            "model": self.model, "thinking": True, "limits": self.limits,
            "sampling": {"reasoning_effort": "high", "top_p": 0.95},
            "halted": self.halted, **self.ledger.snapshot(),
        }))

    def request(self, messages, tools):
        value = {
            "model": self.model, "messages": self.history.restore(messages, thinking=True),
            "max_tokens": self.maximum_output_tokens, "stream": False,
            "thinking": {"type": "enabled"}, "reasoning_effort": "high", "top_p": 0.95,
            "user_id": api.slot_user_id(self.slot_id, self.condition_id),
        }
        if tools:
            value.update(tools=copy.deepcopy(tools), tool_choice="auto")
        api.validate_payload(value, self.allowed_tool_names)
        return value

    def _measurement(self, request, result, *, prefix=False):
        expected = digest(json_bytes(request))
        if (type(result.get("prompt_tokens")) is not int or result["prompt_tokens"] <= 0
                or not isinstance(result.get("method"), str)
                or result.get("request_sha256") != expected
                or (prefix and result.get("count_only_not_dispatchable") is not True)):
            raise ValueError("Remote count lacks the exact request and counting provenance")
        return {**result, "context_limit": api.CONTEXT_TOKENS,
                "exact_provider_token_ids_available": False}

    def count(self, request):
        return self._measurement(request, self.post("/tokenize", {"wire": request}))

    def count_prefix(self, request, pending):
        return self._measurement(request, self.post("/tokenize-prefix", {
            "wire": request, "pending_ids": list(pending)}), prefix=True)

    def _record(self, inflight, body):
        normalized = api.normalize_usage(body)
        ref = write_new(self.folder / f"response-{inflight['attempt']:04d}.json", body)
        self.ledger.calls.append({**inflight, "usage": copy.deepcopy(body["usage"]),
                                  "normalized_usage": normalized, "response": ref,
                                  "response_id": body["id"]})
        self.ledger.actual += normalized["total_tokens"]
        self.ledger.inflight = None
        return normalized

    def complete(self, request, usage_id="agent"):
        if usage_id not in {"agent", "condenser"}:
            raise ValueError("Only the one agent and its condenser may generate")
        with self.lock:
            if self.halted or self.ledger.inflight:
                raise RemoteEpisodeBoundary("episode_closed_or_uncertain_usage")
            if self.soft_at is not None and time.monotonic() >= self.soft_at:
                raise RemoteEpisodeBoundary("soft_deadline_before_dispatch")
            if request != self.request(request["messages"], request.get("tools")):
                raise ValueError("Request differs from the fixed provider configuration")
            if usage_id == "condenser" and request.get("tools"):
                raise ValueError("The original condenser cannot acquire tools")
            if self.arm == "REF" and usage_id == "agent":
                if {tool["function"]["name"] for tool in request.get("tools", [])} != NATIVE_TOOLS:
                    raise ValueError("Native REF must retain its exact five local tools")
            measured = self.count(request)
            reservation = measured["prompt_tokens"]+self.maximum_output_tokens
            if measured["prompt_tokens"] > self.maximum_input_tokens:
                raise RemoteEpisodeBoundary("conservative_context_reservation_exhausted")
            if self.ledger.attempts >= 512 or (usage_id == "agent" and self.ledger.decisions >= 512):
                raise RemoteEpisodeBoundary("episode_call_limit")
            if self.ledger.actual+reservation > self.ledger.token_budget:
                raise RemoteEpisodeBoundary("episode_token_reservation_exhausted")
            index = self.ledger.attempts+1
            ref = write_new(self.folder / f"request-{index:04d}.json", {
                "request": request, "measurement": measured, "usage_id": usage_id})
            inflight = {"attempt": index, "usage_id": usage_id, "reservation": reservation,
                        "request": ref, "request_id": self.slot_id+f":{index:04d}"}
            self.ledger.inflight = inflight
            self.ledger.attempts += 1
            self.ledger.decisions += usage_id == "agent"
            self.save()

            def unstarted(reason):
                self.ledger.inflight = None
                self.ledger.attempts -= 1
                self.ledger.decisions -= usage_id == "agent"
                self.halted = reason
                self.save()
                raise RemoteEpisodeBoundary(reason)

            try:
                while True:
                    if self.soft_at is not None and time.monotonic() >= self.soft_at:
                        unstarted("soft_deadline_during_provider_admission_wait")
                    try:
                        body = self.post("/chat/completions", {
                            "wire": request, "request_id": inflight["request_id"],
                            "slot_id": self.slot_id, "condition": self.condition_id,
                            "usage_id": usage_id, "prompt_upper_bound": measured["prompt_tokens"],
                        })
                        break
                    except api.PreDispatchConcurrencyBusy:
                        time.sleep(0.5)
            except api.PreDispatchBudgetStopped as error:
                unstarted(str(error))
            except api.ProviderOutputBoundViolation as error:
                if error.authoritative_response is not None:
                    self._record(inflight, error.authoritative_response)
                self.halted = str(error)
                self.save()
                raise
            except BaseException as error:
                self.halted = type(error).__name__
                self.save()
                raise
            try:
                normalized = self._record(inflight, body)
                if (normalized["input_tokens"] > measured["prompt_tokens"]
                        or normalized["output_tokens"] > self.maximum_output_tokens):
                    raise api.ProviderOutputBoundViolation("actual_usage_exceeded_engineering_reservation", body=body)
                message = body["choices"][0]["message"]
                if request.get("tools") and not isinstance(message.get("reasoning_content"), str):
                    raise api.ProviderOutputBoundViolation("missing_original_thinking_response", body=body)
                self.history.remember(message)
                self.save()
                return body
            except BaseException as error:
                self.halted = type(error).__name__
                self.save()
                raise


class HostDeepSeekTransport:
    """Trusted host broker operations; no arbitrary URL, path or tool endpoint."""

    port = 18219
    timeout_seconds = 1800

    def __init__(self, *, client, counter, metadata_dir, authorize, slot_id=None, condition_id=None):
        self.client = client.fork_for_episode() if slot_id is not None else client
        self.counter, self.authorize = counter, authorize
        self.slot_id, self.condition_id = slot_id, condition_id
        self.folder = Path(metadata_dir)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._guard, self._slot_locks = threading.Lock(), {}

    def validate_identity(self, slot_id):
        if self.slot_id != slot_id or not isinstance(self.condition_id, str):
            raise ValueError("The episode host broker is not bound to this slot/condition")

    def abort(self):
        # Runtime callers must inject a fork_for_episode client, never a shared
        # HTTP transport. The SQLite cash ledger remains shared and untouched.
        if self.slot_id is None:
            raise ValueError("Only an episode-bound broker can be cancelled")
        self.client.transport.abort()

    def post(self, path, payload):
        if path not in {"/tokenize", "/tokenize-prefix", "/chat/completions"}:
            raise ValueError("No search, fetch, external URL or arbitrary broker operation")
        wire = payload["wire"]
        api.validate_payload(wire, self.client.allowed_tool_names)
        if path == "/tokenize":
            if set(payload) != {"wire"}:
                raise ValueError("Unexpected tokenization extension")
            return self.counter(wire)
        if path == "/tokenize-prefix":
            if set(payload) != {"wire", "pending_ids"}:
                raise ValueError("Unexpected count-only prefix extension")
            pending = tuple(payload["pending_ids"])
            if not pending or pending_tail_tool_ids(wire["messages"]) != pending:
                raise ValueError("Only the original incomplete tool tail may be counted")
            with self._guard:
                value = count_incomplete_prefix(SimpleNamespace(counter=self.counter, folder=self.folder), wire, pending)
            return {"prompt_tokens": value, "request_sha256": digest(json_bytes(wire)),
                    "method": "official_low_level_encoding_of_original_incomplete_SDK_event_prefix",
                    "count_only_not_dispatchable": True, "exact_provider_token_ids_available": False}
        if set(payload) != {"wire", "request_id", "slot_id", "condition", "usage_id", "prompt_upper_bound"}:
            raise ValueError("Unexpected generation broker extension")
        if self.slot_id is not None and (payload["slot_id"] != self.slot_id or payload["condition"] != self.condition_id):
            raise ValueError("A controller cannot cross its bound slot or condition")
        trusted = self.authorize(copy.deepcopy(payload))
        if (not isinstance(trusted, dict) or trusted.get("condition_id") != payload["condition"]
                or trusted.get("token_budget") not in BUDGETS):
            raise ValueError("The trusted host must bind a planned slot, condition and budget")
        if payload["usage_id"] not in {"agent", "condenser"}:
            raise ValueError("Unexpected model-use category")
        with self._guard:
            lock = self._slot_locks.setdefault(payload["slot_id"], threading.Lock())
        with lock:
            measured = self.counter(wire)
            if (measured["request_sha256"] != digest(json_bytes(wire))
                    or measured["prompt_tokens"] != payload["prompt_upper_bound"]):
                raise ValueError("Controller prompt reservation differs from the official host counter")
            with self.client.ledger._connect() as db:
                rows = list(db.execute("SELECT usage_id,status,usage_json FROM requests WHERE slot_id=?",
                                       (payload["slot_id"],)))
            if any(row["status"] != "settled" for row in rows):
                raise api.PreDispatchBudgetStopped("slot_has_unclosed_or_unknown_usage")
            actual = sum(json.loads(row["usage_json"])["total_tokens"] for row in rows)
            if (len(rows) >= 512 or sum(row["usage_id"] == "agent" for row in rows) >= 512
                    or actual+measured["prompt_tokens"]+wire["max_tokens"] > trusted["token_budget"]):
                raise api.PreDispatchBudgetStopped("host_episode_limit_before_dispatch")
            return self.client.complete(wire, **{key: value for key, value in payload.items() if key != "wire"})


@lru_cache(maxsize=1)
def native_type():
    from pydantic import PrivateAttr

    class BrokerNativeLLM(native_llm_type()):
        _normalization_folder: object = PrivateAttr(default=None)

        def _to_chat_dicts(self, messages):
            wire = super()._to_chat_dicts(messages)
            for original, serialized in zip(messages, wire, strict=True):
                if original.role == "assistant" and original.reasoning_content is not None:
                    if not isinstance(original.reasoning_content, str):
                        raise ValueError("Original assistant reasoning must remain text")
                    serialized["reasoning_content"] = original.reasoning_content
            return wire

        def get_token_count(self, messages, tools=None, **kwargs):
            self._adapter.assert_healthy()
            if not messages:
                return 0
            wire = self.format_messages_for_llm(messages)
            pending = pending_tail_tool_ids(wire)
            if not pending:
                return super().get_token_count(messages, tools, **kwargs)
            if set(kwargs)-{"add_security_risk_prediction", "on_token", "call_context"}:
                raise ValueError("Unfrozen native SDK count options")
            request = self._adapter.request(restore_prefix_reasoning(wire, self._adapter.history), [
                dict(tool.to_openai_tool(add_security_risk_prediction=bool(kwargs.get("add_security_risk_prediction"))))
                for tool in tools or []])
            return self._adapter.count_prefix(request, pending)["prompt_tokens"]

        def completion(self, messages, tools=None, **kwargs):
            from litellm.types.utils import ModelResponse
            from openhands.sdk.llm import Message
            from openhands.sdk.llm.llm_response import LLMResponse
            from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
            from .software_benchmark_exact_transport_v057 import normalize_response

            self._adapter.assert_healthy()
            request = self._request(messages, tools, kwargs)
            body = self._adapter.complete(request, self.usage_id)
            try:
                projection, receipt = normalize_response(body)
                raw, projected = ModelResponse(**body), ModelResponse(**projection)
                message = Message.from_llm_chat_message(projected.choices[0].message)
                if self._normalization_folder is not None:
                    receipt.update(usage_id=self.usage_id)
                    name = digest(json_bytes([self.usage_id, body.get("id"), receipt["wire_body_sha256"]]))
                    write_new(Path(self._normalization_folder)/(name+".json"), receipt)
                totals = self._adapter.ledger.snapshot()["per_usage_id"][self.usage_id]
                return LLMResponse(message=message, raw_response=raw,
                    metrics=MetricsSnapshot(model_name=api.MODEL,
                        accumulated_token_usage=TokenUsage(model=api.MODEL, **totals)))
            except Exception as error:
                self._adapter.record_failure(body, error, self.usage_id)
                raise

    return BrokerNativeLLM


def build_native_llm(adapter, *, normalization_folder=None):
    from .software_benchmark_exact_transport_v057 import ProjectionGuard, ResponseProjectionFault

    llm = native_type()(model="openai/"+api.MODEL, usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        native_tool_calling=True, force_string_serializer=True,
        max_input_tokens=adapter.maximum_input_tokens, max_output_tokens=adapter.maximum_output_tokens)
    if getattr(adapter, "_v057_projection_guard", None) is not None:
        raise ResponseProjectionFault("An adapter cannot obtain a second fresh projection guard")
    folder = None
    if normalization_folder is not None:
        folder = Path(normalization_folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        llm._normalization_folder = str(folder)
    guard = ProjectionGuard(adapter, folder)
    adapter._v057_projection_guard = guard
    llm._adapter = guard
    return llm
