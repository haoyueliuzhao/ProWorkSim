#!/usr/bin/env python3
"""CAL-0: read-only audit of every fixed v050 development terminal.

Only the Python standard library is imported. No candidate code, world,
acceptance driver, model, tokenizer, checkpoint or GPU operation is executed.
Original evidence is read; reports are written only below the chosen output.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


VERSION = "software-calibration-v051-cal0-v1"
ROOT = Path(__file__).resolve().parents[1]
REPORT = Path("docs/experiments/software-learning-v050-final.json")
BRANCHES = ("S_star", "B", "Q_plus", "Q_minus")
FAILURES = {
    "org50-dev-DA-s1-S_star": {
        "case_id": "allocation-sixteen",
        "file": "allocation.py",
        "obligation": "Give one additional cent to each of the first remaining accounts ordered by decreasing integer remainder; ties use ascending ID.",
        "code_fragment": 'results[0]["cents"] += extra',
        "finding_zh": "16个等权账户分3分，应给按ID排序的前三账户各1分；固定提交把3分全给首账户。代码直接将extra整体加到results[0]，与公开的逐账户加1要求不符。",
    },
    "org50-dev-DD-s2-B": {
        "case_id": "patch-private-interior-insert",
        "file": "textpatch.py",
        "obligation": "an insertion `[x,x)` conflicts with a nonempty `[a,b)` precisely when `a < x < b`.",
        "code_fragment": "if max(a, c) < min(b, d):",
        "finding_zh": "原请求在非空替换区间内部插入，应拒绝为patch:conflict；固定提交返回Icd。冲突循环仅检查两区间正长度交叠，没有覆盖零长度插入位于区间内部的情况。",
    },
    "org50-dev-DC-s1-Q_plus": {
        "case_id": "inventory-private-invalid-id",
        "file": "inventory.py",
        "obligation": "SKU names and reservation IDs are ASCII strings matching `[a-z][a-z0-9_]{0,15}`.",
        "code_fragment": 'if not _name(operation["id"]):',
        "finding_zh": "原请求用大写X作reserve ID，应拒绝为inventory:invalid；固定提交返回包含X的成功预订。固定代码只在cancel分支校验operation.id，reserve分支遗漏相同校验。",
    },
    "org50-dev-DD-s2-Q_plus": {
        "case_id": "patch-private-endpoints",
        "file": "textpatch.py",
        "obligation": "At each coordinate emit same-point insertions in ascending ID order, after any replacement ending there and before any replacement starting there.",
        "code_fragment": 'coordinate_patches[coord].sort(key=lambda x: x[0])',
        "finding_zh": "原请求同时替换bc并在两端插入方括号，应返回a[M]d；固定提交返回aM[bc]d。代码将同坐标的替换与插入一起按ID排序，并逐次重设原文游标，违反先端点插入后起始替换的顺序并重放被替换原文。",
    },
}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def exact(left, right):
    """The frozen scorer's JSON-type-strict comparison, without importing it."""
    return json.dumps(left, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False, allow_nan=False
    )


def comparable(value):
    return {k: v for k, v in value.items() if k != "source_api_trace"} if isinstance(value, dict) else value


class Reader:
    def __init__(self, root):
        self.root = root
        self.sources = {}

    def path(self, value):
        path = Path(value)
        # Original absolute paths are rebased only when their repository suffix is known.
        marker = "/ProWorkSim/"
        if path.is_absolute() and marker in str(path):
            return self.root / str(path).split(marker, 1)[1]
        return path if path.is_absolute() else self.root / path

    def ref(self, path):
        path = self.path(path)
        data = path.read_bytes()
        name = str(path.relative_to(self.root))
        reference = {"path": name, "sha256": sha(data), "bytes": len(data)}
        self.sources[name] = reference
        return reference

    def read(self, path):
        path = self.path(path)
        self.ref(path)
        return json.loads(path.read_text())


def decode_saved(execution, marker):
    matches = [line[len(marker):] for line in execution["output"].splitlines() if line.startswith(marker)]
    if len(matches) != 1:
        raise ValueError("Expected exactly one archived scorer marker: " + marker)
    return json.loads(matches[0])


def check_slot(reader, row):
    folder = reader.path(row["episode_folder"])
    slot = reader.read(folder / "slot-result.json")
    assessment = reader.read(folder / "assessment.json")
    raw = reader.read(folder / "raw-independent-assessment.json")
    lock = reader.read(folder / "final-candidate-lock.json")
    state = reader.read(folder / "episode/end/control/state.json")
    deadline = reader.read(folder / "deadline-receipt.json")
    guard = reader.read(folder / "evaluation-guard.json")
    facts = state["projects"]["SOFTWARE27"]["software"]
    checks = {}

    def check(name, value):
        checks[name] = bool(value)

    check("slot_identity", row["slot_id"] == slot["slot_id"] == lock["slot_id"])
    check("report_original_file_shas", all(
        reader.ref(ref["path"])["sha256"] == ref["sha256"] for ref in row["references"].values()
    ))
    for key in ("R_joint", "R_token", "Q_joint", "Q_token", "submitted", "complete_delivery", "administrative_censoring"):
        check("report_slot_" + key, exact(row[key], slot[key]))
    check("assessment_embedded_identical", exact(slot["assessment"], assessment))
    check("raw_assessment_preserved", all(exact(assessment.get(k), v) for k, v in raw.items()))
    check("formal_R_from_assessment", slot["R_joint"] == assessment["R"])
    check("closed_known_not_censored", slot["status"] == "closed" and slot["R_joint"] in (0, 1)
          and not slot["administrative_censoring"] and not slot["process_violation"])
    check("unique_locked_close", deadline["final_submission_locked"] and deadline["unique_final_acceptance"]
          and deadline["final_assessment_calls"] == 1 and deadline["all_dispatched_attempts_settled"]
          and deadline["closed_before_hard_deadline"] and not deadline["hard_deadline_expired"])
    check("recorded_guards_passed", all(guard.get(k) is True for k in row["evaluation_guard"]))
    check("lock_matches_deadline", exact(lock["delivery"], deadline["locked_submission"]))
    check("new_dispatch_disabled_at_lock", lock["new_model_calls_allowed"] is False and lock["new_stages_allowed"] is False)
    case = facts["case"]
    asset_base = "examples/software-organization-v049" if row["root"] in ("DA", "DB") else "examples/software-learning-v050"
    asset = Path(asset_base) / slot["case_id"]
    contract_path = reader.path(asset / "contract.md")
    contract = contract_path.read_text()
    contract_ref = reader.ref(contract_path)
    fixture_path = asset / "acceptance.json"
    fixture = reader.read(fixture_path)
    public_fixture = reader.read(asset / "public-checks.json")
    source = assessment["source_contract"]
    check("source_contract_identical", exact(source, case["source_contract"]))
    check("public_contract_bound", contract == source["public_requirements"] and contract_ref["sha256"] == source["requirements_sha256"])
    check("fixture_bound", reader.ref(fixture_path)["sha256"] == source["independent_verifier_sha256"])
    check("public_checks_bound", reader.ref(asset / "public-checks.json")["sha256"] == source["public_checks_sha256"])
    outcomes = slot["boundary"]["outcomes"]
    attempts = [x for x in outcomes if x.get("decision", {}).get("action") == "submit_integration"]
    test_events = [e for e in state["software_events"] if e["kind"] == "test"]
    latest = {}
    for event in test_events:
        latest[event["actor_id"]] = {
            "sequence": event["sequence"], "passed": event["passed"],
            "source_reference": event["source_reference"], "files_sha256": event["files_sha256"],
            "failed_public_tests": [test["test_id"] for group in event["groups"].values()
                                    for test in group.get("tests", []) if not test["passed"]],
        }
    result = {k: row[k] for k in ("slot_id", "root", "branch", "sampling_seed", "R_joint", "Q_joint", "submitted")}
    result.update({
        "stored_score_only": True, "private_reexecution": False,
        "source_folder": str(folder.relative_to(reader.root)),
        "references": {name: reader.ref(folder / name) for name in (
            "slot-result.json", "assessment.json", "raw-independent-assessment.json", "final-candidate-lock.json",
            "episode/end/control/state.json", "deadline-receipt.json", "evaluation-guard.json")},
        "public_contract": contract_ref,
        "submit_integration_attempts": len(attempts),
        "historical_public_test_count": len(test_events),
        "latest_historical_test_by_member": latest,
        "role_stops": slot["boundary"]["role_stops"],
        "current_work_ended": slot["boundary"]["current_work_ended"],
        "new_evaluation_of_unsubmitted_code": None,
    })
    failure = None
    if not row["submitted"]:
        check("no_delivery_anywhere", lock["delivery"] is None and lock["absence_locked"] is True
              and not facts["deliveries"] and not raw["submitted"])
        check("no_private_assessment_on_workspace", "independent_acceptance" not in raw
              and raw["content_correct"] is None
              and raw["reason"] == "No fixed delivery; mutable workspaces are not independently assessed")
        check("no_submission_action", not attempts)
        check("no_delivery_scores_zero", slot["R_joint"] == 0 and slot["Q_joint"] == 0
              and row["private_checks_total"] == 0)
        check("both_members_team_budget_stop", slot["boundary"]["role_stops"]
              == {"member_001": "team_budget_exhausted", "member_002": "team_budget_exhausted"})
        result["classification"] = "workflow_no_fixed_delivery_budget_exhausted"
        result["code_correctness"] = "unknown_unsubmitted_workspace_not_assessed"
    else:
        delivery = lock["delivery"]
        check("last_legal_delivery_bound", exact(delivery, facts["deliveries"][-1])
              and exact(delivery, assessment["delivery"]) and not lock["absence_locked"])
        reference = delivery["source_reference"]
        artifact = state["artifacts"][reference["object_id"]]
        bundle_path = folder / "episode/end/control/versions" / reference["object_id"] / reference["version_id"] / artifact["filename"]
        bundle = reader.read(bundle_path)
        check("fixed_bundle_sha", reader.ref(bundle_path)["sha256"] == delivery["source_sha256"]
              == artifact["versions"][reference["version_id"]]["sha256"])
        check("fixed_files_sha", sha(json_bytes(bundle["files"])) == delivery["files_sha256"] == assessment["files_sha256"])
        check("fixed_contract_exact", bundle["files"]["contract.md"] == contract)
        test = next(e for e in test_events if e["sequence"] == delivery["test_sequence"])
        check("same_tree_test_before_submit", test["passed"] and test["executed"]
              and all(exact(test[k], delivery[k]) for k in ("actor_id", "source_reference", "source_sha256", "files_sha256")))
        result["fixed_delivery"] = delivery
        result["fixed_bundle"] = reader.ref(bundle_path)
        private = assessment["independent_acceptance"]
        public = assessment["public_acceptance"]
        prefix = "PROWORKSIM_V049" if row["root"] in ("DA", "DB") else "PROWORKSIM_V050"
        observed = decode_saved(private["execution"], prefix + "_OBSERVATIONS:")
        saved_public = decode_saved(public["execution"], prefix + "_PUBLIC:")
        check("scorers_completed", all(x["execution"]["executed"] and x["execution"]["driver_completed"]
              and x["execution"]["returncode"] == 0 and not x["execution"]["timeout"]
              and not x["execution"]["output_truncated"] for x in (private, public)))
        check("private_fixture_sha", private["fixture_sha256"] == reader.ref(fixture_path)["sha256"])
        check("private_counts", len(observed) == len(fixture["cases"]) == len(private["checks"]))
        recomputed = []
        for item, expected, output in zip(private["checks"], fixture["cases"], observed, strict=True):
            check("private_binding_" + item["case_id"], item["case_id"] == expected["case_id"]
                  and exact(item["expected"], expected["expected"]) and exact(item["observed"], output))
            passed = exact(comparable(output), expected["expected"])
            recomputed.append(passed)
            check("private_score_" + item["case_id"], passed is item["passed"])
        check("public_stdout_identical", exact(saved_public, public["tests"]))
        for item, expected in zip(saved_public, public_fixture["cases"], strict=True):
            check("public_binding_" + item["test_id"], item["test_id"] == expected["case_id"]
                  and exact(item["expected"], expected["expected"]))
            check("public_score_" + item["test_id"], exact(comparable(item["observed"]), expected["expected"]) is item["passed"])
        check("formal_score_recomputed", row["private_checks_passed"] == sum(recomputed)
              and row["private_checks_total"] == len(recomputed)
              and slot["Q_joint"] == sum(recomputed) / len(recomputed)
              and private["passed"] == all(recomputed)
              and public["passed"] == all(x["passed"] for x in saved_public)
              and row["R_joint"] == int(private["passed"] and public["passed"]))
        result["private_checks_passed"] = sum(recomputed)
        result["private_checks_total"] = len(recomputed)
        result["classification"] = "fixed_delivery_contract_success" if row["R_joint"] else "fixed_delivery_business_contract_failure"
        failed = [x for x in private["checks"] if not x["passed"]]
        result["failed_private_checks"] = failed
        if failed:
            spec = FAILURES[row["slot_id"]]
            check("known_four_failure_scope", len(failed) == 1 and failed[0]["case_id"] == spec["case_id"])
            check("failure_obligation_is_public", spec["obligation"] in contract)
            code = bundle["files"][spec["file"]]
            check("failure_fixed_code_fragment", spec["code_fragment"] in code)
            source_case = next(x for x in fixture["cases"] if x["case_id"] == spec["case_id"])
            failure = {"slot_id": row["slot_id"], **spec, "classification": "business_implementation_defect",
                       "contract_or_scoring_bug_evidence": False, "execution_technical_fault_evidence": False,
                       "request": source_case["request"], "expected": failed[0]["expected"], "observed": failed[0]["observed"],
                       "fixed_bundle": reader.ref(bundle_path), "production_source_sha256": sha(code.encode()),
                       "fixed_production_source": code, "public_contract": contract_ref,
                       "analysis_method": "Static reading of immutable delivered source, public contract, archived request and output; no candidate execution."}
    result["checks"] = checks
    result["passed"] = all(checks.values())
    return result, failure


def build(root):
    reader = Reader(root)
    final = reader.read(REPORT)
    selected = [row for row in final["rows"] if row["phase"] == "development"]
    if len(selected) != 32 or len({r["slot_id"] for r in selected}) != 32:
        raise ValueError("Expected all 32 unique development terminals")
    rows, failures = [], []
    for row in selected:
        result, failure = check_slot(reader, row)
        rows.append(result)
        if failure:
            failures.append(failure)
    counts = Counter(row["classification"] for row in rows)
    issues = [{"slot_id": row["slot_id"], "check": key} for row in rows for key, value in row["checks"].items() if not value]
    groups = {}
    for branch in BRANCHES:
        sample = [row for row in rows if row["branch"] == branch]
        groups[branch] = {"slots": len(sample), "successes": sum(x["R_joint"] for x in sample),
                          "submitted_partial": sum(x["submitted"] and not x["R_joint"] for x in sample),
                          "unsubmitted": sum(not x["submitted"] for x in sample),
                          "F": sum(x["R_joint"] for x in sample) / len(sample),
                          "mean_Q_task": sum(x["Q_joint"] for x in sample) / len(sample)}
    original_files_unchanged = all(reader.ref(path)["sha256"] == reference["sha256"]
                                   for path, reference in list(reader.sources.items()))
    if not original_files_unchanged:
        issues.append({"check": "source_changed_during_read_only_audit"})
    return {"version": VERSION, "source_v050_final": reader.ref(REPORT), "read_only": True,
            "new_model_calls": 0, "new_backward_calls": 0, "new_optimizer_steps": 0,
            "new_world_or_acceptance_executions": 0, "new_candidate_executions": 0,
            "old_R_Q_or_artifact_rewrites": 0, "original_files_unchanged": original_files_unchanged,
            "scope": "All 32 v050 development terminal artifacts. Archived scorer stdout decoded and compared with frozen fixtures; fixed submission, same-tree public test and score provenance checked. No private retest, no unsubmitted workspace assessment.",
            "passed": not issues, "issues": issues,
            "summary": {"slots": len(rows), "classification_counts": dict(counts),
                        "checks": sum(len(r["checks"]) for r in rows), "failed_checks": len(issues),
                        "submitted_trees_bound": sum(r["submitted"] for r in rows),
                        "original_private_checks_read": sum(r.get("private_checks_total", 0) for r in rows),
                        "contract_failure_count": len(failures),
                        "unsubmitted_no_submit_action": sum(not r["submitted"] and r["submit_integration_attempts"] == 0 for r in rows),
                        "unsubmitted_with_historical_public_tests": sum(not r["submitted"] and r["historical_public_test_count"] > 0 for r in rows)},
            "groups": groups, "rows": rows, "contract_failures": failures,
            "limitations": [
                "This is an independent read-only consistency and public-obligation audit, not an independent re-execution of the 22 submitted trees or reconstruction of model generation.",
                "Ten unsubmitted mutable workspaces remain unevaluated; R/Q=0 records the absence of fixed delivery and does not establish final source-code incorrectness.",
                "Nine of ten unsubmitted slots have failing last historical public tests; those tests may precede later edits. Q_minus DD-s2 has no member test. All ten made zero submit_integration attempts and stopped at the team budget.",
                "No scoring or fixed-delivery integration defect was observed within this audit. This does not prove every system or model capability issue absent.",
                "The four private failures instantiate obligations already in the public contract. Passing the finite public test set does not imply full-contract correctness.",
                "Older SQL, chat-stop and SDK interface calibrations are scoped evidence and do not establish completion of the proposed original-9B official-code and repository single-agent bridge.",
            ], "source_manifest": sorted(reader.sources.values(), key=lambda x: x["path"])}


def render(report):
    lines = ["# v051 CAL-0：v050 全32开发终态只读评分核对", "",
             "CAL-0已完成。全32槽原R/Q保持：18份固定提交完整成功，4份固定提交有公开合同实现缺陷，10槽未形成固定提交。未发现本范围内的评分转换或固定交付接入错误。", "",
             "这次只读取原件、复算已保存评分、静态阅读四份失败交付代码；模型调用、反向、optimizer、业务重执行与新增私验均为0。没有对10份未提交工作区追加验收或回填R。", "",
             f"{report['summary']['checks']}项只读一致性判断，失败{report['summary']['failed_checks']}项；22份最后合法固定树均与原锁、世界版本SHA、同树公共测试和最终评分绑定。读取原私验{report['summary']['original_private_checks_read']}个判定，原输出到期望比较的结果全部一致。读取前后所有纳入来源文件SHA一致。", "",
             "| 状态 | 完整成功 | 提交未全过 | 未提交 | F | 平均Q_task |", "|---|---:|---:|---:|---:|---:|"]
    for branch, group in report["groups"].items():
        lines.append(f"| {branch} | {group['successes']}/8 | {group['submitted_partial']} | {group['unsubmitted']} | {group['F']:.3f} | {group['mean_Q_task']:.6f} |")
    lines += ["", "## 四份提交失败：公开义务与原固定代码", ""]
    for failure in report["contract_failures"]:
        lines += [f"### {failure['slot_id']} / {failure['case_id']}", "", failure["finding_zh"], "",
                  "公开义务：" + failure["obligation"], "",
                  "原请求：`" + json.dumps(failure["request"], ensure_ascii=False) + "`。", "",
                  "期望：`" + json.dumps(failure["expected"], ensure_ascii=False) + "`。", "",
                  "原观察：`" + json.dumps(failure["observed"], ensure_ascii=False) + "`。", "",
                  "固定代码线索：`" + failure["code_fragment"] + "`。JSON保留完整固定生产文件和SHA。这些是业务实现偏差，未见私有新增义务、评分转换错误或执行器技术故障的证据。", ""]
    lines += ["## 全32终态分类", "", "| 槽 | R | Q_task | 分类 | submit尝试 | 历史公共测试 |", "|---|---:|---:|---|---:|---:|"]
    names = {"fixed_delivery_contract_success": "固定提交完整成功", "fixed_delivery_business_contract_failure": "固定提交合同失败", "workflow_no_fixed_delivery_budget_exhausted": "未提交／团队预算终止"}
    for row in report["rows"]:
        lines.append(f"| {row['slot_id']} | {row['R_joint']} | {row['Q_joint']:.6f} | {names[row['classification']]} | {row['submit_integration_attempts']} | {row['historical_public_test_count']} |")
    lines += ["", "10个未提交槽均从未发起submit_integration，两个成员均因团队预算用尽停止。9槽存在历史公共测试且各成员最后已运行测试均未通过；Q−/DD-s2没有成员测试。已有测试可能早于后续编辑，不能据此推断未提交最终代码必然失败。这里的R=0是固定交付缺失，不是新增代码正确率。", "",
              "## 复算范围与限制", "",
              "脚本仅使用stdlib，读取原固定评分器stdout、acceptance.json和public-checks.json，在不运行候选代码的条件下核对原始观察、类型严格的JSON比较、评分汇总及锁定版本。要求公开合同/私验fixture SHA与原slot source_contract相同，最后合法交付与deadline锁、世界deliveries末项一致，固定bundle与files SHA相同，提交引用的历史公共测试属于本人同树且通过。", "",
              "本结论不替代官方单人能力校准，也不是v050业务结果的独立重执行。历史v011 SQL、v0151聊天停止、v016 SDK接口校准只支持各自范围；尚未据本次有限检索取得与CAL-1/CAL-2等价的完成凭据，不能据此断言历史从未做过任何校准。", "",
              "复算：`.venv/bin/python scripts/software_calibration_v051_cal0.py --output artifacts/software-calibration-v051/cal0`。脚本默认不覆盖已存在且内容不同的报告；若要保存新读数，请使用新输出目录。原业务/训练产物只读。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("artifacts/software-calibration-v051/cal0"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    report = build(root)
    outputs = {output / "report.json": json_bytes(report), output / "report.md": render(report).encode()}
    for path, content in outputs.items():
        if path.exists() and path.read_bytes() != content:
            raise FileExistsError("Use a new output directory to preserve the previous analysis: " + str(path))
    output.mkdir(parents=True, exist_ok=True)
    for path, content in outputs.items():
        if not path.exists():
            path.write_bytes(content)
    print(json.dumps({"passed": report["passed"], "summary": report["summary"], "issues": report["issues"], "output": str(output)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
