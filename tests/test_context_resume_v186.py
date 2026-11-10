import json
import sqlite3
import threading
from types import SimpleNamespace
import pytest
from proworksim import software_context_resume_v186 as r
from proworksim.software_context_api_v175 import ReplayLedger,CashClosed

G=1024**3

def policy():
    return SimpleNamespace(CONSTRAINTS=r.scope.CONSTRAINTS,host_cpu_pool=lambda:list(range(176)))

def test_disk_gate_honors_real_plan_and_spool_reservations():
    resources={'memory_available_bytes':900*G,'disk_free_bytes':216*G,'passed':True}
    value=r.capacity_status(policy(),physical=resources,active=[],load1=45)
    assert value['admit'] and value['disk_floor_bytes']==132*G
    value=r.capacity_status(policy(),physical={**resources,'disk_free_bytes':131*G},active=[],load1=45)
    assert not value['admit'] and value['waiting_reasons']==['disk_reservation']
    active=[{'spec':{'role':'actor'},'reserved_spool_bytes':4*G}]
    value=r.capacity_status(policy(),physical={**resources,'disk_free_bytes':135*G},active=active,load1=45)
    assert value['disk_floor_bytes']==136*G and not value['admit']

def ledger(tmp_path):
    value=r.TaskLedger.__new__(r.TaskLedger)
    ReplayLedger.__init__(value,tmp_path/'ledger.sqlite',plan_ref={'fixture':'no_production_ledger'})
    value.rows={}
    return value

def test_group_subset_never_turns_other_same_batch_holds_into40(tmp_path):
    value=ledger(tmp_path);value.rows={'only-pylint':{}}
    with value.transaction() as db:
        for i in range(4):db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',(f'other-{i}','v181-full-task',40_000_000_000,'running',0))
        assert value._account(db)==(0,20_000_000_000)
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',('another-study','different-experiment',7_000_000_000,'running',0))
        assert value._account(db)==(0,27_000_000_000)

def test_previous_zero_call_grant_is_adopted_without_new_cash_hold(tmp_path,monkeypatch):
    value=ledger(tmp_path);row={'slot_id':'fixture-waiting','slot_index':999999};value.rows={row['slot_id']:row}
    pending=tmp_path/'remaining.json';pending.write_text(json.dumps({'rows':[row]}))
    handoff=tmp_path/'handoff.json';handoff.write_text(json.dumps({'old_manager_stopped':True}))
    monkeypatch.setattr(r,'REMAINING',pending);monkeypatch.setattr(r,'HANDOFF',handoff)
    monkeypatch.setattr(r,'never_entered',lambda row,db=None:True)
    with value.transaction() as db:
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,NULL)',(row['slot_id'],'v181-full-task',40_000_000_000,'running',123))
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('unrelated-cost','previous','agent',1,1,'unknown','x',249_000_000_000,None,None,None,None,0,None))
    assert value.admit_block([row])=={'adopted_prior_grants':1,'new_grants':0}
    with value.transaction() as db:
        assert db.execute('SELECT started FROM jobs').fetchone()[0]==123
        assert db.execute('SELECT count(*) FROM start_handoff_v186').fetchone()[0]==1
    with pytest.raises(sqlite3.IntegrityError):value.admit_block([row])

def test_actual_episode_capacity_binding_can_cancel_before_objects():
    from proworksim.software_benchmark_episode_v181 import build_episode
    from proworksim.software_benchmark_alignment_contract_v181 import VERSION
    from proworksim.software_benchmark_candidates_v054 import reference
    def guard(*args,**kwargs):return {'status':'approved','execution_alignment_version':VERSION,
        'source_index':reference(r.scope.PLAN_FILE),'plan':reference(r.scope.PLAN_FILE),'constraints':r.scope.CONSTRAINTS}
    episode=build_episode(scope=r.scope,guard=guard)
    stop=threading.Event();seen=[]
    r.bind_capacity(episode,r.scope.dispatch_view(guard),stop,seen.append)
    assert episode._run.__globals__['capacity'] is episode.capacity
    assert episode._run.__globals__['wait_capacity'] is episode.wait_capacity
    stop.set()
    with pytest.raises(InterruptedError):episode.wait_capacity()
    assert not seen
