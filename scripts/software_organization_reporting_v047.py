"""Planned-denominator reporting for the frozen 44-slot architecture pilot.

No score is inferred from a missing record, no successful-subset cost replaces
the all-slot ledger, and an administrative close never uncensors token-only R.
"""
from __future__ import annotations

from collections import Counter
import math

VERSION = "software-organization-reporting-v0.47"
CONDITIONS = ("S1", "D2", "D4", "I2", "I4", "P2", "P4")
BUDGET_CONDITIONS = ("S1", "D4", "I4", "P4")
ROOTS = ("LA", "HA", "LB", "HB")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _binary(value):
    return type(value) is int and value in (0, 1)


def _score(value):
    return _number(value) and 0 <= value <= 1


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def classify_outcome(row):
    """Keep administrative censoring independent of a known joint acceptance."""
    if not row:
        return "not_started"
    if row.get("status") in {"not_started", "not_started_stopped", "not_started_paused", "queued"}:
        return "not_started"
    if row.get("status") != "closed":
        return "technical_unknown"
    if row.get("administrative_censoring") is True:
        return "administratively_censored"
    if not _binary(row.get("R_token")):
        return "technical_unknown"
    if row["R_token"] == 1:
        return "accepted_complete_delivery"
    if row.get("submitted") is False:
        return "normal_no_submission"
    if row.get("submitted") is True:
        return "submitted_acceptance_failed"
    return "technical_unknown"


def outcome_values(row):
    """Validate explicit outcomes; do not use legacy R to fill missing fields."""
    row = row or {}
    closed = row.get("status") == "closed"
    values = {key: row.get(key) if closed else None for key in ("R_joint", "R_token", "Q_joint", "Q_token")}
    for key in ("R_joint", "R_token"):
        _require(values[key] is None or _binary(values[key]), "nonbinary_" + key)
    for key in ("Q_joint", "Q_token"):
        _require(values[key] is None or _score(values[key]), "nonunit_interval_" + key)
    if row.get("administrative_censoring") is True:
        _require(values["R_token"] is None and values["Q_token"] is None,
                 "administrative_censoring_cannot_be_filled_from_joint_outcome")
    elif closed:
        _require(values["R_joint"] == values["R_token"] and values["Q_joint"] == values["Q_token"],
                 "uncensored_joint_token_outcomes_disagree")
    if row.get("R") is not None and values["R_joint"] is not None:
        _require(row["R"] == values["R_joint"], "legacy_R_must_equal_joint_assessment")
    return values


def _bounds(values, *, binary):
    known = [value for value in values if value is not None]
    count, unknown = len(values), len(values) - len(known)
    total = sum(known)
    return {
        "planned_denominator": count, "known_results": len(known), "unknown_results": unknown,
        "known_successes" if binary else "known_score_sum": total,
        "mean": total / count if count and not unknown else None,
        "identification_interval": [total / count, (total + unknown) / count] if count else None,
        "interval_kind": "unknown-outcome identification bounds, not confidence interval",
    }


def cost_values(row):
    """Return actual consumption and charged reservations as separate quantities."""
    if not row:
        return {"known_actual_tokens": 0, "complete_actual_tokens": None,
                "budget_charged_tokens": None, "uncertain_usage_attempts": None,
                "status": "not_started_no_cost_record"}
    usage = row.get("usage", {})
    known = row.get("known_actual_total_tokens")
    if known is None:
        known = row.get("known_actual_usage", {}).get("total_tokens")
    if known is None and _number(usage.get("total_tokens")):
        # Runtime usage.total_tokens is the sum of reported actual trace usage;
        # unknown reservation charges live in budget_charged_tokens separately.
        known = usage["total_tokens"]
    uncertain = row.get("uncertain_usage_attempts", usage.get("uncertain_usage_attempts"))
    complete = row.get("total_actual_tokens")
    if complete is None and row.get("status") == "closed" and uncertain == 0:
        complete = known
    charged = row.get("budget_charged_tokens", usage.get("budget_charged_tokens"))
    for name, value in (("known_actual_tokens", known), ("complete_actual_tokens", complete),
                        ("budget_charged_tokens", charged), ("uncertain_usage_attempts", uncertain)):
        _require(value is None or type(value) is int and value >= 0, "invalid_" + name)
    if complete is not None:
        _require(uncertain == 0 and complete == known, "complete_actual_usage_with_unresolved_attempt")
    if charged is not None and known is not None:
        _require(charged >= known, "budget_charge_less_than_known_actual_usage")
    return {"known_actual_tokens": known, "complete_actual_tokens": complete,
            "budget_charged_tokens": charged, "uncertain_usage_attempts": uncertain,
            "status": "complete" if complete is not None else "incomplete_or_unstarted"}


def submission_costs(calls, submissions, *, final_submission=None, episode_usage_complete=True):
    """Costs through actual submit calls, including all members, in original order.

    Call rows require call_id, experience_sequence and exact usage. Submission
    rows must already be independently bound to their originating actual call
    and exact fixed version. This helper does not fabricate that binding.
    """
    ordered = sorted(calls, key=lambda row: row["experience_sequence"])
    _require(len({row["call_id"] for row in ordered}) == len(ordered), "duplicate_call_for_submission_cost")
    _require(len({row["experience_sequence"] for row in ordered}) == len(ordered), "ambiguous_call_order")
    cumulative, total = {}, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for call in ordered:
        usage = call["usage"]
        _require(all(type(usage.get(key)) is int and usage[key] >= 0
                     for key in ("prompt_tokens", "completion_tokens", "total_tokens"))
                 and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"],
                 "submission_cost_usage_not_exact")
        total["calls"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total[key] += usage[key]
        cumulative[call["call_id"]] = dict(total)
    fixed = sorted(submissions, key=lambda row: row["sequence"])
    _require(len({row["sequence"] for row in fixed}) == len(fixed), "ambiguous_submit_order")
    boundaries = []
    for submission in fixed:
        _require(submission.get("actual_native_binding_verified") is True
                 and submission.get("call_id") in cumulative
                 and bool(submission.get("source_reference"))
                 and bool(submission.get("patch_id") or submission.get("fixed_patch_ids")),
                 "submission_cost_requires_actual_call_and_exact_fixed_reference")
        boundaries.append({"submission": dict(submission), "through_submission": cumulative[submission["call_id"]]})
    if final_submission is not None:
        _require(bool(fixed) and final_submission == fixed[-1], "final_acceptance_not_locked_to_last_submission")
    last = boundaries[-1] if boundaries else None
    first = boundaries[0] if boundaries else None
    suffix = ({key: total[key] - first["through_submission"][key] for key in total} if first else None)
    return {
        "first_fixed_submission": first, "final_fixed_submission": last,
        "first_submission_present": first is not None, "submission_count": len(fixed),
        "after_first_submission_known_cost": suffix,
        "complete_episode_cost": total if episode_usage_complete else None,
        "known_episode_cost": total,
        "no_submission_terminal_cost_retained": dict(total) if first is None else None,
        "scope": "First fixed submission is not first correct solution. Costs include every member and the submitting call; worker time is not estimated at submission boundaries.",
    }


def aggregate_metrics(plan_units, results):
    """Use the unique prelocked inventory; all cells retain four planned roots."""
    units = list(plan_units)
    ids = [unit["slot_id"] for unit in units]
    _require(len(ids) == len(set(ids)), "duplicate_planned_slot")
    if isinstance(results, dict):
        supplied = dict(results)
    else:
        rows = list(results)
        _require(len({row["slot_id"] for row in rows}) == len(rows), "duplicate_result_slot")
        supplied = {row["slot_id"]: row for row in rows}
    _require(set(supplied) <= set(ids), "result_outside_frozen_inventory")
    cells = {}
    planned = {}
    slots = []
    for unit in units:
        slot, root, condition = unit["slot_id"], unit["root_id"], unit["condition"]
        token_budget = unit["team_token_budget"]
        expected = CONDITIONS if token_budget == 250000 else BUDGET_CONDITIONS if token_budget == 500000 else ()
        _require(root in ROOTS and condition in expected, "unlocked_root_configuration_or_budget")
        key = (token_budget, condition)
        cell = cells.setdefault(key, [])
        _require(root not in {entry["root_id"] for entry in cell}, "duplicate_root_within_cell")
        row = supplied.get(slot)
        if row:
            _require(row.get("slot_id") == slot, "result_key_identity_mismatch")
            for field in ("condition", "team_token_budget", "sampling_seed"):
                _require(row.get(field) == unit[field], "result_plan_mismatch:" + field)
        work = (row or {}).get("work_use", {})
        entry = {"slot_id": slot, "root_id": root, "condition": condition,
                 "team_token_budget": token_budget, "sampling_seed": unit["sampling_seed"],
                 "status": classify_outcome(row), **outcome_values(row), "cost": cost_values(row),
                 "submission_costs": (row or {}).get("submission_costs", work.get("submission_costs")),
                 "member_usage": (row or {}).get("usage_by_member", work.get("cost_accounting", {}).get("by_member")),
                 "member_lifecycle": (row or {}).get("member_lifecycle"),
                 "stage_accounting": (row or {}).get("stage_accounting", work.get("stage_accounting")),
                 "population_measurements": work.get("population_measurements"),
                 "exact_candidate_applications": work.get("exact_candidate_applications"),
                 "work_measurement_status": work.get("status"),
                 "administrative_censoring": (row or {}).get("administrative_censoring"),
                 "termination_cost_retained_without_submission": (row or {}).get("submitted") is False}
        cell.append(entry)
        slots.append(entry)
        planned[(token_budget, condition, root)] = entry
    expected_keys = {(250000, condition) for condition in CONDITIONS} | {(500000, condition) for condition in BUDGET_CONDITIONS}
    _require(set(cells) == expected_keys and all(len(rows) == 4 for rows in cells.values()),
             "require_complete_44_slot_plan_not_result_selected_subset")
    summaries = []
    for (token_budget, condition), rows in sorted(cells.items()):
        costs = [row["cost"] for row in rows]
        complete_costs = [cost["complete_actual_tokens"] for cost in costs]
        summaries.append({
            "condition": condition, "team_token_budget": token_budget, "planned_root_count": 4,
            "outcomes": {key: _bounds([row[key] for row in rows], binary=key.startswith("R"))
                         for key in ("R_joint", "R_token", "Q_joint", "Q_token")},
            "statuses": dict(Counter(row["status"] for row in rows)),
            "known_actual_tokens_all_planned_slots": sum(cost["known_actual_tokens"] or 0 for cost in costs),
            "missing_known_actual_usage_records": sum(cost["known_actual_tokens"] is None for cost in costs),
            "complete_actual_tokens_all_planned_slots": sum(complete_costs) if all(value is not None for value in complete_costs) else None,
            "mean_actual_tokens_per_planned_slot": sum(complete_costs) / 4 if all(value is not None for value in complete_costs) else None,
            "complete_cost_records": sum(value is not None for value in complete_costs),
            "rows": rows,
            "cost_scope": "Every planned slot remains present, including no delivery, censoring, technical unknown and unstarted. Low cost without delivery is not an efficiency win.",
        })
    budget_pairs = []
    for condition in BUDGET_CONDITIONS:
        pairs = []
        for root in ROOTS:
            low, high = planned[(250000, condition, root)], planned[(500000, condition, root)]
            _require(low["sampling_seed"] == high["sampling_seed"], "budget_pair_seed_mismatch")
            delta = {key: high[key] - low[key] if low[key] is not None and high[key] is not None else None
                     for key in ("R_joint", "R_token", "Q_joint", "Q_token")}
            low_cost, high_cost = low["cost"]["complete_actual_tokens"], high["cost"]["complete_actual_tokens"]
            pairs.append({"root_id": root, "low_slot": low["slot_id"], "high_slot": high["slot_id"],
                          "delta": delta, "actual_token_difference": high_cost - low_cost if low_cost is not None and high_cost is not None else None})
        budget_pairs.append({"condition": condition, "pairs": pairs,
                            "mean_delta": {key: sum(pair["delta"][key] for pair in pairs) / 4
                                           if all(pair["delta"][key] is not None for pair in pairs) else None
                                           for key in ("R_joint", "R_token", "Q_joint", "Q_token")}})
    return {"version": VERSION, "planned_slots": 44, "results_supplied": len(supplied),
            "planned_roots": 4, "cells": summaries, "budget_responses": budget_pairs, "slots": slots,
            "Q_definition": "Original private contract checks passed / total for the sole last legal fixed submission; no submission or invalid process gives formal Q_joint=0, technical unknown remains null. Public-test scores are not mixed into Q. Administrative censoring keeps Q_token null.",
            "scope": "Four repeatedly observed authored roots in two related task families; 44 runs are not 44 independent tasks. Slot capacity is a policy treatment, not a fixed actual-member causal effect. No winner or automatic successor is selected."}
