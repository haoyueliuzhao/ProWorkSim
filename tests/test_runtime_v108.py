"""The real continuation queue preserves history and runs each unused slot once."""
from __future__ import annotations

import importlib.util
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_scope_v108 as scope
from proworksim import software_benchmark_resume_inventory_v108 as inventory_module
from proworksim import software_benchmark_host_api_v108 as host
from proworksim import software_benchmark_grading_v108 as grading_module
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def load_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_original_43_results_and_57_exact_unused_rows_are_bound():
    ref = reference(inventory_module.INVENTORY)
    value = scope.load(ref)
    plan = scope.load(reference(scope.PLAN_FILE))
    old = inventory_module.validate(value, plan, check_unconsumed=True)
    assert len(old['generation']) == 43 and len(value['remaining_rows']) == 57
    assert min(r['slot_index'] for r in value['remaining_rows']) == 7043
    assert set(old['generation']).isdisjoint(r['slot_id'] for r in value['remaining_rows'])
    with pytest.raises(ValueError, match='preserve exactly'):
        inventory_module.validate({**value, 'remaining_count': 58}, plan)
    altered = {**value, 'remaining_rows': [plan['rows'][0], *value['remaining_rows'][1:]]}
    with pytest.raises(ValueError, match='replayed'):
        inventory_module.validate(altered, plan)


def test_actual_manager_imports_history_without_replaying_models_or_scores(tmp_path, monkeypatch):
    manager = load_file(scope.ROOT/'tools/run_nonthinking_interface_v108.py', 'manager_v108_cpu')
    original = load_file(scope.ROOT/'tests/test_async_queue_v082.py', 'queue_fixture_v108_cpu')
    plan = scope.load(reference(scope.PLAN_FILE))
    rows = plan['rows'][:4]
    fixture = original.Fixture(tmp_path)
    fixture.separate_delivery = True
    fixture.prepare_environment_qualifications = lambda: {
        'qualifications': {r['instance_id']: {'status': 'qualified'} for r in rows}, 'controls': []}
    api = original.API()
    api.initialize_for_run = api.logical_resident
    api.preparation_usage = lambda: {'calls': [], 'unresolved_calls': [], 'usage_capture_complete': True}
    def call(row):
        return {'call_id': row['slot_id']+':0001', 'purpose': 'agent', 'prompt_tokens': 8,
            'completion_tokens': 2, 'reasoning_tokens': 0, 'prompt_cache_hit_tokens': 0,
            'prompt_cache_miss_tokens': 8, 'accounted_cost_cny': '0'}
    api.usage_for_slot = lambda row: {'calls': [call(row)] if row['slot_id'] in fixture.entered else [],
        'unresolved_calls': [], 'usage_capture_complete': True}
    old_generation, old_usage = {}, {}
    for row in rows[:2]:
        result_ref = write_new(tmp_path/f'old-{row["slot_index"]}.json', {
            'slot_id': row['slot_id'], 'configuration': row['configuration'], 'status': 'closed', 'model_calls': 1})
        old_generation[row['slot_id']] = {'status': 'closed', 'entered': True, 'result': result_ref}
        old_usage[row['slot_id']] = write_new(tmp_path/f'old-usage-{row["slot_index"]}.json', {
            'slot_id': row['slot_id'], 'group_id': row['group_id'], 'entered': True,
            'generation_state': 'closed', 'code_result': None, 'calls': [call(row)],
            'unresolved_calls': [], 'usage_capture_complete': True})
    history = {'generation': old_generation,
        'scores': {row['slot_id']: {'status': 'technical_unknown'} for row in rows[:2]},
        'deliveries': {}, 'exceptions': [], 'provider_failures': {}}
    history_ref = write_new(tmp_path/'history.json', history)
    health = write_new(tmp_path/'health.json', {'passed': True})
    usage = write_new(tmp_path/'usage.json', {'record_files': old_usage})
    inventory = write_new(tmp_path/'inventory.json', {'history': history_ref, 'usage_index': usage,
                                                     'initial_health': health})
    recovery = write_new(tmp_path/'recovery.json', {'scripted': True})
    authorization = {'preparation_recovery': recovery, 'resume_inventory': inventory}
    auth_ref = write_new(tmp_path/'auth.json', authorization)
    plan_ref = write_new(tmp_path/'plan.json', {**plan, 'rows': rows})
    monkeypatch.setattr(scope, 'PLAN_FILE', scope.Path(plan_ref['path']))
    monkeypatch.setattr(scope, 'AUTH_FILE', scope.Path(auth_ref['path']))
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'manager')
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: authorization)
    monkeypatch.setattr(scope, 'verify_host_limits', lambda: {'scripted': True})
    monkeypatch.setattr(scope, 'reserve_api_coordinator', lambda: {'scripted': True})
    released = []
    monkeypatch.setattr(scope, 'release_api_coordinator', released.append)
    monkeypatch.setattr(manager, 'validate_preparation_recovery', lambda value: value)
    monkeypatch.setattr(manager.resume_inventory, 'validate', lambda *_a, **_kw: history)
    monkeypatch.setattr(manager, 'DeepSeekRuntime', lambda: api)
    monkeypatch.setattr(manager, 'build_episode', lambda: SimpleNamespace(run_episode=fixture.episode))
    monkeypatch.setattr(grading_module, 'factory', lambda **_kw: fixture)
    result = manager.run()
    assert result['failure'] is None
    assert len(result['generation']) == len(result['scores']) == 4
    assert all(fixture.calls[row['slot_id']] == 0 for row in rows[:2])
    assert all(fixture.calls[row['slot_id']] == 1 for row in rows[2:])
    assert all(slot not in {r['slot_id'] for r in rows[:2]} for slot, _ in fixture.score_calls)
    assert sum(fixture.score_calls.values()) == 3
    assert result['generation'][rows[0]['slot_id']] == history['generation'][rows[0]['slot_id']]
    assert len(released) == 1 and api.cancelled
    assert (scope.API_ROOT/'initial-pair-api-health-reused.json').is_file()
    assert not (scope.API_ROOT/'initial-pair-api-health.json').exists()
    saved = scope.load(reference(scope.API_ROOT/'actual-usage-records.json'))
    assert set(saved['record_files']) == {row['slot_id'] for row in rows}
    assert manager.queue_module().executors is manager.queue_base.executors


def test_new_host_reuses_exact_existing_API_admission_without_requests(monkeypatch):
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_kw: {
        'reused_API_qualification': reference(host.QUALIFICATION)})
    class ForbiddenClient:
        def __getattr__(self, name):
            raise AssertionError('No additional admission request: '+name)
    value = host.qualify(ForbiddenClient(), None)
    assert value['passed'] is True and value['model_calls'] == 2
    assert value['actual_known_input_output_tokens'] == 746
    assert host.DeepSeekRuntime.transport_factory.__globals__['scope'] is scope
