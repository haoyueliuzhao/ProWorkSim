"""Injected-model fixed-organization runtime on the real managed SDK harness.

This library has no credential, network, GPU, Docker or evaluation launcher.
It is prepared for subsequent review; CPU fixtures inject scripted responses.
"""
from __future__ import annotations

import copy
from pathlib import Path
import time

from . import software_fixed_organization_world_v065 as world
from . import software_benchmark_managed_v064 as aligned
from . import software_calibration_collector_v051 as base
from .experience import capture_port
from .harness_port import HarnessPort
from .online_collection import _config
from .repository_sources_v054 import RepositorySources, tree_manifest
from .software_benchmark_candidates_v054 import write_new
from .software_fixed_organization_v065 import MEMBERS, validate_organization, require_evaluation_disabled
from .software_organization_runtime_v038 import _CollectionOwner
from .software_organization_runtime_v047 import NativeDispatchGate
from .software_runtime_v033 import TECHNICAL_FAILURES, TERMINAL, _terminal_detail
from .storage import digest, json_bytes

VERSION = "v065-fixed-organization-managed-runtime-r1"
ProjectOwner = aligned.ProjectOwner
ManagedTeamBudget = aligned.ManagedTeamBudget
close_runtime = base.close_runtime


class FixedPhaseSchedule:
    """Finite, predeclared cyclic slots; skipping never executes world work."""
    def __init__(self, spec):
        validate_organization(spec)
        self.spec = copy.deepcopy(spec)
        self.slots = [(index, phase["name"], phase["active_members"][n % len(phase["active_members"])])
            for index, phase in enumerate(spec["phases"]) for n in range(phase["opportunities"])]
        self.position, self.executed, self.skipped = 0, 0, 0

    def choose(self, runnable):
        runnable = set(runnable)
        if not runnable <= set(MEMBERS):
            raise ValueError("The scheduler cannot admit another identity")
        for _ in self.slots:
            index, name, member = self.slots[self.position % len(self.slots)]
            value = {"organization_id": self.spec["id"], "cycle": self.position // len(self.slots),
                     "slot_position": self.position, "phase_index": index, "phase_name": name,
                     "member": member, "selection_basis": "fixed schedule, never score or hidden feedback"}
            if member in runnable:
                return value
            self.position += 1
            self.skipped += 1
        return None

    def consume(self, selection):
        if selection["slot_position"] != self.position:
            raise ValueError("Only the previously selected schedule slot can be consumed")
        self.position += 1
        self.executed += 1

    def snapshot(self):
        return {"position": self.position, "executed_opportunities": self.executed,
                "skipped_unavailable_positions": self.skipped, "cycle_length": len(self.slots),
                "organization_id": self.spec["id"], "world_actions_created_by_scheduler": 0}


class OrganizationRuntime(base.OrganizationRuntime):
    def __init__(self, *args, offline_fixture=False, **kwargs):
        if offline_fixture is not True:
            require_evaluation_disabled()
        super().__init__(*args, **kwargs)
        self.offline_fixture = True
        self.fixed_spec = copy.deepcopy(self.prepared.case["fixed_organization"])
        self.schedule = FixedPhaseSchedule(self.fixed_spec)
        self._selected = None

    def sync_members(self):
        registry = base._registry(self.prepared.world)
        if (self.initial_members != list(MEMBERS) or list(registry) != list(MEMBERS)
                or self.labels != list(MEMBERS) or any(row["status"] != "live" for row in registry.values())
                or self.prepared.case["fixed_organization"] != self.fixed_spec):
            raise ValueError("The fixed four-member registry and organization cannot change")

    def select_next(self):
        self.sync_members()
        self._selected = self.schedule.choose(set(self.labels) - set(self.stopped) - set(self.waiting))
        if self._selected is not None:
            self.cursor = self.labels.index(self._selected["member"])
        return copy.deepcopy(self._selected)

    def _step(self):
        if self.offline_fixture is not True:
            require_evaluation_disabled()
        if getattr(self.prepared.world, "fixed_candidates_closed", False):
            raise ValueError("No model opportunity may occur after the unique candidate lock")
        selection = self._selected or self.select_next()
        if selection is None:
            raise ValueError("No fixed member is runnable")
        self._selected = None
        member = selection["member"]
        self.cursor = self.labels.index(member)
        actual_world = self.prepared.world
        actual_world.scheduled_member = member
        actual_world.schedule_observation = copy.deepcopy(selection)
        self.recorder.record("fixed_organization_opportunity", {**selection,
            "team_budget_before": self.team_budget.snapshot()}, worker_id=member)
        try:
            return super()._step()
        finally:
            actual_world.scheduled_member = None
            self.schedule.consume(selection)

    def snapshot(self):
        value = super().snapshot()
        value.update(organization_runtime_version=VERSION,
                     fixed_organization=copy.deepcopy(self.fixed_spec), fixed_schedule=self.schedule.snapshot())
        return value


def worker_config(owner, case, member, *, public_initial_message):
    if member not in MEMBERS or not isinstance(public_initial_message, str) or not public_initial_message.strip():
        raise ValueError("Bind one fixed role and the same public issue/environment guidance")
    value = _config(owner, member, world.member_instruction(case, member) + "\n\n" + public_initial_message,
                    case["role_decision_limits"])
    value.update(backend_id="key_free_fixed_organization_broker_v065", model=owner.adapter.model,
        api_key_env=None, thinking=True, reasoning_effort=None, context_policy="full_history",
        format_error_policy="format_feedback_budgeted_v033", max_output_tokens=aligned.MAX_OUTPUT_TOKENS,
        max_context_tokens=aligned.CONTEXT_LIMIT, timeout_seconds=aligned.REQUEST_SECONDS)
    value["budget"].update(max_decisions=case["team_limits"]["max_decisions"],
        max_http_attempts=case["team_limits"]["max_attempts"],
        max_total_tokens=case["team_limits"]["max_total_tokens"], max_context_bytes=aligned.MAX_RAW_CONTEXT_BYTES)
    return value


def specialize_control_tools(worker):
    descriptions = {
        "staff_wait": "Suspend your current work until a later actual visible event from this fixed team. No message, action, replacement or additional budget is generated.",
        "staff_done": "End your current work in this same fixed-team session. This is not submission or success. A later actual visible event may reopen it without budget reset.",
    }
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


class PublicTestCallback:
    """Bind each accepted test to its real scheduled member and exact version."""
    def __init__(self, callback, *, instance_id, hard_at, folder, clock=time.monotonic):
        if not callable(callback) or not instance_id or hard_at <= clock():
            raise ValueError("Bind an injected public-test callback and a future deadline")
        self.callback, self.instance_id, self.hard_at = callback, instance_id, hard_at
        self.folder, self.clock = Path(folder), clock
        self.world, self.calls = None, 0

    def bind_world(self, prepared):
        if self.world is not None or prepared.case["case_id"] != self.instance_id:
            raise ValueError("Public execution must bind exactly one fresh fixed-team world")
        self.world = prepared.world

    def __call__(self, *, files, entry_metadata, task, run_root):
        if self.world is None or self.clock() >= self.hard_at:
            raise ValueError("The public callback requires its live bounded world")
        actor = getattr(self.world, "_active_public_test_actor", None)
        if actor not in MEMBERS:
            raise ValueError("A real managed run_tests operation must bind the requesting member")
        artifact, version, bundle = self.world._bundle(actor)
        tree = tree_manifest(files, entry_metadata)["tree_sha256"]
        if tree_manifest(bundle["files"], bundle["entry_metadata"])["tree_sha256"] != tree:
            raise ValueError("The public-test payload is not this member's current private tree")
        self.calls += 1
        request = {"version": VERSION, "instance_id": self.instance_id, "actor_id": actor,
            "call_index": self.calls, "source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
            "tree_sha256": tree, "hard_deadline_monotonic": self.hard_at,
            "hidden_evaluation": False, "arbitrary_command": False}
        folder = self.folder / f"test-{self.calls:04d}"
        folder.mkdir(parents=True, exist_ok=False)
        write_new(folder / "request.json", request)
        result = self.callback(files=copy.deepcopy(files), entry_metadata=copy.deepcopy(entry_metadata),
                               request=copy.deepcopy(request))
        write_new(folder / "response.json", result)
        if (not isinstance(result, dict) or not isinstance(result.get("execution"), dict)
                or result["execution"].get("input_tree_sha256") != tree
                or type(result["execution"].get("executed")) is not bool
                or type(result.get("passed")) is not bool or not isinstance(result.get("groups"), dict)
                or (result["passed"] and not result["execution"]["executed"])):
            raise ValueError("Public-test evidence must describe actual execution on this same tree")
        return result


def prepare_case(source_manifest, folder, *, organization_id, max_total_tokens,
                 public_test_callback, deadline, max_decisions=512, max_test_runs=512):
    provider = RepositorySources(source_manifest)
    if len(provider.case_ids) != 1:
        raise ValueError("One fixed organization receives one public repository task")
    callback = PublicTestCallback(public_test_callback, instance_id=provider.case_ids[0],
        hard_at=deadline.hard_at, folder=Path(folder).parent / "public-test-rpc", clock=deadline.clock)
    provider.runner = callback
    prepared = world.build_software_collaboration_case(provider.case_ids[0], folder, provider=provider,
        organization_id=organization_id, max_total_tokens=max_total_tokens,
        max_decisions=max_decisions, max_test_runs=max_test_runs)
    callback.bind_world(prepared)
    return prepared


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None,
                  offline_fixture=False):
    if (offline_fixture is not True or getattr(owner.adapter, "fixture_only", None) is not True
            or getattr(owner.adapter, "external_resources_enabled", None) is not False):
        require_evaluation_disabled()
    world.validate_case(prepared.case, provider=prepared.source_provider)
    if ((deadline.soft_seconds, deadline.hard_seconds) != (aligned.SOFT_SECONDS, aligned.HARD_SECONDS)
            or not isinstance(prepared.source_provider.runner, PublicTestCallback)
            or prepared.source_provider.runner.world is not prepared.world
            or prepared.source_provider.runner.hard_at != deadline.hard_at):
        raise ValueError("All fixed organizations require the aligned shared deadline and real public binding")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = base._StreamRecorder(folder / "experience.jsonl")
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = ManagedTeamBudget(members=list(MEMBERS), team_id=owner.window_id, require_exact_resident=False,
        **{key: prepared.case["team_limits"][key] for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    gate = NativeDispatchGate(owner.transport, deadline)
    context = aligned.ManagedContextTransport(_CollectionOwner(owner, gate), folder / "managed-transport")
    gate.context, context.native_dispatch_gate = context, gate
    facade = _CollectionOwner(owner, context)
    captured, interfaces, holder = {}, {}, {}
    factory = worker_factory or aligned.worker_type()

    def create_member(member, record):
        if member not in MEMBERS or record["origin"] != "initial_fixed_organization":
            raise ValueError("Only the four original sessions may be assembled")
        interface = world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
        interfaces[member] = interface
        rows = base._StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        config = worker_config(owner, prepared.case, member, public_initial_message=public_initial_message)
        port = HarnessPort(capture_port(interface, rows), member, project_id=world.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(member, payload, association))
        worker = factory(member, port.tools(), config, transport=context, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member, context_selection=aligned.SDK_CONTEXT_SELECTION)
        specialize_control_tools(worker)
        return port, worker

    ports, workers = {}, {}
    for member in MEMBERS:
        ports[member], workers[member] = create_member(member, base._registry(prepared.world)[member])
    runtime = OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
        recorder=recorder, member_factory=create_member, deadline=deadline, offline_fixture=True)
    holder["runtime"], gate.runtime = runtime, runtime
    runtime.owner = facade
    runtime.sync_members()
    prepared.world.runtime_availability = runtime.availability
    prepared.world.require_scheduled_actions = True
    if any(e["kind"] in {"model_call", "tool_call"} for e in recorder.events) or before != prepared.world.store.load():
        close_runtime(runtime)
        raise ValueError("Assembly must not sample a model or alter business state")
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in MEMBERS:
        recorder.record("organization_session_born", runtime.birth_records[member], worker_id=member)
    runtime.note_population("initial_fixed_four")
    write_new(folder / "alignment.json", {"version": VERSION, "actual_managed_SDK_harness": True,
        "context_limit": aligned.CONTEXT_LIMIT, "maximum_input_tokens": aligned.MAX_INPUT_TOKENS,
        "maximum_output_tokens": aligned.MAX_OUTPUT_TOKENS, "sdk_context_selection": aligned.SDK_CONTEXT_SELECTION,
        "actual_team_limits": prepared.case["team_limits"], "shared_pool_not_four_personal_budgets": True,
        "fixed_members": list(MEMBERS), "organization": copy.deepcopy(runtime.fixed_spec),
        "model_calls_during_assembly": 0, "hidden_evaluation_accessible": False,
        "unmanaged_bash_added": False, "formal_execution_authorized": False,
        "execution_kind": "explicit_scripted_cpu_fixture", "real_model_calls_authorized": 0,
        "API_calls_authorized": 0, "GPU_operations_authorized": 0,
        "fixture_declarations_are_not_a_security_sandbox": True})
    return runtime, captured, interfaces


def run_fragment(prepared, runtime, *, on_opportunity=None):
    """Exercise the injected harness; this function grants no external resources."""
    if getattr(runtime, "offline_fixture", False) is not True:
        require_evaluation_disabled()
    outcomes, integrity_failure, reason = [], None, None
    deadline = runtime.deadline
    while True:
        deadline.check_hard("fixed_organization_schedule")
        runtime.sync_members()
        budget = runtime.team_budget.snapshot()
        if budget.get("integrity_failure"):
            integrity_failure, reason = budget["integrity_failure"], "execution_integrity_failure"
            break
        if any(budget[key] <= 0 for key in ("remaining_decisions", "remaining_attempts", "available_tokens")):
            reason = "shared_team_pool_exhausted"
            break
        base._wake_reachable(runtime)
        selection = runtime.select_next()
        if selection is None:
            reason = "all_members_stopped_or_no_reachable_event"
            break
        if not deadline.admit_new_work("before_fixed_member_opportunity"):
            reason = "administrative_soft_deadline"
            break
        member, first_event = selection["member"], len(runtime.recorder.events)
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
            reason = status
        elif status == "completed":
            base._sleep(runtime, member, status, result)
        elif fatal or status in TERMINAL - {"completed", "policy_error", "model_format_error"}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = _terminal_detail(member, result, runtime, runtime.recorder.events[first_event:])
            runtime.waiting.pop(member, None)
            runtime.work_ended.pop(member, None)
            if fatal:
                integrity_failure = {"member": member, "status": status, "reason": result.get("reason")}
                reason = "execution_integrity_failure"
        elif status in {"worker_waiting", "world_blocked"}:
            base._sleep(runtime, member, status, result)
        runtime.note_population("fixed_member_opportunity")
        if on_opportunity:
            on_opportunity(result)
        if integrity_failure is not None or status == "administrative_soft_deadline":
            break
    runtime.note_population("fixed_episode_closed")
    boundary = {"version": VERSION, "status": "execution_integrity_blocked" if integrity_failure else "bounded_work_closed",
        "kind": "fixed_four_member_repository_terminal", "organization_id": runtime.fixed_spec["id"],
        "closure_reason": reason, "outcomes": outcomes, "execution_integrity_failure": integrity_failure,
        "opportunities": runtime.opportunities, "actions": runtime.actions,
        "team_budget": base.budget_snapshot(runtime, prepared), "schedule": runtime.schedule.snapshot(),
        "initial_members": list(MEMBERS), "born_members": list(runtime.labels),
        "role_stops": copy.deepcopy(runtime.stopped), "waiting_members": copy.deepcopy(runtime.waiting),
        "current_work_ended": copy.deepcopy(runtime.work_ended), "work_boundaries": copy.deepcopy(runtime.work_boundaries),
        "terminal_details": copy.deepcopy(runtime.terminal_details), "continuation": False,
        "execution_kind": "explicit_scripted_cpu_fixture", "real_model_calls_authorized": 0,
        "scripted_counters_are_not_actual_model_consumption": True,
        "training_eligible": False, "admission_eligible": False,
        "action_error_policy": base.error_policy_summary(runtime),
        "administrative_censoring": deadline.prevented_work, "deadline_receipt": deadline.snapshot(runtime.team_budget)}
    runtime.recorder.record("run_boundary", boundary)
    return boundary


def lock_fixed_candidates(prepared, folder, *, sdk_closed):
    """Lock only member_001's final tree and last legal version, never best of four."""
    from . import software_benchmark_candidates_v054 as candidates
    if sdk_closed is not True:
        raise ValueError("Close every fixed-team SDK conversation before candidate locking")
    actual_world = prepared.world
    root = Path(folder).resolve()
    root.mkdir(parents=True, exist_ok=False)
    with actual_world.store.lock():
        actual_world.state = actual_world.store.load()
        facts = actual_world._software()
        actor = facts["case"]["fixed_organization"]["delivery_member"]
        if actor != "member_001" or facts["case"]["active_roles"] != list(MEMBERS):
            raise ValueError("Candidate closing must retain the genuine four-member organization")
        if any(row["actor_id"] != actor for row in facts["deliveries"]):
            raise ValueError("Another member acquired a forbidden team delivery")
        artifact, version, bundle = actual_world._bundle(actor)
        base_artifact, base_version, baseline = actual_world._bundle(actor, baseline=True)
        policy = copy.deepcopy(facts["case"]["file_policy"])
        candidates._tree(baseline, policy)
        manifest = candidates._tree(bundle, policy)
        prepared.source_provider.validate_files(prepared.case["case_id"], bundle["files"], entry_metadata=bundle["entry_metadata"])
        terminal = {"task_id": prepared.case["case_id"], "baseline": copy.deepcopy(baseline),
            "gitlinks": prepared.source_provider.gitlink_descriptors(prepared.case["case_id"]),
            "candidate": copy.deepcopy(bundle), "policy": policy, "manifest": manifest,
            "binding": {"endpoint": "terminal_code", "actor_id": actor,
                "baseline_reference": {"object_id": base_artifact["artifact_id"], "version_id": base_version},
                "source_reference": {"object_id": artifact["artifact_id"], "version_id": version},
                "source_sha256": digest(json_bytes(bundle)), "files_sha256": digest(json_bytes(bundle["files"])),
                "entry_metadata_sha256": digest(json_bytes(bundle["entry_metadata"])),
                "requires_fixed_patch_or_submission": False, "automatic_submission": False}}
        delivery = candidates._select_last_submission_locked(prepared)
        claim_ref = write_new(Path(actual_world.store.control) / "v065-candidate-close.json", {
            "version": VERSION, "task_id": prepared.case["case_id"], "episode_lock_path": str(root / "lock.json"),
            "fixed_members": list(MEMBERS), "designated_delivery_member": actor,
            "terminal_source_reference": terminal["binding"]["source_reference"],
            "delivery_source_reference": delivery["binding"]["source_reference"] if delivery else None})
        actual_world.fixed_candidates_closed = True
    terminal_root = root / "terminal-code"
    terminal_root.mkdir()
    terminal_ref, terminal_value = candidates._write_selected(terminal_root, terminal, endpoint="terminal_code")
    delivery_ref, identical = None, False
    if delivery is not None:
        delivery_root = root / "last-legal-delivery"
        delivery_root.mkdir()
        identical = all(delivery[key] == terminal[key] for key in ("candidate", "baseline", "policy"))
        delivery_ref, _ = candidates._write_selected(delivery_root, delivery, endpoint="last_legal_submission",
                                                     reuse=terminal_value if identical else None)
    return write_new(root / "lock.json", {"version": candidates.EPISODE_VERSION,
        "organization_closure_version": VERSION, "task_id": prepared.case["case_id"], "close_claim": claim_ref,
        "terminal_code": terminal_ref, "last_legal_delivery": delivery_ref, "submitted": delivery is not None,
        "same_candidate_artifacts": identical,
        "same_tree": manifest["tree_sha256"] == delivery["manifest"]["tree_sha256"] if delivery else None,
        "assessment_reuse": "not_performed", "current_working_tree_substituted_for_delivery": False,
        "same_world_transaction": True, "locked_before_grading": True,
        "model_calls": 0, "public_test_calls": 0, "grading_calls": 0,
        "candidate_selection": "Predeclared member_001 only; other unmerged member trees never selected"})
