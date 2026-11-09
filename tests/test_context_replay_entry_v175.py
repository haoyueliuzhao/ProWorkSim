"""Exercise the actual replay driver through scripted HTTP and bounded recall."""
import importlib.util
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_candidates_v054 import write_new
from proworksim.software_context_api_v175 import ReplayLedger,ReplayAPI
from proworksim.software_context_compression_v175 import EvidenceStore,apply


@pytest.mark.parametrize('method',['M1','M3'])
def test_real_replay_entry_summary_recall_settlement_and_no_world_action(tmp_path,monkeypatch,method):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('cpu_actual_replay_entry',root/'tools/run_context_replay_v175.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'RUN',tmp_path)
    messages=[{'role':'system','content':'Frozen permissions'},{'role':'user','content':'Task'}]
    for i in range(12):
        messages.extend([{'role':'assistant','content':None,'tool_calls':[{'id':'c'+str(i),'type':'function',
            'function':{'name':'read_file','arguments':'{}'}}]},
            {'role':'tool','tool_call_id':'c'+str(i),'name':'read_file','content':'original code\n'*300}])
    messages.append({'role':'user','content':'Latest observation'})
    raw={'model':'deepseek-flash','thinking':{'type':'disabled'},'stream':False,'max_tokens':32768,
        'temperature':1,'top_p':1,'messages':messages,'tools':[{'type':'function','function':{'name':'read_file',
            'parameters':{'type':'object','properties':{'path':{'type':'string'}}}}}]}
    store=EvidenceStore('p0','slot','member_001');payload,measurement=apply(raw,method,store,count=len)
    ref=measurement['replaced'][0]['reference']
    payload_ref=write_new(tmp_path/'payload.json',payload)
    evidence_ref=write_new(tmp_path/'evidence.json',{'point_id':'p0','slot_id':'slot','member_id':'member_001','entries':store.entries})
    plan_ref=write_new(tmp_path/'plan.json',{'CPU_only':True})
    owner=module.Replay.__new__(module.Replay)
    owner.points={'p0':{'point_id':'p0','slot_id':'slot','member_id':'member_001','instance_id':'fixture','partition':'development'}}
    owner.inputs={('p0',method):{'payload':payload_ref,'evidence_store':evidence_ref,'summary_prefix_available':method=='M3'}}
    owner.count=len;owner.lock=threading.Lock();owner.finished={};owner.started=time.time()
    owner.ledger=ReplayLedger(tmp_path/'ledger.sqlite',plan_ref=plan_ref)
    calls=[]
    class Script:
        def request(self,method,path,value):
            calls.append(value)
            if not value.get('tools'):
                message={'role':'assistant','content':'Earlier exact observations remain available from private context references.'}
            else:
                invoked=sum(bool(c.get('tools')) for c in calls)
                name='context_read' if invoked==1 else 'read_file'
                arguments={'reference':ref} if invoked==1 else {'path':'sample.py'}
                message={'role':'assistant','content':None,'tool_calls':[{'id':'returned-'+str(invoked),
                    'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]}
            return {'id':'cpu-response-'+str(len(calls)),'model':'deepseek-flash',
                'choices':[{'finish_reason':'stop','message':message}],
                'usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,
                    'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100}}
    owner.api=ReplayAPI(owner.ledger,counter=SimpleNamespace(measure=lambda _: {'prompt_tokens':100}),
        api_key='never-used',transport_factory=Script,sleep=lambda _:None)
    result=owner.one('p0',method)
    assert result['status']=='closed' and result['final_action']['name']=='read_file'
    assert len(result['recalls'])==1 and result['recalls'][0]['feedback']['result']['text']=='original code\n'*300
    assert result['world_actions_executed']==0
    assert owner.ledger.snapshot()['settled_requests']==(3 if method=='M3' else 2)
    if method=='M3':assert result['summary']['adopted']
    before=len(calls);assert owner.one('p0',method)==result;assert len(calls)==before
