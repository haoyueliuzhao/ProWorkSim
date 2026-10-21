"""DeepSeek model transport for the original native and managed interfaces.

Only the provider seam changes here. Tool execution remains in the isolated
native worker or in the actual managed World. No web/search/browser tool is
introduced. Remote token counts are provider usage, never invented token IDs.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path
import threading
import time

from .software_benchmark_candidates_v054 import write_new
from .storage import atomic_write, digest, json_bytes

VERSION = "v055-deepseek-interface-r1"
MODEL = "deepseek-flash"
NATIVE_TOOLS = frozenset({"terminal", "file_editor", "task_tracker", "finish", "think"})
LIMITS = {
    "REF": {"context_limit": 131072, "max_output_tokens": 32768},
    "MATCH": {"context_limit": 18432, "max_output_tokens": 2048},
    "PROJECT": {"context_limit": 18432, "max_output_tokens": 2048},
}
COUNT_METHOD = "UTF8_request_bytes_plus_1024_plus_64_per_message_and_tool_estimate_not_tokenizer_proof"


class RemoteEpisodeBoundary(BaseException):
    """Known pre-dispatch exhaustion, with no retry of a consumed generation."""


def prompt_reservation(request):
    """Deliberately conservative engineering estimate; actual API usage wins."""
    return len(json_bytes(request)) + 1024 + 64 * (
        len(request.get("messages", [])) + len(request.get("tools", [])))


def _canonical_call(call):
    function = call["function"]
    return (call["id"], call.get("type", "function"), function["name"],
            json.loads(function["arguments"]))


class ReasoningHistory:
    """Restore only returned assistant messages whose exact tool IDs match.

    SDKs may drop reasoning_content or normalize argument whitespace. Neither
    authorizes reconstructing reasoning. We retain the original API response
    and verify the action's parsed arguments before restoring its message.
    """
    def __init__(self):
        self.messages = {}

    def remember(self, message):
        calls = message.get("tool_calls") or []
        if calls:
            key = tuple(call["id"] for call in calls)
            if key in self.messages and self.messages[key] != message:
                raise ValueError("Provider tool-call IDs cannot identify two assistant responses")
            self.messages[key] = copy.deepcopy(message)

    def restore(self, messages, *, thinking):
        selected = copy.deepcopy(messages)
        for index, message in enumerate(selected):
            calls = message.get("tool_calls") or []
            if message.get("role") != "assistant" or not calls:
                continue
            key = tuple(call["id"] for call in calls)
            original = self.messages.get(key)
            if original is None:
                if thinking and not isinstance(message.get("reasoning_content"), str):
                    raise ValueError("Thinking tool continuation has no original reasoning provenance")
                continue
            if ([_canonical_call(call) for call in calls]
                    != [_canonical_call(call) for call in original["tool_calls"]]):
                raise ValueError("SDK changed the arguments of an original provider tool call")
            selected[index] = copy.deepcopy(original)
            if thinking and not isinstance(selected[index].get("reasoning_content"), str):
                raise ValueError("Thinking provider omitted reasoning_content for its tool call")
        return selected


class RemoteEpisodeLedger:
    def __init__(self):
        self.calls = []
        self.inflight = None
        self.decisions = 0
        self.attempts = 0
        self.actual = 0

    def snapshot(self):
        totals = {}
        for call in self.calls:
            subtotal = totals.setdefault(call["usage_id"], {
                "prompt_tokens": 0, "completion_tokens": 0})
            for key in subtotal:
                subtotal[key] += call["usage"][key]
        return {
            "version": VERSION, "attempts": self.attempts, "decisions": self.decisions,
            "known_actual_tokens": self.actual,
            "complete_actual_tokens": self.actual if self.inflight is None else None,
            "uncertain_reserved_tokens": self.inflight["reservation"] if self.inflight else 0,
            "inflight": copy.deepcopy(self.inflight), "calls": copy.deepcopy(self.calls),
            "per_usage_id": totals, "token_limit": 500000,
            "all_model_attempt_limit": 128, "agent_decision_limit": 128,
            "reasoning_tokens_included_in_completion_tokens": True,
            "seed_supported_by_provider": False, "automatic_retry": False,
        }


class DeepSeekAdapter:
    """One immutable arm/mode, shared by native Agent and condenser copies."""
    def __init__(self, *, client, arm, thinking, slot_id, condition_id, folder,
                 allowed_tool_names, soft_at=None, hard_at=None, counter=None):
        if arm not in LIMITS or type(thinking) is not bool:
            raise ValueError("Use one of the three frozen interfaces and an explicit thinking mode")
        self.client, self.arm, self.thinking = client, arm, thinking
        self.slot_id, self.condition_id = slot_id, condition_id
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.allowed_tool_names = frozenset(allowed_tool_names)
        self.limits = copy.deepcopy(LIMITS[arm])
        self.maximum_output_tokens = self.limits["max_output_tokens"]
        self.maximum_input_tokens = self.limits["context_limit"] - self.maximum_output_tokens
        self.soft_at, self.hard_at = soft_at, hard_at
        self.counter = counter
        self.ledger, self.history, self.lock = RemoteEpisodeLedger(), ReasoningHistory(), threading.Lock()
        self.halted = None
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "slot_id": self.slot_id, "condition_id": self.condition_id,
            "arm": self.arm, "thinking": self.thinking, "model": MODEL,
            "limits": self.limits, "count_method": (COUNT_METHOD if self.counter is None
                                                     else "bound_counter_provenance_in_request_measurement"),
            "sampling_parameters": ("thinking_high_temperature_omitted" if self.thinking
                                    else "REF_temperature_0.6_MATCH_PROJECT_0.7_top_p_omitted"),
            "halted": self.halted, **self.ledger.snapshot()}))

    def request(self, messages, tools):
        from .software_benchmark_deepseek_api_v055 import slot_user_id
        tools = copy.deepcopy(tools or [])
        names = set()
        for tool in tools:
            if tool.get("type") != "function" or not isinstance(tool.get("function"), dict):
                raise ValueError("Only the already declared local function tools are allowed")
            name = tool["function"]["name"]
            if name not in self.allowed_tool_names or name in names:
                raise ValueError("Unknown or duplicate function; no remote search tool is allowed")
            names.add(name)
        value = {"model": MODEL, "messages": self.history.restore(messages, thinking=self.thinking),
                 "max_tokens": self.maximum_output_tokens, "stream": False,
                 "user_id": slot_user_id(self.slot_id, self.condition_id),
                 "thinking": {"type": "enabled" if self.thinking else "disabled"}}
        if self.thinking:
            value["reasoning_effort"] = "high"
        else:
            value["temperature"] = 0.6 if self.arm == "REF" else 0.7
        if tools:
            value.update(tools=tools, tool_choice="auto")
        return value

    def count(self, request):
        if self.counter is not None:
            result = copy.deepcopy(self.counter(request))
            if (type(result.get("prompt_tokens")) is not int or result["prompt_tokens"] <= 0
                    or not isinstance(result.get("method"), str)
                    or result.get("request_sha256") != digest(json_bytes(request))):
                raise ValueError("Remote counter must bind its method and exact request")
            return result
        count = prompt_reservation(request)
        return {"prompt_tokens": count, "count_kind": "conservative_estimate",
                "method": COUNT_METHOD, "exact_provider_token_ids_available": False,
                "request_sha256": digest(json_bytes(request))}

    def complete(self, request, usage_id="agent"):
        from .software_benchmark_deepseek_api_v055 import BudgetStopped, ConcurrencyBusy
        if usage_id not in {"agent", "condenser"}:
            raise ValueError("Only this single Agent and its original condenser may generate")
        with self.lock:
            if self.halted or self.ledger.inflight:
                raise RemoteEpisodeBoundary("episode_closed_or_uncertain_usage")
            if self.soft_at is not None and time.monotonic() >= self.soft_at:
                raise RemoteEpisodeBoundary("soft_deadline_before_dispatch")
            if request != self.request(request["messages"], request.get("tools")):
                raise ValueError("Request differs from the frozen remote provider configuration")
            if (usage_id == "condenser" and request.get("tools")):
                raise ValueError("Original native condenser cannot acquire tools")
            if self.arm != "PROJECT" and usage_id == "agent":
                if {t["function"]["name"] for t in request.get("tools", [])} != NATIVE_TOOLS:
                    raise ValueError("Native REF/MATCH must retain their exact five tools")
            measure = self.count(request)
            reservation = measure["prompt_tokens"] + self.maximum_output_tokens
            if reservation > self.limits["context_limit"]:
                raise RemoteEpisodeBoundary("conservative_context_reservation_exhausted")
            if self.ledger.attempts >= 128 or (usage_id == "agent" and self.ledger.decisions >= 128):
                raise RemoteEpisodeBoundary("episode_call_limit")
            if self.ledger.actual + reservation > 500000:
                raise RemoteEpisodeBoundary("episode_token_reservation_exhausted")
            index = self.ledger.attempts + 1
            request_ref = write_new(self.folder / f"request-{index:04d}.json", {
                "request": request, "measurement": measure, "usage_id": usage_id})
            inflight = {"attempt": index, "usage_id": usage_id, "reservation": reservation,
                        "request": request_ref, "request_id": self.slot_id + f":{index:04d}"}
            self.ledger.inflight = inflight
            self.ledger.attempts += 1
            self.ledger.decisions += usage_id == "agent"
            self.save()

            def stop_unstarted(reason):
                self.ledger.inflight = None
                self.ledger.attempts -= 1
                self.ledger.decisions -= usage_id == "agent"
                self.halted = reason
                self.save()
                raise RemoteEpisodeBoundary(reason)

            try:
                while True:
                    if self.soft_at is not None and time.monotonic() >= self.soft_at:
                        stop_unstarted("soft_deadline_during_provider_admission_wait")
                    try:
                        body = self.client.complete(request, request_id=inflight["request_id"],
                            slot_id=self.slot_id, condition=self.condition_id, usage_id=usage_id,
                            prompt_upper_bound=measure["prompt_tokens"])
                        break
                    except (ConcurrencyBusy, BudgetStopped) as error:
                        snapshot = self.client.ledger.snapshot()
                        # A cooldown may be active with zero in-flight calls.
                        # ConcurrencyBusy proves reserve() did not create this
                        # request; another admission check is not an HTTP retry.
                        if not snapshot["halted"] and (
                                isinstance(error, ConcurrencyBusy) or snapshot["inflight_count"]):
                            cooldown = max(0.0, float(snapshot.get("admission_wait_seconds", 0)))
                            delay = min(5.0, cooldown) if cooldown else 0.5
                            if self.soft_at is not None:
                                delay = min(delay, max(0.0, self.soft_at - time.monotonic()))
                            if delay:
                                time.sleep(delay)
                            continue
                        raise BudgetStopped(str(error)) from None
            except BudgetStopped:
                stop_unstarted("global_cny_budget_pre_dispatch_stop")
            except RemoteEpisodeBoundary:
                raise
            except BaseException as error:
                self.halted = f"{type(error).__name__}:{error}"
                self.save()
                raise
            response_ref = write_new(self.folder / f"response-{index:04d}.json", body)
            usage = body.get("usage", {})
            if (any(type(usage.get(k)) is not int or usage[k] < 0 for k in
                    ("prompt_tokens", "completion_tokens", "total_tokens"))
                    or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
                self.halted = "provider_usage_invalid"
                self.save()
                raise ValueError(self.halted)
            self.ledger.calls.append({**inflight, "usage": copy.deepcopy(usage),
                                      "response": response_ref, "response_id": body.get("id")})
            self.ledger.actual += usage["total_tokens"]
            self.ledger.inflight = None
            self.history.remember(body["choices"][0]["message"])
            if (usage["prompt_tokens"] > measure["prompt_tokens"]
                    or usage["completion_tokens"] > self.maximum_output_tokens):
                self.halted = "actual_usage_exceeded_engineering_reservation"
                self.save()
                raise ValueError(self.halted)
            self.save()
            return body


@lru_cache(maxsize=1)
def native_llm_type():
    from openhands.sdk import LLM
    from pydantic import PrivateAttr

    class DeepSeekNativeLLM(LLM):
        _adapter: object = PrivateAttr(default=None)

        def resolve_runtime_metadata(self):
            return None

        def _request(self, messages, tools, kwargs):
            unexpected = set(kwargs) - {"add_security_risk_prediction", "on_token", "call_context"}
            if unexpected:
                raise ValueError("Unfrozen SDK options: " + ",".join(sorted(unexpected)))
            return self._adapter.request(self.format_messages_for_llm(messages), [
                dict(tool.to_openai_tool(add_security_risk_prediction=bool(
                    kwargs.get("add_security_risk_prediction")))) for tool in tools or []])

        def get_token_count(self, messages, tools=None, **kwargs):
            return self._adapter.count(self._request(messages, tools, kwargs))["prompt_tokens"] if messages else 0

        def completion(self, messages, tools=None, **kwargs):
            from litellm.types.utils import ModelResponse
            from openhands.sdk.llm import Message
            from openhands.sdk.llm.llm_response import LLMResponse
            from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
            request = self._request(messages, tools, kwargs)
            body = self._adapter.complete(request, self.usage_id)
            raw = ModelResponse(**body)
            usage = self._adapter.ledger.snapshot()["per_usage_id"][self.usage_id]
            return LLMResponse(message=Message.from_llm_chat_message(raw.choices[0].message),
                raw_response=raw, metrics=MetricsSnapshot(model_name=MODEL,
                    accumulated_token_usage=TokenUsage(model=MODEL, **usage)))

        async def acompletion(self, messages, tools=None, **kwargs):
            return self.completion(messages, tools, **kwargs)

    return DeepSeekNativeLLM


def build_native_llm(adapter):
    llm = native_llm_type()(model="openai/" + MODEL, usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        native_tool_calling=True, force_string_serializer=True,
        max_input_tokens=adapter.maximum_input_tokens,
        max_output_tokens=adapter.maximum_output_tokens)
    llm._adapter = adapter
    return llm


def unwrap_boundary(error):
    if isinstance(error, RemoteEpisodeBoundary):
        return error
    for child in getattr(error, "exceptions", []):
        found = unwrap_boundary(child)
        if found is not None:
            return found
    cause = getattr(error, "__cause__", None)
    return unwrap_boundary(cause) if cause is not None and cause is not error else None
