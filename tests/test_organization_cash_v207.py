import pytest
from proworksim.software_organization_api_v207 import Ledger,AdmissionStopped

def test_whole_blocks_fit_without_double_counting_active_cost(tmp_path):
 l=Ledger(tmp_path/'l');l.reserve_block('a',{'a':5000000,'b':5000000,'c':5000000})
 l.admit('a',5000000)
 with l.db() as c:
  c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',('r','a','settled',8_000_000_000,4000000,None,'p'))
  assert l.exposure(c)==31_500_000_000
 l.close('a')
 with l.db() as c:assert l.exposure(c)==29_000_000_000
 for i in range(5):l.reserve_block(str(i),{f'{i}-{j}':5000000 for j in range(3)})
 with pytest.raises(AdmissionStopped):l.reserve_block('no',{'x':5000000,'y':5000000,'z':5000000})
 with l.db() as c:assert c.execute('select count(*) from block_slots where block_id="no"').fetchone()[0]==0

def test_started_block_retains_next_member_and_unknown_reservations(tmp_path):
 l=Ledger(tmp_path/'l');l.reserve_block('pair',{'a':5000000,'b':5000000});l.admit('a',5000000)
 with l.db() as c:c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',('r','a','settled',201_000_000_000,1000,None,'p'))
 l.admit('b',5000000) # protected previously admitted complete block
 l.reserve('b','uncertain',1000);l.close('b')
 with pytest.raises(AdmissionStopped):l.reserve_block('new',{'new':5000000})
 with l.db() as c:assert l.exposure(c)==211_500_000_000
