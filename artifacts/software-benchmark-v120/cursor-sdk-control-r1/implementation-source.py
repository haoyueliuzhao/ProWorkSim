"""Fix the instance-local cursor bridge's JSON object-order false rejection.

JSON object field order is not an argument change. Types, values, list order,
keys, explicit null provenance and the original managed gateway stay strict.
No default value is invented, no action replayed and no old worker is modified.
"""
from __future__ import annotations

import copy
import json

from . import software_benchmark_tooling_v117 as previous
from .work_interface import _schema_errors

VERSION = 'v120-typed-order-independent-managed-cursor-projection-r1'
PROJECT, MEMBERS = previous.PROJECT, previous.MEMBERS
prepare_case, validate_case = previous.prepare_case, previous.validate_case
member_instruction, tool_definitions = previous.member_instruction, previous.tool_definitions
SoftwareCollaborationPort = previous.SoftwareCollaborationPort
PublicTestCallback = previous.PublicTestCallback
CURSOR_TOOLS = previous.CURSOR_TOOLS


def canonical_arguments(value):
    """Ignore only object order; retain JSON scalar types and array order."""
    if not isinstance(value, dict):
        raise ValueError('Managed tool arguments must remain a JSON object')
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


class NullableCursorExecutor(previous._NullableCursorExecutor):
    def __call__(self, action, conversation=None):
        pending = self.worker._pending
        if pending is None or self.worker._executions != 0 or pending['name'] != self.name:
            return self.delegate(action, conversation)
        original = pending['arguments']
        errors = _schema_errors(self.schema, original)
        if errors:
            raise ValueError('Pending arguments violate the declared schema: ' + '; '.join(errors))
        projected = action.model_dump(mode='json', by_alias=True,
                                      exclude_unset=True, exclude_computed_fields=True)
        if canonical_arguments(projected) != canonical_arguments(original):
            if ('cursor' not in original or original['cursor'] is not None or 'cursor' in projected
                    or canonical_arguments(projected) != canonical_arguments({key: value for key, value in original.items()
                                                                               if key != 'cursor'})):
                raise ValueError('SDK changed managed arguments beyond omission of an admitted cursor:null')
            action = type(action).model_validate(copy.deepcopy(original))
            restored = action.model_dump(mode='json', by_alias=True,
                                         exclude_unset=True, exclude_computed_fields=True)
            if canonical_arguments(restored) != canonical_arguments(original):
                raise RuntimeError('Nullable cursor restoration changed original managed arguments')
            self.worker._emit('sdk_explicit_null_cursor_restored', {'version': VERSION,
                'tool': self.name, 'model_tool_call_id': pending['tool_call_id'],
                'restored_field': 'cursor', 'original_value': None,
                'other_arguments_changed': False, 'world_action_executed': False,
                'original_gateway_comparison_still_required': True})
        return self.delegate(action, conversation)


def install_nullable_cursors(worker):
    """Replace exactly six verified wrappers before the first model decision."""
    from .harness_sdk import HarnessWorker, _GatewayExecutor
    if (not isinstance(worker, HarnessWorker) or hasattr(worker, '_nullable_cursor_v120')
            or worker.meter['decisions'] != 0 or worker._pending is not None or worker._executions != 0
            or worker._done is not None or worker._in_step
            or set(getattr(worker, '_nullable_cursor_v117', {}).get('tools', [])) != CURSOR_TOOLS):
        raise ValueError('Install the order-independent bridge only on its fresh verified worker')
    agent = worker.conversation.agent
    tools, replacements = agent.tools_map, {}
    definitions = {row['name']: row['parameters'] for row in worker.definitions}
    for name in sorted(CURSOR_TOOLS):
        tool = tools[name]
        executor = tool.executor
        if (type(executor) is not previous._NullableCursorExecutor
                or executor.worker is not worker or executor.name != name
                or executor.schema != definitions[name] or tool.response_schema is not None
                or not isinstance(executor.delegate, _GatewayExecutor)
                or executor.delegate.worker is not worker or executor.delegate.name != name):
            raise ValueError('Require the exact fresh original cursor/gateway chain')
        replacements[name] = tool.set_executor(NullableCursorExecutor(
            executor.delegate, worker, name, executor.schema))
    with agent._tools_lock:
        if set(agent._tools) != set(tools) or any(agent._tools[key] is not value for key, value in tools.items()):
            raise RuntimeError('Tool bindings changed during fresh cursor bridge installation')
        object.__setattr__(agent, '_tools', {**agent._tools, **replacements})
    worker._nullable_cursor_v120 = {'version': VERSION, 'tools': sorted(CURSOR_TOOLS),
        'JSON_object_order_is_semantic': False, 'scalar_types_and_values_preserved': True,
        'automatic_default_insertion': False, 'SDK_globals_changed': False,
        'original_raw_response_changed': False, 'old_accepted_calls_replayed': False}
    return copy.deepcopy(worker._nullable_cursor_v120)


class ToolFeedbackWorkerMixin(previous.ToolFeedbackWorkerMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            install_nullable_cursors(self)
        except BaseException:
            self.close()
            raise
