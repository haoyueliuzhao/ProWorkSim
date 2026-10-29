import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]


def tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


bootstrap = tool('bootstrap_v076_control', 'adaptive_bootstrap_v076.py')
launcher = tool('bootstrap_v076_launcher_control', 'launch_adaptive_v076.py')


class ClockStop:
    def __init__(self):
        self.now = 0
    def is_set(self):
        return False
    def wait(self, seconds):
        self.now += seconds


def observation(unix, ready=True):
    return {'ready': ready, 'reasons': [], 'snapshots': {
        role: {'progress': {'unix': unix}} for role in ('primary', 'api')}}


def test_boundary_requires_post_gate_snapshots_and_two_separated_empty_samples():
    timer = ClockStop()
    samples = iter([observation(9), observation(11), observation(12)])
    seen = []
    result = bootstrap.wait_boundary(observe=lambda: next(samples), gate_unix=10,
        stop=timer, report=seen.append, clock=lambda: timer.now, maximum_wait=100)
    assert result['snapshots']['api']['progress']['unix'] == 12
    assert timer.now == 18
    assert [entry['ready'] for entry in seen] == [False, True, True]


def test_nonquiet_reappearance_restarts_confirmation_and_timeout_is_bounded():
    timer = ClockStop()
    samples = iter([observation(11), observation(12, False), observation(13), observation(14)])
    bootstrap.wait_boundary(observe=lambda: next(samples), gate_unix=10,
        stop=timer, report=lambda x: None, clock=lambda: timer.now, maximum_wait=100)
    assert timer.now == 21
    timer = ClockStop()
    with pytest.raises(TimeoutError):
        bootstrap.wait_boundary(observe=lambda: observation(9), gate_unix=10,
            stop=timer, report=lambda x: None, clock=lambda: timer.now, maximum_wait=20)
    assert timer.now == 20


def test_recorded_signal_disables_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(scope, 'HANDOFF_ROOT', tmp_path)
    (tmp_path / 'primary-signal-intent.json').write_text('{}')
    monkeypatch.setattr(bootstrap.handoff, 'rollback_gate', lambda **kw: pytest.fail('No rollback after a signal'))
    assert bootstrap.pre_signal_rollback(guard=lambda x: {})['performed'] is False


def test_bootstrap_reserves_under_original_budget_and_cannot_replay_released_identity(tmp_path, monkeypatch):
    directory = tmp_path / 'claims'
    directory.mkdir()
    root = tmp_path / 'primary'
    root.mkdir()
    auth = tmp_path / 'auth.json'
    auth.write_text('{}')
    monkeypatch.setattr(scope, 'AUTH_FILE', auth)
    monkeypatch.setattr(scope, 'PRIMARY_ROOT', root)
    monkeypatch.setattr(scope, 'BOOTSTRAP_CLAIM', root / 'bootstrap-capacity.json')
    monkeypatch.setattr(scope, 'BOOTSTRAP_LEASE', directory / 'active-bootstrap.json')
    monkeypatch.setattr(scope, 'require_allowed', lambda *a, **kw: {})
    old = {'spec': {'role': 'model'}, 'reserved_cpu': 12, 'reserved_memory_bytes': 96*scope.GIB}
    (directory / 'active-model.json').write_text(json.dumps(old))
    budgets = []
    monkeypatch.setattr(scope.original, '_budget', lambda active, cpu, memory: budgets.append((active,cpu,memory)) or {})
    claim = scope.reserve_primary_bootstrap()
    assert budgets == [([old], 4, 16*scope.GIB)]
    assert scope.reserve_primary_bootstrap() == claim and len(budgets) == 1
    with pytest.raises(ValueError, match='needed until'):
        scope.release_primary_bootstrap(claim)
    scope.release_primary_bootstrap(claim, aborted_before_generation=True)
    assert not scope.BOOTSTRAP_LEASE.exists()
    assert json.loads((directory / 'active-model.json').read_text()) == old
    with pytest.raises(ValueError, match='cannot be restarted'):
        scope.reserve_primary_bootstrap()


def test_primary_bootstrap_launcher_does_not_require_post_handoff_plan_or_api(tmp_path, monkeypatch):
    primary, handoff = tmp_path / 'primary', tmp_path / 'handoff'
    primary.mkdir()
    handoff.mkdir()
    (handoff / 'gate.json').write_text('{}')
    (primary / 'coordinator-unit.json').write_text('{"role":"primary"}')
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(scope, 'PRIMARY_ROOT', primary)
    monkeypatch.setattr(scope, 'HANDOFF_ROOT', handoff)
    auth = tmp_path / 'auth.json'
    auth.write_text('{}')
    monkeypatch.setattr(scope, 'AUTH_FILE', auth)
    calls = []
    monkeypatch.setattr(launcher, 'ordinary_user', lambda: None)
    monkeypatch.setattr(bootstrap.parent, 'require_qualified', lambda: calls.append('parent'))
    monkeypatch.setattr(scope, 'require_allowed', lambda op: calls.append(op))
    monkeypatch.setattr(scope, 'reserve_primary_bootstrap', lambda: {'temporary': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: pytest.fail('No API before handoff'))
    monkeypatch.setattr(launcher, 'validate_spec', lambda value: 'primary')
    monkeypatch.setattr(launcher, 'inactive', lambda role: {'inactive': True})
    monkeypatch.setattr(launcher, 'command', lambda spec: ['owned-primary'])
    monkeypatch.setattr(launcher, 'user_manager_environment', lambda: {})
    monkeypatch.setattr(launcher.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0,stdout='',stderr=''))
    result = launcher.launch('primary')
    assert calls == ['parent', 'v076.handoff']
    assert result['launched']['primary']['natural_handoff_bootstrap'] is True
    with pytest.raises(ValueError, match='only the bounded primary'):
        launcher.launch('all')


def test_auto_api_starter_launches_only_after_new_primary_cursor_and_never_retries(tmp_path, monkeypatch):
    cursor = tmp_path / 'cursor.json'
    monkeypatch.setattr(scope, 'PRIMARY_CURSOR', cursor)
    cursor.write_text('{"phase":"starting","qualifications":{},"failure":null}')
    reports, calls = [], []
    monkeypatch.setattr(bootstrap, 'snapshot', lambda name, value: reports.append(value))
    def launch(role):
        calls.append(role)
        raise RuntimeError('simulated ambiguous start')
    monitor = bootstrap.AutoAPILauncher(launcher=SimpleNamespace(launch=launch))
    monitor.start()
    monitor.thread.join(timeout=1)
    monitor.close()
    assert calls == ['api']
    assert reports[-1]['status'] == 'launch_requires_review'
    assert reports[-1]['automatic_retry'] is False


def test_wait_failure_rolls_back_only_before_signal_and_releases_temporary_capacity(tmp_path, monkeypatch):
    primary, handoff = tmp_path / 'primary', tmp_path / 'handoff'
    primary.mkdir()
    handoff.mkdir()
    write_new(handoff / 'gate.json', {'unix': 10})
    auth = tmp_path / 'auth.json'
    auth.write_text('{}')
    lease = tmp_path / 'lease.json'
    lease.write_text('{}')
    for key, value in [('PRIMARY_ROOT',primary),('HANDOFF_ROOT',handoff),('BATCH_ROOT',tmp_path),
                       ('AUTH_FILE',auth),('BOOTSTRAP_LEASE',lease)]:
        monkeypatch.setattr(scope,key,value)
    monkeypatch.setattr(scope,'require_allowed',lambda *a,**kw:{})
    monkeypatch.setattr(scope,'verify_host_limits',lambda role:{'bounded':True})
    monkeypatch.setattr(bootstrap.parent,'require_qualified',lambda: {})
    monkeypatch.setattr(scope,'reserve_primary_bootstrap',lambda: reference(lease))
    monkeypatch.setattr(bootstrap,'wait_boundary',lambda **kw: (_ for _ in ()).throw(TimeoutError('fixture')))
    actions=[]
    monkeypatch.setattr(bootstrap,'pre_signal_rollback',lambda **kw: actions.append('rollback') or {'performed':True})
    monkeypatch.setattr(scope,'release_primary_bootstrap',lambda ref,**kw: actions.append(kw) or {})
    with pytest.raises(TimeoutError,match='fixture'):
        bootstrap.wait_and_prepare()
    assert actions == ['rollback', {'aborted_before_generation': True}]
    assert json.loads((primary/'bootstrap-failure.json').read_text())['API_parent_retained'] is True
