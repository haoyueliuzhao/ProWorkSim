"""Run the new PROJECT-only panel with async scoring under the cumulative cash cap."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading
import time
from types import ModuleType

from proworksim import software_benchmark_scope_v119 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim.software_benchmark_episode_v119 import build_episode
from proworksim.software_benchmark_host_api_v119 import DeepSeekRuntime
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v119-preformal-project-recovery-coordinator-r1'
TLS_TASKS = frozenset(('psf__requests-1766', 'psf__requests-1921'))


def validate_startup_recovery(plan):
    """Preserve the consumed zero-model attempt and admit only untouched rows."""
    recovery = scope.load(reference(scope.RECOVERY_FILE))
    expected = {'version': 'v119-project-zero-model-startup-recovery-r1',
        'old_diagnostic_measurement_retained': True, 'old_grading_preparation_failure_retained': True,
        'prior_created_containers': 2, 'prior_created_volumes': 1,
        'formal_model_calls': 0, 'neutral_model_calls': 0,
        'new_generation_attempts_beyond_original_50': 0, 'new_diagnostic_index': 2,
        'cumulative_maximum_containers': 304, 'cumulative_maximum_named_volumes': 52,
        'additional_cash': 0, 'old_model_generations_resampled': 0}
    if any(recovery.get(key) != value for key, value in expected.items()):
        raise ValueError('This recovery only replaces the preformal v118 startup')
    prior = scope.load(recovery['prior_plan'])
    if plan['rows'] != prior['rows'] or len(plan['diagnostics']) != 1 or plan['diagnostics'][0]['index'] != scope.DIAGNOSTIC_INDEX:
        raise ValueError('Keep all original formal rows and use only the new diagnostic identity')
    audit = scope.load(recovery['prior_call_audit'])
    if (audit.get('formal_requests') != 0 or audit.get('neutral_requests') != 0
            or audit.get('formal_entered_files') != [] or audit.get('active_claims') != []
            or audit.get('query_only') is not True):
        raise ValueError('Prior provider use must be explicitly audited before replay-free startup')
    diagnostic = scope.load(recovery['prior_diagnostic_result'])
    quiet = scope.load(diagnostic['quiescence'])
    writers = scope.load(recovery['prior_diagnostic_quiescence'])
    if (diagnostic.get('passed') is not True or diagnostic.get('model_calls') != 0
            or diagnostic.get('model_dispatch_started') is not False
            or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('retained_objects') != []
            or quiet.get('create_result_unknown') is not False or writers.get('all_quiet') is not True
            or writers.get('errors') != [] or writers.get('create_result_unknown_roles') != []
            or scope.load(recovery['prior_owner_release']).get('released') is not True):
        raise ValueError('The consumed diagnostic and prior owner must be fully quiescent')
    for row in plan['rows']:
        folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
        if ((scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists()
                or any((folder/name).exists() for name in ('entered.json', 'result.json'))):
            raise ValueError('A consumed formal episode cannot be restarted')
    return reference(scope.RECOVERY_FILE)


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

    def _cleanup_known(self, ref):
        try:
            return never_consumed(ref) or self.delegate.trustworthy_cleanup(ref) is True
        except Exception:
            return False

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
                try:
                    untouched = never_consumed(ref)
                except Exception:
                    untouched = False
                if untouched:
                    return {'status': 'not_started_cancelled', 'request': ref}
                self.fault('consumed_scoring_capacity_or_cancellation', ref)
                raise
            except Exception:
                if not self._cleanup_known(ref):
                    self.fault('unproven_scoring_cleanup', ref)
                raise
            if not self._cleanup_known(ref):
                self.fault('unproven_scoring_cleanup', ref)
                raise RuntimeError('A consumed scorer has no trusted cleanup proof')
            return result
        finally:
            for lock in reversed(held):
                lock.release()



def prepare_diagnostics(plan, impl, stop):
    """One new PROJECT-only zero-model pair qualifies this lifecycle before API."""
    from proworksim.software_benchmark_alignment_contract_v117 import shared_strategy
    results, public_fixtures = {}, {}
    specs = plan.get('diagnostics', [])
    if len(specs) != 1 or specs[0].get('index') != scope.DIAGNOSTIC_INDEX:
        raise ValueError('The separately authorized new PROJECT diagnostic index is required')
    for spec in specs:
        rows = [row for row in plan['rows'] if row['slot_id'] == spec['slot_id']]
        if len(rows) != 1 or rows[0]['arm'] != 'PROJECT' or rows[0]['arm'] in results:
            raise ValueError('Only the new PROJECT route may enter this diagnostic')
        row = rows[0]
        ref = impl._run(row, None, diagnostic=True, diagnostic_index=spec['index'], stop_event=stop)
        result = scope.load(ref)
        quiet = scope.load(result['quiescence'])
        child = scope.load(result['controller_result'])
        if (result.get('passed') is not True or result.get('model_calls') != 0
                or result.get('model_dispatch_started') is not False
                or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
                or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False
                or quiet.get('retained_objects') != [] or child.get('model_calls') != 0
                or child.get('diagnostic_passed') is not True
                or child.get('actual_SDK_initialized') is not True
                or child.get('execution_alignment') != shared_strategy()):
            raise ValueError('The new zero-model SDK, selected-test or closure preparation failed')
        results[row['arm']] = ref
        if row['instance_id'] == 'psf__requests-2931':
            from proworksim.software_benchmark_generation_admission_v119 import diagnostic_descriptor, qualification_valid
            descriptor = diagnostic_descriptor()
            fixture = child.get('public_fixture_qualification')
            public_fixtures[row['instance_id']] = {'diagnostic': ref,
                'controller_result': result['controller_result'], 'descriptor': descriptor,
                'qualification': fixture, 'qualified_for_generation': qualification_valid(fixture, descriptor)}
    if set(results) != {'PROJECT'}:
        raise ValueError('The new PROJECT route requires its own diagnostic')
    return write_new(scope.API_ROOT/'preparation-qualification.json', {
        'version': VERSION, 'passed': True, 'execution_alignment': shared_strategy(),
        'diagnostics': results, 'public_fixture_qualifications': public_fixtures,
        'model_calls': 0, 'previous_results_reused': False})


def apply_public_fixture_qualifications(qualifications, preparation):
    """A measured public-fixture failure blocks its task, never the other 49."""
    for task, record in scope.load(preparation).get('public_fixture_qualifications', {}).items():
        if record['qualified_for_generation'] is not True:
            qualifications[task] = {'status': 'not_qualified',
                'failure_reason': 'public_generation_fixture_environment_unknown',
                'public_fixture_diagnostic': record,
                'official_qualification': qualifications.get(task)}
    return qualifications


def old_helpers():
    spec = importlib.util.spec_from_file_location('v118_compact_usage_helpers',
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


class NoLocalModel:
    start_residents = staticmethod(lambda: [])
    ready_residents = staticmethod(lambda: [])
    stop_residents = staticmethod(lambda: [])


class ArmHealthRamp:
    """Start with one PROJECT episode, expand after its first settled response.

    A local task exception cannot freeze this gate. Subsequent preplanned rows
    may establish route health; scoring outcomes never enter this decision.
    """
    def __init__(self, rows, runtime, receipt_sink):
        self.rows, self.runtime, self.receipt_sink = {r['slot_id']: r for r in rows}, runtime, receipt_sink
        self.passed = False

    def ceiling(self):
        if self.passed:
            return scope.MAX_GENERATIONS
        settled = self.runtime.settled_route_witnesses()
        if any(slot not in self.rows or self.rows[slot]['arm'] != arm for arm, slot in settled.items()):
            raise ValueError('A route-health witness does not belong to the new planned panel')
        if set(settled) == {'PROJECT'}:
            self.passed = True
            self.receipt_sink('initial-routes-api-health.json', {'passed': True,
                'slot_ids': settled, 'next_generation_limit': scope.MAX_GENERATIONS,
                'basis': 'The new PROJECT route has a settled response in a new planned attempt',
                'local_failure_does_not_block_remaining_rows': True, 'score_used_for_admission': False})
        return scope.MAX_GENERATIONS if self.passed else min(1, scope.MAX_GENERATIONS)


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


def run():
    scope.require_allowed()
    limits = scope.verify_host_limits()
    plan = scope.load(reference(scope.PLAN_FILE))
    scope.validate_plan(plan)
    recovery = validate_startup_recovery(plan)
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('An entered coordinator is never automatically restarted')
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    lease = scope.reserve_api_coordinator()
    stop = threading.Event()
    api, failure = None, None
    def snapshot(name, value):
        atomic_write(scope.API_ROOT/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))
    def event(kind, **values):
        with (scope.API_ROOT/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'unix': time.time(), **values}, ensure_ascii=False)+'\n')
    prior_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def terminate(*_):
        stop.set()
        if api is not None:
            api.cancel_all()
    for sig in prior_signals:
        signal.signal(sig, terminate)
    write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION,
        'authorization': reference(scope.AUTH_FILE), 'plan': reference(scope.PLAN_FILE),
        'startup_recovery': recovery,
        'host_limits': limits, 'new_attempts': len(plan['rows']), 'API_cash_cap_CNY': scope.CASH_CAP_CNY,
        'old_queues_resumed': False, 'old_generation_records_imported': 0, 'training': False})
    try:
        scope.require_allowed()
        impl = build_episode(scope=scope, guard=scope.require_allowed)
        preparation = prepare_diagnostics(plan, impl, stop)
        from proworksim.software_benchmark_grading_v119 import factory
        def shared_fault(reason, request):
            stop.set()
            if api is not None:
                api.cancel_all()
            event('shared_cleanup_requires_review', reason=reason, request=request)
        grading = SharedScoring(factory(watchdog_guard=lambda *_args, **_identity: None), fault=shared_fault)
        qualification = grading.prepare_environment_qualifications()
        qualifications = dict(qualification['qualifications'])
        controls = qualification['controls']
        if controls:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(grading.run_request, ref, stop_event=stop): ref for ref in controls}
                for future in as_completed(futures):
                    ref = futures[future]
                    try:
                        future.result()
                    except Exception as error:
                        event('isolated_environment_control_error', request=ref,
                              error={'type': type(error).__name__, 'message': str(error)})
            if stop.is_set():
                raise RuntimeError('Environment controls stopped with unresolved cleanup or cancellation')
        for task in plan['environments']:
            if not isinstance(qualifications.get(task), dict) or qualifications[task].get('status') != 'qualified':
                try:
                    value = grading.qualify(task)
                    if isinstance(value, dict) and value.get('path'):
                        proof = scope.load(value)
                        qualifications[task] = {'status': 'qualified' if proof.get('passed') is True else 'not_qualified',
                                                'qualification': value}
                    elif isinstance(value, dict) and value.get('status') in {'qualified', 'not_qualified'}:
                        qualifications[task] = value
                    else:
                        raise ValueError('Environment qualification did not return a declared state')
                except Exception as error:
                    qualifications[task] = {'status': 'not_qualified',
                        'failure_reason': 'environment_qualification_error',
                        'error': {'type': type(error).__name__, 'message': str(error)}}
        apply_public_fixture_qualifications(qualifications, preparation)
        snapshot('qualification-status.json', {'qualifications': qualifications})
        api = DeepSeekRuntime()
        if any(qualifications.get(row['instance_id'], {}).get('status') == 'qualified' for row in plan['rows']):
            api.initialize_for_run()
        matrix = {'rows': plan['rows'], 'groups': {row['group_id']: {} for row in plan['rows']}}
        recorder = UsageRecorder(matrix, api)
        health_gate = ArmHealthRamp(plan['rows'], api, snapshot)
        def ceiling():
            capacity = scope.dispatch_view().physical_capacity()
            load = os.getloadavg()[0]
            if not capacity['passed'] or load > len(scope.host_cpu_pool())*.85:
                return 0
            return health_gate.ceiling()
        def disk_check():
            value = scope.dispatch_view().physical_capacity()
            return {'passed': value['passed'],
                    'disk_free_bytes': value['disk_free_bytes'],
                    'memory_available_bytes': value['memory_available_bytes'],
                    'disk_floor': scope.CONSTRAINTS['disk_minimum_free_bytes'],
                    'memory_floor': scope.CONSTRAINTS['memory_minimum_free_bytes']}
        result = queue_module().execute_queue(plan['rows'], controls=[], qualifications=qualifications,
            grading=grading, runtime=NoLocalModel(), run_episode=impl.run_episode,
            api_runtime=api, stop_event=stop, progress_sink=lambda value: snapshot('progress.json', value),
            event_sink=event, result_sink=recorder, generation_limit=ceiling,
            entered_probe=lambda row: (scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists(),
            disk_check=disk_check, model_exhausted=lambda _: False, initial_state={},
            cursor_sink=lambda value: snapshot('cursor.json', value),
            job_root=scope.API_ROOT/'async-grading-jobs',
            heartbeat_sink=lambda value: snapshot('heartbeat.json', value))
        recorder.flush(final=True)
        result.update(version=VERSION, plan=reference(scope.PLAN_FILE), finished_unix=time.time(),
                      planned_tasks_per_group=50, arms=['PROJECT'], thinking=False, original_results_overwritten=False,
                      preparation_qualification=preparation, imported_previous_attempts=0)
        final = write_new(scope.API_ROOT/'run-summary.json', result)
        snapshot('progress.json', {'phase': 'closed' if not result.get('failure') else 'review_required',
            'summary': final, 'generation_status_counts': dict(Counter(v['status'] for v in result['generation'].values())),
            'active_generation': 0, 'pending_grading_jobs': len(result.get('pending_grading_jobs', [])),
            'cash': api.budget_status()})
        return result
    except BaseException as error:
        failure = {'version': VERSION, 'status': 'preparation_or_coordinator_failure',
            'error': {'type': type(error).__name__, 'message': str(error)},
            'cash': api.budget_status() if api is not None else None,
            'no_automatic_retry': True}
        write_new(scope.API_ROOT/'coordinator-failure.json', failure)
        raise
    finally:
        stop.set()
        if api is not None:
            api.cancel_all()
        for sig, handler in prior_signals.items():
            signal.signal(sig, handler)
        active = list((scope.BATCH_ROOT/'resource-claims').glob('active-actor-*.json'))
        active += list((scope.BATCH_ROOT/'resource-claims').glob('active-grader-*.json'))
        if not active:
            scope.release_api_coordinator(lease)
        else:
            snapshot('cleanup-pending.json', {'active_claims': [str(p) for p in active],
                                             'manager_lease_retained': True, 'failure': failure})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
