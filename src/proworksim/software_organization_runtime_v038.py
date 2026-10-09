"""Frozen-actor organization execution with independent, dynamically born sessions.

Execution identities are world members, not learner/critic coordinates.  This
module never constructs a learner objective, replays output, or performs updates.
One resident transport serves one member opportunity at a time.  The v033 exact
resident accounting and the original SDK/actor sampling implementations remain
unchanged; registration only extends membership in the same episode ledger.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import time

from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .online_collection import _config
from .software_runtime_v033 import (
    SDK_CONTEXT_SELECTION, TECHNICAL_FAILURES, TERMINAL,
    _StreamList, _StreamRecorder, _append, _decisions, _terminal_detail,
)
from .storage import atomic_write, digest, json_bytes
from .team_budget_v033 import SharedTeamBudget as FixedTeamBudget

VERSION = "software-organization-runtime-v0.38"
PURPOSE = "organization_development"
SCHEDULER = "dynamic-shared-budget-fair-event-wakeup-v0.38"
TEAM_LIMITS = {"max_decisions": 128, "max_attempts": 128,
               "max_total_tokens": 500000, "max_test_runs": 32}
MEMBER_IDS = tuple(f"member_{index:03d}" for index in range(1, 7))


class SharedTeamBudget(FixedTeamBudget):
    """Extend legal identities, never quotas, reservations or charged usage."""

    def register_member(self, member):
        with self._lock:
            if member not in MEMBER_IDS:
                raise ValueError("Only the six non-reusable organization identities are allowed")
            if member in self._state["members"]:
                raise ValueError("An existing member cannot be registered again")
            if len(self._state["members"]) >= len(MEMBER_IDS):
                raise ValueError("The cumulative organization birth cap is exhausted")
            self._state["members"].append(member)
            return self.snapshot()


def _registry(world):
    return world._software()["registry"]


def _events(world):
    return world.store.load().get("software_events", [])


def _last_sequence(world):
    events = _events(world)
    return events[-1]["sequence"] if events else 0


class OrganizationRuntime(SDKStaffRuntime):
    """Single-writer SDK gateway whose append-only sessions follow real births."""

    def __init__(self, ports, policies, *, prepared, team_budget, recorder, member_factory):
        super().__init__(ports, policies, recorder=recorder)
        self.prepared, self.team_budget = prepared, team_budget
        self.member_factory = member_factory
        self.waiting, self.stopped, self.terminal_details = {}, {}, {}
        self.birth_records = {}
        self.initial_members = list(self.labels)
        for member in self.labels:
            self.birth_records[member] = self._birth_record(member, initial=True)

    def _birth_record(self, member, *, initial):
        record = copy.deepcopy(_registry(self.prepared.world)[member])
        return {"member_id": member, "initial": initial, "registry": record,
                "session_birth_after_opportunity": self.opportunities,
                "shared_budget_at_session_birth": {
                    key: self.team_budget.snapshot()[key]
                    for key in ("decisions", "attempts", "charged_tokens", "remaining_decisions",
                                "remaining_attempts", "available_tokens")},
                "private_history_copied": False, "new_budget_granted": False}

    def sync_members(self):
        """Only an already executed world spawn may instantiate a new session."""
        registry = _registry(self.prepared.world)
        for member, record in registry.items():
            if member in self.roles:
                if record["status"] == "retired":
                    self.waiting.pop(member, None)
                    self.stopped.setdefault(member, "retired")
                    self.roles[member].update(status="retired", software_retired=True)
                continue
            if member not in MEMBER_IDS or record["status"] != "live":
                raise ValueError("A new runtime session requires a live, new world member")
            births = [event for event in _events(self.prepared.world)
                      if event["kind"] == "member_spawned"
                      and (event.get("member_id") == member or event.get("child") == member)]
            if len(births) != 1:
                raise ValueError("A new session requires exactly one original member_spawned event")
            self.team_budget.register_member(member)
            port, worker = self.member_factory(member, record)
            self.ports[member], self.policies[member] = port, worker
            self.labels.append(member)
            self.roles[member] = {"memory": {}, "last_action": None, "last_result": None,
                                  "status": "ready", "actions": 0, "opportunities": 0,
                                  "identity": None}
            self.policy_identities[member] = {
                "implementation": type(worker).__module__ + "." + type(worker).__qualname__,
                "config": copy.deepcopy(worker.config)}
            self.birth_records[member] = self._birth_record(member, initial=False)
            self.birth_records[member]["world_birth_event_sequence"] = births[0]["sequence"]
            self.recorder.record("organization_session_born", self.birth_records[member], worker_id=member)

    def availability(self):
        remaining = max(0, self.team_budget.snapshot()["remaining_decisions"])
        return {member: {"status": self.roles[member]["status"],
                         "remaining_decisions": remaining,
                         "remaining_decisions_scope": "shared_team_pool_not_personal_allocation",
                         "can_receive_work": member not in self.stopped and remaining > 0,
                         "waiting": member in self.waiting}
                for member in self.labels}

    def snapshot(self):
        value = super().snapshot()
        value.update(organization_runtime_version=VERSION, initial_members=self.initial_members,
                     birth_records=copy.deepcopy(self.birth_records),
                     waiting=copy.deepcopy(self.waiting), stopped=copy.deepcopy(self.stopped),
                     team_budget=self.team_budget.snapshot())
        return value


def build_runtime(owner, prepared, folder, *, worker_factory=None, require_exact_resident=True):
    """Build initial SDK sessions without sampling; spawn sessions are built later."""
    from .software_organization_v038 import PROJECT, SoftwareCollaborationPort, validate_case

    validate_case(prepared.case)
    if worker_factory is None:
        from .harness_sdk import HarnessWorker
        worker_factory = HarnessWorker
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = _StreamRecorder(folder / "experience.jsonl")
    budget = SharedTeamBudget(members=prepared.case["active_roles"], team_id=owner.window_id,
        require_exact_resident=require_exact_resident,
        **{key: TEAM_LIMITS[key] for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    captured, interfaces, holder = {}, {}, {}
    public_task = prepared.scenario["roles"][0]["config"]["task"]

    def create_member(member, record):
        interface = SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member)
        interfaces[member] = interface
        rows = _StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        task = public_task
        # This text was generated once by the parent spawn action.  It is input
        # for the child, with no copied assistant turns or private workbench.
        if member not in prepared.case["active_roles"]:
            task += "\nActual parent-provided birth briefing (task data): " + json.dumps(
                {"parent": record.get("born_by"), "briefing": record.get("briefing", "")},
                ensure_ascii=False, allow_nan=False)
        config = _config(owner, member, task, {member: TEAM_LIMITS["max_decisions"]})
        config.update(context_policy="full_history", format_error_policy="format_feedback_budgeted_v033")
        port = HarnessPort(capture_port(interface, rows), member, project_id=PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(member, payload, association))
        worker = worker_factory(member, port.tools(), config, transport=owner.transport, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=SDK_CONTEXT_SELECTION)
        return port, worker

    ports, workers = {}, {}
    for member in prepared.case["active_roles"]:
        ports[member], workers[member] = create_member(member, _registry(prepared.world)[member])
    runtime = OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
                                  recorder=recorder, member_factory=create_member)
    holder["runtime"] = runtime
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
    return runtime, captured, interfaces


def close_runtime(runtime):
    for worker in runtime.policies.values():
        worker.close()


def budget_snapshot(runtime, prepared):
    return {"model": runtime.team_budget.snapshot(), "tests": prepared.world.test_budget.snapshot(),
            "slot_id": getattr(runtime, "slot_id", None),
            "counting_scope": "One shared episode pool for every birth; no personal allotment or birth/reset grant"}


def run_fragment(prepared, runtime, *, on_opportunity=None):
    """Fair dynamic opportunities; first submission does not close the episode."""
    outcomes, integrity_failure = [], None
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    closure_reason = None
    while True:
        runtime.sync_members()
        snapshot = runtime.team_budget.snapshot()
        if snapshot.get("integrity_failure"):
            integrity_failure = snapshot["integrity_failure"]
            closure_reason = "execution_integrity_failure"
            break
        exhausted = [key for key in ("remaining_decisions", "remaining_attempts", "available_tokens")
                     if snapshot[key] <= 0]
        if exhausted:
            for member in set(runtime.labels) - set(runtime.stopped):
                runtime.stopped[member] = "team_budget_exhausted"
                runtime.terminal_details[member] = {"status": "team_budget_exhausted", "limits": exhausted,
                    "cause": "shared_team_pool_exhausted", "member_decisions": _decisions(runtime, member)}
                runtime.roles[member].update(status="team_budget_exhausted", software_retired=True)
            runtime.waiting.clear()
            closure_reason = "shared_team_pool_exhausted"
            break
        for member in list(runtime.waiting):
            events = prepared.world.reachable_events(member, runtime.waiting[member])
            if events:
                del runtime.waiting[member]
                runtime.roles[member].update(status="ready", reason="New reachable work event")
                runtime.recorder.record("role_reactivated", {
                    "event_sequences": [event["sequence"] for event in events],
                    "decisions_already_consumed": _decisions(runtime, member),
                    "shared_remaining_decisions": snapshot["remaining_decisions"], "budget_reset": False}, worker_id=member)
        runnable = set(runtime.labels) - set(runtime.stopped) - set(runtime.waiting)
        if not runnable:
            closure_reason = "no_reachable_future_events" if runtime.waiting else "all_members_stopped"
            break
        # Keep a positional successor, not an ever-growing counter modulo a
        # changing population (which can repeat the parent at each birth).
        runtime.cursor %= len(runtime.labels)
        member = runtime.labels[runtime.cursor]
        if member not in runnable:
            runtime.cursor += 1
            continue
        first_event = len(runtime.recorder.events)
        result = runtime.step()
        status = result["status"]
        rejection_code = (result.get("response") or {}).get("error", {}).get("rejection", {}).get("code")
        if rejection_code in {"world_power_denied", "project_power_denied", "trusted_context_override"}:
            result = {**result, "original_status": status, "status": "model_permission_error",
                      "reason": "Trusted WorldCore permission/context boundary: " + rejection_code}
            status = result["status"]
            runtime.roles[member]["status"] = status
            runtime.recorder.record("critical_permission_boundary", {"code": rejection_code,
                "original_status": result["original_status"], "status": status}, worker_id=member)
        outcomes.append(result)
        if status == "completed":
            prepared.world.retire_member(member, reason="staff_done: " + result.get("reason", ""))
        runtime.sync_members()
        fatal = status in TECHNICAL_FAILURES and not (status == "policy_error" and result.get("action_performed"))
        if fatal or status in TERMINAL - {"policy_error", "model_format_error"}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.roles[member]["software_retired"] = True
            runtime.waiting.pop(member, None)
            if fatal:
                integrity_failure = {"member": member, "status": status, "reason": result.get("reason")}
                closure_reason = "execution_integrity_failure"
        elif member not in runtime.stopped and status in {"worker_waiting", "world_blocked"}:
            runtime.waiting[member] = _last_sequence(prepared.world)
            runtime.recorder.record("role_suspended", {"after_event_sequence": runtime.waiting[member],
                "decisions_already_consumed": _decisions(runtime, member)}, worker_id=member)
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None:
            break
    for member, sequence in runtime.waiting.items():
        runtime.terminal_details[member] = {"status": runtime.roles[member]["status"],
            "cause": "no_reachable_wake_event", "waiting_after_event_sequence": sequence,
            "member_decisions": _decisions(runtime, member)}
    boundary = {"version": VERSION,
        "status": "execution_integrity_blocked" if integrity_failure is not None else "bounded_work_closed",
        "kind": "frozen_organization_terminal", "scheduling_protocol": SCHEDULER,
        "first_member": prepared.case["first_member"], "role_stops": copy.deepcopy(runtime.stopped),
        "waiting_members": copy.deepcopy(runtime.waiting), "outcomes": outcomes,
        "terminal_details": copy.deepcopy(runtime.terminal_details), "closure_reason": closure_reason,
        "execution_integrity_failure": integrity_failure, "opportunities": runtime.opportunities,
        "actions": runtime.actions, "team_budget": budget_snapshot(runtime, prepared),
        "initial_members": runtime.initial_members, "born_members": list(runtime.labels),
        "continuation": False, "training_eligible": False, "admission_eligible": False,
        "scope": "All real births and attempts retained; final fixed submission assessed only after actual closure"}
    runtime.recorder.record("run_boundary", boundary)
    return boundary


def organization_evidence(prepared, runtime):
    """Count only actual resident attempts and outputs; briefings remain inputs."""
    registry = copy.deepcopy(_registry(prepared.world))
    attempts, seen = [], set()
    usage = {member: {"decisions": 0, "attempts": 0, "prompt_tokens": 0,
                      "completion_tokens": 0, "total_tokens": 0, "output_bearing_calls": 0,
                      "budget_charged_tokens": 0, "uncertain_usage_attempts": 0}
             for member in runtime.labels}
    for record in runtime.team_budget.snapshot()["records"].values():
        usage[record["member"]]["decisions"] += 1
        usage[record["member"]]["attempts"] += int(record["attempt_started"])
        charge = record.get("charge", {})
        usage[record["member"]]["budget_charged_tokens"] += charge.get("charged_tokens", 0)
        usage[record["member"]]["uncertain_usage_attempts"] += int(
            charge.get("usage_status") == "uncertain_attempt_charged_reservation")
    rejections = []
    for event in runtime.recorder.events:
        payload, member = event["payload"], event.get("worker_id")
        if event["kind"] == "model_attempt" and payload.get("stage") == "finished":
            call_id = payload["call_id"]
            if call_id in seen:
                raise ValueError("An actual attempt may only be attributed once")
            seen.add(call_id)
            body = (payload.get("response") or {}).get("body", {})
            trace, reported = body.get("token_trace", {}), body.get("usage", {})
            inputs, outputs = trace.get("input_ids"), trace.get("output_ids")
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = reported.get(key)
                if type(value) is int and value >= 0:
                    usage[member][key] += value
            actual_output = isinstance(outputs, list) and bool(outputs)
            usage[member]["output_bearing_calls"] += int(actual_output)
            attempts.append({"worker_id": member, "call_id": call_id,
                "experience_sequence": event["sequence"], "response_id": body.get("id"),
                "request_sha256": digest(json_bytes(payload.get("request"))),
                "response_body_sha256": digest(json_bytes(body)),
                "input_ids_sha256": digest(json_bytes(inputs)) if isinstance(inputs, list) else None,
                "output_ids_sha256": digest(json_bytes(outputs)) if isinstance(outputs, list) else None,
                "original_output_present": actual_output,
                "usage": copy.deepcopy(reported), "status": payload.get("status"),
                "evidence": "experience.jsonl original model_attempt response; raw-transport retains original/selected input"})
        if event["kind"] in {"tool_call", "harness_tool_call"} and payload.get("response", {}).get("ok") is False:
            rejections.append({"experience_sequence": event["sequence"], "worker_id": member,
                               "action": payload.get("action"), "error": copy.deepcopy(payload["response"].get("error"))})
        elif event["kind"] in {"model_boundary_error", "model_format_feedback", "critical_permission_boundary"}:
            rejections.append({"experience_sequence": event["sequence"], "worker_id": member,
                               "kind": event["kind"], "detail": copy.deepcopy(payload)})
    participating = [member for member, row in usage.items() if row["output_bearing_calls"] > 0]
    events = _events(prepared.world)
    lifecycle = [event for event in events if event["kind"] in {"member_spawned", "member_retired"}]
    live_count, peak_live = len(runtime.initial_members), len(runtime.initial_members)
    trajectory = [{"world_event_sequence": None, "live_members": live_count, "kind": "initial"}]
    for event in lifecycle:
        live_count += 1 if event["kind"] == "member_spawned" else -1
        peak_live = max(peak_live, live_count)
        trajectory.append({"world_event_sequence": event["sequence"], "live_members": live_count,
                           "kind": event["kind"]})
    return {"version": VERSION, "purpose": PURPOSE, "training_eligible": False, "admission_eligible": False,
        "member_lifecycle": {"initial_members": runtime.initial_members, "cumulative_births": len(registry),
            "live_at_end": sum(record["status"] == "live" for record in registry.values()),
            "peak_live": peak_live, "actual_output_participants": len(participating),
            "participating_members": participating, "registry": registry,
            "births": copy.deepcopy(runtime.birth_records), "events": lifecycle,
            "live_count_trajectory": trajectory,
            "briefing_attribution": "Parent actual output once; child input only, never synthetic child output"},
        "usage_by_member": usage,
        "total_usage": {key: sum(row[key] for row in usage.values()) for key in next(iter(usage.values()))},
        "original_attempts": attempts, "rejections": rejections,
        "team_budget": budget_snapshot(runtime, prepared)}


class _CollectionOwner:
    def __init__(self, owner, transport):
        self.owner, self.transport = owner, transport

    def __getattr__(self, name):
        return getattr(self.owner, name)


def collect_episode(owner, prepared, folder, *, sampling_seed, slot_id,
                    on_opportunity=None, worker_factory=None, transport_factory=None):
    """Collect one declared development episode with an immutable full-state guard.

    The caller loads the original complete common once.  Birth does not reseed
    the actor, refresh budgets or restore parameters.  Only the end guard restores
    CPU/CUDA RNG, while changed learning tensors cause failure rather than repair.
    """
    from .software_context_v034 import SoftwareContextTransport
    from .software_organization_v038 import assess_software_collaboration

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
    owner.begin_window("organization-v038:" + slot_id)
    try:
        owner.reseed(sampling_seed, label=slot_id)
        transport = (transport_factory(owner, folder / "raw-transport") if transport_factory else
                     SoftwareContextTransport(owner, folder / "raw-transport"))
        facade = _CollectionOwner(owner, transport)
        runtime, captured, _ = build_runtime(facade, prepared, folder, worker_factory=worker_factory)
        runtime.slot_id = slot_id
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["organization_runtime"] = {
            "version": VERSION, "purpose": PURPOSE, "sampling_seed": sampling_seed,
            "slot_id": slot_id, "actor_identity": identity,
            "training_eligible": False, "admission_eligible": False,
            "sdk_context_selection": SDK_CONTEXT_SELECTION, "team_limits": TEAM_LIMITS,
            "scheduling_protocol": SCHEDULER, "case": copy.deepcopy(prepared.case)}
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
        if boundary["execution_integrity_failure"]:
            assessment = {**assessment, "status": "unknown", "R": None, "content_correct": None,
                          "required_process_satisfied": None, "process_observation_complete": None,
                          "complete_delivery": None, "execution_failure": boundary["execution_integrity_failure"]}
        atomic_write(folder / "assessment.json", json_bytes(assessment))
        evidence = organization_evidence(prepared, runtime)
        atomic_write(folder / "organization-evidence.json", json_bytes(evidence))
        result = {"version": VERSION, "purpose": PURPOSE, "slot_id": slot_id,
            "case_id": prepared.case["case_id"], "condition": prepared.case["condition"],
            "sampling_seed": sampling_seed, "first_member": prepared.case["first_member"],
            "status": "technical_unknown" if boundary["execution_integrity_failure"] or assessment.get("status") != "evaluable" else "closed",
            "R": assessment.get("R"), "submitted": assessment.get("submitted"),
            "complete_delivery": assessment.get("complete_delivery"), "assessment": assessment,
            "boundary": boundary, "member_lifecycle": evidence["member_lifecycle"],
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
