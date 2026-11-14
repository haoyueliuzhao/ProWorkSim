"""Prepare distinct recovery attempts, preserving all paid predecessor records."""
from __future__ import annotations
from collections import Counter
import copy,json,sqlite3
from proworksim import software_benchmark_scope_v203_2_3_r3 as scope
from proworksim import software_benchmark_alignment_contract_v203_2_3_r3 as alignment
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    old_plan_ref=reference(scope.PREVIOUS_BATCH_ROOT/'execution-plan.json')
    old=scope.load(old_plan_ref);rows=[];selected=[];resources={};environments={};mapping=[]
    with sqlite3.connect((scope.PREVIOUS_BATCH_ROOT/'ledgers/pilot.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        calls=dict(db.execute('SELECT slot_id,COUNT(*) FROM requests GROUP BY slot_id'))
        if not db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone():raise PermissionError('Parent spending must already be retired')
    for ordinal,prior in enumerate(old['rows']):
        row=copy.deepcopy(prior);row.pop('configuration')
        row['original_slot_id']=prior['slot_id'];row['slot_id']=f"{alignment.RUN_VERSION}:{row['instance_id']}:{row['group_id']}:{row['seed']}"
        row['slot_index']=2032500+ordinal
        row['engineering_gate']=ordinal<2
        row['attempt_kind']='independent_retest_after_technical_failure' if calls.get(prior['slot_id'],0) else 'first_paid_attempt_after_environment_preparation'
        row['prior_paid_attempt_count']=int(bool(calls.get(prior['slot_id'],0)))
        row['prior_provider_calls']=calls.get(prior['slot_id'],0)
        row['continuation_of_private_SDK_state']=False
        alignment.validate_plan_identity(row);selected.append(copy.deepcopy(row))
        spec=alignment.condition(row['group_id']);cref=scope.retain(scope.BATCH_ROOT/'conditions'/(row['group_id']+'.json'),spec)
        config={**copy.deepcopy(scope.load(prior['configuration'])),**row,
                'version':'v203.2.3-independent-recovery-task-config-r3','configuration':cref,
                'execution_alignment':spec['execution_strategy']}
        row['configuration']=scope.retain(scope.BATCH_ROOT/'configs'/(str(row['slot_index'])+'.json'),config);rows.append(row)
        task=row['instance_id'];environments.setdefault(task,{**copy.deepcopy(old['environments'][task]),'configuration':row['configuration']})
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f'{role}-{row["slot_index"]}']={**copy.deepcopy(old['resources'][f'{role}-{prior["slot_index"]}']),'slot_id':row['slot_id']}
        mapping.append({'slot_id':row['slot_id'],'original_slot_id':prior['slot_id'],'instance_id':task,'condition':row['condition'],'seed':row['seed'],
            'attempt_kind':row['attempt_kind'],'prior_provider_calls':row['prior_provider_calls'],'prior_result':reference(scope.PARENT_RUN_ROOT/'episodes'/str(prior['slot_index'])/'result.json') if row['prior_provider_calls'] else None})
    panel=scope.retain(scope.PANEL_FILE,{'version':scope.VERSION,'rows':selected,'tasks':scope.load(reference(scope.SOURCE_PANEL_FILE))['tasks'],
        'task_ids':list(environments),'task_count':4,'planned_rounds':12,'original_panel':reference(scope.ARTIFACT_ROOT/'execution-panel-r1/panel.json'),
        'original_plan':old_plan_ref,'attempt_mapping':mapping,'not_model_state_resume':True,'child_cap_CNY':scope.CASH_CAP_CNY,'handoff':reference(scope.HANDOFF_FILE)})
    cpu=scope.retain(scope.CPU_POOL_FILE,scope.load(reference(scope.PARENT_RUN_ROOT/'host-cpu-pool.json')))
    first=next(r for r in rows if r['instance_id']=='astropy__astropy-13033' and r['group_id']=='K1');diagnostic={'index':1,'slot_id':first['slot_id'],'instance_id':first['instance_id'],'organization_id':'REVIEW2','group_id':first['group_id'],'model_calls':0}
    for role in ('actor','controller','volume'):
        resources[f'diagnostic-1-{role}']={**copy.deepcopy(resources[f'{role}-{first["slot_index"]}']),'diagnostic':True,'diagnostic_index':1}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,'generation':{},'scores':{},'deliveries':{}})
    plan={**copy.deepcopy(old),'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':panel,'matrix':panel,
        'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,'inventory':inventory,'constraints':scope.CONSTRAINTS,
        'environments':environments,'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'public_qualifications':[],'diagnostics':[diagnostic],'dispatch_admission':declaration(scope.BATCH_ROOT),
        'engineering_gate_slot_indices':[2032500,2032501],'cash_budget_CNY':scope.CASH_CAP_CNY,'new_ledger':str(scope.LEDGER_FILE),
        'additional_budget_CNY':'0.00','cumulative_authorized_CNY':'130.00','handoff':reference(scope.HANDOFF_FILE),
        'wave_policy':{'first_wave':2,'first_wave_included_in_twelve':True,'gate':'source_identity_usage_and_owned_closure_only','code_score_based_selection':False,'ordinary_task_failure_blocks_others':False,'shared_SDK_integrity_failure':'drain_new_admissions_without_cancelling_entered_work'},
        'attempt_mapping':mapping,'original_primary_attempts_preserved':True,'new_independent_attempts':9,'first_paid_attempts':3}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE,plan),'panel':panel,'model_calls':0,'new_budget_CNY':'0.00'}

if __name__=='__main__':print(json.dumps(prepare()))
