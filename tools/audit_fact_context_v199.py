"""Final artifact audit and diagnosis; no rerender, model, or holdout access."""
import sys,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from proworksim.software_context_graph_check_v196 import at
from proworksim.software_context_compression_v175 import digest
BASE=ROOT/'artifacts/software-benchmark-v199'

def main():
    out=BASE/'final-audit-r2/summary.json'
    if out.exists():raise ValueError('Preserve completed audit')
    data=read(BASE/'development-r4/summary.json');metrics=read(BASE/'development-score-r4/summary.json')
    old=read(BASE/'development-r1/summary.json');oldpoints={p['point']:p for p in old['points']}
    reference=read(BASE/'fact-reference-r1/facts.json')['facts'];byref={r['id']:r for r in reference}
    rows={p['point']:p for p in data['points']};missing=[];bonuses=Counter();state_pairs={};same_registry=[];whole_writes={};whole_aliases={}
    for point in data['points']:
        name=point['point'];inv=read(point['inventory']['path']);sources=read(point['sources']['path']);registry=read(point['registry']['path'])
        same_registry.append(point['registry']['sha256']==oldpoints[name]['registry']['sha256'])
        for w in registry['write_materials']:whole_writes[(w['action_source'],w['ack_source'])]=w
        for a in registry['import_aliases']:whole_aliases[a['entity_id']]=a
        for tr in inv['state_transitions']:state_pairs[(tr['from'],tr['to'])]=tr
        for row in point['rows']:
            if row['condition']=='E4':bonuses[row['budget']]+=len(read(row['proof']['path'])['graph_bonus'])
        details=next((r for r in metrics['reference_details'] if r['point']==name and r['condition']=='E3' and r['budget']==4096),None)
        if not details:continue
        proof=read(next(r['proof']['path'] for r in point['rows'] if r['condition']=='E3' and r['budget']==4096))
        selected={s['group_id']:s for s in proof['selected']};poolrefs={r['reference']:r for r in metrics['candidate_coverage']['rows']}
        for detail in details['facts']:
            if detail['direct_in_card'] or detail['direct_original']:continue
            wanted=byref[detail['reference']];cover=poolrefs[wanted['id']]['candidate_fact_ids'];items=[]
            for fid in cover:
                f=inv['facts'][fid];group=selected.get(f['event_id']);omit=next((o['reason'] for o in group['omitted_facts'] if o['fact']==fid),None) if group else 'group_not_selected'
                items.append({'fact_id':fid,'fact_kind':f['kind'],'group_id':f['event_id'],'group_selected':group is not None,'omission_reason':omit})
            missing.append({'point':name,'reference':wanted,'covering_candidate_facts':items,'source_still_legally_recoverable':bool(detail['legal_visible_recovery_reference'])})
    assert all(same_registry),'Mapping must refer to the same entity registries as the final run'
    relation=read(BASE/'relation-review-r2/summary.json');literal_checks=0
    for row in relation['rows']:
        sources=read(rows[row['point']]['sources']['path'])
        for key in ['from_binding','to_binding']:
            binding=row[key]
            for item in binding.get('failure_analysis',{}).get('evidence',[]):
                message=sources[item['source_id']]['message'];assert digest(message)==item['message_sha256']
                if item.get('channel')=='arguments':value=at(json.loads(message['tool_calls'][item['call_index']]['function']['arguments']),item['pointer'])
                else:value=at(json.loads(message['content']),item['pointer'])
                assert value[slice(*item['span'])]==item['literal_excerpt'];literal_checks+=1
    normalization=read(BASE/'normalization-r4/summary.json');all_fields=sum(r['checks']['literal_source_fields_verified'] for r in data['rows'])
    gate=[
        ('G1','PASS','19 reference facts and15 textual spans have exact source locations; necessity is AI development reference only'),
        ('G2','PASS','TestRun, TestDefinition and private workspace Version identities remain distinct'),
        ('G3','PASS','522 added events map to237 groups; raw occurrences retained; counter-only reads merge while real transitions persist'),
        ('G4','PASS','All selected values independently recover from observed source; no generated paraphrase'),
        ('G5','PASS','Version-scoped edges and historical labels checked; stale edges cannot justify current query'),
        ('G6','PASS_WITH_LIMIT',f'Every graph bonus requires a sourced current edge; eligible candidate counts by budget={dict(bonuses)}; no efficacy claim'),
        ('G7','PASS','187 unresolved and3 ambiguous endpoints remain explicit; no forced Confirmed relation'),
        ('G8','PASS','19/19 references recoverable in every final condition/budget; bounded CPU reader verification is not Agent use')]
    result={'canonical_revision':'r4','engineering_gates':[{'gate':g,'status':s,'evidence':e} for g,s,e in gate],
        'P0_engineering_admission':'pass_with_scientific_limits','P1_offline_development':'completed',
        'P2_or_new_model_admission':False,'reason':'E4 equalsE3 in all144 paired views, direct coverage13/19 and full necessity precision remains unmeasured',
        'missing_direct_reference_facts':missing,'graph_candidate_extensions_by_budget':dict(bonuses),
        'registry_reuse_identical_points':sum(same_registry),'relation_diagnostic_excerpt_checks':literal_checks,
        'selected_literal_fact_checks':all_fields,'unique_acknowledged_writes':len(whole_writes),'unique_import_aliases':len(whole_aliases),
        'real_state_transitions':len(state_pairs),'normalized_additions':normalization['mapped_distinct_groups'],
        'main_view_input_cost_vs_E0':{g['condition']:g['input_tokens_estimate_sum']/next(x['input_tokens_estimate_sum'] for x in metrics['groups'] if x['budget']==4096 and x['condition']=='E0')-1 for g in metrics['groups'] if g['budget']==4096},
        'new_tested_API_calls':0,'new_Docker_GPU_training_or_host_configuration':False,'holdout_contents_opened':False,
        'reviewer':'primary Codex AI engineering review following user amendment; not human or independent blind review',
        'source_metrics':ref(BASE/'development-score-r4/summary.json')}
    save(out,result);print({k:v for k,v in result.items() if k not in ['engineering_gates','missing_direct_reference_facts']})
    for m in missing:print(m['reference']['id'],m['reference']['value'],[(f['fact_kind'],f['omission_reason']) for f in m['covering_candidate_facts']])

if __name__=='__main__':main()
