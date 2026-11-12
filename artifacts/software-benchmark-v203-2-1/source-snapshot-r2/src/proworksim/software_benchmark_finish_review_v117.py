"""One common, budgeted final-review policy for REF and managed PROJECT.

This module never dispatches a model or accepts a delivery.  A PROJECT finish
request is offered for review before it becomes an accepted terminal control.
"""
from __future__ import annotations

import copy
import math
import time

from .software_benchmark_execution_guidance_v117 import FINISH_REVIEW
from .software_benchmark_native_execution_v057 import recovery_admission
from .storage import digest

VERSION = 'v117-shared-single-final-review-r1'
MAX_FINISH_REVIEWS = 1
SENDER = 'v117-execution-policy'
DONE_DESCRIPTION = (
    'Request completion of your current single-member work. The first valid request may receive '
    'one final self-review in this same conversation, within the remaining original budget and '
    'deadlines; its response explicitly says whether completion is deferred. A later accepted '
    'request ends the work. This never tests, fixes, submits, approves or creates another member '
    'automatically. Do not treat a deferred request as accepted completion.')


def policy_manifest():
    return {'version': VERSION, 'maximum_finish_reviews': MAX_FINISH_REVIEWS,
            'message': FINISH_REVIEW, 'message_sha256': digest(FINISH_REVIEW.encode()),
            'same_original_budget': True, 'same_original_deadlines': True,
            'additional_agents': 0, 'automatic_delivery': False,
            'admission': 'The common v057 recovery_admission, including full output reservation.',
            'REF_stuck_corrections_unchanged': 2,
            'PROJECT_stuck_corrections_added': 0}


def require_known_usage(snapshot):
    if (snapshot.get('complete_actual_tokens') is None
            or snapshot['complete_actual_tokens'] != snapshot.get('known_actual_tokens')
            or snapshot.get('inflight') is not None
            or snapshot.get('uncertain_reserved_tokens', 0)):
        raise RuntimeError('A final review or accepted finish cannot conceal uncertain usage')


class FinishReviewPolicy:
    """Per-episode state; only a fresh accepted offer consumes the one review."""

    def __init__(self, *, started, limits, clock=time.monotonic, event_sink=None):
        self.started, self.limits = copy.deepcopy(started), copy.deepcopy(limits)
        for key in ('started', 'soft_at', 'hard_at'):
            value = self.started.get(key)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Review needs the original finite absolute deadlines')
        if not self.started['started'] < self.started['soft_at'] <= self.started['hard_at']:
            raise ValueError('The original review deadlines are not ordered')
        for key, maximum in (('soft_at', 'soft_seconds'), ('hard_at', 'hard_seconds')):
            if self.started[key] - self.started['started'] > self.limits[maximum]:
                raise ValueError('Review cannot extend the original episode lifetime')
        self.clock, self.event_sink = clock, event_sink
        self.used, self.events, self.intent_ids = 0, [], set()

    def _emit(self, kind, **values):
        record = {'version': VERSION, 'kind': kind, **copy.deepcopy(values)}
        self.events.append(record)
        if self.event_sink is not None:
            self.event_sink(copy.deepcopy(record))
        return record

    def offer(self, snapshot, *, intent_id, reason):
        """Classify an actual, settled finish request without changing any meter."""
        if not isinstance(intent_id, str) or not intent_id or intent_id in self.intent_ids:
            raise ValueError('A finish intent must have a new actual model-tool identity')
        if not isinstance(reason, str) or not reason:
            raise ValueError('The actual finish reason is required')
        require_known_usage(snapshot)
        refusal = recovery_admission(snapshot, started=self.started,
                                     limits=self.limits, now=self.clock())
        if self.used >= MAX_FINISH_REVIEWS:
            refusal = 'opportunity_limit'
        self.intent_ids.add(intent_id)
        if refusal:
            return self._emit('finish_review_not_offered', intent_id=intent_id,
                permitted=False, reason=refusal, accepted_finish=True,
                opportunities_used=self.used, original_finish_reason=reason)
        self.used += 1
        return self._emit('finish_review_prepared', intent_id=intent_id, permitted=True,
            review_index=self.used, message=FINISH_REVIEW,
            message_sha256=digest(FINISH_REVIEW.encode()), original_finish_reason=reason,
            accepted_finish=False, ledger_reset=False, additional_budget=0, additional_agents=0)

    def snapshot(self):
        return {'definition': policy_manifest(), 'finish_reviews': self.used,
                'events': copy.deepcopy(self.events),
                'started': copy.deepcopy(self.started), 'limits': copy.deepcopy(self.limits)}
