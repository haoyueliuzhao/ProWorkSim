"""Prepare the same50 tasks x five fixed organizations, with no external actions."""
from __future__ import annotations

from collections import Counter
import copy
import json
import os

from proworksim import software_benchmark_scope_v131 as scope
from proworksim.software_benchmark_alignment_contract_v131 import condition, GROUP_IDS, VERSION
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration

SEED_BASE = 20261104013100


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('Never reprepare an entered experiment')
    original = scope.load(reference(scope.SOURCE_PANEL_FILE))
    prior = scope.load(reference(scope.SOURCE_PLAN_FILE))
    tasks = original['task_ids']
    if len(tasks) != 50 or len(set(tasks)) != 50 or len(prior['environments']) != 50:
        raise ValueError('The original prespecified50 task identities are required')
    by_task = {r['instance_id']: r for r in prior['rows']}
    scope.BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    cpu = scope.retain(scope.CPU_POOL_FILE, {'version':VERSION,'uid':os.getuid(),
        'cpu_ids':sorted(os.sched_getaffinity(0)),'captured_before_run':True})
    conditions = {g:scope.retain(scope.BATCH_ROOT/'conditions'/(g+'.json'),condition(g)) for g in GROUP_IDS}
    rows, resources, environments, sources = [], {}, {}, {}
    for task_index, task in enumerate(tasks):
        original_row = by_task[task]
        old_config = scope.load(original_row['configuration'])
        env = prior['environments'][task]
        for group_index, group in enumerate(GROUP_IDS):
            spec = condition(group)
            index = 9000 + task_index*5 + group_index
            seed = SEED_BASE + task_index
            slot = f"v131:{task}:{spec['condition_id']}:{seed}"
            row = {'logical_index':task_index*5+group_index,'slot_index':index,'task_index':task_index,
                'slot_id':slot,'source_slot_id':f'v054-PROJECT-{task}','instance_id':task,
                'repo':old_config['public_task']['repo'],'group_id':group,'organization_id':group,
                'condition_id':spec['condition_id'],'fixed_members':spec['fixed_members'],
                'member_count':spec['member_count'],'model_key':'DEEPSEEK','model':'deepseek-flash',
                'arm':'PROJECT','execution_arm':'PROJECT','thinking':False,'seed':seed,
                'provider_seed_sent':False,'replicate':0,'repeat_index':0,
                'input_plus_output_tokens':5_000_000,'budget_tokens':5_000_000,
                'generation_token_upper_bound':5_000_000,'budget_scope':'whole_team_including_summaries',
                'measurement_kind':'full_verified_comparison','panel_kind':'fixed_organization_comparison'}
            config = {**copy.deepcopy(old_config), **row,
                'version':'v131-private-fixed-organization-config-r1',
                'configuration':conditions[group], 'preparation_only':False,
                'fixed_organization':spec['fixed_organization'], 'execution_alignment':spec['execution_strategy']}
            row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/(str(index)+'.json'),config)
            rows.append(row)
            for role in ('actor','controller','volume','score','delivery-score'):
                key = role+'-'+str(index)
                value = {'role':'delivery_score' if role=='delivery-score' else role,
                    'slot_id':slot,'instance_id':task,'group_id':group,'organization_id':group,
                    'image_id':env['image_id'] if role in ('score','delivery-score') else env['actor_image_id'],
                    'endpoint':'code' if role=='score' else 'delivery' if role=='delivery-score' else None}
                if role=='delivery-score':
                    value.update(skip_when_no_legal_delivery=True,same_tree_can_reuse_own_code_result=True)
                resources[key]=value
            environments.setdefault(task, {**copy.deepcopy(env),'configuration':row['configuration']})
        sources[task] = copy.deepcopy(prior['environment_sources'][task])
    for task in sorted(scope.original.TLS_TASKS):
        for kind in ('gold','empty'):
            resources[f'control-v131-{task}-{kind}']={'role':'control','instance_id':task,
                'patch_kind':kind,'image_id':environments[task]['image_id'],'endpoint':'environment_control'}
    chosen = next(r for r in rows if r['instance_id']=='psf__requests-2931' and r['organization_id']=='CHIEF')
    diagnostic = {'index':1,'arm':'PROJECT','organization_id':'CHIEF','group_id':'CHIEF',
        'slot_id':chosen['slot_id'],'instance_id':chosen['instance_id'],'model_calls':0}
    for role in ('actor','controller','volume'):
        resources[f'diagnostic-1-{role}']={**resources[f"{role}-{chosen['slot_index']}"],
            'diagnostic':True,'diagnostic_index':1,'execution_arm':'PROJECT','model_calls':0}
    panel = {'version':VERSION,'scope':'same50_five_fixed_organizations',
        'task_ids':tasks,'repository_counts':original['repository_counts'],
        'source_panel':reference(scope.SOURCE_PANEL_FILE),
        'selection':'All original prespecified50 task identities; no score-based selection',
        'group_ids':list(GROUP_IDS),'rows':rows,'planned_distinct_tasks':50,'planned_groups':5,
        'planned_episodes':250,'extra_repeats':0,'cash_budget_by_group_CNY':{g:'100.00' for g in GROUP_IDS},
        'total_cash_upper_bound_CNY':'500.00','ledgers':{g:str(p) for g,p in scope.LEDGER_FILES.items()},
        'budget_transfer_between_groups':False,'old_ledger_reused':False,
        'team_token_budget':5_000_000,'aggregate_input_output_token_upper_bound':1_250_000_000,
        'token_upper_bound_is_expected_usage':False,'budget_guarantees_completion':False,
        'seed_base':SEED_BASE,'seed_rule':'Same task index across organizations; provider seed not sent',
        'order':'Original task order, each task five groups; group-local FIFO and global fair admission',
        'independent_initial_states':True,'historical_workspaces_or_feedback_reused':False,
        'selection_uses_previous_scores':False,'hidden_fields_or_scores_to_actor':False,
        'automatic_replay':False,'training':False,'full_500_benchmark_score_claim':False,
        'runtime_authorized_by_this_plan_file':False,'preparation_operations':{'API':0,'Docker':0,'GPU':0}}
    panel_ref=scope.retain(scope.PANEL_FILE,panel)
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':VERSION,'rows':rows,'panel':panel_ref,
        'generation':{},'scores':{},'deliveries':{},'old_results_preserved':True})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'rows':rows,'panel':panel_ref,'matrix':panel_ref,
        'host_cpu_pool':cpu,'inventory':inventory,'constraints':scope.CONSTRAINTS,
        'environments':environments,'environment_sources':sources,'resources':resources,
        'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':[diagnostic],'historical_results_preserved':True,'training':False,
        'model_calls_during_preparation':0,'new_runtime_scope':True,
        'dispatch_admission':declaration(scope.BATCH_ROOT)}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE,plan),'panel':panel_ref,
            'API_calls':0,'Docker_operations':0,'execution_authorized':False}


if __name__=='__main__':
    print(json.dumps(prepare(),ensure_ascii=False))
