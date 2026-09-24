"""A persistent world with project-scoped sessions and dynamically created objects.

Uses the same single-writer runner, version store, conditions and work transitions
as the finite template adapters. No financial object or singleton project exists
in this runtime's state contract.
"""

import copy
import inspect
import re
import uuid
from pathlib import Path

from .core import journal
from .core.maintenance import impact_candidates, apply_impact, successor_identity
from .tool_outcomes import ToolRejection
from .core.issues import (raise_issue, respond_issue, decide_issue, derive_issue_view, submission_for)
from .adapters.locations import read_location
from .core.adoption import (
    binding_key,
    binding_for,
    make_binding,
    snapshot_bindings,
    validate_policy_contract,
    require_version,
    declared_version,
    allowed_policies,
)
from .core.work import current_id
from .core.publication import (
    effective_policy,
    latest_published_version,
    publish_release,
    record_implicit_release,
)
from .adapters.capabilities import (
    capability_for,
    encode,
    read,
    update_xlsx,
    recalculate_xlsx,
    capability_tools,
)
from .evaluation import evaluate_submission as evaluate_work_product
from .core.conditions import apply_response, supersede_condition
from .core.projections import rebuild_projections, derive_current_work_view, record_artifact_edit
from .core.references import VersionRef, ApplicabilityContext
from .core.rules import confirm_credential, registered_applicability
from .core.runner import WorldRunner
from .core.transitions import ActionFrame
from .core.types import Credential
from .core.work import submit_work, approve_submission, withdraw_submission, revise_requirement
from .core.world import (
    WorldSpec,
    new_world_state,
    install_package,
    object_identity,
    validate_deliverable_contract,
)
from .policies.organization import authority
from .storage import Store, atomic_write, json_bytes, digest


class WorldCore(WorldRunner):
    runtime_schema = "world-core-v0.9"

    @classmethod
    def create(cls, root, spec: WorldSpec):
        root = Path(root).resolve()
        if root.exists():
            raise ValueError("World destination must be new")
        state = new_world_state(spec)
        for folder in ("control/versions", "workspace", "control/role_files"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        state.setdefault("shares", [])
        state.setdefault("adoptions", {})
        state.setdefault("episodes", {})
        state.setdefault("project_history", [])
        Store(root).save(state)
        atomic_write(root / "control" / "world_spec.json", json_bytes(spec.to_dict()))
        return cls(root)

    def _role(self, actor):
        for role in self.state["roles"]:
            if role["role_id"] == actor:
                return role
        raise ValueError("Unknown world actor")

    def _after_command(self, record):
        pass

    def _derive(self, state):
        rebuild_projections(state)
        state["adoption_view"] = {}
        for key, adoption in state.get("adoptions", {}).items():
            artifact = state["artifacts"][adoption["object_id"]]
            target = adoption["version_id"]
            if adoption["policy"] == "current_applicable":
                target = artifact["current_version"]
            elif adoption["policy"] == "current_published":
                target = latest_published_version(
                    state, adoption["object_id"], adoption["project_id"]
                )
            state["adoption_view"][key] = {
                "adopted_version": adoption["version_id"],
                "target_version": target,
                "status": "unassessed"
                if target is None
                else "current"
                if target == adoption["version_id"]
                else "update_required",
                "policy": adoption["policy"],
            }

    def _complete_frame(self, frame):
        frame = super()._complete_frame(frame)
        return ActionFrame(
            frame.name,
            frame.paths,
            frame.derived_paths + (("adoption_view",),),
            frame.immutable_submission_extensions + ("adoption_snapshot",),
            frame.append_only_extensions + ("releases", "information_updates"),
        )

    def _operation_identity(self, actor, action, arguments, request_key):
        project = arguments.get("project_id") if isinstance(arguments, dict) else None
        namespace = project if action == "project_action" else "@world"
        # JSON tuple encoding avoids actor/project/key delimiter collisions.
        identity = journal.canonical_digest([actor, namespace, request_key or uuid.uuid4().hex])
        return "command:" + identity, journal.canonical_digest(
            {"actor": actor, "context": namespace, "action": action, "arguments": arguments}
        )

    def session(self, actor, project_id=None):
        self._role(actor)
        if project_id is not None:
            self._project(actor, project_id)
        return ProjectSession(self, actor, project_id)

    def _project(self, actor, project_id, active=False):
        project = self.state["projects"].get(project_id)
        if project is None or actor not in project["participants"]:
            raise ValueError("Project is unavailable to this actor")
        if active and project["status"] != "active":
            raise ValueError("Project no longer accepts new work")
        return project

    def _world_power(self, actor, power):
        if not any(
            grant.get("actor_id") == actor
            and grant.get("scope") == "world"
            and grant.get("power") in (power, "*")
            for grant in self.state["organization"]["grants"]
        ):
            raise ToolRejection("Actor lacks world power: " + power, code="world_power_denied", category="policy_error", context={"power": power})

    def _project_power(self, actor, project_id, power, subject="*", work=None, object_id=None):
        self._project(actor, project_id)
        if not authority(
            self.state, actor, power, subject, work, project_id=project_id, object_id=object_id
        ):
            raise ToolRejection("Actor lacks project power: " + power, code="project_power_denied", category="policy_error", context={"power": power})

    def _work(self, actor, project_id, work_id, current=True):
        self._project(actor, project_id, active=current)
        key = work_id if "::" in work_id else project_id + "::" + work_id
        item = self.state["work_items"].get(key)
        if item is None or item["project_id"] != project_id:
            raise ValueError("Work reference escapes bound project")
        if current and key in self.state.get("work_replacements", {}):
            raise ToolRejection("Work reference is superseded", code="superseded_work", category="business_constraint", context={"work_id": key})
        return item

    def _resolve(self, project_id, alias):
        workspace = (
            self.state.get("world_workspace", {})
            if project_id is None
            else self.state.get("workspaces", {}).get(project_id, {})
        )
        object_id = workspace.get(alias)
        if object_id is None:
            raise ValueError("Unknown alias in the bound workspace")
        return object_id

    def _can_read(self, actor, project_id, artifact, version_id):
        if version_id not in artifact["versions"]:
            return False
        base_access = artifact.get("project_id") == project_id and actor in artifact["readers"]
        return base_access or any(
            share["project_id"] == project_id
            and share["object_id"] == artifact["artifact_id"]
            and share["version_id"] == version_id
            and actor in share["actor_ids"]
            for share in self.state.get("shares", [])
        )

    def _object(self, actor, project_id, alias=None, object_id=None, version_id=None, write=False):
        if project_id is not None:
            self._project(actor, project_id, active=write)
        if (alias is None) == (object_id is None):
            raise ValueError("Select exactly one workspace alias or object identity")
        aid = self._resolve(project_id, alias) if alias is not None else object_id
        artifact = self.state["artifacts"].get(aid)
        if artifact is None:
            raise ValueError("Unknown object")
        version_id = version_id or artifact["current_version"]
        if write:
            if artifact.get("project_id") != project_id or actor not in artifact["writers"]:
                raise ValueError("Cannot write outside the bound project or object grant")
        elif not self._can_read(actor, project_id, artifact, version_id):
            raise ValueError("Exact object version is not shared with this actor and project")
        return artifact, version_id

    def _message(self, sender, recipients, project_id, subject, body, attachments=None):
        message = {
            "message_id": f"mail-{len(self.state['messages']) + 1}",
            "sender": sender,
            "recipients": list(recipients),
            "at": self.state["clock"],
            "project_id": project_id,
            "subject": subject,
            "body": copy.deepcopy(body),
            "attachments": copy.deepcopy(attachments or []),
        }
        self.state["messages"].append(message)
        return message

    def _event(self, kind, payload, delay):
        event = {
            "event_id": journal.canonical_digest(
                {
                    "operation": self._operation_context["operation_id"],
                    "kind": kind,
                    "payload": payload,
                    "ordinal": len(self.state["events"]) + len(self.state["event_history"]),
                }
            )[:32],
            "kind": kind,
            "at": self.state["clock"] + delay,
            "payload": copy.deepcopy(payload),
        }
        self.state["events"].append(event)
        return event

    def _action_frame(self, actor, action, arguments):
        if action not in {"project_action", "world_action"}:
            raise ValueError("Use a bound world or project session")
        tool = arguments.get("tool")
        project_id = arguments.get("project_id") if action == "project_action" else None
        if action == "project_action":
            self._project(actor, project_id)
        # Handlers resolve trusted scope before any state writes. Shared append-only
        # facts are protected by execute_transition; project/object roots are scoped.
        paths = [
            ("knowledge", actor),
            ("messages",),
            ("events",),
            ("shares",),
            ("access_grants",),
            ("requirement_events",),
            ("project_history",),
            ("releases",),
            ("information_updates",),
        ]
        if project_id is None:
            if tool == "install_project":
                pid = arguments.get("arguments", {}).get("package", {}).get("project_id", "")
                paths += [
                    ("projects", pid),
                    ("workspaces", pid),
                    ("organization", "grants"),
                    ("artifacts",),
                    ("work_items",),
                    ("adoptions",),
                ]
            else:
                paths += [("artifacts",), ("world_workspace",), ("episodes",), ("world_status",)]
        else:
            paths += [
                ("projects", project_id),
                ("workspaces", project_id),
                ("episodes",),
                ("adoptions",),
                ("requests",),
                ("raw_condition_responses",),
                ("shares",),
                ("attestations",),
                ("work_replacements",),
            ]
            for aid, artifact in self.state["artifacts"].items():
                if artifact.get("project_id") == project_id:
                    paths.append(("artifacts", aid))
            if tool == "create_object":
                alias = arguments.get("arguments", {}).get("alias", "")
                paths.append(("artifacts", self._object_id(project_id, alias)))
            for wid, item in self.state["work_items"].items():
                if item["project_id"] == project_id:
                    paths.append(("work_items", wid))
                    if tool == "revise":
                        paths.append(
                            (
                                "work_items",
                                item["node_id"] + "@r" + str(item["requirement_version"] + 1),
                            )
                        )
            for cid, condition in self.state.get("condition_specs", {}).items():
                if self.state["work_items"][condition["work_item_id"]]["project_id"] == project_id:
                    paths.append(("condition_specs", cid))
            if tool in {"raise_issue", "respond_issue", "decide_issue"}:
                paths += [("issues",), ("issue_responses",), ("issue_decisions",)]
            if tool in {"request", "request_information"}:
                paths.append(("condition_specs",))
        if tool == "wait":
            paths.append(("clock",))
        return ActionFrame(str(tool), tuple(paths))

    def _tool_project_action(self, actor, project_id, tool, arguments):
        self._project(
            actor,
            project_id,
            active=tool not in {"read_object", "sheet_read", "read_messages", "end_episode", "inspect_submission"},
        )
        return self._dispatch(actor, project_id, tool, arguments)

    def _tool_world_action(self, actor, tool, arguments):
        if tool not in {entry["name"] for entry in self._tool_definitions(None)}:
            raise ValueError("Tool is not a world operation")
        return self._dispatch(actor, None, tool, arguments)

    def _tool_definitions(self, project_id):
        common = [
            "create_object",
            "write_object",
            "read_object",
            "share",
            "publish",
            "start_episode",
            "end_episode",
            "wait",
        ]
        names = common + (
            ["pause", "resume", "install_project"]
            if project_id is None
            else [
                "adopt",
                "adopt_version",
                "submit",
                "approve",
                "inspect_submission",
                "raise_issue",
                "respond_issue",
                "decide_issue",
                "withdraw",
                "confirm",
                "revise",
                "request",
                "request_information",
                "set_information_availability",
                "read_messages",
                "close_project",
            ]
        )
        if project_id is not None and "sql" in self.state["applications"]:
            names += ["sql_build", "sql_query"]
        if "files" not in self.state["applications"]:
            names = [name for name in names if name not in {"read_object", "write_object"}]
        definitions = []
        objects = {"data", "package", "updates", "reference"}
        arrays = {
            "dependencies",
            "actor_ids",
            "work_ids",
            "artifacts",
            "project_ids",
            "target_projects",
            "locator",
            "evidence",
            "input_aliases",
        }
        for name in names:
            properties, required = {}, []
            for key, param in inspect.signature(
                getattr(self, "_action_" + name)
            ).parameters.items():
                if key in {"actor", "project_id"}:
                    continue
                typ = (
                    "object"
                    if key in objects
                    else "array"
                    if key in arrays
                    else "integer"
                    if key in {"ticks", "delay"}
                    else "boolean"
                    if key in {"follow_updates", "available", "blocking"}
                    else "string"
                )
                properties[key] = {"type": typ}
                if param.default is inspect.Parameter.empty:
                    required.append(key)
                elif param.default is not None:
                    properties[key]["default"] = param.default
            if name in {"sql_build", "sql_query"}:
                properties["output_alias"]["description"] = "Existing owned JSON artifact receiving a new immutable execution result; errors and tests are retained."
                if name == "sql_build":
                    properties["input_aliases"]["description"] = "Exact work-adopted JSON sources exposing typed tables. Code object: models[{name,sql}], tests[{name,sql}], config{exports,description}; SELECT/CTE only, tests return failing rows."
                else:
                    properties["sql"]["description"] = "One SELECT/CTE against the source artifact tables; external files/network/extensions and mutable SQL are disabled."
            if name == "create_object":
                properties["data"]["description"] = (
                    "For json: a JSON object. For xlsx: {cells: {Sheet!A1: scalar_or_formula}} or a direct Sheet!A1 mapping; formulas start with =."
                )
                properties["filename"]["description"] = (
                    "A simple .json or .xlsx filename matching kind; no host path."
                )
                properties["kind"]["enum"] = [
                    kind
                    for kind in ("json", "xlsx")
                    if capability_for(kind).application in self.state["applications"]
                ]
            if name == "create_object" and "files" not in self.state["applications"]:
                properties["kind"].pop("default", None)
                required.append("kind")
            for key in arrays & properties.keys():
                properties[key]["items"] = {"type": "object" if key in {"dependencies", "evidence"} else "string"}
            if "locator" in properties:
                properties["locator"]["items"] = {"type": ["string", "integer"]}
            if "answer" in properties:
                properties["answer"] = {
                    "description": "Optional answer value, if required by the public work contract"
                }
            descriptions = {
                "read_object": "Read an exact visible JSON version. Reading records knowledge only: it does not adopt that version for a work or establish a deliverable source binding.",
                "write_object": "Write a new managed JSON version. When a source contributes to a deliverable, supply its exact object/version in dependencies. Adoption and JSON sources fields do not automatically record file dependencies; omitting dependencies retains the previous version dependency list. Existing submitted versions and reviews stay immutable. Editing a pending submission's objects does not update that submission; withdraw it before resubmitting the repaired versions.",
                "adopt": "Bind an exact source object/version to each listed current work edition under its declared input policy. Source-based content contracts require these per-work bindings before submission; reading a source or writing a sources field does not replace adoption.",
                "adopt_version": "Explicitly update an existing non-fixed adoption for one exact work edition. Use adopt for a new work binding. A fixed binding cannot be advanced.",
                "submit": "Submit the current versions of workspace artifact aliases, not object IDs. Artifacts is a list of alias strings in this bound project. Source-based contracts require exact adoptions for this work and matching source references/dependencies; reading alone is insufficient. A pending submission must be withdrawn before a replacement submission.",
                "withdraw": "Withdraw the named pending submission before repairing/resubmitting the same work. Withdrawal preserves fixed versions and does not automatically resolve located review issues.",
                "inspect_submission": "Inspect one exact submission identified by pending_submission_id or latest_submission_id in the public work observation, subject to actual artifact access checks.",
            }
            if "dependencies" in properties:
                properties["dependencies"]["description"] = "Exact object_id/version_id references of sources contributing to this file version. Adoption and JSON source fields do not populate dependencies. A write with omitted dependencies retains previous dependencies; creation defaults to none."
            if name == "sql_query":
                properties["source_alias"]["description"] = "Use this exact work adoption when one exists; otherwise only a readable local project object is queryable. Shared sources never resolve to an unadopted latest or last-shared version."
            if name == "submit":
                properties["artifacts"]["description"] = "Workspace aliases such as report or result, never object IDs; submitted sources must match this exact work's adoption bindings."
            definitions.append(
                {
                    "name": name,
                    "description": descriptions.get(name, f"{name} within the trusted bound world/project; identity and permissions checked on execution."),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                }
            )
        return definitions + capability_tools(self.state["applications"])

    def tools(self, actor, project_id=None):
        with self.store.lock():
            self.state = self.store.load()
            self._role(actor)
            if project_id is not None:
                self._project(actor, project_id)
            return self._tool_definitions(project_id)

    def _dispatch(self, actor, project_id, tool, arguments):
        if tool not in {entry["name"] for entry in self._tool_definitions(project_id)}:
            raise ToolRejection("Tool capability is not enabled for this session", code="tool_not_enabled", category="capability_gap", context={"tool": tool})
        if self.state.get("world_status") == "paused" and tool not in {
            "resume",
            "read_object",
            "sheet_read",
            "read_messages",
            "end_episode",
            "inspect_submission",
        }:
            raise ToolRejection("World is paused; resume before new work", code="world_paused", category="business_constraint")
        if not isinstance(arguments, dict) or set(arguments) & {"actor", "actor_id", "project_id"}:
            raise ToolRejection("Tool arguments cannot override trusted session context", code="trusted_context_override", category="policy_error")
        handler = getattr(self, "_action_" + tool, None) if isinstance(tool, str) else None
        if handler is None:
            raise ValueError("Unknown world-core tool")
        try:
            inspect.signature(handler).bind(actor, project_id, **arguments)
        except TypeError as exc:
            raise ToolRejection(str(exc), code="invalid_arguments", category="policy_error") from exc
        try:
            return handler(actor, project_id, **arguments)
        except (KeyError, AttributeError, ArithmeticError) as exc:
            raise ToolRejection(str(exc), code="implementation_exception", category="environment_error",
                                context={"exception_type": type(exc).__name__, "tool": tool}) from exc

    def _action_pause(self, actor, project_id):
        if project_id is not None:
            raise ValueError("World lifecycle requires world context")
        self._world_power(actor, "pause_world")
        self.state["world_status"] = "paused"
        return {"world_status": "paused"}

    def _action_resume(self, actor, project_id):
        if project_id is not None:
            raise ValueError("World lifecycle requires world context")
        self._world_power(actor, "pause_world")
        self.state["world_status"] = "running"
        return {"world_status": "running"}

    def _drain_events(self):
        return [] if self.state.get("world_status") == "paused" else super()._drain_events()

    def _action_install_project(self, actor, project_id, package):
        if project_id is not None:
            raise ValueError("Project installation requires world context")
        payloads = install_package(self.state, package, actor)
        for payload in payloads:
            self.store.put(
                self.state,
                payload["object_id"],
                encode(payload["kind"], payload["data"]),
                payload["owner"],
            )
        pid = package["project_id"]
        return {"project_id": pid, "objects": [p["object_id"] for p in payloads]}

    @staticmethod
    def _object_id(project_id, alias):
        return object_identity(project_id, alias)

    def _action_create_object(
        self,
        actor,
        project_id,
        alias,
        filename,
        data,
        deliverable_role="draft",
        dependencies=None,
        kind="json",
        work_id=None,
    ):
        if project_id is None:
            self._world_power(actor, "create_object")
            workspace = self.state.setdefault("world_workspace", {})
        else:
            context = self._work(actor, project_id, work_id) if work_id is not None else None
            self._project_power(
                actor,
                project_id,
                "create_object",
                "artifact",
                work=context["node_id"] if context else None,
            )
            workspace = self.state["workspaces"][project_id]
        aid = self._object_id(project_id, alias)
        if alias in workspace or aid in self.state["artifacts"]:
            raise ValueError("Object alias or identity already exists")
        capability = self._capability(kind)
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}" + re.escape(capability.suffix), filename
        ):
            raise ValueError("Filename must match enabled file capability")
        if not isinstance(data, dict) or not isinstance(deliverable_role, str):
            raise ValueError("JSON object data and an explicit artifact role are required")
        encoded = encode(kind, data)
        deps = self._checked_dependencies(actor, project_id, dependencies or [])
        artifact = {
            "artifact_id": aid,
            "project_id": project_id,
            "filename": filename,
            "storage_path": f"artifacts/{aid}/{filename}",
            "kind": kind,
            "materialization": "workspace",
            "owner": actor,
            "readers": [actor],
            "writers": [actor],
            "deliverable_role": deliverable_role,
            "versions": {},
            "current_version": None,
            "provenance": {"kind": "synthetic", "source_evidence_refs": []},
        }
        # Project readers are explicit participants of a visible work product;
        # upstream objects retain their own exact-version ACLs.
        if project_id is not None:
            artifact["readers"] = list(self.state["projects"][project_id]["participants"])
        self.state["artifacts"][aid] = artifact
        workspace[alias] = aid
        version = self.store.put(self.state, aid, encoded, actor, deps)
        self._writes.append({"artifact_id": aid, "before": None, "after": version["version_id"]})
        self._record_work_edit(actor, project_id, work_id, aid, version["version_id"])
        return {"object_id": aid, "version_id": version["version_id"], "alias": alias}

    def _checked_dependencies(self, actor, project_id, references):
        if not isinstance(references, list):
            raise ValueError("Dependencies must be exact version references")
        result = []
        for value in references:
            ref = VersionRef.from_mapping(value)
            self._object(actor, project_id, object_id=ref.object_id, version_id=ref.version_id)
            if ref.artifact_ref() in result:
                raise ValueError("Duplicate dependency")
            result.append(ref.artifact_ref())
        return result

    def _capability(self, kind):
        capability = capability_for(kind)
        if capability.application not in self.state["applications"]:
            raise ValueError("File capability is not enabled in this world")
        return capability

    def _record_work_edit(self, actor, project_id, work_id, object_id, version_id):
        if work_id is None:
            return
        item = self._work(actor, project_id, work_id)
        if item["owner_role"] != actor:
            raise ValueError("Only the work owner can declare its edit context")
        item.setdefault("artifact_edits", []).append(
            {
                "actor_id": actor,
                "artifact_id": object_id,
                "version_id": version_id,
                "at": self.state["clock"],
                "work_item_id": item["work_item_id"],
                "requirement_version": item["requirement_version"],
            }
        )

    def _save_content(self, actor, project_id, artifact, content, dependencies=None, work_id=None):
        if project_id is None and effective_policy(self.state, artifact) == "implicit_write":
            self._world_power(actor, "publish")
        old = artifact["current_version"]
        refs = (
            artifact["versions"][old]["derived_from"]
            if dependencies is None
            else self._checked_dependencies(actor, project_id, dependencies)
        )
        if any(ref["artifact_id"] == artifact["artifact_id"] for ref in refs):
            raise ValueError("Self dependency")
        version = self.store.put(self.state, artifact["artifact_id"], content, actor, refs)
        record_artifact_edit(self.state, actor, artifact["artifact_id"], version["version_id"])
        self._record_work_edit(
            actor, project_id, work_id, artifact["artifact_id"], version["version_id"]
        )
        self._writes.append(
            {"artifact_id": artifact["artifact_id"], "before": old, "after": version["version_id"]}
        )
        if effective_policy(self.state, artifact) == "implicit_write":
            targets = self._publication_targets(artifact)
            release = record_implicit_release(
                self.state,
                actor,
                artifact.get("project_id"),
                artifact["artifact_id"],
                version["version_id"],
                targets,
            )
            if release["created"]:
                self._publish_shared(
                    actor,
                    artifact,
                    version["version_id"],
                    targets,
                    release["release"]["release_id"],
                )
        return {"object_id": artifact["artifact_id"], "version_id": version["version_id"]}

    def _action_write_object(
        self, actor, project_id, data, alias=None, object_id=None, dependencies=None, work_id=None
    ):
        artifact, _ = self._object(actor, project_id, alias, object_id, write=True)
        self._capability(artifact["kind"])
        if artifact["kind"] != "json":
            raise ValueError("Use sheet_update for workbook content")
        return self._save_content(
            actor, project_id, artifact, encode("json", data), dependencies, work_id
        )

    def _record_read(self, actor, project_id, artifact, vid, work_id=None):
        ref = {"artifact_id": artifact["artifact_id"], "version_id": vid}
        self._reads.append(ref)
        context = {}
        if work_id is not None:
            item = self._work(actor, project_id, work_id, current=False)
            context = {
                "work_item_id": item["work_item_id"],
                "requirement_version": item["requirement_version"],
            }
        self.state["knowledge"][actor]["read_artifacts"].append(
            {**ref, "project_id": project_id, "at": self.state["clock"], **context}
        )
        return ref

    def _action_read_object(
        self, actor, project_id, alias=None, object_id=None, version_id=None, work_id=None
    ):
        artifact, vid = self._object(actor, project_id, alias, object_id, version_id)
        self._capability(artifact["kind"])
        if artifact["kind"] != "json":
            raise ValueError("Use sheet_read for workbook content")
        data = read("json", self.store.version_path(artifact, vid).read_bytes())
        return {
            "reference": self._record_read(actor, project_id, artifact, vid, work_id),
            "data": data,
        }

    def _action_sheet_read(
        self,
        actor,
        project_id,
        alias=None,
        object_id=None,
        version_id=None,
        sheet=None,
        work_id=None,
    ):
        artifact, vid = self._object(actor, project_id, alias, object_id, version_id)
        self._capability("xlsx")
        if artifact["kind"] != "xlsx":
            raise ValueError("Object is not a workbook")
        data = read("xlsx", self.store.version_path(artifact, vid).read_bytes(), sheet=sheet)
        return {
            "reference": self._record_read(actor, project_id, artifact, vid, work_id),
            "sheets": data,
        }

    def _action_sheet_update(
        self, actor, project_id, cells, alias=None, object_id=None, dependencies=None, work_id=None
    ):
        artifact, vid = self._object(actor, project_id, alias, object_id, write=True)
        self._capability("xlsx")
        if artifact["kind"] != "xlsx":
            raise ValueError("Object is not a workbook")
        content = update_xlsx(self.store.version_path(artifact, vid).read_bytes(), cells)
        return self._save_content(actor, project_id, artifact, content, dependencies, work_id)

    def _action_sheet_recalculate(
        self, actor, project_id, alias=None, object_id=None, work_id=None
    ):
        artifact, vid = self._object(actor, project_id, alias, object_id, write=True)
        self._capability("xlsx")
        if artifact["kind"] != "xlsx":
            raise ValueError("Object is not a workbook")
        content = recalculate_xlsx(self.store.version_path(artifact, vid).read_bytes())
        return self._save_content(actor, project_id, artifact, content, work_id=work_id)

    def _sql_inputs(self, actor, project_id, item, aliases):
        if not isinstance(aliases, list) or len(aliases) > 8 or len(aliases) != len(set(aliases)):
            raise ValueError("SQL inputs must name at most eight distinct adopted aliases")
        tables, references = {}, {}
        for alias in aliases:
            binding = binding_for(self.state, item["work_item_id"], alias)
            if binding is None:
                raise ValueError("SQL input requires this work's exact adoption: " + alias)
            data = self._action_read_object(actor, project_id, object_id=binding["object_id"], version_id=binding["version_id"], work_id=item["work_item_id"])
            source = data["data"]
            if not isinstance(source.get("tables"), dict):
                raise ValueError("SQL source must expose explicit typed tables")
            references[alias] = {"object_id": binding["object_id"], "version_id": binding["version_id"]}
            for name, table in source["tables"].items():
                if name in tables:
                    raise ValueError("SQL input table collision: " + name)
                tables[name] = table
        return tables, references

    def _action_sql_build(self, actor, project_id, work_id, code_alias, output_alias, input_aliases):
        from .domains.executable_project import execute, ENGINE_VERSION
        item = self._work(actor, project_id, work_id)
        if item["owner_role"] != actor:
            raise ValueError("Only the exact work owner may execute its SQL build")
        self._project_power(actor, project_id, "execute_sql", "artifact", item["node_id"])
        sql_scope = item.get("requirements", {}).get("sql_project", {})
        expected_output = sql_scope.get("result_alias")
        if expected_output != output_alias or sql_scope.get("code_alias") != code_alias:
            raise ValueError("SQL code/output alias is outside this work's declared execution scope")
        output, _ = self._object(actor, project_id, alias=output_alias, write=True)
        if output["kind"] != "json" or output.get("project_id") != project_id:
            raise ValueError("SQL output must be this project's managed JSON object")
        code = self._action_read_object(actor, project_id, alias=code_alias, work_id=item["work_item_id"])
        tables, sources = self._sql_inputs(actor, project_id, item, input_aliases)
        executed = execute(code["data"], tables)
        code_ref = VersionRef.from_mapping(code["reference"]).to_dict()
        evidence = {"kind": "sql_build", "engine": ENGINE_VERSION, "code_reference": code_ref, "source_references": sources, "work_id": item["work_item_id"], "requirement_version": item["requirement_version"], "status": executed["status"]}
        data = {**executed, "execution": evidence, "sources": sources}
        data["test_results"] = data.pop("tests")
        ref = self._save_content(actor, project_id, output, encode("json", data), [code_ref, *sources.values()], item["work_item_id"])
        output["versions"][ref["version_id"]]["execution_provenance"] = copy.deepcopy(evidence)
        return {"reference": ref, "execution_status": executed["status"], "tables": executed["tables"], "tests": executed["tests"], "error": executed.get("error"), "limits": executed["limits"]}

    def _action_sql_query(self, actor, project_id, work_id, source_alias, sql, output_alias):
        from .domains.executable_project import execute, ENGINE_VERSION
        item = self._work(actor, project_id, work_id)
        if item["owner_role"] != actor:
            raise ValueError("Only the exact work owner may execute its SQL query")
        self._project_power(actor, project_id, "execute_sql", "artifact", item["node_id"])
        sql_scope = item.get("requirements", {}).get("sql_project", {})
        expected_output = sql_scope.get("query_alias")
        if expected_output != output_alias:
            raise ValueError("SQL code/output alias is outside this work's declared execution scope")
        output, _ = self._object(actor, project_id, alias=output_alias, write=True)
        if output["kind"] != "json" or output.get("project_id") != project_id:
            raise ValueError("SQL query output must be this project's managed JSON object")
        binding = binding_for(self.state, item["work_item_id"], source_alias)
        if binding is not None:
            # A readonly workspace alias can outlive upstream drafts. Resolve
            # the version through this exact work binding, never the object's
            # latest version or a guessed last shared version.
            source = self._action_read_object(
                actor, project_id, object_id=binding["object_id"],
                version_id=binding["version_id"], work_id=item["work_item_id"],
            )
        else:
            source_id = self.state["workspaces"][project_id].get(source_alias)
            artifact = self.state["artifacts"].get(source_id)
            if artifact is None or artifact.get("project_id") != project_id:
                raise ToolRejection(
                    "A shared SQL query source requires an adoption for this exact work",
                    code="sql_query_source_binding_required", category="policy_error",
                    context={"work_id": item["work_item_id"], "source_alias": source_alias},
                )
            # An unadopted local result remains queryable under its existing ACL.
            source = self._action_read_object(
                actor, project_id, alias=source_alias, work_id=item["work_item_id"],
            )
        if not isinstance(source["data"].get("tables"), dict):
            raise ValueError("Query source needs managed typed tables")
        executed = execute(tables=source["data"]["tables"], query=sql)
        evidence = {"kind": "sql_query", "engine": ENGINE_VERSION, "source_reference": source["reference"], "work_id": item["work_item_id"], "requirement_version": item["requirement_version"], "status": executed["status"]}
        data = {**executed, "execution": evidence}
        data["test_results"] = data.pop("tests")
        ref = self._save_content(actor, project_id, output, encode("json", data), [source["reference"]], item["work_item_id"])
        output["versions"][ref["version_id"]]["execution_provenance"] = copy.deepcopy(evidence)
        return {"reference": ref, "execution_status": executed["status"], "tables": executed["tables"], "error": executed.get("error"), "limits": executed["limits"]}

    def _action_share(
        self,
        actor,
        project_id,
        object_id,
        version_id,
        target_project,
        actor_ids,
        follow_updates=False,
    ):
        artifact, _ = self._object(actor, project_id, object_id=object_id, version_id=version_id)
        if actor not in artifact["writers"] or artifact.get("project_id") != project_id:
            raise ValueError("Only owning workspace may share its object")
        if project_id is None:
            self._world_power(actor, "share")
        else:
            self._project_power(actor, project_id, "share", "artifact", object_id=object_id)
        target = self.state["projects"].get(target_project)
        allowed = set(target["participants"]) if target else set(self.state["actors"])
        if target is None:
            if project_id is not None:
                raise ValueError("Only world operator may prepare sharing for a future project")
            self._object_id(target_project, "scope")
        if not actor_ids or not set(actor_ids) <= allowed:
            raise ValueError("Share recipients must be known target participants")
        if type(follow_updates) is not bool:
            raise ValueError("Explicit follow_updates boolean required")
        share = {
            "share_id": f"share-{len(self.state['shares']) + 1}",
            "object_id": object_id,
            "version_id": version_id,
            "project_id": target_project,
            "actor_ids": sorted(set(actor_ids)),
            "at": self.state["clock"],
            "actor_id": actor,
            "follow_updates": follow_updates,
        }
        self.state["shares"].append(share)
        return copy.deepcopy(share)

    def _publication_targets(self, artifact):
        targets = {
            s["project_id"]
            for s in self.state["shares"]
            if s["object_id"] == artifact["artifact_id"]
            and s.get("follow_updates")
            and s["project_id"] in self.state["projects"]
        }
        if artifact.get("project_id") is not None:
            targets.add(artifact["project_id"])
        return sorted(targets)

    def _action_publish(
        self,
        actor,
        project_id,
        version_id,
        alias=None,
        object_id=None,
        target_projects=None,
        work_ids=None,
    ):
        artifact, _ = self._object(actor, project_id, alias, object_id, version_id, write=True)
        if version_id not in artifact["versions"]:
            raise ValueError("Publish requires an existing exact version")
        work_scope = [
            self._work(actor, project_id, wid)["work_item_id"] for wid in (work_ids or [])
        ]
        targets = (
            self._publication_targets(artifact) if target_projects is None else target_projects
        )
        result = publish_release(
            self.state, actor, project_id, artifact["artifact_id"], version_id, targets, work_scope
        )
        if result["created"]:
            self._publish_shared(
                actor,
                artifact,
                version_id,
                result["release"]["scope"]["target_projects"],
                result["release"]["release_id"],
            )
        return result

    def _publish_shared(self, actor, artifact, version_id, target_projects=None, release_id=None):
        subscriptions = {}
        for share in self.state["shares"]:
            if share["object_id"] == artifact["artifact_id"] and share.get("follow_updates"):
                subscriptions[(share["project_id"], tuple(share["actor_ids"]))] = share
        for (pid, readers), source in subscriptions.items():
            if target_projects is not None and pid not in target_projects:
                continue
            self.state["shares"].append(
                {
                    **copy.deepcopy(source),
                    "share_id": f"share-{len(self.state['shares']) + 1}",
                    "version_id": version_id,
                    "at": self.state["clock"],
                    "publication_actor": actor,
                    "release_id": release_id,
                }
            )
            for adoption in self.state["adoptions"].values():
                if (
                    adoption["object_id"] == artifact["artifact_id"]
                    and adoption["project_id"] == pid
                    and adoption["policy"] in {"current_applicable", "current_published"}
                ):
                    self._message(
                        actor,
                        readers,
                        pid,
                        "Shared input published",
                        {
                            "object_id": artifact["artifact_id"],
                            "version_id": version_id,
                            "effect": "review_required",
                            "work_ids": adoption["work_ids"],
                        },
                    )

        if release_id is not None:
            release = next(r for r in self.state["releases"] if r["release_id"] == release_id)
            for payload in impact_candidates(self.state, release):
                if not any(
                    e["kind"] == "maintenance_impact"
                    and e["payload"]["impact_id"] == payload["impact_id"]
                    for e in self.state["events"]
                ):
                    self._event("maintenance_impact", payload, delay=1)

    def _action_adopt(self, actor, project_id, alias, object_id, version_id, policy, work_ids):
        self._project(actor, project_id, active=True)
        self._object_id(project_id, alias)
        artifact, version_id = self._object(
            actor, project_id, object_id=object_id, version_id=version_id
        )
        object_id = artifact["artifact_id"]
        if not isinstance(work_ids, list) or not work_ids or len(set(work_ids)) != len(work_ids):
            raise ValueError("Adoption needs distinct exact work IDs")
        items = [self._work(actor, project_id, wid) for wid in work_ids]
        workspace = self.state["workspaces"][project_id]
        if alias in workspace and workspace[alias] != object_id:
            raise ValueError("Alias already points to another object")
        candidate = {
            **self.state,
            "workspaces": {**self.state["workspaces"], project_id: {**workspace, alias: object_id}},
        }
        bindings = []
        for item in items:
            key = binding_key(item["work_item_id"], alias)
            if key in self.state["adoptions"]:
                raise ValueError("This exact work already has an adoption; use its version update")
            if not authority(
                candidate,
                actor,
                "adopt",
                "artifact",
                item["node_id"],
                project_id=project_id,
                object_id=object_id,
            ):
                raise ValueError("Actor lacks project power: adopt")
            bindings.append(
                make_binding(self.state, item, alias, object_id, version_id, policy, actor)
            )
        workspace[alias] = object_id
        self.state["adoptions"].update({binding["adoption_id"]: binding for binding in bindings})
        return copy.deepcopy(bindings[0] if len(bindings) == 1 else {"bindings": bindings})

    def _action_adopt_version(self, actor, project_id, alias, version_id, work_id=None):
        self._project(actor, project_id, active=True)
        if work_id is None:
            candidates = [
                a
                for a in self.state["adoptions"].values()
                if a["project_id"] == project_id
                and a["alias"] == alias
                and current_id(self.state, a["work_id"]) == a["work_id"]
            ]
            if len(candidates) != 1:
                raise ValueError("Specify exact work_id when adoption context is ambiguous")
            work_id = candidates[0]["work_id"]
        item = self._work(actor, project_id, work_id)
        adoption = binding_for(self.state, item["work_item_id"], alias)
        if adoption is None:
            raise ValueError("No adoption for this exact work; explicitly adopt for the new work")
        object_id = self._resolve(project_id, alias)
        if object_id != adoption["object_id"]:
            raise ValueError("Adoption object does not match its workspace alias")
        self._project_power(
            actor, project_id, "adopt", "artifact", work=item["node_id"], object_id=object_id
        )
        if adoption["policy"] == "fixed":
            raise ValueError("Fixed adoption requires a new work declaration")
        self._object(actor, project_id, object_id=object_id, version_id=version_id)
        require_version(item, alias, version_id, adoption["policy"])
        if version_id != adoption["version_id"]:
            adoption["history"].append(
                {
                    "previous_version": adoption["version_id"],
                    "version_id": version_id,
                    "actor_id": actor,
                    "at": self.state["clock"],
                }
            )
            adoption["version_id"] = version_id
        return copy.deepcopy(adoption)

    def _require_credentials(self, actor, item):
        context = ApplicabilityContext(
            item["project_id"],
            item["work_item_id"],
            item["requirement_dimension"],
            item["requirement_version"],
            item["node_id"],
            item.get("period"),
            item["purpose"],
            self.state["clock"],
        )
        for reference in item.get("required_credentials", []):
            ref = VersionRef.from_mapping(reference)
            self._object(
                actor, item["project_id"], object_id=ref.object_id, version_id=ref.version_id
            )
            check = registered_applicability(self.state, ref, context)
            if check.status.value != "PASS":
                raise ValueError(
                    "Required credential is not applicable: " + ",".join(check.reasons)
                )

    def _action_submit(self, actor, project_id, work_id, artifacts, answer=None):
        item = self._work(actor, project_id, work_id)
        self._require_credentials(actor, item)
        if not isinstance(artifacts, list) or len(set(artifacts)) != len(artifacts):
            raise ValueError("Artifact aliases must be unique")
        versions = {}
        for alias in artifacts:
            artifact, vid = self._object(actor, project_id, alias=alias)
            if artifact.get("project_id") != project_id:
                raise ValueError("Deliverables must be created in the bound project")
            versions[artifact["artifact_id"]] = vid
        snapshots = snapshot_bindings(self.state, item)
        return submit_work(
            self.state,
            actor,
            item["work_item_id"],
            versions,
            answer=answer,
            extensions={"adoption_snapshot": snapshots},
        )

    def _action_approve(self, actor, project_id, work_id, submission_id):
        item = self._work(actor, project_id, work_id)
        self._require_credentials(actor, item)
        return approve_submission(self.state, actor, item["work_item_id"], submission_id)

    def _action_withdraw(self, actor, project_id, work_id, submission_id, reason):
        item = self._work(actor, project_id, work_id)
        return withdraw_submission(self.state, actor, item["work_item_id"], submission_id, reason)

    def _action_inspect_submission(self, actor, project_id, work_id, submission_id):
        item = self._work(actor, project_id, work_id, current=False)
        _, submission = submission_for(self.state, item["work_item_id"], submission_id)
        for aid, vid in submission["artifact_versions"].items():
            self._object(actor, project_id, object_id=aid, version_id=vid)
        return copy.deepcopy(submission)

    def _review_read(self, actor, project_id, object_id, version_id, locator=None):
        artifact, vid = self._object(actor, project_id, object_id=object_id, version_id=version_id)
        if not any(read.get("artifact_id") == object_id and read.get("version_id") == vid
                   and read.get("project_id") == project_id
                   for read in self.state["knowledge"][actor]["read_artifacts"]):
            raise ToolRejection("Located review requires a prior actual read of its exact evidence",
                                code="review_evidence_not_read", category="business_constraint")
        if locator is not None:
            content = self.store.version_path(artifact, vid).read_bytes()
            if digest(content) != artifact["versions"][vid]["sha256"]:
                raise ValueError("Located evidence bytes differ from the committed version")
            read_location(artifact["kind"], content, locator)
        return {"object_id": object_id, "version_id": vid}

    def _review_evidence(self, actor, project_id, evidence, required=False):
        if not isinstance(evidence, list) or len(evidence) > 30 or (required and not evidence):
            raise ValueError("Review evidence must be a bounded list of exact read references")
        result = []
        for entry in evidence:
            if not isinstance(entry, dict) or set(entry) - {"object_id", "artifact_id", "version_id", "locator"}:
                raise ValueError("Unsupported review evidence fields")
            ref = VersionRef.from_mapping(entry)
            result.append({**self._review_read(actor, project_id, ref.object_id, ref.version_id,
                                              entry.get("locator")),
                           **({"locator": copy.deepcopy(entry["locator"])} if "locator" in entry else {})})
        return result

    def _review_issue(self, actor, project_id, issue_id):
        self._project(actor, project_id)
        issue = self.state.get("issues", {}).get(issue_id)
        if issue is None or issue["project_id"] != project_id:
            raise ToolRejection("Issue is outside the bound project", code="issue_scope_mismatch",
                                category="policy_error")
        return issue

    def _action_raise_issue(self, actor, project_id, work_id, submission_id, issue_key,
                            object_id, version_id, locator, description, evidence, blocking=True):
        if not isinstance(locator, list) or not locator:
            raise ToolRejection("Located issue requires a nonempty location path",
                                code="invalid_issue_location", category="policy_error")
        item = self._work(actor, project_id, work_id, current=False)
        self._project_power(actor, project_id, "review", "deliverable", item["node_id"], object_id)
        target = self._review_read(actor, project_id, object_id, version_id, locator)
        references = self._review_evidence(actor, project_id, evidence)
        return raise_issue(self.state, actor, item["work_item_id"], submission_id, issue_key,
                           target, locator, description, references, blocking)

    def _action_respond_issue(self, actor, project_id, issue_id, response_key, submission_id,
                              body, evidence):
        self._review_issue(actor, project_id, issue_id)
        references = self._review_evidence(actor, project_id, evidence, required=True)
        return respond_issue(self.state, actor, issue_id, response_key, submission_id, body, references)

    def _action_decide_issue(self, actor, project_id, issue_id, response_id, decision_key,
                             decision, reason):
        issue = self._review_issue(actor, project_id, issue_id)
        response = self.state.get("issue_responses", {}).get(response_id)
        if response is None or response["issue_id"] != issue_id:
            raise ToolRejection("Response targets another issue", code="issue_response_mismatch",
                                category="policy_error")
        item, submission = submission_for(self.state, issue["work_id"], response["submission_id"])
        self._project_power(actor, project_id, "review", "deliverable", item["node_id"], issue["target"]["object_id"])
        for aid, vid in submission["artifact_versions"].items():
            self._review_read(actor, project_id, aid, vid)
        self._review_evidence(actor, project_id, response["evidence"])
        return decide_issue(self.state, actor, issue_id, response_id, decision_key, decision, reason)

    def _action_confirm(self, actor, project_id, work_id, alias, dimension, purpose, period=None):
        item = self._work(actor, project_id, work_id)
        artifact, vid = self._object(actor, project_id, alias=alias)
        if artifact.get("project_id") != project_id:
            raise ValueError("A project confirms its own credential objects")
        ref = VersionRef(artifact["artifact_id"], vid)
        credential = Credential(
            reference=ref.to_dict(),
            project_id=project_id,
            requirement_dimension=dimension,
            requirement_version=item["requirement_version"],
            work_nodes=(item["node_id"],),
            period=period,
            purpose=purpose,
            effective_at=self.state["clock"],
            confirmed_by=actor,
            attestation_ref="att-" + journal.canonical_digest([ref.to_dict(), project_id])[:24],
        )
        return confirm_credential(self.state, actor, ref, credential)

    def _action_revise(self, actor, project_id, work_id, updates, reason):
        item = self._work(actor, project_id, work_id)
        updates = copy.deepcopy(updates)
        if (
            "owner_role" in updates
            and updates["owner_role"] not in self.state["projects"][project_id]["participants"]
        ):
            raise ValueError("Replacement owner must participate in project")
        if "approval_policy" in updates and updates["approval_policy"] not in {
            "review",
            "delivery_only",
        }:
            raise ValueError("Unknown approval policy")
        if "deliverable_contract" in updates:
            updates["deliverable_contract"] = validate_deliverable_contract(
                updates["deliverable_contract"]
            )
        for aid in updates.get("deliverables", []):
            artifact, _ = self._object(actor, project_id, object_id=aid)
            if artifact.get("project_id") != project_id:
                raise ValueError("Deliverable scope exceeds project")
        for aid in updates.get("inputs", []):
            self._object(actor, project_id, object_id=aid)
        for ref in updates.get("required_credentials", []):
            parsed = VersionRef.from_mapping(ref)
            self._object(
                actor, project_id, object_id=parsed.object_id, version_id=parsed.version_id
            )
        validate_policy_contract({**item, **updates})
        replacements = revise_requirement(
            self.state, [item["work_item_id"]], updates, actor, reason
        )
        self.state["projects"][project_id]["work_ids"].extend(replacements.values())
        self._message(
            actor,
            [item["owner_role"]],
            project_id,
            "Requirements revised",
            {"replacements": replacements},
        )
        return {"replacements": replacements}

    def _action_request(
        self, actor, project_id, work_id, provider, reference, purpose="evidence", delay=10
    ):
        item = self._work(actor, project_id, work_id)
        if (
            actor != item["owner_role"]
            or provider not in self.state["projects"][project_id]["participants"]
        ):
            raise ValueError("Only owner may request a project provider")
        if type(delay) is not int or not 1 <= delay <= 100:
            raise ValueError("Reply delay must be between 1 and 100")
        ref = VersionRef.from_mapping(reference)
        self._project_power(
            provider, project_id, "provide", purpose, item["node_id"], ref.object_id
        )
        self._object(provider, project_id, object_id=ref.object_id, version_id=ref.version_id)
        msg = self._message(actor, [provider], project_id, purpose, {"reference": ref.to_dict()})
        msg["work_item_id"] = item["work_item_id"]
        rid = msg["message_id"]
        cid = project_id + "::condition-" + rid
        self.state["requests"][rid] = {
            "request_id": rid,
            "project_id": project_id,
            "work_item_id": item["work_item_id"],
            "requirement_version": item["requirement_version"],
            "requested_role": provider,
            "evidence_reference": ref.to_dict(),
            "status": "pending",
        }
        self.state["condition_specs"][cid] = {
            "condition_id": cid,
            "work_item_id": item["work_item_id"],
            "requirement_version": item["requirement_version"],
            "request_id": rid,
            "providers": [provider],
            "expected_version": item["requirement_version"],
            "purpose": purpose,
            "required_power": "provide",
            "subject": purpose,
            "evidence_spec": {"kind": "version", "reference": ref.to_dict()},
            "history": [{"event": "created", "at": self.state["clock"], "request_id": rid}],
        }
        self._event(
            "project_reply",
            {
                "project_id": project_id,
                "request_id": rid,
                "condition_id": cid,
                "actor": provider,
                "reference": ref.to_dict(),
                "purpose": purpose,
            },
            delay,
        )
        return {"request_id": rid, "condition_id": cid}

    def _action_set_information_availability(self, actor, project_id, route_id, available, reason):
        self._project(actor, project_id, active=True)
        if type(available) is not bool or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Availability needs a boolean and a concrete reason")
        route = next(
            (
                r
                for r in self.state["projects"][project_id]["information_routes"]
                if r["route_id"] == route_id
            ),
            None,
        )
        if route is None or actor != route["provider"]:
            raise ValueError("Only the declared provider may update this information route")
        self._project_power(
            actor,
            project_id,
            "provide",
            route["purpose"],
            work=route["work_node"],
            object_id=route["object_id"],
        )
        value = "available" if available else "unavailable"
        if route["availability"] == value:
            return {
                "route_id": route_id,
                "availability": value,
                "availability_revision": route["availability_revision"],
                "changed": False,
            }
        route["availability"] = value
        route["availability_revision"] += 1
        update = {
            "project_id": project_id,
            "route_id": route_id,
            "actor_id": actor,
            "at": self.state["clock"],
            "availability": value,
            "availability_revision": route["availability_revision"],
            "reason": reason,
        }
        self.state.setdefault("information_updates", []).append(update)
        recipients = sorted(
            {
                item["owner_role"]
                for item in self.state["work_items"].values()
                if item["project_id"] == project_id and item["node_id"] == route["work_node"]
            }
        )
        self._message(
            actor, recipients, project_id, "Information route availability changed", update
        )
        return {**update, "changed": True}

    def _action_request_information(self, actor, project_id, route_id, work_id):
        item = self._work(actor, project_id, work_id)
        routes = self.state["projects"][project_id].get("information_routes", [])
        route = next((r for r in routes if r["route_id"] == route_id), None)
        if route is None or item["node_id"] != route["work_node"]:
            raise ValueError("No supported information route for this exact work lineage")
        version = route["version_id"]
        if route["version_policy"] == "work_requirement":
            version = declared_version(item, route["object_alias"])
            if version is None and "current_published" in allowed_policies(
                item, route["object_alias"]
            ):
                version = latest_published_version(self.state, route["object_id"], project_id)
            version = version or route["version_id"]
        elif route["version_policy"] == "current_published":
            version = latest_published_version(self.state, route["object_id"], project_id)
            if version is None:
                raise ValueError("Information route has no published target")
        reference = {"object_id": route["object_id"], "version_id": version}
        result = self._action_request(
            actor,
            project_id,
            work_id,
            route["provider"],
            reference,
            purpose=route["purpose"],
            delay=route["delay"],
        )
        request = self.state["requests"][result["request_id"]]
        request.update(route_id=route_id, route_revision=route["availability_revision"])
        if route["availability"] == "available":
            for old in self.state["requests"].values():
                if (
                    old["request_id"] != request["request_id"]
                    and old.get("route_id") == route_id
                    and old["work_item_id"] == item["work_item_id"]
                    and old["status"] in {"pending", "unavailable"}
                    and old.get("route_revision", 0) < route["availability_revision"]
                ):
                    for cid, condition in self.state["condition_specs"].items():
                        if condition.get("request_id") == old["request_id"] and condition[
                            "status"
                        ] in {"open", "unavailable"}:
                            supersede_condition(
                                self.state,
                                cid,
                                "Provider availability restored; new exact request",
                                {"request_id": request["request_id"]},
                            )
        for event in self.state["events"]:
            if event["payload"].get("request_id") == result["request_id"]:
                event["payload"].update(grant_on_reply=True, availability=route["availability"])
        return result

    def _event_actor(self, event):
        return event["payload"]["actor"]

    def _event_frame(self, event):
        if event["kind"] == "maintenance_impact":
            payload = event["payload"]
            item = self.state["work_items"][payload["target_work_id"]]
            new_id = (
                successor_identity(payload)
                if payload["effect"] == "successor"
                else item["node_id"] + "@r" + str(item["requirement_version"] + 1)
            )
            paths = (
                ("messages",),
                ("maintenance_impacts", payload["impact_id"]),
                ("projects", payload["project_id"]),
                ("work_items", item["work_item_id"]),
                ("work_items", new_id),
                ("work_replacements", item["work_item_id"]),
                ("requirement_events",),
            )
            paths += tuple(
                ("condition_specs", cid)
                for cid, c in self.state["condition_specs"].items()
                if c["work_item_id"] == item["work_item_id"]
            )
            return ActionFrame("PublicationImpact", paths)
        if event["kind"] != "project_reply":
            raise ValueError("Unknown world event")
        payload = event["payload"]
        return ActionFrame(
            "ProjectReply",
            (
                ("messages",),
                ("raw_condition_responses",),
                ("shares",),
                ("condition_specs", payload["condition_id"]),
                ("requests", payload["request_id"]),
            ),
        )

    def _apply_event(self, event):
        payload = event["payload"]
        if event["kind"] == "maintenance_impact":
            result = apply_impact(self.state, payload)
            if result["created"] and result["outcome"] == "applied":
                item = self.state["work_items"][payload["target_work_id"]]
                self._message(
                    payload["actor"],
                    [item["owner_role"]],
                    payload["project_id"],
                    "Declared publication consequence",
                    result,
                )
            return {"outcome": result["outcome"], "result": result}
        request = self.state["requests"][payload["request_id"]]
        project = self.state["projects"][payload["project_id"]]
        if (
            project["status"] != "active"
            and project["close_policy"]["pending_obligations"] == "cancel"
        ):
            request.update(
                status="cancelled",
                cancellation_reason="project_closed",
                cancelled_at=self.state["clock"],
            )
            return {"outcome": "cancelled", "result": {"reason": "project_closed"}}
        response = {
            "response_id": "response-" + event["event_id"],
            "request_id": payload["request_id"],
            "work_item_id": request["work_item_id"],
            "requirement_version": request["requirement_version"],
            "responder": payload["actor"],
            "condition_version": request["requirement_version"],
            "purpose": payload["purpose"],
            "status": "unavailable"
            if payload.get("availability") == "unavailable"
            else "delivered",
            "reference": payload["reference"],
        }
        # Only an explicitly installed information route delegates exact-version
        # delivery. Ordinary replies never infer an access grant.
        if (
            payload.get("grant_on_reply")
            and response["status"] == "delivered"
            and current_id(self.state, request["work_item_id"]) == request["work_item_id"]
        ):
            ref = VersionRef.from_mapping(payload["reference"])
            artifact, _ = self._object(
                payload["actor"],
                payload["project_id"],
                object_id=ref.object_id,
                version_id=ref.version_id,
            )
            if (
                artifact.get("project_id") != payload["project_id"]
                or payload["actor"] not in artifact["writers"]
            ):
                raise ValueError("Information route cannot re-share another workspace's material")
            owner = self.state["work_items"][request["work_item_id"]]["owner_role"]
            self.state["shares"].append(
                {
                    "share_id": f"share-{len(self.state['shares']) + 1}",
                    "object_id": ref.object_id,
                    "version_id": ref.version_id,
                    "project_id": payload["project_id"],
                    "actor_ids": [owner],
                    "actor_id": payload["actor"],
                    "at": self.state["clock"],
                    "follow_updates": False,
                    "route_id": request["route_id"],
                }
            )
        result = apply_response(self.state, response)
        item = self.state["work_items"][request["work_item_id"]]
        self._message(
            payload["actor"],
            [item["owner_role"]],
            payload["project_id"],
            "Requested reply",
            response,
        )
        request["status"] = response["status"]
        return {"outcome": "applied", "result": result}

    def _action_read_messages(self, actor, project_id):
        rows = [
            m
            for m in self.state["messages"]
            if actor in m["recipients"] and m.get("project_id") == project_id
        ]
        seen = self.state["knowledge"][actor]["read_messages"]
        for row in rows:
            if row["message_id"] not in seen:
                seen.append(row["message_id"])
        return copy.deepcopy(rows)

    def _action_wait(self, actor, project_id, ticks=1):
        if type(ticks) is not int or not 1 <= ticks <= 100:
            raise ValueError("ticks must be an integer between 1 and 100")
        # Clock is owned by runner except for explicit wait advancement.
        self.state["clock"] += ticks - 1
        return {"advanced_ticks": ticks}

    def _action_close_project(self, actor, project_id, mode="completed", reason=""):
        self._project_power(actor, project_id, "close_project")
        project = self.state["projects"][project_id]
        if mode not in {"completed", "archived"} or not reason:
            raise ValueError("Explicit completed/archived mode and reason required")
        views = derive_current_work_view(self.state)
        current = [
            item
            for item in self.state["work_items"].values()
            if item["project_id"] == project_id and views[item["work_item_id"]]["is_current"]
        ]
        if mode == "completed" and any(
            views[item["work_item_id"]]["status"] != "accepted" for item in current
        ):
            raise ValueError("Project has unfinished current obligations")
        if (
            mode == "archived"
            and project.get("close_policy", {}).get("pending_obligations") == "cancel"
        ):
            for item in current:
                if views[item["work_item_id"]]["status"] != "accepted":
                    item["cancelled_at"] = self.state["clock"]
                    item["cancellation_reason"] = reason
                for cid, condition in self.state["condition_specs"].items():
                    if condition["work_item_id"] == item["work_item_id"] and condition[
                        "status"
                    ] in {"open", "unavailable"}:
                        supersede_condition(self.state, cid, reason)
        project.update(status=mode, ended_at=self.state["clock"], end_reason=reason)
        self.state["project_history"].append(
            {
                "project_id": project_id,
                "event": mode,
                "at": self.state["clock"],
                "actor": actor,
                "reason": reason,
            }
        )
        # Pending local events are retained and later commit an explicit cancelled
        # outcome. Other projects and world subscriptions are not removed.
        return copy.deepcopy(project)

    def _action_start_episode(self, actor, project_id, episode_id, project_ids=None):
        pids = [project_id] if project_id is not None else project_ids
        if not pids or episode_id in self.state["episodes"]:
            raise ValueError("Episode needs new identity and selected projects")
        for pid in pids:
            self._project(actor, pid)
        self.state["episodes"][episode_id] = {
            "episode_id": episode_id,
            "actor_id": actor,
            "project_ids": pids,
            "started_at": self.state["clock"],
            "ended_at": None,
            "start_revision": self.state["state_revision"],
        }
        return copy.deepcopy(self.state["episodes"][episode_id])

    def _action_end_episode(self, actor, project_id, episode_id):
        episode = self.state["episodes"][episode_id]
        if (
            episode["actor_id"] != actor
            or episode["ended_at"] is not None
            or (project_id is not None and project_id not in episode["project_ids"])
        ):
            raise ValueError("Episode is not active for this session")
        episode["ended_at"] = self.state["clock"]
        episode["end_revision"] = self.state["state_revision"] + 1
        return copy.deepcopy(episode)

    def observe(self, actor, project_id=None):
        with self.store.lock():
            self.state = self.store.load()
            self._role(actor)
            self._derive(self.state)
            if project_id is not None:
                self._project(actor, project_id)
            projects = {
                pid: {
                    key: copy.deepcopy(value)
                    for key, value in p.items()
                    if key != "information_routes"
                }
                for pid, p in self.state["projects"].items()
                if actor in p["participants"] and (project_id is None or pid == project_id)
            }
            work = {}
            views = derive_current_work_view(self.state)
            for wid, item in self.state["work_items"].items():
                if item["project_id"] not in projects:
                    continue
                view = copy.deepcopy(views[wid])
                view["enabled_actions"] = [
                    action
                    for action in view["enabled_actions"]
                    if (action in {"submit", "withdraw"} and item["owner_role"] == actor)
                    or (
                        action == "approve"
                        and authority(
                            self.state,
                            actor,
                            "approve",
                            "deliverable",
                            item["node_id"],
                            project_id=item["project_id"],
                        )
                    )
                ]
                try:
                    self._require_credentials(actor, item)
                except ValueError:
                    view["enabled_actions"] = [
                        a for a in view["enabled_actions"] if a not in {"submit", "approve"}
                    ]
                if (
                    projects[item["project_id"]]["status"] != "active"
                    or self.state.get("world_status") == "paused"
                ):
                    view["enabled_actions"] = []
                work[wid] = {
                    **view,
                    "latest_submission_id": item["submissions"][-1]["submission_id"] if item.get("submissions") else None,
                    **{
                        key: copy.deepcopy(item[key])
                        for key in (
                            "project_id",
                            "local_work_id",
                            "node_id",
                            "requirement_version",
                            "goal",
                            "owner_role",
                            "visible_requirements",
                            "requirements",
                            "inputs",
                            "deliverables",
                            "deliverable_contract",
                            "approval_policy",
                            "required_credentials",
                            "requirement_dimension",
                            "purpose",
                            "period",
                        )
                        if key in item
                    },
                }
            objects = {}
            for aid, artifact in self.state["artifacts"].items():
                scope = project_id
                if any(self._can_read(actor, scope, artifact, vid) for vid in artifact["versions"]):
                    objects[aid] = {
                        "filename": artifact["filename"],
                        "kind": artifact["kind"],
                        "role": artifact.get("deliverable_role", "draft"),
                        "versions": [
                            vid
                            for vid in artifact["versions"]
                            if self._can_read(actor, scope, artifact, vid)
                        ],
                    }
            return {
                "world_id": self.state["world_id"],
                "instance_id": self.state["instance_id"],
                "branch_id": self.state["branch_id"],
                "actor_id": actor,
                "logical_time": self.state["clock"],
                "world_status": "paused"
                if self.state.get("world_status") == "paused"
                else "active"
                if any(p["status"] == "active" for p in self.state["projects"].values())
                else "idle",
                "projects": projects,
                "workspaces": {
                    pid: {
                        alias: aid
                        for alias, aid in self.state["workspaces"][pid].items()
                        if any(
                            self._can_read(actor, pid, self.state["artifacts"][aid], vid)
                            for vid in self.state["artifacts"][aid]["versions"]
                        )
                    }
                    for pid in projects
                },
                "work_items": work,
                "objects": objects,
                "information_routes": [
                    {
                        **{
                            key: copy.deepcopy(route[key])
                            for key in (
                                "route_id",
                                "project_id",
                                "provider",
                                "object_alias",
                                "purpose",
                                "work_node",
                                "availability",
                                "availability_revision",
                            )
                        },
                        "work_id": wid,
                    }
                    for pid in projects
                    for route in self.state["projects"][pid].get("information_routes", [])
                    for wid, item in self.state["work_items"].items()
                    if item["project_id"] == pid
                    and item["node_id"] == route["work_node"]
                    and views[wid]["is_current"]
                    and views[wid]["status"] not in {"accepted", "cancelled"}
                ],
                "issues": {iid: copy.deepcopy(issue) for iid, issue in self.state.get("issues", {}).items()
                           if issue["project_id"] in projects},
                "issue_views": {iid: copy.deepcopy(view) for iid, view in derive_issue_view(self.state).items()
                                if self.state["issues"][iid]["project_id"] in projects},
                "issue_responses": {rid: copy.deepcopy(record) for rid, record in self.state.get("issue_responses", {}).items()
                                    if record["project_id"] in projects},
                "issue_decisions": {did: copy.deepcopy(record) for did, record in self.state.get("issue_decisions", {}).items()
                                    if record["project_id"] in projects},
                "conditions": {
                    cid: copy.deepcopy(condition)
                    for cid, condition in self.state["condition_specs"].items()
                    if condition["work_item_id"] in work
                },
                "publications": [
                    copy.deepcopy(release)
                    for release in self.state.get("releases", [])
                    if (
                        project_id is None
                        and release["source_project"] is None
                        or project_id in release["scope"]["target_projects"]
                    )
                    and self._can_read(
                        actor,
                        project_id,
                        self.state["artifacts"][release["object_id"]],
                        release["version_id"],
                    )
                ],
                "adoptions": {
                    key: {
                        **copy.deepcopy(value),
                        **{
                            field: copy.deepcopy(self.state["adoptions"][key][field])
                            for field in (
                                "alias",
                                "object_id",
                                "work_id",
                                "work_ids",
                                "requirement_version",
                            )
                        },
                    }
                    for key, value in self.state["adoption_view"].items()
                    if self.state["adoptions"][key]["project_id"] in projects
                },
            }

    def evaluate_submission(self, project_id, work_id, submission_id):
        """Independent finite contract evaluation of immutable submitted bytes."""
        with self.store.lock():
            self.state = self.store.load()
            wid = work_id if "::" in work_id else project_id + "::" + work_id
            item = self.state["work_items"][wid]
            if item["project_id"] != project_id:
                raise ValueError("Wrong evaluation scope")
            sub = next(s for s in item["submissions"] if s["submission_id"] == submission_id)
            return evaluate_work_product(self.store, self.state, item, sub)

    def applicability(self, project_id, work_id, reference, dimension, purpose, period=None):
        item = self.state["work_items"][work_id if "::" in work_id else project_id + "::" + work_id]
        return registered_applicability(
            self.state,
            reference,
            ApplicabilityContext(
                project_id,
                item["work_item_id"],
                dimension,
                item["requirement_version"],
                item["node_id"],
                period,
                purpose,
                self.state["clock"],
            ),
        ).to_dict()


class ProjectSession:
    """Trusted host binds actor/project once; tool data cannot replace that scope."""

    def __init__(self, world, actor, project_id):
        self._world, self.actor_id, self.project_id = world, actor, project_id

    def call(self, action, request_key=None, **arguments):
        envelope = {"tool": action, "arguments": arguments}
        if self.project_id is not None:
            envelope["project_id"] = self.project_id
        return self._world.act(
            self.actor_id,
            "project_action" if self.project_id is not None else "world_action",
            envelope,
            request_key=request_key,
        )

    def observe(self):
        return self._world.observe(self.actor_id, self.project_id)

    def tools(self):
        return self._world.tools(self.actor_id, self.project_id)
