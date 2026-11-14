"""Operating-domain adapter for formally confirmed analytical assumptions."""

import json
from dataclasses import asdict, dataclass

from .core.references import ApplicabilityContext
from .core.rules import confirm_credential, credential_applicability, registered_applicability
from .core.types import CheckStatus, Credential
from .core.visibility import grant_version, visible_version  # noqa: F401 -- public adapter import
from .policies.organization import authority, position, require_authority
from .storage import json_bytes


@dataclass(frozen=True)
class ApprovedBasis:
    basis_id: str
    version_id: str
    project_id: str
    requirement_version: int
    applicable_work_nodes: list[str]
    period: str
    effective_at: int
    confirmed_by: str
    confirmation_ref: str
    assumptions: dict
    supersedes: str | None = None
    status: str = "approved"
    requirement_dimension: str = "analytical_assumptions"
    purpose: str = "analytical_input"


def basis_context(item, project_id, clock):
    return ApplicabilityContext(
        project_id=project_id,
        work_id=item["work_item_id"],
        requirement_dimension="analytical_assumptions",
        requirement_version=item.get("basis_requirement_version", item["requirement_version"]),
        work_node=item.get("node_id", item["work_item_id"]),
        period=item.get("source_period"),
        purpose="analytical_input",
        at=clock,
    )


def basis_credential(record):
    return Credential(
        reference={"object_id": record["basis_id"], "version_id": record["version_id"]},
        project_id=record["project_id"],
        requirement_dimension=record.get("requirement_dimension", "analytical_assumptions"),
        requirement_version=record["requirement_version"],
        work_nodes=tuple(record["applicable_work_nodes"]),
        period=record["period"],
        purpose=record.get("purpose", "analytical_input"),
        effective_at=record["effective_at"],
        confirmed_by=record["confirmed_by"],
        attestation_ref=record["confirmation_ref"],
        status=record["status"],
    )


def read_basis(store, state, version):
    return json.loads(store.version_path(state["artifacts"]["basis"], version).read_bytes())


def issue_basis(
    store,
    state,
    assumptions,
    period,
    requirement_version,
    nodes,
    scenario_revision,
    public=False,
    confirmer=None,
):
    confirmer = confirmer or position(state, "coordinator")
    for node in nodes:
        require_authority(state, confirmer, "confirm", "analytical_assumptions", node)
    artifact = state["artifacts"]["basis"]
    version = f"v{len(artifact['versions']) + 1}"
    previous = artifact["current_version"]
    record = ApprovedBasis(
        "basis",
        version,
        state["project"]["project_id"],
        requirement_version,
        list(nodes),
        period,
        state["clock"],
        confirmer,
        f"approval-{version}",
        dict(assumptions),
        previous,
    )
    store.put(state, "basis", json_bytes(asdict(record)), confirmer)
    confirm_credential(
        state,
        confirmer,
        {"artifact_id": "basis", "version_id": version},
        basis_credential(asdict(record)),
    )
    # Historical v0.3 projection only. Canonical confirmation lives in attestations.
    state.setdefault("basis_approvals", []).append(
        {
            "approval_id": record.confirmation_ref,
            "actor_id": confirmer,
            "basis_version": version,
            "at": state["clock"],
            "requirement_version": requirement_version,
            "work_nodes": list(nodes),
        }
    )
    state.setdefault("basis_by_scenario", {})[str(scenario_revision)] = {
        "artifact_id": "basis",
        "version_id": version,
    }
    if public:
        grant_basis(state, version, position(state, "worker"), record.confirmation_ref)
    return asdict(record)


def grant_basis(state, version, actor, confirmation_ref):
    if grant_version(state, "basis", version, actor, confirmation_ref):
        state.setdefault("basis_visibility", []).append(
            {
                "actor_id": actor,
                "version_id": version,
                "confirmation_ref": confirmation_ref,
                "at": state["clock"],
            }
        )


def applicable(record, item, project_id, clock):
    """Context-only check; callers must separately establish the formal attestation."""
    credential = basis_credential(record)
    attestation = {
        "attestation_id": record["confirmation_ref"],
        "actor_id": record["confirmed_by"],
        "reference": credential.reference,
        "requirement_dimension": credential.requirement_dimension,
        "requirement_version": credential.requirement_version,
        "work_nodes": list(credential.work_nodes),
        "at": record["effective_at"],
    }
    return (
        credential_applicability(
            credential, basis_context(item, project_id, clock), attestation
        ).status
        == CheckStatus.PASS
    )


def legacy_basis_applicability(state, item, version):
    """Read-only v0.3 metadata adapter, used only when canonical registry is absent."""
    approved = next(
        (a for a in state.get("basis_approvals", []) if a.get("basis_version") == version), None
    )
    if not approved or not authority(
        state,
        approved.get("actor_id"),
        "confirm",
        "analytical_assumptions",
        item.get("node_id", item["work_item_id"]),
    ):
        return None
    if (
        approved.get("requirement_version")
        != item.get("basis_requirement_version", item["requirement_version"])
        or item.get("node_id", item["work_item_id"]) not in approved.get("work_nodes", [])
        or approved.get("at", state["clock"] + 1) > state["clock"]
    ):
        return None
    return approved


def requirement_basis(store, state, item):
    reference = item.get("required_basis")
    if not reference:
        return None
    record = read_basis(store, state, reference["version_id"])
    if "attestations" in state or state.get("schema_version") not in (None, "0.1", "0.2", "0.3"):
        result = registered_applicability(
            state, reference, basis_context(item, state["project"]["project_id"], state["clock"])
        )
        if result.status != CheckStatus.PASS:
            return None
    elif legacy_basis_applicability(state, item, reference["version_id"]) is None:
        return None
    return (
        record if applicable(record, item, state["project"]["project_id"], state["clock"]) else None
    )
