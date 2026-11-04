"""Run the new PROJECT-only panel with async scoring under the cumulative cash cap."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading
import time
from types import ModuleType

from proworksim import software_benchmark_scope_v121 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim.software_benchmark_episode_v121 import build_episode
from proworksim.software_benchmark_host_api_v121 import DeepSeekRuntime, ledger_read
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes
from proworksim.software_benchmark_prior_completion_v121 import require_prior_completion
from proworksim.software_benchmark_dispatch_control_v120 import DispatchAdmissionController, write_control

VERSION = 'v121-independent27-project-recovery-coordinator-r1'
TLS_TASKS = frozenset(('psf__requests-1766', 'psf__requests-1921'))


def validate_independent_recovery(plan):
    """Admit27 explicitly new attempts; original called attempts remain intact."""
    panel = scope.load(plan['panel'])
    inventory = scope.load(panel['source_inventory'])
    held = {item['row']['slot_id']: item for item in inventory['rows']}
    proposed = {row['slot_id']: row for row in panel['rows']}
    rows = plan['rows']
    if (len(rows) != 27 or len({row['slot_id'] for row in rows}) != 27
            or len({row['instance_id'] for row in rows}) != 27
            or {row['slot_index'] for row in rows} != set(range(8500, 8527))
            or {row['slot_id'] for row in rows} != set(proposed)
            or {row['original_slot_id'] for row in rows} != set(held)
            or set(proposed) & set(held) or plan.get('diagnostics') != []):
        raise ValueError('Only the explicitly authorized27 new mapped recovery attempts are admitted')
    for row in rows:
        original = held[row['original_slot_id']]['row']
        if (any(row.get(key) != proposed[row['slot_id']].get(key) for key in (
                'slot_id', 'slot_index', 'seed', 'instance_id', 'condition_id', 'analysis_endpoint',
                'original_slot_id', 'original_slot_index', 'old_result_overwritten'))
                or row['instance_id'] != original['instance_id']
                or row['original_slot_index'] != original['slot_index']
                or row['seed'] == original['seed'] or row['old_result_overwritten'] is not False
                or row['analysis_endpoint'] != 'independent_recovery_v121'):
            raise ValueError('Independent attempts must preserve their mapping without replacing old outcomes')
        folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
        if ((scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists()
                or any((folder/name).exists() for name in ('entered.json', 'result.json'))):
            raise ValueError('A new physical recovery attempt was already consumed')
    slots = [row['slot_id'] for row in rows]
    with ledger_read() as db:
        used = db.execute('SELECT request_id FROM requests WHERE slot_id IN ('
                          + ','.join('?' for _ in slots) + ') LIMIT 1', slots).fetchone()
    if used is not None:
        raise ValueError('This independent recovery never automatically replays an already-used new ID')
    return plan


def reuse_preparation(plan):
    from proworksim.software_benchmark_alignment_contract_v117 import shared_strategy
    from proworksim.software_benchmark_generation_admission_v119 import qualification_valid
    recovery = scope.load(reference(scope.RECOVERY_FILE))
    source = recovery['prior_preparation_qualification']
    if source != reference(scope.ROOT/'runs/software-benchmark-v118/project-repaired-r1/api-coordinator-v119/preparation-qualification.json'):
        raise ValueError('Preparation must be the frozen prior owner receipt')
    prior = scope.load(source)
    if (prior.get('passed') is not True or prior.get('model_calls') != 0
            or prior.get('execution_alignment') != shared_strategy()
            or set(prior.get('diagnostics', {})) != {'PROJECT'} or plan.get('diagnostics') != []
            or set(prior.get('public_fixture_qualifications', {})) != {'psf__requests-2931'}):
        raise ValueError('Reuse requires the actual prior aligned zero-model SDK qualification')
    diagnostic = scope.load(prior['diagnostics']['PROJECT'])
    quiet = scope.load(diagnostic['quiescence'])
    if (diagnostic.get('passed') is not True or diagnostic.get('model_calls') != 0
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('all_owned_objects_removed') is not True or quiet.get('create_result_unknown') is not False):
        raise ValueError('The old diagnostic has not closed cleanly')
    for task, record in prior.get('public_fixture_qualifications', {}).items():
        if task != 'psf__requests-2931' or not qualification_valid(record['qualification'], record['descriptor']):
            raise ValueError('The original public fixture qualification is not trustworthy')
    return write_new(scope.API_ROOT/'preparation-reused.json', {'version': VERSION,
        'passed': True, 'original_preparation': source, 'diagnostics_repeated': 0,
        'public_fixture_qualifications': prior['public_fixture_qualifications'],
        'model_calls': 0, 'new_controls': 0})


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


class RepeatedIntegrityDrain:
    """Two distinct tasks at the same trusted managed boundary pause admission."""
    def __init__(self, rows, admission, event):
        self.rows = {row['slot_id']: row for row in rows}
        self.admission, self.event = admission, event
        self.seen, self.triggered, self.lock = {}, False, threading.Lock()

    def observe(self, row, result_ref):
        from proworksim.software_benchmark_alignment_contract_v117 import shared_strategy
        if self.rows.get(row['slot_id']) != row:
            raise ValueError('Integrity monitoring only accepts this stage\'s exact row')
        result = scope.load(result_ref)
        if result.get('status') != 'technical_unknown' or not result.get('controller_result'):
            return
        if (result.get('slot_id') != row['slot_id'] or result.get('instance_id') != row['instance_id']
                or result.get('configuration') != row['configuration']):
            raise ValueError('Integrity evidence belongs to another original attempt')
        child = scope.load(result['controller_result'])
        boundary = child.get('managed_boundary', {})
        failure = boundary.get('execution_integrity_failure')
        if (child.get('slot_id') != row['slot_id'] or child.get('condition_id') != row['condition_id']
                or child.get('execution_alignment') != shared_strategy()
                or child.get('arm') != 'PROJECT' or boundary.get('status') != 'execution_integrity_blocked'
                or not isinstance(failure, dict) or failure.get('status') != 'execution_integrity_error'):
            return
        quiet = scope.load(result['quiescence'])
        if (quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
                or quiet.get('create_result_unknown') is not False):
            return  # Existing queue integrity handling owns unsafe cleanup.
        with self.lock:
            self.seen.setdefault(row['instance_id'], {'row': row, 'result': result_ref,
                'controller_result': result['controller_result'], 'failure': failure})
            if len(self.seen) < 2 or self.triggered:
                return
            control = write_control(reference(scope.PLAN_FILE), mode='drain',
                reason='Automatic admission pause: two distinct tasks reached the trusted managed execution_integrity_error boundary')
            proof = write_new(scope.API_ROOT/'automatic-integrity-drain.json', {
                'version': VERSION, 'family': 'managed_execution_integrity_error',
                'distinct_tasks': sorted(self.seen), 'evidence': list(self.seen.values()),
                'control': control, 'inflight_cancelled': False, 'scoring_allowed': True,
                'ordinary_code_failure_triggers_drain': False, 'automatic_resume': False})
            self.triggered = True
            self.event('automatic_generation_admission_drained', evidence=proof)


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
    prior_completion = require_prior_completion()
    scope.require_allowed()
    limits = scope.verify_host_limits()
    plan = scope.load(reference(scope.PLAN_FILE))
    scope.validate_plan(plan)
    validate_independent_recovery(plan)
    admission = DispatchAdmissionController(reference(scope.PLAN_FILE))
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
        'startup_recovery': reference(scope.RECOVERY_FILE), 'prior_completion': prior_completion,
        'host_limits': limits, 'new_attempts': len(plan['rows']), 'API_cash_cap_CNY': scope.CASH_CAP_CNY,
        'old_queues_resumed': False, 'old_generation_records_imported': 0, 'training': False})
    try:
        scope.require_allowed()
        impl = build_episode(scope=scope, guard=scope.require_allowed)
        preparation = reuse_preparation(plan)
        from proworksim.software_benchmark_grading_v121 import factory
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
            raise ValueError('This stage has no allowance for new environment controls')
        if any(not isinstance(qualifications.get(row['instance_id']), dict)
                or qualifications[row['instance_id']].get('status') != 'qualified' for row in plan['rows']):
            raise ValueError('Every retained first-generation task needs its bound prior environment qualification')
        snapshot('qualification-status.json', {'qualifications': qualifications})
        api = DeepSeekRuntime()
        if any(qualifications.get(row['instance_id'], {}).get('status') == 'qualified' for row in plan['rows']):
            api.initialize_for_run()
        matrix = {'rows': plan['rows'], 'groups': {row['group_id']: {} for row in plan['rows']}}
        recorder = UsageRecorder(matrix, api)
        integrity_monitor = RepeatedIntegrityDrain(plan['rows'], admission, event)
        def run_episode(row, resident, **kwargs):
            result_ref = impl.run_episode(row, resident, **kwargs)
            try:
                integrity_monitor.observe(row, result_ref)
            except Exception as error:
                event('admission_monitor_error', slot_id=row['slot_id'],
                      error={'type': type(error).__name__, 'message': str(error)})
            return result_ref
        health_gate = ArmHealthRamp(plan['rows'], api, snapshot)
        def ceiling():
            capacity = scope.dispatch_view().physical_capacity()
            load = os.getloadavg()[0]
            if not capacity['passed'] or load > len(scope.host_cpu_pool())*.85:
                return 0
            return admission.limit(health_gate.ceiling())
        def disk_check():
            value = scope.dispatch_view().physical_capacity()
            return {'passed': value['passed'],
                    'disk_free_bytes': value['disk_free_bytes'],
                    'memory_available_bytes': value['memory_available_bytes'],
                    'disk_floor': scope.CONSTRAINTS['disk_minimum_free_bytes'],
                    'memory_floor': scope.CONSTRAINTS['memory_minimum_free_bytes']}
        result = queue_module().execute_queue(plan['rows'], controls=[], qualifications=qualifications,
            grading=grading, runtime=NoLocalModel(), run_episode=run_episode,
            api_runtime=api, stop_event=stop, progress_sink=lambda value: snapshot('progress.json', admission.annotate(value)),
            event_sink=event, result_sink=recorder, generation_limit=ceiling,
            entered_probe=lambda row: (scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists(),
            disk_check=disk_check, model_exhausted=lambda _: False, initial_state={},
            cursor_sink=lambda value: snapshot('cursor.json', value),
            job_root=scope.API_ROOT/'async-grading-jobs',
            heartbeat_sink=lambda value: snapshot('heartbeat.json', admission.annotate(value)))
        recorder.flush(final=True)
        result.update(version=VERSION, plan=reference(scope.PLAN_FILE), finished_unix=time.time(),
                      planned_tasks_per_group=27, original_panel_tasks=50, independent_recovery_tasks=27, old_results_preserved=True, arms=['PROJECT'], thinking=False, original_results_overwritten=False,
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
