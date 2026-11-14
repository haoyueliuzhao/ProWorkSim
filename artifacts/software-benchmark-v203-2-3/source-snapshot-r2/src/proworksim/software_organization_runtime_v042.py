"""v042 collector: unchanged business/organization semantics with private exact report pages.

No external member is created and no interface diagnostic is added. All births
use the same v040 SDK worker factory. Existing numerical state/RNG guards and
sampling remain unchanged. Initial environment checks are exported separately
from model actions and from the member test budget.
"""
from __future__ import annotations

import copy
from pathlib import Path
import time

from . import software_organization_runtime_v041 as previous
from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_policy_v040 import POLICY as ACTION_ERROR_POLICY
from .harness_port import HarnessPort
from .online_collection import _config
from .software_organization_runtime_v038 import (
    SharedTeamBudget, _CollectionOwner, _registry, _StreamList, _StreamRecorder,
    _append, budget_snapshot, close_runtime,
)
from .software_organization_runtime_v039 import specialize_control_tools
from .software_organization_runtime_v040 import apply_process_contract, error_policy_summary
from .software_organization_v042 import PAGING_VERSION, SCHEDULER
from .software_runtime_v033 import SDK_CONTEXT_SELECTION
from .storage import atomic_write, json_bytes

VERSION = "software-organization-runtime-v0.42"
CONTEXT_VERSION = "software-context-v0.42"


class OrganizationRuntime(previous.OrganizationRuntime):
    def snapshot(self):
        value = super().snapshot()
        value.update(organization_runtime_version=VERSION,
            inherited_runtime_version=previous.VERSION, context_protocol=CONTEXT_VERSION, test_feedback_protocol=PAGING_VERSION, action_error_policy=error_policy_summary(self))
        return value


def run_fragment(prepared, runtime, *, on_opportunity=None):
    inherited = previous.run_fragment(prepared, runtime, on_opportunity=on_opportunity)
    boundary = {**inherited, "version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION, "scheduling_protocol": SCHEDULER,
        "inherited_runtime_provenance": {"version": inherited["version"],
            "external_intervention_enabled": False, "organization_mechanics": "Unchanged shared budget, fair scheduling, real events and permanent retirement"},
        "action_error_policy": error_policy_summary(runtime)}
    runtime.recorder.record("organization_run_boundary_v042", boundary)
    return boundary


def organization_evidence(prepared, runtime):
    value = previous.organization_evidence(prepared, runtime)
    facts = prepared.world._software()
    preparation_cost = copy.deepcopy(facts["environment_preparation_cost"])
    preparation_cost["cache_reuse"] = facts["environment_preparation_provenance"].get("cache_reuse", False)
    value.update(version=VERSION, inherited_evidence_version=previous.VERSION, context_protocol=CONTEXT_VERSION, test_feedback_protocol=PAGING_VERSION,
        test_reports=copy.deepcopy(facts["test_reports"]),
        information_condition=prepared.case["information_condition"], framing_condition=prepared.case["framing_condition"],
        initial_diagnostics={"assigned_ids_by_member": copy.deepcopy(facts["initial_diagnostic_assignments"]),
            "reports": copy.deepcopy(facts["initial_diagnostics"]),
            "preparation_provenance": copy.deepcopy(facts["environment_preparation_provenance"]),
            "origin": "environment_initial_diagnostic", "model_generated": False, "autonomous_discovery": False},
        environment_preparation_cost=preparation_cost, action_error_policy=error_policy_summary(runtime))
    return value


def build_runtime(owner, prepared, folder, *, worker_factory=None, require_exact_resident=True):
    """Build initial SDK sessions without sampling; spawn sessions are built later."""
    from .software_organization_v042 import PROJECT, SoftwareCollaborationPort, validate_case, member_instruction

    validate_case(prepared.case)
    if worker_factory is None:
        from .harness_policy_v040 import OrganizationHarnessWorker
        worker_factory = OrganizationHarnessWorker
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = _StreamRecorder(folder / "experience.jsonl")
    budget = SharedTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        require_exact_resident=require_exact_resident,
        **{key: prepared.case["team_limits"][key] for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    captured, interfaces, holder = {}, {}, {}

    def create_member(member, record):
        interface = SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member)
        interfaces[member] = interface
        rows = _StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        task = member_instruction(prepared.case, briefing=record.get("briefing", ""),
            born=member not in prepared.case["active_roles"], origin=record.get("origin"))
        config = _config(owner, member, task, {member: prepared.case["team_limits"]["max_decisions"]})
        config.update(context_policy="full_history", format_error_policy="format_feedback_budgeted_v033")
        port = HarnessPort(capture_port(interface, rows), member, project_id=PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(member, payload, association))
        worker = worker_factory(member, port.tools(), config, transport=owner.transport, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=SDK_CONTEXT_SELECTION)
        specialize_control_tools(worker)
        return port, worker

    ports, workers = {}, {}
    for member in prepared.case["active_roles"]:
        ports[member], workers[member] = create_member(member, _registry(prepared.world)[member])
    runtime = OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
                                  recorder=recorder, member_factory=create_member)
    holder["runtime"] = runtime
    runtime.owner = owner
    runtime.sync_members()
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    prepared.world.runtime_availability = runtime.availability
    if any(event["kind"] in {"model_call", "tool_call"} for event in recorder.events) or before != prepared.world.store.load():
        close_runtime(runtime)
        raise ValueError("SDK session construction cannot sample or change world state")
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in runtime.labels:
        recorder.record("organization_session_born", runtime.birth_records[member], worker_id=member)
    runtime.note_population("initial")
    return runtime, captured, interfaces


def collect_episode(owner, prepared, folder, *, sampling_seed, slot_id,
                    on_opportunity=None, worker_factory=None, transport_factory=None):
    """Collect one declared development episode with an immutable full-state guard.

    The caller loads the original complete common once.  Birth does not reseed
    the actor, refresh budgets or restore parameters.  Only the end guard restores
    CPU/CUDA RNG, while changed learning tensors cause failure rather than repair.
    """
    from .software_context_v042 import SoftwareContextTransport
    from .software_organization_v042 import assess_software_collaboration

    purpose = prepared.case["purpose"]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "slot-result.json").exists() or (folder / "episode").exists():
        raise ValueError("An already collected episode cannot be silently replayed")
    if type(sampling_seed) is not int or not 0 <= sampling_seed < 2**63 or not isinstance(slot_id, str) or not slot_id:
        raise ValueError("Each organization episode needs its frozen slot and integer sampling seed")
    before, identity = owner.capture_evaluation_state(), owner.freeze_identity()
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in
               ("recipe", "inference_profile", "base_identity", "software_learning_binding") if hasattr(owner, key)}
    runtime, captured, entries, result = None, {}, [], None
    episode_open, episode_closed = False, False
    started = time.time()
    owner.begin_window("organization-v042:" + slot_id)
    try:
        owner.reseed(sampling_seed, label=slot_id)
        transport = (transport_factory(owner, folder / "raw-transport") if transport_factory else
                     SoftwareContextTransport(owner, folder / "raw-transport"))
        facade = _CollectionOwner(owner, transport)
        runtime, captured, _ = build_runtime(facade, prepared, folder, worker_factory=worker_factory)
        runtime.slot_id = slot_id
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["organization_runtime"] = {
            "version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION, "purpose": purpose, "sampling_seed": sampling_seed,
            "slot_id": slot_id, "actor_identity": identity,
            "training_eligible": False, "admission_eligible": False,
            "sdk_context_selection": SDK_CONTEXT_SELECTION, "team_limits": prepared.case["team_limits"],
            "scheduling_protocol": SCHEDULER, "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
            "case": copy.deepcopy(prepared.case)}
        atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        begin_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(),
                      work_ids=[], scenario=scenario, policies=runtime.policy_identities)
        episode_open = True

        def checkpoint(outcome):
            _append(folder / "runtime-opportunities.jsonl", outcome)
            atomic_write(folder / "runtime-state.json", json_bytes({"slot_id": slot_id,
                "opportunities": runtime.opportunities, "actions": runtime.actions,
                "availability": runtime.availability(), "team_budget": budget_snapshot(runtime, prepared)}))
            if on_opportunity:
                on_opportunity(outcome)

        boundary = run_fragment(prepared, runtime, on_opportunity=checkpoint)
        finish_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(), termination=boundary)
        episode_closed = True
        assessment = assess_software_collaboration(prepared, run_root=folder / "private-assessment")
        atomic_write(folder / "raw-independent-assessment.json", json_bytes(assessment))
        assessment = apply_process_contract(assessment, boundary, runtime)
        atomic_write(folder / "assessment.json", json_bytes(assessment))
        evidence = organization_evidence(prepared, runtime)
        atomic_write(folder / "organization-evidence.json", json_bytes(evidence))
        result = {"version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION, "purpose": purpose, "slot_id": slot_id,
            "case_id": prepared.case["case_id"], "condition": prepared.case["condition"],
            "sampling_seed": sampling_seed, "first_member": prepared.case["first_member"],
            "status": "technical_unknown" if boundary["execution_integrity_failure"] or assessment.get("status") != "evaluable" else "closed",
            "R": assessment.get("R"), "submitted": assessment.get("submitted"),
            "complete_delivery": assessment.get("complete_delivery"), "assessment": assessment,
            "boundary": boundary, "member_lifecycle": evidence["member_lifecycle"],
            "information_condition": prepared.case["information_condition"],
            "framing_condition": prepared.case["framing_condition"],
            "initial_diagnostics": evidence["initial_diagnostics"],
            "environment_preparation_cost": evidence["environment_preparation_cost"],
            "action_error_policy": evidence["action_error_policy"],
            "process_violation": evidence["action_error_policy"]["process_violation"],
            "outcome_type": "business_delivery",
            "usage": evidence["total_usage"], "usage_by_member": evidence["usage_by_member"],
            "team_budget": evidence["team_budget"], "started_at": started, "ended_at": time.time(),
            "wall_seconds": time.time() - started,
            "training_eligible": False, "admission_eligible": False, "actor_identity": identity,
            "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0,
            "evaluation_guard": str((folder / "evaluation-guard.json").resolve()),
            "evidence_path": str((folder / "organization-evidence.json").resolve())}
        entries.append({"slot_id": slot_id, "active_members": list(runtime.labels),
                        "reward": {"value": assessment.get("R"), "eligible": False}})
    except BaseException as error:
        detail = {"type": type(error).__name__, "message": str(error), "slot_id": slot_id,
                  "episode_closed_before_error": episode_closed}
        atomic_write(folder / "interruption.json", json_bytes(detail))
        if episode_open and not episode_closed:
            finish_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(),
                           termination={"status": "interrupted", "kind": "collector_or_external_failure",
                                        "error": detail, "business_result": None, "continuation": False})
        raise
    finally:
        try:
            if runtime is not None:
                close_runtime(runtime)
                atomic_write(folder / "team-budget.json", json_bytes(budget_snapshot(runtime, prepared)))
                atomic_write(folder / "public-capture.json", json_bytes(captured))
                atomic_write(folder / "runtime.json", json_bytes(runtime.snapshot()))
                if not (folder / "organization-evidence.json").exists():
                    atomic_write(folder / "organization-evidence.json", json_bytes(organization_evidence(prepared, runtime)))
        finally:
            try:
                if owner.phase == "collecting" and not owner.busy:
                    owner.finish_evaluation(entries, folder / "frozen-collection-close")
            finally:
                guard = owner.finish_evaluation_guard(before)
                guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in binding.items()),
                             actor_identity_unchanged=owner.freeze_identity() == identity)
                atomic_write(folder / "evaluation-guard.json", json_bytes(guard))
                if not all(guard[key] for key in ("learning_unchanged", "rng_restored_exactly",
                                                "software_binding_unchanged", "actor_identity_unchanged")):
                    raise ValueError("Frozen organization collection changed protected learner state or RNG restoration failed")
    atomic_write(folder / "slot-result.json", json_bytes(result))
    return result
