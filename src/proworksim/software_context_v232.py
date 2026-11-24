"""Version-bound T1 snapshots for current organization experiments."""

import json
from collections import Counter
from .software_context_builder_v230 import build, compact, identity, object_text, GRAPH_FIELDS

DEFAULT_CONTEXT = "T1"
CHECK_INTERVAL = 8


def state_id(actor, state):
    return identity([actor, state])


def restore_delta(previous, delta, actor, base_index, anchor, messages):
    if (
        delta["inherits_observation_at_message"] != base_index
        or delta["base_state_version"] != state_id(actor, previous)
        or delta["snapshot_version"] != anchor
    ):
        raise ValueError("Wrong snapshot or delta base")
    state = previous.copy()
    for k in delta["removed"]:
        del state[k]
    for k, v in delta["changed"].items():
        if k in ("messages", "handoffs") and isinstance(v, list):
            resolved = []
            for item in v:
                if isinstance(item, dict) and set(item) == {"same_message_at"}:
                    item = messages[tuple(item["same_message_at"])]
                resolved.append(item)
            v = resolved
        state[k] = v
    if state_id(actor, state) != delta["state_version"]:
        raise ValueError("Delta state checksum mismatch")
    return state


def checked_context(raw, actor, role, graph_version, history=(), interval=CHECK_INTERVAL):
    if interval < 1:
        raise ValueError("Snapshot interval must be positive")
    shown, meta = build(raw, actor=actor, role=role, condition=DEFAULT_CONTEXT)
    previous = None
    base_index = anchor = None
    count = 0
    refs = {}
    records = []
    for i, (original, msg) in enumerate(zip(raw["messages"], shown["messages"])):
        text = original.get("content") or ""
        if isinstance(text, str) and text.startswith("[Derived private history summary"):
            previous = None
        src = object_text(text) or {}
        obs = src.get("observation")
        if original["role"] != "user" or not isinstance(obs, dict):
            continue
        if obs.get("actor_id", actor) != actor:
            raise ValueError("Peer-private snapshot")
        encoded = object_text(msg["content"])
        version = state_id(actor, obs)
        reason = "new_history" if previous is None else "periodic" if count >= interval else None
        if not reason:
            try:
                d = encoded["observation_delta"]
                d.update(
                    base_state_version=state_id(actor, previous),
                    state_version=version,
                    snapshot_version=anchor,
                )
                restored = restore_delta(previous, d, actor, base_index, anchor, refs)
                if compact(restored) != compact(obs):
                    raise ValueError("State drift")
            except (ValueError, KeyError, TypeError):
                reason = "recovery_full"
        if reason:
            encoded = {
                **src,
                "observation": obs,
                "state_version": version,
                "snapshot_version": version,
            }
            count = 0
            refs = {}
            anchor = version
        for field in ("messages", "handoffs"):
            if isinstance(obs.get(field), list):
                refs.update({(i, field, j): item for j, item in enumerate(obs[field])})
        msg["content"] = compact(encoded)
        records.append(
            dict(
                index=i,
                version=version,
                anchor=anchor,
                base=base_index if not reason else None,
                full=reason,
            )
        )
        previous, base_index = obs, i
        count += 1
    if role == "osa":
        view = json.loads(shown["messages"][1]["content"])
        view["public_organization_history"] = list(history)
        shown["messages"][1]["content"] = compact(view)
    if role == "worker" and shown["messages"] and graph_version is not None:
        # Keep the native system + tool prefix intact. Attach live version to the last worker observation.
        if records:
            i = records[-1]["index"]
            data = json.loads(shown["messages"][i]["content"])
            data["active_organization_version"] = graph_version
            shown["messages"][i]["content"] = compact(data)
        else:
            # Do not append a user message after an unfinished tool call.
            # The role-specific system header is safe even for an incomplete-prefix count.
            shown["messages"][0] = {
                **shown["messages"][0],
                "content": shown["messages"][0]["content"]
                + f"\nActive organization version: {graph_version}.",
            }
    for item, m in zip(meta["items"], shown["messages"]):
        item["shown_hash"] = identity(m)
    meta.update(
        version="v232-checked-T1",
        shown_wire=identity(shown),
        snapshots=records,
        org_graph_version=graph_version,
        interval=interval,
    )
    return shown, meta


def source_estimates(wire, role, counter):
    amounts = Counter()

    def add(name, s):
        amounts[name] += counter(s if isinstance(s, str) else compact(s))

    add("tool_schema", wire.get("tools", []))
    tools = {}
    for msg in wire["messages"]:
        for call in msg.get("tool_calls") or []:
            tools[call["id"]] = call["function"]["name"]
            add("action_history", call)
        text = msg.get("content") or ""
        data = object_text(text) or {}
        if msg["role"] == "system":
            add("system", text)
        elif role == "condenser" or (
            isinstance(text, str) and text.startswith("[Derived private history summary")
        ):
            add("history_summary", text)
        elif msg["role"] == "assistant":
            add("action_history", text)
        elif msg["role"] == "tool":
            name = tools.get(msg.get("tool_call_id"))
            add(
                "tests"
                if name in ("run_tests", "run_patch_review_tests", "read_test_result")
                else "files"
                if name
                in (
                    "search_repository",
                    "read_file",
                    "replace_file",
                    "list_files",
                    "diff_workspace",
                    "search_file",
                )
                else "other_tool_feedback",
                text,
            )
        elif role == "osa" and "options" in data:
            for k, v in data.items():
                add(
                    "anomaly"
                    if k in ("anomaly_id", "anomaly", "subject", "evidence")
                    else "organization",
                    v,
                )
        elif "observation" in data or "observation_delta" in data:
            d = data.get("observation_delta", {})
            fields = data.get("observation", d.get("changed", {}))
            for k, v in fields.items():
                add(
                    "peer_messages"
                    if k in ("messages", "older_message_sequences")
                    else "organization"
                    if k in GRAPH_FIELDS
                    else "action_history"
                    if k == "personal_workbench"
                    else "project",
                    v,
                )
            other = {k: v for k, v in data.items() if k not in ("observation", "observation_delta")}
            if d:
                other.update({k: v for k, v in d.items() if k != "changed"})
            if other:
                add("state_metadata", other)
        elif isinstance(text, str) and text.startswith("Work observation:"):
            add("anomaly", text)
        elif isinstance(text, str) and "Active graph:" in text:
            add("organization", text)
        else:
            add("other", text)
    return amounts
