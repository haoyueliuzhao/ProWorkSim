"""CPU-only checks for independent cash, condition identity and bounded dispatch."""
import importlib.util
import json
import sqlite3
import pytest
from proworksim import software_benchmark_deepseek_api_v203_2_3 as api
from proworksim import software_benchmark_scope_v203_2_3 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def fixture(tmp_path):
    rows=[{'slot_id':f'v203.2.3:fixture__repo-{i}:K{i%3}:1','organization_id':'REVIEW2',
        'group_id':f'K{i%3}','condition_id':f'K{i%3}','fixed_members':['member_001','member_002']} for i in range(12)]
    panel=tmp_path/'panel.json';panel.write_text(json.dumps({'rows':rows}))
    path=tmp_path/'independent.sqlite';authority=tmp_path/'authority.json'
    authority.write_text(json.dumps({'version':api.AUTHORITY_VERSION,'ledger_path':str(path),
        'cap_nanoyuan':130_000_000_000,'panel_sha256':reference(panel)['sha256'],'approved':True}))
    views={g:api.group_api(g,path,max_concurrency=2,panel_ref=reference(panel),cash_authority_ref=reference(authority)) for g in api.GROUP_IDS}
    return rows,views


def request(row):
    return {'logical_id':row['slot_id']+':member_001:0001','attempt_index':1,'slot_id':row['slot_id'],
        'member_id':'member_001','condition':row['condition_id'],'usage_id':'agent','request_sha256':'a'*64,
        'prompt_upper_bound':1000,'max_output_tokens':100}


def test_three_conditions_share_only_new_130_account(tmp_path):
    rows,views=fixture(tmp_path)
    ledgers={g:v.BudgetLedger() for g,v in views.items()}
    assert len({str(l.path) for l in ledgers.values()})==1
    assert all(v.POLICY['cap_nanoyuan']==130_000_000_000 for v in views.values())
    for row in rows[:3]:ledgers[row['group_id']].cash_admission(row['slot_id'])
    with pytest.raises(api.PreDispatchBudgetStopped):ledgers['K0'].cash_admission(rows[3]['slot_id'])
    rid=ledgers['K0'].reserve(**request(rows[0]))
    # Already admitted work proceeds when insufficient cash remains for a new team.
    assert rid.endswith(':http-1')
    with sqlite3.connect(ledgers['K0'].path) as db:
        assert db.execute('SELECT condition,slot_id FROM requests').fetchone()==('K0',rows[0]['slot_id'])
    with pytest.raises(ValueError):ledgers['K1'].reserve(**request(rows[0]))


def test_condenser_and_both_members_share_team_token_cap(tmp_path):
    rows,views=fixture(tmp_path);ledger=views['K2'].BudgetLedger();row=rows[2]
    ledger.cash_admission(row['slot_id']);rid=ledger.reserve(**request(row))
    with sqlite3.connect(ledger.path) as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=1,usage_json=? WHERE request_id=?",
            (json.dumps({'total_tokens':4_999_999}),rid))
    other={**request(row),'logical_id':row['slot_id']+':member_002:0002','member_id':'member_002','usage_id':'condenser'}
    with pytest.raises(api.PreDispatchBudgetStopped,match='shared_team'):ledger.reserve(**other)


def test_plan_and_cpu_bounds_keep_condition_and_organization_distinct():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert len(plan['rows'])==12 and {r['organization_id'] for r in plan['rows']}=={'REVIEW2'}
    assert {r['group_id'] for r in plan['rows']}=={'K0','K1','K2'}
    lanes=[set(scope.cpu_set('coordinator').split(','))]
    for i in range(2):
        lanes += [set(scope.cpu_set(r,i).split(',')) for r in ('actor','controller')]
    lanes += [set(scope.cpu_set('grader').split(','))]
    assert sum(map(len,lanes))==len(set.union(*lanes))==24
    with pytest.raises(ValueError):scope.cpu_set('grader',1)


def test_admission_keeps_each_context_queue_separate(tmp_path):
    path=scope.ROOT/'tools/run_role_context_pilot_v203_2_3.py'
    spec=importlib.util.spec_from_file_location('role_context_runner',path)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    control=runner.DrainControl(tmp_path/'control.json',batch_root=tmp_path,groups=api.GROUP_IDS,maximum=2)
    admission=runner.ConditionAdmission(api.GROUP_IDS,control=control,maximum=2,maximum_startups=2,
        pressure_probe=lambda:{'passed':True})
    rows=[{'slot_id':g,'group_id':g,'organization_id':'REVIEW2'} for g in api.GROUP_IDS]
    for row in rows:
        admission.register_pending(row['group_id'],[row['slot_id']])
        admission.set_group_status(row['group_id'],healthy=True,can_dispatch=True)
    assert admission.try_enter(rows[0]);admission.require_start(rows[0]);admission.ready(rows[0])
    assert admission.try_enter(rows[1]);assert not admission.try_enter(rows[2])
    admission.leave(rows[0]);assert admission.try_enter(rows[2])
    assert all(row['organization_id']=='REVIEW2' for row in rows)


def pending_fixture(tmp_path):
    from types import SimpleNamespace
    path=scope.ROOT/'tools/run_role_context_pilot_v203_2_3.py'
    spec=importlib.util.spec_from_file_location('pending_runner',path)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    plan=scope.load(reference(scope.PLAN_FILE))
    control=runner.DrainControl(tmp_path/'control.json',batch_root=tmp_path,groups=api.GROUP_IDS,maximum=2)
    admission=runner.ConditionAdmission(api.GROUP_IDS,control=control,maximum=2,maximum_startups=2,pressure_probe=lambda:{'passed':True})
    runtime=SimpleNamespace(for_group=lambda g:SimpleNamespace(settled_route_witnesses=lambda:{'PROJECT':'cpu'}),admit_qualified_task=lambda *args:None)
    qualified={task:{'passed':True} for task in plan['environments']}
    qualified['psf__requests-1766']={'status':'pending_controls','qualification_path':str(tmp_path/'qualified.json'),'terminal_result_path':str(tmp_path/'terminal.json')}
    validation={'accept':False}
    def validate(*args):
        if not validation['accept']:raise ValueError('incomplete frozen qualification')
    grading=SimpleNamespace(scorer=SimpleNamespace(validate_qualification=validate))
    coordinator=runner.Coordinator(runtime=runtime,implementation=None,grading=grading,memory=None,admission=admission,
        plan=plan,qualifications=qualified,output=tmp_path/'output',cash_status=lambda group:{'state':'ready','can_start_generation':True})
    return coordinator,runner,validation


def test_pending_environment_does_not_block_ready_nine_or_enter_before_validated(tmp_path,monkeypatch):
    from concurrent.futures import Future
    c,runner,validation=pending_fixture(tmp_path)
    assert sum(map(len,c.pending.values()))==9 and len(c.waiting_qualification)==3
    entered=[]
    class Executor:
        def submit(self,fn,row):entered.append(row);return Future()
    monkeypatch.setattr(runner.scope,'require_runtime_gate',lambda:None)
    c._admit(Executor())
    assert len(entered)==2 and all(r['instance_id']!='psf__requests-1766' for r in entered)
    (tmp_path/'qualified.json').write_text('{"passed":true}')
    c.refresh_pending_qualifications()
    assert len(c.waiting_qualification)==3
    validation['accept']=True;c.last_qualification_check=0;c.refresh_pending_qualifications()
    assert not c.waiting_qualification
    assert sum(r['instance_id']=='psf__requests-1766' for q in c.pending.values() for r in q)==3
    assert len({r['slot_id'] for r in c.plan['rows']})==12


def test_pending_terminal_environment_failure_preserves_denominator_and_other_tasks(tmp_path):
    c,_,_=pending_fixture(tmp_path)
    (tmp_path/'terminal.json').write_text('{')
    c.refresh_pending_qualifications()
    assert len(c.waiting_qualification)==3 and sum(map(len,c.pending.values()))==9
    (tmp_path/'terminal.json').write_text('{"passed":false,"reason":"unreachable"}')
    c.last_qualification_check=0;c.refresh_pending_qualifications()
    assert not c.waiting_qualification and len(c.deferred)==3
    assert sum(map(len,c.pending.values()))==9 and len(c.plan['rows'])==12
    assert all(v['reason']=='fresh_environment_control_not_qualified' for v in c.deferred.values())


def test_host_provider_authority_rejects_a_pending_slot_before_any_network(monkeypatch):
    from proworksim import software_benchmark_host_api_v203_2_3 as host
    runtime=host.DeepSeekRuntime()
    calls=[]
    monkeypatch.setattr(scope,'require_allowed',lambda *a,**k:calls.append((a,k)))
    with pytest.raises(PermissionError,match='before verified environment'):
        runtime.authorize('v203.2.3.api.request',slot_id='pending',instance_id='psf__requests-1766')
    assert calls==[]
    runtime.qualified_slots.add('ready')
    runtime.authorize('v203.2.3.api.request',slot_id='ready',instance_id='ready')
    assert len(calls)==1
