"""Pure accounting for the paired v064 matrix; unknown usage is never zero.

The caller supplies deduplicated immutable per-call receipts, including all
condenser/continuation calls. Monetary reservations are reported separately from
observed usage and from cost calculated from those observed provider receipts.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import statistics

from .software_benchmark_full_plan_v064 import VERSION as PLAN_VERSION

VERSION = "v064-actual-usage-and-outcomes-r1"
TERMINAL = frozenset(("closed", "technical_unknown", "interface_unsupported"))
STATES = TERMINAL | {"not_started", "running"}


def integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + " must be an explicit nonnegative integer")
    return value


def optional_integer(value, label):
    return None if value is None else integer(value, label)


def money(value, label):
    if value is None:
        return None
    if not isinstance(value, (str, int, Decimal)) or type(value) is bool:
        raise ValueError(label + " must be an exact decimal string, integer, or null")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(label + " is not a decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError(label + " must be finite and nonnegative")
    return result


def normalize_usage_call(call_id, purpose, usage, *, accounted_cost_cny=None):
    """Normalize only explicit provider counts; do not invent missing details."""
    prompt = integer(usage.get("prompt_tokens"), "prompt_tokens")
    completion = integer(usage.get("completion_tokens"), "completion_tokens")
    if "total_tokens" in usage and integer(usage["total_tokens"], "total_tokens") != prompt + completion:
        raise ValueError("Provider total differs from prompt plus completion")
    details = usage.get("completion_tokens_details")
    if details is not None and not isinstance(details, dict):
        raise ValueError("Malformed completion token detail")
    value = {
        "call_id": call_id,
        "purpose": purpose,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "reasoning_tokens": (details or {}).get("reasoning_tokens"),
        "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
        "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens"),
        "accounted_cost_cny": accounted_cost_cny,
    }
    return validate_call(value)


def validate_call(call):
    if not isinstance(call, dict) or any(not isinstance(call.get(key), str) or not call[key]
                                         for key in ("call_id", "purpose")):
        raise ValueError("Each settled call requires a unique call_id and purpose")
    prompt = integer(call.get("prompt_tokens"), "prompt_tokens")
    completion = integer(call.get("completion_tokens"), "completion_tokens")
    reasoning = optional_integer(call.get("reasoning_tokens"), "reasoning_tokens")
    hit = optional_integer(call.get("prompt_cache_hit_tokens"), "prompt_cache_hit_tokens")
    miss = optional_integer(call.get("prompt_cache_miss_tokens"), "prompt_cache_miss_tokens")
    if reasoning is not None and reasoning > completion:
        raise ValueError("Reasoning is a subset of completion tokens")
    if (hit is not None and hit > prompt) or (miss is not None and miss > prompt):
        raise ValueError("Cache counts are subsets of prompt tokens")
    if hit is not None and miss is not None and hit + miss != prompt:
        raise ValueError("Reported cache hit plus miss differs from prompt tokens")
    cost = money(call.get("accounted_cost_cny"), "accounted_cost_cny")
    return {**call, "prompt_tokens": prompt, "completion_tokens": completion,
            "reasoning_tokens": reasoning, "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": miss,
            "accounted_cost_cny": str(cost) if cost is not None else None}


def validate_unresolved(call):
    if not isinstance(call.get("call_id"), str) or not call["call_id"]:
        raise ValueError("An unresolved call requires a stable call_id")
    reserved = integer(call.get("reserved_tokens"), "reserved_tokens")
    cost = money(call.get("reserved_cost_cny"), "reserved_cost_cny")
    return {**call, "reserved_tokens": reserved,
            "reserved_cost_cny": str(cost) if cost is not None else None}


def episode_record(slot, record):
    """A missing record is unentered, not a successful zero-cost episode."""
    if record is None:
        return {"slot_id": slot["slot_id"], "entered": False, "generation_state": "not_started",
                "not_started_reason": "no_entered_record", "code_result": None,
                "code_status": "pending", "delivery_result": None,
                "usage_capture_complete": False, "calls": [], "unresolved_calls": [],
                "usage_final_for_episode": False}
    if record.get("slot_id") != slot["slot_id"]:
        raise ValueError("Episode record belongs to another slot")
    for key in ("group_id", "instance_id", "model_key", "arm"):
        if key in record and record[key] != slot[key]:
            raise ValueError("Episode record identity differs from the fixed matrix")
    state = record.get("generation_state")
    entered = record.get("entered")
    complete = record.get("usage_capture_complete")
    if state not in STATES or type(entered) is not bool or type(complete) is not bool:
        raise ValueError("Explicit generation, entry and usage-capture states are required")
    if (state == "not_started" and entered) or (state in {"running", "closed"} and not entered):
        raise ValueError("Generation state conflicts with entry state")
    calls = [validate_call(call) for call in record.get("calls", [])]
    unknown = [validate_unresolved(call) for call in record.get("unresolved_calls", [])]
    names = [call["call_id"] for call in calls + unknown]
    if len(names) != len(set(names)):
        raise ValueError("A call may be counted once and cannot be both settled and unresolved")
    if not entered and (calls or unknown):
        raise ValueError("An unentered episode cannot have model calls")
    if complete and unknown:
        raise ValueError("Unknown billed usage cannot be marked complete")
    result, delivery = record.get("code_result"), record.get("delivery_result")
    if any(value is not None and type(value) is not bool for value in (result, delivery)):
        raise ValueError("Code and delivery endpoints must be boolean or unknown")
    status = record.get("code_status", "pending")
    if status not in {"scored", "pending", "technical_unknown", "interface_unsupported"}:
        raise ValueError("Unrecognized code endpoint state")
    if (result is not None and (status != "scored" or state not in TERMINAL or not entered)) or (
            status == "scored" and result is None):
        raise ValueError("Official resolved status must have a terminal entered candidate and known report")
    if slot["arm"] != "PROJECT" and delivery is not None:
        raise ValueError("REF has no project delivery endpoint; do not fill zero")
    if delivery is not None and (not entered or state not in TERMINAL):
        raise ValueError("Delivery requires a terminal entered PROJECT episode")
    return {**record, "calls": calls, "unresolved_calls": unknown,
            "code_status": status, "code_result": result, "delivery_result": delivery,
            "usage_final_for_episode": entered and state in TERMINAL and complete and not unknown}


def call_totals(calls):
    prompt = sum(call["prompt_tokens"] for call in calls)
    completion = sum(call["completion_tokens"] for call in calls)
    value = {"settled_calls": len(calls), "prompt_tokens": prompt,
             "completion_tokens": completion, "input_plus_output_tokens": prompt + completion}
    for key in ("reasoning_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        known = [call[key] for call in calls if call[key] is not None]
        value[key + "_known"] = sum(known)
        value[key + "_missing_calls"] = len(calls) - len(known)
        value[key + "_if_all_reported"] = sum(known) if len(known) == len(calls) else None
    costs = [money(call["accounted_cost_cny"], "accounted_cost_cny") for call in calls]
    value["accounted_cost_cny_known"] = str(sum((cost for cost in costs if cost is not None), Decimal(0)))
    value["accounted_cost_missing_calls"] = sum(cost is None for cost in costs)
    return value


def distribution(values):
    values = list(values)
    return {"episodes": len(values), "sum": sum(values),
            "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "minimum": min(values) if values else None, "maximum": max(values) if values else None}


def usage_summary(records):
    calls = [call for record in records for call in record["calls"]]
    unresolved = [call for record in records for call in record["unresolved_calls"]]
    entered = [record for record in records if record["entered"]]
    final = [record for record in records if record["usage_final_for_episode"]]
    closed_final = [record for record in final if record["generation_state"] == "closed"]
    def amount(row):
        return sum(call["prompt_tokens"] + call["completion_tokens"] for call in row["calls"])
    known_total = call_totals(calls)
    full = len(final) == len(records) and bool(records)
    return {
        "planned_episodes": len(records), "entered_episodes": len(entered),
        "unentered_episodes": len(records) - len(entered),
        "closed_generation_episodes": sum(row["generation_state"] == "closed" for row in records),
        "generation_states": dict(Counter(row["generation_state"] for row in records)),
        "unentered_reasons": dict(Counter(row.get("not_started_reason", "not_recorded")
                                          for row in records if not row["entered"])),
        "usage_final_episodes": len(final),
        "entered_usage_not_final_episodes": len(entered) - len(final),
        "known_usage_all_entered_including_unknown_outcomes": known_total,
        "actual_tokens_final_usage_episodes": distribution(amount(row) for row in final),
        "actual_prompt_tokens_final_usage_episodes": distribution(
            sum(call["prompt_tokens"] for call in row["calls"]) for row in final),
        "actual_completion_tokens_final_usage_episodes": distribution(
            sum(call["completion_tokens"] for call in row["calls"]) for row in final),
        "actual_tokens_closed_final_usage_episodes": distribution(amount(row) for row in closed_final),
        "actual_average_tokens_full_planned_group": known_total["input_plus_output_tokens"] / len(records) if full else None,
        "actual_average_prompt_tokens_full_planned_group": known_total["prompt_tokens"] / len(records) if full else None,
        "actual_average_completion_tokens_full_planned_group": known_total["completion_tokens"] / len(records) if full else None,
        "known_tokens_divided_by_entered_lower_bound": known_total["input_plus_output_tokens"] / len(entered) if entered else None,
        "known_tokens_divided_by_planned_lower_bound": known_total["input_plus_output_tokens"] / len(records) if records else None,
        "unresolved_calls": len(unresolved),
        "uncertain_reserved_tokens_not_actual": sum(call["reserved_tokens"] for call in unresolved),
        "uncertain_reserved_cost_cny_not_actual": str(sum((money(call["reserved_cost_cny"], "reserved_cost_cny")
            or Decimal(0) for call in unresolved), Decimal(0))),
        "unresolved_calls_missing_monetary_reservation": sum(call["reserved_cost_cny"] is None for call in unresolved),
        "purpose_usage": {purpose: call_totals([call for call in calls if call["purpose"] == purpose])
                          for purpose in sorted({call["purpose"] for call in calls})},
    }


def summarize(plan, episode_records, *, preparation_calls=(), preparation_unresolved_calls=()):
    """Return twelve complete-denominator summaries; reject old or duplicate slots."""
    if plan.get("version") != PLAN_VERSION or len(plan.get("rows", [])) != 6000 or len(plan.get("groups", {})) != 12:
        raise ValueError("Usage must be tied to the complete frozen v064 matrix")
    rows = plan["rows"]
    by_slot = {row["slot_id"]: row for row in rows}
    if len(by_slot) != 6000:
        raise ValueError("Duplicate planned episode identity")
    records = {}
    for record in episode_records:
        identity = record.get("slot_id")
        if identity not in by_slot or identity in records:
            raise ValueError("Historical, foreign or duplicate episode usage record")
        records[identity] = episode_record(by_slot[identity], record)
    all_records = [records.get(row["slot_id"]) or episode_record(row, None) for row in rows]
    grouped = {}
    api_calls, api_unknown = [], []
    api_capture_gaps = 0
    for group_id, profile in plan["groups"].items():
        selected = [record for row, record in zip(rows, all_records) if row["group_id"] == group_id]
        if len(selected) != 500:
            raise ValueError("Every group must retain its full 500-task denominator")
        passes = [record for record in selected if record["code_result"] is True]
        failures = [record for record in selected if record["code_result"] is False]
        unknown_count = 500 - len(passes) - len(failures)
        delivery = None
        if profile["arm"] == "PROJECT":
            delivery = {"passed": sum(record["delivery_result"] is True for record in selected),
                        "failed": sum(record["delivery_result"] is False for record in selected),
                        "unknown_or_pending": sum(record["delivery_result"] is None for record in selected)}
        grouped[group_id] = {
            "profile": profile,
            "all_planned": usage_summary(selected),
            "code_outcomes": {"resolved": len(passes), "unresolved": len(failures),
                              "unknown_or_pending": unknown_count,
                              "endpoint_states": dict(Counter(record["code_status"] for record in selected)),
                              "full_group_completion_rate": len(passes) / 500 if unknown_count == 0 else None,
                              "success_fraction_lower_bound": len(passes) / 500,
                              "success_fraction_upper_bound": (len(passes) + unknown_count) / 500},
            "resolved_episode_usage": usage_summary(passes),
            "unresolved_episode_usage": usage_summary(failures),
            "delivery": delivery,
            "monetary_cost_applicable": profile["model_key"] == "DEEPSEEK",
        }
        if profile["model_key"] == "DEEPSEEK":
            api_calls.extend(call for record in selected for call in record["calls"])
            api_unknown.extend(call for record in selected for call in record["unresolved_calls"])
            api_capture_gaps += sum(record["entered"] and not record["usage_capture_complete"]
                                    for record in selected)
    prep = [validate_call(call) for call in preparation_calls]
    prep_unknown = [validate_unresolved(call) for call in preparation_unresolved_calls]
    names = [call["call_id"] for call in prep + prep_unknown]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate preparation API call identity")
    api_usage, prep_usage = call_totals(api_calls), call_totals(prep)
    known_cost = Decimal(api_usage["accounted_cost_cny_known"]) + Decimal(prep_usage["accounted_cost_cny_known"])
    uncertain = api_unknown + prep_unknown
    reserved_cost = sum((money(call["reserved_cost_cny"], "reserved_cost_cny") or Decimal(0)
                         for call in uncertain), Decimal(0))
    missing_cost = api_usage["accounted_cost_missing_calls"] + prep_usage["accounted_cost_missing_calls"]
    missing_reserve = sum(call["reserved_cost_cny"] is None for call in uncertain)
    cap = money(plan["api_total_budget_cny"], "api_total_budget_cny")
    return {
        "version": VERSION, "plan_version": plan["version"], "groups": grouped,
        "planned_episodes": 6000, "received_episode_records": len(records),
        "aggregate_actual_usage": usage_summary(all_records),
        "api_money": {
            "total_limit_cny": str(cap), "episode_cost_cny_known": api_usage["accounted_cost_cny_known"],
            "preparation_cost_cny_known": prep_usage["accounted_cost_cny_known"],
            "total_accounted_cost_cny_known": str(known_cost),
            "unresolved_reserved_cost_cny_not_actual": str(reserved_cost),
            "costs_missing_calls": missing_cost,
            "reservations_missing_calls": missing_reserve,
            "entered_api_episodes_with_usage_capture_gaps": api_capture_gaps,
            "known_plus_reserved_within_cap": known_cost + reserved_cost <= cap,
            "remaining_cap_after_known_and_reserved_upper_bound_cny": str(max(Decimal(0), cap - known_cost - reserved_cost)),
            "remaining_cap_is_complete_accounting": missing_cost == 0 and missing_reserve == 0 and api_capture_gaps == 0,
            "cost_is_from_observed_usage_and_frozen_price_ledger_not_a_provider_invoice": True,
            "preparation_usage_not_assigned_to_task_mean": prep_usage,
        },
        "interpretation": {
            "unknown_usage_and_unstarted_tasks_are_not_zero_cost_samples": True,
            "full_group_average_requires_all_500_entered_terminal_and_complete_usage": True,
            "complete_usage_subset_means_are_labelled_and_not_full_group_means": True,
            "actual_usage_includes_agent_condenser_repeated_prompts_and_continuations": True,
            "reasoning_is_included_in_completion": True,
            "cache_hit_and_miss_are_included_in_prompt": True,
            "uncertain_reservations_are_never_added_to_actual_tokens_or_cost": True,
            "statistics_do_not_change_budget_admission_or_task_selection": True,
        },
    }
