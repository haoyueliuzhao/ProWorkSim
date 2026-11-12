"""Frozen F0-F4 offline factorization. No reference labels in selection."""
import sys,os,time,resource,copy,json,traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,frame_for,graph_from_snapshot
import run_fact_context_v199 as old
from proworksim.software_fact_budget_v200 import FactCatalogue,project,CONDITIONS,location
from proworksim.software_fact_context_v199 import FactInventory
from proworksim.software_global_evidence_v198 import enrich
from proworksim.software_evidence_bindings_v199 import EvidenceBindings
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_compression_v175 import digest,canonical
from proworksim.software_context_graph_check_v196 import recover_field
BASE=ROOT/'artifacts/software-benchmark-v200';RUN=ROOT/'runs/software-benchmark-v200/development-r1'

def initialize():
    old.initialize()

def check(frame,view,proof,g,cat,store):
    masks={m['index'] for m in proof['masked']};texts=defaultdict(list);fields=0;addresses=defaultdict(list)
    assert frame.get('tools')==view.get('tools') and len(frame['messages'])==len(view['messages'])
    for i,(a,b) in enumerate(zip(frame['messages'],view['messages'])):
        assert (a.get('role'),a.get('tool_call_id'),a.get('tool_calls'))==(b.get('role'),b.get('tool_call_id'),b.get('tool_calls'))
        if i not in masks or a['role'] in {'assistant','system'}:assert a==b
    assert all(m['reference'] in canonical(view) for m in proof['masked'])
    for card in proof['selected']:
        text=card.get('content') or view['messages'][card['anchor']]['content']
        assert old.count(text)<=768 and json.loads(text.split('\n',1)[1])==card['card'];texts[card['anchor']].append(text)
        assert len(card['selected_facts'])==len(card['card']['facts'])
        for field,shown in zip(card['selected_facts'],card['card']['facts']):
            assert recover_field(field,g.sources)==shown['value'];fields+=1
            assert digest(g.sources[field['origin']['source_id']]['message'])==field['origin']['message_sha256']
            for origin in field.get('origins',[]):recover_field({'value':field['value'],'origin':origin},g.sources)
            if proof['condition']=='F4':
                u={**cat.units[field['unit_id']],'origin':field['origin'],'value':field['value']}
                loc=location(u,cat)
                if loc:
                    key,(a,z)=loc;assert not any(max(a,x)<min(z,y) for x,y in addresses[key]),'F4 repeated exact source characters'
                    addresses[key].append((a,z))
        if card['card']['version_status']=='current_observed_version':assert card['card']['source_version']==g.nodes[g.current_version]['attrs']['source_reference']
        for r in card['card']['originals']:assert [store.entries[r]['slot_id'],store.entries[r]['member_id']]==[g.episode,g.member]
    for a,text in texts.items():assert '\n\n'.join(text)==view['messages'][a]['content']
    assert sum(old.count('\n\n'.join(x)) for x in texts.values())==proof['added_tokens_estimate']<=proof['budget']
    assert proof['input_tokens_estimate']<=98304
    for closure in proof.get('dependency_closures',[]):
        for d in closure['requirements']:
            if 'edge_id' in d:
                edge=cat.entities.edges[d['edge_id']];assert edge['verification_status']=='Confirmed' and edge['effective_for_current_workspace']
    return {'source_fragment_presentations_checked':fields,'source_or_permission_or_budget_errors':0}

def one(p):
    cpu=time.process_time();start=time.monotonic();frame,indices,s,_,_=frame_for(p);g=graph_from_snapshot(s);enrich(g,frame,indices)
    m=old.metadata[p['instance_id']];entities=EvidenceBindings(g.snapshot(),repo=m['repo'],base_commit=m['base_commit'],issue_id=p['instance_id'])
    store=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001');_,masked,cut=baseline(frame,store,old.count,indices)
    inv=FactInventory(g,frame,indices,masked,cut);t=time.process_time();cat=FactCatalogue(inv,entities,old.count);build_cpu=time.process_time()-t
    folder=RUN/p['point'];catalogue=save(folder/'catalogue.json.gz',cat.snapshot());baseline_refs=ROOT/'runs/software-benchmark-v199/development-r4'/p['point']
    assert digest(inv.snapshot())==digest(read(baseline_refs/'fact-inventory.json.gz'))
    cache={}
    def measure(v):
        key=digest(v)
        if key not in cache:cache[key]=old.counter.measure(v)['prompt_tokens']
        return cache[key]
    rows=[]
    for budget in [1024,2048,4096]:
        for condition in CONDITIONS:
            st=SourceLabeledHistoryReader(p['point_id'],p['slot_id'],'member_001');t=time.process_time()
            view,proof=project(frame,condition,g,entities,inv,cat,st,count=old.count,measure=measure,indices=indices,budget=budget)
            elapsed=time.process_time()-t;checks=check(frame,view,proof,g,cat,st)
            if condition=='F0':assert view==read(baseline_refs/f'E3-{budget}/payload.json.gz'),'F0 differs from frozen E3'
            f=folder/f'{condition}-{budget}'
            rows.append({'point':p['point'],'instance_id':p['instance_id'],'condition':condition,'budget':budget,
                'fact_pool_sha256':proof['fact_pool_sha256'],'catalogue_sha256':proof['catalogue_sha256'],
                'selected_groups':sorted({c['group_id'] for c in proof['selected']}),'cards':len(proof['selected']),
                'input_tokens_estimate':proof['input_tokens_estimate'],'added_tokens_estimate':proof['added_tokens_estimate'],
                'unmet_mandatory_groups':proof['unmet_mandatory'],'unmet_required_units':proof.get('unmet_required_units',[]),
                'query_CPU_seconds':elapsed,'checks':checks,'proof':save(f/'proof.json.gz',proof),'payload':save(f/'payload.json.gz',view)})
    assert len({r['fact_pool_sha256'] for r in rows})==len({r['catalogue_sha256'] for r in rows})==1
    result={'point':p['point'],'instance_id':p['instance_id'],'rows':rows,'catalogue':catalogue,
        'inventory':ref(baseline_refs/'fact-inventory.json.gz'),'sources':ref(baseline_refs/'sources.json.gz'),'registry':ref(baseline_refs/'entity-registry.json.gz'),
        'units':len(cat.units),'facts':len(cat.by_fact),'dependency_links':sum(map(len,cat.dependencies.values())),
        'catalogue_CPU_seconds':build_cpu,'CPU_seconds':time.process_time()-cpu,'wall_seconds':time.monotonic()-start,
        'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    save(folder/'completed.json',result);return result

def main():
    out=BASE/'development-r1'
    if (out/'sources.json').exists():raise ValueError('Preserve frozen run')
    os.nice(10);os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-4:]))
    points=read(ROOT/'artifacts/software-benchmark-v197/private-map-r1/manifest.json')['points']
    files=[Path(__file__),ROOT/'src/proworksim/software_fact_budget_v200.py',ROOT/'src/proworksim/software_fact_context_v199.py',ROOT/'src/proworksim/software_evidence_bindings_v199.py']
    saved=[]
    for p in files:
        target=BASE/'source-r1'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes());saved.append(ref(target))
    save(out/'sources.json',{'files':saved,'v199_dependency_manifest':ref(ROOT/'artifacts/software-benchmark-v199/development-r4/sources.json'),
        'protocol':ref(BASE/'protocol-r1/plan.json'),'reference_labels_not_loaded':True,'CPU_workers':4})
    start=time.monotonic();results=[];errors=[]
    with ProcessPoolExecutor(max_workers=4,initializer=initialize) as pool:
        jobs={pool.submit(one,p):p for p in points}
        for job in as_completed(jobs):
            p=jobs[job]
            try:results.append(job.result());print(p['point'],'15 views verified',flush=True)
            except Exception as e:
                error={'point':p['point'],'error':repr(e),'traceback':traceback.format_exc()};errors.append(error);save(RUN/p['point']/'error.json',error);print(p['point'],repr(e),flush=True)
            save(out/'progress.json',{'completed_points':len(results),'errors':errors,'planned_points':48})
    results.sort(key=lambda p:p['point']);save(out/'summary.json',{'version':'v200-fact-budget-r1','points':results,'rows':[r for p in results for r in p['rows']],
        'failures':errors,'planned_points':48,'planned_views':720,'wall_seconds':time.monotonic()-start,
        'worker_CPU_seconds':sum(p['CPU_seconds'] for p in results),'peak_worker_RSS_KiB':max((p['peak_RSS_KiB'] for p in results),default=0),
        'new_API_calls':0,'Agent_reads':0,'Agent_fact_use_measured':False,'holdout_opened':False})
    print('finished',len(results),'points',len(errors),'errors',flush=True)
if __name__=='__main__':main()
