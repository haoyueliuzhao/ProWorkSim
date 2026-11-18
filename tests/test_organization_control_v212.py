import pytest
from proworksim.software_organization_api_v211 import Ledger as Old
from proworksim.software_organization_api_v212 import Ledger,AdmissionStopped
from proworksim.software_organization_capacity_v212 import Capacity

def test_phase_cash_keeps_old_cost_and_complete_block(tmp_path):
 p=tmp_path/'cash';old=Old(p);old.reserve_block('old',{'v211:old':5_000_000});old.admit('v211:old',5_000_000)
 with old.db() as c:c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',('old','v211:old','settled',8_000_000_000,4_000_000,None,'old'))
 old.close('v211:old');l=Ledger(p)
 for i in range(2):l.reserve_block(str(i),{f'v212:{i}:{z}':5_000_000 for z in ('SINGLE','COMBO')})
 with pytest.raises(AdmissionStopped,match='phase'):l.reserve_block('third',{f'v212:2:{z}':5_000_000 for z in ('SINGLE','COMBO')})
 for z in ('SINGLE','COMBO'):
  slot=f'v212:0:{z}';l.admit(slot,5_000_000)
  with l.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(slot,slot,'settled',5_000_000_000,3_000_000,None,slot))
  l.close(slot)
 l.reserve_block('third',{f'v212:2:{z}':5_000_000 for z in ('SINGLE','COMBO')})
 s=l.snapshot();assert s['worst_exposure_CNY']==178 and s['new_phase_estimates']['A']['estimated_exposure_CNY']==52
 assert s['peak_cost_upper_CNY']==18

def test_cleanup_release_idempotent_and_owned():
 c=Capacity(lambda:None);c.leases['own']={'count':1};assert c.release('own');assert not c.release('own');assert not c.release('unknown')
