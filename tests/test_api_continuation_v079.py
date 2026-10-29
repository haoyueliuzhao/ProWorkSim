import copy
import importlib.util
from pathlib import Path

import pytest

from proworksim import software_benchmark_api_handoff_v079 as handoff
from proworksim import software_benchmark_api_scope_v079 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_qualification_guard_v079 import require_unchanged_terminal

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prepare = module('test_prepare_api79', 'prepare_api_startup_v079.py')
runner = module('test_run_api79', 'run_api_startup_v079.py')
launcher = module('test_launch_api79', 'launch_api_startup_v079.py')


def idle():
    progress = {'unix': 110, 'failure': None, 'effective_generation_limit': 0,
        'actual_generation_futures': 0, 'active_generation': 0, 'active_grading': 0,
        'pending_scores': 0, 'pending_controls': 0}
    cursor = {'failure': None, 'active_generation': [], 'active_grading': [],
        'pending_scores': [], 'pending_controls': []}
    return progress, cursor


def test_quiet_API_does_not_require_Qwen_pause_but_pending_or_reserved_prevents_handoff():
    progress, cursor = idle()
    assert handoff.quiet_reasons(progress, cursor, [], 0, now=111, gate_unix=100) == []
    for key in ('active_generation', 'active_grading', 'pending_scores', 'pending_controls'):
        altered = {**cursor, key: ['still-owned']}
        assert handoff.quiet_reasons(progress, altered, [], 0, now=111, gate_unix=100)
    assert handoff.quiet_reasons(progress, cursor, ['actor-42'], 0, now=111, gate_unix=100)
    assert handoff.quiet_reasons(progress, cursor, [], 1, now=111, gate_unix=100)
    assert handoff.quiet_reasons(progress, cursor, [], 0, now=200, gate_unix=100)


def test_nonquiet_handoff_never_addresses_process(monkeypatch):
    monkeypatch.setattr(handoff, 'observe', lambda: {'ready': False})
    monkeypatch.setattr(handoff, 'show', lambda: pytest.fail('Must not inspect or address a process'))
    with pytest.raises(ValueError, match='not quiet'):
        handoff.stop_quiet()


def test_dead_cursor_preserves_history_and_cannot_drop_orphans():
    before = {'generation': {'old': {'status': 'closed', 'result': 'immutable'}},
        'scores': {'old': {'resolved': True}}, 'deliveries': {}, 'active_generation': ['orphan']}
    after = copy.deepcopy(before)
    after.update(active_generation=[], active_grading=[], pending_controls=[])
    after['generation']['orphan'] = {'status': 'technical_unknown', 'automatic_replay': False}
    assert handoff.validate_dead_cursor(before, after) is after
    tampered = copy.deepcopy(after)
    tampered['generation']['old']['result'] = 'different'
    with pytest.raises(ValueError, match='terminal'):
        handoff.validate_dead_cursor(before, tampered)
    del after['generation']['orphan']
    with pytest.raises(ValueError, match='lost'):
        handoff.validate_dead_cursor(before, after)


def test_inventory_does_not_replay_any_original_consumed_identity():
    rows = [{'slot_id': f'api-{i}', 'slot_index': i, 'model_key': 'DEEPSEEK',
             'input_plus_output_tokens': 5_000_000} for i in range(1000)]
    rows += [{'slot_id': f'qwen-{i}', 'slot_index': 1000+i, 'model_key': 'QWEN',
              'input_plus_output_tokens': 5_000_000} for i in range(5000)]
    old = {'status': 'closed', 'result': {'exact': True}}
    cursor = {'generation': {'api-0': old}, 'scores': {}, 'deliveries': {},
        'active_generation': [], 'active_grading': [], 'pending_controls': [], 'pending_scores': []}
    targets, state, allowed, excluded = prepare.selected_inventory(rows, cursor,
        {'excluded_old_scheduled_slot_ids': ['api-1']}, scheduled=['api-2'],
        consumed=['api-3'], requested=['api-4'], partial=['api-5'])
    assert len(targets) == 1000 and len(allowed) == 994
    assert state['generation']['api-0'] is old
    assert not set(allowed) & {f'api-{i}' for i in range(6)}
    assert all(state['generation'][f'api-{i}']['status'] == 'technical_unknown' for i in range(1, 6))
    assert excluded == ['api-1', 'api-2']


def test_private_runner_has_new_scope_and_old_runner_globals_unchanged():
    before = runner.prior._run.__globals__['scope']
    bound = runner.api_run_binding()
    assert bound.__globals__['scope'] is scope
    assert runner.prior._run.__globals__['scope'] is before
    assert 'proworksim.software_benchmark_episodes_v079' in bound.__code__.co_names
    assert scope.PRIMARY_CURSOR.name == 'cursor.json'
    assert 'software-benchmark-v080' in str(scope.PRIMARY_CURSOR)


def test_new_API_unit_is_user_only_64GiB_and_cannot_stop_Qwen():
    spec = {**launcher.fixed_spec(), 'ownership_token': 'f'*32}
    command = launcher.command(spec)
    assert command[:2] == ['systemd-run', '--user']
    assert '--property=MemoryMax=64G' in command
    assert '--property=CPUQuota=400%' in command
    assert scope.API_UNIT == 'proworksim-v079-api.service'
    assert not any('stop' == part or 'model-' in part for part in command)


def test_auxiliary_uses_real_headroom_and_releases_only_its_lease(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'require_allowed', lambda *a, **kw: {})
    monkeypatch.setattr(scope, 'CLAIM_FILE', tmp_path/'api/coordinator-capacity.json')
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'api')
    monkeypatch.setattr(scope, 'LEASE_FILE', tmp_path/'claims/active-v079.json')
    monkeypatch.setattr(scope, 'AUTH_FILE', tmp_path/'auth.json')
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path/'new')
    monkeypatch.setattr(scope, 'cpu_affinity', lambda: [1, 2, 3, 4])
    (tmp_path/'claims').mkdir()
    write_new(tmp_path/'auth.json', {'approved': True})
    # Existing maximum quotas exceed the old sum gate but real RAM is ample.
    write_new(tmp_path/'claims/active-else.json', {'reserved_memory_bytes': 1800*scope.GIB})
    monkeypatch.setattr(scope.original, '_budget', lambda *a, **kw: pytest.fail('Do not use quota-sum admission'))
    monkeypatch.setattr(scope.original, 'physical_capacity', lambda: {'passed': True, 'memory_available_bytes': 800*scope.GIB})
    claim = scope.reserve_api_coordinator()
    assert scope.load(claim)['reserved_memory_bytes'] == 64*scope.GIB
    assert scope.reserve_api_coordinator() == claim
    scope.release_api_coordinator(claim)
    assert not scope.LEASE_FILE.exists() and (tmp_path/'claims/active-else.json').exists()
    assert reference(tmp_path/'api/coordinator-capacity-released.json')


def test_failed_handoff_does_not_rollback_after_recorded_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff, 'OUT', tmp_path)
    monkeypatch.setattr(scope, 'require_allowed', lambda *a, **kw: {})
    (tmp_path/'signal-intent.json').write_text('{}')
    monkeypatch.setattr(handoff, 'stage_value', lambda: pytest.fail('No old-state adoption after signal'))
    assert handoff.rollback()['performed'] is False


def test_finalized_dead_handoff_requires_same_evidence_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(handoff, 'OUT', tmp_path)
    monkeypatch.setattr(scope, 'require_allowed', lambda *a, **kw: {})
    proof = write_new(tmp_path/'proof.json', {'trusted': True})
    write_new(tmp_path/'stopped.json', {'dead_owner_recovery': proof})
    assert handoff.accept_dead_owner(proof) == reference(tmp_path/'stopped.json')
    with pytest.raises(ValueError, match='Another'):
        handoff.accept_dead_owner({'different': True})


def test_Qwen_failure_does_not_block_API_with_unchanged_trusted_terminal_qualifications(tmp_path):
    ref = write_new(tmp_path/'qualified.json', {'instance_id': 'task', 'passed': True})
    expected = {'task': {'status': 'qualified', 'qualification': ref},
                'not-admitted': {'status': 'not_qualified', 'reason': 'Original gold control failed'}}
    snapshot = {'failure': {'kind': 'coordinator_error'}, 'qualifications': copy.deepcopy(expected)}
    assert require_unchanged_terminal(expected, snapshot)['Qwen_failure_is_not_API_failure']
    snapshot['qualifications']['task'] = {'status': 'not_qualified', 'reason': 'changed'}
    with pytest.raises(ValueError, match='changed'):
        require_unchanged_terminal(expected, snapshot)


def test_missing_or_changed_qualification_evidence_still_stops_API(tmp_path):
    path = tmp_path/'qualified.json'
    ref = write_new(path, {'instance_id': 'task', 'passed': True})
    expected = {'task': {'status': 'qualified', 'qualification': ref}}
    snapshot = {'failure': {'kind': 'coordinator_error'}, 'qualifications': copy.deepcopy(expected)}
    assert require_unchanged_terminal(expected, snapshot)
    path.write_text('{"instance_id":"task","passed":false}')
    with pytest.raises((ValueError, RuntimeError)):
        require_unchanged_terminal(expected, snapshot)
    with pytest.raises(ValueError):
        require_unchanged_terminal(expected, {'qualifications': {}})
