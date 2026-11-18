import copy,pytest
from test_organization_planning_v216 import state
from proworksim.software_organization_generator_v216_1 import compile_target
from proworksim.software_organization_api_v216 import Ledger as Old
from proworksim.software_organization_api_v216_1 import Ledger

def test_target_compiler_handles_real_actor_changes_and_incomplete_setup():
 s=state();s['work']['other']['reviewer']=None;s['collaboration']=[e for e in s['collaboration'] if e[0]!='other'];before=copy.deepcopy(s)
 p={'reason':'Redistribute unfinished work','remaining_work':[{'source_task_id':'left','parts':[{'scope':['left'],'owner':'member_002','mode':'implementation'}]},{'source_task_id':'other','parts':[{'scope':['other'],'owner':'member_001','mode':'implementation'}]}],'dependencies':[{'task_id':'left','depends_on':'done','operation':'add'}]}
 result=compile_target(s,p);assert s==before
 dep=next(a for a in result['actions'] if a['tool']=='change_dependency');assert dep['actor']=='member_002'
 assert any(a['tool']=='assign_verification' and a['arguments']['task_id']=='other' for a in result['actions'])
 assert any(a['tool']=='accept_joint_arrangement' for a in result['actions'])
 bad=copy.deepcopy(p);bad['remaining_work'][0]['parts']*=2
 with pytest.raises(ValueError):compile_target(s,bad)

def test_combined_line_retains_initial_failure_cost(tmp_path):
 p=tmp_path/'cash';old=Old(p);old.reserve_block('old',{'v216:task-00:PREFIX':2000000},phase='prepare');old.admit('v216:task-00:PREFIX',2000000)
 with old.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',('old','v216:task-00:PREFIX','settled',3_000_000_000,1900000,None,'old'))
 old.close('v216:task-00:PREFIX');new=Ledger(p);new.reserve_block('repair',{'v216:r2-task-00:KEEP':3000000,'v216:r2-task-00:ADAPT':3000000})
 s=new.snapshot();assert s['cap_CNY']==700 and s['new_phase_estimates']['A_and_prepare']['estimated_exposure_CNY']==24
