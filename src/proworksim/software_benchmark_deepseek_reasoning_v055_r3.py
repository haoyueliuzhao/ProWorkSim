"""Preserve original SDK assistant reasoning, including no-tool/empty values.

This changes serialization only. The original SDK Message owns the reasoning
field; no response is guessed from text and no missing value is manufactured.
The r2 count-only prefix path and strict generation transport are inherited.
"""
from __future__ import annotations

from functools import lru_cache

from .software_benchmark_deepseek_interfaces_v055 import MODEL
from .software_benchmark_deepseek_prefix_v055_r2 import prefix_llm_type

VERSION = "v055-native-original-reasoning-serialization-r3"


@lru_cache(maxsize=1)
def reasoning_llm_type():
    class OriginalReasoningNativeLLM(prefix_llm_type()):
        def _to_chat_dicts(self, messages):
            wire = super()._to_chat_dicts(messages)
            if not self._adapter.thinking:
                return wire
            for original, serialized in zip(messages, wire, strict=True):
                if original.role != "assistant":
                    continue
                value = original.reasoning_content
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError("Original SDK reasoning_content must be a string or absent")
                    serialized["reasoning_content"] = value
            return wire

    return OriginalReasoningNativeLLM


def build_native_llm(adapter):
    llm = reasoning_llm_type()(model="openai/" + MODEL, usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        native_tool_calling=True, force_string_serializer=True,
        max_input_tokens=adapter.maximum_input_tokens,
        max_output_tokens=adapter.maximum_output_tokens)
    llm._adapter = adapter
    return llm
