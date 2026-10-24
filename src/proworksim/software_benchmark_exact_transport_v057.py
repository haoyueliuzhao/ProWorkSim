"""Preserve provider reasoning in the SDK projection of an exact REF response.

The admitted adapter still owns counting, dispatch, the original wire archive,
and usage settlement. This version changes only response conversion after that
settlement; it does not change inference settings, count tokens, or retry calls.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

from . import software_benchmark_exact_transport_v054 as original
from .software_benchmark_candidates_v054 import write_new
from .storage import digest, json_bytes

VERSION = "v057-exact-native-response-projection-r2-fault-guard"


class ResponseNormalizationError(ValueError):
    """An ambiguous provider response must not silently choose one reasoning field."""


class ResponseProjectionFault(RuntimeError):
    """A settled but unusable response permanently closes this model adapter."""


class ProjectionGuard:
    """Shared by agent/condenser copies; never resets the underlying ledger."""

    def __init__(self, delegate, folder):
        self.delegate, self.folder = delegate, folder
        self.fault = None

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def assert_healthy(self):
        if self.fault is not None:
            raise ResponseProjectionFault("Prior response projection failed; further model access is forbidden")

    def count(self, request):
        self.assert_healthy()
        return self.delegate.count(request)

    def complete(self, request, usage_id):
        self.assert_healthy()
        return self.delegate.complete(request, usage_id)

    def record_failure(self, body, error, usage_id):
        if self.fault is not None:
            return
        self.fault = {
            "version": VERSION, "usage_id": usage_id, "response_id": body.get("id"),
            "wire_body_sha256": digest(json_bytes(body)),
            "error_type": type(error).__name__, "error": str(error),
            "wire_response_overwritten": False, "usage_already_settled": True,
            "future_count_and_completion_forbidden": True, "automatic_retry": False,
        }
        if self.folder is not None:
            try:
                write_new(self.folder / "projection-fault.json", self.fault)
            except Exception as evidence_error:
                # The sticky in-memory guard must survive an evidence-write
                # failure too; the controller retains this state on closure.
                self.fault["receipt_write_error"] = {
                    "type": type(evidence_error).__name__, "message": str(evidence_error)}


def response_projection_fault(adapter):
    guard = getattr(adapter, "_v057_projection_guard", None)
    return copy.deepcopy(guard.fault) if isinstance(guard, ProjectionGuard) else None


def assert_response_projection_healthy(adapter):
    guard = getattr(adapter, "_v057_projection_guard", None)
    if not isinstance(guard, ProjectionGuard):
        raise ResponseProjectionFault("The v057 response projection guard was not bound")
    guard.assert_healthy()


def normalize_response(body):
    """Return an independent SDK projection and a content-free binding receipt.

    Null is an absent field; an empty string is an explicit value. Existing
    reasoning_content is retained. Two non-null unequal values are a conflict,
    including empty versus nonempty, and unsupported value types are rejected.
    """
    if not isinstance(body, dict):
        raise ResponseNormalizationError("Expected one complete response object")
    choices = body.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ResponseNormalizationError("Expected the admitted single response choice")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ResponseNormalizationError("Expected an assistant response message")
    reasoning, content = message.get("reasoning"), message.get("reasoning_content")
    if any(value is not None and not isinstance(value, str) for value in (reasoning, content)):
        raise ResponseNormalizationError("Reasoning fields must be text or null")
    if reasoning is not None and content is not None and reasoning != content:
        raise ResponseNormalizationError("Conflicting provider and SDK reasoning fields")
    projection = copy.deepcopy(body)
    added = reasoning is not None and content is None
    if added:
        projection["choices"][0]["message"]["reasoning_content"] = reasoning
    projected = projection["choices"][0]["message"].get("reasoning_content")
    receipt = {
        "version": VERSION, "response_id": body.get("id"),
        "wire_body_sha256": digest(json_bytes(body)),
        "sdk_projection_sha256": digest(json_bytes(projection)),
        "reasoning_alias_added": added,
        "reasoning_characters": len(projected) if projected is not None else 0,
        "reasoning_sha256": digest(projected.encode()) if projected is not None else None,
        "content_preserved": projection["choices"][0]["message"].get("content") == message.get("content"),
        "tool_calls_preserved": projection["choices"][0]["message"].get("tool_calls") == message.get("tool_calls"),
        "usage_preserved": projection.get("usage") == body.get("usage"),
        "raw_wire_response_overwritten": False, "additional_model_calls": 0,
    }
    return projection, receipt


@lru_cache(maxsize=1)
def shared_llm_type():
    from pydantic import PrivateAttr

    class ReasoningPreservingNativeLLM(original.shared_llm_type()):
        _normalization_folder: object = PrivateAttr(default=None)

        def completion(self, messages, tools=None, **kwargs):
            from litellm.types.utils import ModelResponse
            from openhands.sdk.llm import Message
            from openhands.sdk.llm.llm_response import LLMResponse
            from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage

            self._adapter.assert_healthy()
            request = self._request(messages, tools, kwargs)
            # The adapter archives and settles this unmodified response first.
            body = self._adapter.complete(request, self.usage_id)
            try:
                projection, receipt = normalize_response(body)
                raw = ModelResponse(**body)
                projected_raw = ModelResponse(**projection)
                message = Message.from_llm_chat_message(projected_raw.choices[0].message)
                if self._normalization_folder is not None:
                    receipt.update(usage_id=self.usage_id)
                    name = digest(json_bytes([self.usage_id, body.get("id"), receipt["wire_body_sha256"]]))
                    write_new(Path(self._normalization_folder) / (name + ".json"), receipt)
                totals = self._adapter.ledger.snapshot()["per_usage_id"][self.usage_id]
                return LLMResponse(
                    message=message, raw_response=raw,
                    metrics=MetricsSnapshot(model_name=request["model"],
                                            accumulated_token_usage=TokenUsage(
                                                model=request["model"], **totals)))
            except Exception as error:
                self._adapter.record_failure(body, error, self.usage_id)
                raise

    return ReasoningPreservingNativeLLM


def build_llm(adapter, *, normalization_folder=None):
    """Drop-in v057 factory; inherited exact request export and limits are intact."""
    llm = shared_llm_type()(
        model="openai/Qwen3.5-9B", usage_id="agent", api_mode="chat",
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        max_input_tokens=adapter.maximum_input_tokens,
        max_output_tokens=adapter.maximum_output_tokens, temperature=adapter.temperature,
    )
    folder = None
    if normalization_folder is not None:
        folder = Path(normalization_folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        llm._normalization_folder = str(folder)
    if getattr(adapter, "_v057_projection_guard", None) is not None:
        raise ResponseProjectionFault("An adapter cannot obtain a second fresh projection guard")
    guard = ProjectionGuard(adapter, folder)
    adapter._v057_projection_guard = guard
    llm._adapter = guard
    return llm
