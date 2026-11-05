"""Join frozen compact behavior summaries to the final official score audit.

No controller archives, workspaces, provider databases or live resources are read.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEHAVIOR = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/per-task.json"
MATCHED = ROOT / "artifacts/software-benchmark-v133/token-comparison-r2/matched-subsets.json"
ROLES = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1/role-allocation-r1.json"
GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")
OUTPUT = ROOT / "artifacts/software-benchmark-v134/final-mechanism-analysis-r1.json"


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return json.loads(raw), {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)
    }


def compact(score, behavior):
    value = {
        key: score[key]
        for key in (
            "slot_id", "slot_index", "instance_id", "organization_id",
            "code_classification", "delivery_classification", "code", "delivery",
            "S1_PROJECT_resolved", "S1_PROJECT_slot_id", "paired_code_category",
        )
    }
    if behavior is None:
        value["trusted_behavior_available"] = False
        return value
    value.update({
        key: behavior[key]
        for key in (
            "stage", "controller_result", "actual_tokens", "actual_calls",
            "collaboration_operations", "performed_actions", "exclusive_end_class",
            "legal_delivery_evidence", "same_final_tree_and_legal_delivery",
            "terminal_tree_sha256", "S1_PROJECT_tokens_same_task", "token_ratio_vs_S1",
        )
    })
    value["trusted_behavior_available"] = True
    value["governance_and_delivery_operations"] = {
        key: {field: counts[field] for field in (
            "dispatched", "successful_responses", "explicit_rejections"
        )}
        for key, counts in behavior["tool_operations"].items()
        if key.startswith("org_") or key in {
            "create_task", "claim_task", "send_message", "handoff_patch",
            "integrate_patch", "fix_patch", "submit_integration", "run_tests",
        }
    }
    value["explicit_rejection_reasons"] = behavior["explicit_rejection_reasons"]
    value["retained_rejection_examples"] = behavior["rejection_examples"]
    return value


def counted_outcomes(scores):
    return {
        "n": len(scores),
        "code": dict(Counter(row["code_classification"] for row in scores)),
        "delivery": dict(Counter(row["delivery_classification"] for row in scores)),
        "paired": dict(Counter(row.get("paired_code_category", "unavailable") for row in scores)),
        "S1_passed": sum(row["S1_PROJECT_resolved"] is True for row in scores),
    }


def build(score_path):
    scores, score_ref = read(score_path)
    behaviors, behavior_ref = read(BEHAVIOR)
    matched, matched_ref = read(MATCHED)
    roles, roles_ref = read(ROLES)
    unknown_notes, unknown_ref = read(Path(score_path).with_name("unknown-diagnostic-notes.json"))
    by_slot = {row["slot_id"]: row for row in behaviors}
    if len(by_slot) != 191 or len(scores) != 250:
        raise ValueError("The frozen behavior/plan denominators changed")
    score_by_slot = {row["slot_id"]: row for row in scores}
    if len(score_by_slot) != 250 or not set(by_slot) <= set(score_by_slot):
        raise ValueError("Official and retained behavior identities do not match")
    for slot, row in by_slot.items():
        score = score_by_slot[slot]
        if (score["slot_index"] != row["slot_index"]
                or score["instance_id"] != row["instance_id"]
                or score["organization_id"] != row["group"]):
            raise ValueError("A compact behavior row belongs to another official candidate")
    baseline = {}
    for score in scores:
        task = score["instance_id"]
        original = baseline.setdefault(task, score["S1_PROJECT_resolved"])
        if original is not score["S1_PROJECT_resolved"] or not isinstance(original, bool):
            raise ValueError("S1 is not a single resolved baseline per task")
        expected = {"passed": True, "failed": False}.get(score["code_classification"])
        if expected is not None and score["code"].get("resolved") is not expected:
            raise ValueError("Official code classification disagrees with its endpoint")
    if len(baseline) != 50 or sum(baseline.values()) != 33:
        raise ValueError("The selected PROJECT S1 baseline changed")

    result = {
        "version": "v134-final-organization-mechanism-analysis-r1",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources": {"final_official_per_task": score_ref, "compact_behavior": behavior_ref,
                    "frozen_matched_subsets": matched_ref, "frozen_role_tokens": roles_ref,
                    "final_scoring_unknown_diagnostics": unknown_ref},
        "planned_tasks_per_group": 50,
        "S1_PROJECT": {"code_passed": 33, "tasks": 50},
        "groups": {},
        "common_all_five_20": {},
        "trusted_behavior_end_classes": dict(Counter(
            row["exclusive_end_class"] for row in behaviors)),
        "scoring_unknown_diagnostics": unknown_notes,
        "boundaries": [
            "Official code, official delivery, legal-submission evidence and successful tool responses are distinct endpoints.",
            "Technical unknown and unstarted tasks are not model code failures; all 50 planned identities remain in each group.",
            "The 20-task subset was selected by trusted closure before final scores, not by success; it remains completion-selected and partly cash-censored.",
            "A cash/token boundary records how generation stopped, not the counterfactual cause of a wrong patch.",
            "Governance success means a protocol operation was recorded; it does not mean review accepted, tests passed or the issue was solved.",
            "Operation-attributed requests include the whole input history and are not marginal coordination-token costs.",
            "These are comparisons of complete deployed conditions; harness, cash-admission and recovery differences prevent a topology-only causal claim.",
            "The compact record does not prove event order or semantic contribution of messages; no new patch-content or full-trajectory analysis was performed.",
        ],
        "new_model_calls": 0, "Docker_operations": 0,
        "new_tests_or_grading": 0, "new_full_trajectory_reads": 0,
    }
    for group in GROUPS:
        group_scores = [row for row in scores if row["organization_id"] == group]
        rows = [row for row in behaviors if row["group"] == group]
        if len(group_scores) != 50:
            raise ValueError("A group lost a planned identity")
        valid = [row for row in group_scores if row["code_classification"] in {"passed", "failed"}]
        passed = [row for row in valid if row["code_classification"] == "passed"]
        paired = {
            "S1_only": [row for row in valid if row["S1_PROJECT_resolved"]
                        and row["code_classification"] == "failed"],
            "team_only": [row for row in passed if not row["S1_PROJECT_resolved"]],
            "both_passed": [row for row in passed if row["S1_PROJECT_resolved"]],
            "both_failed": [row for row in valid if not row["S1_PROJECT_resolved"]
                            and row["code_classification"] == "failed"],
        }
        tools = sorted({name for row in rows for name in row["tool_operations"]})
        operations = {}
        for name in tools:
            counts = [row["tool_operations"].get(name, {}) for row in rows]
            operations[name] = {
                key: sum(item.get(key, 0) for item in counts)
                for key in ("dispatched", "successful_responses", "explicit_rejections")
            }
            operations[name]["tasks_with_successful_response"] = sum(
                item.get("successful_responses", 0) > 0 for item in counts)
        end_table = {}
        for end in sorted({row["exclusive_end_class"] for row in rows}):
            subset = [score_by_slot[row["slot_id"]] for row in rows
                      if row["exclusive_end_class"] == end]
            end_table[end] = counted_outcomes(subset)
        rejections = Counter()
        for row in rows:
            rejections.update(row["explicit_rejection_reasons"])
        result["groups"][group] = {
            "official_all_50": counted_outcomes(group_scores),
            "generation_categories_for_unscored_tasks": dict(Counter(
                row["generation_category"] for row in group_scores
                if row["code_classification"] not in {"passed", "failed"})),
            "full50_confirmed_code_lower_bound": len(passed) / 50,
            "full50_unknown_all_pass_upper_bound": (50 - sum(
                row["code_classification"] == "failed" for row in group_scores)) / 50,
            "officially_scored_same_task_pairing": counted_outcomes(valid),
            "paired_task_lists": {key: [row["instance_id"] for row in values]
                                  for key, values in paired.items()},
            "paired_difference_cases": {
                key: [compact(row, by_slot.get(row["slot_id"])) for row in paired[key]]
                for key in ("S1_only", "team_only")},
            "all_code_pass_cases": [compact(row, by_slot.get(row["slot_id"])) for row in passed],
            "code_pass_without_legal_delivery_evidence": [row["instance_id"] for row in passed
                if row["slot_id"] in by_slot and not by_slot[row["slot_id"]]["legal_delivery_evidence"]],
            "code_pass_without_official_delivery_pass": [row["instance_id"] for row in passed
                if row["delivery_classification"] != "passed"],
            "trusted_behavior_tasks": len(rows),
            "trusted_behavior_end_classes_with_official_outcomes": end_table,
            "operations": operations,
            "explicit_rejection_reasons": dict(rejections.most_common()),
            "legal_delivery_evidence_tasks": sum(row["legal_delivery_evidence"] for row in rows),
            "same_final_tree_legal_delivery_tasks": sum(row["same_final_tree_and_legal_delivery"] for row in rows),
            "S1_only_end_classes": dict(Counter(
                by_slot[row["slot_id"]]["exclusive_end_class"] for row in paired["S1_only"])),
        }

    common = matched["subsets"]["common_all_five"]
    common_tasks = set(common["task_ids"])
    if len(common_tasks) != 20:
        raise ValueError("The frozen common subset changed")
    common_table = {
        "task_ids": sorted(common_tasks), "n": 20,
        "S1_PROJECT": common["S1_PROJECT"], "groups": {},
        "selected_without_final_score_filtering": True,
        "still_conditioned_on_trusted_closure": True,
    }
    for group in GROUPS:
        selected = [row for row in scores
                    if row["organization_id"] == group and row["instance_id"] in common_tasks]
        values = [by_slot[row["slot_id"]] for row in selected]
        if len(values) != 20:
            raise ValueError("The frozen common subset lost a behavior row")
        tokens = sum(row["actual_tokens"] for row in values)
        passed = sum(row["code_classification"] == "passed" for row in selected)
        common_table["groups"][group] = {
            **counted_outcomes(selected), **common["groups"][group],
            "total_team_tokens": tokens,
            "tokens_per_confirmed_code_success_including_all_20_costs": tokens / passed if passed else None,
            "unknown_results_not_imputed_as_failures": True,
            "code_pass_without_legal_delivery_evidence": sum(
                score["code_classification"] == "passed" and not behavior["legal_delivery_evidence"]
                for score, behavior in zip(selected, values, strict=True)),
            "successful_code_instances": [row["instance_id"] for row in selected
                                          if row["code_classification"] == "passed"],
        }
    result["common_all_five_20"] = common_table
    scored_common = {
        task for task in common_tasks
        if all(score["code_classification"] in {"passed", "failed"}
               for score in scores if score["instance_id"] == task)
    }
    s1_rows = {row["instance_id"]: row for row in behaviors
               if row["instance_id"] in scored_common}
    result["common_all_five_officially_determined"] = {
        "task_ids": sorted(scored_common), "n": len(scored_common),
        "excluded_from_original_common20": sorted(common_tasks - scored_common),
        "auxiliary_only_not_a_replacement_for_common20": True,
        "S1_PROJECT": {
            "code_passed": sum(baseline[task] for task in scored_common),
            "total_tokens": sum(row["S1_PROJECT_tokens_same_task"] for row in s1_rows.values()),
            "mean_tokens": sum(row["S1_PROJECT_tokens_same_task"] for row in s1_rows.values()) / len(scored_common),
            "mean_calls": sum(row["S1_PROJECT_calls_same_task"] for row in s1_rows.values()) / len(scored_common),
        },
        "groups": {},
    }
    for group in GROUPS:
        selected = [row for row in scores if row["organization_id"] == group
                    and row["instance_id"] in scored_common]
        values = [by_slot[row["slot_id"]] for row in selected]
        result["common_all_five_officially_determined"]["groups"][group] = {
            **counted_outcomes(selected),
            "total_tokens": sum(row["actual_tokens"] for row in values),
            "mean_tokens": sum(row["actual_tokens"] for row in values) / len(values),
            "mean_calls": sum(row["actual_calls"] for row in values) / len(values),
            "end_classes": dict(Counter(row["exclusive_end_class"] for row in values)),
            "mean_collaboration_operations": sum(row["collaboration_operations"] for row in values) / len(values),
        }
    sprint_roles = roles["groups"]["SPRINT"]
    result["SPRINT_role_cost_correction"] = {
        "PO_member": "member_003", "SM_member": "member_004",
        "PO_SM_tokens": sum(sprint_roles[key]["tokens"] for key in ("member_003", "member_004")),
        "PO_SM_fraction": sum(sprint_roles[key]["token_share"] for key in ("member_003", "member_004")),
        "developers": ["member_001", "member_002"],
        "not_a_pure_management_overhead_estimate": True,
    }
    gaps = [by_slot[row["slot_id"]] for row in scores
            if row["code_classification"] == "passed"
            and not by_slot[row["slot_id"]]["legal_delivery_evidence"]]
    result["code_correct_but_no_legal_delivery"] = {
        "n": len(gaps),
        "end_classes": dict(Counter(row["exclusive_end_class"] for row in gaps)),
        "interpretation": "这些回合同时有正确代码与资源边界终止；不能据此断言增加预算必定完成交付。",
    }
    result["mechanism_interpretation"] = {
        "overall": [
            "CHIEF、PIPELINE、SPRINT、MATRIX在原50题中的成功上界均低于恢复后S1的33/50；REVIEW的完整50题仍不能判定优劣。",
            "在各组官方确定同题上，新增成功/丢失S1成功依次为2/15、0/23、4/2、0/11、2/15。这里只是配对观察，不是协作因果贡献。",
            "共同20题团队成本均高于S1；REVIEW已有13通过并有1未知，S1为13通过。严格共同19题REVIEW13通过、S1为12通过，净增仅1题。",
            "121现金截止、50团队token边界、12组织协议阻断和8其他闭合均保留；协议阻断中仍有3题代码及官方交付通过，停止标签不等于任务失败。",
        ],
        "CHIEF": [
            "40个可信回合只有1题成功记录显式派工、1题成功整合补丁；15个S1成功但CHIEF失败的回合没有成功整合或合法提交。",
            "新增成功Requests2931有合法交付；SymPy15345的14次消息全部被拒，未执行固定/交接/整合/提交。不能把新增成功都解释为可追踪跨成员补丁复用。",
        ],
        "PIPELINE": [
            "同题44个有效评分只有5代码通过，少于S1的28；交付通过4。代码端点差距远大于代码到交付的1题缺口，因此不能只修自动提交就期望恢复差距。",
            "41题设计记录、20题实现阶段记录、8题验证阶段记录、6题合法提交证据；这些是各阶段被记录的任务数，不是成功率漏斗或同一批题的嵌套子集证明。",
            "12个组织协议阻断回合有3代码与交付通过、9代码未通过；23个S1-only中有7协议阻断、15现金截止、1团队token边界。不能将任一停止原因单独认定为失败因果。",
        ],
        "REVIEW": [
            "37个官方确定任务中24代码通过，对照S1同题22；新增4题、丢失2题。该局部优势需要保留小样本、未完成计划和配置差异边界。",
            "Requests2931及SymPy15345新增成功同时有复核/合法交付；SymPy15017与Django13158没有完成复核与交付，不把四题全归于独立审核。Requests2931还与公开fixture修订混杂。",
            "pytest6197虽有合法复核交付仍未通过官方代码评分；Django15957在现金边界停止且无合法交付，二者不宜统一归为接口故障。",
            "24代码通过仅11官方交付通过，仍有13个正确候选缺合法交付。",
        ],
        "SPRINT": [
            "40个可信回合仅Flask5014成功启动Sprint，也是唯一官方交付通过；其余15个代码通过候选未完成合法交付。",
            "协作动作占31.3%、org_status324次、104次治理操作40次明确拒绝，支持当前协议执行负担突出；不等于已测得成熟Sprint团队的效益。",
            "PO(member003)和SM(member004)占31.95%token，开发成员001/002占68.05%；角色用量不等于净管理开销。",
        ],
        "MATRIX": [
            "28个有效代码评分为5通过、对照S1同题18；29个可信回合无合法交付。两条权责确认与整合链的闭合缺口仍在。",
            "新增Xarray4687与Django13158均未执行固定/交接/整合/提交；消息可能影响001，但现摘要不能证明两次增益来自显式跨成员补丁复用。",
            "共同20题平均383.31万token，对照S1为195.60万；投入更多而代码通过5对13，不能把昂贵解释为取得更高能力。",
        ],
        "next_identification_step_not_new_experiment_authorization": [
            "优先核对任务ID发现、职责/所有权一致性、可执行下一步和同候选确认链；不能把正确权限拒绝一律称为实现bug。",
            "同新版harness统一S1、现金准入和恢复规则后，再对一个明确瓶颈作单项消融；当前同面板已用于开发诊断，不能冒称独立确认。",
        ],
    }
    source = Path(__file__).resolve()
    source_bytes = source.read_bytes()
    result["analysis_source"] = {
        "path": str(source), "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "bytes": len(source_bytes),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(args.scores)
    if args.output.exists():
        raise FileExistsError("Preserve the existing final analysis snapshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "groups": {
        group: values["officially_scored_same_task_pairing"]
        for group, values in result["groups"].items()},
        "common20": {group: {key: values[key] for key in ("code", "delivery", "mean_team_tokens")}
                     for group, values in result["common_all_five_20"]["groups"].items()}
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
