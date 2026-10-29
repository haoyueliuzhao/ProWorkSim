"""Scope controls prevent cross-provider dispatch without runtime operations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from proworksim import software_benchmark_adaptive_scope_v076 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return reference(path)


@pytest.fixture
def authorized(tmp_path, monkeypatch):
    roots = {'BATCH_ROOT': tmp_path, 'AUTH_FILE': tmp_path / 'auth.json', 'SOURCE_FILE': tmp_path / 'sources.json',
        'PLAN_FILE': tmp_path / 'plan.json', 'INVENTORY_FILE': tmp_path / 'inventory.json',
        'API_INVENTORY_FILE': tmp_path / 'api-inventory.json', 'HANDOFF_ROOT': tmp_path / 'handoff',
        'CLAIM_FILE': tmp_path / 'claim.json', 'LEASE_FILE': tmp_path / 'lease.json'}
    for key, value in roots.items():
        monkeypatch.setattr(scope, key, value)
    monkeypatch.setattr(scope.original, 'AUTHORIZATION_FILE', tmp_path / 'original-auth.json')
    monkeypatch.setattr(scope.original, 'PLAN_FILE', tmp_path / 'original-plan.json')
    monkeypatch.setattr(scope.original, 'PREDECESSOR_ROOT', tmp_path / 'original')
    original_auth = dump(scope.original.AUTHORIZATION_FILE, {})
    rows = [{'slot_id': slot, 'model_key': model, 'input_plus_output_tokens': budget, 'instance_id': slot+'-task'}
            for slot, model, budget in [('api', 'DEEPSEEK', 5_000_000), ('qwen', 'QWEN', 5_000_000),
                ('high', 'DEEPSEEK', 10_000_000), ('old', 'DEEPSEEK', 5_000_000)]]
    original_plan = dump(scope.original.PLAN_FILE, {'rows': rows})
    monkeypatch.setattr(scope.original, 'require_v066_allowed', lambda *a, **kw: {'plan': original_plan})
    monkeypatch.setattr(scope.original, '_cached_json', lambda ref: json.loads(Path(ref['path']).read_bytes()))
    monkeypatch.setattr(scope, 'verify_host_limits', lambda role: {'role': role})
    source_ref = dump(scope.SOURCE_FILE, {'files': []})
    auth_ref = dump(scope.AUTH_FILE, {'version': scope.VERSION, 'status': 'approved',
        'original_authorization': original_auth, 'source_index': source_ref, 'API_total_cash_cap_CNY': '1500.00',
        'desired_API_concurrency': 44, 'maximum_API_concurrency': 48, 'maximum_global_actor_lanes': 52,
        'per_container_limits_unchanged': True, 'model_visible_configuration_unchanged': True,
        'shared_host_configuration_changed': False})
    ledger = str(scope.original.PREDECESSOR_ROOT / 'api-budget/ledger.sqlite3')
    inventory = {'allowed_generation_slot_ids': ['api', 'qwen', 'high'],
        'generation': {'old': {'status': 'closed', 'result': {'path': 'retained-result'}}}}
    inv_ref = dump(scope.INVENTORY_FILE, inventory)
    api = {'allowed_generation_slot_ids': ['api'], 'generation': {'old': {}},
        'excluded_old_scheduled_slot_ids': ['old'], 'API_ledger': ledger}
    api_ref = dump(scope.API_INVENTORY_FILE, api)
    handoff = dump(scope.HANDOFF_ROOT / 'coordinators-stopped.json', {})
    plan = {'original_plan': original_plan, 'inventory': inv_ref, 'API_inventory': api_ref,
        'API_ledger': ledger, 'planned_Qwen_slots': 3000, 'planned_API_slots': 1000,
        'handoff': handoff, 'new_model_calls_for_preparation': 0}
    plan_ref = dump(scope.PLAN_FILE, plan)
    dump(tmp_path / 'plan-seal.json', {'authorization': auth_ref, 'plan': plan_ref})
    claim = dump(scope.CLAIM_FILE, {'owned': True})
    scope.LEASE_FILE.write_bytes(Path(claim['path']).read_bytes())
    return {'api': api, 'plan': plan, 'auth': auth_ref, 'inventory': inventory}


def reseal(value):
    value['plan']['API_inventory'] = reference(scope.API_INVENTORY_FILE)
    value['plan']['inventory'] = reference(scope.INVENTORY_FILE)
    plan = dump(scope.PLAN_FILE, value['plan'])
    dump(scope.BATCH_ROOT / 'plan-seal.json', {'authorization': value['auth'], 'plan': plan})


def test_api_request_and_provider_initialization_require_exact_owned_inventory(authorized):
    assert scope.require_allowed('v072.api.request', slot_id='api', instance_id='api-task')['status'] == 'approved'
    assert scope.require_allowed('v076.api.request')['status'] == 'approved'
    with pytest.raises(PermissionError, match='slot identity'):
        scope.require_allowed('v076.api.request', instance_id='api-task')
    with pytest.raises(PermissionError, match='DeepSeek 5M identity'):
        scope.require_allowed('v076.api.request', slot_id='api', instance_id='another-task')


@pytest.mark.parametrize('slot', ['qwen', 'high'])
def test_even_api_subinventory_cannot_authorize_wrong_model_or_budget(authorized, slot):
    authorized['api']['allowed_generation_slot_ids'].append(slot)
    dump(scope.API_INVENTORY_FILE, authorized['api'])
    reseal(authorized)
    with pytest.raises(PermissionError, match='DeepSeek 5M identity'):
        scope.require_allowed('v076.api.request', slot_id=slot)


def test_consumed_api_task_cannot_replay_but_closed_candidate_can_be_scored(authorized):
    assert scope.require_allowed('v076.run', slot_id='old')['status'] == 'approved'
    with pytest.raises(PermissionError, match='Consumed generation'):
        scope.require_allowed('v076.api.request', slot_id='old')
    authorized['inventory']['generation']['old']['status'] = 'technical_unknown'
    dump(scope.INVENTORY_FILE, authorized['inventory'])
    reseal(authorized)
    with pytest.raises(PermissionError, match='Consumed generation'):
        scope.require_allowed('v076.run', slot_id='old')


def test_api_inventory_seal_and_owner_lease_are_required(authorized):
    scope.API_INVENTORY_FILE.write_text('{}')
    with pytest.raises(PermissionError, match='identity or handoff'):
        scope.require_allowed('v076.api.request', slot_id='api')
    dump(scope.API_INVENTORY_FILE, authorized['api'])
    reseal(authorized)
    scope.LEASE_FILE.write_text('{"foreign":true}')
    with pytest.raises(PermissionError, match='owner reservation'):
        scope.require_allowed('v076.api.request', slot_id='api')
