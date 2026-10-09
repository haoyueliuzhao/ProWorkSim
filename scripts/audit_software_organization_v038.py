"""Read only the 32 completed v036 episodes; never execute code, models or acceptance.

The B archive is streamed once. Only selected members are decoded and checked
against the existing cold-archive receipt; the full archive is not rehashed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = ("member_a", "member_b")
CORE_FILES = {"world/control/state.json", "runtime-state.json", "runtime-opportunities.jsonl",
              "experience.jsonl", "assessment.json"}
TASK_KINDS = {"task_created", "claim", "task_revised", "delegate", "task_returned",
              "dependency_declared", "dependency_removed"}
MESSAGE_KINDS = {"work_message", "delegate", "task_returned", "handoff"}
ATTEMPT_TOOLS = {"create_task", "claim_task", "revise_task", "delegate_task", "return_task",
                 "declare_dependency", "remove_dependency", "send_message", "handoff_patch",
                 "fix_patch", "run_tests", "submit_integration"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bound(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def compact_event(event):
    keys = ("sequence", "actor_id", "kind", "logical_time", "action_id", "task_id",
            "task_snapshot", "previous_task", "previous_owner", "owner", "recipient",
            "body", "reason", "notification", "patch_id", "source_reference", "source_sha256",
            "files_sha256", "included_patch_ids", "delivery_id", "test_sequence",
            "conflicts", "changed_paths", "task_ids", "message", "depends_on", "path")
    result = {key: event[key] for key in keys if key in event}
    if event.get("kind") == "test":
        result["groups"] = {name: {k: group.get(k) for k in ("status", "executed", "passed")}
                            for name, group in event.get("groups", {}).items()}
        result["passed"] = event.get("passed")
    return result


def selected_summary(value, reference):
    observations, tool_results = [], []
    for index, message in enumerate(value.get("messages", [])):
        if message.get("role") not in {"user", "tool"}:
            continue
        try:
            content = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        if not isinstance(content, dict):
            continue
        obs = content.get("observation")
        if isinstance(obs, dict):
            observations.append({"message_index": index, "actor_id": obs.get("actor_id"),
                "logical_time": obs.get("logical_time"),
                "workspace_reference": obs.get("workspace_reference"),
                "messages": obs.get("messages", []), "handoffs": obs.get("handoffs", []),
                "deliveries": obs.get("deliveries", []), "tasks": obs.get("tasks", {}),
                "older_message_sequences": obs.get("older_message_sequences", []),
                "member_availability": obs.get("member_availability", {})})
        if message.get("role") == "tool":
            tool_results.append({"message_index": index, "tool_call_id": message.get("tool_call_id"),
                                 "content": content})
    return {"source": reference, "observations": observations, "tool_results": tool_results}


def process_file(slot, relative, data, reference):
    slot.setdefault("sources", {})[relative] = reference
    if relative == "experience.jsonl":
        controls, boundary, errors, responses = [], None, [], {}
        for line in data.splitlines():
            event = json.loads(line)
            payload = event["payload"]
            if event["kind"] == "model_response":
                response = payload.get("response", {})
                named = [call.get("function", {}).get("name") for choice in response.get("choices", [])
                         for call in choice.get("message", {}).get("tool_calls", [])]
                responses[payload["call_id"]] = named or re.findall(
                    r"<function=([A-Za-z_]+)>", response.get("raw_generated_text", ""))
            elif event["kind"] == "model_control":
                controls.append({"sequence": event["sequence"], "actor_id": event.get("worker_id"),
                                 **{k: payload.get(k) for k in ("kind", "reason", "call_id")}})
            elif event["kind"] == "run_boundary":
                boundary = {k: payload.get(k) for k in ("status", "kind", "role_stops", "waiting_members",
                    "terminal_details", "closure_reason", "execution_integrity_failure", "opportunities", "actions")}
            elif event["kind"] in {"model_budget_exhausted", "model_context_exhausted",
                                    "model_format_error", "model_call_skipped", "model_boundary_error"}:
                errors.append({"sequence": event["sequence"], "actor_id": event.get("worker_id"),
                               "kind": event["kind"], "reason": payload.get("reason"),
                               "call_id": payload.get("call_id"),
                               "named_calls": responses.get(payload.get("call_id"), []),
                               "boundary_details": payload if event["kind"] == "model_boundary_error" else None})
        slot["experience"] = {"controls": controls, "boundary": boundary, "errors": errors}
    elif relative == "runtime-opportunities.jsonl":
        slot["opportunities"] = [json.loads(line) for line in data.splitlines()]
    elif relative.endswith("selected-request.json"):
        slot.setdefault("selected", []).append(selected_summary(json.loads(data), reference))
    elif relative.endswith("projection.json"):
        p = json.loads(data)
        slot.setdefault("projections", []).append({"source": reference, **{k: p.get(k) for k in (
            "fits", "context_limit", "reserved_output_tokens", "original_prompt_tokens", "selected_prompt_tokens",
            "selected_request_sha256", "input_ids_sha256", "removed_indices")}})
    else:
        slot[relative] = json.loads(data)


def wanted(relative):
    return relative in CORE_FILES or bool(re.fullmatch(
        r"raw-transport/context-projections/request-\d+/(selected-request|projection)\.json", relative))


def load_inputs(data_root):
    slots = defaultdict(dict)
    live = data_root / "qwen3.5-9b/actual/collection"
    for index in range(16):
        folder = live / f"slot-{index}"
        paths = [folder / name for name in sorted(CORE_FILES)]
        paths += sorted((folder / "raw-transport/context-projections").glob("*/selected-request.json"))
        paths += sorted((folder / "raw-transport/context-projections").glob("*/projection.json"))
        for path in paths:
            data = path.read_bytes()
            process_file(slots[("P2", index)], str(path.relative_to(folder)), data,
                         {"path": str(path), "bytes": len(data), "sha256": sha(data)})
    receipt_path = data_root / "trial-B/actual/cold-archive-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    expected = {e["path"]: e for e in receipt["entries"] if e["type"] == "file"}
    archive = Path(receipt["archive"]["path"])
    if not archive.exists():
        archive = receipt_path.parent / "development-original.tar.gz"
    count = 0
    with tarfile.open(archive, "r|gz") as handle:
        for member in handle:
            match = re.fullmatch(r"(?:\./)?slot-(\d+)/(.*)", member.name)
            if not match or not member.isfile() or not wanted(match[2]):
                continue
            key = member.name.removeprefix("./")
            stream = handle.extractfile(member)
            if stream is None:
                raise ValueError("Missing archive member: " + key)
            data = stream.read()
            digest = sha(data)
            if expected[key]["sha256"] != digest or expected[key]["size"] != len(data):
                raise ValueError("Selected archive member differs from original receipt: " + key)
            reference = {"archive": str(archive), "member": key, "bytes": len(data), "sha256": digest,
                         "matches_original_receipt": True}
            process_file(slots[("B-development", int(match[1]))], match[2], data, reference)
            count += 1
    return slots, {"receipt": bound(receipt_path), "archive": receipt["archive"],
        "archive_digest_scope": "Inherited previously verified digest; no redundant full-archive rehash",
        "selected_member_count_verified": count}


def last(rows):
    return rows[-1] if rows else None


def summarize(label, index, slot):
    state = slot["world/control/state.json"]
    software = state["projects"]["SOFTWARE27"]["software"]
    events = state["software_events"]
    tasks = software["tasks"]
    opportunities = slot["opportunities"]
    assessment = slot["assessment.json"]
    counts = Counter(e["kind"] for e in events)
    edits = [e for e in events if e["kind"] == "edit"]
    creates = [e for e in events if e["kind"] == "task_created"]
    budget = slot["runtime-state.json"]["team_budget"]["model"]
    def origin(reference):
        return reference.get("member", reference.get("path"))
    projections = {str(Path(origin(p["source"])).parent): p for p in slot["projections"]}
    generated = {v.get("reservation", {}).get("preparation", {}).get("selected_request_sha256"): key
                 for key, v in budget["records"].items() if v.get("attempt_started") and v.get("charge")}
    selected = []
    for inp in sorted(slot["selected"], key=lambda x: origin(x["source"])):
        projection = projections[str(Path(origin(inp["source"])).parent)]
        request_hash = projection["selected_request_sha256"]
        if request_hash in generated:
            inp["source"].update(selected_request_sha256=request_hash,
                input_ids_sha256=projection["input_ids_sha256"], model_call_id=generated[request_hash],
                actual_generation_evidence=slot["sources"]["runtime-state.json"])
            selected.append(inp)
    if len(selected) != budget["attempts"]:
        raise ValueError("Exact selected input must match actual charged generation attempts")
    attempts, endings = [], []
    for i, opp in enumerate(opportunities):
        decision = opp.get("decision", {})
        action = decision.get("action")
        response = opp.get("response", {})
        if action in ATTEMPT_TOOLS:
            args = decision.get("arguments", {})
            attempts.append({"opportunity": i + 1, "actor_id": opp["worker_id"], "action": action,
                "arguments": args, "ok": response.get("ok"), "action_id": response.get("action_id"),
                "error": response.get("error"), "status": opp.get("status"),
                "model_call_id": decision.get("model_call_id")})
        if opp.get("status") != "running":
            endings.append({"opportunity": i + 1, "actor_id": opp["worker_id"],
                            "status": opp.get("status"), "reason": opp.get("reason"),
                            "decision": {k: decision[k] for k in ("kind", "action", "model_call_id") if k in decision}})
    visibility = []
    for event in events:
        if event["kind"] not in MESSAGE_KINDS:
            continue
        matches = []
        for inp in selected:
            for obs in inp["observations"]:
                if obs["actor_id"] != event.get("recipient"):
                    continue
                if any(m.get("sequence") == event["sequence"] for m in obs["messages"] + obs["handoffs"]):
                    matches.append({"source": inp["source"], "message_index": obs["message_index"],
                        "observation_logical_time": obs["logical_time"]})
            for tool in inp["tool_results"]:
                result = tool["content"].get("result", {})
                if isinstance(result, dict) and result.get("sequence") == event["sequence"]:
                    # Keep explicit read evidence separate: an action receipt alone is not a recipient input.
                    actors = {o["actor_id"] for o in inp["observations"]}
                    if event.get("recipient") in actors:
                        matches.append({"source": inp["source"], "message_index": tool["message_index"],
                                        "source_kind": "selected_tool_return"})
        following = [compact_event(e) for e in events if e["sequence"] > event["sequence"]
                     and e["actor_id"] == event.get("recipient") and e["kind"] in TASK_KINDS | {
                         "work_message", "patch_fixed", "integrate", "test", "submit", "edit"}]
        visibility.append({"event": compact_event(event), "addressed_delivery_recorded": True,
            "recipient_selected_input_occurrences": len(matches), "first_selected_input": next(iter(matches), None),
            "subsequent_recipient_events": following,
            "response_scope": "Temporal subsequent actions only; no automatic causal response or understanding label"})
    adoption = []
    for event in events:
        if event["kind"] == "integrate":
            later = [e for e in events if e["sequence"] > event["sequence"] and e["actor_id"] == event["actor_id"]]
            adoption.append({"integration": compact_event(event),
                "first_later_test": next((compact_event(e) for e in later if e["kind"] == "test"), None),
                "later_submissions": [compact_event(e) for e in later if e["kind"] == "submit"],
                "scope": "Explicit import and subsequent tests/submissions; import IDs do not prove retained useful peer code"})
    members = {}
    for actor in MEMBERS:
        own_events = [e for e in events if e["actor_id"] == actor]
        obj = state["workspaces"]["SOFTWARE27"][actor]
        artifact = state["artifacts"][obj]
        current = {"object_id": obj, "version_id": artifact["current_version"]}
        latest_obs = [(inp, obs) for inp in selected for obs in inp["observations"] if obs["actor_id"] == actor]
        latest = last(latest_obs)
        test = last([e for e in own_events if e["kind"] == "test"])
        fixed = last([e for e in own_events if e["kind"] == "patch_fixed"])
        member_stops = [s for s in endings if s["actor_id"] == actor]
        stop = next((s for s in member_stops if s["status"] in {"completed", "budget_exhausted", "context_exhausted", "team_budget_exhausted", "model_budget_exhausted"}), None)
        post_stop = opportunities[stop["opportunity"]:] if stop else []
        members[actor] = {"current_workspace": {**current,
                "source_sha256": artifact["versions"][artifact["current_version"]]["sha256"]},
            "last_edit": compact_event(last([e for e in own_events if e["kind"] == "edit"]) or {}),
            "last_test": compact_event(test) if test else None,
            "last_test_is_current_version": test is not None and test.get("source_reference") == current,
            "last_fixed_patch": compact_event(fixed) if fixed else None,
            "last_fixed_patch_is_current_version": fixed is not None and fixed.get("source_reference") == current,
            "test_fix_submit_attempts": [a for a in attempts if a["actor_id"] == actor and a["action"] in {
                "run_tests", "fix_patch", "submit_integration"}],
            "runtime_endings": member_stops,
            "schema_or_format_rejected_calls": [e for e in slot["experience"]["errors"]
                if e["actor_id"] == actor and e["kind"] == "model_format_error"],
            "terminal_owned_task_ids": [t for t, task in tasks.items() if task["owner"] == actor],
            "last_selected_observation": {"source": latest[0]["source"], **latest[1]} if latest else None,
            "other_member_opportunities_after_stop": len([o for o in post_stop if o["worker_id"] != actor]),
            "other_member_actions_after_stop": [o.get("decision", {}).get("action") for o in post_stop
                if o["worker_id"] != actor and o.get("decision", {}).get("action")],
            "other_member_submissions_after_stop": sum(o.get("decision", {}).get("action") == "submit_integration"
                and o.get("response", {}).get("ok") is True for o in post_stop if o["worker_id"] != actor)}
    edited = {a: sorted({e["path"] for e in edits if e["actor_id"] == a}) for a in MEMBERS}
    read_paths = {a: {e["path"] for e in events if e["actor_id"] == a and e["kind"] in {"read", "search"}}
                  for a in MEMBERS}
    overlapping = sorted(set(edited[MEMBERS[0]]) & set(edited[MEMBERS[1]]))
    budget = slot["runtime-state.json"]["team_budget"]["model"]
    main_sources = {name: slot["sources"][name] for name in sorted(CORE_FILES)}
    return {"panel": label, "slot": index, "case_id": software["case"]["task_id"],
        "R": assessment.get("R"), "submitted": assessment.get("submitted"),
        "content_correct": assessment.get("content_correct"), "assessment_reason": assessment.get("reason"),
        "sources": main_sources, "event_counts": dict(sorted(counts.items())),
        "task_events": [{**compact_event(e), "next_own_actions": [compact_event(a) for a in events
            if a["actor_id"] == e["actor_id"] and a["sequence"] > e["sequence"]][:5]}
            for e in events if e["kind"] in TASK_KINDS],
        "terminal_tasks": tasks,
        "first_edit_sequence": edits[0]["sequence"] if edits else None,
        "first_create_sequence": creates[0]["sequence"] if creates else None,
        "edited_before_first_task": bool(edits and creates and edits[0]["sequence"] < creates[0]["sequence"]),
        "edited_paths_by_member": edited, "overlapping_edit_paths": overlapping,
        "overlapping_production_edit_paths": [p for p in overlapping if p != "test_member.py"],
        "both_explored_paths": sorted(read_paths[MEMBERS[0]] & read_paths[MEMBERS[1]]),
        "attempts": attempts, "message_visibility": visibility, "adoption_and_later_validation": adoption,
        "submissions": [compact_event(e) for e in events if e["kind"] == "submit"],
        "members": members, "runtime": slot["experience"],
        "budget": {k: budget.get(k) for k in ("limits", "decisions", "attempts", "charged_tokens",
            "available_tokens", "remaining_decisions", "remaining_attempts", "integrity_failure")},
        "context": {"actual_selected_request_count": len(selected), "projection_count": len(slot["projections"]),
            "prepared_without_charged_generation_count": len(slot["selected"]) - len(selected),
            "fits_false_count": sum(p["fits"] is False for p in slot["projections"]),
            "capacity_removed_any_count": sum(bool(p["removed_indices"]) for p in slot["projections"]),
            "max_selected_prompt_tokens": max(p["selected_prompt_tokens"] for p in slot["projections"]),
            "scope": "History projection/removal is distinct from an actual context-boundary stop"},
        "obligation_scope": "Owner records persist; old task schema has no completed flag. A remaining owner is not by itself proof of unfinished business. Requests are free text, without ack/close lifecycle; exact input and later acts are recorded separately."}


def aggregate(rows):
    result = {}
    for panel in ("P2", "B-development"):
        subset = [r for r in rows if r["panel"] == panel]
        event_counts = Counter()
        stops = Counter()
        for row in subset:
            event_counts.update(row["event_counts"])
            boundary = row["runtime"]["boundary"] or {}
            stops.update(detail.get("cause", detail.get("status", "unknown"))
                         for detail in boundary.get("terminal_details", {}).values())
        result[panel] = {"episodes": len(subset), "submitted": sum(bool(r["submitted"]) for r in subset),
            "successes": sum(r["R"] == 1 for r in subset), "event_counts": dict(event_counts),
            "slots_with_task_creation": sum(bool(r["terminal_tasks"]) for r in subset),
            "slots_edited_before_task_creation": sum(r["edited_before_first_task"] for r in subset),
            "slots_both_edited_production_paths": sum(bool(r["overlapping_production_edit_paths"]) for r in subset),
            "addressed_work_events": sum(len(r["message_visibility"]) for r in subset),
            "addressed_events_seen_in_recipient_selected_input": sum(v["first_selected_input"] is not None
                for r in subset for v in r["message_visibility"]), "member_stop_causes": dict(stops),
            "audited_world_tool_rejections": sum(a["ok"] is False for r in subset for a in r["attempts"]),
            "format_rejections": sum(e["kind"] == "model_format_error" for r in subset for e in r["runtime"]["errors"]),
            "slots_with_partner_work_after_done": sum(any(m["other_member_opportunities_after_stop"]
                and any(s["status"] == "completed" for s in m["runtime_endings"])
                for m in r["members"].values()) for r in subset),
            "partner_submissions_after_done": sum(m["other_member_submissions_after_stop"] for r in subset
                for m in r["members"].values() if any(s["status"] == "completed" for s in m["runtime_endings"])),
            "submitted_slots_final_delivery_in_both_members_last_actual_input": sum(bool(r["submissions"]) and all(
                any(d.get("delivery_id") == r["submissions"][-1]["delivery_id"]
                    for d in m["last_selected_observation"]["deliveries"]) for m in r["members"].values()) for r in subset),
            "context_boundary_episodes": sum(any(d.get("cause") == "context_capacity" for d in
                r["runtime"]["boundary"].get("terminal_details", {}).values()) for r in subset)}
    return result


def actor_letter(actor):
    return actor.removeprefix("member_").upper()


def status_cell(row):
    boundary = row["runtime"]["boundary"] or {}
    labels = []
    for actor, detail in boundary.get("terminal_details", {}).items():
        labels.append(actor_letter(actor) + ":" + detail.get("cause", detail.get("status", "?")))
    return "; ".join(labels)


def render(report):
    lines = ["# v0.38 阶段 A：已有 32 条经历的组织行为复核", "",
        "日期：2026-10-09。仅复核已结束的 P2 16 条与共同 B 开发 16 条；"
        "没有调用模型、使用 GPU、重跑测试或验收，也没有读取 TextFSM 确认池。"
        "本表描述旧 v0.36 运行，不是新 O1/O2/O3 实验结果。", "",
        "机器明细：[software-organization-v038-prior-audit.json](software-organization-v038-prior-audit.json)。"
        "每槽保留原文件 SHA256；开发数据以 `development-original.tar.gz::slot-n/…` 定位。"
        "归档只顺序读取一次，被抽取成员逐项与既有归档回执核对，不重复整包校验。", "",
        "## 行为表", "",
        "C/K/R/D 分别为成功创建、认领、修订、直接转交次数；M/V 为已送达工作事件／"
        "在收件人实际 selected input 中出现的事件数；I 为显式整合数。重叠编辑按生产文件计数，"
        "不称为浪费。P2 为同一 SQL root，开发四 root 以 job/command/room/order 缩写。", "",
        "| 槽 | root | R/提交 | C/K/R/D | 编辑→建任务 | 重叠生产路径 | M/V | I | 终态原因 A/B |",
        "|---|---|---|---|---|---:|---|---:|---|"]
    for r in report["rows"]:
        c = r["event_counts"]
        root = r["case_id"].replace("sc-", "").replace("-v035", "").replace("-v036", "")
        if r["panel"] == "P2":
            root = "SQL inventory"
        counts = "/".join(str(c.get(k, 0)) for k in ("task_created", "claim", "task_revised", "delegate"))
        timing = f"W{r['first_edit_sequence']}→W{r['first_create_sequence']}" if r["first_create_sequence"] else "无登记"
        visibility = r["message_visibility"]
        mv = f"{len(visibility)}/{sum(v['first_selected_input'] is not None for v in visibility)}"
        prefix = "P2" if r["panel"] == "P2" else "B"
        lines.append(f"| {prefix}-{r['slot']:02d} | {root} | {r['R']}/{int(bool(r['submitted']))} | {counts} | "
                     f"{timing} | {len(r['overlapping_production_edit_paths'])} | {mv} | {c.get('integrate', 0)} | {status_cell(r)} |")
    lines += ["", "## 汇总与真实语义", ""]
    for panel, agg in report["aggregate"].items():
        lines.append(f"- **{panel}**：提交 {agg['submitted']}/16，R=1 为 {agg['successes']}/16；"
            f"{agg['slots_with_task_creation']} 槽建过任务，其中 {agg['slots_edited_before_task_creation']} 槽先编辑后登记；"
            f"{agg['slots_both_edited_production_paths']} 槽双方编辑同一生产路径。"
            f"定向工作事件 {agg['addressed_work_events']} 条，实际收件输入证据覆盖 "
            f"{agg['addressed_events_seen_in_recipient_selected_input']} 条。")
    lines += ["", "`claim_task` 是成员主动接受无人负责的任务；旧 `delegate_task` 则直接改 owner 并通知，"
        "不是“先提议、后接受”，接收者只能随后 `return_task`。本批成功转交、退回、修订和依赖调整次数见机器表，"
        "不能以接口存在代替使用证据。普通工作消息没有形式化请求完成状态。", "",
        "编辑与测试不需要建任务；`fix_patch` 却要求关联本人负责任务，"
        "所以后置建任务可能与发布手续有关，但本复核不替模型推断动机。"
        "正式 owner 不切分私有文件编辑权限；同范围的实现和测试可以重叠。", "",
        "整合之后的测试与提交已逐一连接到原版本。整合 ID 出现在提交中不证明最终保留了有效伙伴代码，"
        "更不证明因果必要性；本次不重算旧 Mapper。公开测试是否执行、是否通过、是否为终态版本分别记录。", "",
        "## 11 条开发未提交的可观察断点", "",
        "下表 T/F/S 是实际测试执行／成功固定／成功提交次数；世界工具拒绝单列，格式拒绝另存机器记录。"
        "“当前测试”只说明已有最后测试对应终态可变版本，不对未提交代码补验。"
        "预算终止依据运行器原记录，不从接近 50 万 token 推断唯一原因。", "",
        "| 槽/root | T/F/S（拒绝 F/S） | A 终态版本／最后测试 | B 终态版本／最后测试 | 原终止证据 |",
        "|---|---|---|---|---|"]
    for r in report["rows"]:
        if r["panel"] != "B-development" or r["submitted"]:
            continue
        cells = []
        for actor in MEMBERS:
            member = r["members"][actor]
            test = member["last_test"]
            groups = test["groups"] if test else {}
            public = groups.get("public_normal", {})
            cells.append(f"{member['current_workspace']['version_id']} / " + ("未测试" if test is None else
                f"W{test['sequence']} {test['source_reference']['version_id']} public={public.get('passed')} "
                + ("当前" if member["last_test_is_current_version"] else "旧版")))
        counts = r["event_counts"]
        rejected = Counter(a["action"] for a in r["attempts"] if a["ok"] is False)
        tfs = "/".join(str(counts.get(k, 0)) for k in ("test", "patch_fixed", "submit"))
        lines.append(f"| B-{r['slot']:02d} {r['case_id']} | {tfs}（{rejected['fix_patch']}/{rejected['submit_integration']}） | "
                     f"{cells[0]} | {cells[1]} | {status_cell(r)} |")
    lines += ["", "11 条未提交中，10 条没有成功固定补丁；B-12 是唯一已固定仍未提交的槽。"
        "A 在 W24 对 v4 的公开测试已通过，随后将 `root_goal` 当执行任务发布，被 `Unknown task` 拒绝；"
        "再创建、认领 `complete_validation` 并固定成功，下一机会因团队剩余 token 无法覆盖预留而终止。"
        "其间 B 仍在修复；没有实际 submit_integration 调用。不能把这一槽说成验收失败。", "",
        "其余 10 槽，两成员各自最后已有公开测试都未通过（B-10 的 A 没有测试）；"
        "部分成员最后一次修改还晚于最后一次测试。"
        "11 槽均有成员被团队 token 预留边界停止，此外 B-05 的 A 先触及 context_capacity，"
        "B-10 的 A 处于等待、终态没有可达唤醒事件。"
        "这些是多种并存的断点，不能简化为“只差预算”，也不能替未提交终态下隐藏正确性结论。", "",
        "另一个上下文停止发生于成功槽 B-08 的 B；A 继续并完成固定提交。"
        "两个停止都在生成前发生，不能把预备好的 selected request 当成实际调用；"
        "本表可见性只纳入已实际启动并记账的生成，绑定团队账本中的 selected-request/input-ID hash。", "",
        "## 收件可见、结束与未闭合责任", "",
        "两个工作请求均来自 P2，且均确实进入收件人的生成输入。P2-08：B 的 W23 请求 A 实现、测试、提交，"
        "A 后续 W24/29/32/35 测试及 W31/33 编辑，最终没有固定提交；"
        "P2-13：A 的 W14 请求 B 发布，B 随后 W16 测试、W17 固定、W19 提交。"
        "后者在收到请求前已于 W11 认领任务，不能把文字中的“请认领”当成新责任已经转移。", "",
        "P2 有 14 槽在一方 done 后另一方仍获得机会，其中 5 槽另一方随后又提交；"
        "B 开发有 4 槽如此继续，但没有后续新提交。最后固定交付在双方最后实际输入中都出现的槽为 "
        "P2 9/14 个已提交槽、B 开发 4/5 个已提交槽；可见不等于双方协商认可。"
        "P2 的 4 次 wait 分布于槽 06/08/13（槽 13 两人各一次），B 的唯一 wait 在槽 10。", "",
        "JSON 的 `message_visibility` 区分发送落库、收件人精确 selected input 和后续行为。"
        "后续行为仅是时间关联，不能自动认定为理解或因果响应。`members.last_selected_observation` "
        "列出成员最后实际输入看到的交付、任务和人员状态；`other_member_actions_after_stop` "
        "保留另一方后续工作，避免把一人 staff_done 当成团队协调结束。", "",
        "旧任务记录没有 completed 字段；终态保留 owner 不等于该责任确实未完成。"
        "本复核保留所有终态任务、固定补丁及交付关联，同时明确：自由文本请求缺少确认／关闭协议，"
        "不能可靠自动判定所有请求均已履行。没有消息或双方分别 done，也不能据此称为已经协调过结束。", "",
        "## 对新入口的直接约束", "",
        "1. 明确区分主动认领、提议转交、接收责任和退回；记录修订前后及真正接受者。",
        "2. 不把任务板变成发布手续负担；集中完成与不建复杂图的合法路径仍可运行。",
        "3. 新成员、等待和退出共用预算；退出不删除 owner、请求、固定产物或版本历史。",
        "4. 维持精确 selected input 留档，分别统计事件已送达、已呈现和之后实际动作。",
        "5. 保留当前版本测试与固定提交要求，同时记录拒绝；不要把公开测试通过自动变成提交或验收。",
        "6. 保持终态最后固定交付口径；不因首个交付后仍有工作而强制提前停止。", "",
        "复现：`python scripts/audit_software_organization_v038.py`。此命令只读取上述 P2 / B 开发数据，"
        "只覆盖本报告及对应 JSON，不启动模型、GPU、验收或训练。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "runs/software-support-v036")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/experiments/software-organization-v038-prior-audit.json")
    args = parser.parse_args()
    slots, archive = load_inputs(args.data_root.resolve())
    rows = [summarize(panel, index, slots[(panel, index)]) for panel in ("P2", "B-development") for index in range(16)]
    if len(rows) != 32 or sum(r["submitted"] for r in rows) != 19 or sum(r["R"] for r in rows) != 19:
        raise ValueError("Unexpected original episode counts or outcomes")
    report = {"version": "software-organization-prior-audit-v0.38", "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "32 original completed episodes only; no mutable workspace acceptance, no new model/GPU calls, no TextFSM confirmation access",
        "model_calls": 0, "gpu_used": False, "new_test_or_acceptance_executions": 0,
        "archive": archive, "aggregate": aggregate(rows), "rows": rows,
        "semantics_sources": [bound(ROOT / name) for name in (
            "src/proworksim/software_collaboration_v028.py", "src/proworksim/software_collaboration_v030.py")],
        "extractor": bound(Path(__file__).resolve())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(render(report))
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
