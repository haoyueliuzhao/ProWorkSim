"""Actual REVIEW2 migration, reciprocal review and designated delivery CPU control."""
import copy,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from inventory_multimember_v203 import ROOT,save,ref
from test_multifile_migration_v203_3 import Fixture,M1,M2
from proworksim.software_passive_observer_v203_2 import PassiveRecorder,ObservedPort,observed_model_invoke,digest
ART=ROOT/'artifacts/software-benchmark-v203-2/passive-delivery-r2'
RUN=ROOT/'runs/software-benchmark-v203-2/passive-delivery-r2'

class LiveFixture(Fixture):
    def __init__(self,folder,recorder):self.passive=recorder;self.wrapped=False;self.schema_checks=[];super().__init__(folder)
    def call(self,actor,tool,**args):
        if not self.wrapped:
            for m,port in list(self.ports.items()):
                original=copy.deepcopy(port.tools());wrapped=ObservedPort(port,m,self.passive);assert wrapped.tools()==original;self.ports[m]=wrapped;self.schema_checks.append(digest(original))
            self.wrapped=True
        result=super().call(actor,tool,**args);assert not self.passive.pending and not self.passive.faults;return result

def main():
    RUN.mkdir(parents=True);save(ART/'protocol.json',{'source':ref(Path(__file__)),'observer':ref(ROOT/'src/proworksim/software_passive_observer_v203_2.py'),
        'base_fixture':ref(ROOT/'tests/test_multifile_migration_v203_3.py'),'members':2,'organization':'REVIEW2','delivery_member':M1,
        'acceptance_frozen_before_actions':{'helper_OFFSET':1,'sample_value':2},'no_SWE_official_scoring':True,'new_model_API':0,'model_boundary_test':'cpu_scripted only'})
    recorder=PassiveRecorder(RUN/'observer','cpu-delivery',[M1,M2]);recorder.initialize({'protocol':ref(ART/'protocol.json')},
        {'issue':'Controlled two-module repair; OFFSET=1 and value=2','organization':'REVIEW2','delivery_member':M1})
    (RUN/'fixture').mkdir();f=LiveFixture(RUN/'fixture',recorder)
    f.ok(M1,'write_file',path='helper.py',text='OFFSET = 0\n')
    failed=f.ok(M1,'run_tests');assert failed['result']['passed'] is False
    f.package();original_patch=f.patch['patch_id'];f.transfer();f.receive_package()
    observation=f.ports[M2].observe();wire={'model':'cpu-scripted','messages':[{'role':'user','content':json.dumps({'observation':observation})}],'tools':f.ports[M2].tools()};original_wire=copy.deepcopy(wire)
    result={'id':'cpu-only','usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
    observed_model_invoke(recorder,M2,'cpu-input-1',wire,lambda p:result,mode='cpu_scripted');assert wire==original_wire
    f.read_all();f.adopt_all();f.ok(M2,'write_file',path='helper.py',text='OFFSET = 1\n')
    test=f.ok(M2,'run_tests');assert test['result']['passed'];f.observer.advance('VERIFIED',test)
    successor=f.ok(M2,'fix_patch',task_ids=['repair'],message='Successor completed remaining module')['result']
    f.ok(M2,'handoff_patch',patch_id=successor['patch_id'],to_member=M1,message='Return completed work to the fixed integrator')
    denied=f.call(M2,'submit_integration',message='No automatic delivery-right transfer');assert not denied['ok']
    f.ok(M1,'integrate_patch',patch_id=successor['patch_id']);assert f.ok(M1,'run_tests')['result']['passed']
    review=f.ok(M1,'org_review_patch',patch_id=successor['patch_id'],decision='accept',reason='Actual adopted successor version tested')
    final=f.ok(M1,'fix_patch',task_ids=[],message='Exact integrated final candidate')['result']
    early=f.call(M1,'submit_integration',message='Must still satisfy final REVIEW2 gate');assert not early['ok']
    f.ok(M1,'handoff_patch',patch_id=final['patch_id'],to_member=M2,message='Final version requires original designated review')
    f.ok(M2,'integrate_patch',patch_id=final['patch_id']);assert f.ok(M2,'run_tests')['result']['passed']
    f.ok(M2,'org_review_patch',patch_id=final['patch_id'],decision='accept',reason='Original REVIEW2 final same-version gate')
    delivered=f.ok(M1,'submit_integration',message='Fixed deliverer, explicit final acceptance')
    assert delivered['result']['source_reference']==final['source_reference']
    assert f.world._software()['tasks']['repair']['owner']==M2 and f.world._software()['tasks']['other']['owner']==M1
    assert f.world._software()['patches'][original_patch]['author']==M1 and f.world._software()['patches'][successor['patch_id']]['author']==M2
    _,_,bundle=f.world._bundle(M1);check=RUN/'independent-cpu-acceptance';check.mkdir()
    for name in ['sample.py','helper.py']:(check/name).write_text(bundle['files'][name])
    code='from helper import OFFSET\nfrom sample import value\nassert OFFSET == 1\nassert value == 2\n'
    proc=subprocess.run([sys.executable,'-c',code],cwd=check,capture_output=True,text=True,timeout=10);assert proc.returncode==0
    replay,proof=recorder.replay(RUN/'observer/events.jsonl','cpu-delivery',[M1,M2]);assert replay.snapshot()==recorder.state.snapshot()
    assert set(recorder.state.phases)=={'T0','T1','T2','T3','T4','T5','T6'}
    assert recorder.state.phases['T6']['state']['deliveries']==[]
    save(ART/'receipts.json',f.receipts);save(ART/'phases.json',recorder.state.phases)
    save(ART/'summary.json',{'passed':True,'actual_harness_calls':len(f.receipts),'actual_public_pytest_runs':f.test_calls,'independent_CPU_acceptance_runs':1,
        'actual_delivery_member':M1,'transferred_task_owner':M2,'other_task_owner':M1,'schema_sha256_before_and_after':f.schema_checks,
        'scripted_model_wire_unchanged':True,'new_real_model_API_calls':0,'phase_coverage':sorted(recorder.state.phases),'journal_replay_equal':True,'journal_proof':proof,
        'original_publication_authorship_preserved':True,'review_contract_unchanged':True,'final_delivery_source_reference':final['source_reference'],
        'code_contribution_level_review_independence_not_proven':True,'official_SWE_scoring_not_run':True,'runtime_scope':'local CPU fixtures only'})
    print('Passive recorder: original REVIEW2 migration/review/delivery and independent CPU acceptance passed.')
if __name__=='__main__':main()
