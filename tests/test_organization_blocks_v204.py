import pytest
from proworksim.software_organization_api_v204 import Ledger,AdmissionStopped

def test_complete_block_and_unrelated_old_funds(tmp_path):
 l=Ledger(tmp_path/'new.sqlite');l.reserve_block('d1',{'a':5000000,'b':5000000,'c':5000000})
 with pytest.raises(AdmissionStopped):l.reserve_block('d2',{'d':5000000,'e':5000000,'f':5000000})
 # Failed block admission is atomic, no partially allocated identities.
 with l.db() as c:assert c.execute('select count(*) from block_slots').fetchone()[0]==3
 for s in ('a','b','c'):l.admit(s,5000000)
 with pytest.raises(AdmissionStopped):l.admit('unplanned',5000000)
 for s in ('a','b','c'):l.close(s)
 l.reserve_block('d2',{'d':5000000,'e':5000000,'f':5000000})
 assert l.snapshot()['cap_CNY']==200
