"""CPU synthetic controls of an amended identity view, not another cash pool."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest
from proworksim import software_benchmark_deepseek_api_v157 as base
from proworksim import software_benchmark_recovery_api_v161 as recovery
from proworksim.software_benchmark_candidates_v054 import reference


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value,str) else value)
    return reference(path)


def body(name):
    return {'id':name,'model':'deepseek-flash','choices':[{'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':10,'completion_tokens':3,'total_tokens':13,'prompt_cache_hit_tokens':4,'prompt_cache_miss_tokens':6}}


def setup(tmp_path):
    panel=[];rows=[]
    for index,g in enumerate(base.GROUP_IDS):
        slot='v157:task:'+g;pre='v156:task:'+g
        cfg={'slot_id':slot,'slot_index':15700+index,'instance_id':'repo__name-1','seed':123,'condition_id':g,
            'fixed_members':['member_001','member_002'],'team_budget':5_000_000,'issue':'unchanged public issue'}
        cfg_ref=put(tmp_path/f'config-{g}.json',cfg)
        row={**cfg,'group_id':g,'condition':g,'organization_id':'REVIEW2','configuration':cfg_ref,'wave':1}
        panel.append({**row,'slot_id':pre})
        rows.append({**row,'source_preparation_slot_id':pre})
    panel_ref=put(tmp_path/'panel.json',{'rows':panel});plan_ref=put(tmp_path/'plan.json',{'rows':rows})
    ledger=tmp_path/'original500.sqlite'
    cash=put(tmp_path/'cash.json',{'version':base.AUTHORITY_VERSION,'approved':True,'ledger_path':str(ledger),
        'cap_nanoyuan':500_000_000_000,'panel_sha256':panel_ref['sha256'],'execution_plan_sha256':plan_ref['sha256']})
    api=base.group_api('C1',ledger,max_concurrency=16,panel_ref=panel_ref,cash_authority_ref=cash,execution_plan_ref=plan_ref)
    book=api.BudgetLedger();old=rows[1];prefix=old['slot_id']+':member_001:0001'
    rid=book.reserve(logical_id=prefix,attempt_index=1,slot_id=old['slot_id'],member_id='member_001',condition='C1',
        usage_id='agent',request_sha256='a'*64,prompt_upper_bound=100,max_output_tokens=100)
    book.settle(rid,body('original-response'))
    new=old['slot_id']+':independent-technical-recovery-r1'
    cfg=json.loads(Path(old['configuration']['path']).read_text());cfg.update(slot_id=new,slot_index=16100)
    entry={k:deepcopy(old[k]) for k in ('instance_id','condition_id','group_id','seed','fixed_members')}
    entry.update(original_slot_id=old['slot_id'],recovery_slot_id=new,slot_index=16100,
        classification='request_source_capture_failure',original_configuration=old['configuration'],
        configuration=put(tmp_path/'recovery-config.json',cfg),failure_evidence={
            'result':put(tmp_path/'episode/result.json',{'slot_id':old['slot_id'],'status':'technical_unknown','candidate_lock':None}),
            'observer':put(tmp_path/'episode/observer.json',{'completion_status':'partial','runtime_measurement_errors':[
                {'scope':'request_capture','type':'AccountingConflict','message':'Actual request source attribution is below the approved 98% gate'}]}),
            'quiescence':put(tmp_path/'episode/quiescence.json',{'quiescent':True,'cleanup_errors':[],'create_result_unknown':False}),
            'controller_stderr':put(tmp_path/'episode/controller.stderr','result["ledger"] = owner.save()\nargument must be an int, or have a fileno() method.')})
    grant={'version':recovery.AUTH_VERSION,'status':'approved','base_policy_sha256':base.sha(api.POLICY),
        'ledger_path':str(ledger),'cash_authority':cash,'cap_nanoyuan':500_000_000_000,
        'additional_cash_allowance_nanoyuan':0,'maximum_recoveries_per_original':1,
        'team_token_limit':5_000_000,'team_http_attempt_limit':512,'same_initial_state_seed_and_condition':True,
        'normal_model_failures_may_retry':False,'attempts':[entry]}
    ref=put(tmp_path/'grant.json',grant)
    return api,book,old,entry,ref


class Script:
    def __init__(self):self.count=0
    def request(self,*args):self.count+=1;return body('recovery-response-'+str(self.count))


def test_registration_is_explicit_same_cash_and_three_purpose_same_team(tmp_path):
    api,book,old,entry,ref=setup(tmp_path)
    before=api.POLICY.copy();view=recovery.recovery_api('C1',api,ref)
    with pytest.raises(ValueError,match='not registered'):view.BudgetLedger().team_snapshot(entry['recovery_slot_id'])
    events=[];proof=recovery.register_authorized_attempts(api,ref,lambda *a,**k:events.append((a,k)))
    assert proof['additional_cash_allowance_nanoyuan']==0 and proof['model_calls']==0 and len(events)==1
    client=view.DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=Script())
    new=entry['recovery_slot_id']
    for i,purpose in enumerate(('agent','condenser','compressor'),1):
        request={'model':'deepseek-flash','messages':[{'role':'user','content':'same task'}],
            'max_tokens':512 if purpose=='compressor' else 100,'thinking':{'type':'disabled'},
            'temperature':.2 if purpose=='compressor' else 1.,'top_p':1.,'stream':False,
            'user_id':base.old.slot_user_id(new+':member_001','C1')}
        tag=':compressor:' if purpose=='compressor' else ':'
        client.complete(request,request_id=new+':member_001'+tag+f'{i:04d}',slot_id=new,member_id='member_001',
            condition='C1',usage_id=purpose,prompt_upper_bound=100)
    state=client.ledger.team_snapshot(new)
    assert state['known_actual_tokens']==39 and state['decisions']==1 and state['attempts']==3
    assert book.snapshot()['known_actual_tokens']==52
    assert book.snapshot()['settled_nanoyuan']==4*(4*40+6*2000+3*8000)
    with sqlite3.connect(book.path) as db:
        assert json.loads(db.execute("select value from metadata where name='policy'").fetchone()[0])==before
        assert db.execute('select additional_cash_nanoyuan from technical_recovery_authorities').fetchone()[0]==0
    with pytest.raises(ValueError,match='consumed'):recovery.register_authorized_attempts(api,ref,lambda *a,**k:None)


def test_locked_candidate_normal_failure_or_changed_config_cannot_be_registered(tmp_path):
    api,book,old,entry,ref=setup(tmp_path)
    folder=tmp_path/'episode/controller-output/project-candidates/terminal-code';folder.mkdir(parents=True)
    (folder/'lock.json').write_text('{}')
    with pytest.raises(ValueError,match='uniquely locked'):recovery.recovery_api('C1',api,ref)
    (folder/'lock.json').unlink()
    grant=json.loads(Path(ref['path']).read_text());grant['attempts'][0]['seed']=999
    ref2=put(tmp_path/'changed-seed.json',grant)
    with pytest.raises(ValueError,match='identity/seed'):recovery.recovery_api('C1',api,ref2)
    assert book.snapshot()['known_actual_tokens']==13


def test_global_original_cash_limit_applies_to_new_attempt_and_no_registration_on_import(tmp_path):
    api,book,old,entry,ref=setup(tmp_path)
    with sqlite3.connect(book.path) as db:
        assert db.execute("select count(*) from sqlite_master where name='technical_recovery_attempts'").fetchone()[0]==0
    recovery.register_authorized_attempts(api,ref,lambda *a,**k:None)
    with book.transaction() as db:db.execute('update requests set settled_nanoyuan=499999999999')
    newbook=recovery.recovery_api('C1',api,ref).BudgetLedger();new=entry['recovery_slot_id']
    with pytest.raises(base.PreDispatchBudgetStopped,match='cash'):
        newbook.reserve(logical_id=new+':member_001:0001',attempt_index=1,slot_id=new,
            member_id='member_001',condition='C1',usage_id='agent',request_sha256='b'*64,
            prompt_upper_bound=10,max_output_tokens=10)
    assert newbook.team_snapshot(new)['attempts']==0


def test_actual_recovery_host_preserves_physical_capture_and_shared_retry_budget(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from proworksim import software_benchmark_host_api_v157 as original_host
    from proworksim import software_benchmark_host_api_v161 as host
    from proworksim.software_benchmark_budget_v157 import encode_annotations
    from proworksim.software_input_provenance_v156 import SourceFragment,annotate_tree
    from proworksim.software_communication_finish_v159 import require_known_usage
    from proworksim.storage import digest,json_bytes
    api,book,old,entry,ref=setup(tmp_path)
    cash=api.POLICY['cash_authority'];panel=api.POLICY['panel'];plan=api.POLICY['execution_plan']
    apis={group:base.group_api(group,book.path,max_concurrency=16,panel_ref=panel,
        cash_authority_ref=cash,execution_plan_ref=plan) for group in base.GROUP_IDS}
    row={**old,'slot_id':entry['recovery_slot_id'],'slot_index':entry['slot_index'],
        'configuration':entry['configuration'],'original_slot_id':entry['original_slot_id']}
    host.checked_authority({'rows':[row]},ref,apis)
    changed=deepcopy(row);changed['group_id']='C0'
    with pytest.raises(ValueError,match='condition'):
        host.checked_authority({'rows':[changed]},ref,apis)
    recovery.register_authorized_attempts(api,ref,lambda *a,**k:None)
    views={group:recovery.recovery_api(group,value,ref) for group,value in apis.items()}
    runtime=original_host.runtime_for(apis=views,
        schemas={group:{member:[] for member in row['fixed_members']} for group in base.GROUP_IDS},
        counter=lambda wire:{'prompt_tokens':100,'request_sha256':digest(json_bytes(wire))},
        authorize=lambda *a,**k:None,api_key='unused',max_concurrency=16)
    class Retry:
        def __init__(self):self.calls=0
        def request(self,*args):
            self.calls+=1
            if self.calls==1:
                raise base.TransportFailure('complete_http_error_response',phase='complete_http_response',status=503)
            return body('physical-'+str(self.calls))
    script=Retry()
    client=views['C1'].DeepSeekClient(api_key='unused',allowed_tool_names=(),transport=script,
        http_slots=runtime.http_slots,sleep=lambda _:None,jitter=lambda:0)
    runtime.clients['C1'].fork_for_episode=lambda:client
    @contextmanager
    def read(group):
        connection=sqlite3.connect(book.path);connection.row_factory=sqlite3.Row
        try:yield connection
        finally:connection.close()
    monkeypatch.setattr(original_host,'ledger_read',read)
    route=host.HostTeamTransport(runtime,row,tmp_path/'actual-host')
    for i,purpose in enumerate(('agent','condenser','compressor'),1):
        wire={'model':'deepseek-flash','messages':[{'role':'user','content':'unchanged issue'}],
            'max_tokens':512 if purpose=='compressor' else 100,'thinking':{'type':'disabled'},
            'temperature':.2 if purpose=='compressor' else 1.,'top_p':1.,'stream':False,
            'user_id':api.slot_user_id(row['slot_id']+':member_001',row['condition_id'])}
        source=SourceFragment('Base/Template','synthetic-template','event','member_001')
        tag=':compressor:' if purpose=='compressor' else ':'
        envelope={'wire':wire,'member_id':'member_001','team_slot_id':row['slot_id'],
            'request_id':row['slot_id']+':member_001'+tag+f'{i:04d}','slot_id':row['slot_id'],
            'condition':row['condition_id'],'usage_id':purpose,'prompt_upper_bound':100,
            'source_annotations':encode_annotations({'payload':annotate_tree(wire,source),'template_source':source})}
        route.post('/chat/completions',envelope)
    state=route.post('/team-budget',{'team_slot_id':row['slot_id']})
    assert script.calls==4 and state['attempts']==4 and state['decisions']==1
    assert state['known_actual_tokens']==39 and state['uncertain_reserved_tokens']==200
    require_known_usage({'known_actual_tokens':state['known_actual_tokens'],'complete_actual_tokens':None,
        'uncertain_reserved_tokens':state['uncertain_reserved_tokens'],'inflight':None,
        'authoritative_provider_snapshot':state})
    assert len(client.provenance_capture.receipts())==4
    assert all(item['request_capture'] and item['final_receipt_ref'] for item in client.provenance_capture.receipts())
    assert book.snapshot()['known_actual_tokens']==52
    assert book.snapshot()['unknown_tokens_upper']==200
    with pytest.raises(ValueError,match='already dispatched'):
        managed=host.DeepSeekRuntime();managed.rows={row['slot_id']:row};managed._route_claimed=set()
        managed.transport_factory(row,tmp_path/'illegal-replay')
