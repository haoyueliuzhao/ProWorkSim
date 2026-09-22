"""Contextual institutional applicability, independent of domain calculations."""

import json
from dataclasses import asdict, is_dataclass

from .references import VersionRef
from .types import CheckResult, CheckStatus


def credential_applicability(credential, context, attestation=None):
    """Evaluate a specified credential against a specified work requirement.

    No latest-version pointer, reading history, or hidden target enters this
    relation. Missing formal evidence remains UNASSESSED, not numeric failure.
    """
    query = asdict(context) if is_dataclass(context) else dict(context)
    evidence = {"context": query}
    if credential is None:
        return CheckResult(CheckStatus.UNASSESSED, ("credential_missing",), evidence)
    record = credential.to_dict() if hasattr(credential, "to_dict") else credential
    evidence["credential_ref"] = record.get("reference")
    if record.get("kind") != "credential":
        return CheckResult(CheckStatus.FAIL, ("not_a_credential",), evidence)
    if attestation is None:
        return CheckResult(CheckStatus.UNASSESSED, ("attestation_missing",), evidence)
    try:
        reference = VersionRef.from_mapping(record["reference"])
        attested = VersionRef.from_mapping(attestation["reference"])
    except (KeyError, TypeError, ValueError):
        return CheckResult(CheckStatus.UNASSESSED, ("attestation_reference_invalid",), evidence)
    if (
        attested != reference
        or attestation.get("attestation_id") != record.get("attestation_ref")
        or attestation.get("actor_id") != record.get("confirmed_by")
        or attestation.get("requirement_dimension") != record.get("requirement_dimension")
        or attestation.get("requirement_version") != record.get("requirement_version")
        or set(attestation.get("work_nodes", ())) != set(record.get("work_nodes", ()))
        or attestation.get("at", query["at"] + 1) > query["at"]
    ):
        return CheckResult(CheckStatus.UNASSESSED, ("attestation_mismatch",), evidence)
    reasons = []
    for key in ("project_id", "requirement_dimension", "requirement_version", "purpose"):
        if record.get(key) != query.get(key):
            reasons.append(f"{key}_mismatch")
    if query.get("period") is not None and record.get("period") != query["period"]:
        reasons.append("period_mismatch")
    if query.get("work_node") not in record.get("work_nodes", ()):
        reasons.append("work_scope_mismatch")
    if record.get("effective_at", query["at"] + 1) > query["at"]:
        reasons.append("not_effective_yet")
    if record.get("expires_at") is not None and query["at"] >= record["expires_at"]:
        reasons.append("expired")
    if record.get("status") not in ("confirmed", "approved"):
        reasons.append("credential_not_confirmed")
    return CheckResult(CheckStatus.FAIL if reasons else CheckStatus.PASS, tuple(reasons), evidence)


def confirm_credential(state, actor, reference, credential):
    """Sign one existing immutable version with scoped organizational power.

    The caller owns persistence and rollback. Repeating an identical confirmation
    is a no-op; neither readers nor adoption declarations are modified.
    """
    from ..policies.organization import require_authority
    from .references import resolve_version

    ref = VersionRef.from_mapping(reference)
    version = resolve_version(state, ref)

    record = credential.to_dict() if hasattr(credential, "to_dict") else dict(credential)
    record = json.loads(json.dumps(record))
    if record.get("kind") != "credential":
        raise ValueError("Only a credential can receive formal confirmation")
    if VersionRef.from_mapping(record.get("reference", {})) != ref:
        raise ValueError("Credential and confirmed version must be identical")
    if record.get("confirmed_by") != actor or version["logical_time"] > state["clock"]:
        raise ValueError("Confirmation actor or version time is invalid")
    nodes = record.get("work_nodes", ())
    if not nodes or not record.get("attestation_ref"):
        raise ValueError("Confirmation requires a work scope and attestation identifier")
    for node in nodes:
        require_authority(state, actor, "confirm", record["requirement_dimension"], node)
    if "credential" in version:
        if version["credential"] == record:
            return state["attestations"][record["attestation_ref"]]
        raise ValueError("A version's credential cannot be rewritten")
    registry = state.setdefault("attestations", {})
    if record["attestation_ref"] in registry:
        raise ValueError("Attestation identifier already exists")
    attestation = {
        "attestation_id": record["attestation_ref"],
        "actor_id": actor,
        "reference": ref.to_dict(),
        "requirement_dimension": record["requirement_dimension"],
        "requirement_version": record["requirement_version"],
        "work_nodes": list(nodes),
        "at": state["clock"],
        "power": "confirm",
        "subject": record["requirement_dimension"],
    }
    # Already normalized above for stable idempotence after persistence.
    version["credential"] = record
    registry[record["attestation_ref"]] = attestation
    return attestation


def registered_applicability(state, reference, context):
    """Query the registered credential and attestation, never trust a response flag."""
    from ..policies.organization import authority
    from .references import resolve_version

    try:
        version = resolve_version(state, reference)
    except (TypeError, ValueError):
        return CheckResult(CheckStatus.UNASSESSED, ("credential_version_missing",))
    record = version.get("credential")
    if record is None:
        return credential_applicability(None, context)
    query = asdict(context) if is_dataclass(context) else dict(context)
    try:
        matches = VersionRef.from_mapping(record.get("reference", {})) == VersionRef.from_mapping(
            reference
        )
    except (TypeError, ValueError):
        matches = False
    if not matches or version.get("logical_time", query["at"] + 1) > query["at"]:
        return CheckResult(CheckStatus.UNASSESSED, ("credential_reference_or_time_mismatch",))
    attestation = state.get("attestations", {}).get(record.get("attestation_ref"))
    if attestation and not authority(
        state,
        attestation.get("actor_id"),
        "confirm",
        record.get("requirement_dimension"),
        query.get("work_node"),
    ):
        return CheckResult(
            CheckStatus.UNASSESSED,
            ("confirmation_authority_missing",),
            {"credential_ref": record.get("reference"), "context": query},
        )
    return credential_applicability(record, query, attestation)
