"""Located issues, responses and institutional treatment decisions.

These facts describe a review relationship, never domain truth. An issue raised
against a currently pending submission can gate approval of that same work edition.
Late comments remain historical. File edits and resubmission do not close issues;
only a scoped decision on an actual response does. All three registries append.
"""

import copy
import hashlib
import json

from ..policies.organization import require_authority

DECISIONS = frozenset({"accept_fix", "accept_rebuttal", "keep_open"})


def _identity(prefix, values):
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return prefix + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 12000:
        raise ValueError(label + " must be bounded nonempty text")


def submission_for(state, work_id, submission_id):
    item = state["work_items"][work_id]
    submission = next((s for s in item["submissions"] if s["submission_id"] == submission_id), None)
    if submission is None:
        raise ValueError("Issue reference must name an actual submission of this work")
    return item, submission


def _pending(state, item, submission):
    return (
        item["work_item_id"] not in state.get("work_replacements", {})
        and item.get("cancelled_at") is None
        and item["submissions"][-1]["submission_id"] == submission["submission_id"]
        and submission.get("review") is None
        and not submission.get("invalidated")
        and submission["requirement_version"] == item["requirement_version"]
    )


def _review_power(state, actor, item, object_id):
    require_authority(state, actor, "review", "deliverable", item["node_id"],
                      project_id=item["project_id"], object_id=object_id)


def derive_issue_view(state):
    """Fold immutable decisions; keep their exact submission scope explicit."""
    decisions = {}
    for record in state.get("issue_decisions", {}).values():
        previous = decisions.get(record["issue_id"])
        if previous is None or record["sequence"] > previous["sequence"]:
            decisions[record["issue_id"]] = record
    result = {}
    for iid, issue in state.get("issues", {}).items():
        item = state["work_items"][issue["work_id"]]
        applicable = (
            issue["active_at_creation"]
            and issue["work_id"] not in state.get("work_replacements", {})
            and issue["requirement_version"] == item["requirement_version"]
            and item.get("cancelled_at") is None
        )
        decision = decisions.get(iid)
        resolved = decision is not None and decision["decision"] in {"accept_fix", "accept_rebuttal"}
        accepted = any((s.get("review") or {}).get("decision") == "accepted"
                       for s in item["submissions"])
        result[iid] = {
            "issue_id": iid, "work_id": issue["work_id"],
            "status": "resolved" if resolved else "open",
            "applicability": "active" if applicable and not accepted else "historical",
            "blocks_approval": applicable and not accepted and issue["blocking"] and not resolved,
            "decision_id": decision["decision_id"] if decision else None,
            "decision_submission_id": decision["submission_id"] if decision else None,
        }
    return result


def _store(state, registry, identity, payload):
    records = state.setdefault(registry, {})
    if identity in records:
        old = records[identity]
        if {key: value for key, value in old.items() if key not in {"at", "sequence"}} != payload:
            raise ValueError("Review relation identity reused for different payload")
        return copy.deepcopy(old)
    value = {**copy.deepcopy(payload), "at": state["clock"], "sequence": len(records) + 1}
    records[identity] = value
    return copy.deepcopy(value)


def raise_issue(state, actor, work_id, submission_id, issue_key, target, locator,
                description, evidence, blocking=True):
    _text(issue_key, "Issue key")
    _text(description, "Issue description")
    if not isinstance(locator, list) or not locator:
        raise ValueError("Located issue requires a nonempty location path")
    if type(blocking) is not bool:
        raise ValueError("Issue blocking must be a boolean")
    item, submission = submission_for(state, work_id, submission_id)
    _review_power(state, actor, item, target["object_id"])
    if submission["artifact_versions"].get(target["object_id"]) != target["version_id"]:
        raise ValueError("Issue target must be an exact version pinned in its submission")
    iid = _identity("issue-", [item["project_id"], work_id, submission_id, actor, issue_key])
    existing = state.get("issues", {}).get(iid)
    # Capture once; a retry after withdrawal keeps the original activation fact.
    active = existing["active_at_creation"] if existing else _pending(state, item, submission)
    result = _store(state, "issues", iid, {
        "issue_id": iid, "issue_key": issue_key, "project_id": item["project_id"],
        "work_id": work_id, "requirement_version": submission["requirement_version"],
        "submission_id": submission_id, "raised_by": actor, "target": copy.deepcopy(target),
        "locator": copy.deepcopy(locator), "description": description,
        "evidence": copy.deepcopy(evidence), "blocking": blocking, "active_at_creation": active,
    })
    return {**result, "view": derive_issue_view(state)[iid]}


def respond_issue(state, actor, issue_id, response_key, submission_id, body, evidence):
    _text(response_key, "Response key")
    _text(body, "Response body")
    issue = state["issues"][issue_id]
    item, submission = submission_for(state, issue["work_id"], submission_id)
    if actor != item["owner_role"]:
        raise ValueError("Only the responsible work owner may respond to its issue")
    if submission["requirement_version"] != issue["requirement_version"]:
        raise ValueError("Issue response targets another requirement edition")
    rid = _identity("issue-response-", [issue_id, actor, response_key])
    result = _store(state, "issue_responses", rid, {
        "response_id": rid, "response_key": response_key, "issue_id": issue_id,
        "work_id": issue["work_id"], "project_id": issue["project_id"],
        "requirement_version": issue["requirement_version"], "submission_id": submission_id,
        "actor_id": actor, "body": body, "evidence": copy.deepcopy(evidence),
    })
    return {**result, "view": derive_issue_view(state)[issue_id]}


def decide_issue(state, actor, issue_id, response_id, decision_key, decision, reason):
    _text(decision_key, "Decision key")
    _text(reason, "Decision reason")
    if decision not in DECISIONS:
        raise ValueError("Unknown review treatment decision")
    issue = state["issues"][issue_id]
    response = state.get("issue_responses", {}).get(response_id)
    if response is None or response["issue_id"] != issue_id:
        raise ValueError("Treatment response belongs to a different issue")
    item, submission = submission_for(state, issue["work_id"], response["submission_id"])
    _review_power(state, actor, item, issue["target"]["object_id"])
    did = _identity("issue-decision-", [issue_id, actor, decision_key])
    payload = {
        "decision_id": did, "decision_key": decision_key, "issue_id": issue_id,
        "response_id": response_id, "submission_id": response["submission_id"],
        "work_id": issue["work_id"], "project_id": issue["project_id"],
        "requirement_version": issue["requirement_version"], "actor_id": actor,
        "decision": decision, "reason": reason,
    }
    if did not in state.get("issue_decisions", {}):
        from .projections import submission_versions_current

        if not issue["active_at_creation"] or not _pending(state, item, submission):
            raise ValueError("Only a response to this work's current pending submission may be decided")
        if not submission_versions_current(state, item, submission):
            raise ValueError("Treatment requires a current fixed submission version")
        if derive_issue_view(state)[issue_id]["status"] == "resolved":
            raise ValueError("Issue already has a treatment decision; open a new located issue")
    result = _store(state, "issue_decisions", did, payload)
    return {**result, "view": derive_issue_view(state)[issue_id]}
