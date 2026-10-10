"""v045 window binding of the unchanged v044r2 batch-stop semantics.

Safe bound local context termination stays local for every formal outcome;
input, permission, identity, accounting and shared-service faults still pause.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes

VERSION = "v045-batch-stop-scope-v044r2"
GLOBAL_FACTS = ("page_protocol_violations", "projection_violations", "feedback_missing_from_first_actual_followup")
PENDING_FACTS = ("page_protocol_unresolved", "projection_unresolved", "unresolved_no_followup_ids",
                 "termination_attribution_unresolved")
INTEGRITY_KINDS = {"execution_integrity_error", "permission_violation", "model_permission_error", "process_violation", "world_integrity_error", "storage_integrity_error"}
TECHNICAL_STATUSES = {"model_service_error", "model_usage_missing", "binding_mismatch", "environment_error",
                      "execution_integrity_error", "model_permission_error"}
EFFECT_KINDS = {"model_attempt", "model_response", "policy_decision", "tool_call", "model_action_link", "model_tool_result", "harness_tool_call"}


def read(path):
    return json.loads(Path(path).read_text())


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def payload(event):
    value = event.get("payload", {})
    return value if isinstance(value, dict) else {}


def snapshot_valid(value):
    return value.get("state_sha256") == digest(json_bytes({k: v for k, v in value.items() if k != "state_sha256"}))


class EvidenceProblem(ValueError):
    def __init__(self, reason, *, missing=False):
        super().__init__(reason)
        self.missing = missing


def require(condition, reason, *, missing=False):
    if not condition:
        raise EvidenceProblem(reason, missing=missing)


def unique(rows, reason):
    require(len(rows) == 1, reason, missing=not rows)
    return rows[0]


def bind_context(call_id, record, *, row, budget, evidence, events, feedback):
    """Bind only the saved rejection, without tokenizing or reconstructing inputs."""
    member = record.get("member")
    require(record.get("call_id") == call_id and member in budget.get("members", []), "rejected_call_or_member_mismatch")
    require(record.get("attempt_started") is False and record.get("status") == "admission_rejected",
            "context_rejection_started_or_not_rejected")
    require(not record.get("charge") and not record.get("reservation"), "context_rejection_has_charge_or_active_reservation")
    reservation = record.get("rejected_reservation", {})
    prep = reservation.get("preparation", {})
    require(bool(prep), "context_preparation_missing", missing=True)
    require(prep.get("preparation_sha256") == digest(json_bytes({k: v for k, v in prep.items() if k != "preparation_sha256"})),
            "context_preparation_hash_mismatch")
    require(all(isinstance(prep.get(k), str) and len(prep[k]) == 64 for k in ("original_request_sha256",
            "selected_request_sha256", "rendered_prompt_sha256", "input_ids_sha256")), "context_request_binding_hash_missing", missing=True)
    p, o, c = (prep.get(k) for k in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
    require(type(p) is int and p > 0 and o == 2048 and c == 16384 and prep.get("fits") is False and p + o > c,
            "not_fixed_hard_context_overflow")
    require(reservation.get("input_token_reservation") == p and reservation.get("output_token_reservation") == o
            and reservation.get("token_reservation") == p + o
            and reservation.get("reservation_kind") == "exact_resident_prompt", "context_reservation_mismatch")
    binding = budget.get("binding", {})
    identity, window = binding.get("actor_identity"), binding.get("window_id")
    require(bool(identity) and identity == row.get("actor_identity") == prep.get("actor_identity"), "context_actor_identity_mismatch")
    require(window == "organization-v045:" + row["slot_id"] and window == prep.get("window_id")
            and binding.get("recipe_sha256") == prep.get("recipe_sha256") and bool(binding.get("recipe_sha256")),
            "context_window_or_recipe_mismatch")
    require(record.get("budget_kind") == "context_capacity" and record.get("admission_limits") == ["context_capacity"],
            "context_rejection_kind_mismatch")
    start = unique([e for e in events if e.get("kind") == "model_call" and payload(e).get("call_id") == call_id
                    and payload(e).get("stage") == "started"], "context_call_start_missing_or_ambiguous")
    sp = payload(start)
    require(start.get("worker_id") == sp.get("worker_id") == member and sp.get("decision_id") == call_id
            and sp.get("weight_identity") == identity and sp.get("reservation") == reservation
            and sp.get("request_sha256") == prep.get("original_request_sha256"), "context_start_binding_mismatch")
    opportunity = sp.get("opportunity_id")
    require(isinstance(opportunity, str) and bool(opportunity), "context_opportunity_missing", missing=True)
    boundary = unique([e for e in events if e.get("kind") == "model_boundary_error"
                       and payload(e).get("opportunity_id") == opportunity], "context_boundary_missing_or_ambiguous")
    bp = payload(boundary)
    require(boundary.get("worker_id") == member and boundary["sequence"] > start["sequence"]
            and bp.get("status") == "model_budget_exhausted" and bp.get("budget_kind") == "context_capacity"
            and bp.get("limits") == ["context_capacity"], "context_boundary_binding_mismatch")
    contemporaneous = bp.get("team_budget", {})
    require(bool(contemporaneous), "context_boundary_snapshot_missing", missing=True)
    require(snapshot_valid(contemporaneous) and contemporaneous.get("binding") == binding
            and contemporaneous.get("records", {}).get(call_id) == record
            and not contemporaneous.get("integrity_failure"), "context_boundary_budget_mismatch")
    available = contemporaneous.get("available_tokens")
    require(type(available) is int and available >= 0, "context_team_available_tokens_not_trusted_nonnegative_integer")
    terminal = row.get("boundary", {}).get("terminal_details", {}).get(member, {})
    require(terminal.get("status") == row.get("boundary", {}).get("role_stops", {}).get(member) == "model_budget_exhausted"
            and terminal.get("cause") == terminal.get("budget_kind") == "context_capacity"
            and terminal.get("generation_started") is False
            and {"sequence": boundary["sequence"], "kind": "model_boundary_error"} in terminal.get("evidence", []),
            "context_member_terminal_mismatch")
    linked = [e for e in events if call_id in (payload(e).get("call_id"), payload(e).get("model_call_id"),
              payload(e).get("decision", {}).get("model_call_id") if isinstance(payload(e).get("decision"), dict) else None)]
    require(not any(e.get("kind") in EFFECT_KINDS or (e.get("kind") == "model_call" and payload(e).get("stage") == "finished")
                    for e in linked), "context_rejection_has_output_attempt_or_execution_effect")
    attempts = evidence.get("original_attempts", [])
    require(not any(a.get("call_id") == call_id for a in attempts), "context_rejection_has_original_output")
    require(not any(a.get("worker_id") == member and a.get("experience_sequence", -1) > start["sequence"] for a in attempts),
            "context_member_has_later_actual_generation")
    require(not any(e.get("worker_id") == member and e.get("sequence", -1) > boundary["sequence"]
                    and e.get("kind") in EFFECT_KINDS | {"model_call"} for e in events), "context_member_restarted_after_boundary")
    affected = []
    for f in feedback.get("feedback_records", []):
        if f.get("member") != member or (f.get("no_actual_followup") or {}).get("reason") != "context_capacity":
            continue
        presentation = f.get("presentation", {})
        require(f.get("generated_and_saved") is True and f.get("actual_originating_generation_bound") is True
                and f.get("experience_sequence", start["sequence"]) < start["sequence"], "context_feedback_source_not_bound")
        require(presentation.get("status") == "no_actual_followup" and presentation.get("later_actual_generation_count") == 0
                and presentation.get("first_actual_followup") is None and presentation.get("first_exact_presentation") is None
                and presentation.get("presented_in_first_actual_followup") is False
                and presentation.get("matching_actual_request_count") == 0, "context_feedback_has_actual_followup_or_presentation")
        require(f.get("no_actual_followup", {}).get("terminal_detail") == terminal, "context_feedback_terminal_mismatch")
        origin = unique([a for a in attempts if a.get("call_id") == f.get("originating_call_id")], "context_feedback_origin_missing_or_ambiguous")
        require(origin.get("worker_id") == member and origin.get("original_output_present") is True
                and origin.get("experience_sequence", start["sequence"]) < f["experience_sequence"], "context_feedback_origin_mismatch")
        original_feedback = unique([e for e in events if e.get("sequence") == f["experience_sequence"]], "context_feedback_event_missing_or_ambiguous")
        fp = payload(original_feedback)
        expected_kind = "model_format_feedback" if f.get("kind") == "format_feedback" else "model_tool_result"
        original_value = {"public_format_feedback": fp.get("feedback")} if expected_kind == "model_format_feedback" else fp.get("world_response")
        require(original_feedback.get("worker_id") == member and original_feedback.get("kind") == expected_kind
                and fp.get("call_id") == f.get("originating_call_id")
                and fp.get("model_tool_call_id") == f.get("model_tool_call_id")
                and digest(json_bytes(original_value)) == f.get("feedback_payload_sha256"), "context_feedback_event_binding_mismatch")
        affected.append(f["feedback_id"])
    return {"classification": "safe_local_resource_stop", "call_id": call_id, "member": member,
        "window_id": window, "opportunity_id": opportunity, "call_experience_sequence": start["sequence"],
        "boundary_experience_sequence": boundary["sequence"], "preparation_sha256": prep["preparation_sha256"],
        "selected_request_sha256": prep.get("selected_request_sha256"), "input_ids_sha256": prep.get("input_ids_sha256"),
        "prompt_tokens": p, "reserved_output_tokens": o, "context_limit": c, "excess_tokens": p + o - c,
        "team_available_tokens_at_rejection": available, "concurrent_team_reservation_shortage": available < p + o,
        "attempt_started": False,
        "new_native_output": False, "charged_tokens": 0, "execution_side_effect": False,
        "context_blocked_feedback_ids": affected, "member_remains_stopped": True,
        "R_used_for_classification": False, "submission_timing_used_for_classification": False}


def assess_records(row, feedback, team_budget, evidence, guard, events):
    """Pure CPU policy core. Inputs are original saved records, never modified."""
    result = {"version": VERSION, "slot_id": row.get("slot_id"), "decision": "measurement_pending",
        "read_only": True, "local_context_events": [], "global_violations": [], "unresolved": [],
        "formal_result": {k: row.get(k) for k in ("status", "R", "submitted", "complete_delivery")},
        "context_blocked_feedback_ids": copy.deepcopy(feedback.get("mechanism_gate_inputs", {}).get("context_blocked_feedback_ids", [])),
        "R_used_for_scope": False, "restart_current_member": False, "feedback_visibility_changed": False,
        "model_visible_Gamma_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0, "new_world_actions": 0, "sources": {},
        "scope": "Continue permits only another independently authorized unstarted slot. Current member/episode treatment and all feedback visibility remain unchanged."}
    bad, pending = result["global_violations"], result["unresolved"]
    facts, boundary, budget = feedback.get("mechanism_gate_inputs", {}), row.get("boundary", {}), team_budget.get("model", {})
    if row.get("status") != "closed" or type(row.get("R")) is not int or row["R"] not in (0, 1):
        pending.append("episode_not_closed_with_formal_binary_result")
    assessment = row.get("assessment", {})
    if assessment.get("status") != "evaluable":
        pending.append("formal_assessment_not_evaluable")
    elif assessment.get("R") != row.get("R") or assessment.get("submitted") != row.get("submitted"):
        bad.append("formal_result_assessment_mismatch")
    if feedback.get("slot_id") != row.get("slot_id") or team_budget.get("slot_id") != row.get("slot_id"):
        bad.append("episode_identity_mismatch")
    if feedback.get("status") != "measured" or feedback.get("episode_closed") is not True or facts.get("resolved") is not True:
        pending.append("frozen_feedback_measurement_unresolved")
    for key in GLOBAL_FACTS:
        if facts.get(key):
            bad.append({key: copy.deepcopy(facts[key])})
    for key in PENDING_FACTS:
        if facts.get(key):
            pending.append({key: copy.deepcopy(facts[key])})
    if feedback.get("measurement_gaps"):
        pending.append({"measurement_gaps": copy.deepcopy(feedback["measurement_gaps"])})
    if facts.get("actual_generated_requests") != facts.get("requests_verified_under_v044") or type(facts.get("actual_generated_requests")) is not int:
        pending.append("actual_input_verification_incomplete")
    for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged"):
        if key not in guard:
            pending.append("missing_guard:" + key)
        elif guard[key] is not True:
            bad.append("failed_guard:" + key)
    if not guard.get("learning_before_sha256") or not guard.get("rng_before_sha256"):
        pending.append("missing_original_guard_hashes")
    if guard.get("learning_before_sha256") != guard.get("learning_after_sha256") or guard.get("rng_before_sha256") != guard.get("rng_after_restore_sha256"):
        bad.append("guard_hash_mismatch")
    if any(row.get(k) != 0 for k in ("actor_updates", "critic_updates", "new_backward_calls")):
        bad.append("frozen_learning_invariant_not_preserved")
    if boundary.get("execution_integrity_failure") or budget.get("integrity_failure"):
        bad.append("execution_or_budget_integrity_failure")
    if row.get("process_violation") or assessment.get("process_violation"):
        bad.append("process_violation")
    for member, status in boundary.get("role_stops", {}).items():
        if status not in {"completed", "retired", "model_budget_exhausted", "team_budget_exhausted"}:
            bad.append({"untrusted_member_terminal": member, "status": status})
    for event in events:
        ep = payload(event)
        unknown_boundary = event.get("kind") == "model_boundary_error" and ep.get("status") not in {"model_budget_exhausted", "team_budget_exhausted"}
        if event.get("kind") in INTEGRITY_KINDS or ep.get("status") in TECHNICAL_STATUSES or unknown_boundary:
            bad.append({"integrity_event": event.get("sequence"), "kind": event.get("kind")})
    try:
        require(bool(budget), "team_budget_missing", missing=True)
        require(snapshot_valid(budget), "final_team_budget_hash_mismatch")
        require(row.get("team_budget") == team_budget == evidence.get("team_budget") == boundary.get("team_budget"), "final_team_budget_copies_disagree")
        usage = row.get("usage", {})
        require(usage == evidence.get("total_usage"), "usage_records_disagree")
        records = budget.get("records", {})
        attempts = evidence.get("original_attempts", [])
        require(len({a.get("call_id") for a in attempts}) == len(attempts), "duplicate_actual_attempt_identity")
        require(usage.get("uncertain_usage_attempts") == 0 and usage.get("attempts") == len(attempts)
                == budget.get("attempts") == facts.get("actual_generated_requests")
                and usage.get("decisions") == budget.get("decisions") == len(records)
                and usage.get("total_tokens") == usage.get("budget_charged_tokens") == budget.get("charged_tokens")
                == sum(r.get("charge", {}).get("charged_tokens", 0) for r in records.values())
                and budget.get("held_tokens") == 0, "episode_accounting_not_closed_and_conserved")
        require(budget.get("binding", {}).get("actor_identity") == row.get("actor_identity")
                and budget.get("binding", {}).get("window_id") == "organization-v045:" + row["slot_id"], "final_actor_or_window_mismatch")
        for call_id, record in records.items():
            prep = record.get("rejected_reservation", {}).get("preparation", {})
            if record.get("budget_kind") == "context_capacity" or prep.get("fits") is False:
                try:
                    result["local_context_events"].append(bind_context(call_id, record, row=row, budget=budget,
                        evidence=evidence, events=events, feedback=feedback))
                except EvidenceProblem as exc:
                    (pending if exc.missing else bad).append({"call_id": call_id, "reason": str(exc)})
        bound_ids = sorted(f for event in result["local_context_events"] for f in event["context_blocked_feedback_ids"])
        require(bound_ids == sorted(result["context_blocked_feedback_ids"]), "context_feedback_not_uniquely_bound", missing=True)
    except EvidenceProblem as exc:
        (pending if exc.missing else bad).append(str(exc))
    result["decision"] = "global_pause" if bad else "measurement_pending" if pending else "continue"
    result["classification"] = ("safe_local_resource_stop" if result["local_context_events"] else "ordinary_closed_episode") if result["decision"] == "continue" else result["decision"]
    return result


def assess_episode(episode_dir, row=None, feedback=None):
    """Read saved artifacts once; do not remeasure history or execute anything."""
    folder = Path(episode_dir).resolve()
    names = {"result": "slot-result.json", "feedback": "feedback-loop.json", "budget": "team-budget.json",
             "evidence": "organization-evidence.json", "guard": "evaluation-guard.json", "experience": "experience.jsonl"}
    try:
        values = {k: read(folder / v) for k, v in names.items() if k != "experience"}
        events = [json.loads(line) for line in (folder / names["experience"]).read_text().splitlines() if line.strip()]
        result = assess_records(values["result"], values["feedback"], values["budget"], values["evidence"], values["guard"], events)
        for supplied, saved, label in ((row, values["result"], "result"), (feedback, values["feedback"], "feedback")):
            if supplied is not None and supplied != saved:
                result["global_violations"].append("supplied_" + label + "_differs_from_saved_record")
                result["decision"] = result["classification"] = "global_pause"
        result["sources"] = {key: reference(folder / name) for key, name in names.items()}
        result["sources"]["policy"] = reference(__file__)
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"version": VERSION, "slot_id": (row or {}).get("slot_id", folder.name), "decision": "measurement_pending",
            "classification": "measurement_pending", "read_only": True, "local_context_events": [], "global_violations": [],
            "unresolved": [{"missing_or_unreadable_original_artifact": type(exc).__name__, "reason": str(exc)}],
            "formal_result": None, "context_blocked_feedback_ids": copy.deepcopy((feedback or {}).get("mechanism_gate_inputs", {}).get("context_blocked_feedback_ids", [])),
            "R_used_for_scope": False, "restart_current_member": False, "feedback_visibility_changed": False,
            "model_visible_Gamma_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
            "new_test_or_acceptance_executions": 0, "new_world_actions": 0, "sources": {}}

