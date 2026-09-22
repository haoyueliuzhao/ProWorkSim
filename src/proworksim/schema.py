"""Versioned contracts. Workers never receive the complete world specification."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "0.3"
SUPPORTED_SCHEMA_VERSIONS = ("0.1", "0.2", SCHEMA_VERSION)


class Status(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    REVISION_REQUIRED = "revision_required"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    WAITING_DEPENDENCIES = "waiting_dependencies"


@dataclass(frozen=True)
class RoleSpec:
    role_id: str
    responsibility: str
    policy: str
    trainable: bool = False
    can_approve: bool = False
    can_confirm_basis: bool = False


@dataclass(frozen=True)
class ProjectSpec:
    project_id: str
    lineage_id: str
    split: str
    company: str
    business_object: str = "operating_valuation"
    initial_state: str = "existing_model_requires_update"
    information_access: str = "mail"
    core_operations: tuple[str, ...] = ("retrieve", "recalculate", "compare", "modify")
    delivery: str = "continuous"
    continuity: bool = True
    pool: str = "representative"
    source_family_id: str = "synthetic-operating-toy"
    template_id: str = "operating-toy"
    topology_id: str = "chain"
    layout_id: str = "standard"
    role_information_id: str = "mail"
    scenario_id: str = "standard"
    configuration_id: str = "chain"
    work_graph_id: str = "chain"
    event_policy_id: str = "disclosure_and_basis"
    error_injection_id: str = "none"


@dataclass(frozen=True)
class WorldSpec:
    project: ProjectSpec
    roles: tuple[RoleSpec, ...]
    seed: int
    facts: dict[str, Any]
    assumptions: dict[str, Any]
    schema_version: str = SCHEMA_VERSION
    provenance: str = "fully_synthetic"
    workflow: dict | None = None
    layout: dict = field(default_factory=dict)
    lifecycle_events: list[dict] = field(default_factory=list)
    unavailable_topics: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WorkItem:
    project_id: str
    work_item_id: str
    origin_event: str
    owner_role: str
    goal: str
    visible_requirements: list[str]
    inputs: list[str]
    dependencies: list[str]
    deliverables: list[str]
    acceptance_spec_ref: str
    requirement_version: int = 1
    status: str = Status.OPEN
    submissions: list[dict] = field(default_factory=list)
    blocker: str | None = None
    blocker_ids: list[str] = field(default_factory=list)

    def public(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "acceptance_spec_ref"}


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_id: str
    version_id: str
    owner: str
    sha256: str
    logical_time: int
    derived_from: list[dict]
    status: str = "draft"
    review_status: str = "unreviewed"


@dataclass(frozen=True)
class WorldSnapshot:
    schema_version: str
    instance_id: str
    branch_id: str
    logical_time: int
    state_sha256: str


@dataclass
class InteractionRecord:
    action_id: str
    actor_id: str
    action: str
    inputs: dict
    output: dict
    logical_time: int
    reads: list[dict]
    writes: list[dict]
    wall_seconds: float


@dataclass
class EvaluationRecord:
    instance_id: str
    branch_id: str
    work_item_id: str
    requirement_version: int
    submission_id: str | None
    passed: bool
    reward: float
    checks: list[dict]
    uncertain: list[str]
    validity: str = "valid"
    evaluator_version: str = "finance-v0.1"
