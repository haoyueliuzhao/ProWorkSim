from pathlib import Path
import json
import pytest
from proworksim.software_benchmark_finalization_v159 import finalize_controller

class Channel:
    def __init__(self):self.closed=False;self.reads=0
    def budget(self):
        if self.closed:raise RuntimeError('budget channel is already closed')
        self.reads+=1;return {'complete_actual_tokens':23,'known_actual_tokens':23,'per_member':{},'uncertain_reserved_tokens':0}
    def close(self):self.closed=True
class Owner:
    def __init__(self,channel):self.channel=channel
    def save(self):return self.channel.budget()

def test_full_normal_finalization_reads_budget_before_close(tmp_path):
    channel=Channel();result={'status':'closed','candidate_lock':{'sha256':'a'*64}}
    finalize_controller(result,tmp_path,runtime=None,close_runtime=lambda _:None,owner=Owner(channel),transport=channel)
    saved=json.loads((tmp_path/'controller-result.json').read_text())
    assert saved['status']=='closed' and saved['ledger']['complete_actual_tokens']==23
    assert channel.closed and channel.reads==1 and saved['candidate_lock']==result['candidate_lock']
    assert saved['controller_finalization']['secondary_errors']==[]

def test_disconnected_channel_retains_original_error_and_prior_usage(tmp_path):
    channel=Channel();channel.close();primary={'type':'AccountingConflict','message':'original source capture failure'}
    result={'status':'technical_unknown','error':primary,'ledger':{'known_actual_tokens':23,'complete_actual_tokens':None}}
    finalize_controller(result,tmp_path,runtime=None,close_runtime=lambda _:None,owner=Owner(channel),transport=channel)
    saved=json.loads((tmp_path/'controller-result.json').read_text())
    assert saved['error']==primary and saved['ledger']=={'known_actual_tokens':23,'complete_actual_tokens':None}
    assert saved['final_owner_snapshot_unavailable'] is True
    assert saved['controller_finalization']['secondary_errors'][0]['step']=='owner_save'

def test_private_sdk_close_failure_does_not_skip_ledger_or_result(tmp_path):
    channel=Channel();result={'status':'technical_unknown','error':{'type':'Primary','message':'keep me'}}
    def fail(_):raise RuntimeError('SDK close failed')
    finalize_controller(result,tmp_path,runtime=object(),close_runtime=fail,owner=Owner(channel),transport=channel)
    saved=json.loads((tmp_path/'controller-result.json').read_text())
    assert saved['error']['message']=='keep me' and channel.closed and channel.reads==1
    assert saved['ledger']['known_actual_tokens']==23

def test_result_write_failure_preserves_original_evidence(tmp_path):
    result={'status':'technical_unknown','error':{'type':'Primary','message':'keep me'}}
    def fail(*_):raise OSError('injected write failure')
    with pytest.raises(OSError):finalize_controller(result,tmp_path,runtime=None,close_runtime=lambda _:None,
        owner=None,transport=None,writer=fail)
    saved=json.loads((tmp_path/'controller-result-write-failure.json').read_text())
    assert saved['result']['error']==result['error'] and saved['write_error']['type']=='OSError'
