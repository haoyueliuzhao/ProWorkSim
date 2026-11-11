"""Source-limited endpoint resolution and explicit failure causes for all123.

This consumes old AI annotations for evaluation only, never for view selection.
"""
import sys,re
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from map_evidence_annotations_v198 import resolve
from proworksim.software_context_graph_v196 import obj
BASE=ROOT/'artifacts/software-benchmark-v199'
REVISION='r2' if '--revision-r2' in sys.argv else 'r1'

def enhanced(text,relation,indices,registry,sources):
    result=resolve(text,relation,indices,registry,{'sources':sources})
    if result['status']=='bound':return result
    selected={s['id'] for s in sources.values() if s['message_index'] in indices};entities=registry['entities']
    versions=set(re.findall(r'(?<![\w])v\d+\b',text))
    references=[]
    for sid in selected:
        b=obj(sources[sid]['message'].get('content'));r=b.get('result',{});r=r if isinstance(r,dict) else {}
        v=r.get('source_reference') or b.get('observation',{}).get('workspace_reference')
        if v:references.append(v)
    def allowed(e):
        v=e['identity'].get('revision',{}).get('workspace_reference') or e['attrs'].get('source_reference')
        return (not versions or not v or v['version_id'] in versions) and (not references or not v or v in references)
    matches=[];basis=None;stripped=re.sub(r'^v\d+:','',text).strip()
    # Only a complete endpoint spelling; descriptive/composite labels stay open.
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',stripped):
        matches=[e['id'] for e in entities.values() if e['kind']=='Symbol' and allowed(e) and set(e['attrs'].get('source_ids',[]))&selected and e['identity'].get('qualified_name','').split('.')[-1]==stripped]
        basis='unique_complete_definition_leaf_in_cited_sources'
    if not matches and re.fullmatch(r'(patch|delivery)-[\w-]+',stripped):
        matches=[e['id'] for e in entities.values() if e['kind']=='Artifact' and allowed(e) and set(e['attrs'].get('source_ids',[]))&selected and stripped in e['attrs'].get('observed_aliases',{}).values()]
        basis='exact_artifact_receipt_alias'
    if not matches and '::' in stripped and ' ' not in stripped:
        matches=[e['id'] for e in entities.values() if e['kind']=='TestDefinition' and allowed(e) and set(e['attrs'].get('source_ids',[]))&selected and e['identity'].get('node_id')==stripped]
        basis='exact_visible_test_identity_not_test_execution'
    matches=sorted(set(matches))
    if len(matches)==1:return {'status':'bound','entity_id':matches[0],'entity_kind':entities[matches[0]]['kind'],'basis':basis,'source_ids':sorted(selected)}
    if matches:result.update(status='ambiguous',candidates=matches)
    return result

def explain(binding,text,registry,sources):
    selected={sid:sources[sid] for sid in binding['source_ids']};reasons=[];evidence=[]
    if binding['status']=='ambiguous':reasons.append('ambiguous_symbols_or_versions')
    if binding['status']=='bound':return []
    paths=set(re.findall(r'(?:/testbed/)?([\w./-]+\.py)',text))
    relevant=[]
    for entry in registry['coverage']:
        if paths and entry['path'] in paths:relevant.append(entry)
    for e in registry['entities'].values():
        if e['kind']=='Reference' and set(e['attrs'].get('source_ids',[]))&set(selected):
            reason=e['attrs'].get('reason','')
            if reason in {'partial_file_not_qualified_definition','missing_exact_file_coverage'}:reasons.append('partial_source_without_complete_qualified_definition')
            if 'alias' in reason:
                aliases=[e['identity'].get('import_alias'),e['identity'].get('imported_name')]
                if any(a and re.search(r'(?<!\w)'+re.escape(a)+r'(?!\w)',text) for a in aliases):reasons.append('import_alias_runtime_target_unresolved')
    for sid,s in selected.items():
        b=obj(s['message'].get('content'));r=b.get('result',{});r=r if isinstance(r,dict) else {}
        chunks=[]
        if isinstance(r.get('text'),str):chunks.append(('/result/text',r['text']))
        if isinstance(r.get('page',{}).get('text'),str):chunks.append(('/result/page/text',r['page']['text']))
        for pointer,raw in chunks:
            terms=re.findall(r'[A-Za-z_]\w{3,}',text)
            hits=[raw.find(t) for t in terms if t in raw];a=max(0,min(hits)-80) if hits else 0;z=min(len(raw),a+400)
            evidence.append({'source_id':sid,'message_index':s['message_index'],'message_sha256':s['message_sha256'],
                'pointer':pointer,'span':[a,z],'literal_excerpt':raw[a:z],'scope':'diagnostic_pointer_not_relation_proof'})
        if s['message'].get('role')=='assistant' and not r:
            for call_index,call in enumerate(s['message'].get('tool_calls',[])):
                if call['function']['name'] in {'replace_file','integrate_patch'}:reasons.append('delta_edit_not_complete_definition_source')
                args=obj(call['function'].get('arguments'))
                for key in ['text','old','new','old_text','new_text','path']:
                    raw=args.get(key)
                    if not isinstance(raw,str):continue
                    terms=re.findall(r'[A-Za-z_]\w{3,}',text);hits=[raw.find(t) for t in terms if t in raw]
                    a=max(0,min(hits)-80) if hits else 0;z=min(len(raw),a+400)
                    evidence.append({'source_id':sid,'message_index':s['message_index'],'message_sha256':s['message_sha256'],
                        'channel':'arguments','call_index':call_index,'pointer':'/'+key,'span':[a,z],'literal_excerpt':raw[a:z],
                        'scope':'observed_argument_diagnostic_pointer_not_relation_proof'})
    if relevant and any(not e['complete'] for e in relevant):reasons.append('partial_source_without_complete_qualified_definition')
    if re.search(r'\s/\s|→|->|\(not |not current',text):reasons.append('composite_or_negative_version_annotation')
    if re.search(r'\s',text) and not re.fullmatch(r'\s*v\d+\s*',text):reasons.append('descriptive_endpoint_without_single_identity')
    if re.search(r'\b(?:numpy|pandas|collections|urllib3|os)\.',text):reasons.append('external_definition_or_dynamic_target_unobserved')
    if re.search(r'\(|\[',text) and not '::' in text:reasons.append('expression_or_dispatch_not_entity_identity')
    exact=re.sub(r'^v\d+:','',text).strip()
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',exact):
        outside=[e for e in registry['entities'].values() if e['kind']=='Symbol' and e['identity'].get('qualified_name')==exact and not set(e['attrs'].get('source_ids',[]))&set(selected)]
        reasons.append('definition_exists_outside_cited_source_or_version' if outside else 'no_complete_qualified_definition_in_cited_sources')
    if not reasons:reasons.append('unsupported_endpoint_form_or_missing_identity_evidence')
    return {'categories':sorted(set(reasons)),'evidence':evidence,'file_coverage':relevant,
        'diagnosis_scope':'nonexclusive parser/source-context categories; not proof of endpoint-specific causality or source information absence'}

def main():
    path=BASE/('relation-review-'+REVISION)/'summary.json'
    if path.exists():raise ValueError('Preserve completed relation audit')
    data=read(BASE/'development-r1/summary.json');lookup={p['point']:p for p in data['points']}
    prior=read(ROOT/'artifacts/software-benchmark-v198/annotation-binding-r1/summary.json');rows=[]
    registries={};source_sets={}
    for previous in prior['rows']:
        point=previous['point'];d=previous['original_annotation'];p=lookup[point]
        if point not in registries:registries[point]=read(p['registry']['path']);source_sets[point]=read(p['sources']['path'])
        registry,sources=registries[point],source_sets[point]
        left=enhanced(d['from'],d['relation'],d['source_messages'],registry,sources);right=enhanced(d['to'],d['relation'],d['source_messages'],registry,sources)
        for binding,text in [(left,d['from']),(right,d['to'])]:
            if binding['status']!='bound':binding['failure_analysis']=explain(binding,text,registry,sources)
        edges=[]
        if left['status']==right['status']=='bound':
            compatible={'version':{'validates','derived_from'},'test':{'reports_test','validates'},'call':{'runtime_calls'},'import':{'resolves_to'},'other':set()}.get(d['relation'],set())
            edges=[e for e in registry['edges'].values() if e['source_entity_id']==left['entity_id'] and e['target_entity_id']==right['entity_id'] and e['relation_type'] in compatible]
        status='sourced_direct_relation' if edges else 'endpoints_only_not_relation_proof' if left['status']==right['status']=='bound' else 'unmapped_relation'
        rows.append({'point':point,'instance_id':previous['instance_id'],'annotation_index':previous['annotation_index'],
            'original_annotation':d,'from_binding':left,'to_binding':right,'relation_status':status,'relation_proofs':edges,
            'old_relation_status':previous['relation_status'],'old_endpoint_statuses':[previous['from_binding']['status'],previous['to_binding']['status']],
            'remaining_relation_reason':None if edges else 'no_sourced_edge_for_requested_semantics' if status=='endpoints_only_not_relation_proof' else 'one_or_both_endpoints_not_uniquely_bound',
            'AI_annotation_not_promoted_to_Confirmed':True,'source_annotation':previous['source_annotation']})
    assert len(rows)==123 and sum(r['old_relation_status']=='unmapped_relation' for r in rows)==114
    counts=Counter(b['status'] for r in rows for b in [r['from_binding'],r['to_binding']]);causes=Counter(c for r in rows for b in [r['from_binding'],r['to_binding']] if b['status']!='bound' for c in b['failure_analysis']['categories'])
    result={'version':'v199-source-bound-relation-failure-review-r1','rows':rows,'relation_count':123,'prior_unmapped_each_reviewed':114,
        'endpoint_statuses':dict(counts),'relation_statuses':dict(Counter(r['relation_status'] for r in rows)),
        'nonexclusive_endpoint_failure_categories':dict(causes),'source_kind':'old AI development annotations, not independent gold',
        'relation_proof_requires_more_than_both_endpoints':True,'runtime_causality_not_inferred_from_AST':True}
    save(path,result);print({k:v for k,v in result.items() if k!='rows'})
if __name__=='__main__':main()
