import pytest
from proworksim.software_organization_api_v211 import Ledger,AdmissionStopped

def test_global_guard_and_phase_guard_are_separate(tmp_path):
 l=Ledger(tmp_path/'cash.sqlite')
 for k in range(5):l.reserve_block(str(k),{f'{k}-{j}':5_000_000 for j in range(3)})
 with pytest.raises(AdmissionStopped,match='Global'):l.reserve_block('six',{f'6-{j}':5_000_000 for j in range(3)})
 # One completed block releases unused worst-price exposure; actual stays charged.
 for j in range(3):
  s=f'0-{j}';l.admit(s,5_000_000)
  with l.db() as c:c.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',(s,s,'settled',8_000_000_000,4_000_000,None,s))
  l.close(s)
 l.reserve_block('six',{f'6-{j}':5_000_000 for j in range(3)})
 assert l.snapshot()['worst_exposure_CNY']==624
 assert l.snapshot()['cap_CNY']==700

def test_cannot_open_old_cash_authority(tmp_path):
 import sqlite3
 p=tmp_path/'old';c=sqlite3.connect(p);c.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)');c.execute('INSERT INTO meta VALUES("cap","200000000000")');c.commit();c.close()
 with pytest.raises(ValueError):Ledger(p)
 with sqlite3.connect(p) as c:assert c.execute("SELECT * FROM meta").fetchall()==[("cap","200000000000")]
