import pytest
from proworksim.software_context_task_api_v192 import TaskLedger,CashClosed

def ledger(tmp_path):
    rows=[{'slot_id':'main-'+str(i),'primary_panel':True} for i in range(4)]
    rows += [{'slot_id':'repeat-'+str(i),'primary_panel':False} for i in range(2)]
    value=TaskLedger(path=tmp_path/'ledger.sqlite',plan={'rows':rows},counter=type('Counter',(),{'measure':lambda _,payload:{'prompt_tokens':100}})())
    return value,rows

def spend(value,nanoyuan):
    with value.transaction() as db:
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('fixture-prior','other','agent',1,1,'unknown','x',nanoyuan,None,None,None,None,0,None))

def test_main_cannot_consume_preselected_repeat_earmark(tmp_path):
    value,rows=ledger(tmp_path);spend(value,270_000_000_000)
    with pytest.raises(CashClosed):value.admit_block(rows[:4])
    value.admit_block(rows[4:])
    snapshot=value.snapshot();assert snapshot['cap_CNY']==300 and snapshot['unentered_repeat_earmark_CNY']==0
    assert snapshot['unused_active_job_holds_CNY']==10
    with pytest.raises(ValueError):value.admit_block(rows[4:])

def test_started_episode_is_not_stopped_by_total_cash(tmp_path):
    value,rows=ledger(tmp_path);value.admit_block(rows[:4]);spend(value,310_000_000_000)
    value.reserve(rows[0]['slot_id'],'new-physical','agent',1,1,{'max_tokens':32})
    assert value.request('new-physical')['status']=='reserved'

def test_subset_does_not_turn_same_batch_start_hold_into_worst_case40(tmp_path):
    value,rows=ledger(tmp_path);value.admit_block(rows[:4]);value.rows={r['slot_id']:r for r in rows[4:]}
    with value.transaction() as db:assert value._account(db)==(0,20_000_000_000)
