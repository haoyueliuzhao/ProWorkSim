"""Extensible request/response satisfaction, independent of message delivery.

A response may be delivered yet fail to satisfy an obligation. This module
checks explicit references and institutional evidence; text and topic labels
alone do not establish support. Domain adapters choose evidence requirements.
"""

import copy

from .types import CheckResult, CheckStatus

INACTIVE_WORK = frozenset({"accepted", "superseded", "cancelled", "withdrawn"})


def _check(status, reason, **evidence):
    return CheckResult(CheckStatus(status), (reason,), evidence)


def _reference(value):
    if not isinstance(value, dict):
        return None
    object_id = value.get("object_id", value.get("artifact_id"))
    version_id = value.get("version_id")
    return (object_id, version_id) if object_id and version_id else None


def _current(state, work_id):
    return work_id not in state.get("work_replacements", {})


def condition_has_future(state, condition):
    """A provider's current inability does not exhaust other explicit routes."""
    if condition.get("status") in {"resolved", "superseded"}:
        return False
    unavailable = set(condition.get("unavailable_providers", []))
    if any(provider not in unavailable for provider in condition.get("providers", [])):
        return True
    return any(
        opportunity.get("condition_id") == condition["condition_id"]
        and opportunity.get("status") in {"pending", "available"}
        for opportunity in state.get("future_opportunities", [])
    )


def check_evidence(state, condition, response):
    spec = condition.get("evidence_spec", {})
    kind = spec.get("kind")
    # Explicit compatibility only for old in-memory protocol fixtures. Newly
    # compiled worlds always declare an object/credential evidence requirement.
    if kind == "legacy_protocol" and "schema_version" not in state:
        return _check("PASS", "legacy_protocol_only")
    reference = _reference(response.get("reference"))
    if reference is None:
        return _check("UNASSESSED", "no_evidence_reference")
    expected = _reference(spec.get("reference"))
    if expected is not None and reference != expected:
        return _check("FAIL", "wrong_evidence_reference")
    artifact = state.get("artifacts", {}).get(reference[0])
    if artifact is None:
        artifact = state.get("objects", {}).get(reference[0])
    version = (artifact or {}).get("versions", {}).get(reference[1])
    if version is None:
        return _check("FAIL", "unknown_evidence_version")
    if version.get("logical_time", version.get("at", 0)) > state["clock"]:
        return _check("UNASSESSED", "evidence_not_yet_available")
    if kind == "version":
        return _check("PASS", "referenced_version_exists", reference=response["reference"])
    if kind != "credential":
        return _check("UNASSESSED", "unsupported_evidence_requirement")
    from .rules import registered_applicability
    from .references import ApplicabilityContext

    context_data = copy.deepcopy(condition.get("context", {}))
    context_data["at"] = state["clock"]
    try:
        context = ApplicabilityContext(**context_data)
    except TypeError:
        return _check("UNASSESSED", "incomplete_applicability_context")
    return registered_applicability(state, response["reference"], context)


def match_response(state, condition, response):
    """Pure four-valued satisfaction check over a real request and its evidence."""
    if condition.get("status") in {"resolved", "superseded"}:
        return _check("NOT_APPLICABLE", "condition_is_closed")
    if condition.get("status") == "unavailable":
        return _check("NOT_APPLICABLE", "unavailable_request_requires_new_binding")
    request_id = response.get("request_id")
    if request_id != condition.get("request_id"):
        return _check("NOT_APPLICABLE", "different_request")
    item = state.get("work_items", {}).get(condition.get("work_item_id"))
    if (
        item is None
        or item.get("status") in INACTIVE_WORK
        or not _current(state, item["work_item_id"])
    ):
        return _check("NOT_APPLICABLE", "work_is_not_current")
    requirement_version = condition.get("requirement_version")
    if item.get("requirement_version") != requirement_version:
        return _check("NOT_APPLICABLE", "condition_requirement_is_obsolete")
    request = state.get("requests", {}).get(request_id)
    message = next(
        (m for m in state.get("messages", []) if m.get("message_id") == request_id), None
    )
    if message is None or message.get("sender") != item.get("owner_role"):
        return _check("FAIL", "request_identity_not_established")
    responder = response.get("responder")
    if responder not in message.get("recipients", []) or responder not in condition.get(
        "providers", []
    ):
        return _check("FAIL", "unrequested_provider")
    if response.get("work_item_id") != item["work_item_id"]:
        return _check("FAIL", "different_work")
    if response.get("requirement_version") != requirement_version:
        return _check("NOT_APPLICABLE", "response_requirement_is_obsolete")
    if message.get("work_item_id", item["work_item_id"]) != item["work_item_id"]:
        return _check("FAIL", "request_targets_other_work")
    if "schema_version" in state and request is None:
        return _check("FAIL", "unregistered_request")
    if request and (
        request.get("work_item_id") != item["work_item_id"]
        or request.get("requirement_version") != requirement_version
        or request.get("requested_role") != responder
    ):
        return _check("FAIL", "request_contract_mismatch")
    if (
        request
        and request.get("evidence_reference") is not None
        and response.get("status") == "delivered"
        and _reference(request["evidence_reference"]) != _reference(response.get("reference"))
    ):
        return _check("FAIL", "response_differs_from_requested_evidence")
    expected_version = condition.get("expected_version")
    if expected_version is not None and (
        type(response.get("condition_version")) is not type(expected_version)
        or response.get("condition_version") != expected_version
    ):
        return _check("FAIL", "condition_version_mismatch")
    if condition.get("purpose") != response.get("purpose"):
        return _check("FAIL", "response_purpose_mismatch")
    if condition.get("required_power"):
        from ..policies.organization import authority

        if not authority(
            state,
            responder,
            condition["required_power"],
            condition["subject"],
            item.get("node_id", item["work_item_id"]),
        ):
            return _check("FAIL", "provider_lacks_authority")
    if response.get("status") == "unavailable":
        return _check("UNASSESSED", "provider_currently_unavailable", provider=responder)
    if response.get("status") != "delivered":
        return _check("FAIL", "response_does_not_supply_evidence")
    return check_evidence(state, condition, response)


def reopen_work(state, work_id):
    item = state["work_items"][work_id]
    if item.get("status") != "blocked" or not _current(state, work_id):
        return False
    conditions = [
        c for c in state.get("condition_specs", {}).values() if c["work_item_id"] == work_id
    ]
    if any(c.get("status") not in {"resolved", "superseded"} for c in conditions):
        return False
    if any(
        state.get("blockers", {}).get(bid, {}).get("status") not in {"resolved", "superseded"}
        for bid in item.get("blocker_ids", [])
    ):
        return False
    from .work import dependencies_ready

    if not dependencies_ready(state, item):
        return False
    item["status"] = "open"
    item["blocker"] = None
    return True


def _transition(state, condition, status, **details):
    condition["status"] = status
    condition.setdefault("history", []).append(
        {"at": state["clock"], "status": status, **copy.deepcopy(details)}
    )
    blocker = state.get("blockers", {}).get(condition.get("blocker_id"))
    if blocker:
        blocker["status"] = status
        if "resolution_ref" in details:
            blocker["resolution_ref"] = copy.deepcopy(details["resolution_ref"])
        blocker["history"].append(
            {"at": state["clock"], "status": status, **copy.deepcopy(details)}
        )


def apply_response(state, response):
    """Apply satisfaction effects only; callers separately deliver/record mail.

    Idempotency is keyed by a concrete response ID. Repeated processing neither
    extends histories nor reopens work. Failed checks do not mutate conditions.
    """
    response_id = response.get("response_id")
    if not response_id:
        raise ValueError("A response event needs an identity")
    previous = state.get("condition_responses", {}).get(response_id)
    if previous is not None:
        return copy.deepcopy(previous)
    result = {
        "response_id": response_id,
        "checks": {},
        "resolved_conditions": [],
        "reopened_work_items": [],
    }
    touched = False
    for condition in state.get("condition_specs", {}).values():
        if condition.get("request_id") != response.get("request_id"):
            continue
        changed = False
        check = match_response(state, condition, response)
        result["checks"][condition["condition_id"]] = check.to_dict()
        resolution = {
            "message_id": response_id,
            "reference": copy.deepcopy(response.get("reference")),
        }
        if check.status == CheckStatus.PASS:
            _transition(
                state,
                condition,
                "resolved",
                responder=response["responder"],
                resolution_ref=resolution,
            )
            result["resolved_conditions"].append(condition["condition_id"])
            touched = changed = True
        elif (
            check.status == CheckStatus.UNASSESSED
            and "provider_currently_unavailable" in check.reasons
        ):
            providers = condition.setdefault("unavailable_providers", [])
            if response["responder"] not in providers:
                providers.append(response["responder"])
            _transition(
                state,
                condition,
                "unavailable",
                reason=response.get("reason", "Provider currently cannot supply the evidence"),
                resolution_ref=resolution,
            )
            touched = changed = True
        if changed and reopen_work(state, condition["work_item_id"]):
            result["reopened_work_items"].append(condition["work_item_id"])
    if touched:
        state.setdefault("condition_responses", {})[response_id] = copy.deepcopy(result)
    return result


def supersede_condition(state, condition_id, reason, replacement_ref=None):
    condition = state["condition_specs"][condition_id]
    if condition["status"] not in {"open", "unavailable"}:
        raise ValueError("Only outstanding conditions can be superseded")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Supersession requires a concrete reason")
    _transition(state, condition, "superseded", reason=reason, replacement_ref=replacement_ref)
    reopen_work(state, condition["work_item_id"])
    return copy.deepcopy(condition)
