"""Real optional SDK machinery with declared deterministic CPU transport fixtures."""

import copy
import json

import pytest

pytest.importorskip("openhands.sdk")

from proworksim.harness_sdk import HarnessWorker  # noqa: E402
from proworksim.staff_runtime import PolicyBoundaryError  # noqa: E402

TOOLS = [
    {
        "name": "write_note",
        "description": "Save only your role's private note.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    }
]
CONFIG = {
    "model": "cpu-fixture-not-a-model",
    "api_key_env": None,
    "base_url": "http://127.0.0.1",
    "backend_id": "explicit_test_fixture",
    "retry": {"max_attempts": 1, "backoff_seconds": []},
    "budget": {"max_cost_usd": 50},
    "weight_identity": {"step": 0, "policy_version": "fixture-policy-0"},
    "model_revision": "fixture-policy-0",
}


class FixtureTransport:
    def __init__(self, calls):
        self.calls, self.requests = list(calls), []

    def complete(self, request, **kwargs):
        self.requests.append(copy.deepcopy(request))
        call = self.calls.pop(0)
        body = {
            "id": f"fixture-response-{len(self.requests)}",
            "model": CONFIG["model"],
            "object": "chat.completion",
            "created": 0,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {"role": "assistant", "content": None, "tool_calls": call},
                }
            ],
            "usage": {"prompt_tokens": 17, "completion_tokens": 3, "total_tokens": 20},
            # Explicit fixture-only sentinels; never admissible model behavior.
            "token_trace": {
                "input_ids": [101, 102],
                "output_ids": [201, 202],
                "behavior_logprobs": [-0.1, -0.2],
                "fixture_only": True,
            },
        }
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def call(name, arguments, identifier="fixture-call"):
    return [
        {
            "id": identifier,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
    ]


def worker(tmp_path, role, transport, execute, sink=None):
    return HarnessWorker(
        role, TOOLS, CONFIG, transport, execute, event_sink=sink, directory=tmp_path / role
    )


def test_actual_sdk_one_decision_error_feedback_pause_roles_and_refresh(tmp_path):
    a_transport = FixtureTransport(
        [
            call("write_note", {"text": "first"}),
            call("write_note", {"text": "retry-after-error"}, "fixture-second"),
        ]
    )
    b_transport = FixtureTransport([call("write_note", {"text": "private-B"})])
    actual, events = [], []

    def execute_a(name, args, association):
        actual.append((name, args, association))
        return {"ok": False, "error": "real fixture denial"}

    a = worker(
        tmp_path, "A", a_transport, execute_a, lambda kind, payload: events.append((kind, payload))
    )
    b = worker(tmp_path, "B", b_transport, lambda *_: {"ok": True})
    first = a.step({"role_data": "private-A"}, {"run_id": "cpu", "opportunity_id": "1"})
    assert first["executed"] and len(a_transport.requests) == len(actual) == 1
    assert str(a.conversation.state.execution_status.value) == "paused"
    assert b.meter["decisions"] == 0
    b.step({"role_data": "private-B"}, {"run_id": "cpu", "opportunity_id": "2"})
    a.refresh_transport(a_transport, {"step": 1, "policy_version": "fixture-policy-1"})
    a.step({"role_data": "private-A"}, {"run_id": "cpu", "opportunity_id": "3"})
    assert len(a_transport.requests) == len(actual) == 2
    assert "real fixture denial" in json.dumps(a_transport.requests[1])
    assert "private-B" not in json.dumps(a_transport.requests)
    assert "private-A" not in json.dumps(b_transport.requests)
    assert actual[1][2]["weight_identity"] == {"step": 1, "policy_version": "fixture-policy-1"}
    assert actual[0][2]["model_revision"] == "fixture-policy-0"
    assert actual[1][2]["model_revision"] == "fixture-policy-1"
    assert a.config["model_revision"] == a.snapshot()["model_revision"] == "fixture-policy-1"
    after_refresh = [
        payload
        for kind, payload in events
        if kind == "model_attempt" and payload["stage"] == "finished"
    ][-1]
    assert after_refresh["model_revision"] == "fixture-policy-1"
    sdk_events = a.snapshot()["sdk_events"]
    assert sum(event["kind"] == "ActionEvent" for event in sdk_events) == 2
    assert sum(event["kind"] == "ObservationEvent" for event in sdk_events) == 2
    assert {tool["function"]["name"] for tool in a_transport.requests[0]["tools"]} == {
        "write_note",
        "staff_wait",
        "staff_done",
    }
    response = next(payload["response"] for kind, payload in events if kind == "model_response")
    attempt = next(
        payload
        for kind, payload in events
        if kind == "model_attempt" and payload["stage"] == "finished"
    )
    assert response == attempt["response"]["body"]
    assert response["token_trace"]["input_ids"] == [101, 102]
    assert a.snapshot()["identity_epoch"] == 1
    a.close()
    b.close()


@pytest.mark.parametrize(
    "calls",
    [
        call("write_note", {"text": "A"}) + call("write_note", {"text": "B"}, "second"),
        call("BashTool", {"command": "pwd"}),
        call("write_note", {"text": 123}),
        call("write_note", {"text": "A", "summary": "SDK auto-removes this"}),
    ],
)
def test_no_automatic_sdk_repair_multiple_call_or_unmanaged_execution(tmp_path, calls):
    transport = FixtureTransport([calls])
    actual = []
    w = worker(tmp_path, "A", transport, lambda *args: actual.append(args))
    with pytest.raises(PolicyBoundaryError, match="schema|Exactly one|managed gateway"):
        w.step({}, {"run_id": "cpu", "opportunity_id": "1"})
    assert len(transport.requests) == 1
    assert actual == []
    w.close()


def test_context_projection_keeps_four_exact_complete_rounds_and_latest_observation():
    from proworksim.harness_sdk import select_context

    messages = [{"role": "system", "content": "fixed"}]
    observations = []
    for index in range(7):
        text = json.dumps({"observation": index})
        observations.append(text)
        messages.append({"role": "user", "content": text})
        if index < 6:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": call("write_note", {"text": str(index)}, str(index)),
                }
            )
            messages.append(
                {"role": "tool", "tool_call_id": str(index), "content": json.dumps({"ok": True})}
            )
    original = copy.deepcopy(messages)
    selected, audit = select_context(messages, observations, "latest_observation_last4_tool_rounds")
    assert messages == original
    assert len(selected) == 10
    assert sum(m["role"] == "assistant" for m in selected) == 4
    assert selected[-1] == messages[-1]
    assert selected == [original[i] for i in audit["selected_indices"]]
    with pytest.raises(RuntimeError, match="association|orphan|complete"):
        select_context(
            messages[:-2] + messages[-1:], observations, "latest_observation_last4_tool_rounds"
        )


def test_format_feedback_is_next_opportunity_input_without_repaired_action(tmp_path):
    transport = FixtureTransport(
        [
            call("write_note", {"text": 123}),
            call("write_note", {"text": "model-recovered"}, "recovered"),
        ]
    )
    config = {**CONFIG, "format_error_policy": "format_feedback_continue"}
    actual, events = [], []
    w = HarnessWorker(
        "A",
        TOOLS,
        config,
        transport,
        lambda *args: actual.append(args) or {"ok": True},
        event_sink=lambda kind, payload: events.append((kind, payload)),
        directory=tmp_path / "A",
    )
    rejected = w.step({"step": 1}, {"run_id": "cpu", "opportunity_id": "1"})
    assert rejected["kind"] == "protocol_rejection"
    assert not rejected["executed"] and len(transport.requests) == 1 and actual == []
    done = w.step({"step": 2}, {"run_id": "cpu", "opportunity_id": "2"})
    assert done["executed"] and len(transport.requests) == 2 and len(actual) == 1
    assert "public_format_feedback" in json.dumps(transport.requests[1])
    assert w.format_errors == {"total": 1, "consecutive": 0}
    assert len([row for row in w.snapshot()["sdk_events"] if row["kind"] == "ActionEvent"]) == 1
    assert len([row for kind, row in events if kind == "model_response"]) == 2
    w.close()


def test_two_consecutive_format_failures_stop_without_model_retry(tmp_path):
    transport = FixtureTransport([call("unknown", {}), call("unknown", {}, "second")])
    config = {**CONFIG, "format_error_policy": "format_feedback_continue"}
    actual = []
    w = HarnessWorker(
        "A", TOOLS, config, transport, lambda *args: actual.append(args), directory=tmp_path / "A"
    )
    assert w.step({}, {"run_id": "cpu", "opportunity_id": "1"})["kind"] == "protocol_rejection"
    with pytest.raises(PolicyBoundaryError, match="limit"):
        w.step({}, {"run_id": "cpu", "opportunity_id": "2"})
    assert len(transport.requests) == 2 and actual == []
    assert w.format_errors == {"total": 2, "consecutive": 2}
    w.close()


def test_exact_json_wait_is_sdk_message_and_direct_control_executor(tmp_path):
    class ControlTransport(FixtureTransport):
        def complete(self, request, **kwargs):
            response = super().complete(request, **kwargs)
            if len(self.requests) == 1:
                response["body"]["choices"][0]["message"] = {
                    "role": "assistant",
                    "content": json.dumps({"kind": "wait", "reason": "wait-for-colleague"}),
                }
                response["body"]["choices"][0]["finish_reason"] = "stop"
                response["raw_body"] = json.dumps(response["body"])
            return response

    transport = ControlTransport([[], call("write_note", {"text": "after-wait"}, "afterwait")])
    actual = []
    w = worker(tmp_path, "A", transport, lambda *args: actual.append(args) or {"ok": True})
    result = w.step({}, {"run_id": "cpu", "opportunity_id": "1"})
    assert result["kind"] == "wait" and result["executed"] and len(actual) == 1
    assert actual[0][0] == "staff_wait"
    w.step({}, {"run_id": "cpu", "opportunity_id": "2"})
    assert len(actual) == 2 and len(transport.requests) == 2
    assert "wait-for-colleague" in json.dumps(transport.requests[1])
    assert not any(m["role"] == "tool" for m in transport.requests[1]["messages"])
    assert len([e for e in w.snapshot()["sdk_events"] if e["kind"] == "ActionEvent"]) == 1
    w.close()
