"""Retain the owner's hard cap while distinguishing inactive clean file cache."""
from __future__ import annotations

from pathlib import Path

from . import software_benchmark_pressure_v079 as previous
from . import software_benchmark_rolling_scope_v083 as scope
from .software_benchmark_deepseek_runtime_v069 import private_function


def working_set(value, statistics):
    required = ('file', 'inactive_file', 'file_dirty', 'file_writeback', 'anon')
    if any(type(statistics.get(key)) is not int or statistics[key] < 0 for key in required):
        raise ValueError('Complete nonnegative owner memory.stat observations are mandatory')
    if type(value.get('current_bytes')) is not int or value['current_bytes'] < 0:
        raise ValueError('A trustworthy raw owner memory.current observation is mandatory')
    reclaimable = max(0, min(statistics['inactive_file'], statistics['file'])
                      - statistics['file_dirty']-statistics['file_writeback'])
    reclaimable = min(reclaimable, value['current_bytes'])
    return {**value, 'raw_current_bytes': value['current_bytes'], 'memory_stat': statistics,
        'conservative_reclaimable_file_bytes': reclaimable,
        'working_set_bytes': value['current_bytes']-reclaimable}


def owner_probe():
    value = private_function(previous.owner_probe, scope=scope)()
    path = Path('/sys/fs/cgroup')/value['cgroup'].lstrip('/')/'memory.stat'
    statistics = {key: int(number) for key, number in
                  (line.split() for line in path.read_text().splitlines())}
    return working_set(value, statistics)


class PressureWatchdog(previous.PressureWatchdog):
    def __init__(self, *args, coordinator_probe=owner_probe, **kwargs):
        super().__init__(*args, coordinator_probe=coordinator_probe, **kwargs)

    def owner_observation(self):
        # Reuse the existing hysteresis/emergency thresholds; only its admission
        # measurement changes. Kernel memory.max remains exactly 64 GiB.
        try:
            observed = self.coordinator_probe()
            value = working_set(observed, observed.get('memory_stat', {}))
            if value.get('qualified') is not True or value.get('max_bytes') != scope.API_MEMORY_BYTES:
                raise ValueError('Owner memory observation is outside the exact scope')
            available = max(0, value['max_bytes']-value['working_set_bytes'])
            if available < previous.PAUSE:
                self._owner_paused = True
            elif available >= previous.RESUME:
                self._owner_paused = False
            return {**value, 'admit': not self._owner_paused, 'available_bytes': available,
                'raw_available_bytes': max(0, value['max_bytes']-value['raw_current_bytes']),
                'pause_bytes': previous.PAUSE, 'resume_bytes': previous.RESUME,
                'emergency_bytes': previous.EMERGENCY, 'critical_bytes': previous.CRITICAL,
                'emergency': available <= previous.EMERGENCY, 'critical': available <= previous.CRITICAL,
                'admission_measure': 'conservative_working_set', 'hard_memory_max_unchanged': True}
        except Exception as error:
            self._owner_paused = True
            return {'qualified': False, 'admit': False, 'available_bytes': None,
                'emergency': False, 'critical': False,
                'error': {'type': type(error).__name__, 'message': str(error)}}
