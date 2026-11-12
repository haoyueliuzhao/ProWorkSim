"""Explicit fresh-conversation rejection handling for the v117 comparison.

REF uses the source-bound SDK marker repair already checked in v114. PROJECT
rejects invalid JSON/schema before returning an SDK response, and retains its
existing later-opportunity recovery. Neither path repairs or replays an action.
"""
from __future__ import annotations

import copy
from pathlib import Path
from types import MethodType

from .software_benchmark_candidates_v054 import write_new
from .software_benchmark_rejected_history_v114 import (
    SDKRejectedHistory, build_native_llm as _build_native_llm,
    bind_native_history as _bind_native_history,
)
from .storage import digest, json_bytes

VERSION = 'v117-explicit-same-budget-rejected-history-r1'


def build_native_llm(adapter, *, normalization_folder, rejected_history_folder):
    """Before native Conversation construction; fresh REF adapters only."""
    return _build_native_llm(adapter, normalization_folder=normalization_folder,
                             rejected_history_folder=rejected_history_folder)


def bind_native_history(adapter, conversation):
    """After bind_ref_conversation and before its first send/run."""
    return _bind_native_history(adapter, conversation)


def bind_project_worker(worker):
    """Install a source receipt around existing strict managed rejections.

    Call after the real fresh worker/history construction, before the first
    scheduler step. The original parser, public feedback and SDK events remain
    authoritative; no malformed assistant is injected into the Conversation.
    """
    from openhands.sdk import LocalConversation
    from .software_benchmark_history_budget_v110 import AlignedManagedTeamBudget
    adapter = worker.transport.owner.adapter
    conversation = worker.conversation
    if (hasattr(worker, '_rejected_history_v117') or adapter.arm != 'PROJECT'
            or not isinstance(conversation, LocalConversation)
            or not isinstance(worker.team_budget, AlignedManagedTeamBudget)
            or adapter.ledger.attempts or adapter.ledger.inflight is not None
            or worker.meter['decisions'] or worker._in_step or worker._done is not None):
        raise ValueError('Bind rejected history once to a fresh original PROJECT worker')
    worker._history_trace_v110.assert_bound_to(conversation)
    folder = Path(worker.directory)/'rejected-history-v117'
    folder.mkdir(parents=True, exist_ok=False)
    original = worker._format_rejection
    receipts = []

    def checked_rejection(self, error):
        self._history_trace_v110.assert_bound_to(conversation)
        body = copy.deepcopy(self._last_body)
        if (self.conversation is not conversation or error.status != 'model_format_error'
                or self._executions != 0 or self._pending is not None
                or not isinstance(body, dict) or not body.get('id')
                or adapter.ledger.inflight is not None or not adapter.ledger.calls):
            raise ValueError('PROJECT rejection lacks an unexecuted settled original response')
        settled = adapter.ledger.calls[-1]
        if settled.get('usage_id') != 'agent' or settled.get('response_id') != body['id']:
            raise ValueError('PROJECT rejection does not belong to its original agent response')
        budgets = (copy.deepcopy(self.meter), adapter.ledger.snapshot(), self.team_budget.snapshot())
        events_before = len(conversation.state.events)
        result = original(error)
        if (self._last_body != body or self._executions != 0 or self._pending is not None
                or budgets != (self.meter, adapter.ledger.snapshot(), self.team_budget.snapshot())
                or result.get('kind') != 'protocol_rejection' or result.get('executed') is not False):
            raise ValueError('A rejected action changed its original usage, response or execution')
        added = list(conversation.state.events)[events_before:]
        from openhands.sdk.event.llm_convertible import MessageEvent
        if (len(added) != 1 or not isinstance(added[0], MessageEvent)
                or added[0].llm_message.role != 'user'):
            raise ValueError('Managed rejection must append only its real public feedback')
        receipt = {'version': VERSION, 'arm': 'PROJECT', 'worker_id': self.role_id,
            'conversation_id': str(conversation.id), 'response_id': body['id'],
            'response_sha256': digest(json_bytes(body)), 'original_response': settled['response'],
            'decision_id': self._association['call_id'], 'feedback_event_id': added[0].id,
            'feedback_event_sha256': digest(json_bytes(added[0].model_dump(mode='json'))),
            'original_response_changed': False, 'tool_action_executed': False,
            'automatic_retry': False, 'additional_budget': 0,
            'original_decision_and_usage_retained': True,
            'recovery_only_on_a_later_budgeted_opportunity': True,
            'SDK_malformed_marker_fabricated': False}
        write_new(folder/(digest(self._association['call_id'].encode())+'.json'), receipt)
        receipts.append(receipt)
        return result

    worker._format_rejection = MethodType(checked_rejection, worker)
    worker._rejected_history_v117 = {'version': VERSION, 'receipts': receipts,
        'conversation': conversation, 'strict_pre_SDK_rejection_retained': True}
    return worker


__all__ = ['VERSION', 'SDKRejectedHistory', 'build_native_llm',
           'bind_native_history', 'bind_project_worker']
