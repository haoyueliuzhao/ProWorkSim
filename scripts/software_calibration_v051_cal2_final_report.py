"""Compact terminal CAL2 report: preserved r1+r2 stage plus the unique r3 seven.

Large original reports remain immutable source artifacts. This report retains
bounded metrics and exact references, not nested native/test/supervisor bodies.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import software_calibration_v051_cal2_report as base
from scripts.software_calibration_v051_cal2_r2_report import native_fee_evidence
from scripts.software_calibration_v051_merged_report import merge_worker_cost

VERSION = "software-calibration-v051-cal2-final-compact-v1"
HOST_VERSION = "software-calibration-cal2-resume-r3-v0.51"
PREDECESSOR_VERSION = "software-calibration-v051-cal2-r2-unique-report-v1"
PENDING = ("v051-cal2-parse-2-U", "v051-cal2-xmltodict-1-P", "v051-cal2-xmltodict-1-U",
           "v051-cal2-xmltodict-1-R", "v051-cal2-xmltodict-2-U", "v051-cal2-xmltodict-2-R",
           "v051-cal2-xmltodict-2-P")


def compact_row(row, *, origin):
    fields = ("slot_id", "task_id", "condition", "seed", "generation_tokens", "decisions", "attempts",
        "project_public_tests", "status", "source_bound", "slot_entered", "R_joint_applicable",
        "raw_R_code", "R_code", "raw_Q_terminal", "Q_terminal", "raw_R_joint", "R_joint", "R_token",
        "administrative_censoring", "gpu_index", "report_source", "worker_attempt",
        "original_stage_status", "logical_outcome_stage", "zero_generation_exception_history_retained",
        "host_final_evaluation_attempts", "host_final_test_executions")
    result = {key: row.get(key) for key in fields}
    result["origin_row"] = origin
    tests = row.get("terminal_tests") or {}
    result["terminal_tests"] = {key: tests.get(key) for key in (
        "frozen_test_count", "observed_test_nodes", "observed_passed", "observed_failed", "observed_errors",
        "observed_skipped", "not_run_count", "collection_failure", "all_expected_tests_observed",
        "Q_terminal", "Q_full_node_outcome_bounds")}
    account = row.get("accounting") or {}
    result["generation_accounting_summary"] = {key: account.get(key) for key in (
        "started_generations", "complete_generations", "bound_complete_generations", "known_actual_tokens",
        "uncertain_reservation_tokens", "unknown_reservation_amount_count", "complete_actual_tokens")}
    result["environment_code_invalidated"] = "environment_validity_overlay" in row
    result["binding_issue_count"] = len(row.get("binding_issues", []))
    result["preexecution_refusal_counts"] = (row.get("preexecution_refusal_measurement") or {}).get("counts")
    result["mechanical_decision"] = (row.get("original_verdict") or {}).get("decision")
    result["measurement_decision"] = (row.get("measurement") or {}).get("decision")
    boundary = row.get("raw_stop_reason")
    result["stop_summary"] = ({key: boundary.get(key) for key in ("status", "kind", "reason", "member")}
                              if isinstance(boundary, dict) else boundary)
    return result


def merge_rows(old, inventory, new_rows, *, predecessor_reference):
    base.validate_inventory(old)
    if ([r["slot_id"] for r in old if r["status"] == "not_started"] != list(PENDING)
            or [r["slot_id"] for r in inventory] != list(PENDING)
            or [r["slot_id"] for r in new_rows] != list(PENDING)):
        raise ValueError("Only the exact seven originally untouched r3 slots may be inserted")
    indexed = {r["slot_id"]: r for r in old}
    for frozen, new in zip(inventory, new_rows):
        prior = indexed[frozen["slot_id"]]
        if prior["slot_entered"] or any(prior.get(k) != v or new.get(k) != v for k, v in frozen.items()):
            raise ValueError("r3 changed an identity/budget or replaced an entered slot")
    new_indexed = {row["slot_id"]: row for row in new_rows}
    rows = []
    for index, prior in enumerate(old):
        name = prior["slot_id"]
        if name in new_indexed:
            new = new_indexed[name]
            origin = {"worker_report": new.get("report_source"), "stage": "r3"}
            row = compact_row(new, origin=origin)
            row["logical_outcome_stage"] = "r3"
        else:
            row = compact_row(prior, origin={"report": predecessor_reference, "json_pointer": f"/rows/{index}"})
        rows.append(row)
    return rows


def combine_billing(previous, new, *, new_fee, rows):
    keys = ("known_actual_tokens", "uncertain_reservation_tokens", "unknown_reservation_amount_count",
            "started_generations", "complete_generations", "source_bound_complete_generations", "prepared_without_generation")
    result = {key: previous[key] + new[key] for key in keys}
    a, b = previous["complete_actual_tokens"], new_fee["complete_actual_tokens"]
    result["complete_actual_tokens"] = a + b if a is not None and b is not None else None
    result["known_plus_reserved_tokens"] = (result["known_actual_tokens"] + result["uncertain_reservation_tokens"]
        if result["unknown_reservation_amount_count"] == 0 else None)
    result["unstarted_slots"] = sum(row["status"] == "not_started" for row in rows)
    result["scope"] = "One predecessor r1+r2 merged subtotal plus r3 only. Initial-stage and CAL1 charges are not added again."
    return result


def verify_predecessor(previous, plan, reference):
    refs = plan["predecessor_references"]
    if (previous.get("version") != PREDECESSOR_VERSION or previous.get("host_status") != "paused"
            or refs.get("predecessor_stage_report") != reference
            or refs.get("predecessor_plan") != previous.get("plan")
            or refs.get("predecessor_supervisor") != previous.get("supervisor")
            or plan.get("predecessor_root") != previous.get("root")
            or refs.get("environment_audit") != previous.get("environment_audit")):
        raise ValueError("The single predecessor report/host/audit source is not exactly bound")


def build_report(predecessor_report, r3_root):
    reader, root = base.common.Reader(), Path(r3_root).resolve()
    supervisor = reader.load(root / "supervisor.json")
    base.common._require_final(supervisor)
    plan = reader.load(root / "plan.json")
    if (plan.get("version") != HOST_VERSION or plan.get("sha256") != base.common.sha(base.common.json_bytes(
            {k: v for k, v in plan.items() if k != "sha256"}))
            or supervisor.get("plan") != reader.reference(root / "plan.json")):
        raise ValueError("Require the exact sealed r3 plan and its closed host")
    old = reader.load(predecessor_report)
    old_ref = reader.reference(predecessor_report)
    verify_predecessor(old, plan, old_ref)
    states = supervisor["states"]
    if set(states) != set(PENDING):
        raise ValueError("r3 host does not contain only the original seven slots")
    new_cost = base.common.worker_cost(states)
    raw_rows = [base.read_slot(reader, root, row, plan, states[row["slot_id"]]) for row in plan["rows"]]
    rows = merge_rows(old["rows"], plan["rows"], raw_rows, predecessor_reference=old_ref)
    new_bill = base.aggregate_cost(raw_rows)
    new_fee = native_fee_evidence(raw_rows, new_bill)
    costs = merge_worker_cost(old["worker_cost"], new_cost)
    billing = combine_billing(old["billing"], new_bill, new_fee=new_fee, rows=rows)
    issues = [{"slot_id": r["slot_id"], "binding_issue_count": len(r["binding_issues"]),
               "worker_report": r["report_source"]} for r in raw_rows if r["binding_issues"]]
    if not math.isclose(new_cost["gpu_worker_seconds"], supervisor.get("gpu_worker_seconds", -1), abs_tol=1e-6):
        issues.append({"kind": "r3_host_worker_seconds_mismatch"})
    for key in ("known_actual_tokens", "uncertain_reservation_tokens", "started_generations", "complete_generations"):
        if new_bill[key] != supervisor.get("ledger", {}).get(key):
            issues.append({"kind": "r3_host_ledger_mismatch", "field": key})
    metrics = {field: base.endpoint_metrics(rows, field, conditions=("P", "U") if "joint" in field else base.CONDITIONS)
        for field in ("R_code", "raw_R_code", "Q_terminal", "raw_Q_terminal", "R_joint", "raw_R_joint")}
    if any(metrics[field][contrast]["mean"] is not None for field in ("R_code", "raw_R_code", "Q_terminal", "raw_Q_terminal")
           for contrast in ("P_minus_R", "U_minus_P")):
        raise ValueError("Historical unknown code outcomes cannot yield a complete panel contrast")
    return {"version": VERSION, "created_at_beijing": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "root": str(root), "read_only": True, "host_status": supervisor["status"],
        "plan": reader.reference(root / "plan.json"), "supervisor": reader.reference(root / "supervisor.json"),
        "source_commit": plan["source_commit"], "predecessor_report": old_ref,
        "report_source": reader.reference(Path(__file__)), "binding_library": reader.reference(Path(base.__file__)),
        "rows": rows, "metrics": metrics, "billing": billing, "worker_cost": costs,
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "all18_source_bound": all(r["source_bound"] for r in rows),
        "historical_four_technical_attempts": {"count": 4, "source": old_ref, "json_pointer": "/original_entered_history"},
        "zero_generation_R_history": {"source": old_ref, "json_pointer": "/zero_generation_R_history"},
        "environment_audit": old["environment_audit"],
        "historical_environment_invalidated_slots": [r["slot_id"] for r in rows if r["environment_code_invalidated"]],
        "stages": [{"name": "initial_plus_r2_once", "report": old_ref, "billing": old["billing"],
                    "worker_seconds": old["worker_cost"]["gpu_worker_seconds"]},
                   {"name": "r3", "billing": new_bill, "independent_generation_fee": new_fee,
                    "worker_seconds": new_cost["gpu_worker_seconds"], "supervisor": reader.reference(root / "supervisor.json")}],
        "integrity_issues": [{"kind": "historical_preserved_issues", "source": old_ref,
            "json_pointer": "/integrity_issues"}, *issues],
        "r3_binding_issues": issues, "original_pause": {"historical": old_ref,
            "r3": reader.reference(root / "pause.json") if (root / "pause.json").exists() else None},
        "CAL1_ancillary_cost_only": {"included_in_CAL2_costs": False, "source": old_ref,
                                    "json_pointer": "/CAL1_ancillary_cost_only"},
        "source_manifest": list(reader.manifest.values()),
        "original_records_modified": False, "new_model_calls": 0, "new_scoring_calls": 0,
        "new_tokenizer_calls": 0, "new_actor_updates": 0, "new_critic_updates": 0,
        "new_backward_calls": 0, "HOLD_material_opened": False, "next_stage_released": False,
        "scope": "Compact original18 logical panel, immutable predecessor and worker references; no embedded original reports or raw native/test output."}


def markdown(report):
    return "\n".join(["# v051 CAL2最终唯一合并", "",
        "本报告以原r1+r2阶段合并为单一前阶段来源，只增加r3原七条库存。大段原记录仍在原件，"
        "各行以path、SHA及JSON位置追溯，未重复嵌入或重新生成45MB阶段报告。", "",
        "原3条真实P/U轨迹代码未知、原R零生成失败历史及r2三条受socket环境故障影响的严格代码未知均保留。"
        "旧raw得分不是有效业务失败；boltons-2/U的无固定提交R_joint=0保持。原四历史尝试和R双历史层未删除。", "",
        base.markdown(report).replace("# v051 CAL2：固定六题、三条件只读结案", "## 原18槽指标与费用", 1),
        "完整六题P−R与U−P点估计仍null；不能用已知子集、raw固定交付0或环境失效raw代码0补全未知。"
        "费用独立于代码评分有效性，前阶段原227,876token已包含在r1+r2单一小计内，不再另加。"
        "本报告不启动HOLD或任何后继，来源/初始输入资格仍须独立准入。", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-report", type=Path, required=True)
    parser.add_argument("--r3-root", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    paths = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(path.exists() for path in paths):
        raise FileExistsError("Use a new output prefix; original reports are immutable")
    report = build_report(args.predecessor_report, args.r3_root)
    for path, content in zip(paths, [base.common.json_bytes(report), markdown(report).encode()]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    print(json.dumps({"paths": [str(p) for p in paths], "statuses": report["status_counts"],
                      "billing": report["billing"], "new_model_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
