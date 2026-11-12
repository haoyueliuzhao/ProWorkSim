"""Actual managed declaration/transfer events; no circular dependency confirmation."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from inventory_multimember_v203 import ROOT,save,ref
from test_multifile_migration_v203_3 import Fixture,M1,M2
from proworksim.software_dependency_evidence_v203_1 import DependencyEvidence
OUT=ROOT/'artifacts/software-benchmark-v203-1/live-observer-control-r1'
def main():
    folder=ROOT/'runs/software-benchmark-v203-1/live-observer-control-r1';folder.mkdir(parents=True);f=Fixture(folder);g=DependencyEvidence()
    def bind(r,name):
        p=OUT/(name+'.json');save(p,r['full_response']);return g.source(p,'','harness_receipt',r['actor'])
    offered=f.ok(M1,'offer_transfer',task_id='other',to_member=M2,reason='Separate upstream artifact task');sid=bind(offered,'offer');g.observe_transfer('offer_transfer',M1,offered['arguments'],offered['full_response'],sid)
    accepted=f.ok(M2,'accept_transfer',offer_id=offered['result']['offer_id']);sid=bind(accepted,'accept');g.observe_transfer('accept_transfer',M2,accepted['arguments'],accepted['full_response'],sid)
    declared=f.ok(M1,'declare_dependency',task_id='repair',depends_on='other');sid=bind(declared,'declared');rid=g.observe_dependency_declaration(M1,declared['arguments'],declared['full_response'],sid)
    denied=f.call(M1,'fix_patch',task_ids=['repair'],message='Must not bypass declared prerequisite');assert not denied['ok'];sid=bind(denied,'blocked')
    g.emit('TASK_BLOCKED',task='task:repair',upstream='task:other',cause='declared_protocol_prerequisite',evidence=sid,scope='fixed_patch_admission_only',independent_task_dependency_proven=False)
    f.ok(M2,'write_file',path='helper.py',text='OFFSET = 1\n');patch=f.ok(M2,'fix_patch',task_ids=['other'],message='Upstream fixed artifact')['result']
    f.ok(M2,'handoff_patch',patch_id=patch['patch_id'],to_member=M1,message='Explicit prerequisite artifact');f.ok(M1,'integrate_patch',patch_id=patch['patch_id'])
    fixed=f.ok(M1,'fix_patch',task_ids=['repair'],message='Declared artifact now included');sid=bind(fixed,'unblocked')
    g.emit('TASK_UNBLOCKED',task='task:repair',evidence=sid,scope='fixed_patch_admission_only',independent_task_dependency_proven=False)
    assert g.relations[rid]['status']=='candidate' and g.relations[rid]['verifier'] is None
    save(OUT/'events.json',g.snapshot());save(OUT/'receipts.json',f.receipts)
    save(OUT/'summary.json',{'passed':True,'source':ref(Path(__file__)),'contract_source':ref(ROOT/'src/proworksim/software_dependency_evidence_v203_1.py'),
        'actual_harness_actions':len(f.receipts),'actual_owner_transfer':True,'actual_dependency_declaration':True,'blocked_then_recovered':True,
        'relation_after_successful_protocol_execution':g.relations[rid]['status'],'independent_software_task_dependency_proven':False,'policy_feedback_confirmation':False,
        'new_model_API':0,'pytest_runs':f.test_calls,'no_benchmark_task_executed':True})
    print('Managed declaration observed as candidate; enforced contract did not self-confirm necessity.')
if __name__=='__main__':main()
