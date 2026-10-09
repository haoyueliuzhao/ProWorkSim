"""Finite autonomous organization world for frozen-actor development only.

No model, optimizer or critic is constructed here. All member creation comes
from a real accepted tool action. The runtime instantiates independent sessions
from the persisted registry and never invents responsibilities.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_collaboration_v027 as base
from . import software_collaboration_v029 as file_base
from . import software_collaboration_v030 as task_base
from . import software_collaboration_v036 as previous
from . import software_organization_tasks_v038 as source
from .adapters.capabilities import encode
from .core.transitions import ActionFrame
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-organization-v0.38"
INTERFACE_REVISION = "frozen-actor-autonomous-organization-v0.38"
CONTRACT_VERSION = "unchanged-schema-quality-organization-development-v0.38"
PUBLIC_FEEDBACK_VERSION = previous.PUBLIC_FEEDBACK_VERSION
PURPOSE = source.PURPOSE
PROJECT, ROOT_GOAL_ID = previous.PROJECT, previous.ROOT_GOAL_ID
CASE_IDS = TASK_IDS = source.TASK_IDS
MEMBERS = tuple(f"member_{index:03d}" for index in range(1, 7))
CONDITIONS = ("O1", "O2", "O3")
SCHEDULER = "dynamic-shared-budget-fair-event-wakeup-v0.38"
TEAM_LIMITS = copy.deepcopy(previous.TEAM_LIMITS)
TestBudget = previous.TestBudget
MEMBER_TEST_VERSION = previous.MEMBER_TEST_VERSION
member_test_specification = previous.member_test_specification
_TEXT = {"type": "string", "minLength": 1, "maxLength": 2000}
_MEMBER = {"type": "string", "enum": list(MEMBERS)}
PUBLIC_TASK_EVENTS = {"task_created", "task_revised", "dependency_declared", "dependency_removed",
    "claim", "task_returned", "transfer_offered", "transfer_accepted", "transfer_declined", "transfer_expired"}
PUBLIC_EVENTS = PUBLIC_TASK_EVENTS | {"patch_fixed", "submit"}
ADDRESSED_EVENTS = {"work_message", "handoff"}
TOOLS = [copy.deepcopy(item) for item in previous.TOOLS if item["name"] != "delegate_task"]
for _definition in TOOLS:
    for _key in ("recipient", "to_member"):
        if _key in _definition["parameters"]["properties"]:
            _definition["parameters"]["properties"][_key] = copy.deepcopy(_MEMBER)
    if _definition["name"] == "fix_patch":
        _definition["parameters"]["properties"]["task_ids"]["minItems"] = 0
        _definition["description"] = "Publish your actual changed files as an immutable cumulative patch. task_ids=[] explicitly records no task binding, so direct work needs no task-board ceremony; any named tasks must be owned by you and satisfy declared exact-revision dependencies. Publishing is not testing or acceptance."
    if _definition["name"] == "claim_task":
        _definition["parameters"]["properties"]["reason"] = _TEXT
        _definition["description"] = "Accept an unassigned task, or explicitly take over a retired owner's task with a reason. Responsibility does not restrict file editing."
    if _definition["name"] == "return_task":
        _definition["description"] = "Relinquish your task to the shared unassigned board with a reason. Does not assign another member."
    if _definition["name"] == "send_message":
        _definition["description"] = "Send an addressed message to any other live member; root_goal allows negotiation before task creation. Does not transfer ownership or files."
TOOLS += [
    base._tool("offer_transfer", "Offer one owned task to another live member. Ownership stays yours until explicit acceptance of this exact task revision.",
        {"task_id": base._PATH, "to_member": _MEMBER, "reason": _TEXT}),
    base._tool("accept_transfer", "Accept an addressed pending transfer if its owner and task revision remain current.",
        {"offer_id": base._PATH}),
    base._tool("decline_transfer", "Decline an addressed pending transfer with a reason; ownership is unchanged.",
        {"offer_id": base._PATH, "reason": _TEXT}),
    base._tool("spawn_member", "O3 only: create an equal-capability member with your explicit briefing. Default copy is the public baseline; optional patch_id is an already published exact snapshot. Waiting counts toward live capacity; births never reset any budget. No private history is copied.",
        {"briefing": {"type": "string", "minLength": 1, "maxLength": 4000},
         "patch_id": base._PATH, "replaces": _MEMBER}, ["briefing"]),
    base._tool("retire_member", "Permanently retire yourself. Your owned tasks and historical actions remain; others may explicitly claim your orphan obligations. Fixed conditions have no replacement births.",
        {"reason": _TEXT}),
]


def material(case_id):
    return source.build_case(case_id)


def case_spec(case_id=CASE_IDS[0], *, condition="O1", first_member=None, role_decision_limits=None):
    if condition not in CONDITIONS:
        raise ValueError("Organization condition must be O1, O2 or O3")
    value = material(case_id)
    active = list(MEMBERS[:4 if condition == "O2" else 2])
    first = active[0] if first_member is None else first_member
    limits = dict.fromkeys(active, TEAM_LIMITS["max_decisions"])
    if first not in active or role_decision_limits is not None and role_decision_limits != limits:
        raise ValueError("Choose an initial first member; every member shares the one episode pool")
    return {"version": VERSION, "case_id": value["task_id"], "task_id": value["task_id"],
        "original_case_id": value["original_case_id"], "condition": condition,
        "family": "schema", "task_type": "autonomous_organization_root_goal", "category": "organization_development",
        "purpose": PURPOSE, "usage": PURPOSE, "split": PURPOSE,
        "training_eligible": False, "contribution_eligible": False,
        "independent_confirmation_eligible": False, "active_roles": active,
        "role_decision_limits": limits, "team_limits": copy.deepcopy(TEAM_LIMITS), "first_member": first,
        "scheduling_protocol": SCHEDULER, "interface_revision": INTERFACE_REVISION,
        "public_feedback_version": PUBLIC_FEEDBACK_VERSION, "member_test_protocol": member_test_specification(),
        "organization_level": condition,
        "member_limits": {"initial_members": len(active), "max_live_members": 4 if condition == "O3" else len(active),
            "max_cumulative_births": 6 if condition == "O3" else len(active), "births_enabled": condition == "O3",
            "waiting_counts_as_live": True, "fixed_means_fixed_birth_set": True,
            "voluntary_retirement_allowed": True, "retired_ids_reused": False},
        "editable_paths": value["editable_paths"], "source_contract": value["source_contract"],
        "initial_binding": value["initial_binding"], "root_goal": value["root_goal"],
        "max_created_tasks": task_base.MAX_CREATED_TASKS, "predefined_execution_tasks": False,
        "responsibility_scope": "Member-created tasks and explicit consent-based transfers; file ACLs do not depend on task ownership",
        "submission_requires": ["current_fixed_patch", "current_version_public_test_execution"],
        "public_feedback_protocol": "separate_upstream_public_semantics_member_and_untested",
        "forced_initial_failure_feedback": False}


def validate_case(case):
    try:
        expected = case_spec(case["case_id"], condition=case["condition"], first_member=case["first_member"],
            role_decision_limits=case["role_decision_limits"])
    except (KeyError, TypeError) as error:
        raise ValueError("Declare the exact frozen organization-development case") from error
    if case != expected:
        raise ValueError("Frozen organization-development source, condition or budgets changed")
    return case


def member_instruction(case, *, briefing=""):
    instruction = (
        "Complete the immutable public root contract. Equal members have independent private workspaces and sessions. "
        "There are no assigned execution tasks or permanent manager. Create/revise tasks and accept responsibility as useful; "
        "concentrated completion, direct editing/testing, overlapping exploration and collaboration are legal. "
        "Ownership records responsibility, not exclusive editing rights. offer_transfer proposes; accept_transfer is required "
        "before ownership moves; decline_transfer keeps the owner. A retired owner's tasks remain visible obligations, "
        "which another member may explicitly claim with a reason. "
        "All sessions use the same frozen actor and ONE episode pool: 128 decisions, 128 generation attempts, "
        "500000 actual tokens and 32 real run_tests calls, unchanged by births or retirement. "
        "Your execution_condition and member_limits define initial membership and birth capacity. In O3 any live member "
        "may spawn an equal member with an explicit briefing, starting at baseline or an explicitly selected published patch. "
        "No private history is inherited. Waiting still occupies live capacity; retirement is permanent; replacements get new IDs. "
        "send_message addresses any other live member. Fixed patches are shared snapshots; integrate_patch explicitly imports them. "
        "write_file replaces the full file; replace_file changes one exact match. Use the actual APIs and complete all requirements. "
        "After your last edit run current-version public tests, fix a patch and actively submit_integration. "
        "fix_patch(task_ids=[]) explicitly publishes direct work without requiring a task; named tasks must be yours. "
        "Submission is not independent acceptance and does not automatically end the episode. "
        "staff_wait suspends until a reachable real event; no external producer exists. staff_done or retire_member "
        "permanently ends your opportunities. No work, test, transfer or submission is performed automatically. "
        "This is organization development only: no actor/critic update or contribution trial is allowed.")
    return instruction + ("\nActual briefing from the member who created you:\n" + briefing if briefing else "")


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def live_members(self):
        return [member for member, record in self._software()["registry"].items() if record["status"] == "live"]

    def member_availability(self):
        callback = getattr(self, "runtime_availability", None)
        supplied = copy.deepcopy(callback()) if callback is not None else {}
        result = {}
        for member, record in self._software()["registry"].items():
            row = supplied.get(member, {"status": "ready", "remaining_decisions": TEAM_LIMITS["max_decisions"], "can_receive_work": True})
            if record["status"] != "live":
                row = {**row, "status": "retired", "remaining_decisions": 0, "can_receive_work": False}
            result[member] = row
        return result

    def _action_frame(self, actor, action, arguments):
        frame = super()._action_frame(actor, action, arguments)
        if arguments.get("tool") == "spawn_member":
            new_member = MEMBERS[len(self._software()["registry"])] if len(self._software()["registry"]) < len(MEMBERS) else "birth-limit"
            return ActionFrame(frame.name, frame.paths + (("actors", new_member), ("roles",), ("knowledge", new_member),
                ("artifacts", self._object_id(PROJECT, new_member))), frame.derived_paths,
                frame.immutable_submission_extensions, frame.append_only_extensions)
        return frame

    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if project_id != PROJECT or actor not in self.live_members():
            raise ValueError("Only currently live registered members may act")
        specs = {item["name"]: item for item in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the organization interface", code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        for name, schema in specs[tool]["parameters"].get("properties", {}).items():
            value = arguments.get(name)
            if isinstance(value, str) and len(value) > schema.get("maxLength", len(value)):
                errors.append(name + " exceeds its declared text limit")
            if isinstance(value, list) and schema.get("uniqueItems") and all(isinstance(item, str) for item in value) and len(value) != len(set(value)):
                errors.append(name + " must contain distinct items")
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _available_recipient(self, actor, recipient):
        if recipient == actor or recipient not in self.live_members():
            raise ValueError("Choose another currently live member")
        if not self.member_availability()[recipient]["can_receive_work"]:
            raise ValueError("Recipient cannot receive new work under the remaining shared budget")

    def _share_fixed(self, actor, reference):
        # An exact-version grant to every finite legal identity covers later
        # births without giving anyone access to subsequent private versions.
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
            "shared_by": actor, "at": self.state["clock"]})

    def _action_fix_patch(self, actor, project_id, task_ids, message):
        if task_ids:
            return super()._action_fix_patch(actor, project_id, task_ids, message)
        # Direct concentrated work can be fixed without inventing a task merely
        # to satisfy paperwork. Nonempty task bindings retain all old checks.
        result = file_base.SoftwareCollaborationWorld._action_fix_patch(self, actor, project_id, task_ids, message)
        self._software()["patches"][result["patch_id"]]["task_snapshots"] = {}
        self.state["software_events"][-1]["task_snapshots"] = {}
        result["task_snapshots"] = {}
        return result

    def _action_claim_task(self, actor, project_id, task_id, reason=""):
        task = self._task(task_id)
        owner = task["owner"]
        orphan = owner is not None and self._software()["registry"][owner]["status"] == "retired"
        if owner is not None and not orphan:
            raise ValueError("Task is already owned by a live member; use an accepted transfer")
        if orphan and not reason.strip():
            raise ValueError("Explicitly explain taking over the retired owner's obligation")
        task["owner"] = actor
        self._event(actor, "claim", task_id=task_id, previous_owner=owner, owner=actor,
            orphan_takeover=orphan, reason=reason, task_snapshot=task)
        return copy.deepcopy(task)

    def _action_return_task(self, actor, project_id, task_id, reason):
        task = self._task(task_id, actor)
        if not reason.strip():
            raise ValueError("Explain relinquishing responsibility")
        task["owner"] = None
        self._event(actor, "task_returned", task_id=task_id, previous_owner=actor,
            owner=None, reason=reason, task_snapshot=task)
        return copy.deepcopy(task)

    def _action_offer_transfer(self, actor, project_id, task_id, to_member, reason):
        task = self._task(task_id, actor)
        self._available_recipient(actor, to_member)
        if not reason.strip():
            raise ValueError("Give a nonblank transfer reason")
        offers = self._software()["transfer_offers"]
        for row in offers.values():
            if row["task_id"] != task_id or row["status"] != "pending":
                continue
            stale = (row["from_member"] != actor or row["task_revision"] != task["revision"]
                or row["recipient"] not in self.live_members())
            if not stale:
                raise ValueError("Resolve the existing pending offer before offering this task again")
            row.update(status="expired", resolution_reason="Explicit new offer supersedes stale ownership, revision or retired recipient")
            self._event(actor, "transfer_expired", **row)
        offer_id = "offer-" + str(len(offers) + 1)
        offer = {"offer_id": offer_id, "task_id": task_id, "from_member": actor, "recipient": to_member,
            "task_revision": task["revision"], "status": "pending", "reason": reason}
        offers[offer_id] = offer
        self._event(actor, "transfer_offered", **offer, task_snapshot=task)
        return copy.deepcopy(offer)

    def _offered(self, actor, offer_id):
        offer = self._software()["transfer_offers"].get(offer_id)
        if offer is None or offer["recipient"] != actor or offer["status"] != "pending":
            raise ValueError("Choose your addressed pending transfer")
        return offer

    def _action_accept_transfer(self, actor, project_id, offer_id):
        offer = self._offered(actor, offer_id)
        task = self._task(offer["task_id"])
        if task["owner"] != offer["from_member"] or task["revision"] != offer["task_revision"]:
            raise ValueError("Offer owner or task revision is stale; decline and negotiate again")
        task["owner"] = actor
        offer["status"] = "accepted"
        self._event(actor, "transfer_accepted", **offer, previous_owner=offer["from_member"],
            owner=actor, task_snapshot=task)
        return copy.deepcopy(task)

    def _action_decline_transfer(self, actor, project_id, offer_id, reason):
        offer = self._offered(actor, offer_id)
        if not reason.strip():
            raise ValueError("Give a nonblank refusal reason")
        offer.update(status="declined", resolution_reason=reason)
        self._event(actor, "transfer_declined", **offer)
        return copy.deepcopy(offer)

    def _action_spawn_member(self, actor, project_id, briefing, patch_id=None, replaces=None):
        software = self._software()
        limits = software["case"]["member_limits"]
        if not limits["births_enabled"]:
            raise ValueError("The fixed birth set cannot add or replace members")
        if not briefing.strip():
            raise ValueError("A birth requires an actual nonblank member-authored briefing")
        if len(software["registry"]) >= limits["max_cumulative_births"]:
            raise ValueError("Cumulative birth limit exhausted; retired identities are never reused")
        if len(self.live_members()) >= limits["max_live_members"]:
            raise ValueError("Live member capacity exhausted; waiting still occupies capacity")
        if replaces is not None and (replaces not in software["registry"] or software["registry"][replaces]["status"] != "retired"):
            raise ValueError("Replacement must explicitly name a permanently retired member")
        origin, origin_version, bundle = self._bundle(actor, patch_id=patch_id, baseline=patch_id is None)
        bundle = copy.deepcopy(bundle)
        if patch_id is not None:
            bundle["included_patch_ids"] = sorted(set(bundle["included_patch_ids"]) | {patch_id})
        member = MEMBERS[len(software["registry"])]
        self.state["actors"][member] = {"actor_id": member}
        self.state["roles"].append({"actor_id": member, "role_id": member})
        self.state["knowledge"][member] = {"read_artifacts": [], "read_messages": []}
        self.state["projects"][PROJECT]["participants"].append(member)
        aid = self._object_id(PROJECT, member)
        artifact = {"artifact_id": aid, "project_id": PROJECT, "filename": member + ".json",
            "storage_path": f"artifacts/{aid}/{member}.json", "kind": "json", "materialization": "workspace",
            "owner": member, "readers": [member, "operator"], "writers": [member], "deliverable_role": "draft",
            "versions": {}, "current_version": None,
            "provenance": {"kind": "synthetic", "source_evidence_refs": []}}
        self.state["artifacts"][aid] = artifact
        self.state["workspaces"][PROJECT][member] = aid
        version = self.store.put(self.state, aid, encode("json", bundle), member, [])
        self._writes.append({"artifact_id": aid, "before": None, "after": version["version_id"]})
        record = {"member_id": member, "birth_index": len(software["registry"]) + 1, "status": "live",
            "born_by": actor, "briefing": briefing, "initial_source_reference": base._reference(origin, origin_version),
            "initial_patch_id": patch_id, "replaces": replaces,
            "birth_sequence": len(self.state["software_events"]) + 1, "private_history_copied": False}
        software["registry"][member] = record
        self._event(actor, "member_spawned", recipient=member, **record,
            workspace_reference=base._reference(artifact, version["version_id"]),
            live_members=self.live_members(), cumulative_births=len(software["registry"]), budget_reset=False)
        return copy.deepcopy(record)

    def _action_retire_member(self, actor, project_id, reason):
        if not reason.strip():
            raise ValueError("Retirement requires a nonblank reason")
        record = self._software()["registry"][actor]
        record.update(status="retired", retirement_reason=reason,
            retirement_sequence=len(self.state["software_events"]) + 1)
        obligations = [task["task_id"] for task in self._software()["tasks"].values() if task["owner"] == actor]
        self._event(actor, "member_retired", member_id=actor, reason=reason,
            retained_obligations=obligations, live_members=self.live_members(), automatic_reassignment=False)
        return {"member_id": actor, "status": "retired", "retained_obligations": obligations}

    def retire_member(self, member, reason="staff_done"):
        """Runtime hook after an actual staff_done; executes a recorded transition."""
        self.state = self.store.load()
        if member not in self._software()["registry"]:
            raise ValueError("Unknown member")
        if self._software()["registry"][member]["status"] == "retired":
            return copy.deepcopy(self._software()["registry"][member])
        response = self.session(member, PROJECT).call("retire_member", reason=reason)
        if not response["ok"]:
            raise ValueError(response)
        return response["result"]

    def reachable_events(self, member, after_sequence=0):
        return [copy.deepcopy(event) for event in self.state["software_events"]
            if event["sequence"] > after_sequence and event["actor_id"] != member
            and (event["kind"] in PUBLIC_EVENTS
                 or event["kind"] in ADDRESSED_EVENTS and event.get("recipient") == member
                 or event["kind"] == "member_retired" and bool(event["retained_obligations"]))]

    def _action_read_work_event(self, actor, project_id, sequence):
        event = next((row for row in self.state["software_events"] if row["sequence"] == sequence), None)
        if event is None:
            raise ValueError("Unknown work event")
        if event["kind"] in PUBLIC_EVENTS or event["kind"] == "member_retired":
            return copy.deepcopy(event)
        if event["kind"] in ADDRESSED_EVENTS | {"member_spawned"} and actor in {event["actor_id"], event.get("recipient")}:
            return copy.deepcopy(event)
        raise ValueError("Choose a public event or your own addressed event; private edits are not shared")

    def _action_run_tests(self, actor, project_id):
        artifact, version, bundle = self._bundle(actor)
        self.test_budget.consume(actor)
        public = source.run_public_tests(self._software()["case"]["case_id"], bundle["files"],
            run_root=self.store.root / "software-execution/public")
        groups = {name: {**copy.deepcopy(group), "passed": group["passed"] if group["executed"] else None}
            for name, group in public["groups"].items()}
        member = previous.member_test_feedback(bundle["files"], run_root=self.store.root / "software-execution/member")
        result = {"groups": {**groups, "member_tests": member}, "public_execution": public,
            "passed": all(group["passed"] is True for group in groups.values()) and member["passed"] is not False,
            "executed": all(group["executed"] for group in groups.values()),
            "source_reference": base._reference(artifact, version), "source_sha256": digest(json_bytes(bundle)),
            "files_sha256": digest(json_bytes(bundle["files"])), "suite": "unchanged-schema-public-and-member-v0.38",
            "untested": [name for name, group in {**groups, "member_tests": member}.items() if group["status"] == "untested"]
                + ["independent_acceptance", "full_upstream_suite"],
            "scope": "Unchanged parent public quality drivers; no private acceptance input enters a member tool",
            "independent_acceptance": "not_run_by_public_tool", "fixed_submission_is_acceptance": False,
            "team_test_budget": self.test_budget.snapshot()}
        self._event(actor, "test", **result)
        return previous.project_public_test_feedback(result)


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **_):
        if role not in session._world._software()["registry"] or session.actor_id != role or session.project_id != PROJECT:
            raise ValueError("Member identity must match a registered trusted session")
        self._session, self.role = session, role
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world = self._session._world
        facts, case = world._software(), world._software()["case"]
        registry = {member: {key: copy.deepcopy(item) for key, item in row.items() if key != "briefing"}
            for member, row in facts["registry"].items()}
        value.update(interface_revision=INTERFACE_REVISION, purpose=PURPOSE,
            execution_condition={"condition": case["condition"], "initial_members": case["active_roles"],
                "active_executors": world.live_members(), "cumulative_births": len(registry),
                "private_working_copies": len(registry), "same_actor_shared_across_sessions": True,
                "centralized_completion_allowed": True, "preassigned_tasks_or_manager": False},
            member_registry=registry, member_limits=copy.deepcopy(case["member_limits"]),
            own_initial_briefing=facts["registry"][self.role]["briefing"],
            transfer_offers=copy.deepcopy(facts["transfer_offers"]),
            orphan_obligations=[copy.deepcopy(task) for task in facts["tasks"].values()
                if task["owner"] and facts["registry"][task["owner"]]["status"] == "retired"],
            organization_event_sequences=[row["sequence"] for row in world.state["software_events"]
                if row["kind"] in PUBLIC_TASK_EVENTS | {"member_retired"}])
        value["scheduling"].update(protocol=SCHEDULER,
            done="Permanently retire only yourself; owned obligations remain visible and no assignment is automatic",
            wait="Wait for a real addressed message, public task/responsibility change, fixed patch or retained obligation; still consumes a live member position")
        return value


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    bundle = {"files": material(case["case_id"])["files"], "included_patch_ids": []}
    active = case["active_roles"]
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
        "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle}]
    # WorldCore installation validates current actors. Future members receive
    # baseline read access only when their creation transaction commits.
    objects[0]["readers"] = [*active, "operator"]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
        "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in active)
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*active, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "synthetic", "note": "Organization-development variant; same schema quality contracts, no predefined decomposition"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"],
        "world": {"world_id": "software-organization-v038", "actors": {actor: {} for actor in (*active, "operator")},
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
    with world.store.lock():
        world.state = world.store.load()
        baseline, baseline_version, _ = world._bundle(active[0], baseline=True)
        # Finite exact baseline access, shared to future valid birth identities.
        world.state["shares"].append({"project_id": PROJECT, **base._reference(baseline, baseline_version),
            "actor_ids": list(MEMBERS), "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "initial_public_feedback": None, "transfer_offers": {},
            "registry": {member: {"member_id": member, "birth_index": index + 1, "status": "live",
                "born_by": None, "briefing": "", "initial_source_reference": base._reference(baseline, baseline_version),
                "initial_patch_id": None, "replaces": None, "birth_sequence": 0, "private_history_copied": False}
                for index, member in enumerate(active)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "usage": PURPOSE, "preparation_credit": False,
        "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract": case["source_contract"], "initial_binding": case["initial_binding"],
        "condition": case["condition"], "actual_work_copy_count": len(active),
        "training_eligible": False, "independent_confirmation_eligible": False,
        "actor_trajectories_created": False, "predefined_execution_tasks": False, "forced_initial_public_test": False}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION, "training_supported": False,
        "purpose": PURPOSE, "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
        "independent_assessment": "assess_software_collaboration"}, prefix)
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared


def software_collaboration_facts(prepared_or_state):
    return {**base.software_collaboration_facts(prepared_or_state), "version": VERSION}


def assess_software_collaboration(prepared, *, run_root):
    case = validate_case(prepared.case)
    world = prepared.world
    world.state = world.store.load()
    facts = software_collaboration_facts(world.state)
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
    return {**common, **result, "version": VERSION, "status": "evaluable" if result["executed"] else "unknown",
        "R": int(result["passed"]) if result["executed"] else None,
        "complete_delivery": result["passed"] if result["executed"] else None,
        "submitted": True, "delivery": delivery, "source_reference": delivery["source_reference"],
        "files_sha256": delivery["files_sha256"]}
