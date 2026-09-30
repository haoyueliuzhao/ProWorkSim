"""C0: read-only collaboration evidence from the sixteen original v0.25 episodes.

No world/grader replay, model requests, new labels in training, or mutations of
source files. Mere order or text similarity never establishes causal influence.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from proworksim.storage import digest, json_bytes

VERSION = "collaboration-evidence-c0-v0.26"
READS = {"read_alias", "read_version", "read_object"}
WRITES = {"write_object", "edit_artifact", "sql_build"}
CHANGES = WRITES | {"withdraw", "submit"}


def read(path):
    return json.loads(Path(path).read_text())


def source(path):
    data = Path(path).read_bytes()
    return {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(data).hexdigest()}


def nodes(value, path=""):
    """Walk structured content, parsing JSON string envelopes without text guessing."""
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from nodes(item, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from nodes(item, path + "/" + str(index))
    elif isinstance(value, str) and value.startswith(("{", "[")):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return
        yield from nodes(parsed, path + "::<json>")


def request_nodes(request):
    # Assistant history is the model's own claim, not independently delivered evidence.
    for index, message in enumerate((request or {}).get("messages", [])):
        if message.get("role") in {"user", "tool"}:
            yield from nodes(message.get("content"), f"/messages/{index}/content")


def exposure(decisions, recipient, after, predicate):
    """First exact input occurrence and first occurrence followed by real generation."""
    found = []
    for decision in decisions:
        if decision["member_id"] != recipient or decision["sequence"] <= after:
            continue
        for pointer, value in decision["nodes"]:
            if predicate(value):
                found.append(
                    {
                        "member_id": recipient,
                        "sequence": decision["sequence"],
                        "call_id": decision["call_id"],
                        "decision_index": decision["decision_index"],
                        "input_event_sequence": decision["input_event_sequence"],
                        "generation_status": decision["generation_status"],
                        "generated": decision["generated"],
                        "projection_pointer": decision["projection_pointer"]
                        + "/actual_input"
                        + pointer,
                    }
                )
                break
    return {
        "first_request_input": found[0] if found else None,
        "first_input_with_generation": next((x for x in found if x["generated"]), None),
    }


def entity_matches(key, identifier, body=None):
    def match(value):
        if not isinstance(value, dict):
            return False
        keys = [key]
        if key == "submission_id":
            keys += ["latest_submission_id", "pending_submission_id"]
        if not any(value.get(candidate) == identifier for candidate in keys):
            return False
        return body is None or any(value.get(field) == body for field in ("body", "description"))

    return match


def ref_matches(reference, content=False):
    def match(value):
        if not isinstance(value, dict):
            return False
        if not content:
            object_view = value.get(reference["object_id"])
            if object_view == reference["version_id"]:
                return True
            if isinstance(object_view, dict) and reference["version_id"] in object_view.get(
                "versions", []
            ):
                return True
        ref = value.get("reference", {}) if content else value
        return (
            isinstance(ref, dict)
            and ref.get("object_id") == reference["object_id"]
            and any(
                ref.get(key) == reference["version_id"]
                for key in (
                    ["version_id"]
                    if content
                    else ["version_id", "current_version", "adopted_version", "target_version"]
                )
            )
            and (not content or "data" in value)
        )

    return match


def result_dict(payload):
    result = payload.get("response", {}).get("result")
    return result if isinstance(result, dict) else {}


def brief(event):
    payload = event["payload"]
    result = result_dict(payload)
    return {
        "sequence": event["sequence"],
        "actor": event["worker_id"],
        "action": payload["action"],
        "tool_ok": payload["response"].get("ok"),
        "execution_status": result.get("execution_status"),
        "model_call_id": payload.get("model_call_id"),
    }


def successful(event):
    return event["payload"].get("response", {}).get("ok") is True


def later_actions(actions, actor, after, names):
    return [
        brief(a)
        for a in actions
        if a["worker_id"] == actor
        and a["sequence"] > after
        and a["payload"]["action"] in names
        and successful(a)
    ]


def extract_episode(rollout, projection, start, end, *, slot_id, artifact_sources=None):
    events = rollout["events"]
    actions = [e for e in events if e["kind"] == "tool_call"]
    starts = {
        (e["worker_id"], e["payload"].get("call_id")): e["sequence"]
        for e in events
        if e["kind"] == "model_call" and e["payload"].get("stage") == "started"
    }
    decisions = []
    for role, view in projection["member_views"].items():
        for index, item in enumerate(view["decisions"]):
            request = item.get("actual_input")
            if item.get("input_sha256") and digest(json_bytes(request)) != item["input_sha256"]:
                raise ValueError("Original input SHA mismatch")
            decisions.append(
                {
                    "member_id": role,
                    "call_id": item["call_id"],
                    "sequence": starts[(role, item["call_id"])],
                    "decision_index": item.get("decision_index"),
                    "input_event_sequence": item.get("input_event_sequence"),
                    "generation_status": item.get("generation_status"),
                    "generated": item.get("actual_response") is not None,
                    "projection_pointer": f"#/member_views/{role}/decisions/{index}",
                    "nodes": list(request_nodes(request)),
                }
            )
    decisions.sort(key=lambda d: d["sequence"])
    members = list(projection["member_views"])
    facts = projection.get("method_mapping", {}).get("evidence", {}).get("facts", {})
    judgments = {j["sequence"]: j for j in facts.get("judgments", [])}
    all_artifacts = end.get("artifacts", {})
    artifact_by_id = {v.get("object_id", k): v for k, v in all_artifacts.items()}
    records = []

    def new_record(kind, identifier, sender, recipients, current, event=None):
        row = {
            "kind": kind,
            "id": identifier,
            "sender": sender,
            "recipients": recipients,
            "current_model_action": current,
            "origin": "current_model_action" if current else "inherited_preparation",
            "send_or_write": brief(event) if event else None,
            "delivered_or_accessible": [],
            "recipient_inputs": {},
            "execution_use": [],
            "later_change_candidates": [],
            "reverification": [],
            "diagnostic_labels": [],
            "causal_effect": "not_identified_by_observation",
            "recipients_scope": "roles checked for receipt; inclusion alone does not assert delivery",
        }
        records.append(row)
        return row

    def populate_entity(row, key, body=None):
        after = row["send_or_write"]["sequence"] if row["send_or_write"] else -1
        for recipient in row["recipients"]:
            found = exposure(decisions, recipient, after, entity_matches(key, row["id"], body))
            row["recipient_inputs"][recipient] = {
                "content" if body else "identity_or_metadata": found
            }
            first = found["first_request_input"]
            if first:
                row["delivered_or_accessible"].append(
                    {
                        "recipient": recipient,
                        "proof": "exact_entity_in_actual_request",
                        "sequence": first["sequence"],
                    }
                )

    # Inherited deliveries are retained even though origin=member_action in old preparation state.
    handoffs = [(h, None) for h in start.get("handoffs", {}).values()]
    for event in actions:
        if event["payload"]["action"] == "handoff_information" and successful(event):
            result = event["payload"]["response"]["result"]
            handoff = end.get("handoffs", {}).get(result.get("handoff_id"))
            if handoff and result.get("created") is True:
                handoffs.append((handoff, event))
    for handoff, event in handoffs:
        row = new_record(
            "handoff",
            handoff["handoff_id"],
            handoff["sender"],
            handoff.get("recipients", []),
            event is not None,
            event,
        )
        row.update(
            {
                "reference": handoff.get("reference"),
                "request_id": handoff.get("request_id"),
                "body": handoff.get("body"),
                "formal_request_bound": bool(handoff.get("request_id")),
                "referenced_information_origin": "inherited_artifact",
            }
        )
        populate_entity(row, "handoff_id", handoff.get("body"))
        for env in events:
            if env["kind"] == "environment_event" and env["payload"].get("event_id") == handoff.get(
                "event_id"
            ):
                row["delivered_or_accessible"].append(
                    {"proof": "applied_environment_handoff", "sequence": env["sequence"]}
                )
        if event is None:
            row["delivered_or_accessible"].append(
                {"proof": "start_state_inherited_delivery", "status": handoff.get("status")}
            )
        matching = []
        for a in actions:
            if (
                a["worker_id"] == row["sender"]
                and a["payload"]["action"] in READS
                and successful(a)
            ):
                r = result_dict(a["payload"])
                if r.get("reference") == row["reference"] and (
                    event is None or a["sequence"] < event["sequence"]
                ):
                    matching.append(a)
        body = handoff.get("body", "")
        try:
            parsed_body = json.loads(body)
        except (ValueError, TypeError):
            parsed_body = None
        row["exact_full_data_forward"] = (
            any(a["payload"]["response"]["result"].get("data") == parsed_body for a in matching)
            if parsed_body is not None
            else False
        )
        row["prior_source_reads"] = [brief(a) for a in matching]
        row["content_conditioning"] = (
            "not_identified; no counterfactual condition or feedback-dependent revision inferred"
        )
        after = event["sequence"] if event else -1
        for a in actions:
            p = a["payload"]
            if (
                a["sequence"] <= after
                or a["worker_id"] not in row["recipients"]
                or not successful(a)
            ):
                continue
            result, args = result_dict(p), p.get("arguments", {})
            reference = result.get("reference", {})
            if (p["action"] in READS and reference == row["reference"]) or (
                p["action"] == "adopt" and ref_matches(row["reference"])(args)
            ):
                row["execution_use"].append(brief(a))
        qualifying = facts.get("qualifying_handoffs", [])
        row["saved_current_fixed_product_use"] = next(
            (
                h.get("actually_used_in_current_fixed_product")
                for h in qualifying
                if h["handoff_id"] == row["id"]
            ),
            None,
        )
        row["diagnostic_labels"].append(
            "fixed_material_forward"
            if row["exact_full_data_forward"]
            else "fixed_material_summary_or_reference_forward"
            if event
            else "inherited_delivery"
        )

    for event in actions:
        p = event["payload"]
        if p["action"] != "request_information" or not successful(event):
            continue
        request_id = p["response"]["result"]["request_id"]
        request = end.get("requests", {}).get(request_id, {})
        recipient = request.get("requested_role")
        row = new_record(
            "request", request_id, event["worker_id"], [recipient] if recipient else [], True, event
        )
        row["request_state"] = request
        populate_entity(row, "request_id")
        row["execution_use"] = [
            r["send_or_write"]
            for r in records
            if r["kind"] == "handoff" and r.get("request_id") == request_id and r["send_or_write"]
        ]
        row["diagnostic_labels"] = [
            "formally_bound_reply" if row["execution_use"] else "no_formally_bound_reply"
        ]

    # Fixed submissions are evidence of a product, not an inferred current-member message.
    submissions = [
        (s, None) for w in start.get("work_items", {}).values() for s in w.get("submissions", [])
    ]
    for event in actions:
        if event["payload"]["action"] == "submit" and successful(event):
            submissions.append((event["payload"]["response"]["result"], event))
    for submission, event in submissions:
        sid = submission["submission_id"]
        sender = submission.get("actor_id", "implementer")
        recipients = [m for m in members if m != sender]
        row = new_record("fixed_submission", sid, sender, recipients, event is not None, event)
        row["artifact_versions"] = submission.get("artifact_versions", {})
        populate_entity(row, "submission_id")
        after = event["sequence"] if event else -1
        for a in actions:
            p = a["payload"]
            if (
                a["sequence"] > after
                and a["worker_id"] in recipients
                and p.get("arguments", {}).get("submission_id") == sid
            ):
                if p["action"] == "inspect_submission" and successful(a):
                    row["execution_use"].append(brief(a))
                elif p["action"] in {"raise_issue", "approve"}:
                    b = brief(a)
                    b["saved_judgment_valid"] = judgments.get(a["sequence"], {}).get("valid")
                    row["reverification"].append(b)
        row["diagnostic_labels"] = [
            "current_fixed_delivery" if event else "inherited_fixed_product_not_current_delivery"
        ]

    for event in actions:
        p = event["payload"]
        if p["action"] != "raise_issue":
            continue
        result = result_dict(p)
        iid = result.get("issue_id", f"rejected-issue-at-{event['sequence']}")
        row = new_record("issue", iid, event["worker_id"], ["implementer"], True, event)
        row.update(
            {
                "description": p.get("arguments", {}).get("description"),
                "target_submission": p.get("arguments", {}).get("submission_id"),
                "saved_judgment_valid": judgments.get(event["sequence"], {}).get("valid"),
                "active_at_creation": result.get("active_at_creation"),
            }
        )
        populate_entity(row, "issue_id", row["description"])
        first = row["recipient_inputs"]["implementer"]["content"]["first_input_with_generation"]
        row["prior_implementation_changes"] = [
            brief(a)
            for a in actions
            if a["worker_id"] == "implementer"
            and a["sequence"] < event["sequence"]
            and a["payload"]["action"] in CHANGES
            and successful(a)
        ]
        if first:
            row["later_change_candidates"] = later_actions(
                actions, "implementer", first["sequence"], CHANGES
            )
        for a in actions:
            if a["sequence"] <= event["sequence"] or not successful(a):
                continue
            args = a["payload"].get("arguments", {})
            if args.get("issue_id") == iid:
                if a["payload"]["action"] == "respond_issue":
                    row["execution_use"].append(brief(a))
                if a["payload"]["action"] == "decide_issue":
                    row["reverification"].append(brief(a))
        row["diagnostic_labels"] = [
            "explicit_feedback_use" if row["execution_use"] else "no_explicit_feedback_treatment",
            "temporal_followup_only"
            if row["later_change_candidates"]
            else "no_generated_followup_change",
        ]

    # Every retained artifact version has origin and actual body exposure, including drafts never sent.
    artifact_rows = []
    start_versions = {
        (v.get("object_id", k), ver)
        for k, v in start.get("artifacts", {}).items()
        for ver in v.get("versions", {})
    }
    for oid, artifact in artifact_by_id.items():
        for version in artifact.get("versions", {}):
            reference = {"object_id": oid, "version_id": version}
            inherited = (oid, version) in start_versions
            creators = [
                a
                for a in actions
                if successful(a)
                and a["payload"]["action"] in WRITES
                and (
                    result_dict(a["payload"]).get("reference") == reference
                    or ref_matches(reference)(result_dict(a["payload"]))
                )
            ]
            created = creators[0] if creators else None
            sender = created["worker_id"] if created else artifact.get("owner")
            after = created["sequence"] if created else -1
            # Both members are retained for inherited evidence, only peers for current work.
            recipients = [m for m in members if inherited or m != sender]
            artifact_rows.append(
                {
                    "alias": artifact.get("alias"),
                    "reference": reference,
                    "origin": "inherited_preparation"
                    if inherited
                    else "current_model_action"
                    if created
                    else "unattributed_retained_version",
                    "current_model_action": bool(created) and not inherited,
                    "sender": sender,
                    "write": brief(created) if created else None,
                    "recipients": recipients,
                    "recipient_inputs": {
                        m: {
                            "identity_or_metadata": exposure(
                                decisions, m, after, ref_matches(reference)
                            ),
                            "content": exposure(decisions, m, after, ref_matches(reference, True)),
                        }
                        for m in recipients
                    },
                    "execution_use": [
                        brief(a)
                        for a in actions
                        if a["sequence"] > after
                        and a["worker_id"] in recipients
                        and successful(a)
                        and (
                            any(
                                ref_matches(reference)(v)
                                for _, v in nodes(a["payload"].get("arguments", {}))
                            )
                            or (
                                a["payload"]["action"] in READS
                                and result_dict(a["payload"]).get("reference") == reference
                            )
                        )
                    ],
                    "fixed_submission_links": [
                        {
                            "submission_id": submission["submission_id"],
                            "origin": "current_model_action" if event else "inherited_preparation",
                            "submit_sequence": event["sequence"] if event else None,
                        }
                        for submission, event in submissions
                        if submission.get("artifact_versions", {}).get(oid) == version
                    ],
                    "reverification": [
                        judgment
                        for row in records
                        if row["kind"] == "fixed_submission"
                        and row.get("artifact_versions", {}).get(oid) == version
                        for judgment in row["reverification"]
                    ],
                    "source": (artifact_sources or {}).get((oid, version)),
                    "delivery_scope": "body exposure is shown separately from reference visibility; writing is not delivery",
                }
            )
    labels = []
    if any(r["kind"] == "handoff" and r["current_model_action"] for r in records):
        labels.append("one_way_current_material_handoff")
    if any(r["kind"] == "request" and r["execution_use"] for r in records):
        labels.append("request_bound_reply")
    if any(r["kind"] == "issue" and r.get("saved_judgment_valid") is True for r in records):
        labels.append("valid_issue_discovery")
    if any(r["kind"] == "issue" and r["later_change_candidates"] for r in records):
        labels.append("changes_after_issue_input_not_causal_proof")
    if not projection["work_validity"]["value"]:
        labels.append("not_complete_method_support")
    return {
        "slot_id": slot_id,
        "members": members,
        "original_result": {
            "reward": projection["assessment"]["reward"],
            "completed": projection["assessment"]["completed"],
            "V": projection["work_validity"]["value"],
            "mapper_status": projection["method_mapping"]["status"],
            "mapper_class": projection["method_mapping"].get("class_id"),
        },
        "saved_facts": facts,
        "records": records,
        "communication_attempts_without_new_evidence": [
            {
                **brief(a),
                "arguments": a["payload"].get("arguments"),
                "error": a["payload"]["response"].get("error"),
                "created": result_dict(a["payload"]).get("created"),
            }
            for a in actions
            if a["payload"]["action"]
            in {
                "handoff_information",
                "request_information",
                "submit",
                "approve",
                "respond_issue",
                "decide_issue",
            }
            and (
                not successful(a)
                or (
                    a["payload"]["action"] == "handoff_information"
                    and result_dict(a["payload"]).get("created") is False
                )
            )
        ],
        "artifacts": artifact_rows,
        "diagnostic_labels": labels,
        "coverage": {
            "requests": len(decisions),
            "generations": sum(d["generated"] for d in decisions),
            "world_actions": len(actions),
            "retained_artifact_versions": len(artifact_rows),
        },
    }


def collect(folder):
    rollout, projection = read(folder / "team-rollout.json"), read(folder / "projection.json")
    manifest = read(folder / "episode/manifest.json")
    if manifest != rollout["manifest"]:
        raise ValueError("Manifest differs from original rollout")
    states, artifacts, refs = {}, {}, {}
    for phase in ("start", "end"):
        spec = manifest[phase]
        state_path = folder / "episode" / spec["path"] / spec["state"]["path"]
        states[phase] = read(state_path)
        refs[phase + "_state"] = source(state_path)
        if refs[phase + "_state"]["sha256"] != spec["state"]["sha256"]:
            raise ValueError("Snapshot SHA mismatch")
        for item in spec["files"]:
            key = (item["object_id"], item["version_id"])
            path = folder / "episode" / spec["path"] / item["path"]
            ref = source(path)
            if ref["sha256"] != item["sha256"]:
                raise ValueError("Artifact SHA mismatch")
            artifacts.setdefault(key, ref)
    result = extract_episode(
        rollout,
        projection,
        states["start"],
        states["end"],
        slot_id=folder.name,
        artifact_sources=artifacts,
    )
    result["sources"] = {
        **refs,
        "rollout": source(folder / "team-rollout.json"),
        "projection": source(folder / "projection.json"),
        "manifest": source(folder / "episode/manifest.json"),
    }
    return result


def seqs(items):
    return (
        "、".join(
            f"#{x['sequence']} {x['action']}"
            + ("（工具拒绝）" if x.get("tool_ok") is False else "")
            + ("（原判无效）" if x.get("saved_judgment_valid") is False else "")
            for x in items
        )
        or "无"
    )


def inputs(row):
    parts = []
    for member, levels in row["recipient_inputs"].items():
        value = levels.get("content", levels.get("identity_or_metadata", {}))
        first, generated = (
            value.get("first_request_input"),
            value.get("first_input_with_generation"),
        )
        desc = f"#{first['sequence']} / decision {first['decision_index']}" if first else "未见"
        if first and not first["generated"]:
            desc += "（未开始生成）"
        if generated and first != generated:
            desc += f"；首次生成 #{generated['sequence']}"
        parts.append(member + ": " + desc)
    return "；".join(parts) or "无接收成员"


def markdown(report):
    totals = report["totals"]
    current_artifacts = [
        a for e in report["episodes"] for a in e["artifacts"] if a["current_model_action"]
    ]
    metadata_count = sum(
        any(
            v["identity_or_metadata"]["first_request_input"] for v in a["recipient_inputs"].values()
        )
        for a in current_artifacts
    )
    body_count = sum(
        any(v["content"]["first_request_input"] for v in a["recipient_inputs"].values())
        for a in current_artifacts
    )
    lines = [
        "# v0.26 C0：v0.25 原 16 条联合经历的协作证据复核",
        "",
        "本报告只读原支持窗口，不调用模型，不重演世界或评分，不更改原 V、Mapper 与支持池。诊断标签仅用于审阅，不进入训练类别。",
        "",
        f"覆盖 {len(report['episodes'])} 条经历、{totals['requests']} 次请求、{totals['generations']} 次实际生成、{totals['world_actions']} 个世界动作。原合格经历仍只有 train-00-5；原结果不变。",
        "",
        "## 证据规则",
        "",
        "发出/写入、送达/可访问、进入实际输入、执行使用、再次验证分别保留。首次输入以 projection 中保存的真实请求为准，给出原 team-rollout 的 model_call start 序号与角色 decision index；JSON 另保存 input_event_sequence（可能为空）、call_id 和精确字段路径。",
        "",
        "输入匹配仅检查 user/tool 消息的结构化实体或确切版本，不把 assistant 自述当成已经收到信息。因上下文限制未生成的请求仍保留输入证据，但不能视为模型已处理反馈。产物引用可见与完整内容读取分开；B 初始 submission 和 prepared-basis 是继承准备状态，即使其历史 actor_id/origin 写有角色名，也不算当前模型交付。",
        "",
        "使用关系限定为明确引用/采用/问题处理等可核对执行证据。反馈之后发生写代码、构建或提交，只列为时间顺序候选；没有受控反事实，不能据此宣称因果作用。问题是否有效直接引用原判定，工具 ok 不替代业务有效性。自然语言的条件化回应不以文本相似度自动判定。交接正文与先前读得的完整 JSON 完全相等仅标为精确全量转发（本批 2 条）；其余摘要或引用交付保留原文，不因此推断内容条件化。",
        "",
        "## 16 条概览",
        "",
        "| 经历 | 原 R / V | 当前交接 / 绑定回复 | issue：记录 / 原有效 | 当前新固定提交 | 原方法 |",
        "|---|---|---|---|---|---|",
    ]
    for episode in report["episodes"]:
        rs = episode["records"]
        orig = episode["original_result"]
        handoffs = [r for r in rs if r["kind"] == "handoff" and r["current_model_action"]]
        issues = [r for r in rs if r["kind"] == "issue"]
        lines.append(
            f"| [{episode['slot_id']}](../reviews/v025-joint-experiences/episodes/{episode['slot_id']}.html) | {orig['reward']} / {orig['V']} | {len(handoffs)} / {sum(h.get('formal_request_bound', False) for h in handoffs)} | {len(issues)} / {sum(i.get('saved_judgment_valid') is True for i in issues)} | {sum(r['kind'] == 'fixed_submission' and r['current_model_action'] for r in rs)} | {orig['mapper_class'] or '未映射'} |"
        )
    lines += [
        "",
        "## 关键时序与解释边界",
        "",
        f"本批当前模型产生的 code/result 等产物版本共 {len(current_artifacts)} 个；其中 {metadata_count} 个版本标识进入过对方实际输入，{body_count} 个版本的完整内容经实际读取后进入对方输入。这是产物可见性统计，不含已单列的 basis 消息正文，也不把版本目录可见当作产物已被复核。",
        "",
        "- **train-00-5**：唯一完整有效 A。提供者一次交接之后由实现者完成后续工作。准确来源、采用与固定产物使用见下表及原 saved_facts；不能据此宣称存在持续双向内容适配。",
        "- **train-00-1**：唯一正式 request_id 绑定的当前交接；请求绑定真实成立，仍不等于实现与完整职责成功。",
        "- **train-01-3**：实现者 #145、#168 写代码早于 reviewer #179 的有效 issue；下一实现者请求 #185 保存了该问题，但因上下文限制未开始生成。不能把前两次修改归因于后来的问题，也没有问题后模型修复或再验证闭环。",
        "- **train-01-6**：issue #131 进入后续实现者输入，后有撤回/改写/构建/新提交，但原 issue 有效性为 False、V 为 False、R=0.3。时间上后续改变与正确新产物均可保留；没有明确问题处理和最终核准，不能提升为有效反馈修复方法。",
        "",
        "上述判断不证明协作无用；它说明当前证据的层次与限制。条件化回应、信息的必要性与分配价值，需要后继受控实验分别判断。",
    ]
    titles = {
        "handoff": "资料交接",
        "request": "正式请求",
        "fixed_submission": "固定产物",
        "issue": "问题反馈",
    }
    for episode in report["episodes"]:
        lines += [
            "",
            f"## {episode['slot_id']}",
            "",
            "| 证据 / 来源 | 发出或写入 | 送达 / 可访问 | 首次接收者实际输入 | 执行使用 / 后续改变 | 再次验证 |",
            "|---|---|---|---|---|---|",
        ]
        for row in episode["records"]:
            origin = "当前模型" if row["current_model_action"] else "继承准备"
            created = seqs([row["send_or_write"]]) if row["send_or_write"] else "采样前"
            delivered = (
                "；".join(
                    ("#" + str(x["sequence"]) + " " if "sequence" in x else "") + x["proof"]
                    for x in row["delivered_or_accessible"]
                )
                or "未见已送达证据"
            )
            use = seqs(row["execution_use"])
            if row["later_change_candidates"]:
                use += "；时间候选（非因果）" + seqs(row["later_change_candidates"])
            lines.append(
                f"| {titles[row['kind']]} `{row['id']}`；{origin}，来源 {row['sender']}；核查接收者 {','.join(row['recipients'])} | {created} | {delivered} | {inputs(row)} | {use} | {seqs(row['reverification'])} |"
            )
        lines += [
            "",
            "产物版本的来源与首次内容输入：",
            "",
            "| 产物版本 | 来源 / 写入 | 对方首次内容输入 |",
            "|---|---|---|",
        ]
        for art in episode["artifacts"]:
            if art["current_model_action"] or art["alias"] in {
                "basis",
                "code",
                "result",
                "audit_basis",
            }:
                origin = (
                    "继承"
                    if art["origin"] == "inherited_preparation"
                    else seqs([art["write"]])
                    if art["write"]
                    else "来源未归属"
                )
                lines.append(
                    f"| {art['alias']} {art['reference']['version_id']} | {origin} | {inputs(art)} |"
                )
        if episode["communication_attempts_without_new_evidence"]:
            lines += [
                "",
                "未形成新交付/有效核准的尝试（包含幂等重复）："
                + seqs(episode["communication_attempts_without_new_evidence"])
                + "。",
            ]
        lines += [
            "",
            "诊断标签：" + "、".join(episode["diagnostic_labels"]) + "。",
            "",
            "原结果：`" + json.dumps(episode["original_result"], ensure_ascii=False) + "`。",
        ]
    lines += [
        "",
        "## 可复现与来源",
        "",
        "运行：`.venv/bin/python scripts/collaboration_evidence_v026.py`。输出 JSON 保留原文件路径与 SHA256、逐实体输入定位、所有捕获产物版本来源及原 saved_facts。只产生本报告，不写入 runs。",
        "",
        "[机器可核对证据表](collaboration-v026-c0.json)；[原 16 条全文审阅](../reviews/v025-joint-experiences/index.html)。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection", type=Path, default=Path("runs/domain-v025/support/actual/collection")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("docs/experiments/collaboration-v026-c0")
    )
    args = parser.parse_args()
    expected = {f"train-{task:02d}-{repeat}" for task in (0, 1) for repeat in range(8)}
    folders = [p for p in args.collection.glob("train-*") if p.is_dir()]
    if {p.name for p in folders} != expected:
        raise ValueError("C0 is restricted to the original sixteen support episodes")
    episodes = [
        collect(args.collection / f"train-{task:02d}-{repeat}")
        for repeat in range(8)
        for task in (0, 1)
    ]
    totals = Counter()
    for episode in episodes:
        totals.update(episode["coverage"])
    report = {
        "version": VERSION,
        "scope": "read-only original v0.25 support; diagnostic only, no support relabeling",
        "causality": "observed execution dependencies are not causal effects",
        "totals": dict(totals),
        "episodes": episodes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    args.output.with_suffix(".md").write_text(markdown(report))
    print(
        json.dumps(
            {"episodes": len(episodes), "totals": dict(totals), "output": str(args.output)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
