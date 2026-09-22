"""Operating-tool compatibility adapter over canonical condition facts.

Blockers are a disposable one-way projection; no transition reads their cache.
"""

import copy

from .core.conditions import apply_response, reopen_work, supersede_condition
from .core.projections import (
    derive_blocker_view,
    derive_current_work_view,
    rebuild_projections,
)

TERMINAL_WORK_STATUSES = frozenset({"accepted", "superseded", "cancelled", "withdrawn"})


def _item(state, work_item_id):
    item = state["work_items"].get(work_item_id)
    if item is None:
        raise ValueError("Unknown work item for blocker")
    return item


def _blocker(state, blocker_id):
    blocker = derive_blocker_view(state).get(blocker_id)
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


def reopen_if_ready(state, work_item_id):
    return reopen_work(state, work_item_id)


def create_blocker(
    state, item, kind, requested_role, required_scope_version, detail, request_id=None
):
    """Create one explicit condition; status and legacy records are projections."""
    wid = item["work_item_id"]
    if state["work_items"].get(wid) is not item:
        raise ValueError("Blocker must refer to the current work item")
    view = derive_current_work_view(state)[wid]
    if not view["is_current"] or view["status"] in TERMINAL_WORK_STATUSES | {"in_review"}:
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
    index = len(state.get("condition_specs", {})) + 1
    ids = {c.get("blocker_id") for c in state.get("condition_specs", {}).values()}
    while f"blocker-{index}" in ids or f"condition-{index}" in state.get("condition_specs", {}):
        index += 1
    bid, cid = f"blocker-{index}", f"condition-{index}"
    candidate = {
        "blocker_id": bid,
        "condition_id": cid,
        "work_item_id": wid,
        "kind": kind,
        "requested_role": requested_role,
        "status": "open",
        "request_id": None,
    }
    if request_id is not None:
        _validate_binding(state, candidate, request_id, item["owner_role"], wid)
    condition.update(
        condition_id=cid,
        blocker_id=bid,
        request_id=request_id,
        detail=detail,
        requested_role=requested_role,
        created_at=state["clock"],
        history=[{"at": state["clock"], "event": "created", "request_id": request_id}],
    )
    state.setdefault("condition_specs", {})[cid] = condition
    rebuild_projections(state)
    return copy.deepcopy(state["blockers"][bid])


def _validate_binding(state, blocker, request_id, actor, work_item_id):
    item = _item(state, work_item_id)
    view = derive_current_work_view(state)[work_item_id]
    if (
        item["owner_role"] != actor
        or not view["is_current"]
        or view["status"] in TERMINAL_WORK_STATUSES
    ):
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
        other.get("request_id") == request_id and other["work_item_id"] != work_item_id
        for other in state.get("condition_specs", {}).values()
    ):
        raise ValueError("A request cannot be shared across work items")


def bind_request(state, blocker_id, request_id, actor, work_item_id):
    blocker = _blocker(state, blocker_id)
    _validate_binding(state, blocker, request_id, actor, work_item_id)
    if blocker["request_id"] != request_id:
        condition = state["condition_specs"][blocker["condition_id"]]
        condition["request_id"] = request_id
        condition["requested_role"] = next(
            r for r in _request(state, request_id)["recipients"] if r in condition["providers"]
        )
        condition.setdefault("history", []).append(
            {
                "at": state["clock"],
                "event": "bound",
                "request_id": request_id,
            }
        )
    rebuild_projections(state)
    return copy.deepcopy(state["blockers"][blocker_id])


def resolve_for_reply(state, request_id, responder, topic, scope_version, resolution_ref):
    if not resolution_ref:
        raise ValueError("A blocker resolution needs a visible resolution reference")
    resolved = []
    for blocker in derive_blocker_view(state).values():
        if blocker["status"] != "open" or blocker["request_id"] != request_id:
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
        result = apply_response(state, response)
        if blocker["condition_id"] in result["resolved_conditions"]:
            resolved.append(blocker["blocker_id"])
    return resolved


def supersede_blocker(state, blocker_id, reason, replacement_ref=None):
    blocker = _blocker(state, blocker_id)
    supersede_condition(state, blocker["condition_id"], reason, replacement_ref)
    return copy.deepcopy(state["blockers"][blocker_id])


def mark_unavailable(state, blocker_id, reason, resolution_ref=None):
    """Explicit provider inability fact, used by controlled scenario adapters."""
    blocker = _blocker(state, blocker_id)
    if blocker["status"] != "open":
        raise ValueError("Only an unresolved blocker can be marked unavailable")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Unavailability requires a concrete reason")
    condition = state["condition_specs"][blocker["condition_id"]]
    condition.setdefault("history", []).append(
        {
            "at": state["clock"],
            "event": "unavailability_recorded",
            "reason": reason,
            "provider": blocker["requested_role"],
            "resolution_ref": copy.deepcopy(resolution_ref),
        }
    )
    rebuild_projections(state)
    return copy.deepcopy(state["blockers"][blocker_id])
