"""Describe the user-selected noncash, officially determined team subset.

Read only the existing score audit and compact behavior summaries. No raw
trajectory, provider database, workspace, test or live resource is accessed.
"""

from __future__ import annotations

from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path

from analyze_collaboration_costs_v133 import aggregate


ROOT = Path(__file__).resolve().parents[1]
SCORES = ROOT / "artifacts/software-benchmark-v134/final-score-audit-r1/per-task.json"
BEHAVIOR = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json"
ROLES = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/role-allocation-r1.json"
OUTPUT = ROOT / "artifacts/software-benchmark-v136/cash-excluded-mechanism-r1"
GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(raw), {
        "path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)
    }


def outcomes(rows):
    return {
        "n": len(rows),
        "code": dict(Counter(row["code_classification"] for row in rows)),
        "delivery": dict(Counter(row["delivery_classification"] for row in rows)),
        "S1_same_tasks_code_passed": sum(row["S1_PROJECT_resolved"] for row in rows),
        "paired": dict(Counter(row["paired_code_category"] for row in rows)),
    }


def main():
    scores, score_ref = read(SCORES)
    behavior, behavior_ref = read(BEHAVIOR)
    roles, role_ref = read(ROLES)
    by_slot = {row["slot_id"]: row for row in behavior}
    if len(scores) != 250 or len(by_slot) != 191:
        raise ValueError("The frozen source denominators changed")
    selected, excluded = [], []
    for score in scores:
        row = by_slot.get(score["slot_id"])
        if score["code_classification"] not in {"passed", "failed"}:
            reason = "official_code_not_determined"
        else:
            if row is None or (row["slot_index"], row["instance_id"], row["group"]) != (
                    score["slot_index"], score["instance_id"], score["organization_id"]):
                raise ValueError("A determined score lost its exact trusted behavior identity")
            if row["cash_censored"] != (row["exclusive_end_class"] == "cash_boundary"):
                raise ValueError("The cash cutoff markers disagree")
            reason = "cash_boundary" if row["cash_censored"] else None
        if reason is not None:
            excluded.append({
                key: score[key] for key in (
                    "slot_id", "slot_index", "instance_id", "organization_id",
                    "code_classification", "delivery_classification", "generation_category"
                )
            } | {"exclusion_reason": reason,
                 "original_end_class": row["exclusive_end_class"] if row else None})
        else:
            if score["delivery_classification"] not in {"passed", "failed"}:
                raise ValueError("The retained delivery endpoint is still unknown")
            selected.append({**row, "official_code": score["code"],
                "official_delivery": score["delivery"],
                "code_classification": score["code_classification"],
                "delivery_classification": score["delivery_classification"],
                "S1_PROJECT_resolved": score["S1_PROJECT_resolved"],
                "paired_code_category": score["paired_code_category"]})
    exclusion_counts = dict(Counter(row["exclusion_reason"] for row in excluded))
    if len(selected) != 68 or exclusion_counts != {
            "official_code_not_determined": 61, "cash_boundary": 121}:
        raise ValueError("The explicit exclusion inventory changed")
    aggregates = aggregate(selected)
    result = {
        "version": "v136-cash-excluded-organization-mechanisms-r1",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources": {"official_scores": score_ref, "compact_behavior": behavior_ref,
                    "original_role_titles": role_ref,
                    "aggregate_implementation": reference(ROOT / "tools/analyze_collaboration_costs_v133.py"),
                    "analysis_source": reference(__file__)},
        "selection_rule": {
            "include": "Official code classification is passed or failed AND cash_censored is false.",
            "exclude": "All61 undetermined results plus all121 cash-boundary records, including cash-boundary code passes.",
            "team_5M_cutoffs_retained": True,
            "organization_contract_blocked_retained": True,
            "no_score_based_success_selection": True,
            "S1_reference": "The previously frozen selected PROJECT S1 attempt for exactly each retained issue; S1 is not independently refiltered here.",
        },
        "retained": len(selected), "excluded": exclusion_counts,
        "retained_end_classes": dict(Counter(row["exclusive_end_class"] for row in selected)),
        "groups": {},
        "common_subsets": {},
        "boundaries": [
            "These conditional denominators are not50, not intention-to-evaluate completion rates, and not the full planned population.",
            "Excluding cash cutoffs removes37 code passes and84 code failures; exclusion is not equivalent to deleting only unsuccessful or technically invalid executions.",
            "Cash availability depends on dispatch order, group scheduling, elapsed prices/cache and earlier tasks. Surviving the cash gate is not randomized.",
            "Excluded initialization OOM and other missing candidates can depend on repository size and group membership. The retained subset is also environment-selected.",
            "The five group denominators contain different issues; compare each to its exact same-task S1 and do not rank the five percentages as a balanced five-arm result.",
            "Team-token cutoffs remain valid observations, not automatically completed work; 12 protocol-blocked records remain, including3 official code/delivery passes.",
            "Legal-submission evidence, successful tool responses, official code and official delivery remain separate endpoints.",
            "The retained SPRINT PO/SM percentage is recomputed from retained records; neither the old32% nor68% is reused.",
            "Budget cutoff labels and governance rejections do not prove the counterfactual cause of a code failure. No new repair or causal contribution tracing was performed.",
            "The previous full50 success-bound comparison is not used as the conclusion about this selected subset.",
        ],
        "new_API_calls": 0, "Docker_operations": 0, "new_tests_or_grading": 0,
        "new_full_trajectory_reads": 0, "new_database_reads": 0,
    }
    group_sets = []
    for group, expected in zip(GROUPS, (10, 17, 16, 11, 14), strict=True):
        rows = [row for row in selected if row["group"] == group]
        if len(rows) != expected:
            raise ValueError("The group's retained denominator changed")
        group_sets.append({row["instance_id"] for row in rows})
        agg = aggregates[group]
        official = outcomes(rows)
        roles_out = {}
        for member, usage in agg["member_costs"].items():
            roles_out[member] = {**usage, "role_title": roles["groups"][group][member]["role"]["title"],
                                 "token_share": usage["tokens"] / agg["actual_tokens"]}
        operations = agg["tools"]
        for name, counts in operations.items():
            counts["tasks_with_successful_response"] = sum(
                row["tool_operations"].get(name, {}).get("successful_responses", 0) > 0 for row in rows)
        passed = official["code"].get("passed", 0)
        delivery = official["delivery"].get("passed", 0)
        result["groups"][group] = {
            "official": official,
            "code_rate_in_retained_subset": passed / len(rows),
            "delivery_rate_in_retained_subset": delivery / len(rows),
            "behavior": agg,
            "member_role_costs": roles_out,
            "end_classes_with_official_outcomes": {
                end: outcomes([row for row in rows if row["exclusive_end_class"] == end])
                for end in sorted({row["exclusive_end_class"] for row in rows})},
            "code_correct_no_legal_delivery": [row["instance_id"] for row in rows
                if row["code_classification"] == "passed" and not row["legal_delivery_evidence"]],
            "S1_only": [row["instance_id"] for row in rows if row["paired_code_category"] == "S1_only"],
            "team_only": [row["instance_id"] for row in rows if row["paired_code_category"] == "organization_only"],
            "instance_ids": sorted(row["instance_id"] for row in rows),
        }
    for name, sets in (("all_five", group_sets), ("first_four", group_sets[:4])):
        tasks = set.intersection(*sets)
        groups = GROUPS if name == "all_five" else GROUPS[:4]
        result["common_subsets"][name] = {
            "n": len(tasks), "task_ids": sorted(tasks),
            "groups": {group: outcomes([row for row in selected
                if row["group"] == group and row["instance_id"] in tasks]) for group in groups},
            "too_small_for_general_organization_ranking": True,
        }
    sprint = result["groups"]["SPRINT"]["member_role_costs"]
    result["SPRINT_PO_SM_fraction"] = sum(sprint[key]["token_share"] for key in ("member_003", "member_004"))
    result["interpretation"] = {
        "headline": "排除未定与现金截止后保留68个团队回合；REVIEW在自己16题子集11过，对照S1同题10过，优势只有1题，不能外推或作五组均衡排名。",
        "CHIEF": "10题均达到团队5M边界，4代码通过、2交付通过；其余代码正确但未交付2题仍是流程缺口。",
        "PIPELINE": "17题包含12次协议阻断和5次token边界；3代码与交付通过都来自协议阻断集合。停止标签不能代替任务判定。",
        "REVIEW": "16题中8次token边界、8次成员停止；分别4/8、7/8代码通过。后者是事后终止分层，不应解释为正常结束造成更高正确率。",
        "SPRINT": "11题均达到token边界，6代码通过但仅1交付通过；PO/SM用量改为筛选后27.69%，两名开发者72.31%。",
        "MATRIX": "14题均达到token边界，3代码通过且0交付通过，不能将此流程缺口归为现金不足；但仍不能断言增加token必然补齐。",
        "selection_warning": "去掉现金中断后样本更接近获得较充分token机会的回合，却同时偏向先启动、较早闭合或通过环境准入的题；这既有幸存者偏差，也有调度选择偏差。五组共同题仅2道。",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (("per-task.json", selected), ("excluded.json", excluded), ("summary.json", result)):
        path = OUTPUT / name
        if path.exists():
            raise FileExistsError("Preserve the existing selected-subset snapshot")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"summary": reference(OUTPUT / "summary.json"),
        "groups": {group: value["official"] for group, value in result["groups"].items()},
        "retained_end_classes": result["retained_end_classes"],
        "SPRINT_PO_SM_fraction": result["SPRINT_PO_SM_fraction"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
