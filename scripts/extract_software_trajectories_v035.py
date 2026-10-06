"""Extract archived v035 decisions and exact selected inputs without replaying work.

The compressed artifacts remain usable without the original runs directory.
Use --show-call SLOT STEP --view decision|input to inspect one complete record.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(Path(path).read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reference(path, root):
    data = path.read_bytes()
    return {"path": str(path.relative_to(root)), "sha256": digest(data), "bytes": len(data)}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl_gz(path, rows):
    data = "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in rows)
    path.write_bytes(gzip.compress(data.encode(), mtime=0))


def read_jsonl_gz(path):
    return [json.loads(x) for x in gzip.decompress(path.read_bytes()).splitlines()]


def brief(value, limit=150):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\n", " ").replace("|", "／").replace("<", "&lt;")
    return text if len(text) <= limit else text[:limit] + "…（完整值见原记录）"


def outcome(action):
    payload = action["payload"]
    response = payload["response"]
    if not response.get("ok"):
        return "拒绝：" + brief(response.get("error", {}))
    result = response.get("result", {})
    ref = result.get("source_reference", {})
    version = ref.get("version_id", "")
    name = payload["action"]
    if name == "run_tests":
        groups = result["groups"]
        parts = [f"{k}={v['passed'] if v.get('passed') is not None else v.get('status')}" for k, v in groups.items()]
        return f"{version} 整体={result.get('passed')}；" + "；".join(parts)
    if name == "integrate_patch":
        return f"{version} {result.get('status')}；冲突={','.join(result.get('conflicts', []))}"
    if name in {"write_file", "replace_file"}:
        return version + " 已写入"
    if name in {"create_task", "claim_task", "revise_task", "delegate_task", "return_task"}:
        return brief({k: v for k, v in result.items() if k in {"task_id", "owner", "revision", "description"}})
    if name in {"fix_patch", "submit_integration"}:
        return brief({k: v for k, v in result.items() if k in {"patch_id", "delivery_id", "actor_id", "author", "source_reference", "task_ids", "status"}})
    if name in {"staff_done", "staff_wait"}:
        return brief(response)
    return f"ok；{version}" if version else "ok"


def argument_brief(payload):
    args = payload["arguments"]
    if payload["action"] in {"write_file", "replace_file"}:
        code = args.get("text", args.get("new", ""))
        return f"{args.get('path')}；写入文本{len(code)}字符（原文保留）"
    return brief(args)


def extract_slot(root, output, slot_index, accounting, methods):
    source = root / f"runs/software-support-v035/qwen3.5-9b/actual/collection/slot-{slot_index}"
    target = output / f"slot-{slot_index:02d}"
    target.mkdir(parents=True, exist_ok=True)
    projections = {}
    for path in sorted((source / "raw-transport/context-projections").glob("request-*/budget-preparation.json")):
        prep = read(path)
        key = prep["original_request_sha256"]
        if key in projections:
            assert projections[key][1] == prep
        projections[key] = (path.parent, prep)
    raw = (source / "experience.jsonl").read_bytes()
    calls, current, terminal = {}, {}, None
    kind_counts = Counter()
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        event = json.loads(line)
        kind, p = event["kind"], event["payload"]
        kind_counts[kind] += 1
        pointer = {"sequence": event["sequence"], "line_1based": line_number, "original_line_sha256": digest(line)}
        actor = event.get("worker_id")
        if kind == "model_call" and p["stage"] == "started":
            call_id = p["call_id"]
            assert call_id not in calls
            current[actor] = call_id
            calls[call_id] = {"slot_index": slot_index, "step": len(calls) + 1,
                "call_id": call_id, "member": actor, "member_decision_index": p["decision_index"],
                "opportunity_id": p["opportunity_id"], "call_started": pointer,
                "request_sha256": p["request_sha256"], "reservation": p["reservation"],
                "sampled": False, "model_output": None, "action_events": [], "feedback_events": []}
        elif kind == "run_boundary":
            terminal = {"source": pointer, "payload": {k: v for k, v in p.items() if k not in {"outcomes", "team_budget"}}}
        elif kind in {"model_response", "tool_call", "harness_tool_call", "model_format_error",
                      "model_format_feedback", "model_tool_result", "model_boundary_error", "model_control"}:
            call_id = p.get("call_id", p.get("model_call_id", current.get(actor)))
            assert call_id in calls, (slot_index, kind, pointer)
            row = calls[call_id]
            assert row["member"] == actor
            if kind == "model_response":
                response = p["response"]
                row["sampled"] = True
                row["model_output"] = {"source": pointer, "response_id": response["id"],
                    "raw_generated_text": response["raw_generated_text"], "choices": response["choices"],
                    "usage": response["usage"], "protocol_parse_error": response.get("protocol_parse_error"),
                    "token_trace_reference": "Original model_response at this source sequence; token IDs/probabilities are not regenerated or duplicated."}
            elif kind in {"tool_call", "harness_tool_call"}:
                row["action_events"].append({"kind": kind, "source": pointer, "payload": p})
            else:
                # The boundary's cumulative ledger duplicates all previous calls.
                payload = {k: v for k, v in p.items() if k != "team_budget"}
                row["feedback_events"].append({"kind": kind, "source": pointer, "payload": payload})
        elif kind == "model_attempt" and p["stage"] == "finished":
            calls[p["call_id"]]["attempt"] = {"source": pointer, **{k: p[k] for k in
                ("started_at", "ended_at", "wall_seconds", "status", "team_accounting")}}
    rows, inputs = list(calls.values()), []
    for row in rows:
        if row["request_sha256"] not in projections:
            assert not row["sampled"]
            prep = row["reservation"]["preparation"]
            row["selected_input"] = {"source": None, "projection_source": None,
                "input_ids_sha256": prep["input_ids_sha256"], "selected_request_sha256": prep["selected_request_sha256"],
                "actually_generated": False, "archive_record": row["step"],
                "missing_reason": "Pre-generation refusal: preparation hashes exist, but no selected-request file was archived. No input is reconstructed."}
            inputs.append({"slot_index": slot_index, "step": row["step"], "call_id": row["call_id"], "member": row["member"],
                "actually_generated": False, "source": None, "selected_request_original_text": None,
                "projection": None, "budget_preparation": prep, "missing_reason": row["selected_input"]["missing_reason"]})
            continue
        path, prep = projections[row["request_sha256"]]
        selected_path = path / "selected-request.json"
        selected_text = selected_path.read_text()
        assert prep["input_ids_sha256"] == row["reservation"]["preparation"]["input_ids_sha256"]
        row["selected_input"] = {"source": reference(selected_path, root), "projection_source": reference(path / "projection.json", root),
            "input_ids_sha256": prep["input_ids_sha256"], "selected_request_sha256": prep["selected_request_sha256"],
            "actually_generated": row["sampled"], "archive_record": row["step"]}
        inputs.append({"slot_index": slot_index, "step": row["step"], "call_id": row["call_id"], "member": row["member"],
            "actually_generated": row["sampled"], "source": row["selected_input"]["source"],
            "selected_request_original_text": selected_text, "projection": read(path / "projection.json"), "budget_preparation": prep})
    a = accounting[slot_index]
    m = methods[slot_index]
    assert len(rows) == a["decisions_including_admission_rejections"]
    assert sum(row["sampled"] for row in rows) == a["actual_attempts_and_calls"]
    assert sum(row["model_output"]["usage"]["total_tokens"] for row in rows if row["sampled"]) == a["charged_tokens"]
    actions = [action for row in rows for action in row["action_events"]]
    assert len(actions) == kind_counts["tool_call"] + kind_counts["harness_tool_call"]
    assert sum(x["payload"]["action"] == "run_tests" and x["payload"]["response"].get("ok", False) for x in actions) == a["test_runs"]
    by_member = {}
    for member in ("member_a", "member_b"):
        actor_rows = [r for r in rows if r["member"] == member]
        actor_actions = [x for r in actor_rows for x in r["action_events"]]
        accepted = [x for x in actor_actions if x["payload"]["response"].get("ok")]
        tests = [x for x in accepted if x["payload"]["action"] == "run_tests"]
        by_member[member] = {"actual_calls": sum(r["sampled"] for r in actor_rows),
            "action_attempts": dict(Counter(x["payload"]["action"] for x in actor_actions)),
            "accepted_actions": dict(Counter(x["payload"]["action"] for x in accepted)),
            "edited_paths": dict(Counter(x["payload"]["arguments"]["path"] for x in accepted if x["payload"]["action"] in {"write_file", "replace_file"})),
            "test_results": [{"sequence": x["source"]["sequence"], "passed": x["payload"]["response"]["result"]["passed"],
                "groups": {k: {f: g.get(f) for f in ("passed", "status")} for k, g in x["payload"]["response"]["result"]["groups"].items()}} for x in tests]}
    write_jsonl_gz(target / "decisions.jsonl.gz", rows)
    write_jsonl_gz(target / "selected-inputs.jsonl.gz", inputs)
    manifest = {"version": "v035-real-trajectory-audit-v1", "slot_index": slot_index,
        "seed": a["sampling_seed"], "decisions": len(rows), "actual_calls": a["actual_attempts_and_calls"],
        "pregen_rejections": len(rows) - a["actual_attempts_and_calls"], "charged_tokens": a["charged_tokens"],
        "R": a["R"], "mapping": a["mapping_status"], "method_class": a["method_class"],
        "final_delivery": m["final_delivery"], "actual_integrations": m["actual_integrations"],
        "source": {"path": str((source / "experience.jsonl").relative_to(root)), "sha256": digest(raw), "bytes": len(raw), "lines": sum(kind_counts.values())},
        "event_kind_counts": dict(kind_counts), "members": by_member, "terminal": terminal,
        "accounting_source": reference(root / "runs/v035-report-analysis/accounting.json", root),
        "frozen_method_analysis_source": reference(root / "runs/v035-report-analysis/methods.json", root),
        "artifacts": {name: reference(target / name, root) for name in ("decisions.jsonl.gz", "selected-inputs.jsonl.gz")},
        "consistency": {"call_count": True, "token_total": True, "all_action_records_extracted": True, "test_count": True},
        "new_model_calls": 0, "new_acceptance_executions": 0, "new_mapper_executions": 0}
    write_json(target / "manifest.json", manifest)
    return manifest


def render_slot(root, output, analyses, index):
    target = output / f"slot-{index:02d}"
    manifest = read(target / "manifest.json")
    rows = read_jsonl_gz(target / "decisions.jsonl.gz")
    summary_path = analyses / f"slot-{index:02d}-summary.json"
    summary = read(summary_path) if summary_path.exists() else None
    if summary:
        assert summary["slot_index"] == index
        sequences = {x["source"]["sequence"] for row in rows for field in ("action_events", "feedback_events") for x in row[field]}
        sequences |= {r["call_started"]["sequence"] for r in rows}
        sequences.add(manifest["terminal"]["source"]["sequence"])
        for text in [*summary["division_of_work"], *summary["collaboration"], *summary["outcome"], *summary["audit_focus"]]:
            for number in re.findall(r"\bseq\s+(\d+)", text):
                assert int(number) in sequences, (index, number)
        write_json(target / "summary.json", summary)
    title = summary["headline"] if summary else "完整动作已抽取，摘要待合并"
    final = manifest["final_delivery"]
    final_text = f"{final['actor_id']}/{final['source_reference']['version_id']}（{final['delivery_id']}）" if final else "无固定交付"
    lines = [f"# 槽{index:02d}：{title}", "", "[返回审计索引](../index.md)", "",
        f"seed={manifest['seed']}；R={manifest['R']}；原映射={manifest['method_class'] or manifest['mapping']}；最终交付={final_text}。",
        f"{manifest['decisions']}个账本决定，其中{manifest['actual_calls']}次真实生成、{manifest['pregen_rejections']}次生成前拒绝；实际token={manifest['charged_tokens']}。", ""]
    if summary:
        for field, heading in [("division_of_work", "任务分工：声明与实际动作"), ("collaboration", "协作交互与产物流向"), ("outcome", "最终交付与终止"), ("audit_focus", "审计时应留意")]:
            linked = [re.sub(r"\[seq\s+(\d+)\]", r"[seq \1](#seq-\1)", x) for x in summary[field]]
            lines += [f"## {heading}", ""] + ["- " + x for x in linked] + [""]
    lines += ["## 双方动作概况", "", "| 成员 | 实际生成 | 成功编辑次数（按文件） | 已执行测试 | 公开业务与上游均通过 | run_tests整体通过 |", "|---|---:|---|---:|---:|---:|"]
    for member, data in manifest["members"].items():
        tests = data["test_results"]
        public = sum(all(t["groups"][g]["passed"] is True for g in ("public_normal", "upstream_regressions")) for t in tests)
        lines.append(f"| {member} | {data['actual_calls']} | {brief(data['edited_paths'], 500)} | {len(tests)} | {public} | {sum(t['passed'] is True for t in tests)} |")
    lines += ["", "编辑次数是成功操作次数，不代表原创归属；测试通过数是工具调用数，不是独立任务数。", "", "## 完整动作时间线", "",
        "按原日志顺序列出所有决定，包括读取、失败、格式拒绝、等待和终止。表格只压缩展示长文本；完整参数、代码、原输出、工具返回均保存在下方数据文件。`seq`是原experience日志的sequence，不是世界内部事件号。", "",
        "| 步 | 成员 | 原seq | 动作／状态 | 参数或对象 | 原结果摘要 |", "|---:|---|---:|---|---|---|"]
    for row in rows:
        if row["action_events"]:
            for action in row["action_events"]:
                p = action["payload"]
                seq = action["source"]["sequence"]
                lines.append(f"| {row['step']} | {row['member']} | <a id=\"seq-{seq}\"></a>{seq} | {p['action']} | {argument_brief(p)} | {outcome(action)} |")
        else:
            feedback = next((x for x in row["feedback_events"] if x["kind"] in {"model_format_error", "model_boundary_error"}), None)
            seq = feedback["source"]["sequence"] if feedback else row["call_started"]["sequence"]
            lines.append(f"| {row['step']} | {row['member']} | <a id=\"seq-{seq}\"></a>{seq} | {'格式拒绝' if row['sampled'] else '生成前预算拒绝'} | 无世界动作 | {brief(feedback['payload'].get('reason', feedback['payload'].get('message', ''))) if feedback else '原账无动作'} |")
    terminal_seq = manifest["terminal"]["source"]["sequence"]
    lines += ["", f"<a id=\"seq-{terminal_seq}\"></a>终态原seq {terminal_seq}：`{manifest['terminal']['payload']['role_stops']}`。", "", "## 可移植原文与定位", "",
        "- [decisions.jsonl.gz](decisions.jsonl.gz)：每行一个账本决定；保留完整原生成文本、解析后的assistant消息、动作参数与工具原返回、反馈和原日志行hash。",
        "- [selected-inputs.jsonl.gz](selected-inputs.jsonl.gz)：同序号真实调用的完整selected-request原文件文本、投影记录和输入IDs hash。生成前拒绝只有原准备hash，没有归档的selected-request全文；该项保留null并以actually_generated=false标明，不重建输入。",
        "- [manifest.json](manifest.json)：原日志／抽取文件hash、逐成员统计、原最终交付与原停止信息。",
        "", "`model_tool_result`只说明回执进入了会话记录；是否实际出现在某次模型输入，以该次selected-request为准。后台完整回执不等同于成员看见的内容。原输出中的自述仅为模型声明，不能替代执行／验收。输入和动作不被事后改写。", "",
        "从仓库根目录查看某一步（把最后的步号换成表中的值）：", "", "```bash",
        f".venv/bin/python -m scripts.extract_software_trajectories_v035 --show-call {index} 1 --view decision",
        f".venv/bin/python -m scripts.extract_software_trajectories_v035 --show-call {index} 1 --view input", "```", "",
        "原始日志：`" + manifest["source"]["path"] + "`；sha256=`" + manifest["source"]["sha256"] + "`。", ""]
    (target / "trajectory.md").write_text("\n".join(lines))
    return manifest, summary


def render(root, output, analyses):
    results = [render_slot(root, output, analyses, i) for i in range(16)]
    manifests = [x[0] for x in results]
    assert sum(x["decisions"] for x in manifests) == 710
    assert sum(x["actual_calls"] for x in manifests) == 701
    assert sum(x["charged_tokens"] for x in manifests) == 7286778
    mapped_others = []
    for m in manifests:
        if m["method_class"] != "own_tree_delivery":
            continue
        other = "member_b" if m["final_delivery"]["actor_id"] == "member_a" else "member_a"
        tests = m["members"][other]["test_results"]
        mapped_others.append({"slot_index": m["slot_index"], "member": other,
            "any_public_groups_passed": any(all(t["groups"][g]["passed"] is True for g in ("public_normal", "upstream_regressions")) for t in tests),
            "any_overall_passed": any(t["passed"] is True for t in tests), "tests": tests})
    assert sum(x["any_public_groups_passed"] for x in mapped_others) == 10
    assert sum(x["any_overall_passed"] for x in mapped_others) == 9
    index = {"version": "v035-real-trajectory-audit-v1", "slots": 16, "ledger_decisions": 710,
        "actual_model_calls": 701, "pregen_rejections": 9, "charged_tokens": 7286778,
        "new_model_calls": 0, "new_acceptance_executions": 0, "new_mapper_executions": 0,
        "narrative_summaries_complete": all(x[1] is not None for x in results),
        "public_pass_erratum": {"old_report_commit": "9662d65", "old_public_pass_count": 9,
            "correct_public_pass_count": 10, "overall_pass_count": 9,
            "reason": "The prior derived analysis used top-level run_tests.passed for a public-group pass label. Slot2/member_b has four public-group passes but failing member_tests; original scores/mapping are unchanged.",
            "mapped_other_member_evidence": mapped_others},
        "source_scope": "All sixteen predeclared trajectories, all generated decisions and pre-generation refusals; no resampling, replay, regrading or method remapping.",
        "generator": reference(Path(__file__).resolve(), root),
        "trajectories": [{"slot_index": m["slot_index"], "headline": s["headline"] if s else None,
            "manifest": reference(output / f"slot-{m['slot_index']:02d}/manifest.json", root),
            "document": reference(output / f"slot-{m['slot_index']:02d}/trajectory.md", root)} for m, s in results]}
    write_json(output / "index.json", index)
    validation_path = analyses / "extraction-validation.json"
    if validation_path.exists():
        validation = read(validation_path)
        assert validation["passed"] and validation["counts"]["decisions"] == 710
        write_json(output / "extraction-validation.json", validation)
        index["independent_extraction_validation"] = reference(output / "extraction-validation.json", root)
        write_json(output / "index.json", index)
    lines = ["# v0.35真实轨迹审计包：16条逐槽分工与交互", "",
        "本包抽取本轮全部16条预登记轨迹。每条都有逐项核对的分工／协作摘要、完整决定时间线和可移植原文。原R、冻结Mapper与原停止决定保持。", "",
        "共710个账本决定：701次真实模型生成与9次生成前预算拒绝，实际7286778 token。抽取新增模型调用、验收执行和Mapper执行均为0。", "",
        "## 共同任务与初始组织", "",
        "16条都是同一新sqlparse根目标的不同预登记seed：reader.statement_records(script)使用真实sqlparse.split、sqlparse.parse和Statement.get_type()生成有序记录；report.summarize(script)消费reader结果，返回原记录、SELECT／UPDATE／DELETE三类整数计数及total。输入限合同声明的合法平面单表语句，包括空白、重复、引号内分号与可选末尾分号。完整原合同在每次实际selected输入中保留。", "",
        "两名等权成员共享同一固定9B参数与团队预算，但各有私有会话和文件副本，A固定先手，初始任务板为空。任务、认领、发布、导入及提交均由实际动作产生。下表的‘先各自实现’描述写文件事实，不意味着两个早期版本均已正确。", "",
        "## 阅读方式", "",
        "先看每槽摘要及双方动作概况，再按原seq核对时间线。需检查具体代码、参数或模型原输出时，用文末命令查看decisions记录；需判断当时实际可见信息时，查看对应selected-inputs。两种压缩文件均为UTF-8 JSONL，可用Python标准库gzip读取，无需原运行目录。", "",
        "任务创建／描述不等于已认领；认领不等于独占代码作者；固定发布不等于验收通过；导入成功受理不等于没有冲突。最终R仅来自原独立验收。原模型在message或reason中声称完成、分工或采纳，不自动成为事实。", "",
        "## 逐槽入口", "", "| 槽 | seed尾号 | 任务分工与交互摘要 | R | 原方法标签 |", "|---:|---:|---|---:|---|"]
    for m, s in results:
        i = m["slot_index"]
        lines.append(f"| [{i:02d}](slot-{i:02d}/trajectory.md) | {str(m['seed'])[-3:]} | {s['headline'] if s else '摘要待合并'} | {m['R']} | {m['method_class'] or m['mapping']} |")
    lines += ["", "## 本次逐轨迹抽取发现的统计勘误", "",
        "上一详细报告提交9662d65将10条own轨迹中‘另一成员至少一次公开业务通过’写成9/10。原脚本实际数的是run_tests整体passed：正确口径是**公开业务与上游组均通过10/10，工具整体至少一次通过9/10**。差异来自槽02的B：原seq 300、606、657、756四次公开两组均通过，但成员自测失败，整体为false。", "",
        "本包按原groups逐项统计并提供全部证据；旧派生分析文件保留以追踪勘误，详细报告同步修正。不改变任何原测试记录、R、Mapper、15/16成功率或10条单类支持结论。", "",
        "## 提取范围与核验", "",
        "压缩的decisions保留完整动作参数、原生成文本、assistant消息、世界工具返回及反馈；只省去重复的SDK日志、累计观测副本、累计预算账和大体积token IDs／概率数组，这些仍可按原日志路径、行号和SHA定位。selected-inputs保留701次真实调用的原请求文件文本（包含完整消息与工具定义），并保存投影和input IDs hash；没有重分词。9个被拒请求仅保有预算准备hash，未归档selected-request全文；该全文明确为null，actually_generated=false，不重建输入或补造输出。", "",
        "必要核验包括每槽账本决定／实际生成／测试／token计数与封存账一致、所有tool_call和harness_tool_call完整抽取、摘要seq存在、输入准备hash对应。没有重跑模型、世界、验收、分类或全仓测试。", "",
        "[独立原文核验](extraction-validation.json)逐项确认701份原输出、673个实际工具／控制动作payload与原日志相等，701份selected输入的UTF-8原字节和hash相等；9次拒绝无输出。所有原调用和动作完整、唯一对应，原seq／行号／行hash与16份源日志hash匹配。", "",
        "完整selected输入包含历史多轮消息，不能把同一历史动作在不同输入中的重复出现算作多次执行；实际执行次数以decisions动作事件为准。", "",
        "[机器索引与勘误证据](index.json) · [本轮详细报告](../software-support-v035-final.md)", "",
        "重新抽取与合并摘要（需原归档及runs/v035-trajectory-analysis中的摘要）：", "", "```bash",
        ".venv/bin/python -m scripts.extract_software_trajectories_v035", "```", ""]
    (output / "index.md").write_text("\n".join(lines))
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--analyses", type=Path)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--show-call", type=int, nargs=2, metavar=("SLOT", "STEP"))
    parser.add_argument("--view", choices=("decision", "input"), default="decision")
    args = parser.parse_args()
    root = args.data_root.resolve()
    output = (args.output or root / "docs/experiments/software-support-v035-trajectories").resolve()
    if args.show_call:
        slot, step = args.show_call
        name = "decisions.jsonl.gz" if args.view == "decision" else "selected-inputs.jsonl.gz"
        rows = read_jsonl_gz(output / f"slot-{slot:02d}" / name)
        row = next(r for r in rows if r["step"] == step)
        if args.view == "input":
            original_text = row.pop("selected_request_original_text")
            row["selected_request"] = json.loads(original_text) if original_text is not None else None
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return
    output.mkdir(parents=True, exist_ok=True)
    if not args.render_only:
        accounting = read(root / "runs/v035-report-analysis/accounting.json")["slots"]
        methods = read(root / "runs/v035-report-analysis/methods.json")["episodes"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: extract_slot(root, output, i, accounting, methods), range(16)))
    index = render(root, output, args.analyses or root / "runs/v035-trajectory-analysis")
    print(json.dumps({k: index[k] for k in ("slots", "ledger_decisions", "actual_model_calls", "pregen_rejections", "narrative_summaries_complete")}))


if __name__ == "__main__":
    main()
