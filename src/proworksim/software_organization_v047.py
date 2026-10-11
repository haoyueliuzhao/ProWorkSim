"""Isolated v047 architecture and staged-budget world over unchanged v045 business roots.

All work, adoption, public testing and submission still require native member tools.
No learner, model generation, private candidate search or automatic tree copy occurs here.
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import software_organization_v039 as previous
from . import software_organization_v045 as original
from .adapters.capabilities import encode
from .stage_budget_v047 import StageTestBudget, stage_plan
from .work_interface import _schema_errors
from .world_core import WorldCore
from . import software_organization_tasks_v045 as source
from . import software_organization_v042 as paged
from .harness_policy_v040 import FORBIDDEN_TOOLS
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-organization-v0.47"
INTERFACE_REVISION = "architecture-efficiency-staged-organization-v0.47"
CONTRACT_VERSION = "architecture-efficiency-business-contract-v0.47"
PURPOSE = "organization_development"
CONDITIONS = ("S1", "D2", "D4", "I2", "I4", "P2", "P4")
CASE_IDS = TASK_IDS = source.TASK_IDS
PROJECT, ROOT_GOAL_ID, MEMBERS = previous.PROJECT, previous.ROOT_GOAL_ID, previous.MEMBERS[:4]
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = "v047-forward-stages-fair-native-member-opportunities"
PAGING_VERSION = paged.PAGING_VERSION
PAGE_BODY_CHARACTERS = paged.PAGE_BODY_CHARACTERS
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
TestBudget = previous.TestBudget
TOOLS = copy.deepcopy(paged.TOOLS)


def material(case_id):
    return source.build_case(case_id)


def case_spec(
    case_id=CASE_IDS[0],
    *,
    condition="S1",
    team_token_budget=250000,
    first_member=None,
    role_decision_limits=None,
):
    if condition not in CONDITIONS:
        raise ValueError("Declare one of the seven v047 architectures")
    stages = stage_plan(condition, team_token_budget)
    dynamic = condition.startswith("D")
    count = int(condition[1])
    active = list(MEMBERS[: 1 if dynamic else count])
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, 128)
    if first not in stages[0]["members"] or first not in active:
        raise ValueError("The first member must be initially runnable")
    if role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Member fixed decision bounds do not grant a second team allowance")
    # Copy only the unchanged business/source contract; construct a new exact case.
    value = original.case_spec(case_id, condition="S1")
    value.update(
        version=VERSION,
        condition=condition,
        public_condition="dynamic"
        if dynamic
        else "independent"
        if condition.startswith("I")
        else "pipeline"
        if condition.startswith("P")
        else "single",
        organization_level=condition,
        task_type="architecture_efficiency_pilot",
        active_roles=active,
        role_decision_limits=limits,
        team_limits={**TEAM_LIMITS, "max_total_tokens": team_token_budget},
        first_member=first,
        scheduling_protocol=SCHEDULER,
        interface_revision=INTERFACE_REVISION,
        stage_plan=stages,
        architecture_policy_version=VERSION,
        member_limits={
            "initial_members": len(active),
            "max_live_members": count,
            "max_cumulative_births": count,
            "births_enabled": dynamic,
            "waiting_counts_as_live": True,
            "fixed_means_fixed_birth_set": not dynamic,
            "voluntary_retirement_allowed": True,
            "retired_ids_reused": False,
        },
        responsibility_scope="Free native organization"
        if condition[0] in "SD"
        else "Predeclared artificial architecture stages",
        external_intervention={
            "enabled": False,
            "maximum_events": 0,
            "scope": "No external births in v047",
        },
        architecture_contract={
            "selector_member": MEMBERS[0] if condition.startswith("I") else None,
            "candidate_rule": "Last fixed generation patch per initial member, if any",
            "only_final_stage_may_submit": True,
            "unused_allowance": "forward_only",
            "no_automatic_working_tree_copy": True,
            "private_report_owner_only": True,
            "artificial_policy_is_not_claimed_optimal": True,
        },
    )
    return value


def validate_case(case):
    try:
        expected = case_spec(
            case["case_id"],
            condition=case["condition"],
            team_token_budget=case["team_limits"]["max_total_tokens"],
            first_member=case["first_member"],
            role_decision_limits=case["role_decision_limits"],
        )
    except (KeyError, TypeError) as error:
        raise ValueError("Declare an exact v047 case, architecture and real team budget") from error
    if expected != case:
        raise ValueError("Frozen v047 business, architecture, stage plan or quota changed")
    return case


def member_instruction(case, *, briefing="", born=False, origin=None):
    limits, condition = case["team_limits"], case["condition"]
    instruction = (
        "Complete the immutable public root contract using the actual public APIs. "
        "Each logical member has its own private workspace and session; all use one frozen actor. "
        f"The effective ONE team allowance is {limits['max_total_tokens']} actual input+output tokens, "
        "128 decisions, 128 attempts and 32 public test calls, including all members and all stages. "
        "Birth, retirement, stage changes and waiting never renew this allowance. "
        "Private histories and test reports are not copied. Fixed published trees may be explicitly read, "
        "merged with integrate_patch when permitted, or exactly restored with adopt_candidate. "
        "adopt_candidate is a real tool action replacing your entire files map with that legal fixed tree; "
        "it does not test, fix your new version or submit. write_file replaces a full file; replace_file changes one exact match. "
        "To submit, execute your own real public tests on your exact current version, publish a fixed patch "
        "of that same version, then call submit_integration. Public passing is not required by the submit gate. "
        "Submission is not private acceptance and does not end work automatically; only the last fixed delivery is assessed. "
        "staff_done or retire_member permanently retires you from every later stage. "
        "staff_wait suspends until a legally reachable event and does not perform work. "
    )
    if condition[0] in "SD":
        instruction += (
            "Choose your own work, tasks, sharing and division of responsibility. No roles are assigned. "
            "Member limits state the available cumulative positions; D may freely choose fewer members, including one. "
            "Only native spawn_member creates a new session, with no copied private history or extra budget. "
        )
    elif condition.startswith("I"):
        instruction += (
            "This is independent candidate generation followed by paid selection by the existing member_001. "
            "During generate, each member receives an equal part of 70% team tokens, 88 decisions/attempts and 24 tests; "
            "cross-member code, reports, messages and tasks are unavailable. Fix your chosen candidate and call finish_stage "
            "to finish only this phase without retirement. The last fixed generation patch per member becomes its candidate. "
            "Unused generator allowances move only to selection, never to another generator. Selection reserves at least "
            "30% tokens, 40 decisions/attempts and 8 tests. member_001 retains its existing session and may inspect/adopt "
            "and test multiple legal fixed candidates, but may not edit or merge them. Its final submitted files must "
            "exactly equal its most recently adopted generation candidate. No hidden selector or private candidate evaluation exists. "
        )
    else:
        roles = (
            "member_001 implements; member_002 reviews, revises and submits. Token shares 60%/40%, "
            "decisions/attempts 76/52, tests 20/12."
            if condition == "P2"
            else "member_001 implements; member_002 independently reviews without editing; member_003 revises and integrates; "
            "member_004 performs final validation and submission without editing. Token shares 35%/20%/25%/20%, "
            "decisions/attempts 44/26/32/26, tests 8/8/8/8."
        )
        instruction += (
            "This is a fixed sequential pipeline. "
            + roles
            + " All members exist initially, but only the current stage member acts. Explicitly adopt legal fixed predecessor "
            "work, read addressed review messages, and do the assigned work. Review/final validation may adopt and test "
            "a fixed tree but cannot edit or merge. Fixed trees and messages survive author retirement. "
            "Call finish_stage to finish only your stage; unused tokens, decisions, attempts and tests move only forward. "
            "Earlier stages may fix work but cannot submit. No file transfer, test, revision or submission happens automatically. "
        )
    instruction += "Your observation declares current stage, runnable members, permissions and remaining stage resources."
    if briefing:
        instruction += "\nActual briefing from the member who created you:\n" + briefing
    return instruction + paged.PAGING_INSTRUCTION


_TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
TOOLS += [
    {
        "name": "finish_stage",
        "description": "Finish your current artificial architecture stage without retiring. No work is copied or performed; later stages still require their own budgeted actions.",
        "parameters": {
            "type": "object",
            "properties": {"reason": _TEXT},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "adopt_candidate",
        "description": "Explicitly replace your complete working files with one legally readable fixed patch. Exact snapshot adoption, not three-way merge. No test, fix or submission is performed. I selection accepts only its frozen generation candidates.",
        "parameters": {
            "type": "object",
            "properties": {"patch_id": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["patch_id"],
            "additionalProperties": False,
        },
    },
]
_FILE_TOOLS = {
    "list_files",
    "read_file",
    "search_file",
    "write_file",
    "replace_file",
    "diff_workspace",
    "run_tests",
    "read_test_result",
    "fix_patch",
    "finish_stage",
    "retire_member",
}


class SoftwareCollaborationWorld(original.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return (
            copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)
        )

    def stage_state(self):
        facts = self._software()
        state = copy.deepcopy(facts["architecture"])
        stage = facts["case"]["stage_plan"][state["stage_index"]]
        state.update(
            stage_members=list(stage["members"]),
            final_stage=stage["submit_allowed"],
            condition=facts["case"]["condition"],
            live_members=self.live_members(),
        )
        return state

    def bind_stage_budget(self, budget):
        self.stage_budget = budget
        self.model_budget_snapshot = budget.snapshot

    def runnable_members(self):
        state = self.stage_state()
        if state["closed"]:
            return []
        return [
            member
            for member in self.live_members()
            if member in state["stage_members"]
            and member not in state["finished_members"]
            and member not in state["unavailable_members"]
        ]

    def allowed_tools(self, member):
        case, state = self._software()["case"], self.stage_state()
        if member not in self.runnable_members():
            return []
        names = {tool["name"] for tool in TOOLS}
        condition = case["condition"]
        if condition[0] in "SD":
            names.discard("finish_stage")
            if condition == "S1":
                names.discard("spawn_member")
        elif condition.startswith("I"):
            names = set(_FILE_TOOLS)
            if state["stage_id"] == "select":
                names -= {"write_file", "replace_file"}
                names |= {"adopt_candidate", "submit_integration", "read_work_event"}
        else:
            names.discard("spawn_member")
            if state["stage_id"] in {"review", "validate_submit"}:
                names -= {"write_file", "replace_file", "integrate_patch"}
        if not state["final_stage"]:
            names.discard("submit_integration")
        return sorted(names)

    def architecture_snapshot(self, member=None):
        state = self.stage_state()
        value = {
            **state,
            "runnable_members": self.runnable_members(),
            "stage_plan": copy.deepcopy(self._software()["case"]["stage_plan"]),
        }
        value.pop("history", None)
        if member is not None:
            value.update(
                allowed_tools=self.allowed_tools(member),
                stage_test_budget=self.test_budget.stage_snapshot(member),
            )
            if hasattr(self, "stage_budget"):
                value["stage_model_budget"] = self.stage_budget.stage_snapshot(member)
            value["candidates"] = self.visible_patches(member)
        return value

    def visible_patches(self, member):
        facts, state = self._software(), self.stage_state()
        rows = list(facts["patches"].values())
        if facts["case"]["condition"].startswith("I"):
            if state["stage_id"] == "generate":
                rows = [row for row in rows if row["author"] == member]
            else:
                rows = [
                    row
                    for row in rows
                    if row["patch_id"] in state["candidate_patch_ids"] or row["author"] == member
                ]
        return copy.deepcopy(rows)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection(
                "Controller operations are not member tools",
                code="forbidden_controller_request",
                category="policy_error",
                context={"process_violation": True},
            )
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only live registered members may act")
        definitions = {item["name"]: item for item in TOOLS}
        if tool not in definitions:
            raise ToolRejection(
                "Not in the v047 interface", code="tool_not_enabled", category="capability_gap"
            )
        errors = _schema_errors(definitions[tool]["parameters"], arguments)
        for name, schema in definitions[tool]["parameters"].get("properties", {}).items():
            value = arguments.get(name)
            if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
                errors.append(name + " exceeds its declared text limit")
            if (
                isinstance(value, list)
                and schema.get("uniqueItems")
                and all(isinstance(item, str) for item in value)
                and len(value) != len(set(value))
            ):
                errors.append(name + " must contain distinct items")
        if errors:
            raise ToolRejection(
                "; ".join(errors), code="public_argument_schema", category="policy_error"
            )
        if tool not in self.allowed_tools(actor):
            raise ToolRejection(
                "This operation is unavailable in your current architecture stage",
                code="architecture_stage_permission",
                category="capability_gap",
            )
        return WorldCore._tool_project_action(
            self, actor, project_id, tool, arguments, interface_profile
        )

    def _event(self, actor, kind, **facts):
        facts.setdefault("stage_id", self.stage_state()["stage_id"])
        return super()._event(actor, kind, **facts)

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        result = super()._action_fix_patch(actor, project_id, task_ids, message)
        result["stage_id"] = self.stage_state()["stage_id"]
        self._software()["patches"][result["patch_id"]]["stage_id"] = result["stage_id"]
        return result

    def _share_fixed(self, actor, reference):
        facts, state = self._software(), self.stage_state()
        legal = list(MEMBERS[: facts["case"]["member_limits"]["max_cumulative_births"]])
        if facts["case"]["condition"].startswith("I"):
            legal = [actor] if state["stage_id"] == "generate" else [MEMBERS[0]]
        self.state["shares"].append(
            {
                "project_id": PROJECT,
                **reference,
                "actor_ids": legal,
                "shared_by": actor,
                "at": self.state["clock"],
            }
        )

    def _bundle(self, actor, *, patch_id=None, reference=None, write=False, baseline=False):
        if patch_id is not None and self._software().get("architecture"):
            if patch_id not in {row["patch_id"] for row in self.visible_patches(actor)}:
                raise ToolRejection(
                    "This fixed patch is not available to your stage",
                    code="architecture_patch_not_readable",
                    category="capability_gap",
                )
        return super()._bundle(
            actor, patch_id=patch_id, reference=reference, write=write, baseline=baseline
        )

    def _available_recipient(self, actor, recipient):
        if self._software()["case"]["condition"].startswith("P"):
            if recipient == actor or recipient not in self.live_members():
                raise ValueError(
                    "Choose another live pipeline member; inactive future stages may receive messages"
                )
            return
        return super()._available_recipient(actor, recipient)

    def reachable_events(self, member, after_sequence=0):
        rows = super().reachable_events(member, after_sequence)
        if self._software()["case"]["condition"].startswith("I"):
            visible = {row["patch_id"] for row in self.visible_patches(member)}
            rows = [
                row
                for row in rows
                if row["kind"] == "patch_fixed" and row.get("patch_id") in visible
            ]
        return rows

    def _action_read_work_event(self, actor, project_id, sequence):
        if self._software()["case"]["condition"].startswith("I"):
            rows = [row for row in self.state["software_events"] if row["sequence"] == sequence]
            allowed = {row["patch_id"] for row in self.visible_patches(actor)}
            if (
                not rows
                or rows[0]["kind"] != "patch_fixed"
                or rows[0].get("patch_id") not in allowed
            ):
                raise ToolRejection(
                    "Independent candidates share only fixed candidate metadata",
                    code="architecture_event_not_readable",
                    category="capability_gap",
                )
            return copy.deepcopy(rows[0])
        return super()._action_read_work_event(actor, project_id, sequence)

    def _action_finish_stage(self, actor, project_id, reason):
        if not reason.strip():
            raise ValueError("Explain finishing the current stage")
        state = self._software()["architecture"]
        state["finished_members"].append(actor)
        event = self._event(
            actor,
            "stage_finished",
            stage_id=state["stage_id"],
            reason=reason,
            permanent_retirement=False,
            work_performed_automatically=False,
        )
        return {
            "stage_id": state["stage_id"],
            "member_id": actor,
            "status": "stage_complete",
            "event_sequence": event["sequence"],
            "permanent_retirement": False,
        }

    def finish_member_stage(
        self, member, reason, *, origin="runtime", unavailable=False, receipt=None
    ):
        """Record a host scheduling boundary without inventing a model action."""
        with self.store.lock():
            self.state = self.store.load()
            state = self._software()["architecture"]
            if member not in self._software()["registry"]:
                raise ValueError("A host stage boundary requires a real registered member")
            if member not in state["finished_members"]:
                state["finished_members"].append(member)
            if unavailable and member not in state["unavailable_members"]:
                state["unavailable_members"].append(member)
            state["history"].append(
                {
                    "kind": "host_stage_finished",
                    "stage_id": state["stage_id"],
                    "member_id": member,
                    "reason": reason,
                    "origin": origin,
                    "unavailable_in_later_stages": unavailable,
                    "model_generated": False,
                    "runtime_receipt": copy.deepcopy(receipt),
                }
            )
            self.store.save(self.state)
        return self.stage_state()

    def advance_stage(self):
        """Host-only phase release. Caller must not invoke after its soft deadline."""
        with self.store.lock():
            self.state = self.store.load()
            facts, state = self._software(), self._software()["architecture"]
            if state["closed"] or self.runnable_members():
                return False
            if hasattr(self, "stage_budget"):
                self.stage_budget.assert_transition_ready()
            index = state["stage_index"]
            if facts["case"]["condition"][0] in "SD":
                state["closed"] = True
            elif index + 1 == len(facts["case"]["stage_plan"]):
                state["closed"] = True
            else:
                old = state["stage_id"]
                if facts["case"]["condition"].startswith("I") and old == "generate":
                    latest = {}
                    for patch in facts["patches"].values():
                        if patch["stage_id"] == "generate":
                            latest[patch["author"]] = patch
                    state["candidate_patch_ids"] = [
                        latest[member]["patch_id"]
                        for member in facts["case"]["active_roles"]
                        if member in latest
                    ]
                    for patch_id in state["candidate_patch_ids"]:
                        self.state["shares"].append(
                            {
                                "project_id": PROJECT,
                                **facts["patches"][patch_id]["source_reference"],
                                "actor_ids": [MEMBERS[0]],
                                "shared_by": "operator",
                                "at": self.state["clock"],
                                "origin": "predeclared_candidate_release",
                                "no_working_tree_copy": True,
                            }
                        )
                state.update(
                    stage_index=index + 1,
                    stage_id=facts["case"]["stage_plan"][index + 1]["stage_id"],
                    finished_members=[],
                )
                state["history"].append(
                    {
                        "kind": "stage_transition",
                        "from_stage": old,
                        "to_stage": state["stage_id"],
                        "model_generated": False,
                        "working_trees_copied": 0,
                        "new_budget_granted": 0,
                    }
                )
            self.store.save(self.state)
        return True

    def _action_adopt_candidate(self, actor, project_id, patch_id):
        facts, state = self._software(), self.stage_state()
        if (
            facts["case"]["condition"].startswith("I")
            and patch_id not in state["candidate_patch_ids"]
        ):
            raise ValueError("Select only a frozen generation candidate")
        patch = self._patch(patch_id)
        _, _, incoming = self._bundle(actor, patch_id=patch_id)
        if digest(json_bytes(incoming["files"])) != patch["files_sha256"]:
            raise RuntimeError("Fixed candidate files differ from their published identity")
        artifact, version, _ = self._bundle(actor, write=True)
        bundle = copy.deepcopy(incoming)
        bundle["included_patch_ids"] = sorted(set(bundle["included_patch_ids"]) | {patch_id})
        dependencies = [
            self._patch(pid)["source_reference"]
            for pid in bundle["included_patch_ids"]
            if self._patch(pid)["source_reference"]["object_id"] != artifact["artifact_id"]
        ]
        reference = self._save_content(
            actor, PROJECT, artifact, encode("json", bundle), dependencies
        )
        binding = {
            "patch_id": patch_id,
            "author": patch["author"],
            "source_reference": patch["source_reference"],
            "files_sha256": patch["files_sha256"],
        }
        if facts["case"]["condition"].startswith("I"):
            facts["architecture"]["selected_candidate"] = copy.deepcopy(binding)
        event = self._event(
            actor,
            "candidate_adopted",
            patch_id=patch_id,
            stage_id=state["stage_id"],
            input_reference=patch["source_reference"],
            previous_reference=previous.previous.base._reference(artifact, version),
            source_reference=reference,
            files_sha256=digest(json_bytes(bundle["files"])),
            selected_candidate_files_sha256=patch["files_sha256"],
            candidate_binding=binding,
            exact_files_match=True,
            native_model_action=True,
            test_performed=False,
            submitted=False,
        )
        return {
            key: copy.deepcopy(event[key])
            for key in (
                "patch_id",
                "source_reference",
                "files_sha256",
                "candidate_binding",
                "exact_files_match",
            )
        }

    def _action_submit_integration(self, actor, project_id, message=""):
        facts, state = self._software(), self.stage_state()
        if not state["final_stage"]:
            raise ValueError("Only the final architecture stage may submit")
        if facts["case"]["condition"].startswith("I"):
            binding = state["selected_candidate"]
            _, _, bundle = self._bundle(actor)
            if binding is None or digest(json_bytes(bundle["files"])) != binding["files_sha256"]:
                raise ValueError(
                    "Final I files must exactly equal the explicitly selected fixed candidate"
                )
        result = super()._action_submit_integration(actor, project_id, message)
        if facts["case"]["condition"].startswith("I"):
            result["candidate_binding"] = copy.deepcopy(state["selected_candidate"])
            facts["deliveries"][-1]["candidate_binding"] = copy.deepcopy(
                state["selected_candidate"]
            )
            self.state["software_events"][-1]["candidate_binding"] = copy.deepcopy(
                state["selected_candidate"]
            )
        return result


class SoftwareCollaborationPort(original.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world, member = self._session._world, self.role
        facts, case = world._software(), world._software()["case"]
        architecture = world.architecture_snapshot(member)
        # One complete legal fixed-patch catalog is sufficient in the model
        # observation. The host snapshot retains its original complete copy.
        patches = architecture.pop("candidates")
        architecture["fixed_patch_catalog_field"] = "patches"
        value.update(
            interface_revision=INTERFACE_REVISION,
            profile=self.profile,
            architecture=architecture,
            patches=patches,
            shared_resource_limits=copy.deepcopy(case["team_limits"]),
        )
        value["execution_condition"].update(
            condition=case["condition"],
            active_executors=world.runnable_members(),
            preassigned_tasks_or_manager=case["condition"][0] in "IP",
        )
        value["scheduling"].update(
            protocol=SCHEDULER,
            finish_stage="End only this stage without retirement; no automatic work or free resources",
            done="Permanent retirement from all later stages; never restores a selector",
        )
        if case["condition"].startswith("I"):
            # Registry prose (for example a retirement reason) can contain work
            # content. Only mechanical membership facts cross independent branches.
            value["member_registry"] = {
                member_id: {key: row[key] for key in ("member_id", "birth_index", "status")}
                for member_id, row in value["member_registry"].items()
            }
            value.update(
                tasks={},
                transfer_offers={},
                orphan_obligations=[],
                handoffs=[],
                task_event_sequences=[],
                organization_event_sequences=[],
            )
            value["task_formation"].update(tasks_created=0, level="isolated_candidates")
            value["deliveries"] = [
                copy.deepcopy(row) for row in facts["deliveries"] if row["actor_id"] == member
            ]
        return value


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    bundle = {"files": material(case["case_id"])["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [
        {
            "alias": "baseline",
            "filename": "baseline.json",
            "kind": "json",
            "owner": "operator",
            "readers": [*active, "operator"],
            "writers": ["operator"],
            "data": bundle,
        }
    ]
    objects.extend(
        {
            "alias": member,
            "filename": member + ".json",
            "kind": "json",
            "owner": member,
            "readers": [member, "operator"],
            "writers": [member],
            "data": copy.deepcopy(bundle),
        }
        for member in active
    )
    package = {
        "project_id": PROJECT,
        "goal": case["root_goal"],
        "participants": [*active, "operator"],
        "objects": objects,
        "works": [],
        "grants": [],
        "provenance": {
            "kind": "synthetic",
            "note": "Artificially derived organization-development roots; public initial defects/facts are environment preparation, not assigned member work",
        },
    }
    spec = {
        "version": SCENARIO_VERSION,
        "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {
            "world_id": "software-organization-v047",
            "actors": {actor: {} for actor in (*active, "operator")},
            "applications": ["files"],
            "publication_policy": "explicit",
            "bootstrap_grants": [
                {"actor_id": "operator", "power": "install_project", "scope": "world"}
            ],
        },
        "installer": "operator",
        "projects": [{"package": package}],
        "roles": [
            {
                "role_id": member,
                "actor": member,
                "project": PROJECT,
                "policy": "model",
                "config": {"task": member_instruction(case)},
            }
            for member in active
        ],
        "setup": [],
        "events": [],
        "start": {"kind": "initial"},
        "boundary": {
            "max_opportunities": TEAM_LIMITS["max_decisions"]
            + case["member_limits"]["max_cumulative_births"]
        },
    }
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.test_budget = StageTestBudget(
        root / "team-test-budget.json",
        stage_provider=world.stage_state,
        stage_plan=case["stage_plan"],
    )
    preparation = source.prepare_initial_diagnostics(
        case["case_id"], run_root=root / "environment-preparation"
    )
    if preparation["initial_files_sha256"] != digest(json_bytes(bundle["files"])):
        raise ValueError(
            "Initial diagnostic facts must identify the exact installed baseline files"
        )
    with world.store.lock():
        world.state = world.store.load()
        baseline, baseline_version, _ = world._bundle(active[0], baseline=True)
        reference = previous.previous.base._reference(baseline, baseline_version)
        reports = {
            row["diagnostic_id"]: {
                **copy.deepcopy(row),
                "source_reference": copy.deepcopy(reference),
                "initial_source_reference": copy.deepcopy(reference),
                "initial_report": True,
            }
            for row in (preparation["diagnostic_a"], preparation["diagnostic_b"])
        }
        ids = [preparation[key]["diagnostic_id"] for key in ("diagnostic_a", "diagnostic_b")]
        assignments = {member: list(ids) for member in active}
        world.state["shares"].append(
            {
                "project_id": PROJECT,
                **reference,
                "actor_ids": list(MEMBERS[: case["member_limits"]["max_cumulative_births"]]),
                "shared_by": "operator",
                "at": world.state["clock"],
            }
        )
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {
            "case": case,
            "tasks": {},
            "patches": {},
            "deliveries": [],
            "initial_public_feedback": None,
            "architecture": {
                "stage_index": 0,
                "stage_id": case["stage_plan"][0]["stage_id"],
                "finished_members": [],
                "unavailable_members": [],
                "candidate_patch_ids": [],
                "selected_candidate": None,
                "history": [],
                "closed": False,
            },
            "transfer_offers": {},
            "test_reports": {},
            "initial_diagnostics": reports,
            "initial_diagnostic_assignments": assignments,
            "environment_preparation_provenance": copy.deepcopy(
                preparation["preparation_provenance"]
            ),
            "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
            "registry": {
                member: {
                    "member_id": member,
                    "birth_index": index + 1,
                    "status": "live",
                    "born_by": None,
                    "origin": "initial_configuration",
                    "briefing": "",
                    "model_generated_briefing": False,
                    "initial_source_reference": copy.deepcopy(reference),
                    "initial_patch_id": None,
                    "replaces": None,
                    "birth_sequence": 0,
                    "private_history_copied": False,
                }
                for index, member in enumerate(active)
            },
        }
        world.store.save(world.state)
    prefix = {
        "version": VERSION,
        "usage": PURPOSE,
        "preparation_credit": False,
        "test_feedback_protocol": PAGING_VERSION,
        "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"],
        "initial_binding": case["initial_binding"],
        "condition": case["condition"],
        "information_condition": case["information_condition"],
        "framing_condition": case["framing_condition"],
        "actual_work_copy_count": len(active),
        "initial_diagnostic_assignments": assignments,
        "environment_preparation_provenance": copy.deepcopy(preparation["preparation_provenance"]),
        "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
        "training_eligible": False,
        "independent_confirmation_eligible": False,
        "actor_trajectories_created": False,
        "predefined_execution_tasks": False,
        "initial_diagnostics_are_member_work": False,
        "actor_test_budget_charged_for_preparation": False,
    }
    prepared = PreparedOnlineCase(
        deployment,
        case,
        {
            "version": VERSION,
            "training_supported": False,
            "purpose": PURPOSE,
            "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
            "independent_assessment": "assess_software_collaboration",
            "runtime_process_contract": case["process_contract"],
        },
        prefix,
    )
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def assess_software_collaboration(prepared, *, run_root):
    """Raw last-fixed-tree quality only; runtime process gating is separate."""
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = world._software()
    common = {
        "version": VERSION,
        "usage": PURPOSE,
        "purpose": PURPOSE,
        "training_eligible": False,
        "contribution_eligible": False,
        "independent_confirmation_eligible": False,
        "contract_version": CONTRACT_VERSION,
        "source_contract": case["source_contract"],
        "condition": case["condition"],
    }
    if not facts["deliveries"]:
        return {
            **common,
            "status": "evaluable",
            "R": 0,
            "submitted": False,
            "complete_delivery": False,
            "content_correct": None,
            "required_process_satisfied": None,
            "process_observation_complete": None,
            "reason": "No fixed delivery; mutable workspaces are not independently assessed",
        }
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = source.assess_files(case["case_id"], bundle["files"], run_root=run_root)
    return {
        **common,
        **result,
        "version": VERSION,
        "usage": PURPOSE,
        "purpose": PURPOSE,
        "status": "evaluable" if result["executed"] else "unknown",
        "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None,
        "submitted": True,
        "delivery": delivery,
        "source_reference": delivery["source_reference"],
        "files_sha256": delivery["files_sha256"],
    }
