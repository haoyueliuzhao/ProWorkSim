import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_context_probe_v177 import evaluate,covered
from proworksim.software_context_api_v175 import ReplayLedger,ReplayAPI
from proworksim.software_benchmark_candidates_v054 import write_new,reference
from proworksim.software_context_recovery_v176 import HistoryEvidenceStore


def case():
    return {'expected':{'status':'recovered','scope':'historical','facts':{'passed':False},'next_decision':'fix'},
        'archive_reference':'ctx:a','required_original_ranges':[{'message_index':4,'start':10,'end':20}],
        'equivalent_observation_sources':[{'reference':'ctx:b','message_index':4,'characters':4}]}


def test_restored_fact_requires_actual_read_and_matching_citation():
    c=case();answer={**c['expected'],'evidence':[{'reference':'ctx:a','message_index':4}]}
    assert not evaluate(c,answer,[])['passed']
    read=[{'ok':True,'result':{'reference':'ctx:a','start':10,'text':'12345'}},
          {'ok':True,'result':{'reference':'ctx:a','start':15,'text':'67890'}}]
    assert evaluate(c,answer,read)['passed']
    answer['facts']={'passed':0};assert not evaluate(c,answer,read)['passed']


def test_equivalent_original_observation_and_unknown_are_accepted():
    c=case();answer={**c['expected'],'evidence':[{'reference':'ctx:b','message_index':4}]}
    read=[{'ok':True,'result':{'reference':'ctx:b','start':0,'text':'data'}}]
    assert evaluate(c,answer,read)['passed']
    c['expected'].update(status='unknown',facts={'tests_run':None},next_decision='report_unknown')
    answer={**c['expected'],'evidence':[{'reference':'ctx:b','message_index':4}]}
    assert evaluate(c,answer,read)['passed']
    answer['facts']={'tests_run':0};assert not evaluate(c,answer,read)['passed']


def test_same_ledger_phase_does_not_change_old_policy_or_request_rows(tmp_path,monkeypatch):
    import proworksim.software_context_probe_v177 as module
    monkeypatch.setattr(module,'OLD',tmp_path)
    old=write_new(tmp_path/'plan.json',{'old':'frozen'})
    ledger=ReplayLedger(tmp_path/'api-ledger.sqlite',plan_ref=old)
    original_policy=copy.deepcopy(ledger.policy)
    phase=write_new(tmp_path/'new.json',{'cases':[{'case_id':'r00'}]})
    auth=write_new(tmp_path/'auth.json',{'cap':250})
    next_ledger=module.ProbeLedger(phase_plan=phase,authority=auth)
    assert next_ledger.policy==original_policy
    assert next_ledger.admit('v177:r00','v177-recovery-probe')=='running'
    with pytest.raises(ValueError):next_ledger.admit('unplanned','v177-recovery-probe')
    with next_ledger.transaction() as db:assert db.execute('SELECT count(*) FROM phase_authorizations_v177').fetchone()[0]==1


def test_real_probe_driver_reads_index_then_uses_recovered_evidence(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('actual_probe_entry',root/'tools/run_context_probe_v177.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.setattr(mod,'RUN',tmp_path)
    store=HistoryEvidenceStore('point','slot','member_001')
    ref=store.put_history([{'role':'tool','content':'{"passed":false}'}],4,5)
    offset=store.entries[ref]['message_offsets'][0]
    c=case();c.update(case_id='r00',kind='fixture',archive_reference=ref,required_original_ranges=[offset])
    c['store']=write_new(tmp_path/'store.json',{'point_id':'point','slot_id':'slot','member_id':'member_001','entries':store.entries})
    c['actual_initial_payload']=write_new(tmp_path/'payload.json',{'model':'deepseek-flash','thinking':{'type':'disabled'},
        'stream':False,'max_tokens':4096,'messages':[]})
    owner=mod.Probe.__new__(mod.Probe)
    owner.ledger=ReplayLedger(tmp_path/'ledger.sqlite',plan_ref=write_new(tmp_path/'plan.json',{'CPU':True}))
    class HTTP:
        def request(self,method,path,payload):
            n=len([m for m in payload['messages'] if m['role']=='tool'])
            if n<2:
                args={'reference':ref,'characters':1} if n==0 else {'reference':ref,'start':offset['start'],'characters':offset['end']-offset['start']}
                message={'role':'assistant','content':None,'tool_calls':[{'id':str(n),'type':'function','function':{
                    'name':'context_read','arguments':json.dumps(args)}}]}
            else:message={'role':'assistant','content':json.dumps({**c['expected'],'evidence':[{'reference':ref,'message_index':4}]})}
            return {'choices':[{'message':message}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120,
                'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100}}
    owner.api=ReplayAPI(owner.ledger,counter=SimpleNamespace(measure=lambda _: {'prompt_tokens':100}),api_key='unused',transport_factory=HTTP)
    result=owner.one(c)
    assert result['status']=='closed' and result['assessment']['passed']
    assert result['assessment']['index_actually_observed'] and len(result['reads'])==2
    assert result['new_world_actions']==0 and owner.ledger.snapshot()['settled_requests']==3
    assert owner.one(c)==result and owner.ledger.snapshot()['settled_requests']==3
