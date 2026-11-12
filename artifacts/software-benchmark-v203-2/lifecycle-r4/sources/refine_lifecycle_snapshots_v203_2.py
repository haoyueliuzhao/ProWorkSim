"""Refine provenance/initial metadata from frozen frames without rerunning source recovery."""
import copy,gzip,json,sys,time,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from inventory_multimember_v203 import ROOT,read,ref,save
from proworksim.software_passive_observer_v203_2 import PassiveState,digest
ART=ROOT/'artifacts/software-benchmark-v203-2';RUN=ROOT/'runs/software-benchmark-v203-2'
def main():
    panel=read(ROOT/'artifacts/software-benchmark-v203-1/panel-r1/plan.json')['rows'];results=[];start=time.process_time()
    save(ART/'lifecycle-r4/protocol.json',{'source':ref(Path(__file__)),'observer':ref(ROOT/'src/proworksim/software_passive_observer_v203_2.py'),
        'parent':ref(ART/'lifecycle-r1/protocol.json'),'change':'T0 explicitly binds frozen public issue/organization; T6 decision-only provenance; explicit rejection categories; ordinary message send/read lifecycle retained separately',
        'no_new_source_tree_recovery_or_model_calls':True,'phase_selection_unchanged':True})
    for row in panel:
        original=RUN/f'lifecycle-r1/{row["slot_index"]}.json.gz';data=json.loads(gzip.decompress(original.read_bytes()));s=PassiveState(row['slot_id'],row['fixed_members']);frames=copy.deepcopy(data['frames'])
        controller=read(row['controller']);source=Path(row['controller']).parent/'source-snapshot/source-manifest.json';manifest=read(source)
        initial={'instance_id':row['instance_id'],'organization_id':row['organization_id'],'fixed_members':row['fixed_members'],'issue':manifest['tasks'][0]['problem_statement'],
            'source_manifest':ref(source),'frozen_organization_configuration':controller.get('execution_alignment',{}).get('organization'),
            'final_member_registry_or_terminal_scores_used':False}
        frames.insert(0,{'kind':'INITIAL','source':data['phases']['T0']['source'],'payload':initial})
        for frame in frames:
            if frame['kind']=='INTENT' and frame['payload']['tool']=='submit_integration':
                frame['source'].pop('outcome_structure_sha256',None);frame['source']['intent_structure_sha256']=digest(frame['payload'])
            s.apply(frame)
        assert set(s.phases)==set(data['phases'])
        for k in s.phases:assert s.phases[k]['state']['receipt_count']==data['phases'][k]['state']['receipt_count']
        after={**data,'frames':frames,'phases':s.phases,'events':s.events,'final_state':s.snapshot()};p=RUN/f'lifecycle-r4/{row["slot_index"]}.json.gz';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('xb') as f:f.write(gzip.compress(json.dumps(after,ensure_ascii=False).encode(),mtime=0))
        results.append({'slot_index':row['slot_index'],'instance_id':row['instance_id'],'source':ref(original),'snapshots':ref(p),'phase_count':len(s.phases),'phase_boundaries_unchanged':True,
            'event_types':dict(collections.Counter(e['kind'] for e in s.events)),
            'rejection_causes':dict(collections.Counter(e['cause'] for e in s.events if e['kind']=='Operation Rejected'))})
    summary=read(ART/'lifecycle-r1/summary.json');summary.update(refinement_CPU_seconds=time.process_time()-start,canonical_revision='r4',rows=results,
        rejection_causes=dict(sum((collections.Counter(r['rejection_causes']) for r in results),collections.Counter())),event_types=dict(sum((collections.Counter(r['event_types']) for r in results),collections.Counter())))
    save(ART/'lifecycle-r4/summary.json',summary);print('Refined36 historical streams; all phase boundaries unchanged.')
if __name__=='__main__':main()
