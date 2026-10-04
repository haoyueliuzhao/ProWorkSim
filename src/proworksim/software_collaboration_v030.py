"""O1 task formation and explicit public coverage for model/interface selection.

This new development world preserves v0.29 originals. It does not provide an
execution decomposition: members create and revise their own task board. Public
test feedback and immutable delivery are distinct from independent acceptance.
"""
from __future__ import annotations

import ast
import copy
import re
from pathlib import Path

from . import software_collaboration_v027 as base
from . import software_collaboration_v028 as interface
from . import software_collaboration_v029 as previous
from . import software_tasks_v030 as source
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .software_sandbox import run_isolated
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-collaboration-v0.30"
INTERFACE_REVISION = "software-collaboration-o1-v0.30"
PROJECT = interface.PROJECT
MEMBERS = interface.MEMBERS
TASK_IDS = CASE_IDS = source.TASK_IDS
SCHEDULER = interface.SCHEDULER
CONTRACT_VERSION = "model-interface-development-work-validity-v0.30"
ROOT_GOAL_ID = "root_goal"
MAX_CREATED_TASKS = 24
PURPOSE = "model_interface_development"

TOOLS = copy.deepcopy(previous.TOOLS)
for _tool in TOOLS:
    if _tool["name"] == "claim_task":
        _tool["description"] = "Atomically claim an unassigned task created by a member. There are no predefined execution tasks."
    elif _tool["name"] == "declare_dependency":
        _tool["description"] += " Binds the prerequisite's current task revision; remove and redeclare to adopt revised scope."
    elif _tool["name"] == "read_work_event":
        _tool["description"] += " Member-created task and dependency revision events are also public."
    elif _tool["name"] == "send_message":
        _tool["description"] += " Use task_id=root_goal to negotiate before any task exists."
    elif _tool["name"] == "run_tests":
        _tool["description"] = (
            "Execute public upstream regressions, public normal business cases, and your optional test_member.py "
            "on this exact tree. Results separate these groups and untested requirements. All candidates receive "
            "these same mandatory public groups. No independent acceptance result is returned.")
    elif _tool["name"] == "submit_integration":
        _tool["description"] = (
            "Save a fixed submission pending independent acceptance. Requires a real current-version run_tests "
            "execution of both public groups and a current fixed patch. Tests need not pass to submit. "
            "A saved submission is not a correctness or acceptance result.")
TOOLS += [
    base._tool("create_task", "Create your own unassigned execution task under the root goal or an existing task. "
               "No member is assigned until claim_task. At most 24 tasks may be created in an episode.",
               {"task_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                "parent_task_id": base._PATH}, ["task_id", "description"]),
    base._tool("revise_task", "Revise your owned task, or your own unassigned task, with its current revision and reason. "
               "Earlier task text and responsibility remain archived. Root acceptance is immutable.",
               {"task_id": base._PATH, "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                "expected_revision": {"type": "integer", "minimum": 1},
                "reason": {"type": "string", "minLength": 1, "maxLength": 2000}}),
    base._tool("remove_dependency", "Remove one declared dependency from your owned task, recording why. "
               "Previous patches retain their original task/dependency snapshots.",
               {"task_id": base._PATH, "depends_on": base._PATH,
                "reason": {"type": "string", "minLength": 1, "maxLength": 2000}}),
]


def case_spec(case_id=CASE_IDS[0], *, first_member=None, role_decision_limits=None):
    material = source.build_case(case_id)
    active = list(material["active_roles"])
    if active not in [[MEMBERS[0]], list(MEMBERS)]:
        raise ValueError("Development cases have one executor or the two stable startup members")
    first = active[0] if first_member is None else first_member
    if first not in active:
        raise ValueError("The first opportunity must belong to an active member")
    limits = dict.fromkeys(active, 64) if role_decision_limits is None else copy.deepcopy(role_decision_limits)
    if (not isinstance(limits, dict) or set(limits) != set(active)
            or any(type(value) is not int or not 1 <= value <= 128 for value in limits.values())):
        raise ValueError("Freeze from 1 to 128 decisions for each active member")
    if material["purpose"] != PURPOSE:
        raise ValueError("Only the new model/interface development pool may enter selection")
    return {"version": VERSION, "case_id": case_id, "task_id": case_id,
            "family": source.NAMES[case_id], "task_type": material["category"],
            "category": material["category"], "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE,
            "training_eligible": False, "independent_confirmation_eligible": False,
            "active_roles": active, "role_decision_limits": limits, "first_member": first,
            "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
            "organization_level": "O1" if len(active) == 2 else "single_executor_diagnostic",
            "editable_paths": copy.deepcopy(material["editable_paths"]),
            "source_contract": copy.deepcopy(material["source_contract"]),
            "root_goal": material["root_goal"], "max_created_tasks": MAX_CREATED_TASKS,
            "predefined_execution_tasks": False,
            "responsibility_scope": "Members create/revise tasks, claim/transfer responsibility, declare dependencies, and integrate fixed work",
            "submission_requires": ["current_fixed_patch", "current_version_public_test_execution"],
            "public_feedback_protocol": "separate_upstream_public_normal_member_and_untested",
            "forced_initial_failure_feedback": "repair" in material["category"]}


def validate_case(case):
    if not isinstance(case, dict):
        raise ValueError("Case must be a frozen v0.30 model/interface development declaration")
    try:
        expected = case_spec(case["case_id"], first_member=case["first_member"],
                             role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Case must be a frozen v0.30 model/interface development declaration") from error
    if case != expected:
        raise ValueError("Case differs from the frozen v0.30 source/purpose declaration")
    return case


def _public_feedback(task_id, files, *, run_root):
    """Public driver results only; independent fixtures never enter this path."""
    result = source.run_public_tests(task_id, files, run_root=run_root)
    groups = {}
    for name in ("upstream_regressions", "public_normal"):
        tests = [row for row in result["tests"] or [] if row["group"] == name]
        executed = bool(result.get("execution", {}).get("executed", result.get("executed", False)))
        raw_group = result.get("groups", {}).get(name, {})
        executed = bool(raw_group.get("executed", executed))
        passed = bool(tests) and all(row["passed"] for row in tests)
        groups[name] = {"status": ("passed" if passed else "failed") if executed and tests else "untested",
                        "executed": executed, "passed": passed if executed and tests else None, "tests": tests}
    return {"groups": groups, "public_execution": result,
            "passed": all(group["passed"] is True for group in groups.values()),
            "executed": all(group["executed"] for group in groups.values())}


def _member_test_feedback(files, *, run_root):
    code = files.get("test_member.py", "")
    try:
        body = ast.parse(code).body
        substantive = [node for node in body if not isinstance(node, ast.Pass)
                       and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                                and isinstance(node.value.value, str))]
    except SyntaxError:
        substantive = [True]  # Actual execution must expose the syntax failure.
    if not substantive:
        return {"status": "untested", "executed": False, "passed": None,
                "reason": "No executable member test script", "test_discovery": False}
    execution = run_isolated(files, "import runpy\nrunpy.run_path('test_member.py', run_name='__main__')\n",
                             run_root=run_root)
    passed = execution["driver_completed"] and execution["returncode"] == 0
    return {"status": ("passed" if passed else "failed") if execution["executed"] else "untested",
            "executed": execution["executed"], "passed": passed if execution["executed"] else None,
            "execution": execution, "scope": "member_script_execution_no_test_discovery", "test_discovery": False}


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if project_id != PROJECT or actor not in self._software()["case"]["active_roles"]:
            raise ValueError("Only active startup members may use this interface")
        specs = {entry["name"]: entry for entry in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the software interface", code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        for name, schema in specs[tool]["parameters"].get("properties", {}).items():
            value = arguments.get(name)
            if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
                errors.append(name + " exceeds the declared text limit")
            if (isinstance(value, list) and schema.get("uniqueItems")
                    and all(isinstance(item, str) for item in value) and len(set(value)) != len(value)):
                errors.append(name + " must contain distinct items")
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def member_availability(self):
        callback = getattr(self, "runtime_availability", None)
        if callback is not None:
            supplied = copy.deepcopy(callback())
        else:
            supplied = {member: {"status": "ready", "remaining_decisions": limit, "can_receive_work": True}
                        for member, limit in self._software()["case"]["role_decision_limits"].items()}
        return {member: supplied.get(member, {"status": "inactive", "remaining_decisions": 0,
                                              "can_receive_work": False}) for member in MEMBERS}

    def _action_create_task(self, actor, project_id, task_id, description, parent_task_id=ROOT_GOAL_ID):
        tasks = self._software()["tasks"]
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", task_id) or task_id == ROOT_GOAL_ID
                or task_id in tasks):
            raise ValueError("Use a new task ID of 1 to 64 letters, digits, underscores or hyphens, starting with a letter")
        if len(tasks) >= MAX_CREATED_TASKS:
            raise ValueError("The frozen 24-task creation budget is exhausted; revise existing tasks")
        if parent_task_id != ROOT_GOAL_ID:
            self._task(parent_task_id)
        if not description.strip():
            raise ValueError("Task description must not be blank")
        task = {"task_id": task_id, "description": description, "owner": None, "depends_on": [],
                "dependency_revisions": {}, "created_by": actor, "parent_task_id": parent_task_id, "revision": 1}
        tasks[task_id] = task
        self._event(actor, "task_created", task_id=task_id, task_snapshot=task)
        return copy.deepcopy(task)

    def _action_revise_task(self, actor, project_id, task_id, description, expected_revision, reason):
        task = self._task(task_id)
        if task["owner"] != actor and not (task["owner"] is None and task["created_by"] == actor):
            raise ValueError("Only the current owner, or creator while unassigned, may revise this task")
        if expected_revision != task["revision"]:
            raise ValueError("Task revision changed; read the current task board before revising")
        if not description.strip() or not reason.strip() or description == task["description"]:
            raise ValueError("Supply changed task text and a nonblank revision reason")
        before = copy.deepcopy(task)
        task.update(description=description, revision=task["revision"] + 1)
        self._event(actor, "task_revised", task_id=task_id, previous_task=before, task_snapshot=task, reason=reason)
        return copy.deepcopy(task)

    def _action_declare_dependency(self, actor, project_id, task_id, depends_on):
        result = super()._action_declare_dependency(actor, project_id, task_id, depends_on)
        task = self._task(task_id)
        task["dependency_revisions"][depends_on] = self._task(depends_on)["revision"]
        task["revision"] += 1
        event = self.state["software_events"][-1]
        event["task_snapshot"] = copy.deepcopy(task)
        result.update(revision=task["revision"], dependency_revisions=copy.deepcopy(task["dependency_revisions"]))
        return result

    def _action_remove_dependency(self, actor, project_id, task_id, depends_on, reason):
        task = self._task(task_id, actor)
        if depends_on not in task["depends_on"] or not reason.strip():
            raise ValueError("Choose an existing dependency and give a nonblank removal reason")
        before = copy.deepcopy(task)
        task["depends_on"].remove(depends_on)
        del task["dependency_revisions"][depends_on]
        task["revision"] += 1
        self._event(actor, "dependency_removed", task_id=task_id, depends_on=depends_on,
                    previous_task=before, task_snapshot=task, reason=reason)
        return copy.deepcopy(task)

    def _action_send_message(self, actor, project_id, recipient, task_id, body, fixed_reference=None):
        self._available_recipient(actor, recipient)
        if task_id != ROOT_GOAL_ID:
            self._task(task_id)
        if not body.strip():
            raise ValueError("Work message body must not be blank")
        if fixed_reference is not None:
            references = [patch["source_reference"] for patch in self._software()["patches"].values()]
            references += [delivery["source_reference"] for delivery in self._software()["deliveries"]]
            if fixed_reference not in references:
                raise ValueError("Message reference must identify an already published fixed patch or delivery")
        event = self._event(actor, "work_message", recipient=recipient, task_id=task_id,
                            body=body, fixed_reference=fixed_reference)
        return {"message_sequence": event["sequence"], "recipient": recipient,
                "task_id": task_id, "world_file_effect": False}

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        if not task_ids or len(task_ids) != len(set(task_ids)):
            raise ValueError("A fixed patch must name distinct tasks you own")
        snapshots = {task_id: copy.deepcopy(self._task(task_id, actor)) for task_id in task_ids}
        _, _, bundle = self._bundle(actor)
        supplied = {(task["task_id"], task["revision"]) for task in snapshots.values()}
        supplied.update((task["task_id"], task["revision"])
                        for patch_id in bundle["included_patch_ids"]
                        for task in self._patch(patch_id)["task_snapshots"].values())
        for task in snapshots.values():
            if any((task_id, revision) not in supplied
                   for task_id, revision in task["dependency_revisions"].items()):
                raise ValueError("Integrate a fixed patch for the exact declared prerequisite revision, or include it in this patch")
        result = super()._action_fix_patch(actor, project_id, task_ids, message)
        self._software()["patches"][result["patch_id"]]["task_snapshots"] = snapshots
        self.state["software_events"][-1]["task_snapshots"] = copy.deepcopy(snapshots)
        result["task_snapshots"] = copy.deepcopy(snapshots)
        return result

    def _action_read_work_event(self, actor, project_id, sequence):
        events = [event for event in self.state["software_events"] if event["sequence"] == sequence]
        if events and events[0]["kind"] in {"task_created", "task_revised", "dependency_declared", "dependency_removed"}:
            return copy.deepcopy(events[0])
        return super()._action_read_work_event(actor, project_id, sequence)

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        task_id = self._software()["case"]["task_id"]
        result = _public_feedback(task_id, bundle["files"], run_root=self.store.root / "software-execution" / "public")
        member = _member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution" / "member")
        result["groups"]["member_tests"] = member
        result["passed"] = result["passed"] and member["passed"] is not False
        untested = [name for name, group in result["groups"].items() if group["status"] == "untested"]
        result.update(source_reference=base._reference(artifact, version), source_sha256=digest(json_bytes(bundle)),
                      files_sha256=digest(json_bytes(bundle["files"])), suite="separate-public-and-member-v0.30",
                      untested=untested + ["independent_acceptance", "full_upstream_suite"],
                      scope="Executed finite public checks; member scripts have no automatic test discovery",
                      independent_acceptance="not_run_by_public_tool", fixed_submission_is_acceptance=False)
        self._event(actor, "test", **result)
        return result

    def _action_submit_integration(self, actor, project_id, message):
        result = super()._action_submit_integration(actor, project_id, message)
        return {**result, "status": "fixed_submission_pending_independent_acceptance",
                "accepted": None, "fixed_submission_is_acceptance": False}


class SoftwareCollaborationPort(interface.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        if role not in session._world._software()["case"]["active_roles"]:
            raise ValueError("Inactive member has no development role or action opportunities")
        self.profile = VERSION + ":" + role

    def observe(self):
        observation = super().observe()
        world = self._session._world
        case = world._software()["case"]
        reference = observation["workspace_reference"]
        tests = [event for event in world.state["software_events"] if event["kind"] == "test"
                 and event["actor_id"] == self.role and event["source_reference"] == reference]
        coverage = ({name: {key: group[key] for key in ("status", "executed", "passed")}
                     for name, group in tests[-1]["groups"].items()} if tests else {
                         name: {"status": "untested", "executed": False, "passed": None}
                         for name in ("upstream_regressions", "public_normal", "member_tests")})
        initial = world._software().get("initial_public_feedback")
        observation.update(interface_revision=INTERFACE_REVISION,
                           editable_paths=copy.deepcopy(case["editable_paths"]),
                           root_goal={"task_id": ROOT_GOAL_ID, "description": case["root_goal"],
                                      "is_execution_task": False, "immutable": True},
                           task_formation={"level": case["organization_level"], "predefined_tasks": False,
                                           "max_created_tasks": MAX_CREATED_TASKS, "tasks_created": len(observation["tasks"])},
                           acceptance_contract={"requirements": copy.deepcopy(case["source_contract"].get("complete_delivery_requires", [])),
                                                "public_contract": "contract.md", "submission_requires": case["submission_requires"],
                                                "fixed_submission_is_acceptance": False},
                           current_version_test_coverage=coverage,
                           initial_public_feedback=copy.deepcopy(initial),
                           independent_acceptance="not_available_during_work",
                           task_event_sequences=[event["sequence"] for event in world.state["software_events"]
                                                 if event["kind"] in {"task_created", "task_revised", "dependency_declared", "dependency_removed"}])
        return observation


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    material = source.build_case(case["task_id"])
    bundle = {"files": material["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
                "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
                    "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in MEMBERS)
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*MEMBERS, "operator"],
               "objects": objects, "works": [], "grants": [],
               "provenance": {"kind": "synthetic", "note": "Pinned source with new model/interface development contracts; member-created tasks."}}
    instruction = (
        "Complete the common root goal and immutable public contract. There are no predefined execution subtasks. "
        "Use create_task and revise_task to form your own work, claim_task to accept responsibility, and declare_dependency "
        "or remove_dependency to organize it. Both active members have equal tools; no manager or new member is created. "
        "In a single-executor diagnostic only member_a is active. send_message(task_id='root_goal') permits negotiation "
        "before task formation; delegate_task transfers your task to an available partner, who may return_task. "
        "A partner's published patch must be imported explicitly with integrate_patch. Resolve conflicts yourselves. "
        "write_file replaces the entire file; use replace_file for local edits. run_tests always executes the same "
        "public upstream and normal-path groups and separately reports member scripts and untested requirements. "
        "After your last edit, run_tests, publish a current fixed patch, then submit_integration. Test failure does not "
        "prevent a fixed submission, and a fixed submission never establishes independent acceptance. Forced initial "
        "public feedback on repair cases is environment preparation, not your own error discovery. staff_wait suspends "
        "until addressed work or a partner patch; staff_done permanently ends your own remaining opportunities.")
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"],
            "world": {"world_id": "software-collaboration-v030", "actors": {actor: {} for actor in (*MEMBERS, "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": package}],
            "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
                       "config": {"task": instruction}} for member in active],
            "setup": [], "events": [], "start": {"kind": "initial"},
            "boundary": {"max_opportunities": sum(case["role_decision_limits"].values()) + len(active)}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    initial_feedback = None
    if case["forced_initial_failure_feedback"]:
        public = _public_feedback(case["task_id"], bundle["files"], run_root=root / "preparation-public-execution")
        # Measured execution duration belongs to the archived preparation
        # record, not the exact business situation shared across seeds/models.
        atomic_write(root / "initial-public-execution.json", json_bytes(public))
        initial_feedback = {"origin": "forced_baseline_public_test", "actor_trajectory": False,
                            "autonomous_failure_discovery": False, "files_sha256": digest(json_bytes(bundle["files"])),
                            "groups": copy.deepcopy(public["groups"]), "executed": public["executed"],
                            "passed": public["passed"], "original_execution_path": "initial-public-execution.json"}
    with world.store.lock():
        world.state = world.store.load()
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {}, "deliveries": [],
                                                         "initial_public_feedback": initial_feedback}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
              "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "source_contract": copy.deepcopy(case["source_contract"]), "training_eligible": False,
              "actor_trajectories_created": False, "predefined_execution_tasks": False,
              "forced_initial_public_test": initial_feedback is not None}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
                                 "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def software_collaboration_facts(prepared_or_state):
    facts = base.software_collaboration_facts(prepared_or_state)
    facts["version"] = VERSION
    return facts


def assess_files(task_id, files, *, run_root):
    root = Path(run_root)
    independent = source.assess(task_id, files, run_root=root / "independent")
    public = source.run_public_tests(task_id, files, run_root=root / "public")
    executed = all(result["execution"]["executed"] for result in (independent, public))
    components = {"independent_development_contract": independent["passed"],
                  "public_upstream_and_normal_cases": public["passed"]}
    return {"version": CONTRACT_VERSION, "task_id": task_id, "executed": executed,
            "passed": executed and all(components.values()), "components": components,
            "independent_acceptance": independent, "public_acceptance": public,
            "scope": "finite_independent_development_acceptance_and_public_regressions"}


def assess_software_collaboration(prepared, *, run_root):
    """Score only the latest fixed delivery; development evidence is never B/G/I support."""
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
    common = {"version": VERSION, "usage": PURPOSE, "purpose": PURPOSE, "training_eligible": False,
              "independent_confirmation_eligible": False, "contract_version": CONTRACT_VERSION,
              "source_contract": copy.deepcopy(case["source_contract"])}
    if not facts["deliveries"]:
        return {**common, "status": "evaluable", "R": 0, "submitted": False, "reason": "No fixed integrated delivery"}
    delivery = facts["deliveries"][-1]
    _, _, bundle = world._bundle(delivery["actor_id"], reference=delivery["source_reference"])
    result = assess_files(case["task_id"], bundle["files"], run_root=run_root)
    result.update(source_reference=copy.deepcopy(delivery["source_reference"]), files_sha256=delivery["files_sha256"])
    return {**common, **result, "version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
            "R": int(result["passed"]) if result["executed"] else None, "submitted": True, "delivery": delivery}
