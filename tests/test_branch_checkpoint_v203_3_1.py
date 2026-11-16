import importlib.util,json
from pathlib import Path
import pytest
from proworksim.software_branch_checkpoint_v203_3_1 import capture,restore,require_live_resume

def test_control_state_clones_private_information_budget_and_rejects_tamper(tmp_path):
    root=Path(__file__).resolve().parents[1]
    s=importlib.util.spec_from_file_location('fixture',root/'tests/test_role_baseline_world_v141.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    prepared,_,_,_=m.prepare(tmp_path/'case','REVIEW2')
    histories={'member_001':['private-A'],'member_002':['private-B']}
    cp=tmp_path/'checkpoint';capture(prepared,cp,histories=histories,budget={'remaining_tokens':123},schedule={'next':'member_001'})
    left,lstate,lid=restore(prepared,cp,tmp_path/'left')
    right,rstate,rid=restore(prepared,cp,tmp_path/'right')
    assert lid==rid and lstate==rstate
    assert lstate['histories']==histories and lstate['budget']['remaining_tokens']==123
    lstate['histories']['member_001'].append('only-left')
    assert rstate['histories']['member_001']==['private-A']
    assert left.world.store.root!=right.world.store.root
    with pytest.raises(ValueError):require_live_resume(lstate)
    (cp/'continuation.json').write_text('{}')
    with pytest.raises(ValueError):restore(prepared,cp,tmp_path/'tampered')

def test_business_refusal_does_not_call_actor_or_poison_transport(tmp_path):
    root=Path(__file__).resolve().parents[1]
    s=importlib.util.spec_from_file_location('fixture_refusal',root/'tests/test_role_baseline_world_v141.py')
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    prepared,_,call,test_calls=m.prepare(tmp_path/'case','REVIEW2')
    bad=call('member_001','run_tests',selection={'kind':'pytest','targets':['../test_sample.py']})
    assert not bad['ok'] and bad['error']['rejection']['code']=='public_test_selection_invalid'
    refusal=call('member_001','create_file',path='sample.py',text='already exists')
    assert not refusal['ok'] and not test_calls
    assert call('member_001','read_file',path='sample.py')['ok']
