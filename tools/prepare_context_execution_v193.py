"""Materialize the existing12-task,60-attempt design without using scores."""
from collections import Counter
import copy
import json
import os

from proworksim import software_benchmark_scope_v193 as scope
from proworksim.software_benchmark_alignment_contract_v193 import GROUP_IDS,condition
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_dispatch_control_v120 import declaration


def prepare():
    if (scope.API_ROOT/'execution-started.json').exists():raise ValueError('Never reprepare an entered experiment')
    claims=scope.BATCH_ROOT/'resource-claims';claims.mkdir(parents=True,exist_ok=True)
    (claims/'allocation.lock').touch(exist_ok=True)
    panel=scope.load(reference(scope.PANEL_FILE));source=scope.load(reference(scope.SOURCE_PLAN_FILE))
    cpu=scope.retain(scope.CPU_POOL_FILE,{'version':scope.VERSION,'uid':os.getuid(),
        'cpu_ids':sorted(os.sched_getaffinity(0)),'captured_before_run':True})
    specs={g:scope.retain(scope.BATCH_ROOT/'conditions'/(g+'.json'),condition(g)) for g in GROUP_IDS}
    tasks={t['instance_id']:t for t in panel['tasks']}
    rows=[];environments={};resources={}
    for logical,selected in enumerate(panel['rows']):
        tid=selected['instance_id'];group=selected['condition'];index=19300+logical
        env=source['environments'][tid];original=scope.load(env['configuration']);task=tasks[tid]
        if any(original['public_task'][k]!=task[k] for k in ('instance_id','repo','base_commit','problem_statement')):
            raise ValueError('Frozen public task changed')
        if env['actor_image_id']!=task['actor_image_id']:raise ValueError('Actor image changed')
        spec=condition(group);seed=selected['framework_seed']
        row={**copy.deepcopy(selected),'slot_id':f'v193:{tid}:{spec["condition_id"]}:{seed}',
            'source_slot_id':original['source_slot_id'],'slot_index':index,'logical_index':logical,'seed':seed,
            'group_id':group,'organization_id':'S1','context_condition':group,'member_count':1,
            'fixed_members':['member_001'],'condition_id':spec['condition_id'],'model_key':'DEEPSEEK',
            'model':'deepseek-flash','thinking':False,'arm':'PROJECT','execution_arm':'PROJECT',
            'input_plus_output_tokens':5_000_000,'generation_token_upper_bound':5_000_000,
            'measurement_kind':'full_verified_comparison','replicate':selected['repeat_index']}
        config={**copy.deepcopy(original),**row,'version':'v193-context-pilot-config-r1',
            'configuration':specs[group],'preparation_only':False,'fixed_organization':spec['fixed_organization'],
            'execution_alignment':spec['execution_strategy']}
        row['configuration']=scope.retain(scope.BATCH_ROOT/'configs'/(str(index)+'.json'),config)
        rows.append(row);environments.setdefault(tid,{**copy.deepcopy(env),'configuration':row['configuration']})
        for role in ('actor','controller','volume','score','delivery-score'):
            resources[f'{role}-{index}']={'role':'delivery_score' if role=='delivery-score' else role,
                'slot_id':row['slot_id'],'instance_id':tid,'group_id':group,'organization_id':'S1',
                'image_id':env['image_id'] if role in {'score','delivery-score'} else env['actor_image_id'],
                'endpoint':'code' if role=='score' else 'delivery' if role=='delivery-score' else None}
    for tid,env in environments.items():
        for kind in ('gold','empty'):
            resources[f'control-{tid}-{kind}']={'role':'control','instance_id':tid,'patch_kind':kind,
                'image_id':env['image_id'],'endpoint':'environment_control'}
    diagnostics=[]
    for n,group in enumerate(GROUP_IDS,1):
        row=next(r for r in rows if r['group_id']==group)
        diagnostics.append({'index':n,'arm':'PROJECT','organization_id':'S1','group_id':group,
            'slot_id':row['slot_id'],'instance_id':row['instance_id'],'model_calls':0})
        for role in ('actor','controller','volume'):
            resources[f'diagnostic-{n}-{role}']={**resources[f'{role}-{row["slot_index"]}'],
                'diagnostic':True,'diagnostic_index':n,'execution_arm':'PROJECT','model_calls':0}
    inventory=scope.retain(scope.INVENTORY_FILE,{'version':scope.VERSION,'rows':rows,'panel':reference(scope.PANEL_FILE),
        'generation':{},'scores':{},'deliveries':{}})
    plan={'version':scope.VERSION,'root':str(scope.BATCH_ROOT),'panel':reference(scope.PANEL_FILE),
        'matrix':reference(scope.PANEL_FILE),'rows':rows,'generation_rows':rows,'host_cpu_pool':cpu,
        'inventory':inventory,'constraints':scope.CONSTRAINTS,'environments':environments,'resources':resources,
        'resource_role_counts':dict(Counter(r['role'] for r in resources.values())),'diagnostics':diagnostics,
        'training':False,'new_runtime_scope':True,'model_calls_during_preparation':0,
        'dispatch_admission':declaration(scope.BATCH_ROOT)}
    scope.validate_plan(plan)
    return scope.retain(scope.PLAN_FILE,plan)


if __name__=='__main__':print(json.dumps(prepare()))
