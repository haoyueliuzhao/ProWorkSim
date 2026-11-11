"""Frozen offline development, no labels in selection and no tested API."""
from __future__ import annotations
import sys,copy,json,hashlib,time,os,resource
from pathlib import Path
from collections import Counter
from functools import lru_cache
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,frame_for,graph_from_snapshot
from proworksim.software_global_evidence_v198 import project,enrich
from proworksim.software_evidence_entities_v198 import EvidenceEntities
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_graph_check_v196 import recover_field
from proworksim.software_context_compression_v175 import digest

BASE=ROOT/'artifacts/software-benchmark-v198';RUN=ROOT/'runs/software-benchmark-v198'

def check(frame,view,proof,graph,store,count):
    masks={m['index']:m for m in proof['masked']};amount=0
    assert frame.get('tools')==view.get('tools') and len(frame['messages'])==len(view['messages'])
    for i,(a,b) in enumerate(zip(frame['messages'],view['messages'])):
        if i not in masks or a['role'] in {'assistant','system'}:assert a==b
        assert (a.get('role'),a.get('tool_calls'),a.get('tool_call_id'))==(b.get('role'),b.get('tool_calls'),b.get('tool_call_id'))
    ids=[];fields=0
    for item in proof['selected']:
        text=view['messages'][item['anchor']]['content'];amount+=count(text);assert count(text)<=768
        assert json.loads(text.split('\n',1)[1])==item['card']
        assert len(item['card']['facts'])==len(item['selected_fields']);ids.append(item['event_id'])
        for fact,field in zip(item['card']['facts'],item['selected_fields']):
            assert fact['value']==recover_field(field,graph.sources);fields+=1
        if item['card']['version_status']=='current_observed_version':
            assert item['card']['source_version']==graph.nodes[graph.current_version]['attrs']['source_reference']
        for reference in item['card']['originals']:
            e=store.entries[reference];assert [e['slot_id'],e['member_id']]==[graph.episode,graph.member]
            assert hashlib.sha256(e['text'].encode()).hexdigest()==e['text_sha256']
    assert len(ids)==len(set(ids)) and amount==proof['added_tokens_estimate']<=proof['budget']
    assert proof['input_tokens_estimate']<=98304
    assert set(proof['unmet_mandatory'])==set(proof['mandatory'])-set(ids)
    return {'selected_fields_verified':fields,'scope_or_version_errors':0,'duplicate_events':0}

def main():
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]));os.nice(10)
    out=BASE/'development-r1';run=RUN/'development-r1'
    if (out/'summary.json').exists():raise ValueError('Do not overwrite completed result')
    points=read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points']
    metadata={t['instance_id']:{k:t[k] for k in ['repo','base_commit','instance_id']} for t in read(ROOT/'artifacts/software-benchmark-v191/full-task-design-r1/plan.json')['tasks']}
    token=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,tokenizer=load_official_content_counter(token,manifest_sha256=ref(token)['sha256']);count=lru_cache(maxsize=8192)(count)
    counter=OfficialDeepSeekCounter(token,manifest_sha256=ref(token)['sha256'])
    sources=[ROOT/'src/proworksim/software_evidence_entities_v198.py',ROOT/'src/proworksim/software_global_evidence_v198.py',Path(__file__)]
    save(out/'sources.json',{'files':[ref(f) for f in sources],'protocol':ref(BASE/'protocol-r1/plan.json'),'tokenizer':tokenizer,'annotation_labels_loaded':False})
    rows=[];inventories=[];start=time.monotonic();cpu=time.process_time()
    for p in points:
        frame,indices,s,oldpool,cutoff=frame_for(p);g=graph_from_snapshot(s);open_info=enrich(g,frame,indices);m=metadata[p['instance_id']]
        t=time.process_time();entities=EvidenceEntities(g.snapshot(),repo=m['repo'],base_commit=m['base_commit'],issue_id=p['instance_id']);construction=time.process_time()-t
        snapshot=entities.as_json()
        for e in snapshot['edges'].values():
            assert e['source_entity_id'] in snapshot['entities'] and e['target_entity_id'] in snapshot['entities']
            assert all(sid in g.sources and g.sources[sid]['first_seen_step']<=g.step for sid in e['evidence_source_ids'])
            assert e['verification_status']!='Confirmed' or e['relation_type'] not in {'resolves_to','runtime_calls','caused_by'}
        registry_ref=save(run/p['point']/'entity-registry.json.gz',snapshot)
        cache={}
        def measure(value):
            key=digest(value)
            if key not in cache:cache[key]=counter.measure(value)['prompt_tokens']
            return cache[key]
        pool=None
        for budget in [1024,2048,4096]:
            for c in ['G0','G1','G2','G3','G4']:
                store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001');t=time.process_time()
                view,proof,pool=project(frame,c,g,entities,store,count=count,measure=measure,indices=indices,budget=budget)
                elapsed=time.process_time()-t;checks=check(frame,view,proof,g,store,count)
                folder=run/p['point']/f'{c}-{budget}'
                refs={'proof':save(folder/'proof.json.gz',proof),'payload':save(folder/'payload.json.gz',view)}
                rows.append({'point':p['point'],'instance_id':p['instance_id'],'condition':c,'budget':budget,
                    'candidate_pool_sha256':proof['candidate_pool_sha256'],'candidate_count':proof['candidate_count'],
                    'selected':[v['event_id'] for v in proof['selected']],
                    'input_tokens_estimate':proof['input_tokens_estimate'],'added_tokens_estimate':proof['added_tokens_estimate'],
                    'mandatory_count':len(proof['mandatory']),'unmet_mandatory':proof['unmet_mandatory'],
                    'coverage_constraint_satisfied':proof['coverage_constraint_satisfied'],'query_cpu_seconds':elapsed,
                    'checks':checks,**refs})
        current=[r for r in rows if r['point']==p['point']];assert len({r['candidate_pool_sha256'] for r in current})==1
        old_ids={e['event_id'] for e in oldpool};new_ids={e['event_id'] for e in pool}
        assert old_ids<=new_ids
        inventories.append({'point':p['point'],'instance_id':p['instance_id'],'repo':m['repo'],'base_commit':m['base_commit'],
            'old_candidates':len(oldpool),'new_candidates':len(pool),'legacy_event_ids':sorted(old_ids),
            'additional_candidates':[{'event_id':e['event_id'],'kind':e['kind'],'sources':e['sources'],'paths':e['paths'],'fields':e['fields']} for e in pool if e['event_id'] not in old_ids],
            'open_info':open_info,'entity_types':dict(Counter(e['kind'] for e in snapshot['entities'].values())),
            'edge_types':dict(Counter(e['relation_type']+':'+e['verification_status'] for e in snapshot['edges'].values())),
            'complete_files':sum(f['complete'] for f in snapshot['coverage']),'partial_files':sum(not f['complete'] for f in snapshot['coverage']),
            'registry_construction_CPU_seconds':construction,'registry':registry_ref})
        print(p['point'],'old/new',len(oldpool),len(pool),'15 views verified',flush=True)
    save(out/'summary.json',{'version':'v198-global-evidence-development-r1','rows':rows,'inventories':inventories,
        'wall_seconds':time.monotonic()-start,'CPU_seconds':time.process_time()-cpu,'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'new_tested_API_calls':0,'new_API_cost_CNY':0,'labels_seen_by_selector':False,
        'independent_confirmation':False,'actual_task_success_not_measured':True})
    print('complete',len(rows),'views',flush=True)
if __name__=='__main__':main()
