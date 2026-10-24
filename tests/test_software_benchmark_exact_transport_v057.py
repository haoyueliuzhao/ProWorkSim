"""Response projection preserves evidence and rejects ambiguous reasoning."""
import copy

import pytest

from proworksim.software_benchmark_exact_transport_v057 import (
    ResponseNormalizationError, normalize_response,
)


def response(**fields):
    return {"id": "saved-response", "model": "fixed-model", "usage": {
        "prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "literal final content",
            "tool_calls": [{"id": "one", "type": "function", "function": {
                "name": "think", "arguments": '{"thought":"literal"}'}}], **fields}}]}


def test_reasoning_alias_preserves_raw_content_tools_usage_and_idempotence():
    body = response(reasoning="recorded reasoning")
    before = copy.deepcopy(body)
    projected, receipt = normalize_response(body)
    assert body == before and projected is not body
    assert projected["choices"][0]["message"]["reasoning_content"] == "recorded reasoning"
    projected["choices"][0]["message"].pop("reasoning_content")
    assert projected == before
    assert receipt["reasoning_alias_added"] and all(receipt[key] for key in (
        "content_preserved", "tool_calls_preserved", "usage_preserved"))
    twice, receipt2 = normalize_response(normalize_response(body)[0])
    assert twice == normalize_response(body)[0] and not receipt2["reasoning_alias_added"]


def test_null_absence_and_explicit_empty_reasoning_are_distinct():
    for fields in ({}, {"reasoning": None}, {"reasoning": None, "reasoning_content": "SDK text"},
                   {"reasoning": "same", "reasoning_content": "same"}):
        body = response(**fields)
        projected, receipt = normalize_response(body)
        assert projected == body and not receipt["reasoning_alias_added"]
    projected, receipt = normalize_response(response(reasoning="", reasoning_content=None))
    assert projected["choices"][0]["message"]["reasoning_content"] == ""
    assert receipt["reasoning_alias_added"] and receipt["reasoning_characters"] == 0


def test_conflicting_or_untyped_reasoning_is_rejected_without_mutation():
    for fields in ({"reasoning": "provider", "reasoning_content": "SDK"},
                   {"reasoning": "provider", "reasoning_content": ""},
                   {"reasoning": ["not-text"]}, {"reasoning_content": 4}):
        body = response(**fields)
        before = copy.deepcopy(body)
        with pytest.raises(ResponseNormalizationError):
            normalize_response(body)
        assert body == before
