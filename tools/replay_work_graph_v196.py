"""Offline P0: replay actually visible prefixes, never model outputs or scores.

Freeze point identities first; independently witness source hashes in actual
wire payloads, then restore only prior seen observations. No hidden World,
repository files, public RPC bodies, final candidates or model/API clients.
"""
from __future__ import annotations
import argparse,copy,gzip,hashlib,json,os,resource,sqlite3,time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from proworksim.software_context_graph_v196 import ObservedWorkGraph
from proworksim.software_context_graph_check_v196 import verify_graph,verify_view
from proworksim.software_context_selection_v196 import project,candidates,RULES
from proworksim.software_context_compression_v175 import digest,canonical
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader

ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'runs/software-benchmark-v055/secondary-volume-r1/software-benchmark-v193/key-event-pilot-r1'
PLAN=ROOT/'artifacts/software-benchmark-v196/p0-plan-r1/plan.json'
POINTS=ROOT/'artifacts/software-benchmark-v196/fixed-points-r1/manifest.json'


def read(path):return json.loads(Path(path).read_bytes())
def reference(path):
    p=Path(path);raw=p.read_bytes()
    return {'path':str(p.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    if path.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
    path.write_bytes(raw);return reference(path)
def header(path):
    data=b''
    with path.open('rb') as f:
        while b',"spans":' not in data:
            block=f.read(4096)
            if not block or len(data)>1024**2:raise ValueError('Unexpected provenance header')
            data+=block
    return json.loads(data.split(b',"spans":',1)[0]+b'}')
def captures(item):
    with sqlite3.connect((HISTORY/'api-ledger.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT step,payload_sha,purpose,attempt,status FROM requests WHERE job_id=? ORDER BY started,request_id',(item['slot_id'],))]
    assert all(r['attempt']==1 and r['status']=='settled' and r['purpose']=='agent' for r in rows)
    for r in rows:
        r['capture']=HISTORY/'episodes'/str(item['slot_index'])/'controller-output/model-ledger/request-capture-v193'/hashlib.sha256(r['step'].encode()).hexdigest()
    return rows
def freeze():
    if POINTS.exists():raise ValueError('Point manifest already frozen')
    plan=read(PLAN);rows=[];histories=[]
    for item in plan['histories']:
        calls=captures(item);point_numbers=sorted({int((len(calls)-1)*q) for q in plan['decision_point_quantiles']})
        assert len(point_numbers)==4
        histories.append({**item,'requests':len(calls)})
        for index in point_numbers:
            r=calls[index]
            rows.append({**item,'point_id':f"{item['slot_index']}-request-{index+1:04d}",'request_number':index+1,
                'decision_step':index,'logical_request_id':r['step'],'payload':reference(r['capture']/'payload.json'),
                'projection':reference(r['capture']/'projection-evidence.json'),'ledger_payload_sha256':r['payload_sha']})
    write(POINTS,{'version':'v196-fixed-points-before-view-comparison-r1','plan':reference(PLAN),'histories':histories,'points':rows,
        'outcome_selection':False,'future_length_for_sampling_only_not_selector_input':True})
    print('Frozen',len(rows),'points',flush=True)


def source_frame(call,known,stats):
    folder=call['capture'];raw=(folder/'payload.json').read_bytes();wire=json.loads(raw);projection=read(folder/'projection-evidence.json')
    h=header(folder/'provenance.json')
    assert h['identity']['request_id']==call['step']
    assert hashlib.sha256(raw).hexdigest()==call['payload_sha']==h['payload_sha256']
    indices=projection['selected_indices'];assert len(indices)==len(wire['messages'])
    treatment=projection.get('observation_history_projection',{}).get('context_treatment',{})
    assert treatment.get('condition','M1-5')=='M1-5' and not treatment.get('critical_cards')
    masked={m['index']:m for m in treatment.get('masked',[])}
    frame=copy.deepcopy(wire)
    for position,(index,message) in enumerate(zip(indices,wire['messages'])):
        if position in masked:
            key=(index,masked[position]['source_sha256'])
            if key not in known:raise ValueError(f'Cannot recover source previously seen on wire: {key}')
            frame['messages'][position]=copy.deepcopy(known[key]);stats['restored_old_observation_exposures']+=1
        else:
            known[(index,digest(message))]=copy.deepcopy(message)
    stats['actual_requests_checked']+=1
    return frame,indices,wire


def run(revision):
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-2:]));os.nice(10)
    out=ROOT/f'artifacts/software-benchmark-v196/offline-graph-{revision}'
    runroot=ROOT/f'runs/software-benchmark-v196/offline-graph-{revision}'
    if (out/'summary.json').exists():raise ValueError('Preserve completed offline result')
    out.mkdir(parents=True,exist_ok=True)
    manifest=read(POINTS);plan=read(PLAN)
    assert manifest['plan']==reference(PLAN)
    token=ROOT/'runs/software-benchmark-v055/tokenizer-r1/manifest.json'
    count,meta=load_official_content_counter(token,manifest_sha256=reference(token)['sha256']);count=lru_cache(maxsize=8192)(count)
    counter=OfficialDeepSeekCounter(token,manifest_sha256=reference(token)['sha256'])
    source_files=[ROOT/f'src/proworksim/software_context_{x}_v196.py' for x in ('graph','selection','graph_check')]+[Path(__file__).resolve()]
    write(out/'source-manifest.json',{'files':[reference(p) for p in source_files],'fixed_points':reference(POINTS),'rules':RULES,'tokenizer':meta})
    results=[];histories=[];errors=[];stats=Counter();wall_start=time.monotonic();cpu_start=time.process_time()
    for item in plan['histories']:
        known={};plain=ObservedWorkGraph(item['slot_id'],'member_001',dependencies_enabled=False)
        graph=ObservedWorkGraph(item['slot_id'],'member_001');timings=Counter();history_stats=Counter()
        points={p['decision_step']:p for p in manifest['points'] if p['slot_id']==item['slot_id']}
        try:
            for step,call in enumerate(captures(item)):
                frame,indices,wire=source_frame(call,known,history_stats)
                for label,g in [('canonical_events',plain),('work_graph',graph)]:
                    t=time.process_time();g.ingest(frame,step=step,source_indices=indices);timings[label]+=time.process_time()-t
                if step not in points:continue
                point=points[step];folder=runroot/point['point_id'];snapshot=graph.snapshot()
                checked=verify_graph(snapshot,episode=item['slot_id'],member='member_001',step=step,witnesses=set(known))
                snapshot_ref=write(folder/'graph.json.gz',snapshot)
                row={'point_id':point['point_id'],'instance_id':item['instance_id'],'decision_step':step,
                    'graph':snapshot_ref,'graph_check':checked,'focus':snapshot['focus'],'variants':{}}
                for method,g,edge_enabled in [('M1-5',plain,False),('M1-5K-v2',plain,False),('M1-5G',graph,True),('M1-5G-no-edges',graph,False)]:
                    store=SourceLabeledHistoryReader(point['point_id'],item['slot_id'],'member_001')
                    t=time.process_time()
                    value,proof=project(frame,'M1-5G' if method=='M1-5G-no-edges' else method,g,store,count=count,
                        source_indices=indices,decision_step=step,measure=counter.measure,dependency_edges=edge_enabled)
                    elapsed=time.process_time()-t
                    check=verify_view(frame,value,proof,snapshot,store,count=count,indices=indices)
                    variant_folder=folder/method
                    refs={'payload':write(variant_folder/'payload.json.gz',value),'proof':write(variant_folder/'proof.json.gz',proof),
                        'original_evidence':write(variant_folder/'original-evidence.json.gz',store.entries)}
                    selected=proof['selected'];field_counts=Counter(f['name'] for s in selected for f in s['selected_fields'])
                    row['variants'][method]={'input_tokens_local_estimate':proof['input_tokens_local_estimate'],
                        'added_content_tokens_local_estimate':proof['added_content_tokens_local_estimate'],
                        'cards':len(selected),'card_kinds':dict(Counter(s['card']['kind'] for s in selected)),
                        'selected_ids':[s['event_id'] for s in selected],
                        'selected_version_statuses':dict(Counter(s['card']['version_status'] for s in selected)),
                        'selected_fields':dict(field_counts),'omitted_fields':sum(len(s['omitted_fields']) for s in selected),
                        'candidate_pool_sha256':proof.get('candidate_pool_sha256'),'candidate_pool_size':proof.get('candidate_pool_size',0),
                        'fallback':proof['fallback'],'input_capacity_fits':proof['input_capacity_fits'],
                        'dependency_selected':sum(bool(s['rank_reason'].get('dependency_path')) for s in selected),
                        'view_query_cpu_seconds':elapsed,'checks':check,'evidence':refs}
                b=row['variants']['M1-5K-v2'];c=row['variants']['M1-5G'];d=row['variants']['M1-5G-no-edges']
                assert b['candidate_pool_sha256']==c['candidate_pool_sha256']==d['candidate_pool_sha256']
                row['edges_change_selected_set']=set(c['selected_ids'])!=set(d['selected_ids'])
                row['edges_change_selected_order']=c['selected_ids']!=d['selected_ids']
                row['K_vs_G_selection_changed']=b['selected_ids']!=c['selected_ids']
                row['independent_recovery_witness_count']=len(known)
                results.append(row);print(point['point_id'],'verified',flush=True)
            s=graph.snapshot();final_ref=write(runroot/str(item['slot_index'])/'final-graph.json.gz',s)
            test_events=[e for e in graph.events.values() if e['kind']=='test'];failures=[e for e in test_events if e.get('critical_failure')]
            changes=[e for e in graph.events.values() if e['kind']=='change']
            def has(e,names):return any(f['name'] in names for f in e['fields'])
            histories.append({**item,**history_stats,'nodes':dict(Counter(n['type'] for n in graph.nodes.values())),
                'edges':dict(Counter(e['type'] for e in graph.edges.values())),
                'edge_statuses':dict(Counter(e['status'] for e in graph.edges.values())),
                'ast_fragments':len(graph.ast_attempts),'ast_fragments_parsed':sum(a['parsed'] for a in graph.ast_attempts.values()),
                'canonical_tests':len(test_events),'test_read_observation_sources':sum(len(e['sources']) for e in test_events),
                'failed_runs':len(failures),'failed_with_name':sum(has(e,{'failed_test'}) for e in failures),
                'failed_with_error_excerpt':sum(has(e,{'error_excerpt'}) for e in failures),
                'failed_with_command_or_declared_selection':sum(has(e,{'observed_command','observed_command_json','declared_selection','observed_selection'}) for e in failures),
                'code_changes':len(changes),'changes_with_path':sum(has(e,{'path'}) for e in changes),
                'changes_with_code_excerpt':sum(has(e,{'change_before','change_after','written_text','diff_excerpt'}) for e in changes),
                'graph_json_bytes':len(canonical(s).encode()),'compressed_graph':final_ref,'cpu_seconds':dict(timings)})
            stats.update(history_stats)
        except Exception as error:
            import traceback
            errors.append({**item,'step':locals().get('step'),'error':str(error),'type':type(error).__name__,'traceback':traceback.format_exc()})
            write(out/'errors.json',errors);print(item['instance_id'],'ERROR',type(error).__name__,str(error),flush=True)
        write(out/'progress.json',{'points':len(results),'histories_completed':len(histories),'errors':errors})
    groups={}
    for method in ('M1-5','M1-5K-v2','M1-5G','M1-5G-no-edges'):
        vs=[r['variants'][method] for r in results];fields=Counter();kinds=Counter();versions=Counter()
        for v in vs:fields.update(v['selected_fields']);kinds.update(v['card_kinds']);versions.update(v['selected_version_statuses'])
        groups[method]={'points':len(vs),'input_tokens_local_estimate_sum':sum(v['input_tokens_local_estimate'] for v in vs),
            'added_content_tokens_local_estimate_sum':sum(v['added_content_tokens_local_estimate'] for v in vs),
            'cards':sum(v['cards'] for v in vs),'selected_fields':dict(fields),'card_kinds':dict(kinds),'versions':dict(versions),
            'fallbacks':sum(v['fallback'] is not None for v in vs),'over_capacity':sum(not v['input_capacity_fits'] for v in vs),
            'omitted_fields':sum(v['omitted_fields'] for v in vs),'dependency_selected':sum(v['dependency_selected'] for v in vs),
            'view_query_cpu_seconds':sum(v['view_query_cpu_seconds'] for v in vs)}
    result={'version':'v196-offline-private-work-graph-r1','plan':reference(PLAN),'points':reference(POINTS),
        'sources':reference(out/'source-manifest.json'),'groups':groups,'rows':results,'histories':histories,'errors':errors,
        'prefix_audit':dict(stats),'edge_ablation_changed_sets':sum(r['edges_change_selected_set'] for r in results),
        'edge_ablation_changed_orders':sum(r['edges_change_selected_order'] for r in results),
        'K_vs_G_changed':sum(r['K_vs_G_selection_changed'] for r in results),
        'elapsed_seconds':time.monotonic()-wall_start,'process_CPU_seconds':time.process_time()-cpu_start,
        'process_peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'RSS_includes_tokenizer_payload_and_verifier':True,
        'local_token_estimates_not_provider_usage':True,'new_model_calls':0,'new_API_cost_CNY':0,
        'new_task_outcomes_measured':False,'necessary_dependency_recall_ground_truth_available':False,
        'all48_passed':len(results)==48 and len(histories)==12 and not errors}
    write(out/'summary.json',result);print(json.dumps({'groups':groups,'errors':errors,'points':len(results)},ensure_ascii=False),flush=True)
    if errors:raise SystemExit(2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--revision',default='r1');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.revision)
