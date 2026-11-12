"""Versioned decision gates for CHIEF, REVIEW and MATRIX organizations.

Only explicit member tools create organizational decisions. Task ownership is
never written here: the original claim/offer/accept contract remains in force.
All records bind public tasks and immutable patches, not private file contents.
"""
from __future__ import annotations

import copy

from .software_collaboration_v027 import _tool

VERSION = "v104-fixed-organization-governance-r1"
LEAD, REVIEWER = "member_001", "member_002"
IMPLEMENTERS = ("member_003", "member_004")
MEMBERS = (LEAD, REVIEWER, *IMPLEMENTERS)
_TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
_ID = {"type": "string", "minLength": 1, "maxLength": 128}
_REVISION = {"type": "integer", "minimum": 1}
_PRIORITY = {"type": "integer", "minimum": 0, "maximum": 1000}
_DECISION = {"type": "string", "enum": ["accept", "request_changes"]}


def tool_definitions(organization_id):
    if organization_id == "CHIEF":
        return [
            _tool("org_assign_task", "Only member_001 may authorize the assignee and priority of "
                  "an exact public task revision. This never claims or transfers responsibility; "
                  "the member must use claim_task or the existing offer/accept protocol.",
                  {"task_id": _ID, "task_revision": _REVISION,
                   "assignee": {"type": "string", "enum": list(MEMBERS)},
                   "priority": _PRIORITY, "reason": _TEXT}),
            _tool("org_select_patch", "Only member_001 may authorize one recipient to integrate "
                  "an immutable published patch. To submit, member_001 must explicitly select "
                  "its own final fixed version; an earlier incoming patch does not approve later edits.",
                  {"patch_id": _ID, "recipient": {"type": "string", "enum": list(MEMBERS)},
                   "reason": _TEXT}),
        ]
    if organization_id == "REVIEW":
        return [_tool("org_review_patch", "Only member_002 may accept or request changes for an "
                      "immutable candidate published by member_001. Acceptance binds that exact "
                      "author version, expires after an edit, and never substitutes for real tests.",
                      {"patch_id": _ID, "decision": _DECISION, "reason": _TEXT})]
    if organization_id == "MATRIX":
        return [
            _tool("org_matrix_scope", "Only member_001 may confirm a public task revision, "
                  "its implementation owner, priority and scope. Every confirmation replaces "
                  "the scope identity and invalidates previous candidate signoffs. Ownership "
                  "still requires the original explicit claim or accepted transfer.",
                  {"task_id": _ID, "task_revision": _REVISION,
                   "assignee": {"type": "string", "enum": list(IMPLEMENTERS)},
                   "priority": _PRIORITY, "scope": _TEXT, "reason": _TEXT}),
            _tool("org_matrix_review", "member_001 records the project decision and member_002 "
                  "records the independent technical decision on this exact published patch "
                  "and its bound task revisions. Both must accept the same scope identities "
                  "before integration, and both must accept member_001's exact final fixed "
                  "version before submission. Neither lane can overwrite the other.",
                  {"patch_id": _ID,
                   "task_ids": {"type": "array", "items": _ID, "minItems": 1,
                                "maxItems": 24, "uniqueItems": True},
                   "decision": _DECISION, "reason": _TEXT}),
        ]
    return []


def initial_state(organization_id):
    if organization_id == "CHIEF":
        return {"chief": {"assignments": {}, "selections": {}, "history": []}}
    if organization_id == "REVIEW":
        return {"review": {"reviews": {}, "history": []}}
    if organization_id == "MATRIX":
        return {"matrix": {"scopes": {}, "reviews": {}, "history": []}}
    return {}


class GovernanceMixin:
    def _governance(self, kind):
        if self.org_kind() != kind.upper():
            self.org_reject("This organization does not expose that decision", "organization_tool")
        return self.org_state()[kind]

    def _org_role(self, actor, allowed):
        if actor not in allowed:
            self.org_reject("This member has no authority for that organizational decision",
                            "organization_authority")

    def _org_text(self, value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            self.org_reject("Supply a nonblank bounded explanation", "organization_record")

    def _org_task_revision(self, task_id, revision):
        task = self._task(task_id)
        if type(revision) is not int or task["revision"] != revision:
            self.org_reject("Task revision changed; read the public task before deciding",
                            "organization_stale_task")
        return task

    def _org_record(self, state, actor, kind, **facts):
        row = {"decision_id": f"{kind}-{len(state['history']) + 1}", "actor": actor,
               "kind": kind, **copy.deepcopy(facts)}
        event = self.org_event(actor, kind, **{key: value for key, value in row.items()
                                             if key not in {"kind", "actor"}})
        if isinstance(event, dict) and "sequence" in event:
            row["event_sequence"] = event["sequence"]
        state["history"].append(copy.deepcopy(row))
        return row

    def _action_org_assign_task(self, actor, project_id, task_id, task_revision,
                                assignee, priority, reason):
        state = self._governance("chief")
        self._org_role(actor, (LEAD,))
        self._org_role(assignee, MEMBERS)
        self._org_text(reason)
        self._org_task_revision(task_id, task_revision)
        row = self._org_record(state, actor, "chief_assignment", task_id=task_id,
                               task_revision=task_revision, assignee=assignee,
                               priority=priority, reason=reason)
        state["assignments"][task_id] = row
        return copy.deepcopy(row)

    def _action_org_select_patch(self, actor, project_id, patch_id, recipient, reason):
        state = self._governance("chief")
        self._org_role(actor, (LEAD,))
        self._org_role(recipient, MEMBERS)
        self._org_text(reason)
        identity = self.org_patch_identity(patch_id)
        row = self._org_record(state, actor, "chief_patch_selected", patch_id=patch_id,
                               recipient=recipient, identity=identity, reason=reason)
        state["selections"].setdefault(recipient, {})[patch_id] = row
        return copy.deepcopy(row)

    def _action_org_review_patch(self, actor, project_id, patch_id, decision, reason):
        state = self._governance("review")
        self._org_role(actor, (REVIEWER,))
        self._org_text(reason)
        if decision not in ("accept", "request_changes") or self._patch(patch_id)["author"] != LEAD:
            self.org_reject("Review the developer's published candidate with an explicit decision",
                            "organization_review_candidate")
        row = self._org_record(state, actor, "candidate_reviewed", patch_id=patch_id,
                               identity=self.org_patch_identity(patch_id), decision=decision,
                               reason=reason)
        state["reviews"][patch_id] = row
        return copy.deepcopy(row)

    def _action_org_matrix_scope(self, actor, project_id, task_id, task_revision,
                                 assignee, priority, scope, reason):
        state = self._governance("matrix")
        self._org_role(actor, (LEAD,))
        self._org_role(assignee, IMPLEMENTERS)
        self._org_text(scope)
        self._org_text(reason)
        self._org_task_revision(task_id, task_revision)
        row = self._org_record(state, actor, "matrix_scope", task_id=task_id,
                               task_revision=task_revision, assignee=assignee,
                               priority=priority, scope=scope, reason=reason)
        state["scopes"][task_id] = row
        return copy.deepcopy(row)

    def _matrix_bindings(self, patch_id, task_ids):
        state = self._governance("matrix")
        patch = self._patch(patch_id)
        if (not task_ids or len(set(task_ids)) != len(task_ids)
                or patch["author"] not in (LEAD, *IMPLEMENTERS)):
            self.org_reject("Choose distinct tasks bound by an implementation or final candidate",
                            "matrix_candidate_binding")
        supplied = dict(patch.get("task_snapshots", {}))
        pending, visited = list(patch.get("included_patch_ids", [])), {patch_id}
        while pending:
            incoming = pending.pop()
            if incoming in visited:
                continue
            visited.add(incoming)
            prior = self._patch(incoming)
            for key, value in prior.get("task_snapshots", {}).items():
                # Integrated patch IDs are cumulative provenance. A later
                # actually fixed task revision supersedes an older snapshot;
                # the current task revision must still be supplied below.
                if key not in supplied or value["revision"] > supplied[key]["revision"]:
                    supplied[key] = value
            pending.extend(prior.get("included_patch_ids", []))
        if set(task_ids) != set(supplied):
            self.org_reject("Confirm every task revision carried by this immutable candidate",
                            "matrix_candidate_binding")
        bindings = {}
        for task_id in sorted(task_ids):
            task = self._task(task_id)
            scope = state["scopes"].get(task_id)
            if (not scope or scope["task_revision"] != task["revision"]
                    or supplied[task_id]["revision"] != task["revision"]):
                self.org_reject("Candidate task or project scope revision is stale",
                                "organization_stale_task")
            bindings[task_id] = {"task_revision": task["revision"],
                                  "scope_id": scope["decision_id"]}
        return bindings

    def _action_org_matrix_review(self, actor, project_id, patch_id, task_ids, decision, reason):
        state = self._governance("matrix")
        self._org_role(actor, (LEAD, REVIEWER))
        self._org_text(reason)
        if decision not in ("accept", "request_changes"):
            self.org_reject("Record acceptance or requested changes", "organization_record")
        lane = "project" if actor == LEAD else "technical"
        row = self._org_record(state, actor, "matrix_candidate_review", patch_id=patch_id,
                               lane=lane, task_bindings=self._matrix_bindings(patch_id, task_ids),
                               identity=self.org_patch_identity(patch_id), decision=decision,
                               reason=reason)
        state["reviews"].setdefault(patch_id, {})[lane] = row
        return copy.deepcopy(row)

    def _governance_assignment(self, task_id, member, *, matrix=False):
        key, name = ("matrix", "scopes") if matrix else ("chief", "assignments")
        task = self._task(task_id)
        entry = self._governance(key)[name].get(task_id)
        if not entry or entry["task_revision"] != task["revision"] or entry["assignee"] != member:
            self.org_reject("This exact task revision has no current authorization for that member",
                            "organization_assignment")

    def _matrix_approved(self, patch_id):
        all_reviews = self._governance("matrix")["reviews"]
        reviews = all_reviews.get(patch_id, {})
        project, technical = reviews.get("project"), reviews.get("technical")
        if (not project or not technical or project["decision"] != "accept"
                or technical["decision"] != "accept"
                or project["task_bindings"] != technical["task_bindings"]):
            self.org_reject("The same candidate needs independent project and technical acceptance",
                            "matrix_dual_confirmation")
        source = self.org_patch_identity(patch_id)["source_reference"]
        for lane in ("project", "technical"):
            opinions = [value[lane] for value in all_reviews.values()
                        if lane in value and value[lane]["identity"]["source_reference"] == source]
            latest = max(opinions, key=lambda row: row["event_sequence"])
            if latest["decision"] != "accept":
                self.org_reject("A newer opinion rejects this same candidate version, even "
                                "when it uses another fixed patch ID", "matrix_latest_rejection")
        current = self._matrix_bindings(patch_id, list(project["task_bindings"]))
        if current != project["task_bindings"]:
            self.org_reject("Project scope changed after the two candidate confirmations",
                            "matrix_stale_confirmation")

    def _current_fixed_patches(self, actor):
        source = self.org_current_identity(actor)["source_reference"]
        return [patch_id for patch_id, patch in self._software()["patches"].items()
                if patch["author"] == actor and patch["source_reference"] == source]

    def _org_guard_governance(self, actor, tool, arguments):
        organization = self.org_kind()
        if organization not in {"CHIEF", "REVIEW", "MATRIX"}:
            return
        if organization in {"CHIEF", "MATRIX"}:
            matrix = organization == "MATRIX"
            if tool == "claim_task":
                self._governance_assignment(arguments["task_id"], actor, matrix=matrix)
            elif tool == "offer_transfer":
                self._governance_assignment(arguments["task_id"], arguments["to_member"], matrix=matrix)
            elif tool == "accept_transfer":
                offer = self._software()["transfer_offers"].get(arguments["offer_id"])
                if offer is not None:
                    self._governance_assignment(offer["task_id"], actor, matrix=matrix)
            elif tool == "integrate_patch":
                if matrix:
                    # Technical reviewers and implementers may inspect/test
                    # public candidates in their own private workspaces. The
                    # dual gate protects entry into the final integration tree.
                    if actor == LEAD:
                        self._matrix_approved(arguments["patch_id"])
                elif arguments["patch_id"] not in self._governance("chief")["selections"].get(actor, {}):
                    self.org_reject("The lead has not selected this patch for this recipient",
                                    "chief_patch_selection")
        if tool != "submit_integration":
            return
        self._org_role(actor, (LEAD,))
        patches = self._current_fixed_patches(actor)
        if organization == "CHIEF":
            selected = self._governance("chief")["selections"].get(actor, {})
            if not any(patch_id in selected for patch_id in patches):
                self.org_reject("The lead must select its own exact final fixed candidate",
                                "chief_final_selection")
        elif organization == "REVIEW":
            reviews = self._governance("review")["reviews"]
            # Re-fixing unchanged content can create multiple patch IDs for the
            # same author version. Its latest independent opinion governs all
            # aliases; an older acceptance cannot bypass a newer rejection.
            current_reviews = [reviews[patch_id] for patch_id in patches if patch_id in reviews]
            latest = max(current_reviews, key=lambda row: row["event_sequence"], default=None)
            if latest is None or latest["decision"] != "accept":
                self.org_reject("The exact current developer version has no independent acceptance",
                                "review_required")
        elif not patches:
            self.org_reject("Fix the exact current final candidate before dual confirmation",
                            "matrix_final_confirmation")
        else:
            # Each newly fixed candidate has a unique identity. Require the last
            # fixed version's dual confirmation; never select a better old tree.
            self._matrix_approved(patches[-1])
