"""Role-scoped deterministic projection of a single already-authorized provider payload."""

from hashlib import sha256
import json


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def identity(value):
    return sha256(compact(value).encode()).hexdigest()


def object_text(s):
    if isinstance(s, str) and s.lstrip().startswith("{"):
        try:
            v = json.loads(s)
            if isinstance(v, dict):
                return v
        except (ValueError, RecursionError):
            pass
    return None


OSA_FIELDS = {
    "base_version",
    "base_sha256",
    "anomaly",
    "subject",
    "anomaly_id",
    "graph",
    "evidence",
    "options",
    "remaining_team_tokens",
    "reported_execution_blocker",
    "candidate_role",
}
GRAPH_FIELDS = set(
    "member_registry scheduling member_availability fixed_organization organization_protocol dynamic_organization organization_decision organization_choice dynamic_contract actor_delivery_checklist team_model_budget team_test_budget shared_resource_limits member_limits transfer_offers tasks task_count handoffs older_handoff_sequences".split()
)


def validate_role(wire, actor, role):
    if actor not in ("member_001", "member_002"):
        raise ValueError("Unbound member")
    names = {x["function"]["name"] for x in wire.get("tools", [])}
    if role == "osa":
        msgs = wire["messages"]
        if (
            names != {"activate_organization"}
            or len(msgs) < 2
            or msgs[0]["role"] != "system"
            or msgs[1]["role"] != "user"
        ):
            raise ValueError("Expected isolated controller request")
        view = object_text(msgs[1]["content"])
        if (
            not view
            or set(view) - OSA_FIELDS
            or not {"graph", "evidence", "options", "anomaly_id"} <= view.keys()
        ):
            raise ValueError("Unrecognized controller view")
        if len(msgs) > 2:
            correction = (
                "Correct the decision once using only the supplied option and evidence IDs."
            )
            assistant = msgs[2]
            if (
                assistant["role"] != "assistant"
                or msgs[-1] != {"role": "user", "content": correction}
                or len(msgs) < 4
                or any(m["role"] != "tool" for m in msgs[3:-1])
            ):
                raise ValueError("Foreign material in controller correction")
            calls = assistant.get("tool_calls") or []
            if [c["id"] for c in calls] != [m.get("tool_call_id") for m in msgs[3:-1]] or any(
                c["function"]["name"] != "activate_organization" for c in calls
            ):
                raise ValueError("Foreign tool result in controller correction")
    elif role not in ("worker", "condenser") or "activate_organization" in names:
        raise ValueError("Worker/controller boundary mismatch")


def visible_ids(value):
    """Index references explicitly present in the authorized input, including nested reports."""
    fields = {
        "artifact_id",
        "object_id",
        "version_id",
        "report_id",
        "patch_id",
        "task_id",
        "event_id",
        "message_sequence",
        "handoff_sequence",
        "anomaly_id",
        "action_id",
        "command_id",
    }
    found = {}
    stack = [value]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for k, v in value.items():
                if k in fields and isinstance(v, (str, int)):
                    found.setdefault(k, set()).add(str(v))
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(value, list):
            stack.extend(value)
    return {k: sorted(values) for k, values in sorted(found.items())}


def worker_graph(graph, actor):
    """Preserve this member's work, dependency closure and addressed duties."""
    work = graph["work"]
    selected = {k for k, row in work.items() if actor in (row["owner"], row["reviewer"])}
    selected.update(
        k for k, row in graph["duties"].items() if actor in (row["owner"], row["recipient"])
    )
    selected.update(edge[0] for edge in graph["collaboration"] if actor in edge[1:])
    pending = list(selected)
    while pending:
        current = pending.pop()
        for dep in (*work[current]["depends_on"], *work[current]["children"]):
            if dep not in selected:
                selected.add(dep)
                pending.append(dep)
    return {
        **graph,
        "work": {k: v for k, v in work.items() if k in selected},
        "duties": {k: v for k, v in graph["duties"].items() if k in selected},
        "collaboration": [e for e in graph["collaboration"] if e[0] in selected],
    }


def build(wire, *, actor, role, condition="T1", scope=""):
    validate_role(wire, actor, role)
    if condition not in ("T0", "T1"):
        raise ValueError("Unknown treatment")
    result = {**wire, "messages": []}
    manifest = {
        "version": "v230.1",
        "condition": condition,
        "scope": scope,
        "actor": actor,
        "role": role,
        "original_wire": identity(wire),
        "schema_hash": identity(wire.get("tools", [])),
        "items": [],
        "worker_graphs": [],
        "tool_pages": [],
        "duplicate_reads": [],
        "observation_deltas": [],
        "message_refs": [],
    }
    calls = {}
    prev = None
    prev_index = None
    reads = {}
    messages = {}
    names = {t["function"]["name"] for t in wire.get("tools", [])}
    for i, msg in enumerate(wire["messages"]):
        m = msg.copy()
        result["messages"].append(m)
        for c in msg.get("tool_calls") or []:
            calls[c["id"]] = c["function"]["name"]
        item = {"index": i, "role": msg["role"], "source_hash": identity(msg)}
        if msg.get("tool_call_id"):
            item["tool_call_id"] = msg["tool_call_id"]
        manifest["items"].append(item)
        v = object_text(msg.get("content"))
        if v is None:
            marker = " Active graph: "
            if (
                role == "worker"
                and condition == "T1"
                and msg["role"] == "user"
                and isinstance(msg.get("content"), str)
                and marker in msg["content"]
                and "dynamic_status" in names
            ):
                head, _, raw = msg["content"].rpartition(marker)
                graph = object_text(raw)
                if graph and set(graph) == {"members", "work", "collaboration", "duties"}:
                    projected = worker_graph(graph, actor)
                    m["content"] = head + marker + compact(projected)
                    manifest["worker_graphs"].append(
                        {
                            "index": i,
                            "source": identity(graph),
                            "shown_tasks": sorted(projected["work"]),
                            "omitted_tasks": sorted(set(graph["work"]) - set(projected["work"])),
                        }
                    )
            item["shown_hash"] = identity(m)
            continue
        obs = v.get("observation")
        if msg["role"] == "user" and isinstance(obs, dict):
            if obs.get("actor_id", actor) != actor:
                raise ValueError("Peer private observation")
            if condition == "T1":
                values = (
                    dict(obs)
                    if prev is None
                    else {k: x for k, x in obs.items() if k not in prev or prev[k] != x}
                )
                for field in ("messages", "handoffs"):
                    if not isinstance(values.get(field), list):
                        continue
                    indexed = []
                    for j, message in enumerate(values[field]):
                        key = (field, identity(message))
                        if key in messages:
                            indexed.append({"same_message_at": messages[key]})
                            manifest["message_refs"].append([i, field, j, messages[key]])
                        else:
                            messages[key] = [i, field, j]
                            indexed.append(message)
                    values[field] = indexed
                if prev is None:
                    v = {**v, "observation": values}
                else:
                    v = {k: x for k, x in v.items() if k != "observation"}
                    v["observation_delta"] = {
                        "inherits_observation_at_message": prev_index,
                        "changed": values,
                        "removed": sorted(set(prev) - set(obs)),
                    }
                    manifest["observation_deltas"].append(
                        {"index": i, "base": prev_index, "full_hash": identity(obs)}
                    )
                m["content"] = compact(v)
                prev = obs
                prev_index = i
        elif (
            msg["role"] == "tool"
            and isinstance(v.get("result"), dict)
            and v.get("ok") is True
            and condition == "T1"
        ):
            tool = calls.get(msg.get("tool_call_id"))
            body = v["result"]
            if (
                tool in ("read_file", "diff_workspace")
                and body.get("source_reference")
                and ("text" in body or "diff" in body)
            ):
                key = (tool, identity(body))
                old = reads.get(key)
                if old is None:
                    reads[key] = i
                elif len(compact(body)) > 256:
                    v = {
                        **v,
                        "result": {
                            "same_immutable_result_at_message": old,
                            "source_reference": body["source_reference"],
                        },
                    }
                    manifest["duplicate_reads"].append([i, old])
            elif (
                tool in ("run_tests", "run_patch_review_tests")
                and "read_test_result" in names
                and body.get("report_id")
                and body.get("body_sha256")
            ):
                page = body.get("page") or {}
                if (
                    isinstance(page.get("text"), str)
                    and len(page["text"]) > 500
                    and (
                        body.get("passed") is True
                        or (body.get("diagnostic_summary") or {}).get("failed_tests")
                    )
                ):
                    args = {"report_id": body["report_id"]}
                    if page.get("cursor"):
                        args["cursor"] = page["cursor"]
                    page = {k: x for k, x in page.items() if k != "text"}
                    page["retrieve"] = {"tool": "read_test_result", "arguments": args}
                    v = {**v, "result": {**body, "page": page}}
                    manifest["tool_pages"].append(
                        {
                            "index": i,
                            "source_reference": body.get("source_reference"),
                            "retrieve": args,
                        }
                    )
            m["content"] = compact(v)
        elif role == "osa" and i == 1 and condition == "T1":
            m["content"] = compact({k: v[k] for k in sorted(v)})
        item["shown_hash"] = identity(m)
        item["original_refs"] = visible_ids(object_text(msg.get("content")))
        item["shown_refs"] = visible_ids(object_text(m.get("content")))
    manifest.update(
        shown_wire=identity(result),
        base_hash=identity([wire["messages"][0], wire.get("tools", [])]),
    )
    return result, manifest


def recover_observations(wire):
    snapshots = {}
    message_index = {}
    for i, m in enumerate(wire["messages"]):
        if m["role"] != "user":
            continue
        v = object_text(m.get("content")) or {}
        if "observation_delta" in v:
            d = v["observation_delta"]
            snapshot = snapshots[d["inherits_observation_at_message"]].copy()
            for field in d["removed"]:
                del snapshot[field]
            fields = d["changed"]
        elif isinstance(v.get("observation"), dict):
            snapshot = {}
            fields = v["observation"]
        else:
            continue
        for field, value in fields.items():
            if field in ("messages", "handoffs") and isinstance(value, list):
                entries = []
                for j, x in enumerate(value):
                    if isinstance(x, dict) and set(x) == {"same_message_at"}:
                        x = message_index[tuple(x["same_message_at"])]
                    message_index[(i, field, j)] = x
                    entries.append(x)
                value = entries
            snapshot[field] = value
        snapshots[i] = snapshot
    return snapshots


def source_parts(wire, role):
    yield "schema", compact(wire.get("tools", []))
    for m in wire["messages"]:
        content = m.get("content") or ""
        v = object_text(content)
        if m["role"] == "system":
            yield "system", content
        elif role == "condenser":
            yield "summary", content
        elif m["role"] == "tool":
            yield "tool_observations", content
        elif m["role"] == "assistant":
            yield "work_history", content
        elif content.startswith("[Derived private history summary"):
            yield "summary", content
        elif v and role == "osa":
            for k, x in v.items():
                yield (
                    (
                        "project"
                        if k in ("anomaly", "subject", "evidence", "anomaly_id")
                        else "organization"
                    ),
                    compact(x),
                )
        elif v and isinstance(v.get("observation"), dict):
            for k, x in v["observation"].items():
                cat = (
                    "peer_messages"
                    if k in ("messages", "older_message_sequences")
                    else "organization"
                    if k in GRAPH_FIELDS
                    else "work_history"
                    if k == "personal_workbench"
                    else "project"
                )
                yield cat, compact(x)
            for k, x in v.items():
                if k != "observation":
                    yield ("system" if k == "role_task" else "other"), compact(x)
        elif content.startswith(
            (
                "Active organization",
                "Work observation:",
                "CONTINUATION STAGE:",
                "Autonomous organization",
            )
        ):
            yield "organization", content
        else:
            yield "other", content
        if m.get("tool_calls"):
            yield "work_history", compact(m["tool_calls"])
