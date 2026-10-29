"""API queue whose scoring preparation, delivery checks and reporting are workers.

No candidate selection, scoring validation or authoritative money admission is
removed. Only orchestration moves slow operations off the dispatch thread.
"""
from __future__ import annotations

from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import queue
import threading
import time

from . import software_benchmark_dispatch_v066 as policy
from .software_benchmark_candidates_v054 import checked, reference, write_new

VERSION = 'v082-API-asynchronous-grading-and-measurement-r1'
PENDING_DELIVERY = {'waiting_for_own_code_score', 'requires_separate_official_score'}
ROOT = policy.ROOT
_spec = importlib.util.spec_from_file_location('v082_frozen_coordinator', ROOT/'tools/run_full_benchmark_v066.py')
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


def load(ref):
    return json.loads(checked(ref).read_bytes())


def error_value(error):
    return {'type': type(error).__name__, 'message': str(error)[:4000]}


def delivery_can_advance(old, new):
    """Only the two original nonterminal dispositions may advance in handoff."""
    status = old.get('status')
    if status == 'waiting_for_own_code_score':
        if new.get('status') == 'requires_separate_official_score':
            return isinstance(new.get('scoring_request'), dict)
        if new.get('status') == 'official_attempt_completed':
            return isinstance(new.get('request'), dict)
        return new.get('status') in {'no_legal_delivery', 'same_tree_official_result_reused', 'technical_unknown'}
    if status == 'requires_separate_official_score':
        request = old.get('scoring_request')
        return (isinstance(request, dict) and new.get('status') == 'official_attempt_completed'
                and new.get('request') == request)
    return False


def not_consumed(request_ref):
    """Only exact never-started preparation can be retried after cancellation."""
    request = load(request_ref)
    folder = Path(request['directory'])
    if any((folder/name).exists() for name in ('capacity-claim.json', 'started.json', 'initial-container.json')):
        return False
    if folder.resolve() == policy.GRADING_ROOT/request['resource_key']:
        if (policy.BATCH_ROOT/'resource-claims'/(request['resource_key']+'.json')).exists():
            return False
    return True


class JobStore:
    """Durable immutable jobs; request publication precedes official execution."""
    def __init__(self, root, *, consumed_check=not_consumed):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.never_consumed = consumed_check
        self.lock = threading.Lock()
        self.states = {}

    def prepare(self, kind, row, item, prepared, result_ref):
        if kind not in {'code', 'delivery'} or type(row.get('slot_index')) is not int or row['slot_index'] < 0:
            raise ValueError('Only exact original code/delivery jobs are allowed')
        if type(prepared) is not bool or not isinstance(result_ref, dict):
            raise ValueError('A grading job requires its fixed generation result')
        value = {'version': VERSION, 'kind': kind, 'slot_id': row['slot_id'], 'row': row,
            'generation_result': result_ref, 'prepared_request': item if prepared else None,
            'preparation_candidate': None if prepared else item,
            'new_model_calls': 0, 'candidate_reselection': False}
        directory = self.root/f"{row['slot_index']:06d}-{kind}"
        directory.mkdir(exist_ok=True)
        target = directory/'job.json'
        if target.exists():
            if load(reference(target)) != value:
                raise ValueError('A grading identity cannot select a different candidate')
            return reference(target)
        return write_new(target, value)

    def validate(self, ref):
        path = checked(ref)
        if path.name != 'job.json' or path.parent.parent.resolve() != self.root.resolve():
            raise ValueError('Async recovery must use the exact owned job store')
        value = load(ref)
        if (value.get('version') != VERSION or value.get('kind') not in {'code', 'delivery'}
                or value['row']['slot_id'] != value.get('slot_id')
                or path.parent.name != f"{value['row']['slot_index']:06d}-{value['kind']}"):
            raise ValueError('Async job ownership or original task identity changed')
        return value

    def transition(self, ref, phase, **values):
        with self.lock:
            self.states[ref['sha256']] = {'job': ref, 'phase': phase, **values}

    def state(self, ref):
        with self.lock:
            return copy.deepcopy(self.states.get(ref['sha256'], {'job': ref, 'phase': 'queued'}))

    def run(self, ref, grading, stop):
        job = self.validate(ref)
        folder = Path(ref['path']).parent
        with (folder/'execution.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            final = folder/'outcome.json'
            if final.exists():
                outcome = load(reference(final))
                if outcome.get('job') != ref or outcome.get('version') != VERSION:
                    raise ValueError('Completed async job belongs to another immutable descriptor')
                self.transition(ref, 'complete', outcome=reference(final), request=outcome.get('request'))
                return outcome
            request_path = folder/'prepared-request.json'
            request = load(reference(request_path))['request'] if request_path.exists() else job['prepared_request']
            intent = folder/'execution-intent.json'
            if intent.exists():
                saved = load(reference(intent))
                request = saved.get('request')
                if saved.get('job') != ref or not request:
                    raise ValueError('Existing grading intent has no exact request identity')
                original = load(request)
                completion = Path(original['directory'])/'completion.json'
                if completion.exists():
                    done = load(reference(completion))
                    if done.get('request') != request or not grading.trustworthy_cleanup(request):
                        raise ValueError('Consumed scoring recovery lacks exact completion and cleanup')
                    outcome = self._after_execution(ref, job, request, done, grading)
                    return self._finish(ref, outcome, final)
                if not self.never_consumed(request):
                    raise ValueError('Consumed official scoring identity cannot be replayed')
                # An execution intent is not proof of a Docker start. The
                # original protocol writes the global claim before creation.
            if stop.is_set():
                self.transition(ref, 'deferred', request=request)
                return {'version': VERSION, 'job': ref, 'status': 'deferred', 'request': request}
            self.transition(ref, 'preparing', request=request)
            if request is None:
                try:
                    request = grading.prepare_score(job['preparation_candidate'], endpoint=job['kind'])
                except Exception as error:
                    outcome = {'version': VERSION, 'job': ref, 'status': 'preparation_unknown',
                        'request': None, 'preparation_error': error_value(error), 'fatal': False}
                    if job['kind'] == 'code':
                        outcome.update(self._delivery(job, None, grading))
                    return self._finish(ref, outcome, final)
            prepared = {'version': VERSION, 'job': ref, 'request': request}
            if request_path.exists():
                if load(reference(request_path)) != prepared:
                    raise ValueError('Prepared async request identity changed')
            else:
                write_new(request_path, prepared)
            self.transition(ref, 'prepared', request=request)
            if stop.is_set():
                self.transition(ref, 'deferred', request=request)
                return {'version': VERSION, 'job': ref, 'status': 'deferred', 'request': request}
            request_body = load(request)
            completion_path = Path(request_body['directory'])/'completion.json'
            if completion_path.exists():
                completion = load(reference(completion_path))
                if completion.get('request') != request or not grading.trustworthy_cleanup(request):
                    raise ValueError('Existing scoring completion is not bound to this exact request')
                outcome = self._after_execution(ref, job, request, completion, grading)
                return self._finish(ref, outcome, final)
            if not self.never_consumed(request):
                raise ValueError('An already consumed score lacks recoverable completion')
            if not intent.exists():
                write_new(intent, {'version': VERSION, 'job': ref, 'request': request,
                                   'unix': time.time(), 'official_resource_created_by_intent': False})
            self.transition(ref, 'executing', request=request)
            try:
                completion = grading.run_request(request, stop_event=stop)
            except Exception as error:
                completion = {'status': 'technical_unknown', 'error': error_value(error)}
            if completion.get('status') == 'not_started_cancelled' and self.never_consumed(request):
                self.transition(ref, 'deferred', request=request)
                return {'version': VERSION, 'job': ref, 'status': 'deferred', 'request': request}
            outcome = self._after_execution(ref, job, request, completion, grading)
            return self._finish(ref, outcome, final)

    def _delivery(self, job, request, grading):
        if job['row']['arm'] != 'PROJECT':
            return {}
        try:
            return {'delivery': grading.delivery_disposition(job['generation_result'], request)}
        except Exception as error:
            return {'delivery': {'status': 'technical_unknown', 'resolved': None,
                                  'error': error_value(error)}, 'delivery_error': error_value(error)}

    def _after_execution(self, ref, job, request, completion, grading):
        quiet = grading.trustworthy_cleanup(request)
        value = {'version': VERSION, 'job': ref, 'status': 'completed', 'request': request,
            'completion': completion, 'cleanup_proven': quiet, 'fatal': not quiet}
        if quiet and job['kind'] == 'code':
            self.transition(ref, 'checking_delivery', request=request)
            value.update(self._delivery(job, request, grading))
        return value

    def _finish(self, ref, value, path):
        outcome = write_new(path, value)
        self.transition(ref, 'complete', request=value.get('request'), outcome=outcome)
        return value


class Measurements:
    """One reporting owner; authoritative request admission stays on runtime."""
    def __init__(self, sink):
        self.sink = sink
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='v082-measurement')
        self.errors = queue.SimpleQueue()
        self.refresh = None
        self.last_refresh = 0.0
        self.closed = False

    def _call(self, row, entry, score, delivery):
        try:
            self.sink(row, entry, load(entry['result']) if entry.get('result') else None, score, delivery)
        except Exception as error:
            self.errors.put({'kind': 'usage_measurement', 'slot_id': row['slot_id'], 'error': error_value(error)})
            if hasattr(self.sink, 'mark_unknown'):
                try:
                    self.sink.mark_unknown(row, entry, str(error))
                except Exception as secondary:
                    self.errors.put({'kind': 'usage_measurement_unknown_record',
                                     'slot_id': row['slot_id'], 'error': error_value(secondary)})

    def update(self, row, entry, score, delivery):
        if self.sink is not None:
            self.pool.submit(self._call, copy.deepcopy(row), copy.deepcopy(entry),
                             copy.deepcopy(score), copy.deepcopy(delivery))

    def refresh_active(self, rows):
        if (self.closed or self.sink is None or not hasattr(self.sink, 'refresh_active')
                or time.monotonic()-self.last_refresh < 60
                or self.refresh is not None and not self.refresh.done()):
            return
        self.last_refresh = time.monotonic()
        def work():
            try:
                self.sink.refresh_active(copy.deepcopy(rows))
            except Exception as error:
                self.errors.put({'kind': 'live_usage_reporting', 'error': error_value(error)})
        self.refresh = self.pool.submit(work)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=True)


class Heartbeat:
    def __init__(self, sink, interval):
        self.sink, self.interval = sink, interval
        self.lock = threading.Lock()
        self.last, self.cycle = None, time.monotonic()
        self.stop = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, name='v082-progress-heartbeat', daemon=False)

    def start(self):
        self.thread.start()

    def publish(self, value):
        with self.lock:
            self.last, self.cycle = copy.deepcopy(value), time.monotonic()
            self._emit(False)

    def _emit(self, heartbeat_only):
        age = max(0.0, time.monotonic()-self.cycle)
        self.sink({**self.last, 'heartbeat_only': heartbeat_only,
            'scheduler_cycle_age_seconds': age, 'scheduler_stale': age > 5,
            'heartbeat_unix': time.time()})

    def _run(self):
        while not self.stop.wait(self.interval):
            try:
                with self.lock:
                    if self.last is not None:
                        self._emit(True)
            except Exception as error:
                self.error = error
                return

    def close(self):
        self.stop.set()
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise RuntimeError('Progress heartbeat did not finish')


@contextmanager
def executors(stop):
    with (ThreadPoolExecutor(max_workers=48) as generation,
          ThreadPoolExecutor(max_workers=3) as grading,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix='v082-handoff') as handoff):
        try:
            yield generation, grading, handoff
        finally:
            stop.set()


def factory(job_root, *, heartbeat_sink=None, heartbeat_interval=1.0):
    def bound(rows, **kwargs):
        return execute_queue(rows, job_root=job_root, heartbeat_sink=heartbeat_sink,
                             heartbeat_interval=heartbeat_interval, **kwargs)
    return bound


def execute_queue(rows, *, controls, qualifications, grading, runtime, run_episode,
                  api_runtime=None, stop_event=None, progress_sink=lambda _: None,
                  event_sink=lambda *a, **kw: None, disk_check=None, result_sink=None,
                  entered_probe=base._slot_entered, model_exhausted=None,
                  generation_limit=lambda: 48, initial_state=None, cursor_sink=lambda _: None,
                  job_root, heartbeat_sink=None, heartbeat_interval=1.0,
                  external_poll=None, external_pending=lambda: False):
    """API-only original slots, three complete scoring workers and fast dispatch."""
    if controls or api_runtime is None or any(row.get('model_key') != 'DEEPSEEK' for row in rows):
        raise ValueError('The async adapter accepts API generation and existing qualifications only')
    if len({row['slot_id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate task identity')
    initial = initial_state or {}
    if initial.get('retry_zero_generation'):
        raise ValueError('This continuation never replays any consumed generation')
    stop = stop_event if stop_event is not None else threading.Event()
    api_stop = threading.Event()
    episode_stop = base.ProviderStop(stop, api_stop)
    generations, scores, deliveries = (copy.deepcopy(initial.get(key, {})) for key in ('generation', 'scores', 'deliveries'))
    qualified = dict(qualifications)
    pending = [row for row in rows if row['slot_id'] not in generations]
    by_id = {row['slot_id']: row for row in rows}
    scheduled = set(generations)
    entered = {slot for slot, value in generations.items() if value.get('entered') is True}
    exceptions = copy.deepcopy(initial.get('exceptions', []))
    provider_failures = copy.deepcopy(initial.get('provider_failures', {}))
    if 'DEEPSEEK' in provider_failures:
        api_stop.set()
    store = JobStore(job_root)
    jobs, deferred, job_ids = deque(), [], set()
    generation_futures, grade_futures = {}, {}
    failure = disk_observation = api_status = None
    measurements = Measurements(result_sink)
    heartbeat = Heartbeat(heartbeat_sink or progress_sink, heartbeat_interval)
    last_cursor = None
    external_future, last_external_poll = None, 0.0
    external_disabled = False

    def fail(kind, **values):
        nonlocal failure
        failure = failure or {'kind': kind, **values}
        stop.set()

    def isolated(kind, row=None, **values):
        item = {'kind': kind, **({'slot_id': row['slot_id']} if row else {}), **values}
        exceptions.append(item)
        event_sink('isolated_exception', exception=item)

    def update(row):
        measurements.update(row, generations[row['slot_id']], scores.get(row['slot_id']), deliveries.get(row['slot_id']))

    def enqueue(kind, row, item, prepared, result_ref):
        key = kind, row['slot_id']
        if key in job_ids:
            return
        ref = store.prepare(kind, row, item, prepared, result_ref)
        jobs.append(ref)
        job_ids.add(key)

    def import_external(value):
        """Accept the sealed old-owner handoff, never widen new generation."""
        if value is None:
            return
        incoming = {key: value.get(key, {}) for key in ('generation', 'scores', 'deliveries')}
        for key, entries in incoming.items():
            if not isinstance(entries, dict):
                raise ValueError('External handoff must contain slot-keyed records')
            target = {'generation': generations, 'scores': scores, 'deliveries': deliveries}[key]
            for slot, entry in entries.items():
                if slot not in by_id or slot not in generations:
                    raise ValueError('External handoff cannot add an unreserved generation identity')
                old = target.get(slot)
                if old == entry:
                    continue
                if key == 'generation':
                    if not old or not str(old.get('status', '')).startswith('external_'):
                        raise ValueError('External handoff conflicts with a final generation record')
                else:
                    endpoint = 'code' if key == 'scores' else 'delivery'
                    if (endpoint, slot) in job_ids:
                        raise ValueError('External handoff conflicts with a locally owned grading identity')
                    if old is not None and not (key == 'deliveries' and delivery_can_advance(old, entry)):
                        raise ValueError('External handoff conflicts with an existing grading identity')
        # Validate the entire handoff before changing even the in-memory state.
        imported_jobs = value.get('pending_score_jobs', [])
        for kind, row, item, prepared in imported_jobs:
            if kind not in {'code', 'delivery'} or type(prepared) is not bool or not isinstance(item, dict):
                raise ValueError('External grading job has no valid endpoint and immutable reference')
            if by_id.get(row['slot_id']) != row or row['slot_id'] not in generations:
                raise ValueError('External scoring handoff differs from the original planned row')
            generation = incoming['generation'].get(row['slot_id'], generations[row['slot_id']])
            if generation.get('status') != 'closed' or not generation.get('result'):
                raise ValueError('External scoring requires an exact closed original generation')
            if kind == 'code' and row['slot_id'] in incoming['scores']:
                raise ValueError('External handoff contains both a completed and pending score')
            if kind == 'delivery':
                disposition = incoming['deliveries'].get(row['slot_id'], deliveries.get(row['slot_id']))
                if disposition is not None and not (
                        disposition.get('status') == 'requires_separate_official_score'
                        and prepared and disposition.get('scoring_request') == item):
                    raise ValueError('Pending delivery must match its exact nonterminal scoring request')
        descriptors = []
        for kind, row, item, prepared in imported_jobs:
            generation = incoming['generation'].get(row['slot_id'], generations[row['slot_id']])
            ref = store.prepare(kind, row, item, prepared, generation['result'])
            descriptors.append(((kind, row['slot_id']), ref))
        for key, entries in incoming.items():
            target = {'generation': generations, 'scores': scores, 'deliveries': deliveries}[key]
            target.update(copy.deepcopy(entries))
        for slot, entry in incoming['generation'].items():
            if entry.get('entered') is True:
                entered.add(slot)
        for key, ref in descriptors:
            if key not in job_ids:
                jobs.append(ref)
                job_ids.add(key)
        for slot in set().union(*(entries.keys() for entries in incoming.values())):
            update(by_id[slot])
        event_sink('external_handoff_imported', generation=len(incoming['generation']),
                   scores=len(incoming['scores']), deliveries=len(incoming['deliveries']),
                   pending_score_jobs=len(imported_jobs))

    for kind, row, item, prepared in initial.get('pending_score_jobs', []):
        if by_id.get(row['slot_id']) != row:
            raise ValueError('Recovered scoring row differs from the original planned row')
        enqueue(kind, row, item, prepared, generations[row['slot_id']]['result'])
    for ref in initial.get('pending_grading_jobs', []):
        job = store.validate(ref)
        if by_id.get(job['slot_id']) != job['row']:
            raise ValueError('Recovered async job differs from the original row')
        key = job['kind'], job['slot_id']
        if key not in job_ids:
            jobs.append(ref)
            job_ids.add(key)

    heartbeat.start()

    def generate(row, resident):
        result_ref = run_episode(row, resident, stop_event=episode_stop,
                                 api_transport_factory=api_runtime.transport_factory)
        result = load(result_ref)
        if result.get('slot_id') != row['slot_id'] or result.get('configuration') != row['configuration']:
            raise ValueError('Generation returned another fixed task identity')
        return result_ref, result, base.administrative_truncation(result)

    def report():
        nonlocal last_cursor
        for row in generation_futures.values():
            if entered_probe(row):
                entered.add(row['slot_id'])
        measurements.refresh_active([row for row in generation_futures.values() if row['slot_id'] in entered])
        while not measurements.errors.empty():
            item = measurements.errors.get()
            exceptions.append(item)
            event_sink('isolated_exception', exception=item)
        states = [store.state(ref) for ref in grade_futures.values()]
        active_requests = [item['request'] for item in states if item.get('request')]
        status_counts = Counter(value['status'] for value in generations.values())
        groups = {}
        for row in rows:
            group = groups.setdefault(row['group_id'], {'planned': 0, 'entered': 0, 'generation_closed': 0,
                'not_started': 0, 'technical_unknown': 0})
            group['planned'] += 1
            group['entered'] += row['slot_id'] in entered
            state = generations.get(row['slot_id'], {}).get('status')
            if state in {'closed', 'not_started', 'technical_unknown'}:
                group['generation_closed' if state == 'closed' else state] += 1
        payload = {'version': VERSION, 'phase': 'stopping' if stop.is_set() else 'running',
            'planned_generation': len(rows), 'scheduled_generation': len(scheduled),
            'entered_generation': len(entered), 'finished_generation': sum(v.get('entered') is True for v in generations.values()),
            'accounted_unentered_generation': sum(v.get('entered') is False for v in generations.values()),
            'pending_generation': len(pending), 'active_generation': len(generation_futures),
            'active_grading': len(grade_futures), 'pending_scores': len(jobs)+len(deferred), 'pending_controls': 0,
            'async_grading_stages': dict(Counter(item['phase'] for item in states)),
            'finished_code_scores': len(scores),
            'finished_delivery_endpoints': sum(v.get('status') not in PENDING_DELIVERY for v in deliveries.values()),
            'generation_status_counts': dict(status_counts), 'groups': groups, 'isolated_exception_count': len(exceptions),
            'failure': failure, 'disk_guard': disk_observation, 'api_status': api_status,
            'provider_failures': provider_failures, 'imported_original_attempts': len(initial.get('generation', {})),
            'authorized_zero_generation_continuations': 0, 'statistics_are_not_money_admission_authority': True}
        if heartbeat_sink is not None:
            progress_sink({**payload, 'heartbeat_only': False, 'scheduler_cycle_age_seconds': 0.0,
                           'scheduler_stale': False, 'heartbeat_unix': time.time()})
        heartbeat.publish(payload)
        signature = (len(pending), tuple(row['slot_id'] for row in generation_futures.values()),
            tuple((item['job']['sha256'], item['phase'], (item.get('request') or {}).get('sha256')) for item in states),
            tuple(ref['sha256'] for ref in jobs), tuple(ref['sha256'] for ref in deferred),
            len(generations), len(scores), len(deliveries), len(exceptions), stop.is_set())
        if signature != last_cursor:
            cursor_sink({'version': VERSION, 'phase': 'stopping' if stop.is_set() else 'running',
                'pending_generation': [row['slot_id'] for row in pending],
                'active_generation': [row['slot_id'] for row in generation_futures.values()],
                'active_grading': active_requests, 'active_grading_jobs': list(grade_futures.values()),
                'pending_grading_jobs': list(jobs)+deferred, 'pending_scores': [], 'pending_controls': [],
                'generation': copy.deepcopy(generations), 'scores': copy.deepcopy(scores),
                'deliveries': copy.deepcopy(deliveries), 'qualifications': qualified,
                'provider_failures': copy.deepcopy(provider_failures), 'failure': copy.deepcopy(failure),
                'resume_inventory': initial.get('inventory'), 'retry_zero_generation': {}, 'automatic_model_retry': False})
            last_cursor = signature

    def accept_grade(outcome, ref):
        job = store.validate(ref)
        row, slot, kind = job['row'], job['slot_id'], job['kind']
        if outcome.get('status') == 'deferred':
            deferred.append(ref)
            return
        if outcome.get('fatal'):
            fail('unproven_grader_cleanup', job=ref, request=outcome.get('request'))
        if outcome.get('request'):
            value = {'request': outcome['request'], 'completion': outcome.get('completion', {})}
            if kind == 'delivery':
                value['status'] = 'official_attempt_completed'
        else:
            value = {'status': 'technical_unknown', 'error': outcome.get('preparation_error')}
            isolated('score_preparation', row, endpoint=kind, error=outcome.get('preparation_error'))
        (scores if kind == 'code' else deliveries)[slot] = value
        if 'delivery' in outcome:
            deliveries[slot] = outcome['delivery']
            if outcome['delivery'].get('scoring_request'):
                enqueue('delivery', row, outcome['delivery']['scoring_request'], True, job['generation_result'])
        if outcome.get('delivery_error'):
            isolated('delivery_evidence_or_preparation', row, error=outcome['delivery_error'])
        update(row)
        event_sink('grading_finished', job_kind=kind, job=ref, request=outcome.get('request'),
                   status=outcome.get('completion', {}).get('status', outcome.get('status')))

    try:
        last_disk = 0.0
        with executors(stop) as (generation_pool, grade_pool, external_pool):
            while (pending or jobs or generation_futures or grade_futures or external_future is not None
                   or external_poll is not None and not external_disabled and external_pending()):
                if stop.is_set() and failure is None:
                    fail('coordinator_cancellation_requested')
                if heartbeat.error is not None:
                    raise heartbeat.error
                if external_future is not None and external_future.done():
                    try:
                        import_external(external_future.result())
                    except Exception as error:
                        external_disabled = True
                        isolated('external_handoff_requires_review', error=error_value(error))
                    external_future = None
                if (not stop.is_set() and external_poll is not None and external_future is None
                        and not external_disabled and external_pending()
                        and time.monotonic()-last_external_poll >= 1):
                    last_external_poll = time.monotonic()
                    external_future = external_pool.submit(external_poll)
                if disk_check is not None and time.monotonic()-last_disk >= 5:
                    disk_observation, last_disk = disk_check(), time.monotonic()
                    if disk_observation.get('passed') is not True:
                        fail('disk_free_space_floor', observation=disk_observation)
                try:
                    api_status = api_runtime.budget_status()
                except Exception as error:
                    api_status = {'state': 'shared_halted', 'reason': error_value(error)}
                if api_status.get('state') in {'shared_halted', 'qualification_failed', 'cash_exhausted', 'authentication_failed'}:
                    if 'DEEPSEEK' not in provider_failures:
                        reason = ('api_monetary_budget_exhausted' if api_status['state'] == 'cash_exhausted'
                                  else 'api_'+api_status['state'])
                        provider_failures['DEEPSEEK'] = {'scope': 'provider', 'reason': reason}
                        api_stop.set()
                        if hasattr(api_runtime, 'cancel_all'):
                            api_runtime.cancel_all()
                        event_sink('provider_stopped', provider='DEEPSEEK', reason=api_status['state'])
                # Collect first so a completed slot does not delay replacement
                # behind a slow scoring preparation from the same loop.
                completed = [future for future in (*grade_futures, *generation_futures) if future.done()]
                for future in completed:
                    if future in grade_futures:
                        ref = grade_futures.pop(future)
                        try:
                            accept_grade(future.result(), ref)
                        except Exception as error:
                            deferred.append(ref)
                            fail('unproven_async_grader_outcome', job=ref, error=error_value(error))
                        continue
                    row = generation_futures.pop(future)
                    slot = row['slot_id']
                    try:
                        ref, result, administrative = future.result()
                        entered.add(slot)
                        generations[slot] = {'result': ref, 'status': result.get('status'), 'entered': True,
                            'administrative_truncation': administrative,
                            'retained_objects': result.get('retained_objects', []), 'prior_zero_generation_attempt': None}
                        reason = base.generation_stop_reason(result, row, api_status)
                        if reason and reason['scope'] == 'global':
                            fail(reason['reason'], result=ref)
                        elif reason and reason['scope'] == 'provider':
                            provider_failures['DEEPSEEK'] = reason
                            api_stop.set()
                        if result.get('status') == 'closed' and (not reason or reason['scope'] != 'global'):
                            enqueue('code', row, ref, False, ref)
                        elif result.get('status') != 'closed':
                            isolated('generation_technical_unknown', row, result=ref)
                        update(row)
                    except (policy.ResourceBusy, InterruptedError) as error:
                        if entered_probe(row):
                            fail('generation_capacity_or_cancel_without_cleanup', slot_id=slot, error=error_value(error))
                        else:
                            scheduled.remove(slot)
                            pending.append(row)
                            pending.sort(key=lambda value: value['slot_index'])
                    except Exception as error:
                        generations[slot] = {'status': 'technical_unknown', 'entered': entered_probe(row),
                                             'error': error_value(error)}
                        fail('generation_failed_without_trusted_result', slot_id=slot)
                    event_sink('generation_finished', slot_id=slot, status=generations.get(slot, {}).get('status', 'not_entered'))
                for row in list(pending):
                    qualification = qualified.get(row['instance_id'], {})
                    reason = ('environment_not_qualified' if qualification.get('status') == 'not_qualified' else
                        provider_failures.get('DEEPSEEK', {}).get('reason'))
                    if reason:
                        pending.remove(row)
                        generations[row['slot_id']] = {'status': 'not_started', 'entered': False,
                            'not_started_reason': reason, 'qualification': qualification}
                        update(row)
                        event_sink('generation_not_started', slot_id=row['slot_id'], reason=reason)
                while not stop.is_set() and jobs and len(grade_futures) < 3:
                    ref = jobs.popleft()
                    grade_futures[grade_pool.submit(store.run, ref, grading, stop)] = ref
                ceiling = generation_limit()
                if type(ceiling) is not int or not 0 <= ceiling <= 48:
                    raise ValueError('Generation ceiling must remain within 0..48')
                while (not stop.is_set() and not api_stop.is_set() and len(generation_futures) < ceiling
                       and api_status.get('can_start_generation') is True):
                    row = next((value for value in pending if qualified.get(value['instance_id'], {}).get('status') == 'qualified'), None)
                    if row is None:
                        break
                    slot = row['slot_id']
                    if slot in scheduled:
                        raise RuntimeError('A consumed task was returned to pending generation')
                    resident = api_runtime.logical_resident()
                    pending.remove(row)
                    scheduled.add(slot)
                    event_sink('generation_scheduled', slot_id=slot, model_key='DEEPSEEK', resident='deepseek-direct-api')
                    generation_futures[generation_pool.submit(generate, row, resident)] = row
                report()
                if stop.is_set() and not grade_futures and not generation_futures:
                    break
                futures = list(grade_futures)+list(generation_futures)
                if external_future is not None:
                    futures.append(external_future)
                if futures:
                    wait(futures, timeout=.2, return_when=FIRST_COMPLETED)
                else:
                    stop.wait(.2)
    except Exception as error:
        fail('coordinator_error', error=error_value(error))
    finally:
        stop.set()
        measurements.close()
        try:
            report()
        finally:
            heartbeat.close()
    return {'version': VERSION, 'generation': generations, 'scores': scores, 'deliveries': deliveries,
        'qualifications': qualified, 'exceptions': exceptions,
        'unentered_generation': [row['slot_id'] for row in pending], 'unentered_controls': [],
        'unentered_scores': [], 'pending_grading_jobs': list(jobs)+deferred+list(grade_futures.values()),
        'resident_closure': [], 'failure': failure, 'last_disk_guard': disk_observation,
        'last_api_status': api_status, 'automatic_replay': False, 'historical_results_overwritten': False,
        'provider_failures': provider_failures, 'continuation_inventory': initial.get('inventory'),
        'external_handoff_requires_review': external_disabled,
        'preserved_prior_zero_generation_attempts': {},
        'retained_objects': [{'slot_id': slot, **obj} for slot, value in generations.items()
                             for obj in value.get('retained_objects', [])]}
