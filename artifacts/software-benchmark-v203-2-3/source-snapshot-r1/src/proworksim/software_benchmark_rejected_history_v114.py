"""Future native history handling for actual SDK-rejected provider tool calls.

This is not installed into the frozen v110-v113 experiments. Original provider
responses and accounting stay unchanged. Only a source-bound SDK rejection may
replace an invalid historical arguments string with the SDK's own error marker.
No arguments are repaired, no rejected action is executed, and no call is retried.
"""
from __future__ import annotations

import copy
from functools import cache
import json
from pathlib import Path

from .software_benchmark_deepseek_interfaces_v055 import ReasoningHistory, _canonical_call
from .software_benchmark_candidates_v054 import write_new
from .storage import digest, json_bytes

VERSION = 'v114-native-source-bound-rejected-tool-history-r1'


class SDKRejectedHistory(ReasoningHistory):
    def __init__(self, adapter, folder):
        super().__init__()
        self.adapter, self.folder = adapter, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.conversation = self.state = None
        self.responses, self.receipts = {}, {}

    def bind_conversation(self, conversation):
        from .software_benchmark_history_budget_v110 import RefSummaryGuard
        guard = conversation.agent.llm._adapter
        if (self.conversation is not None or self.messages or self.adapter.ledger.attempts
                or type(guard) is not RefSummaryGuard or guard.delegate is not self.adapter._v057_projection_guard
                or guard.delegate.delegate is not self.adapter or guard.trace.conversation is not conversation):
            raise ValueError('Bind rejected-tool history once to the fresh original REF conversation')
        guard.trace.assert_bound_to(conversation)
        self.conversation, self.state = conversation, conversation.state

    def remember(self, message):
        super().remember(message)
        if not message.get('tool_calls'):
            return
        if self.conversation is None or not self.adapter.ledger.calls:
            raise ValueError('An original settled response and bound conversation are required')
        row = self.adapter.ledger.calls[-1]
        if row.get('usage_id') != 'agent' or not row.get('response_id'):
            raise ValueError('Only a settled original agent response may own tool-call history')
        key = tuple(call['id'] for call in message['tool_calls'])
        prior = self.responses.get(key)
        if prior is not None and prior != row['response_id']:
            raise ValueError('Original tool identities cannot identify two provider responses')
        self.responses[key] = row['response_id']

    def _sdk_rejection(self, current, original, response_id):
        from openhands.sdk.event import ActionEvent, AgentErrorEvent
        if self.conversation is None or self.conversation.state is not self.state:
            raise ValueError('Rejected history lost its original conversation/state binding')
        trace = self.conversation.agent.llm._adapter.trace
        trace.assert_bound_to(self.conversation)
        marker = json.loads(current['function']['arguments'])
        if (not isinstance(marker, dict) or set(marker) != {'_openhands_malformed_tool_call', 'error'}
                or marker['_openhands_malformed_tool_call'] is not True or not isinstance(marker['error'], str)):
            raise ValueError('Only the actual SDK malformed-call marker may represent rejection')
        events = list(self.state.events)
        actions = [(i, event) for i, event in enumerate(events) if isinstance(event, ActionEvent)
                   and event.tool_call_id == current['id']]
        errors = [(i, event) for i, event in enumerate(events) if isinstance(event, AgentErrorEvent)
                  and event.tool_call_id == current['id']]
        if len(actions) != 1 or len(errors) != 1:
            raise ValueError('A rejected provider call needs one actual source action/error pair')
        ai, action = actions[0]
        ei, error = errors[0]
        if (not ai < ei or getattr(action, 'action', None) is not None
                or action.tool_name != original['function']['name'] or error.tool_name != action.tool_name
                or action.llm_response_id != response_id or action.tool_call.origin != 'completion'
                or action.tool_call.id != current['id'] or action.tool_call.name != current['function']['name']
                or action.tool_call.arguments != current['function']['arguments']
                or error.error != marker['error']):
            raise ValueError('The historical marker is not this provider call\'s actual unexecuted SDK rejection')
        receipt = {'version': VERSION, 'response_id': response_id, 'call_id': current['id'],
            'conversation_id': str(self.conversation.id), 'action_event_id': action.id, 'error_event_id': error.id,
            'action_sha256': digest(json_bytes(action.model_dump(mode='json'))),
            'error_sha256': digest(json_bytes(error.model_dump(mode='json'))),
            'original_arguments_sha256': digest(original['function']['arguments'].encode()),
            'SDK_marker_sha256': digest(current['function']['arguments'].encode()),
            'original_response_changed': False, 'tool_action_executed': False,
            'automatic_retry': False, 'additional_budget': 0}
        key = current['id']
        if key in self.receipts and self.receipts[key] != receipt:
            raise ValueError('A previously validated SDK rejection source changed')
        if key not in self.receipts:
            write_new(self.folder/(digest(key.encode())+'.json'), receipt)
            self.receipts[key] = receipt
        return copy.deepcopy(current)

    def _project(self, message, original, key, *, thinking, prefix):
        current_calls = message['tool_calls']
        original_calls = original['tool_calls'][:len(current_calls)] if prefix else original['tool_calls']
        if len(current_calls) != len(original_calls):
            raise ValueError('Historical tool-call inventory changed')
        selected = []
        for current, previous in zip(current_calls, original_calls, strict=True):
            if (current.get('id') != previous.get('id') or current.get('type', 'function') != previous.get('type', 'function')
                    or current['function']['name'] != previous['function']['name']):
                raise ValueError('Historical tool identity changed')
            try:
                parsed = json.loads(current['function']['arguments'])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get('_openhands_malformed_tool_call') is True:
                selected.append(self._sdk_rejection(current, previous, self.responses[key]))
            else:
                try:
                    equal = _canonical_call(current) == _canonical_call(previous)
                except json.JSONDecodeError as error:
                    raise ValueError('Unparseable history lacks an actual SDK rejection receipt') from error
                if not equal:
                    raise ValueError('SDK changed the arguments of an original provider tool call')
                selected.append(copy.deepcopy(previous))
        projected = {**copy.deepcopy(original), 'tool_calls': selected}
        if thinking and not isinstance(projected.get('reasoning_content'), str):
            raise ValueError('Thinking provider omitted its original reasoning provenance')
        return projected

    def restore(self, messages, *, thinking):
        result = copy.deepcopy(messages)
        for index, message in enumerate(result):
            if message.get('role') != 'assistant' or not message.get('tool_calls'):
                continue
            key = tuple(call['id'] for call in message['tool_calls'])
            original = self.messages.get(key)
            if original is None:
                if thinking and not isinstance(message.get('reasoning_content'), str):
                    raise ValueError('Thinking continuation has no original reasoning provenance')
                continue
            result[index] = self._project(message, original, key, thinking=thinking, prefix=False)
        return result

    def restore_prefix(self, messages):
        result = copy.deepcopy(messages)
        for index, message in enumerate(result):
            if message.get('role') != 'assistant' or not message.get('tool_calls'):
                continue
            ids = tuple(call['id'] for call in message['tool_calls'])
            matches = [key for key in self.messages if key[:len(ids)] == ids]
            if len(matches) != 1:
                raise ValueError('Count-only history lacks one original response provenance')
            key = matches[0]
            result[index] = self._project(message, self.messages[key], key, thinking=False, prefix=True)
        return result


@cache
def native_type():
    from .software_benchmark_deepseek_adapter_v105 import native_type as original_type
    from .software_benchmark_deepseek_prefix_v055_r2 import pending_tail_tool_ids

    class RejectedHistoryNativeLLM(original_type()):
        def get_token_count(self, messages, tools=None, **kwargs):
            self._adapter.assert_healthy()
            if not messages:
                return 0
            wire = self.format_messages_for_llm(messages)
            pending = pending_tail_tool_ids(wire)
            if not pending:
                return super().get_token_count(messages, tools, **kwargs)
            if set(kwargs)-{'add_security_risk_prediction', 'on_token', 'call_context'}:
                raise ValueError('Unfrozen native SDK count options')
            history = self._adapter.history
            if type(history) is not SDKRejectedHistory:
                raise ValueError('Bind the source-checked rejected-call history before prefix counting')
            request = self._adapter.request(history.restore_prefix(wire), [dict(tool.to_openai_tool(
                add_security_risk_prediction=bool(kwargs.get('add_security_risk_prediction')))) for tool in tools or []])
            return self._adapter.count_prefix(request, pending)['prompt_tokens']
    return RejectedHistoryNativeLLM


def build_native_llm(adapter, *, normalization_folder, rejected_history_folder):
    from .software_benchmark_exact_transport_v057 import ProjectionGuard, ResponseProjectionFault
    from .software_benchmark_deepseek_adapter_v105 import api
    if (adapter.arm != 'REF' or adapter.ledger.attempts or adapter.ledger.inflight is not None
            or adapter.history.messages or getattr(adapter, '_v057_projection_guard', None) is not None):
        raise ResponseProjectionFault('This future repair cannot resume or rebind a consumed episode')
    adapter.history = SDKRejectedHistory(adapter, rejected_history_folder)
    llm = native_type()(model='openai/'+api.MODEL, usage_id='agent', api_mode='chat',
        num_retries=0, stream=False, caching_prompt=False, disable_vision=True,
        native_tool_calling=True, force_string_serializer=True,
        max_input_tokens=adapter.maximum_input_tokens, max_output_tokens=adapter.maximum_output_tokens)
    folder = Path(normalization_folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    llm._normalization_folder = str(folder)
    guard = ProjectionGuard(adapter, folder)
    adapter._v057_projection_guard = guard
    llm._adapter = guard
    return llm


def bind_native_history(adapter, conversation):
    if type(adapter.history) is not SDKRejectedHistory:
        raise ValueError('Only the explicitly constructed future native history may be bound')
    adapter.history.bind_conversation(conversation)
    return conversation


def create_ref_conversation(config, adapter, rpc, output, limits, *, workspace='/testbed'):
    """Future explicit opt-in factory; the current frozen controllers do not import it."""
    from openhands.sdk import Conversation
    from .software_benchmark_native_binding_v054 import build_isolated_agent
    from .software_benchmark_history_v110 import bind_ref_history, bind_ref_conversation
    output = Path(output)
    llm = build_native_llm(adapter, normalization_folder=output/'sdk-response-projections',
                           rejected_history_folder=output/'sdk-rejected-tool-history')
    condenser = bind_ref_history(llm, directory=output/'history-summary')
    agent = build_isolated_agent(llm, rpc=rpc).model_copy(update={'condenser': condenser})
    conversation = Conversation(agent=agent, workspace=workspace,
        persistence_dir=output/'native-conversation', plugins=[], max_iteration_per_run=limits['agent_decisions'],
        stuck_detection=True, visualizer=None, delete_on_close=False)
    bind_ref_conversation(conversation)
    return bind_native_history(adapter, conversation)
