"""Independent frozen two-member HOLD repository world; no calibration terminal-tree endpoint."""
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
from .adapters.capabilities import encode
from .work_interface import _schema_errors
from .world_core import WorldCore
from .software_organization_v047 import TOOLS as ARCHITECTURE_TOOLS

VERSION = "software-holdout-world-v0.51"
INTERFACE_REVISION = "stable-two-member-repository-holdout-v0.51"
CONTRACT_VERSION = "heldout-repository-tests-and-fixed-delivery-v0.51"
PURPOSE = "held_out_checkpoint_evaluation"
PROJECT, ROOT_GOAL_ID = previous.PROJECT, previous.ROOT_GOAL_ID
MEMBERS = ("member_001", "member_002")
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
SCHEDULER = "stable-o1-shared-pool-fair-visible-event-wakeup-v0.49"
PAGING_VERSION = paged.PAGING_VERSION
PAGE_BODY_CHARACTERS = paged.PAGE_BODY_CHARACTERS
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
TestBudget = previous.TestBudget
TOOLS = [copy.deepcopy(tool) for tool in paged.TOOLS if tool["name"] not in {"spawn_member", "retire_member"}]
ADOPT_CANDIDATE_TOOL = copy.deepcopy(next(tool for tool in ARCHITECTURE_TOOLS if tool["name"] == "adopt_candidate"))
ADOPT_CANDIDATE_TOOL["description"] = ADOPT_CANDIDATE_TOOL["description"].removesuffix(" I selection accepts only its frozen generation candidates.")
TOOLS.append(ADOPT_CANDIDATE_TOOL)
for _tool in TOOLS:
    if _tool["name"] == "run_tests":
        _tool["description"] = "Execute the frozen full original repository test set on this exact tree once. Save the permitted result in your private immutable report and return its directory plus first exact3072-character page. At most32 calls; page reads do not rerun tests. No extra member script is injected."
    if _tool["name"] == "write_file":
        _tool["description"] = "Replace the ENTIRE declared editable production file; retain all intended code. Original tests and supporting files are read-only."


def case_spec(case_id, *, provider, condition="O1", first_member="member_001", role_decision_limits=None):
    value = provider.build_case(case_id)
    if value.get("purpose") != PURPOSE or value.get("training_eligible") is not False:
        raise ValueError("Bind a nontraining HOLD repository source purpose")
    limits = dict.fromkeys(MEMBERS, 128)
    if condition != "O1" or first_member not in MEMBERS or role_decision_limits not in (None, limits):
        raise ValueError("HOLD uses two stable members with one unchanged episode budget")
    return {
        "version": VERSION, "case_id": case_id, "task_id": case_id,
        "family": value["family"], "constraint_family": value["family"],
        "condition": "O1", "public_condition": "fixed", "organization_level": "O1",
        "information_condition": "shared", "framing_condition": "neutral",
        "task_type": "repository_held_out_checkpoint_evaluation", "category": PURPOSE,
        "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE, "training_window_id": None,
        "training_eligible": False, "contribution_eligible": False, "independent_confirmation_eligible": False,
        "holdout_evaluation": True,
        "active_roles": list(MEMBERS), "role_decision_limits": limits,
        "team_limits": copy.deepcopy(TEAM_LIMITS), "first_member": first_member,
        "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION,
        "member_test_protocol": {"version": "full-original-repository-tests-v0.51",
                                 "optional_member_script": False, "same_full_test_union_in_public_and_final": True},
        "member_limits": {"initial_members": 2, "max_live_members": 2, "max_cumulative_births": 2,
            "births_enabled": False, "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": True,
            "voluntary_retirement_allowed": False, "retired_ids_reused": False,
            "stable_identities": True, "staff_done_scope": "current_work_until_later_visible_partner_event"},
        "external_intervention": {"enabled": False, "maximum_events": 0, "scope": "Two fixed equal members; no external work, birth or replacement"},
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
        raise ValueError("Frozen HOLD source, stable two-member identity, or budget changed")
    return case


def member_instruction(case, **_):
    limits = case["team_limits"]
    return (
        "Resolve the unchanged original repository issue in the immutable public root goal. Two stable equal members have independent private workspaces "
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
        "patch, exactly rather than merging; it performs no test, fix or submission. Original tests/configuration/support are read-only. No extra member test script or initial diagnostic is injected. run_tests executes the same full original repository test union for both members. write_file replaces a full declared production file; "
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

class _RepositoryTaskWorld(base.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            raise ToolRejection("Controller operations are unavailable in HOLD",
                code="forbidden_controller_request", category="policy_error", context={"process_violation": True})
        if tool in {"spawn_member", "retire_member"}:
            raise ToolRejection("Strict O1 has exactly two stable identities", code="tool_not_enabled", category="capability_gap")
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

    def _action_spawn_member(self, *args, **kwargs):
        raise ValueError("HOLD cannot create a third member")

    def _action_retire_member(self, *args, **kwargs):
        raise ValueError("HOLD completion never retires an identity")

    def retire_member(self, *args, **kwargs):
        raise ValueError("HOLD completion sleeps the same member under the stable O1 scheduler")

    def _share_fixed(self, actor, reference):
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
            "shared_by": actor, "at": self.state["clock"]})


class SoftwareCollaborationPort(paged.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        if role not in MEMBERS:
            raise ValueError("Only the two frozen HOLD members have ports")
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
                "isolation": "Private managed faulty repository versions; common confined full original repository test engine",
                "member_availability": world.member_availability(),
                "scheduling": {"protocol": SCHEDULER, "first_member": case["first_member"],
                    "done": "End current work and sleep; the same session may wake on later actual visible partner work",
                    "wait": "Suspend until later actual visible partner work; no event or budget is created",
                    "blocked": "Close only if neither stable member is runnable and no actual reachable partner event exists"},
                "root_goal": {"task_id": ROOT_GOAL_ID, "description": case["root_goal"],
                              "is_execution_task": False, "immutable": True},
                "task_formation": {"level": "O1", "population": "stable_two", "predefined_tasks": False,
                    "max_created_tasks": case["max_created_tasks"], "tasks_created": len(facts["tasks"])},
                "acceptance_contract": {"requirements": copy.deepcopy(case["source_contract"]["complete_delivery_requires"]),
                    "public_contract": "root_goal.description: unchanged original problem statement",
                    "submission_requires": list(case["submission_requires"]), "fixed_submission_is_acceptance": False},
                "current_version_test_coverage": coverage, "initial_public_feedback": None,
                "independent_acceptance": "reserved final classification over the same complete original test set",
                "task_event_sequences": [event["sequence"] for event in events
                    if event["kind"] in {"task_created", "task_revised", "dependency_declared", "dependency_removed"}],
                "execution_condition": {"condition": "O1", "initial_members": list(MEMBERS),
                    "active_executors": world.live_members(), "cumulative_births": 2, "private_working_copies": 2,
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
        raise ValueError("Bind the confined common repository executor before constructing a runnable world")
    bundle = {"files": provider.build_case(case["case_id"])["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
        "readers": [*active, "operator"], "writers": ["operator"], "data": bundle},
    ]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
        "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in active)
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "reconstructed", "note": "Fixed public repository plus original SWE-smith synthetic defect; operator baseline is faulty, never the correct source"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-O1",
        "world": {"world_id": "software-holdout-v051", "actors": {actor: {} for actor in (*active, "operator")},
            "applications": ["files"], "publication_policy": "explicit",
            "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
                   "config": {"task": member_instruction(case)}} for member in active],
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
            "initial_diagnostics": {}, "initial_diagnostic_assignments": {member: [] for member in MEMBERS},
            "environment_preparation_provenance": provenance, "environment_preparation_cost": cost,
            "registry": {member: {"member_id": member, "birth_index": index + 1, "status": "live",
                "born_by": None, "origin": "initial_configuration", "briefing": "", "model_generated_briefing": False,
                "initial_source_reference": copy.deepcopy(reference), "initial_patch_id": None, "replaces": None,
                "birth_sequence": 0, "private_history_copied": False} for index, member in enumerate(active)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
        "test_feedback_protocol": PAGING_VERSION, "page_body_unicode_characters": PAGE_BODY_CHARACTERS,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": "O1", "information_condition": "shared", "framing_condition": "neutral", "actual_work_copy_count": 2,
        "initial_diagnostic_assignments": {member: [] for member in MEMBERS}, "environment_preparation_provenance": provenance,
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
        "contract_version": CONTRACT_VERSION, "source_contract": case["source_contract"], "condition": "O1"}
    if not deliveries:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
            "content_correct": None, "required_process_satisfied": None, "process_observation_complete": None,
            "reason": "No fixed delivery; mutable working trees are never independently assessed"}
    delivery = deliveries[-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = prepared.source_provider.assess_files(case["case_id"], bundle["files"], run_root=run_root)
    return {**common, **result, "status": "evaluable" if result["executed"] else "unknown",
        "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None, "submitted": True,
        "delivery": delivery, "source_reference": delivery["source_reference"], "files_sha256": delivery["files_sha256"]}

