"""Only new zero-call recovery, reporting partition and automatic-drain wiring."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess

import pytest

from proworksim import software_benchmark_scope_v120 as scope
from proworksim import software_benchmark_host_api_v120 as host
from proworksim import software_benchmark_dispatch_control_v120 as admission
from proworksim.software_benchmark_alignment_contract_v117 import shared_strategy
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def tool(name):
    spec = importlib.util.spec_from_file_location(name+'_CPU', scope.ROOT/'tools'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('Only CPU fixtures and read-only evidence are permitted')
    for name in ('connect', 'bind', 'sendto'):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, 'getaddrinfo', refuse)
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(host.api, 'load_api_key', refuse)


def test_actual_23_zero_call_scope_reuses_diagnostic_and_neutral_with_no_dispatch(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v120')
    launcher = tool('launch_project_rerun_v120')
    plan = scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    recovery = manager.validate_first_generation_recovery(plan)
    assert recovery['held_called_generation_count'] == 27
    assert {row['slot_index'] for row in plan['rows']} == set(range(8031,8050)) | set(range(8100,8104))
    assert manager.build_episode.__globals__['bundle'] is host.bundle
    assert host.MAX_CONCURRENCY == scope.MAX_GENERATIONS == 16 and scope.MAX_GRADERS == 2
    assert scope.CONSTRAINTS['maximum_containers'] == 92 and scope.CONSTRAINTS['maximum_named_volumes'] == 23
    monkeypatch.setattr(scope, 'API_ROOT', tmp_path/'api')
    scope.API_ROOT.mkdir()
    preparation = scope.load(manager.reuse_preparation(plan))
    assert preparation['diagnostics_repeated'] == preparation['new_controls'] == preparation['model_calls'] == 0
    original_qualification = scope.load(recovery['prior_API_qualification'])
    schemas = scope.load(original_qualification['schema_inventory'])
    new_schemas = {**schemas, 'version': host.VERSION, 'runtime_bundle': {'CPU':'new deployment metadata only'}}
    schema_ref = write_new(tmp_path/'schemas.json', new_schemas)
    monkeypatch.setattr(host, 'SCHEMAS', Path(schema_ref['path']))
    monkeypatch.setattr(scope, 'require_allowed', lambda *_a, **_k: {})
    result = host.qualify(None, None, new_schemas)
    assert result == original_qualification and result['actual_known_input_output_tokens'] == 592
    assert host.DeepSeekRuntime.preparation_usage()['calls'] == []
    assert host.DeepSeekRuntime.preparation_usage()['new_preparation_API_calls'] == 0
    monkeypatch.setattr(host, 'QUALIFICATION', tmp_path/'no-proof.json')
    with pytest.raises(ValueError, match='no new API qualification allowance'):
        host.qualify(None, None, new_schemas)
    spec = {**launcher.specification(), 'ownership_token':'a'*32}
    argv = launcher.command(spec)
    assert argv[-2:] == [str(scope.ROOT/'tools/run_project_rerun_v120.py'),'--execute']
    assert '--unit=proworksim-v118-project.service' in argv


def test_report_keeps_own23_mean_held27_cost_and_original50_unknown_separate(tmp_path, monkeypatch):
    reporting = tool('summarize_project_rerun_v120')
    plan = scope.load(reference(scope.PLAN_FILE))
    held = scope.load(reference(scope.HELD_INVENTORY_FILE))['rows']
    ledger = tmp_path/'api-ledger.sqlite'
    host.api.BudgetLedger(ledger, max_concurrency=16)
    own, prior = plan['rows'][0], held[0]['row']
    records = [(own['slot_id'],own['condition_id'],'agent',8,2),
               (prior['slot_id'],prior['condition_id'],'agent',16,4),
               (host.NEUTRAL_SLOT,host.NEUTRAL_CONDITION,'preparation',5,1),
               ('v105:unrelated','unrelated','agent',900,100)]
    with sqlite3.connect(ledger) as db:
        for index,(slot,condition,purpose,prompt,completion) in enumerate(records):
            db.execute('INSERT INTO requests (request_id,slot_id,condition,usage_id,status,request_sha256,'
                'reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc,usage_json) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'CPU-{index}',slot,condition,purpose,'settled','a'*64,100,50,100,prompt,'CPU',
                 json.dumps({'prompt_tokens':prompt,'completion_tokens':completion,'total_tokens':prompt+completion})))
    owner = tmp_path/'api-coordinator-v120'
    owner.mkdir()
    write_new(owner/'run-summary.json', {'finished_unix':1,
        'unentered_generation':[row['slot_id'] for row in plan['rows'][1:]]})
    folder = tmp_path/'episodes'/str(own['slot_index'])
    folder.mkdir(parents=True)
    write_new(folder/'result.json', {'slot_id':own['slot_id'],'instance_id':own['instance_id'],
        'status':'closed','delivery_validation':{'submitted':False}})
    before = ledger.read_bytes()
    result = reporting.run(scope.PLAN_FILE,tmp_path)
    stage = result['groups']['PROJECT']
    assert stage['planned'] == 23 and stage['known_token_lower_bounds']['total_tokens'] == 10
    assert stage['mean_actual_tokens_complete_called_subset'] == 10
    assert stage['mean_actual_tokens_all_stage_tasks'] == 10/23
    assert stage['stage_23_accuracy_if_fully_scored'] is None
    context = result['original_50_context']
    assert context['planned_original_tasks'] == 50 and context['prior_called_held_tasks'] == 27
    assert context['complete_original_50_code_accuracy'] is None
    assert context['held_known_token_lower_bounds']['total_tokens'] == 20
    assert result['original_preparation_usage']['known_tokens'] == 6
    assert result['original_preparation_usage']['new_preparation_requests'] == 0
    assert len(json.loads((tmp_path/'reporting-v120/prior-called-held.json').read_bytes())) == 27
    assert ledger.read_bytes() == before


def test_two_distinct_trusted_integrity_faults_drain_but_not_duplicate_or_R0(tmp_path, monkeypatch):
    manager = tool('run_project_rerun_v120')
    original = scope.load(reference(scope.PLAN_FILE))['rows'][:2]
    batch = tmp_path/'runs/fixture'
    batch.mkdir(parents=True)
    monkeypatch.setattr(admission,'ROOT',tmp_path)
    plan_ref = write_new(batch/'plan.json',{'root':str(batch),'rows':original,
        'dispatch_admission':admission.declaration(batch)})
    monkeypatch.setattr(scope,'PLAN_FILE',Path(plan_ref['path']))
    monkeypatch.setattr(scope,'API_ROOT',batch/'owner')
    scope.API_ROOT.mkdir()
    gate = admission.DispatchAdmissionController(plan_ref)
    events = []
    monitor = manager.RepeatedIntegrityDrain(original,gate,lambda *a,**k: events.append((a,k)))
    quiet = write_new(batch/'quiet.json', {'quiescent':True,'cleanup_errors':[],'create_result_unknown':False})
    for index,row in enumerate(original):
        child = write_new(batch/f'child-{index}.json',{'slot_id':row['slot_id'],'condition_id':row['condition_id'],
            'arm':'PROJECT','execution_alignment':shared_strategy(),
            'managed_boundary':{'status':'execution_integrity_blocked',
                'execution_integrity_failure':{'status':'execution_integrity_error','reason':'CPU fixture'}}})
        value = {'status':'technical_unknown','slot_id':row['slot_id'],'instance_id':row['instance_id'],
            'configuration':row['configuration'],'controller_result':child,'quiescence':quiet}
        r0 = write_new(batch/f'r0-{index}.json',{**value,'status':'closed','code_resolved':False})
        monitor.observe(row,r0)
        assert gate.limit(16) == 16
        ref = write_new(batch/f'result-{index}.json',value)
        monitor.observe(row,ref)
        monitor.observe(row,ref)  # Same task cannot count twice.
        assert gate.limit(16) == (16 if index == 0 else 0)
    assert len(events) == 1 and monitor.triggered
    proof = json.loads((scope.API_ROOT/'automatic-integrity-drain.json').read_bytes())
    assert len(proof['distinct_tasks']) == 2 and proof['inflight_cancelled'] is False
    assert proof['scoring_allowed'] is True and proof['ordinary_code_failure_triggers_drain'] is False
    assert gate.annotate({'active_generation':1})['dispatch_admission']['state'] == 'draining'
