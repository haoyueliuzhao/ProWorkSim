"""CPU-only controls for exact token-budget selection and durable preflight."""

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v028 import (
    CAPACITY_ERROR, SoftwareContextTransport, project_software_request,
)


def render(request):
    text = "".join(message.get("content") or "" for message in request["messages"])
    return text, request["messages"], {"fixture": True}


def tokenizer(text, **kwargs):
    return {"input_ids": list(text)}


def request(old=300, newest=20):
    return {"model": "explicit-cpu-fixture", "max_tokens": 20, "temperature": 0.7,
            "tools": [{"name": "public-fixture"}], "messages": [
                {"role": "system", "content": "Task"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
                {"role": "tool", "tool_call_id": "old", "content": "x" * old},
                {"role": "user", "content": "Exact observation"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "new", "function": {"name": "read"}}]},
                {"role": "tool", "tool_call_id": "new", "content": "y" * newest}]}


def test_remove_only_old_complete_round_preserving_latest_and_all_other_fields():
    original = request()
    before = copy.deepcopy(original)
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=100)
    assert audit["fits"] and audit["removed_indices"] == [1, 2]
    assert selected["messages"] == [original["messages"][i] for i in [0, 3, 4, 5]]
    assert {k: v for k, v in selected.items() if k != "messages"} == {
        k: v for k, v in original.items() if k != "messages"}
    assert original == before
    assert audit["latest_complete_round_preserved"] == [4, 5]
    assert audit["retained_messages_unchanged"]


def test_fitting_input_is_not_changed_and_irreducible_latest_round_is_not_dropped():
    original = request(old=1, newest=1)
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=100)
    assert selected == original and audit["removed_indices"] == []
    selected, audit = project_software_request(request(newest=150), render=render,
                                              tokenizer=tokenizer, context_limit=100)
    assert not audit["fits"] and audit["removed_indices"] == [1, 2]
    assert selected["messages"][-1]["content"] == "y" * 150


def test_orphan_or_mismatched_tool_results_are_never_repaired_by_projection():
    original = request()
    original["messages"][-1]["tool_call_id"] = "wrong"
    with pytest.raises(ValueError, match="match"):
        project_software_request(original, render=render, tokenizer=tokenizer, context_limit=100)


def test_transport_archives_both_requests_and_never_calls_model_for_irreducible_overflow(tmp_path):
    calls = []

    def complete(payload, **kwargs):
        assert (tmp_path / "request-00001/original-request.json").exists()
        assert (tmp_path / "request-00001/selected-request.json").exists()
        calls.append(payload)
        return {"http_status": 200, "body": {"explicit_cpu_fixture": True}}

    owner = SimpleNamespace(recipe={"max_length": 100}, prepare_request=render, tokenizer=tokenizer,
                            transport=SimpleNamespace(complete=complete))
    transport = SoftwareContextTransport(owner, tmp_path)
    transport.complete(request(), timeout_seconds=5)
    assert len(calls) == 1 and len(calls[0]["messages"]) == 4
    result = transport.complete(request(newest=150), timeout_seconds=5)
    assert len(calls) == 1 and result["http_status"] == 400
    assert result["body"]["generation_started"] is False
    assert result["body"]["error"]["code"] == CAPACITY_ERROR
    saved = json.loads((tmp_path / "request-00002/original-request.json").read_text())
    assert saved == request(newest=150)
