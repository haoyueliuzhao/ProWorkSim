"""Fixed queue and diagnostic boundaries, using no runtime resources."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new


@pytest.fixture
def coordinator(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'tools/run_ref_capability_v062.py'
    spec = importlib.util.spec_from_file_location('coordinator_v062_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(module, 'RUN_ROOT', tmp_path / 'coordinator')
    monkeypatch.setattr(module.policy, 'sources', lambda: [{'synthetic_current_source': 1}])
    return module


def quiet_result(slot, **updates):
    return {'slot_id': slot, 'status': 'closed', 'failure_scope': 'local', 'batch_stop_required': False,
            'quiescence': {'quiescent': True, 'cleanup_errors': []},
            'ledger': {'known_actual_tokens': 100, 'complete_actual_tokens': 100,
                       'inflight': None, 'uncertain_reserved_tokens': 0}, **updates}


def fixtures(coordinator, tmp_path, *, ready=True):
    calls = {'start': 0, 'stop': 0, 'generation': [], 'score': []}
    resident = {'root': 'synthetic-owned-resident'}
    def start():
        calls['start'] += 1
        return [resident] if ready else []
    def stop():
        calls['stop'] += 1
        return [{'owned_unit_stopped': True}]
    runtime = SimpleNamespace(start_residents=start, ready_residents=lambda: [resident] if ready else [], stop_residents=stop)
    def prepare_score(ref, lane):
        body = coordinator.load(ref)
        return write_new(tmp_path / (body['slot_id'] + '-request.json'),
                         {'slot_id': body['slot_id'], 'instance_id': 'task', 'cpuset_cpus': str(lane)})
    def grade(ref, stop_event=None):
        calls['score'].append(coordinator.load(ref)['slot_id'])
        return {'status': 'complete'}
    grading = SimpleNamespace(prepare_score=prepare_score, run_request=grade,
                              trustworthy_cleanup=lambda ref: True, selected_cpus=str)
    progress, events = [], []
    def sink(kind, **values):
        events.append({'kind': kind, **values})
    kwargs = {'controls': [], 'qualifications': {'task': {'status': 'qualified'}}, 'grading': grading,
              'runtime': runtime, 'progress_sink': progress.append, 'event_sink': sink}
    return calls, kwargs, progress, events


def test_main_then_repeat_keeps_clean_local_failure_and_never_resamples(coordinator, tmp_path):
    rows = [{'slot_id': f'slot-{index}', 'instance_id': 'task', 'replicate': int(index == 2)} for index in range(3)]
    calls, kwargs, progress, events = fixtures(coordinator, tmp_path)
    def episode(row, resident, stop_event=None):
        calls['generation'].append(row['slot_id'])
        result = quiet_result(row['slot_id'])
        if row['slot_id'] == 'slot-0':
            result.update(status='technical_unknown', failure_scope='local')
        return write_new(tmp_path / (row['slot_id'] + '-result.json'), result)
    result = coordinator.execute_queue(rows, run_episode=episode, **kwargs)
    assert result['failure'] is None and result['unentered_generation'] == []
    assert calls['generation'] == ['slot-0', 'slot-1', 'slot-2']
    assert sorted(calls['score']) == ['slot-1', 'slot-2'] and calls['stop'] == 1
    repeat = next(index for index, event in enumerate(events) if event['kind'] == 'generation_entered' and event['slot_id'] == 'slot-2')
    assert {event['slot_id'] for event in events[:repeat] if event['kind'] == 'generation_finished'} == {'slot-0', 'slot-1'}
    assert all(row['active_generation'] <= 2 and row['active_grading'] <= 2 for row in progress)


def test_accounting_or_cleanup_failure_stops_new_rows_but_drains_inflight(coordinator, tmp_path):
    rows = [{'slot_id': f'slot-{index}', 'instance_id': 'task', 'replicate': 0} for index in range(3)]
    calls, kwargs, _, _ = fixtures(coordinator, tmp_path)
    def episode(row, resident, stop_event=None):
        calls['generation'].append(row['slot_id'])
        result = quiet_result(row['slot_id'])
        result['ledger']['complete_actual_tokens'] = None
        return write_new(tmp_path / (row['slot_id'] + '-result.json'), result)
    result = coordinator.execute_queue(rows, run_episode=episode, **kwargs)
    assert result['failure']['kind'] == 'unresolved_generation_accounting'
    assert result['unentered_generation'] == ['slot-2'] and calls['stop'] == 1
    assert calls['score'] == [] and set(result['generation']) == {'slot-0', 'slot-1'}


def test_both_closed_residents_stop_without_polling_forever(coordinator, tmp_path):
    for index in range(2):
        folder = tmp_path / 'residents' / f'model-{index}'
        folder.mkdir(parents=True)
        write_new(folder / 'spec.json', {})
        write_new(folder / 'closed.json', {})
    calls, kwargs, _, _ = fixtures(coordinator, tmp_path, ready=False)
    row = {'slot_id': 'never-entered', 'instance_id': 'task', 'replicate': 0}
    result = coordinator.execute_queue([row], run_episode=lambda *args, **kwargs: pytest.fail('No resident'), **kwargs)
    assert result['failure']['kind'] == 'model_admission_exhausted'
    assert result['unentered_generation'] == ['never-entered'] and calls['start'] == calls['stop'] == 1


def test_unconfirmed_model_closure_is_retained(coordinator, tmp_path):
    _, kwargs, _, _ = fixtures(coordinator, tmp_path)
    kwargs['runtime'].stop_residents = lambda: [{'owned_unit_stopped': False, 'error': 'ownership unknown'}]
    result = coordinator.execute_queue([], run_episode=lambda *args, **kwargs: None, **kwargs)
    assert result['failure']['kind'] == 'resident_cleanup_unconfirmed'
    assert result['resident_closure'][0]['owned_unit_stopped'] is False


def test_no_second_batch_entry_even_with_valid_new_authorization(coordinator, tmp_path, monkeypatch):
    coordinator.RUN_ROOT.mkdir()
    write_new(coordinator.RUN_ROOT / 'execution-started.json', {'entered': True})
    monkeypatch.setattr(coordinator.policy, 'require_v062_allowed', lambda *args: {})
    monkeypatch.setattr(coordinator, 'coordinator_limits', lambda: {})
    monkeypatch.setattr(coordinator, 'prepare', lambda: pytest.fail('Cannot reprepare an entered batch'))
    with pytest.raises(ValueError, match='not automatically replayed'):
        coordinator.run()


def test_diagnostic_qualification_requires_both_current_clean_zero_model_protocols(coordinator, tmp_path):
    for index, arm in enumerate(('BASE', 'FIX')):
        result = write_new(tmp_path / f'result-{arm}.json', quiet_result(arm, passed=True, model_calls=0))
        directory = tmp_path / 'diagnostic-qualifications' / arm
        directory.mkdir(parents=True)
        write_new(directory / f'{index + 1}.json',
                  {'version': coordinator.VERSION, 'arm': arm, 'sources': coordinator.policy.sources(), 'result': result})
        if index == 0:
            with pytest.raises(ValueError, match='exactly one'):
                coordinator.diagnostic_qualifications()
    assert set(coordinator.diagnostic_qualifications()) == {'BASE', 'FIX'}
    for index in (1, 2, 3, 4):
        with pytest.raises(ValueError, match='already passed'):
            coordinator.diagnostic_admission(index)


def test_reserved_diagnostic_requires_failed_clean_prior_and_revised_sources(coordinator, tmp_path):
    attempts = tmp_path / 'diagnostic-attempts'
    attempts.mkdir()
    failed = write_new(tmp_path / 'failed.json', quiet_result('BASE', passed=False, model_calls=0))
    write_new(attempts / '1.json', {'sources': [{'old_source': 0}], 'result': failed})
    assert coordinator.diagnostic_admission(3) == 'BASE'
    write_new(attempts / '3-intent.json', {'entered': True})
    with pytest.raises(ValueError, match='cannot be retried'):
        coordinator.diagnostic_admission(3)
    with pytest.raises(FileNotFoundError):
        coordinator.diagnostic_admission(4)


def test_stale_success_can_use_reserved_identity_without_overwriting_old_qualification(coordinator, tmp_path):
    attempts = tmp_path / 'diagnostic-attempts'
    attempts.mkdir()
    passed = write_new(tmp_path / 'old-pass.json', quiet_result('BASE', passed=True, model_calls=0))
    old_record = {'version': coordinator.VERSION, 'arm': 'BASE', 'sources': [{'old_source': 0}], 'result': passed}
    write_new(attempts / '1.json', old_record)
    directory = tmp_path / 'diagnostic-qualifications/BASE'
    directory.mkdir(parents=True)
    old_reference = write_new(directory / '1.json', old_record)
    assert coordinator.diagnostic_admission(3) == 'BASE'
    assert coordinator.load(old_reference) == old_record
    with pytest.raises(ValueError, match='exactly one'):
        coordinator.diagnostic_qualifications()


def test_invalid_or_unclassified_failure_cannot_be_declared_local(coordinator):
    result = quiet_result('synthetic', status='technical_unknown')
    assert coordinator.generation_stop_reason(result) is None
    result.pop('failure_scope')
    assert coordinator.generation_stop_reason(result) == 'unclassified_generation_failure'
    result['quiescence']['quiescent'] = False
    assert coordinator.generation_stop_reason(result) == 'unproven_generation_cleanup'


def test_unexpected_coordinator_error_signals_tasks_before_join(coordinator):
    import threading
    stop = threading.Event()
    with pytest.raises(RuntimeError, match='fixture interruption'):
        with coordinator._executor_pair(stop) as (generation, _):
            future = generation.submit(stop.wait, 2)
            raise RuntimeError('fixture interruption')
    assert future.result() is True


def test_disk_floor_prevents_resource_entry_and_retains_measured_failure(coordinator, tmp_path):
    calls, kwargs, _, _ = fixtures(coordinator, tmp_path)
    result = coordinator.execute_queue([], run_episode=lambda *args, **kwargs: pytest.fail('No admission'),
        disk_check=lambda: {'passed': False, 'free_bytes': coordinator.DISK_FLOOR_BYTES - 1}, **kwargs)
    assert result['failure']['kind'] == 'disk_free_space_floor'
    assert calls['start'] == 0 and calls['stop'] == 1


def test_different_filesystems_are_checked_individually(coordinator, tmp_path, monkeypatch):
    root, data = tmp_path / 'workspace', tmp_path / 'data'
    root.mkdir()
    data.mkdir()
    source = write_new(tmp_path / 'daemon.json', {'data-root': str(data)})
    original_stat = Path.stat
    def stat(path, *args, **kwargs):
        if path == root:
            return SimpleNamespace(st_dev=1)
        if path == data:
            return SimpleNamespace(st_dev=2)
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    observed = []
    def usage(path):
        observed.append(str(path))
        return SimpleNamespace(free=coordinator.DISK_FLOOR_BYTES + (1 if str(path) == str(root) else -1))
    monkeypatch.setattr(coordinator.shutil, 'disk_usage', usage)
    boundary = {'daemon_configuration': source, 'paths_and_devices': {str(root): 1, str(data): 2},
                'minimum_free_bytes': coordinator.DISK_FLOOR_BYTES, 'disk_hard_quota': False}
    result = coordinator.check_disk_boundary(boundary)
    assert observed == [str(root), str(data)] and result['passed'] is False
    assert len(result['filesystems']) == 2 and result['disk_hard_quota'] is False
