"""Exact references and fully specified applicability query contexts."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class VersionRef:
    object_id: str
    version_id: str

    def __post_init__(self):
        if (
            not isinstance(self.object_id, str)
            or not self.object_id
            or not isinstance(self.version_id, str)
            or not self.version_id
        ):
            raise ValueError("A version reference requires object and version identifiers")

    @classmethod
    def from_mapping(cls, value):
        if isinstance(value, cls):
            return value
        return cls(value.get("object_id", value.get("artifact_id")), value.get("version_id"))

    from_dict = from_mapping

    def to_dict(self):
        return asdict(self)

    def artifact_ref(self):
        return {"artifact_id": self.object_id, "version_id": self.version_id}


def resolve_version(state, reference):
    ref = VersionRef.from_mapping(reference)
    obj = state.get("artifacts", {}).get(ref.object_id)
    if obj is None or ref.version_id not in obj.get("versions", {}):
        raise ValueError("Referenced object version does not exist")
    return obj["versions"][ref.version_id]


@dataclass(frozen=True)
class ApplicabilityContext:
    project_id: str
    work_id: str
    requirement_dimension: str
    requirement_version: int | str
    work_node: str
    period: str | None
    purpose: str
    at: int

    def to_dict(self):
        return asdict(self)
