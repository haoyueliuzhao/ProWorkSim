"""Run the new REF-only panel with async scoring under the cumulative cash cap."""
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

from proworksim import software_benchmark_scope_v126 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim.software_benchmark_episode_v126 import build_episode
from proworksim.software_benchmark_host_api_v126 import DeepSeekRuntime, ledger_read
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes
from proworksim.software_benchmark_prior_completion_v126 import require_prior_completion
from proworksim.software_benchmark_dispatch_control_v120 import DispatchAdmissionController

VERSION = 'v126-independent-ref-recovery-coordinator-r1'
TLS_TASKS = frozenset()


def validate_independent_recovery(plan):
    """Admit the two approved fresh attempts, retaining their called predecessors."""
    original_plan = scope.load(reference(scope.ORIGINAL_PLAN_FILE))
    originals = {row['slot_index']: row for row in original_plan['rows']}
    grant = scope.load(reference(scope.USER_GRANT_FILE))
    if (grant.get('status') != 'approved'
            or grant.get('explicit_user_reply') != '两题各新跑一次（推荐）'
            or grant.get('proposal') != reference(scope.USER_PROPOSAL_FILE)):
        raise ValueError('Two explicitly approved independent REF attempts are required')
    rows = plan['rows']
    if (len(rows) != 2 or {row['slot_index'] for row in rows} != {8800, 8801}
            or len({row['slot_id'] for row in rows}) != 2 or plan.get('diagnostics') != []):
        raise ValueError('Only the two fresh REF recovery identities are admitted')
    mapping = {8800: (7244, 20261104012600), 8801: (7251, 20261104012601)}
    keys = ('instance_id', 'condition_id', 'arm', 'execution_arm', 'model',
            'model_key', 'thinking', 'input_plus_output_tokens')
    for row in rows:
        old_index, seed = mapping[row['slot_index']]
        original = originals[old_index]
        if (row.get('original_slot_index') != old_index
                or row.get('original_slot_id') != original['slot_id']
                or row.get('seed') != seed or row['slot_id'] == original['slot_id']
                or row.get('analysis_endpoint') != 'independent_REF_recovery_v126'
                or any(row.get(key) != original.get(key) for key in keys)
                or row['arm'] != 'REF' or row['thinking'] is not False):
            raise ValueError('A recovery changed its original task, fixed new seed or REF policy')
        folder = scope.BATCH_ROOT/'episodes'/str(row['slot_index'])
        if ((scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists()
                or any((folder/name).exists() for name in ('entered.json', 'result.json'))):
            raise ValueError('This new independent attempt was already consumed')
    slots = [row['slot_id'] for row in rows]
    with ledger_read() as db:
        used = db.execute('SELECT request_id FROM requests WHERE slot_id IN (?,?) LIMIT 1', slots).fetchone()
    if used is not None:
        raise ValueError('An already-called recovery identity cannot be replayed')
    return plan


def reuse_preparation(plan):
    from proworksim.software_benchmark_alignment_contract_v110 import shared_strategy
    recovery = scope.load(reference(scope.RECOVERY_FILE))
    source = recovery['prior_preparation_qualification']
    expected = scope.ROOT/'runs/software-benchmark-v111/aligned-interface-r1/diagnostic-1/result.json'
    if source != reference(expected) or plan.get('diagnostics') != []:
        raise ValueError('Reuse only the original REF zero-model qualification')
    diagnostic = scope.load(source)
    quiet = scope.load(diagnostic['quiescence'])
    child = scope.load(diagnostic['controller_result'])
    if (diagnostic.get('passed') is not True or diagnostic.get('diagnostic_passed') is not True
            or diagnostic.get('arm') != 'REF' or diagnostic.get('model_calls') != 0
            or child.get('execution_alignment') != shared_strategy()
            or quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []
            or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('create_result_unknown') is not False):
        raise ValueError('The original REF diagnostic or cleanup is not trustworthy')
    return write_new(scope.API_ROOT/'preparation-reused.json', {'version': VERSION,
        'passed': True, 'original_REF_diagnostic': source, 'diagnostics_repeated': 0,
        'model_calls': 0, 'new_controls': 0, 'rejected_history_repair_controls': reference(scope.ROOT/'artifacts/software-benchmark-v126/rejected-history-sdk-r1/summary.json')})


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


class ArmHealthRamp:
    """Start with one REF episode, expand after its first settled response.

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
        if set(settled) == {'REF'}:
            self.passed = True
            self.receipt_sink('initial-routes-api-health.json', {'passed': True,
                'slot_ids': settled, 'next_generation_limit': scope.MAX_GENERATIONS,
                'basis': 'The new REF route has a settled response in a new planned attempt',
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
        impl = build_episode()
        preparation = reuse_preparation(plan)
        from proworksim.software_benchmark_grading_v126 import factory
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
            raise ValueError('Every original REF task needs its bound prior environment qualification')
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
            return admission.limit(health_gate.ceiling())
        def disk_check():
            value = scope.dispatch_view().physical_capacity()
            return {'passed': value['passed'],
                    'disk_free_bytes': value['disk_free_bytes'],
                    'memory_available_bytes': value['memory_available_bytes'],
                    'disk_floor': scope.CONSTRAINTS['disk_minimum_free_bytes'],
                    'memory_floor': scope.CONSTRAINTS['memory_minimum_free_bytes']}
        result = queue_module().execute_queue(plan['rows'], controls=[], qualifications=qualifications,
            grading=grading, runtime=NoLocalModel(), run_episode=impl.run_episode,
            api_runtime=api, stop_event=stop, progress_sink=lambda value: snapshot('progress.json', admission.annotate(value)),
            event_sink=event, result_sink=recorder, generation_limit=ceiling,
            entered_probe=lambda row: (scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists(),
            disk_check=disk_check, model_exhausted=lambda _: False, initial_state={},
            cursor_sink=lambda value: snapshot('cursor.json', value),
            job_root=scope.API_ROOT/'async-grading-jobs',
            heartbeat_sink=lambda value: snapshot('heartbeat.json', admission.annotate(value)))
        recorder.flush(final=True)
        result.update(version=VERSION, plan=reference(scope.PLAN_FILE), finished_unix=time.time(),
                      planned_tasks_per_group=2, original_panel_tasks=50, independent_recovery_tasks=2, old_results_preserved=True, arms=['REF'], thinking=False, original_results_overwritten=False,
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
