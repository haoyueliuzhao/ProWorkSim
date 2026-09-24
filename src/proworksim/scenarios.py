"""Finite declarative scenario deployment and external-event host.

This host may inspect world progress to fire declared events. Worker decisions
are supplied by separately bound policies. The host neither imports an evaluator
nor writes world state; deployment and event effects use real public sessions.
"""

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from .core.maintenance import work_stage
from .core.projections import derive_current_work_view
from .core.world import WorldSpec
from .core.work import current_id
from .templates.reconciliation import package as reconciliation_package
from .templates.research_review import BACKGROUND, contract, package as report_package
from .world_core import WorldCore
from .storage import atomic_write, digest, json_bytes

SCENARIO_VERSION = "scenario-v0.10"


def _mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def _keys(value, allowed, label):
    _mapping(value, label)
    if set(value) - set(allowed):
        raise ValueError(
            label + " has unsupported fields: " + str(sorted(set(value) - set(allowed)))
        )


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be nonempty text")


def _list(value, label):
    if not isinstance(value, list):
        raise ValueError(label + " must be a list")
    return value


def _predicate(predicate):
    _mapping(predicate, "predicate")
    if len(predicate) != 1:
        raise ValueError("A predicate selects exactly one finite condition")
    kind, value = next(iter(predicate.items()))
    if kind == "all":
        if not _list(value, "all"):
            raise ValueError("all requires conditions")
        for item in value:
            _predicate(item)
    elif kind == "clock_at_least":
        if type(value) is not int or value < 0:
            raise ValueError("clock_at_least must be a nonnegative integer")
    elif kind == "event_fired":
        _text(value, "event identity")
    elif kind == "work":
        _keys(value, {"project", "node", "phase", "source_alias"}, "work predicate")
        for key in ("project", "node"):
            _text(value.get(key), key)
        if value.get("phase") not in {
            "before_read",
            "after_read",
            "output_ready",
            "pending",
            "accepted",
            "blocked",
        }:
            raise ValueError("Unsupported work phase")
        if value["phase"] in {"before_read", "after_read"} and not value.get("source_alias"):
            raise ValueError("Read phases require an exact source_alias")
    else:
        raise ValueError("Unsupported predicate: " + kind)


def _action(action):
    _keys(action, {"actor", "project", "tool", "arguments"}, "controller action")
    for key in ("actor", "tool"):
        _text(action.get(key), key)
    if action.get("project") is not None:
        _text(action["project"], "project")
    _mapping(action.get("arguments", {}), "action arguments")


def validate_scenario(spec):
    """Validate the finite schema; package authority/content checks stay in core."""
    try:
        spec = json.loads(json.dumps(spec, allow_nan=False))
    except (ValueError, TypeError) as error:
        raise ValueError("Scenario must contain finite JSON values") from error
    _keys(
        spec,
        {
            "version",
            "scenario_id",
            "description",
            "world",
            "installer",
            "projects",
            "roles",
            "setup",
            "events",
            "start",
            "boundary",
            "variation",
        },
        "scenario",
    )
    if spec.get("version") != SCENARIO_VERSION:
        raise ValueError("Unsupported scenario version")
    _text(spec.get("scenario_id"), "scenario_id")
    _mapping(spec.get("world"), "world")
    _text(spec.get("installer"), "installer")
    if not _list(spec.get("projects"), "projects"):
        raise ValueError("Scenario needs projects")
    for project in spec["projects"]:
        _keys(project, {"recipe", "parameters", "package"}, "project declaration")
        if ("recipe" in project) == ("package" in project):
            raise ValueError("Project selects exactly one package or recipe")
        if "package" in project:
            _mapping(project["package"], "project package")
        else:
            if project["recipe"] not in {"reconciliation", "research_review", "linked_report"}:
                raise ValueError("Unsupported template recipe")
            _mapping(project.get("parameters", {}), "recipe parameters")
    role_ids = set()
    for role in _list(spec.get("roles"), "roles"):
        _keys(role, {"role_id", "actor", "project", "policy", "config"}, "role binding")
        for key in ("role_id", "actor", "project", "policy"):
            _text(role.get(key), key)
        if role["policy"] not in {"reconciliation", "report_author", "reviewer"}:
            raise ValueError("Unsupported declared policy: " + role["policy"])
        if role["role_id"] in role_ids:
            raise ValueError("Duplicate role identity")
        role_ids.add(role["role_id"])
        _mapping(role.setdefault("config", {}), "policy config")
    for action in _list(spec.setdefault("setup", []), "setup"):
        _action(action)
    event_ids = set()
    for event in _list(spec.setdefault("events", []), "events"):
        _keys(event, {"event_id", "when", "effects", "fire_once"}, "event")
        _text(event.get("event_id"), "event_id")
        if event["event_id"] in event_ids:
            raise ValueError("Duplicate event identity")
        event_ids.add(event["event_id"])
        if event.get("fire_once") is not True:
            raise ValueError("Only explicit fire_once events are supported")
        _predicate(event.get("when"))
        if not _list(event.get("effects"), "effects"):
            raise ValueError("External event needs declared effects")
        for effect in event["effects"]:
            _action(effect)
    start = spec.setdefault("start", {"kind": "initial"})
    _keys(start, {"kind", "when", "max_opportunities"}, "start")
    if start.get("kind") not in {"initial", "executed_prefix"}:
        raise ValueError("Start must be initial or executed_prefix")
    if start["kind"] == "executed_prefix":
        _predicate(start.get("when"))
        if type(start.get("max_opportunities")) is not int or start["max_opportunities"] < 1:
            raise ValueError("Prefix requires a positive opportunity bound")
    boundary = spec.setdefault("boundary", {"max_opportunities": 500})
    _keys(boundary, {"max_opportunities", "complete_when"}, "boundary")
    if type(boundary.get("max_opportunities")) is not int or boundary["max_opportunities"] < 1:
        raise ValueError("Boundary requires a positive opportunity bound")
    if "complete_when" in boundary:
        _predicate(boundary["complete_when"])
    return spec


def _continuous(package, owner, reviewer, source_alias, output_alias):
    work = package["works"][0]
    work["requirements"].update(output_alias=output_alias)
    work["requirements"]["input_policies"][source_alias] = "current_published"
    work["requirements"]["input_versions"].pop(source_alias, None)
    package["grants"].append(
        {
            "actor_id": reviewer,
            "power": "revise_requirement",
            "subject": "requirements",
            "work_nodes": [work["work_id"]],
        }
    )
    package["maintenance_rules"] = [
        {
            "rule_id": "source-active",
            "source": {"alias": source_alias},
            "work_nodes": [work["work_id"]],
            "when": ["after_read", "output_ready", "pending"],
            "effect": "revise",
            "actor": reviewer,
            "updates": {"goal": "Reconcile the newly published source"},
        },
        {
            "rule_id": "source-accepted",
            "source": {"alias": source_alias},
            "work_nodes": [work["work_id"]],
            "when": ["accepted"],
            "effect": "successor",
            "actor": reviewer,
            "updates": {"goal": "Maintain comparison after source publication"},
        },
    ]
    return package


def project_package(declaration):
    """Expand a finite existing-template recipe; no historical facts are seeded."""
    if "package" in declaration:
        return copy.deepcopy(declaration["package"])
    recipe, params = declaration["recipe"], copy.deepcopy(declaration.get("parameters", {}))
    if recipe == "reconciliation":
        continuous = params.pop("continuous", False)
        output_alias = params.pop("output_alias", "comparison")
        public_delivery = params.pop("public_delivery", {})
        package = reconciliation_package(**params)
        owner = package["works"][0]["owner"]
        reviewer = next(p for p in package["participants"] if p != owner)
        package["works"][0]["requirements"].update(
            output_alias=output_alias, public_delivery=public_delivery
        )
        package["objects"].append(
            {
                "alias": output_alias,
                "filename": output_alias + ".json",
                "owner": owner,
                "readers": [owner, reviewer],
                "kind": "json",
                "deliverable_role": "reconciliation",
                "data": {},
            }
        )
        if continuous:
            _continuous(
                package,
                owner,
                reviewer,
                "external_schedule" if params.get("variant") else "statement",
                output_alias,
            )
        return package
    if recipe == "research_review":
        package = report_package(**params)
        package["works"][0]["requirements"]["output_alias"] = "report"
        return package
    _keys(
        params,
        {"project_id", "author", "reviewer", "source_project", "source_alias"},
        "linked report parameters",
    )
    pid, author, reviewer = (
        params.get("project_id", "REPORT"),
        params.get("author", "author"),
        params.get("reviewer", "reviewer"),
    )
    source_pid, source_alias = (
        params.get("source_project", "FINANCE"),
        params.get("source_alias", "comparison"),
    )
    reference = {"$object": {"project": source_pid, "alias": source_alias}}
    spec = {
        "kind": "research_report",
        "path": ["report"],
        "sources": [{"alias": "comparison", "reference_path": ["sources", "comparison"]}],
        "claims": [
            {
                "claim_id": key,
                "section_id": key,
                "label": label,
                "source_alias": "comparison",
                "value_path": ["reconciliation", "summary", key],
                "period_path": ["reconciliation", "period"],
            }
            for key, label in (("conflict", "Conflicts"), ("incomparable", "Incomparable"))
        ],
    }
    return {
        "project_id": pid,
        "goal": "Maintain finite reader-facing reconciliation assertions",
        "participants": [author, reviewer],
        "objects": [
            {
                "alias": "report",
                "filename": "report.json",
                "owner": author,
                "readers": [author, reviewer],
                "kind": "json",
                "deliverable_role": "report",
                "data": {
                    "report": {
                        "sections": [{"section_id": "context", "body": BACKGROUND, "claims": []}]
                    }
                },
            }
        ],
        "works": [
            {
                "work_id": "research",
                "owner": author,
                "approval_policy": "review",
                "goal": "Report the current published comparison",
                "requirements": {
                    "input_policy": "current_published",
                    "output_alias": "report",
                    "source_objects": {"comparison": reference},
                },
                "deliverable_contract": contract(spec),
            }
        ],
        "grants": [
            {"actor_id": author, "power": power, "subject": "artifact", "work_nodes": ["research"]}
            for power in ("adopt", "create_object")
        ]
        + [
            {
                "actor_id": reviewer,
                "power": power,
                "subject": "deliverable",
                "work_nodes": ["research"],
            }
            for power in ("review", "approve")
        ]
        + [
            {
                "actor_id": reviewer,
                "power": "revise_requirement",
                "subject": "requirements",
                "work_nodes": ["research"],
            }
        ],
        "maintenance_rules": [
            {
                "rule_id": "comparison-active",
                "source": {"object_id": reference, "source_project": source_pid},
                "work_nodes": ["research"],
                "when": ["after_read", "output_ready", "pending"],
                "effect": "revise",
                "actor": reviewer,
                "updates": {"goal": "Express the newly published comparison"},
            },
            {
                "rule_id": "comparison-accepted",
                "source": {"object_id": reference, "source_project": source_pid},
                "work_nodes": ["research"],
                "when": ["accepted"],
                "effect": "successor",
                "actor": reviewer,
                "updates": {"goal": "Maintain report after comparison publication"},
            },
        ],
    }


def resolve_references(world, value):
    """Resolve declared object selectors against installed workspace identities."""
    if isinstance(value, list):
        return [resolve_references(world, item) for item in value]
    if not isinstance(value, dict):
        return value
    if "$object" in value:
        if set(value) != {"$object"}:
            raise ValueError("Object reference cannot contain other fields")
        ref = value["$object"]
        _keys(ref, {"project", "alias"}, "object reference")
        try:
            return world.state["workspaces"][ref["project"]][ref["alias"]]
        except (KeyError, TypeError) as error:
            raise ValueError("Unresolved installed object reference: " + str(ref)) from error
    return {key: resolve_references(world, item) for key, item in value.items()}


def _public_call(world, action, request_key):
    arguments = resolve_references(world, action.get("arguments", {}))
    result = world.session(action["actor"], action.get("project")).call(
        action["tool"], request_key=request_key, **arguments
    )
    return {
        "kind": "controller",
        "actor": action["actor"],
        "project": action.get("project"),
        "tool": action["tool"],
        "arguments": copy.deepcopy(arguments),
        "result": copy.deepcopy(result),
    }


def initial_business_state(world):
    """Compare all business state and bytes; exclude only declared diagnostics.

    Only root instance/branch identities, interaction wall-clock durations and
    receipt/transition state digests are excluded. Logical clock/at, command IDs,
    calls, revisions, ordering, authority, bytes, routes and obligations remain.
    """

    def normalize(value, path=()):
        if isinstance(value, dict):
            return {
                key: normalize(item, path + (key,))
                for key, item in value.items()
                if not (
                    (not path and key in {"instance_id", "branch_id", "parent_branch_id"})
                    or (key == "wall_seconds" and len(path) == 2 and path[0] == "interactions")
                    or (key == "state_digests" and path and path[-1] in {"receipt", "transition"})
                )
            }
        if isinstance(value, list):
            return [normalize(item, path + (index,)) for index, item in enumerate(value)]
        return value

    state = copy.deepcopy(world.state)
    result = {"state": normalize(state), "immutable_files": {}}
    for oid, artifact in state["artifacts"].items():
        for version in artifact["versions"]:
            result["immutable_files"][oid + ":" + version] = (
                world.store.version_path(artifact, version).read_bytes().hex()
            )
    return result


@dataclass
class ScenarioDeployment:
    spec: dict
    world: WorldCore | None = None
    status: str = "ready"
    diagnostics: list = field(default_factory=list)
    deployment_log: list = field(default_factory=list)
    prefix: dict = field(default_factory=lambda: {"prefix_executed": False})

    def role_bindings(self):
        return copy.deepcopy(self.spec.get("roles", [])) if self.status == "ready" else []

    def prepare_start(self, runtime, controller=None):
        """Reach a declared start only through completed runtime opportunities."""
        start = self.spec["start"]
        if self.status != "ready" or start["kind"] == "initial":
            return self.prefix
        controller = controller or ScenarioController(self, recorder=runtime.recorder)
        controller.recorder = runtime.recorder
        begin = len(runtime.recorder.events)
        results = []
        failure_reason = "Declared prefix target was not reached within its bound"
        for index in range(start["max_opportunities"] + 1):
            effects = controller.tick()
            if any(event["status"] != "executed" for event in effects):
                failure_reason = "Declared external event was rejected during prefix execution"
                break
            if controller.matches(start["when"]):
                self.prefix = {
                    "prefix_executed": True,
                    "status": "reached",
                    "opportunities": results,
                    "experience_range": [begin, len(runtime.recorder.events)],
                    "experience_sha256": digest(json_bytes(runtime.recorder.events[begin:])),
                    "worker_checkpoint": runtime.snapshot(),
                }
                save_deployment(self)
                return self.prefix
            if index < start["max_opportunities"]:
                results.append(runtime.step())
                controller.record_environment()
        self.prefix = {
            "prefix_executed": True,
            "status": "unbuildable",
            "reason": failure_reason,
            "opportunities": results,
            "experience_range": [begin, len(runtime.recorder.events)],
            "experience_sha256": digest(json_bytes(runtime.recorder.events[begin:])),
            "worker_checkpoint": runtime.snapshot(),
        }
        self.status = "unbuildable"
        self.diagnostics.append(self.prefix["reason"])
        save_deployment(self)
        return self.prefix


def _validate_bound_predicate(deployment, predicate, event_ids):
    kind, value = next(iter(predicate.items()))
    if kind == "all":
        for child in value:
            _validate_bound_predicate(deployment, child, event_ids)
    elif kind == "event_fired" and value not in event_ids:
        raise ValueError("Predicate references unknown event: " + value)
    elif kind == "work":
        state = deployment.world.state
        node = value["node"] if "::" in value["node"] else value["project"] + "::" + value["node"]
        item = state["work_items"].get(node)
        if item is None or item["project_id"] != value["project"] or item["node_id"] != node:
            raise ValueError("Predicate requires an installed work node: " + node)
        if (
            value.get("source_alias")
            and value["source_alias"] not in state["workspaces"][value["project"]]
        ):
            raise ValueError("Predicate requires a missing source alias")


def _validate_bound_spec(deployment):
    spec, world = deployment.spec, deployment.world
    event_ids = {event["event_id"] for event in spec["events"]}
    for event in spec["events"]:
        _validate_bound_predicate(deployment, event["when"], event_ids)
        for action in event["effects"]:
            resolve_references(world, action.get("arguments", {}))
            session = world.session(action["actor"], action.get("project"))
            if action["tool"] not in {tool["name"] for tool in session.tools()}:
                raise ValueError("Declared event requires unsupported tool: " + action["tool"])
    for block in (spec["start"], spec["boundary"]):
        predicate = block.get("when", block.get("complete_when"))
        if predicate is not None:
            _validate_bound_predicate(deployment, predicate, event_ids)
    for item in world.state["work_items"].values():
        requirements = item.get("requirements", {})
        workspace = world.state["workspaces"][item["project_id"]]
        for check in item.get("deliverable_contract", {}).get("content_checks", []):
            for source in check.get("sources", []):
                alias = source["alias"]
                oid = requirements.get("source_objects", {}).get(alias, workspace.get(alias))
                if oid not in world.state["artifacts"]:
                    raise ValueError(
                        "Missing required source " + alias + " for " + item["work_item_id"]
                    )
        delivery = requirements.get("public_delivery", {})
        for recipient in delivery.get("recipients", []):
            target = world.state["projects"].get(recipient["project_id"])
            if target is None or not set(recipient["actor_ids"]) <= set(target["participants"]):
                raise ValueError("Publication recipient is not an installed project participant")
    # Policy configuration is checked without observations or action opportunities.
    for role in spec["roles"]:
        _make_policy(role)


def save_deployment(deployment, root=None):
    if deployment.world is None:
        raise ValueError("No created world to persist")
    if root is not None and Path(root).resolve() != deployment.world.store.root.resolve():
        raise ValueError("Deployment manifest belongs to its created world")
    record = {
        "version": SCENARIO_VERSION,
        "world_id": deployment.world.state["world_id"],
        "instance_id": deployment.world.state["instance_id"],
        "scenario_sha256": digest(json_bytes(deployment.spec)),
        "spec": deployment.spec,
        "status": deployment.status,
        "diagnostics": deployment.diagnostics,
        "deployment_log": deployment.deployment_log,
        "prefix": deployment.prefix,
    }
    atomic_write(deployment.world.store.control / "scenario.json", json_bytes(record))
    return deployment.world.store.control / "scenario.json"


def load_deployment(root):
    record = json.loads((Path(root) / "control" / "scenario.json").read_text())
    spec = validate_scenario(record["spec"])
    if record.get("version") != SCENARIO_VERSION or record.get("scenario_sha256") != digest(
        json_bytes(spec)
    ):
        raise ValueError("Scenario manifest identity mismatch")
    world = WorldCore(root)
    if (
        world.state["world_id"] != record["world_id"]
        or world.state["world_id"] != spec["world"]["world_id"]
        or world.state["instance_id"] != record["instance_id"]
    ):
        raise ValueError("Scenario manifest does not identify this world")
    return ScenarioDeployment(
        spec,
        world,
        record["status"],
        record["diagnostics"],
        record["deployment_log"],
        record["prefix"],
    )


def build_scenario(spec, root):
    """Deploy explicitly, returning unbuildable rather than silently weakening it."""
    deployment = ScenarioDeployment(copy.deepcopy(spec))
    try:
        deployment.spec = validate_scenario(spec)
        world = WorldCore.create(root, WorldSpec(**deployment.spec["world"]))
        deployment.world = world
        for index, declaration in enumerate(deployment.spec["projects"]):
            package = resolve_references(world, project_package(declaration))
            record = _public_call(
                world,
                {
                    "actor": deployment.spec["installer"],
                    "tool": "install_project",
                    "arguments": {"package": package},
                },
                "scenario-install-" + str(index),
            )
            deployment.deployment_log.append(record)
            if not record["result"].get("ok"):
                raise ValueError(
                    "Project installation rejected: "
                    + json.dumps(record["result"], ensure_ascii=False)
                )
        for role in deployment.spec["roles"]:
            world.session(role["actor"], role["project"])
        for index, action in enumerate(deployment.spec["setup"]):
            record = _public_call(world, action, "scenario-setup-" + str(index))
            deployment.deployment_log.append(record)
            if not record["result"].get("ok"):
                raise ValueError(
                    "Declared setup rejected: " + json.dumps(record["result"], ensure_ascii=False)
                )
        _validate_bound_spec(deployment)
    except (ValueError, KeyError, TypeError) as error:
        deployment.status = "unbuildable"
        deployment.diagnostics.append(type(error).__name__ + ": " + str(error))
    if deployment.world is not None:
        save_deployment(deployment)
    return deployment


class ScenarioController:
    """Fire only predeclared actions; never call a worker/evaluator for answers."""

    def __init__(self, deployment, checkpoint=None, recorder=None):
        if deployment.status != "ready":
            raise ValueError("Cannot run an unbuildable scenario")
        self.deployment = deployment
        self.world = deployment.world
        self.identity = {
            "world_id": self.world.state["world_id"],
            "instance_id": self.world.state["instance_id"],
            "scenario_sha256": digest(json_bytes(deployment.spec)),
        }
        if checkpoint is not None and checkpoint.get("identity") != self.identity:
            raise ValueError(
                "Controller checkpoint requires the same world and scenario specification"
            )
        self.fired = copy.deepcopy((checkpoint or {}).get("fired", {}))
        self.log = copy.deepcopy((checkpoint or {}).get("log", []))
        self.recorder = recorder
        self.environment_cursor = (checkpoint or {}).get(
            "environment_cursor", len(self.world.state.get("event_history", []))
        )

    def matches(self, predicate):
        state = self.world.state
        kind, value = next(iter(predicate.items()))
        if kind == "all":
            return all(self.matches(item) for item in value)
        if kind == "clock_at_least":
            return state["clock"] >= value
        if kind == "event_fired":
            return self.fired.get(value) == "executed"
        node = value["node"] if "::" in value["node"] else value["project"] + "::" + value["node"]
        project = state["projects"].get(value["project"], {})
        wid = current_id(state, project.get("maintenance_heads", {}).get(node, node))
        if wid not in state["work_items"]:
            return False
        if value["phase"] == "blocked":
            return derive_current_work_view(state)[wid]["status"] == "blocked"
        source = state["workspaces"].get(value["project"], {}).get(value.get("source_alias"))
        return work_stage(state, wid, source) == value["phase"]

    def record_environment(self):
        history = self.world.state.get("event_history", [])
        if self.recorder is not None:
            for record in history[self.environment_cursor :]:
                self.recorder.record("environment_event", record)
        self.environment_cursor = len(history)

    def tick(self):
        self.record_environment()
        new = []
        for event in self.deployment.spec["events"]:
            eid = event["event_id"]
            if eid in self.fired or not self.matches(event["when"]):
                continue
            record = {
                "kind": "controller",
                "event_id": eid,
                "when": copy.deepcopy(event["when"]),
                "matched_at": self.world.state["clock"],
                "effects": [],
                "status": "executed",
            }
            for index, action in enumerate(event["effects"]):
                effect = _public_call(
                    self.world, action, "scenario-event-" + eid + "-" + str(index)
                )
                record["effects"].append(effect)
                if self.recorder is not None:
                    self.recorder.record(
                        "controller_action", {"event_id": eid, "trigger": event["when"], **effect}
                    )
                self.record_environment()
                if not effect["result"].get("ok"):
                    record["status"] = "rejected"
                    break
            self.fired[eid] = record["status"]
            self.log.append(record)
            new.append(copy.deepcopy(record))
        return new

    def snapshot(self):
        return {
            "identity": copy.deepcopy(self.identity),
            "fired": copy.deepcopy(self.fired),
            "log": copy.deepcopy(self.log),
            "environment_cursor": self.environment_cursor,
        }


def load_scenario(path):
    return validate_scenario(json.loads(Path(path).read_text()))


def _make_policy(role):
    from .workers.team_policies import ReconciliationPolicy, ReportAuthorPolicy, ReviewerPolicy

    factories = {
        "reconciliation": ReconciliationPolicy,
        "report_author": ReportAuthorPolicy,
        "reviewer": ReviewerPolicy,
    }
    if role["policy"] not in factories:
        raise ValueError("Unsupported declared policy: " + role["policy"])
    return factories[role["policy"]](**role["config"])


def _business_complete(world):
    views = derive_current_work_view(world.state)
    current = [wid for wid, view in views.items() if view["status"] != "superseded"]
    if (
        not current
        or world.state.get("events")
        or any(views[wid]["status"] != "accepted" for wid in current)
    ):
        return False
    return _publication_complete(world, current)


def _publication_complete(world, work_ids):
    for wid in work_ids:
        item = world.state["work_items"][wid]
        delivery = item.get("requirements", {}).get("public_delivery", {})
        if not delivery.get("publish"):
            continue
        targets = {item["project_id"]} | {
            recipient["project_id"] for recipient in delivery.get("recipients", [])
        }
        # Accepted predecessor publications are historical facts; newer formal
        # releases may supersede them without undoing the fulfilled old duty.
        for oid, vid in item["submissions"][-1]["artifact_versions"].items():
            if not all(
                any(
                    r["object_id"] == oid
                    and r["version_id"] == vid
                    and target in r["scope"]["target_projects"]
                    for r in world.state["releases"]
                )
                for target in targets
            ):
                return False
    return True


def _accepted_predicate(predicate):
    kind, value = next(iter(predicate.items()))
    if kind == "all":
        return all(_accepted_predicate(child) for child in value)
    return kind == "event_fired" or (kind == "work" and value["phase"] == "accepted")


def _predicate_work_ids(world, predicate):
    kind, value = next(iter(predicate.items()))
    if kind == "all":
        return [wid for child in value for wid in _predicate_work_ids(world, child)]
    if kind != "work":
        return []
    node = value["node"] if "::" in value["node"] else value["project"] + "::" + value["node"]
    head = world.state["projects"][value["project"]].get("maintenance_heads", {}).get(node, node)
    return [current_id(world.state, head)]


def bind_runtime(deployment, checkpoint=None, recorder=None, captured=None):
    """Trusted binding only; policies receive opaque sessions, never this host."""
    from .experience import capture_port
    from .staff_runtime import StaffRuntime

    ports, policies = {}, {}
    for role in deployment.role_bindings():
        label = role["role_id"]
        session = deployment.world.session(role["actor"], role["project"])
        ports[label] = (
            capture_port(session, captured.setdefault(label, []))
            if captured is not None
            else session
        )
        policies[label] = _make_policy(role)
    runtime = StaffRuntime(ports, policies, checkpoint=checkpoint, recorder=recorder)
    if checkpoint is None:
        for record in deployment.deployment_log:
            runtime.recorder.record("controller_action", {"stage": "deployment", **record})
        for event in deployment.world.state.get("event_history", []):
            runtime.recorder.record("environment_event", event)
    return runtime


def run_scenario(deployment, runtime=None, controller=None, max_opportunities=None):
    """Transparent round robin opportunities and predeclared external events.

    No evaluator is used for stopping or rescue. A full idle sweep separates
    genuine acceptance from untriggered events, persistent world blocking and
    unsupported/waiting strategies. Boundaries preserve the world and memories.
    """
    if deployment.status != "ready":
        return {"status": "unbuildable", "diagnostics": copy.deepcopy(deployment.diagnostics)}
    bound = deployment.spec["boundary"]
    invocation_limit = (
        bound["max_opportunities"] if max_opportunities is None else max_opportunities
    )
    if type(invocation_limit) is not int or not 0 <= invocation_limit <= bound["max_opportunities"]:
        raise ValueError(
            "Invocation budget must be nonnegative and no greater than declared boundary"
        )
    runtime = runtime or bind_runtime(deployment)
    controller = controller or ScenarioController(deployment, recorder=runtime.recorder)
    controller.recorder = runtime.recorder
    if (
        deployment.spec["start"]["kind"] == "executed_prefix"
        and not deployment.prefix["prefix_executed"]
    ):
        deployment.prepare_start(runtime, controller)
        if deployment.status != "ready":
            return {
                "status": "unbuildable",
                "diagnostics": copy.deepcopy(deployment.diagnostics),
                "prefix": copy.deepcopy(deployment.prefix),
            }
    outcomes, idle = [], set()
    status = "budget_exhausted"
    start_actions, start_opportunities = runtime.actions, runtime.opportunities

    def explicit_boundary():
        predicate = bound.get("complete_when")
        if predicate is None or not controller.matches(predicate):
            return None
        remaining = [
            event
            for event in deployment.spec["events"]
            if event["event_id"] not in controller.fired
        ]
        if _business_complete(deployment.world) and not remaining:
            return "completed"
        if not _accepted_predicate(predicate):
            return "boundary_reached"
        if not deployment.world.state.get("events") and _publication_complete(
            deployment.world, _predicate_work_ids(deployment.world, predicate)
        ):
            return "boundary_reached"
        return None

    for _ in range(invocation_limit):
        reached = explicit_boundary()
        if reached:
            status = reached
            break
        effects = controller.tick()
        if effects:
            idle.clear()
        if any(event["status"] != "executed" for event in effects):
            status = "controller_rejected"
            break
        result = runtime.step()
        controller.record_environment()
        outcomes.append(result)
        reached = explicit_boundary()
        if reached:
            status = reached
            break
        if result["action_performed"]:
            idle.clear()
        else:
            idle.add(result["worker_id"])
        if len(idle) < len(runtime.labels):
            continue
        views = derive_current_work_view(deployment.world.state)
        current = [view for view in views.values() if view.get("status") != "superseded"]
        condition = (
            controller.matches(bound["complete_when"])
            if "complete_when" in bound
            else bool(current) and all(view["status"] == "accepted" for view in current)
        )
        remaining = [
            event["event_id"]
            for event in deployment.spec["events"]
            if event["event_id"] not in controller.fired
        ]
        states = {runtime.roles[key]["status"] for key in runtime.labels}
        if condition and not remaining and _business_complete(deployment.world):
            status = "completed"
        elif "environment_error" in states:
            status = "environment_error"
        elif "policy_error" in states or "binding_mismatch" in states:
            status = "policy_error"
        elif any(view.get("status") == "blocked" for view in current):
            status = "world_blocked"
        elif remaining:
            status = "worker_waiting"
        else:
            status = "worker_waiting"
        break
    remaining = [
        event["event_id"]
        for event in deployment.spec["events"]
        if event["event_id"] not in controller.fired
    ]
    boundary = {
        "status": status,
        "actions": runtime.actions - start_actions,
        "opportunities": runtime.opportunities - start_opportunities,
        "untriggered_events": remaining,
        "pending_environment_events": len(deployment.world.state.get("events", [])),
        "declared_opportunity_limit": bound["max_opportunities"],
        "invocation_opportunity_limit": invocation_limit,
        "total_runtime_opportunities": runtime.opportunities,
    }
    runtime.recorder.record("scenario_boundary", boundary)
    save_deployment(deployment)
    return {
        **boundary,
        "outcomes": outcomes,
        "controller": controller.snapshot(),
        "prefix": copy.deepcopy(deployment.prefix),
        "worker_checkpoint": runtime.snapshot(),
        "experience": runtime.recorder.snapshot(),
    }
