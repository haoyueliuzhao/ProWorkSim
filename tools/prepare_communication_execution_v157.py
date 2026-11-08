"""Materialize frozen24xC0/C1/C2 identities; no API, Docker or service action."""
from __future__ import annotations
from collections import Counter
import copy
import json
import os
from proworksim import software_benchmark_scope_v157 as scope
from proworksim.software_benchmark_alignment_contract_v157 import GROUP_IDS, condition
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration

def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():
        raise PermissionError('An entered experiment cannot be prepared again')
    panel=scope.load(reference(scope.PANEL_FILE)); previous=scope.load(reference(scope.SOURCE_PLAN_FILE))
    cpu=scope.retain(scope.CPU_POOL_FILE,{'version':scope.VERSION,'uid':os.getuid(),
        'cpu_ids':sorted(os.sched_getaffinity(0)),'captured_before_run':True})
    conditions={g:scope.retain(scope.BATCH_ROOT/'conditions'/(g+'.json'),condition(g)) for g in GROUP_IDS}
    tasks={t['instance_id']:t for t in panel['tasks']}
    rows,resources,environments,sources=[],{},{},{}
    for selected in panel['rows']:
        task=selected['instance_id'];group=selected['condition'];index=15700+selected['logical_index']
        env=previous['environments'][task];original=scope.load(env['configuration']); public=tasks[task]
        for k in ('instance_id','repo','base_commit','problem_statement'):
            if original['public_task'][k]!=public[k]: raise ValueError('Frozen public task differs: '+task)
        if (env['actor_image_id']!=public['actor_image_identity'] or
            {k:original['public_test_entry'][k] for k in public['public_test']}!=public['public_test']):
            raise ValueError('Frozen actor image/public test changed: '+task)
        spec=condition(group)
        row={**copy.deepcopy(selected),'slot_id':f'v157:{task}:REVIEW2_{group}:{selected["seed"]}',
            'source_slot_id':original['source_slot_id'],'source_preparation_slot_id':selected['slot_id'],
            'slot_index':index,'group_id':group,'organization_id':'REVIEW2','communication_condition':group,
            'member_count':2,'condition_id':spec['condition_id'],'model_key':'DEEPSEEK',
            'model':'deepseek-flash','thinking':False,'arm':'PROJECT','execution_arm':'PROJECT',
            'input_plus_output_tokens':5_000_000,'generation_token_upper_bound':5_000_000,
            'measurement_kind':'full_verified_comparison','replicate':0}
        config={**copy.deepcopy(original),**row,'version':'v157-communication-pilot-config-r1',
            'configuration':conditions[group],'preparation_only':False,
            'fixed_organization':spec['fixed_organization'],'execution_alignment':spec['execution_strategy']}
        row['configuration']=scope.retain(scope.BATCH_ROOT/'configs'/(str(index)+'.json'),config)
        rows.append(row)
        environments.setdefault(task,{**copy.deepcopy(env),'configuration':row['configuration']})
        sources.setdefault(task,{'configuration':env['configuration'],'plan':reference(scope.SOURCE_PLAN_FILE),
            'qualification':reference(scope.ROOT/'runs/software-benchmark-v066/v064-continuation-r3/coordinator/qualifications'/(task+'.json'))
            if (scope.ROOT/'runs/software-benchmark-v066/v064-continuation-r3/coordinator/qualifications'/(task+'.json')).is_file() else None})
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f'{role}-{index}']={'role':'delivery_score' if role=='delivery-score' else role,
                'slot_id':row['slot_id'],'instance_id':task,'group_id':group,'organization_id':'REVIEW2',
                'image_id':env['image_id'] if role in {'score','delivery-score'} else env['actor_image_id'],
                'endpoint':'code' if role=='score' else 'delivery' if role=='delivery-score' else None}
            if role=='delivery-score':
                resources[f'{role}-{index}'].update(skip_when_no_legal_delivery=True,same_tree_can_reuse_own_code_result=True)
    for task in tasks:
        for kind in ('gold','empty'):
            resources[f'control-{task}-{kind}']={'role':'control','instance_id':task,'patch_kind':kind,
                'image_id':environments[task]['image_id'],'endpoint':'environment_control',
                'skip_if_exact_unchanged_qualification_proven':True}
    # Four qualified, never-entered reservations are reassigned to the two
    # concrete environment repairs; the original48-control ceiling is retained.
    for task in ('astropy__astropy-14369','sympy__sympy-17318'):
        for kind in ('gold','empty'):
            del resources[f'control-{task}-{kind}']
    for task in ('psf__requests-1142','psf__requests-1724'):
        for kind in ('gold','empty'):
            key=f'control-recovery-r2-{task}-{kind}'
            resources[key]={**resources[f'control-{task}-{kind}'],
                'recovery_of':f'control-{task}-{kind}',
                'reason':'initial_environment_baseline_or_python2_observation_repair'}
    diagnostics=[]
    for index,group in enumerate(GROUP_IDS,1):
        row=next(r for r in rows if r['group_id']==group)
        diagnostics.append({'index':index,'arm':'PROJECT','organization_id':'REVIEW2','group_id':group,
            'slot_id':row['slot_id'],'instance_id':row['instance_id'],'model_calls':0,
            'purpose':'actual_sdk_actor_public_test_and_condition_identity_export'})
        for role in ('actor','controller','volume'):
            resources[f'diagnostic-{index}-{role}']={**resources[f'{role}-{row["slot_index"]}'],
                'diagnostic':True,'diagnostic_index':index,'execution_arm':'PROJECT','model_calls':0}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,
        'panel':reference(scope.PANEL_FILE),'generation':{},'scores':{},'deliveries':{}})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':reference(scope.PANEL_FILE),
        'matrix':reference(scope.PANEL_FILE),'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,
        'inventory':inventory,'constraints':scope.CONSTRAINTS,'environments':environments,
        'environment_sources':sources,'resources':resources,
        'resource_role_counts':dict(Counter(v['role'] for v in resources.values())),
        'diagnostics':diagnostics,'training':False,'old_results_preserved':True,
        'new_runtime_scope':True,'model_calls_during_preparation':0,
        'dispatch_admission':declaration(scope.BATCH_ROOT),
        'wave_policy':{'waves':2,'tasks_per_wave':12,'episodes_per_wave':36,
            'gate_basis':['physical_request_capture','actual_usage','execution_integrity'],
            'score_based_selection_or_tuning':False,'second_wave_requires_actual_first_wave_gate':True}}
    scope.validate_plan(plan)
    return {'plan':scope.retain(scope.PLAN_FILE,plan),'API_calls':0,'Docker_operations':0,
        'execution_authorized':False}

if __name__=='__main__': print(json.dumps(prepare(),ensure_ascii=False))
