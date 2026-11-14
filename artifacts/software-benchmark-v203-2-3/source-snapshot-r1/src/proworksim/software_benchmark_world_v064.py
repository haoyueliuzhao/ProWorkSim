"""Actual S1 rules with explicit REF-aligned episode allowances.

Reuse the repaired v056 operations, permissions and delivery evidence. Only
resource quotas, the visible resource declaration and this version change.
"""
from __future__ import annotations

import copy
from pathlib import Path

from . import software_benchmark_world_v056 as previous
from .software_benchmark_world_v054 import _reference
from .scenarios import SCENARIO_VERSION, build_scenario, initial_business_state
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import PreparedOnlineCase
from .tool_outcomes import ToolRejection

VERSION = "software-benchmark-world-v064-ref-aligned-S1"
PURPOSE = "full_verified_single_agent_comparison_v064"
PROJECT, MEMBERS = previous.PROJECT, previous.MEMBERS
BUDGETS = frozenset((5_000_000, 7_500_000, 10_000_000))
MAX_DECISIONS = 512
MAX_TEST_RUNS = 512


def case_spec(case_id, *, provider, max_total_tokens):
    if type(max_total_tokens) is not int or max_total_tokens not in BUDGETS:
        raise ValueError("Only the three predeclared v064 cumulative budgets are supported")
    case = previous.case_spec(case_id, provider=provider)
    case.update(version=VERSION, interface_revision=VERSION, purpose=PURPOSE,
                usage=PURPOSE, category=PURPOSE, split=PURPOSE,
                role_decision_limits={MEMBERS[0]: MAX_DECISIONS},
                team_limits={"max_decisions": MAX_DECISIONS, "max_attempts": MAX_DECISIONS,
                             "max_total_tokens": max_total_tokens, "max_test_runs": MAX_TEST_RUNS},
                scheduling_protocol="v064-fixed-S1-ref-aligned-allowances")
    return case


def validate_case(case, *, provider):
    expected = case_spec(case["case_id"], provider=provider,
                         max_total_tokens=case["team_limits"]["max_total_tokens"])
    if case != expected:
        raise ValueError("The v064 source, permissions, identity or explicit allowance changed")
    return case


def member_instruction(case):
    limits = case["team_limits"]
    return (previous.member_instruction(case) +
            f" This episode has {limits['max_decisions']} model decisions, "
            f"{limits['max_attempts']} generation attempts, and "
            f"{limits['max_total_tokens']} cumulative input plus output tokens. "
            f"At most {limits['max_test_runs']} public run_tests operations are available, "
            "each also uses a real decision. These allowances are shared by the sole member; "
            "reading history, rejected formats and organizational operations are not free.")


def tool_definitions(case):
    tools = previous.tool_definitions(case)
    for tool in tools:
        if tool["name"] == "run_tests":
            tool["description"] = (
                "Execute the frozen repository-wide public test entrypoint on this exact current "
                "workspace once, with at most 512 accepted calls per episode. Read immutable "
                "3072-character feedback pages without rerunning tests. Hidden acceptance is "
                "unavailable; a public pass is not official resolved status.")
    return tools


class TestBudget:
    """Count actual accepted public-test attempts outside world rollback."""
    def __init__(self, output):
        self.output, self.records = Path(output), []

    def consume(self, actor):
        if actor != MEMBERS[0]:
            raise ValueError("Only the original S1 member may consume public tests")
        if len(self.records) >= MAX_TEST_RUNS:
            raise ToolRejection("The 512-call public-test allowance is exhausted",
                                code="team_test_budget_exhausted", category="capability_gap")
        self.records.append({"index": len(self.records) + 1, "actor_id": actor,
                             "scope": "One accepted public-test operation, including execution failures"})
        atomic_write(self.output, json_bytes(self.snapshot()))

    def snapshot(self):
        return {"limit": MAX_TEST_RUNS, "used": len(self.records),
                "remaining": MAX_TEST_RUNS - len(self.records), "records": copy.deepcopy(self.records),
                "maximum_executions_per_run_tests": 1,
                "scope": "Only the frozen public entrypoint; no hidden grader or injected member script"}


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def _tool_definitions(self, project_id):
        return tool_definitions(self._software()["case"]) if project_id == PROJECT else super()._tool_definitions(project_id)


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        value.update(interface_revision=VERSION, profile=VERSION, purpose=PURPOSE)
        value["aligned_resource_allowances"] = copy.deepcopy(self._session._world._software()["case"]["team_limits"])
        return value


def build_software_collaboration_case(case, root, *, provider, max_total_tokens=None):
    case = (case_spec(case, provider=provider, max_total_tokens=max_total_tokens)
            if isinstance(case, str) else validate_case(case, provider=provider))
    if max_total_tokens is not None and case["team_limits"]["max_total_tokens"] != max_total_tokens:
        raise ValueError("The supplied and declared cumulative allowances differ")
    if provider.runner is None:
        raise ValueError("A confined public-only test callback must be explicitly bound")
    material = provider.build_case(case["case_id"])
    bundle = {"files": material["files"], "entry_metadata": material["entry_metadata"],
              "included_patch_ids": []}
    provider.validate_files(case["case_id"], bundle["files"], entry_metadata=bundle["entry_metadata"])
    objects = [
        {"alias": "baseline", "filename": "baseline.json", "kind": "json", "owner": "operator",
         "readers": [*MEMBERS, "operator"], "writers": ["operator"], "data": bundle},
        {"alias": MEMBERS[0], "filename": MEMBERS[0] + ".json", "kind": "json", "owner": MEMBERS[0],
         "readers": [MEMBERS[0], "operator"], "writers": [MEMBERS[0]], "data": copy.deepcopy(bundle)},
    ]
    package = {"project_id": PROJECT, "goal": case["root_goal"], "participants": [*MEMBERS, "operator"],
               "objects": objects, "works": [], "grants": [],
               "provenance": {"kind": "reconstructed", "note": "Public baseline only; no answer or hidden grading material"}}
    spec = {"version": SCENARIO_VERSION, "scenario_id": case["case_id"] + "-S1-v064",
            "world": {"world_id": "software-benchmark-v064", "actors": {a: {} for a in (*MEMBERS, "operator")},
                      "applications": ["files"], "publication_policy": "explicit",
                      "bootstrap_grants": [{"actor_id": "operator", "power": "install_project", "scope": "world"}]},
            "installer": "operator", "projects": [{"package": package}],
            "roles": [{"role_id": MEMBERS[0], "actor": MEMBERS[0], "project": PROJECT, "policy": "model",
                       "config": {"task": member_instruction(case)}}],
            "setup": [], "events": [], "start": {"kind": "initial"},
            "boundary": {"max_opportunities": MAX_DECISIONS + 1}}
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    deployment = build_scenario(spec, root / "world")
    if deployment.status != "ready":
        raise ValueError(deployment.diagnostics)
    deployment.world = SoftwareCollaborationWorld(root / "world")
    world = deployment.world
    world.source_provider, world.test_budget = provider, TestBudget(root / "team-test-budget.json")
    with world.store.lock():
        world.state = world.store.load()
        artifact, version, _ = world._bundle(MEMBERS[0], baseline=True)
        reference = _reference(artifact, version)
        world.state["shares"].append({"project_id": PROJECT, **reference, "actor_ids": list(MEMBERS),
                                     "shared_by": "operator", "at": world.state["clock"]})
        world.state["software_events"] = []
        world.state["projects"][PROJECT]["software"] = {
            "case": case, "tasks": {}, "patches": {}, "deliveries": [], "test_reports": {},
            "initial_public_feedback": None, "transfer_offers": {}, "initial_diagnostics": {},
            "initial_diagnostic_assignments": {MEMBERS[0]: []},
            "registry": {MEMBERS[0]: {"member_id": MEMBERS[0], "birth_index": 1, "status": "live",
                                    "born_by": None, "origin": "initial_configuration", "briefing": "",
                                    "model_generated_briefing": False,
                                    "initial_source_reference": reference, "initial_patch_id": None,
                                    "replaces": None, "birth_sequence": 0, "private_history_copied": False}},
        }
        world.store.save(world.state)
    prefix = {"version": VERSION, "prepared_business_state_sha256": digest(json_bytes(initial_business_state(world))),
              "source_contract_sha256": digest(json_bytes(case["source_contract"])),
              "initial_binding_sha256": digest(json_bytes(case["initial_binding"])),
              "model_calls": 0, "test_executions": 0, "hidden_evaluation_calls": 0}
    prepared = PreparedOnlineCase(deployment, case, {
        "version": VERSION, "training_supported": False, "purpose": PURPOSE,
        "source_partition_sha256": provider.manifest_sha256,
        "runtime_process_contract": case["process_contract"]}, prefix)
    prepared.port_factory, prepared.source_provider = SoftwareCollaborationPort, provider
    atomic_write(root / "preparation.json", json_bytes(prefix))
    return prepared
