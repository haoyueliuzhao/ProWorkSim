"""Join two existing terminal summaries once; never read trajectories or run experiments.

Do not execute until the root agent confirms HOLD has reached its terminal state.
Default output is immutable: an existing file is always rejected.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

VERSION = "v051-overall-final-readonly-v1"
CONDITIONS = ("S_star", "B", "Q_plus", "Q_minus")
METRICS = ("F", "Q_joint", "R_token", "Q_token")
QUALIFIED_TASKS = (
    "hold-iniconfig-1", "hold-iniconfig-2", "hold-dominate-1", "hold-dominate-2",
)
ALL_TASKS = (
    "hold-funcy-1", "hold-funcy-2", "hold-python-slugify-1", "hold-python-slugify-2",
    *QUALIFIED_TASKS,
)
DIFFERENCES = (("B", "S_star"), ("Q_plus", "B"), ("Q_minus", "B"), ("Q_plus", "Q_minus"))


def source_reference(path, raw):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def load_summary(path):
    raw = path.read_bytes()
    return json.loads(raw), source_reference(path, raw)


def required_count(mapping, key):
    value = mapping[key]
    if type(value) is not int or value < 0:
        raise ValueError("Required nonnegative reported count is missing or invalid: " + key)
    return value


def required_seconds(mapping, key):
    value = mapping[key]
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Required reported worker seconds are unknown or invalid: " + key)
    return value


def validate_terminal_inputs(calibration, holdout):
    if calibration.get("version") != "v051-final-calibration-subtotals-v1":
        raise ValueError("Use the existing unique CAL0/CAL1/CAL2 subtotal")
    if (holdout.get("version") != "software-holdout-v051-final-v1"
            or holdout.get("host_status") not in ("complete", "paused")):
        raise ValueError("A terminal formal HOLD final report is required")
    cal_total = calibration["calibration_generation_subtotal"]
    if cal_total.get("HOLD_included") is not False or cal_total["complete_actual_tokens"] is not None:
        raise ValueError("Preserve CAL1 incomplete actual fees and add HOLD exactly once")
    if (holdout["logical_slots"] != 32 or holdout["logical_tasks"] != 8
            or holdout["qualified_case_ids"] != list(QUALIFIED_TASKS)):
        raise ValueError("Preserve the original eight tasks and the admitted four-task subset")
    if set(calibration["phases"]) != {"CAL0", "CAL1", "CAL2"}:
        raise ValueError("CAL phases must come directly from the unique existing subtotal")
    if any(cal_total[key] != 0 for key in ("new_actor_updates", "new_critic_updates", "new_backward_calls")):
        raise ValueError("This window authorizes no learning update")
    if any(holdout[key] != 0 for key in ("new_parameter_updates", "new_backward_calls")):
        raise ValueError("The HOLD final report declares an unexpected update")
    bill = holdout["billing"]
    if any(bill[key] != 0 for key in ("new_actor_steps", "new_critic_steps", "new_backward_calls")):
        raise ValueError("The HOLD ledger declares an unexpected update")
    if not isinstance(bill["integrity_errors"], list):
        raise ValueError("Preserve the reported HOLD billing integrity status")
    rows = holdout["rows"]
    expected = {(task, condition) for task in ALL_TASKS for condition in CONDITIONS}
    if len(rows) != 32 or {(row["task_id"], row["condition"]) for row in rows} != expected:
        raise ValueError("Missing or duplicated task/condition cells in the original32 panel")
    for row in rows:
        if row["task_id"] not in QUALIFIED_TASKS:
            if (row["status"] != "source_or_input_blocked" or row["started"] is not False
                    or any(row[metric] is not None for metric in METRICS)):
                raise ValueError("Source-blocked tasks must retain null formal outcomes without execution")
        elif row["status"] != "closed" and any(row[metric] is not None for metric in METRICS):
            raise ValueError("An unclosed row cannot acquire a formal outcome")
    for metric in METRICS:
        full = holdout["metrics"][metric]
        if any(full[condition]["denominator"] != 8 or full[condition]["mean"] is not None
               for condition in CONDITIONS):
            raise ValueError("Keep the original eight-task means null with four source-blocked tasks")
        if any(full["paired"][f"{left}_minus_{right}"]["mean"] is not None
               for left, right in DIFFERENCES):
            raise ValueError("Keep the full eight-task effects null")


def subset_description(holdout, bounded, paired):
    # Only formal endpoint columns enter these functions. raw_outcomes are not a fallback.
    rows = [row for row in holdout["rows"] if row["task_id"] in QUALIFIED_TASKS]
    metrics = {}
    for metric in METRICS:
        metrics[metric] = {
            condition: bounded([row[metric] for row in rows if row["condition"] == condition])
            for condition in CONDITIONS
        }
        metrics[metric]["paired"] = {
            f"{left}_minus_{right}": paired(rows, left, right, metric, list(QUALIFIED_TASKS))
            for left, right in DIFFERENCES
        }
    return {
        "scope": "仅原事前来源及输入合格的四题子集；每题等权，不是完整八题主结果，也不是按模型成绩选题。",
        "task_ids": list(QUALIFIED_TASKS),
        "task_denominator": 4,
        "logical_slots": 16,
        "all16_closed": all(row["status"] == "closed" for row in rows),
        "metrics": metrics,
        "mean_rule": "每个状态或配对差的所有所需正式值均known才给mean；否则null，并保留未知界限。",
        "full_eight_task_main_effects_remain_null": True,
        "new_learning_benefit_claimed": False,
        "combined_with_v050": False,
    }


def join_costs(calibration, holdout):
    cal = calibration["calibration_generation_subtotal"]
    bill, worker = holdout["billing"], holdout["worker_cost"]
    result = {
        key: required_count(cal, key) + required_count(bill, key)
        for key in ("known_actual_tokens", "uncertain_reservation_tokens", "started_generations", "complete_generations")
    }
    result["ledger_tokens"] = required_count(cal, "known_plus_reserved_tokens") + required_count(bill, "ledger_tokens")
    result["known_plus_reserved_tokens"] = result["ledger_tokens"]
    result["complete_actual_tokens"] = None
    result["complete_actual_tokens_null_reason"] = "CAL1原两次已开始请求无完整回包；加入HOLD后仍不补齐旧实际费用。"
    result["unique_gpu_worker_intervals"] = required_count(cal, "gpu_worker_unique_attempts") + required_count(worker, "unique_intervals")
    result["gpu_worker_seconds"] = required_seconds(cal, "gpu_worker_seconds") + required_seconds(worker, "seconds")
    result["gpu_worker_hours"] = result["gpu_worker_seconds"] / 3600
    result["HOLD_reported_complete_actual_tokens"] = bill["complete_actual_tokens"]
    result["HOLD_billing_integrity_errors"] = copy.deepcopy(bill["integrity_errors"])
    result["ledger_scope"] = "逐阶段已报告的known actual与known uncertain reservation相加；未定金额或完整性问题原样保留，账本量不冒称实际收费。"
    result["worker_scope"] = "仅CAL既有唯一worker小计加HOLD既有唯一interval小计；不读取或再加generation/scoring/model/phase嵌套时长。"
    result.update(new_actor_updates=0, new_critic_updates=0, new_parameter_updates=0, new_backward_calls=0)
    return result


def aggregate(calibration, holdout, *, sources, bounded, paired, metric_library_ref, own_ref):
    validate_terminal_inputs(calibration, holdout)
    hold_rows = []
    keys = ("slot_id", "task_id", "condition", "status", "host_state", "started", "submitted",
            *METRICS, "raw_outcomes", "qualification", "worker_report", "started_record", "interruption")
    for row in holdout["rows"]:
        hold_rows.append({key: copy.deepcopy(row[key]) for key in keys if key in row})
    hold_billing = {key: copy.deepcopy(value) for key, value in holdout["billing"].items() if key != "outcomes"}
    hold_worker = {key: copy.deepcopy(value) for key, value in holdout["worker_cost"].items() if key != "intervals"}
    return {
        "version": VERSION,
        "created_at_beijing": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "read_only": True,
        "sources": sources,
        "aggregation_source": own_ref,
        "bounded_and_paired_library": metric_library_ref,
        "calibration": {
            "phases": copy.deepcopy(calibration["phases"]),
            "generation_subtotal": copy.deepcopy(calibration["calibration_generation_subtotal"]),
            "report_sources": copy.deepcopy(calibration["report_sources"]),
            "supporting_stage_decisions": copy.deepcopy(calibration["supporting_stage_decisions"]),
            "source_json_pointers": ["/phases", "/calibration_generation_subtotal"],
        },
        "HOLD": {
            "host_status": holdout["host_status"],
            "plan": copy.deepcopy(holdout["plan"]),
            "supervisor": copy.deepcopy(holdout["supervisor"]),
            "admission": copy.deepcopy(holdout["admission"]),
            "source_commit": copy.deepcopy(holdout["source_commit"]),
            "logical_slots": 32,
            "logical_tasks": 8,
            "qualified_case_ids": list(QUALIFIED_TASKS),
            "source_blocked_case_ids": [task for task in ALL_TASKS if task not in QUALIFIED_TASKS],
            "status_counts": copy.deepcopy(holdout["status_counts"]),
            "closed_successes": holdout["closed_successes"],
            "closed_submitted_not_full": holdout["closed_submitted_not_full"],
            "closed_no_submit": holdout["closed_no_submit"],
            "rows": hold_rows,
            "full_eight_task_metrics": copy.deepcopy(holdout["metrics"]),
            "qualified_four_task_description": subset_description(holdout, bounded, paired),
            "billing": hold_billing,
            "worker_cost": hold_worker,
            "worker_intervals_source": {"source": sources["HOLD_final"], "json_pointer": "/worker_cost/intervals"},
            "source_json_pointers": ["/rows", "/metrics", "/billing", "/worker_cost"],
        },
        "overall_cost": join_costs(calibration, holdout),
        "anti_double_counting_rules": copy.deepcopy(calibration["anti_double_counting_rules"]) + [
            "HOLD final仅加一次；其费用不与原CAL1/CAL2附记或阶段费用再次合并。",
            "这里只读取两个终态摘要；保留的底层path/SHA引用不被打开，原报告与轨迹不重生成。",
        ],
        "interpretation_limits": [
            "CAL0是旧32终态只读核对，不是本轮新模型样本；旧v050费用不导入。",
            "CAL1严格39已知与9缺证保持；完整24题路径均值与差仍null，raw grade不替代guard。",
            "CAL2严格12代码已知与6技术未知保持；完整六题R/P/U与差仍null，raw或R_joint不替代严格代码端点。",
            "HOLD完整32行和四个source-blocked任务保留；全8题主结果仍null，四题描述不能冒称完整面板。",
            "HOLD原input false与独立branch_id只读身份修订的历史由admission来源引用保留；实际模型可见输入未改。",
            "旧检查点在新任务和执行条件下的观察，不与v050合并，不构成新增学习或普遍协作收益证据。",
            "CAL和HOLD端点、任务及分母不同，不计算跨阶段总体成功率。",
        ],
        "original_records_modified": False,
        "new_model_calls": 0,
        "new_scoring_calls": 0,
        "new_SDK_requests": 0,
        "new_tokenizer_calls": 0,
        "new_test_executions": 0,
        "new_actor_updates": 0,
        "new_critic_updates": 0,
        "new_parameter_updates": 0,
        "new_backward_calls": 0,
        "raw_trajectory_reads": 0,
        "CAL_recomputation": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    project = args.project_root.resolve()
    cal_path = project / "artifacts/software-calibration-v051/final-calibration-subtotals.json"
    hold_path = project / "docs/experiments/software-holdout-v051-final.json"
    output = project / "docs/experiments/software-calibration-v051-overall-final.json"
    if output.exists():
        raise FileExistsError("Do not overwrite an existing overall final report: " + str(output))
    calibration, cal_ref = load_summary(cal_path)
    holdout, hold_ref = load_summary(hold_path)
    # Reuse the already-controlled pure formulas, without calling summarize() or main().
    sys.path.insert(0, str(project))
    from scripts.software_holdout_v051_report import bounded, paired
    library_path = project / "scripts/software_holdout_v051_report.py"
    own_path = Path(__file__).resolve()
    result = aggregate(
        calibration, holdout, sources={"calibration_subtotals": cal_ref, "HOLD_final": hold_ref},
        bounded=bounded, paired=paired,
        metric_library_ref=source_reference(library_path, library_path.read_bytes()),
        own_ref=source_reference(own_path, own_path.read_bytes()),
    )
    raw = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also rejects a file created after the preliminary check.
    with output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"output": source_reference(output, raw), "overall_cost": result["overall_cost"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
