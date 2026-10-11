"""Finite CPU controls over original-receipt fixtures; no inference or testing tools."""
import copy

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v045 as proof
from scripts import measure_organization_feedback_v045r2 as feedback


def seal(value, key):
    value.pop(key, None)
    value[key] = digest(json_bytes(value))
    return value


def fixture():
    actor = {"adapter_sha256": "fixture-frozen-actor"}
    binding = {"window_id": "organization-v045:fixture", "actor_identity": actor, "recipe_sha256": "a" * 64}
    prep = seal({**binding, "original_request_sha256": "b" * 64, "selected_request_sha256": "c" * 64,
        "rendered_prompt_sha256": "d" * 64, "input_ids_sha256": "e" * 64,
        "prompt_tokens": 13278, "reserved_output_tokens": 2048, "context_limit": 16384, "fits": True}, "preparation_sha256")
    reservation = {"reservation_kind": "exact_resident_prompt", "preparation": prep,
        "input_token_reservation": 13278, "output_token_reservation": 2048, "token_reservation": 15326}
    usage = {"prompt_tokens": 472198, "completion_tokens": 26364, "total_tokens": 498562}
    attempt = {"call_id": "old", "worker_id": "member_001", "experience_sequence": 1, "status": "success",
        "original_output_present": True, "response_id": "response-old", "response_body_sha256": "f" * 64, "usage": usage}
    charge = {"reported_usage": usage, "charged_tokens": 498562, "usage_status": "reported_actual_trace",
              "response_id": "response-old", "response_body_sha256": "f" * 64}
    before = seal({"binding": binding, "members": ["member_001"], "records": {"old": {"member": "member_001",
        "status": "settled", "attempt_started": True, "charge": charge}}, "decisions": 1, "attempts": 1,
        "charged_tokens": 498562, "held_tokens": 0, "available_tokens": 1438,
        "remaining_decisions": 127, "remaining_attempts": 127}, "state_sha256")
    after = copy.deepcopy(before)
    after["records"]["new"] = {"call_id": "new", "member": "member_001", "status": "decision_consumed", "attempt_started": False}
    after.update(decisions=2, remaining_decisions=126)
    seal(after, "state_sha256")
    op = "staff-opportunity-fixture-2"
    terminal = {"status": "model_budget_exhausted", "cause": "model_budget_exhausted", "limits": [proof.LIMIT],
                "evidence": [{"sequence": 6, "kind": "model_budget_stop"}, {"sequence": 7, "kind": "model_boundary_error"}]}
    def event(seq, kind, p):
        return {"sequence": seq, "kind": kind, "worker_id": "member_001", "payload": p}
    snap = {"member_id": "member_001", "opportunity_id": op, "opportunity_ordinal": 2,
            "world_event_sequence": 1, "availability": {"member_001": {"can_receive_work": True}}}
    events = [event(1, "model_attempt", {"call_id": "old"}),
        event(3, "model_tool_result", {"call_id": "old", "model_tool_call_id": "tool-old", "world_response": {"ok": False}}),
        event(4, proof.OPPORTUNITY_KIND, {**snap, "phase": "before", "team_budget": before}),
        event(5, "model_call", {"call_id": "new", "decision_id": "new", "worker_id": "member_001", "stage": "started",
            "opportunity_id": op, "weight_identity": actor, "reservation": reservation, "request_sha256": "b" * 64,
            "context_selection": {"request_sha256": "b" * 64}, "config": {"backend_id": "resident_direct",
                "max_output_tokens": 2048, "max_context_tokens": 16384, "budget": {"max_total_tokens": 500000}}}),
        event(6, "model_budget_stop", {"call_id": "new", "reservation": copy.deepcopy(reservation), "limits": [proof.LIMIT],
            "meter": {"budget_accounted_tokens": 498562, "reported_total_tokens": 498562, "http_attempts": 1,
                      "unknown_usage_attempts": 0}}),
        event(7, "model_boundary_error", {"model_call_id": "new", "opportunity_id": op,
            "status": "model_budget_exhausted", "limits": [proof.LIMIT]}),
        event(8, proof.OPPORTUNITY_KIND, {**snap, "phase": "after", "team_budget": after, "outcome_status": "model_budget_exhausted"})]
    result = {"slot_id": "fixture", "status": "closed", "R": 0, "submitted": False, "actor_identity": actor,
        "boundary": {"role_stops": {"member_001": "model_budget_exhausted"}, "terminal_details": {"member_001": terminal}}}
    row = {"feedback_id": "feedback-3", "kind": "native_tool_feedback", "tool": "write_file", "member": "member_001",
        "experience_sequence": 3, "originating_call_id": "old", "model_tool_call_id": "tool-old",
        "generated_and_saved": True, "actual_originating_generation_bound": True,
        "feedback_payload_sha256": digest(json_bytes({"ok": False})),
        "presentation": {"status": "no_actual_followup", "later_actual_generation_count": 0, "first_actual_followup": None,
            "first_exact_presentation": None, "presented_in_first_actual_followup": False, "matching_actual_request_count": 0},
        "no_actual_followup": {"reason": "unknown_no_actual_followup", "terminal_detail": terminal}}
    baseline = {"version": "old", "status": "measured", "slot_id": "fixture", "episode_closed": True,
        "feedback_records": [row], "projection_audit": [{"status": "verified"}], "measurement_gaps": [],
        "denominators": {"all_saved_feedback_units": 1, "with_later_actual_generation": 0,
            "without_later_actual_generation": 1, "no_followup_reasons": {"unknown_no_actual_followup": 1},
            "by_tool": {"write_file": {"feedback_units": 1, "no_followup_reasons": {"unknown_no_actual_followup": 1}}}},
        "mechanism_gate_inputs": {"resolved": False, "unresolved_no_followup_ids": ["feedback-3"],
                                  "termination_attribution_unresolved": []}}
    return {"result": result, "budget": after, "evidence": {"original_attempts": [attempt]}, "events": events}, baseline


def test_exact_original_preparation_before_shared_reserve_changes_only_derived_reason():
    original, baseline = fixture()
    frozen = copy.deepcopy((original, baseline))
    value = feedback.revise_records(baseline, **original)
    row = value["feedback_records"][0]
    assert row["no_actual_followup"]["reason"] == "member_fixed_budget"
    assert row["presentation"] == baseline["feedback_records"][0]["presentation"]
    assert value["projection_audit"] == baseline["projection_audit"]
    assert value["denominators"]["all_saved_feedback_units"] == 1
    assert value["mechanism_gate_inputs"]["resolved"] is True
    bound = row["member_fixed_budget_attribution"]
    assert bound["member_available_tokens"] == 1438 and bound["hard_context_headroom_tokens"] == 1058
    assert bound["preparation"] == original["events"][3]["payload"]["reservation"]["preparation"]
    assert (original, baseline) == frozen


def mutate(data, name):
    events, budget = data["events"], data["budget"]
    start, stop, boundary = (events[i]["payload"] for i in (3, 4, 5))
    if name == "equal_cap":
        # Keep all original member charges/meter equal to cap minus reservation.
        used = 500000 - 15326
        a = data["evidence"]["original_attempts"][0]
        a["usage"].update(prompt_tokens=used - 26364, total_tokens=used)
        for ledger in (events[2]["payload"]["team_budget"], budget):
            ledger["records"]["old"]["charge"]["charged_tokens"] = used
            ledger.update(charged_tokens=used, available_tokens=500000-used)
            seal(ledger, "state_sha256")
        stop["meter"].update(budget_accounted_tokens=used, reported_total_tokens=used)
    elif name == "missing_prep":
        start["reservation"].pop("preparation")
    elif name == "mismatch_prep":
        stop["reservation"]["preparation"]["selected_request_sha256"] = "0" * 64
        seal(stop["reservation"]["preparation"], "preparation_sha256")
    elif name == "wrong_slot":
        data["result"]["slot_id"] = "other"
    elif name == "wrong_member":
        events[4]["worker_id"] = "member_002"
    elif name == "wrong_opportunity":
        boundary["opportunity_id"] = "staff-opportunity-other"
    elif name == "wrong_input":
        start["request_sha256"] = "0" * 64
    elif name in {"output", "attempt", "world_effect", "later_generation"}:
        kind = {"output": "model_response", "attempt": "model_attempt", "world_effect": "tool_call",
                "later_generation": "model_response"}[name]
        events.append({"sequence": 9, "kind": kind, "worker_id": "member_001",
                       "payload": {"call_id": "later" if name == "later_generation" else "new"}})
    elif name == "charge":
        budget["records"]["new"]["charge"] = {"charged_tokens": 1}
    elif name == "shared_reservation":
        budget["records"]["new"]["reservation"] = start["reservation"]
    elif name in {"context", "shared", "service"}:
        boundary.update(status="model_service_error" if name == "service" else "model_budget_exhausted",
                        budget_kind="context_capacity" if name == "context" else "shared_total_tokens")
    elif name == "world_sequence":
        events[6]["payload"]["world_event_sequence"] += 1
    elif name == "meter_mismatch":
        stop["meter"]["budget_accounted_tokens"] += 1
    elif name == "broken_snapshot":
        events[2]["payload"]["team_budget"]["available_tokens"] += 1
    elif name == "permission":
        events.append({"sequence": 9, "kind": "permission_violation", "payload": {}})
    else:
        raise AssertionError(name)


@pytest.mark.parametrize("name", ["equal_cap", "missing_prep", "mismatch_prep", "wrong_slot", "wrong_member",
    "wrong_opportunity", "wrong_input", "output", "attempt", "world_effect", "later_generation", "charge",
    "shared_reservation", "context", "shared", "service", "world_sequence", "meter_mismatch", "broken_snapshot", "permission"])
def test_counterexamples_never_become_safe_member_budget(name):
    original, baseline = fixture()
    mutate(original, name)
    with pytest.raises(ValueError):
        proof.bind_member_fixed_budget("new", **original)
    value = feedback.revise_records(baseline, **original)
    assert value["feedback_records"][0]["no_actual_followup"]["reason"] == "unknown_no_actual_followup"
    assert value["mechanism_gate_inputs"]["resolved"] is False
    assert value["member_fixed_budget_revision"]["unresolved"]


def test_actual_followup_without_feedback_is_not_excused_by_budget():
    original, baseline = fixture()
    baseline["feedback_records"][0]["presentation"]["later_actual_generation_count"] = 1
    value = feedback.revise_records(baseline, **original)
    assert value["mechanism_gate_inputs"]["resolved"] is False
    assert value["feedback_records"][0]["presentation"]["later_actual_generation_count"] == 1


def test_fixed_meter_is_first_refusal_even_when_context_would_also_overflow():
    original, baseline = fixture()
    for index in (3, 4):
        reservation = original["events"][index]["payload"]["reservation"]
        reservation.update(input_token_reservation=14500, token_reservation=16548)
        reservation["preparation"].update(prompt_tokens=14500, fits=False)
        seal(reservation["preparation"], "preparation_sha256")
    value = feedback.revise_records(baseline, **original)
    assert value["mechanism_gate_inputs"]["resolved"] is True
    bound = value["feedback_records"][0]["member_fixed_budget_attribution"]
    assert bound["concurrent_hard_context_overflow"] is True
    assert bound["recorded_first_refusal"] == "member_fixed_budget_before_shared_reserve"
    assert bound["hard_context_headroom_tokens"] == -164
