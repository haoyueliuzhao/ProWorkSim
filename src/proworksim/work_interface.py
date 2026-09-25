"""Versioned public work interface: syntax projection, never a task solver."""

import copy
import math
from pathlib import Path

from .storage import atomic_write, digest, json_bytes
from .tool_outcomes import ToolRejection

INTERFACE_VERSION = "work-interface-v0.13"
LEGACY_INTERFACE = "work-interface-legacy-v0.12"
PROFILES = {
    "provider": ("read_alias", "read_version", "read_messages", "request_information", "handoff_information", "wait"),
    "implementer": ("read_alias", "read_version", "read_messages", "request_information", "adopt", "write_object", "sql_build", "sql_query", "preflight_submission", "submit", "withdraw", "respond_issue", "wait"),
    "reviewer": ("read_alias", "read_version", "read_messages", "request_information", "handoff_information", "inspect_submission", "raise_issue", "approve", "decide_issue", "wait"),
}
REFERENCE = {
    "type": "object",
    "properties": {"object_id": {"type": "string", "minLength": 1}, "version_id": {"type": "string", "minLength": 1}},
    "required": ["object_id", "version_id"],
    "additionalProperties": False,
}
DESCRIPTIONS = {
    "read_alias": "Read the current version at a visible workspace alias. Returns its exact reference and content. Does not adopt or hand off anything. Use read_version to choose an older exact version.",
    "read_version": "Read exactly the object_id/version_id you specify. Returns content and the same exact reference. No version is selected for you.",
    "read_messages": "Read actual messages addressed to this role, including requests and deliveries.",
    "request_information": "Ask a declared route provider for information for this work. Only a real provider decision can answer a manual route.",
    "handoff_information": "Choose evidence you actually read and send it through your manual route. Copy its exact reference. Omit request_id for proactive delivery, or provide the real request_id to reply. No adoption or approval is created.",
    "adopt": "Bind an exact readable reference to a work input name. alias is the input name used later by sql_build, not an object ID. Reading and adopting are separate.",
    "write_object": "Write a new version of the chosen local JSON alias. Explicit dependencies are exact source references; no source is selected or added automatically. A SQL project has models[{name,sql}], tests[{name,sql}], config{exports}.",
    "sql_build": "Execute the chosen SQL project using exact work adoptions named in input_aliases; write its real result/error to output_alias. SELECT/CTE only; no files/network/extensions. This is not a correctness judgment.",
    "sql_query": "Run one SELECT/CTE against tables in a local readable source or its exact work adoption. Save actual output/error to output_alias.",
    "preflight_submission": "Check public file, source, dependency and table structure only. Does not reveal correct business values, repair files or submit.",
    "submit": "Submit current versions of the chosen workspace aliases for the work. A submission alone is not approval or business correctness.",
    "withdraw": "Withdraw the specified pending submission before replacing it; prior files and reviews remain immutable.",
    "inspect_submission": "Inspect an exact real submission and its fixed artifact versions. Read the versions themselves before judging them.",
    "raise_issue": "Record a supported issue at an exact submitted object/version and nonempty locator path. Supply real evidence references and a specific description.",
    "approve": "Approve this exact pending submission only after supported review. Does not supply evidence or make incorrect content correct.",
    "respond_issue": "Respond to a real issue using the actual revised submission and exact evidence references.",
    "decide_issue": "Decide a real response after reviewing its actual revision and evidence.",
    "wait": "Advance world time by the declared ticks, allowing due transport events to run. Unlike staff_wait, this is a world action.",
}


def profile_id(role):
    if role not in PROFILES:
        raise ValueError("Unknown work-interface role profile")
    return INTERFACE_VERSION + ":" + role


def tool_definitions(core_definitions, profile):
    prefix, _, role = profile.partition(":")
    if prefix == LEGACY_INTERFACE and role in PROFILES:
        return copy.deepcopy([d for d in core_definitions if d["name"] not in {"read_alias", "read_version"}])
    if prefix != INTERFACE_VERSION or role not in PROFILES:
        raise ValueError("Unknown frozen work interface")
    indexed = {d["name"]: d for d in core_definitions}
    result = []
    for name in PROFILES[role]:
        if name not in indexed:
            continue
        definition = copy.deepcopy(indexed[name])
        definition["description"] = DESCRIPTIONS[name]
        parameters = definition["parameters"]
        props = parameters["properties"]
        for key, value in props.items():
            value.pop("description", None)
            if value.get("type") == "string":
                value["minLength"] = 1
            if key == "reference":
                props[key] = copy.deepcopy(REFERENCE)
            elif key in {"dependencies", "evidence"}:
                value["items"] = copy.deepcopy(REFERENCE)
            elif key in {"artifacts", "work_ids", "input_aliases"}:
                value["items"] = {"type": "string", "minLength": 1}
                value["minItems"] = 1
            elif key == "locator":
                value["items"] = {"type": ["string", "integer"]}
                value["minItems"] = 1
        if name == "write_object":
            props.pop("object_id", None)
            if "alias" not in parameters["required"]:
                parameters["required"].append("alias")
        if name == "adopt":
            props["policy"]["enum"] = ["fixed", "current_published", "current_applicable"]
        if name == "handoff_information":
            props["status"]["enum"] = ["delivered", "unavailable"]
            parameters["allOf"] = [{
                "if": {"properties": {"status": {"const": "unavailable"}}, "required": ["status"]},
                "then": {"required": ["request_id"], "not": {"required": ["reference"]}},
                "else": {"required": ["reference"]},
            }]
        if name == "decide_issue":
            props["decision"]["enum"] = ["accept_fix", "reject_fix", "waive"]
        if name == "wait":
            props["ticks"]["minimum"] = 1
        result.append(definition)
    return result


def _schema_errors(schema, value, path="arguments"):
    """Validate only the explicit JSON Schema subset emitted above; no repair."""
    errors = []
    kinds = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "integer": type(value) is int,
        "boolean": type(value) is bool,
        "number": type(value) in (int, float) and math.isfinite(value),
        "null": value is None,
    }
    typ = schema.get("type")
    if typ and not any(kinds[t] for t in ([typ] if isinstance(typ, str) else typ)):
        return [path + " must have type " + str(typ)]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(path + " must be one of " + str(schema["enum"]))
    if "const" in schema and value != schema["const"]:
        errors.append(path + " must equal " + str(schema["const"]))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(path + "." + key + " is required")
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(props)):
                errors.append(path + "." + key + " is not a public parameter")
        for key in value.keys() & props.keys():
            errors.extend(_schema_errors(props[key], value[key], path + "." + key))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(path + " has too few items")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(_schema_errors(schema["items"], item, path + "/" + str(index)))
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(path + " is empty")
    if type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        errors.append(path + " is below the minimum")
    for child in schema.get("allOf", []):
        errors.extend(_schema_errors(child, value, path))
    if "not" in schema and not _schema_errors(schema["not"], value, path):
        errors.append(path + " contains a forbidden field combination")
    if "if" in schema:
        branch = "then" if not _schema_errors(schema["if"], value, path) else "else"
        errors.extend(_schema_errors(schema.get(branch, {}), value, path))
    return errors


def validate_call(core_definitions, profile, name, arguments):
    definitions = {d["name"]: d for d in tool_definitions(core_definitions, profile)}
    if name not in definitions:
        raise ToolRejection("Tool is not in this declared public role interface", code="tool_not_in_profile", category="capability_gap", context={"tool": name, "interface_profile": profile})
    errors = _schema_errors(definitions[name]["parameters"], arguments)
    if errors:
        raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error", context={"tool": name, "interface_profile": profile})


class WorkInterface:
    """Host-bound port. Restrictions are checked inside the real world command."""

    def __init__(self, session, role, *, audit_dir=None, variant="v13"):
        if session.project_id is None:
            raise ValueError("Work interface requires a bound project")
        self._session = session
        self.profile = profile_id(role)
        if variant not in {"v13", "legacy"}:
            raise ValueError("Unknown declared interface comparison variant")
        self.variant = variant
        if variant == "legacy":
            self.profile = LEGACY_INTERFACE + ":" + role
        self.audit_dir = Path(audit_dir) if audit_dir is not None else None
        self.projections = []

    def tools(self):
        return tool_definitions(self._session.tools(), self.profile)

    def observe(self):
        original = self._session.observe()
        # Drop only redundant installation/project metadata. All work contracts,
        # visible references, routes, adoptions, issues and evidence remain.
        selected = copy.deepcopy(original)
        selected["projects"] = original["projects"] if self.variant == "legacy" else {
            pid: {key: copy.deepcopy(project[key]) for key in ("status", "participants", "title", "description") if key in project}
            for pid, project in original.get("projects", {}).items()
        }
        record = {
            "version": INTERFACE_VERSION, "profile": self.profile,
            "raw_observation": original, "selected_observation_sha256": digest(json_bytes(selected)),
            "selection": {"projects": "retained exactly" if self.variant == "legacy" else ["status", "participants", "title", "description"], "all_other_top_level_fields": "retained exactly"},
            "original_bytes": len(json_bytes(original)), "selected_bytes": len(json_bytes(selected)),
        }
        self.projections.append(record)
        if self.audit_dir is not None:
            self.audit_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(self.audit_dir / (str(len(self.projections)) + ".json"), json_bytes(record))
        return selected

    def call(self, action, request_key=None, **arguments):
        return self._session._world.act(
            self._session.actor_id, "project_action",
            {"project_id": self._session.project_id, "tool": action, "arguments": arguments, "interface_profile": self.profile},
            request_key=request_key,
        )
