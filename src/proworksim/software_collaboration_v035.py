"""Purpose-isolated O1 roots with genuine private copies and autonomous work.

Organization, physical test accounting, permissions and version/submission gates
reuse the established implementation. Only purpose-bound task material and its complete
acceptance contract change; no previous task or result is edited.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_collaboration_v027 as base
from . import software_collaboration_v030 as previous
from . import software_collaboration_v033 as stable
from . import software_tasks_v035 as source
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase

VERSION = "software-collaboration-v0.35"
INTERFACE_REVISION = "purpose-isolated-autonomous-work-v0.35"
CONTRACT_VERSION = "purpose-isolated-complete-work-v0.35"
PUBLIC_FEEDBACK_VERSION = source.PUBLIC_FEEDBACK_VERSION
PURPOSE = source.PURPOSE
PURPOSES = source.PURPOSES
CASE_PURPOSES = source.CASE_PURPOSES
TRAINING_CASE_ID = source.TRAINING_CASE_ID
CONTRIBUTION_CASE_IDS = source.CONTRIBUTION_CASE_IDS
CONFIRMATION_CASE_IDS = source.CONFIRMATION_CASE_IDS
PROJECT, MEMBERS, ROOT_GOAL_ID = stable.PROJECT, stable.MEMBERS, stable.ROOT_GOAL_ID
CASE_IDS = TASK_IDS = source.TASK_IDS
SCHEDULER = stable.SCHEDULER
TEAM_LIMITS = copy.deepcopy(stable.TEAM_LIMITS)
TOOLS = copy.deepcopy(stable.TOOLS)
TestBudget = stable.TestBudget
_validate_files = source._validate_files
run_public_tests = source.run_public_tests
assess_files = source.assess_files
acceptance_dimensions = source.acceptance_dimensions


def material(case_id):
    value = source.build_case(case_id)
    value["initial_binding"] = {
        "new_contract_sha256": digest(value["root_goal"].encode()),
        "initial_code_sha256": {name: digest(text.encode()) for name, text in value["files"].items()},
        "initial_files_sha256": digest(json_bytes(value["files"])),
        "public_driver_sha256": digest(value["files"]["test_visible.py"].encode()),
        "independent_verifier_sha256": value["source_contract"]["independent_verifier_sha256"],
        "public_checks_sha256": value["source_contract"]["public_checks_sha256"]}
    return value


def case_spec(case_id=CASE_IDS[0], *, condition="T", first_member=None, role_decision_limits=None):
    if condition != "T":
        raise ValueError("v035 admits only the frozen two-executor organization")
    value = material(case_id)
    purpose = value["purpose"]
    first = MEMBERS[0] if first_member is None else first_member
    limits = dict.fromkeys(MEMBERS, TEAM_LIMITS["max_decisions"])
    if first not in MEMBERS or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Both executors share the entire pool; no individual allocation")
    return {"version": VERSION, "case_id": case_id, "task_id": case_id, "condition": "T",
        "family": source.NAMES[case_id], "task_type": "o1_root_goal", "category": "o1_root_goal",
        "purpose": purpose, "usage": purpose, "split": purpose, "training_eligible": purpose == "policy_training",
        "contribution_eligible": purpose == "contribution_development",
        "independent_confirmation_eligible": purpose == "independent_confirmation", "active_roles": list(MEMBERS),
        "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS), "first_member": first,
        "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "organization_level": "O1", "editable_paths": value["editable_paths"],
        "source_contract": value["source_contract"], "initial_binding": value["initial_binding"],
        "root_goal": value["root_goal"], "max_created_tasks": previous.MAX_CREATED_TASKS,
        "predefined_execution_tasks": False,
        "responsibility_scope": "Autonomous work formation; centralized completion, help, communication and delegation are allowed and never required",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution"],
        "public_feedback_protocol": "separate_upstream_public_semantics_member_and_untested",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], condition=case["condition"], first_member=case["first_member"],
                             role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact purpose-bound root and shared-resource case") from error
    if case != expected:
        raise ValueError("Frozen new root, purpose, team, first member or resource limits changed")
    return case


def _public_feedback(case_id, files, *, run_root):
    result = source.run_public_tests(case_id, files, run_root=run_root)
    groups = {name: {**copy.deepcopy(group), "passed": group["passed"] if group["executed"] else None}
              for name, group in result["groups"].items()}
    return {"groups": groups, "public_execution": result,
            "passed": all(group["passed"] is True for group in groups.values()),
            "executed": all(group["executed"] for group in groups.values())}


class SoftwareCollaborationWorld(stable.SoftwareCollaborationWorld):
    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        result = _public_feedback(self._software()["case"]["case_id"], bundle["files"],
                                  run_root=self.store.root / "software-execution/public")
        member = previous._member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution/member")
        result["groups"]["member_tests"] = member
        result["passed"] = result["passed"] and member["passed"] is not False
        result.update(source_reference=base._reference(artifact, version), source_sha256=digest(json_bytes(bundle)),
            files_sha256=digest(json_bytes(bundle["files"])), suite="purpose-root-public-and-member-v0.35",
            untested=[name for name, group in result["groups"].items() if group["status"] == "untested"]
                + ["independent_acceptance", "full_upstream_suite"],
            scope="Frozen new public drivers only; independent acceptance is never run by a member tool",
            independent_acceptance="not_run_by_public_tool", fixed_submission_is_acceptance=False,
            team_test_budget=self.test_budget.snapshot())
        self._event(actor, "test", **result)
        return source.project_public_test_feedback(result)


class SoftwareCollaborationPort(stable.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        value["interface_revision"] = INTERFACE_REVISION
        return value


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    source_material = material(case["case_id"])
    bundle = {"files": source_material["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
                "readers": [*active, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
                    "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in active)
    instruction = (
        "Complete the immutable public root contract. Two equal executors start with separate private working copies and no execution tasks. "
        "Create or revise your own work and responsibility as useful; concentrated completion and collaboration are both legal. "
        "All sessions use one frozen actor and share ONE episode allowance: 128 decisions, 128 generation attempts, 500000 actual tokens, "
        "and 32 real run_tests calls. Any runnable executor may use the remaining pool. "
        "Published fixed patches can be explicitly imported with integrate_patch; private edits are not automatically shared. "
        "Use the actual public APIs and preserve the complete contract. write_file replaces a file; replace_file changes one exact match. "
        "run_tests reports public semantic checks, the upstream subset, and optional member tests. Independent inputs remain private. "
        "After your last edit, execute current-version tests, publish a fixed patch and actively submit_integration. "
        "The submission note is optional; fixed-version and test requirements remain. Submission is not acceptance. "
        "Ordinary tool/schema rejection returns real feedback and consumes an opportunity. staff_wait suspends until reachable addressed work "
        "or a partner patch; there is no external producer. staff_done ends only your own opportunities. No work, testing or submission is automatic.")
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "synthetic", "note": "New purpose-isolated contracts on pristine pinned library environments; no predetermined decomposition or old contract reuse."}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-collaboration-v035", "actors": {actor: {} for actor in (*active, "operator")},
                  "applications": ["files"], "publication_policy": "explicit",
                  "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model", "config": {"task": instruction}}
                  for member in active], "setup": [], "events": [], "start": {"kind": "initial"},
        "boundary": {"max_opportunities": TEAM_LIMITS["max_decisions"] + len(active)}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.test_budget = TestBudget(root / "team-test-budget.json")
    with world.store.lock():
        world.state = world.store.load()
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {}, "deliveries": [], "initial_public_feedback": None}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": case["purpose"], "preparation_credit": False,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "actual_work_copy_count": len(active), "training_eligible": case["training_eligible"],
        "actor_trajectories_created": False, "predefined_execution_tasks": False, "forced_initial_public_test": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": case["training_eligible"],
        "purpose": case["purpose"], "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def initial_information(prepared):
    """Normalize only explicit actor/topology identifiers in actual legal views."""
    result = {}
    for member in prepared.case["active_roles"]:
        view = SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member).observe()
        _, _, bundle = prepared.world._bundle(member)
        normalized = copy.deepcopy(view)
        for key in ("role", "profile", "world_id", "instance_id", "branch_id", "actor_id",
                    "workspace_reference", "member_availability", "execution_condition"):
            normalized.pop(key, None)
        normalized["task_formation"].pop("level", None)
        normalized["scheduling"].pop("first_member", None)
        if "team_model_budget" in normalized:
            normalized["team_model_budget"].pop("state_sha256", None)
        result[member] = {"normalized_legal_observation": normalized,
            "readable_files_sha256": {name: digest(text.encode()) for name, text in sorted(bundle["files"].items())}}
    return result


def prove_initial_team(prepared):
    views = initial_information(prepared)
    if set(views) != set(MEMBERS) or views[MEMBERS[0]] != views[MEMBERS[1]]:
        raise ValueError("The two real private copies must start with equal legally available business material")
    state = prepared.world.store.load()
    if len(state["artifacts"]) != 3 or set(state["actors"]) != {*MEMBERS, "operator"}:
        raise ValueError("A T root needs exactly two private copies and one read-only baseline")
    if prepared.world._software()["tasks"] or prepared.world._software()["patches"] or prepared.world._software()["deliveries"]:
        raise ValueError("No work organization or product may be prepared for the model")
    return {"case_id": prepared.case["case_id"], "member_views": views,
            "equal_initial_business_information": True, "actual_private_work_copies": 2,
            "initial_task_count": 0, "initial_patch_count": 0, "initial_delivery_count": 0,
            "scope": "Legal initial observation and file bytes only; no reference program, route witness, or independent input enters any prompt."}


def software_collaboration_facts(prepared_or_state):
    value = base.software_collaboration_facts(prepared_or_state)
    value["version"] = VERSION
    return value


def assess_software_collaboration(prepared, *, run_root):
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
    common = {"version": VERSION, "usage": case["purpose"], "purpose": case["purpose"], "training_eligible": case["training_eligible"],
        "contribution_eligible": case["contribution_eligible"],
        "independent_confirmation_eligible": case["independent_confirmation_eligible"], "contract_version": CONTRACT_VERSION,
        "source_contract": case["source_contract"], "condition": case["condition"]}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "complete_delivery": False,
                "content_correct": None, "required_process_satisfied": None, "process_observation_complete": None,
                "reason": "No fixed integrated delivery; no hidden assessment of an unsubmitted mutable workspace"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = assess_files(case["case_id"], bundle["files"], run_root=run_root)
    result.update(source_reference=delivery["source_reference"], files_sha256=delivery["files_sha256"])
    return {**common, **result, "version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
            "R": int(result["passed"]) if result["executed"] else None,
            "complete_delivery": result["passed"] if result["executed"] else None,
            "submitted": True, "delivery": delivery}
