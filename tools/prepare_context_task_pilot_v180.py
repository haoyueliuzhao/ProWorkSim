"""Prepare a score-blind12-task/60-run context-policy pilot; start no tasks."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import random

from proworksim.software_benchmark_candidates_v054 import reference,write_new

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/software-benchmark-v180/full-task-design-r1'
SELECTION_SEED=20261109180
ORDER_SEED=20261109181
REPEAT_SEED=20261109182
CONDITIONS=('M0','M1-5','M1-10','M3-R')


def read(path):return json.loads((ROOT/path).read_bytes())


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pool=read('artifacts/software-benchmark-v054/source/public-tasks.json')
    old155=read('artifacts/software-benchmark-v142/pilot-design-r1/panel.json')
    old174=read('artifacts/software-benchmark-v156/communication-design-r1/approved-panel.json')
    old175=read('artifacts/software-benchmark-v175/replay-plan-r1/proposal.json')
    excluded=set(old155['task_ids'])|{r['instance_id'] for r in old174['tasks']}|{r['instance_id'] for r in old175['rows']}
    grouped=defaultdict(list);dedup=set()
    for t in sorted(pool,key=lambda r:r['instance_id']):
        if t['instance_id'] in excluded:continue
        key=(t['repo'],t['base_commit'],hashlib.sha256(t['problem_statement'].encode()).hexdigest())
        if key in dedup:continue
        dedup.add(key);grouped[t['repo']].append(t)
    rng=random.Random(SELECTION_SEED)
    repos=sorted(k for k,v in grouped.items() if len(v)>=2);rng.shuffle(repos);repos=repos[:6]
    tasks=[]
    for repo in repos:
        items=sorted(grouped[repo],key=lambda t:t['instance_id']);rng.shuffle(items);tasks.extend(items[:2])
    order_rng=random.Random(ORDER_SEED);order_rng.shuffle(tasks)
    orders=[]
    for block in range(3):
        base=list(CONDITIONS);order_rng.shuffle(base)
        rotations=[base[n:]+base[:n] for n in range(4)];order_rng.shuffle(rotations);orders.extend(rotations)
    tests={e['instance_id']:e for e in read('config/v054-public-test-registry.json')['entries']}
    panel=[];schedule=[]
    for n,t in enumerate(tasks):
        entry=tests[t['instance_id']]
        panel.append({**t,'task_index':n,'condition_order':orders[n],
            'not_in_v155_v174_v175':True,'historically_exposed_before_those_rounds':True,
            'actor_image_id':entry['source_identity']['actor_image_id'],
            'public_test_entry':{k:entry[k] for k in ('cwd','argv','public_python','baseline_mapping')},
            'fresh_task_environment_and_gold_empty_controls_done':False})
        for position,condition in enumerate(orders[n]):
            schedule.append({'logical_id':f'v180:{t["instance_id"]}:{condition}:rep0',
                'instance_id':t['instance_id'],'repo':t['repo'],'condition':condition,'task_index':n,
                'within_task_order':position,'repeat_index':0,'primary_panel':True,
                'framework_seed':20261109180000+n,'provider_seed_sent':False,'token_budget':5_000_000})
    repeats=[];repeat_rng=random.Random(REPEAT_SEED)
    for repo in sorted(repos):
        options=sorted([t for t in panel if t['repo']==repo],key=lambda t:t['instance_id']);repeat_rng.shuffle(options);repeats.append(options[0])
    repeat_rng.shuffle(repeats)
    for n,t in enumerate(repeats):
        pair=['M0','M1-10'] if n%2==0 else ['M1-10','M0']
        for position,condition in enumerate(pair):
            schedule.append({'logical_id':f'v180:{t["instance_id"]}:{condition}:rep1',
                'instance_id':t['instance_id'],'repo':t['repo'],'condition':condition,'task_index':t['task_index'],
                'within_task_order':position,'repeat_index':1,'primary_panel':False,
                'framework_seed':20261109181000+n,'provider_seed_sent':False,'token_budget':5_000_000})
    exposure=read('artifacts/software-benchmark-v156/communication-design-r1/history-exposure.json')
    assert exposure['all_public_pool_previously_exposed']
    s1=read('artifacts/software-benchmark-v155/final-report-r1/summary.json')['groups']['S1']['tokens']
    current_per_run=(s1['uncached_input_tokens']['mean']*2000+s1['cached_input_tokens']['mean']*40+s1['output_tokens']['mean']*8000)/1e9
    value={'version':'v180-context-full-task-pilot-design-r1','status':'protocol_and_panel_prepared_not_dispatched',
        'different_tasks':12,'repositories':6,'repository_counts':dict(Counter(t['repo'] for t in panel)),
        'primary_runs':48,'diagnostic_repeats':12,'total_maximum_runs':60,
        'conditions':list(CONDITIONS),'selection_seed':SELECTION_SEED,'order_seed':ORDER_SEED,'repeat_seed':REPEAT_SEED,
        'excluded_prior_task_count':len(excluded),'eligible_after_exclusion':sum(len(v) for v in grouped.values()),
        'selection_uses_model_scores_or_patch_contents':False,'task_ids':[t['instance_id'] for t in panel],
        'repeat_task_ids':[t['instance_id'] for t in repeats],'tasks':panel,'rows':schedule,
        'provider_seed_control_claimed':False,'independent_confirmation_set':False,
        'historical_exposure_basis':reference(ROOT/'artifacts/software-benchmark-v156/communication-design-r1/history-exposure.json'),
        'original_dataset':reference(ROOT/'artifacts/software-benchmark-v054/manifests/identities.json'),
        'organization':'S1','member_count':1,'base_framework':'same managed OpenHands S1 with current project tools and delivery lifecycle',
        'same_common_private_recovery_tool':'v179 source-labeled reader in all4conditions',
        'model':'deepseek-flash','thinking':False,'temperature':1,'top_p':1,
        'context_limit':131072,'input_limit':98304,'output_limit':32768,'per_episode_actual_input_plus_output':5000000,
        'whole_plan_token_upper':300000000,'upper_is_expected_consumption':False,
        'M0_existing_history':{'max_size_events':80,'keep_first_events':4,'hard_reset_retries':1,'raw_context_claimed':False},
        'M1_windows_completed_tool_cycles':[5,10],'M1_retains_actions':True,
        'M1_automatic_extra_summary':False,'M1_action_history_exceeds_context':'explicit_context_capacity_endpoint',
        'M3_R':{'new_cycles_to_summarize':21,'recent_full_cycles':10,'normal_trigger_unsummarized_cycles':31,
            'source':'complete_original_unmasked_history','summary_persists_across_requests':True,
            'source_versions_and_time_bound':True,'critical_state_change_triggers_validity_check':True,
            'changed_events_retained_in_recent_tail':True,'old_summary_not_claimed_current':True,
            'same_prefix_not_resummarized_without_new_events':True},
        'API_ledger':str(ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'),
        'cumulative_CNY_cap':250,'cash_rule':'new paired-block admission only; running episodes finish',
        'budget_forecast':{'basis':'v155 S1 actual token mix repriced at current peak tariff; no compression saving assumed',
            'per_run_CNY':current_per_run,'for48_CNY':current_per_run*48,'for60_CNY':current_per_run*60,
            'is_guarantee':False,'compression_and_cache_changes_not_forecast_as_known':True},
        'main_denominator_per_condition':12,'repeats_not_pooled_as_independent_tasks':True,
        'primary_endpoints':['official_unique_final_code_resolved','official_last_legal_delivery_resolved'],
        'source_lifecycle_measures':['agent_input','summary_input_output','summary_presentations','validity_proxy_reuses',
            'stale_history_presentations','context_read_cost','failed_attempts','version_mismatches','repeat_tests','trajectory_length'],
        'launch_gates':['actual12-case recovery gate','real SDK strategy and common tool binding',
            'source-bound public and official environment controls','final deployment scope and source freeze',
            'cash admission for next planned paired block'],
        'fresh_model_calls':0,'new_Docker_objects':0,'training':False,'multiagent_communication_migration':False}
    write_new(OUT/'plan.json',value)
    print(json.dumps({'task_ids':value['task_ids'],'repeat_task_ids':value['repeat_task_ids'],
        'repositories':value['repository_counts'],'budget_forecast':value['budget_forecast']},ensure_ascii=False))


if __name__=='__main__':main()
