"""Observe the API owner cgroup separately from its Docker aggregate parent."""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_pressure_v076 as previous
from . import software_benchmark_api_scope_v079 as scope

GIB = 1024**3
PAUSE = 24*GIB
RESUME = 32*GIB
EMERGENCY = 8*GIB
CRITICAL = 4*GIB


def owner_probe():
    paths = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
             if line.startswith('0::')]
    if len(paths) != 1 or Path(paths[0]).name != scope.API_UNIT:
        raise PermissionError('Owner pressure probe is outside the exact new API coordinator')
    folder = Path('/sys/fs/cgroup')/paths[0].lstrip('/')
    maximum = (folder/'memory.max').read_text().strip()
    swap = (folder/'memory.swap.max').read_text().strip()
    current = int((folder/'memory.current').read_text().strip())
    if maximum != str(scope.API_MEMORY_BYTES) or swap != '0' or current < 0:
        raise PermissionError('Owner memory boundary differs from the API64GiB scope')
    return {'qualified': True, 'current_bytes': current, 'max_bytes': scope.API_MEMORY_BYTES,
            'cgroup': paths[0], 'swap_max_bytes': 0}


class PressureWatchdog(previous.PressureWatchdog):
    """One monitor thread gates actors and graders on all three memory layers."""
    def __init__(self, snapshot_pairs, request_abort, observe=lambda value: None, *,
                 coordinator_probe=owner_probe, **kwargs):
        self.coordinator_probe = coordinator_probe
        self._owner_paused = True
        self._owner_state = {'qualified': False, 'admit': False, 'available_bytes': None,
                             'emergency': False, 'critical': False}
        self._owner_observer = observe
        super().__init__(snapshot_pairs, request_abort, observe=lambda value: None, **kwargs)

    def owner_observation(self):
        try:
            value = self.coordinator_probe()
            if (not isinstance(value, dict) or value.get('qualified') is not True
                    or type(value.get('current_bytes')) is not int or value['current_bytes'] < 0
                    or value.get('max_bytes') != scope.API_MEMORY_BYTES):
                raise ValueError('API owner memory observation is incomplete or outside 64GiB scope')
            available = max(0, value['max_bytes']-value['current_bytes'])
            if available < PAUSE:
                self._owner_paused = True
            elif available >= RESUME:
                self._owner_paused = False
            return {**value, 'admit': not self._owner_paused, 'available_bytes': available,
                'pause_bytes': PAUSE, 'resume_bytes': RESUME, 'emergency_bytes': EMERGENCY,
                'critical_bytes': CRITICAL, 'emergency': available <= EMERGENCY,
                'critical': available <= CRITICAL}
        except Exception as error:
            self._owner_paused = True
            return {'qualified': False, 'admit': False, 'available_bytes': None,
                'emergency': False, 'critical': False,
                'error': {'type': type(error).__name__, 'message': str(error)}}

    def admission(self):
        result = super().admission()
        with self._lock:
            owner = dict(self._owner_state)
        return {**result, 'owner_pressure': owner,
            'fresh': result['fresh'] and owner['qualified'],
            'admit': result['admit'] and owner['admit'],
            'reason': ('API_owner_observation_unavailable' if not owner['qualified'] else
                       'API_owner_memory_emergency' if owner['emergency'] else
                       'API_owner_hysteresis_pause' if not owner['admit'] else result['reason']),
            'required_observations_complete': result['required_observations_complete'] and owner['qualified']}

    def tick(self):
        with self._lock:
            self._owner_state = self.owner_observation()
        super().tick()
        owner, now = self._owner_state, self.clock()
        if owner['emergency'] and now-self._last_abort >= previous.ABORT_INTERVAL_SECONDS:
            try:
                rows = [previous._pair(row) for row in self.snapshot_pairs() if row.get('model_key') == 'DEEPSEEK']
                candidates = [row for row in rows if row['slot_id'] not in self._aborted]
                candidates.sort(key=lambda row: (row['started_unix'], row['slot_id']), reverse=True)
                for row in candidates[:4 if owner['critical'] else 1]:
                    self._aborted.add(row['slot_id'])
                    self._last_abort = now
                    event = {'reason': 'API_coordinator_memory_emergency', 'owner_pressure': dict(owner),
                        'technical_unknown': True, 'automatic_retry': False, 'stop_entire_owned_pair': True,
                        'Qwen_affected': False, 'parent_scope_stopped': False}
                    try:
                        self.request_abort(dict(row), event)
                        event['outcome'] = 'owned_episode_stop_requested'
                    except Exception as error:
                        event.update(outcome='abort_callback_outcome_unknown', callback_error=str(error))
                    with self._lock:
                        self._state['last_owner_abort'] = {'slot_id': row['slot_id'], **event}
                        self._state['aborted_slot_ids'] = sorted(self._aborted)
            except Exception as error:
                with self._lock:
                    self._owner_state = {**owner, 'qualified': False, 'admit': False,
                        'error': {'type': type(error).__name__, 'message': str(error)}}
        result = self.admission()
        try:
            self._owner_observer(result)
        except Exception as error:
            with self._lock:
                self._state['observer_error'] = {'type': type(error).__name__, 'message': str(error)}
        return result
