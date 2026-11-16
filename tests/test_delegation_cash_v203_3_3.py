import pytest
from proworksim.software_delegation_api_v203_3_3 import Ledger,AdmissionStopped,PrefixComplete

def response(ident,inp=1000,out=100):
 return {'id':ident,'model':'deepseek-flash','usage':{'prompt_tokens':inp,'completion_tokens':out,'total_tokens':inp+out,'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':inp}}

def test_whole_slot_holds_protect_started_work(tmp_path):
 l=Ledger(tmp_path/'l.sqlite');l.admit('a',5_000_000);l.admit('b',5_000_000)
 with pytest.raises(AdmissionStopped):l.admit('c',1)
 l.reserve('a','req',2000);l.settle('req',response('provider'));l.close('a');l.admit('c',100_000)
 assert l.snapshot()['actual_tokens']==1100

def test_unknown_no_replay_no_cash_release(tmp_path):
 l=Ledger(tmp_path/'l.sqlite');l.admit('a',5_000_000);l.reserve('a','r',2000);l.close('a');l.admit('b',5_000_000)
 with pytest.raises(AdmissionStopped):l.admit('c',1)
 assert l.snapshot()['slots'][0]['status']=='uncertain'

def test_prefix_ceiling_and_no_duplicate_start(tmp_path):
 l=Ledger(tmp_path/'l.sqlite');l.admit('p',500_000)
 with pytest.raises(PrefixComplete):l.reserve('p','x',500001)
 with pytest.raises(ValueError):l.admit('p',500_000)
 assert l.snapshot()['requests']==[]

def test_complete_http_error_releases_only_request(tmp_path):
 l=Ledger(tmp_path/'l.sqlite');l.admit('p',500_000);l.reserve('p','x',1000);l.http_error('x');l.reserve('p','y',2000);l.settle('y',response('id'));l.close('p')
 assert l.snapshot()['peak_cost_upper_CNY']==.0028
