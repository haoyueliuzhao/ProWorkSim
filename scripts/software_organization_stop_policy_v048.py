"""v048 representation binding over unchanged v047 local/global stop rules."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from proworksim.software_context_v048 import CANDIDATE_SHA256
from scripts import measure_organization_budget_v047 as capacity
from scripts.software_organization_reporting_v047 import outcome_values
from scripts.software_organization_stop_policy_v047 import (
    GLOBAL_FACTS, PENDING_FACTS, INTEGRITY_KINDS, TECHNICAL_STATUSES,
    EvidenceProblem, bind_context, payload, read, reference, require, snapshot_valid,
)

VERSION = "v048-representation-bound-batch-stop"


def validate_representation(binding, *, row, feedback):
    require(isinstance(binding, dict), "missing_representation_binding", missing=True)
    gamma = binding.get("representation")
    require(binding.get("version") == "v048-representation-slot-binding-v1"
            and binding.get("slot_id") == row.get("slot_id")
            and gamma in {"Gamma0", "Gamma1"}, "representation_slot_or_version_mismatch")
    require(binding.get("candidate", {}).get("sha256") == CANDIDATE_SHA256,
            "wrong_frozen_representation_candidate")
    require(binding.get("transport_library") == ("software_context_v044" if gamma == "Gamma0" else "software_context_v048")
            and binding.get("base_runtime_library") == "software_organization_runtime_v047"
            and binding.get("new_model_qualification_calls") == 0
            and binding.get("world_or_prompt_instruction_changes") is False,
            "representation_runtime_or_scope_mismatch")
    require(feedback.get("representation") == {"representation": gamma, "candidate_sha256": CANDIDATE_SHA256},
            "feedback_representation_not_bound_to_slot")
    if row.get("representation") is not None:
        require(row["representation"] == gamma, "result_representation_differs_from_slot")
    return {"representation": gamma, "candidate_sha256": CANDIDATE_SHA256,
            "base_runtime_library": binding["base_runtime_library"], "passed": True}


def assess_records(row, feedback, team_budget, evidence, guard, events, *, capacity_binding=None, representation_binding=None):
    """Pure CPU policy core. Inputs are original saved records, never modified."""
    result = {"version": VERSION, "slot_id": row.get("slot_id"), "decision": "measurement_pending",
        "read_only": True, "local_context_events": [], "local_stage_events": [], "global_violations": [], "unresolved": [],
        "formal_result": {k: row.get(k) for k in ("status", "R", "R_joint", "R_token", "Q_joint", "Q_token", "submitted", "complete_delivery")},
        "context_blocked_feedback_ids": copy.deepcopy(feedback.get("mechanism_gate_inputs", {}).get("context_blocked_feedback_ids", [])),
        "R_used_for_scope": False, "restart_current_member": False, "feedback_visibility_changed": False,
        "model_visible_Gamma_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
        "new_test_or_acceptance_executions": 0, "new_world_actions": 0, "sources": {},
        "scope": "Continue permits only another independently authorized unstarted slot. Current member/episode treatment and all feedback visibility remain unchanged."}
    bad, pending = result["global_violations"], result["unresolved"]
    try:
        result["representation_binding"] = validate_representation(representation_binding, row=row, feedback=feedback)
    except EvidenceProblem as error:
        (pending if error.missing else bad).append(str(error))
    facts, boundary, budget = feedback.get("mechanism_gate_inputs", {}), row.get("boundary", {}), team_budget.get("model", {})
    if feedback.get("version") != "organization-feedback-opportunities-v0.48" or evidence.get("version") != "software-organization-runtime-v0.47":
        bad.append("wrong_v048_feedback_or_v047_base_evidence_protocol")
    try:
        result["capacity_binding"] = capacity.validate_episode_capacity(capacity_binding, result=row, budget=budget)
    except (KeyError, TypeError, ValueError) as error:
        (pending if capacity_binding is None else bad).append({"capacity_binding_unresolved" if capacity_binding is None else "capacity_binding_violation": str(error)})
    try:
        result["outcome_scope"] = outcome_values(row)
        require(type(row.get("R_joint")) is int and row["R_joint"] in (0, 1)
                and row.get("R") == row["R_joint"] and type(row.get("Q_joint")) in (int, float),
                "joint_result_or_private_quality_missing_or_not_bound", missing=True)
        result["stage_accounting"] = capacity.validate_stage_accounting(row, team_budget)
        result["administrative_close"] = capacity.validate_deadline_receipt(row, budget, events)
    except EvidenceProblem as error:
        (pending if error.missing else bad).append(str(error))
    except (KeyError, TypeError, ValueError) as error:
        (pending if row.get("deadline_receipt") is None else bad).append({"v047_closure_or_phase_proof": str(error)})
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
    if facts.get("actual_generated_requests") != facts.get("requests_verified_under_v048") or type(facts.get("actual_generated_requests")) is not int:
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
        if status not in {"completed", "retired", "model_budget_exhausted", "team_budget_exhausted",
                          "stage_boundary", "stage_budget_exhausted", "administrative_soft_deadline"}:
            bad.append({"untrusted_member_terminal": member, "status": status})
    for event in events:
        ep = payload(event)
        unknown_boundary = event.get("kind") == "model_boundary_error" and ep.get("status") not in {
            "model_budget_exhausted", "team_budget_exhausted", "stage_budget_exhausted"}
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
                and budget.get("binding", {}).get("window_id") == "organization-v047:" + row["slot_id"], "final_actor_or_window_mismatch")
        for call_id, record in records.items():
            prep = record.get("rejected_reservation", {}).get("preparation", {})
            if record.get("budget_kind") == "context_capacity" or prep.get("fits") is False:
                try:
                    result["local_context_events"].append(bind_context(call_id, record, row=row, budget=budget,
                        evidence=evidence, events=events, feedback=feedback))
                except EvidenceProblem as exc:
                    (pending if exc.missing else bad).append({"call_id": call_id, "reason": str(exc)})
            if record.get("budget_kind") == "stage_budget":
                try:
                    result["local_stage_events"].append(capacity.bind_stage_rejection(
                        call_id, result=row, budget=budget, events=events, capacity_binding=capacity_binding))
                except (KeyError, TypeError, ValueError) as error:
                    bad.append({"call_id": call_id, "unbound_stage_refusal": str(error)})
        bound_ids = sorted(f for event in result["local_context_events"] for f in event["context_blocked_feedback_ids"])
        require(bound_ids == sorted(result["context_blocked_feedback_ids"]), "context_feedback_not_uniquely_bound", missing=True)
    except EvidenceProblem as exc:
        (pending if exc.missing else bad).append(str(exc))
    result["decision"] = "global_pause" if bad else "measurement_pending" if pending else "continue"
    result["classification"] = ("safe_administrative_close_token_censored" if row.get("administrative_censoring") is True
        else "safe_local_resource_stop" if result["local_context_events"]
        else "safe_local_stage_boundary" if result["local_stage_events"]
        else "ordinary_closed_episode") if result["decision"] == "continue" else result["decision"]
    return result


def assess_episode(episode_dir, row=None, feedback=None):
    """Read saved artifacts once; do not remeasure history or execute anything."""
    folder = Path(episode_dir).resolve()
    names = {"result": "slot-result.json", "feedback": "feedback-loop.json", "budget": "team-budget.json",
             "evidence": "organization-evidence.json", "guard": "evaluation-guard.json", "experience": "experience.jsonl"}
    try:
        values = {k: read(folder / v) for k, v in names.items() if k != "experience"}
        events = [json.loads(line) for line in (folder / names["experience"]).read_text().splitlines() if line.strip()]
        capacity_binding = read(folder.parent.parent / "capacity-binding.json")
        representation_binding = read(folder / "representation-binding.json")
        candidate = representation_binding["candidate"]
        actual_candidate = reference(candidate["path"])
        candidate_matches = all(actual_candidate.get(key) == value for key, value in candidate.items())
        result = assess_records(values["result"], values["feedback"], values["budget"], values["evidence"], values["guard"], events, capacity_binding=capacity_binding, representation_binding=representation_binding)
        if not candidate_matches:
            result["global_violations"].append("representation_candidate_file_changed")
            result["decision"] = result["classification"] = "global_pause"
        for supplied, saved, label in ((row, values["result"], "result"), (feedback, values["feedback"], "feedback")):
            if supplied is not None and supplied != saved:
                result["global_violations"].append("supplied_" + label + "_differs_from_saved_record")
                result["decision"] = result["classification"] = "global_pause"
        result["sources"] = {key: reference(folder / name) for key, name in names.items()}
        result["sources"]["policy"] = reference(__file__)
        result["sources"]["representation_binding"] = reference(folder / "representation-binding.json")
        result["sources"]["capacity_binding"] = reference(folder.parent.parent / "capacity-binding.json")
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"version": VERSION, "slot_id": (row or {}).get("slot_id", folder.name), "decision": "measurement_pending",
            "classification": "measurement_pending", "read_only": True, "local_context_events": [], "global_violations": [],
            "unresolved": [{"missing_or_unreadable_original_artifact": type(exc).__name__, "reason": str(exc)}],
            "formal_result": None, "context_blocked_feedback_ids": copy.deepcopy((feedback or {}).get("mechanism_gate_inputs", {}).get("context_blocked_feedback_ids", [])),
            "R_used_for_scope": False, "restart_current_member": False, "feedback_visibility_changed": False,
            "model_visible_Gamma_changed": False, "new_model_calls": 0, "new_tokenizer_calls": 0,
            "new_test_or_acceptance_executions": 0, "new_world_actions": 0, "sources": {}}
