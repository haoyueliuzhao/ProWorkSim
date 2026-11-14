"""New explicit S1 assembly for shared review, history and public-test selection.

This factory constructs only injected, key-free runtime objects. It does not
authorize a benchmark batch or start any model, container or public test.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path

from . import software_benchmark_managed_v105 as previous
from . import software_benchmark_managed_v064 as established
from . import software_benchmark_tooling_v130 as world
from .software_benchmark_alignment_contract_v130 import shared_strategy
from .software_benchmark_candidates_v054 import write_new
from .storage import digest

REPAIR_REVISION = 'v130-managed-schema-and-test-evidence-r1'
ProjectOwner = previous.ProjectOwner
prepare_case = world.prepare_case


def member_instruction(case):
    from .software_benchmark_finish_review_v117 import DONE_DESCRIPTION
    source = world.member_instruction(case)
    old = ('staff_done ends current work without creating '
           'a submission, partner or extra budget.')
    if source.count(old) != 1:
        raise ValueError('The inherited completion description changed; review the new member contract')
    return source.replace(old, DONE_DESCRIPTION)


def worker_config(owner, case, *, public_initial_message):
    config = previous.worker_config(owner, case, public_initial_message=public_initial_message)
    config.update(backend_id='key_free_aligned_broker_v130',
                  task=member_instruction(case) + '\n\n' + public_initial_message)
    return config


@cache
def worker_type():
    from .software_benchmark_history_v117 import history_worker_type
    from .software_benchmark_review_runtime_v117 import FinishReviewWorkerMixin

    from .software_benchmark_tooling_v130 import ToolFeedbackWorkerMixin

    class AlignedManagedWorker(ToolFeedbackWorkerMixin, FinishReviewWorkerMixin, history_worker_type()):
        pass
    return AlignedManagedWorker


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None):
    from . import software_calibration_collector_v051 as collector
    from .experience import capture_port
    from .harness_port import HarnessPort
    from .harness_sdk import SYSTEM
    from .software_organization_runtime_v038 import _CollectionOwner
    from .software_organization_runtime_v047 import NativeDispatchGate
    from .software_benchmark_history_v117 import (
        AlignedManagedTeamBudget, SummarizingManagedContextTransport,
    )
    from .software_benchmark_review_runtime_v117 import decorate_runtime

    world.validate_case(prepared.case, provider=prepared.source_provider)
    if ((deadline.soft_seconds, deadline.hard_seconds) != (established.SOFT_SECONDS, established.HARD_SECONDS)
            or not isinstance(prepared.source_provider.runner, world.PublicTestCallback)
            or prepared.source_provider.runner.world is not prepared.world
            or prepared.source_provider.runner.hard_at != deadline.hard_at):
        raise ValueError('Bind the selected public runner and original episode deadlines')
    if owner.adapter.ledger.token_budget != prepared.case['team_limits']['max_total_tokens']:
        raise ValueError('Agent, summaries and managed operations must share the same token allowance')
    old = 'Use staff_wait(reason) to yield or staff_done(reason) to stop your own work; neither'
    if SYSTEM.count(old) != 1:
        raise ValueError('The managed system completion instruction changed')
    system = SYSTEM.replace(old,
        'Use staff_wait(reason) to yield or staff_done(reason) to request completion; neither')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = collector._StreamRecorder(folder/'experience.jsonl')
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = AlignedManagedTeamBudget(members=prepared.case['active_roles'], team_id=owner.window_id,
        require_exact_resident=False, **{key: prepared.case['team_limits'][key]
        for key in ('max_decisions', 'max_attempts', 'max_total_tokens')})
    prepared.world.model_budget_snapshot = budget.snapshot
    gate = NativeDispatchGate(owner.transport, deadline)
    context = SummarizingManagedContextTransport(_CollectionOwner(owner, gate), folder/'managed-transport')
    gate.context, context.native_dispatch_gate = context, gate
    facade = _CollectionOwner(owner, context)
    captured, interfaces, holder = {}, {}, {}
    factory = worker_factory or worker_type()

    def create_member(member, record):
        interface = world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
        interfaces[member] = interface
        rows = collector._StreamList(folder/'public-capture'/(member+'.jsonl'))
        rows.enabled = recorder.enabled
        captured[member] = rows
        config = worker_config(owner, prepared.case, public_initial_message=public_initial_message)
        port = HarnessPort(capture_port(interface, rows), member, project_id=world.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder['runtime'].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder['runtime'].record_harness_call(member, payload, association))
        worker = factory(member, port.tools(), config, transport=context, team_budget=budget,
            execute=lambda name, arguments, association: holder['runtime'].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder/'sdk-conversations'/member, context_selection='full_history', system_prompt=system)
        from .software_benchmark_rejected_history_v117 import bind_project_worker
        bind_project_worker(worker)
        collector.specialize_control_tools(worker)
        return port, worker

    ports, workers = {}, {}
    for member in prepared.case['active_roles']:
        ports[member], workers[member] = create_member(member, collector._registry(prepared.world)[member])
    runtime = collector.OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
        recorder=recorder, member_factory=create_member, deadline=deadline)
    holder['runtime'], gate.runtime = runtime, runtime
    runtime.owner = facade
    runtime.sync_members()
    runtime.cursor = runtime.labels.index(prepared.case['first_member'])
    prepared.world.runtime_availability = runtime.availability
    started = {key: getattr(deadline, key) for key in ('started', 'soft_at', 'hard_at')}
    limits = {'agent_decisions': established.ATTEMPT_LIMIT,
              'all_model_attempts': established.ATTEMPT_LIMIT,
              'input_plus_output_tokens': prepared.case['team_limits']['max_total_tokens'],
              'output_limit': established.MAX_OUTPUT_TOKENS,
              'soft_seconds': established.SOFT_SECONDS, 'hard_seconds': established.HARD_SECONDS}
    decorate_runtime(runtime, adapter=owner.adapter, started=started, limits=limits, clock=deadline.clock)
    if any(event['kind'] in {'model_call', 'tool_call'} for event in recorder.events) or before != prepared.world.store.load():
        collector.close_runtime(runtime)
        raise ValueError('Aligned assembly may not call a model or change the world')
    recorder.events.clear()
    recorder.enabled = True
    for rows in captured.values():
        rows.clear()
        rows.enabled = True
    for member in runtime.labels:
        recorder.record('organization_session_born', runtime.birth_records[member], worker_id=member)
    runtime.note_population('initial')
    write_new(folder/'alignment.json', {
        'version': REPAIR_REVISION, 'shared_strategy': shared_strategy(),
        'actual_managed_S1_runtime': True, 'actual_team_limits': prepared.case['team_limits'],
        'public_initial_message_sha256': digest(public_initial_message.encode()),
        'sdk_run_iteration_limit_per_managed_opportunity': established.ATTEMPT_LIMIT,
        'maximum_agent_actions_per_opportunity': 1,
        'summaries_count_as_attempts_and_tokens': True, 'summaries_count_as_agent_decisions': False,
        'automatic_submission': False, 'unmanaged_bash_added': False,
        'hidden_evaluation_accessible': False, 'model_calls_during_assembly': 0})
    return runtime, captured, interfaces
