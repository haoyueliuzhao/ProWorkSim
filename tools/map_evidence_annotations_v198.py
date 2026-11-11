"""Resolve annotation endpoints against source-bound identities, or abstain."""
from __future__ import annotations
import sys,re,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref
from proworksim.software_context_compression_v175 import digest
from proworksim.software_context_graph_v196 import obj

BASE=ROOT/'artifacts/software-benchmark-v198'

def resolve(text,relation,source_indices,registry,old_graph):
    entities=registry['entities'];sources=[s for s in old_graph['sources'].values() if s['message_index'] in source_indices]
    source_ids={s['id'] for s in sources};references=[]
    for s in sources:
        b=obj(s['message'].get('content'));r=b.get('result',{});r=r if isinstance(r,dict) else {}
        v=r.get('source_reference') or b.get('observation',{}).get('workspace_reference')
        if v and v not in references:references.append(v)
    explicit_versions=set(re.findall(r'(?<![\w])v\d+\b',text));paths=list(dict.fromkeys(re.findall(r'(?:/testbed/)?([\w./-]+\.py)',text)))
    def allowed(e):
        identity=e['identity'];v=identity.get('revision',{}).get('workspace_reference') or e['attrs'].get('source_reference')
        if v and explicit_versions and v.get('version_id') not in explicit_versions:return False
        if v and references and v not in references:return False
        return True
    matches=[];basis=None
    if paths:
        for path in paths:
            suffix=text.split(path,1)[1].lstrip(': .');qual=re.match(r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*',suffix)
            q=qual.group() if qual else None
            exact=[e for e in entities.values() if e['identity'].get('path')==path and allowed(e)]
            if q:
                matches += [e['id'] for e in exact if e['kind']=='Symbol' and e['identity'].get('qualified_name')==q]
                basis='exact_qualified_name_in_complete_visible_definition'
            else:
                matches += [e['id'] for e in exact if e['kind']=='File'];basis='explicit_path_and_source_revision'
    elif explicit_versions and re.fullmatch(r'\s*v\d+\s*',text):
        matches=[e['id'] for e in entities.values() if e['kind']=='Version' and allowed(e) and e['identity']['revision']['workspace_reference']['version_id'] in explicit_versions]
        basis='exact_version_in_cited_sources'
    elif relation in {'version','test'} and re.search(r'(?i)(report|run\b|result|selected.*test|public.*test|测试.*结果|报告|执行)',text):
        matches=[e['id'] for e in entities.values() if e['kind']=='TestRun' and set(e['attrs'].get('source_ids',[]))&source_ids and allowed(e)]
        basis='single_actual_report_in_cited_sources'
    if not matches:
        # A symbol spelling alone is accepted only with one complete definition
        # in the cited source, never from a repository-wide fuzzy search.
        stripped=re.sub(r'^v\d+:','',text)
        if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',stripped):
            matches=[e['id'] for e in entities.values() if e['kind']=='Symbol' and e['identity'].get('qualified_name')==stripped and set(e['attrs'].get('source_ids',[]))&source_ids and allowed(e)]
            basis='unique_exact_symbol_in_complete_cited_source'
    matches=sorted(set(matches))
    if len(matches)==1:return {'status':'bound','entity_id':matches[0],'entity_kind':entities[matches[0]]['kind'],'basis':basis,'source_ids':sorted(source_ids)}
    return {'status':'ambiguous' if matches else 'unresolved','reference_id':'annotation-ref:'+digest([registry['scope'],text,sorted(source_ids)])[:32],
        'text':text,'candidates':matches,'reason':'multiple compatible source identities' if matches else 'no unique complete definition/execution/version binding in visible evidence',
        'source_ids':sorted(source_ids),'not_counted_as_resolved_entity':True}

def main():
    if (BASE/'annotation-binding-r1/summary.json').exists():raise ValueError('Preserve completed mapping')
    points=read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points'];rows=[]
    for p in points:
        registry=read(ROOT/'runs/software-benchmark-v198/development-r1'/p['point']/'entity-registry.json.gz')
        graph=read(ROOT/'runs/software-benchmark-v196/offline-graph-r4'/p['point_id']/'graph.json.gz')
        source_file=ROOT/'artifacts/software-benchmark-v197/adjudicator-r1'/f'{p["point"]}.json'
        original=read(source_file)
        for i,d in enumerate(original['dependencies']):
            if not d.get('necessary'):continue
            assert d['source_messages'] # The one issue-only empty reference is nonnecessary.
            left=resolve(d['from'],d['relation'],d['source_messages'],registry,graph)
            right=resolve(d['to'],d['relation'],d['source_messages'],registry,graph)
            direct=[]
            if left['status']==right['status']=='bound':
                compatible={'version':{'validates','derived_from'},'test':{'reports_test','validates'},'call':{'runtime_calls'},'import':{'resolves_to'},'other':set()}.get(d['relation'],set())
                direct=[e['edge_id'] for e in registry['edges'].values() if e['source_entity_id']==left['entity_id'] and e['target_entity_id']==right['entity_id'] and e['relation_type'] in compatible]
            rows.append({'point':p['point'],'instance_id':p['instance_id'],'annotation_index':i,'original_annotation':d,
                'source_annotation':ref(source_file),'from_binding':left,'to_binding':right,
                'relation_proofs':direct,'proof_statuses':[registry['edges'][eid]['verification_status'] for eid in direct],
                'relation_status':'sourced_direct_relation' if direct else 'endpoints_only_not_relation_proof' if left['status']==right['status']=='bound' else 'unmapped_relation',
                'AI_annotation_not_promoted_to_Confirmed':True})
    assert len(rows)==123
    statuses=Counter(b['status'] for r in rows for b in [r['from_binding'],r['to_binding']]);relations=Counter(r['relation_status'] for r in rows)
    save(BASE/'annotation-binding-r1/summary.json',{'version':'v198-explicit-source-entity-mapping-r1','rows':rows,'relation_count':len(rows),
        'endpoint_statuses':dict(statuses),'relation_statuses':dict(relations),'all_records_mapped_or_explicitly_unresolved':True,
        'unresolved_reference_id_is_not_a_resolved_code_entity':True,'new_model_calls':0})
    print(dict(statuses),dict(relations))
if __name__=='__main__':main()
