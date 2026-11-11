"""Inspect card duplication and frozen failure cases; no new evaluation calls."""
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
import sqlite3

from proworksim import software_benchmark_scope_v193 as scope
from proworksim.software_context_critical_v191 import PREFIX
from proworksim.storage import json_bytes

ROOT=scope.ROOT
RUN=scope.BATCH_ROOT
OUT=ROOT/'artifacts/software-benchmark-v195/context-report-r1'


def read(path):return json.loads(Path(path).read_bytes())
def ref(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def main():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:]);os.nice(10)
    rows=read(OUT/'episodes.json');cards=read(OUT/'critical-cards.json');index={r['slot_id']:r['slot_index'] for r in rows}
    with sqlite3.connect(scope.LEDGER_FILE.as_uri()+'?mode=ro',uri=True) as db:
        calls=db.execute("SELECT job_id,step FROM requests WHERE job_id LIKE '%M1_5K%' ORDER BY started").fetchall()
    duplicated=[];duplicate_by_slot=defaultdict(Counter);fallbacks=Counter();same_fields=0;extra_token_estimate=0
    for slot,step in calls:
        directory=RUN/'episodes'/str(index[slot])/'controller-output/model-ledger/request-capture-v193'/hashlib.sha256(str(step).encode()).hexdigest()
        projection=read(directory/'projection-evidence.json');treatment=projection.get('observation_history_projection',{}).get('context_treatment',{})
        reports=defaultdict(list)
        for card in treatment.get('critical_cards',[]):
            fields={f['pointer']:f['value'] for f in card['fields']};report=fields.get('/result/report_id')
            if report:reports[(report,fields.get('/result/files_sha256'))].append(card)
        duplicates=[group for group in reports.values() if len(group)>1]
        if duplicates:
            wire=read(directory/'payload.json');details=[]
            for group in duplicates:
                extras=group[1:]
                exact=sum(c['fields']==group[0]['fields'] for c in extras);same_fields+=exact
                extra_token_estimate+=sum(c['tokens_estimate'] for c in extras)
                parsed=[json.loads(wire['messages'][c['index']]['content'][len(PREFIX):]) for c in group]
                details.append({'report_id':next(f['value'] for f in group[0]['fields'] if f['pointer']=='/result/report_id'),
                    'tools':[c['tool'] for c in parsed],'source_references':[c['original']['reference'] for c in parsed],
                    'identical_retained_field_extra_cards':exact,'extra_cards':len(extras)})
            duplicate_by_slot[index[slot]]['requests']+=1
            duplicate_by_slot[index[slot]]['extra_cards']+=sum(d['extra_cards'] for d in details)
            duplicated.append({'slot_index':index[slot],'logical_request_id':step,'payload':ref(directory/'payload.json'),'details':details})
        for f in treatment.get('critical_fallbacks',[]):
            fallbacks['total_candidate_fallback_occurrences']+=1
            fallbacks['individual_card_over_768_local_tokens']+=f.get('tokens',0)>768
    headers=[];rejections=defaultdict(Counter)
    for row in rows:
        for event in read(row['tool_returns']['path']):
            body=event['body'];result=body.get('result',{});result=result if isinstance(result,dict) else {}
            header=result.get('test_evidence')
            if isinstance(header,dict) and header.get('version')=='v193-bounded-public-test-evidence-header-r1':
                size=len(json_bytes(header));assert size<=4096
                headers.append({'slot_index':row['slot_index'],'report_id':result.get('report_id'),'bytes':size})
            if body.get('ok') is False:
                rejections[row['group_id']][str(body.get('error',{}).get('type'))]+=1
    public_issues=[]
    for row in rows:
        if not row['primary_panel']:continue
        for path in sorted((RUN/'episodes'/str(row['slot_index'])/'controller-output/public-test-rpc').glob('test-*/response.json')):
            result=read(path)
            output='\n'.join(str(v.get('output','')) for v in result.get('groups',{}).values() if isinstance(v,dict))
            patterns={
                'recursive_httpbin_fixture':"recursive dependency involving fixture 'httpbin' detected",
                'recursive_httpbin_secure_fixture':"recursive dependency involving fixture 'httpbin_secure' detected",
                'missing_trustme':"No module named 'trustme'",
                'missing_mocker':"fixture 'mocker' not found",
                'isolated_network_unreachable':'Network is unreachable',
            }
            matches=[label for label,pattern in patterns.items() if pattern in output]
            if matches:public_issues.append({'slot_index':row['slot_index'],'instance_id':row['instance_id'],
                'group':row['group_id'],'call':path.parent.name,'observed_categories':matches,
                'counts':result.get('counts'),'passed':result.get('passed'),'response':ref(path)})
    delivery_folder=RUN/'episodes/19322/controller-output'
    boundary=read(delivery_folder/'managed-boundary.json');chain=[]
    for event in boundary['outcomes'][-5:]:
        result=event.get('response',{}).get('result',{})
        chain.append({'status':event.get('status'),'tool':event.get('decision',{}).get('action'),
            'source_reference':result.get('source_reference'),'passed':result.get('passed'),
            'counts':result.get('counts'),'patch_id':result.get('patch_id'),
            'action_performed':event.get('action_performed')})
    result={'version':'v195-critical-mechanism-and-case-audit-r1',
        'card_duplicate_requests':len(duplicated),'extra_same_report_and_code_hash_cards':sum(x['extra_cards'] for v in duplicated for x in v['details']),
        'extra_cards_with_identical_fields':same_fields,'extra_card_content_tokens_local_estimate':extra_token_estimate,
        'duplicates_by_episode':{str(k):dict(v) for k,v in duplicate_by_slot.items()},'duplicates':duplicated,
        'source_rule':ref(ROOT/'src/proworksim/software_context_critical_v191.py'),
        'implementation_cause':'run_tests uses its selector as semantic key; read_test_result falls back to report_id, so the same report can occupy different keys',
        'field_coverage_by_unique_source_card':{category:dict(Counter(p for c in cards if c['category']==category for p in c['field_pointers'])) for category in sorted({c['category'] for c in cards})},
        'unique_source_categories':dict(Counter(c['category'] for c in cards)),
        'fallbacks':dict(fallbacks),'fallback_counts_include_repeated_consideration_of_the_same_source':True,
        'visible_bounded_header_return_count':len(headers),'maximum_header_bytes':max(h['bytes'] for h in headers),
        'headers':headers,'observed_public_execution_issues':public_issues,
        'tool_return_errors_by_type_not_automatically_harness_bugs':{g:dict(v) for g,v in rejections.items()},
        'requests_5414_M1_10_delivery_chain':chain,
        'requests_5414_M1_10_boundary':ref(delivery_folder/'managed-boundary.json'),
        'requests_5414_M1_10_delivery_evidence':ref(delivery_folder/'delivery-evidence.json'),
        'public_fixture_errors_do_not_identify_a_score_counterfactual':True,
        'new_model_calls':0,'new_Docker_objects':0,'original_records_changed':False}
    (OUT/'mechanism-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('card_duplicate_requests','extra_same_report_and_code_hash_cards','extra_cards_with_identical_fields','extra_card_content_tokens_local_estimate','maximum_header_bytes','fallbacks')},ensure_ascii=False))


if __name__=='__main__':main()
