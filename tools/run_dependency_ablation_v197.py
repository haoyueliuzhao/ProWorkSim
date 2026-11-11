"""Run frozen G0-G4 offline, without opening reviewer annotations."""
from __future__ import annotations
import copy,gzip,hashlib,json,os,time,resource,sys
from pathlib import Path
from collections import Counter,defaultdict
from functools import lru_cache
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,OUT,RUN,read,save,ref,frame_for,graph_from_snapshot
from proworksim.software_dependency_query_v197 import project,POLICY,PATHS
from proworksim.software_context_graph_check_v196 import recover_field
from proworksim.software_context_compression_v175 import digest,canonical
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_graph_v196 import ObservedWorkGraph


def verify(raw,view,proof,s,store,count,indices):
    assert raw.get('tools')==view.get('tools') and len(raw['messages'])==len(view['messages'])
    masked={m['index']:m for m in proof['masked']};selected=proof['selected'];ids=[e['event_id'] for e in selected]
    assert len(ids)==len(set(ids)) and len(ids)<=8
    for i,(a,b) in enumerate(zip(raw['messages'],view['messages'])):
        if i not in masked or a['role'] in {'assistant','system'}:assert a==b
        assert (a.get('role'),a.get('tool_call_id'),a.get('tool_calls'))==(b.get('role'),b.get('tool_call_id'),b.get('tool_calls'))
    cost=0;field_count=0;inferred=0;routes=0
    for x in selected:
        content=view['messages'][x['anchor']]['content'];assert json.loads(content.split('\n',1)[1])==x['card']
        cost+=count(content);assert count(content)<=768
        assert len(x['card']['facts'])==len(x['selected_fields'])
        for f,field in zip(x['card']['facts'],x['selected_fields']):assert f['value']==recover_field(field,s['sources']);field_count+=1
        if x['card']['version_status']=='current_observed_version':
            assert x['card']['source_version']==s['nodes'][s['current_version']]['attrs']['source_reference']
        for reference in x['card']['originals']:
            entry=store.entries[reference];assert [entry['slot_id'],entry['member_id']]==s['scope']
            assert hashlib.sha256(entry['text'].encode()).hexdigest()==entry['text_sha256']
        route=x['rank_reason'].get('typed_route')
        if route:
            routes+=1;edge_rows=[s['edges'][eid] for eid in route['edges']]
            assert [e['type'] for e in edge_rows]==route['types']
            allowed=[list(p) for p,w in PATHS[proof['phase']]];assert route['types'] in allowed
            assert all(e['attrs'].get('version') in (None,s['current_version']) for e in edge_rows)
            if proof['condition']=='G3':assert all(e['status']=='Confirmed' for e in edge_rows)
            uncertain=sum(e['status']=='Inferred' for e in edge_rows);assert uncertain==route['inferred_edges'];inferred+=uncertain
            cursor=route['root'];visited={cursor}
            for e in edge_rows:
                assert cursor in (e['source'],e['target']);cursor=e['target'] if e['source']==cursor else e['source'];assert cursor not in visited;visited.add(cursor)
            event=s['events'][x['event_id']];valid={event['node']}
            valid.update(nid for nid,n in s['nodes'].items() if n['type']=='Code' and n['attrs'].get('entity_kind')=='file' and n['attrs']['path'] in event['paths'])
            assert cursor in valid
    assert cost==proof['added_content_tokens_local_estimate'] and cost<=proof['budget']
    for i,m in masked.items():assert store.entries[m['reference']]['text']==raw['messages'][i]['content']
    return {'selected_fields_source_checked':field_count,'typed_routes_checked':routes,'inferred_edge_uses':inferred,
        'scope_or_version_errors':0,'whole_input_cap_fits':proof['input_tokens_local_estimate']<=98304}


def replay_check(point_map):
    """Restore graph history from the source event journal, not final choices."""
    grouped=defaultdict(list)
    for p in point_map:grouped[p['slot_id']].append(p)
    results=[]
    for slot,points in grouped.items():
        final=read(ROOT/'runs/software-benchmark-v196/offline-graph-r4'/str(points[0]['slot_index'])/'final-graph.json.gz')
        g=ObservedWorkGraph(slot,'member_001');by_step=defaultdict(list)
        for source in final['sources'].values():by_step[source['first_seen_step']].append(source)
        target={p['decision_step']:p for p in points};snapshots=[];start=time.process_time()
        for step in range(final['step']+1):
            sources=sorted(by_step[step],key=lambda s:(s['message_index'],s['id']))
            g.ingest({'messages':[s['message'] for s in sources]},step=step,source_indices=[s['message_index'] for s in sources])
            if step in target:
                p=target[step];s=g.snapshot();expected=read(ROOT/'runs/software-benchmark-v196/offline-graph-r4'/p['point_id']/'graph.json.gz')
                assert digest(s)==digest(expected),p['point_id']
                snapshots.append((s,digest(s)))
        assert all(digest(s)==sha for s,sha in snapshots),'Later events mutated historical graph snapshot'
        results.append({'slot_id':slot,'points_restored':len(snapshots),'steps':final['step']+1,'CPU_seconds':time.process_time()-start,
            'historical_snapshot_hashes_preserved':True,'source_only_reconstruction':True})
    save(OUT/'dynamic-replay-r1/summary.json',{'results':results,'same_as_frozen48_graph_snapshots':True,
        'scope':'single-member historical engineering replay; not online multi-agent validation',
        'scientific_gate_not_inferred_from_engineering_pass':True,'new_tested_model_calls':0})


def main():
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]));os.nice(10)
    result_dir=OUT/'ablation-r1';run_dir=RUN/'ablation-r1'
    if (result_dir/'summary.json').exists():raise ValueError('Preserve completed comparison')
    frozen=read(OUT/'query-policy-r1/policy.json');assert frozen['source_sha256']==ref(ROOT/'src/proworksim/software_dependency_query_v197.py')['sha256']
    points=read(OUT/'private-map-r1/manifest.json')['points'];replay_check(points)
    token=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(token,manifest_sha256=ref(token)['sha256']);count=lru_cache(maxsize=8192)(count)
    counter=OfficialDeepSeekCounter(token,manifest_sha256=ref(token)['sha256'])
    save(result_dir/'sources.json',{'query':ref(ROOT/'src/proworksim/software_dependency_query_v197.py'),'runner':ref(Path(__file__)),
        'preparer':ref(ROOT/'tools/prepare_dependency_audit_v197.py'),'tokenizer':meta,'protocol':ref(OUT/'protocol-r1/plan.json')})
    rows=[];start=time.monotonic();cpu_start=time.process_time()
    for p in points:
        frame,indices,s,pool,cutoff=frame_for(p);g=graph_from_snapshot(s);local_cache={}
        def measure(payload):
            key=digest(payload)
            if key not in local_cache:local_cache[key]=counter.measure(payload)['prompt_tokens']
            return local_cache[key]
        variants=[(c,b,{}) for b in POLICY['budgets'] for c in ('G0','G1','G2','G3','G4')]
        variants += [('D_no_path',4096,{'no_path':True}),('D_no_version_bonus',4096,{'no_version_bonus':True}),('D_task_roots_G2',4096,{'extra_roots':True}),('D_task_roots_G3',4096,{'extra_roots':True})]
        for name,budget,options in variants:
            condition='G3' if name=='D_task_roots_G3' else 'G2' if name.startswith('D_') else name
            store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001');t=time.process_time()
            view,proof=project(frame,condition,g,store,count=count,measure=measure,indices=indices,budget=budget,**options)
            query_cpu=time.process_time()-t;validation=verify(frame,view,proof,s,store,count,indices)
            assert proof['candidate_pool_sha256']==digest(pool)
            folder=run_dir/p['point']/f'{name}-{budget}'
            proof_ref=save(folder/'proof.json.gz',proof);payload_ref=save(folder/'payload.json.gz',view)
            selected=[p['event_map'][e['event_id']] for e in proof['selected']]
            rows.append({'point':p['point'],'instance_id':p['instance_id'],'condition':name,'budget':budget,
                'candidate_count':len(pool),'candidate_pool_sha256':digest(pool),'phase':proof['phase'],
                'selected':selected,'selected_kind_counts':dict(Counter(e['card']['kind'] for e in proof['selected'])),
                'version_statuses':dict(Counter(e['card']['version_status'] for e in proof['selected'])),
                'input_tokens_estimate':proof['input_tokens_local_estimate'],'added_tokens_estimate':proof['added_content_tokens_local_estimate'],
                'query_cpu_seconds':query_cpu,'fallback':proof['fallback'],'checks':validation,
                'proof':proof_ref,'payload':payload_ref})
        print(p['point'],'19 views verified',flush=True)
    groups=[]
    for name in dict.fromkeys(r['condition'] for r in rows):
        for budget in sorted({r['budget'] for r in rows if r['condition']==name}):
            rs=[r for r in rows if r['condition']==name and r['budget']==budget]
            groups.append({'condition':name,'budget':budget,'n':len(rs),'input_tokens_estimate_sum':sum(r['input_tokens_estimate'] for r in rs),
                'cards':sum(len(r['selected']) for r in rs),'added_tokens_estimate_sum':sum(r['added_tokens_estimate'] for r in rs),
                'query_cpu_seconds':sum(r['query_cpu_seconds'] for r in rs),'fallbacks':sum(r['fallback'] is not None for r in rs),
                'typed_routes_checked':sum(r['checks']['typed_routes_checked'] for r in rs)})
    save(result_dir/'summary.json',{'version':'v197-frozen-five-condition-offline-ablation-r1','rows':rows,'groups':groups,
        'wall_seconds':time.monotonic()-start,'CPU_seconds':time.process_time()-cpu_start,
        'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'review_labels_opened':False,'new_tested_API_calls':0,'new_tested_API_cost_CNY':0,
        'provider_exact_tokens':False,'query_order_and_tokenizer_cache_affect_timings':True,
        'independent_semantic_annotations_not_yet_scored':True})
    print('completed',len(rows),'views',flush=True)

if __name__=='__main__':main()
