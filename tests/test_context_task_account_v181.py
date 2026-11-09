import json
import shutil
import sqlite3
import pytest
from proworksim import software_context_task_api_v181 as api
from proworksim.software_benchmark_candidates_v054 import reference


class Counter:
    def measure(self,payload):return {'prompt_tokens':100}


def test_admitted_episode_finishes_above_cash_but_new_block_stops(tmp_path):
    path=tmp_path/'ledger.sqlite'
    shutil.copyfile(api.scope.LEDGER_FILE,path)
    plan=api.scope.load(reference(api.scope.PLAN_FILE));rows=plan['rows'][:4]
    ledger=api.TaskLedger(path=path,plan=plan,counter=Counter())
    with ledger.transaction() as db:
        original=[tuple(r) for r in db.execute('SELECT * FROM requests ORDER BY request_id')]
    ledger.admit_block(rows)
    # The synthetic background charge crosses the cash start line. The active
    # frozen task still dispatches; actual input/output caps remain enforced.
    with ledger.transaction() as db:
        db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ('synthetic-prior','synthetic','agent',0,1,'unknown','x',250_000_000_000,None,None,None,None,0,None))
    wire={'max_tokens':50}
    ledger.reserve(rows[0]['slot_id'],'physical1','agent','logical1',1,wire)
    with pytest.raises(api.CashClosed):ledger.admit_block(plan['rows'][4:8])
    with ledger.transaction() as db:
        after=[tuple(r) for r in db.execute("SELECT * FROM requests WHERE request_id NOT IN ('synthetic-prior','physical1') ORDER BY request_id")]
    assert original==after


def test_retry_unknown_stays_in_shared_token_limit(tmp_path):
    path=tmp_path/'ledger.sqlite';shutil.copyfile(api.scope.LEDGER_FILE,path)
    plan=api.scope.load(reference(api.scope.PLAN_FILE));row=plan['rows'][0]
    ledger=api.TaskLedger(path=path,plan=plan,counter=Counter());ledger.admit_block([row])
    ledger.reserve(row['slot_id'],'physical1','agent','logical1',1,{'max_tokens':50})
    ledger.uncertain('physical1',{'type':'transient'})
    ledger.reserve(row['slot_id'],'physical2','agent','logical1',2,{'max_tokens':50})
    body={'usage':{'prompt_tokens':90,'completion_tokens':10,'total_tokens':100,
        'prompt_cache_hit_tokens':0,'prompt_cache_miss_tokens':90}}
    response=tmp_path/'response.json';response.write_text(json.dumps(body))
    ledger.settle('physical2',body,reference(response))
    value=ledger.physical(row['slot_id'])
    assert value['known_actual_tokens']==100 and value['uncertain_reserved_tokens']==150
    assert not value['usage_capture_complete']
    with ledger.transaction() as db:db.execute("UPDATE context_requests_v181 SET token_hold=4999900 WHERE request_id='physical1'")
    with pytest.raises(api.PreDispatchBudgetStopped):ledger.reserve(row['slot_id'],'physical3','agent','logical2',1,{'max_tokens':50})
