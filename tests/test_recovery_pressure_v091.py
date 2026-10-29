import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_api_scope_v091 as scope
from proworksim import software_benchmark_recovery_runtime_v091 as runtime
from proworksim import software_benchmark_pressure_v076 as old_pressure
from proworksim.software_benchmark_recovery_pressure_v091 import pressure_view

GIB = 1024**3


def fixture_registry(tmp_path):
    original, rows = {}, []
    for i in range(44):
        row = {'slot_id': f'v064:task-{i}:DEEPSEEK_REF_B5000K:{i}', 'slot_index': i,
            'model_key': 'DEEPSEEK', 'condition_id': 'DEEPSEEK_REF_B5000K',
            'instance_id': f'task-{i}', 'arm': 'REF', 'input_plus_output_tokens': 5_000_000, 'seed': i}
        original[row['slot_id']] = row
        rows.append({**row, 'slot_id': row['slot_id']+':recovery-v089-r1', 'slot_index': 6000+i,
            'original_slot_id': row['slot_id'], 'original_slot_index': i, 'recovery_attempt': 1})
    inventory = tmp_path/'registry.json'
    inventory.write_text(json.dumps({'rows': rows}))
    view = SimpleNamespace(INVENTORY_FILE=inventory, API_MEMORY_BYTES=64*GIB,
                           load=lambda ref: json.loads(Path(ref['path']).read_bytes()))
    return pressure_view(rows, scope=view, original_rows=original), rows


def owner(current=GIB):
    return {'qualified': True, 'current_bytes': current, 'max_bytes': 64*GIB,
        'memory_stat': {'file': 0, 'inactive_file': 0, 'file_dirty': 0, 'file_writeback': 0, 'anon': current}}


def pairs(rows):
    return [{'slot_id': row['slot_id'], 'model_key': 'DEEPSEEK', 'ownership_token': str(i).zfill(32),
             'started_unix': 100+i} for i, row in enumerate(rows)]


def watchdog(view, registry, abort=lambda *args: None, owner_current=GIB):
    return view.PressureWatchdog(lambda: registry, abort, memory_probe=lambda: 800*GIB,
        coordinator_probe=lambda: owner(owner_current), require_parent=True,
        parent_probe=lambda: {'qualified': True, 'current_bytes': 0, 'max_bytes': 224*GIB},
        clock=lambda: 100, wall_clock=lambda: 1000)


def test_twelve_preentry_recovery_futures_no_longer_deadlock_and_old_guard_remains(tmp_path):
    view, rows = fixture_registry(tmp_path)
    registry = pairs(rows[:12])
    with pytest.raises(ValueError, match='active owned'):
        old_pressure._pair(registry[0])
    monitor = watchdog(view, registry)
    try:
        value = monitor.tick()
        assert value['admit'] is True and value['observation_error'] is None
        assert len(value['API_pair_memory_observations']) == 12
        assert all(row['pair_memory_current_bytes'] is None for row in value['API_pair_memory_observations'])
    finally:
        monitor.close()
    with pytest.raises(ValueError, match='active owned'):
        old_pressure._pair(registry[0])


def test_owner_emergency_uses_same_exact_ids_and_ownership_tokens(tmp_path):
    view, rows = fixture_registry(tmp_path)
    registry, aborted = pairs(rows[:12]), []
    monitor = watchdog(view, registry, abort=lambda pair, reason: aborted.append((pair, reason)),
                       owner_current=63*GIB)
    try:
        value = monitor.tick()
        assert value['admit'] is False and len(aborted) == 4
        for pair, reason in aborted:
            expected = next(row for row in registry if row['slot_id'] == pair['slot_id'])
            assert pair['ownership_token'] == expected['ownership_token']
            assert reason['reason'] == 'API_coordinator_memory_emergency'
            assert reason['Qwen_affected'] is False and reason['automatic_retry'] is False
    finally:
        monitor.close()


def test_foreign_original_and_malformed_registry_entries_remain_rejected(tmp_path):
    view, rows = fixture_registry(tmp_path)
    row = pairs(rows[:1])[0]
    assert view.normalize_owned_pair(row)['slot_id'] == row['slot_id']
    for change in ({'slot_id': row['slot_id'].removesuffix(':recovery-v089-r1')},
                   {'slot_id': row['slot_id']+':foreign'}, {'ownership_token': ''},
                   {'started_unix': float('nan')}, {'model_key': 'QWEN'}):
        with pytest.raises(ValueError):
            view.normalize_owned_pair({**row, **change})
    assert view.capture_owned_container.__globals__['_API_SLOT'].fullmatch(row['slot_id'])
    assert view.capture_owned_container.__globals__['_API_SLOT'].fullmatch('foreign') is None


def test_new_episode_and_score_bindings_resolve_to_current_scope_at_actual_callsites(monkeypatch):
    calls = []

    def guard(*args, **kwargs):
        calls.append((args, kwargs))

    policy = runtime.bindings.policy(guard, watchdog_guard=lambda: {'fresh': True, 'admit': True},
        capacity_probe=lambda: {'memory_available_bytes': 800*GIB, 'disk_free_bytes': 2000*GIB,
            'cpu_sample_fresh': True, 'host_cpu_utilization_percent': 5})
    episode = runtime.bindings.episode(policy)
    assert episode._run.__globals__['policy'] is policy
    assert episode.wait_capacity.__globals__['capacity'] is policy.physical_capacity
    assert episode.OwnedActorPair.create_container.__globals__['policy'] is policy
    assert episode.OwnedActorPair.cleanup.__globals__['policy'] is policy
    assert episode.OwnedActorPair.start.__globals__['parent'] is scope.parent_module()
    grader = runtime.grading.Grading(policy)
    assert grader.run_request.__globals__['scope'] is scope
    assert grader.base.RUN_ROOT == scope.COORDINATOR_ROOT
    assert grader.scorer.validate_qualification.__globals__['scope'] is scope
    assert grader.scorer.Containers.create.__globals__['policy'] is policy
    assert grader.base.delivery_disposition.__globals__['prepare_score'] is grader.base.prepare_score
    monkeypatch.setattr(runtime.original_grading.original_scorer.original_scorer,
                        'installation_manifest', lambda: {'unchanged': True})
    child = runtime.grading.scorer(runtime.bindings.dispatch_view(guard))
    assert grader.scorer.installation_manifest() == child.installation_manifest()


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, scope.ROOT/'tools'/name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_owner_and_recorder_have_no_old_manager_closures():
    runner = load_tool('run_api_pressure_recovery_v091.py')
    launcher = load_tool('launch_api_pressure_recovery_v091.py')
    assert runner.scope is scope
    assert runner.Recorder.save_record.__globals__['scope'] is scope
    assert runner.Recorder.flush.__globals__['scope'] is scope
    assert runner.Admission.limit.__globals__['scope'] is scope
    assert scope.reserve_api_coordinator.__globals__['require_allowed'] is scope.require_allowed
    assert scope.release_api_coordinator.__globals__['CLAIM_FILE'] == scope.CLAIM_FILE
    assert scope.verify_host_limits.__globals__['API_UNIT'] == scope.API_UNIT
    assert scope.PLAN_FILE == scope.predecessor.PLAN_FILE
    assert scope.INVENTORY_FILE == scope.predecessor.INVENTORY_FILE
    assert scope.API_ROOT != scope.predecessor.API_ROOT
    spec = {**launcher.fixed_spec(), 'ownership_token': 'a'*32}
    command = launcher.command(spec)
    assert '--unit=proworksim-v091-api.service' in command
    assert '--property=MemoryHigh=32G' in command and '--property=LimitNOFILE=16384' in command


def test_handoff_rejects_consumption_and_parent_recreation(tmp_path, monkeypatch):
    path = tmp_path/'handoff.json'
    monkeypatch.setattr(scope, 'HANDOFF_FILE', path)
    for value in ({'version': 'v091-exact-zero-consumption-owner-handoff-r1'},
                  {'version': 'v091-exact-zero-consumption-owner-handoff-r1', 'old_main_pid_exited': True,
                   'all_44_model_attempts_unconsumed': False},
                  {'version': 'v091-exact-zero-consumption-owner-handoff-r1', 'old_main_pid_exited': True,
                   'all_44_model_attempts_unconsumed': True, 'all_44_physical_identities_unconsumed': True,
                   'original_API_parent_stopped': True}):
        path.write_text(json.dumps(value))
        with pytest.raises(PermissionError, match='zero-consumption'):
            scope.require_handoff()
