"""D0 uses simulated model outputs against real public world interfaces."""

import copy
import json

import pytest

from proworksim.model_policy import ModelPolicy, normalize_config
from proworksim.scenarios import build_scenario, run_scenario
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import digest, json_bytes
from test_model_policy_v11 import SimulatedTransport, call, events, fixture, response
from test_scenarios_v10 import spec


CONTINUE = {
    "action_protocol": "single_decision_json",
    "format_error_policy": "format_feedback_continue",
    "context_policy": "latest_observation",
}
BAD = response(content='{"kind":"read_object","arguments":{"alias":"input"}}')
READ = response(content='{"kind":"act","action":"read_object","arguments":{"alias":"input"}}')
DONE = response(content='{"kind":"done","reason":"Stop after real observation"}')


def test_failed_decision_is_charged_preserved_and_resumed_only_on_next_opportunity(tmp_path):
    world, transport, policy, runtime = fixture(tmp_path, [BAD, READ, DONE], CONTINUE)
    before = copy.deepcopy(world.store.load())
    failed = runtime.step()
    assert failed["status"] == "model_format_feedback"
    assert failed["decision_consumed"] and not failed["action_performed"]
    assert world.store.load() == before and runtime.actions == 0
    assert len(transport.requests) == 1
    memory = runtime.roles["target"]["memory"]
    assert memory["messages"][2] == BAD["body"]["choices"][0]["message"]
    assert "terminal_error" not in memory and "pending_tool" not in memory
    assert memory["meter"]["decisions"] == memory["meter"]["http_attempts"] == 1
    assert memory["meter"]["reported_total_tokens"] == 120
    assert events(runtime, "model_response")[0]["response"] == BAD["body"]
    assert not events(runtime, "model_action_link")
    checkpoint = json.loads(json.dumps(runtime.snapshot()))
    resumed = StaffRuntime(
        {"target": world.session("worker", "A")},
        {"target": ModelPolicy(policy.config, transport=transport)},
        checkpoint=checkpoint,
    )
    outcome = resumed.step()
    assert outcome["action_performed"] and outcome["response"]["ok"]
    second = transport.requests[1]
    feedback = [
        json.loads(m["content"])["public_format_feedback"]
        for m in second["messages"]
        if m["role"] == "user" and "public_format_feedback" in json.loads(m["content"])
    ]
    assert len(feedback) == 1 and feedback[0]["world_action_executed"] is False
    assert "private-B" not in json.dumps(second)
    assert events(resumed, "model_action_link")[0]["model_call_id"] != feedback[0]["model_call_id"]
    assert resumed.roles["target"]["memory"]["format_errors"] == {"total": 1, "consecutive": 0}
    assert resumed.step()["status"] == "completed"
    assert len(transport.requests) == 3 and resumed.actions == 1


def test_runtime_run_does_not_treat_consumed_format_decision_as_idle(tmp_path):
    _, transport, _, runtime = fixture(tmp_path, [BAD, READ, DONE], CONTINUE)
    outcome = runtime.run(max_actions=2, max_opportunities=5)
    assert outcome["status"] == "completed"
    assert len(transport.requests) == 3 and runtime.actions == 1


def test_scenario_loop_does_not_stop_before_later_real_action(tmp_path):
    deployment = build_scenario(spec("report-direct"), tmp_path / "scenario")
    transport = SimulatedTransport(
        [
            BAD,
            response(
                content='{"kind":"act","action":"read_object","arguments":{"alias":"dataset"}}'
            ),
            DONE,
        ]
    )

    class WaitPolicy:
        def decide(self, context):
            return {"kind": "wait", "reason": "No pending submitted work", "memory": {}}

    runtime = StaffRuntime(
        {
            "author": deployment.world.session("author", "REPORT"),
            "report_reviewer": deployment.world.session("reviewer", "REPORT"),
        },
        {"author": ModelPolicy(CONTINUE, transport=transport), "report_reviewer": WaitPolicy()},
    )
    result = run_scenario(deployment, runtime=runtime, max_opportunities=8)
    assert result["actions"] == 1 and len(transport.requests) == 3
    assert result["status"] == "worker_waiting"
    assert result["outcomes"][0]["status"] == "model_format_feedback"


@pytest.mark.parametrize(
    "limit,answers,expected_calls",
    [
        ({"max_total": 4, "max_consecutive": 2}, [BAD, BAD], 2),
        ({"max_total": 3, "max_consecutive": 2}, [BAD, READ, BAD, READ, BAD], 5),
    ],
)
def test_format_limits_are_cumulative_and_consecutive_not_resampling(
    tmp_path, limit, answers, expected_calls
):
    _, transport, _, runtime = fixture(tmp_path, answers, {**CONTINUE, "format_limits": limit})
    results = [runtime.step() for _ in answers]
    assert results[-1]["status"] == "model_format_error"
    assert len(transport.requests) == expected_calls
    terminal = copy.deepcopy(runtime.roles["target"]["memory"]["terminal_error"])
    assert terminal["details"]["reached_limits"]
    assert runtime.step()["status"] == "model_format_error"
    assert len(transport.requests) == expected_calls
    assert runtime.roles["target"]["memory"]["terminal_error"] == terminal
    assert len(events(runtime, "model_response")) == expected_calls


@pytest.mark.parametrize("cap", ["max_decisions", "max_http_attempts"])
def test_format_feedback_does_not_bypass_existing_model_budgets(tmp_path, cap):
    _, transport, _, runtime = fixture(tmp_path, [BAD], {**CONTINUE, "budget": {cap: 1}})
    assert runtime.step()["status"] == "model_format_feedback"
    assert runtime.step()["status"] == "model_budget_exhausted"
    assert len(transport.requests) == 1
    assert runtime.roles["target"]["memory"]["meter"]["reported_total_tokens"] == 120


def test_valid_wrong_world_action_is_not_a_format_error_or_automatic_repair(tmp_path):
    wrong = response(content='{"kind":"act","action":"unknown_tool","arguments":{}}')
    _, transport, _, runtime = fixture(tmp_path, [BAD, wrong, DONE], CONTINUE)
    runtime.step()
    result = runtime.step()
    assert result["action_performed"] and result["response"]["ok"] is False
    assert result["status"] == "capability_gap"
    assert runtime.roles["target"]["memory"]["format_errors"] == {"total": 1, "consecutive": 0}
    assert len(transport.requests) == 2
    runtime.step()
    actual = [
        json.loads(m["content"]) for m in transport.requests[-1]["messages"] if m["role"] == "user"
    ]
    assert any(x.get("public_tool_result") == result["response"] for x in actual)


@pytest.mark.parametrize("protocol", ["native_tools", "single_decision_json"])
def test_rejected_native_calls_are_quoted_with_wire_provenance_not_fake_results(tmp_path, protocol):
    bad = response(call(identity="first"), call(identity="second"))
    _, transport, _, runtime = fixture(
        tmp_path, [bad, DONE], {**CONTINUE, "action_protocol": protocol}
    )
    runtime.step()
    original = copy.deepcopy(runtime.roles["target"]["memory"]["messages"][2])
    assert runtime.step()["status"] == "completed"
    request = transport.requests[-1]
    assert not any(m["role"] == "tool" or m.get("tool_calls") for m in request["messages"])
    quoted = request["messages"][1]
    assert json.loads(quoted["content"]) == {"rejected_assistant_response": original}
    memory = runtime.roles["target"]["memory"]
    assert memory["messages"][2] == original
    start = [e for e in events(runtime, "model_attempt") if e["stage"] == "started"][-1]
    projection = start["context_selection"]["messages"][2]
    assert projection["projection"] == "rejected_assistant_as_data"
    assert projection["sha256"] == digest(json_bytes(original))
    assert projection["wire_sha256"] == digest(json_bytes(quoted))
    assert start["context_selection"]["selected_messages_sha256"] == digest(
        json_bytes(request["messages"])
    )
    assert runtime.actions == 0 and len(transport.requests) == 2


def test_rejected_native_bad_arguments_are_not_parsed_into_a_correct_tool(tmp_path):
    badcall = call()
    badcall["function"]["arguments"] = "{"
    _, transport, _, runtime = fixture(
        tmp_path, [response(badcall), DONE], {**CONTINUE, "action_protocol": "native_tools"}
    )
    assert runtime.step()["status"] == "model_format_feedback"
    assert runtime.step()["status"] == "completed"
    assert runtime.actions == 0
    assert "{" in transport.requests[-1]["messages"][1]["content"]


def test_length_failure_is_retained_and_bounded_like_other_generated_format_errors(tmp_path):
    bad = copy.deepcopy(READ)
    bad["body"]["choices"][0]["finish_reason"] = "length"
    _, transport, _, runtime = fixture(tmp_path, [bad, DONE], CONTINUE)
    assert runtime.step()["status"] == "model_format_feedback"
    assert runtime.actions == 0
    assert events(runtime, "model_format_feedback")[0]["feedback"]["finish_reason"] == "length"
    runtime.step()
    assert len(transport.requests) == 2


def test_service_or_unrecoverable_envelope_error_is_still_terminal(tmp_path):
    bad = response()
    bad["body"]["choices"] = []
    _, transport, _, runtime = fixture(tmp_path, [bad], CONTINUE)
    assert runtime.step()["status"] == "model_format_error"
    assert not events(runtime, "model_format_feedback")
    assert runtime.step()["status"] == "model_format_error"
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "config",
    [
        {"format_error_policy": "silently_correct"},
        {"format_limits": {"max_total": 0}},
        {"format_limits": {"max_consecutive": True}},
        {"format_limits": {"unbounded": 1}},
    ],
)
def test_invalid_feedback_configuration_is_rejected(config):
    with pytest.raises(ValueError):
        normalize_config(config)
