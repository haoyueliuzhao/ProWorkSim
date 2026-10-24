"""Bind the repaired managed S1 interface to the existing single-member runtime.

Assembly does not sample a model, execute tests, or grant benchmark admission.
This module does not implement or silently authorize the Verified evaluator.
"""
from __future__ import annotations

from pathlib import Path

from . import software_calibration_collector_v051 as runtime_base
from . import software_benchmark_world_v056 as world_api
from .software_benchmark_managed_worker_v056 import worker_type
from .software_benchmark_public_tests_v056 import PublicTestRunner, bind_public_test_runner
from .experience import capture_port
from .harness_port import HarnessPort

VERSION = "software-benchmark-managed-interface-v0.56"


def managed_port(prepared, *, public_sink=None, world_sink=None, harness_sink=None):
    """Use the real managed gateway, including private history and request IDs."""
    world_api.validate_case(prepared.case, provider=prepared.source_provider)
    member = world_api.MEMBERS[0]
    interface = world_api.SoftwareCollaborationPort(
        prepared.world.session(member, world_api.PROJECT), member)
    def noop(*_args, **_kwargs):
        return None

    return HarnessPort(
        interface, member, project_id=world_api.PROJECT,
        public_sink=public_sink or noop,
        world_sink=world_sink or noop,
        harness_sink=harness_sink or noop)


def build_runtime(owner, prepared, folder, *, deadline=None, worker_factory=None,
                  require_exact_resident=True, public_test_config=None):
    """Assemble one actual SDK worker with v056 tools and the retained budget.

    The caller must separately provide a frozen execution admission before
    advancing this runtime. No model owner, weights, or transport is created.
    """
    world_api.validate_case(prepared.case, provider=prepared.source_provider)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    deadline = deadline or runtime_base.DispatchDeadline()
    if public_test_config is not None:
        if float(public_test_config["hard_at"]) > deadline.hard_at:
            raise ValueError("Public-test IPC cannot extend the managed episode hard deadline")
        bind_public_test_runner(prepared, output=folder / "public-tests-client", **public_test_config)
    callback = prepared.source_provider.runner
    if not isinstance(callback, PublicTestRunner) or callback.client.hard_at > deadline.hard_at:
        raise ValueError("v056 managed execution requires its episode-bound public-test runner")
    worker_factory = worker_factory or worker_type()
    before = prepared.world.store.load()
    recorder = runtime_base._StreamRecorder(folder / "experience.jsonl")
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = runtime_base.SingleMemberBudget(
        members=prepared.case["active_roles"], team_id=owner.window_id,
        require_exact_resident=require_exact_resident,
        **{key: prepared.case["team_limits"][key]
           for key in ("max_decisions", "max_attempts", "max_total_tokens")})
    prepared.world.model_budget_snapshot = budget.snapshot
    captured, interfaces, holder = {}, {}, {}

    def create_member(member, record):
        interface = world_api.SoftwareCollaborationPort(
            prepared.world.session(member, world_api.PROJECT), member)
        interfaces[member] = interface
        rows = runtime_base._StreamList(folder / "public-capture" / (member + ".jsonl"))
        rows.enabled = recorder.enabled
        captured[member] = rows
        task = world_api.member_instruction(prepared.case)
        config = runtime_base._config(
            owner, member, task, {member: prepared.case["team_limits"]["max_decisions"]})
        config.update(context_policy="full_history",
                      format_error_policy="format_feedback_budgeted_v033")
        port = HarnessPort(
            capture_port(interface, rows), member, project_id=world_api.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder["runtime"].record_world_call(
                member, payload, association),
            harness_sink=lambda payload, association: holder["runtime"].record_harness_call(
                member, payload, association))
        worker = worker_factory(
            member, port.tools(), config, transport=owner.transport, team_budget=budget,
            execute=lambda name, arguments, association: holder["runtime"].execute(
                member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder / "sdk-conversations" / member,
            context_selection=runtime_base.SDK_CONTEXT_SELECTION)
        runtime_base.specialize_control_tools(worker)
        return port, worker

    ports, workers = {}, {}
    for member in prepared.case["active_roles"]:
        ports[member], workers[member] = create_member(
            member, runtime_base._registry(prepared.world)[member])
    runtime = runtime_base.OrganizationRuntime(
        ports, workers, prepared=prepared, team_budget=budget, recorder=recorder,
        member_factory=create_member, deadline=deadline)
    holder["runtime"] = runtime
    runtime.owner = owner
    gate = getattr(owner.transport, "native_dispatch_gate", None)
    if gate is not None:
        gate.runtime = runtime
    runtime.sync_members()
    runtime.cursor = runtime.labels.index(prepared.case["first_member"])
    prepared.world.runtime_availability = runtime.availability
    if (any(event["kind"] in {"model_call", "tool_call"} for event in recorder.events)
            or before != prepared.world.store.load()):
        runtime_base.close_runtime(runtime)
        raise ValueError("Managed runtime assembly cannot sample or change world state")
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in runtime.labels:
        recorder.record("organization_session_born", runtime.birth_records[member],
                        worker_id=member)
    runtime.note_population("initial")
    return runtime, captured, interfaces
