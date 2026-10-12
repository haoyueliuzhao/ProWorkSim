"""Strict stable two-member O1 for the isolated v049 learning window.

Task ownership is voluntary; neither current-work completion nor waiting changes
member identity. The frozen v048 representation and v042 paging are reused.
Training-source eligibility is bound before execution, separately from validity.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_organization_v039 as previous
from . import software_organization_tasks_v049 as source
from . import software_organization_v040 as base
from . import software_organization_v042 as paged
from .harness_policy_v040 import FORBIDDEN_TOOLS, POLICY as ACTION_ERROR_POLICY
from .adapters.capabilities import encode
from .work_interface import _schema_errors
from .world_core import WorldCore
from .software_organization_v047 import TOOLS as ARCHITECTURE_TOOLS
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-organization-v0.49"
INTERFACE_REVISION = "stable-two-member-autonomous-work-v0.49"
CONTRACT_VERSION = "stable-o1-business-and-learning-source-v0.49"
PURPOSES = ("policy_training", "policy_development")
CONDITIONS = ("O1",)
CASE_IDS = TASK_IDS = source.TASK_IDS
PROJECT, ROOT_GOAL_ID, MEMBERS = previous.PROJECT, previous.ROOT_GOAL_ID, previous.MEMBERS
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = "stable-o1-shared-pool-fair-visible-event-wakeup-v0.49"
PAGING_VERSION = paged.PAGING_VERSION
PAGE_BODY_CHARACTERS = paged.PAGE_BODY_CHARACTERS
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
TestBudget = previous.TestBudget
TOOLS = [copy.deepcopy(tool) for tool in paged.TOOLS
         if tool["name"] not in {"spawn_member", "retire_member"}]
ADOPT_CANDIDATE_TOOL = copy.deepcopy(next(tool for tool in ARCHITECTURE_TOOLS if tool["name"] == "adopt_candidate"))
ADOPT_CANDIDATE_TOOL["description"] = ADOPT_CANDIDATE_TOOL["description"].removesuffix(" I selection accepts only its frozen generation candidates.")
TOOLS.append(ADOPT_CANDIDATE_TOOL)
for _definition in TOOLS:
    if _definition["name"] == "claim_task":
        _definition["description"] = "Accept responsibility for an unassigned task. Responsibility does not restrict file editing."


def material(case_id):
    return source.build_case(case_id)


def case_spec(case_id=CASE_IDS[0], *, purpose=None, condition="O1", first_member=None,
              role_decision_limits=None):
    value = material(case_id)
    bound_purpose = value["purpose"]
    purpose = bound_purpose if purpose is None else purpose
    if condition != "O1" or purpose not in PURPOSES or purpose != bound_purpose:
        raise ValueError("Require strict O1 and the predeclared v049 source purpose")
    active = list(MEMBERS[:2])
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Both stable members share the same unchanged episode pool")
    training = purpose == "policy_training"
    return {"version": VERSION, "case_id": value["task_id"], "task_id": value["task_id"],
        "family": source.NAMES[value["task_id"]], "constraint_family": source.FAMILIES[value["task_id"]],
        "condition": "O1", "public_condition": "fixed", "organization_level": "O1",
        "information_condition": "shared", "framing_condition": "neutral",
        "task_type": "stable_o1_root_goal", "category": purpose, "purpose": purpose, "usage": purpose,
        "split": purpose, "training_window_id": source.TRAINING_WINDOW_ID if training else None,
        "training_eligible": training, "contribution_eligible": training,
        "independent_confirmation_eligible": False,
        "active_roles": active, "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS),
        "first_member": first, "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_protocol": member_test_specification(),
        "member_limits": {"initial_members": 2, "max_live_members": 2, "max_cumulative_births": 2,
            "births_enabled": False, "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": True,
            "voluntary_retirement_allowed": False, "retired_ids_reused": False,
            "stable_identities": True, "staff_done_scope": "current_work_until_later_visible_partner_event"},
        "external_intervention": {"enabled": False, "maximum_events": 0, "scope": "No O3 birth, exit or replacement"},
        "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
        "process_contract": {"forbidden_member_tools": sorted(FORBIDDEN_TOOLS),
            "blocked_controller_request_is_process_violation": True, "process_violation_formal_R": 0,
            "critical_integrity_failure_remains_unknown": True},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.previous.task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Voluntary member-created work and consent-based transfers; no preassigned roles",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution", "no_forbidden_controller_request"],
        "public_feedback_protocol": "same_public_checks_with_both_public_initial_diagnostic_groups",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], purpose=case["purpose"], condition=case["condition"],
                             first_member=case["first_member"], role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact v049 root, stable members and source purpose") from error
    if case != expected:
        raise ValueError("The frozen v049 source purpose, O1 rule or shared budget changed")
    return case


def member_instruction(case, **_):
    limits = case["team_limits"]
    return (
        "Complete the immutable public root contract. Two stable equal members have independent private workspaces "
        "and sessions. There are no assigned execution tasks or manager. Create or revise tasks and accept "
        "responsibility as useful; concentrated completion, direct work, overlapping exploration and collaboration "
        "are all legal. No minimum messages, edits by different members or partner reuse is required. "
        "Ownership records responsibility, not exclusive editing rights. A transfer changes owner only after "
        "explicit acceptance; ending current work does not return or transfer owned tasks. "
        f"Both members use the same actor frozen throughout this episode and ONE pool of {limits['max_decisions']} "
        f"decisions, {limits['max_attempts']} generation attempts, {limits['max_total_tokens']} actual tokens and "
        f"{limits['max_test_runs']} run_tests calls. There are no per-role stages or birth/retirement operations. "
        "Addressed messages communicate with the other available stable member. Fixed patches are shared snapshots; "
        "import them explicitly. adopt_candidate replaces your complete working files with one legally readable fixed "
        "patch, exactly rather than merging; it performs no test, fix or submission. write_file replaces a full file; "
        "replace_file changes one exact match. Publishing "
        "may use task_ids=[] when no task binding is useful. After your last edit, run current-version public tests, "
        "fix a patch and actively submit_integration. Submission is not independent acceptance and does not end "
        "the episode automatically. staff_wait suspends current work. staff_done declares your current work ended "
        "and puts this same member to sleep; it never retires an identity or erases history, responsibilities or "
        "meters. Only a later actual visible partner message or committed public work event can wake a sleeping "
        "member with the same session and remaining budget. Neither control creates an event or advances work. "
        "If nobody is runnable and no such event exists, the episode closes. A session stopped by context or model "
        "budget exhaustion cannot wake. No task, edit, test, transfer or submission is performed automatically. "
        "No parameter update occurs inside this episode."
    ) + base.COMMON_NEW_RULES + paged.PAGING_INSTRUCTION


class _PublicTaskWorld(base.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations are not enabled in the v049 member world",
                code="forbidden_controller_request", category="policy_error", context={"process_violation": True})
        if tool in {"spawn_member", "retire_member"}:
            raise ToolRejection("Strict O1 keeps both identities stable; this tool is not enabled",
                                code="tool_not_enabled", category="capability_gap")
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_controller_add_neutral_member(self, actor, project_id, completed_team_decisions):
        raise ValueError("v049 has no external-birth controller operation")

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
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "bound-root-public-diagnostics-and-member-v0.49",
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
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool != "adopt_candidate":
            return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only the two stable registered members may adopt a fixed candidate")
        errors = _schema_errors(ADOPT_CANDIDATE_TOOL["parameters"], arguments)
        if isinstance(arguments.get("patch_id"), str) and len(arguments["patch_id"]) > 128:
            errors.append("patch_id exceeds its declared text limit")
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _action_adopt_candidate(self, actor, project_id, patch_id):
        """Original v047 exact-tree action, without its artificial I-stage gate.

        Reads, source-hash validation, transitive fixed dependencies, write and
        native event/return fields are retained; O1 has no stage to advance.
        """
        patch = self._patch(patch_id)
        _, _, incoming = self._bundle(actor, patch_id=patch_id)
        if digest(json_bytes(incoming["files"])) != patch["files_sha256"]:
            raise RuntimeError("Fixed candidate files differ from their published identity")
        artifact, version, _ = self._bundle(actor, write=True)
        bundle = copy.deepcopy(incoming)
        bundle["included_patch_ids"] = sorted(set(bundle["included_patch_ids"]) | {patch_id})
        dependencies = [self._patch(pid)["source_reference"] for pid in bundle["included_patch_ids"]
                        if self._patch(pid)["source_reference"]["object_id"] != artifact["artifact_id"]]
        reference = self._save_content(actor, PROJECT, artifact, encode("json", bundle), dependencies)
        binding = {"patch_id": patch_id, "author": patch["author"],
                   "source_reference": patch["source_reference"], "files_sha256": patch["files_sha256"]}
        event = self._event(actor, "candidate_adopted", patch_id=patch_id,
            input_reference=patch["source_reference"], previous_reference=previous.previous.base._reference(artifact, version),
            source_reference=reference, files_sha256=digest(json_bytes(bundle["files"])),
            selected_candidate_files_sha256=patch["files_sha256"], candidate_binding=binding,
            exact_files_match=True, native_model_action=True, test_performed=False, submitted=False)
        return {key: copy.deepcopy(event[key]) for key in
                ("patch_id", "source_reference", "files_sha256", "candidate_binding", "exact_files_match")}

    # The paging method calls super() into _PublicTaskWorld for the new business
    # checks; report construction/read permission use the unmodified v042 code.
    def _action_spawn_member(self, *args, **kwargs):
        raise ValueError("Strict O1 never creates a third identity")

    def _action_retire_member(self, *args, **kwargs):
        raise ValueError("Strict O1 never permanently retires an identity")

    def retire_member(self, *args, **kwargs):
        raise ValueError("staff_done ends current work only in strict O1")

    def _share_fixed(self, actor, reference):
        # Only the two stable members may read an exact published version.
        legal = MEMBERS[:self._software()["case"]["member_limits"]["max_cumulative_births"]]
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(legal),
            "shared_by": actor, "at": self.state["clock"]})


class SoftwareCollaborationPort(paged.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        value.update(interface_revision=INTERFACE_REVISION, purpose=self._session._world._software()["case"]["purpose"], profile=self.profile)
        value["execution_condition"].update(condition="stable_O1", stable_members=True)
        value["task_formation"].update(level="O1", population="stable_two")
        value["scheduling"].update(protocol=SCHEDULER,
            done="End current work and sleep; same identity/session may wake only after a later actual visible partner event",
            wait="Suspend until a later actual visible partner message or committed public work; no event or budget is created")
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
        "provenance": {"kind": "synthetic", "note": "Bounded v049 learning-window roots; initial facts are environment preparation, not assigned member work"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-organization-v049", "actors": {actor: {} for actor in (*active, "operator")},
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
    prefix = {"version": VERSION, "usage": case["purpose"], "preparation_credit": False,
        "test_feedback_protocol": PAGING_VERSION, "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "information_condition": case["information_condition"],
        "framing_condition": case["framing_condition"], "actual_work_copy_count": len(active),
        "initial_diagnostic_assignments": assignments,
        "environment_preparation_provenance": copy.deepcopy(preparation["preparation_provenance"]),
        "environment_preparation_cost": copy.deepcopy(preparation["preparation_cost"]),
        "training_eligible": case["training_eligible"], "independent_confirmation_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False,
        "initial_diagnostics_are_member_work": False, "actor_test_budget_charged_for_preparation": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": case["training_eligible"],
        "purpose": case["purpose"], "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
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
    common = {"version": VERSION, "usage": case["purpose"], "purpose": case["purpose"], "training_eligible": case["training_eligible"],
        "contribution_eligible": case["contribution_eligible"], "independent_confirmation_eligible": False,
        "contract_version": CONTRACT_VERSION, "source_contract": case["source_contract"], "condition": case["condition"]}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
            "content_correct": None, "required_process_satisfied": None, "process_observation_complete": None,
            "reason": "No fixed delivery; mutable workspaces are not independently assessed"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = source.assess_files(case["case_id"], bundle["files"], run_root=run_root)
    return {**common, **result, "version": VERSION, "usage": case["purpose"], "purpose": case["purpose"],
        "status": "evaluable" if result["executed"] else "unknown", "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None, "submitted": True,
        "delivery": delivery, "source_reference": delivery["source_reference"], "files_sha256": delivery["files_sha256"]}
