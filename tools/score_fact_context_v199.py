"""Post-freeze scoring: direct facts, bounded legal recovery and no use claim."""
import sys,re,json
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,frame_for
from proworksim.software_context_compression_v175 import digest,is_observation,canonical
from proworksim.software_context_graph_check_v196 import at
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_fact_metrics_v199 import fact_covers
BASE=ROOT/'artifacts/software-benchmark-v199'
REVISION=next((r for r in ['r4','r3','r2'] if '--revision-'+r in sys.argv),'r1')

def main():
    output=BASE/('development-score-'+REVISION)/'summary.json'
    if output.exists():raise ValueError('Preserve first metric result')
    data=read(BASE/('development-'+REVISION)/'summary.json');assert len(data['rows'])==720 and not data['failures']
    points={p['point']:p for p in read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points']}
    references=read(BASE/'fact-reference-r1/facts.json')['facts'];byref=defaultdict(list)
    for r in references:byref[r['point']].append(r)
    rows=[];reference_rows=[];verification=[];dedup=[];pool_reference=[]
    prior=read(ROOT/'artifacts/software-benchmark-v198/development-r1/summary.json');old_inv={i['point']:i for i in prior['inventories']}
    unique_additions={};unique_mapped_groups={};unique_states={};unique_groups={};unique_facts={};unique_entities={};unique_edges={}
    for point in data['points']:
        name=point['point'];p=points[name];inv=read(point['inventory']['path']);sources=read(point['sources']['path']);registry=read(point['registry']['path'])
        unique_entities.update(registry['entities']);unique_edges.update(registry['edges']);unique_groups.update(inv['groups']);unique_facts.update(inv['facts'])
        for g in inv['groups'].values():
            if g['kind']=='state':unique_states[g['id']]=g
        for addition in old_inv[name]['additional_candidates']:
            key=(p['instance_id'],addition['event_id']);gid=inv['aliases'][addition['event_id']]
            if key not in unique_additions:unique_additions[key]={'instance_id':p['instance_id'],'event_id':addition['event_id'],'kind':addition['kind'],'normalized_group':gid,'first_point':name}
            assert unique_additions[key]['normalized_group']==gid,'Historical event changed group identity as later snapshots arrived'
            unique_mapped_groups[gid]=inv['groups'][gid]
        inverse={v:k for k,v in p['event_map'].items()};labels=read(ROOT/'artifacts/software-benchmark-v197/adjudicator-r1'/f'{name}.json')['labels']
        required={inverse[x['event']] for x in labels if x['label']=='essential'}
        required_facts=byref[name];store=None;positions={};originals={};refmap={};recovery_checks={};candidate={}
        if required_facts:
            frame,indices,_,_,_=frame_for(p);positions=dict(zip(indices,range(len(indices))));originals=dict(zip(indices,frame['messages']))
            store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001')
            for index,message in originals.items():
                if is_observation(message):refmap[digest(message)]=store.put(message,index)
            for required_fact in required_facts:
                sid=required_fact['source_id'];source=sources[sid];body=json.loads(source['message']['content']);value=at(body,required_fact['pointer'])
                if required_fact['span']:value=value[slice(*required_fact['span'])]
                assert value==required_fact['value'] and source['message_sha256']==required_fact['message_sha256']
                candidate[required_fact['id']]=[fid for fid,f in inv['facts'].items() if fact_covers(f,required_fact)]
                pool_reference.append({'reference':required_fact['id'],'point':name,'candidate_fact_ids':candidate[required_fact['id']],
                    'candidate_fact_found':bool(candidate[required_fact['id']]),'textual_span':required_fact['span'] is not None})
                reference=refmap.get(required_fact['message_sha256'])
                if reference and reference not in recovery_checks:
                    pages=[];start=0;responses=[]
                    while True:
                        response=store.read({'reference':reference,'start':start,'characters':8192},point_id=p['point_id'],slot_id=p['slot_id'],member_id='member_001')
                        pages.append(response['text']);responses.append({'start':start,'characters':len(response['text']),'response_sha256':digest(response)})
                        if response['next_start'] is None:break
                        start=response['next_start']
                    text=''.join(pages);assert text==source['message']['content'];recovery_checks[reference]=json.loads(text)
                    verification.append({'point':name,'reference':reference,'source_id':sid,'bounded_CPU_reader_calls':len(pages),
                        'recovered_characters':len(text),'pages':responses,'agent_issued':False,'new_world_read':False})
        for row in point['rows']:
            proof=read(row['proof']['path']);view=read(row['payload']['path']);selected_facts={f['fact_id'] for s in proof['selected'] for f in s['selected_facts']}
            available_refs=set(re.findall(r'ctx:[0-9a-f]{24}',canonical(view)))
            direct=[];recoverable=[];readable=[];statuses=[]
            for wanted in required_facts:
                selected=sorted(set(candidate[wanted['id']])&selected_facts);index=wanted['message_index'];source=sources[wanted['source_id']]
                original_direct=index in positions and originals[index]==source['message'] and view['messages'][positions[index]]==source['message']
                is_direct=bool(selected) or original_direct;reference=refmap.get(wanted['message_sha256']);legal=reference in available_refs and reference in recovery_checks
                if legal:
                    value=at(recovery_checks[reference],wanted['pointer'])
                    if wanted['span']:value=value[slice(*wanted['span'])]
                    assert value==wanted['value']
                    readable.append(wanted['id'])
                if is_direct:direct.append(wanted['id'])
                if legal or original_direct:recoverable.append(wanted['id'])
                statuses.append({'reference':wanted['id'],'direct_in_card':bool(selected),'direct_original':original_direct,
                    'selected_covering_facts':selected,'legal_visible_recovery_reference':reference if legal else None,
                    'recoverable_or_original_direct':legal or original_direct,'agent_read':False,'actual_use':None})
            new={**row,'necessary_events_selected':len(required&set(row['selected_original_events'])),'necessary_events_denominator':len(required),
                'direct_facts':direct,'recoverable_facts':recoverable,'legally_readable_facts':readable,'reference_facts':len(required_facts),
                'all_reference_facts_direct':bool(required_facts) and len(direct)==len(required_facts)}
            rows.append(new)
            if required_facts:reference_rows.append({'point':name,'condition':row['condition'],'budget':row['budget'],'facts':statuses})
    groups=[]
    for budget in [1024,2048,4096]:
        for c in ['E0','E1','E2','E3','E4']:
            rs=[r for r in rows if r['condition']==c and r['budget']==budget]
            groups.append({'condition':c,'budget':budget,'points':len(rs),'tasks':len({r['instance_id'] for r in rs}),
                'reference_events_selected':sum(r['necessary_events_selected'] for r in rs),'reference_events_denominator':8,
                'direct_facts':sum(len(r['direct_facts']) for r in rs),'reference_facts_denominator':19,
                'all_fact_points':sum(r['all_reference_facts_direct'] for r in rs),'reference_points':8,
                'recoverable_facts':sum(len(r['recoverable_facts']) for r in rs),'legally_readable_facts':sum(len(r['legally_readable_facts']) for r in rs),
                'input_tokens_estimate_sum':sum(r['input_tokens_estimate'] for r in rs),'added_tokens_estimate_sum':sum(r['added_tokens_estimate'] for r in rs),
                'cards':sum(len(r['selected_groups']) for r in rs),'selected_facts':sum(r['selected_facts'] for r in rs),
                'unmet_protection_points':sum(bool(r['unmet_mandatory']) for r in rs),'unmet_protection_groups':sum(len(r['unmet_mandatory']) for r in rs),
                'query_CPU_seconds':sum(r['query_CPU_seconds'] for r in rs),'actual_Agent_reads':0,'actual_fact_use':None})
    changes={}
    for budget in [1024,2048,4096]:
        a={r['point']:r for r in rows if r['condition']=='E3' and r['budget']==budget};b={r['point']:r for r in rows if r['condition']=='E4' and r['budget']==budget}
        changes[budget]={'input_payload_changes':sum(a[p]['payload']['sha256']!=b[p]['payload']['sha256'] for p in a),
            'group_set_changes':sum(set(a[p]['selected_groups'])!=set(b[p]['selected_groups']) for p in a),
            'direct_reference_fact_changes':sum(a[p]['direct_facts']!=b[p]['direct_facts'] for p in a)}
    normalization={'prior_distinct_additions':len(unique_additions),'mapped_distinct_groups':len(unique_mapped_groups),
        'prior_addition_types':dict(Counter(e['kind'] for e in unique_additions.values())),
        'normalized_addition_types':dict(Counter(e['kind'] for e in unique_mapped_groups.values())),
        'records':list(unique_additions.values()),'state_epochs_across_all_old_sources':len(unique_states),
        'all_event_groups':len(unique_groups),'unique_fact_ids':len(unique_facts),
        'raw_presentation_costs_not_deduplicated':True,'identical_timestamp_budget_fields_excluded_from_state_projection':True,
        'observed_history_entries_is_occurrence_metadata':REVISION in {'r3','r4'}}
    save(BASE/('normalization-'+REVISION)/'summary.json',normalization)
    candidate_summary={'fact_found':sum(x['candidate_fact_found'] for x in pool_reference),'fact_denominator':len(pool_reference),
        'span_found':sum(x['candidate_fact_found'] and x['textual_span'] for x in pool_reference),'span_denominator':sum(x['textual_span'] for x in pool_reference),'rows':pool_reference}
    result={'groups':groups,'rows':rows,'reference_details':reference_rows,'candidate_coverage':candidate_summary,'E3_E4_changes':changes,
        'reader_verification':verification,'CPU_verification_reader_calls':sum(x['bounded_CPU_reader_calls'] for x in verification),
        'entity_types_unique':dict(Counter(e['kind'] for e in unique_entities.values())),
        'edge_types_unique':dict(Counter(e['relation_type']+':'+e['verification_status'] for e in unique_edges.values())),
        'reference_warning':'19 source-checked facts chosen before views from8 known development events; not independent necessity gold',
        'fact_precision_not_estimated_without_all_fact_labels':True,'literal_source_fidelity_is_not_necessity_precision':True,
        'token_cost':'local official tokenizer estimate of hypothetical input, not actual provider usage or complete rollout cost',
        'actual_agent_read_calls':0,'actual_fact_use_measured':False,'new_API_calls':0}
    save(output,result)
    for g in groups:
        if g['budget']==4096:print(g)
    print('candidate', {k:v for k,v in candidate_summary.items() if k!='rows'});print('changes',changes)
    print('normalization',{k:v for k,v in normalization.items() if k!='records'})
if __name__=='__main__':main()
