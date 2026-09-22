"""Versioned managerial approval as an input, separate from access and adoption."""

import json
from dataclasses import asdict, dataclass

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


def visible_version(artifact, actor, clock, requested=None):
    versions = [requested] if requested else reversed(list(artifact["versions"]))
    for version in versions:
        if (
            version not in artifact["versions"]
            or artifact["versions"][version]["logical_time"] > clock
        ):
            continue
        if actor in artifact["readers"] or actor in artifact.get("version_readers", {}).get(
            version, []
        ):
            return version
    return None


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
    confirmer="manager",
):
    role = next((r for r in state["roles"] if r["role_id"] == confirmer), None)
    if confirmer != "manager" or not role or not role.get("can_confirm_basis", False):
        raise ValueError("Only the project manager can confirm analytical assumptions")
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
        grant_basis(state, version, "analyst", record.confirmation_ref)
    return asdict(record)


def grant_basis(state, version, actor, confirmation_ref):
    artifact = state["artifacts"]["basis"]
    readers = artifact.setdefault("version_readers", {}).setdefault(version, [])
    if actor not in readers:
        readers.append(actor)
    state.setdefault("basis_visibility", []).append(
        {
            "actor_id": actor,
            "version_id": version,
            "confirmation_ref": confirmation_ref,
            "at": state["clock"],
        }
    )


def applicable(record, item, project_id, clock):
    return (
        record.get("status") == "approved"
        and record.get("confirmed_by") == "manager"
        and record.get("project_id") == project_id
        and record.get("effective_at", clock + 1) <= clock
        and record.get("requirement_version")
        == item.get("basis_requirement_version", item["requirement_version"])
        and (item.get("source_period") is None or record.get("period") == item["source_period"])
        and item.get("node_id", item["work_item_id"]) in record.get("applicable_work_nodes", [])
    )


def requirement_basis(store, state, item):
    reference = item.get("required_basis")
    if not reference:
        return None
    record = read_basis(store, state, reference["version_id"])
    confirmed = any(
        a["approval_id"] == record.get("confirmation_ref")
        and a["basis_version"] == record.get("version_id")
        and a["actor_id"] == "manager"
        for a in state.get("basis_approvals", [])
    )
    return (
        record
        if confirmed and applicable(record, item, state["project"]["project_id"], state["clock"])
        else None
    )
