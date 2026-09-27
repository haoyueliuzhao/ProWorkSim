"""Public parser controls, including actual SDK/native next-request feedback."""

import copy
import json

import pytest

from proworksim.candidate_runtime_v017 import (  # noqa: E402
    CandidateActor,
    candidate_profile,
    parse_candidate_generated,
)
from proworksim.candidate_runtime_v0151 import CandidateActor as PreviousActor  # noqa: E402
from proworksim.candidate_runtime_v015 import parse_candidate_generated as parse_previous  # noqa: E402
from proworksim.format_diagnostics import feedback_diagnostics  # noqa: E402
from proworksim.model_policy import ModelPolicy, SYSTEM as NATIVE_SYSTEM  # noqa: E402

TOOLS = [
    {
        "name": "edit",
        "description": "Edit your allowed object.",
        "parameters": {
            "type": "object",
            "properties": {"payload": {"type": "object"}, "count": {"type": "integer"}},
            "required": ["payload"],
            "additionalProperties": False,
        },
    }
]
REQUEST = {
    "messages": [{"role": "user", "content": "Use your legal evidence."}],
    "tools": [{"type": "function", "function": x} for x in TOOLS],
}
BAD = '<tool_call><function=edit><parameter=payload>{"incomplete":</parameter></function></tool_call><|im_end|>'
CONFIG = {
    "model": "diagnostic-fixture-not-model",
    "api_key_env": None,
    "base_url": "http://127.0.0.1",
    "backend_id": "explicit_cpu_fixture",
    "retry": {"max_attempts": 1, "backoff_seconds": []},
    "format_error_policy": "format_feedback_continue",
    "budget": {"max_cost_usd": 50},
}


def test_native_error_is_located_in_public_parameter_without_returning_its_value():
    message, diagnostic = parse_candidate_generated(BAD, REQUEST)
    assert "tool_calls" not in message
    failure = diagnostic["failure"]
    assert failure["field_path"] == ["payload"]
    assert failure["schema_path"] == ["properties", "payload", "type"]
    assert failure["expected_type"] == "object"
    assert failure["observed_type"] is None
    assert failure["position"] == {
        "offset": 14,
        "line": 1,
        "column": 15,
        "scope": "the parsed parameter text",
    }
    assert "incomplete" not in json.dumps(diagnostic)
    _, wrong_type = parse_candidate_generated(
        BAD.replace('{"incomplete":', '"not-an-object"'), REQUEST
    )
    assert wrong_type["failure"]["expected_type"] == "object"
    assert wrong_type["failure"]["observed_type"] == "string"
    assert "not-an-object" not in json.dumps(wrong_type)
    legacy = feedback_diagnostics(
        {"protocol_parse_error": "unknown parser rejection"},
        {"stage": "adapter_structure", "reason": "failed"},
        adapter="test",
    )
    assert legacy["native_parser"]["failure"]["field_path"] is None
    assert legacy["native_parser"]["failure"]["expected_type"] is None


def test_diagnostics_do_not_move_existing_parser_acceptance_boundary():
    examples = [
        BAD,
        "<tool_call><function=edit></function></tool_call>",
        "<tool_call><function=unknown><parameter=x>001</parameter></function></tool_call>",
        '<tool_call><function=edit><parameter=payload>{"any":"value"}</parameter></function></tool_call>',
        "<tool_call><function=edit><parameter=count>true</parameter></function></tool_call>",
        "<tool_call><function=edit><parameter=payload>[]</parameter></function></tool_call>",
        "<tool_call><function=edit></function></tool_call>" * 2,
        '<tool_call><function=edit><parameter=payload>{"x":1e309}</parameter></function></tool_call>',
        '<tool_call><function=edit><parameter=payload>{"x":NaN}</parameter></function></tool_call>',
    ]
    for raw in examples:
        old, old_error = parse_previous(raw, REQUEST)
        new, new_error = parse_candidate_generated(raw, REQUEST)
        assert (old_error is None) == (new_error is None)
        if old_error is None:
            for message in (old, new):
                for call in message.get("tool_calls", []):
                    call.pop("id")
            assert old == new


def test_new_profile_uses_unchanged_loader_before_new_identity(monkeypatch, tmp_path):
    captured = {}

    def previous_init(self, *args, inference_profile, **kwargs):
        captured["owner_profile"] = inference_profile

    def previous_loader(cls, model_path, *, manifest, profile, output, recipe):
        captured["loader_profile"] = copy.deepcopy(profile)
        profile["actual_device_map"] = {"model.layers.0": 0, "model.layers.63": 3}
        return cls(object(), object(), inference_profile=profile)

    monkeypatch.setattr(PreviousActor, "__init__", previous_init)
    monkeypatch.setattr(PreviousActor, "from_candidate", classmethod(previous_loader))
    profile = candidate_profile("qwen3.8-27b", devices=4)
    CandidateActor.from_candidate(
        "unused", manifest="unused", profile=profile, output=tmp_path, recipe={}
    )
    assert captured["loader_profile"]["version"] == "candidate-runtime-v0.15.1"
    assert captured["loader_profile"]["devices"] == 4
    assert captured["loader_profile"]["dtype"] == "float32"
    assert captured["owner_profile"]["version"] == "candidate-runtime-v0.17"
    assert captured["owner_profile"]["actual_device_map"] == {
        "model.layers.0": 0,
        "model.layers.63": 3,
    }
    assert captured["owner_profile"]["parser_contract"] == profile["parser_contract"]


class FixtureTransport:
    def __init__(self):
        self.requests = []
        message, diagnostics = parse_candidate_generated(BAD, REQUEST)
        self.bad_body = {
            "id": "diagnostic-fixture-response",
            "object": "chat.completion",
            "created": 0,
            "model": CONFIG["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "raw_generated_text": BAD,
            "protocol_parse_error": diagnostics,
            "token_trace": {
                "fixture_only": True,
                "output_ids": [201, 202],
                "raw_output_ids": [201, 202],
            },
        }

    def complete(self, request, **kwargs):
        self.requests.append(copy.deepcopy(request))
        if len(self.requests) == 1:
            body = copy.deepcopy(self.bad_body)
        else:
            body = {
                "id": "fixture-done",
                "object": "chat.completion",
                "created": 0,
                "model": CONFIG["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "id": "fixture-done-call",
                                    "function": {
                                        "name": "staff_done",
                                        "arguments": json.dumps({"reason": "fixture complete"}),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            }
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}


def feedback(request):
    for message in request["messages"]:
        if message["role"] == "user":
            try:
                value = json.loads(message["content"])
            except (ValueError, TypeError):
                continue
            if "public_format_feedback" in value:
                return value["public_format_feedback"]
    raise AssertionError("No actual public feedback in next model request")


def test_both_real_interfaces_deliver_two_stages_in_actual_next_request(tmp_path):
    pytest.importorskip("openhands.sdk")
    from proworksim.harness_sdk import HarnessWorker, SYSTEM as SDK_SYSTEM

    assert "choose sources automatically" not in SDK_SYSTEM
    for system in [SDK_SYSTEM, NATIVE_SYSTEM]:
        assert "Autonomously choose permitted sources" in system
        assert "evidence you have actually obtained" in system
    native_transport = FixtureTransport()
    native_events = []
    native = ModelPolicy(CONFIG, transport=native_transport)
    native.bind_event_sink(lambda kind, payload: native_events.append((kind, payload)))
    context = {
        "run_id": "native",
        "worker_id": "worker",
        "opportunity_id": "1",
        "tools": TOOLS,
        "observation": {"task": "private role"},
        "memory": {},
    }
    first = native.decide(context)
    assert first["kind"] == "protocol_rejection" and len(native_transport.requests) == 1
    native.decide({**context, "opportunity_id": "2", "memory": first["memory"]})
    sdk_transport = FixtureTransport()
    sdk_events = []
    executed = []
    sdk = HarnessWorker(
        "worker",
        TOOLS,
        CONFIG,
        sdk_transport,
        lambda *args: executed.append(args) or {"ok": True, "world_effect": False},
        event_sink=lambda kind, payload: sdk_events.append((kind, payload)),
        directory=tmp_path / "sdk",
    )
    rejected = sdk.step({"task": "private role"}, {"run_id": "sdk", "opportunity_id": "1"})
    assert (
        rejected["kind"] == "protocol_rejection"
        and len(sdk_transport.requests) == 1
        and executed == []
    )
    sdk.step({"task": "private role"}, {"run_id": "sdk", "opportunity_id": "2"})
    diagnostics = [
        feedback(t.requests[1])["parse_diagnostics"] for t in [native_transport, sdk_transport]
    ]
    assert (
        diagnostics[0]["native_parser"]
        == diagnostics[1]["native_parser"]
        == native_transport.bad_body["protocol_parse_error"]
    )
    assert (
        diagnostics[0]["adapter_parser"]["failure"] == diagnostics[1]["adapter_parser"]["failure"]
    )
    assert diagnostics[0]["adapter_parser"]["failure"]["stage"] == "adapter_json_control"
    assert diagnostics[0]["native_parser"]["failure"]["field_path"] == ["payload"]
    for events, transport in [(native_events, native_transport), (sdk_events, sdk_transport)]:
        archived = next(p["response"] for k, p in events if k == "model_response")
        assert archived == transport.bad_body
    sdk.close()
