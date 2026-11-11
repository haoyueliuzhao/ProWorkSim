"""Read-only 60-episode outcome, usage and critical-card audit for v193."""
from __future__ import annotations
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, median

from proworksim import software_benchmark_scope_v193 as scope
from proworksim.software_context_compression_v175 import digest, is_observation
from proworksim.software_context_critical_v191 import PREFIX, RULES, _pointer
from proworksim.software_collaboration_observation_v141 import load_official_content_counter

ROOT = scope.ROOT
RUN = scope.BATCH_ROOT
OUT = ROOT / 'artifacts/software-benchmark-v195/context-report-r1'
GROUPS = scope.GROUP_IDS
USAGE = ('input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens', 'cache_miss_input_tokens')


def read(path):return json.loads(Path(path).read_bytes())
def ref(path):
    path = Path(path).resolve(); raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
def checked(value):
    assert ref(value['path']) == value, value['path']
    return read(value['path'])
def save(name, value):
    path = OUT / name; path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if name.endswith('.gz') else raw)
    return ref(path)
def csv_save(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n'); writer.writeheader()
        for row in rows:writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v for k,v in row.items()})
def usage_total(calls):
    return {**{k: sum(c['usage'][k] for c in calls) for k in USAGE}, 'requests': len(calls),
            'cost_nanoyuan': sum(c['cost'] for c in calls),
            'HTTP_seconds': sum(c['finished']-c['started'] for c in calls)}


def provenance_header(path):
    # The canonical manifest places the large spans array after these fields.
    # Read only the header: this does not independently audit every span.
    data = b''
    with path.open('rb') as stream:
        while b',"spans":' not in data:
            block = stream.read(4096)
            if not block or len(data) > 1024**2:raise ValueError('Unexpected capture layout')
            data += block
    return json.loads(data.split(b',"spans":',1)[0] + b'}')


def ending(boundary):
    text = json.dumps(boundary.get('terminal_details', {})).lower()
    if 'context_capacity' in text:return 'context_capacity'
    if any(x in text for x in ('max_total_tokens','token_budget','total_token','conservative_reservation')):return 'token_budget'
    if any(x in text for x in ('deadline','time_limit')):return 'time_limit'
    if 'model_budget_exhausted' in text:return 'other_model_budget'
    return 'natural_or_other_closed'


def summarize(rows):
    fields = (*USAGE, 'requests', 'cost_nanoyuan', 'HTTP_seconds')
    usage = {k: sum(r['usage'][k] for r in rows) for k in fields}
    purposes = {p: {k: sum(r['usage_by_purpose'][p][k] for r in rows) for k in fields} for p in ('agent','condenser')}
    cards = Counter(); categories=Counter(); versions=Counter(); tests=Counter(); tools=Counter()
    for r in rows:
        cards.update(r['critical_numeric']);categories.update(r['critical_categories'])
        versions.update(r['critical_version_statuses']);tests.update(r['public_test_statistics']);tools.update(r['tool_choices'])
    return {'n':len(rows), 'code_pass':sum(r['code'] for r in rows), 'delivery_pass':sum(r['delivery'] for r in rows),
        'usage':usage, 'usage_by_purpose':purposes,
        'mean_total_tokens':mean(r['usage']['total_tokens'] for r in rows),
        'median_total_tokens':median(r['usage']['total_tokens'] for r in rows),
        'mean_agent_input_per_request':purposes['agent']['input_tokens']/purposes['agent']['requests'],
        'agent_requests_per_task':purposes['agent']['requests']/len(rows),
        'mean_actions':mean(r['world_actions'] for r in rows),
        'mean_API_span_seconds':mean(r['API_span_seconds'] for r in rows),
        'median_API_span_seconds':median(r['API_span_seconds'] for r in rows),
        'ends':dict(Counter(r['end_class'] for r in rows)),
        'end_by_code':{end:dict(Counter(str(r['code']) for r in rows if r['end_class']==end)) for end in sorted({r['end_class'] for r in rows})},
        'generated_adopted_summaries':sum(r['context_metrics'].get('generated_adopted_summaries',0) for r in rows),
        'critical_numeric':dict(cards),'critical_categories':dict(categories),'critical_version_statuses':dict(versions),
        'public_tests':dict(tests),'tool_choices':dict(tools),
        'cache_hit_fraction':usage['cached_input_tokens']/usage['input_tokens'],
        'total_tokens_per_legal_delivery':usage['total_tokens']/sum(r['delivery'] for r in rows),
        'cost_upper_CNY_per_legal_delivery':usage['cost_nanoyuan']/1e9/sum(r['delivery'] for r in rows)}


def main():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:]);os.nice(10)
    OUT.mkdir(parents=True,exist_ok=True)
    plan=read(scope.PLAN_FILE);final=read(scope.API_ROOT/'final.json')
    assert final['stage']=='closed' and not final['exceptions'] and len(plan['rows'])==60
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        calls=[dict(r) for r in db.execute('SELECT * FROM requests ORDER BY started,request_id')]
        jobs={r['job_id']:dict(r) for r in db.execute('SELECT * FROM jobs')}
        policy=json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
    assert len(calls)==2843 and all(c['status']=='settled' and c['attempt']==1 for c in calls)
    assert {r['slot_id'] for r in plan['rows']}==set(jobs) and all(j['status']=='closed' for j in jobs.values())
    by_job=defaultdict(list)
    for c in calls:c['usage']=json.loads(c['usage']);by_job[c['job_id']].append(c)
    scores={(r['slot_id'],r['endpoint']):r for r in final['scores'].values()}
    assert len(scores)==120
    token_manifest=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,tokenizer=load_official_content_counter(token_manifest,manifest_sha256=ref(token_manifest)['sha256'])
    token_cache={}
    def text_tokens(text):
        key=hashlib.sha256(text.encode()).hexdigest()
        if key not in token_cache:token_cache[key]=count(text)
        return token_cache[key]
    spec=importlib.util.spec_from_file_location('public_test_audit',ROOT/'tools/audit_context_evidence_v191.py')
    test_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(test_module);test_module.RUN=RUN
    tests,test_groups=test_module.audit_tests(plan['rows'])
    tests_by_slot=defaultdict(list)
    for test in tests:tests_by_slot[test['slot_index']].append(test)
    rows=[];request_rows=[];card_rows=[];models=Counter();fingerprints=Counter();action_rows=[]
    for item in plan['rows']:
        slot=item['slot_id'];physical=by_job[slot];index=item['slot_index']
        folder=RUN/'episodes'/str(index);output=folder/'controller-output'
        record=final['records'][slot];result=checked(record['result'])
        boundary=read(output/'managed-boundary.json');controller=read(output/'controller-result.json')
        ledger=read(output/'model-ledger/ledger.json');observation=read(output/'model-ledger/collaboration-observation/summary.json')
        code_receipt=checked(scores[(slot,'code')]['receipt']);delivery_receipt=checked(scores[(slot,'delivery')]['receipt'])
        assert result['status']=='closed' and code_receipt['status']=='official_report'
        assert code_receipt['resolved'] is scores[(slot,'code')]['resolved'] and delivery_receipt['resolved'] is scores[(slot,'delivery')]['resolved']
        u=usage_total(physical);assert u['total_tokens']==result['known_actual_tokens']==ledger['known_actual_tokens']
        assert not observation['runtime_measurement_errors'] and observation['source_presentations']['requests']==len(physical)
        row={k:item[k] for k in ('slot_id','slot_index','instance_id','repo','group_id','repeat_index','primary_panel','framework_seed')}
        row.update(code=code_receipt['resolved'],delivery=delivery_receipt['resolved'],usage=u,
            usage_by_purpose={p:usage_total([c for c in physical if c['purpose']==p]) for p in ('agent','condenser')},
            end_class=ending(boundary),terminal_details=boundary.get('terminal_details',{}),world_actions=boundary['actions'],
            agent_decisions=ledger['decisions'],context_metrics=controller['context_management']['member_001'],
            API_span_seconds=max(c['finished'] for c in physical)-min(c['started'] for c in physical),
            first_API_unix=min(c['started'] for c in physical),last_API_unix=max(c['finished'] for c in physical),
            delivery_status=delivery_receipt['status'],legal_submission=delivery_receipt.get('legal_submission'),
            evidence={'result':record['result'],'code_score':scores[(slot,'code')]['receipt'],'delivery_score':scores[(slot,'delivery')]['receipt']})
        official=code_receipt['official_result'][1][item['instance_id']]
        row['official_failures']={k:v.get('failure',[]) for k,v in official.get('tests_status',{}).items()}
        row['patch_applied']=official.get('patch_successfully_applied')
        row['candidate_patch']=ref(folder/'candidate.patch')
        row['changed_patch_headers']=[line for line in (folder/'candidate.patch').read_text(errors='replace').splitlines() if line.startswith('diff --git ')]
        known={};unique_cards=set();unique_verified=set();tools=Counter();numeric=Counter();categories=Counter();versions=Counter();seen_tool_returns=set();tool_returns=[]
        capture_root=output/'model-ledger/request-capture-v193'
        assert len(list(capture_root.glob('*/payload.json')))==len(physical)
        for c in physical:
            directory=capture_root/hashlib.sha256(str(c['step']).encode()).hexdigest()
            header=provenance_header(directory/'provenance.json');raw=(directory/'payload.json').read_bytes()
            assert header['identity']['request_id']==str(c['step'])
            assert hashlib.sha256(raw).hexdigest()==c['payload_sha']==header['payload_sha256']
            wire=json.loads(raw);response=checked(json.loads(c['response_ref']))
            assert response==read(directory/'response-original.json')
            ru=response['usage'];cu=c['usage']
            assert (ru['prompt_tokens'],ru['completion_tokens'],ru['total_tokens'])==(cu['input_tokens'],cu['output_tokens'],cu['total_tokens'])
            assert cu['input_tokens']+cu['output_tokens']==cu['total_tokens'] and cu['cached_input_tokens']+cu['cache_miss_input_tokens']==cu['input_tokens']
            assert ru.get('prompt_cache_hit_tokens',ru.get('prompt_tokens_details',{}).get('cached_tokens',0))==cu['cached_input_tokens']
            assert ru.get('prompt_cache_miss_tokens',cu['input_tokens']-cu['cached_input_tokens'])==cu['cache_miss_input_tokens']
            models[response.get('model')]+=1;fingerprints[response.get('system_fingerprint')]+=1
            projection=read(directory/'projection-evidence.json');treatment=projection.get('observation_history_projection',{}).get('context_treatment',{})
            cards=treatment.get('critical_cards',[]);indices=projection.get('selected_indices',[])
            assert not cards or item['group_id']=='M1-5K'
            numeric['agent_requests_with_cards']+=bool(cards)
            numeric['card_exposures']+=len(cards)
            numeric['card_tokens_local_estimate']+=treatment.get('critical_card_tokens_estimate',0)
            numeric['card_budget_fallback_events']+=len(treatment.get('critical_fallbacks',[]))
            numeric['masked_observation_exposures']+=len(treatment.get('masked',[]))
            numeric['requests_with_masking']+=bool(treatment.get('masked'))
            for card in cards:
                i=card['index'];text=wire['messages'][i]['content'];assert text.startswith(PREFIX)
                parsed=json.loads(text[len(PREFIX):]);assert parsed['fields']==card['fields']
                assert parsed['original']['message_sha256']==card['source_sha256'] and parsed['current_version_validated'] is False
                amount=text_tokens(text);assert amount==card['tokens_estimate']
                marker='[Earlier private observation retained at '+card['reference']+'. Use context_read for the exact original; it is historical evidence.]'
                numeric['card_extra_over_marker_tokens_local_estimate']+=amount-text_tokens(marker)
                key=(parsed['original']['message_index'],card['selected_observation_sha256'])
                old=known.get(key);field_proof=False
                if old is not None:
                    body=json.loads(old['content'])
                    for field in card['fields']:
                        exists,value=_pointer(body,field['pointer']);assert exists
                        if field.get('excerpt'):value=value[field['start']:field['end']]
                        assert value==field['value']
                    field_proof=True;unique_verified.add(card['reference'])
                numeric['card_exposures_with_prior_wire_field_match']+=field_proof
                categories[card['category']]+=1;versions[card['version_status']]+=1
                if card['reference'] not in unique_cards:
                    unique_cards.add(card['reference'])
                    card_rows.append({'slot_index':index,'instance_id':item['instance_id'],'reference':card['reference'],
                        'category':card['category'],'first_observed_request':c['request_id'],'version_status_at_first_card':card['version_status'],
                        'field_pointers':[f['pointer'] for f in card['fields']], 'fields':card['fields'],
                        'prior_actual_wire_field_match_at_first_card':field_proof,'payload':ref(directory/'payload.json'),
                        'projection':ref(directory/'projection-evidence.json')})
            for i,message in enumerate(wire['messages']):
                content=message.get('content')
                if message.get('role')=='tool' and message.get('tool_call_id') not in seen_tool_returns and isinstance(content,str):
                    if not content.startswith(('[Earlier private observation',PREFIX)):
                        try:body=json.loads(content)
                        except ValueError:body={}
                        if isinstance(body,dict):
                            tool_returns.append({'call_id':message.get('tool_call_id'),'body':body,'request_id':c['request_id']})
                        seen_tool_returns.add(message.get('tool_call_id'))
                if item['group_id']=='M1-5K' and c['purpose']=='agent' and i<len(indices) and is_observation(message):
                    if not content.startswith(('[Earlier private observation',PREFIX)):
                        known[(indices[i],digest(message))]=message
            for call in response['choices'][0]['message'].get('tool_calls') or []:
                function=call['function'];tools[function['name']]+=1
                try:arguments=json.loads(function['arguments'])
                except (ValueError,TypeError):arguments={'unparsed':function['arguments']}
                action_rows.append({'slot_index':index,'group_id':item['group_id'],'instance_id':item['instance_id'],
                    'primary_panel':item['primary_panel'],'request_id':c['request_id'],'logical_id':str(c['step']),
                    'call_id':call['id'],'tool':function['name'],'arguments':arguments,
                    'input_tokens':cu['input_tokens'],'output_tokens':cu['output_tokens'],
                    'started':c['started'],'finished':c['finished'],'response':json.loads(c['response_ref'])})
            request_rows.append({'slot_index':index,'group_id':item['group_id'],'primary_panel':item['primary_panel'],
                'purpose':c['purpose'],'request_id':c['request_id'],'usage':cu,'HTTP_seconds':c['finished']-c['started'],
                'critical_cards':len(cards),'critical_card_tokens_local_estimate':treatment.get('critical_card_tokens_estimate',0),
                'fallbacks':len(treatment.get('critical_fallbacks',[])), 'masked_observations':len(treatment.get('masked',[])),
                'payload_response_usage_match':True,
                'runtime_reported_semantic_bytes':header['semantic_payload_bytes'],
                'runtime_reported_unattributed_semantic_bytes':header['semantic_payload_bytes']-header['semantic_attributed_payload_bytes']})
        numeric['unique_source_cards']=len(unique_cards);numeric['unique_source_cards_with_prior_wire_field_match']=len(unique_verified)
        row.update(critical_numeric=dict(numeric),critical_categories=dict(categories),critical_version_statuses=dict(versions),tool_choices=dict(tools))
        selected=tests_by_slot[index]
        row['public_test_statistics']={'executed':len(selected),'passed':sum(r['passed'] is True for r in selected),
            'wall_seconds':sum(r['wall_seconds'] or 0 for r in selected),'exact_repeats':sum(r['exact_identity_repeat'] for r in selected),
            'repeats_after_pass':sum(r['previous_equal_identity_passed'] is True for r in selected),
            'new_tree_same_selector':sum(r['same_selector_after_changed_tree'] for r in selected)}
        row['observer_public_tests']=observation['public_tests'];row['source_capture_runtime']=observation['source_presentations']
        row['tool_returns']=save('tool-returns/'+str(index)+'.json',tool_returns)
        rows.append(row);save('episodes/'+str(index)+'.json',row)
        print(index,item['group_id'],u['total_tokens'],row['end_class'],'cards',numeric['card_exposures'],flush=True)
    primary=[r for r in rows if r['primary_panel']];repeats=[r for r in rows if not r['primary_panel']]
    groups={g:summarize([r for r in primary if r['group_id']==g]) for g in GROUPS}
    by_task=defaultdict(dict)
    for r in primary:by_task[r['instance_id']][r['group_id']]=r
    task_rows=[{'instance_id':t,'repo':v['M0']['repo'],**{g:v[g]['code'] for g in GROUPS},
        **{g+'_delivery':v[g]['delivery'] for g in GROUPS},**{g+'_tokens':v[g]['usage']['total_tokens'] for g in GROUPS},
        **{g+'_end':v[g]['end_class'] for g in GROUPS}} for t,v in by_task.items()]
    repeat_pairs=[]
    for r in repeats:
        a=by_task[r['instance_id']][r['group_id']]
        repeat_pairs.append({'instance_id':r['instance_id'],'group_id':r['group_id'],'first_index':a['slot_index'],'repeat_index':r['slot_index'],
            'first_code':a['code'],'repeat_code':r['code'],'first_delivery':a['delivery'],'repeat_delivery':r['delivery'],
            'first_tokens':a['usage']['total_tokens'],'repeat_tokens':r['usage']['total_tokens'],
            'code_flip':a['code']!=r['code'],'delivery_flip':a['delivery']!=r['delivery']})
    paired={}
    for a,b in [('M0',g) for g in GROUPS[1:]]+[('M1-5','M1-5K')]:
        paired[a+'__'+b]={'gain_tasks':[t for t,v in by_task.items() if v[b]['code'] and not v[a]['code']],
            'loss_tasks':[t for t,v in by_task.items() if v[a]['code'] and not v[b]['code']],
            'token_ratio':groups[b]['usage']['total_tokens']/groups[a]['usage']['total_tokens'],
            'agent_request_ratio':groups[b]['usage_by_purpose']['agent']['requests']/groups[a]['usage_by_purpose']['agent']['requests'],
            'agent_mean_input_ratio':groups[b]['mean_agent_input_per_request']/groups[a]['mean_agent_input_per_request']}
    evidence={'plan':ref(scope.PLAN_FILE),'final':ref(scope.API_ROOT/'final.json'),
        'ledger_snapshot':save('ledger-snapshot.json.gz',{'policy':policy,'requests':calls,'jobs':jobs}),
        'source':ref(__file__),'tokenizer':tokenizer}
    outputs={name:save(name,value) for name,value in {'episodes.json':rows,'requests.json':request_rows,'critical-cards.json':card_rows,
        'actions.json':action_rows,'public-tests.json':tests,'primary-tasks.json':task_rows,'repeat-pairs.json':repeat_pairs}.items()}
    repeats_summary={g:{'additional_runs':summarize([r for r in repeats if r['group_id']==g]),
        'two_run_code_distribution':dict(Counter(str(int(r['first_code'])+int(r['repeat_code']))+'/2' for r in repeat_pairs if r['group_id']==g)),
        'code_flips':sum(r['code_flip'] for r in repeat_pairs if r['group_id']==g),
        'delivery_flips':sum(r['delivery_flip'] for r in repeat_pairs if r['group_id']==g)} for g in ('M0','M1-10')}
    gaps=[];end=0
    for c in calls:
        if end and c['started']>end:gaps.append({'start':end,'end':c['started'],'seconds':c['started']-end})
        end=max(end,c['finished'])
    summary={'version':'v195-key-event-context-report-r1','generated_at':datetime.now(timezone.utc).isoformat(),
        'primary':groups,'repeat':repeats_summary,'paired':paired,'all_usage':usage_total(calls),
        'primary_usage':usage_total([c for c in calls if next(r for r in rows if r['slot_id']==c['job_id'])['primary_panel']]),
        'source_models':dict(models),'response_fingerprints':dict(fingerprints),
        'actual_HTTP_requests_matched':len(calls),'actual_retries':0,'unknown':0,
        'runtime_reported_unattributed_semantic_bytes':sum(r['runtime_reported_unattributed_semantic_bytes'] for r in request_rows),
        'full_source_span_token_attribution_not_recomputed':True,
        'card_tokens_are_local_estimates_not_extra_provider_billing':True,
        'longest_no_HTTP_intervals':sorted(gaps,key=lambda r:r['seconds'],reverse=True)[:8],
        'no_HTTP_intervals_include_tools_environment_archive_and_disk_wait_not_pure_GPU_API_time':True,
        'evidence':evidence,'outputs':outputs,'new_model_calls':0,'new_Docker_objects':0,'new_GPU_operations':0,'original_records_modified':False}
    save('summary.json',summary)
    csv_save('episodes.csv',[{k:r[k] for k in ('slot_index','instance_id','repo','group_id','repeat_index','primary_panel','code','delivery','end_class','world_actions','API_span_seconds')}|r['usage'] for r in rows])
    csv_save('primary-tasks.csv',task_rows);csv_save('repeat-pairs.csv',repeat_pairs)
    print(json.dumps({'summary':str(OUT/'summary.json'),'primary':{g:{k:v[k] for k in ('code_pass','delivery_pass','mean_total_tokens','ends')} for g,v in groups.items()}},ensure_ascii=False))


if __name__=='__main__':main()
