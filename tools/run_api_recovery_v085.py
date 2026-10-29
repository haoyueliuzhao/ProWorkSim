"""Resume original unused API tasks with private parent cycle and FD admission."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import importlib.util
import json
import threading
import time
from types import SimpleNamespace

from proworksim import software_benchmark_api_scope_v085 as scope
from proworksim import software_benchmark_api_parent_v085 as parent
from proworksim import software_benchmark_pressure_v083 as pressure
from proworksim import software_benchmark_resources_v083 as resources
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_qualification_guard_v079 import require_unchanged_terminal
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v085-FD-bounded-original-API-recovery-r1'
OWNER_PROBE = private_function(pressure.owner_probe, scope=scope)


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prior = module('v085_adaptive_helpers', 'run_adaptive_v076.py')
rolling = module('v085_rolling_helpers', 'run_rolling_api_v083.py')


class Admission(rolling.Admission):
    limit = private_function(rolling.Admission.limit, scope=scope)


def qwen_target():
    try:
        value = json.loads((scope.PRIMARY_ROOT/'progress.json').read_bytes())
    except (OSError, ValueError):
        return 0
    if value.get('failure') is not None or value.get('phase') in ('closed', 'stopped'):
        return 0
    pending, active = value.get('pending_generation'), value.get('active_generation')
    return min(4, pending+active) if type(pending) is int and type(active) is int else 0


def episode_binding(guard, watchdog):
    from proworksim.software_benchmark_episodes_v076 import api_episode
    policy = resources.policy(guard, watchdog_guard=watchdog.admission,
        authorization_ref=reference(scope.AUTH_FILE), qwen_target=qwen_target)
    # This replacement is applied before creating any actor class/closures.
    # Injecting only outer require_qualified would leave the old released cycle.
    delegate = private_function(api_episode, parent=parent)(policy)
    delegate.run_episode.__globals__['capacity'] = policy.physical_capacity
    delegate.__dict__['capacity'] = policy.physical_capacity
    return policy, delegate


def run():
    from proworksim.software_benchmark_grading_v076 import factory as grading_factory
    from proworksim.software_benchmark_async_queue_v082 import factory as queue_factory
    from proworksim.software_benchmark_fd_v085 import FDGuard, RuntimeView
    scope.require_allowed('v085.run')
    actual = scope.verify_host_limits('api')
    parent.require_qualified()
    folder = scope.API_ROOT
    if (folder/'execution-started.json').exists():
        raise ValueError('A consumed coordinator cannot be restarted')

    def snapshot(name, value):
        atomic_write(folder/name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))

    def event(kind, **values):
        with (folder/'events.jsonl').open('a') as stream:
            stream.write(json.dumps({'unix': time.time(), 'kind': kind, **values}, ensure_ascii=False)+'\n')

    inventory_ref = reference(scope.INVENTORY_FILE)
    inventory = scope.load(inventory_ref)
    rows = [row for row in scope.load(reference(scope.original.PLAN_FILE))['rows']
            if row['model_key'] == 'DEEPSEEK' and row['input_plus_output_tokens'] == 5_000_000]
    by_id = {row['slot_id']: row for row in rows}
    state = prior.state_for(rows, inventory, inventory_ref)
    stopped = threading.Event()
    registry = prior.EpisodeRegistry(event)
    fd_guard = FDGuard(minimum_free=512, resume_free=1024, fd_per_new_episode=32)
    history = SimpleNamespace(old_owned=set(inventory['generation']),
        new_allowed=set(inventory['allowed_generation_slot_ids']), rows=by_id,
        snapshot=lambda: {'active_generation': []})
    with ExitStack() as cleanup:
        watchdog = pressure.PressureWatchdog(registry.snapshot, registry.abort,
            observe=lambda value: snapshot('pressure.json', value),
            parent_probe=parent.pressure_probe, require_parent=True, coordinator_probe=OWNER_PROBE)
        cleanup.callback(watchdog.close)
        watchdog.start()
        policy, delegate = episode_binding(scope.require_allowed, watchdog)
        grading = grading_factory(scope.require_allowed, primary_policy=policy,
                                  authorization_ref=reference(scope.AUTH_FILE))
        api = private_function(prior.runtime_api, scope=scope, VERSION=VERSION)()
        reservation = scope.reserve_api_coordinator()
        cleanup.callback(scope.release_api_coordinator, reservation)
        protected_api = RuntimeView(api, fd_guard)
        protected_api.initialize_for_run()

        class Recorder(prior.api_base.APIUsageRecorder):
            save_record = private_function(prior.api_base.APIUsageRecorder.save_record, RUN_ROOT=folder)
            flush = private_function(prior.api_base.APIUsageRecorder.flush, RUN_ROOT=folder, VERSION=VERSION)

        recorder = Recorder(prior.base.load(reference(scope.original.MATRIX_FILE)), protected_api)
        recorder.import_records(inventory['usage_record_files'], eligible_records=state['generation'])
        # These were already produced before the predecessor exited; only their
        # observations were omitted from its cursor. No model is run again.
        for slot in inventory.get('recovered_original_results', []):
            row, entry = by_id[slot], state['generation'][slot]
            try:
                recorder(row, entry, scope.load(entry['result']), state['scores'].get(slot), state['deliveries'].get(slot))
            except Exception as error:
                recorder.mark_unknown(row, entry, type(error).__name__+': '+str(error))
        admission = Admission(policy, watchdog, history, event)
        qualifications = prior.api_base.PrimaryQualifications({row['instance_id'] for row in rows},
            cursor_path=scope.PRIMARY_CURSOR, initial=inventory['qualifications'])
        qualifications.refresh()

        def ceiling():
            qualifications.refresh()
            if qualifications.snapshot.get('failure') is not None:
                require_unchanged_terminal(inventory['qualifications'], qualifications.snapshot)
            return admission.limit()

        def progress(value):
            snapshot('progress.json', {**value, **admission.observation,
                'fd_pressure': fd_guard.snapshot(), 'runtime_revision': VERSION,
                'API_cash_cap_preserved': '1500.00'})

        def episode(row, resident, **kwargs):
            if row['slot_id'] not in history.new_allowed:
                raise PermissionError('Consumed original generation cannot be replayed')
            parent.require_qualified()
            local = registry.add(row)
            kwargs['stop_event'] = prior.LocalStop(kwargs['stop_event'], local)
            try:
                result = delegate.run_episode(row, resident, **kwargs)
            finally:
                registration = registry.remove(row['slot_id'])
            return prior.pressure_result(result, registration, folder, row)

        write_new(folder/'execution-started.json', {'version': VERSION, 'unix': time.time(),
            'authorization': reference(scope.AUTH_FILE), 'inventory': inventory_ref,
            'host_limits': actual, 'new_API_cash_budget': False, 'Qwen_lifecycle_operations': 0,
            'file_descriptor_admission': True, 'original_consumed_generation_replayed': False})
        handlers = prior.base._handle_termination(stopped)
        cleanup.callback(prior.base._restore_termination, handlers)
        queue = queue_factory(job_root=folder/'async-grading-jobs',
            heartbeat_sink=lambda value: snapshot('heartbeat.json', value))
        result = queue(rows, controls=[], qualifications=qualifications.values, grading=grading,
            runtime=prior.api_base.NoQwenRuntime(), run_episode=episode, api_runtime=protected_api,
            stop_event=stopped, progress_sink=progress, event_sink=admission.record,
            cursor_sink=lambda value: snapshot('cursor.json', value), result_sink=recorder,
            initial_state=state, model_exhausted=lambda _: False,
            generation_limit=fd_guard.admission(ceiling, active=lambda: len(admission.active)),
            disk_check=lambda: prior.base.check_disk_boundary(prior.base.load(reference(
                scope.original.COORDINATOR_RUN_ROOT/'coordinator-plan.json'))['disk_boundary']))
        result.update(version=VERSION, finished_unix=time.time(), fd_pressure=fd_guard.snapshot())
        recorder.flush(final=True)
        write_new(folder/'run-summary.json', result)
        snapshot('progress.json', {'phase': 'closed' if result.get('failure') is None else 'stopped',
            'failure': result.get('failure'), 'active_generation': 0, 'fd_pressure': fd_guard.snapshot(),
            'generation_status_counts': dict(Counter(e['status'] for e in result['generation'].values()))})
        # The parent is this recovery cycle only and stops only when truly empty.
        try:
            event('owned_API_parent_release', result=parent.stop_empty())
        except Exception as error:
            event('owned_API_parent_cleanup_pending', error=str(error))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', required=True, action='store_true')
    parser.parse_args()
    print(json.dumps(run(), ensure_ascii=False))
