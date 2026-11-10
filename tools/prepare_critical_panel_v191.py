"""Select one task per Verified repository without reading scores or patches."""
import json,random
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_critical_v191 import RULES

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v191/full-task-design-r1'
GROUPS=('M0','M1-5','M1-10','M1-5K')
SELECTION_SEED=20261110191
ORDER_SEED=20261110192
REPEAT_SEED=20261110193

def read(path):return json.loads((ROOT/path).read_bytes())
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'plan.json').exists():raise ValueError('Never silently redraw a fixed panel')
    old=read('artifacts/software-benchmark-v180/full-task-design-r1/plan.json')
    pool=read('artifacts/software-benchmark-v054/source/public-tasks.json')
    probes=read('runs/software-benchmark-v175/context-replay-r1/plan.json')
    excluded=set(old['task_ids']);offline_tasks={p['instance_id'] for p in probes['rows']}
    grouped=defaultdict(list)
    for task in sorted(pool,key=lambda x:x['instance_id']):
        if task['instance_id'] not in excluded:grouped[task['repo']].append(task)
    assert len(grouped)==12 and sum(map(len,grouped.values()))==488
    registry={e['instance_id']:e for e in read('config/v054-public-test-registry.json')['entries']}
    rng=random.Random(SELECTION_SEED);selected=[]
    for repo in sorted(grouped):
        candidates=[t for t in grouped[repo] if t['instance_id'] not in offline_tasks] or grouped[repo]
        task=rng.choice(candidates);entry=registry[task['instance_id']]
        selected.append({**task,'actor_image_id':entry['source_identity']['actor_image_id'],
            'public_test_entry':{k:entry[k] for k in ('cwd','argv','public_python','baseline_mapping')},
            'not_in_v181_panel':True,'in_old48_offline_prototype':task['instance_id'] in offline_tasks,
            'historically_exposed':True,'fresh_environment_control_done':False})
    order=random.Random(ORDER_SEED);order.shuffle(selected)
    repeats=random.Random(REPEAT_SEED).sample(selected,6);repeat_ids={t['instance_id'] for t in repeats}
    orders=[]
    for n in range(3):
        base=list(GROUPS);order.shuffle(base);rotations=[base[i:]+base[:i] for i in range(4)]
        order.shuffle(rotations);orders.extend(rotations)
    rows=[];blocks=[];repeat_count=0
    for n,task in enumerate(selected):
        tid=task['instance_id'];task['task_index']=n;task['condition_order']=orders[n]
        planned=[(0,orders[n],20261110192000+n)]
        if tid in repeat_ids:
            planned.append((1,['M0','M1-10'] if repeat_count%2==0 else ['M1-10','M0'],20261110192100+n));repeat_count+=1
        for repeat,conditions,seed in planned:
            block=[]
            for position,group in enumerate(conditions):
                row={'logical_id':f'v191:{tid}:{group}:rep{repeat}','instance_id':tid,'repo':task['repo'],
                    'condition':group,'task_index':n,'within_task_order':position,'repeat_index':repeat,
                    'primary_panel':repeat==0,'framework_seed':seed,'provider_seed_sent':False,'token_budget':5000000}
                rows.append(row);block.append(row['logical_id'])
            blocks.append(block)
    assert len(rows)==60 and sum(r['primary_panel'] for r in rows)==48
    grant=write_new(OUT/'user-authority.json',{'approved':True,'budget_reply':'300元',
        'scope_reply':'调整为12题共60回合（推荐）','new_API_budget_CNY':300,'old_ledger_balance_transferred':False,
        'primary_runs':48,'repeat_runs':12,'total_runs':60,'per_run_token_cap':5000000,
        'standing_nondisruptive_Docker_API_authority':True,'shared_host_changes':False,
        'started_episodes_not_interrupted_by_cash_line':True,'recorded_at':datetime.now(timezone.utc).isoformat()})
    value={'version':'v191-critical-event-pilot-user-revised-design-r1','status':'prepared_not_started',
        'different_tasks':12,'repositories':12,'repository_counts':dict(Counter(t['repo'] for t in selected)),
        'primary_runs':48,'diagnostic_repeats':12,'total_maximum_runs':60,'whole_plan_token_upper_bound':300000000,
        'conditions':list(GROUPS),'selection_seed':SELECTION_SEED,'order_seed':ORDER_SEED,'repeat_seed':REPEAT_SEED,
        'excluded_v181_task_ids':sorted(excluded),'selection_uses_model_scores_or_reference_patches':False,
        'task_ids':[t['instance_id'] for t in selected],'repeat_task_ids':[t['instance_id'] for t in repeats],
        'tasks':selected,'rows':rows,'dispatch_blocks':blocks,
        'repeat_schedule':'preselected repeats immediately follow their own primary block; never chosen from scores',
        'cash':{'new_budget_CNY':300,'old_balance_transferred_CNY':0,
            'initial_repeat_earmark_CNY':120,'earmark_each_unentered_repeat_CNY':10,
            'estimated_start_hold_per_entered_episode_CNY':5,
            'cash_checked_only_at_new_block_start':True,'started_episodes_finish_above_cash_line':True,
            'theoretical_maximum_cost_covered':False,'expected_completion_not_guaranteed':True},
        'model':'deepseek-flash','thinking':False,'organization':'S1','member_count':1,
        'temperature':1,'top_p':1,'context_limit':131072,'input_limit':98304,'output_limit':32768,
        'per_episode_actual_input_plus_output':5000000,'critical_event_rules':RULES,
        'independent_confirmation_set':False,'provider_seed_control_claimed':False,
        'prototype_overlap_exceptions':[t['instance_id'] for t in selected if t['in_old48_offline_prototype']],
        'overlap_reason':'one task per all12 repositories; avoid prototype tasks where the repository has alternatives',
        'user_authority':grant,'prototype_plan':reference(ROOT/'runs/software-benchmark-v175/context-replay-r1/plan.json'),
        'audit_attachment':reference(Path('/home/zhuxinrui/.codex/attachments/5c6c065c-9b76-4d6d-820d-547de40aade8/已粘贴的文本.txt')),
        'new_model_calls':0,'new_Docker_objects':0}
    out=write_new(OUT/'plan.json',value)
    print(json.dumps({'plan':out,'tasks':value['task_ids'],'repeats':value['repeat_task_ids'],'prototype_overlap':value['prototype_overlap_exceptions']},ensure_ascii=False))

if __name__=='__main__':main()
