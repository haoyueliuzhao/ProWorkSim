"""Prepare the fixed twelve-task REVIEW2 plan using local files only."""
from __future__ import annotations
from collections import Counter
import argparse
import copy
import json
import os
from proworksim import software_benchmark_scope_v203_2_1 as scope
from proworksim.software_benchmark_alignment_contract_v203_2_1 import condition, validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration

SEED_BASE = 202611122032100


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('An entered experiment cannot be prepared again')
    reserved = scope.load(reference(scope.SOURCE_PANEL_FILE))
    previous = scope.load(reference(scope.SOURCE_PLAN_FILE))
    if len(reserved['tasks']) != 12 or len({r['repo'] for r in reserved['tasks']}) != 10:
        raise ValueError('The original twelve identities and ten repositories must remain fixed')
    spec = condition('REVIEW2')
    public_tasks, selected_rows = [], []
    for ordinal, identity in enumerate(reserved['tasks']):
        task = identity['instance_id']; env = previous['environments'][task]
        config = scope.load(env['configuration']); public = config['public_task']
        if any(public[k] != identity[k] for k in ('instance_id','repo','base_commit')):
            raise ValueError('Original reserved identity differs from frozen public task')
        seed = SEED_BASE + ordinal; index = 2032100 + ordinal
        row = {'logical_index':ordinal,'task_index':ordinal,'slot_index':index,
            'instance_id':task,'repo':identity['repo'],'seed':seed,
            'slot_id':f"v203.2.1:{task}:{spec['condition_id']}:{seed}",
            'source_slot_id':config['source_slot_id'],'group_id':'REVIEW2','organization_id':'REVIEW2',
            'condition_id':spec['condition_id'],'fixed_members':['member_001','member_002'],'member_count':2,
            'arm':'PROJECT','execution_arm':'PROJECT','model_key':'DEEPSEEK','model':'deepseek-flash',
            'thinking':False,'provider_seed_sent':False,'replicate':0,'repeat_index':0,
            'input_plus_output_tokens':5_000_000,'generation_token_upper_bound':5_000_000,
            'measurement_kind':'full_verified_comparison','engineering_gate':ordinal<2,
            'automatic_retry':False}
        validate_plan_identity(row); selected_rows.append(row); public_tasks.append(copy.deepcopy(public))
    panel = {'version':scope.VERSION,'reservation':reference(scope.SOURCE_PANEL_FILE),
        'tasks':copy.deepcopy(reserved['tasks']),'task_ids':[r['instance_id'] for r in reserved['tasks']],
        'public_tasks':public_tasks,'rows':selected_rows,'task_count':12,'repository_count':10,
        'cash_budget_CNY':'150.00','new_independent_ledger':str(scope.LEDGER_FILE),
        'organization_id':'REVIEW2','team_token_limit':5_000_000,'total_token_upper_bound':60_000_000,
        'engineering_gate_slot_indices':[2032100,2032101],'engineering_gate_included_in_formal_12':True,
        'second_wave_requires_first_two_capture_and_execution_gate':True,
        'task_replacement_or_score_based_selection':False,'training':False,
        'models_prompts_tools_permissions_communication_summaries_organization_unchanged':True}
    panel_ref = scope.retain(scope.PANEL_FILE,panel)
    cpu = scope.retain(scope.CPU_POOL_FILE,{'version':scope.VERSION,'uid':os.getuid(),
        'cpu_ids':sorted(os.sched_getaffinity(0)),'captured_before_run':True})
    condition_ref = scope.retain(scope.BATCH_ROOT/'conditions/REVIEW2.json',spec)
    rows,resources,environments,sources = [],{},{},{}
    for selected in selected_rows:
        row=copy.deepcopy(selected); task=row['instance_id']; index=row['slot_index']
        env=previous['environments'][task]; original=scope.load(env['configuration'])
        config={**copy.deepcopy(original),**row,'version':'v203.2.1-passive-pilot-config-r1',
            'configuration':condition_ref,'preparation_only':False,
            'fixed_organization':spec['fixed_organization'],'execution_alignment':spec['execution_strategy']}
        row['configuration']=scope.retain(scope.BATCH_ROOT/'configs'/(str(index)+'.json'),config);rows.append(row)
        environments[task]={**copy.deepcopy(env),'configuration':row['configuration']}
        old_qualification=scope.ROOT/'runs/software-benchmark-v066/v064-continuation-r3/coordinator/qualifications'/(task+'.json')
        sources[task]={'configuration':env['configuration'],'plan':reference(scope.SOURCE_PLAN_FILE),
            'qualification':reference(old_qualification) if old_qualification.is_file() else None,
            'historical_evidence_does_not_establish_current_readiness':True}
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f'{role}-{index}']={'role':'delivery_score' if role=='delivery-score' else role,
                'slot_id':row['slot_id'],'instance_id':task,'group_id':'REVIEW2','organization_id':'REVIEW2',
                'image_id':env['image_id'] if role in {'score','delivery-score'} else env['actor_image_id'],
                'endpoint':'code' if role=='score' else 'delivery' if role=='delivery-score' else None}
            if role=='delivery-score':resources[f'{role}-{index}'].update(
                skip_when_no_legal_delivery=True,same_tree_can_reuse_own_code_result=True)
        for kind in ('gold','empty'):
            resources[f'control-{task}-{kind}']={'role':'control','instance_id':task,'patch_kind':kind,
                'image_id':env['image_id'],'endpoint':'environment_control'}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,
        'panel':panel_ref,'generation':{},'scores':{},'deliveries':{}})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':panel_ref,'matrix':panel_ref,
        'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,'inventory':inventory,
        'constraints':scope.CONSTRAINTS,'environments':environments,'environment_sources':sources,
        'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':[],'training':False,'old_results_preserved':True,'new_runtime_scope':True,
        'model_calls_during_preparation':0,'dispatch_admission':declaration(scope.BATCH_ROOT),
        'engineering_gate_slot_indices':[2032100,2032101],
        'wave_policy':{'first_wave':2,'second_wave':10,'first_wave_included_in_12':True,
            'gate_basis':['actual_provider_request_response_usage_capture','observer_noninterference',
                         'source_version_consistency','normal_execution_and_cleanup'],
            'score_based_selection_or_tuning':False,'no_automatic_replay':True}}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE,plan),'panel':panel_ref,'API_calls':0,
            'Docker_operations':0,'execution_authorized':False,'old_ledgers_read_or_written':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',action='store_true',help='Also prepare the new local SDK bundle; no Docker/API')
    args=parser.parse_args(); result=prepare()
    if args.bundle:
        from proworksim.software_benchmark_sdk_bundle_v203_2_1 import prepare_bundle
        result['bundle']=prepare_bundle()
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
