"""P0 wiring for the actual managed SDK, preserving v141 solver behavior."""
from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path

from . import software_role_baseline_runtime_v141 as base
from .software_benchmark_deepseek_adapter_v105 import DeepSeekEpisodeAdapter
from .software_benchmark_deepseek_contract_v105 import PreDispatchBudgetStopped
from .software_collaboration_runtime_observer_v156 import RuntimeObservationBridge

VERSION = 'v156-actual-sdk-observation-wiring-r1'
member_wire_tools = base.member_wire_tools
prepare_case = base.prepare_case
worker_config = base.worker_config


def sdk_input_origins(worker, messages):
    """Project event identity by SDK order/merge rules, never search history text.

    Equality below verifies an already position-bound projection. It never chooses
    which source event owns a message. Unknown transformations remain unbound.
    """
    from openhands.sdk.event import LLMConvertibleEvent
    from openhands.sdk.event.llm_convertible import ActionEvent
    from openhands.sdk.llm import Message

    def wire(message):
        return message.to_chat_dict(cache_enabled=False, vision_enabled=False,
            function_calling_enabled=True, force_string_serializer=True, send_reasoning_content=True)

    def plain(message):
        return (message.role == 'user' and message.tool_calls is None
                and message.tool_call_id is None and message.name is None)

    trace = worker._history_trace_v110
    view = worker.conversation.state.view
    events = list(view.events)
    if tuple(e.id for e in events) != trace.current_view_ids:
        raise ValueError('Current SDK view and condenser-observed event order differ')
    groups, index = [], 0
    while index < len(events):
        event = events[index]
        if not isinstance(event, LLMConvertibleEvent):
            raise ValueError('An unconverted SDK event entered the actual LLM view')
        group, index = [event], index+1
        if isinstance(event, ActionEvent):
            while (index < len(events) and isinstance(events[index], ActionEvent)
                   and events[index].llm_response_id == event.llm_response_id):
                group.append(events[index])
                index += 1
        converted = LLMConvertibleEvent.events_to_messages(group)
        if len(converted) != 1:
            raise ValueError('One identified SDK event group changed its conversion shape')
        msg = converted[0]
        origins = [group for _ in msg.content]
        if groups and plain(groups[-1][0]) and plain(msg):
            previous, blocks, whole = groups[-1]
            merged = previous.model_copy(update={'content': list(previous.content)+list(msg.content)})
            groups[-1] = (merged, blocks+origins, whole+group)
        else:
            groups.append((msg, origins, group))
    if len(groups) != len(messages):
        raise ValueError('Unattributed extra SDK message; do not infer its source from text')
    result = []
    for sdk_index, (actual, (projected, blocks, whole)) in enumerate(zip(messages, groups, strict=True)):
        if wire(actual) != wire(projected):
            raise ValueError('Position-bound SDK projection differs from actual completion input')
        split = actual.role == 'user' and len(actual.content) > 1
        parts = [(Message(role='user', content=[block]), blocks[i], i)
                 for i, block in enumerate(actual.content)] if split else [(actual, whole, None)]
        for item, sources, block_index in parts:
            serialized = wire(item)
            calls = serialized.get('tool_calls') or []
            if serialized.get('role') == 'assistant' and len(calls) == 1:
                original = worker._assistant_messages.get(calls[0]['id'])
                if original is None:
                    raise ValueError('Assistant source lacks its original tool-call identity')
                serialized = copy.deepcopy(original)
            event_ids = list(dict.fromkeys(e.id for e in sources))
            unique = {e.id: e for e in sources}
            result.append({'flattened_index': len(result), 'sdk_index': sdk_index, 'block_index': block_index,
                'event_ids': event_ids, 'event_types': [type(unique[e]).__name__ for e in event_ids],
                'events': [unique[e].model_dump(mode='json') for e in event_ids],
                'wire_message': serialized, 'sdk_wire_message': wire(item),
                'tool_call_id': serialized.get('tool_call_id'),
                'source_binding': 'actual_sdk_view_order_and_conversion',
                'content_search_used': False})
    return result


class InputOriginsWorkerMixin:
    def _complete(self, messages, tools):
        self._v156_input_origins = []
        self._v156_input_origin_error = None
        try:
            self._v156_input_origins = sdk_input_origins(self, messages)
        except Exception as error:
            # Observation failure never requests a second model or tool action.
            self._v156_input_origin_error = {'type': type(error).__name__, 'message': str(error)}
        return super()._complete(messages, tools)


@cache
def worker_type():
    class ObservedWorker(InputOriginsWorkerMixin, base.worker_type()):
        pass
    return ObservedWorker


def build_team_owner(post, *, organization_id, slot_id, condition_id, folder, deadline, identity,
                     observation_token_counter=None, observation_tokenizer_id=None,
                     require_content_counter=False, request_capture=None, response_callback=None):
    observation = RuntimeObservationBridge(Path(folder)/'collaboration-observation', team_id=slot_id,
        members=base.organization(organization_id)['fixed_members'], token_counter=observation_token_counter,
        tokenizer_id=observation_tokenizer_id, require_content_counter=require_content_counter,
        explicit_source_presentations=request_capture is not None and response_callback is not None)
    adapters, cash_boundaries, pre_dispatch_boundaries, holder = {}, [], [], {}
    for member in base.organization(organization_id)['fixed_members']:
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
            owner = holder['owner']
            worker = owner._v156_workers.get(member)
            if route == '/chat/completions' and request_capture is not None:
                observation.safely('request_capture', request_capture, member, copy.deepcopy(value), worker, owner)
            try:
                result = post(route, value)
                if route == '/chat/completions':
                    observation.provider_returned(member, value, result)
                    if response_callback is not None:
                        observation.safely('response_capture', response_callback,
                                           member, value, result, worker, owner)
                return result
            except PreDispatchBudgetStopped as error:
                if route == '/chat/completions':
                    boundary = {'member_id': member, 'request_id': value['request_id'],
                        'reason': str(error), 'before_dispatch_proven': True, 'new_provider_request_started': False}
                    pre_dispatch_boundaries.append(boundary)
                    if str(error) == 'group_cash_reservation_insufficient':
                        cash_boundaries.append(copy.deepcopy(boundary))
                    if response_callback is not None:
                        observation.safely('response_capture', response_callback,
                                           member, value, None, worker, owner)
                raise
            except Exception:
                if route == '/chat/completions':
                    observation.provider_uncertain(member, value)
                    if response_callback is not None:
                        observation.safely('response_capture', response_callback,
                                           member, value, None, worker, owner)
                raise

        names = {row['function']['name'] for row in member_wire_tools(organization_id, member)}
        adapters[member] = DeepSeekEpisodeAdapter(post=member_post, arm='PROJECT', slot_id=namespace,
            condition_id=condition_id, token_budget=5_000_000, folder=Path(folder)/member,
            allowed_tool_names=names, soft_at=deadline.soft_at, hard_at=deadline.hard_at)
    owner = base.ProjectOwner(adapters, window_id=slot_id, identity=identity,
        organization_id=organization_id, cash_boundaries=cash_boundaries, folder=folder,
        pre_dispatch_boundaries=pre_dispatch_boundaries)
    owner.observation, owner._v156_workers = observation, {}
    holder['owner'] = owner
    owner.save()
    return owner


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None):
    factory = worker_factory or worker_type()

    def tracked_factory(member, *args, **kwargs):
        worker = factory(member, *args, **kwargs)
        owner._v156_workers[member] = worker
        return worker

    try:
        return base.build_runtime(owner, prepared, folder, deadline=deadline,
            public_initial_message=public_initial_message, worker_factory=tracked_factory)
    except BaseException:
        owner.observation.safely('closure', owner.observation.close_partial, 'runtime_construction_failed')
        raise


def run_fragment(prepared, runtime, *, on_opportunity=None):
    try:
        result = base.run_fragment(prepared, runtime, on_opportunity=on_opportunity)
        runtime._v156_boundary = copy.deepcopy(result)
        if result.get('execution_integrity_failure'):
            runtime.owner.observation.safely('closure', lambda: runtime.owner.observation.close_partial(
                'execution_integrity_failure', evidence={'boundary': result['status']}))
        return result
    except BaseException:
        runtime.owner.observation.safely('closure', runtime.owner.observation.close_partial, 'runtime_exception')
        raise


def close_runtime(runtime, *, abnormal=False):
    try:
        return base.close_runtime(runtime)
    finally:
        if abnormal or getattr(runtime, '_v156_boundary', {}).get('status') != 'bounded_work_closed':
            runtime.owner.observation.safely('closure', runtime.owner.observation.close_partial,
                                             'SDK_closed_without_normal_boundary')


def lock_fixed_candidates(prepared, folder, *, sdk_closed, coverage_evidence=None):
    observer = getattr(prepared.world, 'collaboration_observer_v156', None)
    previous = getattr(prepared.world, 'collaboration_observer_v141', None)
    # Prevent the old generic callback from prematurely closing the new sidecar.
    prepared.world.collaboration_observer_v141 = None
    try:
        result = base.lock_fixed_candidates(prepared, folder, sdk_closed=sdk_closed)
        lock = json.loads(Path(result['path']).read_text())
        code = json.loads(Path(lock['terminal_code']['path']).read_text())
        delivery = (json.loads(Path(lock['last_legal_delivery']['path']).read_text())
                    if lock['last_legal_delivery'] else None)
        if observer is not None:
            observer.safely('closure', lambda: observer.finalize(code['source_reference'],
                delivery['source_reference'] if delivery else None, result,
                completion_status='normal', coverage_evidence=coverage_evidence))
        return result
    except BaseException:
        if observer is not None:
            observer.safely('closure', observer.close_partial, 'candidate_export_failed')
        raise
    finally:
        prepared.world.collaboration_observer_v141 = previous
