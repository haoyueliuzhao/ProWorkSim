"""Explicit role focus, source-bound acceptance and actionable handoff status.

Only public immutable patches and explicit member decisions enter the shared
directory. No view copies a peer workspace, merges code, runs a test or submits.
The old frozen worlds are reused through local bindings and remain unchanged.
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import FunctionType

from . import software_fixed_organization_world_v065 as base
from . import software_benchmark_tooling_v130 as tooling
from . import software_role_baseline_contract_v141 as contract
from .software_fixed_organization_world_v132 import _streamed_preparation
from .software_benchmark_initial_state_hash_v132 import initial_business_state_digest
from .software_fixed_organization_world_v131 import PublicTestCallback as PreviousPublicTestCallback
from .software_benchmark_public_tests_v110 import capabilities, normalize_selection, selected_entry
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_state_storage_v141 import bind_world_type, build_scenario
from .software_collaboration_v027 import _tool
from .storage import atomic_write, digest, json_bytes
from .tool_outcomes import ToolRejection

VERSION = "v141-role-baseline-managed-world-r1"
PURPOSE = "role_baseline_engineering_and_mechanism_calibration"
PROJECT = base.PROJECT
GROUP_IDS = contract.GROUP_IDS
organization = contract.organization
MEMBER_POOL = contract.MEMBER_POOL
EVENT_PREFIX = "organization_v141:"


def _bind(function, **bindings):
    value = FunctionType(function.__code__, {**function.__globals__, **bindings}, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


_base_case = _bind(base.case_spec, get_organization=organization,
                  validate_organization=contract.validate_organization)


def case_spec(case_id, *, provider, organization_id, max_total_tokens=5_000_000,
              max_decisions=512, max_test_runs=512):
    value = _base_case(case_id, provider=provider, organization_id=organization_id,
                      max_total_tokens=max_total_tokens, max_decisions=max_decisions,
                      max_test_runs=max_test_runs)
    value.update(version=VERSION, interface_revision=VERSION, purpose=PURPOSE,
                 usage=PURPOSE, category=PURPOSE, split=PURPOSE,
                 scheduling_protocol="v141-common-fair-fixed-roster",
                 organization_protocol=VERSION, organization_records_are_public=True,
                 organizational_rules_are_enforced=True,
                 public_test_selection_revision="v110-public-test-selection-r1",
                 public_validation_revision="v141-session-bound-public-test-execution-r1",
                 formal_execution_authorized=False,
                 future_budget_selection="An explicit host plan separately freezes paid experiment limits")
    value["submission_requires"] += (["exact_final_candidate_independent_review"]
                                      if organization_id == "REVIEW2" else [])
    return value


def validate_case(case, *, provider):
    expected = case_spec(case["case_id"], provider=provider,
                        organization_id=case["fixed_organization"]["id"],
                        max_total_tokens=case["team_limits"]["max_total_tokens"],
                        max_decisions=case["team_limits"]["max_decisions"],
                        max_test_runs=case["team_limits"]["max_test_runs"])
    if case != expected:
        raise ValueError("The declared source, role baseline, permissions or team budget changed")
    return case


def member_instruction(case, member):
    spec = case["fixed_organization"]
    if member not in spec["fixed_members"]:
        raise ValueError("Only the actual fixed roster receives member instructions")
    return (base.member_instruction(case, member) + "\n" + spec["organization_instruction"] +
        "\nUse org_status for actual task IDs, current responsibility, fixed candidate identities, "
        "accepted/requested-change records and the next explicit actions. Before creating tasks, "
        "send_message uses task_id='root_goal'; the benchmark instance ID is not a task-board ID. "
        "org_declare_role records your current responsibility focus without changing tools, ownership "
        "or frozen review authority. An author publishes with fix_patch and sends handoff_patch; "
        "a recipient explicitly integrate_patch, run_tests, then org_review_patch to accept. "
        "Acceptance does not merge into another member's tree. An accepted peer patch remains "
        "available to member_001, who must explicitly integrate and finish its own current-version "
        "test, fixed candidate and submit_integration. Requested changes name the original patch "
        "author as the responsible recipient. Original public tests are not hidden grading. "
        "There is no pipeline or Sprint startup gate. In FREE2, independent review is optional; "
        "in REVIEW2, member_002 must accept member_001's exact final fixed version before delivery. "
        "All these actions, rejected requests, final self-review and history use the same team budget.")


def tool_definitions(case):
    members = tuple(case["active_roles"])
    tools = [copy.deepcopy(row) for row in tooling.tool_definitions(case)
             if row["name"] not in base.DYNAMIC_TOOLS]
    for tool in tools:
        for field in ("recipient", "to_member"):
            prop = tool["parameters"].get("properties", {}).get(field)
            if isinstance(prop, dict):
                prop["enum"] = list(members)
        if tool["name"] == "send_message":
            tool["description"] += " Use task_id='root_goal' before a task exists; org_status lists real task IDs."
        elif tool["name"] == "handoff_patch":
            tool["description"] += " A notice does not copy or integrate code. org_status shows receiver next steps."
    text = {"type": "string", "minLength": 1, "maxLength": 2000}
    ident = {"type": "string", "minLength": 1, "maxLength": 128}
    tools += [
        _tool("org_status", "Read public responsibility and candidate evidence plus your own closing steps. "
              "This view never adopts, tests, accepts or submits. Exact event records use read_work_event.",
              {"after_sequence": {"type": "integer", "minimum": 0},
               "limit": {"type": "integer", "minimum": 1, "maximum": 32}}, []),
        _tool("org_declare_role", "Record your own responsibility focus and why it changed. In FREE2 this "
              "is self-organized role formation; S1/REVIEW2 retain their frozen role obligations. "
              "A declaration never grants tool power or transfers a task.",
              {"role_label": ident, "responsibility": text, "reason": text}),
    ]
    if len(members) > 1:
        tools.append(_tool("org_review_patch", "Accept or request changes for another member's published "
            "fixed patch. Acceptance requires explicit adoption into your private tree and real public "
            "test execution on that exact content/version. Preserve actual failures. The author owns "
            "rework. This records evidence only: no automatic merge, test or submission.",
            {"patch_id": ident, "decision": {"type": "string", "enum": ["accept", "request_changes"]},
             "reason": text}))
    return tooling._independent_tree(tools)


def schema_case(group):
    spec = organization(group)
    return {"fixed_organization": spec, "active_roles": spec["fixed_members"],
            "team_limits": {"max_test_runs": 512},
            "member_limits": {"max_live_members": spec["member_count"], "births_enabled": False}}


class TestBudget(base.TestBudget):
    def __init__(self, output, limit, members):
        self.members = tuple(members)
        if not 1 <= len(self.members) <= 2 or len(set(self.members)) != len(self.members):
            raise ValueError("Only the actual one/two-member shared pool may consume tests")
        self.output, self.limit, self.records = Path(output), base._positive(limit, "test limit"), []


class PublicTestCallback(PreviousPublicTestCallback):
    __call__ = _bind(PreviousPublicTestCallback.__call__, VERSION=VERSION)


class SoftwareCollaborationWorld(base.SoftwareCollaborationWorld, tooling.SoftwareCollaborationWorld):
    def org_kind(self):
        return self._software()["case"]["fixed_organization"]["id"]

    def org_state(self):
        value = self._software()["organization_state"]
        if value.get("version") != VERSION or value.get("organization_id") != self.org_kind():
            raise ValueError("Role state does not match this world's declared policy")
        return value

    def org_reject(self, message, code="role_baseline_contract", **context):
        raise ToolRejection(message, code=code, category="business_constraint", context=context)

    def org_current_identity(self, actor):
        artifact, version, bundle = self._bundle(actor)
        return {"source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
                "files_sha256": digest(json_bytes(bundle["files"])),
                "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"]))}

    def org_patch_identity(self, patch_id):
        patch = self._patch(patch_id)
        return {key: copy.deepcopy(patch[key]) for key in
                ("source_reference", "files_sha256", "entry_metadata_sha256")}

    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()["case"]) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _task(self, task_id, actor=None):
        if task_id not in self._software()["tasks"]:
            self.org_reject("Unknown task-board ID. Use org_status for actual IDs; messages before "
                            "task creation use task_id='root_goal'.", "unknown_task_id",
                            valid_task_ids=sorted(self._software()["tasks"]), message_root_id="root_goal")
        return super()._task(task_id, actor)

    def _patch(self, patch_id):
        if patch_id not in self._software()["patches"]:
            self.org_reject("Unknown fixed patch ID. Read org_status for published candidates.",
                            "unknown_published_patch", public_patch_ids=sorted(self._software()["patches"])[-32:])
        return super()._patch(patch_id)

    def _action_run_tests(self, actor, project_id, selection=None):
        if getattr(self, "_active_public_test_actor", None) is not None:
            raise ValueError("Actual public tests remain single-writer")
        self._active_public_test_actor = actor
        try:
            return tooling.SoftwareCollaborationWorld._action_run_tests(self, actor, project_id, selection)
        finally:
            self._active_public_test_actor = None

    def _task_revisions(self, patch):
        found, pending, visited = {}, [patch["patch_id"]], set()
        while pending:
            patch_id = pending.pop()
            if patch_id in visited:
                continue
            visited.add(patch_id)
            current = self._patch(patch_id)
            for tid, task in current["task_snapshots"].items():
                found[tid] = max(found.get(tid, 0), task["revision"])
            pending += current.get("included_patch_ids", [])
        if any(self._task(tid)["revision"] != revision for tid, revision in found.items()):
            self.org_reject("Candidate task revisions are stale; publish a new source-bound result.",
                            "stale_candidate_tasks", candidate_task_revisions=found)
        return found

    def _latest_same_version_test(self, actor, current):
        return next((event for event in reversed(self.state["software_events"])
                     if event["kind"] == "test" and event["actor_id"] == actor
                     and event.get("executed") is True
                     and all(event.get(key) == value for key, value in current.items())), None)

    @staticmethod
    def _test_summary(test):
        if test is None:
            return None
        value = {key: copy.deepcopy(test[key]) for key in
                 ("sequence", "actor_id", "source_reference", "files_sha256",
                  "entry_metadata_sha256", "executed", "passed")}
        execution = test.get("public_execution", {}).get("execution", {})
        value.update({key: copy.deepcopy(execution[key]) for key in ("validation_status", "counts")
                      if key in execution})
        return value

    def _decision(self, patch, reviewer=None):
        relevant = [row for row in self.org_state()["reviews"]
                    if row["identity"]["source_reference"] == patch["source_reference"]
                    and (reviewer is None or row["actor_id"] == reviewer)]
        return relevant[-1] if relevant else None

    def _decision_is_current(self, decision, patch):
        if decision is None:
            return False
        try:
            return (decision["identity"] == self.org_patch_identity(patch["patch_id"])
                    and decision["task_revisions"] == self._task_revisions(patch))
        except ToolRejection:
            return False

    def _action_org_declare_role(self, actor, project_id, role_label, responsibility, reason):
        if any(not value.strip() for value in (role_label, responsibility, reason)):
            self.org_reject("Describe a nonblank responsibility and reason.", "empty_role_declaration")
        old = self.org_state()["role_declarations"].get(actor)
        row = {"member_id": actor, "role_label": role_label, "responsibility": responsibility,
               "reason": reason, "source": "explicit_self_declaration",
               "prior_event_sequence": old["event_sequence"] if old else None,
               "frozen_role_obligation": self._software()["case"]["fixed_organization"]["roles"][actor],
               "changes_permissions_or_ownership": False}
        event = self._event(actor, EVENT_PREFIX+"role_declared", **copy.deepcopy(row))
        row["event_sequence"] = event["sequence"]
        row["logical_time"] = event["logical_time"]
        self.org_state()["role_declarations"][actor] = row
        return copy.deepcopy(row)

    def _action_org_review_patch(self, actor, project_id, patch_id, decision, reason):
        patch = self._patch(patch_id)
        if actor == patch["author"]:
            self.org_reject("Independent review must come from another actual member.", "self_review_forbidden")
        if decision not in {"accept", "request_changes"} or not reason.strip():
            self.org_reject("Record accept/request_changes with a nonblank reason.", "invalid_review_decision")
        # Permission check on the actual published version; do not expose its private successors.
        self._bundle(actor, reference=patch["source_reference"])
        revisions = self._task_revisions(patch)
        current = self.org_current_identity(actor)
        adopted, test = False, None
        if decision == "accept":
            _, _, bundle = self._bundle(actor)
            adopted = patch_id in bundle["included_patch_ids"]
            if not adopted or any(current[key] != patch[key] for key in ("files_sha256", "entry_metadata_sha256")):
                self.org_reject("Explicitly integrate this fixed patch, resolve any conflicts and test "
                    "that exact candidate before acceptance.", "review_requires_adoption",
                    next_action={"tool": "integrate_patch", "arguments": {"patch_id": patch_id}})
            test = self._latest_same_version_test(actor, current)
            if test is None:
                self.org_reject("Execute public tests on your exact adopted version before accepting.",
                                "review_requires_same_version_test", next_action={"tool": "run_tests", "arguments": {}})
        row = {"review_id": "review-"+str(len(self.org_state()["reviews"])+1),
               "patch_id": patch_id, "actor_id": actor, "author": patch["author"],
               "identity": self.org_patch_identity(patch_id), "task_revisions": revisions,
               "decision": decision, "reason": reason,
               "adopted_source_reference": copy.deepcopy(current["source_reference"]) if adopted else None,
               "test_evidence": self._test_summary(test),
               "rework_responsible": patch["author"] if decision == "request_changes" else None,
               "automatic_integration": False, "public_test_is_official_score": False}
        event = self._event(actor, EVENT_PREFIX+"candidate_reviewed", **copy.deepcopy(row))
        row["event_sequence"] = event["sequence"]
        row["logical_time"] = event["logical_time"]
        self.org_state()["reviews"].append(row)
        return copy.deepcopy(row)

    def _review_gate(self, actor):
        if self.org_kind() != "REVIEW2":
            return None
        current = self.org_current_identity(actor)
        patches = [p for p in self._software()["patches"].values()
                   if p["author"] == actor and p["source_reference"] == current["source_reference"]]
        if not patches:
            self.org_reject("Fix your exact final version before asking for independent review.",
                            "review_requires_fixed_final", next_action={"tool": "fix_patch", "arguments": {
                                "task_ids": [], "message": "Describe your exact final candidate."}})
        latest = self._decision(patches[-1], reviewer="member_002")
        if not self._decision_is_current(latest, patches[-1]) or latest["decision"] != "accept":
            self.org_reject("member_002 must explicitly adopt, test and accept this exact final fixed "
                            "version. Old or revoked acceptance is insufficient.", "final_review_required",
                            patch_id=patches[-1]["patch_id"], reviewer="member_002")
        return latest

    def _action_submit_integration(self, actor, project_id, message=""):
        current = self.org_current_identity(actor)
        for patch in self._software()["patches"].values():
            if patch["author"] == actor and patch["source_reference"] == current["source_reference"]:
                self._task_revisions(patch)
        review = self._review_gate(actor)
        result = super()._action_submit_integration(actor, project_id, message)
        proof = {"version": VERSION, "organization_id": self.org_kind(),
                 "delivery_member": actor, "delivery_id": result["delivery_id"],
                 "source_reference": copy.deepcopy(result["source_reference"]),
                 "independent_review": copy.deepcopy(review),
                 "explicit_delivery": True, "automatic_work": False}
        self._software().setdefault("organization_delivery_proofs_v141", {})[result["delivery_id"]] = proof
        return {**result, "organization_evidence": proof}

    def organization_active_members(self):
        self.state = self.store.load()
        return tuple(self._software()["case"]["active_roles"])

    def consume_organization_opportunity(self, actor=None):
        with self.store.lock():
            self.state = self.store.load()
            if self.fixed_candidates_closed or actor not in self._software()["case"]["active_roles"]:
                raise ValueError("Only an actual live member opportunity may be recorded")
            self.org_state()["opportunities_consumed"] += 1
            self.store.save(self.state)
            return {"opportunities_consumed": self.org_state()["opportunities_consumed"],
                    "phase_before": {}, "phase_after": {}, "boundary_event_sequence": None}

    def reachable_events(self, member, after_sequence=0):
        rows = super().reachable_events(member, after_sequence)
        existing = {row["sequence"] for row in rows}
        rows += [copy.deepcopy(row) for row in self.state["software_events"]
                 if row["sequence"] > after_sequence and row["sequence"] not in existing
                 and row["actor_id"] != member and row["kind"].startswith(EVENT_PREFIX)]
        return sorted(rows, key=lambda row: row["sequence"])

    def _action_read_work_event(self, actor, project_id, sequence):
        event = next((e for e in self.state["software_events"] if e["sequence"] == sequence), None)
        if event and event["kind"].startswith(EVENT_PREFIX):
            return copy.deepcopy(event)
        return super()._action_read_work_event(actor, project_id, sequence)

    def _receiver_step(self, actor, patch):
        current = self.org_current_identity(actor)
        _, _, bundle = self._bundle(actor)
        if patch["patch_id"] not in bundle["included_patch_ids"]:
            return {"tool": "integrate_patch", "arguments": {"patch_id": patch["patch_id"]},
                    "note": "Explicit adoption may expose conflicts; inspect and resolve them yourself."}
        if any(current[key] != patch[key] for key in ("files_sha256", "entry_metadata_sha256")):
            return {"tool": "org_review_patch", "arguments": {"patch_id": patch["patch_id"]},
                    "member_must_supply": ["decision", "reason"],
                    "note": "Your adopted tree now differs. Request changes, or inspect the fixed patch "
                    "and explicitly restore the intended exact content before a fresh test and acceptance."}
        if self._latest_same_version_test(actor, current) is None:
            return {"tool": "run_tests", "arguments": {}}
        return {"tool": "org_review_patch", "arguments": {"patch_id": patch["patch_id"]},
                "member_must_supply": ["decision", "reason"],
                "allowed_decisions": ["accept", "request_changes"],
                "note": "Decide independently using the actual test outcome and code; execution alone is not correctness."}

    def _closing_steps(self, actor):
        current = self.org_current_identity(actor)
        baseline = super()._delivery_status_for_reference(actor, current["source_reference"])
        _, _, bundle = self._bundle(actor)
        _, _, source = self._bundle(actor, baseline=True)
        has_changes = (bundle["files"] != source["files"]
                       or bundle["entry_metadata"] != source["entry_metadata"])
        own = [p for p in self._software()["patches"].values()
               if p["author"] == actor and p["source_reference"] == current["source_reference"]]
        pending = []
        for patch in self._software()["patches"].values():
            decision = self._decision(patch)
            if (patch["author"] != actor and patch["patch_id"] not in bundle["included_patch_ids"]
                    and self._decision_is_current(decision, patch) and decision["decision"] == "accept"):
                pending.append(patch["patch_id"])
        if self.org_kind() == "REVIEW2" and actor == "member_002":
            author_patches = [p for p in self._software()["patches"].values() if p["author"] == contract.DELIVERY_MEMBER]
            if author_patches:
                candidate = author_patches[-1]
                decision = self._decision(candidate, reviewer=actor)
                next_action = ({"tool": "staff_wait", "arguments": {
                    "reason": "Review recorded; wait for the author response or a new fixed candidate."}}
                    if self._decision_is_current(decision, candidate) else self._receiver_step(actor, candidate))
            else:
                next_action = {"tool": "send_message", "arguments": {"recipient": contract.DELIVERY_MEMBER,
                    "task_id": "root_goal", "body": "Publish a fixed candidate when ready for independent review."}}
        elif not has_changes:
            next_action = ({"tool": "integrate_patch", "arguments": {}, "member_must_supply": ["patch_id"],
                            "available_patch_ids": pending,
                            "note": "Accepted peer results are available; choose explicitly whether to integrate them."}
                           if pending else {"tool": "read_task", "arguments": {},
                            "note": "No net change in this workspace. Choose useful work or inspect a published peer candidate."})
        elif actor != contract.DELIVERY_MEMBER:
            if not own:
                next_action = {"tool": "fix_patch", "arguments": {
                    "task_ids": [], "message": "Describe the exact changed version."}}
            else:
                handed = any(e["kind"] == "handoff" and e["actor_id"] == actor
                             and e.get("patch_id") == own[-1]["patch_id"]
                             and e.get("recipient") == contract.DELIVERY_MEMBER for e in self.state["software_events"])
                next_action = ({"tool": "staff_wait", "arguments": {"reason": "Fixed result sent; wait for real feedback."}}
                    if handed else {"tool": "handoff_patch", "arguments": {"patch_id": own[-1]["patch_id"],
                        "to_member": contract.DELIVERY_MEMBER, "message": "Describe this exact published result."}})
        elif not baseline["public_test_executed"]:
            next_action = {"tool": "run_tests", "arguments": {}}
        elif not own:
            next_action = {"tool": "fix_patch", "arguments": {
                "task_ids": [], "message": "Describe the exact current tested candidate."}}
        elif self.org_kind() == "REVIEW2":
            decision = self._decision(own[-1], reviewer="member_002")
            valid = self._decision_is_current(decision, own[-1])
            if valid and decision["decision"] == "accept":
                next_action = {"tool": "submit_integration", "arguments": {"message": "Deliver this exact version."}}
            elif valid:
                next_action = {"tool": "read_work_event", "arguments": {"sequence": decision["event_sequence"]},
                               "note": "Current independent review requests changes; inspect the reason before revising."}
            else:
                notified = any(e["kind"] == "handoff" and e["actor_id"] == actor
                               and e.get("patch_id") == own[-1]["patch_id"] and e.get("recipient") == "member_002"
                               for e in self.state["software_events"])
                next_action = ({"tool": "staff_wait", "arguments": {"reason": "This candidate is handed off; wait for actual review."}}
                    if notified else {"tool": "handoff_patch", "arguments": {
                        "patch_id": own[-1]["patch_id"], "to_member": "member_002",
                        "message": "Please adopt, run public tests and review this final candidate."}})
        else:
            next_action = {"tool": "submit_integration", "arguments": {"message": "Deliver this exact version."}}
        current_rejection = (self.org_kind() == "REVIEW2" and own
                             and self._decision_is_current(self._decision(own[-1], "member_002"), own[-1])
                             and self._decision(own[-1], "member_002")["decision"] == "request_changes")
        if actor == contract.DELIVERY_MEMBER and baseline["legal_delivery_id"] and not current_rejection:
            next_action = {"tool": "staff_done", "arguments": {"reason": "Current version already delivered."}}
        stages = {"read_task": "choose_work", "integrate_patch": "awaiting_explicit_adoption",
                  "run_tests": "current_version_needs_public_test", "fix_patch": "current_version_needs_fixed_candidate",
                  "handoff_patch": "fixed_candidate_needs_directed_handoff", "org_review_patch": "independent_decision_pending",
                  "read_work_event": "rework_requested", "submit_integration": "ready_for_explicit_delivery",
                  "staff_done": "current_version_legally_delivered", "staff_wait": "awaiting_real_peer_event",
                  "send_message": "awaiting_author_candidate"}
        return {**baseline, "designated_delivery_member": contract.DELIVERY_MEMBER,
                "current_workspace_has_net_changes": has_changes,
                "current_effective_fixed_candidate": self.org_patch_identity(own[-1]["patch_id"]) if own else None,
                "current_effective_patch_id": own[-1]["patch_id"] if own else None,
                "work_stage": stages[next_action["tool"]],
                "pending_accepted_peer_patch_ids": pending,
                "next_explicit_action": next_action,
                "requires_independent_review": self.org_kind() == "REVIEW2",
                "guide_is_not_automatic_execution_or_acceptance": True}

    def _delivery_status_for_reference(self, actor, reference):
        current = self.org_current_identity(actor)
        if current["source_reference"] != reference:
            raise ValueError("Closing guidance must bind the displayed current version")
        return self._closing_steps(actor)

    def _organization_overview(self, actor=None):
        spec = self._software()["case"]["fixed_organization"]
        return {"version": VERSION, "organization_id": self.org_kind(),
                "opportunities_consumed": self.org_state()["opportunities_consumed"],
                "members": list(spec["fixed_members"]), "final_integration_responsible": spec["delivery_member"],
                "role_declarations": copy.deepcopy(self.org_state()["role_declarations"]),
                "independent_review_required": spec["independent_review_required_for_delivery"],
                "phase": "open_work_with_explicit_candidate_handoffs",
                "record_counts": {"published_candidates": len(self._software()["patches"]),
                                  "reviews": len(self.org_state()["reviews"]),
                                  "tasks": len(self._software()["tasks"])}}

    def _action_org_status(self, actor, project_id, after_sequence=0, limit=12):
        facts = self._software()
        public_kinds = {"patch_fixed", "submit", "task_created", "task_revised", "claim",
                        "transfer_offered", "transfer_accepted", "task_returned"}
        events = [e for e in self.state["software_events"] if e["sequence"] > after_sequence
                  and (e["kind"] in public_kinds or e["kind"].startswith(EVENT_PREFIX))]
        selected = events[:limit]
        fields = {"sequence", "actor_id", "kind", "patch_id", "review_id", "decision", "task_id", "source_reference"}
        candidates = []
        _, _, own_bundle = self._bundle(actor)
        for patch in list(facts["patches"].values())[-limit:]:
            decision = self._decision(patch)
            valid = self._decision_is_current(decision, patch)
            adopted = patch["patch_id"] in own_bundle["included_patch_ids"]
            candidates.append({"patch_id": patch["patch_id"], "author": patch["author"],
                "identity": self.org_patch_identity(patch["patch_id"]),
                "decision": decision["decision"] if valid else "pending_or_stale_review",
                "decision_event_sequence": decision["event_sequence"] if decision else None,
                "rework_responsible": patch["author"] if valid and decision["decision"] == "request_changes" else None,
                "adopted_by_you": adopted,
                "available_to_final_integrator": True,
                "next_receiver_step": ("inspect_current_version_and_run_tests" if adopted
                                       else "integrate_patch_explicitly_before_test_and_accept"),
                "original_record": "read_work_event(patch_fixed sequence)"})
        tasks = [{"task_id": t["task_id"], "revision": t["revision"], "owner": t["owner"],
                  "description": t["description"]} for t in list(facts["tasks"].values())[:32]]
        return {"current": self._organization_overview(actor), "your_closure": self._closing_steps(actor),
                "task_directory": tasks, "task_directory_complete": len(facts["tasks"]) <= 32,
                "message_task_id_without_task": "root_goal", "candidates": candidates,
                "candidate_directory_complete": len(facts["patches"]) <= limit,
                "events": [{key: copy.deepcopy(value) for key, value in e.items() if key in fields} for e in selected],
                "next_after_sequence": selected[-1]["sequence"] if len(events) > limit else None,
                "complete": len(events) <= limit,
                "exact_record_tool": "read_work_event(sequence)",
                "no_private_peer_workspace_or_test_output": True}


class SoftwareCollaborationPort(base.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        world = self._session._world
        value.update(profile=VERSION, interface_revision=VERSION, purpose=PURPOSE,
                     tooling_revision=tooling.VERSION,
                     organization_protocol=world._organization_overview(self.role),
                     public_test_selection=capabilities(world.public_test_entry))
        value["scheduling"]["protocol"] = "v141-common-fair-fixed-roster"
        value["tool_navigation"]["organization"] = "org_status"
        return value


SoftwareCollaborationWorld = bind_world_type(SoftwareCollaborationWorld)


_raw_build = _streamed_preparation(base.build_software_collaboration_case,
    VERSION=VERSION, PURPOSE=PURPOSE, case_spec=case_spec, validate_case=validate_case,
    member_instruction=member_instruction, SoftwareCollaborationWorld=SoftwareCollaborationWorld,
    SoftwareCollaborationPort=SoftwareCollaborationPort, TestBudget=TestBudget,
    build_scenario=build_scenario)


def build_software_collaboration_case(*args, **kwargs):
    prepared = _raw_build(*args, **kwargs)
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        world._software()["organization_state"] = {
            "version": VERSION, "organization_id": world.org_kind(), "opportunities_consumed": 0,
            "role_declarations": {}, "reviews": []}
        world._software()["organization_delivery_proofs_v141"] = {}
        world.store.save(world.state)
    prepared.prefix["prepared_business_state_sha256"] = initial_business_state_digest(world)
    prepared.prefix["organization_runtime_revision"] = VERSION
    atomic_write(Path(world.store.root).parent/"preparation.json", json_bytes(prepared.prefix))
    return prepared


def prepare_case(source_manifest, folder, *, organization_id, max_total_tokens=5_000_000,
                 public_test_callback, deadline, public_test_entry, max_decisions=512, max_test_runs=512):
    provider = tooling.previous.previous.public_world.SelectedRepositorySources(source_manifest)
    if len(provider.case_ids) != 1 or public_test_entry.get("instance_id") != provider.case_ids[0]:
        raise ValueError("Exactly one unchanged public task must bind this role baseline")
    selected_entry(public_test_entry, normalize_selection())
    callback = PublicTestCallback(public_test_callback, entry=public_test_entry,
        instance_id=provider.case_ids[0], hard_at=deadline.hard_at,
        folder=Path(folder).parent/"public-test-rpc", clock=deadline.clock)
    provider.runner = callback
    prepared = build_software_collaboration_case(provider.case_ids[0], folder, provider=provider,
        organization_id=organization_id, max_total_tokens=max_total_tokens,
        max_decisions=max_decisions, max_test_runs=max_test_runs)
    prepared.world.public_test_entry = copy.deepcopy(public_test_entry)
    callback.bind_world(prepared)
    write_new(Path(folder)/"role-public-test-selection.json", {"version": VERSION,
        "entry": public_test_entry, "capabilities": capabilities(public_test_entry),
        "fixed_members": list(prepared.case["active_roles"]), "shared_test_limit": max_test_runs,
        "model_calls": 0, "test_executions": 0})
    return prepared
