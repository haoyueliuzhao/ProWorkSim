"""Necessary CPU controls for new Gamma, no sampled model or weight loading."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v028 import validate_budget_preparation
from proworksim.software_context_v034 import (
    CAPACITY_ERROR, SoftwareContextTransport, deduplicate_contracts, project_software_request,
)
from proworksim.storage import digest, json_bytes


def observation(contract, description=None, logical_time=0):
    return {"role": "user", "content": json.dumps({"role_task": "Original role instruction",
            "observation": {"contract": contract,
                            "root_goal": {"description": contract if description is None else description,
                                          "task_id": "root", "immutable": True},
                            "tasks": [{"id": "real-task", "owner": "member_b"}],
                            "logical_time": logical_time, "workspace_reference": {"version_id": "v3"}}})}


def request():
    contract = "Full contract includes every requirement. " * 20
    return {"model": "explicit-no-model-cpu", "max_tokens": 20, "temperature": 0.7,
            "tools": [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}],
            "messages": [{"role": "system", "content": "Original system"}, observation(contract),
                         {"role": "assistant", "content": "old", "tool_calls": [{"id": "old", "function": {"name": "read"}}]},
                         {"role": "tool", "tool_call_id": "old", "content": "old feedback" * 300},
                         {"role": "assistant", "content": "latest", "tool_calls": [{"id": "new", "function": {"name": "read"}}]},
                         {"role": "tool", "tool_call_id": "new", "content": "real latest failed check"},
                         {"role": "user", "content": json.dumps({"public_format_feedback": {"reason": "real format error"}})},
                         observation(contract, logical_time=8)]}


def render(payload):
    return json.dumps(payload, ensure_ascii=False), payload["messages"], {"fixture": True}


def tokenizer(text, **kwargs):
    return {"input_ids": list(text.encode())}


def test_exact_duplicate_only_original_schema_state_and_feedback_preserved():
    original = request()
    before = copy.deepcopy(original)
    selected, audit = deduplicate_contracts(original)
    assert original == before and len(audit["removed_values"]) == 3
    assert selected["tools"] == original["tools"]
    assert selected["messages"][2:7] == original["messages"][2:7]
    for index in [1, 7]:
        left = json.loads(selected["messages"][index]["content"])
        right = json.loads(original["messages"][index]["content"])
        for key in ["tasks", "logical_time", "workspace_reference"]:
            assert left["observation"][key] == right["observation"][key]
    assert json.loads(selected["messages"][-1]["content"])["observation"]["contract"] == json.loads(original["messages"][-1]["content"])["observation"]["contract"]
    assert deduplicate_contracts(selected)[0] == selected


def test_different_contract_and_nonidentical_root_description_are_never_deduplicated():
    original = request()
    original["messages"][1] = observation("Historical distinct contract", "Historical distinct root goal")
    original["messages"][-1] = observation("Current complete contract", "Current root differs by one char.")
    selected, audit = deduplicate_contracts(original)
    assert selected == original and audit["removed_values"] == []


def test_capacity_projection_keeps_unique_latest_contract_and_latest_true_feedback():
    original = request()
    selected, audit = project_software_request(original, render=render, tokenizer=tokenizer, context_limit=2500)
    assert audit["fits"] and audit["removed_indices"] == [2, 3]
    assert selected["messages"][-1] == deduplicate_contracts(original)[0]["messages"][-1]
    assert original["messages"][5] in selected["messages"]
    assert original["messages"][6] in selected["messages"]
    assert audit["original_request_sha256"] == digest(json_bytes(original))


def owner(capacity=2500, corrupt=False):
    calls = []
    identity = {"cpu_fixture": True}
    def complete(payload, **kwargs):
        calls.append(payload)
        actual = tokenizer(render(payload)[0])["input_ids"]
        if corrupt:
            actual[0] += 1
        return {"http_status": 200, "body": {"actor_identity": identity,
                "token_trace": {"input_ids": actual}, "fixture_only": True}}
    return SimpleNamespace(recipe={"max_length": capacity}, prepare_request=render, tokenizer=tokenizer,
                           transport=SimpleNamespace(complete=complete), freeze_identity=lambda: identity,
                           window_id="cpu-control-only", calls=calls)


def test_transport_binds_admitted_ids_and_archives_original_before_fixture_response(tmp_path):
    native = owner()
    transport = SoftwareContextTransport(native, tmp_path)
    original = request()
    prepared = transport.prepare_for_budget(original)
    validate_budget_preparation(original, prepared)
    assert prepared["prompt_tokens"] + original["max_tokens"] <= 2500
    transport.complete(original)
    saved = json.loads((tmp_path / "request-00001/original-request.json").read_text())
    selected = json.loads((tmp_path / "request-00001/selected-request.json").read_text())
    assert saved == original and native.calls == [selected]
    assert prepared["input_ids_sha256"] == digest(json_bytes(tokenizer(render(selected)[0])["input_ids"]))


def test_capacity_and_changed_prepared_request_block_without_fixture_generation(tmp_path):
    native = owner(capacity=100)
    transport = SoftwareContextTransport(native, tmp_path)
    prepared = transport.prepare_for_budget(request())
    assert not prepared["fits"]
    transport.discard_prepared_request(request())
    response = transport.complete(request())
    assert response["body"]["error"]["code"] == CAPACITY_ERROR
    assert response["body"]["generation_started"] is False and native.calls == []
    native = owner()
    transport = SoftwareContextTransport(native, tmp_path / "tamper")
    transport.prepare_for_budget(request())
    changed = request()
    changed["temperature"] = 0.8
    with pytest.raises(ValueError, match="checksum"):
        transport.complete(changed)
    assert native.calls == []


def test_actual_input_id_mismatch_remains_blocking(tmp_path):
    native = owner(corrupt=True)
    transport = SoftwareContextTransport(native, tmp_path)
    transport.prepare_for_budget(request())
    with pytest.raises(ValueError, match="admitted tokenized"):
        transport.complete(request())
