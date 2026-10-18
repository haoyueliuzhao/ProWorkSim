"""Merge the closed CAL1 continuation with its immutable original-stage report.

Only the new continuation artifacts are analyzed. Previously analyzed rows,
grades, unknowns and worker intervals are reused, never regenerated or rescored.
This report supplies evidence for a separate stage decision; it releases nothing.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import software_calibration_v051_report as prior

VERSION = "software-calibration-v051-cal1-unique-merged-v1"
LEDGER_KEYS = ("complete_generations", "started_generations", "known_actual_tokens",
    "uncertain_reservation_tokens", "complete_actual_tokens", "ledger_tokens")


def merge_unique_rows(original, inventory, new_rows):
    """Only replace the original untouched rows, preserving every started row."""
    if len(original) != 48 or len({r["slot_id"] for r in original}) != 48:
        raise ValueError("Original report must retain exactly48 unique slots")
    eligible = [r for r in original if r["status"] == "not_started"]
    expected = [r["slot_id"] for r in eligible]
    if ([r["slot_id"] for r in inventory] != expected
            or [r["slot_id"] for r in new_rows] != expected):
        raise ValueError("Continuation must contain the exact ordered untouched inventory")
    for old, frozen, new in zip(eligible, inventory, new_rows):
        if (old.get("attempted") is not False or old.get("actual_tokens") is not None
                or old.get("original_grade_pass_at_1") is not None or old.get("binding_issues")):
            raise ValueError("Untouched row contains earlier execution or unresolved evidence")
        if any(old.get(k) != v or new.get(k) != v for k, v in frozen.items()):
            raise ValueError("Continuation changed an original slot identity or budget")
    replacements = {r["slot_id"]: r for r in new_rows}
    return [copy.deepcopy(replacements.get(r["slot_id"], r)) for r in original]


def merge_worker_cost(original, continuation):
    """Distinct output paths identify whole worker intervals across both stages."""
    old_paths = {r["output"] for r in original["attempts"]}
    new_paths = {r["output"] for r in continuation["attempts"]}
    if (len(old_paths) != len(original["attempts"])
            or len(new_paths) != len(continuation["attempts"]) or old_paths & new_paths):
        raise ValueError("Worker intervals must be unique across stages; never charge twice")
    attempts = copy.deepcopy(original["attempts"] + continuation["attempts"])
    total = sum(row["seconds"] for row in attempts)
    return {"unique_attempts": len(attempts), "gpu_worker_seconds": total,
        "gpu_worker_hours": total / 3600, "attempts": attempts,
        "issues": copy.deepcopy(original["issues"] + continuation["issues"]),
        "scope": original["scope"]}


def diagnostics(rows):
    return {arm: {
        "native_finish_counts": dict(Counter(r["native_finish_reason"] or "no_complete_generation"
            for r in rows if r["arm"] == arm)),
        "extraction_empty": sum(r["extraction_empty"] is True for r in rows if r["arm"] == arm),
        "native_error_codes": dict(Counter(str(r["native_error_code"]) for r in rows
            if r["arm"] == arm and r["native_error_code"] is not None)),
        "known_actual_tokens": sum(r["actual_tokens"] or 0 for r in rows if r["arm"] == arm),
        "complete_generations": sum(r["actual_tokens"] is not None for r in rows if r["arm"] == arm),
    } for arm in prior.ARMS}


def build_report(original_report, continuation_root):
    root, reader = Path(continuation_root).resolve(), prior.Reader()
    old = reader.load(original_report)
    if (old.get("version") != prior.VERSION or old.get("read_only") is not True
            or old.get("original_records_modified") is not False
            or old.get("original_supervisor_status") != "paused"):
        raise ValueError("Require the preserved original closed-stage report")
    plan = reader.load(root / "plan.json")
    if (plan.get("version") != "software-calibration-host-v0.51"
            or plan.get("sha256") != prior.sha(prior.json_bytes(
                {k: v for k, v in plan.items() if k != "sha256"}))):
        raise ValueError("Continuation plan is not sealed")
    continuation = plan.get("continuation", {})
    if (continuation.get("kind") != "explicit_idle_rescheduling_original_unstarted_only"
            or continuation.get("previous_plan") != old["plan"]
            or continuation.get("previous_supervisor") != old["original_supervisor"]
            or continuation.get("previous_root") != old["root"]
            or continuation.get("new_candidates") != 0 or continuation.get("retries") != 0
            or continuation.get("old_uncertain_reservation_transferred") is not False):
        raise ValueError("Continuation does not bind the original report without replay")
    old_plan = reader.load(reader.verified(old["plan"]))
    excluded = [r["slot_id"] for r in old["rows"] if r["status"] != "not_started"]
    if (continuation.get("excluded_started_slots") != excluded
            or continuation.get("unchanged_source_except") != ["scripts/software_calibration_v051.py"]
            or set(plan["source_files"]) != set(old_plan["source_files"])
            or any(v != old_plan["source_files"][k] for k, v in plan["source_files"].items()
                   if k != "scripts/software_calibration_v051.py")
            or plan["contract"] != old["contract"]
            or any(plan[k] != old_plan[k] for k in ("cases", "model_manifest", "scorer_source"))
            or plan["maximum_generations"] != len(plan["rows"])
            or plan["maximum_actual_tokens"] != sum(r["maximum_tokens"] for r in plan["rows"])):
        raise ValueError("Original inventory, model-visible sources or budget changed")
    if (len(old_plan["rows"]) != 48 or any(
            any(row.get(k) != v for k, v in frozen.items())
            for row, frozen in zip(old["rows"], old_plan["rows"]))):
        raise ValueError("Reused report no longer describes the original frozen inventory")
    supervisor = reader.load(root / "supervisor.json")
    prior._require_final(supervisor)
    if supervisor.get("plan") != reader.reference(root / "plan.json"):
        raise ValueError("Continuation supervisor is bound to another plan")
    states = supervisor["states"]
    if set(states) != {r["worker"] for r in plan["rows"]}:
        raise ValueError("Continuation worker inventory changed")
    cost = prior.worker_cost(states)
    issues = list(cost["issues"])
    worker_evidence = []
    for name, state in states.items():
        declared = {str(Path(a["output"]).resolve()) for a in state["attempts"]}
        observed = {str(p.resolve()) for p in (root / name).glob("attempt-*") if p.is_dir()}
        if observed != declared:
            issues.append({"kind": "continuation_worker_directory_inventory", "worker": name})
        for attempt in state["attempts"]:
            output = Path(attempt["output"])
            item = {"worker": name, "output": str(output), "host_attempt": attempt}
            for filename in ("report.json", "task.json", "host-stop.json",
                             "startup/startup-resource-receipt.json"):
                path = output / filename
                if path.exists():
                    value = reader.load(path)
                    item[filename] = {"source": reader.reference(path), "value": value}
                    if filename == "report.json" and value != attempt.get("report"):
                        issues.append({"kind": "worker_report_differs_from_host_closure", "path": str(path)})
            item["native_faults"] = [{"source": reader.reference(path), "value": reader.load(path)}
                for path in sorted((output / "resident/calls").glob("*-fault.json"))]
            worker_evidence.append(item)
        last = state["attempts"][-1] if state["attempts"] else {}
        report = last.get("report", {})
        if supervisor["status"] == "complete" and (
                state["status"] != "complete" or last.get("exit_code") != 0
                or report.get("guard", {}).get("passed") is not True
                or report.get("source_plan") != reader.reference(root / "plan.json")
                or report.get("completed_slots") != [r["slot_id"] for r in plan["rows"] if r["worker"] == name]):
            issues.append({"kind": "complete_host_worker_closure_unresolved", "worker": name})
    source_lock = reader.load(prior._evidence(reader, plan, "software-calibration-v051-source-lock.json"))
    cases = reader.load(reader.verified(plan["cases"]))
    tasks = {row["ordinal"]: row for row in source_lock["tasks"]}
    new_rows = [prior._slot(reader, root, row, cases[row["ordinal"]], tasks[row["ordinal"]],
                           plan, source_lock, states) for row in plan["rows"]]
    rows = merge_unique_rows(old["rows"], plan["rows"], new_rows)
    billing = prior.generation_ledger(new_rows)
    ledger_matches = all(supervisor["ledger"].get(k) == billing[k] for k in LEDGER_KEYS)
    if not ledger_matches:
        issues.append({"kind": "continuation_host_ledger_differs", "analysis": billing,
                       "host": supervisor["ledger"]})
    if not math.isclose(supervisor["gpu_worker_seconds"], cost["gpu_worker_seconds"], abs_tol=1e-6):
        issues.append({"kind": "continuation_host_worker_seconds_differ"})
    if any(row["binding_issues"] for row in new_rows):
        issues.append({"kind": "continuation_slot_binding_issues",
                       "slots": [r["slot_id"] for r in new_rows if r["binding_issues"]]})
    merged_cost = merge_worker_cost(old["worker_cost"], cost)
    metrics, pairs = prior.outcome_summary(rows)
    merged_billing = prior.generation_ledger(rows)
    for key in ("complete_generations", "started_generations", "known_actual_tokens",
                "uncertain_reservation_tokens", "ledger_tokens"):
        if merged_billing[key] != old["billing"][key] + billing[key]:
            raise ValueError("Merged charges are not the unique original-plus-continuation sum")
    old_unknown = [r["slot_id"] for r in old["rows"] if r["status"] == "technical_unknown"]
    evidence = {
        "version": "v051-cal1-stage-review-evidence-v1", "release_performed": False,
        "score_threshold_applied": False, "all48_inventory_accounted_for": len(rows) == 48,
        "original_stage_report_reused": reader.reference(original_report),
        "original_supervisor": old["original_supervisor"],
        "continuation_supervisor": reader.reference(root / "supervisor.json"),
        "both_supervisors_closed": True, "continuation_integrity_issues": issues,
        "original_pending_preserved": old_unknown,
        "original_pending_scope": {
            "completed_outputs_missing_final_worker_guard": [r["slot_id"] for r in old["rows"]
                if r["status"] == "technical_unknown" and r["actual_tokens"] is not None],
            "started_without_complete_output": [r["slot_id"] for r in old["rows"]
                if r["attempted"] and r["actual_tokens"] is None]},
        "not_a_claim_all_outcomes_known": True,
        "next_stage_decision": "Separate authorized host admission; this report does not release CAL2/HOLD",
    }
    result = {**copy.deepcopy(old), "version": VERSION,
        "created_at_beijing": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "root": str(root), "original_report": reader.reference(original_report),
        "plan": reader.reference(root / "plan.json"), "source_commit": plan["source_commit"],
        "stage_source_commits": [old["source_commit"], plan["source_commit"]],
        "report_generator_source": reader.reference(Path(__file__)),
        "reused_binding_library": reader.reference(Path(prior.__file__)),
        "original_supervisor_status": "original_paused;continuation_" + supervisor["status"],
        "continuation_supervisor": reader.reference(root / "supervisor.json"),
        "continuation_pause": reader.load(root / "pause.json") if (root / "pause.json").exists() else None,
        "metrics": metrics, "pairs": pairs, "rows": rows, "diagnostics": diagnostics(rows),
        "all48_source_bound_outcomes_known": all(r["pass_at_1"] is not None for r in rows),
        "billing": merged_billing, "worker_cost": merged_cost,
        "host_ledger_matches": old["host_ledger_matches"] and ledger_matches,
        "worker_evidence": old["worker_evidence"] + worker_evidence,
        "integrity_issues": copy.deepcopy(old["integrity_issues"]) + issues,
        "source_and_measurement_integrity": old["source_and_measurement_integrity"] and not issues,
        "continuation_source_and_measurement_integrity": not issues,
        "stage_review_evidence": evidence,
        "stages": [
            {"name": "original", "root": old["root"], "status": old["original_supervisor_status"],
             "billing": old["billing"], "worker_cost": old["worker_cost"],
             "report_reused_without_reanalysis": reader.reference(original_report)},
            {"name": "idle_continuation", "root": str(root), "status": supervisor["status"],
             "billing": billing, "worker_cost": cost, "new_source_slots": len(new_rows),
             "host_ledger": supervisor["ledger"], "host_worker_seconds": supervisor["gpu_worker_seconds"],
             "historical_gpu_preference": plan["gpu_preference"], "historical_idle_policy": plan["idle_policy"]}],
        "raw_grade_counts": {arm: {str(value): sum(r["original_grade_pass_at_1"] == value
             for r in rows if r["arm"] == arm) for value in (0, 1, None)} for arm in prior.ARMS},
        "inherited_source_manifest": old["source_manifest"],
        "source_manifest": list(reader.manifest.values()),
        "scope": "Unique original48 CAL1 slots. Original15 started slots retained; only original33 untouched slots replaced by continuation. No new scoring, model, tokenizer, learning, CAL2 or HOLD call.",
    }
    return result


def markdown(report):
    lines = ["# v051 CAL-1唯一48槽合并结案", "",
        "本报告只读复用原阶段JSON，逐项绑定续阶段的新33槽。原15个已开始槽没有重跑、重评分或覆盖；"
        "原7个已评分但缺worker最终guard的结果及2个缺完整回包继续未决。原grade值与分析结果分别保存。", "",
        "| 阶段 | 正式宿主状态 | 完整生成 | 已开始缺完整回包 | 本阶段未开始 | 已知实际token | 不确定预约 | worker秒 |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for stage in report["stages"]:
        b, c = stage["billing"], stage["worker_cost"]
        lines.append(f"| {stage['name']} | {stage['status']} | {b['complete_generations']} | "
            f"{b['started_generations'] - b['complete_generations']} | {b['unstarted_slots']} | "
            f"{b['known_actual_tokens']} | {b['uncertain_reservation_tokens']} | {c['gpu_worker_seconds']:.6f} |")
    lines += ["", "原阶段33个未开始槽已由续阶段唯一补齐，因此合并库存未开始为0；"
        "阶段表保留原停止当时的33，不把它再次计入总库存。已知费用相加一次，不确定预约继续归原中断，"
        "不转为续阶段预算，也不声称是已知实际收费。", "",
        f"续阶段新来源/测量检查全部闭合：`{report['continuation_source_and_measurement_integrity']}`。"
        "这与原未决同时成立；并不将原缺guard解释为已证实权重发生变化。", "",
        "## 原评分与可归属结果", "",
        "| 路径 | 原评分通过 | 原评分失败 | 无原评分 | 来源绑定通过 | 来源绑定失败 | 来源绑定未决 |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for arm in prior.ARMS:
        raw, bound = report["raw_grade_counts"][arm], report["metrics"][arm]
        lines.append(f"| {arm} | {raw['1']} | {raw['0']} | {raw['None']} | {bound['successes']} | "
                     f"{bound['known_failures']} | {bound['unresolved']} |")
    lines += ["", "原评分只描述已保存代码的官方评分，不替代缺失的最终只读guard。"
        "全24题分母下的两路点估计和配对差仍为null。以下完整表保留各槽与配对、原停止、费用与来源限制。", "",
        prior.markdown(report).replace("# v051 CAL-1：原始Qwen3.5-9B两路推理桥接终态", "## 合并测量明细", 1),
        "## 独立阶段判断所需证据", "",
        "本次没有释放CAL2或HOLD，不依据通过率作下一阶段门槛。可供独立准入引用的是："
        "原阶段报告和两个已闭合宿主的SHA、原9个未决的来源与范围、新阶段有无新增完整性问题、唯一库存和费用。"
        "这些字段位于JSON的stage_review_evidence；是否准入由后续独立协议决定。", "",
        "续阶段执行时使用0/1/3/4/6/7空闲60秒且无compute进程、util为0的历史资源门，并发上限4；"
        "实际worker GPU按附表保留。之后用户解除GPU范围及空闲限制属于后续资源协议，不回写本阶段。", "",
        "本报告只新增有限合并CPU控制，不重复先前11项控制；无新模型、评分、分词、训练或学习更新。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-report", type=Path, required=True)
    parser.add_argument("--continuation-root", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("Preserve existing reports; use a new output prefix")
    result = build_report(args.original_report, args.continuation_root)
    for path, value in zip(outputs, [prior.json_bytes(result), markdown(result).encode()]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(value)
    print(json.dumps({"outputs": [str(p) for p in outputs], "billing": result["billing"],
        "metrics": result["metrics"], "continuation_integrity": result["continuation_source_and_measurement_integrity"],
        "worker_seconds": result["worker_cost"]["gpu_worker_seconds"], "release_performed": False}, indent=2))


if __name__ == "__main__":
    main()
