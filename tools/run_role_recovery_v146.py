"""Independent recovery attempts with bounded retry queues and asynchronous grading.

The first twenty-one attempts precede at most one newly identified retry per
original task. Only technical transport failures qualify; normal failed scores
never cause generation retries. Every prior candidate, receipt and usage remains.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import signal
import time
from types import FunctionType

from proworksim import software_benchmark_scope_v146 as scope
from proworksim import software_benchmark_host_api_v146 as host
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_function, clone_namespace
from proworksim.software_benchmark_group_admission_v132 import DrainControl, FairAdmission
from proworksim.software_benchmark_host_memory_v132 import HostMemoryGate
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v146-independent-recovery-and-bounded-technical-retry-queues-r1'
GROUP_IDS = ('FREE2', 'REVIEW2')
DRAIN_FILE = scope.STATE_ROOT/'admission-control.json'


def _previous_module():
    path = scope.ROOT/'tools/run_role_pilot_v143.py'
    spec = importlib.util.spec_from_file_location('role_pilot_v143_recovery_basis', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


_previous = _previous_module()
_namespace = clone_namespace(_previous, scope=scope, GROUP_IDS=GROUP_IDS,
    VERSION=VERSION, DRAIN_FILE=DRAIN_FILE, budget_status=host.budget_status, __file__=__file__)
_base = type('RecoveryScopedCoordinator', (_previous.Coordinator,), {
    name: clone_function(value, _namespace) for name, value in vars(_previous.Coordinator).items()
    if isinstance(value, FunctionType)})
error_value = _namespace['error_value']
never_consumed_score = _namespace['never_consumed_score']
official_endpoint = _namespace['official_endpoint']


def manager_pressure_working_set(cgroup, *, reserve_bytes=2*1024**3):
    """Read-only admission: clean private file cache is reclaimable, not free RAM.

    Keep tmpfs/shmem, dirty/writeback and unevictable pages in the working set.
    Kernel hard limits and PSI remain authoritative; no cache or cgroup writes.
    """
    root = Path(cgroup)
    limits = {name:int((root/name).read_text()) for name in
              ('memory.current','memory.high','memory.max','memory.swap.current','memory.swap.max')}
    if (limits['memory.high'] != scope.API_MEMORY_HIGH_BYTES
            or limits['memory.max'] != scope.API_MEMORY_BYTES or limits['memory.swap.max'] != 0):
        raise PermissionError('The manager no longer has the frozen memory/swap limits')
    stat = {key:int(value) for key,value in (line.split() for line in (root/'memory.stat').read_text().splitlines())}
    required = ('anon','file','shmem','file_dirty','file_writeback','unevictable')
    if any(key not in stat or stat[key] < 0 for key in required):
        raise PermissionError('Manager working-set evidence is incomplete')
    events = {key:int(value) for key,value in (line.split() for line in (root/'memory.events').read_text().splitlines())}
    full = next(line for line in (root/'memory.pressure').read_text().splitlines() if line.startswith('full '))
    psi = float(dict(field.split('=',1) for field in full.split()[1:])['avg10'])
    current = limits['memory.current']
    clean_file = max(0, min(current, stat['file']-stat['shmem']-stat['file_dirty']
                           -stat['file_writeback']-stat['unevictable']))
    working = max(stat['anon'], current-clean_file)
    passed = (0 <= current <= limits['memory.max'] and limits['memory.swap.current'] == 0
              and working+reserve_bytes <= limits['memory.high'] and 0 <= psi <= 20
              and events.get('oom',0) == 0 and events.get('oom_kill',0) == 0)
    return {'passed':passed, **limits, 'working_set_upper_bytes':working,
        'reclaimable_clean_file_estimate_bytes':clean_file,
        'file_exclusions':{key:stat[key] for key in required}, 'memory_events':events,
        'reserve_bytes':reserve_bytes, 'full_avg10':psi, 'maximum_full_avg10':20,
        'reclaim_is_estimated_not_completed':True, 'cache_or_cgroup_writes':0}


def pressure_probe():
    physical = scope.dispatch_view().physical_capacity()
    groups = [line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
              if line.startswith('0::')]
    if len(groups) != 1:
        raise PermissionError('The current manager lacks a unique cgroup')
    memory = manager_pressure_working_set(Path('/sys/fs/cgroup')/groups[0].lstrip('/'))
    load, maximum_load = os.getloadavg()[0], max(1,len(scope.host_cpu_pool())-16)
    return {'passed':physical.get('passed') is True and memory['passed'] and load <= maximum_load,
        'host':physical, 'manager':memory, 'host_load1':load, 'maximum_host_load1':maximum_load}


class Coordinator(_base):
    def __init__(self, *, runtime, implementation, grading, memory, admission, plan,
                 qualifications, output=None, cash_status=host.budget_status,
                 recovery_classifier=host.recovery_queue_record):
        first = [row for row in plan['rows'] if row['recovery_round'] == 1]
        second = [row for row in plan['rows'] if row['recovery_round'] == 2]
        if (not first or len(first) != len(second)
                or len({r['original_slot_id'] for r in first}) != len(first)
                or {r['retry_of_slot_id'] for r in second} != {r['slot_id'] for r in first}):
            raise ValueError('Exactly one reserved second identity must bind each first recovery')
        super().__init__(runtime=runtime, implementation=implementation, grading=grading,
            memory=memory, admission=admission, plan={**plan, 'rows':first},
            qualifications=qualifications, output=output, cash_status=cash_status)
        self.plan = plan
        self.first_rows, self.second_rows = first, second
        self.retry_rows = {r['retry_of_slot_id']: r for r in second}
        self.recovery_classifier = recovery_classifier
        self.recovery_queue, self.score_recovery_queue = {}, {}
        self.score_attempts, self.activated_retries = [], set()
        self.retry_selection_done = False

    def _write_recovery_queues(self):
        atomic_write(self.output/'recovery-queue.json', json_bytes({
            'version': VERSION, 'generation': list(self.recovery_queue.values()),
            'scoring': list(self.score_recovery_queue.values()),
            'maximum_new_generation_attempts_per_original': 2,
            'normal_model_failures_retried': False, 'old_usage_discarded': False}))

    def _record_prepared(self, value):
        super()._record_prepared(value)
        row = value['row']
        if value['status'] == 'closed':
            return
        classification = self.recovery_classifier(row)
        eligible = classification.get('retry_eligible') is True
        queue = {**classification, 'slot_id':row['slot_id'], 'slot_index':row['slot_index'],
            'original_slot_id':row['original_slot_id'], 'recovery_round':row['recovery_round'],
            'generation_result':value['result'], 'new_identity_required':True,
            'prior_usage_preserved':True,
            'state':('waiting_for_first_round' if eligible and row['recovery_round'] == 1
                     else 'retry_limit_reached' if eligible else
                     'waiting_cash' if classification.get('classification') == 'cash_boundary'
                     else 'requires_protocol_repair')}
        self.recovery_queue[row['slot_id']] = queue
        self.event('generation_recovery_queued', **queue)
        self._write_recovery_queues()

    def _activate_second_round(self):
        if self.retry_selection_done or self.generation or self.preparation:
            return
        if any(self.pending[group] for group in GROUP_IDS):
            return
        if self.stop_new_generation.is_set():
            return
        self.retry_selection_done = True
        for first in sorted(self.first_rows, key=lambda r:r['slot_index']):
            item = self.recovery_queue.get(first['slot_id'])
            result = self.finished.get(first['slot_id'])
            if (not item or item.get('retry_eligible') is not True
                    or not result or result['status'] != 'technical_unknown'):
                continue
            second = self.retry_rows[first['slot_id']]
            decision = {'version':scope.VERSION, 'slot_id':second['slot_id'],
                'prior_slot_id':first['slot_id'], 'prior_result':result['result'],
                'reason':'transient_transport_failure_after_first_round',
                'technical_transient':True, 'first_round_drained':True,
                'classification':item.get('classification'), 'prior_usage_preserved':True}
            target = self.output/'recovery-admissions'/(str(second['slot_index'])+'.json')
            target.parent.mkdir(parents=True, exist_ok=True)
            admission_ref = write_new(target, decision)
            group = second['organization_id']
            self.pending[group].append(second)
            self.admission.register_pending(group, [second['slot_id']])
            self.activated_retries.add(second['slot_id'])
            item.update(state='queued_independent_retry', retry_slot_id=second['slot_id'],
                        retry_admission=admission_ref)
            self.event('independent_recovery_admitted', **decision)
        self._write_recovery_queues()

    def _admit(self, executor):
        self._activate_second_round()
        super()._admit(executor)
        for slot, deferred in self.deferred.items():
            if deferred.get('reason') not in {'cash_exhausted', 'shared_halted'}:
                continue
            row = deferred['row']
            self.recovery_queue.setdefault(slot, {
                'slot_id':slot, 'slot_index':row['slot_index'],
                'original_slot_id':row['original_slot_id'], 'recovery_round':row['recovery_round'],
                'classification':'cash_boundary', 'retry_eligible':False,
                'state':'waiting_cash', 'never_entered':True, 'prior_usage_preserved':True})
        if self.deferred:
            self._write_recovery_queues()

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
            completion = {'status':'technical_unknown', 'error':error_value(error)}
        quiet = never_consumed_score(request_ref) or self.grading.trustworthy_cleanup(request_ref) is True
        value = {'row':row, 'generation_result':result_ref, 'request':request_ref,
                 'endpoint':endpoint, 'completion':completion, 'cleanup_proven':quiet}
        value['official_endpoint'] = official_endpoint(request_ref, completion, cleanup_proven=quiet)
        if not quiet:
            value['shared_cleanup_failure'] = True
        return value

    def _record_scored(self, value, item):
        row, result_ref, request_ref, endpoint = item
        request = scope.load(request_ref)
        attempt = 2 if '-retry-' in request['resource_key'] else 1
        key = row['slot_id']+':'+endpoint
        self.completed_scores[key] = value
        if value.get('shared_cleanup_failure'):
            self.drain('scoring_cleanup_not_proven', scoring=True)
        retry = (value['official_endpoint']['status'] == 'technical_unknown'
                 and value['cleanup_proven'] and attempt == 1
                 and not self.stop_new_scoring.is_set())
        if retry:
            retry_ref = self.grading.prepare_score_retry(request_ref)
            next_request = scope.load(retry_ref)
            if (next_request['candidate_lock'] != request['candidate_lock']
                    or next_request['generation_result'] != request['generation_result']
                    or next_request['slot_id'] != row['slot_id']
                    or next_request['resource_key'] != (
                        'score-retry-' if endpoint == 'code' else 'delivery-score-retry-')+str(row['slot_index'])):
                raise PermissionError('Technical scoring retry changed its sole candidate identity')
            self.score_queue.append((row, result_ref, retry_ref, endpoint))
            self.score_recovery_queue[key] = {'slot_id':row['slot_id'], 'endpoint':endpoint,
                'state':'queued_same_candidate_retry', 'first_request':request_ref,
                'retry_request':retry_ref, 'model_rerun':False}
        else:
            prior = self.score_recovery_queue.get(key)
            if prior:
                prior.update(state='resolved' if value['official_endpoint']['status'] == 'scored'
                             else 'retry_limit_reached', final_request=request_ref)
            if endpoint == 'code' and value['cleanup_proven']:
                try:
                    delivery = self.memory.run_heavy(row['slot_id'], 'delivery_after_final_code_score',
                        lambda:self.grading.delivery_disposition(result_ref, request_ref))
                except PermissionError:
                    raise
                except Exception as error:
                    delivery = {'status':'technical_unknown', 'resolved':None, 'error':error_value(error)}
                value['delivery'] = delivery
                self.delivery_endpoints[row['slot_id']] = delivery
                if delivery.get('scoring_request'):
                    self.score_queue.append((row, result_ref, delivery['scoring_request'], 'delivery'))
        value['physical_scoring_attempt'] = attempt
        folder = self.output/'score-records'
        folder.mkdir(parents=True, exist_ok=True)
        ref = write_new(folder/(str(row['slot_index'])+'-'+endpoint+'-attempt'+str(attempt)+'.json'), value)
        self.score_attempts.append({'slot_id':row['slot_id'], 'endpoint':endpoint,
            'physical_scoring_attempt':attempt, 'record':ref})
        self._write_recovery_queues()

    def _collect(self, preparations):
        # Keep the established independent generation/preparation loops; handle
        # physical scorer attempts here so an initial unknown never overwrites.
        scores, self.scores = self.scores, {}
        try:
            super()._collect(preparations)
        finally:
            self.scores = scores
        for future, item in list(self.scores.items()):
            if not future.done():
                continue
            del self.scores[future]
            try:
                self._record_scored(future.result(), item)
            except BaseException as error:
                self._record_exception('scoring', item[0], error)

    def task_records(self):
        records = super().task_records()
        rows = {row['slot_id']:row for row in self.plan['rows']}
        for record in records:
            row = rows[record['slot_id']]
            record.update(first_planned_attempt=False, independent_recovery=True,
                original_slot_id=row['original_slot_id'], recovery_round=row['recovery_round'],
                retry_of_slot_id=row.get('retry_of_slot_id'),
                original_generation_result=row['original_generation_result'],
                original_generation_unknown_preserved=True)
            if (row['recovery_round'] == 2 and row['slot_id'] not in self.activated_retries
                    and record['generation_status'] == 'not_started'):
                record.update(generation_status='not_activated',
                              generation_unknown_reason='No eligible technical failure, or admission drained')
        return records

    def usage_summary(self):
        result = super().usage_summary()
        for group, value in result.items():
            value['original_cases'] = sum(r['organization_id'] == group for r in self.first_rows)
            value['reserved_attempt_ceiling'] = value.pop('planned')
            value['activated_attempts'] = value['original_cases']+sum(
                r['organization_id'] == group and r['slot_id'] in self.activated_retries
                for r in self.second_rows)
            value['mean_tokens_all_planned'] = None
            value['costs_include_all_actual_attempts'] = True
        return result

    def progress(self, *, final=False):
        value = super().progress(final=final)
        if value is not None:
            value.update(planned_original_cases=len(self.first_rows),
                attempt_ceiling=len(self.plan['rows']),
                second_attempts_activated=len(self.activated_retries),
                physical_scoring_attempts=len(self.score_attempts),
                technical_recovery_queue=len(self.recovery_queue),
                main_generation_and_scoring_are_asynchronous=True)
            atomic_write(self.output/'progress.json', json_bytes(value))
        return value

    def execute(self):
        with ThreadPoolExecutor(max_workers=scope.MAX_GENERATIONS, thread_name_prefix='v146-team') as generations, \
                ThreadPoolExecutor(max_workers=2, thread_name_prefix='v146-prepare') as preparations, \
                ThreadPoolExecutor(max_workers=scope.MAX_GRADERS, thread_name_prefix='v146-score') as scorers:
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
                self.deferred[row['slot_id']] = {'row':row, 'reason':'admission_drain_without_entry'}
        self._write_recovery_queues()
        value = {'version':VERSION, 'plan':reference(scope.PLAN_FILE), 'finished_unix':time.time(),
            'planned_original_cases':len(self.first_rows), 'reserved_attempt_ceiling':len(self.plan['rows']),
            'second_attempts_activated':sorted(self.activated_retries),
            'fresh_independent_attempts_only':True, 'prior_results_and_usage_preserved':True,
            'generation_records':{slot:{k:item[k] for k in ('status','result')}
                                  for slot,item in self.finished.items()},
            'task_exceptions':self.exceptions, 'deferred':self.deferred,
            'deferred_score_requests':[item[2] for item in self.score_queue],
            'physical_scoring_attempts':self.score_attempts,
            'delivery_endpoints':self.delivery_endpoints, 'cash_by_group':self.money,
            'actual_token_consumption':self.usage_summary(),
            'recovery_queue':reference(self.output/'recovery-queue.json'),
            'new_neutral_calls':0, 'new_diagnostic_calls':0,
            'original_consumed_model_identities_replayed':0}
        write_new(self.output/'run-summary.json', value)
        write_new(self.output/'task-outcomes.json', {'version':VERSION,
            'planned_original_cases':len(self.first_rows), 'attempt_ceiling':len(self.plan['rows']),
            'cash_censored_tasks_removed':False, 'rows':self.task_records()})
        self.progress(final=True)
        return value


def run():
    from proworksim.software_benchmark_episode_v146 import build_episode
    from proworksim.software_benchmark_grading_v146 import factory
    scope.require_allowed('v146.run')
    limits = scope.verify_host_limits()
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('A consumed recovery owner cannot silently restart')
    lease = scope.reserve_api_coordinator()
    memory, old_signals, result = HostMemoryGate(maximum=2), {}, None
    try:
        control = DrainControl(DRAIN_FILE, batch_root=scope.STATE_ROOT, groups=GROUP_IDS,
                               maximum=scope.MAX_GENERATIONS)
        admission = FairAdmission(GROUP_IDS, control=control, maximum=scope.MAX_GENERATIONS,
            maximum_startups=scope.MAX_STARTUPS, pressure_probe=pressure_probe)
        implementation = build_episode(scope=scope, guard=scope.require_allowed, host_memory=memory,
                                       admission_check=admission.require_start)
        qualifications = scope.load(reference(scope.API_ROOT/'qualification-status.json'))['qualifications']
        write_new(scope.API_ROOT/'execution-started.json', {'version':VERSION,
            'authorization':reference(scope.AUTH_FILE), 'source_index':reference(scope.SOURCE_FILE),
            'plan':reference(scope.PLAN_FILE), 'host_limits':limits,
            'independent_recovery':True, 'old_ledger_read_only':True,
            'maximum_generation':scope.MAX_GENERATIONS, 'maximum_startups':scope.MAX_STARTUPS,
            'maximum_graders':scope.MAX_GRADERS, 'new_system_parent':False,
            'new_diagnostics':0, 'environment_controls_reused_by_exact_identity':True})
        grading = factory(watchdog_guard=lambda *_args, **_identity:None)
        runtime = host.DeepSeekRuntime().initialize_for_run()
        coordinator = Coordinator(runtime=runtime, implementation=implementation, grading=grading,
            memory=memory, admission=admission, plan=plan, qualifications=qualifications)
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_signals[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda number,_frame:coordinator.drain('signal_'+str(number)))
        result = coordinator.execute()
        return result
    finally:
        for sig, handler in old_signals.items():
            signal.signal(sig, handler)
        errors, released = [], None
        try:
            memory.close()
        except Exception as error:
            errors.append({'step':'host_memory_close', **error_value(error)})
        try:
            released = scope.release_api_coordinator(lease)
        except Exception as error:
            errors.append({'step':'coordinator_release', **error_value(error)})
        try:
            ref = scope.retain(scope.API_ROOT/'coordinator-finalization.json', {
                'version':VERSION, 'coordinator_release':released, 'cleanup_errors':errors,
                'entered_tasks_cancelled':False, 'system_parent_created_or_modified':False})
            if isinstance(result, dict):
                result['runtime_finalization'] = ref
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
