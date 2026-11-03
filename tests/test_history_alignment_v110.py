"""Scripted, private-SDK controls; no external model, network, Docker or GPU."""
# ruff: noqa: E402 -- offline settings must precede SDK imports.
from __future__ import annotations

import copy
import os
import tempfile
from types import SimpleNamespace

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
os.environ['OPENHANDS_SUPPRESS_BANNER'] = '1'
_SETTINGS = tempfile.TemporaryDirectory(prefix='v110-history-settings-')
os.environ['OH_PERSISTENCE_DIR'] = _SETTINGS.name

import pytest
from openhands.sdk.context.view import View
from openhands.sdk.event import ActionEvent, ObservationEvent
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from proworksim.harness_sdk import GatewayObservation

from proworksim import software_benchmark_deepseek_adapter_v105 as remote
from proworksim import software_benchmark_deepseek_contract_v105 as contract
from proworksim import software_benchmark_history_v110 as history
from proworksim.software_benchmark_history_budget_v110 import (
    AlignedManagedTeamBudget, ManagedSummaryAdapter, SummaryTrace,
)
from proworksim.model_policy import ModelPolicy
from proworksim.staff_runtime import PolicyBoundaryError
from proworksim.storage import digest, json_bytes


def message(text, source='user'):
    return MessageEvent(llm_message=Message(role='user' if source == 'user' else 'assistant',
        content=[TextContent(text=text)]), source=source)


def tool_round(index, text='public result'):
    call = MessageToolCall(id=f'tool-{index}', name='read_file', arguments='{}', origin='completion')
    action = ActionEvent(thought=[], action=None, tool_name='read_file', tool_call_id=call.id,
        tool_call=call, llm_response_id=f'cpu-agent-{index}')
    obs = ObservationEvent(tool_name='read_file', tool_call_id=call.id,
        action_id=action.id, observation=GatewayObservation(content=[TextContent(text=text)]))
    return [action, obs]


def body(index=1, text='Short private summary.', *, bad_mode=False):
    msg = {'role': 'assistant', 'content': text}
    if bad_mode:
        msg['reasoning_content'] = 'Unexpected reasoning in a disabled mode.'
    return {'id': f'cpu-summary-{index}', 'object': 'chat.completion', 'model': contract.MODEL,
        'choices': [{'index': 0, 'finish_reason': 'stop', 'message': msg}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 5, 'total_tokens': 105,
                  'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 100}}


def adapter(tmp_path, *, failure=None, arm='PROJECT'):
    calls = []
    def post(route, payload):
        if route in ('/tokenize', '/tokenize-prefix'):
            return {'prompt_tokens': 100, 'method': 'scripted CPU count; not provider measurement',
                'request_sha256': digest(json_bytes(payload['wire'])),
                'count_only_not_dispatchable': route.endswith('prefix')}
        assert route == '/chat/completions'
        calls.append(copy.deepcopy(payload))
        if failure == 'unknown':
            raise TimeoutError('Scripted attempted-but-unsettled response')
        if failure == 'before':
            raise contract.PreDispatchBudgetStopped('scripted pre-provider refusal')
        return body(len(calls), bad_mode=failure == 'mode')
    value = remote.DeepSeekEpisodeAdapter(post=post, arm=arm, slot_id='v110-scripted-history',
        condition_id='DEEPSEEK_NT_'+arm+'_ALIGNED_B5000K', token_budget=5_000_000,
        folder=tmp_path/'model', allowed_tool_names=remote.NATIVE_TOOLS if arm == 'REF' else {'read_file'})
    return value, calls


def fake_worker(tmp_path, *, failure=None):
    original, calls = adapter(tmp_path, failure=failure)
    accountant = ModelPolicy()
    config = copy.deepcopy(accountant.config)
    config['budget'].update(max_decisions=512, max_http_attempts=512, max_total_tokens=5_000_000)
    accountant = ModelPolicy(config)
    team = AlignedManagedTeamBudget(members=['member_001'], team_id='cpu-history',
        max_decisions=512, max_attempts=512, max_total_tokens=5_000_000, require_exact_resident=False)
    association = {'call_id': 'cpu-decision-1', 'worker_id': 'member_001'}
    team.consume_decision('member_001', association['call_id'])
    meter = {key: 0 for key in ('decisions', 'http_attempts', 'reported_total_tokens',
        'reported_prompt_tokens', 'reported_completion_tokens', 'cost_upper_bound_usd',
        'budget_accounted_tokens', 'budget_accounted_cost_usd', 'unknown_usage_attempts')}
    meter['decisions'] = 1
    worker = SimpleNamespace(role_id='member_001', _in_step=True, _completions=0, _pending=None,
        _association=association, config=config, meter=meter, team_budget=team,
        _accountant=accountant, _emit=lambda *_: None,
        _boundary_error=None)
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    context = history.SummarizingManagedContextTransport(SimpleNamespace(adapter=original), tmp_path/'transport')
    context.native_dispatch_gate = SimpleNamespace(
        runtime=SimpleNamespace(policies={'member_001': worker}, team_budget=team),
        deadline=DispatchDeadline(soft_seconds=21600, hard_seconds=23400))
    worker.transport = context
    def fail(status, reason, **details):
        worker._boundary_error = PolicyBoundaryError(status, reason, memory={}, details=details)
        raise worker._boundary_error
    worker._fail = fail
    trace = SummaryTrace(directory=tmp_path/'summaries', owner_id='member_001')
    events = [message('Private already-available public source')]
    conversation = SimpleNamespace(state=SimpleNamespace(events=events))
    trace.bind_conversation(conversation)
    trace.begin(events)
    proxy = ManagedSummaryAdapter(worker, original, trace)
    return worker, original, trace, proxy, calls


def test_auxiliary_summary_uses_same_three_ledgers_without_agent_opportunity(tmp_path):
    worker, original, trace, proxy, calls = fake_worker(tmp_path)
    result = proxy.complete(original.request([{'role': 'user', 'content': 'Summarize private events.'}], []))
    assert result['usage']['total_tokens'] == 105
    assert len(calls) == 1 and calls[0]['usage_id'] == 'condenser'
    assert original.ledger.decisions == 0 and original.ledger.attempts == 1
    assert worker.meter['decisions'] == 1 and worker.meter['http_attempts'] == 1
    state = worker.team_budget.snapshot()
    assert state['decisions'] == 1 and state['attempts'] == 1 and state['charged_tokens'] == 105
    assert state['records']['cpu-decision-1']['status'] == 'decision_consumed'
    assert worker.meter['budget_accounted_tokens'] == 105
    assert trace.pending['attempts'] == 1
    with pytest.raises(ValueError, match='cannot act'):
        proxy.complete(original.request([{'role': 'user', 'content': 'again'}], []))
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['unknown', 'mode', 'before'])
def test_failed_summary_cannot_continue_or_refund_attempted_usage(tmp_path, failure):
    worker, original, trace, proxy, calls = fake_worker(tmp_path, failure=failure)
    with pytest.raises(PolicyBoundaryError):
        proxy.complete(original.request([{'role': 'user', 'content': 'Private summary.'}], []))
    before = len(calls)
    with pytest.raises(PolicyBoundaryError):
        proxy.complete(original.request([{'role': 'user', 'content': 'must not dispatch'}], []))
    assert len(calls) == before
    state = worker.team_budget.snapshot()
    assert state['decisions'] == 1
    if failure == 'unknown':
        assert original.ledger.inflight is not None
        assert state['attempts'] == 1 and state['charged_tokens'] == 100+32768
        assert worker.meter['unknown_usage_attempts'] == 1
    elif failure == 'mode':
        assert original.ledger.inflight is None and original.ledger.actual == 105
        assert state['attempts'] == 1 and state['charged_tokens'] == 105
    else:
        assert state['attempts'] == 0 and state['charged_tokens'] == 0
        assert worker.meter['http_attempts'] == 0 and original.ledger.attempts == 0


def test_native_tool_history_summarizes_and_review_does_not_lock_future_history(tmp_path):
    original, calls = adapter(tmp_path, arm='REF')
    llm = remote.build_native_llm(original)
    condenser = history.bind_ref_history(llm, directory=tmp_path/'native-history')
    events = [message('Initial issue: public code only.')]
    for index in range(42):
        events.extend(tool_round(index))
    conversation = SimpleNamespace(agent=SimpleNamespace(llm=llm), state=SimpleNamespace(events=events))
    history.bind_ref_conversation(conversation)
    view = View.from_events(events)
    # Scripted settled earlier agent responses establish which original inputs
    # were presented; this is not an invented world/test/permission event.
    trace = condenser._trace
    trace.note_view(view)
    trace.mark_presented(body(99))
    outcome = condenser.condense(view)
    assert isinstance(outcome, Condensation) and len(calls) == 1
    assert not set(e.id for e in events[:4]) & outcome.forgotten_event_ids
    assert not set(e.id for e in events[-2:]) & outcome.forgotten_event_ids
    assert outcome.summary.startswith(history.SUMMARY_LABEL)
    events.append(outcome)
    review = message('Fixed final self-review from the shared execution policy.')
    events.append(review)
    for index in range(42, 85):
        events.extend(tool_round(index))
    current = View.from_events(events)
    trace.note_view(current)
    trace.mark_presented(body(100))
    again = condenser.condense(current)
    assert isinstance(again, Condensation) and len(calls) == 2
    assert review.id in again.forgotten_event_ids
    assert original.ledger.attempts == 2 and original.ledger.decisions == 0


def test_unseen_input_and_other_member_sources_are_not_laundered(tmp_path):
    original, calls = adapter(tmp_path, arm='REF')
    llm = remote.build_native_llm(original)
    condenser = history.bind_ref_history(llm, directory=tmp_path/'native-history')
    events = [message('Initial public task')]
    for index in range(42):
        events.extend(tool_round(index))
    fresh = message('Newest observation that has not reached an agent response yet')
    events.append(fresh)
    conversation = SimpleNamespace(agent=SimpleNamespace(llm=llm), state=SimpleNamespace(events=events))
    history.bind_ref_conversation(conversation)
    result = condenser.condense(View.from_events(events))
    assert isinstance(result, Condensation) and fresh.id not in result.forgotten_event_ids
    assert len(calls) == 1
    with pytest.raises(ValueError, match='another conversation'):
        condenser._trace.begin([message('Foreign member private material')])
    assert len(calls) == 1


def test_token_pressure_triggers_before_eighty_events(tmp_path):
    original, calls = adapter(tmp_path, arm='REF')
    llm = remote.build_native_llm(original)
    condenser = history.bind_ref_history(llm, directory=tmp_path/'native-history')
    events = [message('Initial issue')]
    for index in range(12):
        events.extend(tool_round(index, text='public evidence '*1500))
    latest = message('Current public observation retained verbatim')
    events.append(latest)
    conversation = SimpleNamespace(agent=SimpleNamespace(llm=llm), state=SimpleNamespace(events=events))
    history.bind_ref_conversation(conversation)
    class Counter:
        effective_max_input_tokens = 98304
        def get_token_count(self, messages, tools=None, **kwargs):
            return sum(len(str(x.to_chat_dict(cache_enabled=False, vision_enabled=False,
                function_calling_enabled=True, force_string_serializer=True,
                send_reasoning_content=True))) for x in messages)
    outcome = condenser.condense(View.from_events(events), agent_llm=Counter())
    assert len(events) < 80 and isinstance(outcome, Condensation)
    assert latest.id not in outcome.forgotten_event_ids
    assert len(calls) == 1
