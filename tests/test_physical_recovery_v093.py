import copy
from pathlib import Path
import threading

import pytest

from proworksim import software_benchmark_api_scope_v093 as scope
from proworksim import software_benchmark_recovery_runtime_v093 as runtime
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_startup_gate_v093 import StartupHealthGate


def actual_rows():
    return scope.load(reference(scope.INVENTORY_FILE))['rows']


def test_complete_real_plan_retains_fixed_cpu_inventory_and_rejects_missing_contract():
    plan = scope.load(reference(scope.PLAN_FILE))
    inventory = scope.load(reference(scope.INVENTORY_FILE))
    assert scope.validate_complete_plan(plan, inventory) is plan
    dispatch = runtime.bindings.dispatch_view(lambda *args, **kwargs: {})
    assert dispatch.host_cpu_pool() == scope.original.host_cpu_pool()
    assert len(dispatch.host_cpu_pool()) >= 176
    for missing in ('host_cpu_pool', 'configurations', 'constraints', 'continuation_inventory', 'resource_role_counts'):
        changed = copy.deepcopy(plan)
        changed.pop(missing)
        with pytest.raises(PermissionError):
            scope.validate_complete_plan(changed, inventory)


def test_physical_broker_preserves_canonical_model_attempt_and_rejects_legacy_physical_identity():
    calls = []

    class OriginalRuntime:
        def transport_factory(self, row, output):
            calls.append((row, output))
            return {'canonical_dispatch': row['slot_id']}

        def usage_for_slot(self, row):
            return row['slot_index']

    rows = actual_rows()
    view = runtime.PhysicalRuntimeView(OriginalRuntime(), rows)
    row = rows[0]
    assert view.transport_factory(row, Path('/tmp/cpu-output'))['canonical_dispatch'] == row['slot_id']
    assert calls[0][0] == scope.canonical_rows()[0]
    assert calls[0][0]['slot_index'] == 6000 and row['slot_index'] == 6044
    assert view.usage_for_slot(row) == 6000
    for changed in ({**row, 'slot_index': 6000}, {**row, 'seed': row['seed']+1},
                    {**row, 'physical_launch_attempt': 3}, {**row, 'input_plus_output_tokens': 10_000_000}):
        with pytest.raises(PermissionError):
            view.transport_factory(changed, Path('/tmp/cpu-output'))
    assert len(calls) == 1


def make_gate(rows):
    stop = threading.Event()
    paid, events, snapshots = {}, [], []
    gate = StartupHealthGate(rows, stop_event=stop,
        event=lambda kind, **values: events.append((kind, values)), snapshot=snapshots.append,
        probe=lambda slots: dict(paid))
    return gate, stop, paid, events


def test_two_startup_failures_cannot_consume_all_44_physical_slots():
    rows = actual_rows()
    gate, stop, paid, events = make_gate(rows)
    ordered = gate.ordered_rows(rows)
    assert [r['arm'] for r in ordered[:2]] == ['REF', 'PROJECT']
    assert gate.limit(48, set()) == 2
    active = set()
    for row in ordered[:2]:
        active.add(row['slot_id'])
        gate.record('generation_scheduled', slot_id=row['slot_id'])
    assert gate.limit(48, active) == 2
    with pytest.raises(PermissionError):
        gate.require_launch(ordered[2]['slot_id'])
    gate.record('generation_finished', slot_id=ordered[0]['slot_id'])
    active.remove(ordered[0]['slot_id'])
    assert stop.is_set() and gate.limit(48, active) == 0
    assert len(gate.scheduled) == 2 and not gate.passed
    assert [kind for kind, _ in events] == ['startup_health_gate_failed']


def test_only_both_prespecified_settled_interfaces_open_48_not_task_score():
    rows = actual_rows()
    gate, stop, paid, events = make_gate(rows)
    ordered = gate.ordered_rows(rows)
    for row in ordered[:2]:
        gate.record('generation_scheduled', slot_id=row['slot_id'])
    ref, project = ordered[:2]
    paid[ref['slot_id']] = {'request_id': ref['slot_id']+':0001', 'settled_nanoyuan': 1}
    gate.record('generation_finished', slot_id=ref['slot_id'], status='technical_unknown')
    assert not stop.is_set() and not gate.passed
    assert gate.limit(48, {project['slot_id']}) == 1
    paid[project['slot_id']] = {'request_id': project['slot_id']+':0001', 'settled_nanoyuan': 1}
    gate.poll(force=True)
    assert gate.limit(48, {project['slot_id']}) == 48 and gate.passed
    gate.require_launch(ordered[2]['slot_id'])
    assert not stop.is_set()
    assert events[-1][1]['task_scores_used'] is False
