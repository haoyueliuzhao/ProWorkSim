"""Scoped blockers whose reply effects require explicit request/version bindings.

Helpers mutate state only: no messages are sent and free text is not interpreted
as confirmation. Every status transition preserves the earlier history entries.
"""

import copy

from .core.conditions import (
    apply_response,
    match_response,
    reopen_work,
    supersede_condition,
)
from .core.types import CheckStatus

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


def _matches_request(state, blocker, request, actor, work_item_id):
    condition = state.get("condition_specs", {}).get(blocker.get("condition_id"), {})
    providers = condition.get("providers", [blocker["requested_role"]])
    return (
        request is not None
        and blocker["work_item_id"] == work_item_id
        and request["sender"] == actor
        and any(provider in request["recipients"] for provider in providers)
        and request.get("topic", request.get("subject")) == blocker["kind"]
        and request.get("work_item_id", work_item_id) == work_item_id
    )


def _transition(state, blocker, status, **details):
    blocker["status"] = status
    blocker["history"].append({"at": state["clock"], "status": status, **copy.deepcopy(details)})


def reopen_if_ready(state, work_item_id):
    return reopen_work(state, work_item_id)


def create_blocker(
    state, item, kind, requested_role, required_scope_version, detail, request_id=None
):
    """Create one condition; never replace another condition or its history."""
    if state["work_items"].get(item["work_item_id"]) is not item:
        raise ValueError("Blocker must refer to the current work item")
    if item["status"] in TERMINAL_WORK_STATUSES | {"in_review"}:
        raise ValueError("This work cannot receive new blockers")
    from .adapters.communication import condition_template

    condition = condition_template(state, item, kind, requested_role, required_scope_version)
    if requested_role not in {role["role_id"] for role in state["roles"]}:
        raise ValueError("Unknown requested role")
    if required_scope_version is not None and (
        type(required_scope_version) is not int or required_scope_version < 1
    ):
        raise ValueError("required_scope_version must be a positive integer or null")
    if not isinstance(detail, str) or not detail.strip() or len(detail) > 10000:
        raise ValueError("A concrete blocker detail of up to 10000 characters is required")
    records = state.get("blockers", {})
    index = len(records) + 1
    while f"blocker-{index}" in records:
        index += 1
    blocker = {
        "blocker_id": f"blocker-{index}",
        "work_item_id": item["work_item_id"],
        "condition_id": f"condition-{index}",
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
    condition.update(
        condition_id=blocker["condition_id"],
        blocker_id=blocker["blocker_id"],
        request_id=blocker["request_id"],
        history=copy.deepcopy(blocker["history"]),
    )
    state.setdefault("condition_specs", {})[condition["condition_id"]] = condition
    state.setdefault("blockers", {})[blocker["blocker_id"]] = blocker
    item.setdefault("blocker_ids", []).append(blocker["blocker_id"])
    item["status"] = "blocked"
    return copy.deepcopy(blocker)


def _validate_binding(state, blocker, request_id, actor, work_item_id):
    item = _item(state, work_item_id)
    if item["owner_role"] != actor or item["status"] in TERMINAL_WORK_STATUSES:
        raise ValueError("Only the current work owner can bind a blocker request")
    if blocker["status"] not in {"open", "unavailable"}:
        raise ValueError("Only an unresolved blocker can receive a request")
    if blocker["status"] == "unavailable" and blocker["request_id"] == request_id:
        raise ValueError("Recovery requires a new request, not replay of an unavailable response")
    if blocker["status"] == "open" and blocker["request_id"] not in (None, request_id):
        raise ValueError("A blocker request cannot be replaced; create a new blocker")
    if not _matches_request(state, blocker, _request(state, request_id), actor, work_item_id):
        raise ValueError("Request does not match blocker work, sender, recipient, or topic")
    if any(
        other["request_id"] == request_id and other["work_item_id"] != work_item_id
        for other in state.get("blockers", {}).values()
    ):
        raise ValueError("A request cannot be shared across work items")


def bind_request(state, blocker_id, request_id, actor, work_item_id):
    blocker = _blocker(state, blocker_id)
    _validate_binding(state, blocker, request_id, actor, work_item_id)
    condition = state.get("condition_specs", {}).get(blocker.get("condition_id"))
    if blocker["request_id"] != request_id:
        if blocker["request_id"]:
            blocker.setdefault("prior_request_ids", []).append(blocker["request_id"])
        blocker["request_id"] = request_id
        recipient = next(
            r for r in _request(state, request_id)["recipients"] if r in condition["providers"]
        )
        blocker["requested_role"] = recipient
        _transition(state, blocker, "open", request_id=request_id)
        if condition:
            condition["request_id"] = request_id
            condition["status"] = "open"
            condition["history"].append(
                {"at": state["clock"], "status": "open", "request_id": request_id}
            )
    return copy.deepcopy(blocker)


def resolve_for_reply(state, request_id, responder, topic, scope_version, resolution_ref):
    """Legacy tool adapter; only generic evidence checks can satisfy conditions."""
    if not resolution_ref:
        raise ValueError("A blocker resolution needs a visible resolution reference")
    resolved = []
    for blocker in state.get("blockers", {}).values():
        # Existing unavailable events cannot be replayed to represent recovery.
        if blocker["status"] != "open" or blocker["request_id"] != request_id:
            continue
        condition = state.get("condition_specs", {}).get(blocker.get("condition_id"))
        if condition is None:
            continue
        response = {
            "response_id": f"{request_id}:{resolution_ref.get('message_id', 'reply')}",
            "request_id": request_id,
            "responder": responder,
            "work_item_id": blocker["work_item_id"],
            "requirement_version": blocker["creation_requirement_version"],
            "condition_version": scope_version,
            "purpose": topic,
            "reference": resolution_ref.get("reference"),
            "status": "delivered",
        }
        if match_response(state, condition, response).status != CheckStatus.PASS:
            continue
        apply_response(state, response)
        # Preserve the legacy tool's exact resolution record shape.
        blocker["resolution_ref"] = copy.deepcopy(resolution_ref)
        resolved.append(blocker["blocker_id"])
    return resolved


def supersede_blocker(state, blocker_id, reason, replacement_ref=None):
    """Retire an obsolete condition without representing it as a satisfied request."""
    blocker = _blocker(state, blocker_id)
    if blocker["status"] not in {"open", "unavailable"}:
        raise ValueError("Only outstanding blockers can be superseded")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Supersession requires a concrete reason")
    if blocker.get("condition_id") in state.get("condition_specs", {}):
        supersede_condition(state, blocker["condition_id"], reason, replacement_ref)
    else:
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
    condition = state.get("condition_specs", {}).get(blocker.get("condition_id"))
    if condition:
        condition["status"] = "unavailable"
        if blocker["requested_role"] not in condition["unavailable_providers"]:
            condition["unavailable_providers"].append(blocker["requested_role"])
        condition["history"].append(
            {"at": state["clock"], "status": "unavailable", "reason": reason}
        )
    return copy.deepcopy(blocker)
