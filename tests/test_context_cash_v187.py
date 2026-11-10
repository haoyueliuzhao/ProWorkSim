import json,sqlite3
import pytest
from proworksim import software_context_cash_v187 as c
from proworksim.software_benchmark_candidates_v054 import reference

def fixture(tmp_path):
    path=tmp_path/'ledger.sqlite';raw=json.dumps({'cap_nanoyuan':c.BASE,'old_policy':'frozen'})
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)')
        db.execute('INSERT INTO metadata VALUES(?,?)',('policy',raw))
        db.execute('CREATE TABLE requests(request_id TEXT PRIMARY KEY,cost INTEGER)')
        db.execute('INSERT INTO requests VALUES(?,?)',('old-request',123))
    grant=tmp_path/'grant.json'
    grant.write_text(json.dumps({'approved':True,'amendment_id':c.AMENDMENT,'ledger':str(path),
        'previous_cap_nanoyuan':c.BASE,'added_nanoyuan':c.ADDED,'effective_cap_nanoyuan':c.CAP}))
    return path,grant,raw

def test_append_only_idempotent_budget_increase(tmp_path):
    path,grant,raw=fixture(tmp_path)
    assert not c.register(path,reference(grant))['already_registered']
    assert c.register(path,reference(grant))['already_registered']
    with sqlite3.connect(path) as db:
        assert c.effective_cap(db,reference(grant))==300_000_000_000
        assert db.execute('SELECT value FROM metadata').fetchone()[0]==raw
        assert db.execute('SELECT * FROM requests').fetchall()==[('old-request',123)]
        assert db.execute('SELECT count(*) FROM cash_amendments_v187').fetchone()[0]==1

def test_unapproved_amount_or_changed_authority_cannot_expand_cap(tmp_path):
    path,grant,_=fixture(tmp_path)
    data=json.loads(grant.read_text());data['effective_cap_nanoyuan']=350_000_000_000
    grant.write_text(json.dumps(data))
    with pytest.raises(ValueError):c.register(path,reference(grant))

def test_actual_scheduler_uses300_without_changing_old_policy(tmp_path,monkeypatch):
    from proworksim import software_context_budget_runtime_v187 as runtime
    from proworksim.software_context_api_v175 import ReplayLedger,CashClosed
    path=tmp_path/'live-shaped.sqlite'
    ledger=runtime.TaskLedger.__new__(runtime.TaskLedger)
    ReplayLedger.__init__(ledger,path,plan_ref={'fixture':'original-policy'})
    rows=[{'slot_id':'fixture-new-'+str(i),'slot_index':999990+i} for i in range(2)]
    ledger.rows={r['slot_id']:r for r in rows}
    remaining=tmp_path/'remaining.json';remaining.write_text(json.dumps({'rows':rows}))
    grant=tmp_path/'authorized300.json';grant.write_text(json.dumps({'approved':True,'amendment_id':c.AMENDMENT,
        'ledger':str(path),'previous_cap_nanoyuan':c.BASE,'added_nanoyuan':c.ADDED,'effective_cap_nanoyuan':c.CAP}))
    monkeypatch.setattr(c,'AUTHORITY',grant);monkeypatch.setattr(runtime,'REMAINING',remaining)
    monkeypatch.setattr(runtime,'AUTHORITY',grant)
    monkeypatch.setattr(runtime,'predecessor_closed',lambda:True)
    monkeypatch.setattr(runtime,'never_entered',lambda row,db=None:True)
    c.register(path,reference(grant))
    with ledger.transaction() as db:
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('synthetic_prior_charge','old','agent',0,1,'settled','x',252_000_000_000,252_000_000_000,
             json.dumps({'total_tokens':1}),None,None,0,0))
    assert ledger.policy['cap_nanoyuan']==250_000_000_000
    assert ledger.admit_block(rows[:1])['effective_cap_CNY']==300
    assert ledger.snapshot()['cap_CNY']==300
    with ledger.transaction() as db:
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('synthetic_uncertain_charge','old','agent',0,1,'unknown','x',50_000_000_000,None,None,None,None,0,0))
    with pytest.raises(CashClosed):ledger.admit_block(rows[1:])
