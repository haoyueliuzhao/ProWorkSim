"""Extract the fixed40-task role pilot, with separately attributed recovery costs.

Only immutable small JSON evidence and read-only SQLite snapshots are read.
No model, Docker, network, training data or raw workspace archive is accessed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sqlite3
import statistics

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'runs/software-benchmark-v142/role-pilot40-r1'
NEW=ROOT/'runs/software-benchmark-v146/api-recovery21-r1'
EXPORT=ROOT/'runs/software-benchmark-v149/closed-export-recovery-r1'
SCORING=ROOT/'runs/software-benchmark-v151/same-tree-score-handoff-r1'
OVERLAY=ROOT/'runs/software-benchmark-v154/three-score-recovery-r1/canonical-overlay.json'
LEDGERS={'original':OLD/'ledgers/pilot.sqlite',
         'recovery':ROOT/'runs/software-benchmark-v145/api-recovery-prepared-r1/ledger.sqlite'}
OUTPUT=ROOT/'artifacts/software-benchmark-v155/final-report-r1'
GROUPS=('S1','FREE2','REVIEW2')
VERSION='v155-fixed40-role-panel-final-assessment-r1'
BOOTSTRAP_SEED=202611080155
BOOTSTRAP_REPLICATES=20_000
MAX_METADATA_BYTES=16*1024**2
NANO=Decimal(1_000_000_000)


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


@lru_cache(maxsize=None)
def json_file(path):
    path=Path(path)
    if path.stat().st_size>MAX_METADATA_BYTES:
        raise ValueError('Only small result/receipt metadata may be parsed: '+str(path))
    raw=path.read_bytes()
    return json.loads(raw),{'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def read(path):
    return json_file(str(path))[0]


def ref(path):
    return json_file(str(path))[1]


def read_ref(value):
    data,actual=json_file(value['path'])
    if actual['sha256']!=value['sha256'] or actual['bytes']!=value['bytes']:
        raise ValueError('Frozen metadata digest changed: '+value['path'])
    return data


def cny(value):
    return format(Decimal(value)/NANO,'f')


def percentile(values,p):
    """Linear interpolation at p*(n-1), the R/type7 convention."""
    values=sorted(values)
    if not values:return None
    index=p*(len(values)-1);lo=math.floor(index);hi=math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)


def describe(values):
    return {'n':len(values),'sum':sum(values),'mean':statistics.fmean(values) if values else None,
        'median':statistics.median(values) if values else None,'p90':percentile(values,.9),
        'min':min(values) if values else None,'max':max(values) if values else None}


def ledger_snapshot(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        columns={r[1] for r in db.execute('PRAGMA table_info(requests)')}
        selected=['request_id','slot_id','condition','usage_id','status','reserved_nanoyuan',
            'settled_nanoyuan','max_output_tokens','prompt_upper_bound','reserved_utc','usage_json']
        selected += [k for k in ['logical_id','member_id','attempt_index','failure_json','evidence_json'] if k in columns]
        expressions=['r.'+k for k in selected]
        join=''
        if 'member_id' not in columns:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='member_requests'").fetchone():
                raise ValueError('Original ledger lost actual member attribution')
            expressions+=['m.member_id AS member_id','m.group_id AS attributed_group_id']
            selected+=['member_id','attributed_group_id']
            join=' LEFT JOIN member_requests m ON m.request_id=r.request_id'
        rows=[dict(r) for r in db.execute('SELECT '+','.join(expressions)+' FROM requests r'+join+' ORDER BY r.request_id')]
        if any(not r.get('member_id') for r in rows):raise ValueError('A provider request lacks actual member attribution')
    return rows,{'path':str(path),'snapshot_rows':len(rows),
        'selected_columns':selected,'query_rows_sha256':hashlib.sha256(canonical(rows)).hexdigest(),
        'read_only':True,'snapshot_hash_is_not_a_hash_of_mutable_SQLite_storage_bytes':True}


def aggregate_calls(rows):
    input_tokens=output_tokens=cached_tokens=uncached_tokens=settled_cost=0
    unresolved=[];purposes=defaultdict(Counter);members=defaultdict(Counter)
    member_purposes=defaultdict(lambda:defaultdict(Counter))
    for row in rows:
        if row['status']!='settled':
            failure=json.loads(row.get('failure_json') or row.get('evidence_json') or '{}')
            unresolved.append({'request_id':row['request_id'],'status':row['status'],
                'prompt_token_upper_bound':row['prompt_upper_bound'],'output_token_upper_bound':row['max_output_tokens'],
                'reserved_token_upper_bound':row['prompt_upper_bound']+row['max_output_tokens'],
                'reserved_nanoyuan':row['reserved_nanoyuan'],'failure':failure})
            members[row['member_id']]['unresolved_requests']+=1
            member_purposes[row['member_id']][row['usage_id']]['unresolved_requests']+=1
            continue
        if not row['usage_json'] or row['settled_nanoyuan'] is None:
            raise ValueError('A settled request must retain actual usage and accounted cost')
        use=json.loads(row['usage_json'])
        inp,out,total=(use[k] for k in ['prompt_tokens','completion_tokens','total_tokens'])
        hit=use.get('prompt_cache_hit_tokens',use.get('prompt_tokens_details',{}).get('cached_tokens'))
        if hit is None:raise ValueError('Cache usage missing; do not fill it with zero')
        miss=use.get('prompt_cache_miss_tokens',inp-hit)
        if any(type(v) is not int or v<0 for v in [inp,out,total,hit,miss]) or inp+out!=total or hit+miss!=inp:
            raise ValueError('Provider token arithmetic is inconsistent')
        input_tokens+=inp;output_tokens+=out;cached_tokens+=hit;uncached_tokens+=miss
        settled_cost+=row['settled_nanoyuan']
        item=dict(input_tokens=inp,output_tokens=out,cached_input_tokens=hit,total_tokens=total,
                  settled_nanoyuan=row['settled_nanoyuan'],settled_requests=1)
        purposes[row['usage_id']].update(item)
        members[row['member_id']].update(item)
        member_purposes[row['member_id']][row['usage_id']].update(item)
    reserved=sum(r['reserved_nanoyuan'] for r in unresolved)
    return {'physical_requests':len(rows),
        'logical_requests':len({r.get('logical_id') or r['request_id'] for r in rows}),
        'settled_requests':len(rows)-len(unresolved),'request_statuses':dict(Counter(r['status'] for r in rows)),
        'input_tokens':input_tokens,'output_tokens':output_tokens,'cached_input_tokens':cached_tokens,
        'uncached_input_tokens':uncached_tokens,'total_tokens':input_tokens+output_tokens,
        'actual_usage_complete':not unresolved,'known_tokens_are_lower_bound':bool(unresolved),
        'settled_nanoyuan':settled_cost,'settled_cost_CNY':cny(settled_cost),
        'unresolved_request_count':len(unresolved),'unresolved_request_records':unresolved,
        'unknown_reserved_tokens_upper_bound':sum(r['reserved_token_upper_bound'] for r in unresolved),
        'unknown_reserved_nanoyuan':reserved,'unknown_reserved_CNY':cny(reserved),
        'unresolved_reservations_are_not_actual_usage':True,
        'usage_by_purpose':{k:dict(v) for k,v in sorted(purposes.items())},
        'usage_by_member':{k:dict(v) for k,v in sorted(members.items())},
        'usage_by_member_and_purpose':{m:{p:dict(v) for p,v in sorted(purposes.items())}
            for m,purposes in sorted(member_purposes.items())}}


def flat_usage(usage):
    return {k:usage[k] for k in ['physical_requests','logical_requests','settled_requests',
        'input_tokens','output_tokens','cached_input_tokens','uncached_input_tokens','total_tokens',
        'settled_nanoyuan','settled_cost_CNY','actual_usage_complete','unresolved_request_count']}


def endpoint_refs(record):
    return {k:v for k,v in record.items() if isinstance(v,dict) and {'path','sha256','bytes'}<=set(v)}


def verify_code(record,slot_id):
    if type(record.get('resolved')) is not bool:raise ValueError('Final code assessment is still unknown')
    basis=record.get('basis','official_report')
    receipt_ref=record.get('receipt')
    if basis=='validated_candidate_failure':
        proof=read_ref(record['failure_proof'])
        if (record['resolved'] is not False or proof.get('slot_id')!=slot_id
                or proof.get('patch_applied_observed') is not True
                or proof.get('offline_build_and_install_succeeded') is not True
                or proof.get('network_failure_absent_after_repair') is not True
                or proof.get('model_calls')!=0):
            raise ValueError('Candidate-failure adjudication is not bound to actual valid execution')
    else:
        if not receipt_ref:raise ValueError('A code result requires an official receipt')
        receipt=read_ref(receipt_ref)
        if (receipt.get('slot_id')!=slot_id or receipt.get('status')!='official_report'
                or receipt.get('resolved') is not record['resolved']):
            raise ValueError('Canonical code result differs from its immutable official receipt')
    return basis


def verify_delivery(record,slot_id,export=None):
    if type(record.get('resolved')) is not bool:raise ValueError('Final delivery remains unknown')
    if export is not None:
        if record.get('state')=='no_legal_delivery':
            if export.get('submitted') is not False or record['resolved'] is not False:
                raise ValueError('Missing-delivery assessment disagrees with the locked normal export')
            return
        if export.get('submitted') is not True:
            raise ValueError('Measured legal delivery lacks a submitted artifact')
        if record.get('state')=='same_tree_official_result_reused' and export.get('same_tree') is not True:
            raise ValueError('Different final and delivery trees cannot reuse one score')
    receipt_ref=record.get('code_receipt') or record.get('receipt')
    if receipt_ref is None:raise ValueError('Delivery assessment lacks its canonical receipt')
    receipt=read_ref(receipt_ref)
    if (receipt.get('slot_id')!=slot_id or receipt.get('resolved') is not record['resolved']
            or receipt.get('status',receipt.get('state')) not in
                {'official_report','no_legal_delivery','same_tree_official_result_reused'}):
        raise ValueError('Delivery receipt identity or result disagrees with the selected episode')


def selected_rows():
    old_plan=read(OLD/'deployment-v143/execution-plan.json')
    old_outcomes=read(OLD/'deployment-v143/api-coordinator/task-outcomes.json')['rows']
    old_by={r['slot_id']:r for r in old_outcomes}
    new_plan=read(NEW/'execution-plan.json')
    targets=dict(read(SCORING/'watch-progress.json')['targets'])
    overlay=read(OVERLAY)
    for key,value in overlay['canonical_results'].items():
        prior=targets.get(key,{})
        if type(prior.get('resolved')) is bool and prior['resolved']!=value['resolved']:
            raise ValueError('Overlay cannot replace a previously determined result')
        targets[key]=value
    ledger_rows={};ledger_evidence={};by_slot={}
    for name,path in LEDGERS.items():
        ledger_rows[name],ledger_evidence[name]=ledger_snapshot(path)
        indexed=defaultdict(list)
        for r in ledger_rows[name]:indexed[r['slot_id']].append(r)
        by_slot[name]=indexed
    episodes=[];excluded_old=[];selected_keys={'original':set(),'recovery':set()}
    original_groups=defaultdict(list)
    for original in old_plan['rows']:
        out=old_by[original['slot_id']]
        original_groups[original['group_id']].append(out)
        export_ref=None;controller_ref=None;export=None
        if out['generation_status']=='closed':
            chosen=original;source='original_normal_attempt';origin='original'
            code={'resolved':out['resolved'],'receipt':out['code_receipt']}
            delivery={'resolved':out['legal_delivery'],'state':out['delivery_status'],'receipt':out['delivery_receipt']}
            generation_ref=out['generation_result']
        else:
            if out['generation_status']!='technical_unknown':raise ValueError('Unexpected original selection state')
            excluded_old.append({'original_slot_id':original['slot_id'],'slot_index':original['slot_index'],
                'instance_id':original['instance_id'],'repo':original['repo'],'group_id':original['group_id'],
                'generation_result_ref':out['generation_result'],
                **aggregate_calls(by_slot['original'][original['slot_id']])})
            choices=sorted([r for r in new_plan['rows'] if r['original_slot_id']==original['slot_id']],key=lambda r:r['recovery_round'])
            chosen=None
            for row in choices:
                path=EXPORT/str(row['slot_index'])/'recovery-result.json'
                if not path.is_file():continue
                exp=read(path)
                c,d=(targets.get(f"{row['slot_index']}:{e}",{}) for e in ('code','delivery'))
                if type(c.get('resolved')) is bool and type(d.get('resolved')) is bool:
                    chosen=row;export_ref=ref(path);export=exp;code=c;delivery=d;break
            if chosen is None:raise ValueError('No complete normal recovery for '+original['slot_id'])
            if (export.get('status')!='recovered_closed_export' or export.get('slot_id')!=chosen['slot_id']
                    or export.get('completed_work_proven_before_export') is not True
                    or export.get('model_resampling') is not False or export.get('new_model_calls')!=0
                    or chosen['seed']!=original['seed'] or chosen['group_id']!=original['group_id']):
                raise ValueError('Recovery is not the same task/seed with a normally closed independent attempt')
            for endpoint in (code,delivery):
                if endpoint.get('slot_id',chosen['slot_id'])!=chosen['slot_id']:
                    raise ValueError('Endpoint identity differs from selected recovery')
            source='first_fully_measured_independent_recovery';origin='recovery'
            generation_ref=export['original_result'];controller_ref=export['controller_result']
        basis=verify_code(code,chosen['slot_id'])
        verify_delivery(delivery,chosen['slot_id'],export)
        calls=by_slot[origin][chosen['slot_id']]
        if (not calls or any(r['condition']!=original['condition_id'] or r['member_id'] not in original['fixed_members']
                or r.get('attributed_group_id',original['group_id'])!=original['group_id'] for r in calls)):
            raise ValueError('Missing or foreign ledger rows')
        usage=aggregate_calls(calls)
        if not usage['actual_usage_complete'] or usage['total_tokens']>5_000_000:
            raise ValueError('Selected normal episode must retain complete whole-team usage within5M')
        if origin=='original' and usage['total_tokens']!=out['actual_tokens_known']:
            raise ValueError('Original outcome and provider usage disagree')
        if origin=='recovery' and usage['total_tokens']!=export['provider_usage']['known_actual_tokens']:
            raise ValueError('Normal export and provider usage disagree')
        selected_keys[origin].add(chosen['slot_id'])
        episodes.append({'instance_id':original['instance_id'],'repo':original['repo'],'group_id':original['group_id'],
            'seed':original['seed'],'fixed_members':original['fixed_members'],'member_count':original['member_count'],
            'original_slot_id':original['slot_id'],'original_slot_index':original['slot_index'],
            'original_generation_status':out['generation_status'],'selected_slot_id':chosen['slot_id'],
            'selected_slot_index':chosen['slot_index'],'selected_recovery_round':chosen.get('recovery_round'),
            'selection_source':source,'ledger_name':origin,'code_passed':code['resolved'],'code_basis':basis,
            'delivery_passed':delivery['resolved'],'delivery_status':delivery.get('state'),
            'code_evidence':endpoint_refs(code),'delivery_evidence':endpoint_refs(delivery),
            'generation_result_ref':generation_ref,'normal_export_ref':export_ref,'controller_result_ref':controller_ref,
            'controller_result_path':str(Path(generation_ref['path']).parent/'controller-output/controller-result.json'),
            'team_token_budget':5_000_000,'near_cap_gt_4900000':usage['total_tokens']>4_900_000,
            'near_cap_gte_95pct':usage['total_tokens']>=4_750_000,
            **flat_usage(usage),'usage_by_purpose':usage['usage_by_purpose'],
            'usage_by_member':usage['usage_by_member'],
            'usage_by_member_and_purpose':usage['usage_by_member_and_purpose']})
    if len(episodes)!=120 or len({(r['instance_id'],r['group_id']) for r in episodes})!=120 or len(excluded_old)!=21:
        raise ValueError('Fixed40x3 accounting selection changed')
    if set(selected_keys['recovery'])!=set(by_slot['recovery']):
        raise ValueError('Additional recovery attempts exist; extend the separate excluded-cost accounting before reporting')
    sources={name:ref(path) for name,path in {
        'original_plan':OLD/'deployment-v143/execution-plan.json',
        'original_outcomes':OLD/'deployment-v143/api-coordinator/task-outcomes.json',
        'recovery_plan':NEW/'execution-plan.json','scoring_watch':SCORING/'watch-progress.json',
        'final_overlay':OVERLAY}.items()}
    return episodes,excluded_old,ledger_rows,ledger_evidence,original_groups,sources


def group_summary(rows):
    count=len(rows)
    result={'episodes':count,'original_normal_selected':sum(r['ledger_name']=='original' for r in rows),
        'independent_recoveries_selected':sum(r['ledger_name']=='recovery' for r in rows),
        'code':{'passed':sum(r['code_passed'] for r in rows),'failed':sum(not r['code_passed'] for r in rows),
                'unknown':0,'rate':sum(r['code_passed'] for r in rows)/count if count else None,
                'basis_counts':dict(Counter(r['code_basis'] for r in rows))},
        'delivery':{'passed':sum(r['delivery_passed'] for r in rows),'failed':sum(not r['delivery_passed'] for r in rows),
                'unknown':0,'rate':sum(r['delivery_passed'] for r in rows)/count if count else None},
        'tokens':{key:describe([r[key] for r in rows]) for key in
                 ['input_tokens','output_tokens','cached_input_tokens','uncached_input_tokens','total_tokens']},
        'requests':{key:describe([r[key] for r in rows]) for key in ['physical_requests','logical_requests']},
        'near_cap':{'greater_than_4900000':sum(r['near_cap_gt_4900000'] for r in rows),
                    'at_least_95pct_of_5M':sum(r['near_cap_gte_95pct'] for r in rows),
                    'is_proof_of_budget_truncation':False}}
    cost=sum(r['settled_nanoyuan'] for r in rows)
    result['settled_cost']={'nanoyuan':cost,'total_CNY':cny(cost),
        'mean_CNY':str(Decimal(cost)/NANO/Decimal(count)) if count else None,
        'median_CNY':statistics.median([float(r['settled_cost_CNY']) for r in rows]) if count else None,
        'p90_CNY':percentile([float(r['settled_cost_CNY']) for r in rows],.9)}
    result['cached_input_fraction']=sum(r['cached_input_tokens'] for r in rows)/sum(r['input_tokens'] for r in rows) if rows else None
    requests=sum(r['settled_requests'] for r in rows)
    result['request_input_decomposition']={'settled_physical_requests':requests,
        'mean_settled_physical_requests_per_episode':requests/count if count else None,
        'mean_input_tokens_per_settled_request':sum(r['input_tokens'] for r in rows)/requests if requests else None,
        'mean_output_tokens_per_settled_request':sum(r['output_tokens'] for r in rows)/requests if requests else None,
        'identity':'mean input per episode = requests per episode * input per request',
        'is_causal_attribution_to_communication':False}
    result['tokens_per_code_pass_including_failed_task_costs']=sum(r['total_tokens'] for r in rows)/result['code']['passed'] if result['code']['passed'] else None
    result['code_delivery_cross_table']={'both_pass':sum(r['code_passed'] and r['delivery_passed'] for r in rows),
        'code_pass_delivery_fail':sum(r['code_passed'] and not r['delivery_passed'] for r in rows),
        'code_fail_delivery_pass':sum(not r['code_passed'] and r['delivery_passed'] for r in rows),
        'both_fail':sum(not r['code_passed'] and not r['delivery_passed'] for r in rows),
        'different_final_and_legal_delivery_trees_may_exist':True}
    result['tokens_by_outcome']={endpoint:{label:describe([r['total_tokens'] for r in rows if r[endpoint+'_passed'] is flag])
        for label,flag in [('success',True),('failure',False)]} for endpoint in ('code','delivery')}
    purposes=defaultdict(Counter);members=defaultdict(Counter);member_purposes=defaultdict(lambda:defaultdict(Counter))
    for row in rows:
        for purpose,value in row['usage_by_purpose'].items():purposes[purpose].update(value)
        for member,value in row['usage_by_member'].items():members[member].update(value)
        for member,by_purpose in row['usage_by_member_and_purpose'].items():
            for purpose,value in by_purpose.items():member_purposes[member][purpose].update(value)
    result['usage_by_purpose']={k:dict(v) for k,v in sorted(purposes.items())}
    result['usage_by_member']={k:dict(v) for k,v in sorted(members.items())}
    result['usage_by_member_and_purpose']={m:{p:dict(v) for p,v in sorted(values.items())}
        for m,values in sorted(member_purposes.items())}
    return result


def pair_statistics(episodes):
    by_task=defaultdict(dict)
    for row in episodes:by_task[row['instance_id']][row['group_id']]=row
    if len(by_task)!=40 or any(set(v)!=set(GROUPS) for v in by_task.values()):raise ValueError('Pairing is incomplete')
    repos=sorted({r['repo'] for r in episodes})
    if len(repos)!=12:raise ValueError('The frozen panel should retain12 repositories')
    pairs={}
    for a,b in itertools.combinations(GROUPS,2):
        pair={'a':a,'b':b,'difference_orientation':b+' minus '+a,'paired_tasks':40,'endpoints':{},'rows':[]}
        for task,conditions in sorted(by_task.items()):
            x,y=conditions[a],conditions[b]
            pair['rows'].append({'instance_id':task,'repo':x['repo'],'a_code':x['code_passed'],'b_code':y['code_passed'],
                'a_delivery':x['delivery_passed'],'b_delivery':y['delivery_passed'],
                'a_total_tokens':x['total_tokens'],'b_total_tokens':y['total_tokens'],
                'token_difference_b_minus_a':y['total_tokens']-x['total_tokens']})
        for endpoint in ('code','delivery'):
            table={name:[] for name in ['both_pass','a_only_pass','b_only_pass','both_fail']}
            for row in pair['rows']:
                x,y=row['a_'+endpoint],row['b_'+endpoint]
                key='both_pass' if x and y else 'a_only_pass' if x else 'b_only_pass' if y else 'both_fail'
                table[key].append(row['instance_id'])
            pair['endpoints'][endpoint]={'counts':{k:len(v) for k,v in table.items()},'task_ids':table,
                'difference_rate':(len(table['b_only_pass'])-len(table['a_only_pass']))/40}
        pair['token_difference_b_minus_a']=describe([r['token_difference_b_minus_a'] for r in pair['rows']])
        pair['total_token_ratio_b_over_a']=sum(r['b_total_tokens'] for r in pair['rows'])/sum(r['a_total_tokens'] for r in pair['rows'])
        shared=[r for r in pair['rows'] if r['a_code'] and r['b_code']]
        pair['shared_success_token_diagnostic']={
            'selection':'Post hoc subset with both selected code endpoints passing',
            'auxiliary_only_does_not_replace_the40_task_panel':True,
            'n':len(shared),'task_ids':[r['instance_id'] for r in shared],
            'a_total_tokens':describe([r['a_total_tokens'] for r in shared]),
            'b_total_tokens':describe([r['b_total_tokens'] for r in shared]),
            'relative_mean_token_change_b_over_a_minus1':
                sum(r['b_total_tokens'] for r in shared)/sum(r['a_total_tokens'] for r in shared)-1 if shared else None}
        pairs[a+'__'+b]=pair
    # All comparisons share the same repository-cluster bootstrap draws.
    repo_sizes=[sum(next(iter(v.values()))['repo']==repo for v in by_task.values()) for repo in repos]
    per_repo={key:{endpoint:[sum(int(r['b_'+endpoint])-int(r['a_'+endpoint]) for r in pair['rows'] if r['repo']==repo)
                 for repo in repos] for endpoint in ('code','delivery')} for key,pair in pairs.items()}
    samples={key:{e:[] for e in ('code','delivery')} for key in pairs}
    rng=random.Random(BOOTSTRAP_SEED)
    for _ in range(BOOTSTRAP_REPLICATES):
        draw=[rng.randrange(len(repos)) for _ in repos]
        n=sum(repo_sizes[i] for i in draw)
        for key in pairs:
            for endpoint in ('code','delivery'):
                samples[key][endpoint].append(sum(per_repo[key][endpoint][i] for i in draw)/n)
    for key,pair in pairs.items():
        for endpoint in ('code','delivery'):
            pair['endpoints'][endpoint]['repository_cluster_bootstrap_95pct']={
                'lower':percentile(samples[key][endpoint],.025),'upper':percentile(samples[key][endpoint],.975)}
    return pairs,{'resampling_unit':'repository','repositories':repos,'repository_task_counts':dict(zip(repos,repo_sizes)),
        'draws_per_replication':12,'replications':BOOTSTRAP_REPLICATES,'seed':BOOTSTRAP_SEED,
        'within_draw_measure':'Pool all tasks in sampled repositories, including every selected duplicate cluster; compute B-A over that task count',
        'percentile_method':'linear interpolation at p*(N-1)',
        'interpretation':'Descriptive uncertainty for this exposed40-task engineering panel, not extrapolation to SWE-bench Verified500'}


def analyze():
    episodes,excluded_old,ledger_rows,ledger_evidence,original_groups,sources=selected_rows()
    groups={g:group_summary([r for r in episodes if r['group_id']==g]) for g in GROUPS}
    baseline=groups['S1']['tokens']['total_tokens']['mean']
    for value in groups.values():
        value['relative_to_S1_mean_total_token_change']=(value['tokens']['total_tokens']['mean']/baseline)-1
        a,b=value['request_input_decomposition'],groups['S1']['request_input_decomposition']
        a['relative_to_S1_requests_per_episode_ratio']=a['mean_settled_physical_requests_per_episode']/b['mean_settled_physical_requests_per_episode']
        a['relative_to_S1_input_per_request_ratio']=a['mean_input_tokens_per_settled_request']/b['mean_input_tokens_per_settled_request']
        a['relative_to_S1_mean_input_tokens_ratio']=value['tokens']['input_tokens']['mean']/groups['S1']['tokens']['input_tokens']['mean']
    repositories={repo:{g:group_summary([r for r in episodes if r['repo']==repo and r['group_id']==g]) for g in GROUPS}
                  for repo in sorted({r['repo'] for r in episodes})}
    paired,bootstrap=pair_statistics(episodes)
    original_first={}
    for group,rows in original_groups.items():
        original_first[group]={'planned':len(rows),'generation_status_counts':dict(Counter(r['generation_status'] for r in rows)),
            'code':dict(Counter('pass' if r['resolved'] is True else 'fail' if r['resolved'] is False else 'unknown' for r in rows)),
            'delivery':dict(Counter('pass' if r['legal_delivery'] is True else 'fail' if r['legal_delivery'] is False else 'unknown' for r in rows))}
    excluded_slots={r['original_slot_id'] for r in excluded_old}
    old_failed_calls=[r for r in ledger_rows['original'] if r['slot_id'] in excluded_slots]
    failed_aggregate=aggregate_calls(old_failed_calls)
    selected_cost=sum(r['settled_nanoyuan'] for r in episodes)
    all_attempts=aggregate_calls(ledger_rows['original']+ledger_rows['recovery'])
    if (selected_cost+failed_aggregate['settled_nanoyuan']!=all_attempts['settled_nanoyuan']
            or sum(r['total_tokens'] for r in episodes)+failed_aggregate['total_tokens']!=all_attempts['total_tokens']
            or all_attempts['settled_nanoyuan']!=423_907_235_760
            or failed_aggregate['unknown_reserved_nanoyuan']!=7_252_874_000):
        raise ValueError('Selected/failed/all-attempt cost and token reconciliation changed')
    summary={'version':VERSION,'selection_rule':'Keep original99 normal episodes; for each original21 unknown use earliest fully measured independent normal recovery. Never use stopped-code supplements or choose a better score.',
        'planned_tasks':40,'planned_group_episodes':120,'groups':groups,'original_first_attempt_panel':original_first,
        'selected_completed_panel':group_summary(episodes),
        'independent_recovery_only':{g:group_summary([r for r in episodes if r['group_id']==g and r['ledger_name']=='recovery']) for g in GROUPS if g!='S1'},
        'selected_recovery_round_counts':dict(Counter(r['selected_recovery_round'] for r in episodes if r['selected_recovery_round'] is not None)),
        'repository_strata':repositories,'paired_comparisons':paired,'bootstrap_method':bootstrap,
        'excluded_original21_failed_attempts':{'episodes':excluded_old,'aggregate':failed_aggregate,
            'by_group':{g:aggregate_calls([r for r in old_failed_calls if r['slot_id'] in {e['original_slot_id'] for e in excluded_old if e['group_id']==g}]) for g in ('FREE2','REVIEW2')},
            'included_in_selected_means':False,'unknown_usage_filled_with_zero':False},
        'all_attempts_cost_and_usage':all_attempts,
        'cash_reconciliation':{'selected120_settled_CNY':cny(selected_cost),
            'excluded_old21_settled_CNY':failed_aggregate['settled_cost_CNY'],
            'all_attempts_settled_CNY':all_attempts['settled_cost_CNY'],
            'old_unresolved_reserved_CNY':failed_aggregate['unknown_reserved_CNY'],
            'cap_CNY':'450','remaining_after_all_reservations_CNY':cny(450_000_000_000-all_attempts['settled_nanoyuan']-all_attempts['unknown_reserved_nanoyuan']),
            'scoring_export_and_repair_model_calls':0,'cost_source':'Ledger settled_nanoyuan under recorded billing rules; reservations are not actual charges'},
        'token_measurement_notes':{'input_includes_cached_input':True,'cached_tokens_not_added_again':True,
            'input_plus_output_equals_total':True,'whole_team_including_summarization':True,
            'statistics_unit':'One selected team episode, not one member or one request',
            'near_cap_is_only_proxy_not_proven_budget_truncation':True,
            'selected_tokens_include_successes_and_failures':True},
        'evidence':{'sources':sources,'ledger_snapshots':ledger_evidence,
            'analysis_source':{'path':str(Path(__file__).resolve()),'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}}
    return episodes,summary


def write_outputs(output):
    rows,summary=analyze()
    output.mkdir(parents=True,exist_ok=True)
    document={'version':VERSION,'selection_rule':summary['selection_rule'],'planned_tasks':40,'episode_count':120,
              'rows':rows,'evidence':summary['evidence']}
    for name,data in [('episodes.json',document),('summary.json',summary)]:
        raw=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        target=output/name
        if not target.exists() or target.read_text()!=raw:target.write_text(raw)
    flat=[]
    for row in rows:
        record={k:v for k,v in row.items() if not isinstance(v,(dict,list)) and not k.endswith('_ref')}
        record['generation_result_path']=row['generation_result_ref']['path']
        record['normal_export_path']=row['normal_export_ref']['path'] if row['normal_export_ref'] else ''
        flat.append(record)
    fields=list(flat[0])
    with (output/'episodes.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    result=write_outputs(args.output)
    print(json.dumps({'output':str(args.output),'groups':{g:{'code':r['code'],'delivery':r['delivery'],
        'mean_tokens':r['tokens']['total_tokens']['mean'],'cost_CNY':r['settled_cost']['total_CNY']} for g,r in result['groups'].items()},
        'cash':result['cash_reconciliation']},ensure_ascii=False,indent=2))
