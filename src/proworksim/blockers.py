"""Scoped blockers whose reply effects require explicit request/version bindings.

Helpers mutate state only: no messages are sent and free text is not interpreted
as confirmation. Every status transition preserves the earlier history entries.
"""

import copy

KINDS = frozenset({"scope", "audience", "evidence"})
TERMINAL_WORK_STATUSES = frozenset({"accepted", "superseded", "cancelled", "withdrawn"})


def _item(state, work_item_id):
    item = state["work_items"].get(work_item_id)
    if item is None:
        raise ValueError("Unknown work item for blocker")
    return item


def _blocker(state, blocker_id):
    blocker = state.get("blockers", {}).get(blocker_id)
    if blocker is None:
        raise ValueError("Unknown blocker")
    return blocker


def _request(state, request_id):
    return next(
        (message for message in state.get("messages", []) if message["message_id"] == request_id),
        None,
    )


def _matches_request(blocker, request, actor, work_item_id):
    return (
        request is not None
        and blocker["work_item_id"] == work_item_id
        and request["sender"] == actor
        and blocker["requested_role"] in request["recipients"]
        and request.get("topic", request.get("subject")) == blocker["kind"]
        and request.get("work_item_id", work_item_id) == work_item_id
    )


def _transition(state, blocker, status, **details):
    blocker["status"] = status
    blocker["history"].append({"at": state["clock"], "status": status, **copy.deepcopy(details)})


def reopen_if_ready(state, work_item_id):
    """Reopen only a blocked work item with every condition and predecessor met."""
    item = _item(state, work_item_id)
    if item["status"] != "blocked":
        return False
    if any(
        state.get("blockers", {}).get(blocker_id, {}).get("status")
        not in {"resolved", "superseded"}
        for blocker_id in item.get("blocker_ids", [])
    ):
        return False
    if any(
        state["work_items"].get(dependency, {}).get("status") != "accepted"
        for dependency in item.get("dependencies", [])
    ):
        return False
    item["status"] = "open"
    item["blocker"] = None
    return True


def create_blocker(
    state, item, kind, requested_role, required_scope_version, detail, request_id=None
):
    """Create one condition; never replace another condition or its history."""
    if state["work_items"].get(item["work_item_id"]) is not item:
        raise ValueError("Blocker must refer to the current work item")
    if item["status"] in TERMINAL_WORK_STATUSES | {"in_review"}:
        raise ValueError("This work cannot receive new blockers")
    if kind not in KINDS:
        raise ValueError("Blocker kind must be scope, audience, or evidence")
    if requested_role not in {role["role_id"] for role in state["roles"]}:
        raise ValueError("Unknown requested role")
    if required_scope_version is not None and (
        type(required_scope_version) is not int or required_scope_version < 1
    ):
        raise ValueError("required_scope_version must be a positive integer or null")
    if kind == "scope" and required_scope_version is None:
        raise ValueError("A scope blocker requires an explicit applicable version")
    if not isinstance(detail, str) or not detail.strip() or len(detail) > 10000:
        raise ValueError("A concrete blocker detail of up to 10000 characters is required")
    records = state.get("blockers", {})
    index = len(records) + 1
    while f"blocker-{index}" in records:
        index += 1
    blocker = {
        "blocker_id": f"blocker-{index}",
        "work_item_id": item["work_item_id"],
        "kind": kind,
        "requested_role": requested_role,
        "required_scope_version": required_scope_version,
        "creation_requirement_version": item["requirement_version"],
        "detail": detail,
        "created_at": state["clock"],
        "status": "open",
        "request_id": None,
        "resolution_ref": None,
        "history": [{"at": state["clock"], "status": "open"}],
    }
    # Optional binding is checked before any mutation, including item status.
    if request_id is not None:
        _validate_binding(state, blocker, request_id, item["owner_role"], item["work_item_id"])
        blocker["request_id"] = request_id
        blocker["history"].append(
            {"at": state["clock"], "status": "open", "request_id": request_id}
        )
    state.setdefault("blockers", {})[blocker["blocker_id"]] = blocker
    item.setdefault("blocker_ids", []).append(blocker["blocker_id"])
    item["status"] = "blocked"
    return copy.deepcopy(blocker)


def _validate_binding(state, blocker, request_id, actor, work_item_id):
    item = _item(state, work_item_id)
    if item["owner_role"] != actor or item["status"] in TERMINAL_WORK_STATUSES:
        raise ValueError("Only the current work owner can bind a blocker request")
    if blocker["status"] != "open":
        raise ValueError("Only an unresolved blocker can receive a request")
    if blocker["request_id"] not in (None, request_id):
        raise ValueError("A blocker request cannot be replaced; create a new blocker")
    if not _matches_request(blocker, _request(state, request_id), actor, work_item_id):
        raise ValueError("Request does not match blocker work, sender, recipient, or topic")
    if any(
        other["request_id"] == request_id and other["work_item_id"] != work_item_id
        for other in state.get("blockers", {}).values()
    ):
        raise ValueError("A request cannot be shared across work items")


def bind_request(state, blocker_id, request_id, actor, work_item_id):
    blocker = _blocker(state, blocker_id)
    _validate_binding(state, blocker, request_id, actor, work_item_id)
    if blocker["request_id"] is None:
        blocker["request_id"] = request_id
        blocker["history"].append(
            {"at": state["clock"], "status": "open", "request_id": request_id}
        )
    return copy.deepcopy(blocker)


def resolve_for_reply(state, request_id, responder, topic, scope_version, resolution_ref):
    """Resolve only explicitly bound, current conditions satisfied by this reply."""
    if not resolution_ref:
        raise ValueError("A blocker resolution needs a visible resolution reference")
    request = _request(state, request_id)
    resolved = []
    for blocker in state.get("blockers", {}).values():
        item = _item(state, blocker["work_item_id"])
        if (
            blocker["status"] != "open"
            or blocker["request_id"] != request_id
            or blocker["requested_role"] != responder
            or blocker["kind"] != topic
            or item["status"] in TERMINAL_WORK_STATUSES
            or item["requirement_version"] != blocker["creation_requirement_version"]
            or not _matches_request(blocker, request, item["owner_role"], item["work_item_id"])
        ):
            continue
        required = blocker["required_scope_version"]
        if required is not None and (type(scope_version) is not int or required != scope_version):
            continue
        blocker["resolution_ref"] = copy.deepcopy(resolution_ref)
        _transition(state, blocker, "resolved", responder=responder, resolution_ref=resolution_ref)
        resolved.append(blocker["blocker_id"])
        reopen_if_ready(state, item["work_item_id"])
    return resolved


def supersede_blocker(state, blocker_id, reason, replacement_ref=None):
    """Retire an obsolete condition without representing it as a satisfied request."""
    blocker = _blocker(state, blocker_id)
    if blocker["status"] not in {"open", "unavailable"}:
        raise ValueError("Only outstanding blockers can be superseded")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Supersession requires a concrete reason")
    _transition(state, blocker, "superseded", reason=reason, replacement_ref=replacement_ref)
    reopen_if_ready(state, blocker["work_item_id"])
    return copy.deepcopy(blocker)


def mark_unavailable(state, blocker_id, reason, resolution_ref=None):
    """Record unavailable information; keep the work blocked and preserve history."""
    blocker = _blocker(state, blocker_id)
    if blocker["status"] != "open":
        raise ValueError("Only an unresolved blocker can be marked unavailable")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Unavailability requires a concrete reason")
    blocker["resolution_ref"] = copy.deepcopy(resolution_ref)
    _transition(state, blocker, "unavailable", reason=reason, resolution_ref=resolution_ref)
    return copy.deepcopy(blocker)
