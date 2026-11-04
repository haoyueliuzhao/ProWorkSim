"""Read retained controller summaries once; no model, grading or archive access."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "runs/software-benchmark-v131/fixed-organization-50-r1"
CONTINUATION = ROOT / "runs/software-benchmark-v132/fixed-organization-recovery-r1/continuation.json"
S1_FILE = ROOT / "artifacts/software-benchmark-v128/independent-count-audit-r1/selected-per-task.json"
OUTPUT = ROOT / "artifacts/software-benchmark-v133/collaboration-cost-evidence-r1"
GROUPS = ("CHIEF", "PIPELINE", "REVIEW", "SPRINT", "MATRIX")
SETS = {
    "task_board": {"create_task", "claim_task", "return_task", "revise_task", "declare_dependency", "remove_dependency", "clear_dependency"},
    "messages": {"send_message"},
    "patch_handoff": {"handoff_patch"},
    "patch_integration": {"integrate_patch", "merge_patch"},
    "responsibility_transfer": {"offer_transfer", "accept_transfer", "decline_transfer", "delegate_task"},
    "publication_delivery": {"fix_patch", "submit_integration", "delivery_status"},
    "public_tests": {"run_tests", "read_test_result"},
    "file_navigation": {"read_file", "list_files", "search_file", "search_repository", "diff_workspace"},
    "file_edits": {"write_file", "replace_file", "create_file", "delete_file", "rename_file"},
    "history_workbench": {"work_note", "work_todo", "work_search", "work_read", "read_work_event"},
    "lifecycle_controls": {"staff_done", "staff_wait"},
}
COLLABORATION = {"task_board", "messages", "patch_handoff", "patch_integration",
                 "responsibility_transfer", "organization_observation", "organization_governance"}


def category(name):
    if name == "org_status":
        return "organization_observation"
    if name.startswith("org_"):
        return "organization_governance"
    return next((key for key, names in SETS.items() if name in names), "other")


def read(path, expected=None):
    path = Path(path)
    raw = path.read_bytes()
    ref = {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if expected is not None and ref != expected:
        raise ValueError("An immutable retained input changed: " + str(path))
    return json.loads(raw), ref


def usage_count(value):
    return sum(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0)
               for v in value.get("per_usage_id", {}).values())


def compact(row, child, source, generation, stage, s1):
    if (child["slot_id"] != row["slot_id"] or child["organization_id"] != row["organization_id"]
            or child["fixed_members"] != row["fixed_members"] or child["status"] != "closed"):
        raise ValueError("Controller identity or original closure differs")
    ledger = child["ledger"]
    members = child["member_usage"]
    if (set(members) != set(row["fixed_members"]) or ledger.get("inflight") is not None
            or ledger.get("uncertain_reserved_tokens") != 0
            or sum(m["attempts"] for m in members.values()) != ledger["attempts"]
            or sum(m["known_actual_tokens"] for m in members.values()) != ledger["known_actual_tokens"]
            or any(m["known_actual_tokens"] != m["complete_actual_tokens"]
                   or usage_count(m) != m["known_actual_tokens"] for m in members.values())):
        raise ValueError("Closed member/provider usage does not reconcile")
    boundary = child["managed_boundary"]
    outcomes = boundary["outcomes"]
    records = boundary["team_budget"]["model"]["records"]
    tools, categories = defaultdict(Counter), defaultdict(Counter)
    rejected = Counter()
    examples = []
    charged_ids = set()
    statuses = Counter()
    performed = 0
    for index, outcome in enumerate(outcomes):
        statuses[outcome.get("status", "missing")] += 1
        if outcome.get("action_performed") is not True:
            continue
        performed += 1
        decision = outcome.get("decision") or {}
        name = decision.get("action")
        if not isinstance(name, str):
            continue
        response = outcome.get("response") or {}
        key = category(name)
        tokens = 0
        call_id = decision.get("model_call_id")
        record = records.get(call_id, {})
        charge = record.get("charge") or {}
        if call_id and record.get("status") == "settled" and isinstance(charge.get("charged_tokens"), int):
            if call_id in charged_ids:
                raise ValueError("One model request was attributed to multiple managed actions")
            charged_ids.add(call_id)
            tokens = charge["charged_tokens"]
        for counter in (tools[name], categories[key]):
            counter["dispatched"] += 1
            counter["explicit_rejections"] += response.get("ok") is False
            counter["successful_responses"] += response.get("ok") is True
            counter["request_tokens"] += tokens
            counter["attributed_requests"] += int(tokens > 0)
        if response.get("ok") is False:
            message = str((response.get("error") or {}).get("message", "unspecified"))
            rejected[name + ": " + message[:250]] += 1
            if len(examples) < 12:
                examples.append({"controller_result": source, "outcome_index": index,
                    "member": outcome.get("worker_id"), "tool": name, "model_call_id": call_id,
                    "action_id": response.get("action_id"), "message": message[:500]})
    if len(outcomes) != child["opportunities"]:
        raise ValueError("Original opportunity count differs from the retained outcomes")
    pending_reviews = sum((outcome.get("response") or {}).get("worker_state") == "finish_review_pending"
                          for outcome in outcomes)
    if performed - pending_reviews != child["actions"]:
        raise ValueError("Non-review managed action count differs from the retained outcomes")
    purpose = Counter(call.get("usage_id", "agent") for call in ledger["calls"])
    if sum(purpose.values()) != ledger["attempts"]:
        raise ValueError("Provider call purpose counts do not reconcile")
    terminal_limits = Counter(limit for item in (boundary.get("terminal_details") or {}).values()
                              for limit in item.get("limits", []))
    cash = child.get("cash_censored") is True
    token_boundary = "team_max_total_tokens" in terminal_limits
    closure = child["project_closure"]
    delivery = closure.get("delivery_validation") or {}
    if (child.get("designated_delivery_member") != "member_001"
            or child.get("best_of_members") is not False
            or child.get("terminal_sync", {}).get("tree_sha256") != closure["terminal_tree_sha256"]):
        raise ValueError("The unique designated-member terminal is not proved")
    total = ledger["known_actual_tokens"]
    coordination = sum(v["dispatched"] for k, v in categories.items() if k in COLLABORATION)
    coordination_tokens = sum(v["request_tokens"] for k, v in categories.items() if k in COLLABORATION)
    prior = s1[row["instance_id"]]
    s1_tokens = prior["usage"]["known_token_totals"]["total_tokens"]
    return {"slot_id": row["slot_id"], "slot_index": row["slot_index"], "instance_id": row["instance_id"],
        "repo": row["repo"], "group": row["organization_id"], "stage": stage,
        "controller_result": source, "original_generation_result": generation,
        "member_count": row["member_count"], "members": members,
        "actual_calls": ledger["attempts"], "calls_by_purpose": purpose, "actual_tokens": total,
        "condenser_tokens": sum(m.get("per_usage_id", {}).get("condenser", {}).get("prompt_tokens", 0)
            + m.get("per_usage_id", {}).get("condenser", {}).get("completion_tokens", 0) for m in members.values()),
        "opportunities": child["opportunities"], "performed_actions": performed,
        "runtime_reported_actions_excluding_review_policy": child["actions"],
        "first_finish_review_requests": pending_reviews,
        "outcome_statuses": statuses, "tool_operations": tools, "operation_categories": categories,
        "collaboration_operations": coordination, "collaboration_request_tokens": coordination_tokens,
        "collaboration_action_fraction": coordination / performed if performed else None,
        "explicit_rejection_reasons": rejected, "rejection_examples": examples,
        "closure_reason": child["closure_reason"], "cash_censored": cash,
        "team_5M_boundary_observed": token_boundary, "terminal_limits": terminal_limits,
        "exclusive_end_class": "cash_boundary" if cash else "team_5M_boundary" if token_boundary else child["closure_reason"],
        "designated_final_member": "member_001", "terminal_tree_sha256": closure["terminal_tree_sha256"],
        "delivery_submitted": closure.get("submitted") is True,
        "legal_delivery_evidence": delivery.get("legal_delivery_evidence") is True,
        "same_final_tree_and_legal_delivery": delivery.get("same_tree") is True,
        "delivery_validation": delivery,
        "S1_PROJECT_tokens_same_task": s1_tokens, "S1_PROJECT_calls_same_task": prior["usage"]["requests"],
        "token_delta_vs_S1": total - s1_tokens, "token_ratio_vs_S1": total / s1_tokens if s1_tokens else None}


def aggregate(rows):
    by_group = {}
    for group in GROUPS:
        values = [x for x in rows if x["group"] == group]
        if not values:
            by_group[group] = {"controller_closed_tasks": 0}
            continue
        categories, tools, members = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
        rejections = Counter()
        for item in values:
            for key, counts in item["operation_categories"].items():
                categories[key].update(counts)
            for key, counts in item["tool_operations"].items():
                tools[key].update(counts)
            for key, usage in item["members"].items():
                members[key].update({"calls": usage["attempts"], "tokens": usage["known_actual_tokens"],
                    "agent_decisions": usage["decisions"], "positive_call_tasks": int(usage["attempts"] > 0)})
            rejections.update(item["explicit_rejection_reasons"])
        total = sum(x["actual_tokens"] for x in values)
        actions = sum(x["performed_actions"] for x in values)
        cooperation = sum(x["collaboration_operations"] for x in values)
        by_group[group] = {"controller_closed_tasks": len(values), "actual_tokens": total,
            "mean_actual_tokens": total / len(values), "median_actual_tokens": statistics.median(x["actual_tokens"] for x in values),
            "actual_calls": sum(x["actual_calls"] for x in values),
            "mean_actual_calls": statistics.mean(x["actual_calls"] for x in values),
            "condenser_tokens": sum(x["condenser_tokens"] for x in values),
            "member_costs": members, "leader_001_token_fraction": members["member_001"]["tokens"] / total if total else None,
            "performed_actions": actions, "mean_actions": actions / len(values),
            "collaboration_operations": cooperation, "mean_collaboration_operations": cooperation / len(values),
            "collaboration_action_fraction": cooperation / actions if actions else None,
            "collaboration_request_tokens": sum(x["collaboration_request_tokens"] for x in values),
            "categories": categories, "tools": tools, "explicit_rejection_reasons_top20": rejections.most_common(20),
            "end_classes": Counter(x["exclusive_end_class"] for x in values),
            "raw_closure_reasons": Counter(x["closure_reason"] for x in values),
            "cash_censored_tasks": sum(x["cash_censored"] for x in values),
            "team_5M_boundary_tasks": sum(x["team_5M_boundary_observed"] for x in values),
            "legal_delivery_tasks": sum(x["legal_delivery_evidence"] for x in values),
            "same_final_tree_legal_delivery_tasks": sum(x["same_final_tree_and_legal_delivery"] for x in values),
            "submitted_tasks": sum(x["delivery_submitted"] for x in values),
            "S1_same_tasks_mean_tokens": statistics.mean(x["S1_PROJECT_tokens_same_task"] for x in values),
            "paired_mean_token_delta_vs_S1": statistics.mean(x["token_delta_vs_S1"] for x in values),
            "ratio_of_total_tokens_vs_same_S1_tasks": total / sum(x["S1_PROJECT_tokens_same_task"] for x in values),
            "tasks_with_more_tokens_than_S1": sum(x["token_delta_vs_S1"] > 0 for x in values)}
    return by_group


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Retain the previous time-stamped analysis; use a new output directory")
    plan, plan_ref = read(BATCH / "execution-plan.json")
    continuation, continuation_ref = read(CONTINUATION)
    single, s1_ref = read(S1_FILE)
    s1 = {r["instance_id"]: r for r in single if r["arm"] == "PROJECT"}
    if len(s1) != 50:
        raise ValueError("Expected the exact selected single-agent PROJECT50")
    original = {item["row"]["slot_id"]: item["result"] for item in continuation["original_results"]}
    included, excluded = [], []
    for row in plan["rows"]:
        directory = BATCH / "episodes" / str(row["slot_index"])
        result_path = directory / "result.json"
        stage = "original_v131" if row["slot_id"] in original else "v132_snapshot"
        try:
            result, result_ref = read(result_path, original.get(row["slot_id"]))
        except FileNotFoundError:
            excluded.append({"slot_index": row["slot_index"], "group": row["organization_id"],
                "stage": stage, "reason": "no_completed_generation_result_at_snapshot"})
            continue
        except json.JSONDecodeError:
            excluded.append({"slot_index": row["slot_index"], "group": row["organization_id"],
                "stage": stage, "reason": "new_result_write_not_complete_at_snapshot"})
            continue
        child_ref = result.get("controller_result")
        if result.get("controller_status") != "closed" or not isinstance(child_ref, dict):
            excluded.append({"slot_index": row["slot_index"], "group": row["organization_id"],
                "stage": stage, "reason": "no_trusted_closed_controller", "generation_status": result.get("status"),
                "generation_result": result_ref, "error_type": (result.get("error") or {}).get("type")})
            continue
        child, child_ref = read(child_ref["path"], child_ref)
        record = compact(row, child, child_ref, result_ref, stage, s1)
        record["host_generation_status"] = result["status"]
        included.append(record)
    frozen = [r for r in included if r["stage"] == "original_v131"]
    fresh = [r for r in included if r["stage"] != "original_v131"]
    common = set.intersection(*[{r["instance_id"] for r in frozen if r["group"] == group} for group in GROUPS])
    all_common = [r for r in frozen if r["instance_id"] in common]
    summary = {"version": "v133-actual-collaboration-cost-evidence-r1", "created_at": datetime.datetime.now().astimezone().isoformat(),
        "plan": plan_ref, "continuation": continuation_ref, "selected_S1": s1_ref,
        "planned_tasks_per_group": 50, "selection": "Trusted closed controller with fully reconciled original member usage, regardless of official code outcome",
        "official_score_used_for_selection": False, "original_v131_closed_controller_count": len(frozen),
        "v132_closed_controller_snapshot_count": len(fresh), "excluded_count": len(excluded),
        "exclusions": {g: Counter(x["reason"] for x in excluded if x["group"] == g) for g in GROUPS},
        "original_v131": aggregate(frozen), "v132_snapshot_separate": aggregate(fresh),
        "original_common_all_five_tasks": sorted(common), "original_common_all_five": aggregate(all_common),
        "original_not_cash_censored": aggregate([r for r in frozen if not r["cash_censored"]]),
        "measurement_boundaries": [
            "Controller closure is not an official resolved score; original host export technical_unknown records remain unchanged.",
            "Missing/nonclosed controllers and unresolved usage are excluded from behavioral averages and retained as coverage limits, never counted as model failures.",
            "Cash-censored but trusted closed controllers remain in the primary behavior inventory and have separate ending counts.",
            "Per-group completed subsets differ. All-five common subset and per-task S1 comparisons are descriptive diagnostics, not whole-panel unbiased estimates.",
            "A dispatched operation includes explicit ok=false responses; successful response is not task success. No-tool/multi-tool format rejection is counted separately, not assigned an invented executed tool.",
            "Observed performed tool requests include first staff_done review-policy replies. The original runtime actions counter excludes those review requests; both counts are retained and reconciled.",
            "Request tokens attributed to a collaboration action include that request's entire historical input. They are observed associated cost, not the marginal causal cost of the mechanism.",
            "Legal delivery evidence is a process property, not official code acceptance; final member001 tree and last legal delivered version can differ.",
            "S1 and team runs differ in frozen interface revisions, group cash constraints and recovery history; equal5M team caps are not equal actual opportunities per member."],
        "tools_category_definition": {**{k: sorted(v) for k, v in SETS.items()},
            "organization_observation": ["org_status"], "organization_governance": "all other org_*"},
        "collaboration_categories": sorted(COLLABORATION), "new_API_calls": 0, "new_grading_calls": 0,
        "giant_worlds_or_archives_loaded": 0}
    args.output.mkdir(parents=True)
    for name, value in (("per-task.json", included), ("excluded.json", excluded), ("summary.json", summary)):
        with (args.output / name).open("x") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps({"output": str(args.output), "original": len(frozen), "new_snapshot": len(fresh),
        "common_tasks": len(common), "groups": {g: {k: v.get(k) for k in (
            "controller_closed_tasks", "mean_actual_tokens", "mean_actual_calls", "mean_collaboration_operations",
            "collaboration_action_fraction", "end_classes", "legal_delivery_tasks")}
            for g, v in summary["original_v131"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
