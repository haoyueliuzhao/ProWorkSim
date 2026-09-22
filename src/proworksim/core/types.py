"""Explicit semantic record kinds and non-binary check outcomes.

A fact records an occurrence or supplied observation, not universal truth. Claims,
assumptions and institutional credentials deliberately carry different kinds.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNASSESSED = "UNASSESSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    reasons: tuple[str, ...] = ()
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "status": self.status.value,
            "reasons": list(self.reasons),
            "evidence": self.evidence,
        }


class EntityKind(StrEnum):
    FACT = "fact"
    CLAIM = "claim"
    ASSUMPTION = "assumption"
    CREDENTIAL = "credential"


@dataclass(frozen=True)
class Fact:
    value: Any
    source_ref: dict
    recorded_at: int
    kind: EntityKind = field(default=EntityKind.FACT, init=False)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Claim:
    value: Any
    asserted_by: str
    at: int
    kind: EntityKind = field(default=EntityKind.CLAIM, init=False)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Assumption:
    value: Any
    proposed_by: str
    at: int
    kind: EntityKind = field(default=EntityKind.ASSUMPTION, init=False)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Credential:
    """Version-bound institutional statement; values need not be numerically true."""

    reference: dict
    project_id: str
    requirement_dimension: str
    requirement_version: int | str
    work_nodes: tuple[str, ...]
    period: str | None
    purpose: str
    effective_at: int
    confirmed_by: str
    attestation_ref: str
    status: str = "confirmed"
    expires_at: int | None = None
    kind: EntityKind = field(default=EntityKind.CREDENTIAL, init=False)

    def to_dict(self):
        return asdict(self)
