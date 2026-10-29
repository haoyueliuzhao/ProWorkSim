"""Finish the quiet handoff inside the already planned new primary service."""
from __future__ import annotations

import importlib.util
import json
import signal
import threading
import time

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim import software_benchmark_api_parent_v076 as parent
from proworksim import software_benchmark_handoff_v075 as handoff
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

VERSION = 'v076-bounded-in-primary-automatic-handoff-r2'
MAX_WAIT_SECONDS = 8*3600
POLL_SECONDS = 15
QUIET_CONFIRM_SECONDS = 3


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT / 'tools' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def snapshot(name, value):
    scope.PRIMARY_ROOT.mkdir(parents=True, exist_ok=True)
    atomic_write(scope.PRIMARY_ROOT / name, json_bytes({'version': VERSION, 'unix': time.time(), **value}))


def quiet_after_gate(observation, gate_unix):
    if observation.get('ready') is not True or not isinstance(gate_unix, (int, float)):
        return False
    snapshots = observation.get('snapshots', {})
    if set(snapshots) != {'primary', 'api'}:
        return False
    return all(isinstance(item.get('progress', {}).get('unix'), (int, float))
               and item['progress']['unix'] > gate_unix for item in snapshots.values())


def wait_boundary(*, observe, gate_unix, stop, report, clock=time.monotonic,
                  maximum_wait=MAX_WAIT_SECONDS, poll=POLL_SECONDS, confirmation=QUIET_CONFIRM_SECONDS):
    """Two fresh empty boundaries; no signal or resource change in this loop."""
    started, first = clock(), None
    while not stop.is_set():
        now = clock()
        if now-started >= maximum_wait:
            raise TimeoutError('The bounded eight-hour natural handoff wait expired')
        observation = observe()
        quiet = quiet_after_gate(observation, gate_unix)
        report({'phase': 'waiting_for_natural_completion', 'elapsed_seconds': now-started,
            'remaining_seconds': max(0, maximum_wait-(now-started)),
            'ready': quiet, 'reasons': observation.get('reasons', []),
            'active_claim_keys': observation.get('active_claim_keys', []),
            'reserved_API_requests': observation.get('reserved_API_requests'),
            'old_tasks_cancelled': False, 'model_units_reloaded': False})
        if quiet:
            if first is None:
                first = now
            elif now-first >= confirmation:
                return observation
        else:
            first = None
        stop.wait(min(confirmation if quiet else poll, maximum_wait-(clock()-started)))
    raise InterruptedError('Automatic handoff stopped before the quiet boundary')


def pre_signal_rollback(*, guard):
    """Never pretend that an original coordinator can resume after any signal."""
    if ((scope.HANDOFF_ROOT / 'coordinators-stopped.json').exists()
            or list(scope.HANDOFF_ROOT.glob('*-signal-intent.json'))):
        return {'performed': False, 'reason': 'owned_coordinator_signal_already_recorded'}
    result = handoff.rollback_gate(guard=guard)
    return {'performed': True, 'result': result}


def wait_and_prepare():
    scope.require_allowed('v076.handoff')
    actual = scope.verify_host_limits('primary')
    parent.require_qualified()
    if (scope.BATCH_ROOT / 'plan-seal.json').exists():
        return {'already_prepared': True}
    if ((scope.PRIMARY_ROOT / 'execution-started.json').exists()
            or (scope.PRIMARY_ROOT / 'bootstrap-started.json').exists()):
        raise ValueError('An entered primary cannot rerun its handoff')
    gate = json.loads((scope.HANDOFF_ROOT / 'gate.json').read_bytes())
    reservation = scope.reserve_primary_bootstrap()
    stop = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        write_new(scope.PRIMARY_ROOT / 'bootstrap-started.json', {'version': VERSION, 'unix': time.time(),
            'authorization': reference(scope.AUTH_FILE), 'gate': reference(scope.HANDOFF_ROOT / 'gate.json'),
            'reservation': reservation, 'actual_limits': actual, 'maximum_wait_seconds': MAX_WAIT_SECONDS,
            'new_model_API_calls': 0, 'additional_service_created': False})
        def observe():
            parent.require_qualified()
            return handoff.observe(guard=scope.require_allowed)

        wait_boundary(observe=observe, gate_unix=gate['unix'], stop=stop,
                      report=lambda value: snapshot('bootstrap-progress.json', value))
        if stop.is_set():
            raise InterruptedError('Handoff cancelled before coordinator signal')
        stopped = handoff.stop_quiescent(guard=scope.require_allowed)
        if stopped.get('status') == 'waiting':
            raise RuntimeError('The physical boundary changed after the confirmed quiet interval')
        # SIGKILL delivery and systemd own cgroup collection are asynchronous;
        # never restore discovery while either old coordinator is still alive.
        staged, deadline = handoff.stage_value(), time.monotonic()+30
        while True:
            live = [role for role, item in staged['coordinators'].items()
                    if handoff.validate_unit(role, scope.load(item['specification']), handoff.show(role)) is not None]
            if not live:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('The signalled original coordinators have not proved inactive')
            time.sleep(.2)
        restored = handoff.restore_ready(guard=scope.require_allowed)
        released = scope.release_primary_bootstrap(reservation, previous_primary_stopped=True)
        preparation = module('v076_bootstrap_preparation', 'prepare_adaptive_v076.py').prepare_inventory()
        result = {'version': VERSION, 'unix': time.time(), 'coordinators_stopped': stopped,
            'original_model_discovery_restored': restored, 'bootstrap_capacity_released': released,
            'inventory_preparation': preparation, 'model_units_reloaded': False,
            'old_inflight_tasks_cancelled': False}
        write_new(scope.PRIMARY_ROOT / 'bootstrap-completed.json', result)
        snapshot('bootstrap-progress.json', {'phase': 'handoff_complete_starting_primary', **result})
        return result
    except Exception as error:
        recovery = {'performed': False}
        try:
            recovery = pre_signal_rollback(guard=scope.require_allowed)
        except Exception as rollback_error:
            recovery = {'performed': False, 'error': str(rollback_error)}
        release = None
        if scope.BOOTSTRAP_LEASE.exists():
            try:
                release = scope.release_primary_bootstrap(reservation, aborted_before_generation=True)
            except Exception as release_error:
                release = {'error': str(release_error)}
        snapshot('bootstrap-failure.json', {'phase': 'handoff_requires_review',
            'error': {'type': type(error).__name__, 'message': str(error)},
            'pre_signal_rollback': recovery, 'bootstrap_release': release,
            'API_parent_retained': True, 'model_units_reloaded': False})
        raise
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


class AutoAPILauncher:
    """One launch attempt after the new primary publishes its own live cursor."""
    def __init__(self, *, stop=None, timeout=600, launcher=None):
        self.stop = stop or threading.Event()
        self.timeout = timeout
        self.launcher = launcher or module('v076_automatic_api_launcher', 'launch_adaptive_v076.py')
        self.thread = threading.Thread(target=self._run, name='v076-start-api-after-primary', daemon=False)

    def start(self):
        self.thread.start()

    def _run(self):
        deadline = time.monotonic()+self.timeout
        try:
            while not self.stop.is_set() and time.monotonic() < deadline:
                if scope.PRIMARY_CURSOR.exists():
                    value = json.loads(scope.PRIMARY_CURSOR.read_bytes())
                    if value.get('failure') is not None:
                        raise RuntimeError('Primary failed before automatic API startup')
                    if value.get('phase') in {'starting', 'running', 'waiting'} and isinstance(value.get('qualifications'), dict):
                        result = self.launcher.launch('api')
                        snapshot('automatic-api-launch.json', {'status': 'launch_returned', 'result': result})
                        return
                self.stop.wait(.2)
            snapshot('automatic-api-launch.json', {'status': 'not_attempted',
                'reason': 'primary_execution_ended' if self.stop.is_set() else 'primary_cursor_timeout',
                'automatic_retry': False})
        except Exception as error:
            snapshot('automatic-api-launch.json', {'status': 'launch_requires_review',
                'error': {'type': type(error).__name__, 'message': str(error)}, 'automatic_retry': False})

    def close(self):
        self.stop.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=60)
        if self.thread.is_alive():
            raise RuntimeError('Owned automatic API starter has not finished')
