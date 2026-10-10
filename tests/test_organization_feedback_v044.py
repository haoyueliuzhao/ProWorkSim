"""Focused synthetic JSON controls for v044 measurement, without model/native encoding."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.software_context_v044 import project_software_request
from proworksim.software_feedback_v044 import OrdinaryFeedbackLedger, event_identity, feedback_message
from proworksim.software_organization_v042 import READ_TEST_RESULT_TOOL, build_test_report, test_result_page as report_page
from proworksim.storage import digest, json_bytes
from scripts import measure_organization_feedback_v044 as measure
from scripts.software_context_replay_v044 import _brief_lifecycle_event, reconstruct_feedback_timeline


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def correction(body):
    return {"version": "public-format-feedback-v0.33", "model_call_id": "call-error",
        "original_response_id": body["id"], "original_response_sha256": digest(json_bytes(body)),
        "status": "decision_rejected", "reason": "Incomplete native tool block",
        "world_action_executed": False, "decision_consumed": True,
        "contract": "Repeated generic contract remains fully archived.",
        "parse_diagnostics": {"native_parser": {"status": "rejected", "failure": {
            "stage": "native_xml", "reason": "Incomplete native tool block", "position": None}},
            "adapter_parser": {"status": "rejected", "failure": {
                "stage": "adapter_json_control", "reason": "Expecting value", "position": {"offset": 0}}}}}


def project(request, ledger):
    # Deterministic character fixture, expressly not a real model tokenizer.
    return project_software_request(request, ledger=ledger, member_id="member_001",
        render=lambda value: (json.dumps(value, ensure_ascii=False), None, None),
        tokenizer=lambda text, **kwargs: {"input_ids": list(range(len(text)))}, context_limit=16384)


def fixture(root, *, spoof=False):
    member = "member_001"
    initial_ref = {"object_id": "baseline", "version_id": "v1"}
    initial = {"diagnostic_id": "initial-1", "origin": "environment_initial_diagnostic", "initial_report": True,
        "source_reference": initial_ref, "initial_source_reference": initial_ref, "files_sha256": "initial-files",
        "executed": True, "passed": False, "tests": []}
    identity = {"world_id": "world", "instance_id": "instance", "branch_id": "branch", "project_id": "SOFTWARE27", "actor_id": member}
    source = {"object_id": "workspace", "version_id": "v3"}
    visible = {"source_reference": source, "files_sha256": "current-files", "executed": True, "passed": False,
        "scope": "Original public checks only", "untested": ["independent_acceptance"], "independent_acceptance": "not_run",
        "fixed_submission_is_acceptance": False, "groups": {"public": {"executed": True, "passed": False,
            "tests": [{"test_id": "long-page", "passed": False, "observed": "界🙂" * 2000, "expected": "published expectation"}]}}}
    report = build_test_report(visible, actor_id=member,
        event_identity={**identity, "test_event_sequence": 1, "operation_id": "test-operation"})
    page_value = {"ok": True, "action_id": "test-action", "result": report_page(report)}
    world_events = [{"sequence": 1, "kind": "test", "actor_id": member, "action_id": "test-action",
        "operation_id": "test-operation", "source_reference": source},
        {"sequence": 2, "kind": "test_report_saved", "actor_id": member, "report_id": report["report_id"],
         "test_event_sequence": 1, "body_sha256": report["body_sha256"], "source_reference": source}]
    observation = {**identity, "interface_revision": measure.PAGE_INTERFACE, "contract": "Complete the original task.",
        "root_goal": {"task_id": "root", "description": "Complete the original task."}, "initial_diagnostics": [initial]}
    obs_message = {"role": "user", "content": json.dumps({"role_task": "Use original public evidence.", "observation": observation})}
    body = {"id": "rejected-response"}
    full = correction(body)
    ledger = OrdinaryFeedbackLedger(evidence_kind="cpu_programmed_fixture")
    association = {"worker_id": member, "call_id": "call-error", "decision_index": 2}
    ledger.register_rejection(member, association, full, body, source_event_id="synthetic-runner-format-event")
    request = {"max_tokens": 2048, "tools": [{"type": "function", "function": READ_TEST_RESULT_TOOL}],
        "messages": [{"role": "system", "content": "Original tool contract."}, obs_message,
            {"role": "assistant", "content": "", "tool_calls": [{"id": "native-test", "type": "function",
                "function": {"name": "run_tests", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "native-test", "content": json.dumps(page_value, ensure_ascii=False)},
            feedback_message(full)]}
    if spoof:
        request["messages"].append({"role": "user", "content": json.dumps({"public_format_feedback": {
            "model_call_id": "call-error", "reason": "An independent real user requirement, not runner feedback"}})})
    snapshot = ledger.snapshot()
    selected, projection = project(request, snapshot)
    folder = root / "raw-transport/request-00003"
    call = {"call_id": "call-followup", "member": member, "experience_sequence": 30,
        "path": str(folder / "selected-request.json"), "selected_request_sha256": digest(json_bytes(selected)),
        "input_ids_sha256": projection["input_ids_sha256"]}
    record = {"reservation": {"preparation": {"original_request_sha256": digest(json_bytes(request)),
        "prompt_tokens": projection["selected_prompt_tokens"]}},
        "charge": {"reported_usage": {"prompt_tokens": projection["selected_prompt_tokens"]}}}
    for name, value in (("original-request.json", request), ("selected-request.json", selected),
                        ("projection.json", projection), ("feedback-lifecycle-before.json", snapshot)):
        save(folder / name, value)
    return SimpleNamespace(folder=folder, call=call, record=record, original=request, selected=selected,
        projection=projection, ledger=snapshot, initial={initial["diagnostic_id"]: initial}, assignments={member: [initial["diagnostic_id"]]},
        report=report, page_value=page_value, world_events=world_events, observation=obs_message, full=full)


def audit(f):
    return measure.audit_projection(f.call, f.record, f.initial, f.assignments, f.ledger)


def test_latest_compact_feedback_and_complete_returned_test_page_are_independently_verified(tmp_path):
    f = fixture(tmp_path)
    result = audit(f)
    assert result["status"] == "verified" and result["uses_v044"] is True
    assert result["latest_complete_round_present"] is True
    assert result["format_feedback_projection"]["removed_indices"] == []
    assert len(result["format_feedback_projection"]["compacted_feedback"]) == 1
    assert f.selected["messages"][3] == f.original["messages"][3]
    visible = json.loads(f.selected["messages"][4]["content"])["public_format_feedback"]
    assert visible["reason"] == f.full["reason"] and "contract" not in visible
    archives = measure.archived_reports({"test_reports": {f.report["report_id"]: f.report}}, f.world_events, tmp_path / "state.json")
    row = {"tool": "run_tests", "feedback_id": "test-feedback", "member": "member_001", "arguments": {},
        "originating_call_id": "call-test", "feedback_ok": True, "_value": f.page_value}
    inputs = SimpleNamespace(calls={"call-test": {"call_id": "call-test"}}, messages=lambda call: [f.observation])
    page = measure.page_feedback(row, [measure.point(f.call, 3)], archives, inputs)
    assert page["status"] == "verified" and page["page_actual_inputs"]
    assert page["end"] - page["start"] <= 3072
    assert f.report["pages"][0]["text"] == f.report["body"][page["start"]:page["end"]]


@pytest.mark.parametrize("target", ["saved_source", "saved_state", "declared_source"])
def test_saved_or_declared_lifecycle_cannot_override_independently_reconstructed_state(tmp_path, target):
    f = fixture(tmp_path)
    if target == "declared_source":
        changed = copy.deepcopy(f.projection)
        changed["format_feedback_projection"]["compacted_feedback"][0]["source_call_id"] = "another-call"
        save(f.folder / "projection.json", changed)
    else:
        changed = copy.deepcopy(f.ledger)
        changed["records"][0]["source_event_id" if target == "saved_source" else "state"] = "forged-source-or-state"
        save(f.folder / "feedback-lifecycle-before.json", changed)
    result = audit(f)
    assert result["status"] == "violation"
    expected = "feedback_projection_differs_from_bound_original_event_timeline" if target == "declared_source" else "saved_lifecycle_state_differs_from_original_events"
    assert expected in result["issues"]


def test_nested_protected_source_metadata_must_match_the_same_independent_lifecycle(tmp_path):
    f = fixture(tmp_path)
    # Decode persisted JSON so shared in-memory references cannot accidentally
    # mutate the top-level proof together with this nested copy.
    changed = json.loads((f.folder / "projection.json").read_text())
    changed["protected_projection"]["format_feedback_projection"]["compacted_feedback"][0]["source_call_id"] = "forged-protected-source"
    save(f.folder / "projection.json", changed)
    assert audit(f)["status"] == "violation"


def test_self_consistent_forged_presentation_cannot_remove_latest_unpresented_feedback(tmp_path):
    f = fixture(tmp_path)
    forged = copy.deepcopy(f.ledger)
    forged["records"][0].update(state="superseded", presentations=[{"forged": "not an actual selected/response receipt"}],
                                 transitions=[{"forged": "new rejection"}])
    selected, projection = project(f.original, forged)
    save(f.folder / "selected-request.json", selected)
    save(f.folder / "projection.json", projection)
    save(f.folder / "feedback-lifecycle-before.json", forged)
    f.call.update(selected_request_sha256=digest(json_bytes(selected)), input_ids_sha256=projection["input_ids_sha256"])
    f.record["reservation"]["preparation"]["prompt_tokens"] = projection["selected_prompt_tokens"]
    f.record["charge"]["reported_usage"]["prompt_tokens"] = projection["selected_prompt_tokens"]
    result = audit(f)  # independent f.ledger remains the true pending state
    assert result["status"] == "violation"
    assert "saved_lifecycle_state_differs_from_original_events" in result["issues"]
    assert "feedback_projection_differs_from_bound_original_event_timeline" in result["issues"]


def test_arbitrary_same_named_user_field_cannot_disappear_from_context_stage(tmp_path):
    f = fixture(tmp_path, spoof=True)
    assert audit(f)["status"] == "verified"
    selected, projection = copy.deepcopy(f.selected), copy.deepcopy(f.projection)
    removed = len(selected["messages"]) - 1
    selected["messages"].pop()
    stage = projection["context_stage_projection"]
    stage["selected_indices"].pop()
    stage["removed_indices"].append(removed)
    projection["selected_indices"].pop()
    projection["removed_indices"].append(removed)
    stage["selected_request_sha256"] = projection["selected_request_sha256"] = digest(json_bytes(selected))
    f.call["selected_request_sha256"] = projection["selected_request_sha256"]
    save(f.folder / "selected-request.json", selected)
    save(f.folder / "projection.json", projection)
    result = audit(f)
    assert result["status"] == "violation" and "protected_message_or_partial_round_removed" in result["issues"]


def test_full_feedback_archive_and_visible_compact_denominators_remain_separate(tmp_path):
    f = fixture(tmp_path)
    payload = {"worker_id": "member_001", "call_id": "call-error", "feedback": f.full}
    events = [{"sequence": 20, "kind": "model_format_feedback", "worker_id": "member_001", "payload": payload}]
    inputs = SimpleNamespace(calls={"call-error": {"member": "member_001", "experience_sequence": 10}})
    rows, _ = measure.feedback_saved(events, inputs, tmp_path / "experience.jsonl", f.ledger)
    assert len(rows) == 1 and rows[0]["generated_and_saved"] is True
    assert rows[0]["full_archived_feedback_payload_sha256"] != rows[0]["visible_feedback_payload_sha256"]
    assert measure.matches_feedback(rows[0], f.selected["messages"][4])
    assert not measure.matches_feedback(rows[0], feedback_message(f.full))
    assert rows[0]["feedback_lifecycle"]["state"] == "pending_or_presented"


def block():
    return [{"slot_id": f"slot-{i}", "R": i % 2, "pages_read": i, "messages": i, "births": i,
        "protected_headroom_after_margin_tokens": -500,
        "mechanism_gate_inputs": {"resolved": True, "actual_generated_requests": 1,
            "requests_verified_under_v044": 1, "projection_unresolved": [], "projection_violations": [],
            "page_protocol_violations": [], "feedback_missing_from_first_actual_followup": [], "context_blocked_feedback_ids": []}}
        for i in range(4)]


def test_gate_ignores_r_reading_and_margin_but_stops_real_feedback_execution_defects():
    rows = block()
    assert measure.first_block_gate(rows)["passed"] is True
    for row in rows:
        row.update(R=0, pages_read=0, messages=0, births=0, protected_headroom_after_margin_tokens=-10000)
    assert measure.first_block_gate(rows)["passed"] is True
    for field in ("projection_violations", "page_protocol_violations", "feedback_missing_from_first_actual_followup", "context_blocked_feedback_ids"):
        changed = copy.deepcopy(rows)
        changed[0]["mechanism_gate_inputs"][field] = ["a concrete execution defect"]
        assert measure.first_block_gate(changed)["passed"] is False
    rows[0]["mechanism_gate_inputs"]["requests_verified_under_v044"] = 0
    assert measure.first_block_gate(rows)["passed"] is False


def test_live_style_ledger_before_equals_independent_reduced_original_event_timeline():
    # These are synthetic archived records to test exact equivalence, not a claim
    # that this CPU test made an actual model generation.
    association = {"worker_id": "member_001", "call_id": "call-error", "decision_id": "call-error", "decision_index": 1}
    selected = {"messages": [{"role": "system", "content": "synthetic initial input"}]}
    body = {"id": "synthetic-response", "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        "token_trace": {"input_ids": [1, 2, 3], "output_ids": [4]}, "choices": [{"message": {"role": "assistant", "content": "bad syntax"}}]}
    full = correction(body)
    response = {"http_status": 200, "body": body, "raw_body": json.dumps(body)}
    sources = {"selected": {"path": "/synthetic/selected.json", "sha256": digest(json_bytes(selected)), "bytes": len(json_bytes(selected))},
        "response": {"path": "/synthetic/response.json", "sha256": digest(json_bytes(response)), "bytes": len(json_bytes(response))}}
    attempt = {**association, "stage": "finished", "status": "success", "request": selected, "response": response,
        "accounting": {"usage_status": "reported", "reported_usage": body["usage"]},
        "team_accounting": {"usage_status": "reported_actual_trace", "reported_usage": body["usage"], "charged_tokens": 4,
            "response_id": body["id"], "response_body_sha256": digest(json_bytes(body))}, "will_retry": False}
    events = [{"kind": "model_call", "payload": {**association, "stage": "started"}},
        {"kind": "model_attempt", "payload": attempt},
        {"kind": "model_format_feedback", "payload": {**association, "feedback": full}},
        {"kind": "model_call", "payload": {**association, "call_id": "next-call", "decision_id": "next-call", "decision_index": 2, "stage": "started"}}]
    live = OrdinaryFeedbackLedger()
    reduced = []
    binding = {"selected_request": selected, "selected_input_ids_sha256": digest(json_bytes([1, 2, 3])),
        "selected_request_ref": sources["selected"], "response_ref": sources["response"]}
    for number, event in enumerate(events, 1):
        event.update(sequence=number, worker_id="member_001")
        reduced.append(_brief_lifecycle_event(event, {"experience_sequence": number, "path": "/synthetic/experience.jsonl"}))
        if number == 4:
            live_before = live.snapshot()
        live.observe_event(event["kind"], event["payload"], source_event_id=event_identity(event["kind"], event["payload"]),
            **(binding if event["kind"] == "model_attempt" else {}))
    history = {"requests": [{"call_id": "call-error", "kind": "generated", "selected_request": selected, "response": response,
        "recorded_preparation": {"input_ids_sha256": digest(json_bytes([1, 2, 3]))}, "sources": sources},
        {"call_id": "next-call", "kind": "hard_context_rejected"}], "events": reduced}
    reconstructed = reconstruct_feedback_timeline(history)
    assert reconstructed["before_call"]["next-call"] == live_before
    assert reconstructed["final_snapshot"] == live.snapshot()
    assert reconstructed["independently_bound_actual_generations"] == 1
