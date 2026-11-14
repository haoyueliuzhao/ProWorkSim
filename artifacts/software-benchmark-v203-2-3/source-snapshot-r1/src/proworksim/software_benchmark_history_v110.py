"""Shared, source-bound SDK summarization for new REF and PROJECT conversations.

No API client, key, shell or evaluator is introduced. All model work uses the
controller's injected original adapter and its original budget.
"""
from __future__ import annotations

import copy
from functools import cache

from .software_benchmark_alignment_contract_v110 import CONDENSER_PARAMETERS
from .software_benchmark_budget_closure_v103 import (
    RemainingBudgetContextTransport, affordable_output_cap, PREPARATION_VERSION,
    VERSION as OUTPUT_POLICY_VERSION,
)
from .software_benchmark_history_budget_v110 import (
    AlignedManagedTeamBudget, ManagedSummaryAdapter, RefSummaryGuard, SummaryTrace,
)
from .software_benchmark_managed_v064 import (
    CONTEXT_LIMIT, MAX_INPUT_TOKENS, MAX_OUTPUT_TOKENS, ATTEMPT_LIMIT,
)
from .software_context_v048 import _prepare, _protected_request, validate_reference_projection
from .storage import digest, json_bytes

VERSION = 'v110-shared-source-bound-sdk-history-r1'
SUMMARY_LABEL = (
    '[Derived private history summary. This may be incomplete or mistaken. '
    'It is not a new observation, permission, test result, submission or evidence. '
    'The current task, current observation and actual tool results remain authoritative.]\n'
)


def _protected_floor(view, trace, keep_first):
    """Keep the latest real user input and latest complete tool round intact."""
    from openhands.sdk.event import ActionEvent, ObservationEvent
    from openhands.sdk.event.llm_convertible import MessageEvent
    events = view.events
    floors = [i for i, event in enumerate(events)
              if (i >= keep_first and isinstance(event, MessageEvent)
                  and event.llm_message.role == 'user' and event.id not in trace.presented_event_ids)]
    observations = [(i, event) for i, event in enumerate(events) if isinstance(event, ObservationEvent)]
    if observations:
        index, observation = observations[-1]
        matching = [i for i, event in enumerate(events[:index])
                    if isinstance(event, ActionEvent) and event.tool_call_id == observation.tool_call_id]
        if matching:
            floors.append(matching[-1])
    return min(floors) if floors else max(0, len(events)-1)


@cache
def condenser_type():
    from pydantic import PrivateAttr
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    from openhands.sdk.context.condenser.base import NoCondensationAvailableException
    from openhands.sdk.context.condenser.utils import get_total_token_count

    class AlignedHistoryCondenser(LLMSummarizingCondenser):
        _trace: object = PrivateAttr(default=None)

        def _get_forgotten_events(self, view, agent_llm=None):
            forgotten, start = super()._get_forgotten_events(view, agent_llm)
            floor = _protected_floor(view, self._trace, self.keep_first)
            end = min(start + len(forgotten), max(i for i in view.manipulation_indices if i <= floor))
            if end <= start:
                raise NoCondensationAvailableException('Only protected current input remains')
            return view.events[start:end], start

        def _generate_condensation(self, forgotten_events, summary_offset, max_event_str_length=None):
            if max_event_str_length is not None:
                raise ValueError('Aligned history never truncates a source event to manufacture fit')
            trace = self._trace
            trace.assert_healthy()
            trace.begin(forgotten_events)
            try:
                result = super()._generate_condensation(forgotten_events, summary_offset, None)
                if not isinstance(result.summary, str) or not result.summary.strip():
                    raise ValueError('An empty or absent summary cannot delete original history')
                result = result.model_copy(update={'summary': SUMMARY_LABEL + result.summary})
                trace.finish(result)
                return result
            except BaseException as error:
                # Prefer the original budget/unknown-usage boundary over SDK's
                # NoCondensationAvailable wrapper, then retain it permanently.
                failure = trace.failure or error
                trace.fail(failure)
                raise failure

        def condense(self, view, agent_llm=None):
            self._trace.assert_healthy()
            result = super().condense(view, agent_llm)
            self._trace.assert_healthy()
            from openhands.sdk.context.view import View
            if isinstance(result, View):
                self._trace.note_view(result)
            return result

        def hard_context_reset(self, view, agent_llm=None):
            self._trace.assert_healthy()
            # Use the largest whole, eligible middle range. Current input and
            # complete tool pairs are never turned into untrusted summary text.
            start = view.manipulation_indices.find_next(self.keep_first)
            floor = _protected_floor(view, self._trace, self.keep_first)
            ends = [i for i in view.manipulation_indices if start < i <= floor]
            if not ends:
                raise NoCondensationAvailableException('No unprotected complete history remains')
            result = self._generate_condensation(view.events[start:max(ends)], start)
            if agent_llm is not None:
                after = result.apply(list(view.events))
                if get_total_token_count(after, agent_llm) >= get_total_token_count(view.events, agent_llm):
                    error = RuntimeError('Summary did not reduce the original complete context')
                    self._trace.failure = error
                    raise error
            return result

        async def acondense(self, view, agent_llm=None):
            return self.condense(view, agent_llm)

    return AlignedHistoryCondenser


def build_condenser(llm, *, trace):
    params = dict(CONDENSER_PARAMETERS)
    params['hard_context_reset_max_retries'] = params.pop('hard_reset_retries')
    value = condenser_type()(llm=llm.model_copy(update={'usage_id': 'condenser'}), **params)
    value._trace = trace
    return value


def bind_ref_history(llm, *, directory):
    """Call on the already constructed key-free native LLM before Agent creation."""
    if getattr(llm, '_adapter', None) is None or isinstance(llm._adapter, RefSummaryGuard):
        raise ValueError('Bind the admitted native LLM history exactly once')
    trace = SummaryTrace(directory=directory, owner_id='REF-single-agent')
    llm._adapter = RefSummaryGuard(llm._adapter, trace)
    return build_condenser(llm, trace=trace)


def bind_ref_conversation(conversation):
    """Bind the source history after construction, before the first run."""
    guard = conversation.agent.llm._adapter
    if not isinstance(guard, RefSummaryGuard):
        raise ValueError('REF history does not use the declared shared guard')
    guard.trace.bind_conversation(conversation)
    return conversation


def _project_messages(messages, worker):
    from openhands.sdk.llm import Message, TextContent
    flattened = []
    for item in messages:
        if item.role == 'user' and len(item.content) > 1:
            for block in item.content:
                if not isinstance(block, TextContent):
                    raise ValueError('Only the original text user observations are allowed')
                flattened.append(Message(role='user', content=[block]))
        else:
            flattened.append(item)
    wire = [item.to_chat_dict(cache_enabled=False, vision_enabled=False,
                             function_calling_enabled=True, force_string_serializer=True,
                             send_reasoning_content=True) for item in flattened]
    for index, message in enumerate(wire):
        calls = message.get('tool_calls') or []
        if message.get('role') == 'assistant' and len(calls) == 1:
            original = worker._assistant_messages.get(calls[0]['id'])
            if original is None:
                raise ValueError('PROJECT count lacks the original assistant response')
            wire[index] = copy.deepcopy(original)
    return wire


@cache
def managed_counting_llm_type():
    from .harness_sdk import ResidentBridgeLLM
    from .software_benchmark_deepseek_prefix_v055_r2 import pending_tail_tool_ids

    class ManagedCountingLLM(ResidentBridgeLLM):
        def get_token_count(self, messages, tools=None, **kwargs):
            worker = self._worker
            worker._history_trace_v110.assert_healthy()
            if not messages:
                return 0
            if set(kwargs) - {'add_security_risk_prediction', 'on_token', 'call_context'}:
                raise ValueError('Unexpected PROJECT token count parameters')
            # Count the same model-visible schema as actual _complete, rather
            # than SDK-added risk fields or the old placeholder model tokenizer.
            adapter = worker.transport.owner.adapter
            definitions = [{'type': 'function', 'function': row} for row in worker.definitions] if tools else []
            wire = adapter.request(_project_messages(messages, worker), definitions)
            pending = pending_tail_tool_ids(wire['messages'])
            _, _, _, _, selected, _ = _prepare(wire, worker.transport.feedback_ledger, worker.role_id)
            counted = adapter.request(selected['messages'], selected.get('tools'))
            if pending:
                return adapter.count_prefix(counted, pending)['prompt_tokens']
            return adapter.count(counted)['prompt_tokens']

    return ManagedCountingLLM


class SummarizingManagedContextTransport(RemainingBudgetContextTransport):
    """Keep SDK's source-bound summary view; never silently slide old work away."""
    def prepare_for_budget(self, request):
        if self._turn is None or self._prepared is not None:
            raise ValueError('Only an unused bound turn may prepare')
        member = self._turn['member_id']
        _, feedback, static, deduplication, selected, references = _prepare(request, self.feedback_ledger, member)
        _, protected = _protected_request(selected)
        indices = list(range(len(selected['messages'])))
        validation = validate_reference_projection(selected, static, indices, references)
        adapter = self.owner.adapter
        wire = adapter.request(selected['messages'], selected.get('tools'))
        measured = adapter.count(wire)
        prompt = measured['prompt_tokens']
        meter, team, local_limit = self._budget_sources_v103[member]
        state = team.snapshot()
        values = {'local_available_tokens': local_limit-meter['budget_accounted_tokens'],
                  'team_available_tokens': state['available_tokens'],
                  'adapter_available_tokens': adapter.ledger.token_budget-adapter.ledger.actual}
        if state.get('integrity_failure') or adapter.ledger.inflight is not None or min(values.values()) < 0:
            raise ValueError('Unresolved accounting cannot prepare another agent request')
        available = min(values.values())
        cap = affordable_output_cap(prompt, available)
        if cap != MAX_OUTPUT_TOKENS:
            wire['max_tokens'] = cap
            recounted = adapter.count(wire)
            if recounted['prompt_tokens'] != prompt:
                raise ValueError('Output cap changed the counted input')
            measured = recounted
        fits = prompt <= MAX_INPUT_TOKENS and prompt+cap <= CONTEXT_LIMIT
        adjustment = {'version': OUTPUT_POLICY_VERSION, **values, 'available_tokens': available,
            'team_state_sha256': state['state_sha256'], 'maximum_output_tokens': MAX_OUTPUT_TOKENS,
            'actual_output_cap': cap, 'reduced': cap != MAX_OUTPUT_TOKENS,
            'input_and_history_unchanged': True, 'automatic_submission': False,
            'no_positive_output_room': available <= prompt}
        mapped = list(feedback['selected_indices'])
        projection = {'version': VERSION, 'fits': fits, 'count_method': measured['method'],
            'measurement': measured, 'selected_prompt_token_reservation': prompt,
            'reserved_output_tokens': cap, 'context_limit': CONTEXT_LIMIT,
            'maximum_input_tokens': MAX_INPUT_TOKENS, 'sdk_context_selection': 'full_history',
            'format_feedback_projection': feedback, 'static_deduplication': deduplication,
            'same_input_references': references, 'reference_validation': validation,
            'selected_indices': mapped, 'removed_indices': [], 'capacity_history_dropped': False,
            'original_request_sha256': digest(json_bytes(request)),
            'selected_request_sha256': digest(json_bytes(selected)),
            'wire_request_sha256': digest(json_bytes(wire)),
            'latest_complete_round_preserved': protected['latest_complete_round_preserved'],
            'output_budget_adjustment': adjustment}
        measure = {'version': PREPARATION_VERSION,
            'original_request_sha256': digest(json_bytes(request)),
            'selected_request_sha256': digest(json_bytes(selected)),
            'wire_request_sha256': digest(json_bytes(wire)), 'prompt_tokens': prompt,
            'reserved_output_tokens': cap, 'context_limit': CONTEXT_LIMIT, 'fits': fits,
            'count_method': measured['method'], 'window_id': self.owner.window_id,
            'actor_identity': self.owner.freeze_identity(), 'output_budget_adjustment': adjustment,
            'history_policy': VERSION}
        measure['preparation_sha256'] = digest(json_bytes(measure))
        self._prepared = {'original': copy.deepcopy(request), 'selected': selected, 'wire': wire,
            'projection': projection, 'measurement': copy.deepcopy(measure), 'turn': copy.deepcopy(self._turn)}
        return measure


class HistoryWorkerMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (not isinstance(self.team_budget, AlignedManagedTeamBudget)
                or not isinstance(self.transport, SummarizingManagedContextTransport)
                or self.meter['decisions'] != 0 or self._in_step):
            raise ValueError('The aligned history worker requires its fresh same-pool runtime')
        self._history_trace_v110 = SummaryTrace(directory=self.directory/'history-summaries',
            owner_id=self.role_id, event_sink=self._emit)
        self._history_trace_v110.bind_conversation(self.conversation)
        from .software_benchmark_deepseek_adapter_v105 import build_native_llm
        summary_adapter = ManagedSummaryAdapter(self, self.transport.owner.adapter, self._history_trace_v110)
        summary_llm = build_native_llm(summary_adapter,
            normalization_folder=self.directory/'summary-response-projections')
        summary_llm.usage_id = 'condenser'
        counting = managed_counting_llm_type()(model='openai/'+self.config['model'], usage_id='agent',
            num_retries=0, stream=False, caching_prompt=False, max_input_tokens=MAX_INPUT_TOKENS,
            max_output_tokens=MAX_OUTPUT_TOKENS, temperature=self.config['temperature'])
        counting._worker = self
        condenser = build_condenser(summary_llm, trace=self._history_trace_v110)
        conversation = self.conversation
        with conversation.state:
            agent = conversation.agent.model_copy(update={'llm': counting, 'condenser': condenser})
            conversation.agent = agent
            conversation.state.agent = agent
            self.agent, self.llm = agent, counting
            for llm in (counting, condenser.llm):
                if llm.usage_id in conversation.llm_registry.list_usage_ids():
                    raise ValueError('Aligned model-use identity was already registered')
                conversation.llm_registry.add(llm)
                conversation._bind_conversation_context(llm)
            # SDK iterations include summaries. The unchanged worker gate still
            # permits exactly one agent completion/action per scheduler turn.
            conversation.max_iteration_per_run = ATTEMPT_LIMIT
        self._history_policy_v110 = {'version': VERSION, 'condenser': dict(CONDENSER_PARAMETERS),
            'same_model_pool': True, 'summary_adds_agent_decision': False,
            'one_agent_action_per_opportunity': True, 'SDK_iteration_limit': ATTEMPT_LIMIT,
            'silent_capacity_history_drop': False}

    def _complete(self, messages, tools):
        self._history_trace_v110.assert_healthy()
        try:
            return super()._complete(messages, tools)
        finally:
            body = self._last_body
            if (isinstance(body, dict) and body.get('id')
                    and isinstance(body.get('usage'), dict)
                    and self.transport.owner.adapter.ledger.inflight is None):
                self._history_trace_v110.mark_presented(body)

    def snapshot(self):
        value = super().snapshot()
        if hasattr(self, '_history_policy_v110'):
            value['history_policy_v110'] = copy.deepcopy(self._history_policy_v110)
        return value


@cache
def history_worker_type():
    from .software_benchmark_managed_v105 import worker_type

    class AlignedHistoryWorker(HistoryWorkerMixin, worker_type()):
        pass

    return AlignedHistoryWorker
