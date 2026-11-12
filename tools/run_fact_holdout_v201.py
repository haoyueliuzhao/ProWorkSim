"""Frozen A/B/C historical task-holdout views, no annotation values in selector."""
import sys,os,time,resource,copy
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read,save,ref,graph_from_snapshot
import run_fact_context_v199 as count_tools
from run_fact_budget_v200 import check
from proworksim.software_fact_budget_v200 import FactCatalogue,project
from proworksim.software_fact_context_v199 import FactInventory
from proworksim.software_evidence_bindings_v199 import EvidenceBindings
from proworksim.software_context_selection_v196 import baseline
from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader
from proworksim.software_context_compression_v175 import digest
BASE=ROOT/'artifacts/software-benchmark-v201';RUN=ROOT/'runs/software-benchmark-v201/offline-r1'

def init():count_tools.initialize()

def one(p):
    start=time.process_time();frame=read(p['frame']['path']);g=graph_from_snapshot(read(p['graph']['path']));indices=p['indices']
    entities=EvidenceBindings(g.snapshot(),repo=p['repo'],base_commit=p['base_commit'],issue_id=p['instance_id'])
    store=SourceLabeledHistoryReader(p['point'],p['slot_id'],'member_001');_,masked,cut=baseline(frame,store,count_tools.count,indices)
    inv=FactInventory(g,frame,indices,masked,cut);assert digest(inv.snapshot())==digest(read(p['inventory']['path']))
    cat=FactCatalogue(inv,entities,count_tools.count);cache={};rows=[]
    def measure(v):
        key=digest(v)
        if key not in cache:cache[key]=count_tools.counter.measure(v)['prompt_tokens']
        return cache[key]
    for budget in [1024,2048,4096]:
        for condition in ['A','B','C']:
            st=SourceLabeledHistoryReader(p['point'],p['slot_id'],'member_001');t=time.process_time()
            if condition=='C':
                view,masks,_=baseline(frame,st,count_tools.count,indices)
                proof={'version':'v201-C-M1-5','condition':'C','budget':budget,'masked':masks,'selected':[],'added_tokens_estimate':0,
                    'input_tokens_estimate':measure(view),'fact_pool_sha256':digest(inv.facts),'catalogue_sha256':digest(cat.snapshot()),'unmet_mandatory':[]}
            else:
                view,proof=project(frame,{'A':'F0','B':'F1'}[condition],g,entities,inv,cat,st,count=count_tools.count,measure=measure,indices=indices,budget=budget)
                proof.update(original_condition=proof['condition'],condition=condition)
            duration=time.process_time()-t;checks=check(frame,view,proof,g,cat,st);folder=RUN/p['point']/f'{condition}-{budget}'
            rows.append({'point':p['point'],'instance_id':p['instance_id'],'repo':p['repo'],'condition':condition,'budget':budget,
                'input_tokens_estimate':proof['input_tokens_estimate'],'added_tokens_estimate':proof['added_tokens_estimate'],'cards':len(proof['selected']),
                'fact_pool_sha256':proof['fact_pool_sha256'],'unmet_mandatory':proof['unmet_mandatory'],'CPU_seconds':duration,'checks':checks,
                'proof':save(folder/'proof.json.gz',proof),'payload':save(folder/'payload.json.gz',view),'reader_entries':save(folder/'reader-entries.json.gz',st.entries)})
    assert len({r['fact_pool_sha256'] for r in rows})==1
    result={**p,'rows':rows,'catalogue':save(RUN/p['point']/'catalogue.json.gz',cat.snapshot()),'registry':save(RUN/p['point']/'registry.json.gz',entities.as_json()),
        'CPU_seconds':time.process_time()-start,'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    save(RUN/p['point']/'completed.json',result);return result

def main():
    out=BASE/'offline-r1'
    if (out/'source-freeze.json').exists():raise ValueError('Preserve completed namespace')
    plan=read(BASE/'protocol-r1/plan.json');source=read(BASE/'source-admission-r1/summary.json')
    for frozen in plan['candidate_sources']:
        local=ROOT/'src/proworksim'/Path(frozen['path']).name
        assert ref(local)['sha256']==frozen['sha256'],'Frozen candidate changed after opening tasks'
    annotations=[]
    for p in source['points']:
        f=BASE/'annotations-r1'/f"{p['point']}.json";assert f.exists();annotations.append(ref(f)) # hash only; no labels read
    save(out/'source-freeze.json',{'plan':ref(BASE/'protocol-r1/plan.json'),'source_admission':ref(BASE/'source-admission-r1/summary.json'),
        'annotations_before_views':annotations,'runner':ref(Path(__file__)),'new_API_calls':0})
    os.nice(10);os.sched_setaffinity(0,set(sorted(os.sched_getaffinity(0))[-4:]));start=time.monotonic();results=[];errors=[]
    with ProcessPoolExecutor(max_workers=4,initializer=init) as pool:
        jobs={pool.submit(one,p):p for p in source['points']}
        for job in as_completed(jobs):
            p=jobs[job]
            try:results.append(job.result());print(p['point'],'9 checked views',flush=True)
            except Exception as e:
                import traceback
                error={'point':p['point'],'error':repr(e),'traceback':traceback.format_exc()};errors.append(error);save(RUN/p['point']/'error.json',error);print(error['error'],flush=True)
    results.sort(key=lambda p:p['point']);save(out/'summary.json',{'version':'v201-frozen-historical-task-holdout-r1','points':results,'rows':[r for p in results for r in p['rows']],
        'planned_tasks':12,'actual_points':len(source['points']),'planned_views':len(source['points'])*9,'errors':errors,'wall_seconds':time.monotonic()-start,
        'worker_CPU_seconds':sum(p['CPU_seconds'] for p in results),'max_worker_RSS_KiB':max((p['peak_RSS_KiB'] for p in results),default=0),
        'labels_loaded_by_selector':False,'new_API_calls':0,'future_model_response_or_final_score_read':False})
    print('complete',len(results)*9,'views',len(errors),'errors',flush=True)
if __name__=='__main__':main()
