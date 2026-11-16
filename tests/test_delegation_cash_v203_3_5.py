import pytest
from proworksim.software_delegation_api_v203_3_5 import Ledger,exposure,AdmissionStopped

def test_exposure_counts_actual_once_and_releases_unused(tmp_path):
 l=Ledger(tmp_path/'ledger');l.admit('a',5000000)
 with l.db() as c:
  c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',('r','a','settled',8_500_000_000,4_800_000,None,'provider'))
  assert exposure(c)==9_500_000_000
 l.close('a')
 with l.db() as c:assert exposure(c)==8_500_000_000
 l.admit('b',5000000)
 with pytest.raises(ValueError):l.admit('b',5000000)

def test_started_not_cut_off_when_estimate_exceeded(tmp_path):
 l=Ledger(tmp_path/'ledger');l.admit('a',5000000)
 with l.db() as c:c.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?)',('r','a','settled',81_000_000_000,1000,None,'provider'))
 # synthetic cost overrun: new admission stops but the active token budget remains usable
 with pytest.raises(AdmissionStopped):l.admit('b',5000000)
 l.reserve('a','next',100)
 with l.db() as c:assert exposure(c)==81_000_800_000
 assert l.snapshot()['over_nominal_CNY']==1

def test_unknown_request_retains_exposure(tmp_path):
 l=Ledger(tmp_path/'ledger');l.admit('a',5000000);l.reserve('a','r',1000);l.close('a')
 with l.db() as c:assert exposure(c)==9_500_000_000
