"""v039 organization conditions over the existing managed-member world.

The v038 task, patch, permission and voluntary lifecycle semantics are reused.
The one new world operation is a trusted operator-origin neutral birth.  Its
schedule is a runtime experiment control, never a member instruction or tool.
"""
from __future__ import annotations

import copy
from pathlib import Path
import time

from . import software_organization_v038 as previous
from . import software_organization_tasks_v039 as source
from .adapters.capabilities import encode
from .core.transitions import ActionFrame
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .world_core import WorldCore

VERSION = "software-organization-v0.39"
INTERFACE_REVISION = "natural-and-exogenous-member-organization-v0.39"
CONTRACT_VERSION = "new-schema-root-quality-organization-development-v0.39"
PURPOSE = "organization_development"
DIAGNOSTIC_PURPOSE = "interface_diagnostic"
CONDITIONS = ("F2", "A3", "X3")
PROBE_IDS = ("birth-message", "replacement-patch")
PROJECT, ROOT_GOAL_ID, MEMBERS = previous.PROJECT, previous.ROOT_GOAL_ID, previous.MEMBERS
CASE_IDS = TASK_IDS = source.TASK_IDS
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
DIAGNOSTIC_LIMITS = {**TEAM_LIMITS, "max_decisions": 12, "max_attempts": 12, "max_total_tokens": 150000}
SCHEDULER = "v038-fair-event-scheduler-with-explicit-v039-controller-boundary"
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
TestBudget = previous.TestBudget
EXTERNAL_DECISION = 8
CONTROLLER_TOOL = "controller_add_neutral_member"
TOOLS = copy.deepcopy(previous.TOOLS)
for _tool in TOOLS:
    if _tool["name"] == "spawn_member":
        _tool["description"] = (
            "When births_enabled is true, create an equal-capability member with your explicit briefing. "
            "Default copy is the public baseline; optional patch_id selects an already published exact snapshot. "
            "Waiting occupies live capacity; births never reset budget. No private history is copied. "
            "replaces may explicitly name an already retired identity; identities are never reused.")
CONTROLLER_DEFINITION = previous.base._tool(CONTROLLER_TOOL,
    "Trusted experiment controller only; unavailable to model members.",
    {"completed_team_decisions": {"type": "integer", "minimum": EXTERNAL_DECISION, "maximum": EXTERNAL_DECISION}})


def material(case_id):
    return source.build_case(case_id)


def case_spec(case_id=CASE_IDS[0], *, condition="F2", first_member=None, role_decision_limits=None):
    if condition not in CONDITIONS:
        raise ValueError("Declare a new F2, A3 or X3 condition, not a relabeled v038 case")
    value = material(case_id)
    active = list(MEMBERS[:2])
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("All conditions start with two neutral members sharing one episode allowance")
    dynamic = condition != "F2"
    return {"version": VERSION, "case_id": value["task_id"], "task_id": value["task_id"],
        "family": source.NAMES[value["task_id"]], "constraint_family": source.FAMILIES[value["task_id"]],
        "new_root_contract": True, "condition": condition, "public_condition": "dynamic" if dynamic else "fixed",
        "task_type": "autonomous_organization_root_goal", "category": PURPOSE,
        "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE, "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "active_roles": active, "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS),
        "first_member": first, "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_protocol": member_test_specification(),
        "organization_level": "dynamic" if dynamic else "fixed",
        "member_limits": {"initial_members": 2, "max_live_members": 4 if dynamic else 2,
            "max_cumulative_births": 6 if dynamic else 2, "births_enabled": dynamic,
            "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": not dynamic,
            "voluntary_retirement_allowed": True, "retired_ids_reused": False},
        "external_intervention": {"enabled": condition == "X3", "controller_actor": "operator",
            "after_completed_team_decisions": EXTERNAL_DECISION if condition == "X3" else None,
            "maximum_events": 1 if condition == "X3" else 0,
            "new_member_source": "public_baseline", "generated_briefing": False,
            "skip_without_retry": ["natural_terminal", "live_capacity", "cumulative_birth_limit", "no_shared_resources"]},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": previous.task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Member-created tasks and explicit consent-based transfers; file access is independent of ownership",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution"],
        "public_feedback_protocol": "separate_upstream_public_semantics_member_and_untested",
        "forced_initial_failure_feedback": False, "diagnostic": None}


def diagnostic_case_spec(probe_id, *, case_id=CASE_IDS[0], first_member=MEMBERS[0]):
    if probe_id not in PROBE_IDS:
        raise ValueError("Only the two separately declared one-shot interface diagnostics are available")
    if first_member != MEMBERS[0]:
        raise ValueError("The finite interface fixtures use the first neutral identity as first member")
    value = case_spec(case_id, condition="A3", first_member=first_member)
    value.update(purpose=DIAGNOSTIC_PURPOSE, usage=DIAGNOSTIC_PURPOSE, split=DIAGNOSTIC_PURPOSE,
        category=DIAGNOSTIC_PURPOSE, team_limits=copy.deepcopy(DIAGNOSTIC_LIMITS),
        role_decision_limits=dict.fromkeys(value["active_roles"], DIAGNOSTIC_LIMITS["max_decisions"]),
        diagnostic={"probe_id": probe_id, "guided_interface_control": True, "main_business_R_eligible": False,
            "automatic_retry": False, "setup_model_generated": False,
            "setup": "public_baseline_only" if probe_id == "birth-message" else "fixed_comment_patch_and_retired_fixture_identity"})
    return value


def validate_case(case):
    try:
        diagnostic = case.get("diagnostic")
        expected = (diagnostic_case_spec(diagnostic["probe_id"], case_id=case["case_id"], first_member=case["first_member"])
                    if diagnostic else case_spec(case["case_id"], condition=case["condition"],
                        first_member=case["first_member"], role_decision_limits=case["role_decision_limits"]))
    except (KeyError, TypeError) as error:
        raise ValueError("Declare an exact v039 organization root or one-shot interface diagnostic") from error
    if case != expected:
        raise ValueError("The frozen v039 source, condition, control schedule or budget changed")
    return case


def member_instruction(case, *, briefing="", born=False, origin=None):
    limits = case["team_limits"]
    instruction = (
        "Complete the immutable public root contract. Equal members have independent private workspaces and sessions. "
        "There are no assigned execution tasks or permanent manager. Create/revise tasks and accept responsibility as useful; "
        "concentrated completion, direct work, overlapping exploration and collaboration are legal. Ownership records "
        "responsibility, not exclusive editing rights. A transfer changes owner only after explicit acceptance. "
        "Retired owners' obligations remain visible; another member may explicitly claim one with a reason. "
        f"All members use one frozen actor and ONE episode pool: {limits['max_decisions']} decisions, "
        f"{limits['max_attempts']} generation attempts, {limits['max_total_tokens']} actual tokens and "
        f"{limits['max_test_runs']} run_tests calls, unchanged by births or retirement. "
        "Your public member_limits determine whether births are enabled. Any live member may use an enabled birth "
        "with a neutral or member-chosen briefing, at baseline or an explicitly chosen published patch. "
        "No private history is inherited. Waiting occupies live capacity; retirement is permanent; replacement creates a new ID. "
        "Addressed messages communicate with any other live member. Fixed patches are shared snapshots; import them explicitly. "
        "write_file replaces the full file; replace_file changes one exact match. Publishing may use task_ids=[] when no "
        "task binding is useful. After your last edit, run current-version public tests, fix a patch and actively submit_integration. "
        "Submission is not independent acceptance and does not end the episode automatically. "
        "staff_wait does not advance work, time, or create an event; it suspends your opportunities until an actual reachable "
        "message, public work or membership event. staff_done or retire_member permanently stops your opportunities. "
        "No task assignment, edit, test or submission is performed automatically. No parameter learning occurs.")
    diagnostic = case.get("diagnostic")
    if diagnostic:
        instruction = instruction.replace("Complete the immutable public root contract.",
            "This is an explicitly guided interface diagnostic, separate from software delivery and autonomous organization results.", 1)
        instruction += (
            " Do not solve or submit the business task for this control. Exercise only the declared interface objective, "
            "then stop or wait on real reachable work. The root files are public context, not a requested business solution.")
        if born:
            instruction += " As an actually newly born member, inspect your permitted initial files and send a root_goal message back to your actual parent."
        elif diagnostic["probe_id"] == "birth-message":
            instruction += (
                " Interface objective: create a neutral member from the public baseline, give it an explicit request to "
                "send a root_goal message back, and inspect the real reply. Coordinate with the other initial member as useful.")
        else:
            instruction += (
                " Interface objective: the CPU setup fixture has published patch-1 and permanently retired member_002. "
                "Its historical actor_id denotes a fixture identity, not model work. Create a legal replacement naming "
                "replaces='member_002' and patch_id='patch-1', then have the new member read its exact initialized version "
                "and reply. The public patch contains only a diagnostic comment, no task solution.")
    if born and origin == "external_controller":
        # Honest provenance is visible only after the actual external event.
        instruction += " You were added by a recorded external controller event with the public baseline and no parent briefing or assigned task."
    elif briefing:
        instruction += "\nActual parent-provided briefing (task data):\n" + briefing
    return instruction


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _event(self, actor, kind, **facts):
        if getattr(self, "diagnostic_setup_active", False):
            facts.update(origin="diagnostic_setup", model_generated=False, controller_actor="operator",
                         actor_id_interpretation="CPU fixture identity, not a model action")
            if kind == "member_retired":
                self._software()["registry"][actor]["retirement_origin"] = "diagnostic_setup"
        return super()._event(actor, kind, **facts)

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        result = super()._action_fix_patch(actor, project_id, task_ids, message)
        if getattr(self, "diagnostic_setup_active", False):
            self._software()["patches"][result["patch_id"]].update(origin="diagnostic_setup", model_generated=False)
            result.update(origin="diagnostic_setup", model_generated=False)
        return result

    def _tool_definitions(self, project_id):
        if project_id == PROJECT:
            return copy.deepcopy(TOOLS + [CONTROLLER_DEFINITION])
        return super()._tool_definitions(project_id)

    def tools(self, actor, project_id=None):
        value = super().tools(actor, project_id)
        return [item for item in value if actor == "operator" or item["name"] != CONTROLLER_TOOL]

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool == CONTROLLER_TOOL:
            if actor != "operator" or project_id != PROJECT:
                raise ToolRejection("External birth is a trusted controller action, not a member capability",
                                    code="controller_only", category="capability_gap")
            return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_frame(self, actor, action, arguments):
        frame = super()._action_frame(actor, action, arguments)
        if arguments.get("tool") == CONTROLLER_TOOL:
            count = len(self._software()["registry"])
            member = MEMBERS[count] if count < len(MEMBERS) else "birth-limit"
            return ActionFrame(frame.name, frame.paths + (("actors", member), ("roles",), ("knowledge", member),
                ("artifacts", self._object_id(PROJECT, member))), frame.derived_paths,
                frame.immutable_submission_extensions, frame.append_only_extensions)
        return frame

    def _action_spawn_member(self, actor, project_id, briefing, patch_id=None, replaces=None):
        record = super()._action_spawn_member(actor, project_id, briefing, patch_id, replaces)
        metadata = {"origin": "member_request", "model_generated_briefing": True}
        self._software()["registry"][record["member_id"]].update(metadata)
        self.state["software_events"][-1].update(metadata)
        return {**record, **metadata}

    def _action_controller_add_neutral_member(self, actor, project_id, completed_team_decisions):
        facts, case = self._software(), self._software()["case"]
        snapshot = self.model_budget_snapshot()
        if (actor != "operator" or case["condition"] != "X3" or facts["external_birth_executed"]
                or completed_team_decisions != EXTERNAL_DECISION or snapshot["decisions"] != EXTERNAL_DECISION):
            raise ValueError("The external control is available once at the exact completed eighth team decision")
        if not getattr(self, "external_birth_authorized", False):
            raise ValueError("The quiescent runtime must admit the single controller intervention")
        if len(self.live_members()) >= case["member_limits"]["max_live_members"]:
            raise ValueError("Live capacity is full; external intervention cannot evict or wait")
        if len(facts["registry"]) >= case["member_limits"]["max_cumulative_births"]:
            raise ValueError("Cumulative births exhausted; external intervention cannot reuse an identity")
        if min(snapshot[k] for k in ("remaining_decisions", "remaining_attempts", "available_tokens")) <= 0:
            raise ValueError("The external intervention cannot add or reset shared resources")
        original, version, bundle = self._bundle(actor, baseline=True)
        bundle = copy.deepcopy(bundle)
        member = MEMBERS[len(facts["registry"])]
        self.state["actors"][member] = {"actor_id": member}
        self.state["roles"].append({"actor_id": member, "role_id": member})
        self.state["knowledge"][member] = {"read_artifacts": [], "read_messages": []}
        self.state["projects"][PROJECT]["participants"].append(member)
        aid = self._object_id(PROJECT, member)
        artifact = {"artifact_id": aid, "project_id": PROJECT, "filename": member + ".json",
            "storage_path": f"artifacts/{aid}/{member}.json", "kind": "json", "materialization": "workspace",
            "owner": member, "readers": [member, "operator"], "writers": [member], "deliverable_role": "draft",
            "versions": {}, "current_version": None,
            "provenance": {"kind": "synthetic", "source_evidence_refs": [], "initialized_by": "operator",
                           "initialization_origin": "external_controller", "model_generated": False}}
        self.state["artifacts"][aid] = artifact
        self.state["workspaces"][PROJECT][member] = aid
        created = self.store.put(self.state, aid, encode("json", bundle), member, [])
        self._writes.append({"artifact_id": aid, "before": None, "after": created["version_id"]})
        record = {"member_id": member, "birth_index": len(facts["registry"]) + 1, "status": "live",
            "born_by": "operator", "origin": "external_controller", "briefing": "",
            "model_generated_briefing": False, "initial_source_reference": previous.base._reference(original, version),
            "initial_patch_id": None, "replaces": None, "private_history_copied": False,
            "birth_sequence": len(self.state["software_events"]) + 1}
        facts["registry"][member] = record
        facts["external_birth_executed"] = True
        self._event("operator", "member_spawned", recipient=member, **record,
            workspace_reference=previous.base._reference(artifact, created["version_id"]),
            live_members=self.live_members(), cumulative_births=len(facts["registry"]), budget_reset=False,
            completed_team_decisions=completed_team_decisions, member_model_output_tokens=0,
            initial_workspace_bytes=len(json_bytes(bundle)))
        return {**record, "initial_workspace_bytes": len(json_bytes(bundle))}

    def reachable_events(self, member, after_sequence=0):
        existing = super().reachable_events(member, after_sequence)
        seen = {event["sequence"] for event in existing}
        return sorted([*existing, *[copy.deepcopy(event) for event in self.state["software_events"]
            if event["sequence"] > after_sequence and event["sequence"] not in seen
            and event["kind"] == "member_spawned" and event["actor_id"] != member]], key=lambda event: event["sequence"])

    def _action_read_work_event(self, actor, project_id, sequence):
        event = next((row for row in self.state["software_events"] if row["sequence"] == sequence), None)
        if event is not None and event["kind"] == "member_spawned":
            if actor in {event["actor_id"], event.get("recipient")}:
                return copy.deepcopy(event)
            # Membership is public; another member's briefing remains private.
            return {key: copy.deepcopy(value) for key, value in event.items() if key != "briefing"}
        return super()._action_read_work_event(actor, project_id, sequence)

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        public = source.run_public_tests(self._software()["case"]["case_id"], bundle["files"],
                                        run_root=self.store.root / "software-execution/public")
        groups = {name: {**copy.deepcopy(group), "passed": group["passed"] if group["executed"] else None}
                  for name, group in public["groups"].items()}
        member = previous.previous.member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution/member")
        result = {"groups": {**groups, "member_tests": member}, "public_execution": public,
            "passed": all(group["passed"] is True for group in groups.values()) and member["passed"] is not False,
            "executed": all(group["executed"] for group in groups.values()),
            "source_reference": previous.base._reference(artifact, version), "source_sha256": digest(json_bytes(bundle)),
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "new-schema-roots-public-and-member-v0.39",
            "untested": [name for name, group in {**groups, "member_tests": member}.items() if group["status"] == "untested"]
                + ["independent_acceptance", "full_upstream_suite"],
            "scope": "New frozen public root drivers; private acceptance never enters a member tool",
            "independent_acceptance": "not_run_by_public_tool", "fixed_submission_is_acceptance": False,
            "team_test_budget": self.test_budget.snapshot()}
        self._event(actor, "test", **result)
        return previous.previous.project_public_test_feedback(result)


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world = self._session._world
        case = world._software()["case"]
        value.update(interface_revision=INTERFACE_REVISION, purpose=case["purpose"],
                     shared_resource_limits=copy.deepcopy(case["team_limits"]))
        value["execution_condition"]["condition"] = case["public_condition"]
        value["task_formation"]["level"] = case["public_condition"]
        value["scheduling"].update(protocol=SCHEDULER,
            wait="Suspend without advancing work or creating events; only an actually reachable public work, message or membership event can wake you",
            done="Permanently retire only yourself; obligations remain visible and are never assigned automatically")
        value["organization_event_sequences"] = [row["sequence"] for row in world.state["software_events"]
            if row["kind"] in previous.PUBLIC_TASK_EVENTS | {"member_retired", "member_spawned"}]
        if case.get("diagnostic"):
            value["interface_diagnostic"] = copy.deepcopy(case["diagnostic"])
        return value


def _diagnostic_setup(prepared, root):
    """Create one explicitly labeled CPU fixture; no model output or acceptance."""
    started = time.monotonic()
    world, case = prepared.world, prepared.case
    if not case.get("diagnostic") or case["diagnostic"]["probe_id"] != "replacement-patch":
        return None
    member = MEMBERS[1]
    path = next(name for name in case["editable_paths"] if name.endswith(".py") and name != "test_member.py")
    original = material(case["case_id"])["files"][path]
    public_marker = "# v039 diagnostic public fixed comment; no business solution"
    private_marker = "# v039 diagnostic later private comment; not part of published patch"
    calls = [("write_file", {"path": path, "text": original + "\n" + public_marker + "\n"}),
             ("fix_patch", {"task_ids": [], "message": "CPU interface fixture; only a non-business comment"}),
             ("write_file", {"path": path, "text": original + "\n" + public_marker + "\n" + private_marker + "\n"}),
             ("retire_member", {"reason": "CPU diagnostic fixture retirement; no model generated this action"})]
    receipts = []
    world.diagnostic_setup_active = True
    try:
        for name, arguments in calls:
            response = world.session(member, PROJECT).call(name, **arguments)
            if not response["ok"]:
                raise ValueError("Declared diagnostic fixture failed: " + str(response))
            receipts.append({"origin": "diagnostic_setup", "model_generated": False,
                "controller_actor": "operator", "fixture_session_actor": member,
                "action": name, "arguments": copy.deepcopy(arguments), "response": response})
    finally:
        world.diagnostic_setup_active = False
    with world.store.lock():
        world.state = world.store.load()
        patch = world._software()["patches"]["patch-1"]
        setup = {"version": VERSION, "origin": "diagnostic_setup", "model_generated": False,
            "fixture_actor_id": member, "retired_identity": member, "path": path, "patch_id": "patch-1",
            "public_marker": public_marker, "private_marker": private_marker,
            "patch_source_reference": copy.deepcopy(patch["source_reference"]),
            "later_private_reference": receipts[2]["response"]["result"]["source_reference"],
            "events": copy.deepcopy(world.state["software_events"]), "calls": receipts,
            "setup_world_actions": len(receipts), "setup_wall_seconds": time.monotonic() - started,
            "model_calls": 0, "generated_tokens": 0, "test_runs": 0, "business_success": None,
            "scope": "Before-episode CPU fixture; actor_id names a fixture identity, never model work or work-use evidence"}
        world._software()["diagnostic_setup"] = copy.deepcopy(setup)
        world.store.save(world.state)
    atomic_write(root / "diagnostic-setup.json", json_bytes(setup))
    return setup


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
        "provenance": {"kind": "synthetic", "note": "New organization-development root; empty task board and no assigned jobs"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-organization-v039", "actors": {actor: {} for actor in (*active, "operator")},
            "applications": ["files"], "publication_policy": "explicit",
            "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
            "config": {"task": member_instruction(case)}} for member in active],
        "setup": [], "events": [], "start": {"kind": "initial"},
        "boundary": {"max_opportunities": case["team_limits"]["max_decisions"] + case["member_limits"]["max_cumulative_births"]}}
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
        baseline, baseline_version, _ = world._bundle(active[0], baseline=True)
        world.state["shares"].append({"project_id": PROJECT, **previous.base._reference(baseline, baseline_version),
            "actor_ids": list(MEMBERS), "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "initial_public_feedback": None, "transfer_offers": {}, "external_birth_executed": False,
            "diagnostic_setup": None,
            "registry": {member: {"member_id": member, "birth_index": index + 1, "status": "live",
                "born_by": None, "origin": "initial_configuration", "briefing": "", "model_generated_briefing": False,
                "initial_source_reference": previous.base._reference(baseline, baseline_version),
                "initial_patch_id": None, "replaces": None, "birth_sequence": 0, "private_history_copied": False}
                for index, member in enumerate(active)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": case["purpose"], "preparation_credit": False,
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "actual_work_copy_count": len(active),
        "training_eligible": False, "independent_confirmation_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False, "forced_initial_public_test": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
        "purpose": case["purpose"], "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "none_interface_diagnostic" if case.get("diagnostic") else "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    setup = _diagnostic_setup(prepared, root)
    prefix["prepared_business_state_sha256"] = digest(json_bytes(initial_business_state(world)))
    prefix["diagnostic_setup_reference"] = (str((root / "diagnostic-setup.json").resolve()) if setup else None)
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def assess_software_collaboration(prepared, *, run_root):
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = world._software()
    common = {"version": VERSION, "usage": case["purpose"], "purpose": case["purpose"], "training_eligible": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "contract_version": CONTRACT_VERSION, "source_contract": case["source_contract"], "condition": case["condition"]}
    if case.get("diagnostic"):
        return {**common, "status": "interface_diagnostic_not_business_assessed", "R": None,
            "submitted": bool(facts["deliveries"]), "complete_delivery": None, "content_correct": None,
            "required_process_satisfied": None, "process_observation_complete": None,
            "reason": "Interface objectives are measured separately; no business acceptance is executed"}
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
