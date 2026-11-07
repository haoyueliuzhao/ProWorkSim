"""Fresh three-arm pilot with fair generation and asynchronous candidate grading.

One 400-CNY ledger; local unknowns remain isolated. Shared ownership, cleanup
and accounting faults drain new admissions while entered tasks settle.
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

from proworksim import software_benchmark_scope_v143 as scope
from proworksim.software_benchmark_alignment_contract_v141 import GROUP_IDS
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_group_admission_v132 import AdmissionDeferred, DrainControl, FairAdmission
from proworksim.software_benchmark_host_api_v143 import DeepSeekRuntime, budget_status
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate, manager_pressure
from proworksim.software_benchmark_usage_metrics_v064 import call_totals
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v143-diagnostic-primary-error-preserving-pilot-r1'
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


def official_endpoint(request_ref, completion, *, cleanup_proven):
    """Read only this request's signed-by-identity scorer receipt, never cache status."""
    request = scope.load(request_ref)
    folder = Path(request['directory'])
    path = folder/'receipt.json'
    if not cleanup_proven or completion.get('returncode') != 0 or not path.is_file():
        return {'status': 'technical_unknown', 'resolved': None,
                'reason': 'score_completion_cleanup_or_receipt_missing', 'completion_status': completion.get('status')}
    ref = reference(path)
    receipt = scope.load(ref)
    identity = scope.load(receipt['identity'])
    if (receipt.get('resource_key') != request.get('resource_key')
            or receipt.get('slot_id') != request.get('slot_id')
            or identity.get('request') != request_ref
            or identity.get('candidate_lock') != request.get('candidate_lock')
            or identity.get('endpoint') != ('delivery' if request['resource_key'].startswith('delivery-score-') else 'code')):
        raise PermissionError('Official scoring receipt changed its request or candidate identity')
    known = receipt.get('status') == 'official_report' and type(receipt.get('resolved')) is bool
    return {'status': 'scored' if known else 'technical_unknown',
            'resolved': receipt['resolved'] if known else None, 'receipt': ref,
            'reason': None if known else receipt.get('scoring_validity', receipt.get('error', receipt.get('status')))}




class Coordinator:
    """One generation pool, one startup pool and one scorer pool for all arms."""

    def __init__(self, *, runtime, implementation, grading, memory, admission, plan, qualifications,
                 output=None, cash_status=budget_status):
        self.runtime, self.implementation, self.grading = runtime, implementation, grading
        self.memory, self.admission = memory, admission
        self.plan, self.qualifications, self.cash_status = plan, qualifications, cash_status
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
        self.usage_records = {}
        self.tls_lock = threading.Lock()
        self.rotation = 0
        self.last_progress = 0.0
        for row in plan['rows']:
            if self._qualified(row):
                self.pending[row['organization_id']].append(row)
            else:
                self.deferred[row['slot_id']] = {'row': row, 'reason': 'environment_not_qualified'}
        for group in GROUP_IDS:
            self.admission.register_pending(group, [row['slot_id'] for row in self.pending[group]])

    def _qualified(self, row):
        value = self.qualifications.get(row['instance_id'])
        if not isinstance(value, dict):
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
                raise PermissionError('Consumed generation capacity lacks a completion proof') from error
            return {'status': 'deferred', 'row': row, 'reason': str(error)}
        except Exception as error:
            # The episode wrapper normally returns a scoped unknown with its
            # cleanup receipt. A raw exception after entry proves neither.
            if not scope.never_consumed(row):
                raise PermissionError('Entered generation failed without its cleanup receipt') from error
            raise
        finally:
            self.admission.leave(row, unentered=unentered)

    def _prepare(self, row, result_ref):
        def prepare():
            value = scope.load(result_ref)
            quiet_ref = value.get('quiescence')
            quiet = scope.load(quiet_ref) if isinstance(quiet_ref, dict) else {}
            if (quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
                    or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False):
                raise PermissionError('Generation cleanup is not fully proven')
            if (value.get('shared_integrity_fault') or value.get('batch_stop_required') is True
                    or value.get('failure_scope') == 'global'):
                raise PermissionError('A generation reported a shared identity or accounting fault')
            record = {'status': value.get('status'), 'row': row, 'result': result_ref,
                      'fresh_attempt': True, 'automatic_retry': False}
            if value.get('status') != 'closed':
                record['generation_unknown_reason'] = value.get('error') or value.get('closure_reason') or value.get('status')
            if value.get('status') == 'closed' and self._qualified(row):
                record['code_request'] = self.grading.prepare_score(result_ref, endpoint='code')
            return record
        return self.memory.run_heavy(row['slot_id'], 'prepare_locked_pilot_candidate', prepare)

    def _score(self, row, result_ref, request_ref, endpoint):
        try:
            if row['instance_id'] in {'psf__requests-1766', 'psf__requests-1921'}:
                with self.tls_lock:
                    completion = self.grading.run_request(request_ref, stop_event=self.entered_stop)
            else:
                completion = self.grading.run_request(request_ref, stop_event=self.entered_stop)
        except BaseException as error:
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            completion = {'status': 'technical_unknown', 'error': error_value(error)}
        untouched = never_consumed_score(request_ref)
        quiet = untouched or self.grading.trustworthy_cleanup(request_ref) is True
        value = {'row': row, 'generation_result': result_ref, 'request': request_ref,
                 'endpoint': endpoint, 'completion': completion, 'cleanup_proven': quiet}
        value['official_endpoint'] = official_endpoint(request_ref, completion, cleanup_proven=quiet)
        if not quiet:
            value['shared_cleanup_failure'] = True
        elif endpoint == 'code' and completion.get('status') != 'not_started_cancelled':
            try:
                value['delivery'] = self.memory.run_heavy(row['slot_id'], 'delivery_evidence_after_code_score',
                    lambda: self.grading.delivery_disposition(result_ref, request_ref))
            except PermissionError:
                raise
            except Exception as error:
                value['delivery'] = {'status': 'technical_unknown', 'resolved': None, 'error': error_value(error)}
        return value

    def _record_prepared(self, value):
        row = value['row']
        self.finished[row['slot_id']] = value
        path = self.output / 'generation-records' / (str(row['slot_index']) + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new(path, value)
        try:
            usage = self.runtime.usage_for_slot(row) if hasattr(self.runtime, 'usage_for_slot') else self.runtime.for_group(
                row['organization_id']).usage_for_slot(row)
        except Exception as error:
            raise PermissionError('The shared provider ledger could not bind this team usage') from error
        calls = usage.get('calls', [])
        unknown = usage.get('unresolved_calls', [])
        ids = [r['call_id'] for r in calls+unknown]
        if len(ids) != len(set(ids)) or (usage.get('usage_capture_complete') is True and unknown):
            raise PermissionError('The shared provider ledger lost exact request identities')
        usage_path = self.output / 'usage-records' / (str(row['slot_index']) + '.json')
        usage_path.parent.mkdir(parents=True, exist_ok=True)
        write_new(usage_path, {'version': VERSION, 'row': row, 'result_record': reference(path), **usage,
            'unique_request_receipts_not_charged_twice': True})
        self.usage_records[row['slot_id']] = {'group': row['organization_id'], 'status': value['status'],
            'complete': usage.get('usage_capture_complete') is True and not unknown,
            'called': bool(calls or unknown), 'totals': call_totals(calls),
            'unresolved_requests': len(unknown), 'record': reference(usage_path)}
        if value.get('code_request'):
            self.score_queue.append((row, value['result'], value['code_request'], 'code'))

    def _record_exception(self, stage, row, error):
        value = {'stage': stage, 'row': row, 'error': error_value(error), 'automatic_retry': False}
        self.exceptions.setdefault(row['slot_id'], []).append(value)
        self.event('task_exception_isolated', **value)
        if isinstance(error, PermissionError):
            self.drain('public_identity_authority_or_accounting_failure', scoring=True)

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
        # All three views share one ledger. Do not take three snapshots and
        # treat a transient reservation difference as different cash budgets.
        shared_money = self.cash_status(GROUP_IDS[0])
        for group in GROUP_IDS:
            money = {**shared_money, 'group_id': group}
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

    def usage_summary(self):
        result = {}
        for group in GROUP_IDS:
            records = [r for r in self.usage_records.values() if r['group'] == group]
            complete = [r for r in records if r['complete'] and r['called']]
            planned = sum(r['organization_id'] == group for r in self.plan['rows'])
            known = sum(r['totals']['input_plus_output_tokens'] for r in records)
            exact = sum(r['totals']['input_plus_output_tokens'] for r in complete)
            result[group] = {'planned': planned, 'usage_records': len(records),
                'known_tokens_lower_bound': known, 'complete_called_tasks': len(complete),
                'mean_tokens_complete_called_tasks': exact/len(complete) if complete else None,
                'mean_tokens_all_planned': exact/planned if planned and len(complete) == planned else None,
                'unresolved_request_count': sum(r['unresolved_requests'] for r in records),
                'failed_completed_tasks_included': True, 'unmeasured_usage_filled_with_zero': False}
        return result

    def task_records(self):
        records = []
        for row in self.plan['rows']:
            slot = row['slot_id']
            generation = self.finished.get(slot)
            deferred = self.deferred.get(slot)
            exceptions = self.exceptions.get(slot, [])
            code = self.completed_scores.get(slot+':code', {}).get('official_endpoint', {})
            delivery = self.delivery_endpoints.get(slot, {})
            if delivery.get('scoring_request'):
                delivery = self.completed_scores.get(slot+':delivery', {}).get('official_endpoint',
                    {'status': 'technical_unknown', 'resolved': None, 'reason': 'separate_delivery_score_pending'})
            usage = self.usage_records.get(slot)
            generation_status = generation['status'] if generation else 'technical_unknown' if exceptions else 'not_started'
            records.append({'slot_id': slot, 'instance_id': row['instance_id'], 'group_id': row['organization_id'],
                'seed': row.get('seed'), 'generation_status': generation_status,
                'generation_result': generation.get('result') if generation else None,
                'generation_unknown_reason': exceptions or (generation or {}).get('generation_unknown_reason') or (deferred or {}).get('reason'),
                'code_status': code.get('status', 'not_scored'), 'resolved': code.get('resolved'),
                'code_unknown_reason': code.get('reason', None if code else 'no_complete_official_endpoint'),
                'code_receipt': code.get('receipt'), 'delivery_status': delivery.get('status', 'not_measured'),
                'legal_delivery': delivery.get('resolved'),
                'delivery_unknown_reason': delivery.get('reason', None if delivery else 'no_delivery_measurement'),
                'delivery_receipt': delivery.get('receipt'),
                'actual_calls': usage['totals']['settled_calls'] if usage else None,
                'actual_tokens_known': usage['totals']['input_plus_output_tokens'] if usage else None,
                'usage_complete': usage['complete'] if usage else False,
                'unresolved_requests': usage['unresolved_requests'] if usage else None,
                'usage_record': usage['record'] if usage else None, 'first_planned_attempt': True})
        return records

    def progress(self, *, final=False):
        now = time.monotonic()
        if not final and now - self.last_progress < 5:
            return
        self.last_progress = now
        value = {'version': VERSION, 'unix': time.time(), 'phase': 'closed' if final else 'running',
            'generation_active': len(self.generation), 'candidate_preparation_active_or_queued': len(self.preparation),
            'scoring_active': len(self.scores), 'scoring_pending': len(self.score_queue),
            'generation_pending': {group: len(rows) for group, rows in self.pending.items()},
            'prepared_statuses': dict(Counter(item['status'] for item in self.finished.values())),
            'scores_completed': len(self.completed_scores), 'task_exceptions': len(self.exceptions),
            'deferred_unentered': len(self.deferred), 'admission': self.admission.snapshot(),
            'host_memory': self.memory.snapshot(), 'cash_by_group': copy.deepcopy(self.money),
            'actual_token_consumption': self.usage_summary(),
            'draining_new_generation': self.stop_new_generation.is_set(),
            'draining_new_scoring': self.stop_new_scoring.is_set(), 'entered_tasks_cancelled_by_drain': False,
            'new_diagnostic_calls': 0, 'new_neutral_calls': 0, 'old_attempts_replayed': 0}
        atomic_write(self.output / 'progress.json', json_bytes(value))
        return value

    def execute(self):
        with ThreadPoolExecutor(max_workers=scope.MAX_GENERATIONS, thread_name_prefix='v143-team') as generations, \
                ThreadPoolExecutor(max_workers=2, thread_name_prefix='v143-prepare') as preparations, \
                ThreadPoolExecutor(max_workers=scope.MAX_GRADERS, thread_name_prefix='v143-score') as scorers:
            while True:
                self._collect(preparations)
                try:
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
                    if (not runnable or self.stop_new_generation.is_set()) and (
                            not self.score_queue or self.stop_new_scoring.is_set()):
                        break
                self.progress()
                time.sleep(.2)
        for group in GROUP_IDS:
            for row in self.pending[group]:
                self.deferred[row['slot_id']] = {'row': row, 'reason': 'admission_drain_without_entry'}
        value = {'version': VERSION, 'plan': reference(scope.PLAN_FILE),
            'finished_unix': time.time(), 'fresh_attempts_only': True,
            'generation_records': {slot: {key: item[key] for key in ('status', 'result', 'original_result') if key in item}
                                   for slot, item in self.finished.items()},
            'task_exceptions': self.exceptions, 'deferred': self.deferred,
            'deferred_score_requests': [item[2] for item in self.score_queue],
            'delivery_endpoints': self.delivery_endpoints, 'cash_by_group': self.money,
            'actual_token_consumption': self.usage_summary(),
            'new_neutral_calls': 0, 'new_diagnostic_calls': 0, 'old_attempts_replayed': 0}
        write_new(self.output / 'run-summary.json', value)
        write_new(self.output/'task-outcomes.json', {'version': VERSION, 'planned': len(self.plan['rows']),
            'full_planned_denominator_preserved': True, 'cash_censored_tasks_removed': False,
            'rows': self.task_records()})
        self.progress(final=True)
        return value


def prepare_diagnostics(implementation, plan, *, stop_new=None):
    """Retired diagnostic identities never reenter; preserve every primary error."""
    import resource
    from proworksim.software_benchmark_alignment_contract_v141 import condition, shared_strategy
    from proworksim.software_benchmark_diagnostic_receipts_v143 import DiagnosticFailure, inspect_diagnostic
    records = []
    for spec in plan['diagnostics']:
        if stop_new is not None and stop_new.is_set():
            raise InterruptedError('Preparation drained before the next diagnostic')
        row = next(r for r in plan['rows'] if r['slot_id'] == spec['slot_id'])
        ref = implementation._run(row, {}, diagnostic=True, diagnostic_index=spec['index'])
        try:
            record = inspect_diagnostic(ref, spec, load=scope.load, condition=condition,
                shared_strategy=shared_strategy,
                controller_memory_bytes=scope.CONSTRAINTS['controller_memory_bytes'], gib=scope.GIB)
        except DiagnosticFailure as error:
            try:
                scope.retain(scope.API_ROOT/'diagnostic-failures'/(str(spec['index'])+'.json'), error.report)
            except Exception as write_error:
                # Do not replace a primary startup failure with another failure
                # from trying to archive it (for example a full disk).
                error.report['failure_report_write_error'] = error_value(write_error)
            raise
        record['manager_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
        records.append(record)
    return scope.retain(scope.PREPARATION_QUALIFICATION_FILE, {
        'version': VERSION, 'passed': True, 'diagnostics': records,
        'API_calls': 0, 'retired_diagnostic_reentered': False,
        'all_planned_groups_checked': True})


def qualify_environments(grading, plan, *, stop_new=None):
    """Run the new scope's gold/empty controls with at most two physical scorers."""
    from concurrent.futures import as_completed
    prepared = grading.prepare_environment_qualifications()
    qualifications = dict(prepared['qualifications'])
    stop, tls = threading.Event(), threading.Lock()

    def control(ref):
        request = scope.load(ref)
        try:
            if request['instance_id'] in {'psf__requests-1766', 'psf__requests-1921'}:
                with tls:
                    outcome = grading.run_request(ref, stop_event=stop)
            else:
                outcome = grading.run_request(ref, stop_event=stop)
        except Exception as error:
            outcome = {'status': 'technical_unknown', 'error': error_value(error)}
        if not never_consumed_score(ref) and grading.trustworthy_cleanup(ref) is not True:
            raise PermissionError('A control scorer has no trustworthy cleanup proof')
        return {'request': ref, 'outcome': outcome}

    results = []
    # Submit at most two at once: after a common failure, queued controls have
    # not acquired identities and are not accidentally started by an executor.
    with ThreadPoolExecutor(max_workers=scope.MAX_GRADERS) as workers:
        pending, controls = {}, iter(prepared.get('controls', []))
        for _ in range(scope.MAX_GRADERS):
            if stop_new is not None and stop_new.is_set():
                break
            ref = None if stop_new is not None and stop_new.is_set() else next(controls, None)
            if ref is not None:
                pending[workers.submit(control, ref)] = ref
        while pending:
            done = next(as_completed(pending))
            pending.pop(done)
            results.append(done.result())
            ref = None if stop_new is not None and stop_new.is_set() else next(controls, None)
            if ref is not None:
                pending[workers.submit(control, ref)] = ref
    for task in plan['environments']:
        if task not in qualifications:
            try:
                qualifications[task] = grading.qualify(task)
            except PermissionError:
                raise
            except Exception as error:
                qualifications[task] = {'passed': False, 'status': 'not_qualified',
                    'reason': 'fresh_environment_control_unknown', 'error': error_value(error)}
    scope.retain(scope.API_ROOT/'qualification-status.json', {
        'version': VERSION, 'qualifications': qualifications, 'control_completions': results})
    return qualifications


def run():
    from proworksim.software_benchmark_episode_v143 import build_episode
    from proworksim.software_benchmark_grading_v143 import factory
    scope.require_allowed('v143.run')
    limits = scope.verify_host_limits()
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('A consumed coordinator identity cannot silently restart')
    lease = scope.reserve_api_coordinator()
    memory = HostMemoryGate(maximum=2)
    coordinator, old_signals, result = None, {}, None
    initial_stop = threading.Event()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_signals[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda _number, _frame: initial_stop.set())
        control = DrainControl(DRAIN_FILE, batch_root=scope.STATE_ROOT, groups=GROUP_IDS,
                               maximum=scope.MAX_GENERATIONS)
        admission = FairAdmission(GROUP_IDS, control=control, maximum=scope.MAX_GENERATIONS,
            maximum_startups=scope.MAX_STARTUPS, pressure_probe=pressure_probe)
        implementation = build_episode(scope=scope, guard=scope.require_allowed, host_memory=memory,
                                       admission_check=admission.require_start)
        write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION,
            'authorization': reference(scope.AUTH_FILE), 'source_index': reference(scope.SOURCE_FILE),
            'plan': reference(scope.PLAN_FILE), 'host_limits': limits, 'fresh_attempts_only': True,
            'shared_cash_cap_CNY': '400.00', 'old_ledgers_opened': False,
            'maximum_generation': scope.MAX_GENERATIONS, 'maximum_startups': scope.MAX_STARTUPS,
            'maximum_graders': scope.MAX_GRADERS, 'new_system_parent': False})
        prepare_diagnostics(implementation, plan, stop_new=initial_stop)
        grading = factory(watchdog_guard=lambda *_args, **_identity: None)
        qualifications = qualify_environments(grading, plan, stop_new=initial_stop)
        if initial_stop.is_set():
            raise InterruptedError('Preparation drained before any provider call')
        runtime = DeepSeekRuntime().initialize_for_run()
        coordinator = Coordinator(runtime=runtime, implementation=implementation, grading=grading,
            memory=memory, admission=admission, plan=plan, qualifications=qualifications)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda number, _frame: coordinator.drain('signal_'+str(number)))
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
        try:
            final_ref = scope.retain(scope.API_ROOT/'coordinator-finalization.json', {
                'version': VERSION, 'coordinator_release': released, 'cleanup_errors': cleanup_errors,
                'entered_tasks_cancelled': False, 'system_parent_created_or_modified': False,
                'original_experiment_error_not_replaced': True})
            if isinstance(result, dict):
                result['runtime_finalization'] = final_ref
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
