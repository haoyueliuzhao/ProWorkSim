"""One fixed local-Qwen accounting contract for REF and managed PROJECT."""
from __future__ import annotations

import copy
from pathlib import Path
import threading
import time

from .software_benchmark_exact_transport_v054 import REF_MODEL, RefExactAdapter, RefLedger, HTTPFailure
from .software_benchmark_ref_budget_v056 import OptionalToolsCounter, canonical_request
from .software_benchmark_match_v054 import AccountingFault, DispatchStopped
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_full_plan_v064 import group_profiles, COMMON_LIMITS
from .storage import atomic_write, json_bytes

VERSION = "v064-qwen-paired-budget-r1"
PORTS = tuple(range(18210, 18216))


class BeforeQwenDispatch(DispatchStopped):
    before_dispatch_proven = True


def validate_condition(condition):
    group = group_profiles().get(condition.get("condition_id"))
    if (group is None or condition.get("version") != "v064-full-comparison-condition-r1"
            or condition.get("arm") != group["arm"] or condition.get("model_key") != group["model_key"]
            or condition.get("single_agent") is not True or condition.get("training") is not False
            or condition.get("thinking") is not True):
        raise ValueError("Unknown fixed twelve-group condition")
    limits = condition.get("episode_limits", {})
    if (limits.get("input_plus_output_tokens") != group["input_plus_output_tokens"]
            or any(limits.get(key) != value for key, value in COMMON_LIMITS.items())):
        raise ValueError("An independent numerical budget or execution limit changed")
    inference = condition["inference"]
    common = {"total_context": 131072, "maximum_full_input": 98304,
              "output_limit": 32768, "max_tokens": 32768, "automatic_retries": 0}
    if any(inference.get(key) != value for key, value in common.items()):
        raise ValueError("REF and PROJECT must have the same real numerical limits")
    if group['model_key'] == 'QWEN':
        expected = {'temperature': .6, 'top_p': .95, 'top_k': 20, 'min_p': 0.,
                    'presence_penalty': 0., 'repetition_penalty': 1.,
                    'chat_template_kwargs': {'enable_thinking': True}}
        if any(inference.get(key) != value for key, value in expected.items()):
            raise ValueError('Local Qwen sampling or thinking differs between interfaces')
    return {**limits, "context_limit": 131072}


class BudgetLedger(RefLedger):
    def __init__(self, condition):
        super().__init__()
        limits = validate_condition(condition)
        self.token_limit = limits["input_plus_output_tokens"]
        self.attempt_limit = limits["all_model_attempts"]
        self.decision_limit = limits["agent_decisions"]


class PairedQwenAdapter(RefExactAdapter):
    """Exact vLLM counts and full usage; tool identity is fixed per interface."""
    model = REF_MODEL
    thinking = True

    def __init__(self, *, transport, folder, slot_id, seed, service_identity, condition, allowed_tools):
        self.limits = validate_condition(condition)
        if condition["model_key"] != "QWEN":
            raise ValueError("This adapter serves only the unchanged local raw Qwen checkpoint")
        expected = {"model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
            "vllm_version": "0.32.0", "raw_release": True, "adapter_sha256": None,
            "model_manifest_sha256": "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6",
            "context_limit": 131072, "max_output_tokens": 32768,
            "service_admission_complete": True, "deployment_version": "v064-owned-user-ref-resident-r1"}
        if (any(service_identity.get(k) != v for k, v in expected.items())
                or service_identity.get("port") != transport.port or transport.port not in PORTS
                or type(seed) is not int or not 0 <= seed < 2**63
                or not slot_id.startswith("v064:") or not slot_id.endswith(":" + str(seed))
                or ":" + condition["condition_id"] + ":" not in slot_id):
            raise ValueError("Local model, deployment or unique condition/seed identity differs")
        self.allowed_tools = frozenset(allowed_tools)
        if not self.allowed_tools:
            raise ValueError("The actual initialized tool schema must be fixed before generation")
        self.transport, self.folder = transport, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.counter = OptionalToolsCounter(transport, self.folder)
        self.ledger = BudgetLedger(condition)
        self.slot_id, self.seed = slot_id, seed
        self.service_identity, self.condition = copy.deepcopy(service_identity), copy.deepcopy(condition)
        self.authorized, self.fixture, self.halted = True, False, None
        self.started, self.lock = time.monotonic(), threading.Lock()
        self.request_defaults = {"model": REF_MODEL, "max_tokens": 32768, "temperature": .6,
            "top_p": .95, "top_k": 20, "min_p": 0., "presence_penalty": 0.,
            "repetition_penalty": 1., "stream": False, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": True}, "add_generation_prompt": True,
            "continue_final_message": False, "add_special_tokens": False}
        self.save()

    def request(self, messages, tools):
        return canonical_request({**copy.deepcopy(self.request_defaults),
                                  "messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})

    def count(self, request):
        result = super().count(canonical_request(request))
        return {**result, "method": "fixed_vllm_exact_provider_ids", "exact_provider_token_ids_available": True}

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({"version": VERSION,
            "arm": self.condition["arm"], "condition_id": self.condition["condition_id"],
            "slot_id": self.slot_id, "service_identity": self.service_identity,
            "formal_execution_authorized": True, "halted": self.halted,
            "tokenize_http_requests": self.counter.requests, **self.ledger.snapshot()}))

    def complete(self, request, usage_id="agent"):
        request = canonical_request(request)
        with self.lock:
            sent = False
            if self.halted:
                raise DispatchStopped("episode_already_stopped:" + self.halted)
            if any(request.get(k) != v for k, v in self.request_defaults.items()):
                raise ValueError("Request differs from the frozen Qwen inference recipe")
            names = {tool["function"]["name"] for tool in request.get("tools", [])}
            if ((usage_id == "agent" and names != self.allowed_tools)
                    or (usage_id == "condenser" and names) or usage_id not in {"agent", "condenser"}):
                raise ValueError("Request tools or purpose differ from the initialized interface")
            try:
                if time.monotonic() - self.started >= self.limits["soft_seconds"]:
                    raise BeforeQwenDispatch("soft_deadline_before_generation")
                measured = self.count(request)
                if time.monotonic() - self.started >= self.limits["soft_seconds"]:
                    raise BeforeQwenDispatch("soft_deadline_after_count")
                index = self.ledger.attempts + 1
                ref = write_new(self.folder / f"request-{index:04d}.json", {
                    "request": request, "exact_input": measured, "usage_id": usage_id,
                    "slot_id": self.slot_id, "service_identity": self.service_identity})
                self.ledger.reserve(measured, usage_id, ref)
                self.save()
                sent = True
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
                    if not sent and self.ledger.inflight is None:
                        raise BeforeQwenDispatch(str(error)) from error
                    raise
                raise AccountingFault(self.halted) from error
