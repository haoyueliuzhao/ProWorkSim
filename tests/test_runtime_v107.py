"""Execute the real coordinator queue with scripted I/O; no external operations."""
from __future__ import annotations

import importlib.util
from types import SimpleNamespace

from proworksim import software_benchmark_scope_v107 as scope
from proworksim import software_benchmark_scope_v106 as prior
from proworksim import software_benchmark_host_api_v107 as host
from proworksim import software_benchmark_grading_v106 as grading_module
from proworksim.software_benchmark_episode_v107 import build_episode
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_actual_manager_enters_generation_async_score_and_cleanup(tmp_path, monkeypatch):
    manager = load_file(scope.ROOT/'tools/run_nonthinking_interface_v107.py', 'manager_v107_control')
    original = load_file(scope.ROOT/'tests/test_async_queue_v082.py', 'original_queue_fixture_v107')
    plan = scope.load(reference(scope.PLAN_FILE))
    rows = plan['rows'][:4]
    fixture = original.Fixture(tmp_path)
    fixture.separate_delivery = True
    controls = {'qualifications': {row['instance_id']: {'status': 'qualified'} for row in rows}, 'controls': []}
    fixture.prepare_environment_qualifications = lambda: controls
    api = original.API()
    api.initialize_for_run = api.logical_resident
    api.preparation_usage = lambda: {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
    api.usage_for_slot = lambda row: {'calls': ([{'call_id': row['slot_id']+':0001', 'purpose': 'agent',
        'prompt_tokens': 8, 'completion_tokens': 2, 'reasoning_tokens': 0,
        'prompt_cache_hit_tokens': 0, 'prompt_cache_miss_tokens': 8, 'accounted_cost_cny': '0'}]
        if row['slot_id'] in fixture.entered else []), 'unresolved_calls': [], 'usage_capture_complete': True}
    plan_ref = write_new(tmp_path/'plan.json', {**plan, 'rows': rows})
    recovery = write_new(tmp_path/'recovery.json', {'scripted': True})
    auth = write_new(tmp_path/'auth.json', {'preparation_recovery': recovery})
    monkeypatch.setattr(scope, 'PLAN_FILE', scope.Path(plan_ref['path']))
    monkeypatch.setattr(scope, 'AUTH_FILE', scope.Path(auth['path']))
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'manager')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: {'preparation_recovery': recovery})
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'scripted_cpu_control': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'scripted': True})
    released = []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    monkeypatch.setattr(manager, 'validate_preparation_recovery', lambda value: value)
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api)
    monkeypatch.setattr(manager, 'build_episode', lambda: SimpleNamespace(run_episode=fixture.episode))
    monkeypatch.setattr(grading_module, 'factory', lambda **_kw: fixture)
    result = manager.run()
    assert result['failure'] is None
    assert len(result['generation']) == len(result['scores']) == 4
    assert len(result['deliveries']) == 2
    assert all(value == 1 for value in fixture.calls.values())
    assert sum(fixture.score_calls.values()) == 6
    assert len(released) == 1 and api.cancelled
    assert (scope.API_ROOT/'initial-pair-api-health.json').is_file()
    assert (scope.API_ROOT/'run-summary.json').is_file()


def test_contextmanager_uses_its_real_contextlib_globals():
    manager = load_file(scope.ROOT/'tools/run_nonthinking_interface_v107.py', 'manager_v107_binding_control')
    queue = manager.queue_module()
    assert queue.execute_queue.__globals__['executors'] is manager.queue_base.executors
    assert queue.executors.__globals__['__name__'] == 'contextlib'
    assert scope.API_UNIT == prior.API_UNIT and scope.LEDGER_FILE == prior.LEDGER_FILE
    assert scope.API_ROOT != prior.API_ROOT and scope.COORDINATOR_ROOT == prior.COORDINATOR_ROOT
    assert host.QUALIFICATION == scope.BATCH_ROOT/'api-qualification/result.json'
    for fn in (host.DeepSeekRuntime.initialize_for_run, host.DeepSeekRuntime.transport_factory,
               host.DeepSeekRuntime.usage_for_slot):
        assert fn.__globals__['scope'] is scope
    def guard(*_a, **_kw):
        return {'plan': reference(scope.PLAN_FILE)}
    episode = build_episode(guard=guard)
    assert episode.OwnedActorPair.__init__.__globals__['policy'].AUTHORIZATION_FILE == scope.AUTH_FILE
    assert episode.runtime.__name__.endswith('_v106')


def test_existing_api_qualification_returns_without_any_new_request(monkeypatch):
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: {
        'reused_API_qualification': reference(host.QUALIFICATION)})
    class ForbiddenClient:
        def __getattr__(self, name):
            raise AssertionError('The already successful neutral check must not call '+name)
    result = host.qualify(ForbiddenClient(), lambda _wire: (_ for _ in ()).throw(AssertionError('No recount')))
    assert result['passed'] is True and result['model_calls'] == 2
    assert result['actual_known_input_output_tokens'] == 746
