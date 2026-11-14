"""Prepare the frozen four-task × three-condition panel without Docker/API calls."""
from __future__ import annotations
from collections import Counter
import copy
import json
import os
from proworksim import software_benchmark_scope_v203_2_3 as scope
from proworksim.software_benchmark_alignment_contract_v203_2_3 import condition, validate_plan_identity
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('Entered scope cannot be prepared again')
    reserved = scope.load(reference(scope.SOURCE_PANEL_FILE))
    previous = scope.load(reference(scope.SOURCE_PLAN_FILE))
    if len(reserved['tasks']) != 4 or len(reserved['rows']) != 12 or reserved['cash_authorized_CNY'] != 130:
        raise ValueError('Exactly four frozen tasks, twelve rounds, and new CNY130 are required')
    rows, envs, sources, resources, selected = [], {}, {}, {}, []
    for ordinal, identity in enumerate(reserved['rows']):
        task, group = identity['instance_id'], identity['condition']
        env = previous['environments'][task]
        original = scope.load(env['configuration'])
        public = original['public_task']
        if any(public[k] != identity[k] for k in ('instance_id','repo','base_commit')):
            raise ValueError('Frozen task identity differs from the source environment')
        spec = condition(group)
        row = {**copy.deepcopy(identity), 'logical_index':ordinal, 'task_index':ordinal//3,
            'source_slot_id':original['source_slot_id'], 'group_id':group, 'condition_id':group,
            'organization_id':'REVIEW2', 'fixed_members':['member_001','member_002'], 'member_count':2,
            'arm':'PROJECT','execution_arm':'PROJECT','model_key':'DEEPSEEK','model':'deepseek-flash',
            'thinking':False,'provider_seed_sent':False,'replicate':0,'repeat_index':0,
            'input_plus_output_tokens':5_000_000,'generation_token_upper_bound':5_000_000,
            'budget_tokens':5_000_000,'measurement_kind':'full_verified_comparison',
            'engineering_gate':False,'automatic_retry':False}
        validate_plan_identity(row)
        selected.append(copy.deepcopy(row))
        cref = scope.retain(scope.BATCH_ROOT/'conditions'/(group+'.json'), spec)
        config = {**copy.deepcopy(original), **row, 'version':'v203.2.3-role-context-config-r1',
            'configuration':cref,'preparation_only':False,'fixed_organization':spec['fixed_organization'],
            'execution_alignment':spec['execution_strategy'],'role_context_condition':group,
            'role_context_budget_tokens':4096}
        row['configuration'] = scope.retain(scope.BATCH_ROOT/'configs'/(str(row['slot_index'])+'.json'), config)
        rows.append(row)
        envs.setdefault(task, {**copy.deepcopy(env), 'configuration':row['configuration']})
        oldq = scope.ROOT/'runs/software-benchmark-v066/v064-continuation-r3/coordinator/qualifications'/(task+'.json')
        sources[task] = {'configuration':env['configuration'],'plan':reference(scope.SOURCE_PLAN_FILE),
            'qualification':reference(oldq) if oldq.is_file() else None,
            'historical_passed_flag_does_not_establish_current_readiness':True}
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f"{role}-{row['slot_index']}"] = {
                'role':'delivery_score' if role == 'delivery-score' else role,'slot_id':row['slot_id'],
                'instance_id':task,'group_id':group,'organization_id':'REVIEW2',
                'image_id':env['image_id'] if role in {'score','delivery-score'} else env['actor_image_id'],
                'endpoint':'code' if role == 'score' else 'delivery' if role == 'delivery-score' else None}
            if role == 'delivery-score':
                resources[f"{role}-{row['slot_index']}"] .update(skip_when_no_legal_delivery=True,same_tree_can_reuse_own_code_result=True)
        for kind in ('gold','empty'):
            resources[f'control-{task}-{kind}'] = {'role':'control','instance_id':task,'patch_kind':kind,
                'image_id':env['image_id'],'endpoint':'environment_control'}
    public_qualifications = []
    for ordinal, task in enumerate(envs, 1):
        key = 'public-qualification-' + task
        resources[key] = {'role':'public_qualification','instance_id':task,'image_id':envs[task]['actor_image_id'],'endpoint':'public_task_interpreter_qualification','model_calls':0}
        public_qualifications.append({'resource_key':key,'instance_id':task,'index':ordinal,'model_calls':0})
    panel = scope.retain(scope.PANEL_FILE, {**copy.deepcopy(reserved), 'version':scope.VERSION,
        'reservation':reference(scope.SOURCE_PANEL_FILE), 'rows':selected,
        'task_ids':[t['instance_id'] for t in reserved['tasks']], 'new_independent_ledger':str(scope.LEDGER_FILE)})
    affinity = sorted(os.sched_getaffinity(0))
    if len(affinity) < 32:
        raise PermissionError('At least 32 available CPUs are needed to capture the declared pool')
    cpu = scope.retain(scope.CPU_POOL_FILE, {'version':scope.VERSION,'uid':os.getuid(),
        'cpu_ids':affinity[:32],'captured_before_run':True})
    inventory = scope.retain(scope.INVENTORY_FILE, {'version':scope.VERSION,'rows':rows,'panel':panel,
        'generation':{},'scores':{},'deliveries':{}})
    plan = {'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':panel,'matrix':panel,
        'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,'inventory':inventory,
        'constraints':scope.CONSTRAINTS,'environments':envs,'environment_sources':sources,
        'resources':resources,'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':[],'public_qualifications':public_qualifications,'training':False,'old_results_preserved':True,'new_runtime_scope':True,
        'model_calls_during_preparation':0,'dispatch_admission':declaration(scope.BATCH_ROOT),
        'engineering_gate_slot_indices':[2032300,2032301],
        'wave_policy':{'maximum_generations':2,'maximum_graders':1,'task_substitution':False,
            'all_first_calls_require_frozen_runtime_gates':True,'automatic_replay':False},
        'cash_budget_CNY':'130.00','new_ledger':str(scope.LEDGER_FILE),'old_ledgers_read_or_written':False}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE, plan),'panel':panel,'API_calls':0,'Docker_operations':0,
        'old_ledgers_read_or_written':False}


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
