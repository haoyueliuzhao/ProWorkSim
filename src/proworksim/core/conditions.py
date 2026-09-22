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
    from .projections import derive_condition_view

    view = derive_condition_view(state).get(condition["condition_id"], condition)
    if view.get("status") in {"resolved", "superseded"}:
        return False
    unavailable = set(view.get("unavailable_providers", []))
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


def _match_response(state, condition, response, replay=False):
    """Pure four-valued satisfaction check over a real request and its evidence."""
    if replay and response.get("receipt_context"):
        receipt_facts = response["receipt_context"]
        state = {
            **state,
            "organization": receipt_facts["organization"],
            "artifacts": receipt_facts["evidence_artifacts"],
            "objects": receipt_facts["evidence_objects"],
            "attestations": receipt_facts["evidence_attestations"],
        }
        condition = {
            **condition,
            **receipt_facts.get("condition_facts", {}).get(condition["condition_id"], {}),
        }
    if condition.get("status") in {"resolved", "superseded"}:
        return _check("NOT_APPLICABLE", "condition_is_closed")
    if condition.get("status") == "unavailable":
        return _check("NOT_APPLICABLE", "unavailable_request_requires_new_binding")
    request_id = response.get("request_id")
    if request_id != condition.get("request_id"):
        return _check("NOT_APPLICABLE", "different_request")
    item = state.get("work_items", {}).get(condition.get("work_item_id"))
    receipt = response.get("receipt_context", {}) if replay else {}
    replacements = receipt.get("work_replacements", state.get("work_replacements", {}))
    accepted = (
        receipt.get("accepted_submission_id")
        if replay and receipt
        else next(
            (
                sub.get("submission_id", "accepted")
                for sub in (item or {}).get("submissions", [])
                if (sub.get("review") or {}).get("decision") == "accepted"
            ),
            None,
        )
    )
    cancelled = (
        receipt.get("cancelled_at") if replay and receipt else (item or {}).get("cancelled_at")
    )
    if item is None or item["work_item_id"] in replacements or accepted or cancelled is not None:
        return _check("NOT_APPLICABLE", "work_is_not_current")
    requirement_version = condition.get("requirement_version")
    work_revision = receipt.get("requirement_version", (item or {}).get("requirement_version"))
    if work_revision != requirement_version:
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
    evidence_state = {
        **state,
        "clock": response.get("received_at", state["clock"]) if replay else state["clock"],
    }
    return check_evidence(evidence_state, condition, response)


def match_response(state, condition, response):
    """Check the same pure condition view used by work readiness and observations."""
    from .projections import derive_condition_view

    view = derive_condition_view(state).get(condition["condition_id"], {})
    return _match_response(state, {**condition, **view}, response)


def reopen_work(state, work_id):
    from .projections import derive_current_work_view, rebuild_projections

    view = derive_current_work_view(state).get(work_id, {})
    rebuild_projections(state)
    return view.get("is_current", False) and view.get("status") == "open"


def apply_response(state, response):
    """Record every real response; satisfaction is a replaceable pure projection."""
    from .projections import rebuild_projections

    response_id = response.get("response_id")
    if not response_id:
        raise ValueError("A response event needs an identity")
    records = state.get("raw_condition_responses", {})
    if response_id in records:
        existing = {
            k: v
            for k, v in records[response_id].items()
            if k not in {"received_at", "receipt_context", "received_sequence"}
        }
        incoming = {
            k: v
            for k, v in response.items()
            if k not in {"received_at", "receipt_context", "received_sequence"}
        }
        if existing != incoming:
            raise ValueError("A response identity cannot be reused for different evidence")
        rebuild_projections(state)
        return copy.deepcopy(state["condition_responses"][response_id])
    item = state.get("work_items", {}).get(response.get("work_item_id"), {})
    reference = _reference(response.get("reference"))
    evidence_artifacts, evidence_objects, attestations = {}, {}, {}
    if reference:
        for registry, target in (("artifacts", evidence_artifacts), ("objects", evidence_objects)):
            artifact = state.get(registry, {}).get(reference[0])
            if artifact is not None:
                version = artifact.get("versions", {}).get(reference[1])
                target[reference[0]] = {
                    "versions": {reference[1]: copy.deepcopy(version)}
                    if version is not None
                    else {}
                }
                attestation_id = (version or {}).get("credential", {}).get("attestation_ref")
                if attestation_id in state.get("attestations", {}):
                    attestations[attestation_id] = copy.deepcopy(
                        state["attestations"][attestation_id]
                    )
    condition_facts = {}
    for cid, definition in state.get("condition_specs", {}).items():
        if response.get("request_id") in (
            {definition.get("request_id")}
            | {event.get("request_id") for event in definition.get("history", [])}
        ):
            condition_facts[cid] = {
                key: copy.deepcopy(definition[key])
                for key in (
                    "evidence_spec",
                    "context",
                    "providers",
                    "expected_version",
                    "purpose",
                    "required_power",
                    "subject",
                )
                if key in definition
            }
    state.setdefault("raw_condition_responses", {})[response_id] = {
        **copy.deepcopy(response),
        "received_at": state["clock"],
        "received_sequence": len(records) + 1,
        # Pin source facts at receipt, not a success/failure conclusion. Later
        # approval or replacement cannot change what was current when mail arrived.
        "receipt_context": {
            "organization": copy.deepcopy(state.get("organization", {})),
            "evidence_artifacts": evidence_artifacts,
            "evidence_objects": evidence_objects,
            "evidence_attestations": attestations,
            "condition_facts": condition_facts,
            "work_replacements": copy.deepcopy(state.get("work_replacements", {})),
            "requirement_version": item.get("requirement_version"),
            "cancelled_at": item.get("cancelled_at"),
            "accepted_submission_id": next(
                (
                    sub.get("submission_id", "accepted")
                    for sub in item.get("submissions", [])
                    if (sub.get("review") or {}).get("decision") == "accepted"
                ),
                None,
            ),
        },
    }
    for condition in state.get("condition_specs", {}).values():
        # Keep obsolete and unsatisfied responses as receipt facts too.
        bindings = {condition.get("request_id")} | {
            event.get("request_id") for event in condition.get("history", [])
        }
        if response.get("request_id") in bindings:
            condition.setdefault("history", []).append(
                {"at": state["clock"], "event": "response_received", "response_id": response_id}
            )
    rebuild_projections(state)
    return copy.deepcopy(state["condition_responses"][response_id])


def supersede_condition(state, condition_id, reason, replacement_ref=None):
    from .projections import derive_condition_view, rebuild_projections

    condition = state["condition_specs"][condition_id]
    if derive_condition_view(state)[condition_id]["status"] not in {"open", "unavailable"}:
        raise ValueError("Only outstanding conditions can be superseded")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Supersession requires a concrete reason")
    condition.setdefault("history", []).append(
        {
            "at": state["clock"],
            "event": "superseded",
            "reason": reason,
            "replacement_ref": copy.deepcopy(replacement_ref),
        }
    )
    rebuild_projections(state)
    return copy.deepcopy(condition)
