import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim.software_context_reader_v179 import SourceLabeledHistoryReader,citation_format_feedback
from proworksim.software_context_api_v175 import ReplayLedger,ReplayAPI
from proworksim.software_benchmark_candidates_v054 import write_new


def store():
    s=SourceLabeledHistoryReader('point','slot','member_001')
    ms=[{'role':'assistant','tool_calls':[{'id':'call-a','function':{'name':'run_tests','arguments':'{}'}}]},
        {'role':'tool','tool_call_id':'call-a','content':json.dumps({'result':{'version':'report-v1',
            'source_reference':{'object_id':'repo','version_id':'v8'},'files_sha256':'a'*64}})}]
    ref=s.put_history(ms,4,6);return s,ref


def test_pairing_source_headers_and_exact_raw_text():
    s,ref=store();out=s.read({'reference':ref},point_id='point',slot_id='slot',member_id='member_001')
    assert out['text']==s.entries[ref]['text']
    assert out['message_offsets'][1]['paired_action_message_index']==4
    header=out['citable_messages'][1]['source_identity']
    assert header['workspace_version_id']=='v8' and header['report_schema_version']=='report-v1'
    part=s.read({'reference':ref,'characters':1},point_id='point',slot_id='slot',member_id='member_001')
    assert not part['citable_messages']
    with pytest.raises(PermissionError):s.read({'reference':ref},point_id='point',slot_id='slot',member_id='member_002')


def test_format_feedback_has_no_fact_or_verdict_oracle():
    s,ref=store();out=s.read({'reference':ref},point_id='point',slot_id='slot',member_id='member_001')
    answer={'facts':{'arbitrary':'wrong'},'evidence':[{'reference':ref+' explanation','message_index':5}]}
    feedback=citation_format_feedback(answer,[{'ok':True,'result':out}])
    assert feedback and not feedback['facts_or_decisions_graded'] and not feedback['expected_answer_revealed']
    assert 'wrong' not in json.dumps(feedback)
    answer['evidence']=[{'reference':ref,'message_index':5}]
    assert citation_format_feedback(answer,[{'ok':True,'result':out}]) is None


def test_actual_driver_budgeted_format_recovery(tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('actual_v179_probe',root/'tools/run_context_probe_v179.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);monkeypatch.setattr(mod,'RUN',tmp_path)
    s,ref=store();off=s.entries[ref]['message_offsets'][1]
    c={'case_id':'r00','kind':'fixture','expected':{'status':'recovered','scope':'historical',
        'facts':{'version_id':'v8'},'decision_checks':{'validates_current':False}},
       'fact_evidence_ranges':{'version_id':[{'reference':ref,'message_index':5,'start':off['start'],'end':off['end']}]},
       'citation_inventory':{ref:{'kind':'original_closed_private_history','message_offsets':s.entries[ref]['message_offsets']}}}
    c['store']=write_new(tmp_path/'store.json',{'point_id':s.point_id,'slot_id':s.slot_id,'member_id':s.member_id,'entries':s.entries})
    c['actual_initial_payload']=write_new(tmp_path/'payload.json',{'model':'deepseek-flash','thinking':{'type':'disabled'},
        'stream':False,'max_tokens':4096,'messages':[]})
    owner=mod.Probe.__new__(mod.Probe);owner.ledger=ReplayLedger(tmp_path/'ledger.sqlite',plan_ref=write_new(tmp_path/'plan.json',{'CPU':True}))
    sent=[]
    class HTTP:
        def request(self,*args):
            payload=args[-1];sent.append(payload)
            if len(sent)==1:
                msg={'role':'assistant','content':None,'tool_calls':[{'id':'read1','type':'function',
                    'function':{'name':'context_read','arguments':json.dumps({'reference':ref})}}]}
            else:
                suffix=' commentary' if len(sent)==2 else ''
                msg={'role':'assistant','content':json.dumps({**c['expected'],'evidence':[{'reference':ref+suffix,'message_index':5}]})}
            return {'choices':[{'message':msg}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120,
                'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':100}}
    owner.api=ReplayAPI(owner.ledger,counter=SimpleNamespace(measure=lambda _: {'prompt_tokens':100}),
        api_key='unused',transport_factory=HTTP)
    result=owner.one(c)
    assert result['assessment']['passed'] and len(result['format_feedback'])==1 and len(sent)==3
    assert owner.ledger.snapshot()['known_actual_tokens']==360 and result['new_world_actions']==0
