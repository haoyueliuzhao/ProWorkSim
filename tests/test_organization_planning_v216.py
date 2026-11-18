import copy,pytest
from proworksim.software_organization_generator_v216 import validate,target_id
from proworksim.software_organization_selector_v216 import SPEC,distribution,target_distribution,fit
from proworksim.software_organization_api_v216 import Ledger,AdmissionStopped

def state():
 return {'work':{k:{'scope':[k],'children':[],'authors':['member_001'] if k=='done' else [],'owner':'member_001','reviewer':'member_002','completion':None,'task_revision':1,'depends_on':[],'mode':'implementation'} for k in ('done','left','other')},'collaboration':[[k,a,b] for k in ('done','left','other') for a,b in [('member_001','member_002'),('member_002','member_001')]]}
def proposal(tid='left'):
 return {'reason':'Move remaining work to the other actual member','operations':[{'op':'JOINT_ASSIGN','actor':'member_001','arguments':{'task_id':tid,'to_member':'member_002','reviewer':'member_001','mode':'implementation'}}]}
def test_real_state_proposal_validation_preserves_source_and_no_fake_consent():
 s=state();before=copy.deepcopy(s);p=validate(s,proposal());assert s==before and target_id(p['target'])!=target_id(s)
 assert p['actions'][-1]['tool']=='accept_joint_arrangement' and 'arguments_from_real_receipt' in p['actions'][-1]
 with pytest.raises(ValueError):validate(s,proposal('done'))
 bad=proposal();bad['operations'][0]['op']='CHANGE_EXECUTION_ORDER'
 with pytest.raises(ValueError,match='Unsupported'):validate(s,bad)

def test_cn_reference_support_and_n_only_null_initial_diagnostic():
 f={'KEEP':[0,0,.5,0,0,0,0],'A':[1,0,.5,.5,.2,.1,0],'B':[.5,1,.8,.5,.3,.2,.8]};r={k:1/3 for k in f};q=distribution(SPEC['initial_theta'],f,r);u={'KEEP':-.1,'A':.95,'B':-.08}
 n=target_distribution(q,r,u,use_contribution=False);assert all(abs(n['q_after'][k]-r[k])<1e-12 for k in r)
 cn=target_distribution(q,r,u);fit_result=fit(SPEC['initial_theta'],[{'features':f,'reference':r,'target':cn['q_after']}]);after=distribution(fit_result['theta'],f,r)
 assert after['A']>q['A'] and all(after[k]>=.05*r[k] for k in r)

def test_complete_phase_blocks_and_shared_prepare_cost(tmp_path):
 l=Ledger(tmp_path/'ledger')
 for i in range(3):l.reserve_block('prefix'+str(i),{f'v216:t{i}:PREFIX':2_000_000},phase='prepare')
 for i in range(3):l.reserve_block('gen'+str(i),{f'v216:t{i}:GENERATOR':200_000},phase='prepare')
 for i in range(3):l.reserve_block('pair'+str(i),{f'v216:t{i}:{z}':3_000_000 for z in ('KEEP','ADAPT')})
 with pytest.raises(AdmissionStopped):l.reserve_block('extra',{'v216:extra:KEEP':3_000_000,'v216:extra:ADAPT':3_000_000})
 assert l.snapshot()['new_phase_estimates']['prepare']['estimated_exposure_CNY']==7.5
 assert l.snapshot()['cap_CNY']==700
