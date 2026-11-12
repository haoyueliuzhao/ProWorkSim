"""Genuine one-member repository world for CAL-2 P/U.

The faulty source, editing/version tools, shared budget, and exact 3072-character
feedback pages are the same in both conditions. Only the loaded actor differs.
There is no second member, automatic repair, test, submission, or initial test.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_organization_v039 as previous
from . import software_organization_v040 as base
from . import software_organization_v042 as paged
from .harness_policy_v040 import FORBIDDEN_TOOLS, POLICY as ACTION_ERROR_POLICY
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-calibration-world-v0.51"
INTERFACE_REVISION = "single-member-repository-calibration-v0.51"
CONTRACT_VERSION = "original-repository-tests-and-fixed-delivery-v0.51"
PURPOSE = "single_agent_calibration"
PROJECT, ROOT_GOAL_ID = previous.PROJECT, previous.ROOT_GOAL_ID
MEMBERS = ("member_001",)
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = "v051-single-member-unchanged-budget-native-opportunities"
PAGING_VERSION = paged.PAGING_VERSION
PAGE_BODY_CHARACTERS = paged.PAGE_BODY_CHARACTERS
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
TestBudget = previous.TestBudget
TOOLS = [copy.deepcopy(tool) for tool in paged.TOOLS if tool["name"] not in {"spawn_member", "retire_member"}]
for _tool in TOOLS:
    if _tool["name"] == "run_tests":
        _tool["description"] = "Execute the frozen full original repository test set on this exact tree once. Save the permitted result in your private immutable report and return its directory plus first exact3072-character page. At most32 calls; page reads do not rerun tests. No extra member script is injected."
    if _tool["name"] == "write_file":
        _tool["description"] = "Replace the ENTIRE declared editable production file; retain all intended code. Original tests and supporting files are read-only."


def case_spec(case_id, *, provider, condition="S1", first_member="member_001", role_decision_limits=None):
    value = provider.build_case(case_id)
    limits = {MEMBERS[0]: 128}
    if condition != "S1" or first_member != MEMBERS[0] or role_decision_limits not in (None, limits):
        raise ValueError("CAL-2 P/U use one real member_001 and one unchanged budget")
    return {
        "version": VERSION, "case_id": case_id, "task_id": case_id,
        "family": value["family"], "constraint_family": value["family"],
        "condition": "S1", "public_condition": "fixed", "organization_level": "S1",
        "information_condition": "shared", "framing_condition": "neutral",
        "task_type": "repository_single_agent_calibration", "category": PURPOSE,
        "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE, "training_window_id": None,
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "active_roles": list(MEMBERS), "role_decision_limits": limits,
        "team_limits": copy.deepcopy(TEAM_LIMITS), "first_member": first_member,
        "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION,
        "member_test_protocol": {"version": "full-original-repository-pytest-v0.51",
                                 "optional_member_script": False, "same_full_test_union_in_public_and_final": True},
        "member_limits": {"initial_members": 1, "max_live_members": 1, "max_cumulative_births": 1,
            "births_enabled": False, "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": True,
            "voluntary_retirement_allowed": False, "retired_ids_reused": False,
            "stable_identities": True, "staff_done_scope": "end_current_single_member_work"},
        "external_intervention": {"enabled": False, "maximum_events": 0, "scope": "No hidden partner or external work"},
        "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
        "process_contract": {"forbidden_member_tools": sorted(FORBIDDEN_TOOLS),
            "blocked_controller_request_is_process_violation": True, "process_violation_formal_R": 0,
            "critical_integrity_failure_remains_unknown": True},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.previous.task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Optional self-created tasks; direct repository work needs no task assignment",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution", "no_forbidden_controller_request"],
        "public_feedback_protocol": "full_original_repository_tests_with_exact_v042_pages",
        "forced_initial_failure_feedback": False,
    }


def validate_case(case, *, provider):
    expected = case_spec(case["case_id"], provider=provider, condition=case["condition"],
                         first_member=case["first_member"], role_decision_limits=case["role_decision_limits"])
    if case != expected:
        raise ValueError("Frozen CAL-2 source, single-member identity, or budget changed")
    return case


def member_instruction(case, **_):
    limits = case["team_limits"]
    return (
        "Resolve the original repository issue shown as your root goal. You are the only executor, member_001, "
        "with one private working tree and one session. There is no hidden partner, manager, external worker, "
        "recruitment or replacement. Optional self-created tasks record your responsibilities; direct work is legal. "
        "Edit the declared production files. The original tests and supporting files are read-only. "
        f"Your entire episode has {limits['max_decisions']} decisions, {limits['max_attempts']} generation attempts, "
        f"{limits['max_total_tokens']} actual tokens and {limits['max_test_runs']} run_tests calls. "
        "run_tests executes the same full original repository test set used for final code correctness. "
        "write_file replaces the full file; replace_file changes one unique exact match. "
        "After the last edit, run tests for that exact current tree, fix_patch(task_ids=[]) and submit_integration. "
        "Submission is a fixed version, not automatic acceptance or automatic work completion. "
        "staff_done ends your current work; staff_wait suspends it. Neither creates a work event or resets meters. "
        "With no runnable member or real later event, the episode closes. No edit, test, fix or submission "
        "is performed automatically. No parameter update occurs inside the episode."
    ) + paged.PAGING_INSTRUCTION


class _RepositoryTaskWorld(base.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations are unavailable in CAL-2",
                code="forbidden_controller_request", category="policy_error", context={"process_violation": True})
        if tool in {"spawn_member", "retire_member"}:
            raise ToolRejection("S1 has exactly one stable identity", code="tool_not_enabled", category="capability_gap")
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        public = self.source_provider.run_public_tests(self._software()["case"]["case_id"], bundle["files"],
            run_root=self.store.root / "software-execution/public")
        reference = previous.previous.base._reference(artifact, version)
        result = {"groups": copy.deepcopy(public["groups"]), "public_execution": public,
            "public_diagnostics": {}, "repository_collection_errors": public.get("repository_collection_errors", []),
            "passed": public["passed"], "executed": public["execution"]["executed"],
            "source_reference": reference, "source_sha256": digest(json_bytes(bundle)),
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "full-original-repository-tests-v0.51",
            "untested": [] if public["execution"]["executed"] else ["repository_tests"],
            "scope": "The original full test union is public; final classification uses this same set",
            "independent_acceptance": "same_test_set_reserved_final_fixed_version",
            "fixed_submission_is_acceptance": False, "team_test_budget": self.test_budget.snapshot()}
        self._event(actor, "test", **result)
        return previous.previous.previous.project_public_test_feedback(result)


class SoftwareCollaborationWorld(paged.SoftwareCollaborationWorld, _RepositoryTaskWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _action_spawn_member(self, *args, **kwargs):
        raise ValueError("CAL-2 S1 cannot create any member")

    def _action_retire_member(self, *args, **kwargs):
        raise ValueError("CAL-2 S1 completion does not alter identity")

    def retire_member(self, *args, **kwargs):
        raise ValueError("CAL-2 S1 completion is handled by its one-session scheduler")

    def _share_fixed(self, actor, reference):
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
            "shared_by": actor, "at": self.state["clock"]})


class SoftwareCollaborationPort(paged.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        if role != MEMBERS[0]:
            raise ValueError("There is no second CAL-2 software member")
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        # The inherited root assumes an artificial contract.md. Repository
        # work instead exposes the unchanged original issue as metadata, so
        # its source file tree stays byte-identical across R/P/U.
        world = self._session._world
        with world.store.lock():
            world.state = world.store.load()
            artifact, version, bundle = world._bundle(self.role)
            facts, case = world._software(), world._software()["case"]
            reference = previous.previous.base._reference(artifact, version)
            events = world.state["software_events"]
            messages = [copy.deepcopy(event) for event in events
                if event["kind"] in {"work_message", "delegate", "task_returned"} and event.get("recipient") == self.role]
            handoffs = [copy.deepcopy(event) for event in events
                if event["kind"] == "handoff" and event.get("recipient") == self.role]
            tests = [event for event in events if event["kind"] == "test"
                     and event["actor_id"] == self.role and event["source_reference"] == reference]
            coverage = ({name: {key: group[key] for key in ("status", "executed", "passed")}
                         for name, group in tests[-1]["groups"].items()} if tests else
                        {"repository_tests": {"status": "untested", "executed": False, "passed": None}})
            registry = {member: {key: copy.deepcopy(item) for key, item in row.items() if key != "briefing"}
                        for member, row in facts["registry"].items()}
            value = {
                "role": self.role, "actor_id": self.role, "project_id": PROJECT,
                "profile": self.profile, "interface_revision": INTERFACE_REVISION, "purpose": PURPOSE,
                **{key: world.state[key] for key in ("world_id", "instance_id", "branch_id", "logical_time")
                   if key in world.state},
                "logical_time": world.state["clock"], "world_status": world.state["world_status"],
                "projects": {PROJECT: {"project_id": PROJECT}}, "contract": case["root_goal"],
                "workspace_reference": reference, "editable_paths": copy.deepcopy(case["editable_paths"]),
                "included_patch_ids": list(bundle["included_patch_ids"]), "tasks": copy.deepcopy(facts["tasks"]),
                "patches": copy.deepcopy(list(facts["patches"].values()))[-6:],
                "deliveries": copy.deepcopy(facts["deliveries"])[-2:], "messages": messages[-4:], "handoffs": handoffs[-4:],
                "older_message_sequences": [event["sequence"] for event in messages[:-4]],
                "older_handoff_sequences": [event["sequence"] for event in handoffs[:-4]],
                "all_fixed_patches": [{"patch_id": event["patch_id"], "sequence": event["sequence"]}
                                      for event in events if event["kind"] == "patch_fixed"],
                "observation_projection": "Latest4 messages/handoffs,6 patches and2 deliveries; text previews500characters; read_work_event restores exact archived text",
                "isolation": "Private managed faulty repository versions; common confined full original pytest executor",
                "member_availability": world.member_availability(),
                "scheduling": {"protocol": SCHEDULER, "first_member": MEMBERS[0],
                    "done": "End this single member's work; no replacement or synthetic wake event",
                    "wait": "Suspend this member; no hidden worker produces new work",
                    "blocked": "Close if this sole member is not runnable and no real event exists"},
                "root_goal": {"task_id": ROOT_GOAL_ID, "description": case["root_goal"],
                              "is_execution_task": False, "immutable": True},
                "task_formation": {"level": "S1", "population": "one_real_member", "predefined_tasks": False,
                    "max_created_tasks": case["max_created_tasks"], "tasks_created": len(facts["tasks"])},
                "acceptance_contract": {"requirements": copy.deepcopy(case["source_contract"]["complete_delivery_requires"]),
                    "public_contract": "root_goal.description: unchanged original problem statement",
                    "submission_requires": list(case["submission_requires"]), "fixed_submission_is_acceptance": False},
                "current_version_test_coverage": coverage, "initial_public_feedback": None,
                "independent_acceptance": "reserved final classification over the same complete original test set",
                "task_event_sequences": [event["sequence"] for event in events
                    if event["kind"] in {"task_created", "task_revised", "dependency_declared", "dependency_removed"}],
                "execution_condition": {"condition": "S1", "initial_members": list(MEMBERS),
                    "active_executors": world.live_members(), "cumulative_births": 1, "private_working_copies": 1,
                    "same_actor_shared_across_sessions": True, "centralized_completion_allowed": True,
                    "preassigned_tasks_or_manager": False, "stable_members": True, "hidden_partners": False},
                "shared_resource_limits": copy.deepcopy(case["team_limits"]),
                "team_test_budget": {key: world.test_budget.snapshot()[key] for key in ("limit", "used", "remaining")},
                "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_version": "original-repository-only-v051",
                "member_registry": registry, "member_limits": copy.deepcopy(case["member_limits"]),
                "own_initial_briefing": "", "transfer_offers": copy.deepcopy(facts["transfer_offers"]),
                "orphan_obligations": [],
                "organization_event_sequences": [event["sequence"] for event in events
                    if event["kind"] in previous.previous.PUBLIC_TASK_EVENTS | {"member_retired", "member_spawned"}],
                "initial_diagnostics": [], "initial_diagnostic_provenance": {"origin": "none_no_automatic_test",
                    "model_generated": False, "autonomous_discovery": False, "role_assignment": False,
                    "public_environment_facts": True, "current_member_credit": False},
                "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
            }
            callback = getattr(world, "model_budget_snapshot", None)
            if callback is not None:
                snapshot = callback()
                value["team_model_budget"] = {key: snapshot[key] for key in (
                    "limits", "decisions", "attempts", "charged_tokens", "held_tokens", "remaining_decisions",
                    "remaining_attempts", "available_tokens", "state_sha256")}
            for rows in (value["messages"], value["handoffs"], value["patches"], value["deliveries"]):
                for row in rows:
                    for key in ("body", "message", "reason"):
                        if isinstance(row.get(key), str) and len(row[key]) > 500:
                            row[key], row[key + "_truncated"] = row[key][:500], True
            return value


def build_software_collaboration_case(case, root, *, provider):
    case = case_spec(case, provider=provider) if isinstance(case, str) else validate_case(copy.deepcopy(case), provider=provider)
    if provider.runner is None:
        raise ValueError("Bind the confined common pytest executor before constructing a runnable repository world")
    bundle = {"files": provider.build_case(case["case_id"])["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
        "readers": [*active, "operator"], "writers": ["operator"], "data": bundle},
        {"alias": MEMBERS[0], "filename": MEMBERS[0] + ".json", "kind": "json", "owner": MEMBERS[0],
         "readers": [MEMBERS[0], "operator"], "writers": [MEMBERS[0]], "data": copy.deepcopy(bundle)}]
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "reconstructed", "note": "Fixed public repository plus original SWE-smith synthetic defect; operator baseline is faulty, never the correct source"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-S1",
        "world": {"world_id": "software-calibration-v051", "actors": {actor: {} for actor in (*active, "operator")},
            "applications": ["files"], "publication_policy": "explicit",
            "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": MEMBERS[0], "actor": MEMBERS[0], "project": PROJECT, "policy": "model",
                   "config": {"task": member_instruction(case)}}],
        "setup": [], "events": [], "start": {"kind": "initial"}, "boundary": {"max_opportunities": 129}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.source_provider = provider
    world.test_budget = TestBudget(root / "team-test-budget.json")
    provenance = {"origin": "static_source_only", "initial_test_executions": 0, "cache_reuse": False,
                  "correct_reference_installed": False, "model_work": False}
    cost = {"program_test_executions": 0, "model_calls": 0, "model_tokens": 0,
            "actor_test_budget_charged": False, "scope": "No automatic initial test or repair"}
    with world.store.lock():
        world.state = world.store.load()
        baseline, baseline_version, _ = world._bundle(MEMBERS[0], baseline=True)
        reference = previous.previous.base._reference(baseline, baseline_version)
        world.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
            "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "initial_public_feedback": None, "transfer_offers": {}, "test_reports": {},
            "initial_diagnostics": {}, "initial_diagnostic_assignments": {MEMBERS[0]: []},
            "environment_preparation_provenance": provenance, "environment_preparation_cost": cost,
            "registry": {MEMBERS[0]: {"member_id": MEMBERS[0], "birth_index": 1, "status": "live",
                "born_by": None, "origin": "initial_configuration", "briefing": "", "model_generated_briefing": False,
                "initial_source_reference": copy.deepcopy(reference), "initial_patch_id": None, "replaces": None,
                "birth_sequence": 0, "private_history_copied": False}}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
        "test_feedback_protocol": PAGING_VERSION, "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": "S1", "information_condition": "shared", "framing_condition": "neutral", "actual_work_copy_count": 1,
        "initial_diagnostic_assignments": {MEMBERS[0]: []}, "environment_preparation_provenance": provenance,
        "environment_preparation_cost": cost, "training_eligible": False, "independent_confirmation_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False, "initial_diagnostics_are_member_work": False,
        "actor_test_budget_charged_for_preparation": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
        "purpose": PURPOSE, "source_partition_sha256": provider.manifest_sha256,
        "independent_assessment": "assess_software_collaboration", "runtime_process_contract": case["process_contract"]}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    prepared.source_provider = provider
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def assess_software_collaboration(prepared, *, run_root):
    case = validate_case(prepared.case, provider=prepared.source_provider)
    world = prepared.world
    world.state = world.store.load()
    deliveries = world._software()["deliveries"]
    common = {"version": VERSION, "usage": PURPOSE, "purpose": PURPOSE, "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "contract_version": CONTRACT_VERSION, "source_contract": case["source_contract"], "condition": "S1"}
    if not deliveries:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
            "content_correct": None, "required_process_satisfied": None, "process_observation_complete": None,
            "reason": "No fixed delivery; terminal working-tree code is a separate CAL-2 endpoint"}
    delivery = deliveries[-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = prepared.source_provider.assess_files(case["case_id"], bundle["files"], run_root=run_root)
    return {**common, **result, "status": "evaluable" if result["executed"] else "unknown",
        "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None, "submitted": True,
        "delivery": delivery, "source_reference": delivery["source_reference"], "files_sha256": delivery["files_sha256"]}


def assess_terminal_working_tree(prepared, *, run_root, fixed_assessment=None):
    """New CAL-2 endpoint only; never rewrite fixed R or any historical run."""
    case = validate_case(prepared.case, provider=prepared.source_provider)
    world = prepared.world
    world.state = world.store.load()
    artifact, version, bundle = world._bundle(MEMBERS[0])
    files_sha = digest(json_bytes(bundle["files"]))
    reference = previous.previous.base._reference(artifact, version)
    lock = {"member_id": MEMBERS[0], "source_reference": reference,
            "source_sha256": digest(json_bytes(bundle)), "files_sha256": files_sha}
    root = Path(run_root)
    atomic_write(root / "terminal-candidate-lock.json", json_bytes(lock))
    reuse = bool(fixed_assessment and fixed_assessment.get("submitted")
                 and fixed_assessment.get("files_sha256") == files_sha)
    result = (copy.deepcopy(fixed_assessment) if reuse else
              prepared.source_provider.assess_files(case["case_id"], bundle["files"], run_root=root / "tests"))
    known = result.get("executed") is True
    checks = result.get("independent_acceptance", {}).get("checks", [])
    score = {"version": VERSION, "endpoint": "terminal_working_tree_code_correctness", **lock,
        "executed": known, "R_code": int(result["passed"]) if known else None,
        "Q_task": sum(row["passed"] is True for row in checks) / len(checks) if known and checks else None,
        "tests_passed": sum(row["passed"] is True for row in checks) if known else None,
        "tests_total": len(checks),
        "observed_pass_fraction": result.get("observed_pass_fraction"),
        "test_nodes_observed": result.get("test_nodes_observed"),
        "all_expected_tests_observed": result.get("all_expected_tests_observed"),
        "measurement_scope": result.get("measurement_scope"),
        "fixed_submission_present": bool(fixed_assessment and fixed_assessment.get("submitted")),
        "reused_same_fixed_tree_assessment": reuse, "new_evaluation_attempts": 0 if reuse else 1,
        "new_test_executions": int(not reuse and result.get("independent_acceptance", {}).get("execution", {}).get("command_executed") is True),
        "fixed_submission_R_unchanged": True, "assessment": result,
        "scope": "Predeclared v051 CAL-2 terminal-code endpoint; no retrospective scoring of old unsubmitted work"}
    atomic_write(root / "terminal-code-assessment.json", json_bytes(score))
    return score
