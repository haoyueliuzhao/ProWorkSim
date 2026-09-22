"""State-only work obligations and version-pinned submissions.

These transitions enforce identity and institutional authority. They do not read
files, compute domain answers, or decide whether a deliverable is substantively
correct. Artifact bytes and unrelated work are outside their mutation scope.
"""

import copy

from ..policies.organization import require_authority
from .references import resolve_version
from .projections import (
    derive_condition_view,
    derive_current_work_view,
    rebuild_projections,
    submission_versions_current,
)

INACTIVE = frozenset({"superseded", "cancelled"})
REQUIREMENT_FIELDS = frozenset(
    {
        "goal",
        "visible_requirements",
        "inputs",
        "deliverables",
        "acceptance_spec_ref",
        "required_credentials",
        "requirements",
        "requirement_dimension",
        "purpose",
        "owner_role",
    }
)


def current_id(state, work_id):
    seen = set()
    while work_id in state.get("work_replacements", {}):
        if work_id in seen:
            raise ValueError("Cyclic work replacement")
        seen.add(work_id)
        work_id = state["work_replacements"][work_id]
    return work_id


def current_item(state, work_id):
    return state["work_items"].get(current_id(state, work_id))


def dependencies_ready(state, item):
    """Readiness follows the current replacement of each declared predecessor."""
    return derive_current_work_view(state)[item["work_item_id"]]["dependencies_ready"]


def current_work_items(state):
    views = derive_current_work_view(state)
    return [
        item
        for key, item in state["work_items"].items()
        if views[key]["is_current"] and views[key]["status"] not in INACTIVE
    ]


def _current_item(state, work_id):
    item = state.get("work_items", {}).get(work_id)
    if (
        item is None
        or current_id(state, work_id) != work_id
        or derive_current_work_view(state)[work_id]["status"] in INACTIVE
    ):
        raise ValueError("Work is not a current obligation")
    return item


def _require_owner(state, item, actor):
    if actor not in {role["role_id"] for role in state.get("roles", [])}:
        raise ValueError("Unknown actor")
    if item["owner_role"] != actor:
        raise ValueError("Only the work owner may perform this action")


def _reason(reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A concrete reason is required")


def revise_requirement(state, targets, updates, actor, reason):
    """Replace exactly the selected obligations, retaining old facts and decisions.

    ``updates`` is a common patch to declarative requirement fields; domain-specific
    values belong in ``requirements``. No file or credential is created here. The
    caller must create any referenced credential before invoking this transition.
    """
    _reason(reason)
    if not isinstance(targets, (list, tuple)) or not targets:
        raise ValueError("Revision requires explicit work targets")
    if not isinstance(updates, dict) or not updates or set(updates) - REQUIREMENT_FIELDS:
        raise ValueError("Revision updates must contain declarative requirement fields")
    if "required_credentials" in updates:
        if not isinstance(updates["required_credentials"], list):
            raise ValueError("Required credentials must be version references")
        for reference in updates["required_credentials"]:
            resolve_version(state, reference)
    ids = list(dict.fromkeys(current_id(state, target) for target in targets))
    items = [_current_item(state, target) for target in ids]
    dimension = updates.get("requirement_dimension", "requirements")
    for item in items:
        require_authority(
            state,
            actor,
            "revise_requirement",
            dimension,
            work_node=item.get("node_id", item["work_item_id"]),
        )
    if "owner_role" in updates and updates["owner_role"] not in {
        role["role_id"] for role in state.get("roles", [])
    }:
        raise ValueError("Unknown replacement owner")
    revision = max(item["requirement_version"] for item in items) + 1
    replacements = {
        item[
            "work_item_id"
        ]: f"{item.get('node_id', item.get('root_work_id', item['work_item_id']))}@r{revision}"
        for item in items
    }
    if len(set(replacements.values())) != len(items) or any(
        work_id in state["work_items"] for work_id in replacements.values()
    ):
        raise ValueError("Requirement revision already exists")
    condition_views = derive_condition_view(state)
    work_views = derive_current_work_view(state)
    for old in items:
        old_id = old["work_item_id"]
        new_id = replacements[old_id]
        new = copy.deepcopy(old)
        new.update(copy.deepcopy(updates))
        new.update(
            work_item_id=new_id,
            requirement_version=revision,
            status="open",
            submissions=[],
            artifact_edits=[],
            blocker=None,
            blocker_ids=[],
            activated_at=state["clock"],
            applicability="current",
            origin_event=reason,
            supersedes=old_id,
            root_work_id=old.get("root_work_id", old_id),
        )
        new.pop("superseded_by", None)
        state["work_items"][new_id] = new
        state.setdefault("work_replacements", {})[old_id] = new_id
        old["applicability"] = "superseded_requirements"
        old["superseded_by"] = new_id
        if work_views[old_id]["status"] != "accepted":
            old["status"] = "superseded"
        for submission in old.get("submissions", []):
            submission["current_applicability"] = "superseded_requirements"
            if submission.get("review") is None:
                submission["invalidated"] = True
                submission["invalidation_reason"] = reason
        for cid, condition in state.get("condition_specs", {}).items():
            if condition["work_item_id"] != old_id or condition_views[cid]["status"] not in {
                "open",
                "unavailable",
            }:
                continue
            from .conditions import supersede_condition

            supersede_condition(state, cid, reason, {"work_item_id": new_id})
    for new_id in replacements.values():
        item = state["work_items"][new_id]
        item["dependencies"] = [current_id(state, dep) for dep in item.get("dependencies", [])]
    state.setdefault("requirement_events", []).append(
        {
            "actor_id": actor,
            "at": state["clock"],
            "reason": reason,
            "replacements": copy.deepcopy(replacements),
            "updates": copy.deepcopy(updates),
        }
    )
    rebuild_projections(state)
    return replacements


def submit_work(
    state, actor, work_item_id, pinned_versions, answer=None, context_versions=None, extensions=None
):
    """Pin a submission without inferring its business correctness.

    The file adapter checks readability and supplies actual immutable versions.
    Context visibility must likewise be computed by that adapter, never guessed here.
    """
    item = _current_item(state, work_item_id)
    _require_owner(state, item, actor)
    if not dependencies_ready(state, item):
        raise ValueError("Work dependencies have not been accepted")
    if "submit" not in derive_current_work_view(state)[work_item_id]["enabled_actions"]:
        raise ValueError("Work is not open for submission by this actor")
    if "answer" in item.get("deliverables", []) and answer is None:
        raise ValueError("This task requires an answer")
    expected = set(item.get("deliverables", [])) - {"answer"}
    if not isinstance(pinned_versions, dict) or set(pinned_versions) != expected:
        raise ValueError("Submission must pin every deliverable version")
    for artifact_id, version in pinned_versions.items():
        if version not in state.get("artifacts", {}).get(artifact_id, {}).get("versions", {}):
            raise ValueError("Submission contains an unknown artifact version")
    submission = {
        "submission_id": f"{work_item_id}-submission-{len(item['submissions']) + 1}",
        "requirement_version": item["requirement_version"],
        "actor_id": actor,
        "artifact_versions": copy.deepcopy(pinned_versions),
        "answer": copy.deepcopy(answer),
        "at": state["clock"],
        "context_versions": copy.deepcopy(context_versions or {}),
        "required_credentials": copy.deepcopy(item.get("required_credentials", [])),
        "requirement_snapshot": {
            key: copy.deepcopy(item[key]) for key in REQUIREMENT_FIELDS if key in item
        },
        "current_applicability": "current",
        "review": None,
        "invalidated": False,
    }
    if extensions:
        if not isinstance(extensions, dict) or set(extensions) & set(submission):
            raise ValueError("Submission extensions cannot overwrite core fields")
        submission.update(copy.deepcopy(extensions))
    item["submissions"].append(submission)
    rebuild_projections(state)
    return copy.deepcopy(submission)


def _pending_submission(state, item, submission_id):
    view = derive_current_work_view(state)[item["work_item_id"]]
    if view["pending_submission_id"] is None:
        raise ValueError("Work is not awaiting review")
    if view["pending_submission_id"] != submission_id:
        raise ValueError("Submission is not current and pending")
    return item["submissions"][-1]


def withdraw_submission(state, actor, work_item_id, submission_id, reason):
    item = _current_item(state, work_item_id)
    _require_owner(state, item, actor)
    _reason(reason)
    submission = _pending_submission(state, item, submission_id)
    submission.update(
        invalidated=True, invalidation_reason=reason, current_applicability="withdrawn"
    )
    submission["review"] = {
        "decision": "withdrawn",
        "actor_id": actor,
        "at": state["clock"],
        "reason": reason,
    }
    rebuild_projections(state)
    return {"submission_id": submission_id, "status": "withdrawn"}


def approve_submission(state, actor, work_item_id, submission_id):
    """Exercise approval authority; this is not an independent quality judgment."""
    item = _current_item(state, work_item_id)
    require_authority(
        state, actor, "approve", "deliverable", work_node=item.get("node_id", work_item_id)
    )
    if not dependencies_ready(state, item):
        raise ValueError("Current work dependencies have not been accepted")
    submission = _pending_submission(state, item, submission_id)
    view = derive_current_work_view(state)[work_item_id]
    if view["outstanding_condition_ids"]:
        raise ValueError("Work conditions have not been satisfied")
    if not submission_versions_current(state, item, submission):
        raise ValueError("Submission versions are no longer current")
    submission["review"] = {
        "decision": "accepted",
        "actor_id": actor,
        "at": state["clock"],
        "defects": [],
    }
    for aid, version in submission["artifact_versions"].items():
        metadata = state["artifacts"][aid]["versions"][version]
        metadata["review_status"] = "accepted"
        metadata["status"] = "submitted"
    rebuild_projections(state)
    return copy.deepcopy(submission)


def blocked_terminal(state):
    """Finite configured recovery exhaustion, derived from canonical conditions."""
    from .conditions import condition_has_future

    work = derive_current_work_view(state)
    active = [view for view in work.values() if view["is_current"] and view["status"] != "accepted"]
    if not active or state.get("events"):
        return False
    conditions = derive_condition_view(state)
    for view in active:
        if view["status"] != "blocked":
            return False
        unavailable = [
            cid
            for cid in view["outstanding_condition_ids"]
            if conditions[cid]["status"] == "unavailable"
        ]
        if not unavailable or any(
            condition_has_future(state, state["condition_specs"][cid]) for cid in unavailable
        ):
            return False
        if any(
            opportunity.get("status") in {"pending", "available"}
            and (
                opportunity.get("work_item_id") == view["work_item_id"]
                or opportunity.get("condition_id") in unavailable
            )
            for opportunity in state.get("future_opportunities", [])
        ):
            return False
    return True
