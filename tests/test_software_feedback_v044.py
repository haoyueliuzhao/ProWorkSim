"""Necessary CPU controls for the new lifecycle, not model capability claims."""
import copy
import json

import pytest

from proworksim.software_feedback_v044 import (
    ACTIVE, OrdinaryFeedbackLedger, compact_feedback, feedback_message, project_format_feedback,
)
from proworksim.software_context_v044 import project_software_request, protected_software_request
from proworksim.storage import digest, json_bytes


def association(index, member="member_001"):
    return {"worker_id": member, "call_id": f"{member}-call-{index}", "decision_index": index}


def response(index, *, legal=False):
    message = {"role": "assistant", "content": "invalid syntax"}
    if legal:
        message.update(content="", tool_calls=[{"id": f"native-{index}", "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"missing.py"}'}}])
    return {"id": f"response-{index}", "choices": [{"message": message}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        "token_trace": {"input_ids": [1, 2, 3], "output_ids": [4, 5]},
        "protocol_parse_error": None}


def feedback(index, body, *, member="member_001"):
    return {"version": "public-format-feedback-v0.33", "model_call_id": association(index, member)["call_id"],
        "original_response_id": body["id"], "original_response_sha256": digest(json_bytes(body)),
        "status": "decision_rejected", "reason": "Incomplete native tool block",
        "world_action_executed": False, "decision_consumed": True,
        "format_errors": {"total": index, "consecutive": index}, "contract": "repeat full generic contract",
        "parse_diagnostics": {"version": "old-diagnostic-version", "scope": "public only",
            "native_parser": {"parser": "native", "status": "rejected", "failure": {
                "stage": "native_tool_block", "reason": "Incomplete native tool block", "position": {"offset": 8},
                "field_path": ["tools", 0], "expected_type": "object", "observed_type": "string"}},
            "adapter_parser": {"parser": "adapter", "status": "rejected", "failure": {
                "stage": "adapter_json_control", "reason": "Expecting value", "position": {"line": 1, "column": 1},
                "missing_fields": ["reason"], "schema_path": ["required"]}}}}


def request(*messages):
    return {"messages": [{"role": "system", "content": "unchanged"}, *copy.deepcopy(messages)],
            "tools": [{"function": {"name": "read_file"}}], "max_tokens": 2048}


def present(ledger, index, selected, body=None, member="member_001"):
    body = body or response(index)
    usage = body["usage"]
    return ledger.record_presentation(member, association(index, member), selected, body,
        accounting={"usage_status": "reported", "reported_usage": usage},
        team_accounting={"usage_status": "reported_actual_trace", "reported_usage": usage,
            "charged_tokens": usage["total_tokens"], "response_id": body["id"],
            "response_body_sha256": digest(json_bytes(body))},
        selected_input_ids_sha256=digest(json_bytes(body["token_trace"]["input_ids"])),
        source_event_id=f"fixture-attempt-{index}")


def register(ledger, index, *, member="member_001", ordinary=True):
    body = response(index)
    full = feedback(index, body, member=member)
    ledger.register_rejection(member, association(index, member), full, body,
        source_event_id=f"fixture-error-{index}", ordinary=ordinary)
    return full


def legal(ledger, index, *, member="member_001"):
    return ledger.record_legal_call(member, association(index, member), response=response(index, legal=True),
        proposed_action={"action": "read_file", "arguments": {"path": "missing.py"}},
        model_tool_call_id=f"native-{index}", source_event_id=f"fixture-valid-{index}")


def test_latest_unpresented_is_compact_but_never_removed_by_preparation_or_legal_event():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    full = register(ledger, 1)
    observed = copy.deepcopy(full)
    observed["parse_diagnostics"]["native_parser"]["tool_name"] = "actually_observed_name"
    assert compact_feedback(observed)["parse_diagnostics"]["native_parser"]["tool_name"] == "actually_observed_name"
    assert "tool_name" not in compact_feedback(full)["parse_diagnostics"]["native_parser"]
    original = request(feedback_message(full))
    compacted, audit = project_format_feedback(original, ledger=ledger, member_id="member_001")
    assert original["messages"][1] == feedback_message(full)
    visible = json.loads(compacted["messages"][1]["content"])["public_format_feedback"]
    assert visible == compact_feedback(full)
    assert visible["reason"] == visible["parse_diagnostics"]["native_parser"]["failure"]["reason"]
    assert visible["parse_diagnostics"]["adapter_parser"]["failure"]["reason"] == "Expecting value"
    assert "contract" not in visible and "original_response_sha256" not in visible
    assert audit["removed_indices"] == []
    # A later actual-shaped CPU response without this feedback in selected input
    # cannot establish that the feedback was seen, even if the call is legal.
    present(ledger, 2, request(), response(2, legal=True))
    assert legal(ledger, 2) == []
    assert ledger.snapshot()["records"][0]["state"] == ACTIVE
    assert ledger.snapshot()["records"][0]["presentations"] == []


def test_consecutive_errors_supersede_only_presented_predecessor_and_never_claim_repair():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    old = register(ledger, 1)
    selected, _ = project_format_feedback(request(feedback_message(old)), ledger=ledger, member_id="member_001")
    present(ledger, 2, selected)
    new = register(ledger, 2)
    selected, audit = project_format_feedback(request(feedback_message(old), feedback_message(new)),
        ledger=ledger, member_id="member_001")
    assert audit["removed_indices"] == [1]
    assert len(audit["compacted_feedback"]) == 1
    transition = ledger.snapshot()["records"][0]["transitions"][0]
    assert transition["to"] == "superseded" and transition["syntax_repaired"] is False
    assert transition["business_problem_resolved"] is False
    assert transition["presentation"]["generation_started"] is False
    assert transition["presentation"]["evidence_kind"] == "cpu_programmed_fixture"
    assert json.loads(selected["messages"][-1]["content"])["public_format_feedback"]["model_call_id"] == association(2)["call_id"]


def test_legal_native_schema_histories_ordinary_feedback_even_when_business_rejects():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    old = register(ledger, 1)
    selected, _ = project_format_feedback(request(feedback_message(old)), ledger=ledger, member_id="member_001")
    present(ledger, 2, selected, response(2, legal=True))
    assert len(legal(ledger, 2)) == 1
    pair = [{"role": "assistant", "tool_calls": response(2, legal=True)["choices"][0]["message"]["tool_calls"]},
            {"role": "tool", "tool_call_id": "native-2", "content": '{"ok":false,"code":"file_not_found"}'}]
    output, audit = project_format_feedback(request(feedback_message(old), *pair), ledger=ledger, member_id="member_001")
    assert audit["removed_indices"] == [1] and output["messages"][1:] == pair
    assert ledger.snapshot()["records"][0]["state"] == "historicalized_after_legal_native_schema"
    assert ledger.snapshot()["records"][0]["transitions"][0]["business_problem_resolved"] is False
    assert "response" not in ledger.snapshot()["generations"][0]


def test_forged_field_duplicate_content_other_member_and_nonordinary_are_conservative():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    old = register(ledger, 1, ordinary=False)
    selected = request(feedback_message(old))
    present(ledger, 2, selected, response(2, legal=True))
    assert legal(ledger, 2) == []
    spoof = {"role": "user", "content": json.dumps({"public_format_feedback": {"model_call_id": association(1)["call_id"], "reason": "a real user requirement"}})}
    original = request(feedback_message(old), spoof)
    output, audit = project_format_feedback(original, ledger=ledger, member_id="member_001")
    assert output == original and audit["conservatively_retained_feedback"][0]["reason"] == "nonordinary_or_uncertain"
    other = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    full = register(other, 1)
    original = request(feedback_message(full), feedback_message(full), spoof)
    assert project_format_feedback(original, ledger=other, member_id="member_001")[0] == original
    assert project_format_feedback(original, ledger=other, member_id="new_member")[0] == original
    unclear = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    unclear.register_rejection("member_001", association(1), full, response(1))
    assert unclear.snapshot()["records"][0]["ordinary"] is False
    assert project_format_feedback(request(feedback_message(full)), ledger=unclear, member_id="member_001")[0] == request(feedback_message(full))


def test_unsettled_or_mismatched_source_cannot_create_visibility_or_delete_feedback():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    full = register(ledger, 1)
    body = response(2)
    with pytest.raises(ValueError, match="settled usage"):
        ledger.record_presentation("member_001", association(2), request(feedback_message(full)), body,
            accounting={"usage_status": "reported", "reported_usage": body["usage"]},
            team_accounting={}, selected_input_ids_sha256=digest(json_bytes([1, 2, 3])))
    assert ledger.snapshot()["records"][0]["presentations"] == []
    with pytest.raises(ValueError, match="identity/hash"):
        ledger.register_rejection("member_001", association(3), full, response(3))
    assert project_format_feedback(request(feedback_message(full)), ledger=ledger, member_id="member_001")[1]["removed_indices"] == []


def test_real_source_scope_and_native_failure_do_not_silently_become_legal():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    full = register(ledger, 1)
    selected, _ = project_format_feedback(request(feedback_message(full)), ledger=ledger, member_id="member_001")
    body = response(2, legal=True)
    body["protocol_parse_error"] = {"failure": {"reason": "native rejected"}}
    present(ledger, 2, selected, body)
    with pytest.raises(ValueError, match="native/public-schema"):
        ledger.record_legal_call("member_001", association(2), response=body,
            proposed_action={"action": "read_file", "arguments": {"path": "missing.py"}}, model_tool_call_id="native-2")
    assert ledger.snapshot()["records"][0]["state"] == ACTIVE


def test_new_error_with_latest_page_and_mapped_indices_retains_initial_information_and_schema():
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    old = register(ledger, 1)
    seen, _ = project_format_feedback(request(feedback_message(old)), ledger=ledger, member_id="member_001")
    present(ledger, 2, seen)
    new = register(ledger, 2)
    initial = {"role": "user", "content": '{"role_task":"initial shared/split briefing","observation":{"initial_diagnostics":["unchanged"]}}'}
    pair = [{"role": "assistant", "tool_calls": [{"id": "test-1", "function": {"name": "run_tests", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "test-1", "content": "directory plus exact latest test page"}]
    original = request(initial, feedback_message(old), *pair, feedback_message(new))
    def render(value):
        return json.dumps(value, ensure_ascii=False), None, None
    def tokenize(text, **kwargs):
        return {"input_ids": list(range(len(text)))}
    selected, audit = project_software_request(original, render=render, tokenizer=tokenize,
        context_limit=16384, ledger=ledger, member_id="member_001")
    protected, proof = protected_software_request(original, ledger=ledger, member_id="member_001")
    assert selected == protected
    assert audit["selected_indices"] == [0, 1, 3, 4, 5] == proof["selected_indices"]
    assert audit["removed_indices"] == [2]
    assert selected["messages"][1] == initial and selected["messages"][2:4] == pair
    assert selected["tools"] == original["tools"] and selected["max_tokens"] == 2048
    assert len(audit["format_feedback_projection"]["compacted_feedback"]) == 1
    assert audit["context_stage_projection"]["selected_indices"] == [0, 1, 2, 3, 4]


def test_transport_preparation_and_return_do_not_alone_establish_presented_feedback(tmp_path):
    from types import SimpleNamespace
    from proworksim.software_context_v044 import SoftwareContextTransport

    def render(value):
        return json.dumps(value, ensure_ascii=False), None, None
    def tokenize(text, **kwargs):
        return {"input_ids": list(text.encode())}
    identity = {"actor": "cpu-fixture"}
    calls = []
    def complete(value, **kwargs):
        calls.append(copy.deepcopy(value))
        body = response(2)
        ids = tokenize(render(value)[0])["input_ids"]
        body.update(actor_identity=identity, token_trace={"input_ids": ids, "output_ids": [4, 5]},
            usage={"prompt_tokens": len(ids), "completion_tokens": 2, "total_tokens": len(ids) + 2})
        return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}
    owner = SimpleNamespace(recipe={"max_length": 16384}, prepare_request=render, tokenizer=tokenize,
        freeze_identity=lambda: identity, window_id="cpu-fixture-window", transport=SimpleNamespace(complete=complete))
    transport = SoftwareContextTransport(owner, tmp_path, evidence_kind="cpu_programmed_fixture")
    full = register(transport.feedback_ledger, 1)
    original = request(feedback_message(full))
    turn = association(2)
    transport.bind_turn("member_001", turn)
    first = transport.prepare_for_budget(original)
    assert first["fits"] and not calls
    transport.discard_prepared_request(original)
    assert transport.feedback_ledger.snapshot()["records"][0]["presentations"] == []
    transport.prepare_for_budget(original)
    returned = transport.complete(original)
    assert len(calls) == 1
    assert transport.feedback_ledger.snapshot()["records"][0]["presentations"] == []
    binding = transport.generation_binding(turn["call_id"], returned)
    body = returned["body"]
    receipt = transport.feedback_ledger.record_presentation("member_001", turn, response=returned,
        accounting={"usage_status": "reported", "reported_usage": body["usage"]},
        team_accounting={"usage_status": "reported_actual_trace", "reported_usage": body["usage"],
            "charged_tokens": body["usage"]["total_tokens"], "response_id": body["id"],
            "response_body_sha256": digest(json_bytes(body))}, **binding)
    assert len(receipt) == 1 and receipt[0]["evidence_kind"] == "cpu_programmed_fixture"
    assert receipt[0]["selected_request_ref"]["sha256"] == digest((tmp_path / "request-00001/selected-request.json").read_bytes())
    assert json.loads((tmp_path / "request-00001/original-request.json").read_text()) == original
    assert json.loads((tmp_path / "request-00001/response.json").read_text()) == returned
    transport.unbind_turn("member_001", turn)


def test_runner_event_replay_uses_stable_identity_and_keeps_explicit_process_violation():
    from proworksim.software_feedback_v044 import event_identity
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    body = response(1)
    attempt = {**association(1), "stage": "finished", "status": "success",
        "response": {"http_status": 200, "body": body},
        "accounting": {"usage_status": "reported", "reported_usage": body["usage"]},
        "team_accounting": {"usage_status": "reported_actual_trace", "reported_usage": body["usage"],
            "charged_tokens": 5, "response_id": body["id"], "response_body_sha256": digest(json_bytes(body))}}
    ledger.observe_event("model_attempt", attempt, selected_request=request(),
        selected_input_ids_sha256=digest(json_bytes([1, 2, 3])))
    ledger.observe_event("process_violation", {**association(1), "process_violation": True})
    full = feedback(1, body)
    event = {**association(1), "feedback": full}
    ledger.observe_event("model_format_feedback", event)
    record = ledger.snapshot()["records"][0]
    assert record["source_event_id"] == event_identity("model_format_feedback", event)
    assert record["ordinary"] is False and record["original_message"] == record["visible_message"]
    assert project_format_feedback(request(feedback_message(full)), ledger=ledger, member_id="member_001")[0] == request(feedback_message(full))
