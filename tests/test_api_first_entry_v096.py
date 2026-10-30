"""Zero-generation proof and first-entry identity guards, with no runtime work."""
from __future__ import annotations

import copy
import importlib.util
import sqlite3

import pytest

from proworksim import software_benchmark_api_scope_v096 as scope
from proworksim import software_benchmark_api_budget_v096 as budget
from proworksim.software_benchmark_deepseek_runtime_v069 import private_function
from proworksim.software_benchmark_candidates_v054 import reference


@pytest.fixture(scope='module')
def prepared():
    if not scope.INVENTORY_FILE.exists():
        pytest.skip('Local prepared 79-row inventory is unavailable')
    return scope.canonical_rows(),scope.load(reference(scope.INVENTORY_FILE))['rows']


def test_physical_continuation_preserves_original_logical_attempt(prepared):
    originals,physical=prepared
    assert len(originals)==len(physical)==79
    assert {row['slot_index'] for row in physical}==set(range(6090,6169))
    assert {row['slot_id'] for row in physical}=={row['slot_id'] for row in originals}
    for position in (0,1,78):
        old,new=originals[position],physical[position]
        scope.validate_physical_mapping(new,old,scope.load(new['configuration']),scope.load(old['configuration']))
    assert not ({r['slot_id'] for r in originals}&{r['slot_id'] for r in budget.financial_recovery_rows()})


@pytest.mark.parametrize('field,value',[('seed',1),('input_plus_output_tokens',10_000_000),
                                      ('slot_index',6000),('slot_id','unregistered:recovery-v089-r1')])
def test_physical_mapping_cannot_change_model_identity(prepared,field,value):
    originals,physical=prepared
    changed={**physical[0],field:value}
    with pytest.raises(PermissionError):
        scope.validate_physical_mapping(changed,originals[0],scope.load(physical[0]['configuration']),
                                        scope.load(originals[0]['configuration']))


def test_registry_cannot_add_sample_or_accept_financial_recovery_rows(prepared):
    originals,_=prepared
    for rows in [originals[:-1],originals+[originals[0]],budget.financial_recovery_rows()]:
        with pytest.raises(PermissionError):
            scope.validate_registry(rows)


@pytest.mark.parametrize('table',['requests','response_observations','provider_protocol_events'])
def test_zero_API_gate_checks_all_three_tables(prepared,tmp_path,table):
    originals,_=prepared
    path=tmp_path/'ledger.sqlite3'
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE requests (request_id TEXT, slot_id TEXT)')
    db.execute('CREATE TABLE response_observations (request_id TEXT)')
    db.execute('CREATE TABLE provider_protocol_events (request_id TEXT)')
    db.commit()
    assert all(n==0 for n in scope.zero_request_snapshot(originals,path=path)['exact_original_ID_counts'].values())
    slot=originals[0]['slot_id']
    if table=='requests':
        db.execute('INSERT INTO requests VALUES (?,?)',(slot+':0001',slot))
    else:
        db.execute('INSERT INTO '+table+' VALUES (?)',(slot+':0001',))
    db.commit()
    db.close()
    with pytest.raises(PermissionError):
        scope.zero_request_snapshot(originals,path=path)


def test_missing_runtime_approval_blocks_before_parent_or_client(tmp_path):
    def unexpected(*args,**kwargs):
        raise AssertionError('No parent/client call before explicit authority')
    guard=private_function(scope.require_allowed,AUTH_FILE=tmp_path/'absent.json',parent_module=unexpected)
    with pytest.raises(PermissionError,match='explicit runtime approval'):
        guard('v096.run')


def test_new_host_thread_profile_does_not_mutate_inherited_environment():
    path=scope.ROOT/'tools/run_offline_scorer_v096.py'
    spec=importlib.util.spec_from_file_location('cpu_only_scorer_loader',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inherited={'OPENBLAS_NUM_THREADS':'64','PYTHONPATH':'untrusted-overlay'}
    old=copy.deepcopy(inherited)
    _,env=module.launch_spec(['-c','pass'],inherited=inherited)
    assert inherited==old
    assert env['OPENBLAS_NUM_THREADS']==env['OMP_NUM_THREADS']=='1'
    assert env['PROWORKSIM_SCORER_HOST_THREAD_PROFILE']==module.VERSION
    assert env['CUDA_VISIBLE_DEVICES']=='' and env['NVIDIA_VISIBLE_DEVICES']=='void'
    assert env['PYTHONPATH']!='untrusted-overlay'


@pytest.mark.parametrize('operation',['v066.model.start','v066.control','v066.transport','v066.resolve'])
def test_scope_does_not_admit_GPU_or_unneeded_control_network(operation):
    with pytest.raises(PermissionError,match='outside'):
        scope.require_allowed(operation)
