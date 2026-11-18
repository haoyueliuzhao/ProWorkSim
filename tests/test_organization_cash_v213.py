import pytest
from proworksim.software_organization_api_v212 import Ledger as Old
from proworksim.software_organization_api_v213 import Ledger,AdmissionStopped

def test_new_complete_pairs_preserve_cash_and_old_phase(tmp_path):
 p=tmp_path/'cash';old=Old(p);old.reserve_block('old',{'v212:prior':5_000_000});old.admit('v212:prior',5_000_000)
 with old.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',('old','v212:prior','settled',8_000_000_000,4_000_000,None,'old'))
 old.close('v212:prior');new=Ledger(p)
 for i in range(3):new.reserve_block(str(i),{f'v213:{i}:{z}':5_000_000 for z in ('SINGLE','COMBO')})
 with pytest.raises(AdmissionStopped):new.reserve_block('extra',{'v213:extra:a':5_000_000,'v213:extra:b':5_000_000})
 with new.db() as c:
  assert c.execute('SELECT count(*) FROM v212_phase_slots').fetchone()[0]==1
  assert c.execute('SELECT count(*) FROM v213_phase_slots').fetchone()[0]==6
 assert new.snapshot()['worst_exposure_CNY']==248 and new.snapshot()['new_phase_estimates']['A2']['estimated_exposure_CNY']==63
