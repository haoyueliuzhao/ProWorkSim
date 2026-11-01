"""Five organization protocols over the existing private repository harness.

Decisions are ordinary budgeted member tools. Only their explicit public records
and actual schedule boundaries become team-visible; private trees stay private.
This module neither starts an experiment nor grants external resources.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_fixed_organization_world_v065 as previous
from . import software_fixed_organization_v104 as catalog
from . import software_organization_governance_v104 as governance
from . import software_organization_flow_v104 as flow
from .software_benchmark_expansion_episode_v069 import clone_namespace
from .software_collaboration_v027 import _tool
from .storage import atomic_write, digest, json_bytes
from .scenarios import initial_business_state
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors

VERSION = "v104-five-organization-managed-world-r1"
PURPOSE = "five_organization_implementation_only"
PROJECT = previous.PROJECT
MAX_DECISIONS, MAX_TEST_RUNS = 512, 512
ORG_EVENT_PREFIX = "organization_v104:"


def tool_definitions(case):
    tools = previous.tool_definitions(case)
    kind = case["fixed_organization"]["id"]
    tools += governance.tool_definitions(kind) + flow.tool_definitions(kind)
    tools.append(_tool("org_status", "Read current organization phase and a bounded directory of "
        "explicit public organization events. Read exact records with read_work_event(sequence). "
        "This does not advance a phase, approve code, transfer tasks or run tests.",
        {"after_sequence": {"type": "integer", "minimum": 0},
         "limit": {"type": "integer", "minimum": 1, "maximum": 32}}, []))
    names = [tool["name"] for tool in tools]
    if len(names) != len(set(names)):
        raise ValueError("Organization tool names must be unique")
    return tools


class SoftwareCollaborationWorld(governance.GovernanceMixin, flow.FlowMixin,
                                 previous.SoftwareCollaborationWorld):
    def org_kind(self):
        return self._software()["case"]["fixed_organization"]["id"]

    def org_state(self):
        state = self._software()["organization_state"]
        if state["version"] != VERSION or state["organization_id"] != self.org_kind():
            raise ValueError("Organization state and frozen case disagree")
        return state

    def org_reject(self, message, code="organization_contract"):
        raise ToolRejection(message, code=code, category="business_constraint")

    def org_event(self, actor, kind, **facts):
        if actor not in self._software()["case"]["active_roles"]:
            raise ValueError("Only registered members may publish organizational decisions")
        return self._event(actor, ORG_EVENT_PREFIX + kind,
                           organization_id=self.org_kind(), **facts)

    def org_current_identity(self, actor):
        artifact, version, bundle = self._bundle(actor)
        return {"source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
                "files_sha256": digest(json_bytes(bundle["files"])),
                "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"]))}

    def org_patch_identity(self, patch_id):
        patch = self._patch(patch_id)
        return {key: copy.deepcopy(patch[key]) for key in
                ("source_reference", "files_sha256", "entry_metadata_sha256")}

    def org_matches_current(self, actor, patch_id):
        current, patch = self.org_current_identity(actor), self.org_patch_identity(patch_id)
        return all(current[key] == patch[key] for key in
                   ("files_sha256", "entry_metadata_sha256"))

    def org_latest_test(self, actor, patch_id):
        """Let the caller publish only its own actual same-version test evidence."""
        current = self.org_current_identity(actor)
        if not self.org_matches_current(actor, patch_id):
            self.org_reject("Your tested working tree must match the fixed candidate",
                            "organization_test_candidate")
        for event in reversed(self.state["software_events"]):
            if (event["kind"] == "test" and event["actor_id"] == actor
                    and event.get("executed") is True
                    and all(event.get(key) == value for key, value in current.items())):
                # Do not copy private test output, raw traces, or model history.
                return {"sequence": event["sequence"], "actor_id": actor,
                        "executed": True, "passed": event["passed"],
                        "patch_id": patch_id, **copy.deepcopy(current)}
        self.org_reject("Run a real public test on this exact working version before "
                        "publishing its test evidence", "organization_test_evidence")

    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()["case"]) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        # Schema/identity checks precede any protocol mutation or artifact lookup.
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only the fixed registered members may act")
        if tool not in previous.FORBIDDEN_TOOLS and tool not in previous.DYNAMIC_TOOLS:
            definitions = {row["name"]: row for row in self._tool_definitions(project_id)}
            if tool not in definitions:
                self.org_reject("Tool is not in this organization's public interface", "tool_not_enabled")
            errors = _schema_errors(definitions[tool]["parameters"], arguments)
            if errors:
                raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
            self._org_guard_governance(actor, tool, arguments)
            self._org_guard_flow(actor, tool, arguments)
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def organization_active_members(self):
        """Eligibility only; no work, synthetic member or phase is created."""
        self.state = self.store.load()
        eligible = self._org_flow_active_members()
        members = tuple(self._software()["case"]["active_roles"])
        if eligible is None:
            return members
        if not set(eligible) <= set(members):
            raise ValueError("An organization phase exposed an unregistered member")
        return tuple(member for member in members if member in eligible)

    def consume_organization_opportunity(self, actor=None):
        """Persist an actual SDK opportunity; only a real boundary wakes waiters."""
        with self.store.lock():
            self.state = self.store.load()
            if self.fixed_candidates_closed:
                raise ValueError("No schedule bookkeeping after final candidate locking")
            members = self._software()["case"]["active_roles"]
            if actor is not None and actor not in members:
                raise ValueError("Opportunity must belong to a registered member")
            state = self.org_state()
            before = self._flow_boundary()
            state["opportunities_consumed"] += 1
            self._org_consume_opportunity()
            after = self._flow_boundary()
            event = None
            if before != after:
                ordinal = state["opportunities_consumed"]
                # A period actually elapsed. This is a trusted scheduling fact,
                # not a generated message, automatic review or completed task.
                event = {"sequence": len(self.state["software_events"]) + 1,
                    "actor_id": "operator", "kind": ORG_EVENT_PREFIX + "schedule_boundary",
                    "logical_time": self.state["clock"],
                    "operation_id": f"v104-schedule-opportunity:{ordinal}", "action_id": None,
                    "organization_id": self.org_kind(), "consumed_member": actor,
                    "opportunity_ordinal": ordinal, "before": before, "after": after,
                    "real_opportunity_elapsed": True, "automatic_work": False}
                self.state["software_events"].append(event)
            self.store.save(self.state)
            return {"opportunities_consumed": state["opportunities_consumed"],
                    "phase_before": before, "phase_after": after,
                    "boundary_event_sequence": event["sequence"] if event else None}

    def _flow_boundary(self):
        state = self.org_state()
        return {key: {field: value for field, value in state.get(key, {}).items()
                       if field in {"stage", "phase", "status", "cycle", "cycle_id"}}
                for key in ("pipeline", "sprint") if key in state}

    def reachable_events(self, member, after_sequence=0):
        rows = super().reachable_events(member, after_sequence)
        ids = {row["sequence"] for row in rows}
        rows += [copy.deepcopy(row) for row in self.state["software_events"]
                 if row["sequence"] > after_sequence and row["sequence"] not in ids
                 and row["actor_id"] != member and row["kind"].startswith(ORG_EVENT_PREFIX)]
        return sorted(rows, key=lambda row: row["sequence"])

    def _action_read_work_event(self, actor, project_id, sequence):
        event = next((row for row in self.state["software_events"] if row["sequence"] == sequence), None)
        if event and event["kind"].startswith(ORG_EVENT_PREFIX):
            return copy.deepcopy(event)
        return super()._action_read_work_event(actor, project_id, sequence)

    def _organization_overview(self):
        state = self.org_state()
        visible = {"version": VERSION, "organization_id": self.org_kind(),
                   "opportunities_consumed": state["opportunities_consumed"]}
        for key in ("chief", "review", "matrix", "pipeline", "sprint"):
            if key not in state:
                continue
            row = state[key]
            # Keep the actual phase/plan readable while large history/index maps
            # are accessed through the immutable public event directory.
            visible[key] = {field: copy.deepcopy(value) for field, value in row.items()
                            if not isinstance(value, (dict, list))}
            visible[key]["record_counts"] = {field: len(value) for field, value in row.items()
                                               if isinstance(value, (dict, list))}
        return visible

    def _action_org_status(self, actor, project_id, after_sequence=0, limit=12):
        rows = [row for row in self.state["software_events"]
                if row["sequence"] > after_sequence and row["kind"].startswith(ORG_EVENT_PREFIX)]
        fields = {"sequence", "kind", "actor_id", "task_id", "task_revision", "patch_id",
                  "decision_id", "recipient", "stage", "cycle", "decision", "proposal_revision"}
        selected = rows[:limit]
        return {"current": self._organization_overview(),
                "events": [{key: copy.deepcopy(value) for key, value in row.items() if key in fields}
                           for row in selected],
                "next_after_sequence": selected[-1]["sequence"] if len(rows) > limit else None,
                "complete": len(rows) <= limit,
                "read_exact_record": "read_work_event(sequence); organization records are public, private test bodies are not"}


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world = self._session._world
        value.update(profile=VERSION, interface_revision=VERSION, purpose=PURPOSE,
                     organization_protocol=world._organization_overview())
        value["scheduling"]["protocol"] = "v104-state-gated-fair-member-opportunities"
        return value


_namespace = clone_namespace(previous, VERSION=VERSION, PURPOSE=PURPOSE,
    get_organization=catalog.get_organization, validate_organization=catalog.validate_organization,
    SoftwareCollaborationWorld=SoftwareCollaborationWorld, SoftwareCollaborationPort=SoftwareCollaborationPort)
_raw_case_spec = _namespace["case_spec"]
_raw_member_instruction = _namespace["member_instruction"]


def case_spec(*args, **kwargs):
    case = _raw_case_spec(*args, **kwargs)
    case.update(scheduling_protocol="v104-state-gated-fair-member-opportunities",
                organization_protocol=VERSION,
                organizational_rules_are_enforced=True,
                organization_records_are_public=True)
    return case


def member_instruction(case, member):
    spec = case["fixed_organization"]
    task_guidance = (" PIPELINE, SPRINT and MATRIX require explicit public task records "
                     "for their organization protocol; a generic fix_patch(task_ids=[]) "
                     "does not bypass those handoff or confirmation requirements."
                     if spec["id"] in {"PIPELINE", "SPRINT", "MATRIX"} else "")
    return (_raw_member_instruction(case, member) + "\n\n" +
            spec["organization_instruction"] + task_guidance +
            "\nOrganization rules are enforced by the declared org_* tools. Read org_status "
            "for phase and record references, and read_work_event for their exact public content. "
            "A chat message cannot substitute for a decision, review, phase handoff or signature. "
            "Organization observations do not reveal private files or other members' private test output.")


_raw_build = _namespace["build_software_collaboration_case"]
# The imported wrappers above are bound after cloning to avoid recursively
# replacing the original implementation functions they deliberately reuse.
_namespace["case_spec"] = case_spec
_namespace["member_instruction"] = member_instruction
validate_case = _namespace["validate_case"]


def build_software_collaboration_case(*args, **kwargs):
    prepared = _raw_build(*args, **kwargs)
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        kind = world.org_kind()
        world._software()["organization_state"] = {
            "version": VERSION, "organization_id": kind, "opportunities_consumed": 0,
            **governance.initial_state(kind), **flow.initial_state(kind)}
        world.store.save(world.state)
    prepared.prefix["prepared_business_state_sha256"] = digest(json_bytes(initial_business_state(world)))
    prepared.prefix["organization_protocol"] = VERSION
    atomic_write(Path(world.store.root).parent / "preparation.json", json_bytes(prepared.prefix))
    return prepared
