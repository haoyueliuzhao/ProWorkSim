"""Temporary SQLite controls only: no API, Docker, user-service mutation, or GPU."""
from contextlib import closing
import json
import sqlite3

import pytest

from proworksim import software_benchmark_cash_amendment_v122 as cash
from proworksim import software_benchmark_deepseek_api_v105 as old
from proworksim import software_benchmark_deepseek_api_v122 as new


def fixture_ledger(tmp_path):
    path = tmp_path / 'cash.sqlite'
    old.BudgetLedger(path, max_concurrency=16)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO requests(request_id,slot_id,condition,usage_id,status,
            request_sha256,reserved_nanoyuan,settled_nanoyuan,max_output_tokens,prompt_upper_bound,
            reserved_utc,settled_peak_nanoyuan) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ('old-settled', 'old-slot', 'PROJECT', 'agent', 'settled', '0'*64,
             334308764800, 334308764800, 100, 200, '2026-11-04T00:00:00+00:00', 334308764800))
        for index in range(2):
            db.execute("""INSERT INTO requests(request_id,slot_id,condition,usage_id,status,
                request_sha256,reserved_nanoyuan,max_output_tokens,prompt_upper_bound,reserved_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (f'old-uncertain-{index}', 'old-slot', 'PROJECT',
                'agent', 'uncertain', '1'*64, 5242880000, 100, 200, '2026-11-04T00:00:00+00:00'))
        db.execute("INSERT INTO metadata VALUES('system_failure_streak','0')")
    with closing(cash.open_read(path)) as db:
        before = cash.validate_before(db)
    cap = before['totals']['committed'] + cash.REMAINING_NANOYUAN
    grant = {'version': cash.VERSION, 'user_authorization': '将剩余可用预算调整为45元',
        'ledger': str(cash.LEDGER), 'authorized_remaining_nanoyuan': cash.REMAINING_NANOYUAN,
        'old_policy': cash.OLD_POLICY, 'new_policy': {**cash.OLD_POLICY, 'cap_nanoyuan': cap},
        'new_cap_nanoyuan': cap, 'increase_nanoyuan': cap - old.CAP_NANOYUAN, 'before': before}
    return path, grant


def apply(path, grant, owner=lambda: {'all_stopped': True}):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        try:
            result = cash.apply_policy_change(db, grant=grant, grant_ref={'sha256': 'test-grant'},
                backup_ref={'sha256': 'test-backup'}, require_quiet=owner)
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return result


def test_atomic_remaining_not_plus_45_and_private_runtime(tmp_path):
    path, grant = fixture_ledger(tmp_path)
    result = apply(path, grant)
    assert grant['new_cap_nanoyuan'] == 389794524800 != old.CAP_NANOYUAN + 45*old.NANOYUAN
    assert grant['increase_nanoyuan'] == 39794524800
    assert result['after']['preserved'] == grant['before']['preserved']
    assert result['after']['totals'] == grant['before']['totals']
    assert result['after']['totals']['uncertain'] == 10485760000
    api = new._api_view(grant['new_policy'], path)
    ledger = api.BudgetLedger(path)
    fake_transport = object()
    client = api.DeepSeekClient(ledger_path=path, api_key=None,
                               allowed_tool_names=[], transport=fake_transport)
    assert client.transport is fake_transport and client.ledger.max_concurrency == 16
    assert ledger.snapshot()['remaining_cny'] == 45.0
    assert api.POLICY == {**old.POLICY, 'cap_nanoyuan': 389794524800}
    assert old.POLICY['cap_nanoyuan'] == old.CAP_NANOYUAN == 350000000000
    with pytest.raises(ValueError, match='another immutable'):
        old.BudgetLedger(path, max_concurrency=16)
    # New runtime actually enforces the new cap, not just its displayed label.
    for index in range(8):
        ledger.reserve(request_id=f'new-{index}', slot_id='test-slot', condition='PROJECT',
                       usage_id='agent', request_sha256='2'*64, max_output_tokens=100,
                       prompt_upper_bound=200)
    with pytest.raises(api.ConcurrencyBusy, match='cash_reserved'):
        ledger.reserve(request_id='over-cap', slot_id='test-slot', condition='PROJECT',
                       usage_id='agent', request_sha256='2'*64, max_output_tokens=100,
                       prompt_upper_bound=200)
    assert ledger.snapshot()['attempts'] == 11


@pytest.mark.parametrize('violation', ['inflight', 'changed_request', 'changed_policy', 'live_owner'])
def test_refuse_unsafe_amendment_without_mutation(tmp_path, violation):
    path, grant = fixture_ledger(tmp_path)
    with sqlite3.connect(path) as db:
        if violation == 'inflight':
            db.execute("UPDATE requests SET status='reserved' WHERE request_id='old-uncertain-0'")
        elif violation == 'changed_request':
            db.execute("UPDATE requests SET condition='changed' WHERE request_id='old-settled'")
        elif violation == 'changed_policy':
            policy = {**cash.OLD_POLICY, 'cap_nanoyuan': 351*old.NANOYUAN}
            db.execute("UPDATE metadata SET value=? WHERE name='policy'", (old.transport._json(policy),))
    with closing(cash.open_read(path)) as db:
        before = cash.snapshot(db)

    def owner():
        if violation == 'live_owner':
            raise PermissionError('live owner')
        return {'all_stopped': True}

    with pytest.raises((ValueError, PermissionError)):
        apply(path, grant, owner)
    with closing(cash.open_read(path)) as db:
        assert cash.snapshot(db) == before
        assert not db.execute('SELECT 1 FROM metadata WHERE name=?', (cash.MARKER,)).fetchone()


def test_single_use_grant_and_no_other_policy_changes(tmp_path):
    path, grant = fixture_ledger(tmp_path)
    original_policy = json.loads(json.dumps(grant['new_policy']))
    grant['new_policy']['max_concurrency'] = 40
    with pytest.raises(ValueError, match='authorization'):
        apply(path, grant)
    grant['new_policy'] = original_policy
    result = apply(path, grant)
    with pytest.raises(ValueError):
        apply(path, grant)
    with closing(cash.open_read(path)) as db:
        assert cash.snapshot(db) == result['after']
