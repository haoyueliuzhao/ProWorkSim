"""Communication Pilot runtime over the unchanged REVIEW2 SDK/action scheduler.

Bindings are per instance/function-copy: old running modules and world types are
not mutated. All three arms expose the same read layers and native tool schema.
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import FunctionType, MethodType, SimpleNamespace

from . import software_role_baseline_runtime_v141 as original
from . import software_role_baseline_runtime_v156 as observed
from . import software_role_baseline_world_v141 as world
from .software_communication_execution_v157 import CommunicationBridge, bind_world, extend_tools
from .software_sdk_input_sources_v159 import SDKRequestCapture
from .software_communication_runtime_v156 import AccountingConflict
from .software_communication_finish_v159 import decorate_reviews

VERSION = REPAIR_REVISION = 'v159-review2-measurement-finalization-repair-r1'
prepare_case = observed.prepare_case
worker_config = observed.worker_config
worker_type = observed.worker_type
close_runtime = observed.close_runtime
lock_fixed_candidates = observed.lock_fixed_candidates


def _bind(function, **bindings):
    result = FunctionType(function.__code__, {**function.__globals__, **bindings},
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def member_wire_tools(group, member):
    if group != 'REVIEW2':
        raise ValueError('P1 freezes REVIEW2 in all three communication conditions')
    rows = original.member_wire_tools(group, member)
    return [{'type': 'function', 'function': row} for row in
            extend_tools([r['function'] for r in rows])]


class CommunicationPort(world.SoftwareCollaborationPort):
    def observe(self):
        value = super().observe()
        bridge = self._session._world.communication_v157
        return bridge.project(value, self.role)


_world = SimpleNamespace(**{name: getattr(world, name) for name in dir(world) if not name.startswith('__')})
_world.SoftwareCollaborationPort = CommunicationPort
_native_build = _bind(original.build_runtime, world=_world, member_wire_tools=member_wire_tools,
    decorate_reviews=decorate_reviews)


def build_team_owner(post, *, organization_id, slot_id, condition_id, folder, deadline, identity,
                     communication_condition, observation_token_counter=None, observation_tokenizer_id=None,
                     require_content_counter=False, request_capture=None, response_callback=None,
                     bind_shared_budget=True):
    if organization_id != 'REVIEW2' or communication_condition not in {'C0', 'C1', 'C2'}:
        raise ValueError('A concrete communication condition within REVIEW2 is required')
    capture = SDKRequestCapture(Path(folder)/'request-capture-v157')
    holder = {}
    def request(member, payload, worker, owner):
        capture.request(member, payload, worker, owner)
        # Byte attribution and token attribution are different denominators.
        # Preserve all unknown spans, assess the approved local-token thresholds
        # in the score-blind wave audit, and never erase a valid paid trajectory
        # merely because one small request has >2% unknown UTF-8 bytes.
        if request_capture is not None:
            request_capture(member, payload, worker, owner)
    def response(member, payload, body, worker, owner):
        capture.response(member, payload, body, worker, owner)
        if response_callback is not None:
            response_callback(member, payload, body, worker, owner)
    def audited_post(route, payload):
        value = copy.deepcopy(payload)
        owner = holder.get('owner')
        if route == '/chat/completions' and value.get('usage_id') in {'agent', 'condenser'}:
            if owner is None or owner.observation.errors:
                raise AccountingConflict('Do not dispatch after failed measurement capture')
            annotations = capture.http_annotations(value['wire'], {
                'logical_id': value['request_id'], 'member_id': value['member_id'],
                'slot_id': value['slot_id']})
            from .software_benchmark_budget_v157 import encode_annotations
            value['source_annotations'] = encode_annotations(annotations)
        return post(route, value)
    owner = observed.build_team_owner(audited_post, organization_id=organization_id, slot_id=slot_id,
        condition_id=condition_id, folder=folder, deadline=deadline, identity=identity,
        observation_token_counter=observation_token_counter, observation_tokenizer_id=observation_tokenizer_id,
        require_content_counter=require_content_counter, request_capture=request, response_callback=response)
    holder['owner'] = owner
    owner.communication_condition = communication_condition
    owner.communication_token_counter = observation_token_counter
    owner.source_capture_v157 = capture
    if bind_shared_budget:
        from .software_benchmark_budget_v157 import bind_owner_budget
        bind_owner_budget(owner, audited_post)
    return owner


def build_runtime(owner, prepared, folder, *, deadline, public_initial_message, worker_factory=None,
                  bind_shared_budget=True):
    bridge = CommunicationBridge(prepared.world, owner, Path(folder)/'communication',
        owner.communication_condition, owner.communication_token_counter)
    bind_world(prepared.world, bridge)
    factory = worker_factory or worker_type()
    def tracked_factory(member, *args, **kwargs):
        worker = factory(member, *args, **kwargs)
        owner._v156_workers[member] = worker
        return worker
    try:
        runtime, captured, interfaces = _native_build(owner, prepared, folder, deadline=deadline,
            public_initial_message=public_initial_message, worker_factory=tracked_factory)
        owner.communication_v157 = bridge
        if bind_shared_budget:
            from .software_benchmark_budget_v157 import bind_runtime_budget
            bind_runtime_budget(owner, runtime)
        previous = runtime.execute
        def execute(self, label, name, arguments, association):
            result = previous(label, name, arguments, association)
            if name in {'send_message', 'handoff_patch', 'delegate_task', 'return_task'} and result.get('ok'):
                bridge.sync()
            return result
        runtime.execute = MethodType(execute, runtime)
        return runtime, captured, interfaces
    except BaseException:
        owner.observation.safely('closure', owner.observation.close_partial, 'communication_runtime_construction_failed')
        raise


def run_fragment(prepared, runtime, *, on_opportunity=None):
    result = observed.run_fragment(prepared, runtime, on_opportunity=on_opportunity)
    owner = runtime.owner
    if owner.observation.errors or owner.source_capture_v157.pending:
        owner.observation.safely('closure', owner.observation.close_partial, 'measurement_capture_incomplete')
        result['execution_integrity_failure'] = 'measurement_capture_incomplete'
    return result


def prepare_schema_inventory():
    schemas = {condition: {member: member_wire_tools('REVIEW2', member)
        for member in ('member_001', 'member_002')} for condition in ('C0', 'C1', 'C2')}
    return {'version': VERSION, 'schemas': schemas, 'generation_calls': 0,
        'same_tools_and_ACL_all_conditions': True, 'compressor_is_autonomous_member': False,
        'organization_id': 'REVIEW2', 'one_member_action_per_opportunity': True}
