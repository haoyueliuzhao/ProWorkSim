"""Predeclared Qwen REF budget gradient; the native inference recipe is unchanged."""
from __future__ import annotations

import copy
from pathlib import Path
import threading
import time

from .software_benchmark_exact_transport_v054 import (
    HTTPFailure, REF_MODEL, TEMPLATE_KEYS, RefExactAdapter, RefLedger, VllmExactCounter,
    exact_measure,
)
from .software_benchmark_match_v054 import AccountingFault, DispatchStopped, TOOL_NAMES, write_new
from .storage import atomic_write, digest, json_bytes

VERSION = "v056-qwen-ref-budget-gradient-r2-empty-tools"
BUDGETS = {"REF_B0500K": 500_000, "REF_B2000K": 2_000_000,
           "REF_B5000K": 5_000_000, "REF_B10000K": 10_000_000}
COMMON_LIMITS = {"all_model_attempts": 512, "agent_decisions": 512,
                 "soft_seconds": 21600, "hard_seconds": 23400}


def validate_condition(condition):
    name = condition.get("condition_id")
    limits = condition.get("episode_limits", {})
    if (condition.get("version") != "v056-ref-budget-condition-r1" or name not in BUDGETS
            or condition.get("arm") != "REF" or condition.get("single_agent") is not True
            or condition.get("training") is not False
            or limits.get("input_plus_output_tokens") != BUDGETS[name]
            or any(limits.get(key) != value for key, value in COMMON_LIMITS.items())):
        raise ValueError("Unknown predeclared REF budget condition")
    inference = condition["inference"]
    expected = {"total_context": 131072, "maximum_full_input": 98304,
                "output_limit": 32768, "temperature": .6, "top_p": .95, "top_k": 20,
                "max_tokens": 32768, "automatic_retries": 0,
                "chat_template_kwargs": {"enable_thinking": True}}
    if any(inference.get(key) != value for key, value in expected.items()):
        raise ValueError("Budget comparison cannot change the REF inference recipe")
    return limits


class BudgetLedger(RefLedger):
    def __init__(self, condition):
        limits = validate_condition(condition)
        super().__init__()
        self.token_limit = limits["input_plus_output_tokens"]
        self.attempt_limit = limits["all_model_attempts"]
        self.decision_limit = limits["agent_decisions"]


def canonical_request(request):
    """A tool-free condenser omits tools; an empty list is rejected by vLLM 0.32."""
    value = copy.deepcopy(request)
    if value.get("tools") == []:
        value.pop("tools")
        if value.get("tool_choice") == "none":
            value.pop("tool_choice")
    return value


class OptionalToolsCounter(VllmExactCounter):
    def measure(self, request):
        request = canonical_request(request)
        payload = {key: copy.deepcopy(request[key]) for key in TEMPLATE_KEYS if key in request}
        key = digest(json_bytes(payload))
        if key not in self.cache:
            self.requests += 1
            result = self.transport.post("/tokenize", payload)
            proof = write_new(self.folder / f"tokenize-{self.requests:04d}.json", {
                "request": payload, "response": result, "generation_attempt": False,
                "wire_revision": VERSION,
            })
            ids, count = result.get("tokens"), result.get("count")
            if (not isinstance(ids, list) or type(count) is not int or count != len(ids)
                    or result.get("max_model_len") != 131072):
                raise ValueError("Official exact token count or context differs")
            self.cache[key] = (copy.deepcopy(ids), proof)
        ids, proof = self.cache[key]
        return exact_measure(request, copy.deepcopy(ids), context_limit=131072,
                             backend="fixed_vllm_service_/tokenize", proof=proof)


class BudgetRefAdapter(RefExactAdapter):
    """Own admission and deadlines, reusing exact counting and settlement semantics."""

    def __init__(self, *, transport, folder, slot_id, seed, service_identity, condition):
        self.limits = validate_condition(condition)
        expected = {
            "model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
            "vllm_version": "0.32.0", "raw_release": True, "adapter_sha256": None,
            "model_manifest_sha256": "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6",
            "context_limit": 131072, "max_output_tokens": 32768,
            "service_admission_complete": True,
        }
        if (any(service_identity.get(k) != v for k, v in expected.items())
                or service_identity.get("port") != transport.port
                or not 18056 <= transport.port <= 18063
                or type(seed) is not int or not 0 <= seed < 2**63):
            raise ValueError("REF requires the admitted raw-Qwen v056 service and planned seed")
        self.transport, self.folder = transport, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.counter = OptionalToolsCounter(transport, self.folder)
        self.ledger = BudgetLedger(condition)
        self.slot_id, self.seed = slot_id, seed
        self.service_identity = copy.deepcopy(service_identity)
        self.condition = copy.deepcopy(condition)
        self.authorized, self.fixture = True, False
        self.halted, self.started = None, time.monotonic()
        self.lock = threading.Lock()
        self.request_defaults = {
            "model": REF_MODEL, "max_tokens": 32768, "temperature": .6,
            "top_p": .95, "top_k": 20, "min_p": 0., "presence_penalty": 0.,
            "repetition_penalty": 1., "stream": False, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": True},
            "add_generation_prompt": True, "continue_final_message": False,
            "add_special_tokens": False,
        }
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "version": VERSION, "arm": "REF", "condition_id": self.condition["condition_id"],
            "slot_id": self.slot_id, "service_identity": self.service_identity,
            "formal_execution_authorized": True, "programmed_http_fixture": False,
            "halted": self.halted, "tokenize_http_requests": self.counter.requests,
            **self.ledger.snapshot(),
        }))

    def count(self, request):
        return super().count(canonical_request(request))

    def complete(self, request, usage_id):
        request = canonical_request(request)
        with self.lock:
            if self.halted:
                raise DispatchStopped("episode_already_stopped:" + self.halted)
            if any(request.get(k) != v for k, v in self.request_defaults.items()):
                raise ValueError("Request differs from the frozen REF inference recipe")
            names = {tool["function"]["name"] for tool in request.get("tools", [])}
            if ((usage_id == "agent" and names != TOOL_NAMES)
                    or (usage_id == "condenser" and names)):
                raise ValueError("REF retains native tools and its tool-free condenser")
            try:
                if time.monotonic() - self.started >= self.limits["soft_seconds"]:
                    raise DispatchStopped("soft_deadline_before_generation")
                measure = self.count(request)
                if time.monotonic() - self.started >= self.limits["soft_seconds"]:
                    raise DispatchStopped("soft_deadline_after_exact_count_before_generation")
                index = self.ledger.attempts + 1
                ref = write_new(self.folder / f"request-{index:04d}.json", {
                    "request": request, "exact_input": measure, "usage_id": usage_id,
                    "slot_id": self.slot_id, "service_identity": self.service_identity,
                })
                self.ledger.reserve(measure, usage_id, ref)
                self.save()
                response = self.transport.post("/v1/chat/completions", request)
                response_ref = write_new(self.folder / f"response-{index:04d}.json", response)
                self.ledger.settle(response, response_ref)
                self.save()
                if time.monotonic() - self.started >= self.limits["hard_seconds"]:
                    raise DispatchStopped("hard_deadline_after_generation")
                return response
            except BaseException as error:
                self.halted = f"{type(error).__name__}:{error}"
                if isinstance(error, HTTPFailure):
                    write_new(self.folder / f"http-fault-{self.ledger.attempts:04d}.json", error.evidence)
                self.save()
                if isinstance(error, DispatchStopped):
                    raise
                raise AccountingFault(self.halted) from error
