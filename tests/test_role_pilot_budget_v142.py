"""CPU-only shared400/member authority controls with temporary synthetic receipts."""
from pathlib import Path
import json
import sqlite3

import pytest

from proworksim import software_benchmark_deepseek_api_v142 as cash
from proworksim import software_benchmark_scope_v142 as scope
from proworksim.software_benchmark_candidates_v054 import reference


PANEL = reference(scope.PANEL_FILE)
ROWS = json.loads(Path(PANEL['path']).read_text())['rows']


def setup_views(tmp_path, concurrency=16):
    path = tmp_path/'pilot.sqlite'
    views = {g: cash.group_api(g, path, max_concurrency=concurrency, panel_ref=PANEL)
             for g in ('S1','FREE2','REVIEW2')}
    ledgers = {g: view.BudgetLedger(path) for g,view in views.items()}
    return path, views, ledgers


def request(row, n=1, member='member_001', **kwargs):
    return {'request_id': f"{row['slot_id']}:{member}:{n:04d}", 'slot_id':row['slot_id'],
            'condition':row['condition_id'], 'usage_id':'agent', 'request_sha256':'a'*64,
            'prompt_upper_bound':98304, 'max_output_tokens':32768, 'member_id':member, **kwargs}


def row_for(group):
    return next(r for r in ROWS if r['organization_id']==group)


def test_one_policy_one_cash_cap_for_all_arms(tmp_path):
    path,views,ledgers=setup_views(tmp_path)
    assert all(v.POLICY==views['S1'].POLICY for v in views.values())
    for group,ledger in ledgers.items():
        ledger.reserve(**request(row_for(group)))
    snapshots=[v.snapshot() for v in ledgers.values()]
    assert all(s==snapshots[0] for s in snapshots)
    assert snapshots[0]['cap_nanoyuan']==400*cash.NANOYUAN
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0]==3
        assert set(r[0] for r in db.execute('SELECT group_id FROM member_requests'))==set(views)


def test_global_cash_guard_cannot_be_bypassed_by_switching_group(tmp_path):
    path,_,ledgers=setup_views(tmp_path)
    first=request(row_for('S1'))
    ledgers['S1'].reserve(**first)
    # Synthetic near-cap prior receipt isolates integer boundary, no API or money.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=? WHERE request_id=?",
                   (399_900_000_000,first['request_id']))
    for group in ('FREE2','REVIEW2'):
        with pytest.raises(cash.original.BudgetStopped, match='cash_reservation_insufficient'):
            ledgers[group].reserve(**request(row_for(group)))


def test_global_inflight_gate_and_local_unknown(tmp_path):
    _,views,ledgers=setup_views(tmp_path, concurrency=1)
    first=request(row_for('S1'))
    ledgers['S1'].reserve(**first)
    with pytest.raises(cash.original.ConcurrencyBusy, match='concurrency_limit'):
        ledgers['FREE2'].reserve(**request(row_for('FREE2')))
    ledgers['S1'].uncertain(first['request_id'], {'reason':'scripted_local_unknown','shared_system_failure':False})
    ledgers['FREE2'].reserve(**request(row_for('FREE2')))
    assert ledgers['S1'].snapshot()['cap_nanoyuan']==views['S1'].CAP_NANOYUAN


def test_exact_member_group_panel_and_no_replay(tmp_path):
    _,_,ledgers=setup_views(tmp_path)
    row=row_for('S1')
    with pytest.raises(ValueError):
        ledgers['S1'].reserve(**request(row, member='member_002'))
    with pytest.raises(ValueError):
        ledgers['FREE2'].reserve(**request(row))
    changed=dict(row,slot_id=row['slot_id']+':new-attempt')
    with pytest.raises(ValueError, match='exact planned'):
        ledgers['S1'].reserve(**request(changed))
    ledgers['S1'].reserve(**request(row))
    with pytest.raises(cash.original.BudgetStopped, match='already_attempted'):
        ledgers['S1'].reserve(**request(row))


def test_team5m_includes_both_members_and_summary(tmp_path):
    path,_,ledgers=setup_views(tmp_path)
    row=row_for('FREE2')
    first=request(row)
    ledgers['FREE2'].reserve(**first)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE requests SET status='settled',settled_nanoyuan=1,usage_json=? WHERE request_id=?",
                   (json.dumps({'total_tokens':4_999_999}), first['request_id']))
    with pytest.raises(cash.original.BudgetStopped, match='shared_team_limit'):
        ledgers['FREE2'].reserve(**request(row,member='member_002',usage_id='condenser'))


def test_old_budget_database_rejected_before_mutation(tmp_path):
    path=tmp_path/'pilot.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY,value TEXT NOT NULL)')
        db.execute("INSERT INTO metadata VALUES ('policy','{}')")
    before=path.read_bytes()
    view=cash.group_api('S1',path,max_concurrency=16,panel_ref=PANEL)
    with pytest.raises(ValueError, match='another immutable budget policy'):
        view.BudgetLedger(path)
    assert path.read_bytes()==before


def test_plan_and_unapproved_runtime_gate():
    plan=scope.validate_plan(scope.load(reference(scope.PLAN_FILE)))
    assert len(plan['rows'])==120
    assert scope.LEDGER_FILES['S1']==scope.LEDGER_FILES['FREE2']==scope.LEDGER_FILES['REVIEW2']
    assert scope.CONSTRAINTS['maximum_containers']==568
    assert scope.CONSTRAINTS['system_parent_slice_created'] is False
    with pytest.raises(PermissionError, match='authorization is not sealed'):
        scope.require_allowed('v142.run')
