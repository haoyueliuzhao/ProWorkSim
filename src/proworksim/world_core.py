"""A persistent world with project-scoped sessions and dynamically created objects.

Uses the same single-writer runner, version store, conditions and work transitions
as the finite template adapters. No financial object or singleton project exists
in this runtime's state contract.
"""

import copy
import json
import re
import uuid
from pathlib import Path

from .core import journal
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
from .storage import Store, atomic_write, json_bytes


class WorldCore(WorldRunner):
    runtime_schema = "world-core-v0.6"

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
            state["adoption_view"][key] = {
                "adopted_version": adoption["version_id"],
                "target_version": target,
                "status": "current" if target == adoption["version_id"] else "update_required",
                "policy": adoption["policy"],
            }

    def _complete_frame(self, frame):
        frame = super()._complete_frame(frame)
        return ActionFrame(frame.name, frame.paths, frame.derived_paths + (("adoption_view",),))

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
            raise ValueError("Actor lacks world power: " + power)

    def _project_power(self, actor, project_id, power, subject="*", work=None, object_id=None):
        self._project(actor, project_id)
        if not authority(
            self.state, actor, power, subject, work, project_id=project_id, object_id=object_id
        ):
            raise ValueError("Actor lacks project power: " + power)

    def _work(self, actor, project_id, work_id, current=True):
        self._project(actor, project_id, active=current)
        key = work_id if "::" in work_id else project_id + "::" + work_id
        item = self.state["work_items"].get(key)
        if item is None or item["project_id"] != project_id:
            raise ValueError("Work reference escapes bound project")
        if current and key in self.state.get("work_replacements", {}):
            raise ValueError("Work reference is superseded")
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
        if artifact.get("project_id") == project_id:
            return actor in artifact["readers"]
        return any(
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
            if tool == "request":
                paths.append(("condition_specs",))
        if tool == "wait":
            paths.append(("clock",))
        return ActionFrame(str(tool), tuple(paths))

    def _tool_project_action(self, actor, project_id, tool, arguments):
        self._project(
            actor, project_id, active=tool not in {"read_object", "read_messages", "end_episode"}
        )
        return self._dispatch(actor, project_id, tool, arguments)

    def _tool_world_action(self, actor, tool, arguments):
        if tool not in {
            "pause",
            "resume",
            "install_project",
            "create_object",
            "write_object",
            "read_object",
            "share",
            "start_episode",
            "end_episode",
            "wait",
        }:
            raise ValueError("Tool is not a world operation")
        return self._dispatch(actor, None, tool, arguments)

    def _dispatch(self, actor, project_id, tool, arguments):
        if self.state.get("world_status") == "paused" and tool not in {
            "resume",
            "read_object",
            "read_messages",
            "end_episode",
        }:
            raise ValueError("World is paused; resume before new work")
        if not isinstance(arguments, dict) or set(arguments) & {"actor", "actor_id", "project_id"}:
            raise ValueError("Tool arguments cannot override trusted session context")
        handler = getattr(self, "_action_" + tool, None) if isinstance(tool, str) else None
        if handler is None:
            raise ValueError("Unknown world-core tool")
        return handler(actor, project_id, **arguments)

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
                self.state, payload["object_id"], json_bytes(payload["data"]), payload["owner"]
            )
        pid = package["project_id"]
        return {"project_id": pid, "objects": [p["object_id"] for p in payloads]}

    @staticmethod
    def _object_id(project_id, alias):
        return object_identity(project_id, alias)

    def _action_create_object(
        self, actor, project_id, alias, filename, data, deliverable_role="draft", dependencies=None
    ):
        if project_id is None:
            self._world_power(actor, "create_object")
            workspace = self.state.setdefault("world_workspace", {})
        else:
            self._project_power(actor, project_id, "create_object", "artifact")
            workspace = self.state["workspaces"][project_id]
        aid = self._object_id(project_id, alias)
        if alias in workspace or aid in self.state["artifacts"]:
            raise ValueError("Object alias or identity already exists")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.json", filename):
            raise ValueError("Only simple JSON filenames are supported")
        if not isinstance(data, dict) or not isinstance(deliverable_role, str):
            raise ValueError("JSON object data and an explicit artifact role are required")
        encoded = json_bytes(data)
        deps = self._checked_dependencies(actor, project_id, dependencies or [])
        artifact = {
            "artifact_id": aid,
            "project_id": project_id,
            "filename": filename,
            "storage_path": f"artifacts/{aid}/{filename}",
            "kind": "json",
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

    def _action_write_object(
        self, actor, project_id, data, alias=None, object_id=None, dependencies=None
    ):
        artifact, old = self._object(actor, project_id, alias, object_id, write=True)
        if project_id is None:
            self._world_power(actor, "publish")
        if not isinstance(data, dict):
            raise ValueError("Content must be a JSON object")
        refs = (
            artifact["versions"][old]["derived_from"]
            if dependencies is None
            else self._checked_dependencies(actor, project_id, dependencies)
        )
        if any(ref["artifact_id"] == artifact["artifact_id"] for ref in refs):
            raise ValueError("Self dependency")
        version = self.store.put(self.state, artifact["artifact_id"], json_bytes(data), actor, refs)
        record_artifact_edit(self.state, actor, artifact["artifact_id"], version["version_id"])
        self._writes.append(
            {"artifact_id": artifact["artifact_id"], "before": old, "after": version["version_id"]}
        )
        self._publish_shared(actor, artifact, version["version_id"])
        return {"object_id": artifact["artifact_id"], "version_id": version["version_id"]}

    def _action_read_object(self, actor, project_id, alias=None, object_id=None, version_id=None):
        artifact, vid = self._object(actor, project_id, alias, object_id, version_id)
        ref = {"artifact_id": artifact["artifact_id"], "version_id": vid}
        self._reads.append(ref)
        record = {**ref, "project_id": project_id, "at": self.state["clock"]}
        self.state["knowledge"][actor]["read_artifacts"].append(record)
        return {"reference": ref, "data": json.loads(self.store.content(artifact, vid))}

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

    def _publish_shared(self, actor, artifact, version_id):
        subscriptions = {}
        for share in self.state["shares"]:
            if share["object_id"] == artifact["artifact_id"] and share.get("follow_updates"):
                subscriptions[(share["project_id"], tuple(share["actor_ids"]))] = share
        for (pid, readers), source in subscriptions.items():
            self.state["shares"].append(
                {
                    **copy.deepcopy(source),
                    "share_id": f"share-{len(self.state['shares']) + 1}",
                    "version_id": version_id,
                    "at": self.state["clock"],
                    "publication_actor": actor,
                }
            )
            for adoption in self.state["adoptions"].values():
                if (
                    adoption["object_id"] == artifact["artifact_id"]
                    and adoption["project_id"] == pid
                    and adoption["policy"] == "current_applicable"
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

    def _action_adopt(self, actor, project_id, alias, object_id, version_id, policy, work_ids):
        if policy not in {"current_applicable", "fixed"}:
            raise ValueError("Unknown adoption policy")
        self._project_power(actor, project_id, "adopt", "artifact")
        self._object(actor, project_id, object_id=object_id, version_id=version_id)
        ids = [self._work(actor, project_id, wid)["work_item_id"] for wid in work_ids]
        workspace = self.state["workspaces"][project_id]
        if alias in workspace and workspace[alias] != object_id:
            raise ValueError("Alias already points to another object")
        self._object_id(project_id, alias)  # Validate local alias syntax only.
        key = project_id + "::" + alias
        existing = self.state["adoptions"].get(key)
        if existing:
            raise ValueError("Use explicit new alias for a changed adoption declaration")
        workspace[alias] = object_id
        self.state["adoptions"][key] = {
            "project_id": project_id,
            "alias": alias,
            "object_id": object_id,
            "version_id": version_id,
            "policy": policy,
            "work_ids": ids,
            "actor_id": actor,
            "at": self.state["clock"],
        }
        return copy.deepcopy(self.state["adoptions"][key])

    def _action_adopt_version(self, actor, project_id, alias, version_id):
        self._project_power(actor, project_id, "adopt", "artifact")
        adoption = self.state["adoptions"][project_id + "::" + alias]
        if adoption["policy"] != "current_applicable":
            raise ValueError("Fixed adoption requires a new explicit declaration")
        self._object(actor, project_id, object_id=adoption["object_id"], version_id=version_id)
        if version_id == adoption["version_id"]:
            return copy.deepcopy(adoption)
        adoption.setdefault("history", []).append(
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
        return submit_work(self.state, actor, item["work_item_id"], versions, answer=answer)

    def _action_approve(self, actor, project_id, work_id, submission_id):
        item = self._work(actor, project_id, work_id)
        self._require_credentials(actor, item)
        return approve_submission(self.state, actor, item["work_item_id"], submission_id)

    def _action_withdraw(self, actor, project_id, work_id, submission_id, reason):
        item = self._work(actor, project_id, work_id)
        return withdraw_submission(self.state, actor, item["work_item_id"], submission_id, reason)

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

    def _event_actor(self, event):
        return event["payload"]["actor"]

    def _event_frame(self, event):
        if event["kind"] != "project_reply":
            raise ValueError("Unknown world event")
        payload = event["payload"]
        return ActionFrame(
            "ProjectReply",
            (
                ("messages",),
                ("raw_condition_responses",),
                ("condition_specs", payload["condition_id"]),
                ("requests", payload["request_id"]),
            ),
        )

    def _apply_event(self, event):
        payload = event["payload"]
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
            "status": "delivered",
            "reference": payload["reference"],
        }
        # Reply delivery does not confer permission on the evidence object.
        result = apply_response(self.state, response)
        item = self.state["work_items"][request["work_item_id"]]
        self._message(
            payload["actor"],
            [item["owner_role"]],
            payload["project_id"],
            "Requested reply",
            response,
        )
        request["status"] = "delivered"
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
                pid: copy.deepcopy(p)
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
                    "project_id": item["project_id"],
                    "goal": item["goal"],
                    "owner_role": item["owner_role"],
                }
            objects = {}
            for aid, artifact in self.state["artifacts"].items():
                scope = project_id
                if any(self._can_read(actor, scope, artifact, vid) for vid in artifact["versions"]):
                    objects[aid] = {
                        "filename": artifact["filename"],
                        "versions": [
                            vid
                            for vid in artifact["versions"]
                            if self._can_read(actor, scope, artifact, vid)
                        ],
                    }
            return {
                "world_id": self.state["world_id"],
                "actor_id": actor,
                "logical_time": self.state["clock"],
                "world_status": "paused"
                if self.state.get("world_status") == "paused"
                else "active"
                if any(p["status"] == "active" for p in self.state["projects"].values())
                else "idle",
                "projects": projects,
                "work_items": work,
                "objects": objects,
                "adoptions": {
                    key: copy.deepcopy(value)
                    for key, value in self.state["adoption_view"].items()
                    if self.state["adoptions"][key]["project_id"] in projects
                },
            }

    def evaluate_submission(self, project_id, work_id, submission_id):
        """Trusted, independent finite JSON contract check; never mutates review."""
        with self.store.lock():
            self.state = self.store.load()
            wid = work_id if "::" in work_id else project_id + "::" + work_id
            item = self.state["work_items"][wid]
            if item["project_id"] != project_id:
                raise ValueError("Wrong evaluation scope")
            sub = next(s for s in item["submissions"] if s["submission_id"] == submission_id)
            contract = sub["requirement_snapshot"].get("deliverable_contract", {})
            combined, conflicts = {}, []
            for aid, vid in sub["artifact_versions"].items():
                data = json.loads(self.store.content(self.state["artifacts"][aid], vid))
                for key, value in data.items():
                    if key in combined and combined[key] != value:
                        conflicts.append(key)
                    combined[key] = value
            missing = sorted(set(contract.get("required_fields", [])) - set(combined))
            return {
                "submission_id": submission_id,
                "passed": not missing and not conflicts,
                "missing_fields": missing,
                "conflicting_fields": conflicts,
                "scope": "finite_json_presence_contract",
                "institutional_review": copy.deepcopy(sub["review"]),
            }

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
