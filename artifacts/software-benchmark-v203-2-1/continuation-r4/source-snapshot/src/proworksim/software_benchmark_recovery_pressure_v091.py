"""Exact sealed recovery identities at every pressure-monitor call site."""
from __future__ import annotations

from types import SimpleNamespace

from . import software_benchmark_pressure_v076 as physical
from . import software_benchmark_pressure_v079 as owner
from . import software_benchmark_pressure_v083 as working
from . import software_benchmark_deepseek_budget_v089 as budget
from .software_benchmark_candidates_v054 import reference
from .software_benchmark_deepseek_runtime_v069 import private_function

VERSION = 'v091-exact-unentered-recovery-pressure-identities-r1'


def pressure_view(rows, *, scope, original_rows=None):
    registry = scope.load(reference(scope.INVENTORY_FILE))
    if registry.get('rows') != rows or len(rows) != 44:
        raise PermissionError('Pressure observation requires the sealed complete recovery registry')
    allowed = frozenset(budget.validate_retry_registry(rows, originals=original_rows))

    class ExactRecoveryIdentities:
        @staticmethod
        def fullmatch(slot):
            return slot if isinstance(slot, str) and slot in allowed else None

    pair = private_function(physical._pair, _API_SLOT=ExactRecoveryIdentities)
    capture = private_function(physical.capture_owned_container, _API_SLOT=ExactRecoveryIdentities)
    private_physical = SimpleNamespace(**{**vars(physical), '_pair': pair,
        'capture_owned_container': capture})

    class PhysicalRecoveryWatchdog(physical.PressureWatchdog):
        tick = private_function(physical.PressureWatchdog.tick, _pair=pair)

    class RecoveryWatchdog(working.PressureWatchdog, PhysicalRecoveryWatchdog):
        # Original owner.tick's super() now resolves to the private physical
        # tick through this MRO, while its owner-emergency path uses the same
        # exact registry validator. No original function dictionary is edited.
        tick = private_function(owner.PressureWatchdog.tick, previous=private_physical)
        owner_observation = private_function(working.PressureWatchdog.owner_observation, scope=scope)

    return SimpleNamespace(**{**vars(working), 'VERSION': VERSION,
        'PressureWatchdog': RecoveryWatchdog,
        'owner_probe': private_function(working.owner_probe, scope=scope),
        'normalize_owned_pair': pair, 'capture_owned_container': capture,
        'allowed_recovery_slot_ids': allowed})
