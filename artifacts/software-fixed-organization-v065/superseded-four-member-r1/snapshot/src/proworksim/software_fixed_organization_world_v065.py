"""Fixed four-member organizations over the existing managed repository world.

Only this new world changes membership and direct collaboration routing. Public
task-board facts and explicitly published fixed versions retain their original
shared harness semantics. Unpublished working versions stay private.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_benchmark_world_v056 as previous
from . import software_benchmark_world_v054 as repository_world
from . import software_organization_v038 as organization_world
from . import software_organization_v042 as paged
from .software_fixed_organization_v065 import MEMBERS, get_organization, validate_organization
from .harness_policy_v040 import FORBIDDEN_TOOLS
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "v065-fixed-four-member-managed-world-r1"
PURPOSE = "fixed_organization_implementation_only"
PROJECT = previous.PROJECT
MAX_DECISIONS, MAX_TEST_RUNS = 512, 512
DYNAMIC_TOOLS = frozenset({"spawn_member", "retire_member", "delegate_task", "external_spawn_member"})


def _positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + " must be an explicit positive integer")
    return value


def case_spec(case_id, *, provider, organization_id, max_total_tokens,
              max_decisions=MAX_DECISIONS, max_test_runs=MAX_TEST_RUNS):
    spec = get_organization(organization_id)
    validate_organization(spec)
    for value, name in ((max_total_tokens, "team tokens"), (max_decisions, "team decisions"),
                        (max_test_runs, "team public tests")):
        _positive(value, name)
    case = previous.case_spec(case_id, provider=provider)
    case.update(version=VERSION, interface_revision=VERSION, purpose=PURPOSE,
        usage=PURPOSE, category=PURPOSE, split=PURPOSE, condition=organization_id,
        organization_level="fixed_four_members", task_type="public_repository_fixed_organization",
        active_roles=list(MEMBERS), role_decision_limits={m: max_decisions for m in MEMBERS},
        team_limits={"max_decisions": max_decisions, "max_attempts": max_decisions,
                     "max_total_tokens": max_total_tokens, "max_test_runs": max_test_runs},
        first_member=spec["phases"][0]["active_members"][0],
        scheduling_protocol="v065-fixed-cyclic-organization-phases",
        fixed_organization=spec,
        member_limits={"initial_members": 4, "max_live_members": 4,
            "max_cumulative_births": 4, "births_enabled": False, "waiting_counts_as_live": True,
            "fixed_means_fixed_birth_set": True, "voluntary_retirement_allowed": False,
            "retired_ids_reused": False, "stable_identities": True,
            "staff_done_scope": "end_current_work_until_real_visible_event"},
        external_intervention={"enabled": False, "maximum_events": 0,
            "scope": "No external worker, automatic task assignment or synthetic wake event"},
        formal_execution_authorized=False,
        future_budget_selection="Wait for the single-model token-bound experiment; this explicit value is an injected implementation fixture or later frozen budget",
        communication_scope="Directed direct messages, patch handoffs and task transfers; shared public task-board metadata remains an indirect channel",
        submission_requires=["current_fixed_patch", "current_version_public_test_execution",
                             "designated_delivery_member", "no_forbidden_controller_request"])
    return case


def validate_case(case, *, provider):
    expected = case_spec(case["case_id"], provider=provider,
        organization_id=case["fixed_organization"]["id"],
        max_total_tokens=case["team_limits"]["max_total_tokens"],
        max_decisions=case["team_limits"]["max_decisions"],
        max_test_runs=case["team_limits"]["max_test_runs"])
    if case != expected:
        raise ValueError("The fixed organization, public source or shared team allowances changed")
    return case


def member_instruction(case, member):
    if member not in MEMBERS:
        raise ValueError("Use one of the four fixed identities")
    spec, limits = case["fixed_organization"], case["team_limits"]
    recipients = [target for source, target in spec["communication_edges"] if source == member]
    return (
        f"Resolve the unchanged original repository issue. You are {member}, "
        f"role {spec['roles'][member]['title']}, in organization {spec['name']}. "
        + spec["roles"][member]["instruction"] + " "
        "All four members use the same model and managed tools, with separate private versions, "
        "SDK conversations and notes. No shell, hidden grading, recruitment or replacement exists. "
        f"Your legal direct recipients are {', '.join(recipients)}. "
        "fix_patch explicitly publishes that immutable version to all four legal members. "
        "Later private edits do not propagate. handoff_patch is a directed notice along a legal edge. "
        "Members must explicitly integrate_patch to use a published version; messages do not merge code. "
        "Task-board metadata is shared. Optional task ownership changes require offer_transfer and "
        "accept_transfer; a message cannot transfer responsibility. "
        "Use read_task for exact issue pages, search_repository or list_files/read_file to locate code, "
        "and write_file/replace_file/create_file/delete_file/rename_file for permitted edits. "
        "Use null or empty cursor for the first page and copy next_cursor unchanged for continuation. "
        "run_tests uses only the frozen public entrypoint on your exact current version. "
        f"The whole team shares {limits['max_total_tokens']} cumulative input-plus-output tokens, "
        f"{limits['max_decisions']} model decisions, {limits['max_attempts']} attempts and "
        f"{limits['max_test_runs']} accepted public test operations; these are not per-member grants. "
        "Communication, reading history, format repair and rejected requests consume real work. "
        f"Only {spec['delivery_member']} may submit the final integration and its final working tree "
        "is the predeclared code endpoint; other members' unmerged code is never selected by a grader. "
        "After the final edit/integration, explicitly run_tests, fix_patch(task_ids=[]), then "
        "submit_integration. Public tests need to execute on that same version; a pass is not hidden "
        "acceptance. staff_done ends your current work, staff_wait suspends it; a real later visible "
        "event may wake the same session without extra budget. No action is performed automatically. "
        + paged.PAGING_INSTRUCTION)


def tool_definitions(case):
    tools = [copy.deepcopy(item) for item in previous.tool_definitions(case)
             if item["name"] not in DYNAMIC_TOOLS]
    for item in tools:
        for name in ("recipient", "to_member"):
            prop = item["parameters"].get("properties", {}).get(name)
            if isinstance(prop, dict):
                prop["enum"] = list(MEMBERS)
        if item["name"] == "run_tests":
            item["description"] = (
                "Run the frozen public repository test entrypoint on your exact current private tree. "
                f"The whole team has {case['team_limits']['max_test_runs']} accepted test calls; "
                "read immutable 3072-character pages without rerunning. Hidden grading is unavailable.")
        elif item["name"] == "handoff_patch":
            item["description"] += (
                " Only a declared direct recipient is legal. A handoff notifies a peer about an "
                "already published immutable version; it does not copy private edits or integrate code.")
    return tools


class TestBudget:
    def __init__(self, output, limit):
        self.output, self.limit, self.records = Path(output), _positive(limit, "test limit"), []

    def consume(self, actor):
        if actor not in MEMBERS:
            raise ValueError("Only fixed team members may consume public tests")
        if len(self.records) >= self.limit:
            raise ToolRejection("The shared public-test allowance is exhausted",
                                code="team_test_budget_exhausted", category="capability_gap")
        self.records.append({"index": len(self.records) + 1, "actor_id": actor})
        atomic_write(self.output, json_bytes(self.snapshot()))

    def snapshot(self):
        return {"limit": self.limit, "used": len(self.records),
                "remaining": self.limit - len(self.records), "records": copy.deepcopy(self.records),
                "maximum_executions_per_run_tests": 1, "scope": "One shared four-member public-test pool"}


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def __init__(self, root):
        super().__init__(root)
        self.fixed_candidates_closed = (Path(self.store.control) / "v065-candidate-close.json").exists()

    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()["case"]) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _edge(self, sender, recipient):
        if [sender, recipient] not in self._software()["case"]["fixed_organization"]["communication_edges"]:
            raise ToolRejection("The fixed organization does not permit this direct collaboration edge",
                code="fixed_organization_edge", category="business_constraint")

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool in FORBIDDEN_TOOLS:
            # Keep the existing process-violation classification exactly.
            return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)
        if tool in DYNAMIC_TOOLS:
            raise ToolRejection("The fixed team cannot add, replace, retire or directly delegate members",
                                code="fixed_organization_membership", category="capability_gap")
        if getattr(self, "fixed_candidates_closed", False):
            raise ToolRejection("The unique final candidates have already been locked",
                                code="fixed_candidates_closed", category="business_constraint")
        active = getattr(self, "scheduled_member", None)
        if getattr(self, "require_scheduled_actions", False) and active != actor:
            raise ToolRejection("A managed action requires this member's current scheduled opportunity",
                                code="fixed_organization_schedule", category="business_constraint")
        if tool == "send_message":
            self._edge(actor, arguments.get("recipient"))
            ref = arguments.get("fixed_reference")
            if ref is not None:
                self._bundle(actor, reference=ref)
        elif tool in {"handoff_patch", "offer_transfer"}:
            self._edge(actor, arguments.get("to_member"))
        elif tool in {"accept_transfer", "decline_transfer"}:
            offer = self._software()["transfer_offers"].get(arguments.get("offer_id"), {})
            if offer.get("recipient") == actor:
                self._edge(offer.get("from_member"), actor)
        if tool == "submit_integration" and actor != self._software()["case"]["fixed_organization"]["delivery_member"]:
            raise ToolRejection("Only the predeclared integration member may submit the team delivery",
                                code="fixed_delivery_member", category="business_constraint")
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _available_recipient(self, actor, recipient):
        self._edge(actor, recipient)
        return super()._available_recipient(actor, recipient)

    def _share_fixed(self, actor, reference):
        # Preserve the original multi-member publication contract; the S1
        # subclass's single-recipient constant must not accidentally survive.
        self.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
                                     "shared_by": actor, "at": self.state["clock"]})

    def _action_run_tests(self, actor, project_id):
        if getattr(self, "_active_public_test_actor", None) is not None:
            raise ValueError("Public execution must be serialized through the managed world")
        self._active_public_test_actor = actor
        try:
            return super()._action_run_tests(actor, project_id)
        finally:
            self._active_public_test_actor = None


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        # The original registry-bound port supports four real members. Bypass
        # only the later S1 constructor, not the trusted session identity check.
        organization_world.SoftwareCollaborationPort.__init__(self, session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        value = super().observe()
        world, facts = self._session._world, self._session._world._software()
        case, spec = facts["case"], facts["case"]["fixed_organization"]
        value.update(profile=VERSION, interface_revision=VERSION, purpose=PURPOSE,
            fixed_organization={"id": spec["id"], "name": spec["name"],
                "role": copy.deepcopy(spec["roles"][self.role]), "members": list(MEMBERS),
                "role_directory": {member: {"member_id": member, **copy.deepcopy(spec["roles"][member])}
                                   for member in MEMBERS},
                "direct_recipients": [b for a, b in spec["communication_edges"] if a == self.role],
                "delivery_member": spec["delivery_member"], "shared_task_board": True,
                "fixed_publication_visible_to_all_members": True,
                "schedule": copy.deepcopy(getattr(world, "schedule_observation", {}))},
            transfer_offers={key: copy.deepcopy(row) for key, row in facts["transfer_offers"].items()
                             if self.role in {row["from_member"], row["recipient"]}},
            execution_condition={"condition": spec["id"], "initial_members": list(MEMBERS),
                "active_executors": world.live_members(), "private_working_copies": 4,
                "same_actor_shared_across_sessions": True, "hidden_partners": False},
            member_limits=copy.deepcopy(case["member_limits"]))
        value["scheduling"].update(protocol=case["scheduling_protocol"], first_member=case["first_member"],
            fixed_phases=copy.deepcopy(spec["phases"]),
            wait="Wait until a real reachable event; fixed membership and shared budget remain unchanged",
            done="End current work in the same session; a real reachable event may reopen it")
        return value


def build_software_collaboration_case(case, root, *, provider, organization_id=None,
                                     max_total_tokens=None, max_decisions=MAX_DECISIONS,
                                     max_test_runs=MAX_TEST_RUNS):
    case = (case_spec(case, provider=provider, organization_id=organization_id,
        max_total_tokens=max_total_tokens, max_decisions=max_decisions, max_test_runs=max_test_runs)
        if isinstance(case, str) else validate_case(copy.deepcopy(case), provider=provider))
    if provider.runner is None:
        raise ValueError("Bind an explicitly confined, public-only callback")
    material = provider.build_case(case["case_id"])
    bundle = {"files": material["files"], "entry_metadata": material["entry_metadata"], "included_patch_ids": []}
    provider.validate_files(case["case_id"], bundle["files"], entry_metadata=bundle["entry_metadata"])
    objects = [{"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
                "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle}]
    objects.extend({"alias": member, "filename": member + ".json", "kind": "json", "owner": member,
        "readers": [member, "operator"], "writers": [member], "data": copy.deepcopy(bundle)} for member in MEMBERS)
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*MEMBERS, "operator"],
        "objects": objects, "works": [], "grants": [],
        "provenance": {"kind": "reconstructed", "note": "Same public faulty repository; no hidden answers"}}
    scenario = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-" + case["condition"] + "-v065",
        "world": {"world_id": "software-fixed-organization-v065", "actors": {a: {} for a in (*MEMBERS, "operator")},
            "applications": ["files"], "publication_policy": "explicit",
            "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
        "installer": "operator", "projects": [{"package": package}],
        "roles": [{"role_id": member, "actor": member, "project": PROJECT, "policy": "model",
                   "config": {"task": member_instruction(case, member)}} for member in MEMBERS],
        "setup": [], "events": [], "start": {"kind": "initial"},
        "boundary": {"max_opportunities": case["team_limits"]["max_decisions"] + 1}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(scenario, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.source_provider, world.test_budget = provider, TestBudget(root / "team-test-budget.json", case["team_limits"]["max_test_runs"])
    with world.store.lock():
        world.state = world.store.load()
        artifact, version, _ = world._bundle(MEMBERS[0], baseline=True)
        source = repository_world._reference(artifact, version)
        world.state["shares"].append({"project_id": PROJECT, **source, "actor_ids": list(MEMBERS),
                                     "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {"case": case, "tasks": {}, "patches": {},
            "deliveries": [], "test_reports": {}, "initial_public_feedback": None,
            "transfer_offers": {}, "initial_diagnostics": {},
            "initial_diagnostic_assignments": {member: [] for member in MEMBERS},
            "registry": {member: {"member_id": member, "birth_index": i + 1, "status": "live",
                "born_by": None, "origin": "initial_fixed_organization", "briefing": "",
                "model_generated_briefing": False, "initial_source_reference": source,
                "initial_patch_id": None, "replaces": None, "birth_sequence": 0,
                "private_history_copied": False} for i, member in enumerate(MEMBERS)}}
        world.store.save(world.state)
    prefix = {"version": VERSION, "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
        "source_contract_sha256": digest(json_bytes(case["source_contract"])),
        "initial_binding_sha256": digest(json_bytes(case["initial_binding"])),
        "organization_sha256": digest(json_bytes(case["fixed_organization"])),
        "model_calls": 0, "test_executions": 0, "hidden_evaluation_calls": 0}
    prepared = PreparedOnlineCase(deployment, case, {"version": VERSION,
        "training_supported": False, "purpose": PURPOSE, "source_partition_sha256": provider.manifest_sha256,
        "runtime_process_contract": case["process_contract"]}, prefix)
    prepared.port_factory, prepared.source_provider = SoftwareCollaborationPort, provider
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared
