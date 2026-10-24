"""Read-only case review of naturally finished but officially unresolved REF runs.

Select the highest-budget such run for every affected task before reviewing its
public trajectory and official failure log. No gold/reference repair is read.
"""
from __future__ import annotations

import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from proworksim.software_benchmark_native_artifact_v054 import decode_native_entry

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runs/software-benchmark-v056/score-encoding-repair-r1/analysis-r2"
OUT = ROOT / "artifacts/software-benchmark-v056/failure-analysis-r1/finished-wrong-cases.json"

# Qualitative notes are tied to the mechanically selected cases, not offered as
# an exhaustive or mutually exclusive causal partition of all model failures.
NOTES = {
    "mwaskom__seaborn-3069": {
        "kind": "semantic_behavior_not_restored", "rpc_ids": [338, 344], "log_lines": [414, 441],
        "observation": "候选修改plot.py和_oldcore.py，finish称已实现三个categorical行为；官方x/y轴边界仍不等于(-0.5, 2.5)/(2.5, -0.5)。",
        "interpretation": "有代码修改和公开自测，但对刻度范围/实际渲染效果的验证不足。不能把此例解释为没时间动手。",
    },
    "psf__requests-2931": {
        "kind": "network_or_fixture_confounded", "rpc_ids": [67, 71], "log_lines": [2540, 2550],
        "observation": "官方test_binary_put目标已通过，未通过端点仅两个连接timeout保持测试；完整日志另含大量fixture错误。",
        "interpretation": "不能仅由resolved=false断定二进制payload修复错误或代码引入回归；需要独立环境控制，保持原分数。",
    },
    "sympy__sympy-15017": {
        "kind": "incomplete_internal_invariant", "rpc_ids": [20, 53], "log_lines": [369, 377],
        "observation": "补丁为rank-0 __len__返回1并调整迭代；官方rank_zero_array[0]仍触发index out of range。模型选择的pytest入口不可用，登记和官方入口均为bin/test；后续主要直接python检查。",
        "interpretation": "长度、迭代与索引内部约束没有一起修复；单个示例输出正确不足以覆盖数据结构契约。",
    },
    "django__django-13807": {
        "kind": "incomplete_identifier_coverage", "rpc_ids": [125, 137], "log_lines": [434, 462],
        "observation": "候选给table_name加quote_name，官方check_constraints(['order'])仍在SELECT路径near select产生SQL语法错误。公开测试有入口/设置错误。",
        "interpretation": "标识符处理覆盖不完整；自写保留字表名检查不足以证明约束检查整条SQL路径正确。",
    },
    "psf__requests-1921": {
        "kind": "network_or_fixture_confounded", "rpc_ids": [45, 47], "log_lines": [23595, 23629],
        "observation": "修改merge_setting处理None；官方有部分目标通过，同时大量目标和保持测试记录网络相关失败。",
        "interpretation": "这是混合且受环境干扰的端点；不把全部失败列表算成模型造成的逻辑回归。",
    },
    "matplotlib__matplotlib-22865": {
        "kind": "edge_case_and_regression", "rpc_ids": [100], "log_lines": [452, 504],
        "observation": "公开colorbar测试56 passed，候选以np.arange(len(C))选择divider段；官方extend=both/max/neither有错误分隔线坐标，包含保持测试失败。",
        "interpretation": "局部几何索引修改未覆盖多个extend模式，公开旧测试通过不能排除新增边界与回归。",
    },
    "django__django-13158": {
        "kind": "shared_query_state_regression_hypothesis", "rpc_ids": [107, 108], "log_lines": [37895, 37905],
        "observation": "候选在set_empty中直接递归修改combined_queries；官方组合查询本应保留[0,1,8,9]却为空。公开174/680项测试有OK反馈。",
        "interpretation": "与共享子查询对象被递归置空的机制一致，但未运行独立消融证明具体别名传播链。不是简单的没跑测试。",
    },
    "django__django-15957": {
        "kind": "requirement_semantics_misapplied", "rpc_ids": [49, 98], "log_lines": [723, 742],
        "observation": "需求为每个父对象取若干相关对象，候选却在分组前对all_related_objects整体切片；公开116项测试OK，官方逐父对象结果不符。",
        "interpretation": "去掉不能filter sliced query的报错后，仍未保住每父对象的切片语义。说明修复目标理解比继续增加token更关键。",
    },
    "psf__requests-1766": {
        "kind": "network_or_fixture_confounded", "rpc_ids": [7, 8], "log_lines": [21455, 21475],
        "observation": "候选仅把Digest qop=auth改成带引号形式；官方大量HTTP端点测试失败，目标与保持测试同时受影响。",
        "interpretation": "不得在没有环境对照时把网络/服务端连通失败归为引用格式修复的结果。",
    },
    "psf__requests-5414": {
        "kind": "network_or_fixture_confounded", "rpc_ids": [67, 68], "log_lines": [5180, 5189],
        "observation": "官方InvalidURL目标通过，失败保持测试为四个连接timeout情形；公开URL类测试也有通过证据。",
        "interpretation": "候选针对问题的修复与全任务resolved不同；timeout结果需要环境归因，不先判模型能力不足。",
    },
    "pytest-dev__pytest-7432": {
        "kind": "fix_one_behavior_break_another", "rpc_ids": [73, 74, 75], "log_lines": [3590, 3625],
        "observation": "skip定位目标通过，但--runxfail情况下本应failed的xfail用例仍被标xfailed；模型移动了makereport中的runxfail分支。",
        "interpretation": "修复skip位置改变了已有xfail语义。公开测试反馈还混有基线颜色测试失败/缺xmlschema，需区分旧噪声与新回归。",
    },
    "mwaskom__seaborn-3187": {
        "kind": "missed_second_public_api", "rpc_ids": [121, 132], "log_lines": [350, 366],
        "observation": "问题正文明确objects.Plot与scatterplot均复现；候选只改_core/scales.py。官方对象接口目标通过，但relational图例仍是2.5而期望>1e7；公开159 passed。",
        "interpretation": "修复覆盖一个入口却遗漏题目明确提及的另一入口，不能仅凭广泛旧测试通过宣布问题整体解决。",
    },
    "pylint-dev__pylint-4604": {
        "kind": "test_collection_contract_unresolved", "rpc_ids": [108, 110], "log_lines": [329, 353],
        "observation": "公开variables单元测试20 passed；官方新增测试收集被缺IS_PYPY符号阻断，列出的21个失败并非21项行为断言已执行。",
        "interpretation": "IS_PYPY在baseline和candidate都缺失且constants.py字节未变；不是模型删除。尚不能区分未补辅助API与测试版本/环境契约问题。",
        "symbol_probe": ["pylint/constants.py", "IS_PYPY"],
    },
    "pylint-dev__pylint-4551": {
        "kind": "test_collection_contract_unresolved", "rpc_ids": [198, 199], "log_lines": [416, 438],
        "observation": "模型修改inspector.py/diagrams.py后在finish称当前版本早已支持type hints；官方测试收集因缺get_annotation符号阻断。",
        "interpretation": "get_annotation在baseline和candidate均不存在、utils.py未改。需要独立检查辅助API/验收契约，不能把10个列出failure当10个独立运行断言。",
        "symbol_probe": ["pylint/pyreverse/utils.py", "get_annotation"],
    },
    "matplotlib__matplotlib-26466": {
        "kind": "incomplete_input_copy_coverage", "rpc_ids": [43, 48, 51], "log_lines": [409, 451],
        "observation": "仅在_AnnotationBase.__init__复制xy，公开103个text测试通过；官方annotate_and_offsetfrom_copy_input组合图像测试仍RMS 4.714。",
        "interpretation": "局部复制修补未覆盖验收中的全部输入引用路径；测试名涉及OffsetFrom只是诊断线索，不据此声称只有某一参考实现才正确。",
    },
}


def ref(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def clean(text):
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def load(path):
    return json.loads(Path(path).read_bytes())


def symbol_probe(lock, path, symbol):
    result = {"path": path, "symbol": symbol}
    for name, key in (("baseline", "baseline"), ("candidate", "candidate")):
        bundle = load(lock[key]["path"])
        raw = decode_native_entry(path, bundle["files"][path], bundle["entry_metadata"][path])
        result[name] = {"snapshot": lock[key], "sha256": hashlib.sha256(raw).hexdigest(),
                        "symbol_present": symbol in raw.decode("utf-8")}
    result["bytes_unchanged"] = result["baseline"]["sha256"] == result["candidate"]["sha256"]
    return result


def verification_environment(config, transcript, official_log):
    entry = config["public_test_entry"]
    mapping = load(entry["baseline_mapping"]["path"])
    evidence = []
    for index, item in enumerate(transcript):
        request = item.get("request", {})
        observation = item.get("response", {}).get("observation", {})
        output = "\n".join(x.get("text", "") for x in observation.get("content", []))
        if "No module named pytest" in output:
            evidence.append({"rpc_id": request.get("id"), "transcript_index": index,
                "command": request.get("action", {}).get("command"),
                "observation_interpreter": observation.get("metadata", {}).get("py_interpreter_path"),
                "error_excerpt": clean(output)[-500:]})
    eval_path = official_log.parent / "eval.sh"
    lines = eval_path.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "Start Test Output" in line)
    return {"baseline_mapping": entry["baseline_mapping"],
        "mapping_public_python": mapping["public_python"],
        "mapping_public_python_details": mapping["public_python_details"],
        "registered_public_frontend_argv": entry["argv"],
        "registered_frontend_not_proof_it_was_presented_to_model": True,
        "official_eval_script": ref(eval_path), "official_test_command": lines[start + 1],
        "official_environment_activation": [line for line in lines if line.startswith("conda activate")],
        "observed_missing_pytest_requests": evidence,
        "interpretation": "Observed Python path matches the admitted testbed interpreter. Missing optional pytest is not proof the repository's own test runner is unavailable; repository entry/module/settings selection must be distinguished from wrong interpreter or failed environment preparation."}


def analyze():
    rows = list(csv.DictReader((INPUT / "slot-results.csv").open()))
    state = load(INPUT / "source-state.json")
    state_rows = {row["slot"]["slot_id"]: row for row in state["rows"]}
    bad = [row for row in rows if row["stop_class"] == "native_finished" and row["resolved"] == "False"]
    selected = {}
    for row in bad:
        old = selected.get(row["instance_id"])
        if old is None or int(row["token_limit"]) > int(old["token_limit"]):
            selected[row["instance_id"]] = row
    assert len(bad) == 31 and len(selected) == 15 and set(selected) == set(NOTES)
    cases = []
    for task, row in selected.items():
        directory = Path(row["generation_result"]).parent
        lock_path = directory / "candidates/lock.json"
        candidate = load(lock_path)
        transcript_path = directory / "native-rpc-transcript.json"
        transcript = load(transcript_path)
        config_path = directory / "controller-config.json"
        config = load(config_path)
        pointer = load(state_rows[row["slot_id"]]["score"]["receipt"]["path"])
        receipt_path = Path(pointer["receipt"]["path"])
        receipt = load(receipt_path)
        official = receipt["official_result"][1][task]
        log_path = next(receipt_path.parent.rglob("test_output.txt"))
        note = NOTES[task]
        lines = log_path.read_text(errors="replace").splitlines()
        lo, hi = note["log_lines"]
        finish = []
        for event_path in sorted((directory / "native-conversation").glob("*/events/*.json")):
            event = load(event_path)
            if event.get("tool_name") == "finish" and event.get("kind") == "ObservationEvent":
                finish.append((event_path, event))
        assert finish
        final_path, final = finish[-1]
        final_text = "\n".join(x.get("text", "") for x in final["observation"].get("content", []))
        commands = []
        for index, entry in enumerate(transcript):
            request = entry.get("request", {})
            if request.get("id") not in note["rpc_ids"]:
                continue
            observation = entry.get("response", {}).get("observation", {})
            output = "\n".join(x.get("text", "") for x in observation.get("content", []))
            commands.append({"rpc_id": request["id"], "transcript_index": index,
                "command_excerpt": request.get("action", {}).get("command", "")[:1800],
                "shell_exit_code": observation.get("exit_code"), "output_tail_excerpt": clean(output)[-2200:],
                "shell_exit_code_is_not_a_test_pass_claim": True})
        patch = candidate["patch_receipt"]
        case = {"slot_id": row["slot_id"], "instance_id": task, "condition_id": row["condition_id"],
            "token_limit": int(row["token_limit"]), "actual_tokens": int(row["actual_tokens"]),
            "remaining_tokens": int(row["token_limit"]) - int(row["actual_tokens"]),
            "model_attempts": int(row["model_attempts"]),
            "selection": "highest budget among native_finished and officially false for this task",
            "prompt_excerpt": config["public_task"]["problem_statement"][:1700],
            "sources": {"controller": ref(directory / "controller-result.json"),
                "public_task_configuration": ref(config_path), "candidate_lock": ref(lock_path),
                "native_rpc_transcript": ref(transcript_path), "official_receipt": ref(receipt_path),
                "official_test_output": ref(log_path), "finish_event": ref(final_path)},
            "modified_noncache_paths": [path for path in patch.get("modified_paths", [])
                if "__pycache__" not in path and not path.startswith(".pytest_cache/")],
            "path_filter_is_display_only": True, "complete_patch": patch["patch"],
            "finish_text_excerpt": final_text[:3000],
            "official_fail_to_pass": official.get("tests_status", {}).get("FAIL_TO_PASS", {}),
            "official_pass_to_pass_failures": official.get("tests_status", {}).get("PASS_TO_PASS", {}).get("failure", []),
            "official_log_excerpt": {"start_line": lo, "end_line": hi,
                "text": "\n".join(lines[lo-1:hi])},
            "public_verification_evidence": commands,
            "diagnostic_category": note["kind"], "direct_observation": note["observation"],
            "interpretation_or_hypothesis": note["interpretation"],
            "inference_is_not_causal_identification": True}
        if "symbol_probe" in note:
            case["baseline_and_candidate_symbol_check"] = symbol_probe(candidate, *note["symbol_probe"])
        if task in {"sympy__sympy-15017", "django__django-13807"}:
            case["verification_environment"] = verification_environment(config, transcript, log_path)
        cases.append(case)
    result = {"version": "v056-finished-wrong-case-review-r1", "script": ref(__file__),
        "sources": {"classification": ref(INPUT / "slot-results.csv"), "state": ref(INPUT / "source-state.json")},
        "population": {"native_finished_officially_false_episodes": len(bad),
            "high_budget_5M_10M_episodes": sum(int(row["token_limit"]) >= 5_000_000 for row in bad)},
        "selection_rule": "For every distinct task among the 31 native_finished+official-false runs, select its highest such budget, before qualitative review.",
        "selected_task_count": len(cases), "selected_budget_counts": dict(Counter(row["condition_id"] for row in cases)),
        "all_selected_budget_limits_at_least_5M": True,
        "diagnostic_group_counts_not_population_causes": dict(Counter(row["diagnostic_category"] for row in cases)),
        "cases": cases,
        "limits": ["Post-result diagnostic cases are not a randomly sampled causal study or an additional benchmark.",
            "Public tests passing does not cover all task semantics; neither does a shell exit 0 prove pytest passed when piped to head/tail.",
            "Requests network/fixture failures and pylint collection/API failures require separate attribution before being called model failures.",
            "Official failure lists may include tests not executed because collection failed.",
            "No reference/gold repair patch was inspected; no candidate or score was changed."],
        "model_calls": 0, "scoring_calls": 0, "public_test_executions": 0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"path": str(OUT), "case_count": len(cases), "population": result["population"]}))


if __name__ == "__main__":
    analyze()
