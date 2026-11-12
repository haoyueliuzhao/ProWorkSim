"""New physical identities for the same twelve zero-request model attempts."""
from __future__ import annotations
from collections import Counter
import copy
import json
import os
import sqlite3
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_1_r2 as scope
from proworksim import software_benchmark_scope_v203_2_1 as previous_scope
from proworksim.software_benchmark_alignment_contract_v203_2_1 import validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_benchmark_dispatch_control_v120 import declaration

PENDING=('psf__requests-2317','pylint-dev__pylint-4661')


def previous_zero_request_evidence():
    prior=scope.PREVIOUS_BATCH_ROOT
    if list((prior/'resource-claims').glob('active-*.json')):
        raise PermissionError('Prior owned resources must be released')
    released=reference(prior/'api-coordinator/coordinator-capacity-released.json')
    if scope.load(released).get('released') is not True:raise PermissionError('Prior coordinator lease is not released')
    quiet=[]
    for index in (2032100,2032101):
        ref=reference(prior/'episodes'/str(index)/'quiescence.json');q=scope.load(ref)
        if (q.get('quiescent') is not True or q.get('all_owned_objects_removed') is not True
            or q.get('cleanup_errors')!=[] or q.get('create_result_unknown') is not False):
            raise PermissionError('Prior attempted volume identity is not safely cleaned')
        quiet.append(ref)
    with sqlite3.connect(scope.LEDGER_FILE.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON');count=db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
        admissions=[dict(zip(('slot_id','state'),r)) for r in db.execute('SELECT slot_id,state FROM team_admissions ORDER BY slot_id')]
    if count!=0:raise PermissionError('Same logical attempt may redeploy only before any provider request')
    return {'provider_request_count':count,'ledger_path':str(scope.LEDGER_FILE),
        'prior_closed_admissions':admissions,'prior_coordinator_released':released,'prior_episode_quiescence':quiet,
        'cash_ledger_not_modified':True,'prior_failures_not_model_failures':True,
        'admissions_recovery_must_be_explicit_new_API_binding':True}


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():raise PermissionError('Never reprepare an entered deployment')
    evidence=previous_zero_request_evidence();old_plan=scope.load(reference(previous_scope.PLAN_FILE))
    old_panel=scope.load(reference(previous_scope.PANEL_FILE))
    chosen=[]
    for ordinal,old in enumerate(old_panel['rows']):
        row=copy.deepcopy(old);row['slot_index']=2032200+ordinal;validate_plan_identity(row);chosen.append(row)
    panel={**copy.deepcopy(old_panel),'version':scope.VERSION,'rows':chosen,
        'physical_redeployment_of':reference(previous_scope.PANEL_FILE),
        'engineering_gate_slot_indices':[2032200,2032201],
        'same_existing_150_CNY_ledger':str(scope.LEDGER_FILE),'additional_budget_CNY':'0.00',
        'logical_model_attempts_added':0,'same_task_seed_slot_id_and_model_policy':True}
    panel.pop('new_independent_ledger',None)
    panel_ref=scope.retain(scope.PANEL_FILE,panel)
    cpu=scope.retain(scope.CPU_POOL_FILE,{'version':scope.VERSION,'uid':os.getuid(),
        'cpu_ids':sorted(os.sched_getaffinity(0)),'captured_before_run':True})
    old_by_id={r['slot_id']:r for r in old_plan['rows']};rows=[];envs={};sources={};resources={}
    for selected in chosen:
        row=copy.deepcopy(selected);old=old_by_id[row['slot_id']];original=scope.load(old['configuration'])
        config={**copy.deepcopy(original),**row,'version':'v203.2.1-passive-zero-API-physical-config-r2'}
        # Conditions and public execution fields remain their original exact bytes.
        row['configuration']=scope.retain(scope.BATCH_ROOT/'configs'/(str(row['slot_index'])+'.json'),config)
        rows.append(row);task=row['instance_id'];index=row['slot_index'];env=old_plan['environments'][task]
        envs[task]={**copy.deepcopy(env),'configuration':row['configuration']}
        sources[task]={**copy.deepcopy(old_plan['environment_sources'][task]),
            'previous_deployment_configuration':old['configuration'],'previous_deployment_plan':reference(previous_scope.PLAN_FILE)}
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f'{role}-{index}']={**copy.deepcopy(old_plan['resources'][f'{role}-{old["slot_index"]}'])}
        if task in PENDING:
            for kind in ('gold','empty'):
                resources[f'control-{task}-{kind}']={**copy.deepcopy(old_plan['resources'][f'control-{task}-{kind}'])}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,'panel':panel_ref,
        'generation':{},'scores':{},'deliveries':{}})
    evidence_ref=scope.retain(scope.ARTIFACT_ROOT/'deployment-preparation-r2/zero-provider-request-and-cleanup.json',evidence)
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':panel_ref,'matrix':panel_ref,
        'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,'inventory':inventory,
        'constraints':scope.CONSTRAINTS,'environments':envs,'environment_sources':sources,
        'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':[],'training':False,'old_results_preserved':True,'new_runtime_scope':True,
        'model_calls_during_preparation':0,'dispatch_admission':declaration(scope.BATCH_ROOT),
        'engineering_gate_slot_indices':[2032200,2032201],
        'wave_policy':copy.deepcopy(old_plan['wave_policy']),
        'previous_execution_plan':reference(previous_scope.PLAN_FILE),'zero_request_redeployment_evidence':evidence_ref,
        'qualification_reuse_from_previous':{'required_strict_environment_equivalence':True,
            'tasks':[r['instance_id'] for r in rows if r['instance_id'] not in PENDING],
            'source_qualification_directory':str(previous_scope.COORDINATOR_ROOT/'qualifications'),
            'current_pending_tasks':list(PENDING),'previous_passed_flag_alone_is_not_authority':True},
        'same_existing_cash_ledger':str(scope.LEDGER_FILE),'additional_cash_CNY':'0.00',
        'new_model_attempts':0,'new_physical_actor_controller_pairs':12,'new_physical_volumes':12,
        'model_visible_controller_and_bundle_reused_without_changes':True}
    scope.validate_plan(plan)
    result={'plan':scope.retain(scope.PLAN_FILE,plan),'panel':panel_ref,'zero_request_evidence':evidence_ref,
        'model_calls':0,'Docker_operations':0,'cash_ledger_changes':0,'new_cash_budget_CNY':'0.00',
        'new_physical_indices':[2032200,2032211],'engineering_gate_indices':[2032200,2032201]}
    scope.retain(scope.ARTIFACT_ROOT/'deployment-preparation-r2/summary.json',result);return result


if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False))
