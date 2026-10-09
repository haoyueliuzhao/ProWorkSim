"""v039 frozen collection: v038 member machinery plus one explicit control boundary.

The resident actor, exact shared ledger, SDK action execution, fairness, event
wakeup and evaluation-state guards are inherited unchanged.  New dependency
bindings name the v039 world directly, without relabeling a v038 case.  X3 is an
operator event after a completed team decision; it never synthesizes a worker
message, assistant output, task assignment, token or optimizer operation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import time

from . import software_organization_runtime_v038 as base
from .episode import begin_episode, finish_episode
from .experience import capture_port
from .harness_port import HarnessPort
from .online_collection import _config
from .software_organization_runtime_v038 import (
    SharedTeamBudget, _CollectionOwner, _registry, _StreamList, _StreamRecorder,
    _append, budget_snapshot, close_runtime,
)
from .software_organization_v039 import (
    CONTROLLER_TOOL, DIAGNOSTIC_PURPOSE, EXTERNAL_DECISION, PROJECT, SCHEDULER,
)
from .software_runtime_v033 import SDK_CONTEXT_SELECTION, TECHNICAL_FAILURES
from .storage import atomic_write, json_bytes

VERSION = "software-organization-runtime-v0.39"
WAIT_DESCRIPTION = (
    "Suspend this member without advancing work or time and without creating an event. "
    "Only an actual reachable message, public work or membership event can wake it; "
    "waiting keeps its live capacity position and never resets the shared budget.")
DONE_DESCRIPTION = (
    "Permanently stop this member's future opportunities. Obligations remain visible. "
    "This does not submit, approve, transfer work or establish business success.")


def specialize_control_tools(worker):
    """Change only this new session's tool text before its first model call.

    The SDK request is built from the worker's own definitions; update its bound
    SDK tool object as well. Historical CONTROL_TOOLS and modules are untouched.
    Scripted CPU workers need not expose SDK internals.
    """
    descriptions = {"staff_wait": WAIT_DESCRIPTION, "staff_done": DONE_DESCRIPTION}
    for definition in getattr(worker, "definitions", []):
        if definition["name"] in descriptions:
            definition["description"] = descriptions[definition["name"]]
    agent = getattr(worker, "agent", None)
    if agent is not None:
        from openhands.sdk.tool import register_tool, resolve_tool
        # These are the worker's uniquely registered fixed instances. Resolving
        # them does not initialize/run the lazy Agent or create an observation.
        for specification in agent.tools:
            for tool in resolve_tool(specification, worker.conversation.state):
                if tool.name in descriptions:
                    # SDK ToolDefinitions are frozen values. Rebind only this
                    # worker's unique registration to a shallow copied value;
                    # its original executor/action schema are retained exactly.
                    register_tool(specification.name, tool.model_copy(update={"description": descriptions[tool.name]}))


class OrganizationRuntime(base.OrganizationRuntime):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        enabled = self.prepared.case["external_intervention"]["enabled"]
        self.external_intervention = {"version": VERSION, "enabled": enabled,
            "status": "pending" if enabled else "not_applicable", "attempts": 0,
            "trigger_team_decisions": EXTERNAL_DECISION if enabled else None,
            "controller_actor": "operator", "origin": "external_controller",
            "member_id": None, "reason": None, "model_generated": False,
            "model_calls": 0, "model_output_tokens": 0, "team_budget_added": False}
        self.controller_cost = {"world_actions": 0, "world_transaction_wall_seconds": 0.0,
            "session_creation_wall_seconds": 0.0, "initial_workspace_bytes": 0,
            "model_calls": 0, "generated_tokens": 0}
        self.population_trace, self._participants = [], set()
        self._participation_cursor = 0
        self.owner = None

    def note_population(self, cause):
        for event in self.recorder.events[self._participation_cursor:]:
            if event["kind"] == "model_attempt" and event["payload"].get("stage") == "finished":
                outputs = event["payload"].get("response", {}).get("body", {}).get("token_trace", {}).get("output_ids")
                if isinstance(outputs, list) and outputs:
                    self._participants.add(event["worker_id"])
        self._participation_cursor = len(self.recorder.events)
        registry = _registry(self.prepared.world)
        row = {"cause": cause, "completed_team_decisions": self.team_budget.snapshot()["decisions"],
            "opportunities": self.opportunities, "initial_member_count": len(self.initial_members),
            "cumulative_births": len(registry),
            "live_members": [member for member, record in registry.items() if record["status"] == "live"],
            "runnable_members": [member for member in self.labels if member not in self.stopped and member not in self.waiting],
            "output_participants": sorted(self._participants)}
        self.population_trace.append(row)
        self.recorder.record("organization_population", row)
        return row

    def snapshot(self):
        result = super().snapshot()
        result.update(organization_runtime_version=VERSION, inherited_runtime_version=base.VERSION,
            external_intervention=copy.deepcopy(self.external_intervention),
            controller_cost=copy.deepcopy(self.controller_cost), population_trace=copy.deepcopy(self.population_trace))
        return result

    def _finish_control(self, status, reason=None, **details):
        self.external_intervention.update(status=status, reason=reason, **details)
        self.recorder.record("external_intervention_disposition", copy.deepcopy(self.external_intervention))

    def after_completed_opportunity(self, result):
        self.note_population("completed_member_opportunity")
        control = self.external_intervention
        if control["status"] != "pending":
            return
        snapshot = self.team_budget.snapshot()
        count = snapshot["decisions"]
        if count < EXTERNAL_DECISION:
            return
        if count != EXTERNAL_DECISION:
            raise ValueError("The single external event cannot be moved past its preregistered decision boundary")
        if self._in_step or self.owner is not None and self.owner.busy:
            raise ValueError("External membership changes require a quiescent, fully completed model opportunity")
        control["observed_team_decisions"] = count
        control["observed_model_attempts"] = snapshot["attempts"]
        control["after_opportunity"] = self.opportunities
        control["trigger_reached"] = True
        world = self.prepared.world
        runnable = set(self.labels) - set(self.stopped) - set(self.waiting)
        reachable_waiters = [member for member, after in self.waiting.items() if world.reachable_events(member, after)]
        fatal = result["status"] in TECHNICAL_FAILURES and not (
            result["status"] == "policy_error" and result.get("action_performed"))
        if fatal or snapshot.get("integrity_failure"):
            self._finish_control("skipped", "execution_integrity_failure")
        elif not runnable and not reachable_waiters:
            self._finish_control("skipped", "natural_terminal")
        elif (min(snapshot[key] for key in ("remaining_decisions", "remaining_attempts", "available_tokens")) <= 0
              or self.owner is not None and snapshot["available_tokens"] <= self.owner.recipe["max_output_tokens"]):
            self._finish_control("skipped", "no_shared_resources")
        elif len(world.live_members()) >= self.prepared.case["member_limits"]["max_live_members"]:
            self._finish_control("skipped", "live_capacity")
        elif len(_registry(world)) >= self.prepared.case["member_limits"]["max_cumulative_births"]:
            self._finish_control("skipped", "cumulative_birth_limit")
        else:
            control["attempts"] = 1
            started = time.monotonic()
            world.external_birth_authorized = True
            try:
                response = world.session("operator", PROJECT).call(CONTROLLER_TOOL,
                    completed_team_decisions=EXTERNAL_DECISION)
            finally:
                world.external_birth_authorized = False
            self.controller_cost["world_transaction_wall_seconds"] = time.monotonic() - started
            self.controller_cost["world_actions"] = 1
            self.recorder.record("controller_world_action", {"origin": "external_controller",
                "actor_id": "operator", "tool": CONTROLLER_TOOL,
                "arguments": {"completed_team_decisions": EXTERNAL_DECISION}, "response": response,
                "model_generated": False, "member_output_tokens": 0})
            if not response["ok"]:
                self._finish_control("execution_error", "controller_world_action_rejected", response=response)
                raise ValueError("The preregistered external birth failed after runtime admission")
            if self.team_budget.snapshot() != snapshot:
                raise ValueError("The controller changed the model ledger before session registration")
            started = time.monotonic()
            self.sync_members()
            self.controller_cost["session_creation_wall_seconds"] = time.monotonic() - started
            self.controller_cost["initial_workspace_bytes"] = response["result"]["initial_workspace_bytes"]
            after = self.team_budget.snapshot()
            if any(after[key] != snapshot[key] for key in ("limits", "records", "binding", "decisions", "attempts",
                    "charged_tokens", "remaining_decisions", "remaining_attempts", "available_tokens")):
                raise ValueError("The external session added resources or rewrote actual attempts")
            self._finish_control("implemented", member_id=response["result"]["member_id"],
                world_birth_event_sequence=response["result"]["birth_sequence"],
                shared_budget_before={key: snapshot[key] for key in ("decisions", "attempts", "charged_tokens", "available_tokens")},
                shared_budget_after={key: after[key] for key in ("decisions", "attempts", "charged_tokens", "available_tokens")})
            self.note_population("external_neutral_member_created")


def run_fragment(prepared, runtime, *, on_opportunity=None):
    def after_step(result):
        runtime.after_completed_opportunity(result)
        if on_opportunity:
            on_opportunity(result)
    inherited = base.run_fragment(prepared, runtime, on_opportunity=after_step)
    if runtime.external_intervention["status"] == "pending":
        runtime._finish_control("skipped", "execution_integrity_failure" if inherited["execution_integrity_failure"] else "natural_terminal",
            trigger_reached=False, observed_team_decisions=runtime.team_budget.snapshot()["decisions"],
            after_opportunity=runtime.opportunities)
    runtime.note_population("episode_closed")
    boundary = {**inherited, "version": VERSION, "scheduling_protocol": SCHEDULER,
        "base_runtime_provenance": {"version": inherited["version"], "scheduling_protocol": inherited["scheduling_protocol"],
            "unchanged": "SDK execution, shared ledger, fair opportunities, real-event wakeup and permanent stops"},
        "external_intervention": copy.deepcopy(runtime.external_intervention),
        "controller_cost": copy.deepcopy(runtime.controller_cost)}
    runtime.recorder.record("organization_run_boundary_v039", boundary)
    return boundary


def organization_evidence(prepared, runtime):
    value = base.organization_evidence(prepared, runtime)
    value.update(version=VERSION, purpose=prepared.case["purpose"], inherited_evidence_version=base.VERSION,
        external_intervention=copy.deepcopy(runtime.external_intervention), controller_cost=copy.deepcopy(runtime.controller_cost))
    life = value["member_lifecycle"]
    life.update(runnable_at_end=len(set(runtime.labels) - set(runtime.stopped) - set(runtime.waiting)),
        initial_live_members=[member for member in runtime.initial_members if runtime.birth_records[member]["registry"]["status"] == "live"],
        population_trace=copy.deepcopy(runtime.population_trace),
        member_requested_births=sum(row["kind"] == "member_spawned" and row.get("origin") == "member_request" for row in life["events"]),
        external_births=sum(row["kind"] == "member_spawned" and row.get("origin") == "external_controller" for row in life["events"]),
        setup_events=[row for row in life["events"] if row.get("origin") == "diagnostic_setup"],
        briefing_attribution="Actual parent briefing is parent output once and child input. External births have no member briefing/output; setup is never model work.")
    setup = prepared.world._software().get("diagnostic_setup")
    value["diagnostic_setup"] = copy.deepcopy(setup)
    return value


def _actual_input_observations(runtime):
    for event in runtime.recorder.events:
        payload = event["payload"]
        if event["kind"] != "model_attempt" or payload.get("stage") != "finished":
            continue
        if not payload.get("response", {}).get("body", {}).get("token_trace", {}).get("output_ids"):
            continue
        # The inherited capacity selector retains the latest full observation.
        for message in reversed(payload.get("request", {}).get("messages", [])):
            if message.get("role") != "user" or not isinstance(message.get("content"), str):
                continue
            try:
                value = json.loads(message["content"])
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and isinstance(value.get("observation"), dict):
                yield event["worker_id"], value["observation"], event["sequence"]
                break


def diagnostic_outcome(prepared, runtime):
    diagnostic = prepared.case.get("diagnostic")
    if diagnostic is None:
        return None
    world = prepared.world
    events = world.store.load().get("software_events", [])
    births = [row for row in events if row["kind"] == "member_spawned" and row.get("origin") == "member_request"]
    observations = list(_actual_input_observations(runtime))
    evidence = organization_evidence(prepared, runtime)
    checks = {"member_requested_birth_executed": bool(births),
              "new_session_produced_output": any(evidence["usage_by_member"].get(row["member_id"], {}).get("output_bearing_calls", 0) > 0 for row in births)}
    witnesses = []
    if diagnostic["probe_id"] == "birth-message":
        messages = [row for row in events if row["kind"] == "work_message" and any(
            row["actor_id"] == birth["member_id"] and row["recipient"] == birth["born_by"] for birth in births)]
        checks.update(public_baseline_birth=any(row["initial_patch_id"] is None for row in births),
            child_reply_executed=bool(messages),
            reply_reached_parent_actual_input=any(member == message["recipient"] and any(
                observed.get("sequence") == message["sequence"] for observed in observation.get("messages", []))
                for message in messages for member, observation, _ in observations))
        witnesses = [{"birth_sequence": row["sequence"], "member_id": row["member_id"], "parent": row["born_by"]} for row in births]
        witnesses += [{"message_sequence": row["sequence"], "sender": row["actor_id"], "recipient": row["recipient"]} for row in messages]
    else:
        setup = world._software()["diagnostic_setup"]
        replacements = [row for row in births if row["replaces"] == setup["retired_identity"]]
        exact = [row for row in replacements if row["initial_patch_id"] == setup["patch_id"]
                 and row["initial_source_reference"] == setup["patch_source_reference"]]
        readers = [row for row in events if row["kind"] == "read" and row.get("origin") != "diagnostic_setup"
            and row["path"] == setup["path"] and any(row["actor_id"] == birth["member_id"]
                and row["source_reference"] in (birth["workspace_reference"], setup["patch_source_reference"])
                for birth in exact)]
        checks.update(explicit_retired_identity_replaced=bool(replacements),
            exact_published_snapshot_initialized=bool(exact), new_member_read_initialized_file=bool(readers))
        witnesses = [{"birth_sequence": row["sequence"], "member_id": row["member_id"],
                      "initial_source_reference": row["initial_source_reference"]} for row in replacements]
        witnesses += [{"read_sequence": row["sequence"], "member_id": row["actor_id"], "source_reference": row["source_reference"]} for row in readers]
    failure = any(status in TECHNICAL_FAILURES for status in runtime.stopped.values())
    return {"probe_id": diagnostic["probe_id"], "purpose": DIAGNOSTIC_PURPOSE,
        "status": "technical_unknown" if failure else "closed", "goals": checks,
        "all_goals_met": None if failure else all(checks.values()), "evidence": witnesses,
        "business_R": None, "training_eligible": False, "autonomous_behavior_evidence": False,
        "setup_model_generated": False, "automatic_retry": False,
        "scope": "One explicitly requested model interface control, not main-panel work quality or spontaneous recruitment"}


def build_runtime(owner, prepared, folder, *, worker_factory=None, require_exact_resident=True):
    """Build initial SDK sessions without sampling; spawn sessions are built later."""
    from .software_organization_v039 import PROJECT, SoftwareCollaborationPort, validate_case, member_instruction

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
    from .software_context_v034 import SoftwareContextTransport
    from .software_organization_v039 import assess_software_collaboration

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
    owner.begin_window("organization-v039:" + slot_id)
    try:
        owner.reseed(sampling_seed, label=slot_id)
        transport = (transport_factory(owner, folder / "raw-transport") if transport_factory else
                     SoftwareContextTransport(owner, folder / "raw-transport"))
        facade = _CollectionOwner(owner, transport)
        runtime, captured, _ = build_runtime(facade, prepared, folder, worker_factory=worker_factory)
        runtime.slot_id = slot_id
        scenario = copy.deepcopy(prepared.scenario)
        scenario.setdefault("variation", {})["organization_runtime"] = {
            "version": VERSION, "purpose": purpose, "sampling_seed": sampling_seed,
            "slot_id": slot_id, "actor_identity": identity,
            "training_eligible": False, "admission_eligible": False,
            "sdk_context_selection": SDK_CONTEXT_SELECTION, "team_limits": prepared.case["team_limits"],
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
        result = {"version": VERSION, "purpose": purpose, "slot_id": slot_id,
            "case_id": prepared.case["case_id"], "condition": prepared.case["condition"],
            "sampling_seed": sampling_seed, "first_member": prepared.case["first_member"],
            "status": "technical_unknown" if boundary["execution_integrity_failure"] or assessment.get("status") not in {"evaluable", "interface_diagnostic_not_business_assessed"} else "closed",
            "R": assessment.get("R"), "submitted": assessment.get("submitted"),
            "complete_delivery": assessment.get("complete_delivery"), "assessment": assessment,
            "boundary": boundary, "member_lifecycle": evidence["member_lifecycle"],
            "external_intervention": evidence["external_intervention"], "controller_cost": evidence["controller_cost"],
            "diagnostic": diagnostic_outcome(prepared, runtime) if prepared.case.get("diagnostic") else None,
            "outcome_type": "interface_control" if prepared.case.get("diagnostic") else "business_delivery",
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
