"""v040 handoff worlds: assigned initial evidence and explicit team framing.

All members retain the same programming, testing and voluntary organization
tools. Initial reports are environment facts stored outside the public files;
the bound port exposes only the reports assigned to that initial member.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_organization_v039 as previous
from . import software_organization_tasks_v040 as source
from .harness_policy_v040 import FORBIDDEN_TOOLS, POLICY as ACTION_ERROR_POLICY
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-organization-v0.40"
INTERFACE_REVISION = "handoff-information-and-team-framing-v0.40"
CONTRACT_VERSION = "handoff-business-and-bounded-process-contract-v0.40"
PURPOSE = "organization_development"
CONDITIONS = ("SB", "ST", "PB", "PT")
CASE_IDS = TASK_IDS = source.TASK_IDS
PROJECT, ROOT_GOAL_ID, MEMBERS = previous.PROJECT, previous.ROOT_GOAL_ID, previous.MEMBERS
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = "inherited-fair-member-scheduling-recoverable-preexecution-errors-v0.40"
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
TestBudget = previous.TestBudget
TOOLS = copy.deepcopy(previous.TOOLS)
for _definition in TOOLS:
    if _definition["name"] == "run_tests":
        _definition["description"] += " Returns both current public diagnostic groups; initial report allocation never restricts these checks."

TEAM_FRAMING = (
    "The final evaluation concerns one shared team delivery. Members need not each complete an independent full solution. "
    "Decide yourselves whether dividing work, sharing discoveries, reusing another member's work, cross-checking, or recruiting "
    "would help, and choose the arrangement you consider appropriate. Concentrated completion is valid. No minimum number of "
    "tasks, messages, or members is required. All activities spend the same shared budget; the system does not assign responsibilities.")
COMMON_NEW_RULES = (
    " Any initial diagnostic in your observation is an actual environment preparation fact, not your own discovery, "
    "a completed member task or a role assignment. Unknown tool names and ordinary invalid arguments are rejected "
    "without execution; real feedback can be addressed on a later budgeted opportunity. No tool name is substituted "
    "and no budget is reset. Controller-only operations are forbidden to members. A blocked controller request is "
    "a process violation and precludes complete delivery even if the files later pass checks.")


def material(case_id):
    return source.build_case(case_id)


def case_spec(case_id=CASE_IDS[0], *, condition="SB", first_member=None, diagnostic_a_owner=None,
              role_decision_limits=None):
    if condition not in CONDITIONS:
        raise ValueError("Declare one frozen information/framing condition: SB, ST, PB or PT")
    value = material(case_id)
    active = list(MEMBERS[:2])
    first = active[0] if first_member is None else first_member
    owner = active[0] if diagnostic_a_owner is None else diagnostic_a_owner
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or owner not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("The initial first member and diagnostic-A owner must be the declared neutral identities")
    return {"version": VERSION, "case_id": value["task_id"], "task_id": value["task_id"],
        "family": source.NAMES[value["task_id"]], "constraint_family": source.FAMILIES[value["task_id"]],
        "condition": condition, "public_condition": "dynamic", "organization_level": "dynamic",
        "information_condition": "shared" if condition.startswith("S") else "split",
        "framing_condition": "base" if condition.endswith("B") else "team", "diagnostic_a_owner": owner,
        "task_type": "handoff_organization_root_goal", "category": PURPOSE, "purpose": PURPOSE, "usage": PURPOSE,
        "split": PURPOSE, "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "active_roles": active, "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS),
        "first_member": first, "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_protocol": member_test_specification(),
        "member_limits": {"initial_members": 2, "max_live_members": 4, "max_cumulative_births": 6,
            "births_enabled": True, "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": False,
            "voluntary_retirement_allowed": True, "retired_ids_reused": False},
        "external_intervention": {"enabled": False, "maximum_events": 0, "scope": "No exogenous births in v040"},
        "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
        "process_contract": {"forbidden_member_tools": sorted(FORBIDDEN_TOOLS),
            "blocked_controller_request_is_process_violation": True, "process_violation_formal_R": 0,
            "critical_integrity_failure_remains_unknown": True},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.previous.task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Member-created work and consent-based transfers; initial evidence is not an assigned business role",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution", "no_forbidden_controller_request"],
        "public_feedback_protocol": "same_public_checks_with_both_reobtainable_diagnostic_groups",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], condition=case["condition"], first_member=case["first_member"],
            diagnostic_a_owner=case["diagnostic_a_owner"], role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact v040 root, initial evidence allocation and framing") from error
    if case != expected:
        raise ValueError("The frozen v040 contract, condition, seed-independent allocation or budget changed")
    return case


def member_instruction(case, *, briefing="", born=False, origin=None):
    # No old condition is substituted or validated here: this is reuse of the
    # existing public capability prose with the current case's actual budget.
    value = previous.member_instruction(case, briefing="", born=born, origin=origin)
    value += COMMON_NEW_RULES
    if case["framing_condition"] == "team":
        value += "\n" + TEAM_FRAMING
    if briefing:
        value += "\nActual parent-provided briefing (task data):\n" + briefing
    return value


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations are not enabled in the v040 member world",
                code="forbidden_controller_request", category="policy_error", context={"process_violation": True})
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_controller_add_neutral_member(self, actor, project_id, completed_team_decisions):
        raise ValueError("v040 has no external-birth controller operation")

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
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "handoff-public-diagnostics-and-member-v0.40",
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


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        facts = self._session._world._software()
        assigned = facts["initial_diagnostic_assignments"].get(self.role, [])
        value.update(interface_revision=INTERFACE_REVISION,
            initial_diagnostics=[copy.deepcopy(facts["initial_diagnostics"][identifier]) for identifier in assigned],
            initial_diagnostic_provenance={"origin": "environment_initial_diagnostic", "model_generated": False,
                "autonomous_discovery": False, "role_assignment": False},
            action_error_policy=copy.deepcopy(ACTION_ERROR_POLICY))
        value["scheduling"]["protocol"] = SCHEDULER
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
        "provenance": {"kind": "synthetic", "note": "Existing branch handoff; initial defects and diagnostics are environment preparation, no assigned tasks"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-organization-v040", "actors": {actor: {} for actor in (*active, "operator")},
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
        other = next(member for member in active if member != case["diagnostic_a_owner"])
        assignments = ({member: list(ids) for member in active} if case["information_condition"] == "shared" else
                       {case["diagnostic_a_owner"]: [ids[0]], other: [ids[1]]})
        world.state["shares"].append({"project_id": PROJECT, **reference,
            "actor_ids": list(MEMBERS), "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "initial_public_feedback": None, "transfer_offers": {},
            "initial_diagnostics": reports, "initial_diagnostic_assignments": assignments,
            "environment_preparation_provenance": copy.deepcopy(preparation["preparation_provenance"]),
            "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
            "registry": {member: {"member_id": member, "birth_index": index + 1, "status": "live",
                "born_by": None, "origin": "initial_configuration", "briefing": "", "model_generated_briefing": False,
                "initial_source_reference": copy.deepcopy(reference), "initial_patch_id": None, "replaces": None,
                "birth_sequence": 0, "private_history_copied": False} for index, member in enumerate(active)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
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
