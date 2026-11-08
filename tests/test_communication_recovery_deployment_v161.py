"""Actual independent-ID, controller, closure and wait-to-start boundaries."""
import ast,copy,importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_scope_v161 as scope
from proworksim import software_benchmark_alignment_contract_v161 as alignment
from proworksim import software_benchmark_project_closure_v161 as closure
from proworksim import software_benchmark_project_closure_v157 as old_closure
from proworksim.software_benchmark_candidates_v054 import reference
ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def test_all14_exact_identities_retain_condition_seed_and_no_locked_original():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert len(plan['rows'])==14 and len(plan['environments'])==5
    assert [r['slot_index'] for r in plan['rows']]==list(range(16100,16114))
    assert all(r['wave']==1 for r in plan['rows'])
    assert not any('sympy__sympy-17318:REVIEW2_C1:' in r['slot_id'] for r in plan['rows'])
    for row in plan['rows']:
        assert alignment.validate_plan_identity(row) is row
        altered={**row,'seed':row['seed']+1}
        with pytest.raises(ValueError):alignment.validate_plan_identity(altered)
        with pytest.raises(ValueError):alignment.validate_plan_identity({**row,'slot_id':row['slot_id'].split(':independent')[0]})

def test_delivery_function_logic_is_original_but_identity_globals_are_private():
    row=scope.load(reference(scope.PLAN_FILE))['rows'][0]
    assert closure.validate_delivery_evidence.__code__ is old_closure.validate_delivery_evidence.__code__
    assert closure.export_managed_closure.__code__ is old_closure.export_managed_closure.__code__
    assert closure.validate_delivery_evidence.__globals__ is not old_closure.validate_delivery_evidence.__globals__
    assert closure.validate_delivery_evidence.__globals__['validate_slot_identity'] is closure.validate_slot_identity
    assert closure._base_validate.__globals__['validate_slot_identity'] is closure.validate_slot_identity
    assert closure.validate_slot_identity(row['slot_id'],row['instance_id'])['group_id']==row['group_id']
    with pytest.raises(ValueError):old_closure.validate_slot_identity(row['slot_id'],row['instance_id'])

def test_actual_controller_uses_new_identity_and_existing_repaired_finalizer():
    source=(ROOT/'tools/run_communication_controller_v161.py').read_text();tree=ast.parse(source)
    imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert 'proworksim.software_benchmark_alignment_contract_v161' in imports
    assert 'proworksim.software_benchmark_project_closure_v161' in imports
    assert 'proworksim.software_benchmark_finalization_v159' in imports
    assert 'proworksim.software_communication_finish_v159' in imports
    assert 'proworksim.software_benchmark_alignment_contract_v157' not in imports

def test_real_episode_builder_binds_new_bundle_and_identity_without_mutating_old():
    from proworksim.software_benchmark_episode_v161 import build_episode
    from proworksim import software_benchmark_sdk_bundle_v161 as bundle
    value=build_episode(scope=scope,guard=lambda *a,**k:{'plan':reference(scope.PLAN_FILE),'status':'approved','execution_alignment_version':alignment.VERSION,'source_index':reference(scope.original_scope.SOURCE_FILE)})
    actual=value._run.__globals__
    assert actual['runtime'] is bundle
    assert actual['validate_condition'] is alignment.validate_condition
    assert value.run_episode.__globals__['_run'] is value._run
    assert value._row_and_config.__globals__['validate_plan_identity'] is alignment.validate_plan_identity
    for row in scope.load(reference(scope.PLAN_FILE))['rows']:
        config,condition,limits=value._row_and_config(row,False)
        assert config['slot_id']==row['slot_id'] and limits['input_plus_output_tokens']==5_000_000
    assert actual['serve_model_channel'].__globals__ is not __import__('proworksim.software_benchmark_model_fifo_v157',fromlist=['x']).__dict__

def test_single_wave_drain_terminates14_without36_row_gate(tmp_path,monkeypatch):
    run=module('run_communication_pilot_v161')
    from proworksim.software_benchmark_group_admission_v157 import FairAdmission,DrainControl,VERSION
    plan=scope.load(reference(scope.PLAN_FILE));p=tmp_path/'admission.json'
    p.write_text(json.dumps({'version':VERSION,'batch_root':str(tmp_path),'mode':'drain',
        'groups':list(alignment.GROUP_IDS),'maximum_generations':16,'revision':0,'reason':'test'}))
    admission=FairAdmission(alignment.GROUP_IDS,control=DrainControl(p,batch_root=tmp_path,groups=alignment.GROUP_IDS,maximum=16),maximum=16,maximum_startups=4)
    monkeypatch.setattr(scope,'reconcile_generation_limit',lambda:{'passed':True})
    runtime=SimpleNamespace(for_group=lambda _:SimpleNamespace(settled_route_witnesses=lambda:True))
    coordinator=run.Coordinator(runtime=runtime,implementation=None,grading=None,memory=SimpleNamespace(snapshot=lambda:{}),
        admission=admission,plan=plan,qualifications={k:{'passed':True} for k in plan['environments']},output=tmp_path/'out',
        cash_status=lambda _:dict(state='ready',can_start_generation=False))
    monkeypatch.setattr(run.time,'sleep',lambda _:pytest.fail('Drained single-wave owner must not wait for another gate'))
    result=coordinator.execute()
    assert len(result['deferred'])==14 and not coordinator.wave2
    assert result['independent_recovery_episodes']==14

def test_waiter_requires_every_cleanup_predicate():
    waiter=module('wait_communication_recovery_v161')
    good={'passed':True,'v159_all_owned_objects_removed':True,'lease_empty':True,'predecessor_service_inactive':True}
    assert waiter.ready(good)
    for key in good:assert not waiter.ready({**good,key:False})
    spec=waiter.specification()
    assert spec['maximum_wait_seconds']==172800 and spec['memory_max_bytes']==512*1024**2
    assert spec['model_calls_in_waiter']==0 and spec['containers_created_in_waiter']==0

def test_predecessor_active_leases_are_never_hidden(monkeypatch,tmp_path):
    root=tmp_path/'old';(root/'resource-claims').mkdir(parents=True)
    (root/'execution-plan.json').write_text(json.dumps({'resources':{},'rows':[]}))
    (root/'resource-claims/active-actor-0.json').write_text('{}')
    monkeypatch.setattr(scope,'PREDECESSOR_ROOT',root)
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='ActiveState=active\nMainPID=123\n'))
    value=scope.predecessor_quiescence_status()
    assert not value['passed'] and not value['lease_empty'] and not value['predecessor_service_inactive']
