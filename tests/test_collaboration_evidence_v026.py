"""Evidence-layer regressions: inherited origin, denied generation, time direction."""

import json

from scripts.collaboration_evidence_v026 import (
    entity_matches,
    exposure,
    extract_episode,
    ref_matches,
    request_nodes,
)


def test_reference_metadata_is_not_content_and_assistant_is_not_delivery():
    reference = {"object_id": "artifact", "version_id": "v2"}
    request = {
        "messages": [
            {
                "role": "assistant",
                "content": json.dumps({"issue_id": "invented", "description": "claim"}),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"objects": [{"object_id": "artifact", "current_version": "v2"}]}
                ),
            },
        ]
    }
    values = list(request_nodes(request))
    assert any(ref_matches(reference)(v) for _, v in values)
    assert not any(ref_matches(reference, content=True)(v) for _, v in values)
    assert not any(entity_matches("issue_id", "invented")(v) for _, v in values)


def test_earlier_changes_cannot_use_later_feedback_and_inherited_is_not_current():
    sid = "work-submission-1"
    issue = {"issue_id": "issue-1", "description": "Correct the count", "active_at_creation": True}

    def action(seq, actor, name, arguments, result):
        return {
            "sequence": seq,
            "kind": "tool_call",
            "worker_id": actor,
            "payload": {
                "action": name,
                "arguments": arguments,
                "response": {"ok": True, "result": result},
            },
        }

    def start(seq, actor, call):
        return {
            "sequence": seq,
            "kind": "model_call",
            "worker_id": actor,
            "payload": {"stage": "started", "call_id": call},
        }

    events = [
        start(2, "reviewer", "r0"),
        action(145, "implementer", "write_object", {}, {"object_id": "code", "version_id": "v3"}),
        action(168, "implementer", "write_object", {}, {"object_id": "code", "version_id": "v4"}),
        action(
            179,
            "reviewer",
            "raise_issue",
            {"submission_id": sid, "description": issue["description"]},
            issue,
        ),
        start(185, "implementer", "i0"),
    ]
    projection = {
        "member_views": {
            "reviewer": {
                "decisions": [
                    {
                        "call_id": "r0",
                        "decision_index": 0,
                        "actual_input": {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": json.dumps({"latest_submission_id": sid}),
                                }
                            ]
                        },
                        "actual_response": {"choices": []},
                        "generation_status": "observed_completion",
                    }
                ]
            },
            "implementer": {
                "decisions": [
                    {
                        "call_id": "i0",
                        "decision_index": 9,
                        "actual_input": {
                            "messages": [
                                {
                                    "role": "user",
                                    "content": json.dumps({"issues": {"issue-1": issue}}),
                                }
                            ]
                        },
                        "actual_response": None,
                        "generation_status": "not_started_direct_context_limit",
                    }
                ]
            },
        },
        "method_mapping": {
            "status": "unmapped",
            "class_id": None,
            "evidence": {"facts": {"judgments": [{"sequence": 179, "valid": True}]}},
        },
        "assessment": {"reward": 0.0, "completed": False},
        "work_validity": {"value": False},
    }
    initial = {
        "work_items": {"work": {"submissions": [{"submission_id": sid, "actor_id": "implementer"}]}}
    }
    result = extract_episode({"events": events}, projection, initial, initial, slot_id="fixture")
    inherited = next(r for r in result["records"] if r["kind"] == "fixed_submission")
    assert inherited["origin"] == "inherited_preparation"
    assert inherited["current_model_action"] is False
    assert (
        inherited["recipient_inputs"]["reviewer"]["identity_or_metadata"]["first_request_input"][
            "sequence"
        ]
        == 2
    )
    feedback = next(r for r in result["records"] if r["kind"] == "issue")
    observed = feedback["recipient_inputs"]["implementer"]["content"]
    assert observed["first_request_input"]["sequence"] == 185
    assert observed["first_input_with_generation"] is None
    assert [a["sequence"] for a in feedback["prior_implementation_changes"]] == [145, 168]
    assert feedback["execution_use"] == []
    assert feedback["later_change_candidates"] == []
    assert feedback["reverification"] == []
    assert result["original_result"]["V"] is False


def test_late_success_is_distinct_from_first_rejected_request():
    base = {
        "member_id": "recipient",
        "call_id": "first",
        "decision_index": 0,
        "input_event_sequence": None,
        "projection_pointer": "#/decisions/0",
        "generation_status": "not_started_direct_context_limit",
        "nodes": [("/messages/1/content", {"issue_id": "i"})],
    }
    decisions = [
        {**base, "sequence": 10, "generated": False},
        {**base, "sequence": 20, "generated": True, "call_id": "second"},
    ]
    observed = exposure(decisions, "recipient", 5, entity_matches("issue_id", "i"))
    assert observed["first_request_input"]["sequence"] == 10
    assert observed["first_input_with_generation"]["sequence"] == 20


def test_repeated_idempotent_handoff_does_not_create_second_delivery():
    handoff = {
        "handoff_id": "h",
        "sender": "provider",
        "recipients": ["implementer"],
        "reference": {"object_id": "basis", "version_id": "v1"},
        "body": "policy",
        "event_id": "delivery",
    }
    events = [
        {
            "sequence": seq,
            "kind": "tool_call",
            "worker_id": "provider",
            "payload": {
                "action": "handoff_information",
                "arguments": {},
                "response": {"ok": True, "result": {"handoff_id": "h", "created": seq == 1}},
            },
        }
        for seq in (1, 2)
    ]
    projection = {
        "member_views": {"provider": {"decisions": []}, "implementer": {"decisions": []}},
        "method_mapping": {"status": "unmapped"},
        "assessment": {"reward": 0.0, "completed": False},
        "work_validity": {"value": False},
    }
    result = extract_episode(
        {"events": events}, projection, {}, {"handoffs": {"h": handoff}}, slot_id="repeat"
    )
    assert len(result["records"]) == 1
    assert result["records"][0]["send_or_write"]["sequence"] == 1
    assert result["communication_attempts_without_new_evidence"][0]["sequence"] == 2
    assert ref_matches({"object_id": "a", "version_id": "v2"})({"a": {"versions": ["v1", "v2"]}})
    assert not ref_matches({"object_id": "a", "version_id": "v2"}, True)(
        {"a": {"versions": ["v1", "v2"]}}
    )
