"""World-first contracts and atomic, state-only project package installation.

A package declares present materials and obligations. It cannot introduce actors,
world powers, historical approvals or messages. Persistence and initial object
version creation belong to the runtime's existing single-writer transaction.
"""

import copy
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import PurePosixPath

from ..policies.organization import require_authority
from .references import VersionRef, resolve_version
from .adoption import make_binding, validate_policy_contract
from .publication import PUBLICATION_POLICIES
from .maintenance import normalize_rules
from ..adapters.capabilities import capability_for, encode
from ..domains.work_product import validate_content_contract

WORLD_SCHEMA_VERSION = "world-core-v0.9"
PROVENANCE_KINDS = frozenset({"observed", "reconstructed", "synthetic", "unknown"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


@dataclass(frozen=True)
class WorldSpec:
    world_id: str
    actors: dict | list
    applications: tuple | list = ("files",)
    bootstrap_grants: tuple | list = ()
    event_policy: dict = field(default_factory=dict)
    publication_policy: str = "explicit"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class WorkContext:
    world_id: str
    project_id: str
    work_id: str
    requirement_version: int
    purpose: str
    period: str | None = None
    requirement_dimension: str = "requirements"
    work_node: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ScopedGrant:
    actor_id: str
    power: str
    project_id: str
    subject: str = "*"
    work_nodes: tuple | list = ("*",)
    object_ids: tuple | list = ("*",)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProjectPackage:
    project_id: str
    goal: str
    participants: list | tuple
    objects: list | tuple = ()
    works: list | tuple = ()
    grants: list | tuple = ()
    adoptions: list | tuple = ()
    provenance: dict = field(
        default_factory=lambda: {"kind": "unknown", "source_evidence_refs": []}
    )
    close_policy: dict = field(default_factory=lambda: {"pending_obligations": "retain"})
    publication_policy: str | None = None
    information_routes: list | tuple = ()
    maintenance_rules: list | tuple = ()

    def to_dict(self):
        return asdict(self)


def _mapping(value, label):
    if is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain finite JSON values") from error


def _identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _known_actor(state, actor):
    if actor not in state["actors"]:
        raise ValueError(f"Unknown actor: {actor}")
    return actor


def _keys(value, allowed, label):
    if set(value) - set(allowed):
        raise ValueError(f"Unsupported {label} fields: {sorted(set(value) - set(allowed))}")


def provenance(value):
    """Validate attribution without synthesizing unobserved workflow events."""
    result = _mapping(value, "provenance")
    _keys(result, {"kind", "source_evidence_refs", "note"}, "provenance")
    if result.get("kind") not in PROVENANCE_KINDS:
        raise ValueError("Provenance must distinguish observed/reconstructed/synthetic/unknown")
    refs = _list(result.setdefault("source_evidence_refs", []), "source evidence refs")
    if any(not isinstance(ref, (str, dict)) or not ref for ref in refs):
        raise ValueError("Source evidence refs must be nonempty strings or structured references")
    if result["kind"] == "observed" and not refs:
        raise ValueError("Observed provenance requires source evidence")
    return result


def new_world_state(spec):
    """Bootstrap trusted identities and explicit world powers, with zero projects."""
    spec = _mapping(spec, "WorldSpec")
    _keys(
        spec,
        {
            "world_id",
            "actors",
            "applications",
            "bootstrap_grants",
            "event_policy",
            "publication_policy",
        },
        "world",
    )
    world_id = _identifier(spec.get("world_id"), "world identity")
    raw_actors = spec.get("actors")
    if isinstance(raw_actors, list):
        actors = {}
        for record in raw_actors:
            record = _mapping(record, "actor")
            aid = _identifier(record.get("actor_id", record.get("role_id")), "actor identity")
            if aid in actors:
                raise ValueError("Duplicate actor identity")
            actors[aid] = {**record, "actor_id": aid}
    elif isinstance(raw_actors, dict):
        actors = {}
        for aid, record in raw_actors.items():
            _identifier(aid, "actor identity")
            record = _mapping(record, "actor")
            if record.get("actor_id", aid) != aid:
                raise ValueError("Actor registry identity mismatch")
            actors[aid] = {**record, "actor_id": aid}
    else:
        raise ValueError("World actors must be a registry or list")
    grants = _list(spec.get("bootstrap_grants", []), "bootstrap grants")
    for grant in grants:
        _keys(
            grant,
            {"actor_id", "power", "subject", "scope", "work_nodes", "object_ids"},
            "bootstrap grant",
        )
        if grant.get("actor_id") not in actors or grant.get("scope") != "world":
            raise ValueError("Bootstrap grants require known actors and explicit world scope")
        _text(grant.get("power"), "bootstrap power")
        grant.setdefault("subject", "*")
    applications = _list(spec.get("applications", ["files"]), "applications")
    if not applications or set(applications) - {"files", "spreadsheets", "sql"}:
        raise ValueError("Applications must select files, spreadsheets and/or sql")
    event_policy = _mapping(spec.get("event_policy", {}), "event policy")
    publication_policy = spec.get("publication_policy", "explicit")
    if publication_policy not in PUBLICATION_POLICIES:
        raise ValueError("Unknown world publication policy")
    state = {
        "schema_version": WORLD_SCHEMA_VERSION,
        "runtime_kind": "world_core",
        "semantics_version": "work-world-v0.9",
        "world_id": world_id,
        "instance_id": uuid.uuid4().hex,
        "branch_id": uuid.uuid4().hex,
        "parent_branch_id": None,
        "clock": 0,
        "state_revision": 0,
        "operation_commits": {},
        "actors": actors,
        "roles": [{**record, "role_id": aid} for aid, record in actors.items()],
        "applications": applications,
        "event_policy": event_policy,
        "publication_policy": publication_policy,
        "releases": [],
        "maintenance_impacts": {},
        "issues": {},
        "issue_responses": {},
        "issue_decisions": {},
        "information_updates": [],
        "organization": {"positions": {}, "grants": grants},
        "world_status": "running",
        "projects": {},
        "workspaces": {},
        "artifacts": {},
        "work_items": {},
        "work_replacements": {},
        "shares": [],
        "adoptions": {},
        "episodes": {},
        "attestations": {},
        "condition_specs": {},
        "condition_responses": {},
        "raw_condition_responses": {},
        "requests": {},
        "handoffs": {},
        "blockers": {},
        "future_opportunities": [],
        "knowledge": {aid: {"read_artifacts": [], "read_messages": []} for aid in actors},
    }
    for key in (
        "messages",
        "events",
        "event_history",
        "event_attempts",
        "interactions",
        "evaluations",
        "calls",
        "requirement_events",
        "project_history",
        "observations",
    ):
        state[key] = []
    return state


def _work_id(project_id, local_id):
    return f"{project_id}::{_identifier(local_id, 'local work identity')}"


def object_identity(project_id, alias):
    """Separate world material and project aliases with an unambiguous tuple key.

    The compact digest is a storage identifier, not a source of authority. All
    registration paths must still reject an already registered identifier.
    """
    if project_id is not None:
        _identifier(project_id, "project identity")
    _identifier(alias, "object alias")
    encoded = json.dumps([project_id, alias], separators=(",", ":")).encode()
    return "obj-" + hashlib.sha256(encoded).hexdigest()[:24]


def _filename(value, kind="json"):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Object filename must be a relative JSON name")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.name != value
        or path.suffix != capability_for(kind).suffix
    ):
        raise ValueError("Object filename must match its supported file kind")
    return value


def _actors(state, values, label):
    values = _list(values, label)
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate actors in {label}")
    return [_known_actor(state, value) for value in values]


def validate_deliverable_contract(contract):
    contract = _mapping(contract, "deliverable contract")
    _keys(
        contract,
        {
            "min_files",
            "max_files",
            "allowed_roles",
            "required_fields",
            "allowed_kinds",
            "content_checks",
            "description",
        },
        "deliverable contract",
    )
    minimum, maximum = contract.get("min_files", 1), contract.get("max_files", 10)
    if type(minimum) is not int or type(maximum) is not int or not 1 <= minimum <= maximum:
        raise ValueError("Deliverable file count bounds must be positive integers")
    contract.update(min_files=minimum, max_files=maximum)
    for key in ("allowed_roles", "required_fields"):
        values = _list(contract.setdefault(key, []), key)
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f"{key} must contain nonempty strings")
    kinds = _list(contract.setdefault("allowed_kinds", []), "allowed_kinds")
    for kind in kinds:
        capability_for(kind)
    return validate_content_contract(contract)


def validate_package(state, package):
    """Return a complete normalized install plan without changing world facts.

    All references, aliases, participants, scopes and adoption access are checked
    before any registration. This is a current-state contract, not a migration of
    fabricated histories from files.
    """
    if state.get("schema_version") != WORLD_SCHEMA_VERSION or "projects" not in state:
        raise ValueError("Project packages require a World Core v0.8 state")
    raw = _mapping(package, "ProjectPackage")
    _keys(
        raw,
        {
            "project_id",
            "goal",
            "participants",
            "objects",
            "works",
            "grants",
            "adoptions",
            "provenance",
            "close_policy",
            "publication_policy",
            "information_routes",
            "maintenance_rules",
        },
        "package",
    )
    pid = _identifier(raw.get("project_id"), "project identity")
    if pid in state["projects"]:
        raise ValueError("Project identity is already registered")
    goal = _text(raw.get("goal"), "project goal")
    participants = _actors(state, raw.get("participants"), "participants")
    package_provenance = provenance(raw.get("provenance", {"kind": "unknown"}))
    close_policy = _mapping(
        raw.get("close_policy", {"pending_obligations": "retain"}), "close policy"
    )
    _keys(close_policy, {"pending_obligations"}, "close policy")
    if close_policy.get("pending_obligations") not in {"retain", "cancel"}:
        raise ValueError("Closing must declare retain or cancel for pending obligations")
    publication_policy = raw.get("publication_policy") or state["publication_policy"]
    if publication_policy not in PUBLICATION_POLICIES:
        raise ValueError("Unknown project publication policy")
    objects, aliases = [], {}
    for value in _list(raw.get("objects", []), "objects"):
        value = _mapping(value, "object")
        _keys(
            value,
            {
                "alias",
                "filename",
                "data",
                "owner",
                "readers",
                "writers",
                "kind",
                "deliverable_role",
                "provenance",
            },
            "object",
        )
        alias = _identifier(value.get("alias"), "object alias")
        oid = object_identity(pid, alias)
        if alias in aliases or oid in state["artifacts"]:
            raise ValueError("Object identity or alias is already registered")
        kind = value.get("kind", "json")
        if capability_for(kind).application not in state["applications"]:
            raise ValueError("Object capability is not enabled in this world")
        owner = _known_actor(state, value.get("owner"))
        if owner not in participants:
            raise ValueError("Project object owner must be a project participant")
        readers = _actors(state, value.get("readers", [owner]), "readers")
        writers = _actors(state, value.get("writers", [owner]), "writers")
        if owner not in readers or owner not in writers or not set(writers) <= set(readers):
            raise ValueError("Object owner and writers must have readable access")
        if not set(readers + writers) <= set(participants):
            raise ValueError("Package object permissions must name project participants")
        if not isinstance(value.get("data"), dict):
            raise ValueError("Initial object data must be a JSON object")
        encode(kind, value["data"])  # Validate bytes before any project or grant registration.
        filename = _filename(value.get("filename"), kind)
        aliases[alias] = oid
        objects.append(
            {
                **value,
                "object_id": oid,
                "project_id": pid,
                "alias": alias,
                "filename": filename,
                "kind": kind,
                "deliverable_role": value.get("deliverable_role", "draft"),
                "owner": owner,
                "readers": readers,
                "writers": writers,
                "storage_path": f"artifacts/{oid}/{filename}",
                "provenance": provenance(value.get("provenance", package_provenance)),
            }
        )
    adoptions = []
    work_locals = []
    raw_works = _list(raw.get("works", []), "works")
    for work in raw_works:
        if not isinstance(work, dict):
            raise ValueError("Work must be an object")
        local = _identifier(work.get("work_id"), "local work identity")
        if local in work_locals:
            raise ValueError("Duplicate local work identity")
        work_locals.append(local)
    for value in _list(raw.get("adoptions", []), "adoptions"):
        value = _mapping(value, "adoption")
        _keys(
            value,
            {"alias", "object_id", "version_id", "policy", "work_ids", "provenance"},
            "adoption",
        )
        alias = _identifier(value.get("alias"), "adoption alias")
        if alias in aliases:
            raise ValueError("Adoption alias conflicts with workspace")
        reference = VersionRef.from_mapping(value)
        resolve_version(state, reference)
        if value.get("policy") not in {"current_applicable", "current_published", "fixed"}:
            raise ValueError("Adoption requires a supported current or fixed policy")
        visible = set()
        for share in state.get("shares", []):
            if (
                share.get("project_id") == pid
                and share.get("object_id") == reference.object_id
                and share.get("version_id") == reference.version_id
            ):
                visible.update(share.get("actor_ids", []))
        if not set(participants) <= visible:
            raise ValueError(
                "Adoption requires prior explicit project and participant version sharing"
            )
        nodes = _list(value.get("work_ids", work_locals), "adoption work IDs")
        if not set(nodes) <= set(work_locals):
            raise ValueError("Adoption targets unknown project work")
        aliases[alias] = reference.object_id
        adoptions.append(
            {
                **value,
                "adoption_id": f"{pid}::{alias}",
                "project_id": pid,
                "work_ids": [_work_id(pid, wid) for wid in nodes],
                "provenance": provenance(value.get("provenance", package_provenance)),
            }
        )
    works = []
    for value in raw_works:
        _keys(
            value,
            {
                "work_id",
                "owner",
                "goal",
                "dependencies",
                "inputs",
                "deliverables",
                "deliverable_contract",
                "approval_policy",
                "required_credentials",
                "requirements",
                "visible_requirements",
                "purpose",
                "period",
                "requirement_dimension",
                "provenance",
            },
            "work",
        )
        local = value["work_id"]
        wid = _work_id(pid, local)
        if wid in state["work_items"]:
            raise ValueError("World work identity is already registered")
        owner = _known_actor(state, value.get("owner"))
        if owner not in participants:
            raise ValueError("Work owner must participate in project")
        deps = _list(value.get("dependencies", []), "work dependencies")
        if not set(deps) <= set(work_locals) or local in deps:
            raise ValueError("Unknown or self-referential work dependency")
        inputs = _list(value.get("inputs", []), "work inputs")
        deliverables = _list(value.get("deliverables", []), "deliverables")
        if not set(inputs + deliverables) <= set(aliases):
            raise ValueError("Work refers to an unknown workspace alias")
        policy = value.get("approval_policy", "review")
        if policy not in {"review", "delivery_only"}:
            raise ValueError("Approval policy must be review or delivery_only")
        credentials = _list(value.get("required_credentials", []), "required credentials")
        for ref in credentials:
            resolve_version(state, ref)
        item = {
            "work_item_id": wid,
            "node_id": wid,
            "root_work_id": wid,
            "local_work_id": local,
            "project_id": pid,
            "owner_role": owner,
            "goal": _text(value.get("goal", goal), "work goal"),
            "requirement_version": 1,
            "status": "open",
            "applicability": "current",
            "dependencies": [_work_id(pid, dep) for dep in deps],
            "inputs": [aliases[name] for name in inputs],
            "deliverables": [aliases[name] for name in deliverables],
            "required_credentials": credentials,
            "approval_policy": policy,
            "requirements": _mapping(value.get("requirements", {}), "work requirements"),
            "visible_requirements": _list(
                value.get("visible_requirements", []), "visible requirements"
            ),
            "purpose": value.get("purpose", "delivery"),
            "period": value.get("period"),
            "requirement_dimension": value.get("requirement_dimension", "requirements"),
            "activated_at": state["clock"],
            "origin_event": "project_installed",
            "submissions": [],
            "artifact_edits": [],
            "blocker": None,
            "blocker_ids": [],
            "provenance": provenance(value.get("provenance", package_provenance)),
        }
        if "deliverable_contract" in value:
            item["deliverable_contract"] = validate_deliverable_contract(
                value["deliverable_contract"]
            )
        elif not deliverables:
            raise ValueError(
                "Work must declare fixed deliverables or a dynamic deliverable contract"
            )
        validate_policy_contract(item)
        works.append(item)
    expanded_adoptions = []
    by_work = {item["work_item_id"]: item for item in works}
    for declaration in adoptions:
        if not declaration["work_ids"]:
            raise ValueError("Adoption must bind at least one exact work")
        for wid in declaration["work_ids"]:
            binding = make_binding(
                state,
                by_work[wid],
                declaration["alias"],
                declaration["object_id"],
                declaration["version_id"],
                declaration["policy"],
                by_work[wid]["owner_role"],
            )
            binding["provenance"] = declaration["provenance"]
            expanded_adoptions.append(binding)
    adoptions = expanded_adoptions
    graph = {item["work_item_id"]: item["dependencies"] for item in works}
    pending, done = set(graph), set()
    while pending:
        ready = {wid for wid in pending if set(graph[wid]) <= done}
        if not ready:
            raise ValueError("Cyclic work dependencies")
        pending -= ready
        done |= ready
    grants = []
    for value in _list(raw.get("grants", []), "grants"):
        value = _mapping(value, "grant")
        _keys(
            value,
            {"actor_id", "power", "subject", "project_id", "scope", "work_nodes", "object_ids"},
            "grant",
        )
        actor = _known_actor(state, value.get("actor_id"))
        if (
            actor not in participants
            or value.get("project_id", pid) != pid
            or value.get("scope", "project") != "project"
        ):
            raise ValueError("Package grant exceeds its project or participants")
        power = _text(value.get("power"), "grant power")
        if power in {"*", "install_project", "create_world", "register_actor"}:
            raise ValueError("A project package cannot grant world bootstrap powers")
        nodes = _list(value.get("work_nodes", ["*"]), "grant work scope")
        object_ids = _list(value.get("object_ids", ["*"]), "grant object scope")
        if (
            not nodes
            or not object_ids
            or ("*" in nodes and nodes != ["*"])
            or ("*" in object_ids and object_ids != ["*"])
        ):
            raise ValueError("Grant scopes must be explicit nonempty sets or a single wildcard")
        if nodes != ["*"] and not set(nodes) <= set(work_locals):
            raise ValueError("Grant targets unknown project work")
        if object_ids != ["*"] and not set(object_ids) <= set(aliases):
            raise ValueError("Grant targets unknown project object")
        grants.append(
            {
                "actor_id": actor,
                "power": power,
                "subject": value.get("subject", "*"),
                "scope": "project",
                "project_id": pid,
                "work_nodes": nodes if nodes == ["*"] else [_work_id(pid, node) for node in nodes],
                "object_ids": object_ids
                if object_ids == ["*"]
                else [aliases[obj] for obj in object_ids],
            }
        )
    routes = []
    object_plan = {obj["object_id"]: obj for obj in objects}
    seen_routes = set()
    for route in _list(raw.get("information_routes", []), "information routes"):
        route = _mapping(route, "information route")
        _keys(
            route,
            {
                "route_id",
                "work_id",
                "provider",
                "object_alias",
                "purpose",
                "delay",
                "availability",
                "version_id",
                "version_policy",
                "mode",
                "recipients",
            },
            "information route",
        )
        route_id = _identifier(route.get("route_id"), "route identity")
        if route_id in seen_routes or route.get("work_id") not in work_locals:
            raise ValueError("Route identity duplicate or work unknown")
        seen_routes.add(route_id)
        provider = route.get("provider")
        oid = aliases.get(route.get("object_alias"))
        obj = object_plan.get(oid)
        mode = route.get("mode", "automatic")
        if mode not in {"automatic", "manual"}:
            raise ValueError("Information route mode must be automatic or manual")
        if (provider not in participants or obj is None
                or provider not in (obj["readers"] if mode == "manual" else obj["writers"])):
            raise ValueError("Information route requires its declared readable/delegated provider")
        recipients = route.get(
            "recipients", [by_work[_work_id(pid, route["work_id"])]["owner_role"]]
        )
        if (not isinstance(recipients, list) or not recipients
                or len(recipients) != len(set(recipients))
                or not set(recipients) <= set(participants)):
            raise ValueError("Information route recipients must be distinct project participants")
        delay = route.get("delay", 3)
        availability = route.get("availability", "available")
        if (
            type(delay) is not int
            or not 1 <= delay <= 100
            or availability not in {"available", "unavailable"}
        ):
            raise ValueError("Unsupported information route delivery policy")
        if route.get("version_policy", "fixed") not in {
            "fixed",
            "current_published",
            "work_requirement",
        }:
            raise ValueError("Unsupported information route version policy")
        if route.get("version_id", "v1") != "v1":
            raise ValueError("Package routes must reference their real initial version")
        purpose = _text(route.get("purpose", "evidence"), "route purpose")
        wid = _work_id(pid, route["work_id"])
        if not any(
            g["actor_id"] == provider
            and g["power"] == "provide"
            and g["subject"] in {purpose, "*"}
            and (g["work_nodes"] == ["*"] or wid in g["work_nodes"])
            and (g["object_ids"] == ["*"] or oid in g["object_ids"])
            for g in grants
        ):
            raise ValueError("Information provider lacks the declared work/object power")
        routes.append(
            {
                **route,
                "route_id": route_id,
                "mode": mode,
                "recipients": recipients,
                "project_id": pid,
                "work_id": wid,
                "work_node": wid,
                "object_id": oid,
                "version_id": "v1",
                "version_policy": route.get("version_policy", "fixed"),
                "purpose": purpose,
                "delay": delay,
                "availability": availability,
                "availability_revision": 0,
            }
        )
    return {
        "project": {
            "project_id": pid,
            "goal": goal,
            "participants": participants,
            "status": "active",
            "started_at": state["clock"],
            "work_ids": [item["work_item_id"] for item in works],
            "close_policy": close_policy,
            "publication_policy": publication_policy,
            "information_routes": routes,
            "maintenance_rules": _list(raw.get("maintenance_rules", []), "maintenance rules"),
            "maintenance_heads": {},
            "provenance": package_provenance,
        },
        "objects": objects,
        "workspace": aliases,
        "works": works,
        "grants": grants,
        "adoptions": adoptions,
    }


def install_package(state, package, actor):
    """Atomically register a validated package; return initial object write payloads."""
    plan = validate_package(state, package)
    require_authority(state, actor, "install_project", "project")
    installed = copy.deepcopy(state)
    project = plan["project"]
    pid = project["project_id"]
    installed["projects"][pid] = project
    installed["workspaces"][pid] = plan["workspace"]
    installed["work_items"].update({item["work_item_id"]: item for item in plan["works"]})
    installed["organization"]["grants"].extend(plan["grants"])
    installed["adoptions"].update({item["adoption_id"]: item for item in plan["adoptions"]})
    for value in plan["objects"]:
        oid = value["object_id"]
        installed["artifacts"][oid] = {
            key: copy.deepcopy(value[key]) for key in value if key != "data"
        }
        installed["artifacts"][oid].update(
            artifact_id=oid,
            semantic_kind="claim",
            versions={},
            current_version=None,
            materialization="workspace",
            version_readers={},
            possibly_stale=False,
        )
    installed["projects"][pid]["maintenance_rules"] = normalize_rules(
        installed, pid, project["maintenance_rules"]
    )
    installed["project_history"].append(
        {"project_id": pid, "actor_id": actor, "at": state["clock"], "event": "installed"}
    )
    state.clear()
    state.update(installed)
    return copy.deepcopy(plan["objects"])
