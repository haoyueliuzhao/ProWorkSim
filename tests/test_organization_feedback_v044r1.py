"""Narrow synthetic termination evidence controls; no world/model/tokenizer execution."""

import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_feedback_v044r1 as measure


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def fixture(root, *, reward=0):
    member, cid, tool_id = "member_001", "retire-call", "native-retire"
    window, opportunity = "organization-v044:fixture", "staff-opportunity-example-4"
    action_id, operation, reason = (
        "action-20",
        "command-retire",
        "I am stopping with unresolved work",
    )
    identity, args = {"actor_sha256": "frozen"}, {"reason": reason}
    selected = {
        "messages": [
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "observation": {
                            "world_id": "world",
                            "instance_id": "instance",
                            "branch_id": "branch",
                            "project_id": "SOFTWARE27",
                            "actor_id": member,
                            "logical_time": 7,
                        }
                    }
                ),
            }
        ]
    }
    body = {
        "id": "original-response",
        "actor_identity": identity,
        "online_window_id": window,
        "protocol_parse_error": None,
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": tool_id,
                            "type": "function",
                            "function": {"name": "retire_member", "arguments": json.dumps(args)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        "token_trace": {"input_ids": [1, 2, 3], "output_ids": [4]},
    }
    raw = root / "raw-transport/request-00004"
    selected_path = raw / "selected-request.json"
    save(selected_path, selected)
    save(raw / "response.json", {"http_status": 200, "body": body})
    call = {
        "call_id": cid,
        "member": member,
        "experience_sequence": 10,
        "path": str(selected_path),
        "selected_request_sha256": digest(json_bytes(selected)),
        "input_ids_sha256": digest(json_bytes([1, 2, 3])),
    }
    prep = {
        "selected_request_sha256": call["selected_request_sha256"],
        "input_ids_sha256": call["input_ids_sha256"],
        "prompt_tokens": 3,
        "actor_identity": identity,
        "window_id": window,
    }
    charge = {
        "usage_status": "reported_actual_trace",
        "reported_usage": body["usage"],
        "charged_tokens": 4,
        "response_id": body["id"],
        "response_body_sha256": digest(json_bytes(body)),
    }
    budget = {
        "binding": {"window_id": window, "actor_identity": identity},
        "records": {
            cid: {
                "member": member,
                "attempt_started": True,
                "status": "settled",
                "reservation": {"preparation": prep},
                "charge": charge,
            }
        },
    }
    evidence = {
        "original_attempts": [
            {
                "call_id": cid,
                "worker_id": member,
                "status": "success",
                "original_output_present": True,
                "experience_sequence": 10,
                "response_id": body["id"],
                "response_body_sha256": digest(json_bytes(body)),
                "input_ids_sha256": call["input_ids_sha256"],
                "output_ids_sha256": digest(json_bytes([4])),
                "usage": body["usage"],
            }
        ]
    }
    actual_result = {
        "member_id": member,
        "status": "retired",
        "retained_obligations": ["unfinished-task"],
    }
    returned = {
        "ok": True,
        "result": actual_result,
        "action_id": action_id,
        "command_id": operation,
        "command_committed": True,
        "committed_revision": 8,
    }
    association = {"model_call_id": cid, "model_tool_call_id": tool_id, "decision_id": cid}
    events = [
        ("model_response", {"call_id": cid, "response": body, "opportunity_id": opportunity}),
        (
            "model_call",
            {
                "call_id": cid,
                "decision_id": cid,
                "worker_id": member,
                "stage": "finished",
                "status": "proposed_action",
                "model_tool_call_id": tool_id,
                "weight_identity": identity,
                "opportunity_id": opportunity,
                "proposed_action": {"action": "retire_member", "arguments": args},
            },
        ),
        (
            "policy_decision",
            {
                "decision": {
                    "kind": "act",
                    "action": "retire_member",
                    "arguments": args,
                    **association,
                }
            },
        ),
        (
            "tool_call",
            {
                "action": "retire_member",
                "arguments": args,
                "response": returned,
                "request_key": "original-request-key",
                "opportunity_id": opportunity,
                **association,
            },
        ),
        (
            "model_action_link",
            {
                "world_action_id": action_id,
                "world_command_id": operation,
                "world_response": returned,
                "request_key": "original-request-key",
                "opportunity_id": opportunity,
                **association,
            },
        ),
        (
            "model_tool_result",
            {
                "call_id": cid,
                "model_tool_call_id": tool_id,
                "world_response": returned,
                "message": {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(returned),
                },
            },
        ),
    ]
    experience = [
        {"sequence": number, "kind": kind, "worker_id": member, "payload": payload}
        for number, (kind, payload) in enumerate(events, 100)
    ]
    # World seq500 deliberately exceeds experience seq105: their numbers must
    # never be compared; they are joined by the committed action/operation IDs.
    retirement = {
        "kind": "member_retired",
        "sequence": 500,
        "actor_id": member,
        "member_id": member,
        "action_id": action_id,
        "operation_id": operation,
        "reason": reason,
        "logical_time": 7,
        "retained_obligations": ["unfinished-task"],
    }
    state = {
        "world_id": "world",
        "instance_id": "instance",
        "branch_id": "branch",
        "software_events": [retirement],
        "interactions": [
            {
                "action_id": action_id,
                "actor_id": member,
                "action": "project_action",
                "inputs": {"tool": "retire_member", "arguments": args, "project_id": "SOFTWARE27"},
                "request_key": "original-request-key",
                "transition_id": operation,
                "output": {"ok": True, "result": actual_result},
            }
        ],
        "operation_commits": {
            operation: {
                "operation_id": operation,
                "bound_actor": member,
                "public_result": returned,
                "committed_revision": 8,
                "receipt": {
                    "contract": "retire_member",
                    "bound_actor": member,
                    "execution_outcome": "committed",
                    "transition_id": operation,
                },
            }
        },
        "projects": {
            "SOFTWARE27": {
                "software": {
                    "registry": {
                        member: {
                            "member_id": member,
                            "status": "retired",
                            "retirement_sequence": 500,
                            "retirement_reason": reason,
                        }
                    },
                    "tasks": {"unfinished-task": {"owner": member, "status": "open"}},
                }
            }
        },
    }
    result = {
        "slot_id": "fixture",
        "status": "closed",
        "R": reward,
        "submitted": bool(reward),
        "boundary": {
            "role_stops": {member: "retired"},
            "terminal_details": {},
            "execution_integrity_failure": None,
        },
    }
    row = {
        "feedback_id": "feedback-105",
        "kind": "native_tool_feedback",
        "tool": "retire_member",
        "member": member,
        "originating_call_id": cid,
        "model_tool_call_id": tool_id,
        "arguments": args,
        "experience_sequence": 105,
        "generated_and_saved": True,
        "actual_originating_generation_bound": True,
        "feedback_ok": True,
        "feedback_payload_sha256": digest(json_bytes(returned)),
        "presentation": {
            "later_actual_generation_count": 0,
            "first_exact_presentation": None,
            "matching_actual_request_count": 0,
            "presented_in_first_actual_followup": False,
        },
        "no_actual_followup": {"reason": "unknown_no_actual_followup", "terminal_detail": {}},
    }
    inputs = SimpleNamespace(
        calls={cid: call},
        by_member=lambda member: [c for c in inputs.calls.values() if c["member"] == member],
    )
    return SimpleNamespace(
        row=row,
        state=state,
        result=result,
        evidence=evidence,
        budget=budget,
        inputs=inputs,
        experience=experience,
        folder=root,
        body=body,
        raw=raw,
        returned=returned,
    )


def bind(f):
    return measure.bind_self_retirement(
        f.row,
        state=f.state,
        result=f.result,
        evidence=f.evidence,
        budget=f.budget,
        inputs=f.inputs,
        experience=f.experience,
        folder=f.folder,
    )


def baseline(row, *, reward=0):
    reason = row["no_actual_followup"]["reason"]
    return {
        "version": measure.previous.VERSION,
        "slot_id": "fixture",
        "status": "measured",
        "episode_closed": True,
        "R": reward,
        "feedback_records": [copy.deepcopy(row)],
        "measurement_gaps": [],
        "denominators": {
            "all_saved_feedback_units": 1,
            "protocol_feedback_saved_exactly": 1,
            "with_later_actual_generation": 0,
            "presented_in_later_actual_generation": 0,
            "presented_in_first_actual_followup": 0,
            "without_later_actual_generation": 1,
            "no_followup_reasons": {reason: 1},
            "by_tool": {
                row["tool"]: {
                    "feedback_units": 1,
                    "presented_in_actual_generation": 0,
                    "no_followup_reasons": {reason: 1},
                }
            },
        },
        "mechanism_gate_inputs": {
            "resolved": reason != "unknown_no_actual_followup",
            "actual_generated_requests": 1,
            "requests_verified_under_v044": 1,
            "projection_unresolved": [],
            "projection_violations": [],
            "page_protocol_unresolved": [],
            "page_protocol_violations": [],
            "feedback_missing_from_first_actual_followup": [],
            "context_blocked_feedback_ids": [],
            "unresolved_no_followup_ids": [row["feedback_id"]]
            if reason == "unknown_no_actual_followup"
            else [],
        },
    }


def block(value):
    return [{**copy.deepcopy(value), "slot_id": f"slot-{index}"} for index in range(4)]


@pytest.mark.parametrize("reward", [0, 1])
def test_original_committed_self_retirement_is_normal_even_with_unfinished_R0_work(
    tmp_path, reward
):
    f = fixture(tmp_path, reward=reward)
    before = json_bytes(f.state), json_bytes(f.row), f.raw.joinpath("response.json").read_bytes()
    proof = bind(f)
    value = measure.apply_termination_revision(
        baseline(f.row, reward=reward), {f.row["feedback_id"]: proof}, []
    )
    assert proof["reason"] == "voluntary_self_retirement" and proof["retained_obligations"] == [
        "unfinished-task"
    ]
    assert (
        proof["actual_feedback_presentation_added"] is False
        and proof["R_used_for_classification"] is False
    )
    assert value["feedback_records"][0]["presentation"] == f.row["presentation"]
    assert (
        value["denominators"]["all_saved_feedback_units"]
        == value["denominators"]["without_later_actual_generation"]
        == 1
    )
    assert value["denominators"]["presented_in_later_actual_generation"] == 0
    assert value["R"] == reward and measure.first_block_gate(block(value))["passed"] is True
    assert before == (
        json_bytes(f.state),
        json_bytes(f.row),
        f.raw.joinpath("response.json").read_bytes(),
    )


@pytest.mark.parametrize(
    "mismatch",
    [
        "uncommitted",
        "actor",
        "call",
        "action",
        "window",
        "target",
        "registry",
        "duplicate_link",
        "missing_link",
        "external",
        "after_generation",
        "after_commit_before_feedback",
        "integrity",
        "uncharged",
        "invented_target",
    ],
)
def test_missing_external_or_conflicting_retirement_evidence_never_becomes_normal(
    tmp_path, mismatch
):
    f = fixture(tmp_path)
    if mismatch == "uncommitted":
        f.returned["command_committed"] = False
    elif mismatch == "actor":
        f.experience[1]["worker_id"] = "member_002"
    elif mismatch == "call":
        f.experience[4]["payload"]["model_call_id"] = "other-call"
    elif mismatch == "action":
        f.state["software_events"][0]["action_id"] = "other-action"
    elif mismatch == "window":
        f.budget["binding"]["window_id"] = "organization-v044:other-slot"
    elif mismatch == "target":
        f.returned["result"]["member_id"] = "member_002"
    elif mismatch == "registry":
        f.state["projects"]["SOFTWARE27"]["software"]["registry"]["member_001"][
            "retirement_sequence"
        ] += 1
    elif mismatch == "duplicate_link":
        f.experience.append(copy.deepcopy(f.experience[4]))
    elif mismatch == "missing_link":
        f.experience.pop(4)
    elif mismatch == "external":
        f.state["software_events"][0]["origin"] = "administrator"
    elif mismatch == "after_generation":
        f.inputs.calls["later"] = {
            **f.inputs.calls["retire-call"],
            "call_id": "later",
            "experience_sequence": 106,
        }
    elif mismatch == "after_commit_before_feedback":
        f.inputs.calls["during_return"] = {
            **f.inputs.calls["retire-call"],
            "call_id": "during_return",
            "experience_sequence": 104,
        }
    elif mismatch == "integrity":
        f.result["boundary"]["execution_integrity_failure"] = {"kind": "identity_mismatch"}
    elif mismatch == "uncharged":
        f.budget["records"]["retire-call"]["charge"]["usage_status"] = "uncertain"
    else:
        f.body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps(
            {"reason": "stopping", "target": "member_001"}
        )
        sha = digest(json_bytes(f.body))
        f.evidence["original_attempts"][0]["response_body_sha256"] = sha
        f.budget["records"]["retire-call"]["charge"]["response_body_sha256"] = sha
        save(f.raw / "response.json", {"http_status": 200, "body": f.body})
    with pytest.raises(measure.UnboundRetirement):
        bind(f)
    value = measure.apply_termination_revision(
        baseline(f.row), {}, [{"feedback_id": f.row["feedback_id"], "detail": mismatch}]
    )
    assert (
        value["feedback_records"][0]["no_actual_followup"]["reason"] == "unknown_no_actual_followup"
    )
    assert measure.first_block_gate(block(value))["passed"] is False


def test_staff_done_bridge_keeps_its_original_reason_and_unseen_return(tmp_path, monkeypatch):
    f = fixture(tmp_path)
    row = copy.deepcopy(f.row)
    row.update(tool="staff_done", arguments={"reason": "normal done"})
    row["no_actual_followup"] = {
        "reason": "voluntary_end",
        "terminal_detail": {"status": "completed"},
    }
    old = baseline(row)
    monkeypatch.setattr(measure.previous, "measure_episode", lambda folder: copy.deepcopy(old))
    value = measure.measure_episode(tmp_path)
    assert value["termination_revision"]["classification_changes"] == []
    assert value["feedback_records"] == old["feedback_records"]
    assert value["denominators"]["no_followup_reasons"] == {"voluntary_end": 1}
    assert measure.first_block_gate(block(value))["passed"] is True


def test_valid_retirement_cannot_override_an_independent_mechanical_problem(tmp_path):
    f = fixture(tmp_path)
    old = baseline(f.row)
    old["mechanism_gate_inputs"]["context_blocked_feedback_ids"] = ["another-real-feedback"]
    value = measure.apply_termination_revision(old, {f.row["feedback_id"]: bind(f)}, [])
    assert value["feedback_records"][0]["no_actual_followup"]["reason"] == measure.REASON
    assert value["mechanism_gate_inputs"]["context_blocked_feedback_ids"] == [
        "another-real-feedback"
    ]
    assert measure.first_block_gate(block(value))["passed"] is False


def test_business_rejection_of_retirement_keeps_ordinary_budget_end_unless_retired_is_claimed(
    tmp_path, monkeypatch
):
    f = fixture(tmp_path)
    f.inputs.issues = []
    f.row.update(feedback_ok=False)
    f.row["no_actual_followup"] = {
        "reason": "team_budget",
        "terminal_detail": {"status": "team_budget_exhausted"},
    }
    f.result["boundary"]["role_stops"]["member_001"] = "team_budget_exhausted"
    f.result["team_budget"] = {"model": f.budget}
    f.returned.update(ok=False, command_committed=False)
    f.state["software_events"] = []
    f.state["projects"]["SOFTWARE27"]["software"]["registry"]["member_001"]["status"] = "live"
    save(tmp_path / "slot-result.json", f.result)
    save(tmp_path / "organization-evidence.json", f.evidence)
    save(tmp_path / "prepared/world/control/state.json", f.state)
    (tmp_path / "experience.jsonl").write_text(
        "\n".join(json.dumps(event) for event in f.experience) + "\n"
    )
    monkeypatch.setattr(measure.previous, "measure_episode", lambda folder: baseline(f.row))
    monkeypatch.setattr(measure.previous.base, "Inputs", lambda *args: f.inputs)
    value = measure.measure_episode(tmp_path)
    assert (
        value["termination_revision"]["bindings"]
        == value["termination_revision"]["unresolved"]
        == []
    )
    assert value["feedback_records"][0]["no_actual_followup"]["reason"] == "team_budget"
    assert measure.first_block_gate(block(value))["passed"] is True
    f.result["boundary"]["role_stops"]["member_001"] = "retired"
    save(tmp_path / "slot-result.json", f.result)
    value = measure.measure_episode(tmp_path)
    assert value["termination_revision"]["unresolved"]
    assert measure.first_block_gate(block(value))["passed"] is False
