import copy
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import reference,write_new
from proworksim.software_context_api_v175 import (
    ReplayLedger,ReplayAPI,AdmissionBusy,CashClosed,FULL_CALL_RESERVATION,TransportFailure)


def ledger(tmp_path):
    plan=write_new(tmp_path/'plan.json',{'purpose':'CPU-only financial controls'})
    return ReplayLedger(tmp_path/'ledger.sqlite',plan_ref=plan,cap=10_000_000_000)


def payload():
    return {'model':'deepseek-flash','thinking':{'type':'disabled'},'stream':False,
        'max_tokens':32768,'messages':[{'role':'user','content':'CPU control'}]}


def body():
    return {'id':'cpu-only','model':'deepseek-flash','choices':[{'message':{'role':'assistant','content':'done'},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,
            'prompt_cache_hit_tokens':20,'prompt_cache_miss_tokens':80}}


def test_cash_admission_waits_without_cancelling_entered_job(tmp_path):
    money=ledger(tmp_path);money.admit('first','replay');money.admit('second','replay')
    with pytest.raises(AdmissionBusy):money.admit('third','replay')
    # A later cash-admission threshold reduction must not cancel an existing grant.
    money.policy['cap_nanoyuan']=0
    money.reserve('first','request','agent',0,1,payload())
    response=write_new(tmp_path/'response.json',body());money.settle('request',body(),response)
    money.finish('first','closed');money.finish('second','closed')
    assert money.snapshot()['known_actual_tokens']==110
    with pytest.raises(CashClosed):money.admit('third','replay')


def test_double_settlement_is_idempotent_but_changed_receipt_is_rejected(tmp_path):
    money=ledger(tmp_path);money.admit('first','replay')
    money.reserve('first','request','agent',0,1,payload());ref=write_new(tmp_path/'response.json',body())
    money.settle('request',body(),ref);first=money.snapshot()
    money.settle('request',body(),ref)
    assert money.snapshot()==first
    changed=body();changed['usage']['completion_tokens']=11;changed['usage']['total_tokens']=111
    with pytest.raises(ValueError,match='Conflicting'):money.settle('request',changed,ref)


def test_retry_keeps_unknown_cost_and_does_not_replay_a_settled_response(tmp_path):
    money=ledger(tmp_path);money.admit('first','replay')
    observed=[]
    class Transport:
        def request(self,*args):
            observed.append(args)
            if len(observed)==1:
                raise TransportFailure('complete_http_error_response',phase='complete_http_response',status=429)
            return body()
    client=ReplayAPI(money,counter=SimpleNamespace(measure=lambda p:{'prompt_tokens':100}),api_key='never-used',
        transport_factory=Transport,sleep=lambda _:None)
    value,rid=client.call('first',payload(),purpose='agent',step=0,folder=tmp_path/'calls')
    assert value==body() and len(observed)==2
    assert money.snapshot()['unknown_or_inflight_upper_CNY']==FULL_CALL_RESERVATION/1e9
    assert money.snapshot()['settled_requests']==1
    value,rid=client.call('first',payload(),purpose='agent',step=0,folder=tmp_path/'calls')
    assert len(observed)==2 and money.snapshot()['physical_requests']==2
