"""Exact 79 original-ID ownership at every inherited pressure-monitor call site."""
from __future__ import annotations

from types import SimpleNamespace

from . import software_benchmark_pressure_v076 as physical
from . import software_benchmark_pressure_v079 as owner
from . import software_benchmark_pressure_v083 as working
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v096-exact-original-first-entry-pressure-r1'


def pressure_view(rows,*,scope):
    allowed = frozenset(scope.validate_registry(rows))

    class ExactOriginalIdentities:
        @staticmethod
        def fullmatch(slot):
            return slot if isinstance(slot,str) and slot in allowed else None

    pair = private_function(physical._pair,_API_SLOT=ExactOriginalIdentities)
    capture = private_function(physical.capture_owned_container,_API_SLOT=ExactOriginalIdentities)
    private_physical = SimpleNamespace(**{**vars(physical),'_pair':pair,'capture_owned_container':capture})

    class PhysicalWatchdog(physical.PressureWatchdog):
        tick = private_function(physical.PressureWatchdog.tick,_pair=pair)

    class Watchdog(working.PressureWatchdog,PhysicalWatchdog):
        tick = private_function(owner.PressureWatchdog.tick,previous=private_physical)
        owner_observation = private_function(working.PressureWatchdog.owner_observation,scope=scope)

    return SimpleNamespace(**{**vars(working),'VERSION':VERSION,'PressureWatchdog':Watchdog,
        'owner_probe':private_function(working.owner_probe,scope=scope),'normalize_owned_pair':pair,
        'capture_owned_container':capture,'allowed_original_slot_ids':allowed})
