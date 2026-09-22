"""Public requirements, shared by renderers and graders; never reference answers."""

from dataclasses import asdict, dataclass, field

CONTRACT_VERSION = "operating-world-v0.3"
LEGACY_CONTRACT_VERSION = "operating-toy-v0.1"
EVALUATOR_VERSION = "operating-world-v0.3"
LEGACY_EVALUATOR_VERSION = "finance-v0.1.2"
CURRENT_EVALUATORS = (EVALUATOR_VERSION, "operating-toy-v0.2", LEGACY_EVALUATOR_VERSION)


@dataclass(frozen=True)
class CitationRequirement:
    allowed_locations: dict[str, tuple[str, ...]]
    required_all_of: tuple[tuple[str, str], ...] = ()
    required_any_of: tuple[tuple[str, str], ...] = ()
    version_binding: str = "submission_input_versions"

    def public(self):
        return asdict(self)

    def validate(self, citations, versions):
        if not isinstance(citations, list) or not citations:
            return False
        cited = set()
        for ref in citations:
            if not isinstance(ref, dict):
                return False
            aid, location = ref.get("artifact_id"), ref.get("location")
            if (
                not isinstance(aid, str)
                or not isinstance(location, str)
                or aid not in versions
                or ref.get("version_id") != versions[aid]
                or location not in self.allowed_locations.get(aid, ())
            ):
                return False
            cited.add((aid, location))
        return set(self.required_all_of) <= cited and (
            not self.required_any_of or bool(set(self.required_any_of) & cited)
        )


@dataclass(frozen=True)
class ArtifactContract:
    artifact_role: str
    required_input_roles: tuple[str, ...] = ()
    body_version_field: str | None = None
    period_rule: str | None = None
    unit_rules: dict = field(default_factory=dict)

    def public(self):
        return asdict(self)


def citation_contract(kind, output_locations=None):
    locations = tuple(output_locations or [f"Outputs!B{i}" for i in range(2, 9)])
    if kind == "short":
        return CitationRequirement(
            {"financials": ("values.diluted_eps",), "model": locations},
            required_all_of=(("model", locations[4]), ("financials", "values.diluted_eps")),
        )
    return CitationRequirement(
        {"financials": ("values.revenue", "values.operating_margin"), "model": locations},
        required_any_of=(
            ("financials", "values.revenue"),
            ("financials", "values.operating_margin"),
        ),
    )


def artifact_contracts():
    return {
        "model": ArtifactContract("model", ("financials", "basis")).public(),
        "memo": ArtifactContract(
            "memo", ("financials", "model"), "source_versions", "source_period"
        ).public(),
    }


def declared_bindings(dependencies):
    """Declarations are not read history and not automatically verified facts."""
    if not isinstance(dependencies, list):
        return None
    result = {}
    for ref in dependencies:
        if not isinstance(ref, dict) or not isinstance(ref.get("artifact_id"), str):
            return None
        aid = ref["artifact_id"]
        if aid in result or not isinstance(ref.get("version_id"), str):
            return None
        result[aid] = ref["version_id"]
    return result


def required_dependencies_match(dependencies, expected):
    declared = declared_bindings(dependencies)
    return declared is not None and all(
        declared.get(aid) == version for aid, version in expected.items()
    )
