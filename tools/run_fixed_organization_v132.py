"""One fair continuation scheduler with asynchronous original-candidate grading.

The original 250 identities, five ledgers and frozen member/model strategies
remain fixed. A drain stops new admissions; it does not cancel entered work.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import signal
import threading
import time

from proworksim import software_benchmark_scope_v132 as scope
from proworksim import software_benchmark_candidate_recovery_v132 as recovery
from proworksim.software_benchmark_alignment_contract_v131 import GROUP_IDS
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_group_admission_v132 import AdmissionDeferred, DrainControl, FairAdmission
from proworksim.software_benchmark_host_api_v132 import DeepSeekRuntime, budget_status
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate, manager_pressure
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v132-single-fair-original-team-continuation-r1'
DRAIN_FILE = scope.STATE_ROOT / 'admission-control.json'


def error_value(error):
    return {'type': type(error).__name__, 'message': str(error)}


def pressure_probe():
    host = scope.dispatch_view().physical_capacity()
    groups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    if len(groups) != 1:
        raise PermissionError('The current manager has no unique frozen cgroup')
    memory = manager_pressure(Path('/sys/fs/cgroup') / groups[0].lstrip('/'))
    return {'passed': host.get('passed') is True and memory['passed'], 'host': host, 'manager': memory}


def never_consumed_score(request_ref):
    request = scope.load(request_ref)
    path = Path(request['directory'])
    return (not any((path / name).exists() for name in ('capacity-claim.json', 'started.json', 'initial-container.json'))
            and not (scope.BATCH_ROOT / 'resource-claims' / (request['resource_key'] + '.json')).exists())


def cleanup_owned_parent(*, parent=None, record_path=None, coordinator_released=True):
    """Use the original exact-owned empty gate; refusal is retained, not forced."""
    approved, called = False, False
    try:
        if not coordinator_released:
            raise PermissionError('Recovery coordinator cleanup is not fully proven')
        if parent is None:
            from proworksim import software_benchmark_api_parent_v131 as parent
        parent.approved()
        approved = True
        called = True
        release = parent.stop_empty()
        outcome = {'status': 'released', 'parent_release': release, 'cleanup_deferred': False}
    except Exception as error:
        outcome = {'status': 'cleanup_deferred', 'cleanup_deferred': True,
            'error': error_value(error), 'owned_parent_preserved_for_review': True}
    outcome.update(version=VERSION, original_root_grant_verified=approved, stop_empty_called=called,
        force_stop=False, scope='original_exact_owned_empty_parent_gate',
        coordinator_release_proven=coordinator_released)
    target = Path(record_path) if record_path is not None else scope.API_ROOT / 'aggregate-parent-cleanup.json'
    try:
        receipt = scope.retain(target, outcome)
        return {**outcome, 'record': receipt}
    except Exception as error:
        return {**outcome, 'record': None, 'audit_write_error': error_value(error)}


class Coordinator:
    """The manager owns one pool per actual resource class, never five copies."""

    def __init__(self, *, runtime, implementation, grading, memory, admission, continuation, qualifications,
                 output=None, cash_status=budget_status):
        self.runtime, self.implementation, self.grading = runtime, implementation, grading
        self.memory, self.admission = memory, admission
        self.continuation, self.qualifications, self.cash_status = continuation, qualifications, cash_status
        self.output = Path(output or scope.API_ROOT)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock, self.event_lock = threading.RLock(), threading.RLock()
        self.stop_new_generation = threading.Event()
        self.stop_new_scoring = threading.Event()
        self.entered_stop = threading.Event()  # Never set by admission drain.
        self.pending = {group: deque() for group in GROUP_IDS}
        self.healthy = {group: bool(runtime.for_group(group).settled_route_witnesses()) for group in GROUP_IDS}
        self.finished, self.exceptions, self.deferred = {}, {}, {}
        self.generation, self.preparation, self.scores = {}, {}, {}
        self.score_queue = deque()
        self.money = {}
        self.completed_scores, self.delivery_endpoints = {}, {}
        self.execution_phase = 'normal'
        self.normal_phase_complete = False
        self.normal_phase_closure = None
        self.historical_started = False
        self.rotation = 0
        self.last_progress = 0.0
        for row in continuation['eligible_first_generation']:
            if self._qualified(row):
                self.pending[row['organization_id']].append(row)
            else:
                self.deferred[row['slot_id']] = {'row': row, 'reason': 'original_environment_not_qualified'}
        for group in GROUP_IDS:
            self.admission.register_pending(group, [row['slot_id'] for row in self.pending[group]])

    def _qualified(self, row):
        value = self.qualifications.get(row['instance_id'])
        if not isinstance(value, dict) or row['instance_id'] == 'psf__requests-1766':
            return False
        if value.get('status') == 'qualified' and isinstance(value.get('qualification'), dict):
            value = scope.load(value['qualification'])
        if set(value) == {'path', 'sha256', 'bytes'}:
            value = scope.load(value)
        return value.get('status') != 'not_qualified' and value.get('passed') is True

    def event(self, kind, **values):
        with self.event_lock, (self.output / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'version': VERSION, 'unix': time.time(), 'kind': kind, **values}) + '\n')

    def drain(self, reason, *, scoring=False):
        self.stop_new_generation.set()
        if scoring:
            self.stop_new_scoring.set()
        self.event('admission_draining', reason=reason, cancel_entered_work=False, scoring_paused=scoring)

    def _generation(self, row):
        unentered = False
        try:
            if not scope.never_consumed(row):
                raise PermissionError('A supposedly first-generation identity was already consumed')
            self.admission.require_start(row)
            view = self.runtime.for_group(row['organization_id'])

            def ready(member_row, output):
                self.admission.ready(member_row)
                return view.transport_factory(member_row, output)

            ref = self.implementation.run_episode(row, view.logical_resident(), stop_event=self.entered_stop,
                api_transport_factory=ready)
            return {'status': 'finished', 'row': row, 'result': ref}
        except AdmissionDeferred as error:
            unentered = scope.never_consumed(row)
            if not unentered:
                raise PermissionError('Admission deferral consumed an original object or request') from error
            return {'status': 'deferred', 'row': row, 'reason': str(error)}
        except scope.ResourceBusy as error:
            unentered = scope.never_consumed(row)
            if not unentered:
                raise
            return {'status': 'deferred', 'row': row, 'reason': str(error)}
        finally:
            self.admission.leave(row, unentered=unentered)

    def _prepare(self, row, result_ref, *, historical=False):
        def prepare():
            original = scope.load(result_ref)
            ref = result_ref
            if historical and original.get('status') != 'closed':
                if original.get('error') != recovery.EXPECTED_ERROR:
                    return {'status': 'original_unknown_preserved', 'row': row,
                            'original_result': result_ref, 'original_error': original.get('error')}
                output = recovery.DEFAULT_OUTPUT / str(row['slot_index'])
                if (output / 'result.json').exists():
                    ref = reference(output / 'result.json')
                    recovery.validate_recovered_result(ref, original_plan_ref=self.continuation['original_plan'])
                else:
                    ref = recovery.recover_closed_candidate(row, result_ref, output,
                        original_plan_ref=self.continuation['original_plan'])
            value = scope.load(ref)
            if (value.get('shared_integrity_fault') or value.get('batch_stop_required') is True
                    or value.get('failure_scope') == 'global'):
                raise PermissionError('A generation reported a shared identity/integrity fault: ' + str(
                    value.get('shared_integrity_fault') or value.get('failure_scope') or 'batch_stop_required'))
            record = {'status': value.get('status'), 'row': row, 'result': ref,
                      'historical_measurement_recovery': historical and ref != result_ref}
            if value.get('status') == 'closed' and self._qualified(row):
                record['code_request'] = self.grading.prepare_score(ref, endpoint='code')
            return record
        return self.memory.run_heavy(row['slot_id'], 'recover_or_prepare_original_candidate', prepare)

    def _score(self, row, result_ref, request_ref, endpoint):
        try:
            completion = self.grading.run_request(request_ref, stop_event=self.entered_stop)
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            completion = {'status': 'technical_unknown', 'error': error_value(error)}
        untouched = never_consumed_score(request_ref)
        quiet = untouched or self.grading.trustworthy_cleanup(request_ref) is True
        value = {'row': row, 'generation_result': result_ref, 'request': request_ref,
                 'endpoint': endpoint, 'completion': completion, 'cleanup_proven': quiet}
        if not quiet:
            value['shared_cleanup_failure'] = True
        elif endpoint == 'code' and completion.get('status') != 'not_started_cancelled':
            try:
                value['delivery'] = self.memory.run_heavy(row['slot_id'], 'delivery_evidence_after_code_score',
                    lambda: self.grading.delivery_disposition(result_ref, request_ref))
            except Exception as error:
                value['delivery'] = {'status': 'technical_unknown', 'resolved': None, 'error': error_value(error)}
        return value

    def _record_prepared(self, value):
        row = value['row']
        self.finished[row['slot_id']] = value
        path = self.output / 'generation-records' / (str(row['slot_index']) + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new(path, value)
        usage = self.runtime.usage_for_slot(row) if hasattr(self.runtime, 'usage_for_slot') else self.runtime.for_group(
            row['organization_id']).usage_for_slot(row)
        usage_path = self.output / 'usage-records' / (str(row['slot_index']) + '.json')
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        write_new(usage_path, {'version': VERSION, 'row': row, 'result_record': reference(path), **usage,
            'same_original_attempt_cost_not_charged_twice': True})
        if value.get('code_request'):
            self.score_queue.append((row, value['result'], value['code_request'], 'code'))

    def _record_exception(self, stage, row, error):
        value = {'stage': stage, 'row': row, 'error': error_value(error), 'automatic_retry': False}
        self.exceptions.setdefault(row['slot_id'], []).append(value)
        self.event('task_exception_isolated', **value)
        if isinstance(error, PermissionError):
            self.drain('public_identity_or_authority_failure')

    def _collect(self, preparations):
        for future, row in list(self.generation.items()):
            if not future.done():
                continue
            del self.generation[future]
            try:
                value = future.result()
                if value['status'] == 'deferred':
                    self.pending[row['organization_id']].appendleft(row)
                    self.event('unentered_deferred', slot_id=row['slot_id'], reason=value['reason'])
                else:
                    self.preparation[preparations.submit(self._prepare, row, value['result'])] = row
            except BaseException as error:
                self._record_exception('generation', row, error)
        for future, row in list(self.preparation.items()):
            if not future.done():
                continue
            del self.preparation[future]
            try:
                self._record_prepared(future.result())
            except BaseException as error:
                self._record_exception('candidate_preparation', row, error)
        for future, item in list(self.scores.items()):
            if not future.done():
                continue
            del self.scores[future]
            row, result_ref, request_ref, endpoint = item
            try:
                value = future.result()
                key = row['slot_id'] + ':' + endpoint
                self.completed_scores[key] = value
                folder = self.output / 'score-records'
                folder.mkdir(parents=True, exist_ok=True)
                write_new(folder / (str(row['slot_index']) + '-' + endpoint + '.json'), value)
                if value.get('shared_cleanup_failure'):
                    self.drain('scoring_cleanup_not_proven', scoring=True)
                delivery = value.get('delivery')
                if delivery:
                    self.delivery_endpoints[row['slot_id']] = delivery
                    if delivery.get('scoring_request'):
                        self.score_queue.append((row, result_ref, delivery['scoring_request'], 'delivery'))
            except BaseException as error:
                self._record_exception('scoring', row, error)

    def _admit(self, executor):
        control = self.admission.control.read()
        for group in GROUP_IDS:
            money = self.cash_status(group)
            self.money[group] = money
            if not self.healthy[group]:
                self.healthy[group] = bool(self.runtime.for_group(group).settled_route_witnesses())
            allowed = money.get('can_start_generation') is True and not self.stop_new_generation.is_set()
            self.admission.set_group_status(group, healthy=self.healthy[group], can_dispatch=allowed)
            if money.get('state') in {'cash_exhausted', 'shared_halted'}:
                for row in self.pending[group]:
                    self.deferred[row['slot_id']] = {'row': row, 'reason': money['state']}
                self.admission.remove_pending(group, [row['slot_id'] for row in self.pending[group]])
                self.pending[group].clear()
        if self.stop_new_generation.is_set():
            return
        # Each pass enters at most one per group; the gate also enforces total
        # fair targets and the rotating minimum occupancy, including startups.
        admitted = True
        while admitted and len(self.generation) < scope.MAX_GENERATIONS:
            admitted = False
            ordered = GROUP_IDS[self.rotation:] + GROUP_IDS[:self.rotation]
            for group in ordered:
                if not self.pending[group] or control.blocks(group):
                    continue
                row = self.pending[group][0]
                try:
                    accepted = self.admission.try_enter(row)
                except AdmissionDeferred:
                    continue
                if accepted:
                    self.pending[group].popleft()
                    self.generation[executor.submit(self._generation, row)] = row
                    self.rotation = (GROUP_IDS.index(group) + 1) % len(GROUP_IDS)
                    admitted = True

    def progress(self, *, final=False):
        now = time.monotonic()
        if not final and now - self.last_progress < 5:
            return
        self.last_progress = now
        value = {'version': VERSION, 'unix': time.time(), 'phase': 'closed' if final else 'running',
            'execution_phase': self.execution_phase, 'normal_phase_complete': self.normal_phase_complete,
            'normal_phase_closure': self.normal_phase_closure, 'historical_started': self.historical_started,
            'historical_pending': 0 if self.historical_started else len(self.continuation['original_results']),
            'generation_active': len(self.generation), 'candidate_preparation_active_or_queued': len(self.preparation),
            'scoring_active': len(self.scores), 'scoring_pending': len(self.score_queue),
            'generation_pending': {group: len(rows) for group, rows in self.pending.items()},
            'prepared_statuses': dict(Counter(item['status'] for item in self.finished.values())),
            'scores_completed': len(self.completed_scores), 'task_exceptions': len(self.exceptions),
            'deferred_unentered': len(self.deferred), 'admission': self.admission.snapshot(),
            'host_memory': self.memory.snapshot(), 'cash_by_group': copy.deepcopy(self.money),
            'draining_new_generation': self.stop_new_generation.is_set(),
            'draining_new_scoring': self.stop_new_scoring.is_set(), 'entered_tasks_cancelled_by_drain': False,
            'new_diagnostic_calls': 0, 'new_neutral_calls': 0, 'old_attempts_replayed': 0}
        atomic_write(self.output / 'progress.json', json_bytes(value))
        return value

    def execute(self):
        with ThreadPoolExecutor(max_workers=scope.MAX_GENERATIONS, thread_name_prefix='v132-team') as generations, \
                ThreadPoolExecutor(max_workers=2, thread_name_prefix='v132-prepare') as preparations, \
                ThreadPoolExecutor(max_workers=scope.MAX_GRADERS, thread_name_prefix='v132-score') as scorers:
            while True:
                self._collect(preparations)
                try:
                    if self.execution_phase == 'normal':
                        self._admit(generations)
                except Exception as error:
                    self.drain('admission_control_failure')
                    self.event('admission_error', error=error_value(error))
                while self.score_queue and len(self.scores) < scope.MAX_GRADERS and not self.stop_new_scoring.is_set():
                    item = self.score_queue.popleft()
                    self.scores[scorers.submit(self._score, *item)] = item
                try:
                    control = self.admission.control.read()
                    runnable = any(self.pending[group] and not control.blocks(group) for group in GROUP_IDS)
                except Exception as error:
                    self.drain('invalid_admission_control')
                    self.event('admission_error', error=error_value(error))
                    runnable = False
                if not self.generation and not self.preparation and not self.scores:
                    if (self.execution_phase == 'normal' and not any(self.pending.values())
                            and not self.stop_new_scoring.is_set()
                            and not self.score_queue):
                        # Explicit phase barrier: lack of a runnable row is
                        # insufficient; no normal pending identity or endpoint
                        # may be left behind by drain/pressure/common failure.
                        self.normal_phase_complete = True
                        self.normal_phase_closure = write_new(self.output / 'normal-phase-closed.json', {
                            'version': VERSION, 'normal_planned_first_attempts': len(self.continuation['eligible_first_generation']),
                            'generation_pending': 0, 'generation_active': 0, 'candidate_preparation_pending': 0,
                            'scoring_pending': 0, 'scoring_active': 0, 'scores_terminal': len(self.completed_scores),
                            'delivery_endpoints_terminal': len(self.delivery_endpoints),
                            'not_started_terminal': copy.deepcopy(self.deferred),
                            'task_exceptions_terminal': copy.deepcopy(self.exceptions),
                            'before_any_historical_recovery': True, 'unix': time.time()})
                        self.execution_phase = 'historical_recovery'
                        self.historical_started = True
                        self.event('normal_phase_closed_before_historical_recovery', proof=self.normal_phase_closure)
                        # The pre-existing score9000 lane is consumed only now;
                        # it was not released or borrowed by normal tasks.
                        for item in sorted(self.continuation['original_results'], key=lambda value: value['row']['slot_index']):
                            self.preparation[preparations.submit(self._prepare, item['row'], item['result'], historical=True)] = item['row']
                        if self.preparation:
                            continue
                    if (not runnable or self.stop_new_generation.is_set()) and (
                            not self.score_queue or self.stop_new_scoring.is_set()):
                        break
                self.progress()
                time.sleep(.2)
        for group in GROUP_IDS:
            for row in self.pending[group]:
                self.deferred[row['slot_id']] = {'row': row, 'reason': 'admission_drain_without_entry'}
        value = {'version': VERSION, 'plan': self.continuation['original_plan'],
            'continuation': reference(scope.CONTINUATION_FILE), 'finished_unix': time.time(),
            'execution_phase': self.execution_phase, 'normal_phase_complete': self.normal_phase_complete,
            'normal_phase_closure': self.normal_phase_closure, 'historical_started': self.historical_started,
            'historical_pending': [] if self.historical_started else copy.deepcopy(self.continuation['original_results']),
            'generation_records': {slot: {key: item[key] for key in ('status', 'result', 'original_result') if key in item}
                                   for slot, item in self.finished.items()},
            'task_exceptions': self.exceptions, 'deferred': self.deferred,
            'deferred_score_requests': [item[2] for item in self.score_queue],
            'delivery_endpoints': self.delivery_endpoints, 'cash_by_group': self.money,
            'new_neutral_calls': 0, 'new_diagnostic_calls': 0, 'old_attempts_replayed': 0}
        write_new(self.output / 'run-summary.json', value)
        self.progress(final=True)
        return value


def run():
    from proworksim.software_benchmark_episode_v132 import build_episode
    from proworksim.software_benchmark_grading_recovery_v132 import factory
    scope.require_allowed('v132.run')
    limits = scope.verify_host_limits()
    continuation = scope.continuation()
    if (scope.API_ROOT / 'execution-started.json').exists():
        raise PermissionError('A consumed coordinator identity cannot silently restart')
    lease = scope.reserve_api_coordinator()
    memory = HostMemoryGate(maximum=2)
    coordinator, old_signals, result = None, {}, None
    try:
        runtime = DeepSeekRuntime().initialize_for_run()
        control = DrainControl(DRAIN_FILE, batch_root=scope.STATE_ROOT, groups=GROUP_IDS,
                               maximum=scope.MAX_GENERATIONS)
        admission = FairAdmission(GROUP_IDS, control=control, maximum=scope.MAX_GENERATIONS,
            maximum_startups=scope.MAX_STARTUPS, pressure_probe=pressure_probe)
        implementation = build_episode(scope=scope, guard=scope.require_allowed, host_memory=memory,
                                       admission_check=admission.require_start)
        grading = factory(watchdog_guard=lambda *_args, **_identity: None)
        qualifications = grading.prepare_environment_qualifications()
        if qualifications.get('controls'):
            raise PermissionError('Continuation cannot create diagnostic or environment control repeats')
        preparation = scope.load(reference(scope.PREPARATION_QUALIFICATION_FILE))
        if preparation.get('passed') is not True:
            raise PermissionError('The original four-member diagnostic has not already passed')
        coordinator = Coordinator(runtime=runtime, implementation=implementation, grading=grading,
            memory=memory, admission=admission, continuation=continuation,
            qualifications=qualifications['qualifications'])
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_signals[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda number, _frame: coordinator.drain('signal_' + str(number)))
        write_new(scope.API_ROOT / 'execution-started.json', {'version': VERSION,
            'authorization': reference(scope.AUTH_FILE), 'source_index': reference(scope.SOURCE_FILE),
            'continuation': reference(scope.CONTINUATION_FILE), 'host_limits': limits,
            'original_preparation': reference(scope.PREPARATION_QUALIFICATION_FILE),
            'original_ledgers_preserved': True, 'cash_cap_by_group_CNY': {g: '100.00' for g in GROUP_IDS},
            'new_neutral_calls': 0, 'new_diagnostic_calls': 0, 'new_environment_controls': 0})
        result = coordinator.execute()
        return result
    finally:
        for sig, handler in old_signals.items():
            signal.signal(sig, handler)
        cleanup_errors, released = [], None
        try:
            memory.close()
        except Exception as error:
            cleanup_errors.append({'step': 'host_memory_close', **error_value(error)})
        try:
            released = scope.release_api_coordinator(lease)
        except Exception as error:
            cleanup_errors.append({'step': 'coordinator_release', **error_value(error)})
        cleanup = cleanup_owned_parent(coordinator_released=released is not None and not cleanup_errors)
        finalization = {'version': VERSION, 'coordinator_release': released,
            'cleanup_errors': cleanup_errors, 'aggregate_parent': cleanup,
            'entered_tasks_cancelled': False, 'original_experiment_error_not_replaced': True}
        try:
            final_ref = scope.retain(scope.API_ROOT / 'coordinator-finalization.json', finalization)
            if isinstance(result, dict):
                result['runtime_finalization'] = final_ref
        except Exception:
            # Preserve an original runtime exception even if the evidence
            # filesystem itself is unavailable during finalization.
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
