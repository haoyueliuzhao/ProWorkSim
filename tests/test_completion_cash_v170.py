"""Synthetic cash-boundary controls; no provider or actual billing operations."""
from copy import deepcopy
import json
import sqlite3

import pytest

from proworksim import software_benchmark_deepseek_api_v157 as base
from proworksim import software_benchmark_completion_api_v170 as policy
from proworksim.software_benchmark_candidates_v054 import reference


def put(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value));return reference(path)


def setup(tmp_path):
    rows=[];panel=[];entries=[]
    for i in range(13):
        g=base.GROUP_IDS[i%3];slot=f'cpu-old-{i}';pre=f'cpu-pre-{i}'
        config={'slot_id':slot,'slot_index':i,'instance_id':f'fixture__repo-{i}','seed':i,
            'condition_id':g,'fixed_members':['member_001','member_002'],'budget_tokens':5_000_000}
        cfg=put(tmp_path/f'old-{i}.json',config)
        row={**config,'group_id':g,'condition':g,'configuration':cfg,'wave':1,'organization_id':'REVIEW2'}
        rows.append({**row,'source_preparation_slot_id':pre});panel.append({**row,'slot_id':pre})
        new=slot+':completion-recovery-v170'
        entry={k:row[k] for k in ('instance_id','condition_id','group_id','seed','fixed_members')}
        entry.update(original_slot_id=slot,recovery_slot_id=new,slot_index=17000+i,
            classification='cash_admission_interruption',original_configuration=cfg,
            configuration=put(tmp_path/f'new-{i}.json',{**config,'slot_id':new,'slot_index':17000+i}),
            failure_evidence={'boundary':put(tmp_path/f'boundary-{i}.json',{'execution_integrity_failure':{
                'reason':'remaining_cash_reservation_insufficient','before_dispatch_proven':True}}),
                'quiescence':put(tmp_path/f'quiet-{i}.json',{'quiescent':True,'all_owned_objects_removed':True,'cleanup_errors':[]})})
        entries.append(entry)
    p=put(tmp_path/'panel.json',{'rows':panel});plan=put(tmp_path/'plan.json',{'rows':rows});ledger=tmp_path/'original.sqlite'
    cash=put(tmp_path/'cash.json',{'version':base.AUTHORITY_VERSION,'approved':True,
        'ledger_path':str(ledger),'cap_nanoyuan':500_000_000_000,
        'panel_sha256':p['sha256'],'execution_plan_sha256':plan['sha256']})
    apis={g:base.group_api(g,ledger,max_concurrency=16,panel_ref=p,cash_authority_ref=cash,execution_plan_ref=plan) for g in base.GROUP_IDS}
    book=apis['C0'].BudgetLedger()
    grant=put(tmp_path/'user.json',{'approved':True,'additional_nominal_CNY':'50.00',
        'new_team_start_cash_threshold_CNY':'550.00','started_team_may_finish_above_threshold':True})
    auth={'version':policy.AUTH_VERSION,'approved':True,'base_policy_sha256':base.sha(apis['C0'].POLICY),
        'ledger_path':str(ledger),'new_team_start_threshold_nanoyuan':policy.THRESHOLD,
        'additional_nominal_nanoyuan':50_000_000_000,'started_teams_finish_above_threshold':True,
        'team_token_limit':5_000_000,'maximum_new_attempts':13,'user_grant':grant,'attempts':entries}
    ref=put(tmp_path/'authority.json',auth)
    policy.register(apis['C0'],ref)
    views={g:policy.completion_api(g,a,ref) for g,a in apis.items()}
    return apis,views,entries,ref,book


def synthetic_prior_spend(book,amount):
    # This fictitious cost forces a cash boundary. It is never an experiment result.
    with book.transaction() as db:
        db.execute("INSERT INTO requests(request_id,logical_id,attempt_index,slot_id,member_id,condition,usage_id,request_sha256,status,reserved_nanoyuan,reserved_tokens,prompt_upper_bound,max_output_tokens,reserved_utc,settled_nanoyuan,usage_json,response_id) VALUES('cpu-history','cpu-history',1,'cpu-history','member_001','C0','agent',?,'settled',?,0,0,0,'CPU',?,?,'cpu-history')",('a'*64,amount,amount,json.dumps({'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})))


def reserve(book,entry,n=1,prompt=98304,output=32768,purpose='agent'):
    slot=entry['recovery_slot_id'];tag=':compressor:' if purpose=='compressor' else ':'
    return book.reserve(logical_id=slot+':member_001'+tag+f'{n:04d}',attempt_index=1,
        slot_id=slot,member_id='member_001',condition=entry['condition_id'],usage_id=purpose,
        request_sha256='b'*64,prompt_upper_bound=prompt,max_output_tokens=output)


def response(request_id,prompt=98304,output=32768):
    return {'id':'response-'+request_id,'model':'deepseek-flash','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'CPU'}}],
        'usage':{'prompt_tokens':prompt,'completion_tokens':output,'total_tokens':prompt+output,
            'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':prompt}}


def test_started_teams_cross550_new_team_is_denied_and_history_not_rewritten(tmp_path):
    apis,views,entries,ref,old=setup(tmp_path);synthetic_prior_spend(old,549_000_000_000)
    a,b,c=entries[:3];ba=views[a['group_id']].BudgetLedger();bb=views[b['group_id']].BudgetLedger();bc=views[c['group_id']].BudgetLedger()
    ba.admit_team(a['recovery_slot_id']);bb.admit_team(b['recovery_slot_id'])
    with pytest.raises(base.PreDispatchBudgetStopped,match='start_cash'):
        bc.admit_team(c['recovery_slot_id'])  # Both initial request buffers count.
    for n in range(1,4):
        req=reserve(ba,a,n);ba.settle(req,response(req))
    req=reserve(bb,b);bb.settle(req,response(req))
    assert ba.snapshot()['over_threshold_nanoyuan']>0
    assert ba.team_snapshot(a['recovery_slot_id'])['attempts']==3
    with pytest.raises(base.PreDispatchBudgetStopped,match='start_cash'):
        bc.admit_team(c['recovery_slot_id'])
    with sqlite3.connect(old.path) as db:
        assert json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])==apis['C0'].POLICY
        assert db.execute("SELECT settled_nanoyuan FROM requests WHERE request_id='cpu-history'").fetchone()[0]==549_000_000_000
        assert db.execute('SELECT COUNT(*) FROM cash_amendments_v170').fetchone()[0]==1


def test_no_actual_start_cannot_dispatch_and_unentered_return_releases_only_buffer(tmp_path):
    _,views,entries,_,_=setup(tmp_path);entry=entries[0];book=views['C0'].BudgetLedger()
    with pytest.raises(base.PreDispatchBudgetStopped,match='no_actual_start'):
        reserve(book,entry)
    book.admit_team(entry['recovery_slot_id']);assert book.snapshot()['new_team_start_hold_nanoyuan']==policy.START_HOLD
    book.release_unentered(entry['recovery_slot_id']);assert book.snapshot()['new_team_start_hold_nanoyuan']==0
    book.admit_team(entry['recovery_slot_id']);req=reserve(book,entry)
    with pytest.raises(ValueError,match='physically attempted'):
        book.release_unentered(entry['recovery_slot_id'])
    book.settle(req,response(req))


def test_started_grace_does_not_relax_shared5M_or_response_settlement_once(tmp_path):
    _,views,entries,_,old=setup(tmp_path);synthetic_prior_spend(old,549_000_000_000)
    e=entries[1];book=views['C1'].BudgetLedger();book.admit_team(e['recovery_slot_id'])
    for n in range(1,39):
        req=reserve(book,e,n);book.settle(req,response(req))
    assert book.team_snapshot(e['recovery_slot_id'])['known_actual_tokens']==38*131072
    with pytest.raises(base.PreDispatchBudgetStopped,match='shared_team'):
        reserve(book,e,39)
    with pytest.raises(ValueError,match='settle once'):
        book.settle(req,response(req))


def test_addition_is_idempotent_before_dispatch_and_cannot_be_stacked(tmp_path):
    apis,_,_,ref,old=setup(tmp_path);policy.register(apis['C0'],ref)
    with sqlite3.connect(old.path) as db:
        assert db.execute('SELECT COUNT(*) FROM cash_amendments_v170').fetchone()[0]==1
    value=json.loads(__import__('pathlib').Path(ref['path']).read_bytes());value['additional_nominal_nanoyuan']+=1
    changed=put(tmp_path/'changed-authority.json',value)
    with pytest.raises(ValueError,match='50-CNY'):
        policy.register(apis['C0'],changed)


def test_same_shared_team_counts_agent_summary_compressor_and_retains_unknown_hold(tmp_path):
    _,views,entries,_,_=setup(tmp_path);e=entries[1];book=views['C1'].BudgetLedger();book.admit_team(e['recovery_slot_id'])
    for n,purpose in enumerate(('agent','condenser','compressor'),1):
        req=reserve(book,e,n,prompt=10,output=512 if purpose=='compressor' else 100,purpose=purpose)
        book.settle(req,response(req,prompt=10,output=3))
    req=reserve(book,e,4,prompt=10,output=512,purpose='compressor')
    book.failed(req,base.TransportFailure('incomplete_response_body',phase='body',status=200))
    view=book.team_snapshot(e['recovery_slot_id'])
    assert view['known_actual_tokens']==39 and view['uncertain_reserved_tokens']==522
    assert view['attempts']==4 and view['decisions']==1
    assert set(view['per_usage_id'])=={'agent','condenser','compressor'}


def test_actual_host_transport_keeps_physical_capture_above_start_threshold(tmp_path):
    from proworksim import software_benchmark_host_api_v157 as host
    from proworksim.software_benchmark_host_api_v159 import HostTeamTransport
    from proworksim.software_benchmark_budget_v157 import encode_annotations
    from proworksim.software_input_provenance_v156 import SourceFragment,annotate_tree
    from proworksim.storage import digest,json_bytes
    _,views,entries,_,old=setup(tmp_path)
    e=entries[1];slot=e['recovery_slot_id'];book=views['C1'].BudgetLedger();book.admit_team(slot)
    synthetic_prior_spend(old,551_000_000_000)  # Synthetic in-flight state, not money spent.
    class Script:
        calls=0
        def request(self,*args):
            self.calls+=1
            return response(str(self.calls),prompt=10,output=3)
    runtime=host.runtime_for(apis=views,schemas={g:{m:[] for m in e['fixed_members']} for g in base.GROUP_IDS},
        counter=lambda wire:{'prompt_tokens':100,'request_sha256':digest(json_bytes(wire))},
        authorize=lambda *a,**k:None,api_key='CPU_unused',max_concurrency=16)
    script=Script();client=views['C1'].DeepSeekClient(api_key='CPU_unused',allowed_tool_names=(),
        transport=script,http_slots=runtime.http_slots)
    runtime.clients['C1'].fork_for_episode=lambda:client
    row={'slot_id':slot,'instance_id':e['instance_id'],'condition_id':'C1','group_id':'C1','fixed_members':e['fixed_members']}
    route=HostTeamTransport(runtime,row,tmp_path/'capture')
    source=SourceFragment('Base/Template','CPU:template','CPU:event','member_001')
    for n,purpose in enumerate(('agent','condenser','compressor'),1):
        wire={'model':'deepseek-flash','messages':[{'role':'user','content':'CPU exact request'}],
            'max_tokens':512 if purpose=='compressor' else 100,'thinking':{'type':'disabled'},
            'temperature':.2 if purpose=='compressor' else 1.,'top_p':1.,'stream':False,
            'user_id':base.old.slot_user_id(slot+':member_001','C1')}
        tag=':compressor:' if purpose=='compressor' else ':'
        route.post('/chat/completions',{'wire':wire,'member_id':'member_001','team_slot_id':slot,
            'request_id':slot+':member_001'+tag+f'{n:04d}','slot_id':slot,'condition':'C1',
            'usage_id':purpose,'prompt_upper_bound':100,
            'source_annotations':encode_annotations({'payload':annotate_tree(wire,source),'template_source':source})})
    assert script.calls==3 and len(client.provenance_capture.receipts())==3
    assert route.post('/team-budget',{'team_slot_id':slot})['known_actual_tokens']==39
    assert client.ledger.snapshot()['over_threshold_nanoyuan']>0
