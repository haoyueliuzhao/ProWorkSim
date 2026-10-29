"""Do not consume more physical launches until both interfaces dispatch safely."""
from __future__ import annotations

import time
import threading

from . import software_benchmark_deepseek_budget_v089 as budget

VERSION = 'v093-two-interface-paid-request-startup-gate-r1'


def settled_paid_requests(slot_ids):
    with budget.ledger_read() as database:
        rows = database.execute('SELECT slot_id,request_id,settled_nanoyuan FROM requests WHERE '
            'slot_id IN ('+','.join('?' for _ in slot_ids)+') AND status=\'settled\' '
            'AND settled_nanoyuan>0 AND response_id IS NOT NULL AND usage_json IS NOT NULL',
            list(slot_ids)).fetchall()
    result = {}
    for slot, request, amount in rows:
        result.setdefault(slot, {'request_id': request, 'settled_nanoyuan': amount})
    return result


class StartupHealthGate:
    def __init__(self, rows, *, stop_event, event, snapshot, probe=settled_paid_requests):
        self.selected = {arm: next(row['slot_id'] for row in rows if row['arm'] == arm)
                         for arm in ('REF', 'PROJECT')}
        self.stop_event, self.event, self.snapshot, self.probe = stop_event, event, snapshot, probe
        self.scheduled, self.finished = set(), set()
        self.paid, self.passed, self.failed = {}, False, None
        self.last_poll = float('-inf')
        self.lock = threading.RLock()

    def ordered_rows(self, rows):
        selected = set(self.selected.values())
        return [next(row for row in rows if row['slot_id'] == self.selected[arm]) for arm in ('REF', 'PROJECT')] + [
            row for row in rows if row['slot_id'] not in selected]

    def poll(self, *, force=False):
        with self.lock:
            return self._poll(force=force)

    def _poll(self, *, force=False):
        if self.passed or self.failed is not None or not force and time.monotonic()-self.last_poll < 1:
            return
        self.last_poll = time.monotonic()
        self.paid = self.probe(tuple(self.selected.values()))
        if set(self.selected.values()) <= set(self.paid):
            self.passed = True
            self.event('startup_health_gate_passed', criterion='settled_paid_request_for_REF_and_PROJECT',
                actual_requests=self.paid, task_scores_used=False, generation_ceiling=48)
        elif any(slot not in self.paid for slot in self.finished):
            self.failed = 'initial_interface_finished_without_confirmed_paid_request'
            self.stop_event.set()
            self.event('startup_health_gate_failed', reason=self.failed,
                unstarted_physical_identities_preserved=True, task_scores_used=False)
        self.snapshot(self.state())

    def record(self, kind, **values):
        with self.lock:
            return self._record(kind, **values)

    def _record(self, kind, **values):
        slot = values.get('slot_id')
        if kind == 'generation_scheduled' and not self.passed:
            if slot not in self.selected.values() or slot in self.scheduled:
                raise PermissionError('No third or duplicate physical launch before both interfaces dispatch')
            self.scheduled.add(slot)
        elif kind == 'generation_finished' and slot in self.selected.values():
            self.finished.add(slot)
            self.poll(force=True)

    def limit(self, actual_ceiling, active):
        with self.lock:
            self.poll()
            if self.failed:
                return 0
            if self.passed:
                return min(48, actual_ceiling)
            remaining = 2-len(self.scheduled)
            return min(actual_ceiling, len(active)+remaining)

    def require_launch(self, slot):
        with self.lock:
            self.poll()
            if self.failed or not self.passed and slot not in self.selected.values():
                raise PermissionError('Physical launch is outside the unopened startup health gate')

    def state(self):
        return {'version': VERSION, 'selected': self.selected, 'passed': self.passed, 'failure': self.failed,
            'scheduled': sorted(self.scheduled), 'finished': sorted(self.finished),
            'confirmed_paid_requests': self.paid, 'task_scores_used': False,
            'maximum_unconfirmed_physical_launches': 2, 'after_pass_generation_ceiling': 48}
