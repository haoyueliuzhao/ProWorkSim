"""Actual independent-ID, controller, closure and wait-to-start boundaries."""
import ast,copy,importlib.util,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from proworksim import software_benchmark_scope_v170 as scope
from proworksim import software_benchmark_alignment_contract_v170 as alignment
from proworksim import software_benchmark_project_closure_v170 as closure
from proworksim import software_benchmark_project_closure_v157 as old_closure
from proworksim.software_benchmark_candidates_v054 import reference
ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def test_all14_exact_identities_retain_condition_seed_and_no_locked_original():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert len(plan['rows'])==13 and len(plan['environments'])==7
    assert [r['slot_index'] for r in plan['rows']]==list(range(17000,17013))
    assert {r['wave'] for r in plan['rows']}=={1,2}
    assert not any('sympy__sympy-17318:REVIEW2_C1:' in r['slot_id'] for r in plan['rows'])
    for row in plan['rows']:
        assert alignment.validate_plan_identity(row) is row
        altered={**row,'seed':row['seed']+1}
        with pytest.raises(ValueError):alignment.validate_plan_identity(altered)
        with pytest.raises(ValueError):alignment.validate_plan_identity({**row,'slot_id':row['slot_id'].split(':completion')[0]})

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
    source=(ROOT/'tools/run_communication_controller_v170.py').read_text();tree=ast.parse(source)
    imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert 'proworksim.software_benchmark_alignment_contract_v170' in imports
    assert 'proworksim.software_benchmark_project_closure_v170' in imports
    assert 'proworksim.software_benchmark_finalization_v159' in imports
    assert 'proworksim.software_communication_finish_v159' in imports
    assert 'proworksim.software_benchmark_alignment_contract_v157' not in imports

def test_real_episode_builder_binds_new_bundle_and_identity_without_mutating_old():
    from proworksim.software_benchmark_episode_v170 import build_episode
    from proworksim import software_benchmark_sdk_bundle_v170 as bundle
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
    run=module('run_communication_pilot_v170')
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
    assert len(result['deferred'])==13 and not coordinator.wave2
    assert result['independent_recovery_episodes']==13

def test_predecessor_active_leases_are_never_hidden(monkeypatch,tmp_path):
    root=tmp_path/'old';(root/'resource-claims').mkdir(parents=True)
    (root/'execution-plan.json').write_text(json.dumps({'resources':{},'rows':[]}))
    (root/'resource-claims/active-actor-0.json').write_text('{}')
    monkeypatch.setattr(scope,'PREDECESSOR_ROOT',root)
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='ActiveState=active\nMainPID=123\n'))
    value=scope.predecessor_quiescence_status()
    assert not value['passed'] and not value['lease_empty'] and not value['predecessor_service_inactive']


def test_actual_native_allocator_claims_pair_without_legacy_overlap_fields(tmp_path, monkeypatch):
    """Use real claim/lease files in tmp, with no Docker or shared reservation."""
    import json
    plan_ref = reference(scope.PLAN_FILE)
    rows = scope.load(plan_ref)['rows']
    auth = tmp_path/'cpu-authority.json'; auth.write_text('{}')
    monkeypatch.setattr(scope, 'BATCH_ROOT', tmp_path)
    monkeypatch.setattr(scope, 'AUTH_FILE', auth)
    monkeypatch.setattr(scope, '_budget', lambda *a, **k: {'CPU_fixture': True})
    # A zero-overlap predecessor need not supply an obsolete blocked-lane map.
    monkeypatch.setattr(scope, 'predecessor_quiescence_status', lambda: {'passed': True})
    dispatch = scope.dispatch_view(guard=lambda *a, **k: {
        'source_index': reference(scope.original_scope.SOURCE_FILE), 'status': 'approved'})
    first, second = (r['slot_index'] for r in rows[:2])
    a = dispatch.claim_resource(f'actor-{first}')
    b = dispatch.claim_resource(f'actor-{second}')
    c = dispatch.claim_resource(f'controller-{first}')
    v = dispatch.claim_resource(f'volume-{first}')
    load = lambda ref: json.loads(Path(ref['path']).read_bytes())
    assert load(a)['lane'] == load(c)['lane'] == load(v)['lane'] == 0
    assert load(b)['lane'] == 1
    assert load(a)['reserved_cpu'] == 6 and load(a)['reserved_memory_bytes'] == 48*1024**3
    with pytest.raises(ValueError, match='already consumed'):
        dispatch.claim_resource(f'actor-{first}')
    for ref in (c, v, a, b):
        dispatch.release_resource(ref, quiescent=True)
    assert not list((tmp_path/'resource-claims').glob('active-*.json'))
