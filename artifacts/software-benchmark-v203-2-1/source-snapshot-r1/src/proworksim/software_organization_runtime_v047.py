"""Frozen v047 architecture runtime with phased quotas and administrative close.

The original native sampler, v044 context projection and feedback lifecycle are
unchanged. Only the host scheduler, stage allowances and true dispatch boundary
are new. A soft deadline cannot manufacture a final-stage model call.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from functools import cache
import math
from pathlib import Path
import time

from . import software_organization_runtime_v045 as previous
from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_policy_v040 import POLICY as ACTION_ERROR_POLICY
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .online_collection import _config
from .software_context_v044 import SoftwareContextTransport
from .software_organization_runtime_v038 import (
    _CollectionOwner, _StreamList, _StreamRecorder, _append, _last_sequence,
    _registry, budget_snapshot, close_runtime,
)
from .software_organization_runtime_v039 import specialize_control_tools
from .software_organization_runtime_v040 import apply_process_contract, error_policy_summary
from .software_runtime_v033 import SDK_CONTEXT_SELECTION, TECHNICAL_FAILURES, TERMINAL, _decisions, _terminal_detail
from .stage_budget_v047 import StageTeamBudget
from .storage import atomic_write, json_bytes

VERSION = "software-organization-runtime-v0.47"
CONTEXT_VERSION = "software-context-v0.44"
PAGING_VERSION = "paged-public-test-feedback-v0.42"
SCHEDULER = "architecture-stages-shared-pool-soft5400-hard6000-v0.47"
SOFT_SECONDS, HARD_SECONDS = 5400, 6000


class AdministrativeSoftDeadline(BaseException):
    """A proven pre-dispatch host boundary; never an unknown attempted call."""


class HardDeadlineReached(BaseException):
    """Administrative hard expiration does not establish a formal outcome."""


class DispatchDeadline:
    def __init__(self, *, clock=time.monotonic, soft_seconds=SOFT_SECONDS,
                 hard_seconds=HARD_SECONDS, sink=None):
        if not (0 < soft_seconds < hard_seconds and math.isfinite(hard_seconds)):
            raise ValueError("Require a positive soft boundary followed by a finite hard boundary")
        self.clock, self.started = clock, clock()
        self.soft_seconds, self.hard_seconds = soft_seconds, hard_seconds
        self.soft_at, self.hard_at = self.started + soft_seconds, self.started + hard_seconds
        self.sink, self.events, self.dispatches, self.cancelled = sink, [], {}, []
        self.soft_triggered, self.prevented_work, self.hard_expired = False, False, False
        self.stage_transitions = []
        self.final_submission = None
        self.final_submission_locked = False
        self.final_assessment_calls = 0
        self.closed_at = None
        self.last_clock = self.started

    def now(self):
        value = self.clock()
        if not math.isfinite(value) or value < self.last_clock:
            raise ValueError("Deadline clock must be finite and monotone")
        self.last_clock = value
        return value

    def record(self, kind, **details):
        value = {"kind": kind, "monotonic_at": self.last_clock,
                 "elapsed_seconds": self.last_clock - self.started, **details}
        self.events.append(copy.deepcopy(value))
        if self.sink is not None:
            self.sink("organization_deadline_v047", value)
        return value

    def check_hard(self, phase):
        now = self.now()
        if now >= self.hard_at:
            self.hard_expired = True
            self.record("hard_expired", phase=phase, result_known=False)
            raise HardDeadlineReached("v047 hard episode deadline reached during " + phase)
        return now

    def admit_new_work(self, phase):
        now = self.check_hard(phase)
        if now >= self.soft_at:
            self.soft_triggered = self.prevented_work = True
            self.record("soft_cutoff_triggered", phase=phase, remaining_work_prevented=True,
                        new_model_calls_allowed=False, new_stages_allowed=False)
            return False
        return True

    def require_dispatch(self, member, call_id):
        if not self.admit_new_work("before_native_dispatch"):
            raise AdministrativeSoftDeadline("No new native transport dispatch after the v047 soft deadline")
        if call_id in self.dispatches:
            raise ValueError("One decision cannot dispatch twice")
        self.dispatches[call_id] = {"member_id": member, "dispatched_at": self.last_clock,
                                    "status": "in_flight", "returned_at": None}
        event = {"stage": "started", "member_id": member, "call_id": call_id,
                 "monotonic_at": self.last_clock, "before_soft_deadline": True}
        if self.sink is not None:
            self.sink("organization_model_dispatch_v047", event)

    def cancel(self, member, call_id, budget, *, reason="soft_deadline_before_dispatch"):
        state = budget.cancel_before_dispatch(member, call_id, reason=reason)
        event = {"stage": "cancelled_before_dispatch", "member_id": member, "call_id": call_id,
                 "monotonic_at": self.last_clock, "actual_generation_started": False,
                 "attempt_started": False, "charged_tokens": 0, "decision_retained": True,
                 "reason": reason, "team_budget": state}
        self.cancelled.append(copy.deepcopy(event))
        if self.sink is not None:
            self.sink("organization_model_dispatch_v047", event)
        return event

    def returned(self, call_id, *, completed):
        now = self.now()
        self.dispatches[call_id].update(status="returned" if completed else "raised_exception", returned_at=now)
        if self.sink is not None:
            self.sink("organization_model_dispatch_v047", {"stage": "returned" if completed else "failed",
                "call_id": call_id, "monotonic_at": now, "dispatched_before_soft": True})

    def stage_changed(self, before, after):
        now = self.check_hard("stage_transition")
        if now >= self.soft_at:
            raise ValueError("A stage cannot start during the administrative close window")
        row = {"before": copy.deepcopy(before), "after": copy.deepcopy(after), "monotonic_at": now}
        self.stage_transitions.append(row)
        if self.sink is not None:
            self.sink("organization_stage_transition_v047", row)

    def lock_submission(self, delivery):
        self.check_hard("lock_final_submission")
        if self.final_submission_locked:
            raise ValueError("The final submitted candidate can be locked only once")
        self.final_submission = copy.deepcopy(delivery)
        self.final_submission_locked = True
        self.record("final_submission_locked", delivery=copy.deepcopy(delivery), absence_locked=delivery is None)

    def begin_assessment(self):
        self.check_hard("final_assessment")
        if not self.final_submission_locked or self.final_assessment_calls:
            raise ValueError("Only one assessment of the locked last candidate is allowed")
        self.final_assessment_calls = 1
        self.record("final_assessment_started", submitted=self.final_submission is not None)

    def mark_closed(self):
        self.closed_at = self.check_hard("final_guard_complete")
        self.record("closed", new_model_calls_allowed=False)

    def snapshot(self, budget=None):
        records = budget.snapshot()["records"] if budget is not None else {}
        settled = bool(budget is not None) and all(
            records.get(cid, {}).get("status") == "settled" for cid in self.dispatches)
        return {"version": "administrative-deadline-v0.47", "soft_seconds": self.soft_seconds,
            "hard_seconds": self.hard_seconds, "started_monotonic": self.started,
            "soft_deadline_monotonic": self.soft_at, "hard_deadline_monotonic": self.hard_at,
            "actual_soft_cutoff_triggered": self.soft_triggered,
            "cutoff_prevented_remaining_work": self.prevented_work,
            "no_new_dispatch_after_cutoff": all(row["dispatched_at"] < self.soft_at for row in self.dispatches.values()),
            "all_dispatched_attempts_settled": settled,
            "no_new_stage_after_cutoff": all(row["monotonic_at"] < self.soft_at for row in self.stage_transitions),
            "final_submission_locked": self.final_submission_locked,
            "unique_final_acceptance": self.final_submission_locked and self.final_assessment_calls == 1,
            "final_assessment_calls": self.final_assessment_calls,
            "locked_submission": copy.deepcopy(self.final_submission),
            "closed_before_hard_deadline": self.closed_at is not None and self.closed_at < self.hard_at and not self.hard_expired,
            "hard_deadline_expired": self.hard_expired, "closed_monotonic": self.closed_at,
            "dispatches": copy.deepcopy(self.dispatches), "cancelled_before_dispatch": copy.deepcopy(self.cancelled),
            "stage_transitions": copy.deepcopy(self.stage_transitions), "events": copy.deepcopy(self.events),
            "scope": "Administrative time policy. Only requests committed to actual transport before soft cutoff may finish; no model call or later architecture stage is added during close."}


class NativeDispatchGate:
    """Host-only boundary immediately around the original owner.transport call."""
    def __init__(self, transport, deadline):
        self.transport, self.deadline = transport, deadline
        self.context, self.runtime = None, None

    def complete(self, request, **kwargs):
        turn = self.context._turn if self.context is not None else None
        if not turn or self.runtime is None:
            raise ValueError("Native dispatch requires a bound runtime/member/call")
        member, call_id = turn["member_id"], turn["association"]["call_id"]
        budget, worker = self.runtime.team_budget, self.runtime.policies[member]
        try:
            self.deadline.require_dispatch(member, call_id)
        except (AdministrativeSoftDeadline, HardDeadlineReached) as error:
            self.deadline.cancel(member, call_id, budget, reason="hard_deadline_before_dispatch"
                if isinstance(error, HardDeadlineReached) else "soft_deadline_before_dispatch")
            worker.cancel_pending_dispatch(call_id)
            raise
        budget.mark_dispatched(member, call_id)
        worker.confirm_native_dispatch(call_id)
        completed = False
        try:
            response = self.transport.complete(request, **kwargs)
            completed = True
            return response
        finally:
            self.deadline.returned(call_id, completed=completed)


def context_transport(owner, directory, deadline, *, transport_factory=None):
    gate = NativeDispatchGate(owner.transport, deadline)
    facade = _CollectionOwner(owner, gate)
    context = (transport_factory(facade, directory) if transport_factory else
               SoftwareContextTransport(facade, directory))
    gate.context = context
    context.native_dispatch_gate = gate
    return context


@cache
def worker_type():
    from .software_feedback_v044 import worker_type as previous_worker_type

    class DeadlineOrganizationWorker(previous_worker_type()):
        def _emit(self, kind, payload):
            if kind == "model_attempt" and payload.get("stage") == "started":
                if getattr(self, "_pending_dispatch", None) is not None:
                    raise ValueError("Only one native dispatch can await admission")
                self.meter["http_attempts"] -= 1
                self._pending_dispatch = copy.deepcopy(payload)
                super()._emit("model_dispatch_prepared_v047", {**payload,
                    "stage": "prepared_not_dispatched", "actual_generation_started": False})
                deadline = self.transport.native_dispatch_gate.deadline
                try:
                    allowed = deadline.admit_new_work("before_team_begin_attempt")
                except HardDeadlineReached:
                    deadline.cancel(self.role_id, payload["call_id"], self.team_budget,
                                    reason="hard_deadline_before_dispatch")
                    self.cancel_pending_dispatch(payload["call_id"])
                    raise
                if not allowed:
                    deadline.cancel(self.role_id, payload["call_id"], self.team_budget)
                    self.cancel_pending_dispatch(payload["call_id"])
                    raise AdministrativeSoftDeadline("Soft deadline reached before the actual attempt")
                return
            super()._emit(kind, payload)

        def confirm_native_dispatch(self, call_id):
            pending = getattr(self, "_pending_dispatch", None)
            if pending is None or pending["call_id"] != call_id:
                raise ValueError("Native dispatch lacks its exact SDK preparation")
            self._pending_dispatch = None
            self.meter["http_attempts"] += 1
            super()._emit("model_attempt", {**pending, "stage": "started",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "dispatch_boundary": "v047_exact_native_transport_entry", "actual_generation_started": True})

        def cancel_pending_dispatch(self, call_id):
            pending = getattr(self, "_pending_dispatch", None)
            if pending is None or pending["call_id"] != call_id:
                raise ValueError("Pre-dispatch cancellation lacks its original SDK request")
            self._pending_dispatch = None

    return DeadlineOrganizationWorker


class OrganizationRuntime(previous.OrganizationRuntime):
    def __init__(self, *args, deadline=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.deadline = deadline or DispatchDeadline()
        self.stage_boundaries = []

    def _step(self):
        member = self.labels[self.cursor % len(self.labels)]
        ordinal = self.opportunities + 1
        opportunity = f"staff-opportunity-{self.run_id}-{ordinal}"
        outcome = None

        def record(phase):
            value = {"version": VERSION, "member_id": member, "opportunity_ordinal": ordinal,
                "opportunity_id": opportunity, "phase": phase, "team_budget": self.team_budget.snapshot(),
                "stage_budget": self.team_budget.stage_snapshot(member),
                "architecture": self.prepared.world.stage_state(),
                "world_event_sequence": _last_sequence(self.prepared.world), "availability": self.availability(),
                "model_visible": False, "source": "Host snapshot around one original scheduled SDK opportunity"}
            if phase == "after":
                value["outcome_status"] = outcome.get("status") if isinstance(outcome, dict) else "raised_exception"
            self.recorder.record("organization_work_opportunity_v047", value, worker_id=member)

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
        active = set(self.prepared.world.runnable_members())
        for member, row in value.items():
            row.update(architecture_stage=self.prepared.world.stage_state()["stage_id"],
                stage_eligible=member in active,
                can_receive_work=row["can_receive_work"] and member in active)
        return value

    def snapshot(self):
        value = super().snapshot()
        value.update(organization_runtime_version=VERSION,
            architecture=self.prepared.world.architecture_snapshot(),
            stage_boundaries=copy.deepcopy(self.stage_boundaries),
            deadline_receipt=self.deadline.snapshot(self.team_budget))
        return value


def _finish_stage(runtime, member, reason, *, unavailable=False):
    before = runtime.prepared.world.stage_state()
    runtime.prepared.world.finish_member_stage(member, reason, origin="runtime", unavailable=unavailable)
    association = getattr(runtime.policies[member], "_association", {})
    related = [event["sequence"] for event in runtime.recorder.events
               if event.get("worker_id") == member and event["kind"] == "model_boundary_error"
               and event["payload"].get("team_budget", {}).get("records", {}).get(association.get("call_id"))]
    row = {"member_id": member, "stage_id": before["stage_id"], "reason": reason,
           "opportunity_id": association.get("opportunity_id"), "last_call_id": association.get("call_id"),
           "boundary_experience_sequences": related,
           "unavailable_in_future_stages": unavailable, "permanent_retirement": _registry(runtime.prepared.world)[member]["status"] == "retired"}
    runtime.stage_boundaries.append(row)
    runtime.recorder.record("organization_stage_boundary_v047", row, worker_id=member)
    runtime.waiting.pop(member, None)


def _wake_reachable(runtime):
    for member in list(runtime.waiting):
        events = runtime.prepared.world.reachable_events(member, runtime.waiting[member])
        if events and member in runtime.prepared.world.runnable_members():
            del runtime.waiting[member]
            runtime.roles[member].update(status="ready", reason="New reachable work event")
            runtime.recorder.record("role_reactivated", {"event_sequences": [event["sequence"] for event in events],
                "decisions_already_consumed": _decisions(runtime, member), "budget_reset": False}, worker_id=member)


def _stage_can_advance(runtime):
    state = runtime.prepared.world.stage_state()
    unavailable = set(state.get("unavailable_members", [])) | set(runtime.stopped)
    registry = _registry(runtime.prepared.world)
    members = state.get("stage_members", runtime.prepared.case["stage_plan"][state["stage_index"]]["members"])
    finished = set(state.get("finished_members", []))
    return not state.get("final_stage", False) and all(
        member in finished or member in unavailable or registry[member]["status"] == "retired" for member in members)


def run_fragment(prepared, runtime, *, on_opportunity=None):
    outcomes, integrity_failure, closure_reason = [], None, None
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    world, deadline = prepared.world, runtime.deadline
    while True:
        deadline.check_hard("schedule")
        runtime.sync_members()
        snapshot = runtime.team_budget.snapshot()
        if snapshot.get("integrity_failure"):
            integrity_failure, closure_reason = snapshot["integrity_failure"], "execution_integrity_failure"
            break
        exhausted = [key for key in ("remaining_decisions", "remaining_attempts", "available_tokens") if snapshot[key] <= 0]
        if exhausted:
            closure_reason = "shared_team_pool_exhausted"
            break
        _wake_reachable(runtime)
        eligible = set(world.runnable_members()) - set(runtime.stopped)
        runnable = eligible - set(runtime.waiting)
        if not runnable:
            # An un-wakeable stage waiter ends only its current phase. Permanent
            # retirement and actual model/context stops remain non-reusable.
            for member in sorted(eligible & set(runtime.waiting)):
                _finish_stage(runtime, member, "no_reachable_stage_event")
            can_advance = _stage_can_advance(runtime)
            if can_advance:
                if not deadline.admit_new_work("before_new_architecture_stage"):
                    closure_reason = "administrative_soft_deadline"
                    break
                before = world.stage_state()
                world.advance_stage()
                after = world.stage_state()
                if after["stage_index"] == before["stage_index"]:
                    raise ValueError("A ready architecture stage failed to advance")
                deadline.stage_changed(before, after)
                for member in world.runnable_members():
                    if member not in runtime.stopped:
                        runtime.roles[member]["status"] = "ready"
                continue
            closure_reason = "architecture_terminal" if prepared.case["condition"][0] in "IP" else "all_members_stopped_or_no_reachable_event"
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
        if status == "completed":
            world.retire_member(member, reason="staff_done: " + result.get("reason", ""))
        runtime.sync_members()
        fatal = status in TECHNICAL_FAILURES and not (status == "policy_error" and result.get("action_performed"))
        if status == "administrative_soft_deadline":
            closure_reason = status
        elif status == "stage_budget_exhausted":
            _finish_stage(runtime, member, status)
        elif fatal or status in TERMINAL - {"policy_error", "model_format_error"}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.roles[member]["software_retired"] = True
            runtime.waiting.pop(member, None)
            _finish_stage(runtime, member, status, unavailable=True)
            if fatal:
                integrity_failure = {"member": member, "status": status, "reason": result.get("reason")}
                closure_reason = "execution_integrity_failure"
        elif member not in runtime.stopped and status in {"worker_waiting", "world_blocked"}:
            runtime.waiting[member] = _last_sequence(world)
            runtime.recorder.record("role_suspended", {"after_event_sequence": runtime.waiting[member],
                "decisions_already_consumed": _decisions(runtime, member)}, worker_id=member)
        runtime.note_population("completed_member_opportunity")
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None or status == "administrative_soft_deadline":
            break
    runtime.note_population("episode_closed")
    boundary = {"version": VERSION, "status": "execution_integrity_blocked" if integrity_failure else "bounded_work_closed",
        "kind": "frozen_architecture_terminal", "scheduling_protocol": SCHEDULER,
        "first_member": prepared.case["first_member"], "role_stops": copy.deepcopy(runtime.stopped),
        "waiting_members": copy.deepcopy(runtime.waiting), "outcomes": outcomes,
        "terminal_details": copy.deepcopy(runtime.terminal_details), "closure_reason": closure_reason,
        "execution_integrity_failure": integrity_failure, "opportunities": runtime.opportunities,
        "actions": runtime.actions, "team_budget": budget_snapshot(runtime, prepared),
        "initial_members": runtime.initial_members, "born_members": list(runtime.labels),
        "architecture": world.architecture_snapshot(), "stage_boundaries": copy.deepcopy(runtime.stage_boundaries),
        "administrative_censoring": deadline.prevented_work, "deadline_receipt": deadline.snapshot(runtime.team_budget),
        "continuation": False, "training_eligible": False, "admission_eligible": False,
        "action_error_policy": error_policy_summary(runtime),
        "scope": "One shared team ledger, real sessions, irreversible retirement, finite architecture phases; administrative cutoff never grants a closing model call."}
    runtime.recorder.record("run_boundary", boundary)
    runtime.recorder.record("organization_run_boundary_v047", boundary)
    return boundary


def build_runtime(owner, prepared, folder, *, deadline=None, worker_factory=None,
                  require_exact_resident=True):
    from .software_organization_v047 import PROJECT, SoftwareCollaborationPort, member_instruction, validate_case

    validate_case(prepared.case)
    worker_factory = worker_factory or worker_type()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = _StreamRecorder(folder / "experience.jsonl")
    deadline = deadline or DispatchDeadline()
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = StageTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        stage_provider=prepared.world.stage_state, stage_plan=prepared.case["stage_plan"],
        require_exact_resident=require_exact_resident,
        **{key: prepared.case["team_limits"][key] for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.bind_stage_budget(budget)
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
        # The personal fixed500k meter is not the released team250k/stage quota.
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
    value.update(version=VERSION, scheduling_protocol=SCHEDULER,
        architecture=prepared.world.architecture_snapshot(), stage_history=prepared.world.stage_state()["history"],
        stage_boundaries=copy.deepcopy(runtime.stage_boundaries),
        deadline_receipt=runtime.deadline.snapshot(runtime.team_budget),
        work_opportunity_snapshots=[copy.deepcopy(event) for event in runtime.recorder.events
            if event["kind"] == "organization_work_opportunity_v047"])
    value["member_lifecycle"]["actual_call_participants"] = sum(
        row["attempts"] > 0 for row in value["usage_by_member"].values())
    value["member_lifecycle"]["actual_call_members"] = [
        member for member, row in value["usage_by_member"].items() if row["attempts"] > 0]
    return value


def outcome_metrics(assessment, *, administratively_censored):
    """Fixed private-check fraction; never evaluate a second/mutable candidate."""
    evaluable = assessment.get("status") == "evaluable" and type(assessment.get("R")) is int
    checks = (assessment.get("independent_acceptance") or {}).get("checks", [])
    raw_score = sum(check.get("passed") is True for check in checks) / len(checks) if checks else None
    if not evaluable:
        r, q = None, None
    elif not assessment.get("submitted") or assessment.get("process_violation"):
        r, q = assessment["R"], 0.0
    else:
        if not checks or any(type(check.get("passed")) is not bool for check in checks):
            raise ValueError("Known submitted quality needs the original private acceptance checks")
        r, q = assessment["R"], raw_score
    return {"R_joint": r, "R_token": None if administratively_censored else r,
        "Q_joint": q, "Q_token": None if administratively_censored else q,
        "raw_content_score": raw_score, "private_checks_passed": sum(check.get("passed") is True for check in checks),
        "private_checks_total": len(checks), "Q_definition": "Original private contract checks passed / total for the sole last legal fixed delivery; no-delivery or process-invalid formal quality is0, technical unknown is null.",
        "administrative_censoring": administratively_censored,
        "outcome_scope": "joint_token_time_policy_only" if administratively_censored else "normal_token_budget_policy"}


def collect_episode(owner, prepared, folder, *, sampling_seed, slot_id, on_opportunity=None,
                    worker_factory=None, transport_factory=None, clock=time.monotonic,
                    soft_seconds=SOFT_SECONDS, hard_seconds=HARD_SECONDS):
    from .software_organization_v047 import assess_software_collaboration

    deadline = DispatchDeadline(clock=clock, soft_seconds=soft_seconds, hard_seconds=hard_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "slot-result.json").exists() or (folder / "episode").exists():
        raise ValueError("An already collected episode cannot be silently replayed")
    if type(sampling_seed) is not int or not 0 <= sampling_seed < 2**63 or not isinstance(slot_id, str) or not slot_id:
        raise ValueError("Each architecture episode needs its frozen slot and integer sampling seed")
    before, identity = owner.capture_evaluation_state(), owner.freeze_identity()
    binding = {key: copy.deepcopy(getattr(owner, key)) for key in
               ("recipe", "inference_profile", "base_identity", "software_learning_binding") if hasattr(owner, key)}
    runtime, captured, entries, result = None, {}, [], None
    episode_open, episode_closed = False, False
    started = time.time()
    owner.begin_window("organization-v047:" + slot_id)
    try:
        owner.reseed(sampling_seed, label=slot_id)
        context = context_transport(owner, folder / "raw-transport", deadline, transport_factory=transport_factory)
        facade = _CollectionOwner(owner, context)
        runtime, captured, _ = build_runtime(facade, prepared, folder, deadline=deadline, worker_factory=worker_factory)
        runtime.slot_id = slot_id
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["organization_runtime"] = {
            "version": VERSION, "context_protocol": CONTEXT_VERSION, "test_feedback_protocol": PAGING_VERSION,
            "purpose": prepared.case["purpose"], "sampling_seed": sampling_seed, "slot_id": slot_id,
            "actor_identity": identity, "training_eligible": False, "admission_eligible": False,
            "sdk_context_selection": SDK_CONTEXT_SELECTION, "team_limits": prepared.case["team_limits"],
            "scheduling_protocol": SCHEDULER, "action_error_policy": copy.deepcopy(ACTION_ERROR_POLICY),
            "case": copy.deepcopy(prepared.case), "time_policy": {"soft_seconds": soft_seconds, "hard_seconds": hard_seconds}}
        atomic_write(folder / "model-scenario.json", json_bytes(scenario))
        begin_episode(prepared.world, folder / "episode", experience=runtime.recorder.snapshot(),
                      work_ids=[], scenario=scenario, policies=runtime.policy_identities)
        episode_open = True

        def checkpoint(outcome):
            _append(folder / "runtime-opportunities.jsonl", outcome)
            atomic_write(folder / "runtime-state.json", json_bytes({"slot_id": slot_id,
                "opportunities": runtime.opportunities, "actions": runtime.actions,
                "availability": runtime.availability(), "team_budget": budget_snapshot(runtime, prepared),
                "architecture": prepared.world.stage_state(), "deadline_receipt": deadline.snapshot(runtime.team_budget)}))
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
            "architecture": prepared.world.architecture_snapshot(), "stage_history": prepared.world.stage_state()["history"],
            "action_error_policy": evidence["action_error_policy"], "process_violation": evidence["action_error_policy"]["process_violation"],
            "outcome_type": "business_delivery_under_joint_policy", "usage": evidence["total_usage"],
            "usage_by_member": evidence["usage_by_member"], "team_budget": evidence["team_budget"],
            "started_at": started, "ended_at": time.time(), "wall_seconds": time.time() - started,
            "training_eligible": False, "admission_eligible": False, "actor_identity": identity,
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
                    if owner.phase == "collecting" and not owner.busy:
                        owner.finish_evaluation(entries, folder / "frozen-collection-close")
                finally:
                    if not deadline.hard_expired:
                        guard = owner.finish_evaluation_guard(before)
                        deadline.check_hard("evaluation_guard")
                        guard.update(software_binding_unchanged=all(getattr(owner, key) == value for key, value in binding.items()),
                            actor_identity_unchanged=owner.freeze_identity() == identity)
                        atomic_write(folder / "evaluation-guard.json", json_bytes(guard))
                        if not all(guard[key] for key in ("learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged")):
                            raise ValueError("Frozen architecture collection changed protected learner state or RNG restoration failed")
            atomic_write(folder / "deadline-receipt.json", json_bytes(deadline.snapshot(runtime.team_budget if runtime else None)))
    deadline.mark_closed()
    receipt = deadline.snapshot(runtime.team_budget)
    result["deadline_receipt"] = receipt
    result["boundary"]["deadline_receipt"] = receipt
    result.update(ended_at=time.time(), wall_seconds=time.time() - started)
    evidence["deadline_receipt"] = receipt
    atomic_write(folder / "deadline-receipt.json", json_bytes(receipt))
    atomic_write(folder / "organization-evidence.json", json_bytes(evidence))
    atomic_write(folder / "slot-result.json", json_bytes(result))
    return result
