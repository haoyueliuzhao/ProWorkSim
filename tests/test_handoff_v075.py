"""CPU-only controls for admission withdrawal and quiet coordinator handover."""
from __future__ import annotations

import hashlib
import json

import pytest

from proworksim import software_benchmark_handoff_v075 as handoff
from proworksim.software_benchmark_candidates_v054 import reference


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return reference(path)


def quiet(role='primary'):
    progress = {'unix': 100., 'failure': None, 'phase': 'running', 'active_generation': 0,
        'active_grading': 0, 'pending_scores': 0, 'pending_controls': 0}
    if role == 'api':
        progress.update(phase='waiting', actual_generation_futures=0, effective_generation_limit=0,
            capacity_wait_reason='invalid_concurrency_control')
    cursor = {'failure': None, 'active_generation': [], 'active_grading': [],
        'pending_scores': [], 'pending_controls': []}
    return progress, cursor


def test_primary_requires_all_scoring_complete_but_model_leases_are_preserved():
    progress, cursor = quiet()
    models = [{'spec': {'role': 'model'}}, {'spec': {'role': 'auxiliary_coordinator'}}]
    assert handoff.quiet_reasons(progress, cursor, models, role='primary', now=101) == []
    cursor['pending_scores'] = ['unconsumed score']
    assert 'primary_grading_not_naturally_complete' in handoff.quiet_reasons(
        progress, cursor, models, role='primary', now=101)
    cursor['pending_scores'] = []
    assert 'owned_non_model_resources_still_active' in handoff.quiet_reasons(
        progress, cursor, models + [{'spec': {'role': 'actor'}}], role='primary', now=101)


def test_api_carries_unstarted_scores_but_requires_its_completed_grader_proof(tmp_path):
    progress, cursor = quiet('api')
    folder = tmp_path / 'score'
    request = dump(folder / 'request.json', {'directory': str(folder)})
    cursor.update(pending_scores=['unconsumed score'], pending_controls=['unconsumed control'],
        active_grading=[request])
    assert 'grader_still_running_or_cleanup_unproven' in handoff.quiet_reasons(
        progress, cursor, [], role='api', now=101)
    dump(folder / 'completion.json', {'status': 'closed'})
    dump(folder / 'quiescence.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    assert handoff.quiet_reasons(progress, cursor, [], role='api', now=101) == []
    progress['phase'] = 'running'
    assert 'api_admission_pause_not_observed' in handoff.quiet_reasons(progress, cursor, [], role='api', now=101)


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    out, models, roots = tmp_path / 'handoff', tmp_path / 'residents', {}
    out.mkdir()
    models.mkdir()
    (models / 'allocation.lock').touch()
    residents = []
    for index in (1, 3, 4, 5):
        folder = models / f'model-{index}'
        ready = dump(folder / 'ready.json', {'index': index, 'stable': True})
        residents.append({'index': index, 'original': ready,
            'hidden_path': str(folder / 'ready.v076-handoff.json')})
    identities, units = {}, {}
    for number, role in enumerate(('api', 'primary'), 100):
        folder = tmp_path / role
        roots[role] = folder
        spec = dump(folder / 'unit.json', {'role': role})
        identities[role] = {'pid': number, 'start_ticks': 1000 + number, 'uid': 1, 'cmdline_sha256': role}
        units[role] = {'specification': spec, 'process': identities[role]}
        progress, cursor = quiet(role)
        dump(folder / 'cursor.json', cursor)
        dump(folder / 'progress.json', progress)
    original_control = dump(out / 'original-api-control.json', {'desired': 32})
    control = roots['api'] / 'concurrency-control.json'
    control.write_bytes((out / 'original-api-control.json').read_bytes())
    value = {'coordinators': units, 'residents': residents, 'API_control': original_control}
    monkeypatch.setattr(handoff, 'OUT', out)
    monkeypatch.setattr(handoff, 'MODEL_ROOT', models)
    monkeypatch.setattr(handoff, 'OLD_ROOTS', roots)
    monkeypatch.setattr(handoff, 'API_CONTROL', control)
    monkeypatch.setattr(handoff, 'authorize', lambda guard: {'approved': True})
    monkeypatch.setattr(handoff, 'stage_value', lambda: value)
    monkeypatch.setattr(handoff, 'show', lambda role: {'role': role})
    monkeypatch.setattr(handoff, 'validate_unit', lambda role, spec, props: identities[role])
    monkeypatch.setattr(handoff, 'process_identity', lambda pid: next(v for v in identities.values() if v['pid'] == pid))
    dump(out / 'stage.json', {'fixture': True})
    return {'out': out, 'value': value, 'roots': roots, 'identities': identities, 'control': control}


def test_gate_only_hides_discovery_and_rollback_restores_original_bytes(prepared):
    value = prepared['value']
    handoff.gate(guard=None)
    assert handoff.gate_intact(value)
    assert json.loads(prepared['control'].read_bytes())['desired'] == 0
    for item in value['residents']:
        hidden = handoff.Path(item['hidden_path'])
        assert hashlib.sha256(hidden.read_bytes()).hexdigest() == item['original']['sha256']
    handoff.rollback_gate(guard=None)
    for item in value['residents']:
        assert reference(item['original']['path']) == item['original']
    assert json.loads(prepared['control'].read_bytes()) == {'desired': 32}


def test_rollback_rejects_any_prior_signal_and_restore_requires_stopped_units(prepared, monkeypatch):
    handoff.gate(guard=None)
    dump(prepared['out'] / 'api-signal-intent.json', {'signal': 'SIGKILL'})
    with pytest.raises(ValueError, match='signalled'):
        handoff.rollback_gate(guard=None)
    with pytest.raises(ValueError, match='reopen discovery'):
        handoff.restore_ready(guard=None)
    dump(prepared['out'] / 'coordinators-stopped.json', {})
    with pytest.raises(ValueError, match='still active'):
        handoff.restore_ready(guard=None)
    monkeypatch.setattr(handoff, 'validate_unit', lambda *args: None)
    handoff.restore_ready(guard=None)
    assert all(handoff.Path(item['original']['path']).exists() for item in prepared['value']['residents'])


def ready_proof(prepared):
    snapshots = {}
    for role, folder in prepared['roots'].items():
        cursor, progress = (folder / 'cursor.json').read_bytes(), (folder / 'progress.json').read_bytes()
        snapshots[role] = {'cursor_bytes': cursor.decode(), 'progress_bytes': progress.decode(),
            'cursor_sha256': hashlib.sha256(cursor).hexdigest()}
    return {'ready': True, 'reasons': [], 'snapshots': snapshots}


def test_inflight_work_prevents_any_signal(prepared, monkeypatch):
    monkeypatch.setattr(handoff, 'observe', lambda **kwargs: {'ready': False, 'reasons': ['active_actor']})
    monkeypatch.setattr(handoff, 'open_process_handle', lambda *_: pytest.fail('must not signal'))
    assert handoff.stop_quiescent(guard=None) == {'status': 'waiting', 'reasons': ['active_actor']}


def test_child_process_prevents_signal_even_with_zero_claims(prepared, monkeypatch):
    handoff.gate(guard=None)
    monkeypatch.setattr(handoff, 'observe', lambda **kwargs: ready_proof(prepared))
    monkeypatch.setattr(handoff, 'unit_members', lambda properties: [100, 999])
    monkeypatch.setattr(handoff, 'open_process_handle', lambda *_: pytest.fail('child must block signalling'))
    with pytest.raises(ValueError, match='child process'):
        handoff.stop_quiescent(guard=None)
    assert not list(prepared['out'].glob('*-signal-intent.json'))


def test_quiet_stop_pins_only_two_coordinator_pids_and_preserves_markers(prepared, monkeypatch):
    handoff.gate(guard=None)
    monkeypatch.setattr(handoff, 'observe', lambda **kwargs: ready_proof(prepared))
    monkeypatch.setattr(handoff, 'unit_members', lambda properties: [prepared['identities'][properties['role']]['pid']])
    opened, signalled, closed = [], [], []
    monkeypatch.setattr(handoff, 'open_process_handle', lambda pid: opened.append(pid) or pid + 1000)
    monkeypatch.setattr(handoff.signal, 'pidfd_send_signal', lambda fd, sig: signalled.append((fd, sig)))
    monkeypatch.setattr(handoff.os, 'close', lambda fd: closed.append(fd))
    result = handoff.stop_quiescent(guard=None)
    assert opened == [100, 101]
    assert signalled == [(1100, handoff.signal.SIGKILL), (1101, handoff.signal.SIGKILL)]
    assert closed == [1100, 1101]
    assert handoff.gate_intact(prepared['value'])
    assert json.loads(handoff.Path(result['path']).read_bytes())['resident_units_stopped'] is False
    assert all((prepared['out'] / 'administrative-boundary' / f'{role}-cursor.json').exists()
        for role in ('api', 'primary'))
    # No extra signal when the completed handoff is queried again.
    assert handoff.stop_quiescent(guard=None) == result
    assert len(signalled) == 2
