"""Count native SDK condenser prefixes without treating them as API requests.

Only get_token_count's incomplete tail uses the low-level official encoder.
Actual generation still uses the unchanged strict complete-request counter.
No synthetic tool result is created or sent, and no retained event is edited.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path

from proworksim.software_benchmark_deepseek_interfaces_v055 import (
    MODEL, _canonical_call, native_llm_type,
)
from proworksim.storage import digest, json_bytes

VERSION = "v055-native-condenser-prefix-count-r2"


def pending_tail_tool_ids(messages):
    """Allow an unfinished tail only; reject orphan or internally broken rounds."""
    pending = []
    for message in messages:
        role = message.get("role")
        if pending:
            if role != "tool" or message.get("tool_call_id") not in pending:
                raise ValueError("Native count prefix has an internally incomplete tool round")
            pending.remove(message["tool_call_id"])
            continue
        if role == "tool":
            raise ValueError("Native count prefix contains an orphan tool result")
        if role == "assistant" and message.get("tool_calls"):
            pending = [call["id"] for call in message["tool_calls"]]
            if len(set(pending)) != len(pending) or any(not isinstance(i, str) or not i for i in pending):
                raise ValueError("Native count prefix contains invalid tool identities")
    return tuple(pending)


def restore_prefix_reasoning(messages, history):
    """An SDK event prefix may include only the first calls of a response batch."""
    result = copy.deepcopy(messages)
    for index, message in enumerate(result):
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        ids = tuple(call["id"] for call in calls)
        matches = [original for keys, original in history.messages.items() if keys[:len(ids)] == ids]
        if len(matches) != 1:
            raise ValueError("Count-only assistant prefix lacks one original response provenance")
        original = matches[0]
        original_calls = original["tool_calls"][:len(ids)]
        if [_canonical_call(c) for c in calls] != [_canonical_call(c) for c in original_calls]:
            raise ValueError("Count-only SDK prefix changed actual tool-call arguments")
        result[index] = {**copy.deepcopy(original), "tool_calls": copy.deepcopy(original_calls)}
    return result


def count_incomplete_prefix(adapter, request, pending):
    """Use official low-level objects that can represent an unfinished prefix."""
    counter = adapter.counter
    if not all(hasattr(counter, name) for name in ("recipe", "encoding", "margin", "manifest_sha256")):
        raise ValueError("Count-only prefixes require the frozen official recipe counter")
    if not pending or pending_tail_tool_ids(request["messages"]) != pending:
        raise ValueError("Only a verified incomplete tail may use the prefix encoder")
    recipe = counter.recipe
    messages = []
    for message in request["messages"]:
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ValueError("Only the frozen text-only SDK serialization is supported")
        role = message["role"]
        if role == "system":
            value = recipe.SystemMessage(content)
        elif role == "user":
            value = recipe.UserMessage(content)
        elif role == "tool":
            value = recipe.ToolMessage(content, tool_call_id=message["tool_call_id"])
        elif role == "assistant":
            calls = [recipe.ToolCall(call["id"], call["function"]["name"], call["function"]["arguments"])
                     for call in message.get("tool_calls") or []]
            value = recipe.AssistantMessage(content, reasoning_content=message.get("reasoning_content"),
                                            tool_calls=calls or None)
        else:
            raise ValueError("Unknown role in native prefix")
        messages.append(value)
    tools = [recipe.ToolDefinition(**item["function"]) for item in request.get("tools", [])]
    conversation = recipe.Conversation(messages,
        thinking_mode=request["thinking"]["type"] == "enabled", tools=tools,
        tool_choice=request.get("tool_choice", "none"), reasoning_effort=request.get("reasoning_effort"))
    ids = counter.encoding.encode(conversation)
    measurement = {"version": VERSION, "count_only_not_dispatchable": True,
        "method": "official_low_level_encoding_of_original_incomplete_SDK_event_prefix",
        "request_sha256": digest(json_bytes(request)), "local_encoded_prompt_tokens": len(ids),
        "reservation_margin_tokens": counter.margin, "prompt_tokens": len(ids) + counter.margin,
        "token_ids_sha256": digest(json_bytes(ids)), "tokenizer_manifest_sha256": counter.manifest_sha256,
        "pending_tail_tool_ids": list(pending), "synthetic_observations_created": 0,
        "network_requests": 0, "actual_generation": False}
    # Small append-only diagnostics contain hashes/counts, never a rewritten
    # transcript or anything returned to the model as tool feedback.
    path = Path(adapter.folder) / "count-only-prefix-r2.jsonl"
    with path.open("a") as stream:
        stream.write(json.dumps(measurement, ensure_ascii=False, separators=(",", ":")) + "\n")
    return measurement["prompt_tokens"]


@lru_cache(maxsize=1)
def prefix_llm_type():
    class PrefixCountingNativeLLM(native_llm_type()):
        def get_token_count(self, messages, tools=None, **kwargs):
            if not messages:
                return 0
            wire = self.format_messages_for_llm(messages)
            pending = pending_tail_tool_ids(wire)
            if not pending:
                return super().get_token_count(messages, tools, **kwargs)
            unexpected = set(kwargs) - {"add_security_risk_prediction", "on_token", "call_context"}
            if unexpected:
                raise ValueError("Unfrozen SDK request kwargs: " + ",".join(sorted(unexpected)))
            restored = restore_prefix_reasoning(wire, self._adapter.history)
            request = self._adapter.request(restored, [dict(tool.to_openai_tool(
                add_security_risk_prediction=bool(kwargs.get("add_security_risk_prediction"))))
                for tool in tools or []])
            return count_incomplete_prefix(self._adapter, request, pending)

    return PrefixCountingNativeLLM


def build_native_llm(adapter):
    llm = prefix_llm_type()(model="openai/" + MODEL, usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        native_tool_calling=True, force_string_serializer=True,
        max_input_tokens=adapter.maximum_input_tokens,
        max_output_tokens=adapter.maximum_output_tokens)
    llm._adapter = adapter
    return llm
