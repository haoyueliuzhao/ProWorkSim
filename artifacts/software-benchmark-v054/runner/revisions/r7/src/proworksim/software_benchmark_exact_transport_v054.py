"""Shared exact input counting and the bounded local vLLM REF transport.

REF obtains input IDs from the pinned service's /tokenize endpoint. MATCH uses
the input IDs prepared by its original project owner. Neither path estimates
tokens with LiteLLM. This module never starts a model service or loads weights.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import http.client
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from .software_benchmark_match_v054 import (
    AccountingFault, DispatchStopped, TOOL_NAMES, write_new,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "software-benchmark-v054-exact-native-transport-v1"
REF_MODEL = "raw-qwen3.5-9b-v054-ref"
TEMPLATE_KEYS = ("model", "messages", "tools", "chat_template_kwargs",
                 "add_generation_prompt", "continue_final_message", "add_special_tokens")


class HTTPFailure(RuntimeError):
    def __init__(self, reason, *, status=None, raw_body=None):
        super().__init__(reason)
        self.evidence = {
            "reason": reason, "http_status": status, "raw_response_body": raw_body,
            "complete_response_available": raw_body is not None,
        }


class LoopbackHTTP:
    """Direct loopback HTTP only; one request, no proxy, redirect or retry."""

    def __init__(self, base_url, *, timeout_seconds=1800, max_response_bytes=16 * 1024 * 1024):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/", "/v1", "/v1/"} or not parsed.port):
            raise ValueError("Only an explicit http://127.0.0.1:<port> vLLM service is accepted")
        self.base_url = f"http://127.0.0.1:{parsed.port}"
        self.port = parsed.port
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def post(self, path, payload):
        if path not in {"/tokenize", "/v1/chat/completions"}:
            raise ValueError("Unapproved local service operation")
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=self.timeout_seconds)
        status, raw = None, None
        try:
            connection.request("POST", path, body=json_bytes(payload),
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            status = response.status
            body = response.read(self.max_response_bytes + 1)
            if len(body) > self.max_response_bytes:
                raise HTTPFailure("Response exceeds the declared bound", status=status)
            raw = body.decode("utf-8")
            if status != 200:
                raise HTTPFailure("Non-200 response; no redirect or retry",
                                  status=status, raw_body=raw)
            decoded = json.loads(raw)
            if not isinstance(decoded, dict):
                raise ValueError("The response is not a JSON object")
            return decoded
        except HTTPFailure:
            raise
        except Exception as error:
            raise HTTPFailure(f"{type(error).__name__}: {error}",
                              status=status, raw_body=raw) from error
        finally:
            connection.close()


def exact_measure(request, token_ids, *, context_limit, backend, proof=None):
    if (not isinstance(token_ids, list) or not token_ids
            or any(type(token) is not int or token < 0 for token in token_ids)):
        raise ValueError("Exact counting requires the backend's complete input IDs")
    value = {
        "version": VERSION, "generation_request_sha256": digest(json_bytes(request)),
        "input_ids": token_ids, "input_ids_sha256": digest(json_bytes(token_ids)),
        "prompt_tokens": len(token_ids), "context_limit": context_limit,
        "backend": backend, "proof": proof,
    }
    value["sha256"] = digest(json_bytes(value))
    return value


class VllmExactCounter:
    def __init__(self, transport, folder):
        self.transport, self.folder = transport, Path(folder)
        self.cache = {}
        self.requests = 0

    def measure(self, request):
        payload = {key: copy.deepcopy(request[key]) for key in TEMPLATE_KEYS}
        key = digest(json_bytes(payload))
        if key not in self.cache:
            self.requests += 1
            result = self.transport.post("/tokenize", payload)
            proof = write_new(self.folder / f"tokenize-{self.requests:04d}.json", {
                "request": payload, "response": result, "generation_attempt": False,
            })
            ids, count = result.get("tokens"), result.get("count")
            if (not isinstance(ids, list) or type(count) is not int or count != len(ids)
                    or result.get("max_model_len") != 131072):
                raise ValueError("Official token count, IDs or fixed context limit disagree")
            self.cache[key] = (copy.deepcopy(ids), proof)
        ids, proof = self.cache[key]
        return exact_measure(
            request, copy.deepcopy(ids), context_limit=131072,
            backend="fixed_vllm_service_/tokenize", proof=proof)


class ProjectExactCounter:
    def __init__(self, bridge):
        self.bridge = bridge

    def measure(self, request):
        native = self.bridge.prepare(request)
        return exact_measure(
            request, native["input_ids"], context_limit=18432,
            backend="unchanged_project_owner_native_input_ids",
            proof={"native_input_sha256": native["sha256"],
                   "renderer_version": native["renderer_version"]})


def export_request(llm, adapter, messages, tools, *, add_security_risk_prediction=False):
    """Both arms call precisely this SDK serialization and schema export."""
    request = {
        **copy.deepcopy(adapter.request_defaults),
        "messages": llm.format_messages_for_llm(messages),
        "tools": [dict(tool.to_openai_tool(
            add_security_risk_prediction=add_security_risk_prediction))
            for tool in (tools or [])],
    }
    request["tool_choice"] = "auto" if request["tools"] else "none"
    return request


class MatchExactAdapter:
    """Wrap the frozen MATCH bridge; its numerical path and ledger are retained."""

    maximum_input_tokens, maximum_output_tokens, temperature = 16384, 2048, 0.7
    request_defaults = {
        "model": "raw-qwen3.5-9b-v054-match", "temperature": 0.7,
        "max_tokens": 2048, "stream": False,
        "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
        "add_generation_prompt": True, "continue_final_message": False,
        "add_special_tokens": False,
    }

    def __init__(self, bridge):
        self.bridge, self.ledger = bridge, bridge.ledger
        self.counter = ProjectExactCounter(bridge)

    def count(self, request):
        return self.counter.measure(request)

    def complete(self, request, usage_id):
        return self.bridge.complete_request(request, usage_id=usage_id)


class RefLedger:
    """The same episode limits, with REF's fixed 32,768-token reservation."""

    def __init__(self):
        self.attempts = self.decisions = self.actual = 0
        self.calls, self.inflight = [], None
        self.token_limit, self.attempt_limit, self.decision_limit = 500000, 128, 128

    def reserve(self, measure, usage_id, request_ref):
        if self.inflight:
            raise AccountingFault("Unresolved REF attempt cannot be replayed")
        if usage_id not in {"agent", "condenser"}:
            raise ValueError("Only agent and its own condenser are admitted")
        if self.attempts >= self.attempt_limit:
            raise DispatchStopped("all_model_attempt_limit")
        if usage_id == "agent":
            if self.decisions >= self.decision_limit:
                raise DispatchStopped("agent_decision_limit")
            self.decisions += 1
        reservation = measure["prompt_tokens"] + 32768
        if reservation > 131072:
            raise DispatchStopped("full_context_preexecution_rejection")
        if reservation > self.token_limit - self.actual:
            raise DispatchStopped("full_input_and_output_reservation_insufficient")
        self.attempts += 1
        self.inflight = {
            "attempt": self.attempts, "usage_id": usage_id, "reservation": reservation,
            "prompt_tokens": measure["prompt_tokens"], "measure_sha256": measure["sha256"],
            "request": request_ref,
        }

    def settle(self, body, response_ref):
        usage, choices = body.get("usage", {}), body.get("choices")
        if (self.inflight is None or body.get("model") != REF_MODEL
                or not isinstance(body.get("id"), str) or not body["id"]
                or any(call["native_attempt_id"] == body["id"] for call in self.calls)
                or not isinstance(choices, list) or len(choices) != 1
                or choices[0].get("index") != 0
                or not isinstance(choices[0].get("message"), dict)
                or choices[0]["message"].get("role") != "assistant"
                or choices[0].get("finish_reason") not in {"stop", "length", "tool_calls"}
                or any(type(usage.get(key)) is not int for key in
                       ("prompt_tokens", "completion_tokens", "total_tokens"))
                or usage["prompt_tokens"] != self.inflight["prompt_tokens"]
                or not 0 < usage["completion_tokens"] <= 32768
                or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
                or usage["total_tokens"] > self.inflight["reservation"]):
            raise AccountingFault("REF identity, full response and exact usage disagree")
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if reasoning is not None and (
                type(reasoning) is not int or not 0 <= reasoning <= usage["completion_tokens"]):
            raise AccountingFault("REF reasoning usage is not included in completion tokens")
        self.actual += usage["total_tokens"]
        self.calls.append({
            **self.inflight, "usage": copy.deepcopy(usage), "response": response_ref,
            "native_attempt_id": body["id"], "finish_reason": choices[0]["finish_reason"],
        })
        self.inflight = None

    def snapshot(self):
        per_usage = {}
        for call in self.calls:
            value = per_usage.setdefault(call["usage_id"], {"prompt_tokens": 0, "completion_tokens": 0})
            for key in value:
                value[key] += call["usage"][key]
        return {
            "attempts": self.attempts, "decisions": self.decisions, "calls": self.calls,
            "known_actual_tokens": self.actual,
            "complete_actual_tokens": self.actual if self.inflight is None else None,
            "uncertain_reserved_tokens": self.inflight["reservation"] if self.inflight else 0,
            "inflight": self.inflight, "per_usage_id": per_usage,
            "token_limit": self.token_limit, "all_model_attempt_limit": self.attempt_limit,
            "agent_decision_limit": self.decision_limit, "local_dollar_cost_estimate": None,
            "automatic_retry": False,
        }


class RefExactAdapter:
    maximum_input_tokens, maximum_output_tokens, temperature = 98304, 32768, 0.6

    def __init__(self, *, transport, folder, slot_id, seed,
                 service_identity, execution_authorized=False, programmed_http_fixture=False):
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("Use the predeclared per-task seed")
        if programmed_http_fixture and (
                transport.port == 18054 or service_identity.get("programmed_fixture") is not True):
            raise ValueError("A synthetic fixture cannot target the configured model endpoint")
        if execution_authorized and (
                programmed_http_fixture or transport.port != 18054
                or service_identity.get("model_revision")
                != "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
                or service_identity.get("vllm_version") != "0.32.0"
                or service_identity.get("raw_release") is not True
                or service_identity.get("adapter_sha256") is not None
                or service_identity.get("model_manifest_sha256")
                != "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6"
                or service_identity.get("context_limit") != 131072
                or service_identity.get("max_output_tokens") != 32768
                or service_identity.get("service_admission_complete") is not True):
            raise ValueError("Formal REF requires the separately admitted fixed local service")
        self.transport = transport
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.counter = VllmExactCounter(transport, self.folder)
        self.ledger = RefLedger()
        self.slot_id, self.service_identity = slot_id, copy.deepcopy(service_identity)
        self.authorized, self.fixture = execution_authorized, programmed_http_fixture
        self.halted, self.started = None, time.monotonic()
        self.lock = threading.Lock()
        self.request_defaults = {
            "model": REF_MODEL, "max_tokens": 32768, "temperature": 0.6,
            "top_p": 0.95, "top_k": 20, "min_p": 0.0,
            "presence_penalty": 0.0, "repetition_penalty": 1.0,
            "stream": False, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": True},
            "add_generation_prompt": True, "continue_final_message": False,
            "add_special_tokens": False,
        }
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "version": VERSION, "arm": "REF", "slot_id": self.slot_id,
            "service_identity": self.service_identity, "formal_execution_authorized": self.authorized,
            "programmed_http_fixture": self.fixture, "halted": self.halted,
            "tokenize_http_requests": self.counter.requests, **self.ledger.snapshot(),
        }))

    def count(self, request):
        if self.halted:
            raise DispatchStopped("episode_already_stopped:" + self.halted)
        try:
            result = self.counter.measure(request)
            self.save()
            return result
        except BaseException as error:
            if isinstance(error, HTTPFailure):
                write_new(self.folder / f"tokenize-fault-{self.counter.requests:04d}.json", {
                    "request": request, "generation_attempt": False, **error.evidence,
                })
            self.halted = f"exact_count_failure:{type(error).__name__}:{error}"
            self.save()
            raise AccountingFault(self.halted) from error

    def complete(self, request, usage_id):
        with self.lock:
            if self.halted:
                raise DispatchStopped("episode_already_stopped:" + self.halted)
            if not self.authorized and not self.fixture:
                raise DispatchStopped("formal_model_execution_not_authorized")
            if any(request.get(key) != value for key, value in self.request_defaults.items()):
                raise ValueError("Request differs from the fixed REF inference configuration")
            names = {tool["function"]["name"] for tool in request.get("tools", [])}
            if ((usage_id == "agent" and names != TOOL_NAMES)
                    or (usage_id == "condenser" and names)):
                raise ValueError("REF retains five native tools and a tool-free condenser")
            try:
                if time.monotonic() - self.started >= 5400:
                    raise DispatchStopped("soft_deadline_before_generation")
                measure = self.count(request)
                if time.monotonic() - self.started >= 5400:
                    raise DispatchStopped("soft_deadline_after_exact_count_before_generation")
                index = self.ledger.attempts + 1
                request_ref = write_new(self.folder / f"request-{index:04d}.json", {
                    "request": request, "exact_input": measure, "usage_id": usage_id,
                    "slot_id": self.slot_id, "service_identity": self.service_identity,
                })
                self.ledger.reserve(measure, usage_id, request_ref)
                self.save()
                body = self.transport.post("/v1/chat/completions", request)
                response_ref = write_new(self.folder / f"response-{index:04d}.json", body)
                self.ledger.settle(body, response_ref)
                self.save()
                if time.monotonic() - self.started >= 6000:
                    raise DispatchStopped("hard_deadline_after_generation")
                return body
            except BaseException as error:
                self.halted = f"{type(error).__name__}:{error}"
                if isinstance(error, HTTPFailure):
                    write_new(self.folder / f"http-fault-{self.ledger.attempts:04d}.json",
                              error.evidence)
                self.save()
                if isinstance(error, DispatchStopped):
                    raise
                raise AccountingFault(self.halted) from error


@lru_cache(maxsize=1)
def shared_llm_type():
    from openhands.sdk import LLM
    from pydantic import PrivateAttr

    class ExactCountingNativeLLM(LLM):
        _adapter: object = PrivateAttr(default=None)

        def resolve_runtime_metadata(self):
            return None

        def _request(self, messages, tools, kwargs):
            unexpected = set(kwargs) - {"add_security_risk_prediction", "on_token", "call_context"}
            if unexpected:
                raise ValueError("Unfrozen SDK request kwargs: " + ",".join(sorted(unexpected)))
            return export_request(
                self, self._adapter, messages, tools,
                add_security_risk_prediction=bool(kwargs.get("add_security_risk_prediction")))

        def get_token_count(self, messages, tools=None, **kwargs):
            if not messages:
                return 0
            request = self._request(messages, tools, kwargs)
            return self._adapter.count(request)["prompt_tokens"]

        def completion(self, messages, tools=None, **kwargs):
            from litellm.types.utils import ModelResponse
            from openhands.sdk.llm import Message
            from openhands.sdk.llm.llm_response import LLMResponse
            from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
            request = self._request(messages, tools, kwargs)
            body = self._adapter.complete(request, self.usage_id)
            raw = ModelResponse(**body)
            totals = self._adapter.ledger.snapshot()["per_usage_id"][self.usage_id]
            return LLMResponse(
                message=Message.from_llm_chat_message(raw.choices[0].message), raw_response=raw,
                metrics=MetricsSnapshot(model_name=request["model"],
                                        accumulated_token_usage=TokenUsage(
                                            model=request["model"], **totals)))

        async def acompletion(self, messages, tools=None, **kwargs):
            return self.completion(messages, tools, **kwargs)

    return ExactCountingNativeLLM


def build_llm(adapter):
    llm = shared_llm_type()(
        model="openai/Qwen3.5-9B", usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        max_input_tokens=adapter.maximum_input_tokens,
        max_output_tokens=adapter.maximum_output_tokens, temperature=adapter.temperature,
    )
    llm._adapter = adapter
    return llm
