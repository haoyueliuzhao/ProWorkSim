"""Whole observed historical lifecycles at frozen causal phase boundaries."""
import collections,copy,gzip,json,sys,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inventory_multimember_v203 import ROOT,read,ref,save
from proworksim.software_passive_observer_v203_2 import PassiveState,digest
from proworksim.software_dual_graph_v203 import CompleteSourceReplay
ART=ROOT/'artifacts/software-benchmark-v203-2'
RUN=ROOT/'runs/software-benchmark-v203-2'
def savegz(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(gzip.compress(json.dumps(value,ensure_ascii=False).encode(),mtime=0))
def one(row):
    p=Path(row['controller']);d=read(p);source=ref(p);members=row['fixed_members'];s=PassiveState(row['slot_id'],members);frames=[];errors=[]
    s.apply({'kind':'INITIAL','source':{'controller':source,'scope':'frozen_members_and_condition_only_no_terminal_state'},'payload':{}})
    baseline=p.parent/'project-baseline-snapshot.json';capture=CompleteSourceReplay(read(baseline),members) if baseline.exists() else None
    action_count=0;timeline=[];phase_steps={};content_checks=collections.Counter();start=time.process_time()
    for i,o in enumerate(d.get('managed_boundary',{}).get('outcomes',[])):
        decision=o.get('decision',{});tool=decision.get('action');actor=o.get('worker_id');response=o.get('response',{})
        src={'controller':source,'pointer':f'/managed_boundary/outcomes/{i}','outcome_structure_sha256':digest(o)}
        if actor not in members:continue
        if not tool or not o.get('action_performed'):
            if o.get('status') in {'waiting','model_budget_exhausted','cash_budget_boundary','model_format_feedback'}:
                record={'kind':'LIFECYCLE','source':src,'payload':{'actor':actor,'status':o['status']}};s.apply(record);frames.append(record)
            continue
        action_count+=1;args=decision.get('arguments',{});intent={'kind':'INTENT','source':src,'payload':{'actor':actor,'tool':tool,'arguments':args}}
        # Submission intent is public before its outcome. Its phase pointer must
        # not invite a reviewer to read the future response as an input feature.
        if tool=='submit_integration':intent['source']={**src,'pointer':f'/managed_boundary/outcomes/{i}/decision','future_response_excluded':True}
        s.apply(intent);frames.append(intent)
        content='not_verified'
        if capture:
            previous=capture.files.get(actor);before_hash=digest(previous) if previous is not None else None
            e={'id':f'{row["slot_index"]}:{i}','actor':actor,'action':tool,'arguments':args,'ok':response.get('ok') is True,'result':response.get('result') or {},'source':src}
            c=capture.observe(e)
            if c:
                content_checks[c['status']]+=1
                if c['status']=='complete_verified' and tool!='fix_patch':content=digest(capture.files[actor])!=before_hash if before_hash else 'not_verified'
        record={'kind':'RECEIPT','source':src,'payload':{'actor':actor,'tool':tool,'arguments':args,'response':response,'content_change':content}}
        try:s.apply(record)
        except Exception as error:errors.append({'source':src,'error':repr(error)});raise
        frames.append(record)
        for key in s.phases:
            if key not in phase_steps:phase_steps[key]=action_count if key!='T0' else 0
        timeline.append({'action':action_count,'outcome_index':i,'tool':tool,'ok':response.get('ok'),'actor':actor})
    saved={'frames':frames,'phases':s.phases,'events':s.events,'final_state':s.snapshot(),'source':source,'phase_action_ordinals':phase_steps,'timeline':timeline,'all_history_previously_exposed_development':True}
    savegz(RUN/f'lifecycle-r1/{row["slot_index"]}.json.gz',saved)
    summary={'slot_index':row['slot_index'],'instance_id':row['instance_id'],'repo':row['repo'],'mode':row['organization_id'],'actions':action_count,
        'phases':{k:{'action_ordinal':phase_steps.get(k,0),'meaning':v['metadata']['meaning'],'receipt_count':v['state']['receipt_count'],'after_previous40_boundary':phase_steps.get(k,0)>40} for k,v in s.phases.items()},
        'missing_phases':[k for k in ['T0','T1','T2','T3','T4','T5','T6'] if k not in s.phases],'event_types':dict(collections.Counter(e['kind'] for e in s.events)),
        'rejection_causes':dict(collections.Counter(e['cause'] for e in s.events if e['kind']=='Operation Rejected')),'content_checks':dict(content_checks),
        'CPU_seconds':time.process_time()-start,'errors':errors,'snapshots':ref(RUN/f'lifecycle-r1/{row["slot_index"]}.json.gz')}
    save(ART/f'lifecycle-r1/task-{row["slot_index"]}.json',summary);return summary
def main():
    rows=read(ROOT/'artifacts/software-benchmark-v203-1/panel-r1/plan.json')['rows']
    save(ART/'lifecycle-r1/protocol.json',{'sources':[ref(Path(__file__)),ref(ROOT/'src/proworksim/software_passive_observer_v203_2.py')],
        'same36_historical_tasks_not_new_independent_sample':True,'new_model_API':0,'selection_uses_no_final_official_scores':True,
        'T0':'frozen initial members/config, no final registry','T1':'first accepted create_task or claim_task; ownership can still be unclaimed',
        'T2':'first accepted actual content-changing edit where recoverable; unknown content changes separately marked','T3':'first fixed artifact publication or peer read, not proof of receipt',
        'T4':'first executed public-test failure; missing if none observed','T5':'first integration, accepted owner transfer or edit after observed failed test',
        'T6':'before first submit attempt, no response or terminal score in that snapshot','repeated_phases_are_not_independent_tasks':True,'raw_phase_sources_are_observer_only':True})
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('fork')) as pool:result=list(pool.map(one,rows))
    summary={'tasks':36,'actions':sum(r['actions'] for r in result),'phase_presence':{},'phase_after40':{},'event_types':dict(sum((collections.Counter(r['event_types']) for r in result),collections.Counter())),
        'rejection_causes':dict(sum((collections.Counter(r['rejection_causes']) for r in result),collections.Counter())),
        'errors':[e for r in result for e in r['errors']],'CPU_seconds':sum(r['CPU_seconds'] for r in result),'new_independent_tasks':0,'new_model_API':0,'new_organization_mismatch_labels':0}
    for k in ['T0','T1','T2','T3','T4','T5','T6']:
        summary['phase_presence'][k]=sum(k in r['phases'] for r in result);summary['phase_after40'][k]=sum(r['phases'].get(k,{}).get('after_previous40_boundary',False) for r in result)
    summary['phase_points']=sum(summary['phase_presence'].values());summary['unique_task_action_boundaries']=sum(len({v['action_ordinal'] for v in r['phases'].values()}) for r in result)
    save(ART/'lifecycle-r1/summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
