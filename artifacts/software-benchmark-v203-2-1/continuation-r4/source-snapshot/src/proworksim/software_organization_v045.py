"""v045 frozen organization diagnostics on four newly declared business roots.

S1 has one real actor/session/workspace, F2 a fixed birth set of two, and O3
starts at two with four live and six cumulative identities. All receive the
same public initial facts and neutral instruction. v044 feedback and v042
exact paging are inherited unchanged; no compatibility alias changes old runs.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_organization_v039 as previous
from . import software_organization_tasks_v045 as source
from . import software_organization_v040 as base
from . import software_organization_v042 as paged
from .harness_policy_v040 import FORBIDDEN_TOOLS, POLICY as ACTION_ERROR_POLICY
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-organization-v0.45"
INTERFACE_REVISION = "shared-facts-neutral-organization-regimes-v0.45"
CONTRACT_VERSION = "derived-business-organization-diagnostic-v0.45"
PURPOSE = "organization_development"
CONDITIONS = ("S1", "F2", "O3")
CASE_IDS = TASK_IDS = source.TASK_IDS
PROJECT, ROOT_GOAL_ID, MEMBERS = previous.PROJECT, previous.ROOT_GOAL_ID, previous.MEMBERS
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = base.SCHEDULER
PAGING_VERSION = paged.PAGING_VERSION
PAGE_BODY_CHARACTERS = paged.PAGE_BODY_CHARACTERS
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
TestBudget = previous.TestBudget
TOOLS = copy.deepcopy(paged.TOOLS)


def material(case_id):
    return source.build_case(case_id)


def case_spec(case_id=CASE_IDS[0], *, condition="S1", first_member=None, role_decision_limits=None):
    if condition not in CONDITIONS:
        raise ValueError("Declare one v045 organization regime: S1, F2 or O3")
    value = material(case_id)
    active = list(MEMBERS[:1 if condition == "S1" else 2])
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Only an actual initial member may start; all members share the unchanged team pool")
    dynamic = condition == "O3"
    return {"version": VERSION, "case_id": value["task_id"], "task_id": value["task_id"],
        "family": source.NAMES[value["task_id"]], "constraint_family": source.FAMILIES[value["task_id"]],
        "condition": condition, "public_condition": "dynamic" if dynamic else "fixed",
        "organization_level": "dynamic" if dynamic else "fixed",
        "information_condition": "shared", "framing_condition": "neutral",
        "task_type": "new_root_organization_diagnostic", "category": PURPOSE, "purpose": PURPOSE, "usage": PURPOSE,
        "split": PURPOSE, "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "active_roles": active, "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS),
        "first_member": first, "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_protocol": member_test_specification(),
        "member_limits": {"initial_members": len(active), "max_live_members": 4 if dynamic else len(active),
            "max_cumulative_births": 6 if dynamic else len(active), "births_enabled": dynamic,
            "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": not dynamic,
            "voluntary_retirement_allowed": True, "retired_ids_reused": False},
        "external_intervention": {"enabled": False, "maximum_events": 0, "scope": "No external births in v045"},
        "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
        "process_contract": {"forbidden_member_tools": sorted(FORBIDDEN_TOOLS),
            "blocked_controller_request_is_process_violation": True, "process_violation_formal_R": 0,
            "critical_integrity_failure_remains_unknown": True},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.previous.task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Member-created work and consent-based transfers; public initial facts confer no assigned roles",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution", "no_forbidden_controller_request"],
        "public_feedback_protocol": "same_public_checks_with_both_public_initial_diagnostic_groups",
        "newborn_initial_facts": "Same public environment facts; not copied private history or current member work",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], condition=case["condition"], first_member=case["first_member"],
            role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact v045 new root and organization regime") from error
    if case != expected:
        raise ValueError("The frozen v045 source, organization regime, public information or budget changed")
    return case


def member_instruction(case, *, briefing="", born=False, origin=None):
    # Identical neutral capability prose in all three regimes. Actual membership
    # is the public registry/limits, never a prose-assigned manager or role.
    return base.member_instruction(case, briefing=briefing, born=born, origin=origin) + paged.PAGING_INSTRUCTION


class _PublicTaskWorld(base.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations are not enabled in the v045 member world",
                code="forbidden_controller_request", category="policy_error", context={"process_violation": True})
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_controller_add_neutral_member(self, actor, project_id, completed_team_decisions):
        raise ValueError("v045 has no external-birth controller operation")

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        public = source.run_public_tests(self._software()["case"]["case_id"], bundle["files"],
                                        run_root=self.store.root / "software-execution/public")
        reference = previous.previous.base._reference(artifact, version)
        groups = {name: {**copy.deepcopy(group), "passed": group["passed"] if group["executed"] else None}
                  for name, group in public["groups"].items()}
        member = previous.previous.previous.member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution/member")
        diagnostics = {key: {**copy.deepcopy(row), "source_reference": copy.deepcopy(reference),
            "origin": "member_public_test_execution", "initial_report": False}
            for key, row in public["public_diagnostics"].items()}
        result = {"groups": {**groups, "member_tests": member}, "public_execution": public,
            "public_diagnostics": diagnostics,
            "passed": all(group["passed"] is True for group in groups.values()) and member["passed"] is not False,
            "executed": all(group["executed"] for group in groups.values()),
            "source_reference": reference, "source_sha256": digest(json_bytes(bundle)),
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "derived-root-public-diagnostics-and-member-v0.45",
            "untested": [name for name, group in {**groups, "member_tests": member}.items() if group["status"] == "untested"]
                + ["independent_acceptance", "full_upstream_suite"],
            "scope": "All members can execute these same public checks and obtain both diagnostic groups",
            "independent_acceptance": "not_run_by_public_tool", "fixed_submission_is_acceptance": False,
            "team_test_budget": self.test_budget.snapshot()}
        self._event(actor, "test", **result)
        projected = previous.previous.previous.project_public_test_feedback(result)
        # Retain exact public facts even if an inherited projection recognizes
        # only the old ordinary test groups.
        projected["public_diagnostics"] = copy.deepcopy(diagnostics)
        return projected


class SoftwareCollaborationWorld(paged.SoftwareCollaborationWorld, _PublicTaskWorld):
    # The paging method calls super() into _PublicTaskWorld for the new business
    # checks; report construction/read permission use the unmodified v042 code.
    def _action_spawn_member(self, actor, project_id, briefing, patch_id=None, replaces=None):
        record = super()._action_spawn_member(actor, project_id, briefing, patch_id, replaces)
        self._software()["initial_diagnostic_assignments"][record["member_id"]] = list(self._software()["initial_diagnostics"])
        return record

    def _share_fixed(self, actor, reference):
        # Fixed regimes have no latent partners; O3 may authorize future legal
        # identities to read this exact published version, never private updates.
        legal = MEMBERS[:self._software()["case"]["member_limits"]["max_cumulative_births"]]
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(legal),
            "shared_by": actor, "at": self.state["clock"]})


class SoftwareCollaborationPort(paged.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        value.update(interface_revision=INTERFACE_REVISION, purpose=PURPOSE, profile=self.profile)
        value["initial_diagnostic_provenance"].update(public_environment_facts=True, current_member_credit=False)
        return value


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    bundle = {"files": material(case["case_id"])["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
        "readers": [*active, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
        "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in active)
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "synthetic", "note": "Artificially derived organization-development roots; public initial defects/facts are environment preparation, not assigned member work"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-organization-v045", "actors": {actor: {} for actor in (*active, "operator")},
            "applications": ["files"], "publication_policy": "explicit",
            "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
            "config": {"task": member_instruction(case)}} for member in active],
        "setup": [], "events": [], "start": {"kind": "initial"},
        "boundary": {"max_opportunities": TEAM_LIMITS["max_decisions"] + case["member_limits"]["max_cumulative_births"]}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.test_budget = TestBudget(root / "team-test-budget.json")
    preparation = source.prepare_initial_diagnostics(case["case_id"], run_root=root / "environment-preparation")
    if preparation["initial_files_sha256"] != digest(json_bytes(bundle["files"])):
        raise ValueError("Initial diagnostic facts must identify the exact installed baseline files")
    with world.store.lock():
        world.state = world.store.load()
        baseline, baseline_version, _ = world._bundle(active[0], baseline=True)
        reference = previous.previous.base._reference(baseline, baseline_version)
        reports = {row["diagnostic_id"]: {**copy.deepcopy(row), "source_reference": copy.deepcopy(reference),
            "initial_source_reference": copy.deepcopy(reference), "initial_report": True}
            for row in (preparation["diagnostic_a"], preparation["diagnostic_b"])}
        ids = [preparation[key]["diagnostic_id"] for key in ("diagnostic_a", "diagnostic_b")]
        assignments = {member: list(ids) for member in active}
        world.state["shares"].append({"project_id": PROJECT, **reference,
            "actor_ids": list(MEMBERS[:case["member_limits"]["max_cumulative_births"]]), "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "initial_public_feedback": None, "transfer_offers": {}, "test_reports": {},
            "initial_diagnostics": reports, "initial_diagnostic_assignments": assignments,
            "environment_preparation_provenance": copy.deepcopy(preparation["preparation_provenance"]),
            "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
            "registry": {member: {"member_id": member, "birth_index": index + 1, "status": "live",
                "born_by": None, "origin": "initial_configuration", "briefing": "", "model_generated_briefing": False,
                "initial_source_reference": copy.deepcopy(reference), "initial_patch_id": None, "replaces": None,
                "birth_sequence": 0, "private_history_copied": False} for index, member in enumerate(active)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
        "test_feedback_protocol": PAGING_VERSION, "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "information_condition": case["information_condition"],
        "framing_condition": case["framing_condition"], "actual_work_copy_count": len(active),
        "initial_diagnostic_assignments": assignments,
        "environment_preparation_provenance": copy.deepcopy(preparation["preparation_provenance"]),
        "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
        "training_eligible": False, "independent_confirmation_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False,
        "initial_diagnostics_are_member_work": False, "actor_test_budget_charged_for_preparation": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
        "purpose": PURPOSE, "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "assess_software_collaboration", "runtime_process_contract": case["process_contract"]}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def assess_software_collaboration(prepared, *, run_root):
    """Raw last-fixed-tree quality only; runtime process gating is separate."""
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = world._software()
    common = {"version": VERSION, "usage": PURPOSE, "purpose": PURPOSE, "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "contract_version": CONTRACT_VERSION, "source_contract": case["source_contract"], "condition": case["condition"]}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
            "content_correct": None, "required_process_satisfied": None, "process_observation_complete": None,
            "reason": "No fixed delivery; mutable workspaces are not independently assessed"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = source.assess_files(case["case_id"], bundle["files"], run_root=run_root)
    return {**common, **result, "version": VERSION, "usage": PURPOSE, "purpose": PURPOSE,
        "status": "evaluable" if result["executed"] else "unknown", "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None, "submitted": True,
        "delivery": delivery, "source_reference": delivery["source_reference"], "files_sha256": delivery["files_sha256"]}
