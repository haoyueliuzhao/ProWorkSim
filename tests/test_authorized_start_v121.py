"""Two bounded mocks for the authorized waiter; no real process limits or launch."""
from __future__ import annotations

import importlib.util
import resource
import socket
import subprocess

import pytest

from proworksim import software_benchmark_scope_v121 as scope
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_prior_completion_v121 import PriorStageIncomplete


@pytest.fixture
def watcher(tmp_path, monkeypatch):
    def deny(*_a,**_k):
        raise AssertionError('No actual network, subprocess, service or API action')
    for name in ('connect','bind','sendto'):
        monkeypatch.setattr(socket.socket,name,deny)
    monkeypatch.setattr(socket,'getaddrinfo',deny)
    monkeypatch.setattr(subprocess,'Popen',deny)
    monkeypatch.syspath_prepend(str(scope.ROOT/'tools'))
    spec=importlib.util.spec_from_file_location('authorized_start_v121_CPU',scope.ROOT/'tools/start_authorized_recovery_v121.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    batch=tmp_path/'batch'
    batch.mkdir()
    proposal=write_new(tmp_path/'user-proposal.json',{'CPU_fixture_only':True})
    grant=write_new(tmp_path/'grant.json',{'status':'approved','explicit_user_reply':'授权27题独立恢复','proposal':proposal})
    for name,value in {'BATCH_ROOT':batch,'USER_PROPOSAL_FILE':tmp_path/'user-proposal.json',
        'USER_GRANT_FILE':tmp_path/'grant.json','AUTH_FILE':batch/'authorization.json',
        'BUDGET_BASELINE_FILE':batch/'cash-before.json'}.items():
        monkeypatch.setattr(scope,name,value)
    for name,filename in [('STATUS','wait.json'),('INTENT','intent.json'),('RESULT','result.json')]:
        monkeypatch.setattr(module,name,batch/filename)
    limits=[]
    monkeypatch.setattr(module.resource,'setrlimit',lambda key,value:limits.append((key,value)))
    monkeypatch.setattr(module.os,'sched_getaffinity',lambda _:{3,4})
    monkeypatch.setattr(module.os,'sched_setaffinity',lambda *_:None)
    monkeypatch.setattr(module.os,'nice',lambda _:0)
    monkeypatch.setattr(module.time,'time',lambda:123456)
    return module,limits,grant


def test_unready_waiter_never_seals_authorizes_or_launches(watcher,monkeypatch):
    module,limits,_=watcher
    def pending():
        raise PriorStageIncomplete('CPU fixture prior stage still running')
    monkeypatch.setattr(module,'inspect_prior_completion',pending)
    def forbidden(*_a,**_k):
        raise AssertionError('Unready prior stage cannot advance to sealing or launch')
    for name in ('service_inactive','prepare_prior_completion','budget_status','seal','launch'):
        monkeypatch.setattr(module,name,forbidden)
    clock=iter([0,2])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(module.time,'sleep',forbidden)
    with pytest.raises(TimeoutError):
        module.run(1)
    assert not scope.AUTH_FILE.exists() and not scope.BUDGET_BASELINE_FILE.exists()
    assert scope.load(reference(module.RESULT))['status']=='review_required'
    assert scope.load(reference(module.RESULT))['automatic_retry'] is False
    assert (resource.RLIMIT_AS,(16*1024**3,16*1024**3)) in limits


def test_ready_waiter_freezes_cash_and_existing_grant_before_exactly_one_launch(watcher,monkeypatch,tmp_path):
    module,limits,grant=watcher
    order=[]
    monkeypatch.setattr(module.time,'monotonic',lambda:0)
    monkeypatch.setattr(module,'inspect_prior_completion',lambda:order.append('inspect'))
    monkeypatch.setattr(module,'service_inactive',lambda:order.append('inactive') or True)
    proof=write_new(tmp_path/'completed-proof.json',{'CPU_fixture_only':True,'passed':True})
    monkeypatch.setattr(module,'prepare_prior_completion',lambda:order.append('proof') or proof)
    monkeypatch.setattr(module,'budget_status',lambda:order.append('budget') or {'state':'ready','inflight_count':0})
    original_retain=scope.retain
    def retain(path,value):
        order.append('cash')
        assert value['prior_completion']==proof and value['additional_cash']==0
        return original_retain(path,value)
    monkeypatch.setattr(scope,'retain',retain)
    proposal=write_new(tmp_path/'prepared-proposal.json',{'status':'prepared','runtime_authorized':False,
        'API_cash_cap_CNY':'350.00','new_generation_attempts':27,'user_grant':grant})
    def seal():
        order.append('seal')
        assert (resource.RLIMIT_AS,(16*1024**3,16*1024**3)) in limits
        assert scope.BUDGET_BASELINE_FILE.is_file()
        return {'proposal':proposal}
    monkeypatch.setattr(module,'seal',seal)
    original_write=module.write_new
    def write(path,value):
        if path==scope.AUTH_FILE:
            order.append('authorization')
            assert value['status']=='approved' and value['runtime_authorized'] is True
            assert value['explicit_user_reply']=='授权27题独立恢复'
            assert value['proposal']==proposal and value['user_grant']==grant
            assert value['API_cash_cap_CNY']=='350.00' and value['new_generation_attempts']==27
        return original_write(path,value)
    monkeypatch.setattr(module,'write_new',write)
    def launch():
        order.append('launch')
        assert scope.AUTH_FILE.is_file()
        return {'CPU_fixture_only':True}
    monkeypatch.setattr(module,'launch',launch)
    result=module.run(1)
    assert result['status']=='launched'
    assert order==['inspect','inactive','proof','budget','cash','seal','authorization','launch']
    with pytest.raises(PermissionError,match='repeat'):
        module.run(1)
    assert order.count('launch')==1
