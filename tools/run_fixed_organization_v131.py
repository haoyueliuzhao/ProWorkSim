"""Five cash-isolated asynchronous team queues with shared bounded resources."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import importlib.util
import inspect
import json
from pathlib import Path
import signal
import threading
import time
from types import ModuleType

from proworksim import software_benchmark_scope_v131 as scope
from proworksim import software_benchmark_async_queue_v082 as queue_base
from proworksim.software_benchmark_alignment_contract_v131 import GROUP_IDS, condition, shared_strategy
from proworksim.software_benchmark_host_api_v131 import DeepSeekRuntime, budget_status
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v131-five-cash-isolated-team-async-coordinator-r1'
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
    def __init__(self, matrix, api_runtime, output):
        super().__init__(matrix, api_runtime)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)

    def save_record(self, row, record):
        path = self.output/'usage-records'/f"{row['slot_index']}.json"
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
        atomic_write(self.output/'actual-usage-summary.json', json_bytes(report))
        if final:
            write_new(self.output/'actual-usage-records.json', {'version': VERSION,
                'record_files': {slot: value['record'] for slot, value in self.records.items()}})
        self.last_write = time.monotonic()


class NoLocalModel:
    start_residents = staticmethod(lambda: [])
    ready_residents = staticmethod(lambda: [])
    stop_residents = staticmethod(lambda: [])


class SharedAdmission:
    """Global identities, distinct startup tickets, and fair elastic group shares."""
    def __init__(self, runtime):
        self.runtime = runtime
        self.generation = threading.BoundedSemaphore(scope.MAX_GENERATIONS)
        self.startups = threading.BoundedSemaphore(scope.MAX_STARTUPS)
        self.lock = threading.RLock()
        self.active, self.starting, self.waiting_startup, self.finished = {}, set(), set(), set()
        self.healthy = set()

    def ceiling(self, group):
        capacity = scope.dispatch_view().physical_capacity()
        if not capacity['passed']:
            return 0
        with self.lock:
            counts = Counter(self.active.values())
            ready = [name for name in GROUP_IDS if name not in self.finished
                     and self.runtime.for_group(name).budget_status().get('can_start_generation')]
            if group not in ready:
                return counts[group]
            if group not in self.healthy and self.runtime.for_group(group).settled_route_witnesses():
                self.healthy.add(group)
            free = max(0, scope.MAX_GENERATIONS-len(self.active))
            base, remainder = divmod(free, len(ready))
            limit = counts[group]+base+(ready.index(group) < remainder)
            return min(limit, 1) if group not in self.healthy else limit

    @staticmethod
    def _acquire(semaphore, stop_event):
        while not semaphore.acquire(timeout=.2):
            if stop_event.is_set():
                raise InterruptedError('Cancelled before a new owned generation reservation')
        if stop_event.is_set():
            semaphore.release()
            raise InterruptedError('Cancelled before owned generation entry')

    def enter(self, row, stop_event):
        self._acquire(self.generation, stop_event)
        with self.lock:
            if row['slot_id'] in self.active:
                self.generation.release()
                raise ValueError('A team cannot acquire two generation identities')
            self.active[row['slot_id']] = row['organization_id']
            self.waiting_startup.add(row['slot_id'])
        try:
            self._acquire(self.startups, stop_event)
        except BaseException:
            with self.lock:
                self.active.pop(row['slot_id'])
                self.waiting_startup.remove(row['slot_id'])
            self.generation.release()
            raise
        with self.lock:
            self.waiting_startup.remove(row['slot_id'])
            self.starting.add(row['slot_id'])

    def ready(self, row):
        with self.lock:
            if row['slot_id'] in self.starting:
                self.starting.remove(row['slot_id'])
                self.startups.release()

    def leave(self, row):
        self.ready(row)
        with self.lock:
            if self.active.pop(row['slot_id'], None) is not None:
                self.generation.release()

    def snapshot(self):
        with self.lock:
            return {'generation_tickets_held': len(self.active), 'startup_tickets_held': len(self.starting),
                'waiting_for_startup_ticket': len(self.waiting_startup),
                'by_group': dict(Counter(self.active.values())), 'healthy_groups': sorted(self.healthy),
                'maximum_generation_pairs': scope.MAX_GENERATIONS, 'maximum_startups': scope.MAX_STARTUPS,
                'nominal_per_object_memory_not_summed_for_admission': True}


def local_preentry_error(error, row):
    """Only an identified private output-path failure is provably task-local."""
    folder = (scope.BATCH_ROOT/'episodes'/str(row['slot_index'])).resolve()
    if type(error) in {FileNotFoundError, NotADirectoryError, IsADirectoryError}:
        filename = getattr(error, 'filename', None)
        return isinstance(filename, str) and Path(filename).resolve().is_relative_to(folder)
    return (type(error) is ValueError
            and str(error) == 'An entered or partially prepared capability slot is not automatically replayed'
            and folder.exists())


def queue_module():
    """Retain the tested async queue; only cash stops become admission drains."""
    policy = scope.dispatch_view()
    namespace = clone_namespace(queue_base, policy=policy)

    class JobStore(queue_base.JobStore):
        def __init__(self, root, **kwargs):
            super().__init__(root, consumed_check=never_consumed, **kwargs)

    namespace['JobStore'] = JobStore
    namespace['executors'] = queue_base.executors
    namespace['local_preentry_error'] = local_preentry_error
    source = inspect.getsource(queue_base.execute_queue)
    old = """                        api_stop.set()
                        if hasattr(api_runtime, 'cancel_all'):
                            api_runtime.cancel_all()
                        event_sink('provider_stopped', provider='DEEPSEEK', reason=api_status['state'])"""
    new = """                        if api_status['state'] != 'cash_exhausted':
                            api_stop.set()
                            if hasattr(api_runtime, 'cancel_all'):
                                api_runtime.cancel_all()
                        event_sink('group_admission_stopped', provider='DEEPSEEK', reason=api_status['state'],
                                   inflight_cancelled=api_status['state'] != 'cash_exhausted')"""
    if source.count(old) != 1:
        raise ValueError('The single declared cash-stop insertion point changed')
    source = source.replace(old, new)
    old_preentry = """                        fail('generation_failed_without_trusted_result', slot_id=slot)"""
    new_preentry = """                        if generations[slot]['entered'] or not local_preentry_error(error, row):
                            fail('generation_failed_without_trusted_result', slot_id=slot)
                        else:
                            isolated('generation_preentry_exception_deferred', row, error=error_value(error))"""
    if source.count(old_preentry) != 1:
        raise ValueError('The single declared preentry-error insertion point changed')
    exec(compile(source.replace(old_preentry, new_preentry), __file__+':cash-draining-async-queue', 'exec'), namespace)
    module = ModuleType(__name__+'.private_cash_draining_queue')
    module.__dict__.update(namespace)
    return module


def diagnostic(implementation, plan):
    from proworksim.software_benchmark_generation_admission_v131 import diagnostic_descriptor, require_qualified
    diagnostics = plan['diagnostics']
    if len(diagnostics) != 1:
        raise ValueError('Exactly one predeclared four-member zero-model diagnostic is allowed')
    spec = diagnostics[0]
    matches = [row for row in plan['rows'] if row['slot_id'] == spec['slot_id']]
    if len(matches) != 1 or matches[0]['organization_id'] != 'CHIEF':
        raise ValueError('Bind the one CHIEF diagnostic identity')
    row = matches[0]
    result_ref = implementation._run(row, {}, diagnostic=True, diagnostic_index=scope.DIAGNOSTIC_INDEX)
    result = scope.load(result_ref)
    quiet = scope.load(result['quiescence'])
    child = scope.load(result['controller_result'])
    team = child.get('team_diagnostic', {})
    members = condition('CHIEF')['fixed_members']
    registry, sessions = child.get('actual_member_registry'), child.get('private_sessions')
    if (result.get('passed') is not True or result.get('model_calls') != 0
            or child.get('diagnostic_passed') is not True
            or team.get('passed') is not True or team.get('model_calls') != 0
            or team.get('organization_id') != 'CHIEF' or team.get('fixed_members') != members
            or set(team.get('registry_members', [])) != set(members)
            or not isinstance(registry, dict) or set(registry) != set(members)
            or any(not isinstance(record, dict) or record.get('status') != 'live' for record in registry.values())
            or not isinstance(sessions, dict) or set(sessions) != set(members)
            or any(not isinstance(value, str) or not value for value in sessions.values())
            or team.get('private_session_ids') != sessions
            or set(team.get('private_session_ids', {})) != set(members)
            or len(set(team.get('private_session_ids', {}).values())) != len(members)
            or child.get('execution_alignment') != shared_strategy('CHIEF')
            or quiet.get('quiescent') is not True or quiet.get('all_owned_objects_removed') is not True
            or quiet.get('cleanup_errors') != [] or quiet.get('create_result_unknown') is not False):
        raise ValueError('The actual four-member SDK diagnostic has not passed and cleaned up')
    descriptor = diagnostic_descriptor()
    fixture = require_qualified(child.get('public_fixture_qualification'), descriptor)
    return scope.retain(scope.PREPARATION_QUALIFICATION_FILE, {'version': VERSION, 'passed': True,
        'diagnostic': result_ref, 'quiescence': result['quiescence'], 'team_diagnostic': team,
        'actual_member_registry': registry, 'private_sessions': sessions, 'model_calls': 0,
        'public_fixture_descriptor': descriptor, 'public_fixture_qualification': fixture})


def cleanup_owned_parent(*, parent=None, record_path=None):
    """Best-effort final cleanup through the existing exact-owned empty gate.

    A refusal preserves the parent and records a deferred operation. This
    helper cannot replace the original experiment exception with its own.
    """
    approved, called = False, False
    try:
        if parent is None:
            from proworksim import software_benchmark_api_parent_v131 as parent
        parent.approved()
        approved = True
        called = True
        release = parent.stop_empty()
        outcome = {'status': 'released', 'parent_release': release, 'cleanup_deferred': False}
    except Exception as error:
        outcome = {'status': 'cleanup_deferred', 'cleanup_deferred': True,
            'error': {'type': type(error).__name__, 'message': str(error)},
            'owned_parent_preserved_for_review': True}
    outcome.update(version=VERSION, root_grant_verified=approved, stop_empty_called=called,
                   force_stop=False, scope='existing_exact_owned_empty_parent_gate')
    target = Path(record_path) if record_path is not None else scope.API_ROOT/'aggregate-parent-cleanup.json'
    try:
        receipt = scope.retain(target, outcome)
        return {**outcome, 'record': receipt}
    except Exception as error:
        # Even a full disk or conflicting receipt must not hide the task error.
        return {**outcome, 'record': None, 'audit_write_error': {
            'type': type(error).__name__, 'message': str(error)}}


def run():
    from proworksim.software_benchmark_episode_v131 import build_episode
    from proworksim.software_benchmark_grading_v131 import factory
    scope.require_allowed('v131.run')
    limits = scope.verify_host_limits()
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    if (scope.API_ROOT/'execution-started.json').exists():
        raise ValueError('An entered coordinator cannot silently restart')
    scope.API_ROOT.mkdir(parents=True, exist_ok=True)
    lease = scope.reserve_api_coordinator()
    global_stop = threading.Event()
    group_stops = {group: threading.Event() for group in GROUP_IDS}
    runtime = DeepSeekRuntime()
    gate = SharedAdmission(runtime)
    locks = threading.RLock()
    latest, completions, errors = {}, {}, {}

    def snapshot(path, value):
        atomic_write(path, json_bytes({'version': VERSION, 'unix': time.time(), **value}))

    def event(kind, **values):
        with locks, (scope.API_ROOT/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': kind, 'unix': time.time(), **values}, ensure_ascii=False)+'\n')

    def terminate(*_args):
        global_stop.set()
        for stop in group_stops.values():
            stop.set()
        runtime.cancel_all()

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, terminate)
    write_new(scope.API_ROOT/'execution-started.json', {'version': VERSION,
        'authorization': reference(scope.AUTH_FILE), 'plan': reference(scope.PLAN_FILE), 'host_limits': limits,
        'groups': list(GROUP_IDS), 'cash_cap_by_group_CNY': {group: '100.00' for group in GROUP_IDS},
        'old_ledgers_opened': False, 'model_neutral_calls': 0})
    monitor_stop = threading.Event()

    def monitor():
        while not monitor_stop.wait(5):
            with locks:
                progress = copy.deepcopy(latest)
            money = {group: budget_status(group) for group in GROUP_IDS}
            snapshot(scope.API_ROOT/'progress.json', {'phase': 'running', 'groups': progress,
                'cash_by_group': money, 'resource_admission': gate.snapshot(),
                'other_groups_cancelled_by_cash_stop': False, 'completed_groups': sorted(completions),
                'group_exceptions': copy.deepcopy(errors)})

    thread = None
    try:
        implementation = build_episode()
        preparation = diagnostic(implementation, plan)
        # Every grader, including initial controls, shares these same two slots.
        def scoring_fault(reason, request_ref):
            request = scope.load(request_ref)
            group = next((row['organization_id'] for row in plan['rows']
                          if row['slot_id'] == request.get('slot_id')), None)
            if group in group_stops:
                group_stops[group].set()
                runtime.cancel_group(group)
            else:
                terminate()
            event('owned_scoring_cleanup_unknown', group_id=group, reason=reason, request=request_ref)
        grading = SharedScoring(factory(watchdog_guard=lambda *_args, **_identity: None), fault=scoring_fault)
        prepared = grading.prepare_environment_qualifications()
        qualifications = dict(prepared['qualifications'])
        with ThreadPoolExecutor(max_workers=scope.MAX_GRADERS) as workers:
            futures = {workers.submit(grading.run_request, ref, global_stop): ref for ref in prepared['controls']}
            for future in as_completed(futures):
                request = scope.load(futures[future])
                try:
                    future.result()
                except Exception as error:
                    event('environment_control_deferred', instance_id=request['instance_id'],
                          error={'type': type(error).__name__, 'message': str(error)})
        for task in plan['environments']:
            if task not in qualifications:
                try:
                    qualifications[task] = grading.qualify(task)
                except Exception as error:
                    qualifications[task] = {'status': 'not_qualified', 'reason': 'environment_control_unknown',
                        'error': {'type': type(error).__name__, 'message': str(error)}}
        fixture = scope.load(preparation).get('public_fixture_qualification')
        if not isinstance(fixture, dict) or fixture.get('passed') is not True:
            qualifications['psf__requests-2931'] = {'status': 'not_qualified',
                'reason': 'public_fixture_environment_unknown', 'qualification': fixture}
        snapshot(scope.API_ROOT/'qualification-status.json', {'qualifications': qualifications})
        if global_stop.is_set():
            raise RuntimeError('Initial environment cleanup needs review before generation')
        runtime.initialize_for_run()
        thread = threading.Thread(target=monitor, name='v131-budget-and-progress-monitor', daemon=True)
        thread.start()

        def group_run(group):
            folder = scope.API_ROOT/'groups'/group
            folder.mkdir(parents=True, exist_ok=True)
            rows = [row for row in plan['rows'] if row['organization_id'] == group]
            view = runtime.for_group(group)
            recorder = UsageRecorder({'rows': rows, 'groups': {group: {}}}, view, folder)

            def progress(value):
                with locks:
                    latest[group] = value
                snapshot(folder/'progress.json', value)

            def episode(row, resident, *, stop_event, api_transport_factory):
                gate.enter(row, stop_event)
                try:
                    def after_ready(member_row, output):
                        gate.ready(member_row)
                        return api_transport_factory(member_row, output)
                    return implementation.run_episode(row, resident, stop_event=stop_event,
                                                       api_transport_factory=after_ready)
                finally:
                    gate.leave(row)

            try:
                result = queue_module().execute_queue(rows, controls=[], qualifications=qualifications,
                    grading=grading, runtime=NoLocalModel(), run_episode=episode, api_runtime=view,
                    stop_event=group_stops[group], progress_sink=progress,
                    event_sink=lambda kind, **values: event(kind, organization_id=group, **values),
                    result_sink=recorder, generation_limit=lambda: gate.ceiling(group),
                    entered_probe=lambda row: (scope.BATCH_ROOT/'resource-claims'/f"actor-{row['slot_index']}.json").exists(),
                    model_exhausted=lambda _: False, initial_state={},
                    cursor_sink=lambda value: snapshot(folder/'cursor.json', value),
                    job_root=folder/'async-grading-jobs', heartbeat_sink=progress)
                recorder.flush(final=True)
                result.update(version=VERSION, organization_id=group, plan=reference(scope.PLAN_FILE),
                    finished_unix=time.time(), planned_tasks=50, cash=budget_status(group),
                    cash_stop_does_not_cancel_inflight=True)
                ref = write_new(folder/'run-summary.json', result)
                with locks:
                    completions[group] = ref
                return ref
            except BaseException as error:
                group_stops[group].set()
                runtime.cancel_group(group)
                failure = {'type': type(error).__name__, 'message': str(error)}
                with locks:
                    errors[group] = failure
                write_new(folder/'coordinator-failure.json', {'version': VERSION, 'error': failure,
                    'other_groups_cancelled': False, 'automatic_retry': False})
                return None
            finally:
                with gate.lock:
                    gate.finished.add(group)

        with ThreadPoolExecutor(max_workers=len(GROUP_IDS)) as workers:
            for future in as_completed([workers.submit(group_run, group) for group in GROUP_IDS]):
                future.result()
        result = {'version': VERSION, 'plan': reference(scope.PLAN_FILE), 'finished_unix': time.time(),
            'group_summaries': completions, 'group_exceptions': errors,
            'cash_by_group': {group: budget_status(group) for group in GROUP_IDS},
            'planned_team_episodes': 250, 'actual_admission': gate.snapshot(),
            'cross_group_cash_borrowing': False, 'new_neutral_calls': 0}
        write_new(scope.API_ROOT/'run-summary.json', result)
        snapshot(scope.API_ROOT/'progress.json', {'phase': 'closed', **result})
        return result
    finally:
        monitor_stop.set()
        if thread is not None:
            thread.join(timeout=10)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        try:
            scope.release_api_coordinator(lease)
        finally:
            cleanup_owned_parent()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))


