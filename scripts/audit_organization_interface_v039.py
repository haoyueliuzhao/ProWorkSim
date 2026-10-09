"""Narrow read-only v039 interface audit of the eight original v038 O3 episodes.

The input rule is fixed: each initial member's first, tenth and last actually
started generation. A missing tenth position stays missing; duplicate positions
are merged. Stored selected-request hashes bind requests to actual attempt
records; preparation alone never proves a generation occurred. All 33 original
format-rejected outputs have separately documented full-text human review.

No model, GPU, test, acceptance, old tensor/archive hash or TextFSM access.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMBER_IDS = [f"member_{i:03d}" for i in range(1, 7)]
ORGANIZATION_TOOLS = ("spawn_member", "send_message", "offer_transfer", "accept_transfer",
                      "decline_transfer", "return_task", "retire_member", "staff_wait", "staff_done")
# Explicit annotations after reading all 33 complete raw_generated_text values.
# These labels are not inferred by a name regex or an automated intent model.
REVIEW_GROUPS = {
    "multiple_read_calls": ["model-8fffc75c569dd4d3e61cd1ae", "model-a4fc97b0808d519f929e82de",
        "model-dfd41ecae410978cd6491acf", "model-129117640eb49661d3b4f851", "model-aa1931f60b57be5d6f29d2a6",
        "model-3e04f3b56b3773ca3df55347", "model-923428d85605bcc8330b5c89"],
    "oversized_read": ["model-7f59b675e47e47795ba41934", "model-647899605b3b7171caf2b290",
        "model-2ae49c405b3d5285b9ff06ea", "model-c7c9dfc5184c157135abf1b4", "model-fede363237126ed50c06ff52",
        "model-b454dafab9c790594d9329d5", "model-1dfe040adf876bd7d228238a", "model-8ed87ae3781770394ff4479e",
        "model-1fd60dfd2b953f6f71f89808", "model-57843a0e3cc8cf4cd44ba35f", "model-11ae8ea9d40e9cfd0bfb66b0",
        "model-3b02c956a771771f9077e15e", "model-d3d913f889fdfaa13ab15841", "model-060aa26c7616bb3eaa25a4a5",
        "model-c82c31bf70df31a8142e3aec", "model-cd78b45072112f835fb7592a", "model-d3f73251e6447088b4afef4e",
        "model-4be3220634d328648c12f712", "model-8ba36c978722a16f9dbfb052"],
    "missing_read_fields": ["model-a4d75bf65ddeb7175b86bb96", "model-0bae159bb13512bffc804591"],
    "incomplete_write": ["model-ea39ca171d61b7bc57bb0450", "model-f4d38c1a2c99122e6d750fdf"],
    "truncated_business_reasoning": ["model-5eeda3389dc576222212d57d"],
    "completion_summary_uncertain": ["model-8534010b2715df43272de300", "model-4135993c3e3f348cdd7dfcb4"],
}
REVIEW_NOTES = {
    "multiple_read_calls": "全文是读取多个代码文件的计划及多个 read_file 调用；没有增员、发送消息或调整职责请求。",
    "oversized_read": "全文是理解 schema API／修复业务实现并读取源文件；max_lines 超过声明上限180，无组织提议。",
    "missing_read_fields": "读取 contract.md，缺少 read_file 的必填行号／行数参数；无组织提议。",
    "incomplete_write": "业务分析或成员测试代码之后 write_file 原生块不完整；没有请求伙伴、创建成员或转交职责。",
    "truncated_business_reasoning": "全文反复讨论 schema 的 Str 导入错误和业务测试；输出截断，无明确组织动作。模型称测试有bug是其自述，不采作环境故障证据。",
    "completion_summary_uncertain": "自然语言完成总结，不含明确 staff_done/retire_member 控制或退出请求；可能意在结束回复，但不能确定为退役意图。",
}
REVIEW_INDEX = {call: group for group, calls in REVIEW_GROUPS.items() for call in calls}


def read(path):
    return json.loads(path.read_text())


def ref(path, line=None, pointer=None):
    return {"path": str(path), **({"line": line} if line is not None else {}),
            **({"json_pointer": pointer} if pointer is not None else {})}


def parse_content(message):
    try:
        content = json.loads(message.get("content", ""))
        return content if isinstance(content, dict) else {}
    except (TypeError, ValueError):
        return {}


def scan_episode(folder):
    budget = read(folder / "team-budget.json")["model"]
    result = read(folder / "slot-result.json")
    actual = {key: value for key, value in budget["records"].items() if value.get("attempt_started") is True}
    calls, outputs, errors, feedback, tool_results, executions, controls = [], {}, [], {}, {}, [], []
    path = folder / "experience.jsonl"
    with path.open() as stream:
        for line, raw in enumerate(stream, 1):
            event = json.loads(raw)
            kind, payload = event["kind"], event["payload"]
            source = ref(path, line)
            if kind == "model_attempt" and payload.get("stage") == "started" and payload["call_id"] in actual:
                calls.append({"call_id": payload["call_id"], "worker_id": event["worker_id"],
                    "experience_sequence": event["sequence"], "source": source})
            elif kind == "model_response":
                body = payload["response"]
                outputs[payload["call_id"]] = {"source": source, "experience_sequence": event["sequence"],
                    "response_id": body.get("id"), "raw_generated_text": body.get("raw_generated_text"),
                    "finish_reasons": [c.get("finish_reason") for c in body.get("choices", [])],
                    "completion_tokens": body.get("usage", {}).get("completion_tokens")}
            elif kind == "model_format_error":
                errors.append({"call_id": payload["call_id"], "worker_id": event["worker_id"],
                    "reason": payload["reason"], "source": source, "experience_sequence": event["sequence"]})
            elif kind == "model_format_feedback":
                feedback[payload["call_id"]] = {"feedback": payload["feedback"], "source": source}
            elif kind == "model_tool_result":
                tool_results[payload["model_tool_call_id"]] = {"message": payload["message"], "source": source}
            elif kind in {"tool_call", "harness_tool_call"} and payload.get("action") in ORGANIZATION_TOOLS:
                executions.append({"action": payload["action"], "worker_id": event["worker_id"],
                    "ok": payload["response"].get("ok"), "arguments": payload.get("arguments"),
                    "error": payload["response"].get("error"), "source": source})
            elif kind == "model_control":
                controls.append({"worker_id": event["worker_id"], "kind": payload["kind"],
                                 "call_id": payload.get("call_id"), "source": source})
    if len(calls) != len(actual) or {c["call_id"] for c in calls} != set(actual):
        raise ValueError("Actual started attempt order does not match original team ledger")
    projections = defaultdict(list)
    for path in sorted((folder / "raw-transport").glob("request-*/projection.json")):
        value = read(path)
        projections[value["selected_request_sha256"]].append((path, value))
    for call in calls:
        record = actual[call["call_id"]]
        preparation = record["reservation"]["preparation"]
        matches = projections[preparation["selected_request_sha256"]]
        if len(matches) != 1:
            raise ValueError("Require an unambiguous stored selected-request binding")
        path, projection = matches[0]
        if projection["input_ids_sha256"] != preparation["input_ids_sha256"]:
            raise ValueError("Stored selected-input-ID binding differs")
        call.update(selected_request=ref(path.with_name("selected-request.json")),
            projection=ref(path), selected_request_sha256=preparation["selected_request_sha256"],
            input_ids_sha256=preparation["input_ids_sha256"], prompt_tokens=preparation["prompt_tokens"],
            actual_attempt_binding=ref(folder / "team-budget.json", pointer="/model/records/" + call["call_id"]),
            actual_attempt_started=True)
    return {"budget": budget, "result": result, "calls": calls, "outputs": outputs,
            "errors": errors, "feedback": feedback, "tool_results": tool_results,
            "executions": executions, "controls": controls}


def expected_schemas():
    path = {"type": "string", "minLength": 1}
    member = {"type": "string", "enum": MEMBER_IDS}
    reference = {"type": "object", "properties": {"object_id": path, "version_id": path},
                 "required": ["object_id", "version_id"], "additionalProperties": False}
    return {
        "spawn_member": {"type": "object", "properties": {
            "briefing": {"type": "string", "minLength": 1, "maxLength": 4000},
            "patch_id": path, "replaces": member}, "required": ["briefing"], "additionalProperties": False},
        "send_message": {"type": "object", "properties": {
            "recipient": member, "task_id": path,
            "body": {"type": "string", "minLength": 1, "maxLength": 4000}, "fixed_reference": reference},
            "required": ["recipient", "task_id", "body"], "additionalProperties": False},
    }


def request_audit(call, episode):
    path = Path(call["selected_request"]["path"])
    request = read(path)
    tools = {tool["function"]["name"]: (index, tool["function"]) for index, tool in enumerate(request["tools"])}
    observations = [(index, parse_content(message).get("observation")) for index, message in enumerate(request["messages"])
                    if message.get("role") == "user"]
    matching = [(i, o) for i, o in observations if isinstance(o, dict) and o.get("actor_id") == call["worker_id"]]
    if not matching:
        raise ValueError("No own observation in sampled actual selected input")
    index, obs = matching[-1]
    registry, availability = obs.get("member_registry", {}), obs.get("member_availability", {})
    condition, limits, budget = obs.get("execution_condition", {}), obs.get("member_limits", {}), obs.get("team_model_budget", {})
    current_live = [m for m, record in registry.items() if record.get("status") == "live"]
    recipients = [m for m in current_live if m != call["worker_id"] and availability.get(m, {}).get("can_receive_work") is True]
    checks = {"all_organization_tools_present": all(name in tools for name in ORGANIZATION_TOOLS),
        "own_member_directory_present": call["worker_id"] in registry,
        "registry_matches_availability_members": set(registry) == set(availability),
        "active_members_match_live_registry": sorted(condition.get("active_executors", [])) == sorted(current_live),
        "cumulative_births_match_registry": condition.get("cumulative_births") == len(registry),
        "O3_capacity_contract_present": limits.get("births_enabled") is True and limits.get("max_live_members") == 4
            and limits.get("max_cumulative_births") == 6,
        "live_capacity_nonnegative": limits.get("max_live_members", -1) >= len(current_live),
        "birth_capacity_nonnegative": limits.get("max_cumulative_births", -1) >= len(registry),
        "remaining_budget_fields_present": {"limits", "decisions", "attempts", "charged_tokens", "held_tokens",
            "remaining_decisions", "remaining_attempts", "available_tokens"} <= set(budget),
        "available_tokens_consistent": budget.get("available_tokens") == budget.get("limits", {}).get("max_total_tokens", 0)
            - budget.get("charged_tokens", -1) - budget.get("held_tokens", -1),
        "remaining_decisions_consistent": budget.get("remaining_decisions") == budget.get("limits", {}).get("max_decisions", 0)
            - budget.get("decisions", -1),
        "remaining_attempts_consistent": budget.get("remaining_attempts") == budget.get("limits", {}).get("max_attempts", 0)
            - budget.get("attempts", -1)}
    for name, expected in expected_schemas().items():
        checks[name + "_complete_parameters"] = tools.get(name, (None, {}))[1].get("parameters") == expected
    recipient_enum = tools.get("send_message", (None, {}))[1].get("parameters", {}).get("properties", {}).get("recipient", {}).get("enum", [])
    checks["all_semantically_eligible_recipients_accepted_by_enum"] = set(recipients) <= set(recipient_enum)
    true_feedback, tool_errors = [], []
    for message_index, message in enumerate(request["messages"]):
        content = parse_content(message)
        feedback = content.get("public_format_feedback")
        if isinstance(feedback, dict):
            call_id = feedback.get("model_call_id")
            original = episode["feedback"].get(call_id)
            true_feedback.append({"call_id": call_id, "reason": feedback.get("reason"),
                "exact_original_feedback": original is not None and original["feedback"] == feedback,
                "source": ref(path, pointer=f"/messages/{message_index}"),
                "original_source": original["source"] if original else None})
        if message.get("role") == "tool" and content.get("ok") is False:
            original = episode["tool_results"].get(message.get("tool_call_id"))
            tool_errors.append({"tool_call_id": message.get("tool_call_id"), "error": content.get("error"),
                "original_error_content_and_call_binding_unchanged": original is not None and all(
                    message.get(key) == value for key, value in original["message"].items()),
                "added_message_metadata": sorted(set(message) - set(original["message"])) if original else None,
                "source": ref(path, pointer=f"/messages/{message_index}"),
                "original_source": original["source"] if original else None})
    checks["present_format_feedback_is_original"] = all(row["exact_original_feedback"] for row in true_feedback)
    checks["present_tool_errors_are_original"] = all(row["original_error_content_and_call_binding_unchanged"] for row in tool_errors)
    return {**call, "checks": checks, "all_checks_passed": all(checks.values()),
        "all_selected_tool_names": list(tools),
        "selected_tools": {name: {"source": ref(path, pointer=f"/tools/{tools[name][0]}"),
            "definition": tools[name][1]} for name in (*ORGANIZATION_TOOLS, "read_file") if name in tools},
        "observation_source": ref(path, pointer=f"/messages/{index}/content/observation"),
        "member_directory": registry, "member_availability": availability,
        "execution_condition": condition, "member_limits": limits,
        "derived_remaining_live_capacity": limits.get("max_live_members", 0) - len(current_live),
        "derived_remaining_birth_capacity": limits.get("max_cumulative_births", 0) - len(registry),
        "derived_semantically_eligible_recipients": recipients, "schema_recipient_enum": recipient_enum,
        "derivation_scope": "Remaining capacity and eligible recipients are mechanically derived from actual displayed state and rules; they are not claimed to be standalone original fields. Enum includes future/self IDs but description plus registry/availability constrain legal recipients.",
        "team_remaining_budget": budget, "team_test_budget": obs.get("team_test_budget"),
        "scheduling": obs.get("scheduling"), "format_feedback_in_input": true_feedback,
        "world_tool_errors_in_input": tool_errors}


def review_errors(unit, episode):
    by_member = defaultdict(list)
    for call in episode["calls"]:
        by_member[call["worker_id"]].append(call)
    result = []
    for error in episode["errors"]:
        call_id = error["call_id"]
        if call_id not in REVIEW_INDEX:
            raise ValueError("Unreviewed raw format output; do not infer intent automatically: " + call_id)
        group = REVIEW_INDEX[call_id]
        own = by_member[error["worker_id"]]
        position = next(i for i, call in enumerate(own) if call["call_id"] == call_id)
        next_call = own[position + 1] if position + 1 < len(own) else None
        original = episode["feedback"].get(call_id)
        receipt = {"has_next_actual_call": next_call is not None,
            "feedback_recorded": original is not None, "feedback_source": original["source"] if original else None,
            "next_actual_call": next_call,
            "next_actual_control": next((control for control in episode["controls"]
                if next_call and control["call_id"] == next_call["call_id"]), None),
            "exact_feedback_in_next_selected_input": None,
            "matching_message_indices": [], "status": "no_next_actual_generation_opportunity"}
        if next_call:
            request = read(Path(next_call["selected_request"]["path"]))
            matches = [i for i, message in enumerate(request["messages"])
                       if message.get("role") == "user" and original is not None
                       and parse_content(message).get("public_format_feedback") == original["feedback"]]
            receipt.update(exact_feedback_in_next_selected_input=bool(matches), matching_message_indices=matches,
                           status="exact_feedback_visible" if matches else "feedback_not_found_in_next_actual_input")
        output = episode["outputs"][call_id]
        result.append({"slot_id": unit["slot_id"], **error, "original_output": output,
            "human_full_text_review": {"classification": "uncertain" if group == "completion_summary_uncertain" else "not_proposed",
                "review_group": group, "reason": REVIEW_NOTES[group],
                "scope": "Full original raw_generated_text was read, including prose and code; natural-language Wait is not a staff_wait request.",
                "spawn_intent": "not_proposed", "message_intent": "not_proposed", "transfer_intent": "not_proposed",
                "wait_intent": "not_proposed", "retire_or_done_intent": "uncertain" if group == "completion_summary_uncertain" else "not_proposed"},
            "feedback_followthrough": receipt})
    return result


def render(report):
    summary = report["summary"]
    lines = ["# v0.39 阶段 A：v0.38 O3 实际接口与格式拒绝窄核查", "",
        "本次只读已有八条 O3，不重跑模型、GPU、验收、张量或大归档校验，不读取 TextFSM 确认池。"
        "仅核查实际输入是否给出了组织操作及真实状态，以及 33 条格式拒绝原输出与其后反馈。旧报告和原轨迹均未改写。", "",
        "## 固定取样规则与输入绑定", "",
        "取样规则在检查前固定：对每槽的两名初始成员，选其实际开始生成的第 1、第 10、最后一次请求。"
        "不足 10 次则将第 10 位置记为不存在；位置重复则合并，不挑选替代位置。"
        "先由原团队账本 `attempt_started=true` 与实际 model_attempt started 顺序确定调用，再以已有 "
        "`selected_request_sha256` / `input_ids_sha256` 绑定原 selected request；不把生成前被拒的准备请求当成实际输入。", "",
        f"八条共有 **{summary['actual_generation_calls']} 次实际调用**；48 个预定位置中 {summary['missing_positions']} 个不存在，"
        f"得到 **{summary['unique_sampled_requests']} 个不同的实际输入**。", "",
        "| O3 槽 | 001 实际调用／选中位置 | 002 实际调用／选中位置 | 输入核查 |",
        "|---|---|---|---|"]
    for slot in report["episodes"]:
        cells = []
        for member in ("member_001", "member_002"):
            row = slot["selection"][member]
            cells.append(f"{row['actual_call_count']} / " + ", ".join(
                str(p["requested_position"]) + ("(不存在)" if p["call_id"] is None else "") for p in row["positions"]))
        lines.append(f"| {slot['slot_id']} | {cells[0]} | {cells[1]} | "
                     + ("全部通过" if all(s["all_checks_passed"] for s in slot["sampled_requests"]) else "存在具体差异") + " |")
    lines += ["", "## 实际呈现了什么", "",
        f"{summary['sampled_requests_all_checks_passed']}/{summary['unique_sampled_requests']} 个选中输入中，"
        "完整 `spawn_member` 和 `send_message` 参数、组织工具集合、成员目录、可接收工作状态、"
        "O3 人数上限与团队剩余预算均可恢复，未发现遗漏必填参数或剩余预算算术矛盾。", "",
        "- `spawn_member`：必填 briefing（1–4000 字符），可选固定 patch_id 与 replaces；描述说明默认公共基线、不复制私有历史、出生不增加预算。",
        "- `send_message`：必填 recipient、task_id、body，可选固定引用；`root_goal` 可以在建任务前沟通。",
        "- 接收者 enum 包含 001–006 全身份空间；合法接收者还需符合当时目录、可接收工作状态和非本人规则。未来身份在 enum 中不表示已存在或可发送。",
        "- 原输入明确给出活动成员、累计出生数、活动上限4、累计上限6；剩余容量由这些原字段计算，并非另有一个原始 remaining-capacity 字段。",
        "- 预定取样只检查这些固定位置，不把 47 个输入推广为全部 314 个请求逐项核验。", "",
        "未发现组织工具的合法接收者被实际误拒：这八条没有进入工具执行层的消息、增员或转交调用，"
        "所以只能说没有观察到反例，不能据此宣称相关动态路径全部通过真实模型验证。", "",
        "**一处措辞残留：** `staff_wait` 的通用工具描述提到使用实际 world wait 工具推进世界时间；"
        "此软件接口的公开工具中没有该时间推进动作，而实际角色说明与 scheduling 字段将等待解释为真实事件唤醒。"
        "这是可定位的说明不一致；本批没有 wait 调用或明确等待提议，不能认定它造成了零增员，也不是已证实的运行接线故障。", "",
        "## 33 条格式拒绝：逐字判读与下一次反馈", "",
        "所有原输出（含完整自然语言、代码和被截断部分）保存在对应 JSON 的 `format_rejections[].original_output.raw_generated_text`。"
        "以下为逐字阅读后的分组，不是仅按工具名正则分类。", "",
        "| 原输出主要内容／格式断点 | 条数 | 组织意图判读 |", "|---|---:|---|"]
    labels = {"multiple_read_calls": "一次生成多个 read_file", "oversized_read": "read_file max_lines 超过180",
        "missing_read_fields": "read_file 缺必填行号／行数", "incomplete_write": "write_file 原生块不完整",
        "truncated_business_reasoning": "业务错误推理长输出截断", "completion_summary_uncertain": "没有控制调用的自然语言完成总结"}
    for group, count in summary["full_text_review_groups"].items():
        lines.append(f"| {labels[group]} | {count} | " + ("退出意图 uncertain；不当作明确退役请求" if group == "completion_summary_uncertain" else "未提出增员、消息、转交或明确等待／退出") + " |")
    lines += ["", "**31 条未提出组织动作；2 条完成总结的结束／退出意图不明确，标为 uncertain。**"
        "未找到明确提出增员、发送消息、转交或等待、却被格式层拦下的原文。"
        "业务推理中的“Wait, I realized…”属于语言转折，不按 staff_wait 计数。"
        "这仍不能被改写成“模型不愿协作”，也不是对全部原生成文本的心理动机判断。", "",
        f"33 条中 **{summary['format_errors_with_next_actual_call']} 条存在下一次同成员实际调用，"
        f"其中 {summary['exact_feedback_visible_in_next_input']} 条的原始错误反馈完整进入下一 selected input**；"
        f"另 {summary['format_errors_without_next_actual_call']} 条没有下一次实际生成机会，不记为反馈丢失。"
        "逐条记录原错误、反馈事件、下一调用和 selected 消息索引，按对象完全一致判断；不重新计算旧输入 hash。", "",
        "以下分层限定于本次关注的增员、消息、责任转交、等待与退出；不否定旧报告已记录的一次建任务／认领和少量产物整合。", "",
        "| 层次 | 本次可观察结果 |", "|---|---|",
        "| 未提出 | 31 条格式拒绝原文无明确组织动作 |",
        "| 提出但不可解析 | 明确增员／消息／转交／等待请求 0；另外保留 2 条 uncertain 完成总结 |",
        "| 可解析但执行拒绝 | 八条 O3 的增员／消息／转交／等待／直接退役工具拒绝 0；没有相应实际尝试 |",
        "| 实际执行 | 原八条 O3 的 staff_done 控制 3 次；没有 spawn、message、transfer、wait 或直接 retire_member 调用 |", "",
        "## 是否需要最多两条真实接口控制", "",
        "**未发现必须先修复组织接线才能继续的具体反例。** 当前缺口是：没有真实调用过增员和新成员交接，"
        "不能判断模型在明确接口测试指令下能否正确操作。仍建议把最多两条短控制单列，用于普通出生／消息回传、"
        "以及已退役身份与固定补丁的有限替换／版本取得。每条最多12次决定／attempt、150,000 token，一次结束，失败也保留。", "",
        "这些控制有明确测试指令，只回答接口调用与后续信息流；不并入自然组织成功率，不当作自主招募证据，"
        "不用于训练支持。**本核查没有启动控制，也没有预约或使用 GPU。**", "",
        "## 可复现来源", "",
        "- [机器明细与33条原文](software-organization-v039-interface-audit.json)",
        "- [只读提取脚本](../../scripts/audit_organization_interface_v039.py)",
        "- 每项原输入、格式拒绝与反馈都有实际文件路径、原 experience 行号或 JSON 指针。", "",
        "复现：`python scripts/audit_organization_interface_v039.py`。脚本只读取固定八条 O3，并重建这两份核查材料；"
        "人工全文分类以33个原 call ID 显式冻结，新增未审读输出会报错，不自动补判。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "runs/software-organization-v038")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/experiments/software-organization-v039-interface-audit.json")
    args = parser.parse_args()
    root = args.root.resolve()
    plan = read(root / "plan.json")
    episodes, reviews, actions, control_counts = [], [], Counter(), Counter()
    for worker, units in plan["assignments"].items():
        for unit in units:
            if unit["condition"] != "O3":
                continue
            folder = root / worker / "actual/episodes" / unit["slot_id"]
            episode = scan_episode(folder)
            selected, selection = {}, {}
            initial = episode["result"]["member_lifecycle"]["initial_members"]
            for member in initial:
                own = [c for c in episode["calls"] if c["worker_id"] == member]
                positions = []
                for label, index in ((1, 0), (10, 9), ("last", len(own) - 1)):
                    call = own[index] if 0 <= index < len(own) else None
                    positions.append({"requested_position": label, "actual_ordinal": index + 1 if call else None,
                                      "call_id": call["call_id"] if call else None})
                    if call:
                        selected.setdefault(call["call_id"], {**call, "selected_positions": []})["selected_positions"].append(label)
                selection[member] = {"actual_call_count": len(own), "positions": positions}
            samples = [request_audit(call, episode) for call in selected.values()]
            checked_errors = review_errors(unit, episode)
            reviews.extend(checked_errors)
            for execution in episode["executions"]:
                actions[execution["action"] + (":executed" if execution["ok"] is True else ":rejected")] += 1
            control_counts.update(c["kind"] for c in episode["controls"])
            episodes.append({"slot_id": unit["slot_id"], "source": ref(folder / "slot-result.json"),
                "selection": selection, "actual_generation_calls": len(episode["calls"]),
                "sampled_requests": samples, "organization_execution_receipts": episode["executions"],
                "actual_controls": episode["controls"], "format_rejections": len(checked_errors)})
    if len(episodes) != 8 or len(reviews) != 33 or {r["call_id"] for r in reviews} != set(REVIEW_INDEX):
        raise ValueError("Expected exactly the frozen eight O3 slots and 33 fully reviewed original outputs")
    sample_rows = [r for episode in episodes for r in episode["sampled_requests"]]
    summary = {"episodes": len(episodes), "actual_generation_calls": sum(e["actual_generation_calls"] for e in episodes),
        "requested_positions": 48, "missing_positions": sum(p["call_id"] is None for e in episodes
            for m in e["selection"].values() for p in m["positions"]),
        "unique_sampled_requests": len(sample_rows),
        "sampled_requests_all_checks_passed": sum(r["all_checks_passed"] for r in sample_rows),
        "full_text_review_groups": dict(Counter(r["human_full_text_review"]["review_group"] for r in reviews)),
        "intent_classifications": dict(Counter(r["human_full_text_review"]["classification"] for r in reviews)),
        "format_errors_with_next_actual_call": sum(r["feedback_followthrough"]["has_next_actual_call"] for r in reviews),
        "exact_feedback_visible_in_next_input": sum(r["feedback_followthrough"]["exact_feedback_in_next_selected_input"] is True for r in reviews),
        "format_errors_without_next_actual_call": sum(not r["feedback_followthrough"]["has_next_actual_call"] for r in reviews),
        "actual_organization_actions": dict(actions), "actual_control_counts": dict(control_counts)}
    report = {"version": "organization-interface-audit-v0.39", "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Narrow read-only original v038 O3 interface/input/output audit; not a new behavior or quality experiment",
        "selection_rule": "Each initial member: actual generation ordinal 1, 10, last; missing tenth stays missing; duplicate call IDs deduplicated. Actual attempt_started ledger plus started-event order, matched to stored selected-request and input-ID hashes.",
        "summary": summary, "episodes": episodes, "format_rejections": reviews,
        "counterexample_scope": "No observed omitted spawn/send schema or mis-rejected legal organization recipient in the inspected evidence. No actual spawn/message/transfer attempt exists; unexercised paths remain untested.",
        "wording_issue_source": sample_rows[0]["selected_tools"]["staff_wait"]["source"],
        "wording_issue": "Generic staff_wait tool description mentions an actual world wait tool for time advancement, absent from this software toolset; role task and scheduling instead describe event-driven suspension. Wording inconsistency only, not established cause or execution-wiring bug.",
        "probe_recommendation": {"recommended_maximum": 2, "started": False, "per_probe_max_decisions": 12,
            "per_probe_max_attempts": 12, "per_probe_max_total_tokens": 150000,
            "reason": "Direct model ability to create/use a new session remains unobserved despite visible tools; controls must stay separate from autonomous recruitment and main effects."},
        "new_model_calls": 0, "gpu_used": False, "new_tests_or_acceptance": 0,
        "old_artifact_hashes_recomputed": False, "textfsm_confirmation_read": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(render(report))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
