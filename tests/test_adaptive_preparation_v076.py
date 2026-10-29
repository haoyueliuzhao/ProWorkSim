"""No-runtime identity handoff and bounded owned-launcher integration controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import reference

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return reference(path)


def test_conflicting_history_is_not_silently_overwritten():
    prepare = module('prepare_adaptive_v076')
    assert prepare.merge_entries({'a': {'status': 'closed'}}, {'a': {'status': 'closed'}}) == {'a': {'status': 'closed'}}
    with pytest.raises(ValueError, match='Conflicting retained history'):
        prepare.merge_entries({'a': {'status': 'closed'}}, {'a': {'status': 'technical_unknown'}})


def test_owned_commands_keep_limits_and_do_not_address_resident_units(tmp_path, monkeypatch):
    launch = module('launch_adaptive_v076')
    scope = launch.scope
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'tools/run_adaptive_v076.py').write_text('# fixture')
    monkeypatch.setattr(scope, 'ROOT', tmp_path)
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path / 'batch')
    monkeypatch.setattr(scope, 'PRIMARY_ROOT', tmp_path / 'batch/primary')
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path / 'batch/api')
    monkeypatch.setattr(launch.original, 'cpu_set', lambda *_: '0,1,2,3')
    monkeypatch.setattr(scope, 'cpu_affinity', lambda: [168, 169, 170, 171])
    units = launch.prepare()['units']
    for role, value in units.items():
        command = value['command']
        assert '--property=MemoryMax=16G' in command
        assert '--property=CPUQuota=400%' in command
        assert '--property=Restart=no' in command
        assert command[-3:] == ['--execute', '--role', role]
        assert all('model-' not in part for part in command)


def test_inventory_keeps_history_unfinished_scores_and_excludes_every_consumed_identity(tmp_path, monkeypatch):
    prepare = module('prepare_adaptive_v076')
    scope, original, handoff, old_api = prepare.scope, prepare.original, prepare.handoff, prepare.old_api
    batch, previous, old_current = tmp_path / 'new', tmp_path / 'original', tmp_path / 'current'
    boundary = batch / 'handoff/administrative-boundary'
    roots = {'primary': tmp_path / 'old-primary', 'api': tmp_path / 'old-api'}
    for path in (previous, old_current, batch, *roots.values()):
        path.mkdir(parents=True, exist_ok=True)
    mapping = {'ROOT': tmp_path, 'BATCH_ROOT': batch, 'HANDOFF_ROOT': batch / 'handoff',
        'INVENTORY_FILE': batch / 'continuation-inventory.json', 'PLAN_FILE': batch / 'plan.json',
        'AUTH_FILE': batch / 'auth.json'}
    for key, value in mapping.items():
        monkeypatch.setattr(scope, key, value)
    monkeypatch.setattr(scope, 'require_allowed', lambda *args, **kwargs: {'approved': True})
    monkeypatch.setattr(original, 'BATCH_ROOT', old_current)
    monkeypatch.setattr(original, 'PREDECESSOR_ROOT', previous)
    monkeypatch.setattr(original, 'PLAN_FILE', previous / 'plan.json')
    monkeypatch.setattr(handoff, 'OLD_ROOTS', roots)
    monkeypatch.setattr(handoff, 'validate_unit', lambda *args: None)
    monkeypatch.setattr(handoff, 'show', lambda *args: {})
    specs = {role: {'specification': dump(folder / 'unit.json', {})} for role, folder in roots.items()}
    monkeypatch.setattr(handoff, 'stage_value', lambda: {'coordinators': specs})
    monkeypatch.setattr(old_api, 'LEASE_FILE', old_current / 'absent-lease.json')
    monkeypatch.setattr(old_api, 'API_ROOT', roots['api'])
    monkeypatch.setattr(old_api, 'INVENTORY_FILE', roots['api'] / 'inventory.json')
    monkeypatch.setattr(prepare, 'launcher', lambda: SimpleNamespace(prepare=lambda: {'units': {}}))
    dump(batch / 'auth.json', {'approved': True})
    dump(batch / 'handoff/coordinators-stopped.json', {'resident_units_stopped': False, 'new_generation': 0})
    dump(roots['api'] / 'coordinator-capacity-released.json', {'quiescent': True})
    rows = [{'slot_id': f's{i}', 'slot_index': i, 'model_key': 'QWEN' if i < 3000 else 'DEEPSEEK',
        'input_plus_output_tokens': 5_000_000 if i < 4000 else 10_000_000,
        'arm': 'PROJECT' if i == 3001 else 'REF'} for i in range(6000)]
    dump(previous / 'plan.json', {'rows': rows})
    prior = dump(roots['primary'] / 'inventory.json', {'usage_record_files': {}, 'completed_controls': {}})
    results = {slot: dump(old_current / 'episodes' / str(index) / 'result.json', {'slot_id': slot})
               for slot, index in [('s0', 0), ('s3000', 3000), ('s3001', 3001), ('s3002', 3002)]}
    entries = {slot: {'status': 'closed', 'entered': True, 'result': ref} for slot, ref in results.items()}
    dump(roots['api'] / 'inventory.json', {'generation': {'s3000': entries['s3000']},
        'scores': {'s3000': {'status': 'known'}}, 'deliveries': {}, 'usage_record_files': {}})
    score = old_current / 'grading/score-3001'
    request = dump(score / 'request.json', {'directory': str(score), 'resource_key': 'score-3001',
        'slot_id': 's3001', 'generation_result': results['s3001']})
    dump(score / 'completion.json', {'status': 'closed'})
    dump(score / 'quiescence.json', {'quiescent': True, 'cleanup_errors': [], 'create_result_unknown': False})
    common = {'failure': None, 'active_generation': [], 'active_grading': [], 'pending_scores': [],
        'pending_controls': [], 'scores': {}, 'deliveries': {}, 'qualifications': {}, 'provider_failures': {}}
    dump(boundary / 'primary-cursor.json', {**common, 'generation': {'s0': entries['s0']},
        'scores': {'s0': {'status': 'known'}}, 'resume_inventory': prior})
    dump(boundary / 'api-cursor.json', {**common,
        'generation': {'s3001': entries['s3001'], 's3002': entries['s3002']},
        'active_grading': [request], 'pending_scores': [['code', rows[3002], results['s3002'], False]]})
    dump(old_current / 'resource-claims/actor-3003.json', {})
    (roots['api'] / 'events.jsonl').write_text(json.dumps({'kind': 'generation_scheduled', 'slot_id': 's3004'}) + '\n')
    (previous / 'api-budget').mkdir()
    with sqlite3.connect(previous / 'api-budget/ledger.sqlite3') as db:
        db.execute('CREATE TABLE requests (slot_id TEXT,status TEXT)')
        db.execute("INSERT INTO requests VALUES ('s3005','settled')")
    (old_current / 'episodes/3006').mkdir()
    output = prepare.prepare_inventory()
    inventory = json.loads(Path(output['inventory']['path']).read_bytes())
    api = json.loads(Path(output['API_inventory']['path']).read_bytes())
    assert len(inventory['allowed_generation_slot_ids']) == 3992
    assert set(inventory['generation']) == {'s0', *(f's{i}' for i in range(3000, 3007))}
    assert all(inventory['generation'][f's{i}']['status'] == 'technical_unknown' for i in range(3003, 3007))
    assert inventory['scores']['s3001']['request'] == request
    assert len(inventory['unused_score_jobs']) == 1 and inventory['unused_score_jobs'][0][1]['slot_id'] == 's3002'
    assert inventory['delivery_reconciliation'] == [{'slot_id': 's3001',
        'generation_result': results['s3001'], 'code_request': request}]
    assert 's0' not in api['generation'] and len(api['allowed_generation_slot_ids']) == 993
    assert api['unused_score_jobs'] == inventory['unused_score_jobs']
    assert not any('launch-intent' in str(path) for path in tmp_path.rglob('*'))
