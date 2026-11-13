"""Offline, receipt-bound public-test, admission and delivery audit of the old 12.

Only reads frozen files/SQLite and writes two new v203.2.2 audit artifacts. No
model, Docker, scorer, shell subprocess, experiment replay or host operation.
Classification is descriptive of contemporaneous evidence, not causal scoring.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "artifacts/software-benchmark-v203-2-1/final-report-r1"
OUT = ROOT / "artifacts/software-benchmark-v203-2-2/natural-audit-r1"
EDIT_TOOLS = {"write_file", "replace_file", "delete_file", "integrate_patch", "apply_patch"}
KEEP_RESULTS = {"source_reference", "files_sha256", "patch_id", "delivery_id", "review_id",
                "decision", "passed", "executed", "report_id", "validation_status", "counts",
                "conflict_count", "paths", "changed_paths", "status", "reason", "identity",
                "adopted_source_reference", "test_evidence"}


def read(path):
    return json.loads(Path(path).read_bytes())


def ref(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def measurement_path(index):
    if index in (2032200, 2032201):
        return ROOT / f"artifacts/software-benchmark-v203-2-1/capture-recovery-r4/{index}-measurement.json"
    return ROOT / f"runs/software-benchmark-v203-2-1/passive-pilot10-r4/api-coordinator/measurement-records/{index}.json"


def journal_rows(path):
    # Decode only actual tool receipts and scheduler boundaries, not large model
    # payloads or duplicated intent/opportunity responses. Full journal integrity
    # is already checked in the original COMPLETE measurements.
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        sql = "SELECT * FROM observations WHERE event_key GLOB 'receipt:*' OR event_key GLOB 'opportunity:*' OR event_key='boundary' ORDER BY sequence"
        result = []
        for row in db.execute(sql):
            raw = row["record_json"]
            if hashlib.sha256(raw.encode()).hexdigest() != row["record_sha256"]:
                raise ValueError("Selected original receipt digest mismatch")
            item = json.loads(raw)
            item["sequence"] = row["sequence"]
            item["evidence"] = {"path": str(path), "observer_sequence": row["sequence"],
                                "event_key": row["event_key"], "record_sha256": row["record_sha256"]}
            result.append(item)
        return result


def event(row):
    p = row["payload"]
    response = p.get("response", {})
    result = response.get("result") or {}
    association = p.get("association") or {}
    args = p.get("arguments", {})
    # Retain notes/messages verbatim as evidence of stated decisions; for edits
    # retain path + changed-text digests, rather than copying full source files.
    if p.get("tool") in EDIT_TOOLS:
        args = {k: v for k, v in args.items() if k not in {"text", "old", "new"}}
        for key in ("text", "old", "new"):
            text = p.get("arguments", {}).get(key)
            if isinstance(text, str):
                args[key + "_sha256"] = hashlib.sha256(text.encode()).hexdigest()
                args[key + "_characters"] = len(text)
                args[key + "_preview"] = text[:160]
    retained = {k: v for k, v in result.items() if k in KEEP_RESULTS and k != "test_evidence"}
    if "test_evidence" in result:
        e = result["test_evidence"] or {}
        retained["test_evidence"] = {k: e.get(k) for k in ("report_id", "passed", "source_reference", "evidence_sha256", "error") if k in e}
    return {"evidence": row["evidence"], "capture_time": row["source"]["capture_time"],
            "actor": p.get("actor", p.get("worker_id")), "tool": p.get("tool"),
            "decision_id": association.get("decision_id"), "decision_index": association.get("decision_index"),
            "arguments": args, "ok": response.get("ok"), "result": retained,
            "error": response.get("error"), "scheduler_status": p.get("status"),
            "scheduler_reason": p.get("reason"), "action_performed": p.get("action_performed")}


def classify(index, call, response):
    """Explicit panel-specific reading rules, always backed by original log text.

    One report gets one primary category; secondary causes are non-additive.
    No final score is an input to this function.
    """
    out = response.get("groups", {}).get("public_repository_tests", {}).get("output", "")
    status = response.get("validation_status")
    category, subtype, reason = "unknown", "undetermined", "回执失败，但现有输出不足以确定原因。"
    secondary, caveats = [], []
    if index == 2032402:
        marker = "pytest.PytestAssertRewriteWarning: Module already imported so cannot be rewritten: pws_public_test_evidence_v141"
        assert marker in out and response["execution"]["returncode"] == 1
        category, subtype = "dependency_environment", "harness_plugin_bootstrap_warning_as_error"
        reason = "sitecustomize 已预载取证插件，pytest 再注册该插件时发出重写警告；仓库 warnings=error 将警告转为启动异常，尚未开始测试会话。"
        caveats.append("executed=True 是测试命令实际启动；框架断言未执行，不能说这17次证明补丁有缺陷。")
    elif status == "no_tests":
        category, subtype = "selector_error", "zero_collected_tests"
        reason = "测试命令实际运行，但此选择未收集到测试，exitstatus=5；不是有效验证。"
    elif index == 2032405 and call == 4:
        assert "401 passed" in out and response["execution"]["returncode"] == 0
        category, subtype = "unknown", "incomplete_framework_session_evidence"
        reason = "命令exit=0且stdout为401 passed/25 skipped/3 xfailed；618条框架记录未组成完整开始/结束会话，原回执因此为unknown_collection、passed=False。"
        caveats.append("没有保存原始618条counts.jsonl，不能确定缺少的是哪个run_id或根/子会话；不把stdout替换为正式通过。")
    elif index == 2032405 and "No module named 'hypothesis'" in out:
        category, subtype = "dependency_environment", "missing_dependency"
        reason = "收集testing/python/metafunc.py时缺少hypothesis；未执行根会话测试。"
    elif index == 2032403 and "Pandas requires version" in out:
        category, subtype = "dependency_environment", "pandas_xarray_version_incompatibility"
        reason = "4个categorical相关测试触发pandas对xarray>=0.19.0的依赖检查；当前版本0.16.1.dev50，属于兼容性错误。"
    elif index == 2032407 and "Temporary failure in name resolution" in out:
        category, subtype = "dependency_environment", "network_dns_unavailable"
        reason = "测试访问网络时DNS解析失败；部分日志还包含Network is unreachable。"
        if "must be callable" in out:
            secondary.append("selector_error")
            reason += "同一执行另有test_conflicting_post_params把字符串传给assertRaises引发TypeError，不得把此执行拆计两次。"
            caveats.append("TypeError来自旧测试调用约定；日志证明错误位置，不足以建立完整依赖版本归因。")
    elif (index == 2032201 and call in (2, 7)) or (index == 2032411 and call == 4):
        category, subtype = "selector_error", "nonexistent_django_test_target"
        reason = "选中的Django测试类或模块不存在，unittest.loader._FailedTest报AttributeError/ModuleNotFoundError；同次其它测试的通过不消除此错误。"
    elif "AssertionError" in out or "re.error: bad escape" in out:
        category = "code_assertion"
        subtype = "runtime_regex_error" if "re.error: bad escape" in out else "assertion_mismatch"
        reason = {
            2032201: "全套执行stdout报告4个断言失败：inspectdb自定义字段和3个时区序列化用例；框架计数缺失，保留日志事实，不断言是本题补丁造成。",
            2032404: "toctree entries与回归测试预期不一致。",
            2032407: "新增bytes_method_name回归在v5失败：PreparedRequest.method仍为bytes b'GET'，预期文本GET；随后v6改models.py并通过同选择。",
            2032408: "断言显示PYLINT_HOME新路径与旧期望不一致，或recursion_error_3152产生额外abstract-method诊断；逐条日志确定哪项实际发生。",
            2032410: "7个日期格式化usetex用例在re替换模板处触发bad escape \\m；这是代码运行错误，不是缺失TeX程序的证据。",
            2032411: "test_empty_string_dir_ignored断言目录集合不符，直接涉及本题空字符串目录行为。",
        }.get(index, "测试中出现断言不匹配或代码运行错误。")
        if index == 2032404 and call == 5:
            subtype = "deliberate_negative_control_assertion"
            reason += "此为reviewer在seq262临时禁用关系页面分支后的负对照(v4)，seq282恢复；不是对候选原样的失败验证。"
        if index == 2032404 and call == 6:
            caveats.append("发生于冲突修复后的reviewer v8；回执仅证明该版本失败，不能直接采信review理由中的与author patch-2完全相同声明。")
    lines = out.splitlines()
    selected = []
    pattern = re.compile(r"(AssertionError|ImportError:|ModuleNotFoundError:|AttributeError:|TypeError:|re\.error:|^pytest\.PytestAssertRewriteWarning:|^FAIL:|^ERROR:|^E\s+(?:socket|requests)|^FAILED |^=+.*(?:passed|failed|error|warning)|^Ran )")
    seen = set()
    for line_no, line in enumerate(lines, 1):
        if pattern.search(line) and line not in seen:
            seen.add(line)
            selected.append({"stdout_line": line_no, "text": line[:1400], "line_truncated": len(line) > 1400})
    return {"primary_category": category, "subtype": subtype,
            "categories_nonadditive": [category, *secondary], "reason_zh": reason,
            "confidence": "high" if category != "unknown" else "limited_to_verification_status",
            "caveats_zh": caveats, "log_excerpts": selected[:26],
            "excerpt_selection_truncated": len(selected) > 26,
            "stdout_sha256": response["execution"].get("stdout_sha256"),
            "final_score_used_for_classification": False}


DELIVERY_NOTES = {
    2032200: "未发布fix_patch、未复核、未提交。reviewer seq303明确等待作者候选；作者随后继续读源码，末次行动seq446，seq448拒绝下一次生成。预算停止了继续探索，但已有材料不能证明增加预算能修复问题。",
    2032402: "作者patch-1 v4已发布并交接，reviewer已采用；17次测试入口启动失败，reviewer seq346/423明确记录BLOCKED并不愿伪造accept，也不愿把环境问题称为request_changes。作者处于等待复核，reviewer下一请求被预算拒绝。无submit_integration尝试；环境阻塞早于预算门。",
    2032408: "作者在反复测试/修改后到seq415才发布patch-1 v8；reviewer seq420采用，seq425交接后双方下一次生成都被预算拒绝。没有reviewer测试或复核决定，没有submit_integration；支持交付窗口在剩余预算不足时才进入，不能据此归因所有代码失败。",
    2032410: "作者seq287将dates.py写成PLACEHOLDER，seq334记录恢复计划；seq421只写回部分内容，seq428明确FAILED TO DELIVER，seq438要求reviewer不要接受候选。没有fix_patch或提交；这项显式破坏和放弃发生在seq440/441预算门之前。",
    2032201: "最后合法提交delivery-2是author v3(seq253)，之后reviewer发布仅新增回归测试的patch-3；author seq382采用成v4，出现一次错误测试类选择、一次聚焦通过和一次全套失败后预算门关闭。未重新发布/复核/提交v4，所以提交仍为仅生产文件的v3，终态另含tests/admin_inlines/tests.py。",
    2032404: "最后合法提交delivery-1是author v3(seq151)。随后增加warning回归得到v5/patch-2；reviewer冲突修复后测试失败并request_changes(seq372)。author修改回归为v6/patch-3并通过，reviewer采用v9且seq436测试通过，但seq438/439预算门发生，未记录patch-3接受和再次提交。最终版本差异来自提交后的测试增强/返修，不等于从未合法提交。",
    2032407: "合法提交delivery-1是author v2(seq248，仅sessions.py)。随后作者新增bytes回归，在v5失败，seq404修改models.py成v6，seq409回归通过，seq419发布patch-2。双方下一次生成seq421/422被拒绝，未完成新候选交接/复核/提交，故终态v6含models.py、sessions.py、test_requests.py而交付仍为v2。",
}


def read_original_usage(path, slots):
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        result = {}
        for slot in slots:
            rows = []
            for row in db.execute("SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,request_id", (slot,)):
                item = dict(row)
                item["usage"] = json.loads(item.pop("usage_json")) if item.get("usage_json") else None
                item.pop("evidence_json", None)
                rows.append(item)
            result[slot] = rows
        return result


def analyze_task(old, usage):
    idx = old["physical_index"]
    mpath = measurement_path(idx)
    measurement = read(mpath)
    journal = measurement["sidecar_journal"]["path"]
    rows = journal_rows(journal)
    receipts = [r for r in rows if r["kind"] == "RECEIPT"]
    boundary = read(old["boundary"]["path"])
    basedir = Path(old["boundary"]["path"]).parent
    all_test_receipts = [r for r in receipts if r["payload"]["tool"] == "run_tests"]
    tests, invalid, actual_ordinal = [], [], 0
    for request_ordinal, row in enumerate(all_test_receipts, 1):
        p = row["payload"]
        result = p["response"].get("result") or {}
        item = event(row)
        item["test_request_ordinal"] = request_ordinal
        if result.get("executed") is not True:
            item["classification"] = "invalid_selection_not_executed"
            item["denominator"] = "four_unexecuted_requests_excluded_from_86_actual_and_43_failed"
            invalid.append(item)
            continue
        actual_ordinal += 1
        rpc = basedir / f"public-test-rpc/test-{actual_ordinal:04d}"
        req, response = read(rpc / "request.json"), read(rpc / "response.json")
        # This join checks actor, exact source, selection, immutable session digest
        # and verdict; test-number ordering alone is never accepted as identity.
        assert req["actor_id"] == p["actor"]
        assert req["source_reference"] == result["source_reference"]
        selected = dict(p["arguments"].get("selection", {"kind": "full"}))
        if selected.get("kind") != "full":
            selected.setdefault("targets", [])
        assert req["public_test_selection"] == selected
        assert response["test_evidence"]["evidence_sha256"] == result["test_evidence"]["evidence_sha256"]
        assert response["passed"] == result["passed"]
        item.update(actual_test_ordinal=actual_ordinal, report_id=result["report_id"],
                    source_reference=result["source_reference"],
                    rpc_request=ref(rpc / "request.json"), rpc_response=ref(rpc / "response.json"),
                    execution={k: v for k, v in response["execution"].items() if k in
                               {"returncode", "timed_out", "wall_seconds", "argv", "command_executed", "input_tree_sha256", "stdout_sha256", "stdout_bytes"}},
                    framework_evidence={k: response["test_evidence"].get(k) for k in
                                        ("framework", "error", "report_count", "journal_record_count", "nested_report_count", "evidence_sha256")})
        if result["passed"] is False:
            item["classification"] = classify(idx, actual_ordinal, response)
            later = [r for r in receipts if r["sequence"] > row["sequence"] and r["payload"]["actor"] == p["actor"]]
            edit = next((r for r in later if r["payload"]["tool"] in EDIT_TOOLS and r["payload"]["response"].get("ok")), None)
            next_test = next((r for r in later if r["payload"]["tool"] == "run_tests" and (r["payload"]["response"].get("result") or {}).get("executed")), None)
            item["followup_same_actor"] = {"first_edit": event(edit) if edit else None,
                                            "next_actual_test": event(next_test) if next_test else None,
                                            "is_temporal_link_not_proof_of_causation": True}
        tests.append(item)
    assert len({t["report_id"] for t in tests}) == len(tests)
    requests = {r["request_id"]: r for r in measurement["accepted_requests"]}
    timeline, settled_total = [], 0
    budget_records = boundary["team_budget"]["model"]["records"]
    for physical in usage:
        accepted = requests.get(physical["logical_id"])
        assert accepted is not None and physical["status"] == "settled"
        assert physical["usage"]["total_tokens"] == accepted["usage"]["total_tokens"]
        settled_total += physical["usage"]["total_tokens"]
        decision = accepted["decision_id"]
        record = budget_records.get(decision, {})
        matched = [event(r) for r in receipts if r["payload"].get("association", {}).get("decision_id") == decision] if decision else []
        timeline.append({"physical_request_id": physical["request_id"], "logical_request_id": physical["logical_id"],
                         "actor": physical["member_id"], "purpose": physical["usage_id"],
                         "reserved_utc": physical["reserved_utc"], "finished_utc": physical["finished_utc"],
                         "decision_id": decision, "usage": physical["usage"],
                         "cumulative_actual_tokens_in_reservation_order": settled_total,
                         "remaining_tokens_after_this_record": 5000000 - settled_total,
                         "physical_ledger_reservation_tokens": physical["reserved_tokens"],
                         "physical_ledger_input_upper_bound": physical["prompt_upper_bound"],
                         "physical_ledger_output_cap": physical["max_output_tokens"],
                         "managed_reservation": {k: record.get("reservation", {}).get(k) for k in
                                                  ("input_token_reservation", "output_token_reservation", "token_reservation")},
                         "actions": [{"evidence": e["evidence"], "tool": e["tool"], "result": e["result"]} for e in matched]})
    assert settled_total == old["tokens_charged"] == boundary["team_budget"]["model"]["charged_tokens"]
    gates = [r for r in rows if r["kind"] == "OPPORTUNITY" and r["payload"].get("status") == "team_budget_exhausted"]
    rejected = [(key, r) for key, r in budget_records.items() if r.get("status") == "admission_rejected"]
    assert len(gates) == len(rejected)
    gate_details = []
    for gate in gates:
        actor = gate["payload"]["worker_id"]
        candidates = [(key, r) for key, r in rejected if r["member"] == actor]
        assert len(candidates) == 1
        decision, rec = candidates[0]
        reservation = rec["rejected_reservation"]
        prep = reservation["preparation"]
        adjust = prep["output_budget_adjustment"]
        prior = [event(r) for r in receipts if r["sequence"] < gate["sequence"]]
        after = [event(r) for r in receipts if r["sequence"] > gate["sequence"]]
        charged_by_time = sum(x["usage"]["total_tokens"] for x in usage if
                              datetime.fromisoformat(x["finished_utc"]).timestamp() <= gate["source"]["capture_time"])
        gate_details.append({"gate": event(gate), "rejected_decision_id": decision,
                             "reservation": reservation, "attempt_started": rec["attempt_started"],
                             "limits": rec["admission_limits"],
                             "tokens_settled_by_gate_capture_time": charged_by_time,
                             "team_available_at_preparation": adjust["team_available_tokens"],
                             "required_next_request_tokens": reservation["token_reservation"],
                             "reservation_shortfall": reservation["token_reservation"] - adjust["team_available_tokens"],
                             "no_positive_output_room": adjust.get("no_positive_output_room"),
                             "last_ten_actions_before_gate": prior[-10:], "actions_after_gate": after,
                             "last_actor_action_before_gate": next((e for e in reversed(prior) if e["actor"] == actor), None),
                             "post_gate_generated_decision_exists": any(datetime.fromisoformat(x["reserved_utc"]).timestamp() > gate["source"]["capture_time"] for x in usage)})
    submissions = [event(r) for r in receipts if r["payload"]["tool"] == "submit_integration"]
    successes = [e for e in submissions if e["ok"] and e["result"].get("delivery_id")]
    last_submission = successes[-1] if successes else None
    after_submission = [event(r) for r in receipts if last_submission and r["sequence"] > last_submission["evidence"]["observer_sequence"]
                        and r["payload"]["tool"] in EDIT_TOOLS | {"fix_patch", "handoff_patch", "run_tests", "org_review_patch", "submit_integration"}]
    delivery = {"submission_attempts": submissions, "successful_submission_receipts": len(successes),
                "last_successful_submission": last_submission, "tree_detail": old["tree_detail"],
                "post_last_submission_version_review_test_events": after_submission,
                "contemporaneous_explanation_zh": DELIVERY_NOTES.get(idx, "最后合法提交与终态工作树一致；本项无未提交或版本漂移。"),
                "interpretation_is_not_counterfactual_causation": True}
    non_action_decisions = [event(r) for r in rows if r["kind"] == "OPPORTUNITY"
                           and r["payload"].get("action_performed") is False]
    # Outcomes are quarantined from failure classification and admission evidence.
    outcome = {k: old[k] for k in ("code_resolved", "protocol_submitted", "official_delivery_resolved", "delivery_status")}
    result = {"instance_id": old["instance_id"], "episode_id": old["slot_id"], "physical_index": idx,
              "measurement": ref(mpath), "original_boundary": old["boundary"],
              "source_journal": journal, "original_complete_integrity_reused": measurement["integrity"]["status"],
              "public_test_requests": len(all_test_receipts), "actual_public_tests": len(tests),
              "passed_actual_tests": sum(t["result"]["passed"] is True for t in tests),
              "failed_actual_tests": sum(t["result"]["passed"] is False for t in tests),
              "invalid_unexecuted_requests": invalid, "public_tests": tests,
              "token_timeline": timeline, "budget_gates": gate_details,
              "non_action_decisions": non_action_decisions,
              "terminal_budget": {k: v for k, v in boundary["team_budget"]["model"].items() if k != "records"},
              "stop_state": {k: boundary.get(k) for k in ("closure_reason", "role_stops", "terminal_details", "waiting_members", "current_work_ended", "work_boundaries", "cash_censored", "deadline_receipt")},
              "accepted_finish_by_member": old["accepted_finish_by_member"],
              "delivery": delivery, "retrospective_outcomes_not_used_for_labels": outcome}
    chain = None
    if gates:
        chain = {"schema": "v203.2.2-natural-budget-chain-r1", "chain_type": "D", "chain_kind": "budget_decision_termination",
                 "chain_id": f"D-{idx}", "instance_id": old["instance_id"], "episode_id": old["slot_id"],
                 "gates": gate_details, "last_ten_token_records": timeline[-10:],
                 "full_token_timeline_reference": {"path": str(OUT / "test-budget-audit.json"), "pointer": f"tasks[physical_index={idx}].token_timeline"},
                 "final_budget": result["terminal_budget"], "stop_state": result["stop_state"],
                 "non_action_decisions": non_action_decisions,
                 "delivery_state": delivery, "retrospective_outcomes_not_for_blinded_review": outcome,
                 "causal_claim": "No counterfactual budget effect estimated; code, environment, workflow and resource mechanisms may coexist."}
    return result, chain


def harness_findings(tasks):
    frozen = ROOT / "artifacts/software-benchmark-v203-2-1/continuation-r4/source-snapshot/tools"
    astropy = next(t for t in tasks if t["physical_index"] == 2032402)
    initial = Path(astropy["original_boundary"]["path"]).parent / "source-snapshot/initial-tree.json"
    # Read this single ~50MB source map once; do not unpack archives or scan all
    # historical snapshots. The exact original warnings rule settles the cause.
    setup = read(initial)["files"]["setup.cfg"]
    lines = setup.splitlines()
    pos = next(i for i, line in enumerate(lines) if line.startswith("filterwarnings"))
    assert lines[pos + 1].strip() == "error"
    return {"astropy_plugin_bootstrap": {
        "actual_test_reports": len(astropy["public_tests"]),
        "distinct_stdout_sha256": sorted({t["execution"]["stdout_sha256"] for t in astropy["public_tests"]}),
        "execution_source": ref(frozen / "public_test_execution_v141.py"),
        "source_locations": {"unconditional_sitecustomize_import_line": 48, "second_pytest_plugin_registration_line": 229},
        "original_repository_rule": {"path": str(initial), "json_key": "files.setup.cfg", "line": pos + 1,
                                     "excerpt": "\n".join(lines[pos:pos + 3]), "setup_cfg_sha256": hashlib.sha256(setup.encode()).hexdigest()},
        "mechanism_zh": "启动预载与pytest插件注册叠加；Astropy将警告视为错误，故测试取证插件本身在框架启动前终止命令。17次失败不能解释为17次待修代码失败。",
        "minimal_new_revision_fix_zh": "在新revision的sitecustomize仅为非pytest frontend预载observer；pytest通过单一PYTEST_PLUGINS入口导入。保留仓库warnings=error，不广泛屏蔽警告，不修改冻结旧源。",
        "existing_implementation_lead": {"path": str(ROOT / "tools/public_test_execution_v175.py"), "line": 49,
                                         "note": "现有v175已采用此条件预载；这只是代码先例，本审计没有执行它或证明全部兼容性。"},
        "offline_cpu_reproduction_recipe_zh": "独立临时目录内创建一条assert True测试和pytest.ini(filterwarnings=error)，用现有可用pytest解释器分别调用冻结v141与新revision执行入口；核对旧版bootstrap warning、新版完整root start/finish及1 pass。无Docker/API/评分，且不对原任务重新测试。",
        "admission_gate_zh": "后续实验应在实际frontend/解释器及warnings=error策略下先验证观察插件可启动、完整根会话可闭合；阳性/阴性/零测试及嵌套会话都要保留。修复后必须新revision，不与旧12题合并成绩。"},
        "pytest_401_stdout_passes": {"instance_id": "pytest-dev__pytest-5262", "actual_test_ordinal": 4,
            "parser_source": ref(frozen / "public_test_execution_v141.py"),
            "parser_lines": {"start_finish_set_equality_guard": 96, "unknown_collection_on_zero_exit": 161},
            "known_zh": "原回执journal_record_count=618、error=missing framework start or complete finish report、returncode=0、validation_status=unknown_collection。_session_tree在start/finish集合不完整时抛错，parse_test_evidence不从stdout升级为通过。",
            "unknown_zh": "原始counts.jsonl位于执行器临时目录并在退出时删除；本审计现存RPC记录只保留摘要/hash，没有逐行journal，不能判定具体缺失的会话、hook或嵌套测试。不得把缺失会话根因写成已证实。"},
        "scientific_limit_zh": "观测工程COMPLETE只证明模型/工具记录闭合，不保证测试测量无扰动。Astropy存在取证插件对被观测执行的干预；pytest存在测量不完整。当前12题不能据此归因组织效果或预算因果；历史成绩保持原状。"}


def main():
    audit = read(OLD / "execution-audit.json")
    snapshot = read(OLD / "provider-usage-snapshot.json")
    original_usage = read_original_usage(snapshot["source_ledger"], [r["slot_id"] for r in audit["rows"]])
    # One necessary ledger reconciliation, no repeated full-history validations.
    saved = {r["request_id"]: r for r in snapshot["requests"]}
    for values in original_usage.values():
        for r in values:
            assert r["request_id"] in saved and r["usage"] == saved[r["request_id"]]["usage"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pairs = list(pool.map(lambda row: analyze_task(row, original_usage[row["slot_id"]]), audit["rows"]))
    tasks = [p[0] for p in pairs]
    chains = [p[1] for p in pairs if p[1]]
    failed = [test for task in tasks for test in task["public_tests"] if test["result"]["passed"] is False]
    counts = Counter(test["classification"]["primary_category"] for test in failed)
    totals = {"tasks": len(tasks), "test_requests": sum(t["public_test_requests"] for t in tasks),
              "actual_executions": sum(t["actual_public_tests"] for t in tasks), "actual_failed": len(failed),
              "actual_passed": sum(t["passed_actual_tests"] for t in tasks),
              "invalid_not_executed": sum(len(t["invalid_unexecuted_requests"]) for t in tasks),
              "budget_gate_tasks": len(chains), "budget_rejected_requests": sum(len(t["budget_gates"]) for t in tasks),
              "no_submission_tasks": sum(not t["delivery"]["last_successful_submission"] for t in tasks),
              "successful_submission_receipts": sum(t["delivery"]["successful_submission_receipts"] for t in tasks),
              "different_delivery_terminal_tree_tasks": sum(bool(t["delivery"]["tree_detail"]) and not t["delivery"]["tree_detail"]["same_tree"] for t in tasks),
              "original_physical_requests": sum(len(x) for x in original_usage.values()),
              "actual_total_tokens": sum(t["terminal_budget"]["charged_tokens"] for t in tasks),
              "failed_execution_primary_categories_mutually_exclusive": dict(counts),
              "failed_execution_primary_subtypes": dict(Counter(t["classification"]["subtype"] for t in failed))}
    assert (totals["tasks"], totals["test_requests"], totals["actual_executions"], totals["actual_failed"], totals["invalid_not_executed"], totals["budget_gate_tasks"], totals["no_submission_tasks"], totals["different_delivery_terminal_tree_tasks"]) == (12, 90, 86, 43, 4, 7, 4, 3)
    assert totals["original_physical_requests"] == 915 and totals["actual_total_tokens"] == 49381273
    report = {"schema": "v203.2.2-natural-test-budget-audit-r1", "new_model_calls": 0,
              "new_public_test_or_scoring_calls": 0, "old_data_modified": False,
              "scope": "Exactly the existing twelve episodes; original SQLite receipts, request accounts and public-test RPC logs.",
              "counting_rules": {"unit": "one actual run_tests report/execution, not each failing test case or each diagnostic cause",
                                 "primary_categories": "mutually exclusive; secondary categories non-additive",
                                 "executed_meaning": "command actually ran; does not imply test collection or assertions ran",
                                 "historical_verdicts_preserved": True,
                                 "outcomes_do_not_label_prior_mechanisms": True,
                                 "budget_timeline": "Provider timestamps + original request reservation/settlement, joined to decision and receipt; cumulative values in reservation order are not an assertion about concurrent holds."},
              "sources": {"execution_audit": ref(OLD / "execution-audit.json"),
                          "provider_snapshot": ref(OLD / "provider-usage-snapshot.json"),
                          "original_provider_sqlite": {"path": snapshot["source_ledger"], "table": "requests", "access": "mode=ro; PRAGMA query_only=ON", "rows_selected": 915},
                          "summary": ref(OLD / "summary.json"),
                          "analysis_script": ref(Path(__file__))},
              "totals": totals, "harness_findings": harness_findings(tasks), "tasks": tasks,
              "limitations_zh": ["分类为描述性单次离线审计，不是两名盲法独立审阅或因果实验。",
                                   "同一任务可含多种失败原因；不能将43次失败或其原因标签当作43个独立任务。",
                                   "预算门证明下一次请求不能准入，不能证明若增加预算会通过；已有提交也可能先于预算门。",
                                   "当时Agent对原因/版本的文字声明与实际回执分别保留，文字不自动成为事实。",
                                   "stdout仅解释诊断，原框架verdict与计数保持不变；缺失原始session journal的细节显式未知。"]}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, value in (("test-budget-audit.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                        ("budget-chains.jsonl", "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chains))):
        target = OUT / name
        if target.exists():
            raise FileExistsError(f"Preserve existing audit output: {target}")
        target.write_text(value)
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
