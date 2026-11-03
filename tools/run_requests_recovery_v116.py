"""Four uncalled Requests tasks after isolated installed-CA-path repair.

One shared two-slot scoring gate covers only new controls and these four first
generations. Completed v114 rescores are not loaded or scheduled again.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading
import time
from types import ModuleType

from proworksim import software_benchmark_scope_v116 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim import software_benchmark_grading_requests_v116 as grading_module
from proworksim.software_benchmark_episode_recovery_v116 import build_episode
from proworksim.software_benchmark_host_api_v116 import DeepSeekRuntime, prepare_schemas, qualify
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v116-only-four-uncalled-requests-coordinator-r1'
TLS_TASKS = frozenset(('psf__requests-1766', 'psf__requests-1921'))


def never_consumed(ref):
    request = scope.load(ref)
    folder = Path(request['directory'])
    return (not any((folder/name).exists() for name in ('capacity-claim.json', 'started.json', 'initial-container.json'))
            and not (scope.BATCH_ROOT/'resource-claims'/(request['resource_key']+'.json')).exists())


class SharedScoring:
    def __init__(self, delegate, *, fault):
        self.delegate, self.fault = delegate, fault
        self.slots, self.tls = threading.BoundedSemaphore(scope.MAX_GRADERS), threading.Lock()

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def run_request(self, ref, stop_event):
        request = scope.load(ref)
        locks = ([self.tls] if request.get('instance_id') in TLS_TASKS else []) + [self.slots]
        held = []
        try:
            for lock in locks:
                while not lock.acquire(timeout=.2):
                    if stop_event.is_set():
                        return {'status': 'not_started_cancelled', 'request': ref}
                held.append(lock)
                if stop_event.is_set():
                    return {'status': 'not_started_cancelled', 'request': ref}
            try:
                result = self.delegate.run_request(ref, stop_event=stop_event)
            except (scope.ResourceBusy, InterruptedError):
                if never_consumed(ref):
                    return {'status': 'not_started_cancelled', 'request': ref}
                self.fault('consumed_scoring_capacity_or_cancellation', ref)
                raise
            except Exception:
                if not never_consumed(ref) and not self.delegate.trustworthy_cleanup(ref):
                    self.fault('unproven_scoring_cleanup', ref)
                raise
            if not never_consumed(ref) and not self.delegate.trustworthy_cleanup(ref):
                self.fault('unproven_scoring_cleanup', ref)
                raise RuntimeError('A consumed scorer has no trusted cleanup proof')
            return result
        finally:
            for lock in reversed(held):
                lock.release()


def validate_recovery_rows(plan):
    generation = plan.get('generation_rows', [])
    if (len(plan.get('rows', [])) != 4 or plan['rows'] != generation
            or len({row['slot_id'] for row in generation}) != 4
            or {row['slot_index'] for row in generation} != {7238, 7239, 7266, 7267}
            or set(plan.get('environments', {})) != TLS_TASKS
            or plan.get('score_recoveries') != []):
        raise ValueError('Only four original uncalled Requests rows and no completed rescores may proceed')
    return generation, []


def validate_requests_recovery(recovery, plan, authorization):
    """v115 created real TLS containers; require their cleanup and new allowance."""
    if (recovery.get('version') != 'v116-installed-CA-path-recovery-r1'
            or recovery.get('model_calls') != 0 or recovery.get('volumes_created') != 0
            or recovery.get('actual_unique_container_count') != 12
            or recovery.get('original_authorized_total_containers') != 26
            or recovery.get('additional_control_containers') != 4
            or recovery.get('total_authorized_containers') != 30
            or recovery.get('remaining_container_allowance') != 18
            or recovery.get('original_TLS_session_allowance') != 10
            or recovery.get('additional_TLS_sessions') != 4
            or recovery.get('total_authorized_TLS_sessions') != 14
            or recovery.get('old_failures_overwritten') is not False
            or scope.CONSTRAINTS['maximum_containers'] != 18):
        raise ValueError('The created TLS containers and specifically increased control allowance must be explicit')
    if (authorization.get('status') != 'approved'
            or authorization.get('additional_object_allowance') != 4
            or authorization.get('total_authorized_containers') != 30
            or authorization.get('total_authorized_TLS_sessions') != 14):
        raise PermissionError('The extra four controls require their exact separate authorization')
    actual = set()
    for deployment, expected_receipts, expected_created in (('v114', 12, 8), ('v115', 4, 4)):
        refs = recovery.get(deployment+'_quiescence', [])
        if len(refs) != expected_receipts or len({ref['path'] for ref in refs}) != expected_receipts:
            raise ValueError('Every prior control and scorer requires its original cleanup receipt')
        created = 0
        for ref in refs:
            path = Path(ref['path']).resolve()
            if not path.is_relative_to(scope.BATCH_ROOT/('grading-'+deployment)) or path.name != 'quiescence.json':
                raise ValueError('A cleanup receipt belongs to another deployment')
            quiet = scope.load(ref)
            ids = quiet.get('owned_container_ids')
            if (not isinstance(ids, list) or len(ids) > 1
                    or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
                    or quiet.get('create_result_unknown') is not False
                    or any(not isinstance(value, str) or not value or value in actual for value in ids)):
                raise ValueError('Prior actually created containers lack unambiguous cleanup')
            actual.update(ids)
            created += len(ids)
        if created != expected_created:
            raise ValueError('v115 real container creation must not be relabeled as zero creation')
    if len(actual) != 12 or 30-len(actual) != recovery['remaining_container_allowance']:
        raise ValueError('Actual creation and remaining container authority do not reconcile')
    releases = recovery.get('previous_owner_releases', [])
    expected = {str(scope.BATCH_ROOT/f'api-coordinator-{version}/coordinator-capacity-released.json')
                for version in ('v114', 'v115')}
    if len(releases) != 2 or {ref['path'] for ref in releases} != expected:
        raise ValueError('Both preceding owner releases are required')
    for ref in releases:
        if scope.load(ref).get('released') is not True:
            raise ValueError('An earlier owner still retains capacity')
    for row in plan['generation_rows']:
        folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
        if ((scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists()
                or any((folder/name).exists() for name in ('entered.json', 'result.json'))):
            raise ValueError('Only the four never-entered model episodes may proceed')
    return recovery


def old_helpers():
    spec = importlib.util.spec_from_file_location('v114_compact_usage_helpers',
        scope.ROOT/'tools/run_full_benchmark_v066.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helpers = old_helpers()


class UsageRecorder(helpers.UsageRecorder):
    def save_record(self, row, record):
        path = scope.API_ROOT/'usage-records'/f"{row['slot_index']}.json"
        atomic_write(path, json_bytes(record))
        self.remember_record(row, record, reference(path))

    def flush(self, *, final=False):
        if not final and time.monotonic()-self.last_write < 30:
            return
        groups = {}
        for name in self.matrix['groups']:
            values = [v for v in self.records.values() if v['group_id'] == name]
            complete = [v for v in values if v['generation_state'] in {'closed', 'technical_unknown'}
                        and v['usage_capture_complete'] and v['uncertain_reserved_tokens'] == 0]
            called = [v for v in complete if v['prompt_tokens_known']+v['completion_tokens_known'] > 0]
            known = sum(v['prompt_tokens_known']+v['completion_tokens_known'] for v in values)
            total = sum(v['prompt_tokens_known']+v['completion_tokens_known'] for v in complete)
            groups[name] = {'planned': sum(row['group_id'] == name for row in self.matrix['rows']), 'entered': sum(v['entered'] for v in values),
                'usage_complete_tasks': len(complete), 'usage_complete_called_tasks': len(called),
                'known_actual_tokens_lower_bound': known,
                'mean_complete_called_tasks': total/len(called) if called else None,
                'mean_all_planned_when_usage_complete': total/len(complete) if len(complete) == sum(row['group_id'] == name for row in self.matrix['rows']) and complete else None}
        report = {'version': VERSION, 'unix': time.time(), 'final': final, 'groups': groups,
            'provider_usage_is_authoritative': True, 'cash': self.api_runtime.budget_status(),
            'preparation': self.api_runtime.preparation_usage(), 'panel': reference(scope.PANEL_FILE)}
        atomic_write(scope.API_ROOT/'actual-usage-summary.json', json_bytes(report))
        if final:
            write_new(scope.API_ROOT/'actual-usage-records.json', {'version': VERSION,
                'record_files': {slot: value['record'] for slot, value in self.records.items()}})
        self.last_write = time.monotonic()


def queue_module():
    policy = scope.dispatch_view()
    namespace = clone_namespace(queue_base, policy=policy)
    def unconsumed(ref):
        request = scope.load(ref)
        folder = Path(request['directory'])
        return (not any((folder/name).exists() for name in ('capacity-claim.json', 'started.json', 'initial-container.json'))
                and not (scope.BATCH_ROOT/'resource-claims'/(request['resource_key']+'.json')).exists())
    class JobStore(queue_base.JobStore):
        def __init__(self, root, **kwargs):
            super().__init__(root, consumed_check=unconsumed, **kwargs)
    namespace['JobStore'] = JobStore
    # contextmanager wraps() copied the function module name, but its wrapper
    # still requires contextlib globals. Reuse it with its original globals.
    namespace['executors'] = queue_base.executors
    module = ModuleType(__name__+'.private_async_queue')
    module.__dict__.update(namespace)
    return module


class NoLocalModel:
    start_residents = staticmethod(lambda: [])
    ready_residents = staticmethod(lambda: [])
    stop_residents = staticmethod(lambda: [])


def run():
    authorization = scope.require_allowed()
    limits = scope.verify_host_limits()
    plan = scope.load(reference(scope.PLAN_FILE))
    rows, recovery_specs = validate_recovery_rows(plan)
    recovery_ref = reference(scope.REQUESTS_RECOVERY_FILE)
    validate_requests_recovery(scope.load(recovery_ref), plan, authorization)
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('An entered recovery owner cannot automatically restart')
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    lease = scope.reserve_api_coordinator()
    overall_stop, generation_stop = threading.Event(), threading.Event()
    api, failure = None, None
    recovered, recovery_lock = {}, threading.Lock()
    shared_faults, callback_errors = [], []
    def snapshot(name, value):
        atomic_write(scope.API_ROOT/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))
    def event(kind, **values):
        with recovery_lock, (scope.API_ROOT/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'unix': time.time(), **values}, ensure_ascii=False)+'\n')
    def fault(reason, request):
        with recovery_lock:
            shared_faults.append({'reason': reason, 'request': request})
        overall_stop.set()
        generation_stop.set()
        if api is not None:
            api.cancel_all()
        event('shared_cleanup_requires_review', reason=reason, request=request)
    signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def terminate(*_):
        overall_stop.set()
        generation_stop.set()
        if api is not None:
            api.cancel_all()
    for sig in signals:
        signal.signal(sig, terminate)
    write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION,
        'authorization': reference(scope.AUTH_FILE), 'plan': reference(scope.PLAN_FILE),
        'host_limits': limits, 'first_generation_count': len(rows), 'preserved_candidate_score_count': len(recovery_specs),
        'old_generations_imported_as_new': 0, 'additional_neutral_calls': 0, 'additional_diagnostics': 0,
        'API_cash_cap_CNY': scope.CASH_CAP_CNY, 'API_qualification': authorization['API_qualification'],
        'requests_recovery': recovery_ref, 'prior_completed_rescores_replayed': 0})
    try:
        schemas = scope.load(prepare_schemas())
        qualify(None, None, schemas)
        grading = SharedScoring(grading_module.factory(watchdog_guard=lambda *_a, **_k: None), fault=fault)
        preparation = grading.prepare_environment_qualifications()
        qualifications = dict(preparation['qualifications'])
        controls = preparation['controls']
        expected = {f'control-v116-{task}-{kind}' for task in TLS_TASKS for kind in ('gold', 'empty')}
        if len(controls) != 4 or {scope.load(ref).get('resource_key') for ref in controls} != expected:
            raise ValueError('Exactly four new control-v116 keys are required; old keys cannot be reused')
        with ThreadPoolExecutor(max_workers=scope.MAX_GRADERS) as pool:
            futures = {pool.submit(grading.run_request, ref, overall_stop): ref for ref in controls}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    event('isolated_environment_control_error', request=futures[future],
                          error={'type': type(error).__name__, 'message': str(error)})
        if overall_stop.is_set():
            raise RuntimeError('Environment preparation stopped with unresolved shared cleanup')
        for task in plan['environments']:
            if qualifications.get(task, {}).get('status') == 'qualified':
                continue
            try:
                value = grading.qualify(task)
                if isinstance(value, dict) and value.get('path'):
                    proof = scope.load(value)
                    qualifications[task] = {'status': 'qualified' if proof.get('passed') is True else 'not_qualified',
                                            'qualification': value}
                else:
                    qualifications[task] = value
            except Exception as error:
                qualifications[task] = {'status': 'not_qualified', 'error': {'type': type(error).__name__, 'message': str(error)}}
        snapshot('qualification-status.json', {'qualifications': qualifications})
        api = DeepSeekRuntime()
        if any(qualifications.get(row['instance_id'], {}).get('status') == 'qualified' for row in rows):
            api.initialize_for_run()
        impl = build_episode()
        recorder = UsageRecorder({'rows': rows, 'groups': {row['group_id']: {} for row in rows}}, api)
        def score_existing(spec):
            row = spec['row']
            result = {'slot_id': row['slot_id'], 'slot_index': row['slot_index'], 'kind': spec['kind'],
                'original_result': spec['result'], 'new_model_calls': 0, 'original_generation_overwritten': False}
            if qualifications.get(row['instance_id'], {}).get('status') != 'qualified':
                return {**result, 'status': 'environment_unknown', 'qualification': qualifications.get(row['instance_id'])}
            request = None
            try:
                request = grading.prepare_score_recovery(spec)
                completed = grading.run_request(request, overall_stop)
                return {**result, 'status': completed.get('status', 'technical_unknown'),
                        'request': request, 'completion': completed,
                        'endpoint': scope.load(request).get('endpoint', 'code')}
            except Exception as error:
                return {**result, 'status': 'technical_unknown', 'request': request,
                        'error': {'type': type(error).__name__, 'message': str(error)}}
        def progress(value):
            with recovery_lock:
                extra = dict(recovered)
            snapshot('progress.json', {'generation_queue': value, 'recovered_scores': extra,
                'generation_tasks_planned': len(rows), 'score_only_tasks_planned': len(recovery_specs),
                'old_generations_imported_as_new': 0, 'shared_active_grader_limit': scope.MAX_GRADERS})
        def collect_existing(future, spec):
            try:
                value = future.result()
                receipt = write_new(scope.API_ROOT/f"score-recovery-{spec['row']['slot_index']}.json", value)
                with recovery_lock:
                    recovered[spec['row']['slot_id']] = {**value, 'record': receipt}
            except Exception as error:
                with recovery_lock:
                    callback_errors.append({'slot_id': spec['row']['slot_id'],
                                            'type': type(error).__name__, 'message': str(error)})
                fault('score_recovery_record_failed', None)
        def ceiling():
            capacity = scope.dispatch_view().physical_capacity()
            return scope.MAX_GENERATIONS if capacity['passed'] and os.getloadavg()[0] <= len(scope.host_cpu_pool())*.85 else 0
        def disk_check():
            value = scope.dispatch_view().physical_capacity()
            return {'passed': value['passed'], 'disk_free_bytes': value['disk_free_bytes'],
                'memory_available_bytes': value['memory_available_bytes'],
                'disk_floor': scope.CONSTRAINTS['disk_minimum_free_bytes'],
                'memory_floor': scope.CONSTRAINTS['memory_minimum_free_bytes']}
        with ThreadPoolExecutor(max_workers=scope.MAX_GRADERS) as existing_pool:
            existing = {existing_pool.submit(score_existing, spec): spec for spec in recovery_specs}
            for future, spec in existing.items():
                future.add_done_callback(lambda completed, spec=spec: collect_existing(completed, spec))
            generated = queue_module().execute_queue(rows, controls=[], qualifications=qualifications,
                grading=grading, runtime=NoLocalModel(), run_episode=impl.run_episode,
                api_runtime=api, stop_event=generation_stop, progress_sink=progress, event_sink=event,
                result_sink=recorder, generation_limit=ceiling,
                entered_probe=lambda row: (scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists(),
                disk_check=disk_check, model_exhausted=lambda _: False, initial_state={},
                cursor_sink=lambda value: snapshot('cursor.json', value),
                job_root=scope.API_ROOT/'async-grading-jobs', heartbeat_sink=progress)
            pending = {future for future in existing if not future.done()}
            while pending:
                progress({'phase': 'waiting_for_preserved_candidate_scores', 'active_generation': 0})
                _, pending = wait(pending, timeout=5, return_when=FIRST_COMPLETED)
        recorder.flush(final=True)
        if callback_errors:
            raise RuntimeError('Preserved-candidate completion evidence could not be retained: '+str(callback_errors))
        result = {'version': VERSION, 'plan': reference(scope.PLAN_FILE), 'finished_unix': time.time(),
            'new_generation': generated, 'recovered_scores': recovered,
            'original_generation_count_imported': 0, 'first_generation_count': len(rows),
            'preserved_candidate_score_count': len(recovery_specs), 'additional_diagnostics': 0,
            'additional_neutral_calls': 0, 'failure': generated.get('failure') or
                ({'kind': 'shared_scoring_cleanup_requires_review', 'faults': shared_faults} if shared_faults else None),
            'cash': api.budget_status(), 'all_prior_records_preserved': True}
        final = write_new(scope.API_ROOT/'run-summary.json', result)
        progress({'phase': 'closed' if not result['failure'] else 'review_required', 'summary': final,
                  'active_generation': 0, 'active_grading': 0})
        return result
    except BaseException as error:
        failure = {'version': VERSION, 'status': 'recovery_coordinator_failure',
            'error': {'type': type(error).__name__, 'message': str(error)}, 'no_automatic_retry': True}
        write_new(scope.API_ROOT/'coordinator-failure.json', failure)
        raise
    finally:
        terminate()
        for sig, handler in signals.items():
            signal.signal(sig, handler)
        active = list((scope.BATCH_ROOT/'resource-claims').glob('active-actor-*.json'))
        active += list((scope.BATCH_ROOT/'resource-claims').glob('active-grader-*.json'))
        if not active:
            scope.release_api_coordinator(lease)
        else:
            snapshot('cleanup-pending.json', {'active_claims': [str(path) for path in active],
                                             'manager_lease_retained': True, 'failure': failure})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
