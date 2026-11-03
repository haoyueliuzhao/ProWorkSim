"""Preparation identities and authority boundaries; no external work."""
from __future__ import annotations

import copy
import importlib.util
import json

import pytest

from proworksim import software_benchmark_scope_v111 as scope
from proworksim.software_benchmark_alignment_contract_v110 import VERSION, validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def panel():
    path = scope.ROOT/'tools/prepare_aligned_panel_v111.py'
    spec = importlib.util.spec_from_file_location('v111_panel_control', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_panel(json.loads(module.SOURCE.read_bytes()))


def fixture(tmp_path, monkeypatch):
    values = panel()
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path/'batch')
    for name, filename in (('PANEL_FILE','panel.json'), ('CPU_POOL_FILE','cpus.json'),
                           ('PLAN_FILE','plan.json'), ('SOURCE_FILE','sources.json'),
                           ('BUDGET_BASELINE_FILE','cash-before.json'),
                           ('AUTH_FILE','authorization.json')):
        monkeypatch.setattr(scope, name, tmp_path/filename)
    write_new(scope.PANEL_FILE, values)
    write_new(scope.CPU_POOL_FILE, {'uid': scope.os.getuid(), 'cpu_ids': list(range(176))})
    rows = [{**row, 'execution_arm': row['arm']} for row in values['rows']]
    plan = {'version':scope.VERSION, 'root':str(scope.BATCH_ROOT), 'rows':rows,
            'panel':reference(scope.PANEL_FILE), 'constraints':scope.CONSTRAINTS,
            'host_cpu_pool':reference(scope.CPU_POOL_FILE),
            'environments':{task:{} for task in values['task_ids']}}
    write_new(scope.PLAN_FILE, plan)
    write_new(scope.SOURCE_FILE, {'files':[]})
    write_new(scope.BUDGET_BASELINE_FILE, {'fixture':True})
    return plan


def test_new_panel_keeps_every_prespecified_task_and_uses_fresh_paired_identities():
    value = panel()
    original = json.loads((scope.ROOT/'artifacts/software-benchmark-v062/preparation-r1/panel.json').read_bytes())
    assert value['task_ids'] == original['task_ids']
    assert len(value['rows']) == len({row['slot_id'] for row in value['rows']}) == 100
    assert {row['slot_index'] for row in value['rows']} == set(range(7200,7300))
    for row in value['rows']:
        validate_plan_identity({**row, 'execution_arm':row['arm']})
    for task in value['task_ids']:
        pair = [row for row in value['rows'] if row['instance_id'] == task]
        assert {row['arm'] for row in pair} == {'REF','PROJECT'}
        assert len({row['seed'] for row in pair}) == 1
    assert value['aggregate_input_output_token_upper_bound'] == 500_000_000
    assert value['runtime_authorized_by_this_plan_file'] is False


def test_new_scope_rejects_old_id_and_undeclared_root_authority(tmp_path, monkeypatch):
    plan = fixture(tmp_path, monkeypatch)
    assert scope.validate_plan(plan) == plan
    with pytest.raises(PermissionError, match='authorization'):
        scope.require_allowed()
    bad = copy.deepcopy(plan)
    bad['rows'][0]['slot_id'] = bad['rows'][0]['slot_id'].replace('v110:', 'v105:')
    with pytest.raises(ValueError, match='new v110'):
        scope.validate_plan(bad)
    auth = {'version':scope.VERSION,'status':'approved','plan':reference(scope.PLAN_FILE),
            'source_index':reference(scope.SOURCE_FILE),'API_cash_cap_CNY':scope.CASH_CAP_CNY,
            'new_generation_attempts':100,'constraints':scope.CONSTRAINTS,
            'cash_budget_scope':scope.CASH_MODE,'ledger_path':str(scope.LEDGER_FILE),
            'cash_before_run':reference(scope.BUDGET_BASELINE_FILE),
            'shared_host_configuration_changes':0}
    write_new(scope.AUTH_FILE, auth)
    with pytest.raises(PermissionError, match='authority differs'):
        scope.require_allowed()
    scope.AUTH_FILE.write_text(json.dumps({**auth,'execution_alignment_version':VERSION}))
    scope.require_allowed('v066.resolve', instance_id='psf__requests-1766')
    with pytest.raises(PermissionError, match='two declared TLS'):
        scope.require_allowed('v066.transport', instance_id=plan['rows'][0]['instance_id'])
    with pytest.raises(PermissionError, match='Grading authority'):
        scope.require_grading_allowed('v066.actor.create')
    with pytest.raises(PermissionError):
        scope.require_allowed('v066.model.start')


def test_new_scope_reserves_disjoint_lanes_and_never_adds_system_or_gpu_objects(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    lanes = [set(scope.cpu_set('coordinator').split(','))]
    lanes += [set(scope.cpu_set(role,index).split(','))
              for index in range(8) for role in ('actor','controller')]
    lanes += [set(scope.cpu_set('grader',index).split(',')) for index in range(2)]
    assert sum(map(len,lanes)) == len(set().union(*lanes)) == 64
    assert scope.CONSTRAINTS['maximum_combined_reserved_memory_bytes'] == 320*scope.GIB
    assert scope.CONSTRAINTS['physical_gpus'] == []
    assert scope.CONSTRAINTS['system_parent_slice_created'] is False
    assert scope.CONSTRAINTS['host_bind_mounts'] is False
    assert scope.dispatch_view(lambda *_a, **_kw:{}).BATCH_ROOT != scope.original.BATCH_ROOT
