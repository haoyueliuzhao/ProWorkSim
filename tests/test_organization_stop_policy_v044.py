"""CPU contracts for the new host scope; no model/renderer/acceptance fixture."""
import copy
import json

import pytest

from proworksim.storage import digest, json_bytes
from scripts.software_organization_stop_policy_v044 import assess_episode, assess_records


def seal(value, key):
    value[key] = digest(json_bytes({k: v for k, v in value.items() if k != key}))
    return value


def fixture(*, R=1, submitted=True, context=True):
    actor, slot = {"version": "test-shared-identity", "adapter_sha256": "a" * 64}, "org44-test-ST"
    binding = {"actor_identity": actor, "window_id": "organization-v044:" + slot, "recipe_sha256": "b" * 64}
    prep = seal({**binding, "prompt_tokens": 14565, "reserved_output_tokens": 2048, "context_limit": 16384,
        "fits": False, "original_request_sha256": "c" * 64, "selected_request_sha256": "d" * 64,
        "rendered_prompt_sha256": "e" * 64, "input_ids_sha256": "f" * 64}, "preparation_sha256")
    reservation = {"input_token_reservation": 14565, "output_token_reservation": 2048, "token_reservation": 16613,
                   "reservation_kind": "exact_resident_prompt", "preparation": prep}
    old = {"member": "member_001", "call_id": "model-original", "attempt_started": True, "status": "settled",
           "charge": {"charged_tokens": 100}}
    rejection = {"member": "member_001", "call_id": "model-rejected", "status": "admission_rejected", "attempt_started": False,
        "rejected_reservation": reservation, "budget_kind": "context_capacity", "admission_limits": ["context_capacity"]}
    model = {"binding": binding, "members": ["member_001", "member_002"], "records": {"model-original": old},
        "integrity_failure": None, "attempts": 1, "decisions": 1 + int(context), "charged_tokens": 100, "held_tokens": 0,
        "available_tokens": 499900}
    if context:
        model["records"]["model-rejected"] = rejection
    seal(model, "state_sha256")
    team = {"slot_id": slot, "model": model}
    terminal = {"status": "model_budget_exhausted", "cause": "context_capacity", "budget_kind": "context_capacity",
                "generation_started": False, "evidence": [{"sequence": 5, "kind": "model_boundary_error"}]}
    usage = {"attempts": 1, "decisions": 1 + int(context), "total_tokens": 100, "budget_charged_tokens": 100,
             "uncertain_usage_attempts": 0}
    row = {"slot_id": slot, "status": "closed", "R": R, "submitted": submitted, "complete_delivery": bool(R),
        "assessment": {"status": "evaluable", "R": R, "submitted": submitted}, "actor_identity": actor,
        "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0, "process_violation": False, "usage": usage,
        "team_budget": team, "boundary": {"execution_integrity_failure": None, "team_budget": team,
            "role_stops": {"member_001": "model_budget_exhausted" if context else "retired"},
            "terminal_details": {"member_001": terminal} if context else {}}}
    original = {"call_id": "model-original", "worker_id": "member_001", "experience_sequence": 1, "original_output_present": True}
    evidence = {"team_budget": team, "total_usage": usage, "original_attempts": [original]}
    response = {"ok": True, "result": {"test_report": "saved"}}
    feedback = {"slot_id": slot, "status": "measured", "episode_closed": True, "measurement_gaps": [],
        "mechanism_gate_inputs": {"resolved": True, "actual_generated_requests": 1, "requests_verified_under_v044": 1,
            "context_blocked_feedback_ids": ["feedback-2"] if context else []},
        "feedback_records": [{"feedback_id": "feedback-2", "kind": "native_tool_feedback", "member": "member_001",
            "experience_sequence": 2, "originating_call_id": "model-original", "model_tool_call_id": "native-test",
            "generated_and_saved": True, "actual_originating_generation_bound": True,
            "feedback_payload_sha256": digest(json_bytes(response)),
            "no_actual_followup": {"reason": "context_capacity" if context else "voluntary_self_retirement", "terminal_detail": terminal},
            "presentation": {"status": "no_actual_followup", "later_actual_generation_count": 0,
                "first_actual_followup": None, "first_exact_presentation": None,
                "presented_in_first_actual_followup": False, "matching_actual_request_count": 0}}]}
    events = [{"sequence": 2, "worker_id": "member_001", "kind": "model_tool_result",
               "payload": {"call_id": "model-original", "model_tool_call_id": "native-test", "world_response": response}}]
    if context:
        events.extend([{"sequence": 3, "worker_id": "member_001", "kind": "model_call", "payload": {
            "call_id": "model-rejected", "decision_id": "model-rejected", "worker_id": "member_001", "stage": "started",
            "weight_identity": actor, "reservation": reservation, "request_sha256": prep["original_request_sha256"], "opportunity_id": "opportunity-1"}},
            {"sequence": 5, "worker_id": "member_001", "kind": "model_boundary_error", "payload": {
                "opportunity_id": "opportunity-1", "status": "model_budget_exhausted", "budget_kind": "context_capacity",
                "limits": ["context_capacity"], "team_budget": copy.deepcopy(model)}}])
    guard = {"learning_unchanged": True, "rng_restored_exactly": True, "software_binding_unchanged": True,
        "actor_identity_unchanged": True, "learning_before_sha256": {"actor": "a" * 64}, "learning_after_sha256": {"actor": "a" * 64},
        "rng_before_sha256": "1" * 64, "rng_after_restore_sha256": "1" * 64}
    return {"row": row, "feedback": feedback, "team_budget": team, "evidence": evidence, "guard": guard, "events": events}


@pytest.mark.parametrize(("R", "submitted"), [(0, False), (0, True), (1, True)])
def test_local_context_scope_is_outcome_and_submission_independent(R, submitted):
    values = fixture(R=R, submitted=submitted)
    before = copy.deepcopy(values)
    result = assess_records(**values)
    assert result["decision"] == "continue"
    assert result["classification"] == "safe_local_resource_stop"
    assert result["context_blocked_feedback_ids"] == ["feedback-2"]
    assert result["local_context_events"][0]["excess_tokens"] == 229
    assert result["local_context_events"][0]["concurrent_team_reservation_shortage"] is False
    assert result["R_used_for_scope"] is result["restart_current_member"] is result["feedback_visibility_changed"] is False
    assert values == before


@pytest.mark.parametrize("R", [0, 1])
@pytest.mark.parametrize("available", [0, 100])
def test_context_and_team_shortage_are_local_for_both_formal_outcomes(R, available):
    values = fixture(R=R, submitted=bool(R))
    model = values["team_budget"]["model"]
    model["available_tokens"] = available
    model["charged_tokens"] = model["records"]["model-original"]["charge"]["charged_tokens"] = 500000 - available
    values["row"]["usage"].update(total_tokens=500000 - available, budget_charged_tokens=500000 - available)
    seal(model, "state_sha256")
    values["events"][2]["payload"]["team_budget"] = copy.deepcopy(model)
    result = assess_records(**values)
    assert result["decision"] == "continue"
    assert result["classification"] == "safe_local_resource_stop"
    assert result["local_context_events"][0]["concurrent_team_reservation_shortage"] is True
    assert result["context_blocked_feedback_ids"] == ["feedback-2"]


@pytest.mark.parametrize("status", ["worker_waiting", "world_blocked", "team_budget_exhausted"])
def test_frozen_waiting_and_decision_horizon_end_remain_ordinary(status):
    values = fixture(R=0, submitted=False, context=False)
    boundary = values["row"]["boundary"]
    if status == "team_budget_exhausted":
        boundary.update(role_stops={"member_001": status}, waiting_members={}, closure_reason="shared_team_pool_exhausted",
            terminal_details={"member_001": {"status": status, "cause": "shared_team_pool_exhausted", "limits": ["remaining_decisions"]}})
        reason = "team_budget"
    else:
        boundary.update(role_stops={}, waiting_members={"member_001": 2}, closure_reason="no_reachable_future_events",
            terminal_details={"member_001": {"status": status, "cause": "no_reachable_wake_event", "waiting_after_event_sequence": 2}})
        reason = "waiting_without_event"
    values["feedback"]["feedback_records"][0]["no_actual_followup"]["reason"] = reason
    assert assess_records(**values)["decision"] == "continue"


@pytest.mark.parametrize("reason", ["team_budget", "voluntary_end", "voluntary_self_retirement", "waiting_without_event"])
def test_ordinary_resolved_end_continues_other_slots(reason):
    values = fixture(R=0, submitted=False, context=False)
    values["feedback"]["feedback_records"][0]["no_actual_followup"]["reason"] = reason
    assert assess_records(**values)["decision"] == "continue"


@pytest.mark.parametrize("field", ["feedback_missing_from_first_actual_followup", "projection_violations", "page_protocol_violations"])
def test_actual_input_or_page_permission_violation_still_pauses(field):
    values = fixture()
    values["feedback"]["mechanism_gate_inputs"][field] = ["original-violation"]
    result = assess_records(**values)
    assert result["decision"] == "global_pause"
    assert result["context_blocked_feedback_ids"] == ["feedback-2"]


@pytest.mark.parametrize("fault", ["charge", "identity", "started", "world", "output", "later_generation", "service", "unknown_runtime", "guard"])
def test_integrity_fault_never_gets_local_exception(fault):
    values = fixture()
    model = values["team_budget"]["model"]
    if fault == "charge":
        model["records"]["model-rejected"]["charge"] = {"charged_tokens": 1}
        model["charged_tokens"] = values["row"]["usage"]["total_tokens"] = values["row"]["usage"]["budget_charged_tokens"] = 101
    elif fault == "identity":
        values["events"][1]["payload"]["weight_identity"] = {"adapter_sha256": "wrong"}
    elif fault == "started":
        model["records"]["model-rejected"]["attempt_started"] = True
    elif fault in {"world", "output", "later_generation"}:
        values["events"].append({"sequence": 6, "worker_id": "member_001", "kind": "tool_call" if fault == "world" else "model_response" if fault == "output" else "model_call",
            "payload": {"call_id": "model-rejected" if fault != "later_generation" else "model-restarted", "stage": "started"}})
    elif fault in {"service", "unknown_runtime"}:
        values["events"].append({"sequence": 6, "worker_id": "member_002", "kind": "model_boundary_error",
            "payload": {"status": "model_service_error" if fault == "service" else "unknown_runtime_error"}})
    else:
        values["guard"]["software_binding_unchanged"] = False
    seal(model, "state_sha256")
    values["events"][2]["payload"]["team_budget"] = copy.deepcopy(model)
    assert assess_records(**values)["decision"] == "global_pause"


@pytest.mark.parametrize("missing", ["boundary", "preparation", "unclosed", "unverified", "guard_hash"])
def test_missing_proof_stays_measurement_pending(missing):
    values = fixture()
    if missing == "boundary":
        values["events"].pop()
    elif missing == "preparation":
        values["team_budget"]["model"]["records"]["model-rejected"]["rejected_reservation"].pop("preparation")
        seal(values["team_budget"]["model"], "state_sha256")
    elif missing == "unclosed":
        values["row"]["status"] = "running"
    elif missing == "unverified":
        values["feedback"]["mechanism_gate_inputs"]["resolved"] = False
    else:
        for k in ("learning_before_sha256", "learning_after_sha256"):
            values["guard"].pop(k)
    assert assess_records(**values)["decision"] == "measurement_pending"


def test_context_after_format_feedback_retains_original_unseen_record():
    values = fixture()
    row = values["feedback"]["feedback_records"][0]
    original = {"kind": "ordinary_schema_error"}
    row["kind"] = "format_feedback"
    row["model_tool_call_id"] = None
    row["feedback_payload_sha256"] = digest(json_bytes({"public_format_feedback": original}))
    values["events"][0].update(kind="model_format_feedback", payload={"call_id": "model-original", "feedback": original})
    assert assess_records(**values)["decision"] == "continue"


def test_saved_artifacts_api_and_supplied_record_mismatch(tmp_path):
    values = fixture()
    mapping = {"row": "slot-result.json", "feedback": "feedback-loop.json", "team_budget": "team-budget.json",
               "evidence": "organization-evidence.json", "guard": "evaluation-guard.json"}
    for k, name in mapping.items():
        (tmp_path / name).write_text(json.dumps(values[k]))
    (tmp_path / "experience.jsonl").write_text("\n".join(json.dumps(e) for e in values["events"]))
    assert assess_episode(tmp_path)["decision"] == "continue"
    wrong = copy.deepcopy(values["row"])
    wrong["R"] = 0
    assert assess_episode(tmp_path, row=wrong)["decision"] == "global_pause"
    (tmp_path / "evaluation-guard.json").unlink()
    assert assess_episode(tmp_path)["decision"] == "measurement_pending"
