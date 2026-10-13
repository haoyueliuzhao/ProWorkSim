"""Frozen-episode strict O1 collection for the bounded v050 learning window.

The caller owns the learning-window boundary and loads S_star4/4 or a new branch state.
This module never restores a checkpoint and never updates parameters. Current
work may end without retiring either stable member or discarding its SDK state.
"""
from __future__ import annotations

import copy
from pathlib import Path
import time

from . import software_organization_runtime_v045 as previous
from .software_organization_runtime_v049 import worker_type
from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_policy_v040 import POLICY as ACTION_ERROR_POLICY
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .online_collection import _config
from .software_context_v048 import SoftwareContextTransport, VERSION as CONTEXT_VERSION, CANDIDATE_SHA256
from .software_organization_runtime_v038 import (
    SharedTeamBudget, _CollectionOwner, _StreamList, _StreamRecorder, _append,
    _last_sequence, _registry, budget_snapshot, close_runtime,
)
from .software_organization_runtime_v040 import apply_process_contract, error_policy_summary
from .software_organization_runtime_v047 import (
    AdministrativeSoftDeadline, DispatchDeadline, context_transport,
    outcome_metrics, SOFT_SECONDS, HARD_SECONDS,
)
from .software_organization_v050 import PAGING_VERSION, SCHEDULER
from .software_runtime_v033 import (
    SDK_CONTEXT_SELECTION, TECHNICAL_FAILURES, TERMINAL, _decisions,
    _terminal_detail, _capture_slot_guard,
)
from .stage_budget_v047 import StageTeamBudget
from .storage import atomic_write, digest, json_bytes

VERSION = "software-organization-runtime-v0.50"
COMMON_FEATURE_COORDINATE_BINDING = {"member_a": "member_001", "member_b": "member_002",
                                     "software_inactive": "software_inactive"}
WAIT_DESCRIPTION = (
    "Suspend current work without creating an event or advancing work. Only a later actual visible partner "
    "message or committed public work event can wake this same session; all meters remain unchanged.")
DONE_DESCRIPTION = (
    "End your current work and put this same stable member to sleep. This is not permanent retirement, "
    "submission, approval or success. Only a later actual visible partner message or committed public work "
    "event can wake the same session; history, responsibilities and all meters remain unchanged.")


class O1TeamBudget(SharedTeamBudget):
    """One unpartitioned original ledger, with tested pre-dispatch receipts only."""
    mark_dispatched = StageTeamBudget.mark_dispatched
    cancel_before_dispatch = StageTeamBudget.cancel_before_dispatch

    def register_member(self, member):
        raise ValueError("The strict O1 episode has exactly its original two stable members")



def specialize_control_tools(worker):
    """Bind O1 control text only on the two new SDK instances."""
    descriptions = {"staff_wait": WAIT_DESCRIPTION, "staff_done": DONE_DESCRIPTION}
    for definition in getattr(worker, "definitions", []):
        if definition["name"] in descriptions:
            definition["description"] = descriptions[definition["name"]]
    agent = getattr(worker, "agent", None)
    if agent is not None:
        from openhands.sdk.tool import register_tool, resolve_tool
        for specification in agent.tools:
            for tool in resolve_tool(specification, worker.conversation.state):
                if tool.name in descriptions:
                    register_tool(specification.name, tool.model_copy(update={"description": descriptions[tool.name]}))


class OrganizationRuntime(previous.OrganizationRuntime):
    def __init__(self, *args, deadline=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.deadline = deadline or DispatchDeadline()
        self.work_ended = {}
        self.work_boundaries = []

    def sync_members(self):
        registry = _registry(self.prepared.world)
        if (list(registry) != self.initial_members or list(self.labels) != self.initial_members
                or any(record["status"] != "live" for record in registry.values())):
            raise ValueError("Strict O1 cannot create, remove or retire its stable identities")

    def _step(self):
        member = self.labels[self.cursor % len(self.labels)]
        ordinal = self.opportunities + 1
        opportunity = f"staff-opportunity-{self.run_id}-{ordinal}"
        outcome = None

        def record(phase):
            value = {"version": VERSION, "member_id": member, "opportunity_ordinal": ordinal,
                "opportunity_id": opportunity, "phase": phase, "team_budget": self.team_budget.snapshot(),
                "world_event_sequence": _last_sequence(self.prepared.world), "availability": self.availability(),
                "model_visible": False, "source": "Host snapshot around one original scheduled SDK opportunity"}
            if phase == "after":
                value["outcome_status"] = outcome.get("status") if isinstance(outcome, dict) else "raised_exception"
            self.recorder.record("organization_work_opportunity_v049", value, worker_id=member)

        record("before")
        try:
            try:
                outcome = SDKStaffRuntime._step(self)
            except AdministrativeSoftDeadline as error:
                self.roles[member]["status"] = "administrative_soft_deadline"
                outcome = {"worker_id": member, "status": "administrative_soft_deadline", "reason": str(error),
                           "action_performed": False, "actual_generation_started": False}
            return outcome
        finally:
            record("after")

    def execute(self, label, name, arguments, association):
        self.deadline.check_hard("settle_returned_legal_action")
        return super().execute(label, name, arguments, association)

    def availability(self):
        value = super().availability()
        for member, row in value.items():
            row.update(stable_member=True, current_work_ended=member in self.work_ended,
                       permanent_retirement=False)
        return value

    def snapshot(self):
        value = super().snapshot()
        value.update(organization_runtime_version=VERSION, current_work_ended=copy.deepcopy(self.work_ended),
            work_boundaries=copy.deepcopy(self.work_boundaries),
            deadline_receipt=self.deadline.snapshot(self.team_budget))
        return value


def _sleep(runtime, member, status, result):
    sequence = _last_sequence(runtime.prepared.world)
    runtime.waiting[member] = sequence
    if status == "completed":
        runtime.work_ended[member] = {"after_world_event_sequence": sequence, "reason": result.get("reason", "")}
        runtime.roles[member]["status"] = "current_work_ended"
    row = {"member_id": member, "cause": "current_work_ended" if status == "completed" else status,
        "after_world_event_sequence": sequence, "opportunity_ordinal": runtime.opportunities,
        "permanent_retirement": False, "same_session_retained": True, "budget_reset": False,
        "world_event_created": False, "decisions_already_consumed": _decisions(runtime, member)}
    runtime.work_boundaries.append(row)
    runtime.recorder.record("organization_work_boundary_v049", row, worker_id=member)
    runtime.recorder.record("role_suspended", {"after_event_sequence": sequence,
        "decisions_already_consumed": _decisions(runtime, member), "reason": row["cause"]}, worker_id=member)


def _wake_reachable(runtime):
    world = runtime.prepared.world
    world.state = world.store.load()
    for member in list(runtime.waiting):
        if member in runtime.stopped:
            continue
        events = world.reachable_events(member, runtime.waiting[member])
        if not events:
            continue
        sequences = [event["sequence"] for event in events]
        if member in runtime.work_ended:
            worker = runtime.policies[member]
            if hasattr(worker, "wake_current_work"):
                worker.wake_current_work(sequences)
            elif getattr(worker, "_done", None):
                raise ValueError("The real SDK needs its strict O1 wake hook")
            del runtime.work_ended[member]
        del runtime.waiting[member]
        runtime.roles[member].update(status="ready", reason="Later actual visible partner work event")
        runtime.recorder.record("role_reactivated", {"event_sequences": sequences,
            "decisions_already_consumed": _decisions(runtime, member), "budget_reset": False,
            "same_member_and_session": True}, worker_id=member)


def run_fragment(prepared, runtime, *, on_opportunity=None):
    outcomes, integrity_failure, closure_reason = [], None, None
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    deadline = runtime.deadline
    while True:
        deadline.check_hard("schedule")
        runtime.sync_members()
        snapshot = runtime.team_budget.snapshot()
        if snapshot.get("integrity_failure"):
            integrity_failure, closure_reason = snapshot["integrity_failure"], "execution_integrity_failure"
            break
        if any(snapshot[key] <= 0 for key in ("remaining_decisions", "remaining_attempts", "available_tokens")):
            closure_reason = "shared_team_pool_exhausted"
            break
        _wake_reachable(runtime)
        runnable = set(runtime.labels) - set(runtime.stopped) - set(runtime.waiting)
        if not runnable:
            closure_reason = "all_members_stopped_or_no_reachable_event"
            break
        if not deadline.admit_new_work("before_member_opportunity"):
            closure_reason = "administrative_soft_deadline"
            break
        runtime.cursor %= len(runtime.labels)
        member = runtime.labels[runtime.cursor]
        if member not in runnable:
            runtime.cursor += 1
            continue
        first_event = len(runtime.recorder.events)
        result = runtime.step()
        status = result["status"]
        rejection = (result.get("response") or {}).get("error", {}).get("rejection", {}).get("code")
        if rejection in {"world_power_denied", "project_power_denied", "trusted_context_override"}:
            result = {**result, "original_status": status, "status": "model_permission_error",
                      "reason": "Trusted WorldCore permission/context boundary: " + rejection}
            status = result["status"]
            runtime.roles[member]["status"] = status
            runtime.recorder.record("critical_permission_boundary", {"code": rejection,
                "original_status": result["original_status"], "status": status}, worker_id=member)
        outcomes.append(result)
        runtime.sync_members()
        fatal = status in TECHNICAL_FAILURES and not (status == "policy_error" and result.get("action_performed"))
        if status == "administrative_soft_deadline":
            closure_reason = status
        elif status == "completed":
            _sleep(runtime, member, status, result)
        elif fatal or status in TERMINAL - {"completed", "policy_error", "model_format_error"}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.waiting.pop(member, None)
            runtime.work_ended.pop(member, None)
            if fatal:
                integrity_failure = {"member": member, "status": status, "reason": result.get("reason")}
                closure_reason = "execution_integrity_failure"
        elif status in {"worker_waiting", "world_blocked"}:
            _sleep(runtime, member, status, result)
        runtime.note_population("completed_member_opportunity")
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None or status == "administrative_soft_deadline":
            break
    runtime.note_population("episode_closed")
    boundary = {"version": VERSION, "status": "execution_integrity_blocked" if integrity_failure else "bounded_work_closed",
        "kind": "stable_o1_terminal", "scheduling_protocol": SCHEDULER,
        "first_member": prepared.case["first_member"], "role_stops": copy.deepcopy(runtime.stopped),
        "waiting_members": copy.deepcopy(runtime.waiting), "current_work_ended": copy.deepcopy(runtime.work_ended),
        "work_boundaries": copy.deepcopy(runtime.work_boundaries), "outcomes": outcomes,
        "terminal_details": copy.deepcopy(runtime.terminal_details), "closure_reason": closure_reason,
        "execution_integrity_failure": integrity_failure, "opportunities": runtime.opportunities,
        "actions": runtime.actions, "team_budget": budget_snapshot(runtime, prepared),
        "initial_members": runtime.initial_members, "born_members": list(runtime.labels),
        "administrative_censoring": deadline.prevented_work, "deadline_receipt": deadline.snapshot(runtime.team_budget),
        "continuation": False, "training_eligible": prepared.case["training_eligible"], "admission_eligible": False,
        "action_error_policy": error_policy_summary(runtime),
        "scope": "Stable identities; done ends current work only. No generated wake event, member replacement, budget reset or automatic task assignment."}
    runtime.recorder.record("run_boundary", boundary)
    runtime.recorder.record("organization_run_boundary_v049", boundary)
    return boundary


def build_runtime(owner, prepared, folder, *, deadline=None, worker_factory=None,
                  require_exact_resident=True):
    from .software_organization_v050 import PROJECT, SoftwareCollaborationPort, member_instruction, validate_case

    validate_case(prepared.case)
    worker_factory = worker_factory or worker_type()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = _StreamRecorder(folder / "experience.jsonl")
    deadline = deadline or DispatchDeadline()
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = O1TeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
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
        # Personal fixed500k and the shared episode500k both retain exact accounting.
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
        recorder=recorder, member_factory=create_member, deadline=deadline)
    holder["runtime"] = runtime
    runtime.owner = owner
    gate = getattr(owner.transport, "native_dispatch_gate", None)
    if gate is not None:
        gate.runtime = runtime
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


def organization_evidence(prepared, runtime):
    value = previous.organization_evidence(prepared, runtime)
    value.update(version=VERSION, purpose=prepared.case["purpose"],
        training_eligible=prepared.case["training_eligible"], scheduling_protocol=SCHEDULER,
        work_boundaries=copy.deepcopy(runtime.work_boundaries),
        deadline_receipt=runtime.deadline.snapshot(runtime.team_budget),
        work_opportunity_snapshots=[copy.deepcopy(event) for event in runtime.recorder.events
            if event["kind"] == "organization_work_opportunity_v049"])
    value["member_lifecycle"].update(stable_member_ids=list(runtime.initial_members),
        permanent_retirement_enabled=False, current_work_ended=copy.deepcopy(runtime.work_ended))
    return value


def collect_episode(owner, prepared, folder, *, sampling_seed, slot_id, on_opportunity=None,
                    worker_factory=None, transport_factory=None, clock=time.monotonic,
                    soft_seconds=SOFT_SECONDS, hard_seconds=HARD_SECONDS,
                    manage_owner_window=True, learning_binding=None):
    from .software_organization_v050 import assess_software_collaboration

    deadline = DispatchDeadline(clock=clock, soft_seconds=soft_seconds, hard_seconds=hard_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "slot-result.json").exists() or (folder / "episode").exists():
        raise ValueError("An already collected episode cannot be silently replayed")
    if type(sampling_seed) is not int or not 0 <= sampling_seed < 2**63 or not isinstance(slot_id, str) or not slot_id:
        raise ValueError("Each stable O1 episode needs its frozen slot and integer sampling seed")
    from .software_organization_v050 import validate_case
    validate_case(prepared.case)
    if type(manage_owner_window) is not bool or (not manage_owner_window and owner.phase != "collecting"):
        raise ValueError("Externally managed collection requires its already-open logical window")
    if prepared.case["training_eligible"] and manage_owner_window:
        raise ValueError("Training episodes must share the predeclared externally managed logical window")
    if prepared.case["training_eligible"] and owner.window_id != prepared.case["training_window_id"]:
        raise ValueError("Training native responses must bind the frozen shared logical window")
    before = owner.capture_evaluation_state() if manage_owner_window else _capture_slot_guard(owner)
    identity = owner.freeze_identity()
    episode_steps = {key: getattr(owner, key, None) for key in ("actor_steps", "critic_steps", "policy_revision")}
    learning_binding = copy.deepcopy(learning_binding or {})
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in
               ("recipe", "inference_profile", "base_identity", "software_learning_binding") if hasattr(owner, key)}
    runtime, captured, entries, result = None, {}, [], None
    episode_open, episode_closed = False, False
    started = time.time()
    if manage_owner_window:
        owner.begin_window("organization-v050:" + slot_id)
    try:
        owner.reseed(sampling_seed, label=slot_id)
        context = context_transport(owner, folder / "raw-transport", deadline, transport_factory=transport_factory or SoftwareContextTransport)
        facade = _CollectionOwner(owner, context)
        runtime, captured, _ = build_runtime(facade, prepared, folder, deadline=deadline, worker_factory=worker_factory)
        runtime.slot_id = slot_id
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["organization_runtime"] = {
            "version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION,
            "purpose": prepared.case["purpose"], "sampling_seed": sampling_seed, "slot_id": slot_id,
            "actor_identity": identity, "training_eligible": prepared.case["training_eligible"], "admission_eligible": False,
            "sdk_context_selection": SDK_CONTEXT_SELECTION, "team_limits": prepared.case["team_limits"],
            "scheduling_protocol": SCHEDULER, "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
            "case": copy.deepcopy(prepared.case), "online_window_id": owner.window_id,
            "learning_binding": learning_binding, "episode_start_steps": episode_steps,
            "recipe": copy.deepcopy(owner.recipe), "recipe_sha256": digest(json_bytes(owner.recipe)),
            "common_feature_coordinate_binding": copy.deepcopy(COMMON_FEATURE_COORDINATE_BINDING),
            "representation": {"name": "Gamma1", "candidate_sha256": CANDIDATE_SHA256},
            "time_policy": {"soft_seconds": soft_seconds, "hard_seconds": hard_seconds}}
        scenario["variation"]["software_case"] = copy.deepcopy(prepared.case)
        atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        begin_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(),
                      work_ids=[], scenario=scenario, policies=runtime.policy_identities)
        episode_open = True

        def checkpoint(outcome):
            _append(folder / "runtime-opportunities.jsonl", outcome)
            atomic_write(folder / "runtime-state.json", json_bytes({"slot_id": slot_id,
                "opportunities": runtime.opportunities, "actions": runtime.actions,
                "availability": runtime.availability(), "team_budget": budget_snapshot(runtime, prepared),
                "deadline_receipt": deadline.snapshot(runtime.team_budget)}))
            if on_opportunity:
                on_opportunity(outcome)

        boundary = run_fragment(prepared, runtime, on_opportunity=checkpoint)
        deliveries = prepared.world._software()["deliveries"]
        deadline.lock_submission(deliveries[-1] if deliveries else None)
        atomic_write(folder / "final-candidate-lock.json", json_bytes({"version": VERSION,
            "slot_id": slot_id, "delivery": deadline.final_submission, "absence_locked": not deliveries,
            "new_model_calls_allowed": False, "new_stages_allowed": False}))
        finish_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(), termination=boundary)
        episode_closed = True
        deadline.begin_assessment()
        assessment = assess_software_collaboration(prepared, run_root=folder / "private-assessment")
        deadline.check_hard("after_final_assessment")
        if assessment.get("delivery") != deadline.final_submission:
            raise ValueError("Final assessment differs from the one locked last submission")
        atomic_write(folder / "raw-independent-assessment.json", json_bytes(assessment))
        assessment = apply_process_contract(assessment, boundary, runtime)
        atomic_write(folder / "assessment.json", json_bytes(assessment))
        evidence = organization_evidence(prepared, runtime)
        atomic_write(folder / "organization-evidence.json", json_bytes(evidence))
        metrics = outcome_metrics(assessment, administratively_censored=deadline.prevented_work)
        result = {"version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION,
            "purpose": prepared.case["purpose"], "slot_id": slot_id, "case_id": prepared.case["case_id"],
            "condition": prepared.case["condition"], "team_token_budget": prepared.case["team_limits"]["max_total_tokens"],
            "sampling_seed": sampling_seed, "first_member": prepared.case["first_member"],
            "status": "closed" if metrics["R_joint"] is not None else "technical_unknown",
            **metrics, "R": metrics["R_joint"], "R_alias_scope": "R_joint only; use R_token for the administratively uncensored token estimand",
            "submitted": assessment.get("submitted"), "complete_delivery": assessment.get("complete_delivery"),
            "assessment": assessment, "boundary": boundary, "member_lifecycle": evidence["member_lifecycle"],
            "information_condition": prepared.case["information_condition"], "framing_condition": prepared.case["framing_condition"],
            "initial_diagnostics": evidence["initial_diagnostics"], "environment_preparation_cost": evidence["environment_preparation_cost"],
            "current_work_ended": copy.deepcopy(runtime.work_ended),
            "action_error_policy": evidence["action_error_policy"], "process_violation": evidence["action_error_policy"]["process_violation"],
            "outcome_type": "business_delivery_under_joint_policy", "usage": evidence["total_usage"],
            "usage_by_member": evidence["usage_by_member"], "team_budget": evidence["team_budget"],
            "started_at": started, "ended_at": time.time(), "wall_seconds": time.time() - started,
            "training_eligible": prepared.case["training_eligible"], "admission_eligible": False, "actor_identity": identity,
            "actor_updates": 0, "critic_updates": 0, "new_backward_calls": 0,
            "evaluation_guard": str((folder / "evaluation-guard.json").resolve()),
            "evidence_path": str((folder / "organization-evidence.json").resolve())}
        entries.append({"slot_id": slot_id, "active_members": list(runtime.labels),
                        "reward": {"value": metrics["R_joint"], "eligible": False}})
    except BaseException as error:
        detail = {"type": type(error).__name__, "message": str(error), "slot_id": slot_id,
                  "episode_closed_before_error": episode_closed, "deadline_receipt": deadline.snapshot(runtime.team_budget if runtime else None)}
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
            if not deadline.hard_expired:
                try:
                    deadline.check_hard("evaluation_close")
                    if manage_owner_window and owner.phase == "collecting" and not owner.busy:
                        owner.finish_evaluation(entries, folder / "frozen-collection-close")
                finally:
                    if not deadline.hard_expired:
                        guard = owner.finish_evaluation_guard(before)
                        deadline.check_hard("evaluation_guard")
                        guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in binding.items()),
                            actor_identity_unchanged=owner.freeze_identity() == identity)
                        atomic_write(folder / "evaluation-guard.json", json_bytes(guard))
                        if not all(guard[key] for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
                            raise ValueError("Frozen O1 episode changed its loaded learner state or RNG restoration failed")
            atomic_write(folder / "deadline-receipt.json", json_bytes(deadline.snapshot(runtime.team_budget if runtime else None)))
    deadline.mark_closed()
    receipt = deadline.snapshot(runtime.team_budget)
    result.update(online_window_id=owner.window_id, learning_binding=learning_binding,
        episode_start_steps=episode_steps,
        common_feature_coordinate_binding=copy.deepcopy(COMMON_FEATURE_COORDINATE_BINDING),
        representation="Gamma1", representation_candidate_sha256=CANDIDATE_SHA256,
        episode_manifest=str((folder / "episode/manifest.json").resolve()),
        public_capture=str((folder / "public-capture.json").resolve()),
        assessment_path=str((folder / "assessment.json").resolve()),
        raw_transport_path=str((folder / "raw-transport").resolve()))
    result["deadline_receipt"] = receipt
    result["boundary"]["deadline_receipt"] = receipt
    result.update(ended_at=time.time(), wall_seconds=time.time() - started)
    evidence["deadline_receipt"] = receipt
    atomic_write(folder / "deadline-receipt.json", json_bytes(receipt))
    atomic_write(folder / "organization-evidence.json", json_bytes(evidence))
    atomic_write(folder / "slot-result.json", json_bytes(result))
    return result
