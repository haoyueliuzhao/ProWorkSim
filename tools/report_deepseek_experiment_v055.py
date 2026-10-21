"""Read-only six-condition status/cost snapshot; never starts or changes a run."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

VERSION = "v055-six-condition-readonly-report-r1"
CONDITIONS = tuple(arm + "-" + mode for arm in ("REF", "MATCH", "PROJECT")
                   for mode in ("nonthinking", "thinking"))
NANOYUAN = 1_000_000_000


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def reference(path):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


class SmallReferences:
    """One read per immutable small reference; never follows patch/world fields."""

    def __init__(self):
        self.cache = {}
        self.warnings = []
        self.read_count = 0

    def read(self, ref, *, maximum_bytes=512 * 1024):
        if not isinstance(ref, dict) or not {"path", "sha256", "bytes"} <= set(ref):
            raise ValueError("A complete immutable file reference is required")
        key = (ref["path"], ref["sha256"], ref["bytes"])
        if key in self.cache:
            return self.cache[key]
        path = Path(ref["path"])
        if ref["bytes"] > maximum_bytes or path.stat().st_size != ref["bytes"]:
            raise ValueError("Reference exceeds the small-record bound or its declared size changed")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != ref["sha256"]:
            raise ValueError("Referenced record SHA256 changed")
        value = json.loads(data)
        self.cache[key] = value
        self.read_count += 1
        return value

    def optional(self, ref, *, context):
        try:
            return self.read(ref)
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.warnings.append({"context": context, "error_type": type(error).__name__,
                                  "reason": str(error)})
            return None


def cost_empty():
    return {"requests": 0, "settled_requests": 0, "uncertain_requests": 0,
            "inflight_requests": 0, "known_prompt_tokens": 0, "known_completion_tokens": 0,
            "known_total_tokens": 0, "known_cache_hit_tokens": 0, "known_cache_miss_tokens": 0,
            "known_reasoning_tokens": 0, "reasoning_token_reporting_missing_requests": 0,
            "settled_nanoyuan": 0, "settled_peak_nanoyuan": 0,
            "uncertain_reserved_nanoyuan": 0, "inflight_reserved_nanoyuan": 0,
            "tariff_bases": {}}


def cost_add(target, row):
    target["requests"] += 1
    status = row["status"]
    if status == "settled":
        target["settled_requests"] += 1
        usage = json.loads(row["usage_json"])
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            target["known_" + field] += usage[field]
        hit = usage.get("prompt_cache_hit_tokens", (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0))
        target["known_cache_hit_tokens"] += hit
        target["known_cache_miss_tokens"] += usage.get("prompt_cache_miss_tokens", usage["prompt_tokens"] - hit)
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if reasoning is None:
            target["reasoning_token_reporting_missing_requests"] += 1
        else:
            target["known_reasoning_tokens"] += reasoning
        target["settled_nanoyuan"] += row["settled_nanoyuan"]
        target["settled_peak_nanoyuan"] += row["settled_peak_nanoyuan"]
        basis = json.loads(row["tariff_basis_json"] or "{}").get("basis", "unreported")
        target["tariff_bases"][basis] = target["tariff_bases"].get(basis, 0) + 1
    elif status in {"reserved", "uncertain"}:
        prefix = "inflight" if status == "reserved" else "uncertain"
        target[prefix + "_requests"] += 1
        target[prefix + "_reserved_nanoyuan"] += row["reserved_nanoyuan"]
    else:
        raise ValueError("Unknown budget request state; refuse to undercount costs")


def cost_finish(value):
    value = dict(value)
    unknown = value["uncertain_reserved_nanoyuan"] + value["inflight_reserved_nanoyuan"]
    value.update(
        settled_upper_cny=value["settled_nanoyuan"] / NANOYUAN,
        settled_peak_equivalent_cny=value["settled_peak_nanoyuan"] / NANOYUAN,
        uncertain_reserved_cny=value["uncertain_reserved_nanoyuan"] / NANOYUAN,
        inflight_reserved_cny=value["inflight_reserved_nanoyuan"] / NANOYUAN,
        committed_upper_cny=(value["settled_nanoyuan"] + unknown) / NANOYUAN,
        committed_peak_equivalent_cny=(value["settled_peak_nanoyuan"] + unknown) / NANOYUAN,
        complete_actual_tokens=value["known_total_tokens"] if unknown == 0 else None,
        reasoning_tokens_are_included_in_completion=True,
        costs_are_conservative_not_provider_invoice=True,
    )
    return value


def read_budget(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Shared budget ledger does not exist; report will not create it")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        metadata = dict(db.execute("SELECT name,value FROM metadata"))
        # Never read API request/response contents or any credentials.
        rows = [dict(row) for row in db.execute("""SELECT request_id,slot_id,condition,status,
            reserved_nanoyuan,settled_nanoyuan,settled_peak_nanoyuan,usage_json,
            tariff_basis_json FROM requests""")]
    policy = json.loads(metadata["policy"])
    if policy.get("cap_nanoyuan") != 2000 * NANOYUAN or policy.get("model") != "deepseek-flash":
        raise ValueError("Report requires the independent DeepSeek CNY 2000 ledger")
    return metadata, policy, rows


def interval(resolved, failed, denominator=500):
    unknown = denominator - resolved - failed
    return {"planned_denominator": denominator, "resolved": resolved, "failed": failed,
            "unknown": unknown, "full_panel_point_estimate": resolved / denominator if not unknown else None,
            "success_fraction_bounds": [resolved / denominator, (resolved + unknown) / denominator],
            "bounds_are_missing_outcome_bounds_not_confidence_intervals": True}


def scoring_endpoint(score, slot, references):
    endpoint = score.get("endpoint")
    if endpoint in {"code", "delivery"}:
        return endpoint
    request = references.optional(score.get("request"), context=slot["slot_id"] + ":score_request")
    if request is None:
        return None
    if (request.get("slot_id") != slot["slot_id"]
            or request.get("condition_id") != slot["condition_id"]
            or request.get("model") != "deepseek-flash" or request.get("preparation_only") is not False):
        references.warnings.append({"context": slot["slot_id"], "reason": "Scoring identity crossed experiment/condition/slot"})
        return None
    return request.get("endpoint") if request.get("endpoint") in {"code", "delivery"} else None


def endpoint_result(scores):
    # Repeated official attempts are not silently selected by their outcome.
    official = [score for score in scores if score.get("status") == "official_report"
                and type(score.get("resolved")) is bool]
    if len(official) == 1:
        return "resolved" if official[0]["resolved"] else "failed"
    return "unknown"


def create_report(plan_ref):
    refs = SmallReferences()
    plan = refs.read(plan_ref, maximum_bytes=4 * 1024 * 1024)
    if (plan.get("version") != "v055-six-condition-queue-r1" or plan.get("budget_cny") != 2000
            or set(plan.get("conditions", {})) != set(CONDITIONS)):
        raise ValueError("A frozen independent six-condition v055 plan is required")
    slots = refs.read(plan["slots"], maximum_bytes=4 * 1024 * 1024)["slots"]
    by_slot = {slot["slot_id"]: slot for slot in slots}
    if (len(slots) != 3000 or len(by_slot) != 3000
            or Counter(slot["condition_id"] for slot in slots) != Counter({key: 500 for key in CONDITIONS})
            or any(not slot["slot_id"].startswith("v055-") for slot in slots)):
        raise ValueError("The planned denominator must remain 500 in each of six conditions")
    panels = [{slot["instance_id"] for slot in slots if slot["condition_id"] == condition}
              for condition in CONDITIONS]
    if any(len(panel) != 500 or panel != panels[0] for panel in panels):
        raise ValueError("The six panels must contain the same 500 tasks")
    state_path = Path(plan["queue_root"]) / "state.json"
    if state_path.exists():
        state_bytes = state_path.read_bytes()
        state = json.loads(state_bytes)
        if state.get("plan") != plan_ref:
            raise ValueError("Queue snapshot differs from the supplied frozen plan")
        state_rows = {row["slot"]["slot_id"]: row for row in state["rows"]}
        if (len(state_rows) != 3000 or set(state_rows) != set(by_slot)
                or any(state_rows[key]["slot"] != by_slot[key] for key in by_slot)):
            raise ValueError("Queue no longer retains the complete original inventory")
        state_identity = {"path": str(state_path), "sha256": hashlib.sha256(state_bytes).hexdigest(),
                          "bytes": len(state_bytes), "updated_utc": state.get("updated_utc")}
    else:
        state, state_identity = {}, None
        state_rows = {key: {"slot": slot, "generation": {"status": "pending"}, "scores": []}
                      for key, slot in by_slot.items()}
    metadata, policy, budget_rows = read_budget(plan["ledger_path"])
    admission = refs.read(plan["admission"])
    preparation_ids = set(admission["neutral"]["request_ids"])
    if len(preparation_ids) != 12:
        raise ValueError("The original twelve preparation requests must remain identified")
    halted = metadata.get("halted")
    budget_stop = bool(state.get("dispatch_stopped") and not halted
                       and "budget" in state.get("stop_reason", ""))
    service_stop = bool(halted)
    all_cost, prep_cost, unattributed = cost_empty(), cost_empty(), cost_empty()
    costs = {condition: cost_empty() for condition in CONDITIONS}
    prep_costs = {condition: cost_empty() for condition in CONDITIONS}
    for item in budget_rows:
        cost_add(all_cost, item)
        if item["request_id"] in preparation_ids:
            cost_add(prep_cost, item)
            condition = item["condition"].replace("_", "-")
            arm, mode = condition.split("-", 1)
            condition = arm + "-" + mode.lower()
            if condition in prep_costs:
                cost_add(prep_costs[condition], item)
        elif item["slot_id"] in by_slot and item["condition"] == by_slot[item["slot_id"]]["condition_id"]:
            cost_add(costs[item["condition"]], item)
        else:
            cost_add(unattributed, item)
    conditions = {}
    for condition in CONDITIONS:
        generation, execution, code, delivery = Counter(), Counter(), Counter(), Counter()
        censored_code, technical, same_tree = Counter(), 0, Counter()
        for row in state_rows.values():
            slot = row["slot"]
            if slot["condition_id"] != condition:
                continue
            gen = row["generation"]
            status = gen.get("status", "technical_unknown")
            generation[status] += 1
            censored = gen.get("administratively_censored") or gen.get("controller_status") == "budget_exhausted"
            if status == "pending" and budget_stop or censored and not service_stop:
                execution["global_budget_censored"] += 1
            elif status == "pending" and service_stop or censored and service_stop:
                execution["global_service_halt_affected"] += 1
            else:
                execution[status] += 1
            grouped = {"code": [], "delivery": []}
            for score in row.get("scores", []):
                endpoint = scoring_endpoint(score, slot, refs)
                if endpoint:
                    grouped[endpoint].append(score)
            code_result = endpoint_result(grouped["code"])
            code[code_result] += 1
            if censored or status == "pending" and budget_stop:
                censored_code[code_result] += 1
            if status == "technical_unknown" or any(score.get("status") == "technical_unknown" for score in row.get("scores", [])):
                technical += 1
            if not condition.startswith("PROJECT-"):
                delivery["not_applicable"] += 1
                continue
            lock = None
            if status == "closed" and gen.get("result"):
                result = refs.optional(gen["result"], context=slot["slot_id"] + ":generation_result")
                lock = refs.optional(result.get("candidate"), context=slot["slot_id"] + ":candidate_lock") if result else None
                if lock and lock.get("submitted") is True:
                    same_tree[str(lock.get("same_tree"))] += 1
            delivery_result = endpoint_result(grouped["delivery"])
            if grouped["delivery"]:
                delivery[delivery_result] += 1
            elif status == "closed" and gen.get("result"):
                if (lock and lock.get("task_id") == slot["instance_id"]
                        and lock.get("locked_before_grading") is True
                        and lock.get("submitted") is False and lock.get("last_legal_delivery") is None):
                    delivery["no_legal_submission"] += 1
                else:
                    delivery["unknown"] += 1
            else:
                delivery["unknown"] += 1
        conditions[condition] = {
            "planned_tasks": 500, "generation_status_counts": dict(generation),
            "execution_state_counts": {key: execution[key] for key in (
                "pending", "running", "closed", "technical_unknown", "global_budget_censored",
                "global_service_halt_affected")},
            "technical_unknown_tasks": technical,
            "official_code": interval(code["resolved"], code["failed"]),
            "official_code_within_budget_censored_tasks": dict(censored_code),
            "project_delivery": ({"applicable": False, "not_applicable": 500}
                if not condition.startswith("PROJECT-") else {
                    "applicable": True, "resolved": delivery["resolved"],
                    "official_failed": delivery["failed"], "no_legal_submission": delivery["no_legal_submission"],
                    "unknown": delivery["unknown"],
                    "delivery_rate": interval(delivery["resolved"], delivery["failed"] + delivery["no_legal_submission"]),
                    "final_tree_same_as_legal_submission_diagnostics": dict(same_tree)}),
            "formal_api_cost": cost_finish(costs[condition]),
        }
    global_cost = cost_finish(all_cost)
    global_cost.update(cap_cny=2000, remaining_cny=2000 - global_cost["committed_upper_cny"],
                       halted=halted, policy=policy,
                       consecutive_system_failures=int(metadata.get("system_failure_streak", 0)))
    return {
        "version": VERSION, "created_utc": datetime.now(timezone.utc).isoformat(),
        "plan": plan_ref, "queue_snapshot": state_identity,
        "queue_status": state.get("status", "not_started"),
        "dispatch_stopped": state.get("dispatch_stopped", False), "stop_reason": state.get("stop_reason"),
        "planned_distinct_tasks": 500, "planned_formal_episodes": 3000, "conditions": conditions,
        "global_api_cost_including_preparation": global_cost,
        "preparation": {"planned_requests": 12, "actual": cost_finish(prep_cost),
                        "conditions": {key: cost_finish(value) for key, value in prep_costs.items()}},
        "unattributed_ledger_entries": cost_finish(unattributed),
        "small_immutable_reference_reads": refs.read_count, "warnings": refs.warnings,
        "interpretation": [
            "All six planned denominators remain 500; unknown and unstarted outcomes are not failures.",
            "Budget-censored locked candidates may have official outcomes; censoring remains separate.",
            "Code and legal project delivery are distinct endpoints; REF/MATCH delivery is not applicable.",
            "Missing-outcome bounds are not confidence intervals; no complete-panel point estimate with unknowns.",
            "Known usage excludes unresolved requests; reasoning is already included in completion tokens.",
            "Queue and SQLite are separate read snapshots, not one cross-process atomic transaction.",
            "No v054 scores, large world state, prompt/response body, model weights or patches were read.",
        ], "report_model_calls": 0, "report_service_starts": 0, "ledger_read_only": True,
    }


def markdown(report):
    rows = ["# DeepSeek 六组实验快照", "", f"时间：{report['created_utc']}；每组计划 500 题，共 3000 回合。", "",
            "| 条件 | 待运行 | 运行中 | 闭合 | 技术未知 | 预算截断 | 服务停发影响 | 代码成功/失败/未知 |",
            "|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, value in report["conditions"].items():
        counts, code = value["execution_state_counts"], value["official_code"]
        rows.append(f"| {name} | " + " | ".join(str(counts[key]) for key in (
            "pending", "running", "closed", "technical_unknown", "global_budget_censored", "global_service_halt_affected"))
            + f" | {code['resolved']}/{code['failed']}/{code['unknown']} |")
    rows += ["", "| PROJECT 条件 | 交付成功 | 交付官方失败 | 无合法提交 | 未知 |", "|---|---:|---:|---:|---:|"]
    for name, value in report["conditions"].items():
        delivery = value["project_delivery"]
        if delivery["applicable"]:
            rows.append(f"| {name} | {delivery['resolved']} | {delivery['official_failed']} | {delivery['no_legal_submission']} | {delivery['unknown']} |")
    cost, prep = report["global_api_cost_including_preparation"], report["preparation"]["actual"]
    rows += ["", "REF/MATCH 的项目交付不适用。未运行、技术未知和预算截断不填为模型失败。", "",
             f"全局已知 token：{cost['known_total_tokens']:,}；结算保守费用 ¥{cost['settled_upper_cny']:.8f}；"
             f"峰价等价值 ¥{cost['settled_peak_equivalent_cny']:.8f}；"
             f"未知预约 ¥{cost['uncertain_reserved_cny']:.8f}；在途预约 ¥{cost['inflight_reserved_cny']:.8f}。",
             f"剩余额度 ¥{cost['remaining_cny']:.8f}／总上限 ¥2000；含准备阶段 {prep['requests']} 次请求、"
             f"{prep['known_total_tokens']:,} token、¥{prep['settled_upper_cny']:.8f}。", "",
             "逐组 token、缓存、思考 token、费用、完整分母和未知范围见同名 JSON。思考 token 已包含在输出中。",
             "报告仅只读汇总；队列与账本为相近时刻的两个快照。", ""]
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan_ref = reference(args.plan)
    if plan_ref["sha256"] != args.sha256:
        raise ValueError("Frozen plan hash differs")
    md = args.output.with_suffix(".md")
    if args.output.suffix != ".json" or args.output.exists() or md.exists():
        raise ValueError("Choose new .json and .md snapshot paths; prior reports are immutable")
    report = create_report(plan_ref)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        stream.write(canonical(report))
    with md.open("x") as stream:
        stream.write(markdown(report))
    print(json.dumps({"report": reference(args.output), "markdown": reference(md),
                      "model_calls": 0, "ledger_read_only": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
