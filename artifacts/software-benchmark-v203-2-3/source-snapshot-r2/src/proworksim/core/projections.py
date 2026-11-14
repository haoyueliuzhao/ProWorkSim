"""Pure, replaceable views over declarative obligations and recorded events.

Condition histories contain binding, supersession, restoration and response receipt
facts. Response outcomes and all work/blocker status fields are caches. This is a
checkpointed state model, not a promise of reconstruction from arbitrary old logs.
"""

import copy

CONDITION_CACHE_FIELDS = ("status", "unavailable_providers", "resolution_ref", "response_checks")
WORK_CACHE_FIELDS = ("status", "blocker", "blocker_ids", "applicability")


def _current_id(state, wid):
    seen = set()
    while wid in state.get("work_replacements", {}):
        if wid in seen:
            raise ValueError("Cyclic work replacement")
        seen.add(wid)
        wid = state["work_replacements"][wid]
    return wid


def derive_condition_view(state):
    """Fold canonical condition events without reading any status cache."""
    from .conditions import _match_response

    result = {}
    for cid, definition in state.get("condition_specs", {}).items():
        view = {
            "condition_id": cid,
            "work_item_id": definition["work_item_id"],
            "status": "open",
            "request_id": definition.get("request_id"),
            "unavailable_providers": [],
            "resolution_ref": None,
            "response_checks": {},
        }
        # A binding is a definition fact. History preserves all earlier bindings.
        bindings = [entry for entry in definition.get("history", []) if "request_id" in entry]
        if bindings:
            view["request_id"] = None
        for entry in definition.get("history", []):
            event = entry.get("event")
            if event in {"created", "bound"} or (event is None and entry.get("status") == "open"):
                if "request_id" in entry:
                    view["request_id"] = entry["request_id"]
                    view["status"] = "open"
                    view["resolution_ref"] = None
            elif event == "superseded" or (event is None and entry.get("status") == "superseded"):
                if view["status"] in {"open", "unavailable"}:
                    view["status"] = "superseded"
            elif event == "information_available":
                provider = entry.get("provider")
                if provider in view["unavailable_providers"]:
                    view["unavailable_providers"].remove(provider)
            elif event == "unavailability_recorded":
                view["status"] = "unavailable"
                provider = entry.get("provider")
                if provider and provider not in view["unavailable_providers"]:
                    view["unavailable_providers"].append(provider)
                view["resolution_ref"] = copy.deepcopy(entry.get("resolution_ref"))
            elif event == "response_received":
                response = state.get("raw_condition_responses", {}).get(entry["response_id"])
                if response is None:
                    raise ValueError("Condition receipt refers to a missing raw response")
                condition = {**definition, **view}
                check = _match_response(state, condition, response, replay=True)
                view["response_checks"][entry["response_id"]] = check.to_dict()
                if check.status.value == "PASS":
                    view["status"] = "resolved"
                    view["resolution_ref"] = {
                        "message_id": response["response_id"],
                        "reference": copy.deepcopy(response.get("reference")),
                    }
                elif "provider_currently_unavailable" in check.reasons:
                    view["status"] = "unavailable"
                    if response["responder"] not in view["unavailable_providers"]:
                        view["unavailable_providers"].append(response["responder"])
                    view["resolution_ref"] = {
                        "message_id": response["response_id"],
                        "reference": copy.deepcopy(response.get("reference")),
                    }
        result[cid] = view
    return result


def _submission_state(item):
    latest = next(reversed(item.get("submissions", [])), None)
    if latest is None:
        return "none"
    review = latest.get("review") or {}
    decision = review.get("decision")
    if decision in {"accepted", "revision_required", "withdrawn"}:
        return decision
    if latest.get("invalidated"):
        return "invalidated"
    return "pending"


def submission_versions_current(state, item, submission):
    """One predicate for approval readiness and the institutional transition."""
    return (
        submission.get("requirement_version") == item["requirement_version"]
        and submission.get("required_credentials", []) == item.get("required_credentials", [])
        and all(
            state.get("artifacts", {}).get(aid, {}).get("current_version") == version
            for aid, version in submission.get("artifact_versions", {}).items()
        )
    )


def derive_current_work_view(state):
    """Return work readiness including historical obligations; never mutate facts."""
    from .issues import derive_issue_view

    conditions = derive_condition_view(state)
    issues = derive_issue_view(state)
    result = {}
    for wid, item in state.get("work_items", {}).items():
        current = _current_id(state, wid) == wid
        submission_state = _submission_state(item)
        submission = next(reversed(item.get("submissions", [])), None)
        pending_id = submission["submission_id"] if submission_state == "pending" else None
        status = {
            "none": None,
            "pending": "in_review",
            "accepted": "accepted",
            "revision_required": "revision_required",
            "withdrawn": "in_progress",
            "invalidated": "in_progress",
        }[submission_state]
        if not current and status != "accepted":
            status = "superseded"
        elif item.get("cancelled_at") is not None:
            status = "cancelled"
        if status is None:
            status = "in_progress" if item.get("artifact_edits") else "open"
        obligations = [view for view in conditions.values() if view["work_item_id"] == wid]
        outstanding = [view for view in obligations if view["status"] in {"open", "unavailable"}]
        result[wid] = {
            "work_item_id": wid,
            "is_current": current,
            "status": status,
            "submission_state": submission_state,
            "pending_submission_id": pending_id,
            "submission_versions_current": (
                submission_versions_current(state, item, submission) if submission else None
            ),
            "applicability": "current" if current else "superseded_requirements",
            "outstanding_issue_ids": [iid for iid, issue in issues.items()
                                      if issue["work_id"] == wid and issue["blocks_approval"]],
            "condition_ids": [view["condition_id"] for view in obligations],
            "outstanding_condition_ids": [view["condition_id"] for view in outstanding],
            "blocker_ids": [
                state["condition_specs"][view["condition_id"]]["blocker_id"]
                for view in obligations
                if state["condition_specs"][view["condition_id"]].get("blocker_id")
            ],
        }
    for wid, view in result.items():
        item = state["work_items"][wid]
        ready = all(
            result.get(_current_id(state, dep), {}).get("status") == "accepted"
            for dep in item.get("dependencies", [])
        )
        view["dependencies_ready"] = ready
        if view["is_current"] and view["status"] not in {"accepted", "cancelled"}:
            if view["outstanding_condition_ids"]:
                view["status"] = "blocked"
            elif not ready:
                view["status"] = "waiting_dependencies"
        enabled = []
        if view["is_current"] and view["status"] != "cancelled":
            if view["pending_submission_id"] is not None:
                if (
                    ready
                    and not view["outstanding_condition_ids"]
                    and not view["outstanding_issue_ids"]
                    and view["submission_versions_current"]
                ):
                    enabled.append("approve")
                enabled.append("withdraw")
            elif (
                ready
                and not view["outstanding_condition_ids"]
                and view["status"] in {"open", "in_progress", "revision_required"}
            ):
                enabled.append("submit")
        view["enabled_actions"] = enabled
        view["blocker"] = None
        if view["outstanding_condition_ids"]:
            definition = state["condition_specs"][view["outstanding_condition_ids"][0]]
            view["blocker"] = definition.get("detail")
    return result


def derive_blocker_view(state, conditions=None):
    conditions = conditions if conditions is not None else derive_condition_view(state)
    result = {}
    for cid, definition in state.get("condition_specs", {}).items():
        bid = definition.get("blocker_id")
        if not bid:
            continue
        view = conditions[cid]
        result[bid] = {
            "blocker_id": bid,
            "condition_id": cid,
            "work_item_id": definition["work_item_id"],
            "kind": definition["purpose"],
            "requested_role": definition.get("requested_role", definition["providers"][0]),
            "required_scope_version": definition.get("expected_version"),
            "creation_requirement_version": definition["requirement_version"],
            "detail": definition.get("detail", "Explicit prerequisite"),
            "created_at": definition.get("created_at", 0),
            "request_id": view["request_id"],
            "status": view["status"],
            "resolution_ref": copy.deepcopy(view["resolution_ref"]),
            "history": copy.deepcopy(definition.get("history", [])),
        }
        prior = [
            entry["request_id"]
            for entry in definition.get("history", [])
            if entry.get("request_id") and entry["request_id"] != view["request_id"]
        ]
        if prior:
            result[bid]["prior_request_ids"] = list(dict.fromkeys(prior))
    return result


def projection_frame_paths():
    """Static field-scoped frame contract, including caches for newly created IDs."""
    return (
        (("blockers",), ("condition_responses",))
        + tuple(("condition_specs", "*", field) for field in CONDITION_CACHE_FIELDS)
        + tuple(("work_items", "*", field) for field in WORK_CACHE_FIELDS)
    )


def projection_paths(state):
    return (
        (("blockers",), ("condition_responses",))
        + tuple(
            ("condition_specs", cid, field)
            for cid in state.get("condition_specs", {})
            for field in CONDITION_CACHE_FIELDS
        )
        + tuple(
            ("work_items", wid, field)
            for wid in state.get("work_items", {})
            for field in WORK_CACHE_FIELDS
        )
    )


def rebuild_projections(state):
    conditions = derive_condition_view(state)
    work = derive_current_work_view(state)
    for cid, view in conditions.items():
        for field in CONDITION_CACHE_FIELDS:
            state["condition_specs"][cid][field] = copy.deepcopy(view[field])
    state["blockers"] = derive_blocker_view(state, conditions)
    outcomes = {}
    for response_id in state.get("raw_condition_responses", {}):
        checks = {
            cid: copy.deepcopy(view["response_checks"][response_id])
            for cid, view in conditions.items()
            if response_id in view["response_checks"]
        }
        resolved = [cid for cid, check in checks.items() if check["status"] == "PASS"]
        outcomes[response_id] = {
            "response_id": response_id,
            "checks": checks,
            "resolved_conditions": resolved,
            "reopened_work_items": sorted(
                {
                    conditions[cid]["work_item_id"]
                    for cid in resolved
                    if work[conditions[cid]["work_item_id"]]["status"] == "open"
                }
            ),
        }
    state["condition_responses"] = outcomes
    for wid, view in work.items():
        for field in WORK_CACHE_FIELDS:
            state["work_items"][wid][field] = copy.deepcopy(view[field])
    return {"conditions": conditions, "work": work}


def remove_projection_caches(state):
    for path in projection_paths(state):
        target = state
        for key in path[:-1]:
            target = target[key]
        target.pop(path[-1], None)


def corrupt_projection_caches(state):
    for path in projection_paths(state):
        target = state
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = "CORRUPTED_CACHE"


def record_artifact_edit(state, actor, artifact_id, version_id):
    """Record an edit fact; invalidating a pending submission preserves its bytes."""
    for wid, view in derive_current_work_view(state).items():
        item = state["work_items"][wid]
        if not view["is_current"] or artifact_id not in item.get("deliverables", []):
            continue
        item.setdefault("artifact_edits", []).append(
            {
                "actor_id": actor,
                "artifact_id": artifact_id,
                "version_id": version_id,
                "at": state["clock"],
            }
        )
        if view["pending_submission_id"] is not None:
            item["submissions"][-1].update(
                invalidated=True, invalidation_reason="deliverable_edited"
            )
    rebuild_projections(state)
