"""Read-only outcome, usage and mechanism report for the frozen v181 pilot.

No model, Docker, GPU or scoring operations. Outputs are derived statistics;
the original ledger, candidates and all failed/uncalled identities are retained.
"""
import csv
import gzip
import hashlib
import json
import math
import os
import sqlite3
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean,median

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runs/software-benchmark-v181/full-context-pilot-r1'
FINAL=ROOT/'runs/software-benchmark-v189/lease-race-recovery-r1/api-coordinator/final.json'
LEDGER=ROOT/'runs/software-benchmark-v175/context-replay-r1/api-ledger.sqlite'
OUT=ROOT/'artifacts/software-benchmark-v190/context-pilot-report-r1'
GROUPS=('M0','M1-5','M1-10','M3-R')
USAGE=('input_tokens','output_tokens','total_tokens','cached_input_tokens','cache_miss_input_tokens')


def read(path):return json.loads(Path(path).read_bytes())
def ref(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def checked_read(value):
    assert ref(value['path'])==value,value['path']
    return read(value['path'])
def dump(name,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    path=OUT/(name+'.gz' if name=='ledger-snapshot.json' else name)
    path.write_bytes(gzip.compress(raw,mtime=0) if name=='ledger-snapshot.json' else raw)
    return ref(path)
def csv_write(name,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for row in rows:writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
def usage_total(requests):
    result={key:sum(q['usage'][key] for q in requests) for key in USAGE}
    result.update(requests=len(requests),cost_nanoyuan=sum(q['cost'] for q in requests),
        HTTP_seconds=sum(q['finished']-q['started'] for q in requests))
    return result
def wilson(k,n):
    z=1.959963984540054;p=k/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;delta=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [center-delta,center+delta]
def stop_details(boundary):
    return {m:{k:v.get(k) for k in ('status','reason','cause','budget_kind','limits','member_decisions') if k in v}
        for m,v in boundary.get('terminal_details',{}).items()}
def end_class(row,boundary):
    if row['generation_status']=='technical_unknown':return 'technical_unknown'
    details=json.dumps(stop_details(boundary)).lower()
    if 'context_capacity' in details or 'full_context_capacity' in details:return 'context_capacity'
    if any(s in details for s in ('input_plus_output','token_budget','total_token','token_limit','model_token','reservation')):return 'token_budget'
    if 'model_budget_exhausted' in details:return 'other_model_budget'
    if 'deadline' in details or 'time_limit' in details:return 'time_limit'
    return 'natural_or_other_closed'


def summarize(rows):
    entered=[r for r in rows if r['generation_status']!='not_started']
    closed=[r for r in rows if r['generation_status']=='closed']
    known=[r for r in rows if type(r['code']) is bool]
    usage={key:sum(r['usage'][key] for r in entered) for key in (*USAGE,'requests','cost_nanoyuan','HTTP_seconds')}
    purposes={p:{key:sum(r['usage_by_purpose'].get(p,{}).get(key,0) for r in entered) for key in (*USAGE,'requests','cost_nanoyuan','HTTP_seconds')}
        for p in ('agent','condenser')}
    return {'planned':len(rows),'entered':len(entered),'closed':len(closed),'code_scored':len(known),
        'code_pass':sum(r['code'] is True for r in rows),'code_fail':sum(r['code'] is False for r in rows),
        'delivery_pass':sum(r['delivery'] is True for r in rows),'delivery_known':sum(type(r['delivery']) is bool for r in rows),
        'technical_unknown':sum(r['generation_status']=='technical_unknown' for r in rows),
        'not_started':sum(r['generation_status']=='not_started' for r in rows),
        'usage':usage,'usage_by_purpose':purposes,
        'mean_closed_tokens':mean(r['usage']['total_tokens'] for r in closed) if closed else None,
        'median_closed_tokens':median(r['usage']['total_tokens'] for r in closed) if closed else None,
        'mean_observed_tokens_entered_including_partial':usage['total_tokens']/len(entered) if entered else None,
        'mean_closed_input_tokens':mean(r['usage']['input_tokens'] for r in closed) if closed else None,
        'mean_closed_output_tokens':mean(r['usage']['output_tokens'] for r in closed) if closed else None,
        'ends':dict(Counter(r['end_class'] for r in entered)),
        'end_by_code':{kind:dict(Counter(str(r['code']) for r in entered if r['end_class']==kind)) for kind in sorted({r['end_class'] for r in entered})},
        'context_metrics':{key:sum(r['context_metrics'].get(key,0) for r in entered) for key in (
            'generated_adopted_summaries','actual_agent_presentations','epoch_validity_proxy_presentations','historical_only_presentations','completed_cycles')},
        'wire_observation_masking':{'requests':sum(r['masking']['requests'] for r in entered),
            'message_exposures':sum(r['masking']['message_exposures'] for r in entered)},
        'response_tool_choices':dict(sum((Counter(r['response_tool_choices']) for r in entered),Counter())),
        'boundary_outcome_statuses':dict(sum((Counter(r['boundary_outcome_statuses']) for r in entered),Counter())),
        'mean_closed_agent_decisions':mean(r['agent_decisions'] for r in closed) if closed else None,
        'mean_closed_actions':mean(r['world_actions'] for r in closed) if closed else None,
        'mean_closed_API_span_seconds':mean(r['API_span_seconds'] for r in closed) if closed else None,
        'cache_hit_fraction':usage['cached_input_tokens']/usage['input_tokens'] if usage['input_tokens'] else None}


def main():
    available=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,set(available[-2:]))
    OUT.mkdir(parents=True,exist_ok=True)
    plan=read(RUN/'execution-plan.json');final=read(FINAL)
    assert final['stage']=='closed' and not final['generation_active'] and not final['grading_active']
    assert not list((RUN/'resource-claims').glob('active-*.json'))
    with sqlite3.connect(LEDGER.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        requests=[dict(r) for r in db.execute('SELECT * FROM requests ORDER BY started,request_id')]
        jobs={r['job_id']:dict(r) for r in db.execute('SELECT * FROM jobs')}
        amendments=[dict(r) for r in db.execute('SELECT * FROM cash_amendments_v187')]
        policy=read_policy=json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
    assert all(r['status']=='settled' for r in requests)
    for q in requests:q['usage']=json.loads(q['usage'])
    original_slots={r['slot_id'] for r in plan['rows']}
    phase=[q for q in requests if q['job_id'] in original_slots]
    assert all(q['job_id'] in original_slots for q in requests if q['job_id'].startswith('v181:'))
    by_job=defaultdict(list)
    for q in phase:by_job[q['job_id']].append(q)
    scores=defaultdict(dict);score_evidence=[]
    for value in final['scores'].values():
        slot,endpoint=value['slot_id'],value['endpoint']
        assert endpoint not in scores[slot]
        receipt=checked_read(value['receipt'])
        assert type(value.get('resolved')) is bool
        assert receipt.get('resolved')==value['resolved']
        if endpoint=='code':assert receipt['status']=='official_report'
        scores[slot][endpoint]=value
        score_evidence.append(value['receipt'])
    rows=[];audit_rows=[];response_models=Counter();fingerprints=Counter();all_tools=Counter()
    for item in plan['rows']:
        slot=item['slot_id'];physical=by_job[slot]
        row={k:item[k] for k in ('slot_id','slot_index','instance_id','repo','group_id','repeat_index','primary_panel','framework_seed')}
        row.update(generation_status='not_started',code=None,delivery=None,usage=usage_total(physical),
            usage_by_purpose={p:usage_total([q for q in physical if q['purpose']==p]) for p in ('agent','condenser')},
            context_metrics={},masking={'requests':0,'message_exposures':0},response_tool_choices={},
            end_class='not_started',boundary_outcome_statuses={},agent_decisions=0,world_actions=0,
            API_span_seconds=0,terminal_details={},evidence={})
        folder=RUN/'episodes'/str(item['slot_index'])
        if not physical:
            assert slot not in final['records'] and slot not in jobs and not folder.exists()
            rows.append(row);continue
        record=final['records'][slot];result=checked_read(record['result'])
        quiet=checked_read(result['quiescence'])
        assert quiet['all_owned_objects_removed'] and not quiet['cleanup_errors']
        assert result['slot_id']==slot and result['configuration']==item['configuration']
        row.update(generation_status=result['status'],code=scores[slot].get('code',{}).get('resolved'),
            delivery=scores[slot].get('delivery',{}).get('resolved'),
            API_span_seconds=max(q['finished'] for q in physical)-min(q['started'] for q in physical),
            evidence={'result':record['result'],'quiescence':result['quiescence'],
                'code_score':scores[slot].get('code',{}).get('receipt'),'delivery_score':scores[slot].get('delivery',{}).get('receipt')})
        controller=read(folder/'controller-output/controller-result.json')
        boundary=read(folder/'controller-output/managed-boundary.json')
        model_ledger=read(folder/'controller-output/model-ledger/ledger.json')
        assert model_ledger['known_actual_tokens']==row['usage']['total_tokens']
        if row['generation_status']=='closed':assert result['known_actual_tokens']==row['usage']['total_tokens']
        row.update(context_metrics=controller.get('context_management',{}).get('member_001',{}),
            terminal_details=stop_details(boundary),world_actions=boundary['actions'],
            agent_decisions=model_ledger['decisions'],model_halts=model_ledger.get('member_halts'),
            boundary_outcome_statuses=dict(Counter(o.get('status') for o in boundary.get('outcomes',[]))))
        row['end_class']=end_class(row,boundary)
        if row['generation_status']=='technical_unknown':
            reason=read(ROOT/f"artifacts/software-benchmark-v186/context-failure-analysis-r1/{item['slot_index']}.json")
            row['technical_failure']=reason['interface_errors']
        capture_map={}
        for path in (folder/'controller-output/model-ledger/request-capture-v181').glob('*/provenance.json'):
            capture=read(path);request_id=capture['identity']['request_id']
            assert request_id not in capture_map
            capture_map[request_id]=(path.parent,capture)
        assert len(capture_map)==len({str(q['step']) for q in physical})
        provenance_bytes=Counter();tools=Counter();mask_requests=0;mask_exposures=0;wire_limits=Counter();context_reads=[]
        for q in physical:
            assert q['attempt']==1,'Physical retry requires separate logical mapping'
            directory,capture=capture_map[str(q['step'])]
            payload=(directory/'payload.json').read_bytes()
            assert hashlib.sha256(payload).hexdigest()==q['payload_sha']==capture['payload_sha256']
            response=checked_read(json.loads(q['response_ref']))
            assert response==read(directory/'response-original.json')
            usage=response['usage'];u=q['usage']
            assert (usage['prompt_tokens'],usage['completion_tokens'],usage['total_tokens'])==(u['input_tokens'],u['output_tokens'],u['total_tokens'])
            assert u['input_tokens']+u['output_tokens']==u['total_tokens']
            assert u['cached_input_tokens']+u['cache_miss_input_tokens']==u['input_tokens']
            assert usage.get('prompt_cache_hit_tokens',usage.get('prompt_tokens_details',{}).get('cached_tokens',0))==u['cached_input_tokens']
            assert usage.get('prompt_cache_miss_tokens',u['input_tokens']-u['cached_input_tokens'])==u['cache_miss_input_tokens']
            response_models[response.get('model')]+=1;fingerprints[response.get('system_fingerprint')]+=1
            wire=json.loads(payload)
            n=sum(isinstance(m.get('content'),str) and '[Earlier private observation retained at ctx:' in m['content'] for m in wire['messages'])
            if q['purpose']=='agent':mask_requests+=bool(n);mask_exposures+=n
            wire_limits[str(wire.get('max_tokens',wire.get('max_completion_tokens')))]+=1
            for call in response['choices'][0]['message'].get('tool_calls') or []:
                name=call.get('function',{}).get('name');tools[name]+=1
                if name=='context_read':context_reads.append({'request_id':q['request_id'],'arguments':call['function']['arguments']})
            for k in ('semantic_payload_bytes','semantic_attributed_payload_bytes','unattributed_payload_bytes','payload_bytes'):
                provenance_bytes[k]+=capture.get(k,0)
        row['response_tool_choices']=dict(tools);all_tools.update(tools)
        row['context_read_tool_choices']=context_reads
        row['masking']={'requests':mask_requests,'message_exposures':mask_exposures}
        row['wire_output_caps']=dict(wire_limits)
        audit_rows.append({'slot_index':item['slot_index'],'slot_id':slot,'requests':len(physical),
            'request_response_usage_exact_match':True,'physical_retries':0,
            'controller_ledger_matches_physical_usage':True,'source_bytes':dict(provenance_bytes),
            'source_token_mapping_estimation_recomputed':False})
        rows.append(row)
        print(f"audited {item['slot_index']} {item['group_id']} {len(physical)} calls",flush=True)
    primary=[r for r in rows if r['primary_panel']];repeats=[r for r in rows if not r['primary_panel']]
    groups={g:summarize([r for r in primary if r['group_id']==g]) for g in GROUPS}
    by_task=defaultdict(dict)
    for row in primary:by_task[row['instance_id']][row['group_id']]=row
    common=[task for task,values in by_task.items() if all(type(r['code']) is bool for r in values.values())]
    matched={g:summarize([by_task[t][g] for t in common]) for g in GROUPS}
    pairs={}
    for g in GROUPS[1:]:
        comparable=[(v['M0'],v[g]) for v in by_task.values() if type(v[g]['code']) is bool]
        pairs[g]={'tasks':len(comparable),'both_pass':sum(a['code'] and b['code'] for a,b in comparable),
            'both_fail':sum(not a['code'] and not b['code'] for a,b in comparable),
            'gain_tasks':[b['instance_id'] for a,b in comparable if not a['code'] and b['code']],
            'loss_tasks':[b['instance_id'] for a,b in comparable if a['code'] and not b['code']],
            'excluded_unknown_tasks':[t for t,v in by_task.items() if v[g]['code'] is None]}
    repeat_pairs=[]
    for r in repeats:
        first=by_task[r['instance_id']][r['group_id']]
        repeat_pairs.append({'instance_id':r['instance_id'],'repo':r['repo'],'group_id':r['group_id'],
            'primary_index':first['slot_index'],'repeat_index':r['slot_index'],'first_code':first['code'],
            'repeat_code':r['code'],'repeat_generation_status':r['generation_status'],
            'first_tokens':first['usage']['total_tokens'],'repeat_tokens':r['usage']['total_tokens'] if r['generation_status']!='not_started' else None,
            'flipped':first['code']!=r['code'] if type(r['code']) is bool else None})
    comparisons={}
    for g in GROUPS[1:]:
        a=groups['M0'];b=groups[g]
        comparisons[g]={'observed_total_token_change_fraction':b['usage']['total_tokens']/a['usage']['total_tokens']-1,
            'observed_input_change_fraction':b['usage']['input_tokens']/a['usage']['input_tokens']-1,
            'observed_cost_change_fraction':b['usage']['cost_nanoyuan']/a['usage']['cost_nanoyuan']-1,
            'full12_trajectory_comparison_valid':b['technical_unknown']==0,
            'common10_total_token_change_fraction':matched[g]['usage']['total_tokens']/matched['M0']['usage']['total_tokens']-1,
            'agent_call_ratio':b['usage_by_purpose']['agent']['requests']/a['usage_by_purpose']['agent']['requests'],
            'agent_mean_input_ratio':(b['usage_by_purpose']['agent']['input_tokens']/b['usage_by_purpose']['agent']['requests'])/(a['usage_by_purpose']['agent']['input_tokens']/a['usage_by_purpose']['agent']['requests'])}
    task_rows=[{'instance_id':t,'repo':v['M0']['repo'],**{g:v[g]['code'] for g in GROUPS},
        **{g+'_tokens':v[g]['usage']['total_tokens'] for g in GROUPS},
        **{g+'_end':v[g]['end_class'] for g in GROUPS}} for t,v in by_task.items()]
    repo_summary={repo:{g:summarize([r for r in primary if r['repo']==repo and r['group_id']==g]) for g in GROUPS}
        for repo in sorted({r['repo'] for r in primary})}
    old=[q for q in requests if q['job_id'] not in original_slots]
    cumulative=usage_total(requests);phase_usage=usage_total(phase);historical=usage_total(old)
    assert phase_usage['total_tokens']+historical['total_tokens']==cumulative['total_tokens']
    assert phase_usage['cost_nanoyuan']+historical['cost_nanoyuan']==cumulative['cost_nanoyuan']
    for g,values in groups.items():
        values['full_panel_code_rate_bounds']=[values['code_pass']/values['planned'],(values['code_pass']+values['technical_unknown'])/values['planned']]
        values['descriptive_wilson95']=(wilson(values['code_pass'],values['planned']) if not values['technical_unknown'] else None)
    ledger_identity={'policy':policy,'amendments':amendments,'requests':[{k:q[k] for k in ('request_id','job_id','status','cost','usage','payload_sha','response_ref','started','finished')} for q in requests]}
    ledger_export=dump('ledger-snapshot.json',ledger_identity)
    outputs={'episodes':dump('episodes.json',rows),'capture_audit':dump('capture-audit.json',audit_rows),
        'paired_primary':dump('primary-tasks.json',task_rows),'repeat_pairs':dump('repeat-pairs.json',repeat_pairs),
        'ledger_snapshot':ledger_export}
    summary={'version':'v190-context-pilot-report-r1','generated_at':datetime.now(timezone.utc).isoformat(),
        'plan':ref(RUN/'execution-plan.json'),'final_progress':ref(FINAL),'phase':summarize(rows),
        'primary':groups,'repeat':{g:summarize([r for r in repeats if r['group_id']==g]) for g in ('M0','M1-10')},
        'common_complete_tasks':common,'common_complete':matched,'repository_strata':repo_summary,
        'paired_code_vs_M0':pairs,'token_comparisons':comparisons,
        'repeat_distributions':{g:dict(Counter(str(int(r['first_code'])+int(r['repeat_code']))+'/2' for r in repeat_pairs if r['group_id']==g and r['repeat_code'] is not None)) for g in ('M0','M1-10')},
        'repeat_flips':{g:sum(r['flipped'] is True for r in repeat_pairs if r['group_id']==g) for g in ('M0','M1-10')},
        'cost_scope':{'current_phase':phase_usage,'historical_before_phase':historical,'cumulative_ledger':cumulative,
            'cumulative_admission_cap_nanoyuan':max(a['effective_cap'] for a in amendments),
            'remaining_nanoyuan':max(a['effective_cap'] for a in amendments)-cumulative['cost_nanoyuan'],
            'inflight_or_unknown_requests':0,'current_active_leases':0,'final_new_admission_cash_closed':final['new_admission_cash_closed'],
            'currency_is_peak_tariff_upper_bound_not_provider_invoice':True},
        'capture_audit':{'episodes':len(audit_rows),'physical_requests':sum(r['requests'] for r in audit_rows),
            'all_request_response_usage_matched':True,'source_token_attribution_full_phase_not_recomputed':True,
            'provider_cache_fields_match_ledger':True,
            'models':dict(response_models),'fingerprints':dict(fingerprints)},
        'outputs':outputs,'new_model_calls':0,'new_Docker_objects':0,'new_GPU_use':0,'original_records_changed':False}
    output=dump('summary.json',summary)
    csv_write('episodes.csv',[{k:r[k] for k in ('slot_index','instance_id','repo','group_id','repeat_index','primary_panel','generation_status','code','delivery','end_class','agent_decisions','world_actions','API_span_seconds')}
        |r['usage']|{'terminal_details':r['terminal_details']} for r in rows])
    csv_write('primary-tasks.csv',task_rows);csv_write('repeat-pairs.csv',repeat_pairs)
    dump('evidence.json',{'source_files':[ref(__file__),ref(RUN/'execution-plan.json'),ref(FINAL)],
        'score_receipts':score_evidence,'ledger_snapshot':ledger_export,'originals_immutable':True})
    print(json.dumps({'summary':output,'phase_tokens':phase_usage['total_tokens'],'phase_CNY':phase_usage['cost_nanoyuan']/1e9,
        'entered':summary['phase']['entered'],'scored':summary['phase']['code_scored'],'physical_requests':len(phase)},ensure_ascii=False))


if __name__=='__main__':main()
