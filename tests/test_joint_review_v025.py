"""Small export-only fixture: exact role inputs, failed boundaries and escaped text."""

import copy

from proworksim.storage import digest, json_bytes
from scripts.export_joint_review_v025 import (
    extract_review,
    reconstruct_input,
    render_episode_html,
)


def fixture():
    tools = [
        {
            "type": "function",
            "function": {"name": "read_material", "parameters": {"type": "object"}},
        }
    ]
    shared = {"role": "system", "content": "Shared public instructions."}
    provider = {
        "model": "fixture",
        "messages": [shared, {"role": "user", "content": "provider-private-only"}],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 2,
        "temperature": 0.7,
        "stream": False,
    }
    implementer = {
        "model": "fixture",
        "messages": [shared, {"role": "user", "content": "implementer-private-only"}],
        "tools": tools,
        "tool_choice": {"type": "function", "function": {"name": "read_material"}},
        "max_tokens": 2,
        "temperature": 0.7,
        "stream": False,
    }
    # Absence versus an explicit empty array must also survive reconstruction.
    stopped = {"model": "fixture", "messages": [], "tool_choice": "auto", "max_tokens": 2}
    dangerous = '</script><img src=x onerror=alert("fixture-unsafe")> & raw'

    def response(content):
        return {
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "raw_generated_text": content,
            "protocol_parse_error": None,
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
        }

    responses = {"provider": response("provider actual output"), "implementer": response(dangerous)}
    events = []
    views = {}
    for role, request, seq in [("provider", provider, 1), ("implementer", implementer, 11)]:
        # Same call_id across roles deliberately tests role-scoped association.
        cid = "same-call-id"
        action = {
            "action": "read_material",
            "arguments": {"private_role": role},
            "model_call_id": cid,
            "response": {
                "ok": role == "provider",
                "result": {"role": role} if role == "provider" else None,
                "error": None if role == "provider" else {"code": "access_denied"},
            },
        }
        events += [
            {
                "sequence": seq,
                "kind": "model_call",
                "worker_id": role,
                "payload": {"stage": "started", "call_id": cid},
            },
            {
                "sequence": seq + 1,
                "kind": "model_attempt",
                "worker_id": role,
                "payload": {
                    "stage": "finished",
                    "status": "success",
                    "call_id": cid,
                    "request": request,
                    "response": {"http_status": 200, "body": responses[role]},
                },
            },
            {
                "sequence": seq + 2,
                "kind": "model_response",
                "worker_id": role,
                "payload": {"call_id": cid, "response": responses[role]},
            },
            {"sequence": seq + 3, "kind": "tool_call", "worker_id": role, "payload": action},
        ]
        views[role] = {
            "member_id": role,
            "decisions": [
                {
                    "member_id": role,
                    "call_id": cid,
                    "decision_index": 0,
                    "opportunity_id": role + "-op-0",
                    "actual_input": request,
                    "actual_response": responses[role],
                    "input_sha256": digest(json_bytes(request)),
                    "response_sha256": digest(json_bytes(responses[role])),
                    "input_event_sequence": seq + 1,
                    "response_event_sequence": seq + 2,
                    "generation_status": "observed_completion",
                    "actor_required": True,
                    "actor_trainable": True,
                    "semantic_recoverable": True,
                    "diagnostics": [],
                    "world_actions": [action],
                    "tokens": {"input_ids": [1, 2], "output_ids": [3, 4]},
                }
            ],
            "diagnostics": [],
            "own_action_count": 1,
            "own_action_tokens": 2,
            "complete_actor_trajectory": True,
            "complete_semantic_trajectory": True,
        }
    backend = {
        "http_status": 400,
        "body": {
            "transport_kind": "resident_direct",
            "generation_started": False,
            "error": {
                "code": "context_length_exceeded",
                "prompt_tokens": 19,
                "requested_output": 2,
                "context_limit": 8,
            },
        },
    }
    views["implementer"]["decisions"].append(
        {
            "member_id": "implementer",
            "call_id": "no-generation",
            "decision_index": 1,
            "opportunity_id": "implementer-op-1",
            "actual_input": stopped,
            "input_sha256": digest(json_bytes(stopped)),
            "actual_response": None,
            "tokens": None,
            "generation_status": "not_started_direct_context_limit",
            "actor_required": False,
            "actor_trainable": False,
            "semantic_recoverable": False,
            "diagnostics": ["known_direct_no_generation_context_limit"],
            "world_actions": [],
            "non_generation_response": backend,
        }
    )
    events += [
        {
            "sequence": 21,
            "kind": "model_call",
            "worker_id": "implementer",
            "payload": {"stage": "started", "call_id": "no-generation"},
        },
        {
            "sequence": 22,
            "kind": "model_attempt",
            "worker_id": "implementer",
            "payload": {
                "stage": "finished",
                "status": "backend_context_limit",
                "call_id": "no-generation",
                "request": stopped,
                "response": backend,
            },
        },
        {
            "sequence": 23,
            "kind": "model_boundary_error",
            "worker_id": "implementer",
            "payload": {
                "status": "model_budget_exhausted",
                "model_call_id": "no-generation",
                "backend_error": backend["body"]["error"],
            },
        },
        {
            "sequence": 24,
            "kind": "model_boundary_error",
            "worker_id": "provider",
            "payload": {
                "status": "model_budget_exhausted",
                "opportunity_id": "provider-op-budget",
                "limits": ["max_decisions"],
            },
        },
        {
            "sequence": 25,
            "kind": "model_format_feedback",
            "worker_id": "implementer",
            "payload": {
                "call_id": "same-call-id",
                "message": "Actual final parser feedback; no next input need follow.",
            },
        },
    ]
    rollout = {
        "rollout_id": "explicit-export-fixture",
        "window": {"window_id": "fixture"},
        "members": {role: {"actor_id": role, "origin": "target_model"} for role in views},
        "manifest": {
            "policies": {},
            "termination": {"kind": "fixture_only"},
            "scenario": {"roles": []},
        },
        "events": events,
        "reward_eligibility": {"eligible": True, "reward": 0, "completed": False},
    }
    projection = {
        "member_views": views,
        "work_validity": {"value": False, "components": {}},
        "assessment": {
            "eligible": True,
            "reward": 0,
            "completed": False,
            "facts": {},
            "components": [],
        },
        "method_mapping": {"status": "unmapped", "class_id": None},
    }
    slot = {
        "slot_id": "fixture-slot",
        "task": "joint_a",
        "case_id": "fixture-case",
        "seed": 17,
        "repeat_index": 0,
    }
    return rollout, projection, slot, [provider, implementer, stopped], dangerous


def test_exact_role_input_reconstruction_world_sequence_and_no_generation_are_preserved():
    rollout, projection, slot, expected, _ = fixture()
    original = copy.deepcopy((rollout, projection, slot))
    review = extract_review(rollout, projection, slot)
    decisions = review["decisions"]
    assert len(decisions) == 3
    by_key = {(d["member_id"], d["call_id"]): d for d in decisions}
    order = [
        ("provider", "same-call-id"),
        ("implementer", "same-call-id"),
        ("implementer", "no-generation"),
    ]
    reconstructed = [reconstruct_input(review, by_key[key]) for key in order]
    assert reconstructed == expected
    for rebuilt, original_input, key in zip(reconstructed, expected, order):
        assert list(rebuilt) == list(original_input)
        assert digest(json_bytes(rebuilt)) == by_key[key]["input_sha256"]
    assert by_key[order[0]]["sequence"] == 1 and by_key[order[1]]["sequence"] == 11
    assert by_key[order[0]]["actions"][0]["sequence"] == 4
    rejected = by_key[order[1]]["actions"][0]
    assert rejected["sequence"] == 14 and rejected["worker_id"] == "implementer"
    assert rejected["payload"]["response"]["ok"] is False
    stopped = by_key[order[2]]
    assert stopped["generation_status"] == "not_started_direct_context_limit"
    assert stopped["response"] is None and not stopped["actor_required"]
    assert stopped["token_counts"]["output"] == 0
    assert stopped["token_counts"]["input"] is None
    assert stopped["token_counts"]["reported_prompt_tokens"] == 19
    assert review["coverage"]["started_requests"] == 3
    assert review["coverage"]["actual_generations"] == 2
    assert review["coverage"]["non_generation_requests"] == 1
    assert review["coverage"]["unlinked_boundary_errors"] == 1
    assert stopped["non_generation_response"]["body"]["generation_started"] is False
    assert (
        stopped["input"]["tools_present"] is False and stopped["input"]["messages_present"] is True
    )
    assert len(review["boundary_events"]) == 2
    assert review["format_feedback_events"] == [rollout["events"][-1]]
    assert any("model_call_id" not in event["payload"] for event in review["boundary_events"])
    assert (rollout, projection, slot) == original


def test_source_generated_markup_is_escaped_for_the_human_html_page():
    rollout, projection, slot, _, dangerous = fixture()
    review = extract_review(rollout, projection, slot)
    rendered = render_episode_html(review)
    assert dangerous not in rendered
    assert "&lt;img" in rendered or "\\u003cimg" in rendered
    assert "provider-private-only" in rendered and "implementer-private-only" in rendered
    assert (
        next(d for d in review["decisions"] if d["member_id"] == "implementer")["response"][
            "raw_generated_text"
        ]
        == dangerous
    )
