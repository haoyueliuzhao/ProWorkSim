"""Run original tasks under observed headroom, without reloading resident models."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import importlib.util
import json
from pathlib import Path
import secrets
import threading
import time

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim import software_benchmark_dispatch_v066 as original
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v076-observed-headroom-concurrency-r1'
ROOT = scope.ROOT


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


qwen_base = module('v076_frozen_qwen', 'run_full_benchmark_v068.py')
api_base = module('v076_frozen_api', 'run_api_expansion_v069.py')
base = qwen_base.base


@contextmanager
def executors(stop):
    with ThreadPoolExecutor(max_workers=48) as generation, ThreadPoolExecutor(max_workers=3) as grading:
        try:
            yield generation, grading
        finally:
            stop.set()


class LocalStop:
    def __init__(self, parent, local):
        self.parent, self.local = parent, local

    def is_set(self):
        return self.parent.is_set() or self.local.is_set()

    def wait(self, timeout=None):
        end = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            if end is not None and time.monotonic() >= end:
                return False
            self.local.wait(.1 if end is None else min(.1, max(0, end-time.monotonic())))
        return True


class EpisodeRegistry:
    """Abort callbacks can only set a local Event owned by this running queue."""
    def __init__(self, event):
        self.lock, self.entries, self.event = threading.Lock(), {}, event

    def add(self, row):
        slot = row['slot_id']
        with self.lock:
            if slot in self.entries or row['model_key'] != 'DEEPSEEK':
                raise ValueError('Only a unique current API episode can enter pressure registry')
            self.entries[slot] = {'slot_id': slot, 'model_key': 'DEEPSEEK',
                'started_unix': time.time(), 'ownership_token': secrets.token_hex(16),
                'stop': threading.Event()}
            return self.entries[slot]['stop']

    def remove(self, slot):
        with self.lock:
            return self.entries.pop(slot, None)

    def snapshot(self):
        with self.lock:
            return [{k: v for k, v in item.items() if k != 'stop'} for item in self.entries.values()]

    def abort(self, pair, reason):
        with self.lock:
            current = self.entries.get(pair['slot_id'])
            if current is None or current['ownership_token'] != pair['ownership_token']:
                return False
            if current['stop'].is_set():
                return False
            current['pressure_abort'] = dict(reason)
            current['stop'].set()
        self.event('owned_API_pressure_abort', slot_id=pair['slot_id'], reason=reason,
                   automatic_retry=False, Qwen_affected=False, foreign_objects_affected=False)
        return True


def runtime_api():
    from proworksim import software_benchmark_deepseek_runtime_v072 as prior
    preflight = private_function(prior._preflight, INVENTORY_FILE=scope.BATCH_ROOT / 'api-inventory.json')
    identity = private_function(prior._identity, VERSION=VERSION,
        IDENTITY_FILE=scope.API_ROOT / 'api-runtime/identity.json')

    class Runtime(prior.DeepSeekRuntime):
        def read_only_preflight(self):
            return preflight(self)

        def logical_resident(self):
            return identity(self)

    return Runtime(scope_guard=scope.require_allowed,
                   inventory_ref=reference(scope.BATCH_ROOT / 'api-inventory.json'))


def state_for(rows, inventory, inventory_ref):
    identities = {row['slot_id'] for row in rows}
    generations = {slot: entry for slot, entry in inventory['generation'].items() if slot in identities}
    allowed = identities & set(inventory['allowed_generation_slot_ids'])
    if allowed != identities - generations.keys():
        raise ValueError('Every consumed identity must retain a terminal accounting entry')
    return {'generation': generations, 'scores': {k: v for k, v in inventory['scores'].items() if k in identities},
        'deliveries': {k: v for k, v in inventory['deliveries'].items() if k in identities},
        'retry_zero_generation': {}, 'inventory': inventory_ref,
        'exceptions': inventory.get('exceptions', []),
        'completed_controls': inventory.get('completed_controls', {}),
        'pending_score_jobs': [job for job in inventory.get('unused_score_jobs', []) if job[1]['slot_id'] in identities]}


class AdaptiveAdmission:
    def __init__(self, role, policy, watchdog, registry, control, event):
        self.role, self.policy, self.watchdog, self.registry = role, policy, watchdog, registry
        self.control, self.event = control, event
        self.active, self.observation = set(), {}
        self.ceiling, self.last_growth = (4 if role == 'primary' else 8), 0.0

    def record(self, kind, **values):
        if kind == 'generation_scheduled':
            self.active.add(values['slot_id'])
        elif kind == 'generation_finished':
            self.active.discard(values['slot_id'])
        self.event(kind, **values)

    def limit(self):
        desired = 4 if self.role == 'primary' else 44
        error = None
        try:
            if self.control.exists():
                desired = json.loads(self.control.read_bytes())['desired']
            maximum = 4 if self.role == 'primary' else 48
            if type(desired) is not int or not 0 <= desired <= maximum:
                raise ValueError('Concurrency outside this role scope')
        except (ValueError, KeyError, OSError, TypeError) as failure:
            desired, error = 0, str(failure)
        pressure = self.watchdog.admission()
        # The actual claim path rechecks startup batches and host headroom under
        # the original global allocation lock. This limit bounds queued futures.
        observation = self.policy.admission_snapshot()
        safe = pressure.get('fresh') is True and pressure.get('admit') is True and observation.get('admit') is True
        now = time.monotonic()
        if safe and self.role == 'api' and now-self.last_growth >= 5:
            self.ceiling = min(desired, self.ceiling+4)
            self.last_growth = now
        role_limit = (observation.get('api_generation_limit') if self.role == 'api'
            else observation.get('actual_active_qwen_actors', 0) + observation.get('additional_pair_slots', 0))
        if type(role_limit) is not int or role_limit < 0:
            safe, role_limit = False, 0
        effective = min(desired, self.ceiling, role_limit) if safe else 0
        self.observation = {**observation, 'configured_generation_limit': desired,
            'effective_generation_limit': effective, 'ramp_ceiling': self.ceiling,
            'actual_generation_futures': len(self.active), 'pressure': pressure,
            'concurrency_control_error': error,
            'quota_sum_is_not_actual_resource_usage': True}
        return effective


def reconcile_deliveries(rows, inventory, state, grading):
    """Reuse the exact official delivery disposition and any already prepared request."""
    by_id = {row['slot_id']: row for row in rows}
    for item in inventory.get('delivery_reconciliation', []):
        row = by_id.get(item['slot_id'])
        if row is None or row['slot_id'] in state['deliveries']:
            continue
        disposition = grading.delivery_disposition(item['generation_result'], item.get('code_request'))
        state['deliveries'][row['slot_id']] = disposition
        if disposition.get('scoring_request') is not None:
            state['pending_score_jobs'].append(('delivery', row, disposition['scoring_request'], True))


def pressure_result(result_ref, registration, folder, row):
    """Retain the unchanged original candidate if pressure interrupted this episode."""
    reason = (registration or {}).get('pressure_abort')
    if reason is None:
        return result_ref
    original_result = base.load(result_ref)
    directory = Path(folder) / 'pressure-episodes'
    directory.mkdir(parents=True, exist_ok=True)
    return write_new(directory / f"{row['slot_index']}.json", {**original_result,
        'status': 'technical_unknown', 'pressure_original_status': original_result.get('status'),
        'pressure_original_result': result_ref, 'pressure_abort': reason,
        'deployment_memory_pressure': True, 'automatic_retry': False,
        'original_candidate_changed': False})


def run(role):
    # Register cleanup before every potentially failing bootstrap step.  Starting
    # the watchdog or reserving the auxiliary coordinator is not a successful run.
    with ExitStack() as cleanup:
        return _run(role, cleanup)


def _run(role, cleanup):
    from proworksim.software_benchmark_episodes_v076 import EpisodeBindings
    from proworksim.software_benchmark_grading_v076 import factory
    from proworksim.software_benchmark_pressure_v076 import PressureWatchdog
    from proworksim import software_benchmark_api_parent_v076 as api_parent
    scope.require_allowed('v076.run')
    actual_limits = scope.verify_host_limits(role)
    folder = scope.PRIMARY_ROOT if role == 'primary' else scope.API_ROOT
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'execution-started.json').exists():
        raise ValueError('An adaptive coordinator is single use')

    def snapshot(name, value):
        atomic_write(folder / name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))

    def event(kind, **values):
        with (folder / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False)+'\n')

    inventory_ref = reference(scope.INVENTORY_FILE if role == 'primary' else scope.BATCH_ROOT / 'api-inventory.json')
    inventory = base.load(inventory_ref)
    all_rows = base.load(reference(original.PLAN_FILE))['rows']
    rows = [row for row in all_rows if (row['model_key'] == 'QWEN' if role == 'primary'
             else row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000)]
    state = state_for(rows, inventory, inventory_ref)
    stopped = threading.Event()
    registry = EpisodeRegistry(event)
    watchdog = PressureWatchdog(snapshot_pairs=registry.snapshot, request_abort=registry.abort,
        observe=lambda value: snapshot('pressure.json', value),
        parent_probe=api_parent.pressure_probe if role == 'api' else None,
        require_parent=role == 'api')
    cleanup.callback(watchdog.close)
    watchdog.start()
    bindings = EpisodeBindings(scope.require_allowed, authorization_ref=reference(scope.AUTH_FILE),
                               watchdog_guard=watchdog.admission)
    grading = factory(scope.require_allowed, primary_policy=bindings.primary_policy,
                      authorization_ref=reference(scope.AUTH_FILE))
    api = runtime_api() if role == 'api' else None
    reservation = scope.reserve_api_coordinator() if role == 'api' else None
    if reservation is not None:
        cleanup.callback(scope.release_api_coordinator, reservation)
    admission = AdaptiveAdmission(role, bindings.primary_policy, watchdog, registry,
                                  folder / 'concurrency-control.json', event)
    matrix = base.load(reference(original.MATRIX_FILE))
    if role == 'primary':
        class Recorder(qwen_base.QwenUsageRecorder):
            save_record = private_function(qwen_base.QwenUsageRecorder.save_record, RUN_ROOT=folder)
            flush = private_function(qwen_base.QwenUsageRecorder.flush, RUN_ROOT=folder, snapshot=snapshot)
        recorder = Recorder(matrix, None)
        recorder.import_original(inventory['usage_record_files'], eligible_records=state['generation'])

        class ResidentRuntime(qwen_base.UnusedResidentRuntime):
            def start_residents(self):
                return self.ready_residents()

            def stop_residents(self):
                # A coordinator pause/fault must not unload independent model units.
                return []

        runtime = ResidentRuntime(guard=lambda *a, **kw: scope.require_allowed('v076.run', **kw))
        qualifications = inventory['qualifications']
        qualified_source = None
    else:
        class Recorder(api_base.APIUsageRecorder):
            save_record = private_function(api_base.APIUsageRecorder.save_record, RUN_ROOT=folder)
            flush = private_function(api_base.APIUsageRecorder.flush, RUN_ROOT=folder, VERSION=VERSION)
        api.initialize_for_run()
        recorder = Recorder(matrix, api)
        recorder.import_records(inventory['usage_record_files'], eligible_records=state['generation'])
        runtime = api_base.NoQwenRuntime()
        qualified_source = api_base.PrimaryQualifications({row['instance_id'] for row in rows},
            cursor_path=scope.PRIMARY_CURSOR, initial=inventory['qualifications'])
        qualified_source.refresh()
        qualifications = qualified_source.values

    reconcile_deliveries(rows, inventory, state, grading)

    def episode(row, resident, **kwargs):
        if row['slot_id'] not in inventory['allowed_generation_slot_ids']:
            raise PermissionError('No consumed task may enter generation')
        if role == 'primary':
            return bindings.run_qwen(row, resident, **kwargs)
        local = registry.add(row)
        kwargs['stop_event'] = LocalStop(kwargs['stop_event'], local)
        try:
            result_ref = bindings.run_api(row, resident, **kwargs)
        finally:
            registration = registry.remove(row['slot_id'])
        return pressure_result(result_ref, registration, folder, row)

    def progress(value):
        snapshot('progress.json', {**value, **admission.observation,
            'planned_original_generation': 3000 if role == 'primary' else 1000,
            'API_inflight_requests': (api.budget_status().get('inflight_count') if api else None)})

    def ceiling():
        if qualified_source:
            qualified_source.refresh()
            if qualified_source.snapshot.get('failure') is not None:
                return 0
        return admission.limit()

    queue, proof = qwen_base.recovery_function()
    queue = private_function(queue, _executor_pair=executors)
    write_new(folder / 'execution-started.json', {'version': VERSION, 'unix': time.time(),
        'authorization': reference(scope.AUTH_FILE), 'inventory': inventory_ref, 'queue_binding': proof,
        'host_limits': actual_limits, 'per_object_limits_changed': False, 'new_model_preparation_calls': 0})
    snapshot('cursor.json', qwen_base.starting_cursor(rows, state,
        inventory.get('unused_control_requests', []) if role == 'primary' else [], qualifications))
    handlers = base._handle_termination(stopped)
    try:
        result = queue(rows, controls=inventory.get('unused_control_requests', []) if role == 'primary' else [],
            qualifications=qualifications, grading=grading, runtime=runtime, run_episode=episode,
            api_runtime=api, stop_event=stopped, progress_sink=progress, event_sink=admission.record,
            cursor_sink=lambda value: snapshot('cursor.json', value), result_sink=recorder,
            initial_state=state, model_exhausted=lambda _: False, generation_limit=ceiling,
            disk_check=lambda: base.check_disk_boundary(base.load(reference(original.COORDINATOR_RUN_ROOT /
                'coordinator-plan.json'))['disk_boundary']))
        try:
            recorder.flush(final=True)
        except Exception as error:
            result['exceptions'].append({'kind': 'final_usage_report_failed', 'error': str(error)})
        write_new(folder / 'run-summary.json', {**result, 'version': VERSION, 'finished_unix': time.time()})
        progress({'phase': 'closed' if result['failure'] is None else 'stopped',
            'failure': result['failure'], 'provider_failures': result['provider_failures'],
            'active_generation': 0, 'finished_generation': len(result['generation'])})
        if role == 'primary' and not result['unentered_generation'] and result['failure'] is None:
            event('owned_models_terminal_release', result=runtime.delegate.stop_residents())
        if role == 'api':
            try:
                event('owned_API_parent_release', result=api_parent.stop_empty())
            except Exception as error:
                event('owned_API_parent_cleanup_pending', error=str(error),
                      existing_results_unchanged=True, other_objects_affected=False)
        return result
    finally:
        base._restore_termination(handlers)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['primary', 'api'], required=True)
    parser.add_argument('--execute', action='store_true', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.role), ensure_ascii=False))
