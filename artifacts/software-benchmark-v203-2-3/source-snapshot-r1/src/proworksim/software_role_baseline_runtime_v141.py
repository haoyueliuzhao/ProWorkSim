"""Real fixed-team SDK runtime with private sessions and one shared pool.

The runtime accepts a key-free injected broker. Host authorization remains
outside this module; no old implementation-only switch is enabled or mutated.
"""
from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
from types import MethodType, SimpleNamespace

from . import software_calibration_collector_v051 as base
from . import software_role_baseline_world_v141 as world
from .software_benchmark_alignment_contract_v141 import GROUP_IDS, organization, shared_strategy
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter
from .software_benchmark_deepseek_contract_v105 import PreDispatchBudgetStopped
from .software_benchmark_managed_v105 import ProjectOwner as MemberOwner
from .software_benchmark_managed_v064 import CONTEXT_LIMIT, MAX_OUTPUT_TOKENS, MAX_RAW_CONTEXT_BYTES, REQUEST_SECONDS
from .experience import capture_port
from .harness_port import HarnessPort, TOOLS as PRIVATE_TOOLS, EDIT
from .model_policy import CONTROL_TOOLS
from .online_collection import _config
from .software_organization_runtime_v038 import _CollectionOwner
from .software_organization_runtime_v047 import NativeDispatchGate
from .software_runtime_v033 import TECHNICAL_FAILURES, TERMINAL, _terminal_detail
from .storage import atomic_write, digest, json_bytes

VERSION = 'v141-private-role-baseline-observed-runtime-r1'
REPAIR_REVISION = VERSION
prepare_case = world.prepare_case
close_runtime = base.close_runtime
DONE_DESCRIPTION = ('Request completion of your current work, not the whole team. Your first request may '
    'receive one private final self-review within the same shared team budget and deadline. '
    'An accepted request only ends your current work; a later real visible event may wake this same '
    'session without resetting budget or review allowance. This does not test, publish, submit, '
    'approve or create another member automatically.')
WAIT_DESCRIPTION = ('Wait for a later real visible event from this fixed team. No message, work, '
    'new member or extra budget is generated. Your private session and its consumed budget are retained.')


class TeamLedger:
    def __init__(self, adapters, team_slot_id):
        self.adapters, self.team_slot_id = adapters, team_slot_id
        self.token_budget = 5_000_000

    @property
    def calls(self):
        return [{**copy.deepcopy(call), 'member_id': member, 'team_slot_id': self.team_slot_id}
                for member, adapter in self.adapters.items() for call in adapter.ledger.calls]

    @property
    def actual(self):
        return sum(adapter.ledger.actual for adapter in self.adapters.values())

    @property
    def attempts(self):
        return sum(adapter.ledger.attempts for adapter in self.adapters.values())

    @property
    def decisions(self):
        return sum(adapter.ledger.decisions for adapter in self.adapters.values())

    @property
    def inflight(self):
        values = [{**copy.deepcopy(adapter.ledger.inflight), 'member_id': member}
                  for member, adapter in self.adapters.items() if adapter.ledger.inflight is not None]
        if len(values) > 1:
            raise ValueError('One fixed-team writer cannot have multiple simultaneous provider requests')
        return values[0] if values else None

    def snapshot(self):
        inflight = self.inflight
        per_member, per_usage = {}, {}
        for member, adapter in self.adapters.items():
            value = adapter.ledger.snapshot()
            per_member[member] = {key: copy.deepcopy(value[key]) for key in (
                'attempts', 'decisions', 'known_actual_tokens', 'complete_actual_tokens',
                'uncertain_reserved_tokens', 'per_usage_id')}
            for use, counts in value['per_usage_id'].items():
                target = per_usage.setdefault(use, {'prompt_tokens': 0, 'completion_tokens': 0})
                for key in target:
                    target[key] += counts[key]
        return {'version': VERSION, 'attempts': self.attempts, 'decisions': self.decisions,
            'known_actual_tokens': self.actual, 'complete_actual_tokens': self.actual if inflight is None else None,
            'uncertain_reserved_tokens': inflight['reservation'] if inflight else 0,
            'inflight': inflight, 'calls': self.calls, 'per_usage_id': per_usage, 'per_member': per_member,
            'token_limit': self.token_budget, 'all_model_attempt_limit': 512, 'agent_decision_limit': 512,
            'reasoning_tokens_included_in_completion_tokens': True,
            'seed_supported_by_provider': False, 'automatic_retry': False, 'shared_team_pool': True}


class ProjectOwner:
    def __init__(self, adapters, *, window_id, identity, organization_id,
                 cash_boundaries=None, pre_dispatch_boundaries=None, folder=None):
        self.spec = organization(organization_id)
        if list(adapters) != self.spec['fixed_members'] or not identity.get('policy_version'):
            raise ValueError('Bind exactly the fixed organization member adapters')
        if any(adapter.slot_id != window_id+':'+member for member, adapter in adapters.items()):
            raise ValueError('Each private adapter requires its team/member request namespace')
        self.adapters, self.window_id, self.identity = adapters, window_id, copy.deepcopy(identity)
        self.member_owners = {member: MemberOwner(adapter, window_id=window_id, identity=identity)
                              for member, adapter in adapters.items()}
        first = next(iter(adapters.values()))
        self.adapter = SimpleNamespace(model=first.model, thinking=False,
            limits=copy.deepcopy(first.limits), maximum_input_tokens=first.maximum_input_tokens,
            maximum_output_tokens=first.maximum_output_tokens, ledger=TeamLedger(adapters, window_id))
        self.recipe = copy.deepcopy(next(iter(self.member_owners.values())).recipe)
        self.cash_boundaries = cash_boundaries if cash_boundaries is not None else []
        self.pre_dispatch_boundaries = pre_dispatch_boundaries if pre_dispatch_boundaries is not None else []
        self.folder = Path(folder) if folder is not None else None
        self.transport = None

    def freeze_identity(self):
        return copy.deepcopy(self.identity)

    def save(self):
        value = {'version': VERSION, 'slot_id': self.window_id,
            'organization_id': self.spec['id'], 'group_id': self.spec['id'],
            'model': self.adapter.model, 'thinking': False,
            'halted': next((adapter.halted for adapter in self.adapters.values() if adapter.halted), None),
            'member_halts': {member: adapter.halted for member, adapter in self.adapters.items()},
            'cash_censored': bool(self.cash_boundaries), **self.adapter.ledger.snapshot()}
        if self.folder is not None:
            atomic_write(self.folder/'ledger.json', json_bytes(value))
        return value


def build_team_owner(post, *, organization_id, slot_id, condition_id, folder, deadline, identity,
                     observation_token_counter=None, observation_tokenizer_id=None,
                     require_content_counter=False):
    from .software_collaboration_runtime_observer_v141 import RuntimeObservationBridge
    observation = RuntimeObservationBridge(Path(folder)/'collaboration-observation', team_id=slot_id,
        members=organization(organization_id)['fixed_members'], token_counter=observation_token_counter,
        tokenizer_id=observation_tokenizer_id, require_content_counter=require_content_counter)
    adapters, cash_boundaries, pre_dispatch_boundaries = {}, [], []
    for member in organization(organization_id)['fixed_members']:
        namespace = slot_id+':'+member
        def member_post(route, payload, *, member=member, namespace=namespace):
            value = copy.deepcopy(payload)
            if route == '/chat/completions':
                if value.get('slot_id') != namespace or not value.get('request_id', '').startswith(namespace+':'):
                    raise ValueError('A member cannot issue another session request')
                value['slot_id'] = slot_id
            elif route not in {'/tokenize', '/tokenize-prefix'}:
                raise ValueError('No unplanned broker route exists')
            value.update(member_id=member, team_slot_id=slot_id)
            try:
                result = post(route, value)
                if route == '/chat/completions':
                    observation.safely('provider', observation.provider_returned, member, value, result)
                return result
            except PreDispatchBudgetStopped as error:
                if route == '/chat/completions':
                    boundary = {'member_id': member, 'request_id': value['request_id'],
                        'reason': str(error), 'before_dispatch_proven': True,
                        'new_provider_request_started': False}
                    pre_dispatch_boundaries.append(boundary)
                    if str(error) == 'group_cash_reservation_insufficient':
                        cash_boundaries.append(copy.deepcopy(boundary))
                raise
            except Exception:
                if route == '/chat/completions':
                    observation.safely('provider', observation.provider_uncertain, member, value)
                raise
        names = {row['function']['name'] for row in member_wire_tools(organization_id, member)}
        adapters[member] = DeepSeekEpisodeAdapter(post=member_post, arm='PROJECT',
            slot_id=namespace, condition_id=condition_id, token_budget=5_000_000,
            folder=Path(folder)/member, allowed_tool_names=names,
            soft_at=deadline.soft_at, hard_at=deadline.hard_at)
    owner = ProjectOwner(adapters, window_id=slot_id, identity=identity,
        organization_id=organization_id, cash_boundaries=cash_boundaries, folder=folder)
    owner.pre_dispatch_boundaries = pre_dispatch_boundaries
    owner.observation = observation
    owner.save()
    return owner


def _specialize_definitions(definitions):
    for item in definitions:
        if item['name'] == 'staff_done':
            item['description'] = DONE_DESCRIPTION
        elif item['name'] == 'staff_wait':
            item['description'] = WAIT_DESCRIPTION
    return definitions


def specialize_worker_controls(worker):
    _specialize_definitions(worker.definitions)
    from openhands.sdk.tool import register_tool, resolve_tool
    descriptions = {'staff_done': DONE_DESCRIPTION, 'staff_wait': WAIT_DESCRIPTION}
    for specification in worker.agent.tools:
        for tool in resolve_tool(specification, worker.conversation.state):
            if tool.name in descriptions:
                register_tool(specification.name, tool.model_copy(update={'description': descriptions[tool.name]}))
    # The nullable bridge has already populated this private agent cache.
    # Keep the actual SDK objects consistent with the registered declarations.
    with worker.agent._tools_lock:
        tools = dict(worker.agent._tools)
        for name, description in descriptions.items():
            tools[name] = tools[name].model_copy(update={'description': description})
        object.__setattr__(worker.agent, '_tools', tools)


def member_wire_tools(group, member):
    case = world.schema_case(group)
    if member not in case['active_roles']:
        raise ValueError('Unknown member for this organization')
    base_tools = world.tool_definitions(case)
    additions = [tool for tool in PRIVATE_TOOLS if tool['name'] != EDIT
                 or any(row['name'] == 'write_object' for row in base_tools)]
    definitions = _specialize_definitions(copy.deepcopy(base_tools+additions+list(CONTROL_TOOLS)))
    return [{'type': 'function', 'function': tool} for tool in definitions]


def prepare_schema_inventory():
    return {'version': VERSION, 'schemas': {group: {member: member_wire_tools(group, member)
        for member in organization(group)['fixed_members']} for group in GROUP_IDS},
        'generation_calls': 0, 'schemas_are_declared_before_first_generation': True,
        'condenser_tools': [], 'one_member_action_per_opportunity': True,
        'role_authority_enforced_by_world_not_tool_name_presence': True}


@cache
def worker_type():
    from .software_benchmark_history_v117 import history_worker_type
    from .software_benchmark_review_runtime_v117 import FinishReviewWorkerMixin
    from .software_benchmark_tooling_v130 import ToolFeedbackWorkerMixin
    class FixedTeamWorker(ToolFeedbackWorkerMixin, FinishReviewWorkerMixin, history_worker_type()):
        pass
    return FixedTeamWorker


def worker_config(owner, case, member, *, public_initial_message):
    value = _config(owner, member, world.member_instruction(case, member)+'\n\n'+public_initial_message,
                    case['role_decision_limits'])
    value.update(backend_id='key_free_role_baseline_broker_v141', model=owner.adapter.model,
        api_key_env=None, thinking=False, reasoning_effort=None, temperature=1.0,
        context_policy='full_history', format_error_policy='format_feedback_budgeted_v033',
        max_output_tokens=MAX_OUTPUT_TOKENS, max_context_tokens=CONTEXT_LIMIT, timeout_seconds=REQUEST_SECONDS)
    value['budget'].update(max_decisions=512, max_http_attempts=512, max_total_tokens=5_000_000,
                           max_context_bytes=MAX_RAW_CONTEXT_BYTES)
    return value


class OrganizationSchedule:
    def __init__(self, spec):
        if spec != organization(spec['id']):
            raise ValueError('The fixed organization changed')
        self.spec, self.members = copy.deepcopy(spec), tuple(spec['fixed_members'])
        self.position = self.executed = self.skipped = 0

    def choose(self, runnable):
        runnable = set(runnable)
        if not runnable <= set(self.members):
            raise ValueError('No replacement member may enter the schedule')
        for _ in self.members:
            member = self.members[self.position % len(self.members)]
            if member in runnable:
                return {'organization_id': self.spec['id'], 'member': member,
                    'slot_position': self.position, 'cycle': self.position // len(self.members),
                    'selection_basis': 'persisted organization eligibility then fair round-robin'}
            self.position += 1
            self.skipped += 1
        return None

    def consume(self, selection):
        if selection['slot_position'] != self.position:
            raise ValueError('Consume only the actual selected member opportunity')
        self.position += 1
        self.executed += 1

    def snapshot(self):
        return {'organization_id': self.spec['id'], 'position': self.position,
            'executed_opportunities': self.executed, 'skipped_unavailable_positions': self.skipped,
            'cycle_length': len(self.members), 'world_actions_created_by_scheduler': 0}


class OrganizationRuntime(base.OrganizationRuntime):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_spec = copy.deepcopy(self.prepared.case['fixed_organization'])
        self.members = tuple(self.fixed_spec['fixed_members'])
        self.schedule = OrganizationSchedule(self.fixed_spec)
        self._selected, self.organization_blocked = None, False

    def sync_members(self):
        registry = base._registry(self.prepared.world)
        if (self.initial_members != list(self.members) or list(registry) != list(self.members)
                or self.labels != list(self.members) or any(row['status'] != 'live' for row in registry.values())
                or self.prepared.case['fixed_organization'] != self.fixed_spec):
            raise ValueError('The fixed original member registry cannot change')

    def select_next(self):
        self.sync_members()
        runnable = set(self.labels)-set(self.stopped)-set(self.waiting)
        eligible = set(self.prepared.world.organization_active_members())
        self.organization_blocked = bool(runnable) and not (runnable & eligible)
        self._selected = self.schedule.choose(runnable & eligible)
        if self._selected:
            self.cursor = self.labels.index(self._selected['member'])
        return copy.deepcopy(self._selected)

    def _step(self):
        actual = self.prepared.world
        if getattr(actual, 'fixed_candidates_closed', False):
            raise ValueError('No member may act after final candidates lock')
        selected = self._selected or self.select_next()
        if selected is None or selected['member'] not in actual.organization_active_members():
            raise ValueError('No current organization-eligible member opportunity')
        self._selected = None
        member = selected['member']
        self.cursor = self.labels.index(member)
        actual.scheduled_member, actual.schedule_observation = member, copy.deepcopy(selected)
        before = self.opportunities
        self.recorder.record('fixed_organization_opportunity', {**selected,
            'version': VERSION, 'team_budget_before': self.team_budget.snapshot()}, worker_id=member)
        try:
            return base.OrganizationRuntime._step(self)
        finally:
            try:
                if self.opportunities > before:
                    if self.opportunities != before+1:
                        raise ValueError('Only one real opportunity may be consumed')
                    changed = actual.consume_organization_opportunity(actor=member)
                    self.recorder.record('organization_opportunity_consumed', {'version': VERSION,
                        'member_id': member, 'organization_state_transition': changed}, worker_id=member)
                    self.schedule.consume(selected)
            finally:
                actual.scheduled_member = None

    def snapshot(self):
        result = super().snapshot()
        result.update(organization_runtime_version=VERSION, fixed_organization=copy.deepcopy(self.fixed_spec),
            fixed_schedule=self.schedule.snapshot(), organization_contract_blocked=self.organization_blocked)
        return result


def decorate_reviews(runtime, owner, deadline):
    from .software_benchmark_finish_review_v117 import FinishReviewPolicy, require_known_usage
    from .software_benchmark_review_runtime_v117 import ORIGINAL_HARNESS_VERSION
    runtime.finish_review_policies = {}
    started = {key: getattr(deadline, key) for key in ('started', 'soft_at', 'hard_at')}
    limits = {'agent_decisions': 512, 'all_model_attempts': 512, 'input_plus_output_tokens': 5_000_000,
        'output_limit': MAX_OUTPUT_TOKENS, 'soft_seconds': 21600, 'hard_seconds': 23400}
    for member, worker in runtime.policies.items():
        policy = FinishReviewPolicy(started=started, limits=limits, clock=deadline.clock,
            event_sink=lambda event, member=member: runtime.recorder.record('member_finish_review', event, worker_id=member))
        runtime.finish_review_policies[member] = policy
        worker._v117_original_harness_version = ORIGINAL_HARNESS_VERSION
        worker._v117_finish_review_policy = policy
        worker._v117_finish_review_adapter = owner.adapter
        worker._v117_pending_finish_review = None
        specialize_worker_controls(worker)
    original_execute = runtime.execute
    def execute(self, label, name, arguments, association):
        if name != 'staff_done':
            return original_execute(label, name, arguments, association)
        self.deadline.check_hard('settle_returned_legal_action')
        self._check_active(label, association)
        worker, policy = self.policies[label], self.finish_review_policies[label]
        if (label not in owner.adapters or label in self.stopped or label in self.waiting
                or label in self.work_ended or self._active['executed'] or worker._done is not None
                or worker._v117_pending_finish_review is not None or set(arguments) != {'reason'}
                or not isinstance(arguments['reason'], str) or not arguments['reason']):
            raise RuntimeError('Only a live scheduled member may request its private review')
        team, provider = self.team_budget.snapshot(), owner.adapter.ledger.snapshot()
        require_known_usage(provider)
        if team.get('integrity_failure'):
            raise RuntimeError('Review cannot hide shared accounting uncertainty')
        if any(team[key] <= 0 for key in ('remaining_decisions', 'remaining_attempts', 'available_tokens')):
            return original_execute(label, name, arguments, association)
        intent = association['model_call_id']+':'+association['model_tool_call_id']
        offered = policy.offer(provider, intent_id=intent, reason=arguments['reason'])
        if not offered['permitted']:
            return original_execute(label, name, arguments, association)
        worker._v117_pending_finish_review = {'intent_id': intent,
            'model_call_id': association['model_call_id'], 'model_tool_call_id': association['model_tool_call_id'],
            'reason': arguments['reason'], 'review_index': offered['review_index']}
        interpreted = {'kind': 'act', 'requested_control_kind': 'done', 'action': name,
            'arguments': copy.deepcopy(arguments), **self._association(association)}
        response = {'ok': True, 'worker_state': 'finish_review_pending', 'reason': arguments['reason'],
            'world_effect': False, 'accepted_finish': False, 'review_index': offered['review_index'],
            'policy_version': VERSION, 'message_follows': True, 'team_finished': False}
        self._active['executed'] = True
        self.recorder.record('policy_decision', {'decision': interpreted,
            'memory_before_sha256': digest(json_bytes(self.roles[label]['memory'])), 'harness': VERSION}, worker_id=label)
        self.record_harness_call(label, {'action': name, 'arguments': arguments,
            'response': response, 'request_key': None}, association)
        self.roles[label]['last_action'] = {'action': name, 'arguments': copy.deepcopy(arguments)}
        self.roles[label]['last_result'] = copy.deepcopy(response)
        self._active.update(decision=interpreted, response=copy.deepcopy(response))
        return response
    runtime.execute = MethodType(execute, runtime)


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None):
    from .software_benchmark_history_v117 import AlignedManagedTeamBudget, SummarizingManagedContextTransport
    from .software_benchmark_rejected_history_v117 import bind_project_worker
    from .harness_sdk import SYSTEM
    world.validate_case(prepared.case, provider=prepared.source_provider)
    members = list(prepared.case['active_roles'])
    if (not isinstance(owner, ProjectOwner) or list(owner.adapters) != members
            or prepared.source_provider.runner.world is not prepared.world
            or prepared.source_provider.runner.hard_at != deadline.hard_at):
        raise ValueError('Bind the same fixed roster, shared deadline and public callback')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    before = prepared.world.store.load()
    recorder = base._StreamRecorder(folder/'experience.jsonl')
    deadline.sink = lambda kind, value: recorder.record(kind, value)
    budget = AlignedManagedTeamBudget(members=members, team_id=owner.window_id, require_exact_resident=False,
        **{key: prepared.case['team_limits'][key] for key in ('max_decisions', 'max_attempts', 'max_total_tokens')})
    prepared.world.model_budget_snapshot = budget.snapshot
    captured, interfaces, holder, gates = {}, {}, {}, {}
    factory = worker_factory or worker_type()
    system = SYSTEM.replace('staff_done(reason) to stop your own work',
                            'staff_done(reason) to request completion of your current work')
    def create_member(member, record):
        if member not in members or record['origin'] != 'initial_fixed_organization':
            raise ValueError('Only the original fixed private sessions may be created')
        own = owner.member_owners[member]
        gate = NativeDispatchGate(own.transport, deadline)
        context = SummarizingManagedContextTransport(_CollectionOwner(own, gate), folder/'managed-transport'/member)
        gate.context, context.native_dispatch_gate = context, gate
        gates[member] = gate
        interface = world.SoftwareCollaborationPort(prepared.world.session(member, world.PROJECT), member)
        interfaces[member] = interface
        captured[member] = base._StreamList(folder/'public-capture'/(member+'.jsonl'))
        captured[member].enabled = recorder.enabled
        port = HarnessPort(capture_port(interface, captured[member]), member, project_id=world.PROJECT,
            public_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            world_sink=lambda payload, association: holder['runtime'].record_world_call(member, payload, association),
            harness_sink=lambda payload, association: holder['runtime'].record_harness_call(member, payload, association))
        config = worker_config(own, prepared.case, member, public_initial_message=public_initial_message)
        worker = factory(member, port.tools(), config, transport=context, team_budget=budget,
            execute=lambda name, arguments, association: holder['runtime'].execute(member, name, arguments, association),
            event_sink=lambda kind, value: recorder.record(kind, value, worker_id=member),
            directory=folder/'sdk-conversations'/member, context_selection='full_history', system_prompt=system)
        bind_project_worker(worker)
        _specialize_definitions(worker.definitions)
        expected = member_wire_tools(owner.spec['id'], member)
        if [{'type': 'function', 'function': row} for row in worker.definitions] != expected:
            worker.close()
            raise ValueError('Actual SDK declarations differ from the predeclared member schema')
        return port, worker
    ports, workers = {}, {}
    for member in members:
        ports[member], workers[member] = create_member(member, base._registry(prepared.world)[member])
    runtime = OrganizationRuntime(ports, workers, prepared=prepared, team_budget=budget,
        recorder=recorder, member_factory=create_member, deadline=deadline)
    holder['runtime'], runtime.owner = runtime, owner
    for gate in gates.values():
        gate.runtime = runtime
    runtime.sync_members()
    prepared.world.runtime_availability = runtime.availability
    prepared.world.require_scheduled_actions = True
    decorate_reviews(runtime, owner, deadline)
    owner.observation.bind(runtime)
    if before != prepared.world.store.load() or owner.adapter.ledger.attempts:
        close_runtime(runtime)
        raise ValueError('Assembly may not change business state or call the model')
    recorder.events.clear()
    recorder.enabled = True
    for values in captured.values():
        values.clear()
        values.enabled = True
    for member in members:
        recorder.record('organization_session_born', runtime.birth_records[member], worker_id=member)
    runtime.note_population('initial_fixed_roster')
    write_new(folder/'alignment.json', {'version': VERSION, 'shared_strategy': shared_strategy(owner.spec['id']),
        'fixed_members': members, 'private_contexts_and_adapters': True,
        'team_limits': prepared.case['team_limits'], 'shared_pool_not_per_member_copies': True,
        'model_calls_during_assembly': 0, 'old_offline_runtime_switch_used': False})
    return runtime, captured, interfaces


def run_fragment(prepared, runtime, *, on_opportunity=None):
    outcomes, integrity_failure, reason = [], None, None
    deadline = runtime.deadline
    while True:
        deadline.check_hard('v141_organization_schedule')
        runtime.sync_members()
        budget = runtime.team_budget.snapshot()
        if budget.get('integrity_failure'):
            integrity_failure, reason = budget['integrity_failure'], 'execution_integrity_failure'
            break
        if runtime.owner.cash_boundaries:
            reason = 'cash_budget_exhausted_before_dispatch'
            break
        if runtime.owner.pre_dispatch_boundaries:
            last = runtime.owner.pre_dispatch_boundaries[-1]
            if last['reason'] == 'shared_team_limit_before_dispatch':
                reason = 'shared_team_pool_exhausted_before_dispatch'
            else:
                reason = 'team_transport_boundary'
                integrity_failure = {'scope': 'this_team', 'kind': 'pre_dispatch_transport_stop',
                    'reason': last['reason'], 'before_dispatch_proven': True}
            break
        if any(budget[key] <= 0 for key in ('remaining_decisions', 'remaining_attempts', 'available_tokens')):
            reason = 'shared_team_pool_exhausted'
            break
        base._wake_reachable(runtime)
        selection = runtime.select_next()
        if selection is None:
            reason = 'organization_contract_blocked' if runtime.organization_blocked else 'all_members_stopped_or_no_reachable_event'
            break
        if not deadline.admit_new_work('before_fixed_member_opportunity'):
            reason = 'administrative_soft_deadline'
            break
        member, first_event = selection['member'], len(runtime.recorder.events)
        outcome = runtime.step()
        status = outcome['status']
        outcomes.append(outcome)
        runtime.owner.save()
        fatal = status in TECHNICAL_FAILURES and not (status == 'policy_error' and outcome.get('action_performed'))
        if status == 'completed':
            base._sleep(runtime, member, status, outcome)
        elif fatal or status in TERMINAL - {'completed', 'policy_error', 'model_format_error'}:
            runtime.stopped[member] = status
            runtime.terminal_details[member] = _terminal_detail(member, outcome, runtime, runtime.recorder.events[first_event:])
            runtime.waiting.pop(member, None)
            runtime.work_ended.pop(member, None)
            if fatal:
                integrity_failure, reason = {'member': member, 'status': status, 'reason': outcome.get('reason')}, 'execution_integrity_failure'
        elif status in {'worker_waiting', 'world_blocked'}:
            base._sleep(runtime, member, status, outcome)
        runtime.note_population('v141_member_opportunity')
        if on_opportunity:
            on_opportunity(outcome)
        if integrity_failure is not None or status == 'administrative_soft_deadline':
            reason = reason or status
            break
    boundary = {'version': VERSION, 'status': 'execution_integrity_blocked' if integrity_failure else 'bounded_work_closed',
        'kind': 'fixed_roster_repository_terminal', 'organization_id': runtime.fixed_spec['id'],
        'group_id': runtime.fixed_spec['id'], 'closure_reason': reason, 'outcomes': outcomes,
        'execution_integrity_failure': integrity_failure, 'opportunities': runtime.opportunities,
        'actions': runtime.actions, 'team_budget': base.budget_snapshot(runtime, prepared),
        'schedule': runtime.schedule.snapshot(), 'initial_members': list(runtime.members),
        'born_members': list(runtime.labels), 'role_stops': copy.deepcopy(runtime.stopped),
        'waiting_members': copy.deepcopy(runtime.waiting), 'current_work_ended': copy.deepcopy(runtime.work_ended),
        'work_boundaries': copy.deepcopy(runtime.work_boundaries), 'terminal_details': copy.deepcopy(runtime.terminal_details),
        'continuation': False, 'training_eligible': False, 'admission_eligible': False,
        'action_error_policy': base.error_policy_summary(runtime),
        'administrative_censoring': deadline.prevented_work, 'deadline_receipt': deadline.snapshot(runtime.team_budget),
        'cash_censored': bool(runtime.owner.cash_boundaries), 'cash_boundaries': copy.deepcopy(runtime.owner.cash_boundaries),
        'pre_dispatch_boundaries': copy.deepcopy(runtime.owner.pre_dispatch_boundaries),
        'member_usage': runtime.owner.adapter.ledger.snapshot()['per_member'],
        'finish_reviews': {member: policy.snapshot() for member, policy in runtime.finish_review_policies.items()}}
    runtime.recorder.record('run_boundary', boundary)
    return boundary


def validate_organization(spec):
    if spec != organization(spec["id"]):
        raise ValueError("The fixed organization changed")
    return copy.deepcopy(spec)


def lock_fixed_candidates(prepared, folder, *, sdk_closed):
    """Lock only member_001's final tree and last legal version, never best of the members."""
    from . import software_benchmark_candidates_v054 as candidates
    if sdk_closed is not True:
        raise ValueError("Close every fixed-team SDK conversation before candidate locking")
    actual_world = prepared.world
    root = Path(folder).resolve()
    root.mkdir(parents=True, exist_ok=False)
    with actual_world.store.lock():
        actual_world.state = actual_world.store.load()
        facts = actual_world._software()
        spec = validate_organization(facts["case"]["fixed_organization"])
        members = tuple(spec["fixed_members"])
        actor = spec["delivery_member"]
        if actor != "member_001" or facts["case"]["active_roles"] != list(members):
            raise ValueError("Candidate closing must retain the genuine configured-member organization")
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
        claim_ref = write_new(Path(actual_world.store.control) / "v141-candidate-close.json", {
            "version": VERSION, "task_id": prepared.case["case_id"], "episode_lock_path": str(root / "lock.json"),
            "fixed_members": list(members), "designated_delivery_member": actor,
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
    locked = write_new(root / "lock.json", {"version": candidates.EPISODE_VERSION,
        "organization_closure_version": VERSION, "task_id": prepared.case["case_id"], "close_claim": claim_ref,
        "terminal_code": terminal_ref, "last_legal_delivery": delivery_ref, "submitted": delivery is not None,
        "same_candidate_artifacts": identical,
        "same_tree": manifest["tree_sha256"] == delivery["manifest"]["tree_sha256"] if delivery else None,
        "assessment_reuse": "not_performed", "current_working_tree_substituted_for_delivery": False,
        "same_world_transaction": True, "locked_before_grading": True,
        "model_calls": 0, "public_test_calls": 0, "grading_calls": 0,
        "candidate_selection": "Predeclared member_001 only; other unmerged member trees never selected"})
    observer = getattr(actual_world, 'collaboration_observer_v141', None)
    if observer is not None:
        observer.safely('closure', observer.finalize, terminal['binding']['source_reference'],
            delivery['binding']['source_reference'] if delivery else None, locked)
    return locked
