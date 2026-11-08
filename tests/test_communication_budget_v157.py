"""CPU-only checks of the real physical ledger and live native budget seam."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_deepseek_api_v157 as api
from proworksim import software_benchmark_host_api_v157 as host
from proworksim.software_benchmark_candidates_v054 import reference
from proworksim.software_benchmark_budget_v157 import (
    encode_annotations, decode_annotations, bind_owner_budget, bind_runtime_budget)
from proworksim.software_input_provenance_v156 import SourceFragment, AnnotatedText, TextSegment, build_request
from proworksim.software_benchmark_deepseek_adapter_v105 import EpisodeLedger
from proworksim.software_role_baseline_runtime_v141 import TeamLedger
from proworksim.software_benchmark_history_budget_v110 import AlignedManagedTeamBudget
from proworksim.storage import digest, json_bytes


def setup(tmp_path, concurrency=2):
    rows=[{'slot_id':'v157:task:'+g,'instance_id':'test__repo-1','condition':g,'condition_id':g,
           'group_id':g,'organization_id':'REVIEW2','fixed_members':['member_001','member_002'],
           'budget_tokens':5_000_000} for g in api.GROUP_IDS]
    panel=tmp_path/'panel.json';panel.write_text(json.dumps({'rows':rows}))
    ledger=tmp_path/'new-pilot.sqlite'
    authority=tmp_path/'authority.json';authority.write_text(json.dumps({
        'version':api.AUTHORITY_VERSION,'ledger_path':str(ledger.resolve()),
        'cap_nanoyuan':500_000_000_000,'panel_sha256':reference(panel)['sha256'],'approved':True}))
    views={g:api.group_api(g,ledger,max_concurrency=concurrency,panel_ref=reference(panel),
        cash_authority_ref=reference(authority)) for g in api.GROUP_IDS}
    return views,rows


def wire(row,purpose='agent'):
    return {'model':'deepseek-flash','messages':[{'role':'user','content':'Fix the source-bound issue.'}],
        'max_tokens':512 if purpose=='compressor' else 100,'thinking':{'type':'disabled'},
        'temperature':.2 if purpose=='compressor' else 1.,'top_p':1.,'stream':False,
        'user_id':api.old.slot_user_id(row['slot_id']+':member_001',row['condition_id'])}


def body(identity):
    return {'id':identity,'model':'deepseek-flash','system_fingerprint':'synthetic',
        'choices':[{'message':{'role':'assistant','content':'done'},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13,
                 'prompt_cache_hit_tokens':4,'prompt_cache_miss_tokens':6}}


class Script:
    def __init__(self,items):self.items=list(items);self.calls=[]
    def request(self,*args):
        self.calls.append(args)
        item=self.items.pop(0)
        if isinstance(item,BaseException):raise item
        return item
    def abort(self):pass


def args(row,purpose='agent',index=1):
    middle=':compressor:' if purpose=='compressor' else ':'
    return {'request_id':row['slot_id']+':member_001'+middle+f'{index:04d}',
        'slot_id':row['slot_id'],'condition':row['condition_id'],'usage_id':purpose,
        'prompt_upper_bound':100,'member_id':'member_001'}


def annotation(payload):
    source=SourceFragment('Base/Template','template','template','system')
    def walk(x):
        if isinstance(x,str):return AnnotatedText((TextSegment(x,source),))
        if isinstance(x,list):return [walk(v) for v in x]
        if isinstance(x,dict):return {k:walk(v) for k,v in x.items()}
        return x
    return {'payload':walk(payload),'template_source':source}


def test_three_purposes_share_one_team_and_one_cash_account(tmp_path):
    views,rows=setup(tmp_path)
    row=rows[1]
    script=Script([body('agent'),body('condenser'),body('compressor')])
    client=views['C1'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script)
    for i,purpose in enumerate(('agent','condenser','compressor'),1):
        client.complete(wire(row,purpose),**args(row,purpose,i))
    state=client.ledger.team_snapshot(row['slot_id'])
    assert state['known_actual_tokens']==39 and state['attempts']==3 and state['decisions']==1
    assert set(state['per_usage_id'])=={'agent','condenser','compressor'}
    assert all(views[g].BudgetLedger().snapshot()['known_actual_tokens']==39 for g in api.GROUP_IDS)
    assert views['C0'].CAP_NANOYUAN==500_000_000_000
    assert client.ledger.snapshot()['settled_nanoyuan']==3*(4*40+6*2000+3*8000)
    with client.ledger.transaction() as db:
        db.execute("UPDATE requests SET usage_json=? WHERE request_id=?",(json.dumps({
            'prompt_tokens':4_999_000,'completion_tokens':500,'total_tokens':4_999_500}),
            args(row,'agent',1)['request_id']+':http-1'))
    with pytest.raises(api.PreDispatchBudgetStopped,match='shared_team'):
        client.complete(wire(row,'compressor'),**args(row,'compressor',4))
    assert len(script.calls)==3
    with pytest.raises(ValueError):
        views['C0'].BudgetLedger().team_snapshot(row['slot_id'])


def test_real_host_retries_capture_every_physical_attempt_and_never_replay_paid_body(tmp_path,monkeypatch):
    views,rows=setup(tmp_path)
    runtime=host.runtime_for(apis=views,schemas={g:{m:[] for m in rows[0]['fixed_members']} for g in api.GROUP_IDS},
        counter=lambda w:{'prompt_tokens':100,'request_sha256':digest(json_bytes(w))},
        authorize=lambda *a,**kw:None,api_key='not-used',max_concurrency=2)
    row=rows[1]
    failure=api.TransportFailure('complete_http_error_response',phase='complete_http_response',status=503)
    script=Script([failure,body('successful-compression')])
    client=views['C1'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script,
        http_slots=runtime.http_slots,sleep=lambda _:None,jitter=lambda:0)
    runtime.clients['C1'].fork_for_episode=lambda:client
    route=host.HostTeamTransport(runtime,row,tmp_path/'host')
    request=wire(row,'compressor')
    envelope={**args(row,'compressor'), 'wire':request,'team_slot_id':row['slot_id'],
              'source_annotations':encode_annotations(annotation(request))}
    result=route.post('/chat/completions',envelope)
    assert result['id']=='successful-compression' and len(script.calls)==2
    receipts=client.provenance_capture.receipts()
    assert len(receipts)==2 and all(r['request_capture'] and r['final_receipt_ref'] for r in receipts)
    state=route.post('/team-budget',{'team_slot_id':row['slot_id']})
    assert state['known_actual_tokens']==13 and state['uncertain_reserved_tokens']==612
    assert state['attempts']==2 and state['decisions']==0
    # The paid response may not be replayed even after an observer/disk failure.
    with pytest.raises(api.PreDispatchBudgetStopped,match='already_attempted'):
        route.post('/chat/completions',envelope)
    assert len(script.calls)==2


def test_postpaid_capture_failure_keeps_actual_usage_and_returns_once(tmp_path,monkeypatch):
    from proworksim import software_benchmark_host_api_v156 as capture
    views,rows=setup(tmp_path)
    row=rows[2];script=Script([body('paid-once')])
    client=views['C2'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script)
    capture.instrument_client(client,capture_root=tmp_path/'capture',annotate_payload=lambda w,c:annotation(w))
    original=capture._write
    def write(path,value):
        if path.name=='response-original.json':raise OSError('simulated postpaid capture disk failure')
        return original(path,value)
    monkeypatch.setattr(capture,'_write',write)
    result=client.complete(wire(row),**args(row))
    assert result['id']=='paid-once' and len(script.calls)==1
    assert client.ledger.team_snapshot(row['slot_id'])['known_actual_tokens']==13
    assert client.provenance_capture.errors()


def test_native_budget_and_member_admission_include_compressor_without_new_agent(tmp_path):
    views,rows=setup(tmp_path);row=rows[1]
    ledger=views['C1'].BudgetLedger()
    adapters={m:SimpleNamespace(ledger=EpisodeLedger(5_000_000),condition_id='C1') for m in row['fixed_members']}
    owner=SimpleNamespace(window_id=row['slot_id'],adapters=adapters,
        adapter=SimpleNamespace(ledger=TeamLedger(adapters,row['slot_id'])))
    script=Script([body('auxiliary')])
    client=views['C1'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script)
    def post(path,value):
        if path=='/team-budget':return ledger.team_snapshot(row['slot_id'])
        if path=='/compressor-tokenize':return {'prompt_tokens':100,'request_sha256':digest(json_bytes(value['wire']))}
        assert path=='/chat/completions'
        return client.complete(value['wire'],**{k:v for k,v in value.items() if k not in {'wire','team_slot_id','source_annotations'}})
    bind_owner_budget(owner,post)
    budget=AlignedManagedTeamBudget(max_decisions=512,max_attempts=512,max_total_tokens=5_000_000,
        members=row['fixed_members'],team_id=row['slot_id'],require_exact_resident=False)
    runtime=SimpleNamespace(team_budget=budget,prepared=SimpleNamespace(world=SimpleNamespace(model_budget_snapshot=budget.snapshot)))
    bind_runtime_budget(owner,runtime)
    request=wire(row,'compressor');request.pop('user_id')
    owner.compress(request,{'member_id':'member_001','source_id':'source-1','version_hash':'a'*64,
        'request_id':'source-1:receiver-1','source_annotations':annotation(request)})
    value=budget.snapshot()
    assert value['charged_tokens']==13 and value['available_tokens']==5_000_000-13
    assert value['attempts']==1 and value['decisions']==0
    assert runtime.prepared.world.model_budget_snapshot()['available_tokens']==5_000_000-13
    assert owner.adapter.ledger.actual==13 and owner.adapter.ledger.decisions==0
    assert adapters['member_002'].ledger.token_budget-adapters['member_002'].ledger.actual==5_000_000-13
    # Native pending model reservation is additional only until actual dispatch.
    budget.consume_decision('member_002','decision-1')
    budget.reserve('member_002','decision-1',{'token_reservation':100})
    assert budget.snapshot()['available_tokens']==5_000_000-13-100
    assert owner.adapter.ledger.snapshot()['known_actual_tokens']==13


def test_serialized_annotations_preserve_exact_canonical_wire(tmp_path):
    _,rows=setup(tmp_path);request=wire(rows[0])
    decoded=decode_annotations(encode_annotations(annotation(request)))
    built=build_request(decoded['payload'],{'request_id':'r','episode_id':'e','member_id':'m',
        'decision_id':'d','attempt_id':'a','model_alias':'deepseek-flash','request_time':'now'},
        template_source=decoded['template_source'])
    assert built.payload_bytes==api.canonical(request).encode()
    with pytest.raises(ValueError):api.validate_payload(wire(rows[0],'compressor'),(),usage_id='agent')
    with pytest.raises(ValueError):api.validate_payload(wire(rows[0]),(),usage_id='compressor')


def test_unknown_compressor_is_held_but_raw_fallback_can_continue_team(tmp_path):
    views,rows=setup(tmp_path);row=rows[2]
    failure=api.TransportFailure('transport_exception',phase='body')
    script=Script([failure,body('agent-after-raw-fallback')])
    client=views['C2'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script)
    with pytest.raises(api.APIUncertainFailure):
        client.complete(wire(row,'compressor'),**args(row,'compressor'))
    state=client.ledger.team_snapshot(row['slot_id'])
    assert state['uncertain_reserved_tokens']==612 and state['known_actual_tokens']==0
    assert client.complete(wire(row),**args(row))['id']=='agent-after-raw-fallback'
    state=client.ledger.team_snapshot(row['slot_id'])
    assert state['uncertain_reserved_tokens']==612 and state['known_actual_tokens']==13
    assert state['available_tokens']==5_000_000-625
    assert len(script.calls)==2


def test_real_named_fifo_supports_new_readonly_routes_and_source_annotation_frame(tmp_path):
    import os
    import threading
    import time
    from proworksim import software_benchmark_model_fifo_v157 as fifo
    for name in ('model-request.fifo','model-response.fifo'):
        fd=fifo.open_fifo(tmp_path/name,create=True);os.close(fd)
    request_fd=fifo.open_fifo(tmp_path/'model-request.fifo')
    response_fd=fifo.open_fifo(tmp_path/'model-response.fifo')
    failures=[];seen=[]
    class Delegate:
        def post(self,path,payload):
            seen.append(path)
            if path=='/chat/completions':
                raise api.TransportFailure('transport_exception',phase='body')
            return {'route':path,'payload_bytes':len(json_bytes(payload))}
    def serve():
        reader=fifo.LineReader(request_fd)
        try:
            for sequence in range(1,4):
                request=reader.read(time.monotonic()+10)
                response=fifo.model_response(request,Delegate(),sequence)
                fifo.write_frame(response_fd,response,time.monotonic()+10)
        except BaseException as error:failures.append(error)
    thread=threading.Thread(target=serve);thread.start()
    transport=fifo.FifoModelTransport('http://127.0.0.1:18219',control=tmp_path)
    try:
        assert transport.post('/team-budget',{'team_slot_id':'test'})['route']=='/team-budget'
        large=wire({'slot_id':'s','condition_id':'C2'},'compressor')
        large['messages'][0]['content']='源文本 evidence\n'*80000
        envelope={'wire':large,'source_annotations':encode_annotations(annotation(large))}
        framed=fifo.encoded_frame({'id':2,'path':'/compressor-tokenize','payload':envelope})
        assert 2_000_000<len(framed)<fifo.MAX_FRAME
        assert transport.post('/compressor-tokenize',envelope)['route']=='/compressor-tokenize'
        with pytest.raises(api.APIUncertainFailure):
            transport.post('/chat/completions',{'request_id':'physical-unknown'})
    finally:
        transport.close();thread.join(10);os.close(request_fd);os.close(response_fd)
    assert not failures and not thread.is_alive()
    assert seen==['/team-budget','/compressor-tokenize','/chat/completions']
