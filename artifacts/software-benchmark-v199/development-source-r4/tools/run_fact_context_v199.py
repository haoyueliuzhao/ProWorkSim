"""Frozen, source-checked E0-E4 development views. No labels or API calls."""
from __future__ import annotations
import sys,os,time,resource,json,hashlib,traceback
from pathlib import Path
from functools import lru_cache
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,frame_for,graph_from_snapshot
from proworksim.software_fact_context_v199 import FactInventory,project,CONDITIONS
from proworksim.software_evidence_bindings_v199 import EvidenceBindings
from proworksim.software_global_evidence_v198 import enrich
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_graph_check_v196 import recover_field
from proworksim.software_context_compression_v175 import digest
REVISION=next((r for r in ['r4','r3','r2'] if '--revision-'+r in sys.argv),'r1')
BASE=ROOT/'artifacts/software-benchmark-v199';RUN=ROOT/('runs/software-benchmark-v199/development-'+REVISION)

def initialize():
    global count,counter,metadata
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    token=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,_=load_official_content_counter(token,manifest_sha256=ref(token)['sha256']);count=lru_cache(maxsize=8192)(count)
    counter=OfficialDeepSeekCounter(token,manifest_sha256=ref(token)['sha256'])
    metadata={t['instance_id']:{k:t[k] for k in ['repo','base_commit','instance_id']} for t in read(ROOT/'artifacts/software-benchmark-v191/full-task-design-r1/plan.json')['tasks']}

def check(frame,view,proof,graph,store):
    masks={m['index'] for m in proof['masked']};fields=0;amount=0
    assert frame.get('tools')==view.get('tools') and len(frame['messages'])==len(view['messages'])
    for i,(a,b) in enumerate(zip(frame['messages'],view['messages'])):
        if i not in masks or a['role'] in {'assistant','system'}:assert a==b
        assert (a.get('role'),a.get('tool_calls'),a.get('tool_call_id'))==(b.get('role'),b.get('tool_calls'),b.get('tool_call_id'))
    for item in proof['selected']:
        text=view['messages'][item['anchor']]['content'];assert count(text)<=768;amount+=count(text)
        assert json.loads(text.split('\n',1)[1])==item['card']
        assert len(item['card']['facts'])==len(item['selected_facts'])
        for fact,field in zip(item['card']['facts'],item['selected_facts']):
            assert fact['value']==recover_field(field,graph.sources);fields+=1
            o=field['origin'];assert o['message_sha256']==digest(graph.sources[o['source_id']]['message'])
        if item['card']['version_status']=='current_observed_version':
            assert item['card']['source_version']==graph.nodes[graph.current_version]['attrs']['source_reference']
        for reference in item['card']['originals']:
            entry=store.entries[reference];assert [entry['slot_id'],entry['member_id']]==[graph.episode,graph.member]
            assert hashlib.sha256(entry['text'].encode()).hexdigest()==entry['text_sha256']
    ids={s['group_id'] for s in proof['selected']};assert len(ids)==len(proof['selected'])
    assert amount==proof['added_tokens_estimate']<=proof['budget']
    assert proof['input_tokens_estimate']<=98304
    assert set(proof['unmet_mandatory'])==set(proof['mandatory_groups'])-ids
    assert all(b['edge_ids'] for b in proof['graph_bonus'].values()), 'Graph bonus without a relation proof'
    visible=json.dumps(view,ensure_ascii=False)
    assert all(m['reference'] in visible for m in proof['masked']), 'Replacing a card lost its original recovery reference'
    return {'literal_source_fields_verified':fields,'scope_version_or_source_errors':0,'budget_violations':0}

def one(p):
    start=time.monotonic();cpu=time.process_time();frame,indices,s,oldpool,cutoff=frame_for(p)
    g=graph_from_snapshot(s);open_info=enrich(g,frame,indices);m=metadata[p['instance_id']]
    construction=time.process_time()
    entities=EvidenceBindings(g.snapshot(),repo=m['repo'],base_commit=m['base_commit'],issue_id=p['instance_id'])
    store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001')
    _,masked,cutoff=baseline(frame,store,count,indices);inventory=FactInventory(g,frame,indices,masked,cutoff)
    construction=time.process_time()-construction;registry=entities.as_json();snap=inventory.snapshot()
    for f in snap['facts'].values():
        for origin in f['origins']:recover_field({'value':f['value'],'origin':origin},g.sources)
    for e in registry['edges'].values():
        assert e['source_entity_id'] in registry['entities'] and e['target_entity_id'] in registry['entities']
        assert e['evidence_source_ids'] and all(sid in g.sources and g.sources[sid]['first_seen_step']<=g.step for sid in e['evidence_source_ids'])
        assert e['verification_status']!='Confirmed' or e['relation_type'] not in {'resolves_to','runtime_calls','caused_by'}
    folder=RUN/p['point'];registry_ref=save(folder/'entity-registry.json.gz',registry);inventory_ref=save(folder/'fact-inventory.json.gz',snap)
    # Preserve actual already-seen source material once, never a synthesized observation.
    source_ref=save(folder/'sources.json.gz',g.sources)
    cache={}
    def measure(v):
        key=digest(v)
        if key not in cache:cache[key]=counter.measure(v)['prompt_tokens']
        return cache[key]
    rows=[]
    for budget in [1024,2048,4096]:
        for c in CONDITIONS:
            store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001');t=time.process_time()
            view,proof=project(frame,c,g,entities,inventory,store,count=count,measure=measure,indices=indices,budget=budget)
            elapsed=time.process_time()-t;checks=check(frame,view,proof,g,store)
            target=folder/f'{c}-{budget}'
            rows.append({'point':p['point'],'instance_id':p['instance_id'],'condition':c,'budget':budget,
                'pool_sha256':proof['pool_sha256'],'fact_pool_sha256':proof['fact_pool_sha256'],
                'selected_groups':[x['group_id'] for x in proof['selected']],
                'selected_original_events':sorted({e for x in proof['selected'] for e in x['members']}),
                'selected_facts':len([f for x in proof['selected'] for f in x['selected_facts']]),
                'input_tokens_estimate':proof['input_tokens_estimate'],'added_tokens_estimate':proof['added_tokens_estimate'],
                'unmet_mandatory':proof['unmet_mandatory'],'query_CPU_seconds':elapsed,'checks':checks,
                'proof':save(target/'proof.json.gz',proof),'payload':save(target/'payload.json.gz',view)})
    assert len({r['pool_sha256'] for r in rows})==len({r['fact_pool_sha256'] for r in rows})==1
    result={'point':p['point'],'instance_id':p['instance_id'],'rows':rows,'inventory':inventory_ref,'registry':registry_ref,'sources':source_ref,
        'normalization':{'events_before':len(g.events),'groups_after':len(inventory.groups),'state_epochs':sum(x['kind']=='state' for x in inventory.groups.values()),
            'state_transitions':len(inventory.state_transitions),'raw_event_memberships':sum(len(x['members']) for x in inventory.groups.values()),
            'candidate_groups':len(inventory.pool),'facts':len(inventory.facts)},
        'entity_types':dict(Counter(e['kind'] for e in registry['entities'].values())),
        'edge_types':dict(Counter(e['relation_type']+':'+e['verification_status'] for e in registry['edges'].values())),
        'acknowledged_writes':len(registry['write_materials']),'parsed_acknowledged_writes':sum(w['parsed'] for w in registry['write_materials']),
        'import_aliases':len(registry['import_aliases']),'construction_CPU_seconds':construction,
        'total_CPU_seconds':time.process_time()-cpu,'wall_seconds':time.monotonic()-start,
        'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    save(folder/'completed.json',result);return result

def main():
    out=BASE/('development-'+REVISION)
    if (out/'sources.json').exists():raise ValueError('Frozen first-run namespace already exists; preserve it')
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-4:]));os.nice(10)
    points=read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points']
    files=[ROOT/'src/proworksim'/name for name in ['software_fact_context_v199.py','software_evidence_bindings_v199.py','software_global_evidence_v198.py','software_evidence_entities_v198.py','software_context_selection_v196.py','software_context_graph_v196.py','software_context_reader_v179.py','software_context_graph_check_v196.py']]+[Path(__file__)]
    frozen=[]
    for f in files:
        target=BASE/('development-source-'+REVISION)/f.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes());frozen.append(ref(target))
    save(out/'sources.json',{'files':frozen,'protocol':ref(BASE/'protocol-r1/plan.json'),'labels_or_reference_facts_loaded_by_selector':False,
        'amendment':ref(BASE/('protocol-amendment-'+REVISION)/'record.json') if REVISION!='r1' else None,
        'tokenizer':ref(ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'),'workers':4})
    start=time.monotonic();results=[];failures=[]
    with ProcessPoolExecutor(max_workers=4,initializer=initialize) as pool:
        futures={pool.submit(one,p):p for p in points}
        for future in as_completed(futures):
            p=futures[future]
            try:results.append(future.result());print(p['point'],'15 views checked',flush=True)
            except Exception as e:
                row={'point':p['point'],'error':repr(e),'traceback':traceback.format_exc()};failures.append(row);save(RUN/p['point']/'failure.json',row);print(p['point'],'isolated error',repr(e),flush=True)
            save(out/'progress.json',{'completed_points':len(results),'failed_points':failures,'planned_points':48})
    results.sort(key=lambda x:x['point']);rows=[r for x in results for r in x['rows']]
    save(out/'summary.json',{'version':'v199-fact-context-development-'+REVISION,'points':results,'rows':rows,'failures':failures,
        'planned_points':48,'planned_views':720,'wall_seconds':time.monotonic()-start,'worker_CPU_seconds':sum(r['total_CPU_seconds'] for r in results),
        'max_worker_RSS_KiB':max((r['peak_RSS_KiB'] for r in results),default=0),'new_tested_API_calls':0,'new_API_cost_CNY':0,
        'agent_issued_recovery_reads':0,'actual_fact_use_measured':False,'holdout_opened':False,'development_not_independent_confirmation':True})
    print('complete',len(rows),'views;',len(failures),'failed points',flush=True)

if __name__=='__main__':main()
