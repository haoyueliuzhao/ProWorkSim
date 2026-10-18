"""Terminal-only CAL2 r2 merge with preserved original history and environment audit.

This reader never reruns old scoring, a model, tokenizer, worker or measurement.
The original18 logical slots and the original failed R attempt are separate views.
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

from scripts import software_calibration_v051_cal2_report as base
from scripts.software_calibration_v051_merged_report import merge_worker_cost

VERSION = "software-calibration-v051-cal2-r2-unique-report-v1"
HOST_VERSION = "software-calibration-cal2-resume-r2-v0.51"
ZERO_R = "v051-cal2-boltons-1-R"
EXCLUDED = frozenset({"v051-cal2-boltons-1-P", "v051-cal2-boltons-1-U", "v051-cal2-boltons-2-P"})
ENVIRONMENT_AFFECTED = frozenset({ZERO_R, "v051-cal2-boltons-2-R", "v051-cal2-boltons-2-U"})


def merge_logical_rows(original, inventory, new_rows):
    """One logical row per original condition, retaining the old failed R layer."""
    base.validate_inventory(original)
    old = {r["slot_id"]: r for r in original}
    expected = [r["slot_id"] for r in original if r["slot_id"] not in EXCLUDED]
    if ([r["slot_id"] for r in inventory] != expected
            or [r["slot_id"] for r in new_rows] != expected or len(expected) != 15):
        raise ValueError("Only the exact fourteen untouched rows plus sole zero-generation R are eligible")
    for name in EXCLUDED:
        row = old[name]
        if (row["status"] != "technical_unknown" or row["R_code"] is not None
                or row["raw_R_code"] is not None or row["Q_terminal"] is not None
                or row["raw_Q_terminal"] is not None or row["R_joint"] is not None
                or row["raw_R_joint"] != 0 or not row["slot_entered"]
                or row["accounting"]["started_generations"] <= 0):
            raise ValueError("The three already-exposed original code unknowns must be preserved")
    zero = old[ZERO_R]
    if (zero["status"] != "technical_unknown" or not zero["slot_entered"]
            or zero["R_code"] is not None or zero["R_joint"] is not None
            or zero["accounting"]["started_generations"] != 0
            or zero["accounting"]["complete_generations"] != 0
            or zero["accounting"]["known_actual_tokens"] != 0):
        raise ValueError("The original R layer must remain its zero-generation technical attempt")
    for frozen, fresh in zip(inventory, new_rows):
        prior = old[frozen["slot_id"]]
        if any(prior.get(k) != v or fresh.get(k) != v for k, v in frozen.items()):
            raise ValueError("Original identity, seed or budget changed")
        if frozen["slot_id"] != ZERO_R and (prior["status"] != "not_started" or prior["slot_entered"]):
            raise ValueError("An earlier entered slot cannot be replaced by r2")
    fresh = {r["slot_id"]: r for r in new_rows}
    rows = []
    for prior in original:
        name = prior["slot_id"]
        row = copy.deepcopy(fresh.get(name, prior))
        row["logical_outcome_stage"] = "r2" if name in fresh else "initial_stage"
        row["original_stage_status"] = prior["status"]
        row["zero_generation_exception_history_retained"] = name == ZERO_R
        rows.append(row)
    history = [copy.deepcopy(r) for r in original if r["slot_entered"]]
    if len(history) != 4:
        raise ValueError("The four original entered technical attempts must remain in history")
    return rows, history


def apply_environment_overlay(rows, effects):
    """Invalid test infrastructure changes strict code validity, never raw records."""
    if {e["slot_id"] for e in effects} != ENVIRONMENT_AFFECTED or len(effects) != 3:
        raise ValueError("The independent audit must identify exactly its three affected slots")
    result = copy.deepcopy(rows)
    indexed = {r["slot_id"]: r for r in result}
    for effect in effects:
        row = indexed[effect["slot_id"]]
        if (effect.get("strict_code_status") != "technical_unknown"
                or effect.get("strict_R_code") is not None
                or effect.get("strict_Q_task_terminal") is not None
                or effect.get("preserve_original_R_joint") is not True
                or not effect.get("reason") or not row["slot_entered"]):
            raise ValueError("Environment override must be explicit, bounded and preserve fixed-delivery facts")
        row["pre_environment_overlay"] = {k: copy.deepcopy(row.get(k)) for k in (
            "status", "source_bound", "R_code", "Q_terminal", "R_joint", "cost_integrity_known")}
        row.update(status="technical_unknown", source_bound=False, R_code=None, Q_terminal=None)
        row["endpoint_source_binding"] = {"R_code": False, "Q_terminal": False,
            "R_joint": row["R_joint"] is not None if row["R_joint_applicable"] else "not_applicable"}
        row["environment_validity_overlay"] = copy.deepcopy(effect)
        row["binding_issues"] = [*row["binding_issues"], "independently_bound_test_environment_failure"]
    return result


def native_fee_evidence(rows, reported, *, zero_generation_audit=None):
    """Generation fees can be known despite unavailable or invalid test scores."""
    proofs, unknown = [], []
    known_sum = 0
    for row in rows:
        amount = None
        account = row.get("accounting")
        reason = "generation_fee_source_unresolved"
        if not row["slot_entered"] and row.get("cost_integrity_known") is True:
            amount, reason = 0, "unentered_or_bound_zero_model_startup"
        elif row["slot_id"] == ZERO_R and zero_generation_audit is not None:
            if (zero_generation_audit.get("actual_model_generation_tokens") == 0
                    and all(zero_generation_audit.get(k) == 0 for k in (
                        "native_generation_prepared", "native_generation_started",
                        "native_generation_complete", "native_generation_fault"))
                    and zero_generation_audit.get("actual_call_files") == []):
                amount, reason = 0, "separately_admitted_original_zero_generation_R_audit"
        elif account is not None:
            calls = [call for call in account["rows"] if call["generation_started"]]
            settled = (not account["integrity_errors"] and account["uncertain_reservation_tokens"] == 0
                and account["unknown_reservation_amount_count"] == 0
                and account["started_generations"] == account["complete_generations"]
                    == account["bound_complete_generations"] == len(calls)
                and all(type(call["bound_actual_tokens"]) is int for call in calls)
                and account["known_actual_tokens"] == sum(call["bound_actual_tokens"] for call in calls)
                and (bool(calls) or row.get("cost_integrity_known") is True)
                and "slot_start_not_bound_to_unique_host_attempt" not in row["binding_issues"])
            if settled:
                amount, reason = account["known_actual_tokens"], "all_actual_native_dispatches_have_bound_complete_usage"
        if amount is None:
            unknown.append(row["slot_id"])
        else:
            known_sum += amount
        proofs.append({"slot_id": row["slot_id"], "complete_actual_tokens": amount, "reason": reason,
                       "worker_attempt": row.get("worker_attempt"), "score_used_for_fee_closure": False})
    if not unknown and known_sum != reported["known_actual_tokens"]:
        raise ValueError("Independent closed fees differ from the archived known actual subtotal")
    return {"complete_actual_tokens": known_sum if not unknown else None,
        "reported_complete_actual_tokens_preserved": reported["complete_actual_tokens"],
        "known_actual_tokens": reported["known_actual_tokens"], "unknown_slot_fee_sources": unknown,
        "proofs": proofs, "scope": "Actual generation receipt accounting, independent of test validity; no old report field is changed"}


def combine_billing(original, new, logical_rows, *, original_fee, new_fee):
    keys = ("known_actual_tokens", "uncertain_reservation_tokens", "unknown_reservation_amount_count",
            "started_generations", "complete_generations", "source_bound_complete_generations",
            "prepared_without_generation")
    result = {key: original[key] + new[key] for key in keys}
    complete = original_fee["complete_actual_tokens"] is not None and new_fee["complete_actual_tokens"] is not None
    result["complete_actual_tokens"] = (original_fee["complete_actual_tokens"]
        + new_fee["complete_actual_tokens"]) if complete else None
    result["known_plus_reserved_tokens"] = (result["known_actual_tokens"] + result["uncertain_reservation_tokens"]
        if result["unknown_reservation_amount_count"] == 0 else None)
    result["unstarted_slots"] = sum(not row["slot_entered"] for row in logical_rows)
    result["scope"] = "Unique CAL2 stage charges: original once plus r2 once; no CAL1 or nested duration charge. Original report null is preserved separately; independent native-fee evidence may close full actual fees despite unknown scores."
    return result


def _frozen_original_binding(reader, old, old_ref, plan):
    refs = plan["original_references"]
    if (refs.get("original_stage_report") != old_ref or refs.get("original_plan") != old["plan"]
            or refs.get("original_supervisor") != old["supervisor"]
            or plan.get("original_root") != old["root"]):
        raise ValueError("r2 does not bind this exact original report and historical host")
    old_plan = reader.load(reader.verified(refs["original_plan"]))
    if (old_plan["rows"] != plan["original_rows"] or old["host_status"] != "paused"
            or plan["contract"] != old["contract"] or plan["limits"] != old["limits"]
            or plan["model_manifest"] != old_plan["model_manifest"] or plan["S_star"] != old_plan["S_star"]
            or plan.get("excluded_exposed_slots") != sorted(EXCLUDED)
            or plan.get("old_remaining_budget_transfer") != 0 or plan.get("old_scores_reconstructed") is not False
            or plan.get("old_terminal_code_unknowns_retained") is not True
            or plan.get("one_time_first_exposure_exception", {}).get("slot_id") != ZERO_R
            or plan["one_time_first_exposure_exception"].get("original_attempt_preserved") is not True):
        raise ValueError("The separately authorized r2 scope or historical preservation changed")
    for row, frozen in zip(old["rows"], plan["original_rows"]):
        if any(row.get(key) != value for key, value in frozen.items()):
            raise ValueError("Original report row no longer matches its frozen inventory")
    audit = reader.load(reader.verified(refs["zero_generation_R_audit"]))
    if (audit.get("version") != "v051-cal2-R-boltons1-readonly-initial-tree-diagnosis-v1"
            or any(audit.get(key) != 0 for key in ("native_generation_prepared", "native_generation_started",
                "native_generation_complete", "native_generation_fault", "actual_model_generation_tokens"))
            or audit.get("actual_call_files") != [] or audit.get("native_episode_files") != []):
        raise ValueError("The original R zero-exposure audit is not the preserved source")
    return audit


def read_environment_effects(reader, path, new_rows):
    audit = reader.load(path)
    if audit.get("version") != "v051-cal2-r2-first-execution-audit-v1":
        raise ValueError("Use the independently authored first-execution environment audit")
    effects = audit.get("affected_slots", [])
    indexed = {r["slot_id"]: r for r in new_rows}
    for effect in effects:
        row = indexed.get(effect.get("slot_id"))
        if row is None or effect.get("report_source") != row.get("report_source"):
            raise ValueError("Environment audit is not bound to this new stage's original worker report")
        reader.verified(effect["report_source"])
        runner = reader.verified(effect["terminal_runner_source"])
        evidence = row["terminal_tests"].get("execution", {}).get("evidence")
        if not evidence or runner.resolve() != (Path(evidence) / "result.json").resolve():
            raise ValueError("Environment audit runner source is not this exact terminal assessment")
    return effects, reader.reference(path)


def build_report(original_report, r2_root, *, environment_audit):
    root, reader = Path(r2_root).resolve(), base.common.Reader()
    # Refuse live work before reading any slot. Closed pending/unstarted rows remain unknown.
    supervisor = reader.load(root / "supervisor.json")
    base.common._require_final(supervisor)
    plan = reader.load(root / "plan.json")
    if (plan.get("version") != HOST_VERSION or plan.get("sha256") != base.common.sha(base.common.json_bytes(
            {k: v for k, v in plan.items() if k != "sha256"}))
            or supervisor.get("plan") != reader.reference(root / "plan.json")):
        raise ValueError("Require the sealed r2 plan and terminal bound host")
    old = reader.load(original_report)
    if old.get("version") != base.VERSION:
        raise ValueError("Reuse the original initial-stage report, without reanalysis")
    zero_audit = _frozen_original_binding(reader, old, reader.reference(original_report), plan)
    states = supervisor["states"]
    if set(states) != {r["slot_id"] for r in plan["rows"]}:
        raise ValueError("r2 states differ from its fifteen declared slots")
    new_cost = base.common.worker_cost(states)
    new_rows = [base.read_slot(reader, root, row, plan, states[row["slot_id"]]) for row in plan["rows"]]
    logical, old_history = merge_logical_rows(old["rows"], plan["rows"], new_rows)
    new_billing = base.aggregate_cost(new_rows)
    effects, audit_ref = read_environment_effects(reader, environment_audit, new_rows)
    logical = apply_environment_overlay(logical, effects)
    costs = merge_worker_cost(old["worker_cost"], new_cost)
    old_fee = native_fee_evidence(old["rows"], old["billing"], zero_generation_audit=zero_audit)
    new_fee = native_fee_evidence(new_rows, new_billing)
    billing = combine_billing(old["billing"], new_billing, logical, original_fee=old_fee, new_fee=new_fee)
    seen = set()
    for row in [*old_history, *new_rows]:
        for call in (row.get("accounting") or {}).get("rows", []):
            if not call["generation_started"]:
                continue
            key = (row["worker_attempt"], call["native_attempt_id"])
            if key in seen:
                raise ValueError("A native call appears in two charged histories")
            seen.add(key)
    new_issues = [{"slot_id": row["slot_id"], "problems": row["binding_issues"]}
                  for row in new_rows if row["binding_issues"]]
    new_issues.extend(new_cost["issues"])
    if not math.isclose(new_cost["gpu_worker_seconds"], supervisor.get("gpu_worker_seconds", -1), abs_tol=1e-6):
        new_issues.append({"kind": "r2_host_worker_seconds_mismatch"})
    for key in ("known_actual_tokens", "uncertain_reservation_tokens", "started_generations", "complete_generations"):
        if supervisor.get("ledger", {}).get(key) != new_billing[key]:
            new_issues.append({"kind": "r2_host_ledger_mismatch", "field": key,
                               "host": supervisor.get("ledger", {}).get(key), "analysis": new_billing[key]})
    metrics = {field: base.endpoint_metrics(logical, field, conditions=("P", "U") if "joint" in field else base.CONDITIONS)
               for field in ("R_code", "raw_R_code", "Q_terminal", "raw_Q_terminal", "R_joint", "raw_R_joint")}
    if any(metrics[field][contrast]["mean"] is not None for field in ("R_code", "raw_R_code", "Q_terminal", "raw_Q_terminal")
           for contrast in ("P_minus_R", "U_minus_P")):
        raise ValueError("Original three unknown code trajectories cannot produce complete paired point estimates")
    issues = [*copy.deepcopy(old["integrity_issues"]), *new_issues,
              {"kind": "independent_environment_invalidity", "source": audit_ref, "effects": effects}]
    return {"version": VERSION, "created_at_beijing": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "root": str(root), "read_only": True, "plan": reader.reference(root / "plan.json"),
        "supervisor": reader.reference(root / "supervisor.json"),
        "host_status": supervisor["status"],
        "original_report": reader.reference(original_report), "source_commit": plan["source_commit"],
        "historical_host_statuses": {"initial_stage": old["host_status"], "r2": supervisor["status"]},
        "stage_source_commits": [old["source_commit"], plan["source_commit"]],
        "report_source": reader.reference(Path(__file__)), "binding_library": reader.reference(Path(base.__file__)),
        "rows": logical, "metrics": metrics, "billing": billing, "worker_cost": costs,
        "status_counts": dict(Counter(r["status"] for r in logical)),
        "all18_source_bound": all(r["source_bound"] for r in logical),
        "original_entered_history": old_history, "original_entered_history_count": len(old_history),
        "original_technical_unknowns_erased": False,
        "r2_rows_before_environment_overlay": new_rows,
        "environment_audit": audit_ref, "environment_validity_effects": effects,
        "zero_generation_R_history": {"original_attempt": next(r for r in old_history if r["slot_id"] == ZERO_R),
            "zero_generation_audit": plan["original_references"]["zero_generation_R_audit"],
            "audit_original_generation_tokens": zero_audit["actual_model_generation_tokens"],
            "r2_first_exposure_attempt": next(r for r in logical if r["slot_id"] == ZERO_R),
            "old_unknown_preserved": True, "new_independent_model_candidate_added": False},
        "generation_fee_evidence": {"initial_stage": old_fee, "r2": new_fee,
            "original_zero_R_audit": plan["original_references"]["zero_generation_R_audit"]},
        "stages": [{"name": "initial_stage", "status": old["host_status"], "billing": old["billing"],
                    "independent_generation_fee": old_fee,
                    "worker_cost": old["worker_cost"], "report": reader.reference(original_report)},
                   {"name": "r2", "status": supervisor["status"], "billing": new_billing,
                    "independent_generation_fee": new_fee,
                    "worker_cost": new_cost, "host_ledger": supervisor.get("ledger"),
                    "source_binding_issues_before_environment_overlay": new_issues}],
        "integrity_issues": issues, "original_pause": old["original_pause"],
        "r2_pause": reader.load(root / "pause.json") if (root / "pause.json").exists() else None,
        "CAL1_ancillary_cost_only": copy.deepcopy(old.get("CAL1_ancillary_cost_only")),
        "inherited_source_manifest": old["source_manifest"], "source_manifest": list(reader.manifest.values()),
        "original_records_modified": False, "new_model_calls": 0, "new_scoring_calls": 0,
        "new_tokenizer_calls": 0, "new_actor_updates": 0, "new_critic_updates": 0,
        "new_backward_calls": 0, "HOLD_material_opened": False, "next_stage_released": False,
        "scope": "Original18 logical slots; preserve four original technical histories and one zero-exposure R exception. Closed independent environment audit invalidates only strict code/Q endpoints, never original raw outcomes or independently bound actual generation costs."}


def markdown(report):
    lines = ["# v051 CAL2：原18槽与r2历史层只读合并", "",
        "本报告复用原首阶段JSON，只读取已闭合r2宿主及其新记录。原4条技术未知历史完整保留，"
        "其中原3条有真实P/U模型轨迹的末树评分仍未知。原R零生成失败和r2首次真实模型曝光是两个历史层，"
        "映射同一个逻辑题/条件，不能删除旧失败或创造第19个独立样本。", "",
        "另叠加独立环境有效性审计：boltons-1/R、boltons-2/R、boltons-2/U的socket fixture破坏"
        "原asyncio/ssl导入，命中原P2P测试。保留原执行器raw结果，但严格R_code/Q_terminal为技术未知，"
        "不能把已证实的环境故障解释成业务失败。boltons-2/U的未提交事实及原R_joint=0保留，"
        "不推测修好环境后是否会提交。该暂停来自完整性门，不是通过率阈值。", "",
        "| 阶段 | 状态 | 完整回包 | 已知token | 不确定预约 | 原报告完整费用 | 独立原生费用 | worker秒 |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for stage in report["stages"]:
        b, c = stage["billing"], stage["worker_cost"]
        lines.append(f"| {stage['name']} | {stage['status']} | {b['complete_generations']} | {b['known_actual_tokens']} | "
            f"{b['uncertain_reservation_tokens']} | {base.display(b['complete_actual_tokens'])} | "
            f"{base.display(stage['independent_generation_fee']['complete_actual_tokens'])} | {c['gpu_worker_seconds']:.6f} |")
    lines += ["", "原227,876token及413.1480391025543秒只计一次；原complete_actual_tokens=null保留。"
        "独立账目通过已准入零生成R证明及完整native usage判断费用；评分环境未知不等于费用未知。"
        "环境审计只改变代码结果的严格有效性，不把已绑定实际回包费用改成0。原阶段14未开数不与r2未开数相加；"
        "当前未开始状态按18个逻辑槽列示，未开始/在途不称失败。报告拒绝仍有在途worker的宿主。", "",
        "## 原R的两个历史层", "",
        "| 层 | 含义 | 结果处理 |",
        "|---|---|---|",
        "| 原首阶段 | 已装载、初树读取拒绝，native prepared/started/complete/fault均0 | 原technical_unknown、禁重排标记和worker成本不改 |",
        "| r2 | 独立新准入的一次首次模型曝光；不复用旧模型状态 | 新原结果单独保存，环境审计后的严格末树端点未知 |", "",
        "原首阶段还包含CRLF保真与文件映射排序缺陷、测试child间接依赖导入故障；r2的已披露窄修"
        "不倒改旧3条真实轨迹的失败反馈。socket fixture缺陷是新的独立环境有效性问题。各版本及暂停分别保留。", "",
        "## 固定面板和完整明细", "",
        base.markdown(report).replace("# v051 CAL2：固定六题、三条件只读结案", "### 合并逻辑面板", 1),
        "## 必须保留的比较限制", "",
        "即使其他槽全部有结果，原3条真实P/U轨迹也不补评分、不重采。因此完整六题P−R与U−P点估计"
        "继续null；独立环境审计再使相应三条新末树端点未知。不能用raw固定交付0替代严格代码未知，"
        "不能删去未知后改分母。原执行器raw R_code表含环境无效观测，仅供原记录核对，不能作有效业务成绩。", "",
        "JSON同时保留original_entered_history、r2_rows_before_environment_overlay、独立audit来源、"
        "environment_validity_effects和最终逻辑rows。没有写回任一旧行、run、源码快照、权重或评分。"
        "后续未开库存如获新的修复/准入须另root记录，本报告不自动释放或启动。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-report", type=Path, required=True)
    parser.add_argument("--r2-root", type=Path, required=True)
    parser.add_argument("--environment-audit", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    outputs = [Path(str(args.output_prefix) + suffix) for suffix in (".json", ".md")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("Preserve original reports; use a fresh output prefix")
    report = build_report(args.original_report, args.r2_root, environment_audit=args.environment_audit)
    for path, content in zip(outputs, [base.common.json_bytes(report), markdown(report).encode()]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    print(json.dumps({"outputs": [str(p) for p in outputs], "statuses": report["status_counts"],
        "billing": report["billing"], "old_histories_preserved": report["original_entered_history_count"],
        "new_model_calls": 0, "new_scoring_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
