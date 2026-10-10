"""Source/timing guards only; the declared historical112 native replay is separate."""

import copy
import json

import pytest

from proworksim.software_feedback_v044 import event_identity, feedback_message
from proworksim.storage import digest, json_bytes
from scripts import software_context_replay_v044 as replay


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def source_fixture(tmp_path, *, rejected_kind="context_capacity"):
    """Small immutable source-shaped fixture, never a model/tokenizer run."""
    folder = tmp_path / "episode"
    member = "member_001"
    identity = {"policy_version": "unit-fixture", "adapter_sha256": "no-model"}
    records = {}
    attempts = []
    events = []
    full_feedback = None

    def emit(kind, payload):
        events.append(
            {
                "sequence": len(events),
                "kind": kind,
                "worker_id": member,
                "payload": copy.deepcopy(payload),
            }
        )

    for number in (1, 2, 3):
        call = f"call-{number}"
        assoc = {
            "call_id": call,
            "decision_id": call,
            "worker_id": member,
            "decision_index": number,
        }
        messages = [
            {"role": "system", "content": "unchanged private fixture"},
            {"role": "user", "content": "original user instruction"},
        ]
        if full_feedback is not None:
            messages.append(feedback_message(full_feedback))
        original = {"model": "unit-fixture", "messages": messages, "tools": [], "max_tokens": 2048}
        selection = {
            "selected_indices": list(range(len(messages))),
            "messages": [{"sha256": digest(json_bytes(m))} for m in messages],
            "selected_messages_sha256": digest(json_bytes(messages)),
        }
        prep = {
            "original_request_sha256": digest(json_bytes(original)),
            "selected_request_sha256": digest(json_bytes(original)),
            "rendered_prompt_sha256": "not-native-measured-in-unit-fixture",
            "input_ids_sha256": digest(json_bytes([number, 4, 5])),
            "prompt_tokens": 3,
            "reserved_output_tokens": 2048,
            "context_limit": 16384,
            "actor_identity": identity,
            "window_id": "fixture-window",
            "fits": True,
        }
        emit(
            "model_call",
            {
                **assoc,
                "stage": "started",
                "request_sha256": prep["original_request_sha256"],
                "context_selection": selection,
                "reservation": {"preparation": prep},
            },
        )
        if number == 3:
            records[call] = {
                "member": member,
                "call_id": call,
                "status": "admission_rejected",
                "attempt_started": False,
                "budget_kind": rejected_kind,
                "rejected_reservation": {"preparation": prep},
            }
            continue
        message = {"role": "assistant", "content": "invalid output"}
        if number == 2:
            message = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "native-2",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"missing.py"}'},
                    }
                ],
            }
        body = {
            "id": f"response-{number}",
            "actor_identity": identity,
            "online_window_id": "fixture-window",
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "token_trace": {"input_ids": [number, 4, 5], "output_ids": [6, 7]},
            "protocol_parse_error": None,
        }
        response = {"http_status": 200, "body": body, "raw_body": json.dumps(body)}
        charge = {
            "usage_status": "reported_actual_trace",
            "reported_usage": body["usage"],
            "charged_tokens": 5,
            "response_id": body["id"],
            "response_body_sha256": digest(json_bytes(body)),
        }
        records[call] = {
            "member": member,
            "call_id": call,
            "status": "settled",
            "attempt_started": True,
            "reservation": {"preparation": prep},
            "charge": charge,
        }
        attempts.append(
            {
                "call_id": call,
                "worker_id": member,
                "status": "success",
                "original_output_present": True,
                "request_sha256": prep["original_request_sha256"],
                "input_ids_sha256": prep["input_ids_sha256"],
                "output_ids_sha256": digest(json_bytes([6, 7])),
                "response_body_sha256": digest(json_bytes(body)),
                "usage": body["usage"],
            }
        )
        directory = folder / "raw-transport" / f"request-{number:05d}"
        for filename, value in [
            ("original-request.json", original),
            ("selected-request.json", original),
            ("budget-preparation.json", prep),
            ("projection.json", {"input_ids_sha256": prep["input_ids_sha256"]}),
            ("response.json", response),
        ]:
            write(directory / filename, value)
        emit(
            "model_attempt",
            {
                **assoc,
                "stage": "finished",
                "status": "success",
                "request": original,
                "response": response,
                "accounting": {"usage_status": "reported", "reported_usage": body["usage"]},
                "team_accounting": charge,
            },
        )
        emit("model_response", {**assoc, "response": body})
        if number == 1:
            diagnostic = {
                "native_parser": {"status": "no_failure_reported", "failure": None},
                "adapter_parser": {
                    "status": "rejected",
                    "failure": {"stage": "adapter_structure", "reason": "invalid output"},
                },
            }
            full_feedback = {
                "version": "public-format-feedback-v0.33",
                "model_call_id": call,
                "original_response_id": body["id"],
                "original_response_sha256": digest(json_bytes(body)),
                "status": "decision_rejected",
                "reason": "invalid output",
                "world_action_executed": False,
                "decision_consumed": True,
                "parse_diagnostics": diagnostic,
            }
            emit("model_format_error", {**assoc, "reason": "invalid output"})
            emit("model_format_feedback", {**assoc, "feedback": full_feedback})
            emit(
                "model_call",
                {
                    **assoc,
                    "stage": "finished",
                    "status": "protocol_rejection",
                    "meter": {"kept_for_original_event_id": True},
                },
            )
        else:
            emit(
                "model_call",
                {
                    **assoc,
                    "stage": "finished",
                    "status": "proposed_action",
                    "model_tool_call_id": "native-2",
                    "proposed_action": {"action": "read_file", "arguments": {"path": "missing.py"}},
                    "meter": {"kept_for_original_event_id": True},
                },
            )
    write(folder / "organization-evidence.json", {"original_attempts": attempts})
    write(folder / "team-budget.json", {"model": {"records": records}})
    (folder / "experience.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return folder, events


def test_all_actual_and_rejected_requests_are_bound_and_state_precedes_the_current_output(tmp_path):
    folder, events = source_fixture(tmp_path)
    history = replay.load_episode_history(folder)
    assert history["counts"] == {"generated": 2, "hard_context_rejected": 1}
    timeline = replay.reconstruct_feedback_timeline(history)
    assert set(timeline["before_call"]) == {"call-1", "call-2", "call-3"}
    assert timeline["before_call"]["call-1"]["records"] == []
    before_error = timeline["before_call"]["call-2"]["records"][0]
    assert before_error["state"] == "pending_or_presented" and before_error["presentations"] == []
    after_legal = timeline["before_call"]["call-3"]["records"][0]
    assert after_legal["state"] == "historicalized_after_legal_native_schema"
    assert after_legal["presentations"][0]["call_id"] == "call-2"
    assert after_legal["transitions"][0]["business_problem_resolved"] is False
    original_finish = next(
        e
        for e in events
        if e["kind"] == "model_call" and e["payload"].get("status") == "proposed_action"
    )
    assert after_legal["transitions"][0]["source_event_id"] == event_identity(
        original_finish["kind"], original_finish["payload"]
    )
    assert (
        "meter"
        not in next(e for e in history["events"] if e["sequence"] == original_finish["sequence"])[
            "payload"
        ]
    )


def test_team_budget_rejection_has_a_before_snapshot_but_is_not_historical112(tmp_path):
    folder, _ = source_fixture(tmp_path, rejected_kind=None)
    history = replay.load_episode_history(folder)
    assert history["requests"][-1]["kind"] == "team_budget_rejected"
    assert history["counts"] == {"generated": 2, "hard_context_rejected": 0}
    assert "call-3" in replay.reconstruct_feedback_timeline(history)["before_call"]


def test_changed_output_or_double_charging_cannot_supply_historical_presentation(tmp_path):
    folder, _ = source_fixture(tmp_path)
    path = folder / "raw-transport/request-00002/response.json"
    value = json.loads(path.read_text())
    value["body"]["token_trace"]["output_ids"].append(88)
    write(path, value)
    with pytest.raises(ValueError, match="identity failed"):
        replay.load_episode_history(folder)


def test_feedback_without_runner_error_event_is_not_trusted(tmp_path):
    folder, events = source_fixture(tmp_path)
    (folder / "experience.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events if e["kind"] != "model_format_error")
    )
    with pytest.raises(ValueError, match="runner format-error"):
        replay.load_episode_history(folder)


def test_recovery_refuses_missing_message_or_whole_request_identity(tmp_path):
    folder, _ = source_fixture(tmp_path)
    history = replay.load_episode_history(folder)
    start = next(
        e
        for e in history["events"]
        if e["kind"] == "model_call" and e["payload"].get("call_id") == "call-3"
    )
    rejected = history["requests"][-1]
    with pytest.raises(ValueError, match="exact SDK-selected"):
        replay.recover_request(
            start, rejected["original_request"], {}, rejected["recorded_preparation"]
        )
    bank = {
        digest(json_bytes(m)): {"message": m, "source": {"fixture": True}}
        for m in rejected["original_request"]["messages"]
    }
    bad = copy.deepcopy(rejected["recorded_preparation"])
    bad["original_request_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="whole request"):
        replay.recover_request(start, rejected["original_request"], bank, bad)


def test_latest_page_and_unpresented_error_must_both_survive(tmp_path):
    folder, _ = source_fixture(tmp_path)
    history = replay.load_episode_history(folder)
    state = replay.reconstruct_feedback_timeline(history)["before_call"]["call-2"]
    record = state["records"][0]
    pair = [
        {
            "role": "assistant",
            "tool_calls": [{"id": "native-page", "function": {"name": "run_tests"}}],
        },
        {"role": "tool", "tool_call_id": "native-page", "content": "exact-page-text"},
    ]
    original = {"messages": [*pair, record["original_message"]], "tools": [], "max_tokens": 2048}
    selected = {**original, "messages": [*pair, record["visible_message"]]}
    projection = {"format_feedback_projection": {"removed_feedback": []}}
    checks, _ = replay.feedback_preservation_checks(
        original, selected, projection, ledger=state, member_id="member_001"
    )
    assert all(checks.values())
    selected["messages"] = [*pair]
    checks, _ = replay.feedback_preservation_checks(
        original, selected, projection, ledger=state, member_id="member_001"
    )
    assert checks["latest_unpresented_feedback_retained"] is False
    selected["messages"] = [record["visible_message"]]
    checks, _ = replay.feedback_preservation_checks(
        original, selected, projection, ledger=state, member_id="member_001"
    )
    assert checks["latest_complete_tool_or_page_unchanged"] is False
