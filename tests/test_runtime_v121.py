"""Independent27 recovery: predecessor gate, exact mapping and isolated cost."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess

import pytest

from proworksim import software_benchmark_scope_v121 as scope
from proworksim import software_benchmark_host_api_v121 as host
from proworksim import software_benchmark_prior_completion_v121 as gate
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name+'_CPU',scope.ROOT/'tools'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def refuse(*_a,**_k):
        raise AssertionError('This control cannot call network, services or models')
    for name in ('connect','bind','sendto'):
        monkeypatch.setattr(socket.socket,name,refuse)
    monkeypatch.setattr(socket,'getaddrinfo',refuse)
    monkeypatch.setattr(subprocess,'Popen',refuse)
    monkeypatch.setattr(host.api,'load_api_key',refuse)


def test_prior_gate_never_writes_early_and_accepts_terminal_unknown_with_clean_receipts(tmp_path,monkeypatch):
    prior = tmp_path/'prior'
    owner = prior/'api-coordinator-v120'
    owner.mkdir(parents=True)
    resources = prior/'resource-claims'
    resources.mkdir()
    future = tmp_path/'new/prior-v120-completion.json'
    config = write_new(tmp_path/'configuration.json',{'CPU_fixture_only':True})
    rows = [{'slot_id':f'prior-{i}','slot_index':8031+i,'instance_id':f'task-{i}','configuration':config} for i in range(23)]
    plan_ref = write_new(prior/'execution-plan-v120.json',{'rows':rows})
    for name,value in {'PRIOR_BATCH_ROOT':prior,'PRIOR_API_ROOT':owner,
        'PRIOR_PLAN_FILE':Path(plan_ref['path']),'PRIOR_COMPLETION_FILE':future}.items():
        monkeypatch.setattr(scope,name,value)
    with pytest.raises(gate.PriorStageIncomplete):
        gate.prepare_prior_completion()
    assert not future.exists()
    claim = write_new(owner/'coordinator-capacity.json',{'fixture':True})
    write_new(owner/'coordinator-capacity-released.json',{'claim':claim,'released':True})
    generations = {}
    for i,row in enumerate(rows):
        folder = prior/'episodes'/str(row['slot_index'])
        folder.mkdir(parents=True)
        result = write_new(folder/'result.json',{'slot_id':row['slot_id'],'instance_id':row['instance_id'],
            'configuration':config,'status':'closed' if i==0 else 'technical_unknown'})
        write_new(folder/'quiescence.json',{'quiescent':True,'cleanup_errors':[],
            'create_result_unknown':False,'all_owned_objects_removed':True,'retained_objects':[]})
        generations[row['slot_id']]={'status':'closed' if i==0 else 'technical_unknown','entered':True,'result':result}
    grade = prior/'grading-v120'/'score-8031'
    grade.mkdir(parents=True)
    request = write_new(grade/'request.json',{'slot_id':'prior-0','instance_id':'task-0'})
    write_new(grade/'completion.json',{'request':request,'status':'process_exited','returncode':1})
    write_new(grade/'quiescence.json',{'slot_id':'prior-0','quiescent':True,'cleanup_errors':[],'create_result_unknown':False})
    summary = {'plan':plan_ref,'finished_unix':123,'generation':generations,
        'scores':{'prior-0':{'request':request}},
        'deliveries':{'prior-0':{'status':'no_legal_delivery','resolved':False}},
        'pending_grading_jobs':[],'unentered_generation':[],'retained_objects':[]}
    write_new(owner/'run-summary.json',summary)
    proof_ref = gate.prepare_prior_completion()
    assert proof_ref == gate.require_prior_completion()
    proof = scope.load(proof_ref)
    assert proof['generation_tasks_terminal']==23 and proof['scoring_attempts_terminal']==1
    assert proof['all_outcomes_need_not_be_successful'] is True
    (resources/'active-grader-fixture.json').write_text('{}')
    with pytest.raises(gate.PriorStageIncomplete,match='still active'):
        gate.require_prior_completion()
    assert scope.load(proof_ref)==proof


def test_actual_mapping_new_ids_and_shared_launch_run_predecessor_gate(tmp_path,monkeypatch):
    manager = tool('run_project_recovery_v121')
    launcher = tool('launch_project_recovery_v121')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert manager.validate_independent_recovery(plan)==plan
    assert len(plan['rows'])==27
    assert {row['slot_index'] for row in plan['rows']}==set(range(8500,8527))
    assert all(row['slot_id']!=row['original_slot_id'] for row in plan['rows'])
    assert manager.build_episode.__globals__['bundle'] is host.bundle
    assert host.bundle.__name__.endswith('software_benchmark_sdk_bundle_v120')
    assert host.QUALIFICATION==scope.PRIOR_BATCH_ROOT/'api-qualification/result.json'
    assert host.MAX_CONCURRENCY==scope.MAX_GENERATIONS==16 and scope.MAX_GRADERS==2
    assert scope.CONSTRAINTS['maximum_containers']==108 and scope.CONSTRAINTS['maximum_named_volumes']==27
    assert manager.require_prior_completion is launcher.require_prior_completion is gate.require_prior_completion
    monkeypatch.setattr(scope,'PRIOR_COMPLETION_FILE',tmp_path/'not-complete.json')
    authorized=[]
    monkeypatch.setattr(scope,'require_allowed',lambda *_a,**_k: authorized.append(True))
    with pytest.raises(gate.PriorStageIncomplete):
        launcher.launch()
    with pytest.raises(gate.PriorStageIncomplete):
        manager.run()
    assert authorized==[]
    monkeypatch.setattr(scope,'API_ROOT',tmp_path/'api')
    scope.API_ROOT.mkdir()
    preparation=scope.load(manager.reuse_preparation(plan))
    assert preparation['model_calls']==preparation['diagnostics_repeated']==preparation['new_controls']==0
    original_qualification=scope.load(reference(host.QUALIFICATION))
    schemas=scope.load(original_qualification['schema_inventory'])
    new=write_new(tmp_path/'schemas.json',{**schemas,'version':host.VERSION,'runtime_bundle':{'fixture':'same120 runtime'}})
    monkeypatch.setattr(host,'SCHEMAS',Path(new['path']))
    assert host.qualify(None,None,scope.load(new))==original_qualification
    assert host.DeepSeekRuntime.preparation_usage()['new_preparation_API_calls']==0
    spec={**launcher.specification(),'ownership_token':'a'*32}
    assert launcher.command(spec)[-2:]==[str(scope.ROOT/'tools/run_project_recovery_v121.py'),'--execute']
    assert spec['unit']=='proworksim-v118-project.service'


def test_new_recovery_results_and_mean_exclude_original_unknown_effort(tmp_path):
    reporting=tool('summarize_project_recovery_v121')
    plan=scope.load(reference(scope.PLAN_FILE))
    own=plan['rows'][0]
    ledger=tmp_path/'api-ledger.sqlite'
    host.api.BudgetLedger(ledger,max_concurrency=16)
    records=[(own['slot_id'],own['condition_id'],'agent',8,2),
             (own['original_slot_id'],own['condition_id'],'agent',24,6),
             (host.NEUTRAL_SLOT,host.NEUTRAL_CONDITION,'preparation',5,1)]
    with sqlite3.connect(ledger) as db:
        for i,(slot,condition,purpose,prompt,output) in enumerate(records):
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'fixture-{i}',slot,condition,purpose,'settled','a'*64,100,50,100,prompt,'CPU',
                 json.dumps({'prompt_tokens':prompt,'completion_tokens':output,'total_tokens':prompt+output})))
    owner=tmp_path/'api-coordinator'
    owner.mkdir()
    write_new(owner/'run-summary.json',{'finished_unix':1,
        'unentered_generation':[row['slot_id'] for row in plan['rows'][1:]]})
    folder=tmp_path/'episodes'/str(own['slot_index'])
    folder.mkdir(parents=True)
    write_new(folder/'result.json',{'slot_id':own['slot_id'],'instance_id':own['instance_id'],
        'status':'closed','delivery_validation':{'submitted':False}})
    before=ledger.read_bytes()
    result=reporting.run(scope.PLAN_FILE,tmp_path)
    group=result['groups']['PROJECT']
    assert group['planned']==27 and group['mean_actual_tokens_complete_called_subset']==10
    assert group['mean_actual_tokens_all_stage_tasks']==10/27
    assert group['independent_recovery_27_accuracy_if_fully_scored'] is None
    preserved=result['preserved_original_attempt_context']
    assert preserved['original_known_token_lower_bounds']['total_tokens']==30
    assert preserved['preserved_original_unknowns']==27 and preserved['original_outcomes_overwritten'] is False
    assert preserved['combined_original50_accuracy'] is None
    mapping=json.loads((tmp_path/'reporting/original-to-recovery-mapping.json').read_bytes())
    assert len(mapping)==27 and all(item['new_slot_id']!=item['original_slot_id'] for item in mapping)
    assert ledger.read_bytes()==before
