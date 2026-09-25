"""Offline context-policy tests; no HTTP, GPU generation or learning claim.

The existing A0 fixture uses real WorldCore tools with explicitly simulated model
responses. Context selection is verified against actual retained message bytes.
"""

import copy
import json

import pytest

from proworksim.model_policy import ADAPTER_VERSION, ModelPolicy, normalize_config
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import digest, json_bytes
from test_model_policy_v11 import call, events, fixture, response


def answers(protocol):
    if protocol == "native_tools":
        return [
            response(call(identity="read-one")),
            response(call(identity="read-two")),
            response(content='{"kind":"wait","reason":"Retain actual history"}'),
        ]
    return [
        response(
            content=json.dumps(
                {"kind": "act", "action": "read_object", "arguments": {"alias": "input"}}
            )
        )
        for _ in range(2)
    ] + [response(content='{"kind":"wait","reason":"Retain actual history"}')]


@pytest.mark.parametrize("protocol", ["native_tools", "single_decision_json"])
def test_latest_observation_preserves_full_real_history_and_actual_results(tmp_path, protocol):
    _, transport, _, runtime = fixture(
        tmp_path,
        answers(protocol),
        {"action_protocol": protocol, "context_policy": "latest_observation"},
    )
    first = runtime.step()
    original = copy.deepcopy(runtime.roles["target"]["memory"])
    runtime.step()
    memory = runtime.roles["target"]["memory"]
    assert memory["messages"][: len(original["messages"])] == original["messages"]
    assert [row["index"] for row in memory["observation_messages"]] == [1, 4]
    request = transport.requests[1]
    assert request["messages"] == [memory["messages"][index] for index in (0, 2, 3, 4)]
    tool = request["messages"][2]
    actual = json.loads(tool["content"])
    assert (
        actual["public_tool_result"] if protocol == "single_decision_json" else actual
    ) == first["response"]
    current = json.loads(request["messages"][-1]["content"])
    observations = [
        event["payload"]
        for event in runtime.recorder.events
        if event["kind"] == "public_observation"
    ]
    assert current["observation"] == observations[-1]
    assert current["role_task"] == runtime.policies["target"].config["task"]
    assert (
        current["public_tools"]
        if protocol == "single_decision_json"
        else [row["function"] for row in request["tools"][:-2]]
    ) == [event["payload"] for event in runtime.recorder.events if event["kind"] == "public_tools"][
        -1
    ]
    assert "context_selection" not in request and "observation_messages" not in request


@pytest.mark.parametrize("protocol", ["native_tools", "single_decision_json"])
def test_request_selection_is_reconstructable_from_retained_original_indices(tmp_path, protocol):
    _, transport, _, runtime = fixture(
        tmp_path,
        answers(protocol),
        {"action_protocol": protocol, "context_policy": "latest_observation"},
    )
    runtime.step()
    runtime.step()
    runtime.step()
    memory = runtime.roles["target"]["memory"]
    starts = [row for row in events(runtime, "model_attempt") if row["stage"] == "started"]
    assert len(starts) == 3
    for actual, attempt in zip(transport.requests, starts):
        selection = attempt["context_selection"]
        original = memory["messages"][: selection["original_message_count"]]
        selected = [original[index] for index in selection["selected_indices"]]
        assert selection["original_messages_sha256"] == digest(json_bytes(original))
        assert selection["selected_messages_sha256"] == digest(json_bytes(selected))
        assert all(
            row["sha256"] == digest(json_bytes(original[row["index"]]))
            for row in selection["messages"]
        )
        assert all(
            row["reason"] == "earlier_registered_public_observation"
            for row in selection["messages"]
            if not row["selected"]
        )
        assert actual["messages"] == selected
        assert selection["request_sha256"] == digest(json_bytes(actual))
        assert selection["unfiltered_request_sha256"] == digest(
            json_bytes({**actual, "messages": original})
        )
        assert actual == attempt["request"]
    assert starts[-1]["context_selection"]["removed_indices"] == [1, 4]


def test_default_full_history_request_keeps_all_original_messages(tmp_path):
    _, transport, policy, runtime = fixture(tmp_path, answers("native_tools"))
    assert policy.config["context_policy"] == "full_history"
    runtime.step()
    runtime.step()
    attempt = [row for row in events(runtime, "model_attempt") if row["stage"] == "started"][-1]
    count = attempt["context_selection"]["original_message_count"]
    assert (
        transport.requests[-1]["messages"] == runtime.roles["target"]["memory"]["messages"][:count]
    )
    assert attempt["context_selection"]["removed_indices"] == []


def test_missing_old_observation_provenance_is_preserved_without_content_guessing(tmp_path):
    world, transport, policy, runtime = fixture(
        tmp_path,
        answers("single_decision_json"),
        {"action_protocol": "single_decision_json", "context_policy": "latest_observation"},
    )
    runtime.step()
    checkpoint = runtime.snapshot()
    checkpoint["roles"]["target"]["memory"].pop("observation_messages")
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")},
        {"target": ModelPolicy(policy.config, transport=transport)},
        checkpoint=checkpoint,
    )
    resumed.step()
    memory = resumed.roles["target"]["memory"]
    assert [row["index"] for row in memory["observation_messages"]] == [4]
    assert transport.requests[-1]["messages"] == memory["messages"][:5]
    selection = [row for row in events(resumed, "model_attempt") if row["stage"] == "started"][-1][
        "context_selection"
    ]
    assert selection["removed_indices"] == []
    assert selection["messages"][1]["reason"] == "unregistered_history_preserved"


def test_checkpoint_continuation_retains_all_indexed_history_and_same_scope(tmp_path):
    world, transport, policy, runtime = fixture(
        tmp_path,
        answers("single_decision_json"),
        {"action_protocol": "single_decision_json", "context_policy": "latest_observation"},
    )
    runtime.step()
    runtime.step()
    checkpoint = json.loads(json.dumps(runtime.snapshot()))
    original = copy.deepcopy(checkpoint["roles"]["target"]["memory"])
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")},
        {"target": ModelPolicy(policy.config, transport=transport)},
        checkpoint=checkpoint,
    )
    resumed.step()
    memory = resumed.roles["target"]["memory"]
    assert memory["messages"][: len(original["messages"])] == original["messages"]
    assert memory["observation_messages"][:2] == original["observation_messages"]
    assert [row["index"] for row in memory["observation_messages"]] == [1, 4, 7]
    selection = [row for row in events(resumed, "model_attempt") if row["stage"] == "started"][-1][
        "context_selection"
    ]
    assert selection["removed_indices"] == [1, 4]


def test_tool_result_with_observation_words_is_never_dropped_by_content(tmp_path):
    world, transport, _, runtime = fixture(
        tmp_path,
        answers("single_decision_json"),
        {"action_protocol": "single_decision_json", "context_policy": "latest_observation"},
    )
    written = world.session("worker", "A").call(
        "write_object",
        alias="input",
        data={
            "observation": "This is task data, not adapter provenance",
            "public_tool_result": "marker inside a real file",
        },
    )
    assert written["ok"]
    runtime.step()
    runtime.step()
    tool_message = transport.requests[-1]["messages"][2]
    assert (
        json.loads(tool_message["content"])["public_tool_result"]["result"]["data"]["observation"]
        == "This is task data, not adapter provenance"
    )


def test_offline_token_evidence_is_bound_to_selected_request_and_original_message_roots(tmp_path):
    _, transport, policy, runtime = fixture(
        tmp_path,
        answers("single_decision_json"),
        {"action_protocol": "single_decision_json", "context_policy": "latest_observation"},
    )
    original_complete = transport.complete

    def trace(request, *, timeout_seconds):
        value = original_complete(request, timeout_seconds=timeout_seconds)
        # Explicit offline byte-ID fixture, not GPU tokenizer IDs/logprobs.
        value["body"]["offline_trace"] = {
            "kind": "synthetic_utf8_byte_ids",
            "input_ids": list(json_bytes(request["messages"])),
            "request_sha256": digest(json_bytes(request)),
        }
        value["raw_body"] = json.dumps(value["body"])
        return value

    policy.transport.complete = trace
    runtime.step()
    runtime.step()
    attempt = [row for row in events(runtime, "model_attempt") if row["stage"] == "finished"][-1]
    selection = attempt["context_selection"]
    trace = attempt["response"]["body"]["offline_trace"]
    originals = runtime.roles["target"]["memory"]["messages"]
    roots = [originals[index] for index in selection["selected_indices"]]
    assert trace["input_ids"] == list(json_bytes(roots))
    assert trace["request_sha256"] == selection["request_sha256"]
    assert events(runtime, "model_response")[-1]["response"]["offline_trace"] == trace


def test_context_policy_and_provenance_errors_are_explicit():
    with pytest.raises(ValueError, match="context policy"):
        normalize_config({"context_policy": "summarize_and_guess"})
    policy = ModelPolicy({"context_policy": "latest_observation"})
    message = {"role": "assistant", "content": "actual prior output"}
    with pytest.raises(ValueError, match="observation"):
        policy._select_messages(
            {
                "messages": [message],
                "observation_messages": [{"index": 0, "sha256": digest(json_bytes(message))}],
            }
        )
    assert ADAPTER_VERSION == "model-policy-v0.12"
