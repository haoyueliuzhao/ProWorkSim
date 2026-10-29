"""Process disjoint unused API tasks while the paused predecessor drains."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import threading
import time

from proworksim import software_benchmark_api_scope_v088 as scope
from proworksim import software_benchmark_rolling_handoff_v086 as handoff
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim import software_benchmark_pressure_v083 as owner_pressure
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_qualification_guard_v079 import require_unchanged_terminal
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v088-rolling-API-asynchronous-grading-r1'
OWNER_PROBE = private_function(owner_pressure.owner_probe, scope=scope)


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prior = module('v088_frozen_adaptive_helpers', 'run_adaptive_v076.py')


def combined_history(current, historic, old_owned, new_allowed):
    """Only the predecessor may update its own old IDs; no new ID is replaced."""
    if set(old_owned) & set(new_allowed):
        raise ValueError('Rolling generation ownership overlaps')
    result = {}
    for key in ('generation', 'scores', 'deliveries'):
        merged = dict(current.get(key, {}))
        for slot, value in historic.get(key, {}).items():
            if slot in old_owned:
                if slot in new_allowed:
                    raise ValueError('An old checkpoint claims a successor identity')
                # A transferred grading worker may have completed an endpoint
                # that was merely waiting in the old owner's final snapshot.
                existing = merged.get(slot, {})
                pending_delivery = {'waiting_for_own_code_score', 'requires_separate_official_score'}
                if (key == 'deliveries' and existing
                        and existing.get('status') not in pending_delivery
                        and value.get('status') in pending_delivery):
                    continue
                merged[slot] = value
        result[key] = merged
    return result


def own_future_limit(observation, *, own_actors, old_actors, old_unclaimed, desired, ramp):
    for value in (own_actors, old_actors, old_unclaimed, desired, ramp):
        if type(value) is not int or value < 0:
            raise ValueError('Concurrency observations must be nonnegative integers')
    free_for_owner = max(0, 48-old_actors-old_unclaimed)
    if old_unclaimed:
        # The old allocator still uses startup8. Filling the new startup16
        # allowance could otherwise keep its queued futures blocked forever.
        # Existing new tasks continue; only new admissions wait for old claims.
        return min(desired, ramp, free_for_owner, own_actors)
    additional = max(0, observation['additional_pair_slots']-old_unclaimed)
    return min(desired, ramp, free_for_owner, own_actors+additional)


class History:
    def __init__(self, inventory, rows):
        self.old_owned = set(inventory['continuing_old_owned_slot_ids'])
        self.new_allowed = set(inventory['allowed_generation_slot_ids'])
        self.rows = {row['slot_id']: row for row in rows}
        self.last, self.last_read = {}, float('-inf')

    def snapshot(self):
        if time.monotonic()-self.last_read < 2 and self.last:
            return self.last
        path = (scope.HISTORY_ROOT/'historical-results.json' if (scope.HANDOFF_ROOT/'stopped.json').exists()
                else scope.OLD_API_ROOT/'cursor.json')
        try:
            value = json.loads(path.read_bytes())
        except (OSError, ValueError):
            # A new immutable history file is published before the stop marker;
            # an incomplete derived report is not permission to replay anything.
            if not self.last:
                value = scope.load(scope.load(reference(scope.INVENTORY_FILE))['handoff'])
                value = scope.load(value['continuing_old_snapshot'])
            else:
                return self.last
        self.last = value
        self.last_read = time.monotonic()
        return value

    def statistics(self, current):
        old = self.snapshot()
        combined = combined_history(current, old, self.old_owned, self.new_allowed)
        groups = {}
        for slot, row in self.rows.items():
            group = groups.setdefault(row['group_id'], {'planned': 0, 'generation_closed': 0,
                'technical_unknown': 0, 'not_started': 0, 'external_running': 0, 'entered': 0})
            group['planned'] += 1
            item = combined['generation'].get(slot, {})
            state = item.get('status')
            if state in ('closed', 'technical_unknown', 'not_started', 'external_running'):
                group['generation_closed' if state == 'closed' else state] += 1
            group['entered'] += item.get('entered') is True
        return {'groups': groups,
            'combined_generation_status_counts': {key: sum(group[key] for group in groups.values())
                for key in ('generation_closed', 'technical_unknown', 'not_started', 'external_running')},
            'combined_code_score_records': len(combined['scores']),
            'finished_generation': sum(item.get('entered') is True
                and item.get('status') in {'closed', 'technical_unknown'}
                for item in combined['generation'].values()),
            'external_running': sum(item.get('status') == 'external_running'
                for item in combined['generation'].values()),
            'predecessor_history_final': (scope.HANDOFF_ROOT/'stopped.json').exists(),
            'predecessor_cursor_unix': old.get('unix'),
            'external_slots_not_counted_as_model_failures': True}


class Admission:
    def __init__(self, policy, pressure, history, event):
        self.policy, self.pressure, self.history, self.event = policy, pressure, history, event
        self.active, self.observation = set(), {}
        self.ramp, self.last_growth = 8, 0.0

    def record(self, kind, **values):
        if kind == 'generation_scheduled':
            self.active.add(values['slot_id'])
        elif kind == 'generation_finished':
            self.active.discard(values['slot_id'])
        self.event(kind, **values)

    def limit(self):
        control = scope.API_ROOT/'concurrency-control.json'
        desired = json.loads(control.read_bytes())['desired'] if control.exists() else 48
        if type(desired) is not int or not 0 <= desired <= 48:
            raise ValueError('Desired API concurrency must be within the reviewed 0..48 scope')
        directory = scope.original.BATCH_ROOT/'resource-claims'
        with (directory/'allocation.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            claims = [json.loads(path.read_bytes()) for path in directory.glob('active-*.json')]
        actors = [value for value in claims if value.get('spec', {}).get('role') == 'actor']
        own = sum(value['spec'].get('slot_id') in self.history.new_allowed for value in actors)
        old = sum(value['spec'].get('slot_id') in self.history.old_owned for value in actors)
        unknown_api = [value['key'] for value in actors if ':DEEPSEEK_' in value['spec'].get('slot_id', '')
                       and value['spec']['slot_id'] not in self.history.old_owned|self.history.new_allowed]
        if unknown_api:
            raise PermissionError('An API actor has unrecognized rolling ownership')
        history = self.history.snapshot()
        old_unclaimed = sum(slot in self.history.old_owned
            and not (directory/f"actor-{self.history.rows[slot]['slot_index']}.json").exists()
            for slot in history.get('active_generation', []) if slot in self.history.rows)
        observed = self.policy.admission_snapshot(claims)
        pressure = self.pressure.admission()
        valid = observed['admit'] and pressure['fresh'] and pressure['admit']
        now = time.monotonic()
        if valid and now-self.last_growth >= 5:
            self.ramp = min(desired, self.ramp+4)
            self.last_growth = now
        ceiling = own_future_limit(observed, own_actors=own, old_actors=old,
            old_unclaimed=old_unclaimed, desired=desired, ramp=self.ramp) if valid else 0
        self.observation = {**observed, 'configured_generation_limit': desired,
            'effective_generation_limit': ceiling, 'ramp_ceiling': self.ramp,
            'own_API_actor_count': own, 'old_API_actor_count': old,
            'old_unclaimed_future_reservations': old_unclaimed,
            'actual_generation_futures': len(self.active), 'pressure': pressure,
            'old_and_new_global_API_actor_limit': 48}
        return ceiling


def qwen_target():
    try:
        value = json.loads((scope.PRIMARY_ROOT/'progress.json').read_bytes())
    except (OSError, ValueError):
        return 4
    if value.get('failure') is not None or value.get('phase') in {'closed', 'stopped'}:
        return 0
    pending, active = value.get('pending_generation'), value.get('active_generation')
    return min(4, pending+active) if type(pending) is int and type(active) is int else 4


def episode_binding_class():
    from proworksim.software_benchmark_episodes_v079 import EpisodeBindings as PreviousBindings
    from proworksim.software_benchmark_episodes_v076 import api_episode
    from proworksim import software_benchmark_resources_v086 as safe_resources
    from proworksim.software_benchmark_io_v088 import bind_episode as bind_io
    from proworksim.software_benchmark_failure_scope_v088 import bind_episode as bind_failure_scope

    original_init = private_function(PreviousBindings.__init__, resources=safe_resources,
                                    api_episode=private_function(api_episode, parent=parent))

    class EpisodeBindings(PreviousBindings):
        def __init__(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.api = bind_failure_scope(bind_io(self.api))

        run_api = private_function(PreviousBindings.run_api, parent=parent)
    return EpisodeBindings


def grading_bindings(grading_watchdog):
    from proworksim import software_benchmark_resources_v086 as resources
    from proworksim.software_benchmark_grading_v076 import factory
    from proworksim.software_benchmark_poll_scorer_v088 import bind_grading
    policy = resources.policy(scope.require_grading_allowed,
        watchdog_guard=grading_watchdog.admission, qwen_target=0,
        authorization_ref=reference(scope.AUTH_FILE))
    original_write = policy._write_claim

    def grading_claim_only(path, value):
        if value.get('spec', {}).get('role') not in {'control', 'score', 'delivery_score'}:
            raise PermissionError('Parent-independent policy cannot create actors, models or volumes')
        return original_write(path, value)

    policy.claim_resource.__globals__['_write_claim'] = grading_claim_only
    policy._write_claim = grading_claim_only
    return policy, bind_grading(factory(scope.require_grading_allowed,
        primary_policy=policy, authorization_ref=reference(scope.AUTH_FILE)))


def run():
    from proworksim.software_benchmark_async_queue_v082 import factory as queue_factory
    from proworksim.software_benchmark_fd_v085 import FDGuard, RuntimeView
    EpisodeBindings = episode_binding_class()
    scope.require_allowed('v088.run')
    actual = scope.verify_host_limits('api')
    parent.require_qualified()
    folder = scope.API_ROOT
    if (folder/'execution-started.json').exists():
        raise ValueError('This API service is single use')

    def snapshot(name, value):
        atomic_write(folder/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))

    def event(kind, **values):
        with (folder/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False)+'\n')

    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    rows = [row for row in scope.load(reference(scope.original.PLAN_FILE))['rows']
            if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000]
    state = prior.state_for(rows, inventory, inventory_ref)
    state['pending_grading_jobs'] = inventory.get('pending_grading_jobs', [])
    history = History(inventory, rows)
    stopped = threading.Event()
    shutdown_requested = threading.Event()
    registry = prior.EpisodeRegistry(event)
    fd_guard = FDGuard()
    with ExitStack() as cleanup:
        watchdog = owner_pressure.PressureWatchdog(registry.snapshot, registry.abort,
            observe=lambda value: snapshot('pressure.json', value),
            parent_probe=parent.pressure_probe, require_parent=True, coordinator_probe=OWNER_PROBE)
        cleanup.callback(watchdog.close)
        watchdog.start()
        bindings = EpisodeBindings(scope.require_allowed, watchdog_guard=watchdog.admission,
            authorization_ref=reference(scope.AUTH_FILE), qwen_target=qwen_target)
        # Official graders are outside the API actor parent. Its legitimate
        # empty release must not invalidate fixed candidate scoring. Actual
        # host/owner memory, CPU, disk and original grading limits still apply.
        grading_watchdog = owner_pressure.PressureWatchdog(lambda: [], lambda *_: None,
            observe=lambda value: snapshot('grading-pressure.json', value),
            require_parent=False, coordinator_probe=OWNER_PROBE)
        cleanup.callback(grading_watchdog.close)
        grading_watchdog.start()
        grading_policy, grading = grading_bindings(grading_watchdog)
        raw_api = private_function(prior.runtime_api, scope=scope, VERSION=VERSION)()
        api = RuntimeView(raw_api, fd_guard)
        reservation = scope.reserve_api_coordinator()
        cleanup.callback(scope.release_api_coordinator, reservation)
        api.initialize_for_run()

        class Recorder(prior.api_base.APIUsageRecorder):
            save_record = private_function(prior.api_base.APIUsageRecorder.save_record, RUN_ROOT=folder)
            flush = private_function(prior.api_base.APIUsageRecorder.flush, RUN_ROOT=folder, VERSION=VERSION)

        recorder = Recorder(prior.base.load(reference(scope.original.MATRIX_FILE)), api)
        recorder.import_records(inventory['usage_record_files'], eligible_records=state['generation'])
        by_id = {row['slot_id']: row for row in rows}
        for slot in inventory.get('recovered_original_results', []):
            row, entry = by_id[slot], state['generation'][slot]
            try:
                recorder(row, entry, scope.load(entry['result']), state['scores'].get(slot), state['deliveries'].get(slot))
            except Exception as error:
                recorder.mark_unknown(row, entry, type(error).__name__+': '+str(error))
        admission = Admission(bindings.primary_policy, watchdog, history, event)
        qualifications = prior.api_base.PrimaryQualifications({row['instance_id'] for row in rows},
            cursor_path=scope.PRIMARY_CURSOR, initial=inventory['qualifications'])
        qualifications.refresh()
        drain = handoff.OldDrainMonitor(history.old_owned, event)
        cleanup.callback(drain.close)
        drain.start()
        history_imported = threading.Event()
        if inventory.get('continuing_history_final_at_preparation') is True:
            # The immutable preparation already incorporated this exact final
            # old snapshot. Do not re-import it over newly reconciled grading.
            history_imported.set()
        current = {key: dict(state[key]) for key in ('generation', 'scores', 'deliveries')}

        def external_poll():
            if not drain.finished.is_set() or history_imported.is_set():
                return None
            value = scope.load(reference(scope.HISTORY_ROOT/'historical-results.json'))
            if set(value['old_owned_slot_ids']) != history.old_owned:
                raise PermissionError('Historical results have another predecessor ownership set')
            result = {key: value.get(key, {}) for key in ('generation', 'scores', 'deliveries')}
            if any(set(result[key])-history.old_owned for key in result):
                raise PermissionError('Historical results include a successor identity')
            result['pending_score_jobs'] = value.get('pending_score_jobs', [])
            history_imported.set()
            return result

        def cursor_sink(value):
            for key in current:
                current[key] = value[key]
            snapshot('cursor.json', {**value, 'old_owned_slot_ids': sorted(history.old_owned),
                'rolling_history': history.statistics(current)})

        def progress(value):
            snapshot('progress.json', {**value, **admission.observation, **history.statistics(current),
                'planned_original_generation': 1000, 'fd_pressure': fd_guard.snapshot(),
                'runtime_revision': VERSION, 'API_inflight_requests': api.budget_status().get('inflight_count')})

        def ceiling():
            qualifications.refresh()
            if qualifications.snapshot.get('failure') is not None:
                require_unchanged_terminal(inventory['qualifications'], qualifications.snapshot)
            return admission.limit()

        def episode(row, resident, **kwargs):
            if row['slot_id'] not in history.new_allowed:
                raise PermissionError('The successor cannot generate an old-owned identity')
            local = registry.add(row)
            kwargs['stop_event'] = prior.LocalStop(kwargs['stop_event'], local)
            try:
                result = bindings.run_api(row, resident, **kwargs)
            finally:
                registration = registry.remove(row['slot_id'])
            return prior.pressure_result(result, registration, folder, row)

        write_new(folder/'execution-started.json', {'version': VERSION, 'unix': time.time(),
            'authorization': reference(scope.AUTH_FILE), 'inventory': inventory_ref, 'host_limits': actual,
            'old_owned_generation_excluded': True, 'new_API_cash_budget': False,
            'Qwen_lifecycle_operations': 0, 'all_grading_preparation_and_delivery_validation_async': True})
        class ShutdownSignal:
            def set(self):
                shutdown_requested.set()
                stopped.set()

        handlers = prior.base._handle_termination(ShutdownSignal())
        cleanup.callback(prior.base._restore_termination, handlers)
        queue = queue_factory(job_root=folder/'async-grading-jobs',
                              heartbeat_sink=lambda value: snapshot('heartbeat.json', value))
        result = queue(rows, controls=[], qualifications=qualifications.values, grading=grading,
            runtime=prior.api_base.NoQwenRuntime(), run_episode=episode, api_runtime=api,
            stop_event=stopped, progress_sink=progress, event_sink=admission.record,
            cursor_sink=cursor_sink, result_sink=recorder, initial_state=state,
            model_exhausted=lambda _: False,
            generation_limit=fd_guard.admission(ceiling, active=lambda: len(admission.active)),
            external_poll=external_poll, external_pending=lambda: not history_imported.is_set(),
            disk_check=lambda: prior.base.check_disk_boundary(prior.base.load(reference(
                scope.original.COORDINATOR_RUN_ROOT/'coordinator-plan.json'))['disk_boundary']))
        # New tasks may end before the predecessor's last long public test.
        # Keep its safe monitor alive; never stop the shared parent prematurely.
        deadline = time.monotonic()+8*3600
        while (not drain.finished.is_set() and time.monotonic() < deadline
               and not shutdown_requested.is_set() and result.get('failure') is None):
            snapshot('progress.json', {'phase': 'waiting_for_predecessor_final_history',
                **history.statistics(result), 'actual_generation_futures': 0,
                'predecessor_drain': drain.last, 'failure': result.get('failure')})
            drain.finished.wait(15)
        if drain.finished.is_set():
            result.update(combined_history(result, history.snapshot(), history.old_owned, history.new_allowed))
            # The asynchronous handoff import re-measures final old generations
            # with their latest scoring records. Importing predecessor usage
            # files here would regress scores completed by the new workers.
        result.update(version=VERSION, predecessor_history_final=drain.finished.is_set(),
                      predecessor_drain=drain.last, finished_unix=time.time())
        recorder.flush(final=True)
        write_new(folder/'run-summary.json', result)
        snapshot('progress.json', {'phase': 'closed' if result.get('failure') is None and drain.finished.is_set()
                 and not result.get('external_handoff_requires_review')
                 else 'review_required', **history.statistics(result), 'failure': result.get('failure'),
                 'predecessor_history_final': drain.finished.is_set(), 'active_generation': 0})
        if drain.finished.is_set():
            try:
                if parent.RELEASED.exists():
                    event('owned_API_parent_already_released', receipt=reference(parent.RELEASED))
                else:
                    event('owned_API_parent_release', result=parent.stop_empty())
            except Exception as error:
                event('owned_API_parent_cleanup_pending', error=str(error))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
