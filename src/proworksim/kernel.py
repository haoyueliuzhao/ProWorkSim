"""Operating-world tool facade using the shared semantics kernel and adapters."""

import copy
import json
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from .core.transitions import execute_transition, ordered_due_events
from .core.work import submit_work, withdraw_submission, approve_submission, dependencies_ready
from .core.visibility import project_fields
from .adapters.action_scopes import tool_frame, reply_frame
from .adapters.communication import (
    deliver_reply,
    register_request,
    supports_request,
    restore_information,
)
from .policies.organization import authority, position, require_authority
from .freshness import refresh_freshness
from .workflow import is_complete, on_accept
from .basis import visible_version, requirement_basis
from .blockers import create_blocker, mark_unavailable
from .lifecycle import (
    current_id,
    current_work_items,
    blocked_terminal,
    schedule_interruptions,
    revise_basis,
)
from .schema import (
    InteractionRecord,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    Status,
    WorldSnapshot,
)
from .spreadsheet import Spreadsheet, arithmetic
from .staff import review_submission
from .storage import Store, atomic_write, digest, json_bytes, read_json


class WorldError(ValueError):
    pass


class World:
    def __init__(self, root):
        self.store = Store(root)
        with self.store.lock():
            self.state = self.store.load()
            if self.state["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS:
                raise WorldError("Unsupported world schema")
            self.store.recover(self.state)
        self._reads = []
        self._writes = []

    def _derive(self, state):
        refresh_freshness(state)

    def _action_frame(self, actor, action, arguments):
        return tool_frame(self.state, actor, action, arguments)

    def session(self, actor_id="analyst"):
        self._role(actor_id)
        return WorkerSession(self, actor_id)

    def _role(self, actor):
        for role in self.state["roles"]:
            if role["role_id"] == actor:
                return role
        raise WorldError("Unknown actor")

    def _artifact(self, actor, artifact_id, write=False, version=None):
        artifact = self.state["artifacts"].get(artifact_id)
        if (
            artifact is None
            or visible_version(artifact, actor, self.state["clock"], version) is None
        ):
            raise WorldError("Artifact unavailable to this role or version")
        if write and actor not in artifact["writers"]:
            raise WorldError("Role is not allowed to modify this artifact")
        return artifact

    def _read(self, actor, artifact_id, version=None):
        artifact = self._artifact(actor, artifact_id, version=version)
        version = visible_version(artifact, actor, self.state["clock"], version)
        ref = {"artifact_id": artifact_id, "version_id": version}
        if ref not in self._reads:
            self._reads.append(ref)
        knowledge = self.state["knowledge"][actor]["read_artifacts"]
        if ref not in knowledge:
            knowledge.append(ref)
        return self.store.content(artifact, version)

    def _dependencies(self, actor, artifact, dependencies):
        if dependencies is None:
            return copy.deepcopy(artifact["versions"][artifact["current_version"]]["derived_from"])
        if not isinstance(dependencies, list) or len(dependencies) > 30:
            raise WorldError("dependencies must be a list of at most 30 version references")
        seen = set()
        for ref in dependencies:
            if not isinstance(ref, dict) or set(ref) != {"artifact_id", "version_id"}:
                raise WorldError("Each dependency needs artifact_id and version_id")
            if ref["artifact_id"] == artifact["artifact_id"] or ref["artifact_id"] in seen:
                raise WorldError("Duplicate or self dependency")
            seen.add(ref["artifact_id"])
            self._artifact(actor, ref["artifact_id"], version=ref["version_id"])
        return dependencies

    def _put(self, actor, artifact, data, dependencies):
        before = artifact["current_version"]
        version = self.store.put(self.state, artifact["artifact_id"], data, actor, dependencies)
        self._writes.append(
            {
                "artifact_id": artifact["artifact_id"],
                "before": before,
                "after": version["version_id"],
            }
        )
        for item in current_work_items(self.state):
            if item["status"] == Status.OPEN and artifact["artifact_id"] in item["deliverables"]:
                item["status"] = Status.IN_PROGRESS
            if (
                item["status"] == Status.IN_REVIEW
                and artifact["artifact_id"] in item["deliverables"]
            ):
                item["submissions"][-1]["invalidated"] = True
                item["status"] = Status.IN_PROGRESS
        return {
            "artifact_id": artifact["artifact_id"],
            "version_id": version["version_id"],
            "derived_from": version["derived_from"],
        }

    def _message(self, sender, recipients, subject, body, attachments=None):
        message = {
            "message_id": f"mail-{len(self.state['messages']) + 1}",
            "sender": sender,
            "recipients": recipients,
            "at": self.state["clock"],
            "subject": subject,
            "body": body,
            "attachments": attachments or [],
        }
        self.state["messages"].append(message)
        return message

    def _event(self, kind, payload, delay=1):
        event = {
            "event_id": uuid.uuid4().hex,
            "kind": kind,
            "at": self.state["clock"] + delay,
            "payload": payload,
        }
        self.state["events"].append(event)
        return event

    def _can_view_work(self, actor, item):
        return actor == item["owner_role"] or authority(
            self.state,
            actor,
            "view_work",
            "work",
            work_node=item.get("node_id", item["work_item_id"]),
        )

    def _item(self, actor, work_item_id):
        item = self.state["work_items"].get(work_item_id)
        if item is None or not self._can_view_work(actor, item):
            raise WorldError("Work item unavailable to this role")
        return item

    def _public_item(self, item):
        result = project_fields(copy.deepcopy(item), {"acceptance_spec_ref"})
        result["is_current"] = current_id(self.state, item["work_item_id"]) == item["work_item_id"]
        result["blockers"] = [
            copy.deepcopy(self.state.get("blockers", {})[bid])
            for bid in item.get("blocker_ids", [])
        ]
        result["dependency_readiness"] = {
            "ready": dependencies_ready(self.state, item),
            "current_predecessors": [current_id(self.state, dep) for dep in item["dependencies"]],
        }
        result["conditions"] = [
            copy.deepcopy(condition)
            for condition in self.state.get("condition_specs", {}).values()
            if condition["work_item_id"] == item["work_item_id"]
        ]
        # Conditions expose public requirement/reference metadata, never evidence contents.
        # Submissions are business records; evaluator state is never embedded here.
        return result

    def observe(self, actor="analyst"):
        with self.store.lock():
            self.state = self.store.load()
            role = self._role(actor)
            return {
                "role": role,
                "logical_time": self.state["clock"],
                "project": copy.deepcopy(self.state["project"]),
                "work_items": [
                    self._public_item(item)
                    for item in self.state["work_items"].values()
                    if self._can_view_work(actor, item)
                ],
                "unread_message_count": sum(
                    actor in msg["recipients"]
                    and msg["at"] <= self.state["clock"]
                    and msg["message_id"] not in self.state["knowledge"][actor]["read_messages"]
                    for msg in self.state["messages"]
                ),
                "complete": self._complete(),
                "terminal_reason": "blocked_unavailable" if blocked_terminal(self.state) else None,
            }

    def _complete(self):
        return is_complete(self.state)

    def act(self, actor, action, arguments=None, request_key=None):
        started = time.monotonic()
        arguments = {} if arguments is None else arguments
        with self.store.lock():
            self.state = self.store.load()
            self._role(actor)
            if request_key:
                for old in self.state["interactions"]:
                    if old.get("request_key") == request_key and old["actor_id"] == actor:
                        self._drain_events()
                        self.store.save(self.state)
                        return {
                            **old["output"],
                            "action_id": old["action_id"],
                            "logical_time": old["logical_time"],
                        }
            self.store.recover(self.state)
            before = copy.deepcopy(self.state)
            self._reads, self._writes = [], []
            try:
                if not isinstance(arguments, dict):
                    raise WorldError("Tool arguments must be an object")
                # JSON normalization rejects NaN and nonserializable objects BEFORE mutation.
                json_bytes(arguments)
                handler = (
                    getattr(self, f"_tool_{action}", None) if isinstance(action, str) else None
                )
                if handler is None:
                    raise WorldError("Unknown tool")
                result, transition = execute_transition(
                    self.state,
                    self._action_frame(actor, action, arguments),
                    lambda: handler(actor, **arguments),
                    self._derive,
                )
                output = {"ok": True, "result": project_fields(result, {"acceptance_spec_ref"})}
                json_bytes(output)
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as exc:
                self.state = before
                self.store.recover(self.state)
                self._reads, self._writes = [], []
                transition = {
                    "contract": action,
                    "rolled_back": True,
                    "direct_changes": [],
                    "derived_changes": [],
                }
                output = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
                try:
                    json_bytes(arguments)
                except (ValueError, TypeError):
                    arguments = {"invalid_input": repr(arguments)[:2000]}
            self.state["clock"] += 1
            record = asdict(
                InteractionRecord(
                    action_id=f"action-{len(self.state['interactions']) + 1}",
                    actor_id=actor,
                    action=action,
                    inputs=arguments,
                    output=copy.deepcopy(output),
                    logical_time=self.state["clock"],
                    reads=self._reads,
                    writes=self._writes,
                    wall_seconds=time.monotonic() - started,
                )
            )
            record["request_key"] = request_key
            record["transition"] = transition
            self.state["interactions"].append(record)
            schedule_interruptions(self, record)
            # Persist the candidate action first. Events use their own explicit actor records.
            self.store.save(self.state)
            self._drain_events()
            self.store.save(self.state)
            return {**output, "action_id": record["action_id"], "logical_time": self.state["clock"]}

    def _tool_list_files(self, actor):
        result = []
        for aid, artifact in self.state["artifacts"].items():
            version = visible_version(artifact, actor, self.state["clock"])
            if version:
                result.append(
                    {
                        "artifact_id": aid,
                        "filename": artifact["filename"],
                        "version_id": version,
                        "is_current_version": version == artifact["current_version"],
                        "possibly_stale": artifact["possibly_stale"]
                        or version != artifact["current_version"],
                        "freshness": artifact.get("freshness", "unknown")
                        if version == artifact["current_version"]
                        else "stale",
                        "data_freshness": artifact.get("data_freshness"),
                        "basis_applicability": artifact.get("basis_applicability"),
                    }
                )
        return result

    def _tool_read_file(self, actor, artifact_id, version_id=None):
        artifact = self._artifact(actor, artifact_id, version=version_id)
        if artifact["filename"].endswith(".xlsx"):
            raise WorldError("Use sheet_read for XLSX content")
        return {
            "artifact_id": artifact_id,
            "version_id": visible_version(artifact, actor, self.state["clock"], version_id),
            "content": self._read(actor, artifact_id, version_id).decode(),
        }

    def _tool_search(self, actor, query):
        if not isinstance(query, str) or not query.strip():
            raise WorldError("A nonempty query is required")
        results = []
        for aid, artifact in self.state["artifacts"].items():
            version = visible_version(artifact, actor, self.state["clock"])
            if version is None:
                continue
            text = artifact["filename"]
            if not text.endswith(".xlsx"):
                text += "\n" + self.store.content(artifact, version).decode()
            position = text.casefold().find(query.casefold())
            if position >= 0:
                self._read(actor, aid)
                results.append(
                    {
                        "artifact_id": aid,
                        "version_id": version,
                        "snippet": text[max(0, position - 80) : position + 240],
                    }
                )
        for msg in self.state["messages"]:
            if actor not in msg["recipients"] and actor != msg["sender"]:
                continue
            text = json.dumps(msg["body"], ensure_ascii=False) + msg["subject"]
            if query.casefold() in text.casefold():
                results.append(
                    {
                        "message_id": msg["message_id"],
                        "subject": msg["subject"],
                        "snippet": text[:240],
                    }
                )
        return results[:30]

    def _tool_file_history(self, actor, artifact_id):
        artifact = self._artifact(actor, artifact_id)
        return [
            copy.deepcopy(v)
            for v in artifact["versions"].values()
            if visible_version(artifact, actor, self.state["clock"], v["version_id"])
        ]

    def _tool_write_file(self, actor, artifact_id, content, dependencies=None):
        artifact = self._artifact(actor, artifact_id, write=True)
        if artifact["filename"].endswith(".xlsx"):
            raise WorldError("Use sheet_update for XLSX edits")
        if not isinstance(content, str) or len(content.encode()) > 250_000:
            raise WorldError("Content must be text up to 250KB")
        deps = self._dependencies(actor, artifact, dependencies)
        return self._put(actor, artifact, content.encode(), deps)

    def _tool_sheet_read(self, actor, artifact_id="model", sheet=None, version_id=None):
        artifact = self._artifact(actor, artifact_id, version=version_id)
        if not artifact["filename"].endswith(".xlsx"):
            raise WorldError("Artifact is not a workbook")
        return {
            "artifact_id": artifact_id,
            "version_id": visible_version(artifact, actor, self.state["clock"], version_id),
            "sheets": Spreadsheet(self._read(actor, artifact_id, version_id)).read(sheet),
        }

    def _tool_sheet_update(self, actor, cells, artifact_id="model", dependencies=None):
        artifact = self._artifact(actor, artifact_id, write=True)
        if not isinstance(cells, dict) or not cells:
            raise WorldError("cells must be a nonempty object")
        deps = self._dependencies(actor, artifact, dependencies)
        sheet = Spreadsheet(self._read(actor, artifact_id))
        sheet.update(cells)
        return self._put(actor, artifact, sheet.serialize(), deps)

    def _tool_sheet_recalculate(self, actor, artifact_id="model"):
        artifact = self._artifact(actor, artifact_id, write=True)
        sheet = Spreadsheet(self._read(actor, artifact_id))
        return self._put(
            actor,
            artifact,
            sheet.serialize(),
            artifact["versions"][artifact["current_version"]]["derived_from"],
        )

    def _tool_calculate(self, actor, expression, variables=None):
        return {"value": arithmetic(expression, variables)}

    def _tool_mail_list(self, actor):
        return [
            {k: v for k, v in msg.items() if k not in ("body", "attachments")}
            for msg in self.state["messages"]
            if msg["at"] <= self.state["clock"]
            and (actor in msg["recipients"] or actor == msg["sender"])
        ]

    def _tool_mail_read(self, actor, message_id):
        for msg in self.state["messages"]:
            if (
                msg["message_id"] == message_id
                and msg["at"] <= self.state["clock"]
                and (actor in msg["recipients"] or actor == msg["sender"])
            ):
                read = self.state["knowledge"][actor]["read_messages"]
                if message_id not in read:
                    read.append(message_id)
                return copy.deepcopy(msg)
        raise WorldError("Message unavailable to this role")

    def _tool_mail_send(
        self, actor, to, body, topic="general", attachments=None, work_item_id=None, blocker_id=None
    ):
        self._role(to)
        if not isinstance(body, str) or len(body) > 10000:
            raise WorldError("Message body must be text up to 10000 characters")
        for ref in attachments or []:
            artifact = self._artifact(actor, ref["artifact_id"], version=ref["version_id"])
            if not visible_version(artifact, to, self.state["clock"], ref["version_id"]):
                raise WorldError("Recipient lacks attachment access")
        item = self._item(actor, work_item_id) if work_item_id else None
        if (
            supports_request(self.state, topic)
            and actor == position(self.state, "worker")
            and item is None
        ):
            candidates = [
                w
                for w in current_work_items(self.state)
                if w["status"] not in ("accepted", "waiting_dependencies")
            ]
            if len(candidates) != 1:
                raise WorldError("Specify work_item_id for this scoped request")
            item = candidates[0]
            work_item_id = item["work_item_id"]
        if item and (
            item["status"] in ("superseded", "cancelled")
            or current_id(self.state, work_item_id) != work_item_id
        ):
            raise WorldError("This request must refer to current work")
        msg = self._message(actor, [to], topic, body, attachments)
        msg.update(work_item_id=work_item_id, topic=topic)
        if item and actor == item["owner_role"] and supports_request(self.state, topic):
            register_request(self.state, item, actor, to, topic, msg, blocker_id)
            self._event("staff_reply", {"request_id": msg["message_id"]}, 2)
        return {"message_id": msg["message_id"], "work_item_id": work_item_id}

    def _deliver_reply(self, payload):
        return deliver_reply(self, payload)

    def _tool_work_list(self, actor):
        return [
            self._public_item(item)
            for item in self.state["work_items"].values()
            if self._can_view_work(actor, item)
        ]

    def _tool_block_work(
        self,
        actor,
        work_item_id,
        reason,
        kind="evidence",
        requested_role=None,
        required_scope_version=None,
        request_id=None,
    ):
        requested_role = requested_role or position(self.state, "coordinator")
        item = self._item(actor, work_item_id)
        if item["owner_role"] != actor:
            raise WorldError("Only the work owner can declare a blocker")
        if kind == "scope" and required_scope_version is None:
            required_scope_version = item.get(
                "basis_requirement_version", item["requirement_version"]
            )
        if kind == "scope" and required_scope_version != item.get(
            "basis_requirement_version", item["requirement_version"]
        ):
            raise WorldError(
                "Scope blocker must refer to this work's analytical requirement version"
            )
        candidates = [
            r
            for r in self.state.get("requests", {}).values()
            if r["work_item_id"] == work_item_id
            and r["topic"] == kind
            and r["requested_role"] == requested_role
            and r["requirement_version"] == item["requirement_version"]
            and r["status"] == "unavailable"
        ]
        if request_id is None and len(candidates) == 1:
            request_id = candidates[0]["request_id"]
        request = self.state.get("requests", {}).get(request_id) if request_id else None
        if request_id and (
            request is None
            or request["requirement_version"] != item["requirement_version"]
            or (kind == "scope" and request["basis_requirement_version"] != required_scope_version)
        ):
            raise WorldError("Blocker request is not applicable to this requirement")
        blocker = create_blocker(
            self.state,
            item,
            kind,
            requested_role,
            required_scope_version,
            reason,
            request_id=request_id,
        )
        if request and request["status"] == "unavailable":
            mark_unavailable(
                self.state,
                blocker["blocker_id"],
                "对应请求已明确报告资料不可得",
                {"message_id": request["reply_message_id"], "request_id": request_id},
            )
            blocker = copy.deepcopy(self.state["blockers"][blocker["blocker_id"]])
        item["blocker"] = reason
        return {
            "blocker_id": blocker["blocker_id"],
            "blocker": blocker,
            "work_item": self._public_item(item),
        }

    def _tool_restore_information(
        self,
        actor,
        topic,
        provider,
        reference,
        condition_ids,
        opportunity_id=None,
        reason="Information became available",
    ):
        return restore_information(
            self,
            actor,
            topic,
            provider,
            reference,
            condition_ids,
            opportunity_id=opportunity_id,
            reason=reason,
        )

    def _tool_revise_requirements(self, actor, work_item_ids, growth_delta, reason):
        require_authority(self.state, actor, "revise_requirement", "analytical_assumptions")
        return {
            "replacements": revise_basis(self, work_item_ids, growth_delta, reason, actor=actor)
        }

    def _tool_withdraw(self, actor, work_item_id, submission_id, reason):
        self._item(actor, work_item_id)
        return withdraw_submission(self.state, actor, work_item_id, submission_id, reason)

    def _tool_submit(self, actor, work_item_id, answer=None):
        item = self._item(actor, work_item_id)
        if item["owner_role"] != actor or item["status"] not in (
            Status.OPEN,
            Status.IN_PROGRESS,
            Status.REVISION_REQUIRED,
        ):
            raise WorldError("Work is not open for submission by this actor")
        if "answer" in item["deliverables"] and answer is None:
            raise WorldError("This task requires an answer")
        versions = {
            aid: self._artifact(actor, aid)["current_version"]
            for aid in item["deliverables"]
            if aid != "answer"
        }
        submission = submit_work(
            self.state,
            actor,
            work_item_id,
            versions,
            answer=answer,
            context_versions={
                aid: visible_version(a, actor, self.state["clock"])
                for aid, a in self.state["artifacts"].items()
                if visible_version(a, actor, self.state["clock"])
            },
            extensions={"required_basis": copy.deepcopy(item.get("required_basis"))},
        )
        self._event(
            "review",
            {"work_item_id": work_item_id, "submission_id": submission["submission_id"]},
            2,
        )
        return copy.deepcopy(submission)

    def _tool_approve(self, actor, work_item_id, submission_id):
        self._item(actor, work_item_id)
        approve_submission(self.state, actor, work_item_id, submission_id)
        on_accept(self)
        return {
            "work_item_id": work_item_id,
            "submission_id": submission_id,
            "status": self.state["work_items"][work_item_id]["status"],
        }

    def _tool_wait(self, actor, ticks=1):
        if type(ticks) is not int or not 1 <= ticks <= 100:
            raise WorldError("ticks must be an integer from 1 to 100")
        self.state["clock"] += ticks - 1
        return {"advanced_ticks": ticks}

    def _staff_record(self, actor, action, inputs, result, reads=None, writes=None):
        self.state["interactions"].append(
            asdict(
                InteractionRecord(
                    action_id=f"action-{len(self.state['interactions']) + 1}",
                    actor_id=actor,
                    action=action,
                    inputs=inputs,
                    output={"ok": True, "result": result},
                    logical_time=self.state["clock"],
                    reads=reads or [],
                    writes=writes or [],
                    wall_seconds=0,
                )
            )
        )

    def _drain_events(self):
        due = ordered_due_events(self.state["events"], self.state["clock"])
        for event in due:
            if event not in self.state["events"]:
                continue
            self.state["events"].remove(event)
            payload = event["payload"]
            if event["kind"] == "staff_reply":
                request = self.state["requests"][payload["request_id"]]
                _, receipt = execute_transition(
                    self.state,
                    reply_frame(self.state, request),
                    lambda: self._deliver_reply(payload),
                    self._derive,
                )
                event["transition"] = receipt
            elif event["kind"] == "information_arrival":
                actor = payload["actor"]
                arguments = {key: value for key, value in payload.items() if key != "actor"}
                result, receipt = execute_transition(
                    self.state,
                    self._action_frame(actor, "restore_information", arguments),
                    lambda: self._tool_restore_information(actor, **arguments),
                    self._derive,
                )
                event["transition"] = receipt
                self._staff_record(actor, "restore_information", arguments, result)
            elif event["kind"] == "manager_reply":
                # Archived v0.2 events have no scope binding; deliver historical text only.
                body = json.loads(self._read("manager", "scope"))
                self._message("manager", ["analyst"], "历史未绑定回复", body)
            elif event["kind"] == "review":
                reviewer = position(self.state, "reviewer")
                item = self.state["work_items"][payload["work_item_id"]]
                sub = next(
                    s for s in item["submissions"] if s["submission_id"] == payload["submission_id"]
                )
                if sub["invalidated"] or item["status"] != Status.IN_REVIEW:
                    self.state["event_history"].append({**event, "outcome": "superseded"})
                    continue
                self._reads = []
                defects = review_submission(
                    lambda aid, version: self._read(reviewer, aid, version),
                    sub,
                    item,
                    self.state.get("layout"),
                )
                if not dependencies_ready(self.state, item):
                    defects.append("当前前置工作尚未获批准；请在前置义务就绪后重新提交。")
                if "basis" in self.state["artifacts"] and item["deliverables"] != ["answer"]:
                    basis = requirement_basis(self.store, self.state, item)
                    model_version = sub["artifact_versions"].get(
                        "model", sub["context_versions"]["model"]
                    )
                    deps = self.state["artifacts"]["model"]["versions"][model_version][
                        "derived_from"
                    ]
                    if basis is None or item.get("required_basis") not in deps:
                        defects.append(
                            "工作模型未绑定适用于当前工作/需求版本的批准依据，请核验 basis 凭据与实际采用版本。"
                        )
                if defects:
                    sub["review"] = {
                        "decision": "revision_required",
                        "actor_id": reviewer,
                        "at": self.state["clock"],
                        "defects": defects,
                    }
                    item["status"] = Status.REVISION_REQUIRED
                    result = sub["review"]
                else:
                    result = self._tool_approve(
                        reviewer, item["work_item_id"], sub["submission_id"]
                    )
                self._message(
                    reviewer,
                    [item["owner_role"]],
                    "实际交付审阅",
                    {
                        "work_item_id": item["work_item_id"],
                        "submission_id": sub["submission_id"],
                        "decision": item["status"],
                        "defects": defects,
                    },
                    [
                        {"artifact_id": a, "version_id": v}
                        for a, v in sub["artifact_versions"].items()
                    ],
                )
                self._staff_record(reviewer, "review", payload, result, self._reads)
            elif event["kind"] == "lifecycle_change":
                from .lifecycle import apply_lifecycle_event

                apply_lifecycle_event(self, event)
            elif event["kind"] in ("apply_rule", "requirement_change"):
                from .events import apply_rule

                apply_rule(self, event)
            self.state["event_history"].append({**event, "outcome": "applied"})

    def snapshot(self, destination):
        destination = Path(destination).resolve()
        if destination == self.store.root or self.store.root in destination.parents:
            raise WorldError("Snapshot must be outside the live world")
        with self.store.lock():
            if destination.exists():
                raise WorldError("Snapshot destination already exists")
            state = self.store.load()
            shutil.copytree(
                self.store.root, destination, ignore=shutil.ignore_patterns("world.lock")
            )
            metadata = WorldSnapshot(
                SCHEMA_VERSION,
                state["instance_id"],
                state["branch_id"],
                state["clock"],
                digest(json_bytes(state)),
            )
            atomic_write(destination / "snapshot.json", json_bytes(asdict(metadata)))
        return destination

    @classmethod
    def restore(cls, snapshot, destination, branch=True):
        snapshot, destination = Path(snapshot).resolve(), Path(destination).resolve()
        metadata = read_json(snapshot / "snapshot.json")
        state = read_json(snapshot / "control" / "state.json")
        if digest(json_bytes(state)) != metadata["state_sha256"]:
            raise WorldError("Snapshot checksum mismatch")
        if destination.exists() or snapshot == destination or snapshot in destination.parents:
            raise WorldError("Restore requires a new destination outside the snapshot")
        shutil.copytree(
            snapshot, destination, ignore=shutil.ignore_patterns("world.lock", "snapshot.json")
        )
        if branch:
            state["parent_branch_id"] = state["branch_id"]
            state["branch_id"] = uuid.uuid4().hex
            state["branch_start_action"] = len(state["interactions"])
            Store(destination).save(state)
        return cls(destination)


class WorkerSession:
    """Trusted runner binds identity once; tool arguments cannot switch actor."""

    def __init__(self, world: World, actor_id: str):
        self._world = world
        self.actor_id = actor_id

    def observe(self):
        return self._world.observe(self.actor_id)

    def call(self, action: str, **arguments):
        return self._world.act(self.actor_id, action, arguments)
