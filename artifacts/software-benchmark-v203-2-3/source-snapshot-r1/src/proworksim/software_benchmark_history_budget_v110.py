"""Same-pool auxiliary summary accounting; no additional agent opportunity."""
from __future__ import annotations

import copy
from pathlib import Path
import time

from .software_benchmark_managed_v064 import ManagedTeamBudget
from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_deepseek_adapter_v105 import RemoteEpisodeBoundary
from .storage import digest, json_bytes

VERSION = 'v110-same-pool-history-summary-accounting-r1'


class AlignedManagedTeamBudget(ManagedTeamBudget):
    def snapshot(self):
        value = super().snapshot()
        auxiliary = sum(row.get('usage_id') == 'condenser' for row in value['records'].values())
        value.update(decisions=value['decisions'] - auxiliary,
                     auxiliary_records=auxiliary)
        value['remaining_decisions'] = value['limits']['max_decisions'] - value['decisions']
        value.pop('state_sha256', None)
        value['state_sha256'] = digest(json_bytes(value))
        return value

    def open_summary(self, member, parent_call_id, call_id):
        with self._lock:
            parent = self._record(member, parent_call_id)
            if (parent.get('usage_id') == 'condenser' or parent['status'] != 'decision_consumed'
                    or call_id in self._state['records']
                    or not call_id.startswith(parent_call_id + ':condenser:')):
                self._fail('A summary needs its own unused identity under a live agent decision', integrity=True)
            if any(row['status'] in {'reserved', 'attempting'} for row in self._state['records'].values()):
                self._fail('An unsettled attempt cannot start an auxiliary summary', integrity=True)
            self._state['records'][call_id] = {
                'member': member, 'call_id': call_id, 'parent_call_id': parent_call_id,
                'status': 'decision_consumed', 'attempt_started': False,
                'usage_id': 'condenser', 'consumes_agent_decision': False,
            }
            return self.snapshot()


class SummaryTrace:
    """Only the condenser can open a source-bound, non-tool summary request."""
    def __init__(self, *, directory, owner_id, event_sink=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.owner_id, self.event_sink = owner_id, event_sink
        self.counter, self.pending, self.failure = 0, None, None
        self.event_provider, self.derived_events, self.conversation = None, {}, None
        self._bound_state, self._bound_provider = None, None
        self.presented_event_ids, self.current_view_ids = set(), ()

    def bind_conversation(self, conversation):
        if self.event_provider is not None or self.counter:
            raise ValueError('Bind private history to exactly one original conversation')
        self.conversation = conversation
        self.event_provider = lambda: conversation.state.events
        self._bound_state, self._bound_provider = conversation.state, self.event_provider

    def assert_bound_to(self, conversation):
        if (conversation is None or self.conversation is not conversation
                or self._bound_state is not conversation.state
                or self.event_provider is not self._bound_provider):
            raise ValueError('Private summary history lost its original conversation binding')

    def note_view(self, view):
        self.assert_bound_to(self.conversation)
        self.current_view_ids = tuple(event.id for event in view.events)

    def mark_presented(self, body):
        self.assert_bound_to(self.conversation)
        usage = body.get('usage') if isinstance(body, dict) else None
        if (not isinstance(body, dict) or not body.get('id') or not isinstance(usage, dict)
                or any(type(usage.get(key)) is not int or usage[key] < 0
                       for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                or usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']):
            raise ValueError('Only a settled actual model response establishes presentation')
        self.presented_event_ids.update(self.current_view_ids)
        receipt = {'version': VERSION, 'response_id': body['id'],
                   'response_sha256': digest(json_bytes(body)), 'usage': copy.deepcopy(usage),
                   'event_ids': list(self.current_view_ids), 'owner_id': self.owner_id,
                   'scope': 'this agent request only; not a world/test/permission event'}
        with (self.directory/'presentations.jsonl').open('a') as stream:
            import json
            stream.write(json.dumps(receipt, ensure_ascii=False)+'\n')

    def begin(self, events):
        if self.pending is not None or self.failure is not None or not events:
            raise RuntimeError('Summary history is unresolved, empty, or already active')
        if self.event_provider is None:
            raise ValueError('History summarization needs its actual private conversation binding')
        self.assert_bound_to(self.conversation)
        own = {event.id: event.model_dump(mode='json') for event in self.event_provider()}
        for event in events:
            if event.id in own:
                if event.model_dump(mode='json') != own[event.id]:
                    raise ValueError('A private source event changed before summarization')
            elif event.id in self.derived_events:
                from openhands.sdk.event.condenser import CondensationSummaryEvent
                if (not isinstance(event, CondensationSummaryEvent)
                        or event.summary != self.derived_events[event.id]):
                    raise ValueError('A derived summary changed its private source identity')
            else:
                raise ValueError('A summary cannot import events from another conversation')
        ids = [event.id for event in events]
        if len(ids) != len(set(ids)):
            raise ValueError('Summary history has duplicate source events')
        self.counter += 1
        folder = self.directory / f'summary-{self.counter:04d}'
        folder.mkdir(exist_ok=False)
        rows = [event.model_dump(mode='json') for event in events]
        source = write_new(folder/'sources.json', {
            'version': VERSION, 'owner_id': self.owner_id, 'events': rows,
            'event_ids': ids, 'source': 'this_conversation_view_only',
            'world_authority': False, 'marks_feedback_presented': False,
        })
        self.pending = {'folder': folder, 'sources': source, 'event_ids': ids,
                        'attempts': 0, 'owner_id': self.owner_id}
        return self.pending

    def finish(self, condensation):
        item = self.pending
        if item is None or item['attempts'] != 1:
            raise RuntimeError('A summary must have exactly one accounted attempt')
        if set(condensation.forgotten_event_ids) != set(item['event_ids']):
            raise ValueError('The condensation changed its admitted source set')
        receipt = write_new(item['folder']/'condensation.json', {
            'version': VERSION, 'sources': item['sources'],
            'condensation': condensation.model_dump(mode='json'),
            'derived_private_memory': True, 'world_authority': False,
            'marks_feedback_presented': False,
        })
        self.derived_events[condensation.summary_event.id] = condensation.summary
        self.pending = None
        if self.event_sink:
            self.event_sink('history_condensed_v110', {'receipt': receipt})
        return receipt

    def fail(self, error):
        self.failure = error
        if self.pending is not None:
            write_new(self.pending['folder']/'failure.json', {
                'version': VERSION, 'sources': self.pending['sources'],
                'error_type': type(error).__name__, 'error': str(error),
                'new_agent_action_permitted': False,
            })
        self.pending = None

    def assert_healthy(self):
        if self.failure is not None:
            raise self.failure


class RefSummaryGuard:
    """Retain the real REF adapter; a failed summary cannot silently retry as agent."""
    def __init__(self, delegate, trace):
        self.delegate, self.trace = delegate, trace

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def assert_healthy(self):
        self.trace.assert_healthy()
        return self.delegate.assert_healthy()

    def complete(self, request, usage_id='agent'):
        self.trace.assert_healthy()
        if usage_id == 'condenser':
            if self.trace.pending is None or request.get('tools'):
                raise ValueError('Only the source-bound condenser may issue a tool-free summary')
            self.trace.pending['attempts'] += 1
            if self.trace.pending['attempts'] != 1:
                raise RuntimeError('Summary automatic retries are not allowed')
        try:
            body = self.delegate.complete(request, usage_id)
            if usage_id == 'agent':
                self.trace.mark_presented(body)
            return body
        except BaseException as error:
            if usage_id == 'condenser':
                self.trace.failure = error
            raise


class ManagedSummaryAdapter:
    """Count, reserve and settle an auxiliary call in all three existing ledgers."""
    def __init__(self, worker, adapter, trace):
        self.worker, self.adapter, self.trace = worker, adapter, trace

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def _halt(self, status, reason, **details):
        try:
            self.worker._fail(status, reason, **details)
        except BaseException as error:
            self.trace.failure = error
            raise

    def complete(self, request, usage_id='condenser'):
        worker = self.worker
        context = worker.transport
        gate = getattr(context, 'native_dispatch_gate', None)
        runtime = getattr(gate, 'runtime', None)
        if (not worker._in_step or context._turn is not None or runtime is None
                or runtime.policies.get(worker.role_id) is not worker
                or runtime.team_budget is not worker.team_budget):
            raise ValueError('Summary needs the original live member runtime, outside its agent dispatch')
        context.bind_turn(worker.role_id, worker._association)
        try:
            return self._complete_bound(request, usage_id)
        finally:
            context.unbind_turn(worker.role_id, worker._association)

    def _complete_bound(self, request, usage_id):
        self.trace.assert_healthy()
        worker, trace, adapter = self.worker, self.trace, self.adapter
        pending = trace.pending
        if (usage_id != 'condenser' or request.get('tools') or pending is None
                or pending['attempts'] != 0 or pending['owner_id'] != worker.role_id
                or not worker._in_step or worker._completions != 0 or worker._pending is not None
                or not isinstance(worker.team_budget, AlignedManagedTeamBudget)):
            raise ValueError('A summary cannot act, cross member history, or create another opportunity')
        association = worker._association
        turn = worker.transport._turn
        if turn != {'member_id': worker.role_id, 'association': association}:
            raise ValueError('Summary lacks the exact bound live runner turn')
        if adapter.ledger.inflight is not None or adapter.halted:
            return self._halt('execution_integrity_error', 'Original model ledger is unresolved')
        pending['attempts'] = 1
        call_id = association['call_id'] + f':condenser:{trace.counter:04d}'
        measured = adapter.count(request)
        prompt = measured['prompt_tokens']
        if prompt > adapter.maximum_input_tokens:
            return self._halt('model_budget_exhausted', 'Summary input exceeds the shared context boundary')
        state = worker.team_budget.snapshot()
        available = min(worker.config['budget']['max_total_tokens'] - worker.meter['budget_accounted_tokens'],
                        state['available_tokens'], adapter.ledger.token_budget - adapter.ledger.actual)
        if available <= prompt:
            return self._halt('model_budget_exhausted', 'Original budget cannot admit the history summary')
        cap = min(request['max_tokens'], adapter.maximum_output_tokens, available-prompt)
        wire = {**copy.deepcopy(request), 'max_tokens': cap}
        reservation = {'request_bytes': len(json_bytes(wire)), 'input_token_reservation': prompt,
            'output_token_reservation': cap, 'token_reservation': prompt+cap,
            'cost_reservation_usd': 0, 'method': measured['method'],
            'reservation_kind': VERSION, 'usage_id': 'condenser'}
        memory = {'meter': worker.meter}
        worker._accountant._admit(memory, reservation, call_id)
        worker.team_budget.open_summary(worker.role_id, association['call_id'], call_id)
        worker.team_budget.reserve(worker.role_id, call_id, reservation)
        request_ref = write_new(pending['folder']/'request.json', {
            'request': wire, 'reservation': reservation, 'measurement': measured,
            'usage_id': 'condenser', 'call_id': call_id, 'parent': copy.deepcopy(association),
            'sources': pending['sources'], 'new_agent_decisions': 0,
        })
        deadline = worker.transport.native_dispatch_gate.deadline
        try:
            deadline.require_dispatch(worker.role_id, call_id)
        except BaseException as error:
            worker.team_budget.cleanup(worker.role_id, call_id)
            return self._halt('model_budget_exhausted', str(error), provider_dispatch_started=False)
        worker.meter['http_attempts'] += 1
        worker.team_budget.begin_attempt(worker.role_id, call_id)
        worker.team_budget.mark_dispatched(worker.role_id, call_id)
        before_attempts = adapter.ledger.attempts
        body, error = None, None
        try:
            body = adapter.complete(wire, 'condenser')
        except BaseException as caught:
            error = caught
            if (type(caught) is RemoteEpisodeBoundary and caught.before_dispatch_proven is True
                    and adapter.ledger.attempts == before_attempts and adapter.ledger.inflight is None):
                worker.team_budget.cancel_provider_before_dispatch(worker.role_id, call_id, str(caught))
                worker.meter['http_attempts'] -= 1
                write_new(pending['folder']/'pre-dispatch-refusal.json', {
                    'request': request_ref, 'reason': str(caught), 'provider_dispatch_started': False,
                    'actual_model_attempts': 0, 'tokens_charged': 0,
                })
                return self._halt('model_budget_exhausted', str(caught), provider_dispatch_started=False)
            # Bound violations can carry authoritative usage already settled in
            # the remote ledger. Never charge zero or silently request an agent call.
            if adapter.ledger.inflight is None and len(adapter.ledger.calls) > before_attempts:
                response_ref = adapter.ledger.calls[-1].get('response')
                if response_ref:
                    from .software_benchmark_candidates_v054 import checked
                    import json
                    body = json.loads(checked(response_ref).read_bytes())
        finally:
            deadline.returned(call_id, completed=error is None)
        accounting = worker._accountant._charge(memory, body, reservation)
        team_accounting = worker.team_budget.settle(worker.role_id, call_id, body)
        receipt = write_new(pending['folder']/'usage.json', {
            'version': VERSION, 'request': request_ref, 'usage_id': 'condenser',
            'call_id': call_id, 'parent_call_id': association['call_id'],
            'accounting': accounting, 'team_accounting': team_accounting,
            'response_id': body.get('id') if isinstance(body, dict) else None,
            'new_agent_decisions': 0, 'world_actions': 0, 'unix': time.time(),
        })
        worker._emit('history_summary_usage_v110', {'receipt': receipt})
        if error is not None or accounting['usage_status'] != 'reported':
            return self._halt('model_service_error', 'Summary generation lacks a complete valid outcome',
                              cause=type(error).__name__ if error else None)
        return body
