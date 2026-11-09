"""One-pass actual-usage and literal/behavior analysis; never execute a decision."""
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_compression_v175 import canonical,observations
from proworksim.software_context_dataset_v175 import PATH_RE,VERSION_RE

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v175/context-replay-r1'
OUT=ROOT/'artifacts/software-benchmark-v175/replay-results-r3'


def read(path):return json.loads(Path(path).read_bytes())
def load(ref):return read(ref['path'])
def text(value):return canonical(value)
def signature(action):
    return {'name':action.get('name'),'arguments':action.get('arguments')} if action.get('valid') else None


def source_action(response):
    calls=response['choices'][0]['message'].get('tool_calls',[])
    if len(calls)!=1:return {'valid':False}
    try:return {'valid':True,'name':calls[0]['function']['name'],'arguments':json.loads(calls[0]['function']['arguments'])}
    except (KeyError,ValueError,TypeError):return {'valid':False}


def literals(payload):
    content='\n'.join(str(m.get('content',''))+canonical(m.get('tool_calls',[])) for m in payload['messages'])
    return {
        'path_literals':set(PATH_RE.findall(content)),
        'version_literals':set(VERSION_RE.findall(content)),
        'exception_names':set(re.findall(r'\b[A-Z][A-Za-z]*(?:Error|Exception|Warning)\b',content)),
        'test_node_literals':set(re.findall(r'\b(?:[A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_]+\.py::[A-Za-z0-9_:.\[\]-]+',content)),
    }


def selected_paths(action):
    result=set()
    def visit(value,key=''):
        if isinstance(value,dict):
            for k,v in value.items():visit(v,k)
        elif isinstance(value,list):
            for v in value:visit(v,key)
        elif isinstance(value,str) and key in {'path','paths','file','files','file_path','targets','directory'}:
            result.add(value)
    visit(action.get('arguments',{}))
    return result


def total(rows):
    value=Counter()
    for row in rows:
        usage=row['parsed_usage'];value['physical_calls']+=1
        for name in ('input_tokens','output_tokens','total_tokens','cached_input_tokens','cache_miss_input_tokens'):
            value[name]+=usage[name]
        value['cost_nanoyuan']+=row['cost']
        value[row['purpose']+'_input_tokens']+=usage['input_tokens']
        value[row['purpose']+'_output_tokens']+=usage['output_tokens']
    return dict(value)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    run=read(RUN/'run-summary.json');plan=read(RUN/'plan.json')
    with sqlite3.connect((RUN/'api-ledger.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        calls=[dict(r) for r in db.execute('SELECT * FROM requests ORDER BY started,request_id')]
    if any(r['status']!='settled' for r in calls):raise ValueError('Report unknown costs explicitly before closing the ledger')
    byjob=defaultdict(list);byresponse={};models=Counter();fingerprints=Counter();finishes=Counter()
    for r in calls:
        r['parsed_usage']=json.loads(r['usage']);response=load(json.loads(r['response_ref']))
        byjob[r['job_id']].append(r);byresponse[r['request_id']]=response
        models[response.get('model')]+=1;fingerprints[response.get('system_fingerprint')]+=1
        finishes[response['choices'][0]['finish_reason']]+=1
    all_results=[*run['core'],*run['holdout_M3_G1']]
    index={(r['point_id'],r['method'],r['revision']):r for r in all_results}
    points={r['point_id']:r for r in plan['rows']};rows=[];literal_totals=defaultdict(Counter)
    comparison_rows=[];summary_rows=[]
    for point in plan['rows']:
        pid=point['point_id'];base=index[pid,'M0','G0'];base_input=load(base['effective_payload']);before=literals(base_input)
        original=source_action(load(load(point['source_receipt'])['response_original_ref']))
        for method,revision in [('M0','G0'),('M1','G0'),('M2','G0'),('M3','G0'),*([('M3','G1')] if point['partition']=='holdout_history' else [])]:
            result=index.get((pid,method,revision))
            if not result:continue
            effective=load(result['effective_payload']);after=literals(effective);action=result.get('final_action',{})
            group=method+'-'+revision;cost=total(byjob[result['job_id']]);basecost=total(byjob[base['job_id']])
            restore=read(ROOT/'runs/software-benchmark-v175/context-replay-r1/points-r2'/pid/(method+'-evidence.json'))
            saved='\n'.join(e['text'] for e in restore['entries'].values())
            aftertext='\n'.join(str(m.get('content',''))+text(m.get('tool_calls',[])) for m in effective['messages'])
            visible_refs={ref for ref in restore['entries'] if ref in aftertext}
            addressable='\n'.join(e['text'] for ref,e in restore['entries'].items() if ref in visible_refs)
            hidden_refs=[ref for ref,e in restore['entries'].items() if ref not in visible_refs and e['text'] not in aftertext]
            if method in {'M0','M1','M2'} and hidden_refs:
                raise ValueError('An unabridged observation or its explicit marker must still be visible')
            fact={}
            for kind,found in before.items():
                kept=found & after[kind]
                recoverable={v for v in found if v in saved or v in aftertext}
                addressable_facts={v for v in found if v in addressable or v in aftertext}
                fact[kind]={'original':len(found),'default_view_retained':len(kept),
                    'default_or_storage_present':len(recoverable),
                    'default_or_visible_reference_available':len(addressable_facts)}
                for key,n in fact[kind].items():literal_totals[group][kind+'_'+key]+=n
            row={'job_id':result['job_id'],'point_id':pid,'instance_id':point['instance_id'],
                'partition':point['partition'],'method':method,'revision':revision,'status':result['status'],**cost,
                'net_input_saved_vs_M0':basecost['input_tokens']-cost['input_tokens'],
                'net_total_saved_vs_M0':basecost['total_tokens']-cost['total_tokens'],
                'summary_called':bool(result.get('summary')),'summary_adopted':bool((result.get('summary') or {}).get('adopted')),
                'stored_observations_without_original_or_reference_visible':len(hidden_refs),
                'missing_visible_reference_ids':hidden_refs,
                'recalls':len(result['recalls']),'registered_single_tool_decision':bool(action.get('valid')),
                'same_tool_vs_M0':action.get('name')==base['final_action'].get('name'),
                'same_action_vs_M0':signature(action)==signature(base['final_action']),
                'same_target_paths_vs_M0':selected_paths(action)==selected_paths(base['final_action']),
                'same_nonempty_target_paths_vs_M0':bool(selected_paths(action)|selected_paths(base['final_action'])) and selected_paths(action)==selected_paths(base['final_action']),
                'target_path_comparison_nonempty':bool(selected_paths(action)|selected_paths(base['final_action'])),
                'same_tool_vs_historical':action.get('name')==original.get('name'),
                'same_action_vs_historical':signature(action)==signature(original),
                'literal_retention':fact,'first_action':result.get('first_action'),'final_action':action,
                'historical_action':original,'M0_action':base['final_action'],
                'effective_payload':result['effective_payload'],'result':reference(RUN/'jobs'/result['job_id']/'result.json')}
            rows.append(row)
            if method!='M0':comparison_rows.append(row)
            if result.get('summary'):
                original_prefix='\n'.join(str(m.get('content',''))+text(m.get('tool_calls',[])) for m in base_input['messages'])
                summary=result['summary'].get('text','');summarylit=literals({'messages':[{'content':summary}]})
                summary_rows.append({'job_id':result['job_id'],'point_id':pid,'instance_id':point['instance_id'],
                    'partition':point['partition'],'revision':revision,'adopted':result['summary'].get('adopted'),
                    'summary':summary,'summary_reference':result['summary'],
                    'introduced_path_literals':sorted(v for v in summarylit['path_literals'] if v not in original_prefix),
                    'introduced_version_literals':sorted(v for v in summarylit['version_literals'] if v not in original_prefix),
                    'claims_need_semantic_audit':True,'new_literal_is_not_automatically_false':True})
    def aggregate(selected):
        g={'decisions':len(selected),'closed':sum(r['status']=='closed' for r in selected)}
        for key in ('physical_calls','input_tokens','output_tokens','total_tokens','cached_input_tokens','cost_nanoyuan',
                    'agent_input_tokens','agent_output_tokens','summary_input_tokens','summary_output_tokens',
                    'summary_called','summary_adopted','stored_observations_without_original_or_reference_visible',
                    'recalls','same_tool_vs_M0','same_action_vs_M0',
                    'same_target_paths_vs_M0','same_nonempty_target_paths_vs_M0','target_path_comparison_nonempty','same_tool_vs_historical','same_action_vs_historical',
                    'net_input_saved_vs_M0','net_total_saved_vs_M0'):
            g[key]=sum(r.get(key,0) for r in selected)
        for key in ('input_tokens','output_tokens','total_tokens'):
            g['mean_'+key]=g[key]/len(selected) if selected else None
        g['peak_tariff_CNY']=g['cost_nanoyuan']/1e9
        g['input_saving_fraction_vs_M0']=g['net_input_saved_vs_M0']/(g['input_tokens']+g['net_input_saved_vs_M0']) if selected else None
        g['net_input_wins_vs_M0']=sum(r['net_input_saved_vs_M0']>0 for r in selected)
        g['net_input_losses_vs_M0']=sum(r['net_input_saved_vs_M0']<0 for r in selected)
        g['points_with_hidden_stored_observations']=sum(r['stored_observations_without_original_or_reference_visible']>0 for r in selected)
        return g
    groups={g:aggregate([r for r in rows if r['method']+'-'+r['revision']==g]) for g in sorted(literal_totals)}
    holdout={g:aggregate([r for r in rows if r['method']+'-'+r['revision']==g and r['partition']=='holdout_history']) for g in groups}
    byrepo=defaultdict(list)
    for r in rows:byrepo[(r['method']+'-'+r['revision'],points[r['point_id']]['repo'])].append(r)
    repo_rows=[{'group':g,'repo':repo,**aggregate(items)} for (g,repo),items in sorted(byrepo.items())]
    total_known=total(calls)
    if total_known['total_tokens']!=run['budget']['known_actual_tokens']:raise ValueError('Usage total disagrees with ledger summary')
    if sum(g['total_tokens'] for g in groups.values())+total(byjob['guideline-development'])['total_tokens']!=total_known['total_tokens']:
        raise ValueError('Compressor or development usage was lost/double counted')
    value={'version':'v175-fixed-decision-replay-results-r3','groups':groups,'holdout_groups':holdout,
        'guideline_development':total(byjob['guideline-development']),'all_calls':total_known,
        'actual_models':dict(models),'actual_fingerprints':dict(fingerprints),'finish_reasons':dict(finishes),
        'remaining_nominal_CNY':250-total_known['cost_nanoyuan']/1e9,
        'literal_totals':{g:dict(c) for g,c in literal_totals.items()},'repository_strata':repo_rows,
        'rows':rows,'summary_cases':summary_rows,'real_context_read_calls':sum(r['recalls'] for r in rows),
        'all_context_recall_roundtrips_passed_offline':True,'replay_wall_seconds':run['wall_seconds'],
        'returning_one_registered_tool_is_not_World_permission_validation':True,
        'no_extra_M0_repeat_to_disentangle_sampling_noise':True,
        'behavior_agreement_is_not_task_correctness':True,'literal_retention_is_not_semantic_fidelity':True,
        'storage_presence_is_not_model_discoverability':True,
        'r1_recall_available_label_corrected_to_storage_present':True,
        'unique_source_points':48,'source_tasks':24,'source_environment':'historical C0 REVIEW2 member_001 private views',
        'fresh_S1_or_multiagent_episodes':0,'old_task_results_changed':False,
        'no_official_hidden_scores_in_replay':True,
        'inputs':{'run_summary':reference(RUN/'run-summary.json'),'plan':reference(RUN/'plan.json'),
            'frozen_sources':reference(RUN/'runtime-sources.json'),'API_ledger':reference(RUN/'api-ledger.sqlite')}}
    write_new(OUT/'summary.json',value)
    write_new(OUT/'canonical-completion.json',{'closed':True,'decision_replays':len(rows),
        'physical_requests':len(calls),'settled':len(calls),'technical_unknown':0,
        'all_usage':total_known,'remaining_nominal_CNY':value['remaining_nominal_CNY'],
        'unfinished_jobs':0,'unused_reservations':0,'old_ledger_written':False,
        'new_complete_task_results':0,'summary':reference(OUT/'summary.json')})
    print(json.dumps({'groups':groups,'holdout':holdout,'all':total_known,
        'summaries':len(summary_rows),'results':reference(OUT/'summary.json')},ensure_ascii=False))


if __name__=='__main__':main()
