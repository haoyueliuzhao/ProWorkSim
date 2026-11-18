import math,pytest
from proworksim.software_organization_selector_v212 import SPEC,distribution,target_distribution,fit,policy_value,leave_one_out,utility

def test_shared_fit_support_bound_and_all_candidate_value():
 f={'keep':[0,0,1,0,0],'change1':[1,1,1,.1,.1],'change2':[1,0,1,.2,0]};r={k:1/3 for k in f};old=[0.]*5;q=distribution(old,f,r)
 u={k:utility(k!='keep',4_000_000) for k in f};target=target_distribution(q,r,u)
 rows=[{'features':f,'reference':r,'target':target['q_after']},{'features':{k:[v*.7 for v in x] for k,x in f.items()},'reference':r,'target':target['q_after']}]
 result=fit(old,rows);new=distribution(result['theta'],f,r)
 assert new['keep']<q['keep'] and min(new[k]/r[k] for k in r)>=SPEC['delta']
 assert result['mean_KL']>=0 and len(leave_one_out(old,rows))==2
 out=policy_value(new,{k:{'correct_legal':k!='keep','tokens':4000000} for k in f})
 assert abs(out['utility']-(1-new['keep']-.08))<1e-10
 extreme=distribution([20,-20,0,20,0],f,r);t=target_distribution(extreme,r,u)
 assert max(t['undercoverage_novelty'].values())<=math.log(20)+1e-10
 with pytest.raises(ValueError):policy_value(new,{'keep':{'correct_legal':False,'tokens':1}})

def test_remaining_bank_keeps_authors_and_uses_real_receipt_steps():
 from proworksim.software_organization_remaining_v212 import enumerate_bank
 from proworksim.storage import json_bytes
 state={'work':{'done':{'scope':['implemented'],'owner':'member_001','reviewer':'member_002','authors':['member_001'],'children':[],'completion':None,'task_revision':1,'depends_on':[]},'remaining':{'scope':['behavior','regression'],'owner':'member_001','reviewer':'member_002','authors':[],'children':[],'completion':None,'task_revision':1,'depends_on':[]}}}
 before=json_bytes(state);bank=enumerate_bank(state,4000000)
 assert json_bytes(state)==before and len(bank['selected'])==3
 for row in bank['selected'].values():
  assert row['target']['work']['done']==state['work']['done']
  for a in row['actions']:
   if a['tool']=='accept_joint_arrangement':assert 'arguments_from_real_receipt' in a and 'arguments' not in a
