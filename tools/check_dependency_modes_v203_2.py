"""CPU contract and actual before/after execution, without declaring a world dependency."""
import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from inventory_multimember_v203 import ROOT,save,ref
from test_multifile_migration_v203_3 import Fixture,M1,M2
from proworksim.software_dependency_checks_v203_2 import structural_confirmation,execution_confirmation
ART=ROOT/'artifacts/software-benchmark-v203-2/dependency-checks-r2';RUN=ROOT/'runs/software-benchmark-v203-2/dependency-checks-r2'
def main():
    RUN.mkdir(parents=True)
    contract={'origin':'independently_frozen_task_definition','registered_before_actions':True,
        'tasks':{'repair':{'produces':['helper_interface_v1'],'initial_owner':M1},'other':{'requires':['helper_interface_v1'],'initial_owner':M2}},
        'scope':'authored CPU engineering control, not a real task or human semantic gold'}
    save(ART/'frozen-contract.json',contract);(RUN/'fixture').mkdir();f=Fixture(RUN/'fixture')
    # Establish the preregistered initial task allocation before the comparison;
    # these setup operations are recorded and are not credited as an intervention.
    f.ok(M1,'return_task',task_id='other',reason='Initialize the frozen consumer allocation')
    f.ok(M2,'claim_task',task_id='other',reason='Initial consumer responsibility')
    f.ok(M1,'revise_task',task_id='repair',description='Produce helper_interface_v1 with OFFSET=1',expected_revision=1,reason='Frozen CPU producer contract')
    f.ok(M2,'revise_task',task_id='other',description='Consume helper_interface_v1 with unchanged sample.py and public test',expected_revision=1,reason='Frozen CPU consumer contract')
    bindings={role:{k:f.world._software()['tasks'][tid][k] for k in ['task_id','revision','owner']} for role,tid in [('producer','repair'),('consumer','other')]}
    # M2's downstream code is fixed before the first execution; M1 supplies only helper.py.
    f.ok(M1,'write_file',path='sample.py',text='value = 1\n')
    f.ok(M2,'write_file',path='sample.py',text='from helper import OFFSET\nvalue = OFFSET + 1\n')
    failed=f.ok(M2,'run_tests')['result'];assert failed['passed'] is False
    _,_,tree=f.world._bundle(M2);before={'files':copy.deepcopy(tree['files']),'version':failed['source_reference'],'test':failed,'task_bindings':copy.deepcopy(bindings),'test_actor':M2,
        'environment_id':'frozen_local_python_pytest_entry','selector':'test_sample.py'}
    patch=f.ok(M1,'fix_patch',task_ids=['repair'],message='Producer helper interface')['result'];assert patch['changed_paths']==['helper.py']
    f.ok(M1,'handoff_patch',patch_id=patch['patch_id'],to_member=M2,message='Exact helper implementation')
    adopted=f.ok(M2,'integrate_patch',patch_id=patch['patch_id'])['result'];passed=f.ok(M2,'run_tests')['result'];assert passed['passed'] is True
    after_bindings={role:{k:f.world._software()['tasks'][tid][k] for k in ['task_id','revision','owner']} for role,tid in [('producer','repair'),('consumer','other')]}
    _,_,tree=f.world._bundle(M2);after={'files':copy.deepcopy(tree['files']),'version':passed['source_reference'],'test':passed,'environment_id':before['environment_id'],'selector':before['selector'],'task_bindings':after_bindings,'test_actor':M2,
        'adopted_artifact':{'patch_id':patch['patch_id'],'author':patch['author'],'source_version':patch['source_reference'],'recipient_version':adopted['source_reference']}}
    structural=structural_confirmation(contract,'repair','other','helper_interface_v1');execution=execution_confirmation(before,after,consumer_path='sample.py',artifact_paths=['helper.py'])
    assert structural['supported'] and execution['supported']
    drift=copy.deepcopy(after);drift['files']['sample.py']='value = 2\n';assert not execution_confirmation(before,drift,consumer_path='sample.py',artifact_paths=['helper.py'])['supported']
    assert not structural_confirmation({**contract,'origin':'actor_proposed'},'repair','other','helper_interface_v1')['supported']
    save(ART/'execution-witnesses.json',{'before':before,'after':after});save(ART/'receipts.json',f.receipts)
    save(ART/'summary.json',{'source':ref(Path(__file__)),'checker':ref(ROOT/'src/proworksim/software_dependency_checks_v203_2.py'),'structural':structural,'execution':execution,
        'actual_public_pytest_runs':f.test_calls,'actual_harness_calls':len(f.receipts),'world_dependency_declarations':0,'world_owner_transfers':0,
        'initial_allocation_setup':['return_task other by001','claim_task other by002'],'task_owners_unchanged_during_execution_comparison':bindings==after_bindings,
        'positive_control_is_authored_not_natural_misalignment_sample':True,'new_real_model_API':0,'no_reorganization_was_needed_for_this_control':True})
    print('Structural contract and bounded execution confirmations passed; no universal necessity or organization-benefit claim.')
if __name__=='__main__':main()
