"""A tiny publication configuration for checking kernel reuse, not a benchmark.

Only explicit fields, exact source references and required phrases are evaluated.
Neither the staff review nor the independent check claims editorial expertise.
"""

import copy
import json
import uuid
from pathlib import Path

from ..adapters.action_scopes import projections, tool_frame
from ..core.conditions import apply_response
from ..core.references import ApplicabilityContext
from ..core.rules import confirm_credential, registered_applicability
from ..core.transitions import ActionFrame, execute_transition, ordered_due_events
from ..core.types import CheckStatus, Credential
from ..core.visibility import grant_version
from ..core.work import approve_submission, current_id, current_work_items, revise_requirement
from ..freshness import refresh_freshness
from ..kernel import World
from ..policies.organization import position, require_authority
from ..schema import SCHEMA_VERSION
from ..storage import Store, atomic_write, json_bytes

WORK_ID = "publish-note"
SOURCE_REF = {"artifact_id": "source_note", "version_id": "v1"}


def publication_context(state, item):
    return ApplicabilityContext(
        project_id=state["project"]["project_id"],
        work_id=item["work_item_id"],
        work_node=item["node_id"],
        requirement_dimension="release_edition",
        requirement_version=item["requirement_version"],
        period=None,
        purpose="publication",
        at=state["clock"],
    )


def _confirm_policy(store, state, actor, required_phrases, requirement_version, public):
    require_authority(state, actor, "confirm", "release_edition", WORK_ID)
    if (
        not isinstance(required_phrases, list)
        or not required_phrases
        or not all(isinstance(text, str) and text.strip() for text in required_phrases)
        or type(requirement_version) is not int
        or requirement_version < 1
    ):
        raise ValueError(
            "Policy needs nonempty required phrases and a positive requirement version"
        )
    version = store.put(
        state,
        "editorial_policy",
        json_bytes(
            {
                "required_phrases": required_phrases,
                "source_ref": SOURCE_REF,
                "requirement_version": requirement_version,
            }
        ),
        actor,
    )
    reference = {"artifact_id": "editorial_policy", "version_id": version["version_id"]}
    credential = Credential(
        reference=reference,
        project_id=state["project"]["project_id"],
        requirement_dimension="release_edition",
        requirement_version=requirement_version,
        work_nodes=(WORK_ID,),
        period=None,
        purpose="publication",
        effective_at=state["clock"],
        confirmed_by=actor,
        attestation_ref=f"editorial-confirmation-{version['version_id']}",
    )
    confirm_credential(state, actor, reference, credential)
    if public:
        grant_version(
            state,
            "editorial_policy",
            version["version_id"],
            position(state, "worker"),
            credential.attestation_ref,
        )
    return reference


def _derive_publication(state):
    refresh_freshness(state)
    state["publication_applicability"] = {
        item["work_item_id"]: [
            registered_applicability(state, ref, publication_context(state, item)).to_dict()
            for ref in item["required_credentials"]
        ]
        for item in state["work_items"].values()
    }


def compile_publication(destination, actors=None):
    """Create one fixed micro-world; actor names are pure organization config."""
    actors = {"author": "author", "editor": "editor", **(actors or {})}
    if (
        set(actors) != {"author", "editor"}
        or len(set(actors.values())) != 2
        or not all(isinstance(value, str) and value for value in actors.values())
    ):
        raise ValueError("Provide distinct author and editor identifiers")
    root = Path(destination).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Publication destination must be empty")
    store = Store(root)
    store.control.mkdir(parents=True, exist_ok=True)
    store.workspace.mkdir(parents=True, exist_ok=True)
    author, editor = actors["author"], actors["editor"]
    state = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": "publication-micro-v0.1",
        "instance_id": uuid.uuid4().hex,
        "branch_id": uuid.uuid4().hex,
        "project": {
            "project_id": "publication-micro",
            "template_id": "publication-micro",
            "business_object": "source_based_notice",
            "scope": "finite_fields_only",
        },
        "roles": [
            {"role_id": author, "trainable": True, "policy": "worker"},
            {"role_id": editor, "trainable": False, "policy": "finite_field_review"},
        ],
        "organization": {
            "positions": {"worker": author, "coordinator": editor, "reviewer": editor},
            "grants": [
                {"actor_id": editor, "power": power, "subject": subject, "work_nodes": [WORK_ID]}
                for power, subject in (
                    ("confirm", "release_edition"),
                    ("revise_requirement", "*"),
                    ("approve", "deliverable"),
                    ("view_work", "*"),
                )
            ],
        },
        "clock": 0,
        "artifacts": {},
        "artifact_contracts": {},
        "work_items": {},
        "work_replacements": {},
        "messages": [],
        "requests": {},
        "condition_specs": {},
        "condition_responses": {},
        "blockers": {},
        "events": [],
        "event_history": [],
        "interactions": [],
        "attestations": {},
        "access_grants": [],
        "requirement_events": [],
        "lifecycle_events": [],
        "future_opportunities": [],
        "knowledge": {
            actor: {"read_artifacts": [], "read_messages": []} for actor in actors.values()
        },
    }
    for aid, readers, writers, kind in (
        ("source_note", [author, editor], [], "fact"),
        ("editorial_policy", [editor], [], "credential"),
        ("draft", [author, editor], [author], "claim"),
    ):
        state["artifacts"][aid] = {
            "artifact_id": aid,
            "filename": f"{aid}.json",
            "readers": readers,
            "writers": writers,
            "versions": {},
            "current_version": None,
            "version_readers": {},
            "kind": kind,
            "materialization": "workspace" if author in readers else "private",
        }
    store.put(
        state,
        "source_note",
        json_bytes(
            {
                "record_id": "notice-source-1",
                "status": "READY",
                "description": "Synthetic station readiness record",
            }
        ),
        editor,
    )
    policy_ref = _confirm_policy(
        store, state, editor, ["READY", "Synthetic demonstration"], 1, True
    )
    store.put(state, "draft", json_bytes({"title": "", "body": "", "source_ref": None}), author)
    state["work_items"][WORK_ID] = {
        "work_item_id": WORK_ID,
        "node_id": WORK_ID,
        "project_id": "publication-micro",
        "requirement_version": 1,
        "requirement_dimension": "release_edition",
        "purpose": "publication",
        "owner_role": author,
        "status": "open",
        "goal": "Write the source-based publication note",
        "visible_requirements": [
            "Provide nonempty title and body; cite source_note/v1.",
            "Adopt the applicable editorial_policy and include its exact required phrases.",
        ],
        "inputs": ["source_note", "editorial_policy"],
        "deliverables": ["draft"],
        "dependencies": [],
        "required_credentials": [policy_ref],
        "submissions": [],
        "blocker_ids": [],
        "blocker": None,
        "acceptance_spec_ref": "publication-fields-v1",
    }
    _derive_publication(state)
    store.save(state)
    atomic_write(
        store.control / "spec.json",
        json_bytes(
            {
                "schema_version": SCHEMA_VERSION,
                "template_id": "publication-micro",
                "actors": actors,
                "initial_policy": {
                    "required_phrases": ["READY", "Synthetic demonstration"],
                    "requirement_version": 1,
                },
                "evaluation_scope": "finite fields, references and phrases; not professional editorial quality",
            }
        ),
    )
    return root


class PublicationWorld(World):
    """Same file tools and action transaction boundary, configured publication policy."""

    def session(self, actor_id=None):
        return super().session(actor_id or position(self.state, "worker"))

    def observe(self, actor=None):
        return super().observe(actor or position(self.state, "worker"))

    def _complete(self):
        current = current_work_items(self.state)
        return bool(current) and all(item["status"] == "accepted" for item in current)

    def _derive(self, state):
        _derive_publication(state)

    def _action_frame(self, actor, action, arguments):
        derived = projections(self.state) + (("publication_applicability",),)
        if action in {
            "list_files",
            "read_file",
            "search",
            "file_history",
            "write_file",
            "submit",
            "withdraw",
            "approve",
            "wait",
            "mail_list",
            "mail_read",
        }:
            frame = tool_frame(self.state, actor, action, arguments)
            return ActionFrame(frame.name, frame.paths, derived)
        paths = {
            "confirm": [("artifacts", "editorial_policy"), ("attestations",), ("access_grants",)],
            "revise": [
                ("work_items",),
                ("work_replacements",),
                ("requirement_events",),
                ("blockers",),
                ("condition_specs",),
            ],
            "request": [
                ("messages",),
                ("requests",),
                ("condition_specs",),
                ("blockers",),
                ("work_items", arguments.get("work_item_id", "")),
            ],
            "reply": [
                ("messages",),
                ("requests",),
                ("condition_specs",),
                ("blockers",),
                ("work_items",),
                ("condition_responses",),
                ("access_grants",),
                ("artifacts", "editorial_policy", "version_readers"),
            ],
        }
        if action not in paths:
            raise ValueError("Tool is not configured for the publication micro-world")
        if action == "reply":
            request_id = arguments.get("request_id", "")
            request = self.state["requests"].get(request_id, {})
            condition_id = request.get("condition_id", "")
            condition = self.state["condition_specs"].get(condition_id, {})
            version = arguments.get("version_id") or request.get("policy_ref", {}).get(
                "version_id", ""
            )
            paths[action] = [
                ("messages",),
                ("requests", request_id),
                ("condition_specs", condition_id),
                ("blockers", condition.get("blocker_id", "")),
                ("work_items", request.get("work_item_id", "")),
                ("condition_responses",),
                ("access_grants",),
                ("artifacts", "editorial_policy", "version_readers", version),
            ]
        return ActionFrame(action, tuple(paths[action]), derived)

    def _tool_confirm(self, actor, required_phrases, requirement_version, public=False):
        reference = _confirm_policy(
            self.store, self.state, actor, required_phrases, requirement_version, public
        )
        return {"policy_ref": reference}

    def _tool_revise(self, actor, work_item_id, policy_version, reason):
        item = self._item(actor, work_item_id)
        if current_id(self.state, work_item_id) != work_item_id:
            raise ValueError("Revise the current publication obligation")
        reference = {"artifact_id": "editorial_policy", "version_id": policy_version}
        next_item = {**item, "requirement_version": item["requirement_version"] + 1}
        if (
            registered_applicability(
                self.state, reference, publication_context(self.state, next_item)
            ).status
            != CheckStatus.PASS
        ):
            raise ValueError("New publication policy is not applicable to the next requirement")
        return {
            "replacements": revise_requirement(
                self.state,
                [work_item_id],
                {"required_credentials": [reference], "requirement_dimension": "release_edition"},
                actor,
                reason,
            )
        }

    def _tool_request(self, actor, work_item_id):
        item = self._item(actor, work_item_id)
        if (
            actor != item["owner_role"]
            or current_id(self.state, work_item_id) != work_item_id
            or item["status"] not in {"open", "in_progress", "revision_required"}
        ):
            raise ValueError("Only the current available work owner may request its policy")
        editor = position(self.state, "coordinator")
        message = self._message(
            actor, [editor], "Request editorial policy", {"work_item_id": work_item_id}
        )
        message["work_item_id"] = work_item_id
        request_id = message["message_id"]
        condition_id = f"policy-condition-{len(self.state['condition_specs']) + 1}"
        blocker_id = f"policy-blocker-{len(self.state['blockers']) + 1}"
        reference = copy.deepcopy(item["required_credentials"][0])
        self.state["requests"][request_id] = {
            "request_id": request_id,
            "work_item_id": work_item_id,
            "requirement_version": item["requirement_version"],
            "requested_role": editor,
            "requester": actor,
            "policy_ref": reference,
            "condition_id": condition_id,
            "status": "pending",
        }
        self.state["condition_specs"][condition_id] = {
            "condition_id": condition_id,
            "blocker_id": blocker_id,
            "work_item_id": work_item_id,
            "requirement_version": item["requirement_version"],
            "request_id": request_id,
            "providers": [editor],
            "unavailable_providers": [],
            "expected_version": item["requirement_version"],
            "purpose": "publication",
            "subject": "release_edition",
            "required_power": "confirm",
            "evidence_spec": {"kind": "credential", "reference": reference},
            "context": publication_context(self.state, item).to_dict(),
            "status": "open",
            "history": [{"at": self.state["clock"], "status": "open"}],
        }
        self.state["blockers"][blocker_id] = {
            "blocker_id": blocker_id,
            "condition_id": condition_id,
            "work_item_id": work_item_id,
            "status": "open",
            "history": [{"at": self.state["clock"], "status": "open"}],
        }
        item["blocker_ids"].append(blocker_id)
        item["status"] = "blocked"
        return {"request_id": request_id, "condition_id": condition_id}

    def _tool_reply(self, actor, request_id, version_id=None, status="delivered"):
        request = self.state["requests"].get(request_id)
        if (
            request is None
            or actor != request["requested_role"]
            or status not in {"delivered", "unavailable"}
        ):
            raise ValueError("Reply requires the requested provider and a valid response status")
        if request.get("reply_message_id"):
            # Retrying delivery of the same request is idempotent. New evidence
            # requires an explicitly new request, not rewriting a past response.
            return copy.deepcopy(request["delivered_result"])
        version_id = version_id or request["policy_ref"]["version_id"]
        reference = {"artifact_id": "editorial_policy", "version_id": version_id}
        if status == "delivered":
            self._artifact(actor, "editorial_policy", version=version_id)
            grant_version(
                self.state, "editorial_policy", version_id, request["requester"], request_id
            )
        message = self._message(
            actor,
            [request["requester"]],
            "Editorial policy response",
            {"request_id": request_id, "status": status},
            [reference] if status == "delivered" else [],
        )
        response = {
            "response_id": message["message_id"],
            "request_id": request_id,
            "work_item_id": request["work_item_id"],
            "requirement_version": request["requirement_version"],
            "condition_version": request["requirement_version"],
            "purpose": "publication",
            "responder": actor,
            "status": status,
            "reference": reference if status == "delivered" else None,
        }
        result = apply_response(self.state, response)
        delivered = {"response": response, "satisfaction": result}
        request.update(
            status=status,
            reply_message_id=message["message_id"],
            delivered_result=copy.deepcopy(delivered),
        )
        return delivered

    def _tool_approve(self, actor, work_item_id, submission_id):
        self._item(actor, work_item_id)
        approve_submission(self.state, actor, work_item_id, submission_id)
        return {"work_item_id": work_item_id, "submission_id": submission_id, "status": "accepted"}

    def _drain_events(self):
        for event in ordered_due_events(self.state["events"], self.state["clock"]):
            self.state["events"].remove(event)
            if event["kind"] != "review":
                raise ValueError("Unknown publication event")
            item = self.state["work_items"][event["payload"]["work_item_id"]]
            submission = next(
                sub
                for sub in item["submissions"]
                if sub["submission_id"] == event["payload"]["submission_id"]
            )
            if submission["invalidated"] or item["status"] != "in_review":
                self.state["event_history"].append({**event, "outcome": "superseded"})
                continue
            editor = position(self.state, "reviewer")
            frame = ActionFrame(
                "publication_review",
                (
                    ("work_items", item["work_item_id"]),
                    ("artifacts", "draft"),
                    ("knowledge", editor),
                    ("messages",),
                    ("interactions",),
                ),
                projections(self.state) + (("publication_applicability",),),
            )

            def review():
                self._reads = []
                version = submission["artifact_versions"]["draft"]
                try:
                    content = json.loads(self._read(editor, "draft", version))
                except (ValueError, UnicodeError):
                    content = None
                defects = []
                if not isinstance(content, dict) or any(
                    not isinstance(content.get(key), str) or not content[key].strip()
                    for key in ("title", "body")
                ):
                    defects.append("Provide nonempty title and body fields")
                reference = item["required_credentials"][0]
                if (
                    registered_applicability(
                        self.state, reference, publication_context(self.state, item)
                    ).status
                    != CheckStatus.PASS
                    or reference
                    not in self.state["artifacts"]["draft"]["versions"][version]["derived_from"]
                ):
                    defects.append("Adopt the applicable confirmed editorial policy")
                if defects:
                    submission["review"] = {
                        "decision": "revision_required",
                        "actor_id": editor,
                        "at": self.state["clock"],
                        "defects": defects,
                    }
                    item["status"] = "revision_required"
                    result = copy.deepcopy(submission["review"])
                else:
                    result = self._tool_approve(
                        editor, item["work_item_id"], submission["submission_id"]
                    )
                self._message(editor, [item["owner_role"]], "Publication field review", result)
                self._staff_record(editor, "review", event["payload"], result, self._reads)
                return result

            _, receipt = execute_transition(self.state, frame, review, self._derive)
            self.state["event_history"].append(
                {**event, "outcome": "applied", "transition": receipt}
            )


def evaluate_publication(world, work_item_id=None):
    """Independent finite checks; never mutate staff observations or decisions."""
    state = world.store.load()
    work_item_id = work_item_id or current_id(state, WORK_ID)
    item = state["work_items"][work_item_id]
    sub = item["submissions"][-1] if item["submissions"] else None
    checks = []

    def add(name, passed, details=None):
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "details": details})

    add("has_submission", sub is not None)
    if sub:
        version = sub["artifact_versions"]["draft"]
        try:
            content = json.loads(world.store.content(state["artifacts"]["draft"], version))
        except (ValueError, UnicodeError):
            content = None
        reference = sub["required_credentials"][0]
        applicability = registered_applicability(state, reference, publication_context(state, item))
        checks.append({"name": "policy_applicability", **applicability.to_dict()})
        add("structured_draft", isinstance(content, dict))
        if isinstance(content, dict):
            add("source_reference", content.get("source_ref") == SOURCE_REF)
            add("title", isinstance(content.get("title"), str) and bool(content["title"].strip()))
            if applicability.status == CheckStatus.PASS:
                policy = json.loads(
                    world.store.content(
                        state["artifacts"]["editorial_policy"], reference["version_id"]
                    )
                )
                add(
                    "required_phrases",
                    isinstance(content.get("body"), str)
                    and all(phrase in content["body"] for phrase in policy["required_phrases"]),
                    policy["required_phrases"],
                )
            else:
                checks.append(
                    {
                        "name": "required_phrases",
                        "status": "UNASSESSED",
                        "reasons": ["No applicable confirmed policy"],
                    }
                )
        dependencies = state["artifacts"]["draft"]["versions"][version]["derived_from"]
        add("declared_adoption", reference in dependencies and SOURCE_REF in dependencies)
    return {
        "work_item_id": work_item_id,
        "passed": all(check["status"] == "PASS" for check in checks),
        "business_accepted": bool(sub and (sub.get("review") or {}).get("decision") == "accepted"),
        "currently_applicable": current_id(state, work_item_id) == work_item_id,
        "checks": checks,
        "evaluation_scope": "exact references, fields and phrases; not professional editorial quality",
    }
