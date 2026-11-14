"""Public, key-free Flash wire contract shared with isolated controllers.

This module has no network transport, credential loading or monetary ledger.
"""
from __future__ import annotations

import hashlib
import json

MODEL = "deepseek-flash"
DOCUMENTED_MODEL_VERSION = "DeepSeek-V4.1-Flash-1017"
CONTEXT_TOKENS, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS = 131072, 98304, 32768
PROVIDER_CONTEXT_TOKENS, PROVIDER_MAX_OUTPUT_TOKENS = 1048576, 393216
MISS_NANOYUAN, HIT_NANOYUAN, OUTPUT_NANOYUAN = 2000, 40, 8000


class BudgetStopped(RuntimeError):
    """Shared API budget or accounting integrity stopped dispatch."""


class ConcurrencyBusy(RuntimeError):
    """A shared admission boundary is temporarily occupied."""


class APIUncertainFailure(RuntimeError):
    """The provider attempt may have been billed; never replay it."""


class ProviderOutputBoundViolation(RuntimeError):
    """Known bill, but the response violates the experimental boundary."""

    def __init__(self, reason, *, body=None):
        super().__init__(reason)
        self.authoritative_response = body
        self.before_dispatch_proven = False


class PreDispatchBudgetStopped(BudgetStopped):
    before_dispatch_proven = True


class PreDispatchConcurrencyBusy(ConcurrencyBusy):
    before_dispatch_proven = True


def _integer(value, name, *, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("Invalid nonnegative integer: "+name)
    return value


def slot_user_id(slot_id, condition):
    raw = json.dumps({"slot_id": slot_id, "condition": condition}, sort_keys=True,
                     ensure_ascii=False, separators=(",", ":")).encode()
    return "v064-"+hashlib.sha256(raw).hexdigest()


def model_profile():
    return {
        "model": MODEL, "documented_model_version": DOCUMENTED_MODEL_VERSION,
        "commercial_alias_is_not_immutable_weight_hash": True,
        "thinking": {"type": "enabled"}, "reasoning_effort": "high", "top_p": 0.95,
        "context_tokens": CONTEXT_TOKENS, "max_input_tokens": MAX_INPUT_TOKENS,
        "max_output_tokens": MAX_OUTPUT_TOKENS, "stream": False,
        "unsupported_parameters_omitted": ["temperature", "top_k", "min_p", "seed",
                                           "repetition_penalty", "presence_penalty", "frequency_penalty"],
        "endpoint": "https://api.deepseek.com/chat/completions",
        "proxy": False, "redirects": False, "server_search_or_fetch": False,
    }


def validate_payload(payload, allowed_tool_names):
    allowed = {"model", "messages", "tools", "tool_choice", "max_tokens", "thinking",
               "reasoning_effort", "top_p", "stream", "user_id", "response_format", "stop"}
    if not isinstance(payload, dict) or set(payload)-allowed:
        raise ValueError("Unapproved API fields or server tools")
    if (payload.get("model") != MODEL or payload.get("stream") is not False
            or payload.get("thinking") != {"type": "enabled"}
            or payload.get("reasoning_effort") != "high" or payload.get("top_p") != 0.95):
        raise ValueError("Freeze Flash thinking/high/top_p=0.95 without temperature")
    if not _integer(payload.get("max_tokens"), "max_tokens", maximum=MAX_OUTPUT_TOKENS):
        raise ValueError("A positive output bound is required")
    tools = payload.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("Tools must be the frozen local function list")
    seen = set()
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {"type", "function"} or tool["type"] != "function":
            raise ValueError("Only local function schemas, never server tools")
        function = tool["function"]
        if not isinstance(function, dict) or set(function)-{"name", "description", "parameters", "strict"}:
            raise ValueError("Unexpected function schema extension")
        name = function.get("name")
        if name not in allowed_tool_names or name in seen:
            raise ValueError("Unexpected or duplicated local tool name")
        seen.add(name)
    if payload.get("tool_choice", "auto" if tools else "none") not in {"auto", "none"}:
        raise ValueError("Thinking mode does not admit required or named tool choice")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("A nonempty text history is required")
    for message in messages:
        if (not isinstance(message, dict)
                or set(message)-{"role", "content", "name", "tool_calls", "tool_call_id", "reasoning_content"}
                or message.get("role") not in {"system", "user", "assistant", "tool"}):
            raise ValueError("Unexpected message role or extension")
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise ValueError("Only text messages; no remote files, images or URLs")
        if tools and message["role"] == "assistant" and not isinstance(message.get("reasoning_content"), str):
            raise ValueError("Original reasoning_content required on every assistant history turn")
    return payload


def normalize_usage(body):
    if not isinstance(body, dict) or not isinstance(body.get("usage"), dict):
        raise ValueError("missing_authoritative_usage")
    usage = body["usage"]
    prompt = _integer(usage.get("prompt_tokens"), "prompt_tokens", maximum=PROVIDER_CONTEXT_TOKENS)
    output = _integer(usage.get("completion_tokens"), "completion_tokens", maximum=PROVIDER_MAX_OUTPUT_TOKENS)
    total = _integer(usage.get("total_tokens"), "total_tokens", maximum=PROVIDER_CONTEXT_TOKENS)
    hit = usage.get("prompt_cache_hit_tokens")
    if hit is None:
        hit = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    hit = _integer(hit, "prompt_cache_hit_tokens", maximum=prompt)
    miss = _integer(usage.get("prompt_cache_miss_tokens", prompt-hit), "prompt_cache_miss_tokens", maximum=prompt)
    alternate = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", hit)
    _integer(alternate, "alternate_cached_tokens", maximum=prompt)
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if reasoning is not None:
        _integer(reasoning, "reasoning_tokens", maximum=output)
    if prompt != hit+miss or total != prompt+output or alternate != hit:
        raise ValueError("usage_partitions_disagree")
    if not isinstance(body.get("id"), str) or not body["id"]:
        raise ValueError("missing_provider_response_identity")
    if body.get("model") not in {MODEL, DOCUMENTED_MODEL_VERSION, DOCUMENTED_MODEL_VERSION.lower()}:
        raise ValueError("unexpected_provider_model_identity")
    if body.get("system_fingerprint") is not None and not isinstance(body["system_fingerprint"], str):
        raise ValueError("invalid_provider_system_fingerprint")
    return {
        "input_tokens": prompt, "output_tokens": output, "total_tokens": total,
        "reasoning_tokens": reasoning, "reasoning_tokens_known": reasoning is not None,
        "cache_hit_tokens": hit, "cache_miss_tokens": miss,
        "provider_response_id": body["id"], "provider_model": body["model"],
        "system_fingerprint": body.get("system_fingerprint"), "reasoning_included_in_output": True,
        "peak_cost_nanoyuan": hit*HIT_NANOYUAN+miss*MISS_NANOYUAN+output*OUTPUT_NANOYUAN,
    }
