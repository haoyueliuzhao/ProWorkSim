"""Run the new paired panel with async scoring under the cumulative cash cap."""
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

from proworksim import software_benchmark_scope_v112 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim.software_benchmark_episode_v110 import build_episode
from proworksim.software_benchmark_host_api_v112 import DeepSeekRuntime
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v112-sixteen-pair-asynchronous-coordinator-r1'


def prepare_diagnostics(plan, impl, stop):
    """The two declared zero-model pairs qualify this new lifecycle before API."""
    from proworksim.software_benchmark_alignment_contract_v110 import shared_strategy
    results = {}
    specs = plan.get('diagnostics', [])
    if len(specs) != 2:
        raise ValueError('Two separately authorized new diagnostic pairs are required')
    for spec in specs:
        rows = [row for row in plan['rows'] if row['slot_id'] == spec['slot_id']]
        if len(rows) != 1 or rows[0]['arm'] in results:
            raise ValueError('Each new REF/PROJECT route needs exactly one zero-model diagnostic')
        row = rows[0]
        ref = impl._run(row, None, diagnostic=True, diagnostic_index=spec['index'], stop_event=stop)
        result = scope.load(ref)
        quiet = scope.load(result['quiescence'])
        child = scope.load(result['controller_result'])
        if (result.get('passed') is not True or result.get('model_calls') != 0
                or result.get('model_dispatch_started') is not False
                or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
                or quiet.get('cleanup_errors') != [] or child.get('model_calls') != 0
                or child.get('diagnostic_passed') is not True
                or child.get('actual_SDK_initialized') is not True
                or child.get('execution_alignment') != shared_strategy()):
            raise ValueError('The new zero-model SDK, selected-test or closure preparation failed')
        results[row['arm']] = ref
    if set(results) != {'REF', 'PROJECT'}:
        raise ValueError('Both new execution routes require their own diagnostic')
    return write_new(scope.API_ROOT/'preparation-qualification.json', {
        'version': VERSION, 'passed': True, 'execution_alignment': shared_strategy(),
        'diagnostics': results, 'model_calls': 0, 'previous_results_reused': False})


def old_helpers():
    spec = importlib.util.spec_from_file_location('v112_compact_usage_helpers',
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
    """Start with two live episodes, expand after both routes settle real usage.

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
        if set(settled) == {'REF', 'PROJECT'}:
            self.passed = True
            self.receipt_sink('initial-routes-api-health.json', {'passed': True,
                'slot_ids': settled, 'next_generation_limit': scope.MAX_GENERATIONS,
                'basis': 'Each route has an authoritative settled response in its original planned task',
                'local_failure_does_not_block_remaining_rows': True, 'score_used_for_admission': False})
        return scope.MAX_GENERATIONS if self.passed else min(2, scope.MAX_GENERATIONS)


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
        'host_limits': limits, 'new_attempts': len(plan['rows']), 'API_cash_cap_CNY': scope.CASH_CAP_CNY,
        'old_queues_resumed': False, 'old_generation_records_imported': 0, 'training': False})
    try:
        scope.require_allowed()
        impl = build_episode(scope=scope, guard=scope.require_allowed)
        preparation = prepare_diagnostics(plan, impl, stop)
        api = DeepSeekRuntime()
        api.initialize_for_run()
        from proworksim.software_benchmark_grading_v112 import factory
        grading = factory(watchdog_guard=lambda *_args, **_identity: None)
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
            for task in plan['environments']:
                if task not in qualifications or qualifications[task].get('status') != 'qualified':
                    try:
                        value = grading.qualify(task)
                        if isinstance(value, dict) and value.get('path'):
                            proof = scope.load(value)
                            qualifications[task] = {'status': 'qualified' if proof.get('passed') is True else 'not_qualified',
                                                    'qualification': value}
                        else:
                            qualifications[task] = value
                    except Exception as error:
                        qualifications[task] = {'status': 'not_qualified',
                            'failure_reason': 'environment_qualification_error',
                            'error': {'type': type(error).__name__, 'message': str(error)}}
        snapshot('qualification-status.json', {'qualifications': qualifications})
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
                      planned_tasks_per_group=50, thinking=False, original_results_overwritten=False,
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
