"""Strict v047 capacity, phase allowance and administrative-close provenance.

A shared decision_consumed record is never itself proof of preparation or a
safe budget stop. Only the original sealed start/stop, member meter, snapshots,
terminal boundary and complete absence of effects establish the new reason.
"""
from __future__ import annotations

import copy
from pathlib import Path
import json
import math

from proworksim.storage import digest, json_bytes

VERSION = "original-member-fixed-budget-attribution-v0.47"
REASON = "member_fixed_budget"
OPPORTUNITY_KIND = "organization_work_opportunity_v047"
LIMIT = "max_total_tokens_exact_reservation"
EFFECT_KINDS = {"model_attempt", "model_response", "policy_decision", "tool_call", "model_action_link",
                "model_tool_result", "model_format_feedback", "harness_tool_call"}
INTEGRITY_KINDS = {"process_violation", "execution_integrity_error", "permission_violation", "model_permission_error",
                   "world_integrity_error", "storage_integrity_error"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def one(rows, reason):
    require(len(rows) == 1, reason)
    return rows[0]


def payload(event):
    value = event.get("payload", {})
    return value if isinstance(value, dict) else {}


def sealed(value, field):
    return value.get(field) == digest(json_bytes({k: v for k, v in value.items() if k != field}))


def call_ids(event):
    value = payload(event)
    decision = value.get("decision", {})
    return (value.get("call_id"), value.get("model_call_id"),
            decision.get("model_call_id") if isinstance(decision, dict) else None)


def reference(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": digest(data), "bytes": len(data)}


def read_episode(folder):
    """No raw inference is executed or reconstructed by this reader."""
    folder = Path(folder).resolve()
    result = json.loads((folder / "slot-result.json").read_text())
    evidence = json.loads((folder / "organization-evidence.json").read_text())
    budget = json.loads((folder / "team-budget.json").read_text())["model"]
    require(budget == result["team_budget"]["model"] == evidence["team_budget"]["model"],
            "fixed_budget_saved_ledger_copies_disagree")
    events = [json.loads(line) for line in (folder / "experience.jsonl").read_text().splitlines() if line.strip()]
    sequences = [e.get("sequence") for e in events]
    require(all(type(s) is int for s in sequences) and sequences == sorted(set(sequences)),
            "fixed_budget_experience_order_not_unique")
    capacity_binding = read_capacity_binding(folder, result=result, budget=budget)
    return {"result": result, "budget": budget, "evidence": evidence, "events": events,
        "capacity_binding": capacity_binding}



CONTEXT_LIMIT = 18432
OUTPUT_RESERVATION = 2048
MEMBER_TOKEN_CAP = 500000
CAPACITY_BINDING_VERSION = "software-capacity-binding-v0.46"
PROTECTED_COMPONENTS = {"version", "actor", "critic", "actor_optimizer", "critic_optimizer", "rng_cpu", "rng_cuda",
    "policy_revision", "actor_steps", "critic_steps", "critic_has_nonzero_reward_history", "base_identity",
    "last_window_id", "used_window_ids"}


def valid_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_capacity_binding(binding):
    """Bind the new metadata receipt; the old coordinate receipt stays 16K."""
    require(isinstance(binding, dict) and binding.get("version") == CAPACITY_BINDING_VERSION
            and binding.get("passed") is True, "capacity_binding_missing_or_not_passed")
    require(binding.get("original_context_limit") == 16384 and binding.get("context_limit") == CONTEXT_LIMIT
            and binding.get("reserved_output_tokens") == OUTPUT_RESERVATION,
            "capacity_binding_not_unique_C18432_O2048")
    old, new = binding.get("original_recipe"), binding.get("capacity_recipe")
    require(isinstance(old, dict) and isinstance(new, dict) and old.get("max_length") == 16384
            and old.get("max_output_tokens") == OUTPUT_RESERVATION
            and new == {**old, "max_length": CONTEXT_LIMIT}, "capacity_recipe_changed_beyond_max_length")
    require(binding.get("original_recipe_sha256") == digest(json_bytes(old))
            and binding.get("capacity_recipe_sha256") == digest(json_bytes(new)), "capacity_recipe_hash_mismatch")
    old_profile, new_profile = binding.get("original_inference_profile"), binding.get("capacity_inference_profile")
    require(isinstance(old_profile, dict) and isinstance(new_profile, dict)
            and old_profile.get("max_context_tokens") == 16384
            and new_profile == {**old_profile, "max_context_tokens": CONTEXT_LIMIT},
            "capacity_profile_changed_beyond_max_context_tokens")
    require(binding.get("original_profile_sha256") == digest(json_bytes(old_profile))
            and binding.get("capacity_profile_sha256") == digest(json_bytes(new_profile)), "capacity_profile_hash_mismatch")
    old_identity, new_identity = binding.get("original_actor_identity"), binding.get("capacity_actor_identity")
    require(isinstance(old_identity, dict) and bool(old_identity) and isinstance(new_identity, dict)
            and old_identity.get("inference_profile_sha256") == binding["original_profile_sha256"]
            and new_identity == {**old_identity, "inference_profile_sha256": binding["capacity_profile_sha256"]},
            "capacity_actor_identity_changed_beyond_profile_digest")
    protected = binding.get("protected_components_unchanged", {})
    require(set(protected) == PROTECTED_COMPONENTS and all(value is True for value in protected.values())
            and type(binding.get("new_parameter_updates")) is int and binding["new_parameter_updates"] == 0
            and type(binding.get("new_backward_calls")) is int and binding["new_backward_calls"] == 0,
            "capacity_binding_changed_or_missing_protected_state")
    require(valid_hash(binding.get("before_state_sha256")) and valid_hash(binding.get("after_state_sha256"))
            and binding["before_state_sha256"] != binding["after_state_sha256"],
            "capacity_binding_missing_distinct_metadata_state_receipts")
    return {"version": CAPACITY_BINDING_VERSION, "context_limit": CONTEXT_LIMIT,
        "reserved_output_tokens": OUTPUT_RESERVATION, "recipe_sha256": binding["capacity_recipe_sha256"],
        "profile_sha256": binding["capacity_profile_sha256"], "actor_identity": copy.deepcopy(new_identity),
        "only_capacity_metadata_changed": True, "all_protected_components_unchanged": True}


def validate_episode_capacity(binding, *, result, budget):
    proof = validate_capacity_binding(binding)
    require(result.get("version") == "software-organization-runtime-v0.47"
            and result.get("condition") in {"S1", "D2", "D4", "I2", "I4", "P2", "P4"},
            "episode_not_v047_architecture_runtime")
    require(result.get("team_token_budget") in {250000, 500000}
            and budget.get("limits") == {"max_decisions": 128, "max_attempts": 128,
                                          "max_total_tokens": result["team_token_budget"]},
            "episode_effective_team_budget_not_frozen_v047")
    recorded = budget.get("binding", {})
    require(recorded.get("recipe_sha256") == proof["recipe_sha256"]
            and recorded.get("actor_identity") == result.get("actor_identity") == proof["actor_identity"]
            and recorded.get("window_id") == "organization-v047:" + result["slot_id"],
            "episode_not_bound_to_original_C18432_receipt")
    return proof


def read_capacity_binding(folder, *, result, budget):
    path = Path(folder).resolve().parent.parent / "capacity-binding.json"
    binding = json.loads(path.read_text())
    validate_episode_capacity(binding, result=result, budget=budget)
    return binding


def validate_preparation_capacity(prep, binding):
    proof = validate_capacity_binding(binding)
    require(sealed(prep, "preparation_sha256") and prep.get("context_limit") == CONTEXT_LIMIT
            and prep.get("reserved_output_tokens") == OUTPUT_RESERVATION
            and prep.get("recipe_sha256") == proof["recipe_sha256"]
            and prep.get("actor_identity") == proof["actor_identity"]
            and isinstance(prep.get("window_id"), str)
            and prep["window_id"].startswith("organization-v047:")
            and len(prep["window_id"]) > len("organization-v047:"), "preparation_not_bound_to_C18432_v047_recipe")
    return proof

def bind_member_fixed_budget(call_id, *, result, budget, evidence, events, capacity_binding=None):
    """Pure strict proof. Equality at the cap is deliberately not a rejection."""
    validate_episode_capacity(capacity_binding, result=result, budget=budget)
    record = budget.get("records", {}).get(call_id, {})
    member = record.get("member")
    require(result.get("status") == "closed" and not result.get("boundary", {}).get("execution_integrity_failure")
            and not budget.get("integrity_failure"), "fixed_budget_episode_not_safely_closed")
    require(record == {"call_id": call_id, "member": member, "status": "decision_consumed", "attempt_started": False,
                       "stage_id": record.get("stage_id")}
            and record.get("stage_id") in {stage["stage_id"] for stage in frozen_stage_plan(result["condition"], result["team_token_budget"])}
            and member in budget.get("members", []), "fixed_budget_entered_shared_admission_or_charge")
    start = one([e for e in events if e.get("kind") == "model_call" and call_id in call_ids(e)
                 and payload(e).get("stage") == "started"], "fixed_budget_missing_unique_start")
    stop = one([e for e in events if e.get("kind") == "model_budget_stop" and call_id in call_ids(e)],
               "fixed_budget_missing_unique_stop")
    sp, tp = payload(start), payload(stop)
    opportunity = sp.get("opportunity_id")
    require(isinstance(opportunity, str) and opportunity.startswith("staff-opportunity-"),
            "fixed_budget_missing_original_opportunity")
    boundary = one([e for e in events if e.get("kind") == "model_boundary_error"
                    and (call_id in call_ids(e) or payload(e).get("opportunity_id") == opportunity)],
                   "fixed_budget_missing_unique_boundary")
    ep = payload(boundary)
    require(start.get("worker_id") == stop.get("worker_id") == boundary.get("worker_id") == sp.get("worker_id") == member
            and sp.get("call_id") == sp.get("decision_id") == tp.get("call_id") == ep.get("model_call_id") == call_id
            and ep.get("opportunity_id") == opportunity
            and start["sequence"] < stop["sequence"] < boundary["sequence"], "fixed_budget_call_member_or_order_mismatch")
    reservation = sp.get("reservation", {})
    prep = reservation.get("preparation", {})
    require(bool(prep) and reservation == tp.get("reservation") and sealed(prep, "preparation_sha256"),
            "fixed_budget_missing_or_mismatched_sealed_preparation")
    require(all(isinstance(prep.get(k), str) and len(prep[k]) == 64
                and all(c in "0123456789abcdef" for c in prep[k]) for k in
                ("original_request_sha256", "selected_request_sha256", "rendered_prompt_sha256", "input_ids_sha256")),
            "fixed_budget_missing_original_input_identity")
    binding = budget.get("binding", {})
    require(bool(binding.get("actor_identity")) and binding["actor_identity"] == result.get("actor_identity")
            == prep.get("actor_identity") == sp.get("weight_identity")
            and binding.get("window_id") == prep.get("window_id") == "organization-v047:" + result["slot_id"]
            and bool(binding.get("recipe_sha256")) and binding["recipe_sha256"] == prep.get("recipe_sha256")
            and prep["original_request_sha256"] == sp.get("request_sha256")
            == sp.get("context_selection", {}).get("request_sha256"), "fixed_budget_slot_actor_recipe_or_input_mismatch")
    p, o, c = (prep.get(k) for k in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
    require(type(p) is int and p > 0 and type(o) is int and o == 2048 and type(c) is int and c == 18432
            and type(prep.get("fits")) is bool and prep["fits"] == (p + o <= c),
            "fixed_budget_context_fit_arithmetic_mismatch")
    require(reservation.get("reservation_kind") == "exact_resident_prompt"
            and reservation.get("input_token_reservation") == p and reservation.get("output_token_reservation") == o
            and reservation.get("token_reservation") == p + o, "fixed_budget_exact_reservation_mismatch")
    require(tp.get("limits") == ep.get("limits") == [LIMIT] and ep.get("status") == "model_budget_exhausted"
            and ep.get("budget_kind") is None, "fixed_budget_different_rejection_kind")
    config, meter = sp.get("config", {}), tp.get("meter", {})
    cap = config.get("budget", {}).get("max_total_tokens")
    require(type(cap) is int and cap == 500000 and config.get("backend_id") == "resident_direct"
            and config.get("max_output_tokens") == o and config.get("max_context_tokens") == c,
            "fixed_budget_original_member_cap_or_config_mismatch")
    attempts = evidence.get("original_attempts", [])
    require(len({a.get("call_id") for a in attempts}) == len(attempts), "fixed_budget_duplicate_original_attempt")
    prior = [a for a in attempts if a.get("worker_id") == member and a.get("experience_sequence", -1) < start["sequence"]]
    require(not any(a.get("call_id") == call_id for a in attempts)
            and not any(a.get("worker_id") == member and a.get("experience_sequence", -1) > start["sequence"] for a in attempts),
            "fixed_budget_original_output_or_later_generation_exists")
    charged = 0
    for original in prior:
        old = budget["records"].get(original["call_id"], {})
        charge, usage = old.get("charge", {}), original.get("usage", {})
        require(old.get("member") == member and old.get("attempt_started") is True and old.get("status") == "settled"
                and original.get("status") == "success" and original.get("original_output_present") is True
                and charge.get("usage_status") == "reported_actual_trace" and charge.get("reported_usage") == usage
                and charge.get("response_id") == original.get("response_id") and bool(original.get("response_id"))
                and charge.get("response_body_sha256") == original.get("response_body_sha256")
                and bool(original.get("response_body_sha256"))
                and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                and charge.get("charged_tokens") == usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"],
                "fixed_budget_original_member_charge_not_exact")
        charged += usage["total_tokens"]
    require({k for k, r in budget["records"].items() if r.get("member") == member and r.get("attempt_started") is True}
            == {a["call_id"] for a in prior}, "fixed_budget_member_attempt_inventory_mismatch")
    require(type(meter.get("budget_accounted_tokens")) is int
            and meter["budget_accounted_tokens"] == meter.get("reported_total_tokens") == charged
            and meter.get("http_attempts") == len(prior) and meter.get("unknown_usage_attempts") == 0
            and charged + p + o > cap, "fixed_budget_member_meter_does_not_prove_strict_excess")
    linked = [e for e in events if call_id in call_ids(e)]
    require([(e["kind"], e["sequence"]) for e in linked]
            == [(e["kind"], e["sequence"]) for e in (start, stop, boundary)],
            "fixed_budget_unexpected_attempt_output_or_world_effect")
    require(not any(e.get("kind") in INTEGRITY_KINDS for e in events), "fixed_budget_integrity_fault_present")
    require(not any(e.get("worker_id") == member and e.get("sequence", -1) > start["sequence"]
                    and (e.get("kind") in EFFECT_KINDS or e.get("kind") == "model_call") for e in events),
            "fixed_budget_member_later_generation_or_world_effect")
    snapshots = [e for e in events if e.get("kind") == OPPORTUNITY_KIND
                 and payload(e).get("opportunity_id") == opportunity]
    require(len(snapshots) == 2 and [payload(e).get("phase") for e in snapshots] == ["before", "after"],
            "fixed_budget_missing_original_opportunity_pair")
    before, after = snapshots
    bp, ap = payload(before), payload(after)
    bb, ab = bp.get("team_budget", {}), ap.get("team_budget", {})
    require(before.get("worker_id") == after.get("worker_id") == bp.get("member_id") == ap.get("member_id") == member
            and bp.get("opportunity_ordinal") == ap.get("opportunity_ordinal")
            and before["sequence"] < start["sequence"] < boundary["sequence"] < after["sequence"]
            and bp.get("world_event_sequence") == ap.get("world_event_sequence")
            and type(bp.get("world_event_sequence")) is int
            and ap.get("outcome_status") == "model_budget_exhausted", "fixed_budget_opportunity_or_world_changed")
    require(sealed(bb, "state_sha256") and sealed(ab, "state_sha256") and sealed(budget, "state_sha256")
            and bb.get("binding") == ab.get("binding") == binding
            and not bb.get("integrity_failure") and not ab.get("integrity_failure")
            and call_id not in bb.get("records", {})
            and ab.get("records") == {**bb.get("records", {}), call_id: record}
            and ab.get("decisions") == bb.get("decisions", -1) + 1
            and ab.get("remaining_decisions") == bb.get("remaining_decisions", -1) - 1
            and all(ab.get(k) == bb.get(k) and type(bb.get(k)) is int for k in
                    ("attempts", "charged_tokens", "held_tokens", "available_tokens", "remaining_attempts")),
            "fixed_budget_shared_reservation_charge_or_snapshot_changed")
    terminal = result.get("boundary", {}).get("terminal_details", {}).get(member, {})
    require(terminal.get("status") == result["boundary"].get("role_stops", {}).get(member) == "model_budget_exhausted"
            and terminal.get("cause") == "model_budget_exhausted" and terminal.get("limits") == [LIMIT]
            and all({"sequence": e["sequence"], "kind": e["kind"]} in terminal.get("evidence", []) for e in (stop, boundary)),
            "fixed_budget_terminal_not_bound_to_original_stop")
    return {"version": VERSION, "reason": REASON, "status": "bound_original_member_fixed_budget",
        "slot_id": result["slot_id"], "member": member, "call_id": call_id, "opportunity_id": opportunity,
        "window_id": prep["window_id"], "preparation_source": "original_model_call_started_and_model_budget_stop",
        "preparation": copy.deepcopy(prep), "reservation": copy.deepcopy(reservation),
        "start_experience_sequence": start["sequence"], "stop_experience_sequence": stop["sequence"],
        "boundary_experience_sequence": boundary["sequence"], "before_experience_sequence": before["sequence"],
        "after_experience_sequence": after["sequence"], "member_accounted_tokens": charged,
        "member_fixed_token_cap": cap, "member_available_tokens": cap - charged,
        "shared_available_tokens_before_opportunity": bb["available_tokens"],
        "hard_context_headroom_tokens": c - p - o, "concurrent_hard_context_overflow": p + o > c,
        "recorded_first_refusal": "member_fixed_budget_before_shared_reserve",
        "attempt_started": False, "charged_tokens": 0,
        "actual_output": False, "world_side_effect": False, "later_member_generation": False,
        "actual_feedback_presentation_added": False, "R_used_for_classification": False,
        "member_remains_stopped": True, "shared_ledger_not_rewritten": True}


def resolve_preparation(call_id, *, start, before, after, result, budget, evidence, events, capacity_binding=None):
    """The ordinary source stays exact; the new source requires the full proof."""
    validate_episode_capacity(capacity_binding, result=result, budget=budget)
    record = budget["records"][call_id]
    reservation = record.get("reservation", record.get("rejected_reservation", {}))
    proof = None
    if "preparation" not in reservation:
        proof = bind_member_fixed_budget(call_id, result=result, budget=budget, evidence=evidence, events=events, capacity_binding=capacity_binding)
        require(proof["start_experience_sequence"] == start["sequence"]
                and proof["before_experience_sequence"] == before["sequence"]
                and proof["after_experience_sequence"] == after["sequence"], "fixed_budget_resolver_opportunity_mismatch")
        reservation = proof["reservation"]
    prep = reservation["preparation"]
    validate_preparation_capacity(prep, capacity_binding)
    require(payload(start).get("reservation") == reservation
            and payload(after)["team_budget"]["records"][call_id] == record,
            "opportunity_budget_or_preparation_mismatch")
    require(sealed(prep, "preparation_sha256") and prep["window_id"] == "organization-v047:" + result["slot_id"]
            and prep["actor_identity"] == result["actor_identity"], "opportunity_preparation_identity_mismatch")
    return {"preparation": copy.deepcopy(prep), "source": "original_start_before_shared_admission" if proof
            else "original_shared_admission_record", "member_fixed_budget_attribution": proof}


def bind_feedback(row, *, result, budget, evidence, events, capacity_binding=None):
    """Join the still-unseen original feedback to its member's exact refusal."""
    member, followup = row.get("member"), row.get("no_actual_followup")
    presentation = row.get("presentation", {})
    require(row.get("generated_and_saved") is True and row.get("actual_originating_generation_bound") is True
            and isinstance(followup, dict) and followup.get("reason") == "unknown_no_actual_followup"
            and presentation == {"status": "no_actual_followup", "later_actual_generation_count": 0,
                "first_actual_followup": None, "first_exact_presentation": None,
                "presented_in_first_actual_followup": False, "matching_actual_request_count": 0},
            "fixed_budget_feedback_not_original_unseen_unit")
    start = one([e for e in events if e.get("kind") == "model_call" and payload(e).get("stage") == "started"
                 and e.get("worker_id") == member and e.get("sequence", -1) > row["experience_sequence"]],
                "fixed_budget_feedback_missing_unique_later_preparation")
    proof = bind_member_fixed_budget(payload(start)["call_id"], result=result, budget=budget, evidence=evidence, events=events, capacity_binding=capacity_binding)
    terminal = result["boundary"]["terminal_details"][member]
    require(proof["member"] == member and followup.get("terminal_detail") == terminal,
            "fixed_budget_feedback_terminal_mismatch")
    original = one([a for a in evidence.get("original_attempts", []) if a.get("call_id") == row.get("originating_call_id")],
                   "fixed_budget_feedback_missing_original_generation")
    require(original.get("worker_id") == member and original.get("original_output_present") is True
            and original.get("experience_sequence", start["sequence"]) < row["experience_sequence"] < start["sequence"],
            "fixed_budget_feedback_origin_or_order_mismatch")
    event = one([e for e in events if e.get("sequence") == row["experience_sequence"]], "fixed_budget_feedback_missing_original_event")
    fp = payload(event)
    kind = "model_format_feedback" if row.get("kind") == "format_feedback" else "model_tool_result"
    value = {"public_format_feedback": fp.get("feedback")} if kind == "model_format_feedback" else fp.get("world_response")
    require(event.get("kind") == kind and event.get("worker_id") == member
            and fp.get("call_id") == row.get("originating_call_id")
            and fp.get("model_tool_call_id") == row.get("model_tool_call_id")
            and digest(json_bytes(value)) == row.get("feedback_payload_sha256"), "fixed_budget_feedback_input_or_payload_mismatch")
    return {**proof, "feedback_id": row["feedback_id"], "feedback_experience_sequence": row["experience_sequence"],
            "originating_call_id": row["originating_call_id"], "actual_feedback_unchanged": True}


def frozen_stage_plan(condition, token_budget):
    """Independent audit table, fixed before any pilot model output."""
    require(condition in {"S1", "D2", "D4", "I2", "I4", "P2", "P4"}
            and type(token_budget) is int and token_budget in {250000, 500000},
            "unknown_frozen_architecture_or_budget")
    members = [f"member_{index:03d}" for index in range(1, int(condition[1]) + 1)]
    if condition[0] in "SD":
        values = [("free", members, 100, 128, 32, False)]
    elif condition[0] == "I":
        values = [("generate", members, 70, 88, 24, True), ("select", members[:1], 30, 40, 8, False)]
    elif condition == "P2":
        values = [("implement", members[:1], 60, 76, 20, False),
                  ("review_revise_submit", members[1:], 40, 52, 12, False)]
    else:
        values = [("implement", members[:1], 35, 44, 8, False),
                  ("review", members[1:2], 20, 26, 8, False),
                  ("revise_integrate", members[2:3], 25, 32, 8, False),
                  ("validate_submit", members[3:], 20, 26, 8, False)]
    return [{"stage_id": name, "members": active, "token_percent": percent,
             "limits": {"max_total_tokens": token_budget * percent // 100,
                        "max_decisions": decisions, "max_attempts": decisions, "max_test_runs": tests},
             "equal_member_subpools": independent, "submit_allowed": index == len(values) - 1}
            for index, (name, active, percent, decisions, tests, independent) in enumerate(values)]


def _usage(rows):
    return {"decisions": len(rows), "attempts": sum(row.get("attempt_started") is True for row in rows),
            "charged_tokens": sum(row.get("charge", {}).get("charged_tokens", 0) for row in rows),
            "held_tokens": sum(row.get("reservation", {}).get("token_reservation", 0) for row in rows
                               if row.get("status") in {"reserved", "attempting"})}


def validate_stage_snapshot(snapshot, budget, *, condition, token_budget):
    """Recompute a stage view from its same-time unique whole-team ledger."""
    require(sealed(snapshot, "state_sha256") and sealed(budget, "state_sha256"), "stage_or_team_snapshot_unsealed")
    plan = frozen_stage_plan(condition, token_budget)
    index, member = snapshot.get("stage_index"), snapshot.get("member_id")
    require(type(index) is int and 0 <= index < len(plan), "stage_snapshot_index_invalid")
    stage = plan[index]
    require(snapshot.get("version") == "organization-stage-budget-v0.47"
            and snapshot.get("stage_id") == stage["stage_id"]
            and (member is None or member in stage["members"]), "stage_snapshot_identity_invalid")
    rows = list(budget.get("records", {}).values())
    if stage["equal_member_subpools"]:
        rows = [row for row in rows if row.get("stage_id") == stage["stage_id"]
                and (member is None or row.get("member") == member)]
        divisor = len(stage["members"]) if member is not None else 1
        limits = {key: stage["limits"][key] // divisor for key in ("max_total_tokens", "max_decisions", "max_attempts")}
    else:
        limits = {key: sum(prior["limits"][key] for prior in plan[:index + 1])
                  for key in ("max_total_tokens", "max_decisions", "max_attempts")}
    consumed = _usage(rows)
    pending = sum(row.get("status") == "reserved" for row in rows)
    expected = {**consumed, "limits": limits,
                "remaining_decisions": limits["max_decisions"] - consumed["decisions"],
                "remaining_attempts": limits["max_attempts"] - consumed["attempts"] - pending,
                "available_tokens": limits["max_total_tokens"] - consumed["charged_tokens"] - consumed["held_tokens"]}
    require(all(snapshot.get(key) == value for key, value in expected.items()), "stage_snapshot_not_derived_from_same_team_ledger")
    require(all(snapshot[key] >= 0 for key in ("remaining_decisions", "remaining_attempts", "available_tokens")),
            "stage_snapshot_exceeded_released_allowance")
    return {"stage_id": stage["stage_id"], "member": member, "same_team_ledger_verified": True,
            "forward_only_cumulative_allowance": not stage["equal_member_subpools"], **expected}


def validate_stage_accounting(result, team_budget):
    """Account all stages and generator subpools without transferring budget twice."""
    plan = frozen_stage_plan(result["condition"], result["team_token_budget"])
    model, tests = team_budget["model"], team_budget["tests"]
    require(sealed(model, "state_sha256") and not model.get("integrity_failure"), "stage_accounting_team_ledger_untrusted")
    records = model.get("records", {})
    test_rows = tests.get("records", [])
    known_stages = {stage["stage_id"]: stage for stage in plan}
    for call_id, row in records.items():
        require(row.get("call_id") == call_id and row.get("stage_id") in known_stages
                and row.get("member") in known_stages[row["stage_id"]]["members"], "call_outside_frozen_stage_membership")
    require(tests.get("limit") == 32 and tests.get("used") == len(test_rows)
            and tests.get("remaining") == 32 - len(test_rows), "stage_test_ledger_not_conserved")
    for test in test_rows:
        require(test.get("stage_id") in known_stages
                and test.get("actor_id") in known_stages[test["stage_id"]]["members"], "test_outside_frozen_stage_membership")
    require(_usage(list(records.values())) == {key: model.get(key) for key in ("decisions", "attempts", "charged_tokens", "held_tokens")},
            "phase_totals_do_not_equal_unique_team_ledger")
    summaries = []
    for index, stage in enumerate(plan):
        current = [row for row in records.values() if row["stage_id"] == stage["stage_id"]]
        current_tests = [row for row in test_rows if row["stage_id"] == stage["stage_id"]]
        released = {key: sum(row["limits"][key] for row in plan[:index + 1]) for key in stage["limits"]}
        prefix_ids = {row["stage_id"] for row in plan[:index + 1]}
        prefix = _usage([row for row in records.values() if row["stage_id"] in prefix_ids])
        prefix_tests = sum(row["stage_id"] in prefix_ids for row in test_rows)
        require(prefix["decisions"] <= released["max_decisions"] and prefix["attempts"] <= released["max_attempts"]
                and prefix["charged_tokens"] + prefix["held_tokens"] <= released["max_total_tokens"]
                and prefix_tests <= released["max_test_runs"], "stage_borrowed_from_unreleased_future_allowance")
        by_member = {}
        for member in stage["members"]:
            own = _usage([row for row in current if row["member"] == member])
            own["tests"] = sum(row["actor_id"] == member for row in current_tests)
            if stage["equal_member_subpools"]:
                count = len(stage["members"])
                require(own["decisions"] <= stage["limits"]["max_decisions"] // count
                        and own["attempts"] <= stage["limits"]["max_attempts"] // count
                        and own["charged_tokens"] + own["held_tokens"] <= stage["limits"]["max_total_tokens"] // count
                        and own["tests"] <= stage["limits"]["max_test_runs"] // count,
                        "independent_generator_borrowed_another_subpool")
            by_member[member] = own
        summaries.append({"stage_id": stage["stage_id"], "base_limits": stage["limits"],
                          "released_cumulative_limits": released, "usage_in_this_stage": _usage(current),
                          "tests_in_this_stage": len(current_tests), "cumulative_usage": prefix,
                          "cumulative_tests": prefix_tests, "by_member": by_member})
    return {"version": "organization-stage-accounting-review-v0.47", "passed": True,
            "condition": result["condition"], "team_token_budget": result["team_token_budget"],
            "stages": summaries, "unique_team_charged_tokens": model["charged_tokens"],
            "scope": "Stage costs sum to the single team ledger. Released cumulative allowances do not create a second budget; no unused quota moves backward or across independent candidate subpools."}


def validate_deadline_receipt(result, budget, events):
    """Bind safe administrative closure to original dispatches and final events."""
    receipt = result.get("deadline_receipt")
    require(isinstance(receipt, dict) and receipt.get("version") == "administrative-deadline-v0.47", "missing_v047_deadline_receipt")
    start, soft, hard, closed = (receipt.get(key) for key in (
        "started_monotonic", "soft_deadline_monotonic", "hard_deadline_monotonic", "closed_monotonic"))
    require(all(type(value) in (int, float) and math.isfinite(value) for value in (start, soft, hard, closed))
            and soft == start + 5400 and hard == start + 6000 and start <= closed < hard
            and receipt.get("soft_seconds") == 5400 and receipt.get("hard_seconds") == 6000,
            "deadline_limits_or_closed_time_not_frozen_5400_6000")
    for key in ("no_new_dispatch_after_cutoff", "all_dispatched_attempts_settled", "no_new_stage_after_cutoff",
                "final_submission_locked", "unique_final_acceptance", "closed_before_hard_deadline"):
        require(receipt.get(key) is True, "unsafe_or_incomplete_deadline_receipt:" + key)
    require(receipt.get("hard_deadline_expired") is False, "hard_deadline_expired_not_a_safe_close")
    administrative = result.get("administrative_censoring")
    require(type(administrative) is bool and administrative == receipt.get("actual_soft_cutoff_triggered")
            == receipt.get("cutoff_prevented_remaining_work"), "administrative_censoring_not_bound_to_prevented_work")
    dispatches = receipt.get("dispatches", {})
    attempted = {key: row for key, row in budget.get("records", {}).items() if row.get("attempt_started") is True}
    require(set(dispatches) == set(attempted), "deadline_dispatch_inventory_differs_from_actual_attempts")
    dispatch_events = [event for event in events if event.get("kind") == "organization_model_dispatch_v047"]
    starts = [event for event in dispatch_events if payload(event).get("stage") == "started"]
    returns = [event for event in dispatch_events if payload(event).get("stage") == "returned"]
    require(len(starts) == len(returns) == len(dispatches)
            and not any(payload(event).get("stage") == "failed" for event in dispatch_events), "dispatch_return_inventory_unclosed")
    for call_id, dispatch in dispatches.items():
        row = attempted[call_id]
        beginning = one([event for event in starts if payload(event).get("call_id") == call_id], "dispatch_start_not_unique")
        returned = one([event for event in returns if payload(event).get("call_id") == call_id], "dispatch_return_not_unique")
        sent_at, returned_at = dispatch.get("dispatched_at"), dispatch.get("returned_at")
        require(type(sent_at) in (int, float) and type(returned_at) in (int, float)
                and start <= sent_at < soft and sent_at <= returned_at <= closed
                and payload(beginning).get("monotonic_at") == sent_at
                and payload(returned).get("monotonic_at") == returned_at
                and payload(beginning).get("member_id") == dispatch.get("member_id") == row.get("member")
                and beginning["sequence"] < returned["sequence"] and dispatch.get("status") == "returned"
                and row.get("status") == "settled" and row.get("dispatch_started") is True
                and row.get("charge", {}).get("usage_status") == "reported_actual_trace",
                "dispatch_time_identity_or_settlement_not_bound")
        original = one([event for event in events if event.get("kind") == "model_attempt"
                        and payload(event).get("call_id") == call_id and payload(event).get("stage") == "started"],
                       "missing_exact_actual_attempt_start")
        require(beginning["sequence"] < original["sequence"] < returned["sequence"]
                and payload(original).get("dispatch_boundary") == "v047_exact_native_transport_entry",
                "actual_attempt_not_at_native_dispatch_boundary")
    cancelled = receipt.get("cancelled_before_dispatch", [])
    cancelled_records = {key: row for key, row in budget.get("records", {}).items() if row.get("status") == "cancelled_before_dispatch"}
    require(len(cancelled) == len(cancelled_records)
            and {row.get("call_id") for row in cancelled} == set(cancelled_records), "cancelled_dispatch_inventory_mismatch")
    for cancellation in cancelled:
        call_id = cancellation["call_id"]
        row = cancelled_records[call_id]
        event = one([event for event in dispatch_events if payload(event).get("stage") == "cancelled_before_dispatch"
                     and payload(event).get("call_id") == call_id], "cancelled_dispatch_original_event_missing")
        require(payload(event) == cancellation and administrative and call_id not in dispatches
                and row.get("attempt_started") is False and not row.get("charge") and not row.get("dispatch_started")
                and row.get("cancellation", {}).get("charged_tokens") == 0
                and row.get("cancellation", {}).get("actual_usage") == 0,
                "pre_dispatch_cancellation_contains_attempt_charge_or_no_soft_boundary")
    phase_events = [payload(event) for event in events if event.get("kind") == "organization_stage_transition_v047"]
    require(phase_events == receipt.get("stage_transitions", [])
            and all(start <= transition.get("monotonic_at", hard) < soft for transition in phase_events),
            "stage_started_in_administrative_close_window")
    deadline_events = [event for event in events if event.get("kind") == "organization_deadline_v047"]
    require([payload(event) for event in deadline_events] == receipt.get("events"), "deadline_original_event_history_mismatch")
    locks = [event for event in deadline_events if payload(event).get("kind") == "final_submission_locked"]
    assessments = [event for event in deadline_events if payload(event).get("kind") == "final_assessment_started"]
    closes = [event for event in deadline_events if payload(event).get("kind") == "closed"]
    lock, assessment, close = (one(rows, reason) for rows, reason in ((locks, "final_submission_lock_not_unique"),
        (assessments, "final_assessment_not_unique"), (closes, "safe_closed_event_not_unique")))
    require(lock["sequence"] < assessment["sequence"] < close["sequence"]
            and payload(lock).get("delivery") == receipt.get("locked_submission")
            and payload(close).get("monotonic_at") == closed and receipt.get("final_assessment_calls") == 1,
            "final_lock_acceptance_close_order_or_candidate_mismatch")
    require(result.get("assessment", {}).get("delivery") == receipt.get("locked_submission")
            and result.get("submitted") is (receipt.get("locked_submission") is not None),
            "assessed_candidate_different_from_locked_last_submission")
    triggers = [event for event in deadline_events if payload(event).get("kind") == "soft_cutoff_triggered"]
    require(bool(triggers) == administrative and all(soft <= payload(event).get("monotonic_at", -1) < hard for event in triggers),
            "administrative_censoring_lacks_original_soft_trigger")
    require(not any(event["sequence"] > lock["sequence"] and event.get("kind") in EFFECT_KINDS for event in events),
            "model_or_world_effect_after_final_candidate_lock")
    return {"version": "administrative-close-proof-v0.47", "passed": True,
            "administrative_censoring": administrative, "actual_dispatches": len(dispatches),
            "cancelled_before_dispatch": len(cancelled), "stage_transitions": len(phase_events),
            "locked_submission": copy.deepcopy(receipt.get("locked_submission")),
            "closed_monotonic": closed, "soft_deadline_monotonic": soft, "hard_deadline_monotonic": hard,
            "first_soft_trigger_sequence": triggers[0]["sequence"] if triggers else None,
            "final_lock_sequence": lock["sequence"], "final_guard_closed_sequence": close["sequence"],
            "token_outcomes_censored": administrative}


def bind_stage_rejection(call_id, *, result, budget, events, capacity_binding):
    """An exact phase refusal is local and does not retire or restore a member."""
    row = budget.get("records", {}).get(call_id, {})
    require(row.get("status") == "admission_rejected" and row.get("budget_kind") == "stage_budget"
            and row.get("attempt_started") is False and not row.get("charge") and not row.get("dispatch_started"),
            "stage_refusal_has_dispatch_charge_or_different_kind")
    member = row.get("member")
    reservation = row.get("rejected_reservation", {})
    prep = reservation.get("preparation", {})
    validate_preparation_capacity(prep, capacity_binding)
    require(prep.get("fits") is True and prep.get("window_id") == "organization-v047:" + result["slot_id"]
            and reservation.get("token_reservation") == prep["prompt_tokens"] + 2048,
            "phase_refusal_is_not_exact_fitting_preparation")
    start = one([event for event in events if event.get("kind") == "model_call"
                 and payload(event).get("stage") == "started" and payload(event).get("call_id") == call_id],
                "stage_refusal_missing_original_call_start")
    require(start.get("worker_id") == member and payload(start).get("reservation") == reservation,
            "stage_refusal_start_preparation_mismatch")
    opportunity = payload(start).get("opportunity_id")
    boundary = one([event for event in events if event.get("kind") == "model_boundary_error"
                    and payload(event).get("opportunity_id") == opportunity], "stage_refusal_missing_original_boundary")
    value = payload(boundary)
    require(boundary.get("worker_id") == member and boundary["sequence"] > start["sequence"]
            and value.get("status") == "stage_budget_exhausted" and value.get("budget_kind") == "stage_budget"
            and value.get("limits") == row.get("admission_limits"), "stage_refusal_boundary_mismatch")
    same_time_team, same_time_stage = value.get("team_budget", {}), value.get("stage_budget", {})
    proof = validate_stage_snapshot(same_time_stage, same_time_team,
                                   condition=result["condition"], token_budget=result["team_token_budget"])
    require(same_time_team.get("records", {}).get(call_id) == row
            and same_time_stage.get("stage_id") == row.get("stage_id")
            and same_time_stage.get("member_id") == member, "stage_refusal_original_ledger_mismatch")
    expected = []
    if same_time_stage["remaining_attempts"] <= 0:
        expected.append("stage_max_attempts")
    if reservation["token_reservation"] > same_time_stage["available_tokens"]:
        expected.append("stage_max_total_tokens")
    require(expected and expected == row.get("admission_limits")
            and same_time_team["available_tokens"] >= reservation["token_reservation"]
            and same_time_team["remaining_attempts"] > 0, "stage_refusal_wrong_first_exhausted_pool")
    require(not any(event.get("kind") in EFFECT_KINDS and call_id in call_ids(event) for event in events),
            "stage_refusal_has_actual_attempt_output_or_world_effect")
    return {"version": "stage-reservation-refusal-proof-v0.47", "call_id": call_id, "member": member,
            "stage_id": row["stage_id"], "opportunity_id": opportunity, "stage_budget": proof,
            "preparation": copy.deepcopy(prep), "start_experience_sequence": start["sequence"],
            "boundary_experience_sequence": boundary["sequence"], "attempt_started": False,
            "charged_tokens": 0, "permanent_retirement": False,
            "scope": "Only the current released phase is exhausted. Any future phase needs its own native scheduling; no reset or automatic model work is inferred."}
