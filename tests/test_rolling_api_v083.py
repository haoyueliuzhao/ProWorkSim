import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_rolling_handoff_v083 as handoff
from proworksim import software_benchmark_rolling_scope_v083 as scope
from proworksim import software_benchmark_pressure_v083 as pressure
from proworksim import software_benchmark_pressure_v079 as old_pressure
from proworksim import software_benchmark_resources_v083 as resources
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('prepare83_test', 'prepare_rolling_api_v083.py')
runner = module('runner83_test', 'run_rolling_api_v083.py')
launcher = module('launcher83_test', 'launch_rolling_api_v083.py')


def test_rolling_partition_preserves_live_ownership_without_replay_or_failure():
    rows = [{'slot_id': f'api-{i}', 'slot_index': i, 'model_key': 'DEEPSEEK',
             'input_plus_output_tokens': 5_000_000} for i in range(1000)]
    rows += [{'slot_id': f'qwen-{i}', 'slot_index': 1000+i, 'model_key': 'QWEN',
              'input_plus_output_tokens': 5_000_000} for i in range(5000)]
    completed = {'status': 'closed', 'result': {'original': True}}
    targets, state, allowed, old, external, excluded = prepare.partition(rows,
        {'generation': {'api-0': completed}, 'scores': {}, 'deliveries': {}},
        {'excluded_old_scheduled_slot_ids': ['api-1']}, ['api-2', 'api-3'],
        ['api-2', 'api-4'], ['api-5'], ['api-6'])
    assert len(targets) == 1000 and len(allowed) == 993
    assert state['generation']['api-0'] is completed
    assert not set(allowed) & set(old)
    assert set(external) == {'api-2', 'api-3'}
    assert state['generation']['api-3']['status'] == 'external_running'
    assert not state['generation']['api-3']['entered']
    assert set(excluded) == {'api-1', 'api-2', 'api-3'}


def test_owner_ceiling_accounts_for_old_futures_before_they_claim():
    limit = runner.own_future_limit({'additional_pair_slots': 8}, own_actors=30,
        old_actors=10, old_unclaimed=5, desired=48, ramp=48)
    assert limit == 33 and limit+10+5 <= 48
    assert runner.own_future_limit({'additional_pair_slots': 8}, own_actors=0,
        old_actors=43, old_unclaimed=2, desired=48, ramp=48) == 3


def test_new_memory_measure_deducts_only_clean_inactive_file_cache():
    raw = {'qualified': True, 'current_bytes': 41*scope.GIB, 'max_bytes': 64*scope.GIB}
    stats = {'anon': 15*scope.GIB, 'file': 26*scope.GIB, 'inactive_file': 10*scope.GIB,
             'file_dirty': scope.GIB, 'file_writeback': 0}
    value = pressure.working_set(raw, stats)
    assert value['working_set_bytes'] == 32*scope.GIB
    assert value['raw_current_bytes'] == 41*scope.GIB
    assert value['max_bytes'] == 64*scope.GIB
    with pytest.raises(ValueError, match='memory.stat'):
        pressure.working_set(raw, {'file': 20})


def test_new_owner_gate_restores_admission_but_missing_stat_is_not_free_ram():
    values = {'qualified': True, 'current_bytes': 41*scope.GIB, 'max_bytes': 64*scope.GIB,
              'memory_stat': {'anon': 15*scope.GIB, 'file': 26*scope.GIB,
                  'inactive_file': 10*scope.GIB, 'file_dirty': 0, 'file_writeback': 0}}
    guard = pressure.PressureWatchdog(lambda: [], lambda *args: pytest.fail('No abort'),
        coordinator_probe=lambda: values, memory_probe=lambda: 900*scope.GIB,
        parent_probe=lambda: {'qualified': True, 'current_bytes': 80*scope.GIB, 'max_bytes': 224*scope.GIB},
        require_parent=True)
    assert guard.tick()['admit']
    values.pop('memory_stat')
    assert not guard.tick()['admit']
    assert old_pressure.owner_probe.__globals__['scope'] is not scope


def test_API_resource_namespace_uses_tolerant_JSON_without_mutating_live_original():
    assert resources._safe_previous.pending_pairs is resources.safe_pending_pairs
    assert resources.original.pending_pairs is not resources.safe_pending_pairs
    assert resources.policy.__globals__['previous'] is resources._safe_previous
    assert resources.previous.policy.__globals__['previous'] is resources.original
    policy = resources.policy(lambda *args, **kwargs: {}, watchdog_guard=lambda: {},
        capacity_probe=lambda: {}, qwen_target=0)
    assert policy.admission_snapshot.__globals__['pending_pairs'] is resources.safe_pending_pairs


def test_pause_boundary_needs_fresh_desired_zero_ack():
    value = {'unix': 110, 'configured_generation_limit': 0, 'effective_generation_limit': 0}
    assert handoff.acknowledged(value, gate_unix=100, now=111)
    assert not handoff.acknowledged(value, gate_unix=110, now=111)
    assert not handoff.acknowledged(value, gate_unix=100, now=180)
    assert not handoff.acknowledged({**value, 'configured_generation_limit': 48}, gate_unix=100, now=111)
    assert handoff.stage.__globals__['identity'] is handoff.identity
    assert handoff.stage.__globals__['scope'] is scope


def test_history_merge_never_duplicates_or_replaces_successor_scores():
    current = {'generation': {'old': {'status': 'external_running'}, 'new': {'status': 'closed'}},
        'scores': {'new': {'resolved': True}}, 'deliveries': {'old': {'status': 'official_attempt_completed'}}}
    old = {'generation': {'old': {'status': 'closed'}}, 'scores': {'old': {'resolved': False}},
           'deliveries': {'old': {'status': 'waiting_for_own_code_score'}}}
    value = runner.combined_history(current, old, {'old'}, {'new'})
    assert len(value['generation']) == 2 and len(value['scores']) == 2
    assert value['generation']['old']['status'] == 'closed'
    assert value['scores']['new']['resolved']
    assert value['deliveries']['old']['status'] == 'official_attempt_completed'
    with pytest.raises(ValueError, match='overlaps'):
        runner.combined_history(current, old, {'old'}, {'old'})


def scoring_fixture(tmp_path, *, kind='code'):
    row = {'slot_id': 'original', 'slot_index': 7, 'configuration': {'original': True}}
    result = write_new(tmp_path/'result.json', {'slot_id': 'original'})
    folder = tmp_path/('score-7' if kind == 'code' else 'delivery-score-7')
    folder.mkdir()
    request = write_new(folder/'request.json', {'slot_id': 'original', 'configuration': row['configuration'],
        'generation_result': result, 'directory': str(folder), 'resource_key': folder.name})
    cursor = {'generation': {'original': {'status': 'closed', 'result': result}},
              'active_grading': [request], 'pending_scores': []}
    return row, cursor, folder, request


def test_takeover_preserves_never_started_request_but_refuses_started_test(tmp_path):
    row, cursor, folder, request = scoring_fixture(tmp_path)
    assert handoff.transferable_jobs(cursor, {'original'}, [row]) == [('code', row, request, True)]
    (folder/'capacity-claim.json').write_text('{}')
    with pytest.raises(ValueError, match='started official test'):
        handoff.transferable_jobs(cursor, {'original'}, [row])


def test_completed_delivery_can_transfer_with_original_quiescence(tmp_path):
    row, cursor, folder, request = scoring_fixture(tmp_path, kind='delivery')
    write_new(folder/'completion.json', {'request': request})
    write_new(folder/'quiescence.json', {'resource_key': folder.name, 'quiescent': True,
        'cleanup_errors': [], 'create_result_unknown': False})
    assert handoff.transferable_jobs(cursor, {'original'}, [row]) == [('delivery', row, request, True)]
    assert reference(folder/'request.json') == request


def test_new_user_manager_has_distinct_CPU_lanes_and_keeps_parent_and_Qwen():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'f'*32}
    argv = launcher.command(spec)
    assert argv[:2] == ['systemd-run', '--user']
    assert '--property=MemoryMax=64G' in argv
    assert scope.cpu_affinity() == scope.original.host_cpu_pool()[164:168]
    assert not set(scope.cpu_affinity()) & set(scope.prior.cpu_affinity())
    assert scope.API_UNIT == 'proworksim-v083-api.service'
    assert not any(value == 'stop' or value == '--system' for value in argv)


def test_busy_old_process_is_never_addressed(monkeypatch):
    monkeypatch.setattr(scope, 'require_allowed', lambda *args, **kwargs: {})
    monkeypatch.setattr(handoff, 'old_observation', lambda _: {'ready': False})
    monkeypatch.setattr(handoff, 'show', lambda: pytest.fail('Must not address old process'))
    with pytest.raises(ValueError, match='still active'):
        handoff.retire_old({'original'})


def test_post_signal_bookkeeping_can_resume_without_resending_or_touching_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff, 'OUT', tmp_path/'handoff')
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'new')
    monkeypatch.setattr(handoff.old_scope, 'CLAIM_FILE', tmp_path/'old-claim.json')
    handoff.OUT.mkdir()
    scope.API_ROOT.mkdir()
    specification = write_new(tmp_path/'spec.json', {'exact': True})
    claim = write_new(handoff.old_scope.CLAIM_FILE, {'exact_old_lease': True})
    release = write_new(tmp_path/'released.json', {'claim': claim})
    process = {'pid': 12345, 'starttime': 100}
    monkeypatch.setattr(handoff, 'stage_value', lambda: {'process': process, 'specification': specification})
    monkeypatch.setattr(handoff, 'show', lambda: {})
    monkeypatch.setattr(handoff, 'identity', lambda *args: None)
    monkeypatch.setattr(handoff.old_scope, 'release_api_coordinator', lambda ref: release if ref == claim else pytest.fail('Other lease'))
    cursor = write_new(tmp_path/'cursor.json', {'generation': {'original': {'status': 'closed'}}, 'scores': {}, 'deliveries': {}})
    progress = write_new(tmp_path/'progress.json', {'done': True})
    intent = write_new(handoff.OUT/'signal-intent.json', {'process': process, 'signal': 'SIGKILL',
        'old_live_tasks_cancelled': False, 'cursor': cursor, 'progress': progress, 'transferable_scoring_jobs': []})
    result = scope.load(handoff.finish_retirement(intent, {'original'}))
    assert result['parent_stopped_or_recreated'] is False
    assert result['Qwen_lifecycle_operations'] == 0
    assert scope.load(reference(scope.API_ROOT/'historical-results.json'))['generation']['original']['status'] == 'closed'


def test_old_admissions_cannot_reopen_after_successor_launch_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path)
    (tmp_path/'launch-intent.json').write_text('{}')
    with pytest.raises(PermissionError, match='Never reopen'):
        handoff.rollback_before_launch()
