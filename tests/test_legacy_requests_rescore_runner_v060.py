import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_batch_paths_are_single_use_and_controls_keep_two_tasks():
    runner = module('repair_legacy_requests_rescore_v060')
    admission = module('check_legacy_requests_environment_v060')
    assert runner.BATCH_ROOT.name == 'original-ca-rescore-r1-20261025'
    assert runner.DEFAULT_ROOT == runner.BATCH_ROOT / 'requests-rescore'
    assert admission.DEFAULT_ROOT == runner.BATCH_ROOT / 'environment-admission'
    assert set(admission.TASKS) == {'psf__requests-1766', 'psf__requests-1921'}
    with pytest.raises(ValueError, match='fresh independent'):
        admission.prepare(runner.BATCH_ROOT / 'another-control-run')
    with pytest.raises(ValueError, match='independent'):
        runner.prepare(runner.BATCH_ROOT / 'another-score-run', None)


def test_original_launcher_has_no_mount_or_namespace_path():
    runner = module('repair_legacy_requests_rescore_v060')
    command = runner.scorer_command('/tmp/frozen-request.json')
    assert command[2] == str(ROOT / 'tools/run_offline_scorer_v058.py')
    assert command[3:5] == ['-m', 'proworksim.software_benchmark_scorer_v060']
    assert not any('run_benchmark_runtime' in arg or 'enter_benchmark_runtime' in arg for arg in command)


def test_unqualified_task_never_dispatches(monkeypatch):
    runner = module('repair_legacy_requests_rescore_v060')
    monkeypatch.setattr(runner, 'require_v060_rescore_allowed', lambda *a, **k: pytest.fail('must not dispatch'))
    result = runner.run_one({}, {'slot_id': 'fixed-slot', 'admission_status': 'not_qualified', 'admission_reason': 'gold failed'})
    assert result == {'slot_id': 'fixed-slot', 'status': 'not_qualified', 'reason': 'gold failed'}


def test_consumed_started_marker_is_not_replayed(monkeypatch, tmp_path):
    runner = module('repair_legacy_requests_rescore_v060')
    monkeypatch.setattr(runner, 'require_v060_rescore_allowed', lambda *a, **k: {})
    (tmp_path / 'started.json').write_text('{}')
    monkeypatch.setattr(runner.subprocess, 'Popen', lambda *a, **k: pytest.fail('no automatic container replay'))
    result = runner.run_one({}, {'slot_id': 'fixed-slot', 'instance_id': 'psf__requests-1766',
                               'admission_status': 'qualified', 'directory': str(tmp_path)})
    assert result['status'] == 'deferred'


def test_source_plan_rejects_different_cardinality():
    runner = module('repair_legacy_requests_rescore_v060')
    with pytest.raises(ValueError, match='two-task'):
        runner.validate_plan({'version': runner.VERSION, 'root': str(runner.DEFAULT_ROOT), 'rows': [{}] * 16,
                              'concurrency': 2, 'model_calls': 0})
