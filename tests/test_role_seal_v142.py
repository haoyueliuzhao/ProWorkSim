"""Read-only actual review shapes and bounded synthetic refusal controls; no seal."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def tool(name):
    spec = importlib.util.spec_from_file_location('cpu_'+name, ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seal = tool('seal_role_pilot_v142')


def actual_review():
    from proworksim import software_benchmark_sdk_bundle_v141 as bundle
    from proworksim import software_benchmark_host_api_v142 as host
    from proworksim.software_benchmark_candidates_v054 import reference
    def read(path):
        return json.loads(Path(path).read_bytes())
    return (seal.scope.validate_plan(read(seal.scope.PLAN_FILE)),
            read(bundle.OUTPUT/'manifest.json'), read(host.SCHEMAS),
            read(seal.scope.API_ROOT/'coordinator-unit.json'), read(seal.BUDGET_GRANT), reference)


def test_actual_review_does_not_grant_or_create_a_slice():
    plan, bundle, schemas, unit, budget, ref = actual_review()
    result = seal.validate_review_shapes(plan, bundle, schemas, unit, budget)
    assert result['passed'] and result['runtime_authorized'] is False
    assert result['new_system_parent_slice'] is False
    proposal = seal.build_proposal(plan_ref=ref(seal.scope.PLAN_FILE), source_ref={'fixture': True},
        bundle_ref=schemas['runtime_bundle'], schemas_ref={'fixture': True}, unit_ref={'fixture': True},
        controls={}, review=result, payloads={}, cold_preparation={})
    assert proposal['status'] == 'prepared' and proposal['runtime_authorized'] is False
    assert proposal['maximum_containers'] == 568 and proposal['maximum_named_volumes'] == 124
    assert proposal['maximum_generation_pairs'] == 16 and proposal['maximum_graders'] == 2
    assert proposal['combined_CPU_quota_cores'] == 112 and proposal['combined_memory_GiB'] == 840
    assert proposal['API_cash_cap_CNY'] == '400.00'
    assert len(set(proposal['ledger_paths'].values())) == 1
    assert proposal['budget_guarantees_all_tasks_complete'] is False
    assert proposal['new_system_manager_objects'] == 0
    assert not seal.scope.AUTH_FILE.exists() and not seal.scope.SOURCE_FILE.exists()
    assert not seal.scope.PROPOSAL_FILE.exists() and not seal.scope.LEDGER_FILE.exists()


@pytest.mark.parametrize('change', ['parent', 'memory', 'counter', 'members', 'cash'])
def test_changed_review_bounds_fail_closed(change):
    plan, bundle, schemas, unit, budget, _ = actual_review()
    if change == 'parent':
        unit['system_parent_slice'] = 'foreign.slice'
    elif change == 'memory':
        unit['memory_max_bytes'] += 1
    elif change == 'counter':
        bundle['content_tokenizer']['require_content_counter'] = False
    elif change == 'members':
        schemas['schemas']['S1']['member_002'] = []
    else:
        budget['API_cash_cap_CNY'] = '1200.00'
    with pytest.raises(ValueError):
        seal.validate_review_shapes(plan, bundle, schemas, unit, budget)


def test_actual_roots_and_relative_dynamic_source_dependencies(tmp_path):
    root = tmp_path/'fixture'
    package = root/'src/proworksim'
    package.mkdir(parents=True)
    tools = root/'tools'
    tools.mkdir()
    (package/'entry_v142.py').write_text('from . import earlier\nname="proworksim.dynamic"\nhelper="literal.py"\n')
    (package/'earlier.py').write_text('from .leaf import value\n')
    (package/'leaf.py').write_text('value=1\n')
    (package/'dynamic.py').write_text('value=2\n')
    (tools/'literal.py').write_text('pass\n')
    (root/'.env').write_text('not read or sealed')
    found = seal.source_closure(root, roots=[package/'entry_v142.py'])
    assert {Path(row['path']).name for row in found} == {'entry_v142.py','earlier.py','leaf.py','dynamic.py','literal.py'}
    current = seal.source_closure()
    names = {Path(row['path']).name for row in current}
    assert {Path(name).name for name in seal.REQUIRED_SOURCE_NAMES} <= names
    assert 'activate_role_pilot_v142.py' in names
    assert 'software_collaboration_runtime_observer_v141.py' in names
    assert all(Path(row['path']).suffix == '.py' for row in current)


def test_existing_ledger_or_seal_blocks_before_preparation(tmp_path, monkeypatch):
    names = ('AUTH_FILE','USER_GRANT_FILE','SOURCE_FILE','PROPOSAL_FILE','LEDGER_FILE','CLAIM_FILE','LEASE_FILE')
    for name in names:
        monkeypatch.setattr(seal.scope, name, tmp_path/name)
    monkeypatch.setattr(seal.scope, 'API_ROOT', tmp_path/'api')
    seal.ensure_unentered()
    seal.scope.LEDGER_FILE.write_text('synthetic consumed identity')
    with pytest.raises(PermissionError):
        seal.seal()
    assert not seal.scope.SOURCE_FILE.exists() and not seal.scope.PROPOSAL_FILE.exists()


def test_stale_control_source_is_not_silently_reaccepted(tmp_path):
    source = tmp_path/'control.py'
    source.write_text('value=1')
    summary = tmp_path/'summary.json'
    summary.write_text(json.dumps({'passed': True, 'sources': [{'path': str(source),
        'sha256': seal.digest(source.read_bytes())}]}))
    seal.read_control(summary)
    source.write_text('value=2')
    with pytest.raises(ValueError, match='predates'):
        seal.read_control(summary)


def test_activation_order_and_no_grant_prevents_any_external_action(monkeypatch):
    activation = tool('activate_role_pilot_v142')
    assert seal.postgrant_sequence() == activation.postgrant_sequence()
    seen = []
    def reject(operation, **_identity):
        seen.append(operation)
        raise PermissionError('synthetic missing concrete runtime grant')
    monkeypatch.setattr(activation.scope, 'require_allowed', reject)
    monkeypatch.setattr(activation, 'run_phase', lambda *_: pytest.fail('Ungrantable external phase'))
    with pytest.raises(PermissionError):
        activation.activate()
    assert seen == ['v142.prepare']
    assert not activation.OUTPUT.exists()
    assert not seal.scope.AUTH_FILE.exists() and not seal.scope.SOURCE_FILE.exists()


def test_readonly_inspection_does_not_create_required_controls():
    before = copy.deepcopy(seal.inspect_inputs())
    assert before['runtime_authorized'] is False and before['source_seal_created'] is False
    assert before['operations'] == 0
