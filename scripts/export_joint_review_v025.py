"""Read-only human review export of the sixteen original v025 joint episodes.

No model, scorer or world replay. Request messages/tools are content-addressed
for size, and reconstructed verbatim per original role/call. Numeric token/logp
arrays remain in the source records; human-facing output keeps their counts.
"""

import argparse
from collections import Counter
import copy
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import zipfile

from proworksim.storage import digest, json_bytes, read_json

VERSION = "v025-joint-experience-human-review-v1"
ROLES = {"provider": "资料提供者", "implementer": "实现者", "reviewer": "复核者"}
TASKS = {"joint_a": "A · 依据交接与新交付", "joint_b": "B · 错误初稿复核与修复"}
ACTIONS = {
    "read_alias": "读取别名",
    "read_version": "读取确切版本",
    "read_object": "读取对象",
    "read_messages": "读取消息",
    "request_information": "请求信息",
    "handoff_information": "交接信息",
    "adopt": "采用版本",
    "edit_artifact": "编辑产物",
    "adopt_version": "采用版本",
    "adopt_reference": "采用引用",
    "write_object": "写入对象",
    "sql_build": "执行SQL构建",
    "inspect_submission": "检查固定提交",
    "preflight_submission": "提交前结构检查",
    "submit": "固定提交",
    "approve": "核准",
    "raise_issue": "提出问题",
    "withdraw": "撤回提交",
    "respond_issue": "回应问题",
    "decide_issue": "判定问题回应",
    "staff_wait": "等待",
    "staff_done": "结束自身工作",
}
BOOL = {True: "是", False: "否", None: "未知"}


def ref(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def short_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def pretty(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def put(bank, value):
    key = digest(json_bytes(value))
    bank.setdefault(key, copy.deepcopy(value))
    return key


def pack_input(bank, request):
    if request is None:
        return None
    return {
        "metadata": {
            k: copy.deepcopy(v) for k, v in request.items() if k not in {"messages", "tools"}
        },
        "key_order": list(request),
        "messages_present": "messages" in request,
        "tools_present": "tools" in request,
        "messages_refs": [put(bank, message) for message in request.get("messages", [])],
        "tools_ref": put(bank, request["tools"]) if "tools" in request else None,
    }


def reconstruct_input(review, decision):
    packed = decision["input"]
    if packed is None:
        return None
    result = copy.deepcopy(packed["metadata"])
    if packed["messages_present"]:
        result["messages"] = [
            copy.deepcopy(review["payloads"][key]) for key in packed["messages_refs"]
        ]
    if packed["tools_present"]:
        result["tools"] = copy.deepcopy(review["payloads"][packed["tools_ref"]])
    return {key: result[key] for key in packed["key_order"]}


def extract_review(rollout, projection, slot, *, preparation=None, snapshots=None, sources=None):
    bank, decisions = {}, []
    events = rollout.get("events", [])
    boundaries = [copy.deepcopy(e) for e in events if e["kind"] == "model_boundary_error"]
    all_actions = [e for e in events if e["kind"] == "tool_call"]
    starts, actions_by_call, bounds_by_call = {}, {}, {}
    for e in events:
        if e["kind"] not in {"model_call", "tool_call", "model_boundary_error"}:
            continue
        payload = e["payload"]
        role = e.get("worker_id", payload.get("worker_id"))
        call = payload.get("model_call_id", payload.get("call_id", payload.get("decision_id")))
        key = (role, call)
        if e["kind"] == "model_call" and payload.get("stage") == "started":
            if key in starts:
                raise ValueError("Duplicate role/call start identity")
            starts[key] = e
        elif e["kind"] == "tool_call":
            actions_by_call.setdefault(key, []).append(e)
        elif e["kind"] == "model_boundary_error" and call is not None:
            bounds_by_call.setdefault(key, []).append(e)
    for role, view in projection.get("member_views", {}).items():
        for source_index, d in enumerate(view["decisions"]):
            key = (role, d["call_id"])
            start = starts.get(key)
            if start is None:
                raise ValueError("A member decision needs its actual joint model_call start")
            actions = actions_by_call.get(key, [])
            if [e["payload"] for e in actions] != d.get("world_actions", []):
                raise ValueError("Member/world tool payloads differ: do not fabricate a timeline")
            actual_input, response = d.get("actual_input"), d.get("actual_response")
            if d.get("input_sha256") and digest(json_bytes(actual_input)) != d["input_sha256"]:
                raise ValueError("Original input digest mismatch")
            if (
                response is not None
                and d.get("response_sha256")
                and digest(json_bytes(response)) != d["response_sha256"]
            ):
                raise ValueError("Original response digest mismatch")
            choice = (response.get("choices") or [{}])[0] if response else {}
            tokens = d.get("tokens") or {}
            generated = response is not None
            item = {
                "member_id": role,
                "call_id": d["call_id"],
                "decision_index": d.get("decision_index"),
                "sequence": start["sequence"],
                "input_event_sequence": d.get("input_event_sequence"),
                "response_event_sequence": d.get("response_event_sequence"),
                "generation_status": d.get("generation_status"),
                "generated": generated,
                "actor_required": d.get("actor_required"),
                "actor_trainable": d.get("actor_trainable"),
                "input": pack_input(bank, actual_input),
                "response": {
                    "assistant_message": copy.deepcopy(choice.get("message")),
                    "raw_generated_text": response.get("raw_generated_text"),
                    "finish_reason": choice.get("finish_reason"),
                    "protocol_parse_error": response.get("protocol_parse_error"),
                    "usage": copy.deepcopy(response.get("usage")),
                    "error": copy.deepcopy(response.get("error")),
                }
                if response
                else None,
                "non_generation_response": copy.deepcopy(d.get("non_generation_response")),
                "actions": copy.deepcopy(actions),
                "boundary_events": copy.deepcopy(bounds_by_call.get(key, [])),
                "diagnostics": copy.deepcopy(d.get("diagnostics", [])),
                "token_counts": {
                    "input": len(tokens["input_ids"]) if "input_ids" in tokens else None,
                    "output": len(tokens.get("output_ids", [])),
                    "reported_prompt_tokens": (d.get("non_generation_response") or {})
                    .get("body", {})
                    .get("error", {})
                    .get("prompt_tokens"),
                    "reported_prompt_tokens_source": "non_generation_response.body.error.prompt_tokens",
                },
                "source_pointer": "projection.json#/member_views/"
                + role
                + "/decisions/"
                + str(source_index),
                "input_sha256": d.get("input_sha256"),
                "response_sha256": d.get("response_sha256"),
            }
            decisions.append(item)
    decisions.sort(key=lambda d: d["sequence"])
    if len(decisions) != len(starts) or len(
        {(d["member_id"], d["call_id"]) for d in decisions}
    ) != len(decisions):
        raise ValueError("Every started request must be represented exactly once")
    if sorted(e["sequence"] for d in decisions for e in d["actions"]) != sorted(
        e["sequence"] for e in all_actions
    ):
        raise ValueError("A real world action was dropped or duplicated")
    manifest = rollout.get("manifest", {})
    reward = copy.deepcopy(rollout.get("reward_eligibility", {}))
    assessment = copy.deepcopy(projection.get("assessment", {}))
    if assessment and (
        assessment.get("reward") != reward.get("reward")
        or assessment.get("completed") != reward.get("completed")
    ):
        raise ValueError("Saved outcome summaries disagree")
    result = {
        "version": VERSION,
        "slot": copy.deepcopy(slot),
        "episode_id": rollout.get("rollout_id"),
        "window": copy.deepcopy(rollout.get("window", {})),
        "members": copy.deepcopy(rollout.get("members", {})),
        "case": copy.deepcopy(
            manifest.get("scenario", {}).get("variation", {}).get("online_case", {})
        ),
        "public_requirement": reward.get("spec", {}).get("public_requirement"),
        "outcome": {
            k: reward.get(k)
            for k in (
                "eligible",
                "reward",
                "completed",
                "components",
                "independent_assessability",
                "record_trust",
                "exclusions",
            )
        },
        "work_validity": copy.deepcopy(projection.get("work_validity", {})),
        "method_mapping": copy.deepcopy(projection.get("method_mapping", {})),
        "assessment": assessment,
        "termination": {
            k: copy.deepcopy(manifest.get("termination", {}).get(k))
            for k in (
                "status",
                "kind",
                "role_stops",
                "opportunities",
                "actions",
                "continuation",
                "bootstrap",
                "scope",
            )
        },
        "preparation": {
            k: copy.deepcopy((preparation or {}).get(k))
            for k in (
                "version",
                "origin",
                "credited_to_current_actor",
                "case_id",
                "prepared_business_state_sha256",
                "prepared_business_state_hash_format",
            )
        },
        "fixed_deliveries": copy.deepcopy(manifest.get("fixed_deliveries", {})),
        "decisions": decisions,
        "boundary_events": boundaries,
        "environment_events": [
            copy.deepcopy(e) for e in events if e["kind"] == "environment_event"
        ],
        "controller_events": [copy.deepcopy(e) for e in events if e["kind"] == "controller_action"],
        "control_events": [copy.deepcopy(e) for e in events if e["kind"] == "model_control"],
        "format_feedback_events": [
            copy.deepcopy(e) for e in events if e["kind"] == "model_format_feedback"
        ],
        "source_event_counts": dict(Counter(e["kind"] for e in events)),
        "snapshots": snapshots or {},
        "source_references": sources or {},
        "payloads": bank,
        "scope": "Reviewer global timeline. Each decision retains its exact actual local request independently. Chinese labels/notes are editorial; outputs/actions/results are original. No scoring/replay/model execution. Token/logprob numeric arrays remain in the SHA-linked original source; their counts only are exported.",
    }
    for role, view in projection.get("member_views", {}).items():
        by_call = {d["call_id"]: d for d in decisions if d["member_id"] == role}
        for original in view["decisions"]:
            if reconstruct_input(result, by_call[original["call_id"]]) != original.get(
                "actual_input"
            ):
                raise ValueError("Content-addressing changed a role-local request")
            if (
                original.get("input_sha256")
                and digest(json_bytes(reconstruct_input(result, by_call[original["call_id"]])))
                != original["input_sha256"]
            ):
                raise ValueError("Reconstructed request changed original serialized SHA")
    result["coverage"] = {
        "started_requests": len(decisions),
        "actual_generations": sum(d["generated"] for d in decisions),
        "non_generation_requests": sum(not d["generated"] for d in decisions),
        "world_actions": len(all_actions),
        "world_action_ok": sum(e["payload"]["response"].get("ok") is True for e in all_actions),
        "world_action_rejected": sum(
            e["payload"]["response"].get("ok") is False for e in all_actions
        ),
        "format_feedback_events": len(result["format_feedback_events"]),
        "model_control_events": len(result["control_events"]),
        "boundary_errors": len(boundaries),
        "unlinked_boundary_errors": sum(not e["payload"].get("model_call_id") for e in boundaries),
        "parse_errors": sum(
            bool(d["response"] and d["response"].get("protocol_parse_error")) for d in decisions
        ),
        "all_actual_requests_reconstructed_exactly": True,
        "all_world_actions_linked_exactly": True,
        "numeric_token_arrays_included": False,
    }
    return result


def load_snapshots(folder, manifest):
    result, artifacts = {}, {}
    for phase in ("start", "end"):
        spec = manifest[phase]
        base = folder / "episode" / spec["path"]
        state_path = base / spec["state"]["path"]
        if digest(state_path.read_bytes()) != spec["state"]["sha256"]:
            raise ValueError("Captured state digest changed")
        state = read_json(state_path)
        result[phase] = {
            "state_reference": ref(state_path),
            "state": {
                k: copy.deepcopy(state.get(k))
                for k in (
                    "clock",
                    "state_revision",
                    "adoptions",
                    "requests",
                    "handoffs",
                    "issues",
                    "issue_responses",
                    "issue_decisions",
                    "blockers",
                    "work_items",
                )
            },
            "object_permissions": [
                {
                    k: copy.deepcopy(obj.get(k))
                    for k in (
                        "object_id",
                        "alias",
                        "current_version",
                        "owner",
                        "readers",
                        "writers",
                        "version_readers",
                    )
                }
                for obj in state["artifacts"].values()
            ],
        }
        for item in spec["files"]:
            if item.get("availability") != "available":
                raise ValueError("Do not silently skip unavailable captured object bytes")
            path = base / item["path"]
            if digest(path.read_bytes()) != item["sha256"]:
                raise ValueError("Captured object version changed")
            key = (item["object_id"], item["version_id"], item["sha256"])
            if key not in artifacts:
                artifacts[key] = {
                    "object_id": item["object_id"],
                    "version_id": item["version_id"],
                    "alias": state["artifacts"][item["object_id"]]["alias"],
                    "sha256": item["sha256"],
                    "phases": [],
                    "source_references": [],
                    "content": read_json(path),
                }
            artifacts[key]["phases"].append(phase)
            artifacts[key]["source_references"].append(ref(path))
    result["artifacts"] = list(artifacts.values())
    return result


def collect_episode(folder, slot):
    folder = Path(folder)
    paths = {
        "rollout": folder / "team-rollout.json",
        "projection": folder / "projection.json",
        "manifest": folder / "episode/manifest.json",
        "preparation": folder / "preparation.json",
    }
    rollout, projection = read_json(paths["rollout"]), read_json(paths["projection"])
    manifest = read_json(paths["manifest"])
    if rollout["manifest"] != manifest or rollout["manifest_sha256"] != digest(
        paths["manifest"].read_bytes()
    ):
        raise ValueError("Joint rollout differs from the captured original episode")
    if slot["case_id"] != projection["assessment"]["case_id"]:
        raise ValueError("Slot case differs from saved assessment")
    return extract_review(
        rollout,
        projection,
        slot,
        preparation=read_json(paths["preparation"]),
        snapshots=load_snapshots(folder, manifest),
        sources={key: ref(path) for key, path in paths.items()},
    )


def esc(value):
    return html.escape(str(value), quote=True)


def fenced(value, language="json"):
    text = value if isinstance(value, str) else pretty(value)
    runs = [len(s) for s in re.findall(r"`+", text)]
    fence = "`" * max(3, max(runs, default=0) + 1)
    return fence + language + "\n" + text + "\n" + fence + "\n"


def pre(value):
    return "<pre>" + esc(value if isinstance(value, str) else pretty(value)) + "</pre>"


def detail(title, value, *, opened=False):
    return (
        "<details"
        + (" open" if opened else "")
        + "><summary>"
        + esc(title)
        + "</summary>"
        + pre(value)
        + "</details>"
    )


def flag(value):
    return BOOL.get(value, "未知")


def action_title(event):
    p = event["payload"]
    name = p["action"]
    ok = p.get("response", {}).get("ok")
    return f"#{event['sequence']} {ACTIONS.get(name, name)} · {name} · 工具ok={str(ok).lower()}"


def response_excerpt(event):
    response = event["payload"].get("response", {})
    if response.get("ok") is False:
        return pretty(response.get("error", response))
    result = response.get("result", {})
    if isinstance(result, dict):
        chosen = {
            k: result[k]
            for k in (
                "reference",
                "submission_id",
                "issue_id",
                "request_id",
                "handoff_id",
                "status",
                "passed",
                "version_id",
            )
            if k in result
        }
        return pretty(chosen) if chosen else "返回字段：" + ", ".join(result)
    return str(result)


def collaboration_graph(review):
    """Only observed cross-member relations; endpoints come from recorded evidence."""
    members = list(review["members"])
    state = review.get("snapshots", {}).get("end", {}).get("state", {})
    requests, handoffs = state.get("requests", {}), state.get("handoffs", {})
    issues, works = state.get("issues", {}), state.get("work_items", {})
    relevant = {
        "request_information",
        "handoff_information",
        "inspect_submission",
        "raise_issue",
        "approve",
        "respond_issue",
        "decide_issue",
    }
    edges, unlinked = [], []
    for decision in review["decisions"]:
        routes = []
        for key in (decision.get("input") or {}).get("messages_refs", []):
            message = review["payloads"][key]
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                try:
                    content = json.loads(message["content"])
                except ValueError:
                    continue
                if isinstance(content, dict) and isinstance(content.get("observation"), dict):
                    routes = content["observation"].get("information_routes", [])
        for event in decision["actions"]:
            payload = event["payload"]
            action = payload["action"]
            if action not in relevant:
                continue
            source = event.get("worker_id", decision["member_id"])
            args, response = payload.get("arguments", {}), payload["response"]
            result = response.get("result") or {}
            ok = response.get("ok") is True
            work = works.get(args.get("work_id"), {})
            route = next(
                (
                    r
                    for r in routes
                    if r.get("route_id") == args.get("route_id")
                    and r.get("work_id") == args.get("work_id")
                ),
                {},
            )
            targets, evidence, detail_text = [], "", ""
            label = ACTIONS.get(action, action)
            if action == "request_information":
                rid = result.get("request_id")
                target = requests.get(rid, {}).get("requested_role") or route.get("provider")
                targets = [target]
                evidence = "request record / actual input information_routes.provider"
                detail_text = f"请求 {rid}" if rid else "尝试请求"
            elif action == "handoff_information":
                record = handoffs.get(result.get("handoff_id"), {})
                targets = record.get("recipients") or route.get("recipients", [])
                evidence = "handoff record / actual input information_routes.recipients"
                rid = result.get("request_id", args.get("request_id"))
                detail_text = f"绑定请求 {rid}" if rid else "未绑定请求"
                if result.get("created") is False:
                    detail_text += "；幂等重试，未新增交接"
            elif action in {"inspect_submission", "raise_issue", "approve"}:
                targets = [result.get("actor_id") or work.get("owner_role")]
                evidence = "tool result actor_id / captured work_items.owner_role"
                sid = result.get("submission_id") or args.get("submission_id", "")
                detail_text = str(sid)
                if action == "inspect_submission":
                    label = "读取对方固定提交"
                elif action == "raise_issue":
                    label = "登记问题"
                    if result.get("active_at_creation") is False:
                        detail_text += "；创建时已非当前提交"
                else:
                    label = "登记核准"
            elif action == "respond_issue":
                issue = issues.get(args.get("issue_id"), {})
                targets = [issue.get("raised_by")]
                evidence = "captured issue.raised_by"
                detail_text = str(args.get("issue_id", ""))
            elif action == "decide_issue":
                issue = issues.get(args.get("issue_id"), {})
                targets = [works.get(issue.get("work_id"), {}).get("owner_role")]
                evidence = "captured issue.work_id / work_items.owner_role"
                detail_text = str(args.get("issue_id", ""))
            cross_targets = [target for target in targets if target in members and target != source]
            if not cross_targets:
                if not ok and action != "inspect_submission":
                    unlinked.append(
                        {
                            "sequence": event["sequence"],
                            "action": action,
                            "reason": "被拒绝；对象为自身或无法从记录确定另一成员，未绘制连线",
                        }
                    )
                continue
            for target in cross_targets:
                edges.append(
                    {
                        "sequence": event["sequence"],
                        "source": source,
                        "target": target,
                        "action": action,
                        "label": label,
                        "detail": detail_text,
                        "ok": ok,
                        "endpoint_evidence": evidence,
                    }
                )
    return {
        "nodes": [{"id": role, "label": ROLES.get(role, role)} for role in members],
        "edges": sorted(edges, key=lambda e: e["sequence"]),
        "unlinked_attempts": sorted(unlinked, key=lambda e: e["sequence"]),
        "direction": "动作发起成员 → 协作对象；从上到下按原事件顺序。箭头不表示对方已读或已处理，工具已记录也不等于业务正确。",
    }


def collaboration_svg(review, *, standalone=False):
    graph = review.get("collaboration_graph") or collaboration_graph(review)
    nodes, edges = graph["nodes"], graph["edges"]
    width = 840
    height = 180 + max(len(edges), 1) * 92
    xs = {node["id"]: 150 + i * 540 / max(len(nodes) - 1, 1) for i, node in enumerate(nodes)}
    prefix = f"../episodes/{review['slot']['slot_id']}.html" if standalone else ""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" class="collaboration-diagram" role="img" aria-labelledby="collab-title collab-desc">',
        '<title id="collab-title">成员协作有向图</title>',
        '<desc id="collab-desc">' + esc(graph["direction"]) + "</desc>",
        '<defs><marker id="collab-ok" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#256fa8"/></marker><marker id="collab-rejected" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#b65440"/></marker></defs>',
        '<rect width="100%" height="100%" rx="8" fill="#ffffff"/>',
        '<g font-family="system-ui, sans-serif" text-anchor="middle">',
    ]
    colors = {"provider": "#9c751e", "implementer": "#256fa8", "reviewer": "#855ca2"}
    for node in nodes:
        x = xs[node["id"]]
        color = colors.get(node["id"], "#526579")
        parts += [
            f'<line x1="{x}" x2="{x}" y1="78" y2="{height - 64}" stroke="#cfdae5" stroke-dasharray="4 5"/>',
            f'<rect x="{x - 88}" y="18" width="176" height="60" rx="10" fill="#f4f7fb" stroke="{color}"/>',
            f'<text x="{x}" y="44" fill="{color}" font-size="17" font-weight="600">{esc(node["label"])}</text>',
            f'<text x="{x}" y="64" fill="#637486" font-size="12">{esc(node["id"])}</text>',
        ]
    for index, edge in enumerate(edges):
        y = 132 + 92 * index
        x1, x2 = xs[edge["source"]], xs[edge["target"]]
        mid = (x1 + x2) / 2
        status = "ok" if edge["ok"] else "rejected"
        color = "#256fa8" if edge["ok"] else "#b65440"
        dash = "" if edge["ok"] else ' stroke-dasharray="7 5"'
        caption = f"#{edge['sequence']} {edge['label']}" + ("" if edge["ok"] else " · 被拒绝")
        parts += [
            f'<a href="{esc(prefix)}#seq-{edge["sequence"]}" data-event-sequence="{edge["sequence"]}">',
            "<title>"
            + esc(
                f"{ROLES.get(edge['source'], edge['source'])} → {ROLES.get(edge['target'], edge['target'])}：{caption}；{edge['detail']}"
            )
            + "</title>",
            f'<rect x="{min(x1, x2) + 8}" y="{y - 37}" width="{abs(x2 - x1) - 16}" height="73" rx="6" fill="#f7f9fc"/>',
            f'<text x="{mid}" y="{y - 14}" fill="{color}" font-size="16">{esc(caption)}</text>',
            f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="2"{dash} marker-end="url(#collab-{status})"/>',
            f'<circle cx="{x1}" cy="{y}" r="4" fill="{color}"/>',
            f'<text x="{mid}" y="{y + 24}" fill="#526579" font-size="12">{esc(edge["detail"])}</text></a>',
        ]
    if not edges:
        parts.append(
            '<text x="420" y="142" fill="#526579" font-size="16">未记录可确认的跨成员协作动作</text>'
        )
    parts += [
        f'<text x="420" y="{height - 39}" fill="#526579" font-size="12">从上到下：原事件顺序 · 箭头：动作发起者 → 协作对象</text>',
        f'<text x="420" y="{height - 18}" fill="#526579" font-size="12">实线：工具已记录；虚线：尝试被拒绝 · 点击事件查看原记录</text>',
        "</g></svg>",
    ]
    return "".join(parts)


def collaboration_html(review):
    graph = review.get("collaboration_graph") or collaboration_graph(review)
    sid = review["slot"]["slot_id"]
    output = (
        '<section class="panel" id="collaboration"><h2>成员协作有向图</h2><p class="small">'
        + esc(graph["direction"])
        + '</p><div class="scroll">'
        + collaboration_svg(review)
        + "</div>"
    )
    for attempt in graph["unlinked_attempts"]:
        output += f'<p class="small"><a href="#seq-{attempt["sequence"]}" data-event-sequence="{attempt["sequence"]}">#{attempt["sequence"]} {esc(ACTIONS.get(attempt["action"], attempt["action"]))}</a>：{esc(attempt["reason"])}</p>'
    return (
        output
        + '<p class="small"><a href="../graphs/'
        + esc(sid)
        + '.svg">单独打开图</a> · 个人读取、构建和提交等操作见下方完整时间线；继承的准备动作不画作本轮协作。</p></section>'
    )


CSS = """
:root{color-scheme:light;--ink:#172638;--muted:#526579;--line:#dbe3eb;--blue:#1263aa}
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans SC",sans-serif}
main{max-width:1220px;margin:auto;padding:32px 28px 70px}h1{font-size:30px;line-height:1.3;margin:12px 0}h2{font-size:21px;margin-top:28px}h3{font-size:17px}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}.eyebrow{font-size:12px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase}
.sub,.meta{color:var(--muted)}.meta{font-size:12px;overflow-wrap:anywhere}.notice{padding:12px 16px;background:#eaf1f9;border-left:4px solid #417cae;margin:18px 0}
.panel,.card{background:white;border:1px solid var(--line);border-radius:10px;padding:18px;margin:14px 0}.card{border-left:5px solid #8294a7;scroll-margin-top:85px}.card.provider{border-left-color:#b88921}.card.implementer{border-left-color:#2678b3}.card.reviewer{border-left-color:#8b5fa9}.card.boundary{border-left-color:#b65747}.card.environment{border-left-color:#24856c}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric{background:white;border:1px solid var(--line);padding:14px;border-radius:8px}.metric strong{display:block;font-size:26px}.metric span{color:var(--muted);font-size:13px}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;position:sticky;top:0;background:#f3f6faf5;z-index:4;padding:12px 0;border-bottom:1px solid var(--line)}input,select,button{font:inherit;padding:7px 10px;border:1px solid #bdcbd8;border-radius:6px;background:white}input:not([type=checkbox]){min-width:240px;flex:1}input[type=checkbox]{min-width:0;width:auto;flex:none}button{cursor:pointer;color:var(--blue)}label{font-size:13px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:#f5f7f9;padding:12px;border-radius:6px;font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:640px;overflow:auto}.assistant{font:15px/1.7 system-ui,sans-serif;background:#fafbfc;max-height:none}
code{font-family:ui-monospace,monospace;font-size:.9em}details{margin:9px 0}summary{cursor:pointer;color:#254e73;font-weight:550}details details{margin-left:10px}.badge{display:inline-block;font-size:12px;border-radius:5px;background:#eaf0f6;padding:3px 7px;margin-right:7px}.bad{background:#fbece8;color:#8e3d30}.good{background:#e7f3ee;color:#235c43}.scoring-hidden .outcome{display:none}.control-events{display:none}.show-controls .control-events{display:block}
.collaboration-diagram{display:block;width:100%;height:auto;min-width:600px;max-width:1000px;margin:auto}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;background:white;font-size:14px}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);white-space:nowrap}td code{white-space:nowrap}.jump{display:flex;gap:14px;flex-wrap:wrap}.toc{columns:2}.guide{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.guide a{display:block;background:white;border:1px solid var(--line);border-radius:8px;padding:16px}.no-match{display:none}.small{font-size:13px}.message-label{font-size:12px;color:var(--muted)}
@media(max-width:740px){main{padding:20px 14px}.metrics{grid-template-columns:repeat(2,1fr)}.guide{grid-template-columns:1fr}.toolbar{position:static}.toc{columns:1}h1{font-size:25px}}
@media print{body{background:white}.toolbar,.jump{display:none}main{max-width:none;padding:0}pre{max-height:none}.card{break-inside:avoid}.control-events{display:block}}
"""

JS = """
const q=(s)=>document.querySelector(s), all=(s)=>[...document.querySelectorAll(s)];
function filterCards(){let term=(q('#search')?.value||'').toLowerCase(),role=q('#role')?.value||'',kind=q('#kind')?.value||'';let n=0;
 all('.event-card').forEach(el=>{let ok=(!role||el.dataset.role===role||!el.dataset.role)&&(!kind||el.dataset.kind===kind)&&(!term||el.textContent.toLowerCase().includes(term));el.hidden=!ok;if(ok)n++});if(q('#shown'))q('#shown').textContent=n+' 个事件卡片';}
['search','role','kind'].forEach(id=>q('#'+id)?.addEventListener('input',filterCards));
q('#hide-scores')?.addEventListener('change',e=>document.body.classList.toggle('scoring-hidden',e.target.checked));
q('#show-controls')?.addEventListener('change',e=>document.body.classList.toggle('show-controls',e.target.checked));
q('#open-visible')?.addEventListener('click',()=>all('.event-card:not([hidden]) details').filter(x=>!x.closest('.context-body')).forEach(x=>x.open=true));
q('#close-all')?.addEventListener('click',()=>all('details').forEach(x=>x.open=false));
const raw=q('#review-data');
if(raw){const r=JSON.parse(raw.textContent);
 function pp(v){return typeof v==='string'?v:JSON.stringify(v,null,2)}
 function block(v){const p=document.createElement('pre');p.textContent=pp(v);return p;}
 function part(label,v,open=false){const d=document.createElement('details'),s=document.createElement('summary');s.textContent=label;d.append(s,block(v));d.open=open;return d;}
 all('details[data-request]').forEach(el=>el.addEventListener('toggle',()=>{if(!el.open||el.dataset.loaded)return;el.dataset.loaded='yes';const d=r.decisions[Number(el.dataset.request)],req=d.input,body=el.querySelector('.context-body');if(!req){body.textContent='原记录没有请求正文。';return;}
 body.append(part('请求参数（原值）',req.metadata));req.messages_refs.forEach((ref,i)=>{const m=r.payloads[ref];let c=m.content;let pretty=c;if(typeof c==='string'){try{pretty=JSON.parse(c)}catch{}}const label='消息 '+(i+1)+' · '+m.role+(m.name?' · '+m.name:'');const item=part(label,pretty,i===req.messages_refs.length-1);const extra=Object.fromEntries(Object.entries(m).filter(([k])=>k!=='content'));item.append(part('该消息完整字段（content原字符串保存在JSON）',extra));body.append(item)});
 if(req.tools_present)body.append(part('本次实际工具定义',r.payloads[req.tools_ref]));}));}
function filterRows(){const term=(q('#search-rows')?.value||'').toLowerCase(),task=q('#task-filter')?.value||'';all('tr[data-slot]').forEach(el=>el.hidden=(!el.textContent.toLowerCase().includes(term)||!!task&&el.dataset.task!==task));}
all('a[data-event-sequence]').forEach(el=>el.addEventListener('click',()=>{['search','role','kind'].forEach(id=>{if(q('#'+id))q('#'+id).value=''});filterCards();}));
q('#search-rows')?.addEventListener('input',filterRows);q('#task-filter')?.addEventListener('change',filterRows);
"""


def page(title, body, data=None):
    embedded = (
        ""
        if data is None
        else '<script type="application/json" id="review-data">'
        + short_json(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        + "</script>"
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + esc(title)
        + "</title><style>"
        + CSS
        + "</style></head><body><main>"
        + body
        + "</main>"
        + embedded
        + "<script>"
        + JS
        + "</script></body></html>"
    )


def render_episode_html(review):
    slot = review["slot"]
    sid = slot["slot_id"]
    outcome = review["outcome"]
    cov = review["coverage"]
    title = sid + " · " + TASKS.get(slot["task"], slot["task"])
    note = review.get("editorial_note", {})
    task_text = note.get("task_requirement_zh")
    requirement_html = (
        (
            "<p>"
            + esc(task_text)
            + "</p>"
            + detail("原任务要求（原文）", review.get("public_requirement"))
        )
        if task_text
        else ("<p>" + esc(review.get("public_requirement") or "") + "</p>")
    )
    parts = [
        '<nav class="jump"><a href="../index.html">← 全部16条</a><a href="'
        + esc(sid)
        + '.md">Markdown版</a><a href="../data/'
        + esc(sid)
        + '.json">结构化审阅数据</a></nav>',
        '<p class="eyebrow">ProWorkSim / joint experience review</p><h1>' + esc(title) + "</h1>",
        '<p class="sub">重复 '
        + str(slot.get("repeat_index", 0))
        + " · seed "
        + str(slot.get("seed"))
        + " · "
        + esc(" / ".join(ROLES.get(k, k) for k in review["members"]))
        + "</p>",
        '<div class="notice">这是人工审阅者的全局时间线。每张决定卡的“实际输入”严格对应当时该成员的局部请求；全局快照和原评分不表示模型当时可见。模型原话保留原文，中文标签与摘要为审阅辅助。</div>',
        '<section class="panel"><h2>任务与初始条件</h2>' + requirement_html,
        detail(
            "准备元数据与业务事实（审阅者可见，不注入模型）",
            {"case": review["case"], "preparation": review["preparation"]},
        ),
        "</section>",
        '<section class="panel outcome"><h2>原记录的结果</h2><p>完整职责：<b>'
        + flag(outcome.get("completed"))
        + "</b> · 回报：<b>"
        + esc(outcome.get("reward"))
        + "</b> · 重配有效性V：<b>"
        + flag(review["work_validity"].get("value"))
        + "</b> · 方法："
        + esc(review["method_mapping"].get("class_id") or review["method_mapping"].get("status"))
        + "</p>",
        '<p class="small">工具ok、完整职责、完整工作有效性、方法支持是不同字段；没有重新评分。</p>',
        detail("原奖励分项", outcome),
        detail("四维有效性与证据", review["work_validity"]),
        detail("方法映射及原原因", review["method_mapping"]),
        detail("独立评价事实", review["assessment"]),
        detail("终止边界", review["termination"]),
        "</section>",
        '<div class="metrics">'
        + "".join(
            '<div class="metric"><strong>' + str(value) + "</strong><span>" + name + "</span></div>"
            for name, value in [
                ("请求", cov["started_requests"]),
                ("实际生成", cov["actual_generations"]),
                ("世界动作", cov["world_actions"]),
                ("未生成请求", cov["non_generation_requests"]),
            ]
        )
        + "</div>",
        '<div class="toolbar"><input id="search" placeholder="搜索模型输出、动作或返回…"><select id="role"><option value="">全部成员</option>'
        + "".join(
            '<option value="' + esc(k) + '">' + ROLES.get(k, k) + "</option>"
            for k in review["members"]
        )
        + '</select><select id="kind"><option value="">全部事件</option><option value="decision">模型决定</option><option value="boundary">停止/边界</option><option value="environment">世界事件</option><option value="feedback">格式反馈</option><option value="control">成员等待/结束</option></select><label><input type="checkbox" id="hide-scores">隐藏原评分</label><button id="open-visible">展开当前卡片详情</button><button id="close-all">折叠详情</button><span id="shown" class="small"></span></div>',
        '<h2>联合时间线</h2><p class="small">按原model_call开始序号与业务事件序号排序。每个决定保留原调用ID，工具子项保留实际执行序号；未生成请求及发请求前预算停止单独保留。</p>',
    ]
    note = review.get("editorial_note")
    if note:
        note_html = (
            '<section class="panel outcome"><h2>中文阅读提示（事后摘要）</h2><h3>'
            + esc(note["title"])
            + "</h3><p>"
            + esc(note["summary"])
            + "</p>"
        )
        if note.get("review_focus"):
            note_html += "<p><b>审阅重点：</b>" + esc(note["review_focus"]) + "</p>"
        note_html += (
            "<p>重点事件："
            + " · ".join(
                '<a href="#seq-'
                + str(e["sequence"])
                + '">#'
                + str(e["sequence"])
                + " "
                + esc(ACTIONS.get(e.get("action"), e.get("action") or e["kind"]))
                + "</a>"
                for e in note["key_events"]
            )
            + "</p></section>"
        )
        parts.insert(4, note_html)
    parts.insert(4, collaboration_html(review))
    cards = []
    for index, d in enumerate(review["decisions"]):
        role = d["member_id"]
        res = d["response"] or {}
        msg = res.get("assistant_message") or {}
        badge = "实际生成" if d["generated"] else "未开始生成"
        card = (
            '<article class="card event-card '
            + esc(role)
            + '" data-kind="decision" data-role="'
            + esc(role)
            + '" id="seq-'
            + str(d["sequence"])
            + '"><span class="badge">#'
            + str(d["sequence"])
            + '</span><span class="badge">'
            + esc(ROLES.get(role, role))
            + '</span><span class="badge'
            + (" bad" if not d["generated"] else "")
            + '">'
            + badge
            + "</span><h3>成员决定 "
            + str(d["decision_index"])
            + "</h3>"
        )
        card += (
            '<p class="meta">'
            + esc(d["call_id"])
            + " · "
            + esc(d["generation_status"])
            + " · 输出token "
            + str(d["token_counts"]["output"])
            + "</p>"
        )
        if d["generated"]:
            content = msg.get("content")
            card += '<div class="message-label">模型可见回复正文（原文）</div>' + (
                '<pre class="assistant">' + esc(content) + "</pre>"
                if content
                else '<p class="small">正文为空；解析的工具提案与原始生成文本在下方保留。</p>'
            )
            if msg.get("tool_calls"):
                card += detail("模型提出的工具/控制调用", msg["tool_calls"])
            card += detail(
                "完整原始生成文本（包括native XML）", res.get("raw_generated_text") or ""
            )
            if res.get("protocol_parse_error"):
                card += detail("协议解析错误（原记录）", res["protocol_parse_error"], opened=True)
            card += '<p class="meta">finish_reason=' + esc(res.get("finish_reason")) + "</p>"
        else:
            card += "<p>该次请求没有生成输出，不计作一次生成决定或输出token。</p>" + detail(
                "原未生成返回/错误", d["non_generation_response"], opened=True
            )
        if d["actions"]:
            for action in d["actions"]:
                payload = action["payload"]
                card += (
                    '<section id="seq-'
                    + str(action["sequence"])
                    + '"><h3>'
                    + esc(action_title(action))
                    + "</h3>"
                )
                card += detail("实际执行参数", payload.get("arguments", {}), opened=True)
                card += '<div class="small">返回摘要（完整返回可展开）</div>' + pre(
                    response_excerpt(action)
                )
                card += detail("完整实际工具返回", payload.get("response")) + "</section>"
        else:
            card += '<p class="small">本决定没有实际世界工具执行；可能为控制输出、格式问题或未生成，详见原回复与边界。</p>'
        card += (
            '<details data-request="'
            + str(index)
            + '"><summary>本次实际输入 · '
            + str(len((d["input"] or {}).get("messages_refs", [])))
            + ' 条消息（完整、按该角色原顺序）</summary><div class="context-body"></div></details>'
        )
        card += (
            detail(
                "决定溯源与计数",
                {
                    k: d[k]
                    for k in (
                        "input_event_sequence",
                        "response_event_sequence",
                        "input_sha256",
                        "response_sha256",
                        "token_counts",
                        "source_pointer",
                        "diagnostics",
                    )
                },
            )
            + "</article>"
        )
        cards.append((d["sequence"], 0, card))
    for kind, key in [
        ("environment", "environment_events"),
        ("boundary", "boundary_events"),
        ("feedback", "format_feedback_events"),
        ("control", "control_events"),
    ]:
        for e in review[key]:
            role = e.get("worker_id", "")
            p = e["payload"]
            event_title = (
                {
                    "environment": "业务环境事件",
                    "boundary": "停止/边界",
                    "feedback": "运行时格式反馈",
                    "control": "成员等待或结束",
                }[kind]
                + " · "
                + str(p.get("status", p.get("kind", p.get("type", ""))))
            )
            card = (
                '<article class="card event-card '
                + kind
                + '" data-kind="'
                + kind
                + '" data-role="'
                + esc(role)
                + '" id="seq-'
                + str(e["sequence"])
                + '"><span class="badge">#'
                + str(e["sequence"])
                + "</span><h3>"
                + esc(ROLES.get(role, role) + " " + event_title)
                + "</h3>"
                + pre(p)
                + "</article>"
            )
            cards.append((e["sequence"], 1, card))
    parts += [card for _, _, card in sorted(cards)]
    parts += [
        '<section class="panel"><h2>世界快照与实际对象版本</h2><p class="small">全局审阅资料，不是任何单一成员的原输入。start/end表示episode边界，准备动作不计为本次模型成果。</p>'
    ]
    snapshots = review.get("snapshots", {})
    for phase in ("start", "end"):
        if phase in snapshots:
            parts.append(
                detail(
                    ("初始" if phase == "start" else "最终") + "世界状态及对象权限",
                    snapshots[phase],
                )
            )
    for obj in snapshots.get("artifacts", []):
        parts.append(
            detail(
                obj["alias"] + " @ " + obj["version_id"] + " · " + ",".join(obj["phases"]),
                obj["content"],
            )
        )
    parts += [
        '</section><section class="panel"><h2>完整性与原始来源</h2>',
        detail("逐项覆盖核对", cov),
        detail("原始文件SHA与位置", review["source_references"]),
        detail("控制器动作（原始调度/推进记录）", review["controller_events"]),
        detail("模型控制事件", review["control_events"]),
        detail("全部格式反馈", review["format_feedback_events"]),
        detail("所有原事件类型与数量", review["source_event_counts"]),
        '<p class="small">数值token ID/logprob数组没有铺进人工版，保留在SHA绑定的原projection/team-rollout文件。原始文本、每个请求的完整messages/tools、实际动作/返回及对象版本已包含在本审阅包。</p></section>',
    ]
    return page(
        title,
        "".join(parts),
        {
            "payloads": review["payloads"],
            "decisions": [{"input": d["input"]} for d in review["decisions"]],
        },
    )


def render_episode_markdown(review):
    sid = review["slot"]["slot_id"]
    out = review["outcome"]
    lines = [
        f"# {sid} · {TASKS.get(review['slot']['task'], review['slot']['task'])}",
        "",
        f"[交互HTML版]({sid}.html) · [全部16条](../README.md) · [完整结构化数据](../data/{sid}.json)",
        "",
        "> 审阅者全局视角。模型输出保持原文；各成员完整实际输入在HTML的请求详情和JSON中逐调用保留，不能从全局快照补入模型当时视野。数值token/logprob数组仅保留源引用。",
        "",
        "## 成员协作有向图",
        "",
        f"![成员协作有向图](../graphs/{sid}.svg)",
        "",
        "箭头为动作发起成员→协作对象，按原事件顺序向下排列。实线表示工具已记录，虚线表示尝试被拒；不代表对方已读或业务正确。个人操作及准备动作不连成成员关系。",
        "",
        f"[在交互页查看并定位事件]({sid}.html#collaboration) · [单独打开图](../graphs/{sid}.svg)",
        "",
        "## 任务及原结果",
        "",
        review.get("public_requirement") or "",
        "",
        f"完整职责：{flag(out.get('completed'))}；原回报：{out.get('reward')}；重配有效性V：{flag(review['work_validity'].get('value'))}；方法：{review['method_mapping'].get('class_id') or review['method_mapping'].get('status')}。",
        "",
        "| 维度 | 原判定 |",
        "|---|---|",
    ]
    lines += [
        f"| {name} | {flag(v.get('value'))} |"
        for name, v in review["work_validity"].get("components", {}).items()
    ]
    if review.get("editorial_note"):
        note = review["editorial_note"]
        lines += [
            "",
            "## 中文阅读提示（事后摘要）",
            "",
            note.get("task_requirement_zh", ""),
            "",
            note["title"],
            "",
            note["summary"],
            "",
            "审阅重点：" + note.get("review_focus", ""),
            "",
        ]
    lines += [
        "",
        "以下参数完整保留；工具返回仅作带标注的摘要，完整返回、原始XML、全部输入消息及对象文件在HTML/JSON中，不是再次评分。",
        "",
        "## 联合时间线",
        "",
    ]
    timeline = []
    for d in review["decisions"]:
        res = d["response"] or {}
        msg = res.get("assistant_message") or {}
        text = [
            f"### #{d['sequence']} {ROLES.get(d['member_id'], d['member_id'])} · 决定 {d['decision_index']}",
            "",
            f"调用 `{d['call_id']}`；{d['generation_status']}；输出token {d['token_counts']['output']}。",
            "",
        ]
        if d["generated"]:
            text += [
                "模型回复原文：",
                "",
                fenced(msg.get("content") or "（原正文为空；工具提案见下）", "text"),
            ]
            if msg.get("tool_calls"):
                text += ["工具/控制提案：", "", fenced(msg["tool_calls"])]
            if res.get("protocol_parse_error"):
                text += [
                    "协议解析错误：",
                    "",
                    fenced(res["protocol_parse_error"]),
                    "完整生成原文：",
                    "",
                    fenced(res.get("raw_generated_text") or "", "text"),
                ]
        else:
            text += ["本次没有生成输出；原返回：", "", fenced(d["non_generation_response"])]
        for event in d["actions"]:
            text += [
                f"**{action_title(event)}**",
                "",
                "执行参数：",
                "",
                fenced(event["payload"].get("arguments", {})),
                "工具返回摘要（完整返回见HTML/JSON）：",
                "",
                fenced(response_excerpt(event), "text"),
            ]
        if not d["actions"]:
            text += ["没有实际世界工具执行；控制输出、解析失败与未生成分别查看原记录。", ""]
        text += [
            f"原输入/回复序号：{d['input_event_sequence']}/{d['response_event_sequence']}；[在HTML定位](%s.html#seq-%s)。"
            % (sid, d["sequence"]),
            "",
        ]
        timeline.append((d["sequence"], 0, "\n".join(text)))
    for key, label in [
        ("environment_events", "业务环境事件"),
        ("boundary_events", "停止或边界"),
        ("format_feedback_events", "运行时格式反馈"),
        ("control_events", "成员等待或结束"),
    ]:
        for e in review[key]:
            timeline.append(
                (
                    e["sequence"],
                    1,
                    f"### #{e['sequence']} {label} · {ROLES.get(e.get('worker_id'), e.get('worker_id', ''))}\n\n"
                    + fenced(e["payload"]),
                )
            )
    lines += [text for _, _, text in sorted(timeline)]
    lines += [
        "",
        "## 终止、方法及源记录",
        "",
        fenced(review["termination"]),
        fenced(review["method_mapping"]),
        fenced(review["coverage"]),
        "原始文件引用：",
        "",
        fenced(review["source_references"]),
    ]
    return "\n".join(lines) + "\n"


def summary_row(review):
    slot = review["slot"]
    c = review["coverage"]
    o = review["outcome"]
    return {
        "slot_id": slot["slot_id"],
        "task": slot["task"],
        "case_id": slot["case_id"],
        "repeat_index": slot.get("repeat_index"),
        "seed": slot.get("seed"),
        "episode_id": review["episode_id"],
        **c,
        "reward": o["reward"],
        "completed": o["completed"],
        "work_valid": review["work_validity"].get("value"),
        "method_status": review["method_mapping"].get("status"),
        "method_class": review["method_mapping"].get("class_id"),
        "roles": list(review["members"]),
        "role_stops": review["termination"].get("role_stops"),
    }


def render_index(rows, totals):
    parts = [
        '<p class="eyebrow">ProWorkSim / v0.25 / review collection</p><h1>联合经历 · 人工审阅</h1>',
        '<p class="sub">16条真实经历 · 两个精确情境各8次重复 · 原策略实际工作记录</p>',
        '<nav class="jump"><a href="reading-notes.md">中文导读与逐条摘要</a><a href="README.md">Markdown总览</a><a href="summary.csv">结果索引CSV</a><a href="manifest.json">来源与覆盖清单</a><a href="../v025-joint-experiences.zip">下载离线审阅包</a></nav>',
        '<div class="notice">从原始归档只读转换，不重新运行模型或评分。这里可查看审阅者的全局时间线；“实际输入”逐调用保留每名成员当时收到的局部上下文。旧失败、控制输出及预算停止全部保留。</div>',
        '<div class="metrics">'
        + "".join(
            '<div class="metric"><strong>' + str(v) + "</strong><span>" + k + "</span></div>"
            for k, v in [
                ("联合经历", len(rows)),
                ("实际生成", totals["actual_generations"]),
                ("未生成请求", totals["non_generation_requests"]),
                ("世界工具动作", totals["world_actions"]),
            ]
        )
        + "</div>",
        '<h2>建议先看</h2><p class="small">事后阅读导航；全部16条仍列在下方，不改变实验采样或统计。</p><div class="guide">',
        '<a href="episodes/train-00-5.html"><b>① 一次完整A交付</b><br>train-00-5 · 查看交接怎样进入构建与提交。</a>',
        '<a href="episodes/train-00-1.html"><b>② 请求绑定的交接</b><br>train-00-1 · 交接成立，但后续工作未闭合。</a>',
        '<a href="episodes/train-01-6.html"><b>③ 正确产物与未完成职责</b><br>train-01-6 · 区分局部修正、最终复核与有效性。</a></div>',
        '<p class="small">每条经历已附成员协作有向图，可点击图中事件跳转至原记录。</p><h2>全部经历</h2><div class="toolbar"><input id="search-rows" placeholder="搜索编号、角色或状态…"><select id="task-filter"><option value="">A/B全部</option><option value="joint_a">A · 交接与交付</option><option value="joint_b">B · 复核与修复</option></select><label><input id="hide-scores" type="checkbox">隐藏原评分列</label></div><div class="scroll"><table><thead><tr><th>序号/打开</th><th>任务/重复</th><th>生成/请求</th><th>世界动作/拒绝</th><th class="outcome">R / 完整职责</th><th class="outcome">有效性/方法</th><th>停止记录</th></tr></thead><tbody>',
    ]
    for index, r in enumerate(rows, 1):
        sid = r["slot_id"]
        parts.append(
            '<tr data-slot="'
            + sid
            + '" data-task="'
            + r["task"]
            + '"><td><a href="episodes/'
            + sid
            + '.html">'
            + str(index).zfill(2)
            + " · "
            + sid
            + '</a><br><a class="small" href="episodes/'
            + sid
            + '.md">Markdown</a></td><td>'
            + esc(TASKS[r["task"]])
            + "<br>重复 "
            + str(r["repeat_index"])
            + "</td><td>"
            + str(r["actual_generations"])
            + " / "
            + str(r["started_requests"])
            + "</td><td>"
            + str(r["world_actions"])
            + " / "
            + str(r["world_action_rejected"])
            + '</td><td class="outcome">'
            + str(r["reward"])
            + " / "
            + flag(r["completed"])
            + '</td><td class="outcome">'
            + flag(r["work_valid"])
            + "<br>"
            + esc(r["method_class"] or r["method_status"])
            + '</td><td class="small">'
            + esc(
                "; ".join(
                    ROLES.get(k, k) + ": " + str(v) for k, v in (r["role_stops"] or {}).items()
                )
            )
            + "</td></tr>"
        )
    parts += [
        '</tbody></table></div><section class="panel"><h2>阅读口径</h2><ul><li>“请求”包括因上下文限制未开始生成的请求；另有发请求前轮次预算停止，不凭空增加请求或token。</li><li>模型提出的工具/控制调用与真实世界工具执行分列；staff_wait/staff_done也保留。</li><li>工具ok=true不等于内容正确，完整职责与重配有效性也分列。原score来自保存的独立评价。</li><li>HTML包含完整原始生成文本、工具参数/返回、按请求重建的完整messages/tools和实际对象版本。Markdown为便于批注的顺序阅读版，工具返回明确使用摘要，全文见HTML/JSON。</li><li>原始token ID/logprob数值数组留在服务器原件，审阅包保留数量和SHA引用；此包不是完整训练数据备份。</li></ul></section>'
    ]
    return page("v0.25联合经历人工审阅", "".join(parts))


def export(run, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.is_relative_to(run):
        raise ValueError("Review outputs must not mutate the raw experiment")
    collection = run / "support/actual/collection"
    progress = read_json(collection / "progress.json")
    if (
        len(progress) != 16
        or {r["slot_id"] for r in progress}
        != {f"train-{i:02d}-{j}" for i in (0, 1) for j in range(8)}
        or any(r["status"] != "closed" for r in progress)
    ):
        raise ValueError("Exactly the original sixteen closed v025 slots are required")
    for sub in ("episodes", "data", "graphs"):
        (output / sub).mkdir(parents=True, exist_ok=True)
    notes_path = output / "notes.json"
    notes = (
        {n["slot_id"]: n for n in read_json(notes_path)["episodes"]} if notes_path.exists() else {}
    )
    rows, refs = [], []
    for slot in progress:
        # The recorded progress contains outcomes; retain only declared slot identity.
        declared = {
            k: slot[k]
            for k in ("slot_id", "case_id", "task", "repeat_index", "seed", "sampling_seed")
        }
        review = collect_episode(collection / slot["slot_id"], declared)
        sid = slot["slot_id"]
        if sid in notes:
            review["editorial_note"] = copy.deepcopy(notes[sid])
        review["collaboration_graph"] = collaboration_graph(review)
        (output / "graphs" / f"{sid}.svg").write_text(collaboration_svg(review, standalone=True))
        (output / "data" / f"{sid}.json").write_text(pretty(review) + "\n")
        (output / "episodes" / f"{sid}.html").write_text(render_episode_html(review))
        (output / "episodes" / f"{sid}.md").write_text(render_episode_markdown(review))
        rows.append(summary_row(review))
        refs.append({"slot_id": sid, "source_references": review["source_references"]})
    totals = {
        key: sum(r[key] for r in rows)
        for key in (
            "started_requests",
            "actual_generations",
            "non_generation_requests",
            "world_actions",
            "world_action_ok",
            "world_action_rejected",
            "boundary_errors",
            "unlinked_boundary_errors",
            "parse_errors",
            "format_feedback_events",
            "model_control_events",
        )
    }
    (output / "index.html").write_text(render_index(rows, totals))
    (output / "summary.json").write_text(
        pretty({"version": VERSION, "episodes": rows, "totals": totals}) + "\n"
    )
    with (output / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        fields = [
            "slot_id",
            "task",
            "repeat_index",
            "seed",
            "started_requests",
            "actual_generations",
            "non_generation_requests",
            "world_actions",
            "world_action_rejected",
            "reward",
            "completed",
            "work_valid",
            "method_status",
            "method_class",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)
    lines = [
        "# v0.25联合经历人工审阅",
        "",
        "[打开交互HTML总览](index.html) · [中文导读](reading-notes.md) · [CSV索引](summary.csv) · [离线ZIP](../v025-joint-experiences.zip)",
        "",
        "原16条联合经历全部导出；不调用模型、不重放世界、不重新评分。中文标签与导读为审阅辅助；成员原话保留原文。",
        "",
        "| 序号 | 经历 | 类型 | 实际生成/请求 | 原R | 完整职责 |",
        "|---|---|---|---:|---:|---|",
    ]
    for index, r in enumerate(rows, 1):
        lines.append(
            f"| {index:02d} | [{r['slot_id']}](episodes/{r['slot_id']}.md) | {TASKS[r['task']]} | {r['actual_generations']}/{r['started_requests']} | {r['reward']} | {flag(r['completed'])} |"
        )
    lines += [
        "",
        "## 文件结构",
        "",
        "- `index.html`：可筛选总览；`episodes/*.html`：成员/事件/关键词筛选、可展开的完整上下文与返回。",
        "- `graphs/*.svg`：成员协作有向图，按事件顺序展示可确认的跨成员请求、交接、提交检查和复核反馈；在HTML点击箭头可定位原事件。实线为工具已记录，虚线为被拒尝试，不等同业务判断正确或对方已读。未绑定请求、幂等重试与历史提交问题单独标注；无法确认接收成员的拒绝不虚构连线，图下注明原序号。",
        "- `episodes/*.md`：适合逐段批注，模型正文与执行参数保留，工具返回摘要有明确标注。",
        "- `data/*.json`：角色与调用身份绑定的审阅数据；完整输入按message/tool内容地址去重，可精确还原。",
        "- `reading-notes.md`：事后中文导读与逐条原事件证据；不混入模型原始轨迹。",
        "- `manifest.json`：原始文件SHA、覆盖核对与输出清单。",
        "",
        "HTML为离线文件，无CDN、无网络请求；下载ZIP后打开其中index.html。模型输入详情由页面内嵌数据展开，无需本地Web服务。",
        "",
        "审阅者可看全局快照；每名成员实际可见内容以对应请求为准，不能把全局材料当作其当时输入。原数值token/logprob数组没有复制到此阅读包，仍位于服务器SHA绑定原件，故本包不替代完整训练备份。",
        "",
        "## 生成方法与边界",
        "",
        "导出器 `scripts/export_joint_review_v025.py` 只读原支持集合；中文阅读说明独立保存在 `notes.json` / `reading-notes.md`。在仓库根目录运行：",
        "",
        fenced(
            ".venv/bin/python scripts/export_joint_review_v025.py --zip docs/reviews/v025-joint-experiences.zip",
            "bash",
        ),
        "各原请求包含顶层字段顺序，使用 `reconstruct_input(review, decision)` 可原样重建并复现项目 json_bytes 序列化的 input_sha256。导出时核验所有请求、世界动作以及捕获文件，两个独立 fixture 控制跨角色同调用ID、拒绝／未生成／无调用停止、末尾格式反馈和原文HTML转义。",
        "",
        "原model_attempt、public_observation/public_tools、policy_decision、role_not_scheduled、动作链接与服务包装不逐条展开；实际请求中的完整视野与工具定义、生成原文、真实世界执行、格式反馈、控制和边界事件均保留。审阅包不包含完整训练token数组或运行资源遥测。",
        "",
        "## 覆盖计数",
        "",
        fenced(totals),
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    manifest = {
        "version": VERSION,
        "original_run": str(run),
        "scope": "All16original support episodes only; no ongoing R1 confirmation data.",
        "editorial_notes": "notes.json and reading-notes.md are derived Chinese annotations; original role messages and saved outcomes remain authoritative.",
        "inputs": [ref(collection / name) for name in ("progress.json", "declaration.json")],
        "episodes": refs,
        "totals": totals,
        "request_reconstruction_exact": True,
        "reconstructed_request_sha256_exact": True,
        "world_action_coverage_exact": True,
        "omitted_from_human_package": [
            "Numeric input/output token ID and behavior logprob arrays (counts and original SHA references retained)",
            "Standalone public_observation/public_tools, model_attempt/model_tool_result/model_action_link, policy_decision and role_not_scheduled wrappers (actual request messages/tools, responses and executed actions retained)",
            "Repeated service wrappers and resource telemetry (source event counts and raw file references retained)",
        ],
        "not_omitted": [
            "All original generated text",
            "All actual role-local request messages and tool definitions",
            "All actual world tool calls/results",
            "All model boundaries including no-call pre-request stops",
            "Business environment/controller/control events and runtime format feedback",
            "Captured artifact version content",
        ],
        "outputs": [
            {
                "path": str(p.relative_to(output)),
                "sha256": digest(p.read_bytes()),
                "bytes": p.stat().st_size,
            }
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        ],
    }
    (output / "manifest.json").write_text(pretty(manifest) + "\n")
    return {"output": str(output), "totals": totals, "episodes": len(rows)}


def make_zip(output, destination):
    output, destination = Path(output).resolve(), Path(destination).resolve()
    if destination.is_relative_to(output):
        raise ValueError("ZIP must be outside its own input tree")
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=str(Path(output.name) / path.relative_to(output)))
    return ref(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("runs/domain-v025"))
    parser.add_argument("--output", type=Path, default=Path("docs/reviews/v025-joint-experiences"))
    parser.add_argument("--zip", dest="zip_path", type=Path)
    args = parser.parse_args()
    result = export(args.run, args.output)
    if args.zip_path:
        result["zip"] = make_zip(args.output, args.zip_path)
    print(json.dumps(result, ensure_ascii=False))
