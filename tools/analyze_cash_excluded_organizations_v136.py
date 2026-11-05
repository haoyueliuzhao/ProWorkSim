"""Analyze fixed-organization outcomes after a user-requested cash/unknown filter.

Only committed compact evidence is read. No ledger, model, runtime or scorer is
opened; the original 250 identities and excluded costs remain in the output.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")
SCORES = ROOT / "artifacts/software-benchmark-v134/final-score-audit-r1/per-task.json"
BEHAVIOR = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json"
USAGE = ROOT / "artifacts/software-benchmark-v133/token-comparison-r2/per-task.json"
DEFAULT_OUTPUT = ROOT / "artifacts/software-benchmark-v136/cash-excluded-analysis-r1"


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)
    }


def indexed(rows):
    value = {row["slot_id"]: row for row in rows}
    if len(value) != len(rows):
        raise ValueError("Duplicate task identity in compact evidence")
    return value


def metrics(rows):
    n = len(rows)
    passed = sum(row["code_passed"] for row in rows)
    s1_passed = sum(row["S1_code_passed"] for row in rows)
    token_fields = ("input_tokens", "output_tokens", "total_tokens")
    total = {key: sum(row["tokens"][key] for row in rows) for key in token_fields}
    s1_total = {key: sum(row["S1_tokens"][key] for row in rows) for key in token_fields}
    paired = Counter(row["paired_outcome"] for row in rows)
    return {
        "n": n, "code_passed": passed, "code_failed": n - passed,
        "conditional_code_accuracy": passed / n if n else None,
        "official_delivery_passed": sum(row["delivery_passed"] for row in rows),
        "code_pass_without_delivery": sum(row["code_passed"] and not row["delivery_passed"]
                                          for row in rows),
        "S1_code_passed_on_same_tasks": s1_passed,
        "S1_conditional_code_accuracy": s1_passed / n if n else None,
        "paired_outcomes": {key: paired[key] for key in (
            "both_passed", "both_failed", "organization_only", "S1_only")},
        "team_tokens": total, "S1_tokens": s1_total,
        "mean_team_tokens": {key: count / n if n else None for key, count in total.items()},
        "mean_S1_tokens": {key: count / n if n else None for key, count in s1_total.items()},
        "token_ratio_to_same_task_S1": total["total_tokens"] / s1_total["total_tokens"]
        if s1_total["total_tokens"] else None,
        "all_selected_tokens_per_confirmed_code_success": total["total_tokens"] / passed
        if passed else None,
        "S1_all_selected_tokens_per_confirmed_code_success": s1_total["total_tokens"] / s1_passed
        if s1_passed else None,
        "mean_API_calls": sum(row["requests"] for row in rows) / n if n else None,
        "S1_mean_API_calls": sum(row["S1_requests"] for row in rows) / n if n else None,
        "end_reasons": dict(Counter(row["end_reason"] for row in rows)),
        "repository_counts": dict(Counter(row["repo"] for row in rows)),
        "settled_CNY": str(sum((Decimal(row["settled_CNY"]) for row in rows), Decimal(0))),
    }


def build():
    scores, scores_ref = read(SCORES)
    behavior, behavior_ref = read(BEHAVIOR)
    usage, usage_ref = read(USAGE)
    by_behavior, by_usage = indexed(behavior), indexed(usage)
    if len(scores) != 250 or len(indexed(scores)) != 250 or len(by_usage) != 250:
        raise ValueError("The original planned task inventory changed")
    if set(by_usage) != {row["slot_id"] for row in scores}:
        raise ValueError("Usage does not cover the exact original task identities")
    kept, audit = [], []
    for score in scores:
        slot = score["slot_id"]
        act, cost = by_behavior.get(slot), by_usage[slot]
        group, task = score["organization_id"], score["instance_id"]
        if cost["organization_id"] != group or cost["instance_id"] != task:
            raise ValueError("Cost and official task identities differ")
        valid = score["code_classification"] in {"passed", "failed"}
        reason = act["exclusive_end_class"] if act else None
        if act and bool(act["cash_censored"]) != (reason == "cash_boundary"):
            raise ValueError("Cash stop classifications disagree")
        if not valid:
            excluded = "unknown_or_not_started"
        elif reason == "cash_boundary":
            excluded = "cash_boundary_regardless_of_success"
        elif act is None or not cost["trusted_closed_usage"] or not cost["all_request_usage_known"]:
            raise ValueError("A known noncash score has no trustworthy closed usage")
        else:
            excluded = None
        audit.append({
            "slot_id": slot, "slot_index": score["slot_index"], "instance_id": task,
            "group": group, "included": excluded is None, "exclusion_reason": excluded,
            "code_classification": score["code_classification"],
            "delivery_classification": score["delivery_classification"],
            "generation_category": score["generation_category"], "end_reason": reason,
            "known_actual_tokens": cost["known_tokens"], "settled_CNY": cost["settled_CNY"],
            "uncertain_reserved_CNY": cost["uncertain_reserved_CNY"],
        })
        if excluded:
            continue
        if score["delivery_classification"] not in {"passed", "failed"}:
            raise ValueError("Retained delivery endpoint is not known")
        s1 = cost["S1_selected"]
        if s1["resolved"] is not score["S1_PROJECT_resolved"]:
            raise ValueError("Baseline selection changed")
        tokens = {key: cost["known_tokens"][key]
                  for key in ("input_tokens", "output_tokens", "total_tokens")}
        s1_tokens = {key: s1["usage"]["known_token_totals"][key] for key in tokens}
        if act["actual_tokens"] != tokens["total_tokens"]:
            raise ValueError("Behavior and billing token counts differ")
        kept.append({
            "slot_id": slot, "slot_index": score["slot_index"], "instance_id": task,
            "group": group, "repo": act["repo"], "end_reason": reason,
            "code_passed": score["code_classification"] == "passed",
            "delivery_passed": score["delivery_classification"] == "passed",
            "S1_code_passed": score["S1_PROJECT_resolved"],
            "S1_slot_id": score["S1_PROJECT_slot_id"],
            "paired_outcome": score["paired_code_category"],
            "tokens": tokens, "S1_tokens": s1_tokens,
            "requests": cost["requests"], "S1_requests": s1["usage"]["requests"],
            "settled_CNY": cost["settled_CNY"],
        })
    group_results = {}
    for group in GROUPS:
        rows = [row for row in kept if row["group"] == group]
        original = [row for row in audit if row["group"] == group]
        if len(original) != 50:
            raise ValueError("Every group must retain all 50 audit identities")
        cash = [row for row in original if row["exclusion_reason"] == "cash_boundary_regardless_of_success"]
        group_results[group] = {
            **metrics(rows), "planned_tasks": 50,
            "exclusions": dict(Counter(row["exclusion_reason"] for row in original if not row["included"])),
            "cash_excluded_code_passed": sum(row["code_classification"] == "passed" for row in cash),
            "cash_excluded_delivery_passed": sum(row["delivery_classification"] == "passed" for row in cash),
            "per_repository": {repo: metrics([row for row in rows if row["repo"] == repo])
                               for repo in sorted({row["repo"] for row in rows})},
        }
    common = set.intersection(*[
        {row["instance_id"] for row in kept if row["group"] == group} for group in GROUPS])
    excluded = [row for row in audit if not row["included"]]
    summary = {
        "version": "v136-unknown-and-cash-excluded-organization-analysis-r1",
        "created_UTC": datetime.now(timezone.utc).isoformat(),
        "sources": {"scores": scores_ref, "behavior": behavior_ref, "usage": usage_ref},
        "user_instruction": "统计时去掉此部分，包括因现金截断没有完成的任务",
        "filter": {
            "include": "Official code passed or failed, trustworthy closed usage, end_reason != cash_boundary",
            "excluded_cash_does_not_depend_on_pass_fail_or_delivery": True,
            "token_cap_stops_retained": True,
            "filter_pre_registered_before_generation": False,
            "original_records_and_expenses_preserved": True,
            "baseline": "v128 selected PROJECT S1, same instance IDs as each retained team subset",
            "not_full50_accuracy_or_random_sample": True,
        },
        "planned_team_tasks": len(scores), "selected_team_tasks": len(kept),
        "excluded_team_tasks": len(excluded),
        "exclusion_counts": dict(Counter(row["exclusion_reason"] for row in excluded)),
        "groups": group_results,
        "all_five_common_subset": {
            "n": len(common), "instance_ids": sorted(common),
            "groups": {group: metrics([row for row in kept if row["group"] == group
                                        and row["instance_id"] in common]) for group in GROUPS},
            "interpretation": "Auxiliary availability/cash-selected intersection; no ranking if empty or tiny",
        },
        "known_actual_tokens_all_original_rows": sum(row["known_actual_tokens"]["total_tokens"] for row in audit),
        "known_actual_tokens_selected": sum(row["tokens"]["total_tokens"] for row in kept),
        "known_actual_tokens_excluded": sum(row["known_actual_tokens"]["total_tokens"] for row in excluded),
        "settled_CNY_all_original_rows": str(sum((Decimal(row["settled_CNY"]) for row in audit), Decimal(0))),
        "settled_CNY_excluded": str(sum((Decimal(row["settled_CNY"]) for row in excluded), Decimal(0))),
        "new_API_calls": 0, "new_grading": 0, "Docker_operations": 0,
    }
    return summary, kept, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Do not overwrite an existing analysis snapshot")
    summary, rows, exclusions = build()
    args.output.mkdir(parents=True)
    for name, value in (("summary", summary), ("selected-per-task", rows), ("all-task-filter-audit", exclusions)):
        (args.output / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"selected": len(rows), "common": summary["all_five_common_subset"]["n"],
                      "groups": {group: {key: value[key] for key in (
                          "n", "code_passed", "S1_code_passed_on_same_tasks", "mean_team_tokens",
                          "mean_S1_tokens", "end_reasons", "cash_excluded_code_passed",
                          "cash_excluded_delivery_passed")}
                                 for group, value in summary["groups"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
