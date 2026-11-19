import copy
import pytest
from proworksim.software_organization_opportunity_v218 import distinct_structure,admit_bank
from proworksim.software_organization_api_v218 import Ledger

def test_setup_is_not_structural_but_real_transfer_is():
 state={'graph':{'work':{'a':{'owner':'member_001','mode':'implementation','scope':['x'],'children':[],'depends_on':[]}}}}
 c={'target':copy.deepcopy(state['graph'])};c['target']['work']['a']['reviewer']='member_002'
 assert not distinct_structure(state,c)
 c['target']['work']['a']['owner']='member_002';assert distinct_structure(state,c)
 bank={'candidates':{'KEEP':{'target':state['graph']},'C1':c},'remaining_branch_token_limit':2_500_000}
 assert admit_bank(bank,state)['qualified'];bank['remaining_branch_token_limit']=1_000_000;assert not admit_bank(bank,state)['qualified']
def test_shared_cap_and_no_replay(tmp_path):
 ledger=Ledger(tmp_path/'ledger.sqlite');ledger.reserve_block('panel',{'v218:task-00:KEEP':1000,'v218:task-00:C1':1000});ledger.admit('v218:task-00:KEEP',1000)
 with pytest.raises(ValueError):ledger.admit('v218:task-00:KEEP',1000)
 with pytest.raises(ValueError):ledger.reserve_block('again',{'v218:task-00:C1':1000})
 assert ledger.snapshot()['cap_CNY']==1100
