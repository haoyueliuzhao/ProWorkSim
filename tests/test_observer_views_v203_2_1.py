"""CPU-only provenance and completeness controls, not natural-task label accuracy."""
import copy
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from proworksim.software_observer_views_v203_2_1 import (
    AcceptedRequest, INTEGRITY_DIMENSIONS, ObserverViews, assess_integrity,
    make_evidence, validate_stage_assessment,
)


def accepted(request_id="q1", actor="001", accepted_at=10, wire=None, **overrides):
    if wire is None:
        wire = {
            "model": "cpu-scripted",
            "messages": [{"role": "user", "content": json.dumps({
                "observation": {"actor_id": actor, "task_id": "T", "revision": 1,
                                "published_patch": {"patch_id": "p1", "author": "002"},
                                "read_fragment": "Only this literal fragment was presented."},
            })}],
            "tools": [{"type": "function", "function": {"name": "offer_transfer"}}],
        }
    raw = json.dumps(wire, indent=2).encode("utf-8")
    kwargs = {
        "episode_id": "E", "actor": actor, "request_id": request_id,
        "decision_id": f"decision-{request_id}", "accepted_at": accepted_at,
        "raw_request": raw, "request_sha256": hashlib.sha256(raw).hexdigest(),
        "provider_receipt": {"id": f"cpu-response-{request_id}", "usage": {
            "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
        }}, "mode": "cpu_scripted",
    }
    kwargs.update(overrides)
    return AcceptedRequest.from_bytes(**kwargs)


def covered(source):
    return {"expected_sources": [source], "observed_sources": [source],
            "coverage_closed": True, "coverage_evidence": ["frozen-source-inventory"]}


def stage(**updates):
    row = {"episode_id": "E", "actor": "001", "task_id": "T", "task_revision": 1,
           "phase": "T1", "at_time": 10, "request_id": "q1"}
    row.update(updates)
    return row


@pytest.fixture
def views():
    result = ObserverViews("E", ["001", "002"])
    result.add_request(accepted())
    result.add_request(accepted("q2", actor="002", accepted_at=12,
                                wire={"messages": [{"role": "user", "content": "PRIVATE_002"}]}))
    result.add_request(accepted("q3", accepted_at=30,
                                wire={"messages": [{"role": "user", "content": "FUTURE_FINAL_RESULT"}]}))
    result.add_global_event({"episode_id": "E", "event_id": "published", "occurred_at": 5,
                            "payload": {"published": True, "full_source": "UNSEEN_FULL_SOURCE",
                                        "private_state": "GLOBAL_PRIVATE_STATE"}})
    result.add_global_event({"episode_id": "E", "event_id": "future", "occurred_at": 40,
                            "payload": {"result": "FUTURE_OFFICIAL_SCORE"}})
    return result


def test_missing_delivery_preserves_complete_early_ownership():
    report = assess_integrity("E", {
        "ownership": covered("ownership-first-phase"),
        "delivery": {"expected_sources": ["terminal-receipt"], "observed_sources": []},
    }, required_dimensions=("ownership", "delivery"))
    assert report["status"] == "PARTIAL"
    assert report["dimensions"]["ownership"]["status"] == "COMPLETE"
    assert report["analysis_dimensions"] == ["ownership"]
    assert report["dimensions"]["delivery"]["missing_sources"] == ["terminal-receipt"]
    assert not report["dimensions"]["delivery"]["absence_eligible"]


def test_partial_dimension_preserves_available_positive_evidence_not_absence():
    report = assess_integrity("E", {"ownership": {
        "expected_sources": ["early", "late"], "observed_sources": ["early"],
        "coverage_closed": True, "coverage_evidence": ["manifest"],
    }}, required_dimensions=("ownership",))
    dimension = report["dimensions"]["ownership"]
    assert report["status"] == "PARTIAL" and dimension["analysis_eligible"]
    assert dimension["usable_sources"] == ["early"] and not dimension["absence_eligible"]


def test_dimension_corruption_is_local_but_episode_corruption_is_fatal():
    dimensions = {"ownership": covered("early"), "delivery": {
        **covered("terminal"), "invalid_sources": ["terminal"],
    }}
    partial = assess_integrity("E", dimensions, required_dimensions=("ownership", "delivery"))
    assert partial["status"] == "PARTIAL"
    assert partial["dimensions"]["delivery"]["status"] == "INVALID"
    assert not partial["dimensions"]["delivery"]["analysis_eligible"]
    fatal = assess_integrity("E", dimensions, required_dimensions=("ownership", "delivery"),
                             fatal_errors=("episode identity chain compromised",))
    assert fatal["status"] == "INVALID" and not fatal["analysis_dimensions"]


def test_complete_requires_every_required_dimension_and_explicit_coverage():
    all_sources = {name: covered(f"source-{name}") for name in INTEGRITY_DIMENSIONS}
    assert assess_integrity("E", all_sources)["status"] == "COMPLETE"
    assert assess_integrity("E", {"ownership": covered("early")})["status"] == "PARTIAL"
    with pytest.raises(ValueError, match="coverage"):
        assess_integrity("E", {"ownership": {"coverage_closed": True}})
    # No semantic event is a legitimate observation only when its source stream
    # was explicitly closed; an empty unobserved stream remains unknown.
    empty = assess_integrity("E", {}, required_dimensions=("ownership",))
    assert empty["status"] == "PARTIAL" and not empty["analysis_dimensions"]


def test_member_view_never_expands_published_or_global_private_or_future(views):
    view = views.member_view("001", 20).to_dict()
    text = json.dumps(view)
    assert view["request"] == accepted().wire
    assert "published_patch" in text and "Only this literal fragment" in text
    for forbidden in ("UNSEEN_FULL_SOURCE", "PRIVATE_002", "GLOBAL_PRIVATE_STATE",
                      "FUTURE_FINAL_RESULT", "FUTURE_OFFICIAL_SCORE"):
        assert forbidden not in text
    evaluator = views.global_view(20).to_dict()
    assert not evaluator["policy_input_allowed"]
    assert "GLOBAL_PRIVATE_STATE" in json.dumps(evaluator)
    assert "FUTURE_OFFICIAL_SCORE" not in json.dumps(evaluator)


def test_member_view_rejects_other_member_future_unknown_and_wrong_episode(views):
    with pytest.raises(PermissionError):
        views.member_view("001", 20, request_id="q2")
    with pytest.raises(ValueError, match="Future"):
        views.member_view("001", 20, request_id="q3")
    with pytest.raises(PermissionError):
        views.member_view("003", 20)
    with pytest.raises(PermissionError):
        views.add_request(accepted(episode_id="other-episode"))
    assert views.member_view("001", 0).to_dict()["visibility"] == "UNKNOWN"


def test_current_request_projection_does_not_restore_omitted_history(views):
    view = views.member_view("001", 30).to_dict()
    assert view["request_id"] == "q3"
    assert "Only this literal fragment" not in json.dumps(view)
    assert "FUTURE_FINAL_RESULT" in json.dumps(view)
    # Returned JSON can be changed without mutating immutable captured bytes.
    view["request"]["messages"][0]["content"] = "tampered"
    assert views.member_view("001", 30).to_dict()["request"]["messages"][0]["content"] == "FUTURE_FINAL_RESULT"


@pytest.mark.parametrize("overrides", [
    {"request_sha256": "0" * 64},
    {"provider_receipt": {"id": "prepared", "usage": None}},
    {"provider_receipt": {"id": "bad", "usage": {"prompt_tokens": 1,
                                                    "completion_tokens": 2, "total_tokens": 4}}},
    {"mode": "assumed-accepted"},
    {"accepted_at": float("nan")},
])
def test_byte_time_and_provider_acceptance_fail_closed(overrides):
    with pytest.raises(ValueError):
        accepted(**overrides)


def test_ambiguous_json_and_reused_request_identity_are_rejected(views):
    raw = b'{"messages": [], "messages": [{"content": "ambiguous"}]}'
    with pytest.raises(ValueError, match="duplicate"):
        accepted(raw_request=raw, request_sha256=hashlib.sha256(raw).hexdigest())
    views.add_request(accepted())  # Exact duplicate observations are harmless.
    with pytest.raises(ValueError, match="identity"):
        views.add_request(accepted(accepted_at=11))
    views.add_request(accepted("q-same-time", accepted_at=10))
    with pytest.raises(ValueError, match="Tied"):
        views.member_view("001", 10)
    assert views.member_view("001", 10, request_id="q1").accepted_request.request_id == "q1"


def test_evidence_rejects_unseen_source_private_global_and_future(views):
    member = views.member_view("001", 10)
    global_view = views.global_view(10)
    with pytest.raises(PermissionError):
        make_evidence(member, "/events/0/payload")
    with pytest.raises(ValueError):
        make_evidence(member, "/messages/1/content")
    with pytest.raises(PermissionError):
        make_evidence(member, "/messages/0/content", event_id="published")
    with pytest.raises(ValueError):
        make_evidence(global_view, "/payload/result", event_id="future")
    global_ref = make_evidence(global_view, "/payload/full_source", event_id="published")
    with pytest.raises(PermissionError):
        validate_stage_assessment(stage(dependency="PRESENT", dependency_evidence=[global_ref]), member)


def test_assessment_defaults_are_unknown_and_abstain_not_negative(views):
    result = validate_stage_assessment(stage(), views.member_view("001", 10))
    assert result["dependency"] == result["misalignment"] == "UNKNOWN"
    assert result["decision"] == "ABSTAIN"
    assert all(layer["value"] == "UNKNOWN" for layer in result["layers"].values())
    assert result["unknowns_must_not_be_counted_as_negatives"]
    assert result["semantic_truth_not_verified"] and not result["is_permanent_task_label"]
    assert result["world_actions"] == 0
    assert result["source_view_validated"] and result["evidence_mode"] == "cpu_scripted"
    assert result["decision_id"] == "decision-q1"
    with pytest.raises(ValueError):
        validate_stage_assessment(stage(decision="NO_CHANGE"), views.member_view("001", 10))


def test_six_operation_layers_are_independent_and_no_frequency_necessity(views):
    view = views.member_view("001", 10)
    tool_ref = make_evidence(view, "/tools/0/function/name")
    context_ref = make_evidence(view, "/messages/0/content")
    row = stage(operation="offer_transfer", layers={
        "exposure": {"value": "EXPOSED", "evidence": [tool_ref]},
        "preconditions": {"value": "MET", "evidence": [context_ref]},
        "authorization": {"value": "ALLOWED", "evidence": [context_ref]},
        "decision": {"value": "NOT_CALLED", "evidence": [context_ref]},
    })
    result = validate_stage_assessment(row, view)
    assert result["layers"]["necessity"]["value"] == "UNKNOWN"
    assert result["layers"]["outcome"]["value"] == "UNKNOWN"
    assert result["misalignment"] == "UNKNOWN"
    row["layers"]["necessity"] = {
        "value": "NECESSARY", "basis": "tool_call_count", "evidence": [tool_ref],
    }
    with pytest.raises(ValueError, match="never call counts"):
        validate_stage_assessment(row, view)
    row["layers"]["necessity"]["basis"] = "scoped_work_requirement"
    assert validate_stage_assessment(row, view)["semantic_truth_not_verified"]


def test_stage_labels_bind_revision_actor_episode_and_asof_without_backfill(views):
    view = views.member_view("001", 10)
    early = validate_stage_assessment(stage(), view)
    later = validate_stage_assessment(stage(at_time=30, task_revision=2, phase="T6", request_id="q3"),
                                       views.member_view("001", 30))
    assert early["task_revision"] == 1 and later["task_revision"] == 2
    assert early["at_time"] == 10 and later["at_time"] == 30
    for updates in ({"task_revision": None}, {"at_time": 5}, {"episode_id": "other"},
                    {"request_id": "q3"}, {"actor": "002"}, {"decision_id": "other"},
                    {"request_sha256": "0" * 64}, {"evidence_mode": "real_provider"}):
        with pytest.raises((ValueError, PermissionError)):
            validate_stage_assessment(stage(**updates), view)
    future_ref = make_evidence(views.member_view("001", 30), "/messages/0/content")
    with pytest.raises(ValueError):
        validate_stage_assessment(stage(dependency="PRESENT", dependency_evidence=[future_ref]), view)


def test_substantive_decisions_need_scoped_evidence_and_do_not_follow_dependency(views):
    view = views.member_view("001", 10)
    ref = make_evidence(view, "/messages/0/content")
    row = stage(dependency="PRESENT", dependency_evidence=[ref],
                misalignment="ABSENT", misalignment_evidence=[ref],
                decision="NO_CHANGE", decision_evidence=[ref])
    assert validate_stage_assessment(row, view)["decision"] == "NO_CHANGE"
    with pytest.raises(ValueError, match="Dependency alone"):
        validate_stage_assessment({**row, "decision": "INTERVENE"}, view)
    changed = copy.deepcopy(ref)
    changed["value_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not match"):
        validate_stage_assessment({**row, "decision_evidence": [changed]}, view)


def test_global_assessment_is_explicitly_separate_from_member_policy(views):
    view = views.global_view(10)
    ref = make_evidence(view, "/payload/full_source", event_id="published")
    row = stage(view_scope="GLOBAL_EVALUATOR", dependency="PRESENT", dependency_evidence=[ref])
    result = validate_stage_assessment(row, view)
    assert result["view_scope"] == "GLOBAL_EVALUATOR"
    with pytest.raises(PermissionError):
        validate_stage_assessment(row, views.member_view("001", 10))
    with pytest.raises(PermissionError):
        validate_stage_assessment(stage(), view)


def analysis_tool():
    path = Path(__file__).resolve().parents[1] / "tools/analyze_passive_capture_v203_2_1.py"
    spec = importlib.util.spec_from_file_location("passive_capture_analysis_cpu_control", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def captured_controller(tmp_path, *, omit_delivery=False, physical_hash_corrupt=False):
    from proworksim.software_observer_journal_v203_2_1 import ObserverJournal

    controller, host = tmp_path / "controller", tmp_path / "host"
    episode, actor = "E", "001"
    wire = {"messages": [{"role": "user", "content": "public scoped message only"}],
            "tools": [{"type": "function", "function": {"name": "claim_task"}}]}
    response = {"id": "cpu-response", "usage": {
        "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12,
    }}

    def save(relative, value):
        path = controller / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, sort_keys=True) + "\n").encode()
        path.write_bytes(raw)
        return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    request_ref = save("model-ledger/001/request-0001.json", {"request": wire})
    response_ref = save("model-ledger/001/response-0001.json", response)
    save("model-ledger/ledger.json", {"slot_id": episode, "inflight": None,
        "per_member": {actor: {}}, "calls": [{"request_id": "q1", "member_id": actor,
        "request": request_ref, "response": response_ref,
        "usage": response["usage"], "response_id": response["id"]}]})
    association = {"model_call_id": "q1", "model_tool_call_id": "call1", "decision_id": "d1"}
    claim = {"actor": actor, "tool": "claim_task", "arguments": {"task_id": "GLOBAL_TASK_ONLY"},
             "association": association, "response": {"ok": True, "result": {
                 "task_id": "GLOBAL_TASK_ONLY", "owner": actor, "revision": 1, "created_by": actor}}}
    submit = {"actor": actor, "tool": "submit_integration", "arguments": {},
              "association": {**association, "model_tool_call_id": "call2", "decision_id": "d2"},
              "response": {"ok": True, "result": {"delivery_id": "delivery1"}}}
    done = {"actor": actor, "tool": "staff_done", "arguments": {"reason": "complete"},
            "association": {**association, "model_tool_call_id": "call3", "decision_id": "d3"},
            "response": {"ok": True, "worker_state": "done", "reason": "complete", "world_effect": False}}
    actions, outcomes = [claim, submit, done], []
    experience = [{"kind": "model_response", "worker_id": actor, "payload": {
        "service_completion_id": response["id"], "response": response, "decision_id": "sdk-decision-1", "call_id": "sdk-call-1"}}]
    for item in actions:
        decision = {"action": item["tool"], "arguments": item["arguments"], **item["association"]}
        if item is done:
            outcomes.append({"worker_id": actor, "status": "completed", "reason": "complete", "action_performed": False})
        else:
            outcomes.append({"worker_id": actor, "status": "running", "action_performed": True,
                             "decision": decision, "response": item["response"]})
        experience.append({"kind": "policy_decision", "worker_id": actor, "payload": {"decision": decision}})
        experience.append({"kind": "harness_tool_call" if item is done else "tool_call", "worker_id": actor,
                           "payload": {**decision, "response": item["response"]}})
    boundary = {"status": "bounded_work_closed", "closure_reason": "all_members_stopped",
                "initial_members": [actor], "outcomes": outcomes, "actions": 2, "opportunities": 3}
    experience.append({"kind": "run_boundary", "payload": boundary})
    experience_path = controller / "managed-runtime/experience.jsonl"
    experience_path.parent.mkdir(parents=True)
    experience_path.write_text("".join(json.dumps({"sequence": index, **event}) + "\n"
                                       for index, event in enumerate(experience)))
    save("managed-boundary.json", boundary)
    save("controller-result.json", {"status": "closed", "managed_boundary": boundary})
    save("model-ledger/passive-observer/capture-summary.json", {"observer_fault_count": 0})
    with ObserverJournal(controller / "model-ledger/passive-observer/events.sqlite") as journal:
        def append(kind, key, payload, clock):
            journal.append(kind, key, payload, {"episode_id": episode, "capture_time": clock})
        append("INITIAL", "initial", {"episode_id": episode, "fixed_members": [actor],
               "public_initial_message": "public issue", "organization": "REVIEW2", "case_id": "cpu-case"}, 1)
        append("MODEL_REQUEST", "request:q1", {"request_id": "q1", "member_id": actor, "wire": wire}, 2)
        append("MODEL_RESPONSE", "response:q1", {"request_id": "q1", "actor": actor, "body": response}, 3)
        for index, (item, outcome) in enumerate(zip(actions, outcomes)):
            append("INTENT", f"intent:{index}", {key: value for key, value in item.items() if key != "response"}, 4 + index * 3)
            if not (omit_delivery and item is submit):
                append("RECEIPT", f"receipt:{index}", item, 5 + index * 3)
            append("OPPORTUNITY", f"opportunity:{index}", outcome, 6 + index * 3)
        append("BOUNDARY", "boundary", {key: boundary[key] for key in ("status", "closure_reason", "opportunities", "actions")}, 14)
        append("CAPTURE_CLOSED", "closed", {"status": "bounded_work_closed"}, 15)
    context = {"physical_id": "physical1", "logical_id": "q1", "slot_id": episode,
               "member_id": actor, "condition": "cpu", "usage_id": "agent", "attempt_index": 1}
    with ObserverJournal(host / "physical-observer/events.sqlite") as journal:
        for kind, value, clock in (("HTTP_REQUEST", wire, 2.1), ("HTTP_RESPONSE", response, 2.9)):
            raw = json.dumps(value, indent=2).encode()
            journal.append(kind, kind + ":physical1", {
                "raw_base64": base64.b64encode(raw).decode(), "raw_bytes": len(raw),
                "raw_sha256": "0" * 64 if physical_hash_corrupt and kind == "HTTP_REQUEST" else hashlib.sha256(raw).hexdigest(),
                "context": context, "metadata": {"http_status": 200} if kind == "HTTP_RESPONSE" else {},
                "observed_at": clock, "evidence_mode": "cpu_scripted",
            }, {"episode_id": episode})
    return controller, host


def test_postprocess_full_physical_primary_reconciliation_and_read_only(tmp_path):
    controller, host = captured_controller(tmp_path)
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in controller.rglob("*")
              if path.is_file() and not path.name.endswith(("-wal", "-shm"))}
    report = analysis_tool().analyze_capture(controller, "E", host)
    assert report["integrity"]["status"] == "COMPLETE"
    assert report["reconciliation"]["accepted_byte_bound_requests"] == 1
    assert report["accepted_requests"][0]["decision_id"] == "sdk-decision-1"
    assert report["accepted_requests"][0]["decision_id"] != report["accepted_requests"][0]["request_id"]
    assert report["reconciliation"]["independent_runtime_trace_closed"]
    assert report["phases"]["T0"]["observed"] and report["phases"]["T1"]["observed"]
    assert report["phases"]["T6"]["observed"] and not report["phases"]["T2"]["observed"]
    assert report["phases"]["T6"]["global_evaluator_state"]["deliveries"] == []
    assert "GLOBAL_TASK_ONLY" not in json.dumps(report["member_inputs"])
    assert all(row["view_scope"] == "GLOBAL_EVALUATOR" and row["misalignment"] == "UNKNOWN"
               for row in report["stage_assessments"])
    assert report["opportunities"][0]["actor"] == "001"
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in before}
    assert report["new_model_requests"] == report["world_actions_replayed"] == 0


def test_postprocess_missing_delivery_keeps_early_ownership_complete(tmp_path):
    controller, host = captured_controller(tmp_path, omit_delivery=True)
    report = analysis_tool().analyze_capture(controller, "E", host)
    dimensions = report["integrity"]["dimensions"]
    assert report["integrity"]["status"] == "PARTIAL"
    assert dimensions["ownership"]["status"] == "COMPLETE"
    assert dimensions["delivery"]["status"] == "PARTIAL"
    assert not dimensions["delivery"]["absence_eligible"]


def test_postprocess_no_physical_bytes_cannot_claim_complete_requests(tmp_path):
    controller, _ = captured_controller(tmp_path)
    report = analysis_tool().analyze_capture(controller, "E")
    assert report["integrity"]["status"] == "PARTIAL"
    assert report["integrity"]["dimensions"]["requests"]["status"] == "PARTIAL"
    assert report["reconciliation"]["accepted_byte_bound_requests"] == 0
    assert report["member_inputs"] == {}


def test_postprocess_corrupt_physical_bytes_invalidates_requests_not_ownership(tmp_path):
    controller, host = captured_controller(tmp_path, physical_hash_corrupt=True)
    report = analysis_tool().analyze_capture(controller, "E", host)
    assert report["integrity"]["dimensions"]["requests"]["status"] == "INVALID"
    assert report["integrity"]["dimensions"]["ownership"]["status"] == "COMPLETE"
    assert not report["member_inputs"]


def test_postprocess_wrong_episode_is_fatal_and_missing_input_is_partial(tmp_path):
    controller, host = captured_controller(tmp_path)
    wrong = analysis_tool().analyze_capture(controller, "WRONG", host)
    assert wrong["integrity"]["status"] == "INVALID"
    missing = analysis_tool().analyze_capture(tmp_path / "does-not-exist", "E")
    assert missing["integrity"]["status"] == "PARTIAL"
    assert not missing["source_files"]


def test_postprocess_legacy_missing_timestamps_are_not_backfilled(tmp_path):
    from proworksim.software_observer_journal_v203_2_1 import GENESIS, _chain, canonical, sha256

    controller, host = captured_controller(tmp_path)
    path = controller / "model-ledger/passive-observer/events.sqlite"
    # Construct the former valid journal format, which lacked captured times.
    with sqlite3.connect(path) as db:
        previous = GENESIS
        for sequence, raw in db.execute("SELECT sequence,record_json FROM observations ORDER BY sequence").fetchall():
            record = json.loads(raw)
            record["source"].pop("capture_time", None)
            record_hash = sha256(record)
            chain_hash = _chain(sequence, previous, record_hash)
            db.execute("UPDATE observations SET record_json=?,record_sha256=?,previous_sha256=?,chain_sha256=? WHERE sequence=?",
                       (canonical(record), record_hash, previous, chain_hash, sequence))
            previous = chain_hash
    report = analysis_tool().analyze_capture(controller, "E", host)
    assert report["sidecar_journal"]["valid"]
    assert report["integrity"]["status"] == "PARTIAL"
    assert report["integrity"]["dimensions"]["lifecycle"]["status"] == "PARTIAL"
    assert not report["reconciliation"]["sidecar_time_coverage"]
    assert not report["phases"]["T1"]["member_views_available"]
    assert report["member_inputs"] == {}
