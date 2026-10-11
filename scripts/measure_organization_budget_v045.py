"""Read-only binding of preparation before shared admission and a fixed member stop.

A shared decision_consumed record is never itself proof of preparation or a
safe budget stop. Only the original sealed start/stop, member meter, snapshots,
terminal boundary and complete absence of effects establish the new reason.
"""
from __future__ import annotations

import copy
from pathlib import Path
import json

from proworksim.storage import digest, json_bytes

VERSION = "original-member-fixed-budget-attribution-v0.45r2"
REASON = "member_fixed_budget"
OPPORTUNITY_KIND = "organization_work_opportunity_v045"
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
    return {"result": result, "budget": budget, "evidence": evidence, "events": events}


def bind_member_fixed_budget(call_id, *, result, budget, evidence, events):
    """Pure strict proof. Equality at the cap is deliberately not a rejection."""
    record = budget.get("records", {}).get(call_id, {})
    member = record.get("member")
    require(result.get("status") == "closed" and not result.get("boundary", {}).get("execution_integrity_failure")
            and not budget.get("integrity_failure"), "fixed_budget_episode_not_safely_closed")
    require(record == {"call_id": call_id, "member": member, "status": "decision_consumed", "attempt_started": False}
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
            and binding.get("window_id") == prep.get("window_id") == "organization-v045:" + result["slot_id"]
            and bool(binding.get("recipe_sha256")) and binding["recipe_sha256"] == prep.get("recipe_sha256")
            and prep["original_request_sha256"] == sp.get("request_sha256")
            == sp.get("context_selection", {}).get("request_sha256"), "fixed_budget_slot_actor_recipe_or_input_mismatch")
    p, o, c = (prep.get(k) for k in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
    require(type(p) is int and p > 0 and type(o) is int and o == 2048 and type(c) is int and c == 16384
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


def resolve_preparation(call_id, *, start, before, after, result, budget, evidence, events):
    """The ordinary source stays exact; the new source requires the full proof."""
    record = budget["records"][call_id]
    reservation = record.get("reservation", record.get("rejected_reservation", {}))
    proof = None
    if "preparation" not in reservation:
        proof = bind_member_fixed_budget(call_id, result=result, budget=budget, evidence=evidence, events=events)
        require(proof["start_experience_sequence"] == start["sequence"]
                and proof["before_experience_sequence"] == before["sequence"]
                and proof["after_experience_sequence"] == after["sequence"], "fixed_budget_resolver_opportunity_mismatch")
        reservation = proof["reservation"]
    prep = reservation["preparation"]
    require(payload(start).get("reservation") == reservation
            and payload(after)["team_budget"]["records"][call_id] == record,
            "opportunity_budget_or_preparation_mismatch")
    require(sealed(prep, "preparation_sha256") and prep["window_id"] == "organization-v045:" + result["slot_id"]
            and prep["actor_identity"] == result["actor_identity"], "opportunity_preparation_identity_mismatch")
    return {"preparation": copy.deepcopy(prep), "source": "original_start_before_shared_admission" if proof
            else "original_shared_admission_record", "member_fixed_budget_attribution": proof}


def bind_feedback(row, *, result, budget, evidence, events):
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
    proof = bind_member_fixed_budget(payload(start)["call_id"], result=result, budget=budget, evidence=evidence, events=events)
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
